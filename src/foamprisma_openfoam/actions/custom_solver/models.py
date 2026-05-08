from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum

from foamprisma_openfoam.actions.run_solver.models import BaseWorkflowInput


class SolverFormat(str, Enum):
    BINARY = "binary"  # Pre-compiled binary uploaded by user
    SOURCE = "source"  # C++ source that needs wmake compilation


class CustomSolverInput(BaseWorkflowInput):
    """Input for uploading and running a custom OpenFOAM solver."""

    case_entry_id: str = Field(..., description="Entry ID of the OpenFOAM case")
    solver_entry_id: str = Field(
        ..., description="Entry ID of the uploaded custom solver"
    )
    solver_format: SolverFormat = Field(
        default=SolverFormat.BINARY,
        description="Whether the solver is a compiled binary or source code",
    )
    openfoam_version: str = Field(default="2206")
    n_processors: int = Field(default=1)
    max_runtime_hours: float = Field(default=24.0)


class CustomSolverOutput(BaseModel):
    status: str
    wall_time_seconds: Optional[float] = None
    final_residuals: Optional[dict] = None
    log_path: Optional[str] = None
    result_entry_id: Optional[str] = None
