"""Tests for OpenFOAMNormalizer's pure-Python helpers.

The Normalizer class itself depends on nomad-lab (Normalizer base class,
NormalizerEntryPoint), so those paths are only exercised in the integration
job. The lookup tables and arithmetic are pure Python and tested here.
"""

import pytest

from foamprisma_openfoam.normalizer import (
    _SOLVER_CATEGORY,
    _compute_reynolds,
    _infer_case_type,
    _required_field_warnings,
)


class TestSolverCategoryLookup:
    def test_simpleFoam_is_incompressible(self):
        assert _infer_case_type('simpleFoam') == 'incompressible'

    def test_rhoPimpleFoam_is_compressible(self):
        assert _infer_case_type('rhoPimpleFoam') == 'compressible'

    def test_interFoam_is_multiphase(self):
        assert _infer_case_type('interFoam') == 'multiphase'

    def test_chtMultiRegionFoam_is_heat_transfer(self):
        assert _infer_case_type('chtMultiRegionFoam') == 'heat-transfer'

    def test_unknown_solver_returns_none(self):
        assert _infer_case_type('myCustomFoam') is None

    def test_empty_solver_returns_none(self):
        assert _infer_case_type('') is None
        assert _infer_case_type(None) is None

    def test_well_known_solvers_all_categorised(self):
        # Smoke test — every entry resolves to a known case_type.
        valid_types = {
            'incompressible', 'compressible', 'multiphase', 'combustion',
            'heat-transfer', 'electromagnetics', 'stress-analysis', 'other',
        }
        for solver, cat in _SOLVER_CATEGORY.items():
            assert cat in valid_types, f'{solver} maps to invalid category {cat}'


class _FakeMesh:
    def __init__(self, n_cells=None):
        self.n_cells = n_cells


class _FakeCase:
    def __init__(self, **kwargs):
        self.case_name = kwargs.get('case_name')
        self.solver_name = kwargs.get('solver_name')
        self.mesh = kwargs.get('mesh')


class TestRequiredFieldWarnings:
    def test_no_warnings_for_complete_case(self):
        case = _FakeCase(case_name='cavity', solver_name='icoFoam',
                         mesh=_FakeMesh(n_cells=400))
        assert _required_field_warnings(case) == []

    def test_warns_on_empty_case_name(self):
        case = _FakeCase(case_name=None, solver_name='icoFoam',
                         mesh=_FakeMesh(n_cells=400))
        warnings = _required_field_warnings(case)
        assert any('case_name' in w for w in warnings)

    def test_warns_on_missing_mesh(self):
        case = _FakeCase(case_name='cavity', solver_name='icoFoam', mesh=None)
        warnings = _required_field_warnings(case)
        assert any('mesh' in w for w in warnings)

    def test_warns_on_zero_cells(self):
        case = _FakeCase(case_name='cavity', solver_name='icoFoam',
                         mesh=_FakeMesh(n_cells=0))
        warnings = _required_field_warnings(case)
        assert any('n_cells' in w for w in warnings)


class _FakeSolverConfig:
    def __init__(self, nu=None, u=None, l=None):
        self.kinematic_viscosity = nu
        self.reference_velocity = u
        self.characteristic_length = l


class _CaseWithConfig:
    def __init__(self, sc=None):
        self.solver_config = sc


class TestComputeReynolds:
    def test_returns_none_when_no_config(self):
        assert _compute_reynolds(_CaseWithConfig(sc=None)) is None

    def test_returns_none_when_any_field_missing(self):
        assert _compute_reynolds(_CaseWithConfig(_FakeSolverConfig(nu=1e-5))) is None
        assert _compute_reynolds(_CaseWithConfig(_FakeSolverConfig(u=1.0))) is None
        assert _compute_reynolds(_CaseWithConfig(_FakeSolverConfig(l=0.1))) is None

    def test_returns_none_when_nu_is_zero(self):
        sc = _FakeSolverConfig(nu=0.0, u=1.0, l=0.1)
        assert _compute_reynolds(_CaseWithConfig(sc)) is None

    def test_computes_reynolds(self):
        # Re = U * L / nu. Air at room temp roughly: U=1 m/s, L=0.1 m, nu=1.5e-5
        sc = _FakeSolverConfig(nu=1.5e-5, u=1.0, l=0.1)
        re = _compute_reynolds(_CaseWithConfig(sc))
        assert re is not None
        assert re == pytest.approx(1.0 * 0.1 / 1.5e-5)
