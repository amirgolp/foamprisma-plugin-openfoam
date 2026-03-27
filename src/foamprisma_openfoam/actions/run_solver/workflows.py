from __future__ import annotations

from datetime import timedelta
from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from .activities import (
        prepare_case,
        decompose_case,
        run_openfoam_solver,
        parse_solver_results,
        upload_results_to_nomad,
    )
    from .models import RunSolverInput, UserApprovalInput


@workflow.defn
class RunSolverWorkflow:
    """
    Temporal workflow for running an OpenFOAM solver.

    Steps:
      1. Prepare case (copy files, validate structure)
      2. Decompose if parallel
      3. Run solver (long-running, heartbeating)
      4. Parse results
      5. Human-in-the-loop if solver diverged
      6. Upload results back to NOMAD
    """

    def __init__(self):
        self._user_approval: UserApprovalInput | None = None

    @workflow.signal
    def provide_approval(self, data: UserApprovalInput) -> None:
        """Signal from user via GUI: approve or reject continuation."""
        self._user_approval = data

    @workflow.run
    async def run(self, data: RunSolverInput) -> dict:
        retry_policy = RetryPolicy(maximum_attempts=2)

        # Step 1: Prepare
        case_info = await workflow.execute_activity(
            prepare_case,
            data,
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=retry_policy,
        )
        work_dir = case_info['work_dir']

        # Step 2: Decompose
        if data.n_processors > 1:
            await workflow.execute_activity(
                decompose_case,
                args=[work_dir, data.n_processors],
                start_to_close_timeout=timedelta(minutes=10),
                retry_policy=retry_policy,
            )

        # Step 3: Run solver
        solver_result = await workflow.execute_activity(
            run_openfoam_solver,
            args=[
                work_dir,
                data.solver_name,
                data.solver_type.value,
                data.custom_solver_path or '',
                data.n_processors,
                data.openfoam_version,
            ],
            start_to_close_timeout=timedelta(hours=data.max_runtime_hours),
            heartbeat_timeout=timedelta(minutes=2),
            retry_policy=RetryPolicy(maximum_attempts=1),
        )

        # Step 4: Parse results
        results = await workflow.execute_activity(
            parse_solver_results,
            args=[work_dir, solver_result['log_path']],
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=retry_policy,
        )

        # Step 5: Human-in-the-loop on divergence
        if results['diverged']:
            from nomad.actions.manager import (
                request_user_input_activity,
                RequestUserInputActivityInput,
            )
            await workflow.execute_activity(
                request_user_input_activity,
                RequestUserInputActivityInput(
                    action_instance_id=workflow.info().workflow_id,
                    user_id=data.user_id,
                    signal_fn_name='provide_approval',
                    description=(
                        'Solver diverged. Review residuals and decide whether to '
                        're-run with modified settings or accept current results.'
                    ),
                ),
                start_to_close_timeout=timedelta(minutes=5),
            )

            await workflow.wait_condition(
                lambda: self._user_approval is not None,
                timeout=timedelta(days=7),
            )

            if self._user_approval and not self._user_approval.approved:
                return {
                    'status': 'cancelled_by_user',
                    'message': self._user_approval.message,
                    'wall_time_seconds': solver_result['wall_time_seconds'],
                    'final_residuals': results['final_residuals'],
                }

        # Step 6: Upload results
        upload_result = await workflow.execute_activity(
            upload_results_to_nomad,
            args=[data.upload_id, data.user_id, work_dir, data.case_entry_id],
            start_to_close_timeout=timedelta(minutes=10),
            retry_policy=retry_policy,
        )

        return {
            'status': results['status'],
            'wall_time_seconds': solver_result['wall_time_seconds'],
            'final_residuals': results['final_residuals'],
            'log_path': solver_result['log_path'],
            'result_entry_id': upload_result['result_entry_id'],
        }
