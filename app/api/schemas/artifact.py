from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from content_studio.database.models.enums import ArtifactStatus, ArtifactType


class ArtifactCreateRequest(BaseModel):
    stage: str = Field(min_length=1, max_length=50)
    artifact_type: ArtifactType
    name: str = Field(min_length=1, max_length=255)
    content: str
    relative_path: str | None = Field(default=None, max_length=500)
    run_id: str | None = None
    status: ArtifactStatus = ArtifactStatus.DRAFT
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    supersede_previous_drafts: bool = True

    @field_validator("stage", "name")
    @classmethod
    def _strip_required(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Field must not be blank.")
        return cleaned


class ArtifactStatusUpdateRequest(BaseModel):
    status: ArtifactStatus


class ArtifactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    run_id: str | None
    stage: str
    artifact_type: str
    name: str
    relative_path: str
    version: int
    status: str
    checksum_sha256: str | None
    size_bytes: int
    metadata_json: dict[str, Any]
    created_at: datetime


class ArtifactListResponse(BaseModel):
    items: list[ArtifactResponse]
    total: int


class ArtifactContentResponse(BaseModel):
    artifact: ArtifactResponse
    content: str
    encoding: str = "utf-8"


class ArtifactIntegrityResponse(BaseModel):
    artifact_id: str
    relative_path: str
    exists_on_disk: bool
    expected_checksum: str | None
    actual_checksum: str | None
    expected_size_bytes: int
    actual_size_bytes: int | None
    is_valid: bool
