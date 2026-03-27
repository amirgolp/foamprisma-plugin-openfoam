"""
PyFoam-based adapter for reading OpenFOAM dictionary files.

Parses:
  - system/controlDict   → time controls, solver name, write settings
  - system/fvSolution    → solver algorithms, pressure-velocity coupling
  - system/fvSchemes     → discretization schemes (informational)
  - constant/polyMesh/   → mesh statistics (via foamInfo-style fallback)
  - constant/turbulenceProperties or RASProperties → turbulence model
"""

import re
from pathlib import Path
from typing import Optional


def _read_foam_file(path: Path) -> Optional[dict]:
    """
    Read an OpenFOAM dictionary file using PyFoam.
    Falls back to a lightweight regex-based reader if PyFoam is unavailable.
    Returns a nested dict, or None if the file does not exist.
    """
    if not path.exists():
        return None

    try:
        from PyFoam.RunDictionary.ParsedParameterFile import ParsedParameterFile
        pf = ParsedParameterFile(str(path), noHeader=True)
        return dict(pf.content)
    except Exception:
        pass

    # Lightweight fallback: parse key value; pairs (handles simple cases)
    return _parse_foam_dict_simple(path.read_text(errors='replace'))


def _parse_foam_dict_simple(text: str) -> dict:
    """
    Minimal OpenFOAM dict parser for key-value pairs at the top level.
    Handles: key value; and key { ... } blocks (non-recursive).
    """
    result = {}
    # Strip C-style comments
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)
    text = re.sub(r'//[^\n]*', '', text)

    # Match key value; pairs
    for match in re.finditer(r'^\s*(\w+)\s+([^;{}\n]+);', text, re.MULTILINE):
        key, value = match.group(1), match.group(2).strip()
        # Try numeric conversion
        try:
            result[key] = int(value)
        except ValueError:
            try:
                result[key] = float(value)
            except ValueError:
                result[key] = value

    # Match simple sub-dict blocks: key { ... }
    for match in re.finditer(r'(\w+)\s*\{([^{}]*)\}', text, re.DOTALL):
        key, body = match.group(1), match.group(2)
        result[key] = _parse_foam_dict_simple(body)

    return result


