"""
NOMAD parser for OpenFOAM simulation cases.

NOMAD identifies OpenFOAM cases by the presence of system/controlDict.
The parser walks the case directory and populates the OpenFOAMCase schema.
"""
from __future__ import annotations

import logging
from pathlib import Path

from foamprisma_openfoam.parser.adapters.pyfoam_adapter import PyFoamAdapter

try:
    from nomad.datamodel import EntryArchive
    from nomad.parsing import MatchingParser
    _BaseParser = MatchingParser
except ImportError:
    _BaseParser = object  # type: ignore[assignment,misc]
    EntryArchive = object  # type: ignore[assignment,misc]

try:
    from foamprisma_openfoam.schema.case import OpenFOAMCase
    from foamprisma_openfoam.schema.mesh import OpenFOAMMesh
    from foamprisma_openfoam.schema.quality import MeshQuality
    from foamprisma_openfoam.schema.solver import SolverConfiguration
    from foamprisma_openfoam.schema.boundary import BoundaryConditions
    from foamprisma_openfoam.schema.results import SimulationResults
except ImportError:
    OpenFOAMCase = object  # type: ignore[assignment,misc]
    OpenFOAMMesh = MeshQuality = SolverConfiguration = object  # type: ignore
    BoundaryConditions = SimulationResults = object  # type: ignore

logger = logging.getLogger(__name__)


class OpenFOAMParser(_BaseParser):
    """
    Parses an OpenFOAM case directory into the FoamPrisma schema.

    Triggered when NOMAD finds a file matching `system/controlDict`.
    The case root is the grandparent of that file.
    """

    def parse(
        self,
        mainfile: str,
        archive: EntryArchive,
        child_archives=None,
    ) -> None:
        # Resolve case root: mainfile is .../system/controlDict
        control_dict_path = Path(mainfile)
        case_dir = control_dict_path.parent.parent
        case_name = case_dir.name

        logger.info(f'Parsing OpenFOAM case: {case_dir}')

        adapter = PyFoamAdapter(case_dir)

        # ── Top-level case ──
        case = OpenFOAMCase()
        case.case_name = case_name
        case.solver_name = adapter.get_solver_name()
        case.openfoam_version = _detect_openfoam_version(case_dir)
        case.case_type = _infer_case_type(adapter)

        # ── Solver configuration ──
        solver_cfg = SolverConfiguration()
        solver_cfg.application = adapter.get_solver_name()
        solver_cfg.start_time = adapter.get_start_time()
        solver_cfg.end_time = adapter.get_end_time()
        solver_cfg.delta_t = adapter.get_delta_t()
        solver_cfg.write_interval = adapter.get_write_interval()
        solver_cfg.turbulence_model = adapter.get_turbulence_model()
        solver_cfg.turbulence_type = adapter.get_turbulence_type()
        solver_cfg.n_correctors = adapter.get_n_correctors()
        rf = adapter.get_relaxation_factors()
        if rf:
            solver_cfg.relaxation_factors = rf
        case.solver_config = solver_cfg

        # ── Mesh ──
        mesh_stats = adapter.get_mesh_stats()
        if mesh_stats:
            mesh = OpenFOAMMesh()
            mesh.n_cells = mesh_stats.get('n_cells')
            mesh.n_faces = mesh_stats.get('n_faces')
            mesh.n_points = mesh_stats.get('n_points')
            mesh.n_internal_faces = mesh_stats.get('n_internal_faces')
            mesh.mesh_type = _detect_mesh_type(case_dir)
            # Count boundary patches from polyMesh/boundary
            patches = adapter.get_boundary_patches()
            mesh.n_boundary_patches = len(patches)
            case.mesh = mesh

            # Mesh quality if available in mesh_stats
            mq_keys = {'max_non_orthogonality', 'avg_non_orthogonality',
                       'max_skewness', 'mesh_ok'}
            if mq_keys & set(mesh_stats.keys()):
                mq = MeshQuality()
                mq.max_non_orthogonality = mesh_stats.get('max_non_orthogonality')
                mq.average_non_orthogonality = mesh_stats.get('avg_non_orthogonality')
                mq.max_skewness = mesh_stats.get('max_skewness')
                mq.mesh_ok = mesh_stats.get('mesh_ok')
                case.mesh_quality = mq

        # ── Boundary conditions ──
        patches = adapter.get_boundary_patches()
        for patch in patches:
            bc = BoundaryConditions()
            bc.patch_name = patch.get('patch_name')
            bc.patch_type = patch.get('patch_type')
            case.boundary_conditions.append(bc)

        # ── Results (if solver has run) ──
        results = _parse_results(case_dir, adapter.get_solver_name())
        if results:
            case.results = results

        archive.data = case


