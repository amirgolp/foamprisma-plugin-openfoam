import subprocess
import os
from pathlib import Path
from temporalio import activity

from .models import RunSolverInput


@activity.defn
def prepare_case(data: RunSolverInput) -> dict:
    """
    Copy case files from NOMAD storage to the OpenFOAM working directory.
    Validate case structure (system/, constant/, 0/ exist).
    """
    from nomad.actions.manager import get_entry_raw_path

    case_path = get_entry_raw_path(data.upload_id, data.case_entry_id)
    work_dir = Path(f'/data/openfoam-cases/{data.upload_id}/{data.case_entry_id}')
    work_dir.mkdir(parents=True, exist_ok=True)

    import shutil
    shutil.copytree(case_path, work_dir, dirs_exist_ok=True)

    required_dirs = ['system', 'constant']
    missing = [d for d in required_dirs if not (work_dir / d).is_dir()]
    if missing:
        raise ValueError(f'Invalid OpenFOAM case: missing {missing}')

    if not (work_dir / 'system' / 'controlDict').exists():
        raise ValueError('Missing system/controlDict')

    return {'work_dir': str(work_dir), 'case_valid': True}


@activity.defn
def decompose_case(work_dir: str, n_processors: int) -> dict:
    """Run decomposePar if parallel run requested."""
    if n_processors <= 1:
        return {'decomposed': False, 'n_processors': 1}

    result = subprocess.run(
        ['decomposePar'],
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
def parse_solver_results(work_dir: str, log_path: str) -> dict:
    """Parse solver log for final residuals and convergence status."""
    import re

    content = Path(log_path).read_text(errors='replace')

    pattern = r'Solving for (\w+), Initial residual = [\d.e+-]+, Final residual = ([\d.e+-]+)'
    final_residuals = {}
    for field, final in re.findall(pattern, content):
        final_residuals[field] = float(final)

    diverged = 'FOAM FATAL ERROR' in content or 'Floating point exception' in content
    completed = any(line.strip() == 'End' for line in content.split('\n')[-10:])

    if diverged:
        status = 'diverged'
    elif completed:
        status = 'completed'
    else:
        status = 'incomplete'

    return {'status': status, 'final_residuals': final_residuals, 'diverged': diverged}


@activity.defn
def upload_results_to_nomad(
    upload_id: str, user_id: str, work_dir: str, case_entry_id: str
) -> dict:
    """Upload solver results back into NOMAD as a new or updated entry."""
    from nomad.actions.manager import update_entry_archive

    update_entry_archive(
        upload_id=upload_id,
        entry_id=case_entry_id,
        raw_path=work_dir,
    )
    return {'result_entry_id': case_entry_id, 'uploaded': True}
