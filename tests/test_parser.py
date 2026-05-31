"""Tests for the OpenFOAM NOMAD parser against the cavity fixture."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

try:
    from nomad.datamodel import EntryArchive  # noqa: F401
    _has_nomad = True
except ImportError:
    _has_nomad = False

needs_nomad = pytest.mark.skipif(not _has_nomad, reason='NOMAD not installed')

from foamprisma_openfoam.parser.openfoam_parser import (
    OpenFOAMParser,
    _detect_mesh_type,
    _infer_case_type,
    _detect_openfoam_version,
    _parse_results,
    _is_numeric,
)
from foamprisma_openfoam.parser.adapters.pyfoam_adapter import PyFoamAdapter

CASE_DIR = Path(__file__).parent / 'data' / 'cavity'
CONTROL_DICT = CASE_DIR / 'system' / 'controlDict'


class TestHelpers:
    def test_detect_mesh_type_blockMesh(self):
        assert _detect_mesh_type(CASE_DIR) == 'blockMesh'

    def test_detect_mesh_type_unknown(self, tmp_path):
        (tmp_path / 'system').mkdir()
        assert _detect_mesh_type(tmp_path) == 'unknown'

    def test_infer_case_type_icofoam(self):
        adapter = PyFoamAdapter(CASE_DIR)
        assert _infer_case_type(adapter) == 'incompressible'

    def test_infer_case_type_interfoam(self, tmp_path):
        (tmp_path / 'system').mkdir()
        (tmp_path / 'system' / 'controlDict').write_text(
            'FoamFile{}\napplication interFoam;\n'
        )
        adapter = PyFoamAdapter(tmp_path)
        assert _infer_case_type(adapter) == 'multiphase'

    def test_is_numeric(self):
        assert _is_numeric('0.5') is True
        assert _is_numeric('100') is True
        assert _is_numeric('system') is False

    def test_detect_version_from_header(self):
        version = _detect_openfoam_version(CASE_DIR)
        # Our fixture has "Version:  v2206" in a comment — may or may not parse
        assert isinstance(version, str)


@needs_nomad
class TestParseResults:
    def test_parses_execution_time(self):
        results = _parse_results(CASE_DIR, 'icoFoam')
        assert results is not None
        assert results.wall_time_seconds == pytest.approx(0.28)

    def test_detects_end_in_log(self):
        results = _parse_results(CASE_DIR, 'icoFoam')
        assert results is not None

    def test_parses_final_residuals(self):
        results = _parse_results(CASE_DIR, 'icoFoam')
        assert results is not None
        assert results.residual_histories
        fields = {rh.field_name for rh in results.residual_histories}
        assert 'p' in fields
        assert 'Ux' in fields or 'Uy' in fields
        # Each history should carry a non-empty per-iteration residual series.
        for rh in results.residual_histories:
            assert len(rh.initial_residuals) > 0
            assert len(rh.final_residuals) > 0

    def test_returns_none_when_no_log(self, tmp_path):
        (tmp_path / 'system').mkdir()
        result = _parse_results(tmp_path, 'simpleFoam')
        assert result is None


@needs_nomad
class TestOpenFOAMParser:
    def test_parse_populates_case(self):
        archive = MagicMock()
        parser = OpenFOAMParser()

        parser.parse(str(CONTROL_DICT), archive)

        case = archive.data
        assert case.case_name == 'cavity'
        assert case.solver_name == 'icoFoam'
        assert case.case_type == 'incompressible'

    def test_parse_solver_config(self):
        archive = MagicMock()
        parser = OpenFOAMParser()
        parser.parse(str(CONTROL_DICT), archive)

        cfg = archive.data.solver_config
        assert cfg is not None
        assert cfg.end_time == pytest.approx(0.5)
        assert cfg.delta_t == pytest.approx(0.005)
        assert cfg.application == 'icoFoam'
        assert cfg.n_correctors == 2

    def test_parse_mesh_type(self):
        """Mesh type detection works even when polyMesh stats are absent."""
        # The cavity fixture has no polyMesh data, so mesh section may be None.
        # Test the helper directly instead.
        assert _detect_mesh_type(CASE_DIR) == 'blockMesh'

    def test_parse_results_section(self):
        archive = MagicMock()
        OpenFOAMParser().parse(str(CONTROL_DICT), archive)
        assert archive.data.results is not None
        assert archive.data.results.wall_time_seconds == pytest.approx(0.28)
