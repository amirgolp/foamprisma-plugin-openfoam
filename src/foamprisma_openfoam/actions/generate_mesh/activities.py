"""
Temporal activities for mesh generation.
Each activity is an atomic, retryable unit of work.
"""

import subprocess
import re
import os
from pathlib import Path
from temporalio import activity


def _of_env(openfoam_version: str = '2206') -> dict:
    env = os.environ.copy()
    bashrc = f'/usr/lib/openfoam/openfoam{openfoam_version}/etc/bashrc'
    if os.path.exists(bashrc):
        proc = subprocess.run(
            ['bash', '-c', f'source {bashrc} && env'],
            capture_output=True, text=True,
        )
        for line in proc.stdout.splitlines():
            if '=' in line:
                k, v = line.split('=', 1)
                env[k] = v
    return env


@activity.defn
def detect_mesh_tool(work_dir: str, force_snappy: bool) -> str:
    """Detect which mesh tool to use based on available dict files."""
    work = Path(work_dir)

    if force_snappy and (work / 'system/snappyHexMeshDict').exists():
        return 'snappyHexMesh'
    elif (work / 'system/blockMeshDict').exists():
        return 'blockMesh'
    elif (work / 'system/snappyHexMeshDict').exists():
        return 'snappyHexMesh'
    else:
        raise FileNotFoundError(
            'No blockMeshDict or snappyHexMeshDict found in system/'
        )


@activity.defn
def run_block_mesh(work_dir: str) -> dict:
    """Run blockMesh to generate a structured mesh."""
    activity.heartbeat('Starting blockMesh...')
    env = _of_env()

    result = subprocess.run(
        ['blockMesh'],
        cwd=work_dir,
        capture_output=True,
        text=True,
        env=env,
        timeout=600,
    )

    log_path = Path(work_dir) / 'log.blockMesh'
    log_path.write_text(result.stdout + result.stderr)

    if result.returncode != 0:
        raise RuntimeError(f'blockMesh failed:\n{result.stderr[-500:]}')

    activity.heartbeat('blockMesh complete')
    return {'log_path': str(log_path), 'tool': 'blockMesh'}


@activity.defn
def run_snappy_hex_mesh(work_dir: str) -> dict:
    """Run snappyHexMesh. Requires blockMesh to have run first for base mesh."""
    activity.heartbeat('Starting snappyHexMesh...')
    env = _of_env()

    # snappyHexMesh needs a base mesh — run blockMesh first if needed
    poly_mesh = Path(work_dir) / 'constant/polyMesh'
    if not poly_mesh.exists():
        activity.heartbeat('Running blockMesh for base mesh...')
        pre = subprocess.run(
            ['blockMesh'], cwd=work_dir,
            capture_output=True, text=True, env=env, timeout=600,
        )
        if pre.returncode != 0:
            raise RuntimeError(f'Base blockMesh failed:\n{pre.stderr[-500:]}')

    result = subprocess.run(
        ['snappyHexMesh', '-overwrite'],
        cwd=work_dir,
        capture_output=True,
        text=True,
        env=env,
        timeout=3600,
    )

    log_path = Path(work_dir) / 'log.snappyHexMesh'
    log_path.write_text(result.stdout + result.stderr)

    if result.returncode != 0:
        raise RuntimeError(f'snappyHexMesh failed:\n{result.stderr[-500:]}')

    activity.heartbeat('snappyHexMesh complete')
    return {'log_path': str(log_path), 'tool': 'snappyHexMesh'}


@activity.defn
def run_check_mesh(work_dir: str) -> dict:
    """Run checkMesh and parse results."""
    activity.heartbeat('Running checkMesh...')
    env = _of_env()

    result = subprocess.run(
        ['checkMesh'],
        cwd=work_dir,
        capture_output=True,
        text=True,
        env=env,
        timeout=300,
    )

    log_path = Path(work_dir) / 'log.checkMesh'
    output = result.stdout + result.stderr
    log_path.write_text(output)

    # Parse key metrics
    parsed = {'mesh_ok': 'Mesh OK' in output}

    cells_match = re.search(r'cells:\s+(\d+)', output)
    if cells_match:
        parsed['n_cells'] = int(cells_match.group(1))

    faces_match = re.search(r'faces:\s+(\d+)', output)
    if faces_match:
        parsed['n_faces'] = int(faces_match.group(1))

    points_match = re.search(r'points:\s+(\d+)', output)
    if points_match:
        parsed['n_points'] = int(points_match.group(1))

    non_ortho = re.search(r'Max non-orthogonality\s*=\s*([\d.]+)', output, re.IGNORECASE)
    if non_ortho:
        parsed['max_non_orthogonality'] = float(non_ortho.group(1))

    skewness = re.search(r'Max skewness\s*=\s*([\d.]+)', output, re.IGNORECASE)
    if skewness:
        parsed['max_skewness'] = float(skewness.group(1))

    parsed['log_path'] = str(log_path)
    return parsed
