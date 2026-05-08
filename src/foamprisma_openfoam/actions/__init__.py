from pydantic import Field

try:
    from temporalio import workflow as _workflow
    with _workflow.unsafe.imports_passed_through():
        from nomad.config.models.plugins import ActionEntryPoint as _ActionBase
except ImportError:
    class _ActionBase:  # type: ignore[no-redef]
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)


# ── Run Solver Action ──
class RunSolverActionEntryPoint(_ActionBase):
    task_queue: str = Field(
        default='openfoam',
        description='Dedicated OpenFOAM task queue with OF installed',
    )

    def load(self):
        from nomad.actions import Action
        from .run_solver.workflows import RunSolverWorkflow
        from .run_solver.activities import (
            prepare_case, decompose_case, run_openfoam_solver,
            parse_solver_results, upload_results_to_nomad,
        )
        return Action(
            task_queue=self.task_queue,
            workflow=RunSolverWorkflow,
            activities=[
                prepare_case, decompose_case, run_openfoam_solver,
                parse_solver_results, upload_results_to_nomad,
            ],
        )


run_solver_action = RunSolverActionEntryPoint(
    name='RunOpenFOAMSolver',
    description='Run an OpenFOAM solver on an uploaded case with live monitoring.',
)


# ── Generate Mesh Action ──
class GenerateMeshActionEntryPoint(_ActionBase):
    task_queue: str = Field(default='openfoam')

    def load(self):
        from nomad.actions import Action
        from .generate_mesh.workflows import GenerateMeshWorkflow
        from .generate_mesh.activities import (
            detect_mesh_tool, run_block_mesh, run_snappy_hex_mesh, run_check_mesh,
        )
        # GenerateMeshWorkflow also reuses prepare_case and upload_results_to_nomad
        # from run_solver — must register them on the worker or temporal
        # raises NotFoundError when those activities are scheduled.
        from .run_solver.activities import prepare_case, upload_results_to_nomad
        return Action(
            task_queue=self.task_queue,
            workflow=GenerateMeshWorkflow,
            activities=[
                prepare_case,
                detect_mesh_tool,
                run_block_mesh,
                run_snappy_hex_mesh,
                run_check_mesh,
                upload_results_to_nomad,
            ],
        )


generate_mesh_action = GenerateMeshActionEntryPoint(
    name='GenerateOpenFOAMMesh',
    description='Generate mesh using blockMesh or snappyHexMesh.',
)


# ── Check Mesh Action ──
class CheckMeshActionEntryPoint(_ActionBase):
    task_queue: str = Field(default='openfoam')

    def load(self):
        from nomad.actions import Action
        from .check_mesh.workflows import CheckMeshWorkflow
        from .generate_mesh.activities import run_check_mesh
        return Action(
            task_queue=self.task_queue,
            workflow=CheckMeshWorkflow,
            activities=[run_check_mesh],
        )


check_mesh_action = CheckMeshActionEntryPoint(
    name='CheckOpenFOAMMesh',
    description='Run checkMesh to validate mesh quality and store metrics.',
)


# ── Custom Solver Action ──
class CustomSolverActionEntryPoint(_ActionBase):
    """Allows users to upload and run custom solver binaries."""
    task_queue: str = Field(default='openfoam')

    def load(self):
        from nomad.actions import Action
        from .custom_solver.workflows import CustomSolverWorkflow
        from .custom_solver.activities import (
            validate_solver_binary, compile_solver, run_custom_solver,
        )
        return Action(
            task_queue=self.task_queue,
            workflow=CustomSolverWorkflow,
            activities=[validate_solver_binary, compile_solver, run_custom_solver],
        )


custom_solver_action = CustomSolverActionEntryPoint(
    name='RunCustomSolver',
    description='Upload, compile (optional), and run a custom OpenFOAM solver.',
)
