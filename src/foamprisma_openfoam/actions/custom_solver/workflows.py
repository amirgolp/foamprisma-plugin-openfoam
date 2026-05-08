from datetime import timedelta
from pathlib import Path
from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from .activities import validate_solver_binary, compile_solver, run_custom_solver
    from .models import CustomSolverInput, SolverFormat
    from foamprisma_openfoam.actions.run_solver.activities import (
        prepare_case,
        parse_solver_results,
        upload_results_to_nomad,
    )
    from foamprisma_openfoam.actions.run_solver.models import RunSolverInput, SolverType


@workflow.defn
class CustomSolverWorkflow:
    """
    Temporal workflow for uploading, optionally compiling, and running
    a user-provided OpenFOAM solver binary.

    Steps:
      1. Prepare case directory
      2. Fetch solver binary/source from NOMAD storage
      3. Validate binary (or compile source with wmake)
      4. Run solver with heartbeats
      5. Parse results
      6. Upload results back to NOMAD
    """

    @workflow.run
    async def run(self, data: CustomSolverInput) -> dict:
        retry_policy = RetryPolicy(maximum_attempts=2)

        # Step 1: Prepare case
        solver_input = RunSolverInput(
            upload_id=data.upload_id,
            user_id=data.user_id,
            case_entry_id=data.case_entry_id,
            solver_name="customSolver",
            solver_type=SolverType.CUSTOM,
        )
        case_info = await workflow.execute_activity(
            prepare_case,
            solver_input,
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=retry_policy,
        )
        work_dir = case_info["work_dir"]

        # Step 2: Fetch solver path from NOMAD
        solver_dir = str(
            Path(f"/data/openfoam-cases/{data.upload_id}/solver_{data.solver_entry_id}")
        )

        # Step 3a: Validate
        validation = await workflow.execute_activity(
            validate_solver_binary,
            args=[solver_dir],
            start_to_close_timeout=timedelta(minutes=2),
            retry_policy=retry_policy,
        )

        if not validation["valid"]:
            return {"status": "error", "reason": "Solver validation failed"}

        # Step 3b: Compile if source format
        solver_binary = solver_dir
        if data.solver_format == SolverFormat.SOURCE:
            compile_result = await workflow.execute_activity(
                compile_solver,
                args=[solver_dir, data.openfoam_version],
                start_to_close_timeout=timedelta(minutes=15),
                retry_policy=RetryPolicy(maximum_attempts=1),
            )
            solver_binary = compile_result.get("solver_binary", solver_dir)

        # Step 4: Run solver
        run_result = await workflow.execute_activity(
            run_custom_solver,
            args=[work_dir, solver_binary, data.n_processors, data.openfoam_version],
            start_to_close_timeout=timedelta(hours=data.max_runtime_hours),
            heartbeat_timeout=timedelta(minutes=2),
            retry_policy=RetryPolicy(maximum_attempts=1),
        )

        # Step 5: Parse results
        results = await workflow.execute_activity(
            parse_solver_results,
            args=[work_dir, run_result["log_path"]],
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=retry_policy,
        )

        # Step 6: Upload
        upload_result = await workflow.execute_activity(
            upload_results_to_nomad,
            args=[data.upload_id, data.user_id, work_dir, data.case_entry_id],
            start_to_close_timeout=timedelta(minutes=10),
            retry_policy=retry_policy,
        )

        return {
            "status": results["status"],
            "wall_time_seconds": run_result["wall_time_seconds"],
            "final_residuals": results["final_residuals"],
            "log_path": run_result["log_path"],
            "result_entry_id": upload_result["result_entry_id"],
        }
