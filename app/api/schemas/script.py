from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from content_studio.contracts.script import GeneratedScriptReport, ScriptSectionItem


class ScriptGenerateRequest(BaseModel):
    revision_notes: str | None = Field(default=None, max_length=2000)
    require_approved_research: bool = False
    request_script_approval: bool = True
    run_id: str | None = None


class ScriptManualRevisionRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    language: str | None = Field(default=None, max_length=50)
    sections: list[ScriptSectionItem] = Field(min_length=1)
    revision_notes: str | None = Field(default=None, max_length=2000)
    request_script_approval: bool = True


class ScriptApproveRequest(BaseModel):
    reviewer: str | None = Field(default="Creator", max_length=120)
    comments: str | None = Field(default=None, max_length=2000)


class ScriptVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    script_id: str
    project_id: str
    run_id: str | None
    artifact_id: str | None
    version_number: int
    status: str
    language: str
    total_estimated_duration_seconds: int
    word_count: int
    sections_json: list[dict[str, Any]]
    validation_report_json: dict[str, Any]
    revision_notes: str | None
    created_at: datetime


class ScriptResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    title: str
    current_version: int
    approved_version: int | None
    status: str
    versions: list[ScriptVersionResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


ScriptGenerateResponse = GeneratedScriptReport
