from datetime import UTC, datetime

from pydantic import BaseModel, Field


class VideoTopicMapping(BaseModel):
    youtube_video_id: str
    topics_covered: list[str] = Field(default_factory=list)


class CompetitorGapLLMOutput(BaseModel):
    summary: str = Field(min_length=10)
    common_topics: list[str] = Field(default_factory=list)
    content_gaps: list[str] = Field(default_factory=list)
    differentiation_opportunities: list[str] = Field(default_factory=list)
    recommended_positioning: str = Field(min_length=10)
    video_topics: list[VideoTopicMapping] = Field(default_factory=list)


class CompetitorVideoSummary(BaseModel):
    id: str
    youtube_video_id: str
    url: str
    title: str
    channel_name: str
    published_at: str | None = None
    duration_seconds: int | None = None
    view_count: int | None = None
    like_count: int | None = None
    comment_count: int | None = None
    topics_covered: list[str] = Field(default_factory=list)
    provider: str


class CompetitorReport(BaseModel):
    project_id: str
    topic: str
    queries_executed: list[str] = Field(default_factory=list)
    videos_analyzed: int = 0
    duplicates_skipped: int = 0
    videos: list[CompetitorVideoSummary] = Field(default_factory=list)
    gap_analysis: CompetitorGapLLMOutput | None = None
    report_json_artifact_id: str | None = None
    report_markdown_artifact_id: str | None = None
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
