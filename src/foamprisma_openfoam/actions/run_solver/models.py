from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


class BaseWorkflowInput(BaseModel):
    """Standard NOMAD action input. Provides user_id and upload_id."""

    upload_id: str = Field(..., description="NOMAD upload ID containing the case")
    user_id: str = Field(..., description="User who triggered the action")


class SolverType(str, Enum):
    INSTALLED = "installed"  # Use pre-installed OpenFOAM solver
    CUSTOM = "custom"  # User-uploaded custom solver binary


class RunSolverInput(BaseWorkflowInput):
    """Input for running an OpenFOAM solver."""

    case_entry_id: str = Field(..., description="Entry ID of the OpenFOAM case")
    solver_name: str = Field(
        ..., description="Solver application name (e.g., simpleFoam, pimpleFoam)"
    )
    solver_type: SolverType = Field(
        default=SolverType.INSTALLED,
        description="Whether to use installed or custom solver",
    )
    custom_solver_path: Optional[str] = Field(
        None, description="Path to custom solver binary (if solver_type=custom)"
    )
    openfoam_version: str = Field(default="2206", description="OpenFOAM version to use")
    n_processors: int = Field(
        default=1, description="Number of processors for parallel decomposition"
    )
    max_runtime_hours: float = Field(
        default=24.0, description="Maximum runtime before auto-termination"
    )


class RunSolverOutput(BaseModel):
    """Output from a solver run."""

    status: str  # "completed", "diverged", "timeout", "error"
    wall_time_seconds: float
    final_residuals: dict  # {field: residual_value}
    log_path: str
    result_entry_id: Optional[str] = None  # NOMAD entry ID for results


class UserApprovalInput(BaseModel):
    """For human-in-the-loop: user approves/rejects continuation."""

    approved: bool
    message: Optional[str] = None
