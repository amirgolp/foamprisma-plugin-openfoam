from pydantic import BaseModel, Field


class CheckMeshInput(BaseModel):
    upload_id: str = Field(..., description="NOMAD upload ID")
    user_id: str = Field(..., description="User who triggered the action")
    case_entry_id: str = Field(..., description="Entry ID of the OpenFOAM case")
