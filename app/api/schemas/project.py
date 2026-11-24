from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from content_studio.contracts.project import ProjectConfig
from content_studio.database.models.enums import ProjectStatus


class ProjectCreateRequest(BaseModel):
    topic: str = Field(min_length=3, max_length=500)
    title: str | None = Field(default=None, max_length=255)
    config: ProjectConfig = Field(default_factory=ProjectConfig)
    budget_usd: float = Field(default=0.0, ge=0.0)

    @field_validator("topic")
    @classmethod
    def _strip_topic(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 3:
            raise ValueError("Topic must be at least 3 non-whitespace characters.")
        return cleaned

    @field_validator("title")
    @classmethod
    def _strip_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class ProjectUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    topic: str | None = Field(default=None, min_length=3, max_length=500)
    status: ProjectStatus | None = None
    config: ProjectConfig | None = None
    budget_usd: float | None = Field(default=None, ge=0.0)


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    topic: str
    status: str
    current_stage: str | None
    config: dict[str, Any]
    budget_usd: float
    spent_usd: float
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class ProjectListResponse(BaseModel):
    items: list[ProjectResponse]
    total: int