class PyFoamAdapter:
    """
    Adapter that reads an OpenFOAM case directory and extracts structured data
    suitable for populating the FoamPrisma schemas.
    """

    def __init__(self, case_dir: Path):
        self.case_dir = Path(case_dir)
        self._control_dict: Optional[dict] = None
        self._fv_solution: Optional[dict] = None
        self._fv_schemes: Optional[dict] = None
        self._turbulence_props: Optional[dict] = None

    # ── Lazy-loaded dictionaries ──

    @property
    def control_dict(self) -> dict:
        if self._control_dict is None:
            self._control_dict = _read_foam_file(
                self.case_dir / 'system' / 'controlDict'
            ) or {}
        return self._control_dict

    @property
    def fv_solution(self) -> dict:
        if self._fv_solution is None:
            self._fv_solution = _read_foam_file(
                self.case_dir / 'system' / 'fvSolution'
            ) or {}
        return self._fv_solution

    @property
    def fv_schemes(self) -> dict:
        if self._fv_schemes is None:
            self._fv_schemes = _read_foam_file(
                self.case_dir / 'system' / 'fvSchemes'
            ) or {}
        return self._fv_schemes

    @property
    def turbulence_props(self) -> dict:
        if self._turbulence_props is None:
            # Try ESI naming first, then foundation naming
            for name in ('turbulenceProperties', 'RASProperties', 'LESProperties'):
                props = _read_foam_file(self.case_dir / 'constant' / name)
                if props is not None:
                    self._turbulence_props = props
                    break
            if self._turbulence_props is None:
                self._turbulence_props = {}
        return self._turbulence_props

    # ── Extracted data ──

    def get_solver_name(self) -> Optional[str]:
        """Application name from controlDict."""
        return str(self.control_dict.get('application', '')) or None

    def get_start_time(self) -> Optional[float]:
        val = self.control_dict.get('startTime')
        try:
            return float(val)
        except (TypeError, ValueError):
            return None

    def get_end_time(self) -> Optional[float]:
        val = self.control_dict.get('endTime')
        try:
            return float(val)
        except (TypeError, ValueError):
            return None

    def get_delta_t(self) -> Optional[float]:
        val = self.control_dict.get('deltaT')
        try:
            return float(val)
        except (TypeError, ValueError):
            return None

    def get_write_interval(self) -> Optional[float]:
        val = self.control_dict.get('writeInterval')
        try:
            return float(val)
        except (TypeError, ValueError):
            return None

    def get_max_co(self) -> Optional[float]:
        val = self.control_dict.get('maxCo')
        try:
            return float(val)
        except (TypeError, ValueError):
            return None

    def get_pv_coupling(self) -> Optional[str]:
        """Detect SIMPLE/PISO/PIMPLE from fvSolution."""
        for algo in ('SIMPLE', 'PISO', 'PIMPLE', 'COUPLED'):
            if algo in self.fv_solution:
                return algo
        return 'unknown'

    def get_n_correctors(self) -> Optional[int]:
        for key in ('PISO', 'PIMPLE'):
            block = self.fv_solution.get(key)
            if isinstance(block, dict):
                val = block.get('nCorrectors')
                try:
                    return int(val)
                except (TypeError, ValueError):
                    pass
        return None

    def get_n_outer_correctors(self) -> Optional[int]:
        block = self.fv_solution.get('PIMPLE', {})
        if isinstance(block, dict):
            val = block.get('nOuterCorrectors')
            try:
                return int(val)
            except (TypeError, ValueError):
                pass
        return None

    def get_relaxation_factors(self) -> dict:
        """Return {'p': float, 'U': float, ...} relaxation factors."""
        rf_block = self.fv_solution.get('relaxationFactors', {})
        if not isinstance(rf_block, dict):
            return {}

        # ESI format: fields { p 0.3; } equations { U 0.7; }
        result = {}
        for sub in ('fields', 'equations'):
            sub_block = rf_block.get(sub, {})
            if isinstance(sub_block, dict):
                result.update(sub_block)
        # Foundation format: direct key-value pairs
        for k, v in rf_block.items():
            if k not in ('fields', 'equations'):
                result[k] = v
        return {k: float(v) for k, v in result.items() if _is_float(v)}

    def get_turbulence_model(self) -> Optional[str]:
        """Detect turbulence model name from turbulenceProperties."""
        props = self.turbulence_props

        # ESI: simulationType RAS; RAS { RASModel kOmegaSST; }
        sim_type = str(props.get('simulationType', '')).strip()
        if sim_type == 'laminar':
            return 'laminar'

        for block_key in ('RAS', 'LES'):
            block = props.get(block_key, {})
            if isinstance(block, dict):
                model = str(block.get(f'{block_key}Model', '')).strip()
                if model:
                    return model

        # Foundation: RASModel kOmegaSST;
        for key in ('RASModel', 'LESModel'):
            model = str(props.get(key, '')).strip()
            if model:
                return model

        return 'unknown'

    def get_turbulence_type(self) -> Optional[str]:
        props = self.turbulence_props
        sim_type = str(props.get('simulationType', '')).strip()
        if sim_type in ('RAS', 'LES', 'laminar'):
            return sim_type
        return 'unknown'

    def get_mesh_stats(self) -> dict:
        """
        Parse mesh statistics from checkMesh log or constant/polyMesh/owner.
        Returns a dict with n_cells, n_faces, n_points, n_internal_faces.
        """
        stats = {}

        # Try to read from a pre-existing checkMesh log
        for log_name in ('log.checkMesh', 'checkMesh.log'):
            log_path = self.case_dir / log_name
            if log_path.exists():
                stats = _parse_check_mesh_log(log_path.read_text(errors='replace'))
                if stats:
                    return stats

        # Fallback: count from constant/polyMesh/owner header
        owner_path = self.case_dir / 'constant' / 'polyMesh' / 'owner'
        if owner_path.exists():
            header = owner_path.read_text(errors='replace')[:2000]
            for key, pattern in [
                ('n_cells', r'nCells\s+(\d+)'),
                ('n_faces', r'nFaces\s+(\d+)'),
                ('n_internal_faces', r'nInternalFaces\s+(\d+)'),
                ('n_points', r'nPoints\s+(\d+)'),
            ]:
                m = re.search(pattern, header)
                if m:
                    stats[key] = int(m.group(1))

        return stats

    def get_boundary_patches(self) -> list:
        """
        Read constant/polyMesh/boundary to get patch names and types.
        Returns a list of dicts with 'patch_name' and 'patch_type'.
        """
        boundary_path = self.case_dir / 'constant' / 'polyMesh' / 'boundary'
        if not boundary_path.exists():
            return []

        text = boundary_path.read_text(errors='replace')
        patches = []
        for m in re.finditer(
            r'(\w+)\s*\{[^}]*type\s+(\w+)\s*;', text, re.DOTALL
        ):
            patches.append({'patch_name': m.group(1), 'patch_type': m.group(2)})
        return patches


# ── Helpers ──

def _is_float(value) -> bool:
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False


def _parse_check_mesh_log(text: str) -> dict:
    """Extract mesh statistics from a checkMesh output log."""
    stats = {}
    patterns = {
        'n_cells': r'cells:\s+(\d+)',
        'n_faces': r'faces:\s+(\d+)',
        'n_points': r'points:\s+(\d+)',
        'n_internal_faces': r'internal faces:\s+(\d+)',
        'max_non_orthogonality': r'Max non-orthogonality\s*=\s*([\d.e+-]+)',
        'avg_non_orthogonality': r'average non-orthogonality\s*=\s*([\d.e+-]+)',
        'max_skewness': r'Max skewness\s*=\s*([\d.e+-]+)',
    }
    for key, pattern in patterns.items():
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            val = m.group(1)
            try:
                stats[key] = int(val)
            except ValueError:
                stats[key] = float(val)

    stats['mesh_ok'] = 'Mesh OK.' in text or 'No errors found.' in text
    return stats
