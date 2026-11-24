from datetime import UTC, datetime

from pydantic import BaseModel, Field

from content_studio.database.models.enums import FindingCategory


class ResearchFindingItem(BaseModel):
    category: FindingCategory = FindingCategory.FACT
    title: str = Field(min_length=3, max_length=300)
    summary: str = Field(min_length=10)
    source_urls: list[str] = Field(min_length=1)
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    is_contradiction: bool = False


class ResearchSynthesisOutput(BaseModel):
    executive_summary: str = Field(min_length=10)
    key_definitions: list[str] = Field(default_factory=list)
    findings: list[ResearchFindingItem] = Field(min_length=1)
    contradictions: list[str] = Field(default_factory=list)
    recommended_angles: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)


class SourceSummary(BaseModel):
    source_id: str
    url: str
    normalized_url: str
    title: str
    domain: str
    provider: str
    status: str
    word_count: int = 0
    error_message: str | None = None


class ResearchReport(BaseModel):
    project_id: str
    topic: str
    queries_executed: list[str] = Field(default_factory=list)
    sources_discovered: int = 0
    sources_extracted: int = 0
    sources_failed: int = 0
    duplicates_skipped: int = 0
    ungrounded_findings_dropped: int = 0
    synthesis: ResearchSynthesisOutput | None = None
    source_index: list[SourceSummary] = Field(default_factory=list)
    report_markdown_artifact_id: str | None = None
    report_json_artifact_id: str | None = None
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
