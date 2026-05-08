from pydantic import BaseModel, Field
from typing import Optional


class GenerateMeshInput(BaseModel):
    upload_id: str = Field(..., description="NOMAD upload ID")
    user_id: str = Field(..., description="User who triggered the action")
    case_entry_id: str = Field(..., description="Entry ID of the OpenFOAM case")
    force_snappy: bool = Field(
        default=False,
        description="Force snappyHexMesh even if blockMeshDict exists",
    )


class MeshGenerationResult(BaseModel):
    mesh_tool: str  # "blockMesh" or "snappyHexMesh"
    n_cells: Optional[int] = None
    n_faces: Optional[int] = None
    n_points: Optional[int] = None
    mesh_ok: bool = False
    check_mesh_log: str = ""
    max_non_orthogonality: Optional[float] = None
    max_skewness: Optional[float] = None
