from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from content_studio.database.models.enums import ApprovalStatus
from content_studio.workflows.orchestrator import WorkflowRunSnapshot


class WorkflowStartRequest(BaseModel):
    seed_urls: list[str] | None = Field(default=None, max_length=20)
    max_results_per_query: int = Field(default=5, ge=1, le=20)
    auto_approve: bool | None = None


class WorkflowResumeRequest(BaseModel):
    decision: ApprovalStatus
    reviewer: str | None = Field(default="Creator", max_length=120)
    comments: str | None = Field(default=None, max_length=2000)


class WorkflowRunSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    thread_id: str
    status: str
    current_stage: str | None
    error_message: str | None
    started_at: datetime
    completed_at: datetime | None


class WorkflowRunListResponse(BaseModel):
    items: list[WorkflowRunSummaryResponse]
    total: int


WorkflowRunSnapshotResponse = WorkflowRunSnapshot
