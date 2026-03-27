"""Tests for the OpenFOAM schema definitions."""

import pytest


class TestOpenFOAMCaseSchema:
    def test_imports_without_nomad(self):
        """Schema module imports should not crash even without NOMAD installed."""
        try:
            from foamprisma_openfoam.schema.mesh import OpenFOAMMesh
            from foamprisma_openfoam.schema.quality import MeshQuality
            from foamprisma_openfoam.schema.solver import SolverConfiguration
            from foamprisma_openfoam.schema.boundary import BoundaryConditions
            from foamprisma_openfoam.schema.results import SimulationResults
        except ImportError as e:
            pytest.skip(f'NOMAD not installed: {e}')

    def test_run_solver_models(self):
        from foamprisma_openfoam.actions.run_solver.models import (
            RunSolverInput, SolverType, UserApprovalInput,
        )
        inp = RunSolverInput(
            upload_id='upload-123',
            user_id='user-456',
            case_entry_id='entry-789',
            solver_name='simpleFoam',
        )
        assert inp.solver_type == SolverType.INSTALLED
        assert inp.n_processors == 1
        assert inp.openfoam_version == '2206'

    def test_generate_mesh_models(self):
        from foamprisma_openfoam.actions.generate_mesh.models import (
            GenerateMeshInput, MeshGenerationResult,
        )
        inp = GenerateMeshInput(
            upload_id='upload-123',
            user_id='user-456',
            case_entry_id='entry-789',
        )
        assert inp.force_snappy is False
        assert inp.case_entry_id == 'entry-789'

    def test_check_mesh_models(self):
        from foamprisma_openfoam.actions.check_mesh.models import CheckMeshInput
        inp = CheckMeshInput(
            upload_id='u', user_id='user', case_entry_id='e',
        )
        assert inp.upload_id == 'u'
        assert inp.case_entry_id == 'e'

    def test_custom_solver_models(self):
        from foamprisma_openfoam.actions.custom_solver.models import (
            CustomSolverInput, SolverFormat,
        )
        inp = CustomSolverInput(
            upload_id='u', user_id='user',
            case_entry_id='e', solver_entry_id='s',
        )
        assert inp.solver_format == SolverFormat.BINARY
