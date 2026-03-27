"""Tests for the PyFoam adapter against the cavity tutorial fixture."""

import pytest
from pathlib import Path

from foamprisma_openfoam.parser.adapters.pyfoam_adapter import (
    PyFoamAdapter,
    _parse_foam_dict_simple,
    _parse_check_mesh_log,
)

CASE_DIR = Path(__file__).parent / 'data' / 'cavity'


class TestParseFoamDictSimple:
    def test_parses_key_value(self):
        text = "application icoFoam;\nendTime 0.5;\n"
        result = _parse_foam_dict_simple(text)
        assert result['application'] == 'icoFoam'
        assert result['endTime'] == pytest.approx(0.5)

    def test_strips_comments(self):
        text = "// comment\napplication simpleFoam; /* block comment */\n"
        result = _parse_foam_dict_simple(text)
        assert result['application'] == 'simpleFoam'

    def test_numeric_conversion(self):
        text = "deltaT 0.005;\nwriteInterval 20;\n"
        result = _parse_foam_dict_simple(text)
        assert result['deltaT'] == pytest.approx(0.005)
        assert result['writeInterval'] == 20
        assert isinstance(result['writeInterval'], int)


class TestPyFoamAdapter:
    @pytest.fixture
    def adapter(self):
        return PyFoamAdapter(CASE_DIR)

    def test_solver_name(self, adapter):
        assert adapter.get_solver_name() == 'icoFoam'

    def test_end_time(self, adapter):
        assert adapter.get_end_time() == pytest.approx(0.5)

    def test_start_time(self, adapter):
        assert adapter.get_start_time() == pytest.approx(0)

    def test_delta_t(self, adapter):
        assert adapter.get_delta_t() == pytest.approx(0.005)

    def test_write_interval(self, adapter):
        assert adapter.get_write_interval() == pytest.approx(20)

    def test_pv_coupling_piso(self, adapter):
        assert adapter.get_pv_coupling() == 'PISO'

    def test_n_correctors(self, adapter):
        assert adapter.get_n_correctors() == 2

    def test_turbulence_model_unknown_when_missing(self, adapter):
        # No turbulenceProperties in test fixture → should return 'unknown'
        assert adapter.get_turbulence_model() in ('unknown', 'laminar', '')

    def test_mesh_type_blockMesh(self, adapter):
        from foamprisma_openfoam.parser.openfoam_parser import _detect_mesh_type
        assert _detect_mesh_type(CASE_DIR) == 'blockMesh'


class TestParseCheckMeshLog:
    def test_parses_mesh_stats(self):
        log = (
            "Mesh stats\n"
            "    points:           400\n"
            "    faces:            760\n"
            "    internal faces:   360\n"
            "    cells:            200\n"
            "Max non-orthogonality = 0.00\n"
            "Max skewness = 1.26e-08\n"
            "Mesh OK.\n"
        )
        result = _parse_check_mesh_log(log)
        assert result['n_cells'] == 200
        assert result['n_faces'] == 760
        assert result['n_points'] == 400
        assert result['max_skewness'] == pytest.approx(1.26e-08)
        assert result['mesh_ok'] is True

    def test_detects_errors(self):
        log = "Some mesh errors found.\n"
        result = _parse_check_mesh_log(log)
        assert result['mesh_ok'] is False
