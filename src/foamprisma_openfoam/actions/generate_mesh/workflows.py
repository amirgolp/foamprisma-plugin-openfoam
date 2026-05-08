"""
Temporal workflow for mesh generation.
Orchestrates: detect tool -> generate mesh -> check mesh -> upload results.
"""

from datetime import timedelta
from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from .activities import (
        detect_mesh_tool, run_block_mesh, run_snappy_hex_mesh, run_check_mesh,
    )
    from .models import GenerateMeshInput
    from foamprisma_openfoam.actions.run_solver.activities import (
        prepare_case, upload_results_to_nomad,
    )


@workflow.defn
class GenerateMeshWorkflow:
    """Generate mesh for an OpenFOAM case and validate with checkMesh."""

    @workflow.run
    async def run(self, data: GenerateMeshInput) -> dict:
        retry = RetryPolicy(maximum_attempts=2)

        # Step 1: Prepare working directory
        case_info = await workflow.execute_activity(
            prepare_case,
            args=[data.upload_id, data.case_entry_id],
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=retry,
        )
        work_dir = case_info['work_dir']

        # Step 2: Detect mesh tool
        mesh_tool = await workflow.execute_activity(
            detect_mesh_tool,
            args=[work_dir, data.force_snappy],
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=retry,
        )

        # Step 3: Generate mesh
        if mesh_tool == 'blockMesh':
            await workflow.execute_activity(
                run_block_mesh,
                args=[work_dir],
                start_to_close_timeout=timedelta(minutes=30),
                heartbeat_timeout=timedelta(minutes=2),
                retry_policy=retry,
            )
        else:
            await workflow.execute_activity(
                run_snappy_hex_mesh,
                args=[work_dir],
                start_to_close_timeout=timedelta(hours=2),
                heartbeat_timeout=timedelta(minutes=5),
                retry_policy=retry,
            )

        # Step 4: Check mesh quality
        check_result = await workflow.execute_activity(
            run_check_mesh,
            args=[work_dir],
            start_to_close_timeout=timedelta(minutes=10),
            retry_policy=retry,
        )

        # Step 5: Upload results back to NOMAD
        await workflow.execute_activity(
            upload_results_to_nomad,
            args=[data.upload_id, data.user_id, work_dir, data.case_entry_id],
            start_to_close_timeout=timedelta(minutes=10),
            retry_policy=retry,
        )

        return {
            'mesh_tool': mesh_tool,
            'n_cells': check_result.get('n_cells'),
            'mesh_ok': check_result.get('mesh_ok', False),
            'max_non_orthogonality': check_result.get('max_non_orthogonality'),
            'max_skewness': check_result.get('max_skewness'),
        }
