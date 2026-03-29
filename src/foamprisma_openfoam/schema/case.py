"""
Top-level OpenFOAM case schema with full ELN annotations and Action triggers.

The GUI renders this schema as an interactive entry page where users can:
- Browse case metadata (solver, mesh type, boundary conditions)
- See residual convergence plots (from SimulationResults/PlotSection)
- See mesh quality gauges (from MeshQuality/PlotSection)
- Trigger actions: Run Solver, Generate Mesh, Check Mesh (via ActionEditQuantity)
- Monitor workflow status
"""

from nomad.metainfo import Quantity, SubSection, MEnum, Section, Package
from nomad.datamodel.data import EntryData
from nomad.datamodel.metainfo.annotations import (
    ELNAnnotation, ELNComponentEnum, SectionProperties,
)

from .mesh import OpenFOAMMesh
from .solver import SolverConfiguration
from .boundary import BoundaryConditions
from .results import SimulationResults
from .quality import MeshQuality

m_package = Package(name='foamprisma_openfoam')


class OpenFOAMCase(EntryData):
    """
    Top-level schema for an OpenFOAM simulation case.
    Rendered in the NOMAD GUI as an interactive ELN entry.
    """

    m_def = Section(
        a_eln=ELNAnnotation(
            properties=SectionProperties(
                order=[
                    'case_name', 'solver_name', 'case_type',
                    'openfoam_version', 'mesh', 'solver_config',
                    'results', 'mesh_quality',
                    'trigger_run_solver', 'trigger_generate_mesh',
                    'trigger_check_mesh', 'trigger_check_status',
                    'workflow_id', 'workflow_status',
                ],
            ),
        ),
    )

    # ── Case Identity ──
    case_name = Quantity(
        type=str,
        description='Name of the OpenFOAM case directory',
        a_eln=ELNAnnotation(component=ELNComponentEnum.StringEditQuantity),
    )
    openfoam_version = Quantity(
        type=str,
        description='OpenFOAM version used (e.g., 2206, 2312, v11)',
        a_eln=ELNAnnotation(component=ELNComponentEnum.StringEditQuantity),
    )
    solver_name = Quantity(
        type=str,
        description='Solver application (e.g., simpleFoam, pimpleFoam, interFoam)',
        a_eln=ELNAnnotation(component=ELNComponentEnum.StringEditQuantity),
    )
    case_type = Quantity(
        type=MEnum(
            'incompressible', 'compressible', 'multiphase',
            'combustion', 'heat-transfer', 'electromagnetics',
            'stress-analysis', 'other',
        ),
        description='Classification of the simulation type',
        a_eln=ELNAnnotation(component=ELNComponentEnum.EnumEditQuantity),
    )

    # ── Structured Subsections ──
    mesh = SubSection(
        sub_section=OpenFOAMMesh,
        description='Mesh definition and statistics',
    )
    solver_config = SubSection(
        sub_section=SolverConfiguration,
        description='Solver settings (controlDict, fvSchemes, fvSolution)',
    )
    boundary_conditions = SubSection(
        sub_section=BoundaryConditions,
        repeats=True,
        description='Boundary conditions for each patch',
    )
    results = SubSection(
        sub_section=SimulationResults,
        description='Simulation results with convergence plots',
    )
    mesh_quality = SubSection(
        sub_section=MeshQuality,
        description='Mesh quality metrics with visual assessment',
    )

    # ── Action Triggers (rendered as buttons in GUI) ──
    trigger_run_solver = Quantity(
        type=bool,
        description='Run the OpenFOAM solver on this case.',
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.ActionEditQuantity,
            label='▶ Run Solver',
        ),
    )
    trigger_generate_mesh = Quantity(
        type=bool,
        description='Generate mesh using blockMesh or snappyHexMesh.',
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.ActionEditQuantity,
            label='🔧 Generate Mesh',
        ),
    )
    trigger_check_mesh = Quantity(
        type=bool,
        description='Run checkMesh to validate mesh quality.',
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.ActionEditQuantity,
            label='✓ Check Mesh',
        ),
    )
    trigger_check_status = Quantity(
        type=bool,
        description='Refresh the status of the running workflow.',
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.ActionEditQuantity,
            label='🔄 Check Status',
        ),
    )

    # ── Workflow Tracking ──
    workflow_id = Quantity(
        type=str,
        description='Active Temporal workflow ID (auto-populated)',
    )
    workflow_status = Quantity(
        type=str,
        description='Current workflow status (auto-populated)',
    )

    def normalize(self, archive, logger=None):
        super().normalize(archive, logger)

        # ── Handle action triggers ──
        if self.trigger_run_solver:
            self._start_solver_action(archive, logger)
            self.trigger_run_solver = False

        if self.trigger_generate_mesh:
            self._start_mesh_action(archive, logger)
            self.trigger_generate_mesh = False

        if self.trigger_check_mesh:
            self._start_check_mesh_action(archive, logger)
            self.trigger_check_mesh = False

        if self.trigger_check_status and self.workflow_id:
            self._refresh_status(logger)
            self.trigger_check_status = False

    def _start_solver_action(self, archive, logger):
        try:
            from nomad.actions.manager import start_action
            from foamprisma_openfoam.actions.run_solver.models import RunSolverInput
        except ImportError:
            if logger:
                logger.error('nomad.actions.manager not available — cannot start solver.')
            return

        if self.workflow_status == 'RUNNING':
            if logger:
                logger.warn('A workflow is already running for this case.')
            return

        try:
            input_data = RunSolverInput(
                user_id=archive.metadata.main_author.user_id,
                upload_id=archive.metadata.upload_id,
                case_entry_id=archive.metadata.entry_id,
                solver_name=self.solver_name or 'simpleFoam',
                openfoam_version=self.openfoam_version or '2206',
            )
            self.workflow_id = start_action(
                action_name='foamprisma_openfoam.actions:run_solver_action',
                data=input_data,
            )
            self.workflow_status = 'RUNNING'
            if logger:
                logger.info(f'Started solver action: {self.workflow_id}')
        except Exception as e:
            if logger:
                logger.error(f'Failed to start solver: {e}')

    def _start_mesh_action(self, archive, logger):
        try:
            from nomad.actions.manager import start_action
            from foamprisma_openfoam.actions.generate_mesh.models import GenerateMeshInput
        except ImportError:
            if logger:
                logger.error('nomad.actions.manager not available.')
            return

        try:
            input_data = GenerateMeshInput(
                user_id=archive.metadata.main_author.user_id,
                upload_id=archive.metadata.upload_id,
                case_entry_id=archive.metadata.entry_id,
            )
            self.workflow_id = start_action(
                action_name='foamprisma_openfoam.actions:generate_mesh_action',
                data=input_data,
            )
            self.workflow_status = 'RUNNING'
        except Exception as e:
            if logger:
                logger.error(f'Failed to start mesh generation: {e}')

    def _start_check_mesh_action(self, archive, logger):
        try:
            from nomad.actions.manager import start_action
            from foamprisma_openfoam.actions.check_mesh.models import CheckMeshInput
        except ImportError:
            if logger:
                logger.error('nomad.actions.manager not available.')
            return

        try:
            input_data = CheckMeshInput(
                user_id=archive.metadata.main_author.user_id,
                upload_id=archive.metadata.upload_id,
                case_entry_id=archive.metadata.entry_id,
            )
            self.workflow_id = start_action(
                action_name='foamprisma_openfoam.actions:check_mesh_action',
                data=input_data,
            )
            self.workflow_status = 'RUNNING'
        except Exception as e:
            if logger:
                logger.error(f'Failed to start checkMesh: {e}')

    def _refresh_status(self, logger):
        try:
            from nomad.actions.manager import get_action_status
            status = get_action_status(self.workflow_id)
            self.workflow_status = status.name
        except Exception as e:
            if logger:
                logger.error(f'Failed to get workflow status: {e}')


m_package.__init_metainfo__()
