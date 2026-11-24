from datetime import UTC, datetime

from pydantic import BaseModel, Field


class ContentBriefLLMOutput(BaseModel):
    content_angle: str = Field(min_length=10)
    target_audience: str = Field(min_length=5)
    problem_hook: str = Field(min_length=10)
    key_takeaways: list[str] = Field(min_length=2)
    proposed_outline: list[str] = Field(min_length=3)
    search_queries: list[str] = Field(min_length=1, max_length=6)
    competitor_queries: list[str] = Field(min_length=1, max_length=4)
    differentiation_hook: str = Field(min_length=10)


class ContentBriefReport(BaseModel):
    project_id: str
    topic: str
    brief: ContentBriefLLMOutput
    brief_json_artifact_id: str | None = None
    brief_markdown_artifact_id: str | None = None
    approval_id: str | None = None
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
