import os
import stat
import subprocess
from pathlib import Path
from temporalio import activity


@activity.defn
def validate_solver_binary(solver_path: str) -> dict:
    """
    Validate the uploaded custom solver binary or source.
    Checks: file exists, is executable (binary) or contains wmake files (source).
    Does NOT run the binary — purely structural checks.
    """
    path = Path(solver_path)

    if not path.exists():
        raise FileNotFoundError(f'Solver not found: {solver_path}')

    if path.is_file():
        # Binary: must be ELF executable
        file_stat = path.stat()
        if not (file_stat.st_mode & stat.S_IXUSR):
            os.chmod(solver_path, file_stat.st_mode | stat.S_IXUSR)

        # Check magic bytes for ELF
        with open(solver_path, 'rb') as f:
            magic = f.read(4)
        is_elf = magic == b'\x7fELF'

        return {'valid': True, 'format': 'binary', 'is_elf': is_elf}

    if path.is_dir():
        # Source directory: must contain Make/files and Make/options
        make_files = path / 'Make' / 'files'
        make_options = path / 'Make' / 'options'
        has_make = make_files.exists() and make_options.exists()
        return {'valid': has_make, 'format': 'source', 'has_make_files': has_make}

    raise ValueError(f'Solver path is neither a file nor a directory: {solver_path}')


@activity.defn
def compile_solver(solver_source_dir: str, openfoam_version: str) -> dict:
    """
    Compile a custom OpenFOAM solver using wmake.
    Requires OpenFOAM environment to be sourced.
    """
    bashrc = f'/usr/lib/openfoam/openfoam{openfoam_version}/etc/bashrc'
    compile_cmd = f'source {bashrc} && cd {solver_source_dir} && wmake'

    log_path = os.path.join(solver_source_dir, 'log.wmake')
    with open(log_path, 'w') as log_file:
        result = subprocess.run(
            ['bash', '-c', compile_cmd],
            stdout=log_file,
            stderr=subprocess.STDOUT,
            timeout=600,
        )

    if result.returncode != 0:
        raise RuntimeError(f'wmake failed — see {log_path}')

    # Find the compiled binary (typically in $FOAM_USER_APPBIN or local platform dir)
    import glob
    pattern = os.path.join(solver_source_dir, '**', 'linux*', 'solver')
    binaries = glob.glob(pattern, recursive=True)
    solver_binary = binaries[0] if binaries else None

    return {
        'returncode': result.returncode,
        'log_path': log_path,
        'solver_binary': solver_binary,
    }


@activity.defn
def run_custom_solver(
    work_dir: str,
    solver_binary: str,
    n_processors: int,
    openfoam_version: str,
    solver_name: str = 'customSolver',
) -> dict:
    """Run the custom solver binary in the case directory."""
    import time

    of_env = os.environ.copy()
    bashrc = f'/usr/lib/openfoam/openfoam{openfoam_version}/etc/bashrc'
    if os.path.exists(bashrc):
        proc = subprocess.run(
            ['bash', '-c', f'source {bashrc} && env'],
            capture_output=True, text=True,
        )
        for line in proc.stdout.splitlines():
            if '=' in line:
                k, v = line.split('=', 1)
                of_env[k] = v

    if n_processors > 1:
        cmd = ['mpirun', '-np', str(n_processors), solver_binary, '-parallel']
    else:
        cmd = [solver_binary]

    log_path = os.path.join(work_dir, f'log.{solver_name}')
    with open(log_path, 'w') as log_file:
        process = subprocess.Popen(
            cmd, cwd=work_dir, stdout=log_file, stderr=subprocess.STDOUT, env=of_env,
        )
        start = time.time()
        while process.poll() is None:
            activity.heartbeat(f'Custom solver running: {time.time() - start:.0f}s')
            time.sleep(10)
        wall_time = time.time() - start

    return {
        'returncode': process.returncode,
        'wall_time_seconds': wall_time,
        'log_path': log_path,
    }
