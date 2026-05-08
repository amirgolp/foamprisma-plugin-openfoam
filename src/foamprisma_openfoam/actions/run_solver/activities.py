import os
import shutil
import subprocess
from pathlib import Path

from temporalio import activity


def _resolve_case_dir(upload_id: str, entry_id: str) -> tuple[Path, str]:
    """
    Resolve the on-disk path of an OpenFOAM case directory and the case dir
    relative to the upload root.

    The plugin's parser matches `system/controlDict`, so an entry's mainfile
    is `<case_dir>/system/controlDict`. The case dir is therefore the
    grandparent of the mainfile.
    """
    from nomad.files import StagingUploadFiles
    from nomad.processing import Entry

    entry = Entry.objects(entry_id=entry_id).first()
    if entry is None:
        raise ValueError(f'Entry {entry_id} not found')
    if entry.upload_id != upload_id:
        raise ValueError(
            f'Entry {entry_id} belongs to upload {entry.upload_id}, not {upload_id}'
        )

    mainfile_rel = Path(entry.mainfile)
    case_dir_rel = mainfile_rel.parent.parent
    if case_dir_rel == Path('.'):
        raise ValueError(
            f'Mainfile {mainfile_rel} is not under a case directory '
            '(expected <case>/system/controlDict).'
        )

    upload_files = StagingUploadFiles(upload_id)
    case_os_path = Path(upload_files.raw_file_object(str(case_dir_rel)).os_path)
    return case_os_path, str(case_dir_rel)


@activity.defn
def prepare_case(upload_id: str, case_entry_id: str) -> dict:
    """
    Copy case files from NOMAD storage to the OpenFOAM working directory.
    Validate case structure (system/, constant/ exist; system/controlDict present).

    Takes primitive args (not RunSolverInput) so other workflows
    (generate_mesh, check_mesh) can reuse this activity without leaking
    solver-specific fields through Temporal serialization.
    """
    case_path, case_dir_rel = _resolve_case_dir(upload_id, case_entry_id)

    work_dir = Path(f'/data/openfoam-cases/{upload_id}/{case_entry_id}')
    work_dir.mkdir(parents=True, exist_ok=True)
    shutil.copytree(case_path, work_dir, dirs_exist_ok=True)

    required_dirs = ['system', 'constant']
    missing = [d for d in required_dirs if not (work_dir / d).is_dir()]
    if missing:
        raise ValueError(f'Invalid OpenFOAM case: missing {missing}')

    if not (work_dir / 'system' / 'controlDict').exists():
        raise ValueError('Missing system/controlDict')

    return {
        'work_dir': str(work_dir),
        'case_dir_rel': case_dir_rel,
        'case_valid': True,
    }


@activity.defn
def decompose_case(work_dir: str, n_processors: int) -> dict:
    """Run decomposePar if parallel run requested."""
    if n_processors <= 1:
        return {'decomposed': False, 'n_processors': 1}

    result = subprocess.run(
        ['decomposePar', '-force'],
        cwd=work_dir,
        capture_output=True,
        text=True,
        timeout=300,
    )
    if result.returncode != 0:
        raise RuntimeError(f'decomposePar failed: {result.stderr}')

    return {'decomposed': True, 'n_processors': n_processors}


@activity.defn
def run_openfoam_solver(
    work_dir: str,
    solver_name: str,
    solver_type: str,
    custom_solver_path: str,
    n_processors: int,
    openfoam_version: str,
) -> dict:
    """
    Execute the OpenFOAM solver. Long-running activity with heartbeats.
    """
    of_env = os.environ.copy()
    of_bashrc = f'/usr/lib/openfoam/openfoam{openfoam_version}/etc/bashrc'
    if os.path.exists(of_bashrc):
        source_cmd = f'source {of_bashrc} && env'
        proc = subprocess.run(['bash', '-c', source_cmd], capture_output=True, text=True)
        for line in proc.stdout.splitlines():
            if '=' in line:
                k, v = line.split('=', 1)
                of_env[k] = v

    solver_cmd = custom_solver_path if (solver_type == 'custom' and custom_solver_path) else solver_name

    if n_processors > 1:
        cmd = ['mpirun', '-np', str(n_processors), solver_cmd, '-parallel']
    else:
        cmd = [solver_cmd]

    log_path = os.path.join(work_dir, f'log.{solver_name}')

    import time
    with open(log_path, 'w') as log_file:
        process = subprocess.Popen(
            cmd, cwd=work_dir, stdout=log_file, stderr=subprocess.STDOUT, env=of_env,
        )
        start = time.time()
        while process.poll() is None:
            elapsed = time.time() - start
            activity.heartbeat(f'Running {solver_name}: {elapsed:.0f}s elapsed')
            time.sleep(10)
        wall_time = time.time() - start

    return {
        'returncode': process.returncode,
        'wall_time_seconds': wall_time,
        'log_path': log_path,
    }


@activity.defn
def parse_solver_results(log_path: str) -> dict:
    """Parse solver log for final residuals and convergence status."""
    import re

    content = Path(log_path).read_text(errors='replace')

    pattern = r'Solving for (\w+), Initial residual = [\d.e+-]+, Final residual = ([\d.e+-]+)'
    final_residuals = {}
    for field, final in re.findall(pattern, content):
        final_residuals[field] = float(final)

    completed = any(line.strip() == 'End' for line in content.split('\n')[-10:])

    # Solver divergence detection. Both heuristics must NOT also match the
    # benign 'trapFpe: Floating point exception trapping enabled' line that
    # OpenFOAM logs at startup whenever FOAM_SIGFPE is set.
    has_fatal = 'FOAM FATAL ERROR' in content
    has_fpe = any(
        'floating point exception' in line.lower() and 'trapping enabled' not in line.lower()
        for line in content.splitlines()
    )
    diverged = has_fatal or has_fpe

    # Successful runs take priority over divergence heuristics: if the solver
    # printed its 'End' marker the run finished, regardless of any earlier
    # transient warnings.
    if completed:
        status = 'completed'
        diverged = False
    elif diverged:
        status = 'diverged'
    else:
        status = 'incomplete'

    return {'status': status, 'final_residuals': final_residuals, 'diverged': diverged}


@activity.defn
def upload_results_to_nomad(
    upload_id: str, user_id: str, work_dir: str, case_entry_id: str
) -> dict:
    """
    Copy solver outputs from the work directory back into the NOMAD staging
    upload and trigger reprocessing of the case entry so the parser picks up
    the new results.
    """
    from nomad.processing import Entry

    case_path, _ = _resolve_case_dir(upload_id, case_entry_id)
    src = Path(work_dir)
    if not src.is_dir():
        raise ValueError(f'Work dir {work_dir} not found')

    shutil.copytree(src, case_path, dirs_exist_ok=True)

    entry = Entry.objects(entry_id=case_entry_id).first()
    if entry is None:
        raise ValueError(f'Entry {case_entry_id} not found after solver run')
    entry.process_entry()

    return {'result_entry_id': case_entry_id, 'uploaded': True}