# ── Helpers ──

def _detect_openfoam_version(case_dir: Path) -> str:
    """Try to detect the OpenFOAM version from foam.foam or case files."""
    # Look for a version tag in system/controlDict header
    ctrl = case_dir / 'system' / 'controlDict'
    if ctrl.exists():
        text = ctrl.read_text(errors='replace')[:500]
        import re
        m = re.search(r'version\s+([\d.]+)', text)
        if m:
            return m.group(1)
    return 'unknown'


def _detect_mesh_type(case_dir: Path) -> str:
    """Heuristically detect the mesh generation method."""
    system = case_dir / 'system'
    if (system / 'snappyHexMeshDict').exists():
        return 'snappyHexMesh'
    if (system / 'blockMeshDict').exists():
        return 'blockMesh'
    if (system / 'cfMeshDict').exists() or (system / 'meshDict').exists():
        return 'cfMesh'
    if (case_dir / 'constant' / 'polyMesh').exists():
        return 'imported'
    return 'unknown'


def _infer_case_type(adapter: PyFoamAdapter) -> str:
    """Infer physical case type from solver name."""
    solver = (adapter.get_solver_name() or '').lower()
    incompressible = {'simplefoam', 'pisofoam', 'pimplefoam', 'sonicfoam',
                      'icofoam', 'nonlinearsolverfoam'}
    compressible = {'rhosimplefoam', 'rhopimplefoam', 'sonicfoam',
                    'rhocentralfoam', 'dbnssfoam'}
    multiphase = {'interfoam', 'multiphaseinterfoam', 'cavitatingfoam',
                  'driftfluxfoam', 'twophaseeulerfoam'}
    combustion = {'reactingfoam', 'firingsimfoam', 'chemistrysolver'}
    heat = {'buoyantpimplefoam', 'buoyantsimplefoam', 'chtmultiregionfoam'}

    if solver in incompressible:
        return 'incompressible'
    if solver in compressible:
        return 'compressible'
    if solver in multiphase:
        return 'multiphase'
    if solver in combustion:
        return 'combustion'
    if solver in heat:
        return 'heat-transfer'
    return 'other'


def _parse_results(case_dir: Path, solver_name: str) -> SimulationResults | None:
    """Look for a solver log and extract basic convergence info."""
    import re

    solver_name = solver_name or ''
    candidates = [
        case_dir / f'log.{solver_name}',
        case_dir / f'{solver_name}.log',
        case_dir / 'log',
    ]
    log_path = next((p for p in candidates if p.exists()), None)
    if log_path is None:
        return None

    text = log_path.read_text(errors='replace')

    results = SimulationResults()
    results.log_path = str(log_path.relative_to(case_dir))

    # Convergence
    results.converged = 'SIMPLE solution converged' in text or 'solution converged' in text.lower()

    # Wall time
    m = re.search(r'ExecutionTime\s*=\s*([\d.]+)\s*s', text)
    if m:
        results.wall_time_seconds = float(m.group(1))

    # Final residuals
    pattern = r'Solving for (\w+), Initial residual = [\d.e+-]+, Final residual = ([\d.e+-]+)'
    matches = re.findall(pattern, text)
    if matches:
        final = {}
        for field, res in matches:
            final[field] = float(res)
        import json
        results.final_residuals_json = json.dumps(final)

    # Divergence check
    diverged = 'FOAM FATAL ERROR' in text or 'Floating point exception' in text
    if diverged:
        results.converged = False

    # Iteration count (time steps written to disk)
    time_dirs = sorted(
        (d for d in case_dir.iterdir()
         if d.is_dir() and _is_numeric(d.name) and d.name != '0'),
        key=lambda d: float(d.name),
    )
    results.n_iterations = len(time_dirs)
    if time_dirs:
        results.final_time = float(time_dirs[-1].name)

    return results


def _is_numeric(name: str) -> bool:
    try:
        float(name)
        return True
    except ValueError:
        return False
