from datetime import timedelta
from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from foamprisma_openfoam.actions.generate_mesh.activities import run_check_mesh
    from foamprisma_openfoam.actions.run_solver.activities import (
        prepare_case, upload_results_to_nomad,
    )
    from .models import CheckMeshInput


@workflow.defn
class CheckMeshWorkflow:
    """Runs checkMesh on an existing OpenFOAM case mesh."""

    @workflow.run
    async def run(self, data: CheckMeshInput) -> dict:
        retry = RetryPolicy(maximum_attempts=2)

        case_info = await workflow.execute_activity(
            prepare_case,
            data,
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=retry,
        )

        result = await workflow.execute_activity(
            run_check_mesh,
            args=[case_info['work_dir']],
            start_to_close_timeout=timedelta(minutes=10),
            retry_policy=retry,
        )

        await workflow.execute_activity(
            upload_results_to_nomad,
            args=[data.upload_id, data.user_id,
                  case_info['work_dir'], data.case_entry_id],
            start_to_close_timeout=timedelta(minutes=10),
            retry_policy=retry,
        )

        return result
