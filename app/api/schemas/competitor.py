from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from content_studio.contracts.competitor import CompetitorReport


class CompetitorRunRequest(BaseModel):
    queries: list[str] | None = Field(default=None, max_length=10)
    video_urls: list[str] | None = Field(default=None, max_length=20)
    max_results: int = Field(default=5, ge=1, le=20)
    analyze_with_llm: bool = True
    run_id: str | None = None


class CompetitorVideoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    youtube_video_id: str
    url: str
    title: str
    channel_name: str
    published_at: str | None
    duration_seconds: int | None
    view_count: int | None
    like_count: int | None
    comment_count: int | None
    description: str | None
    topics_covered_json: list[str]
    provider: str
    retrieved_at: datetime


class CompetitorVideoListResponse(BaseModel):
    items: list[CompetitorVideoResponse]
    total: int


CompetitorRunResponse = CompetitorReport
