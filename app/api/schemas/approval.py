from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from content_studio.database.models.enums import ApprovalGate, ApprovalStatus


class ApprovalCreateRequest(BaseModel):
    gate: ApprovalGate
    run_id: str | None = None
    artifact_id: str | None = None
    comments: str | None = Field(default=None, max_length=2000)


class ApprovalDecisionRequest(BaseModel):
    status: ApprovalStatus
    reviewer: str | None = Field(default=None, max_length=120)
    comments: str | None = Field(default=None, max_length=2000)


class ApprovalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    run_id: str | None
    artifact_id: str | None
    gate: str
    status: str
    reviewer: str | None
    comments: str | None
    requested_at: datetime
    decided_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ApprovalListResponse(BaseModel):
    items: list[ApprovalResponse]
    total: int
