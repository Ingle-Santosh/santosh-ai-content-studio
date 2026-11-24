from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from content_studio.contracts.research import ResearchReport


class ResearchRunRequest(BaseModel):
    queries: list[str] | None = Field(default=None, max_length=10)
    seed_urls: list[str] | None = Field(default=None, max_length=20)
    max_results_per_query: int = Field(default=5, ge=1, le=20)
    synthesize_with_llm: bool = True
    run_id: str | None = None


class SourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    url: str
    normalized_url: str
    url_hash: str
    title: str
    domain: str
    snippet: str | None
    provider: str
    status: str
    http_status: int | None
    error_message: str | None
    retrieved_at: datetime


class SourceListResponse(BaseModel):
    items: list[SourceResponse]
    total: int


class ResearchFindingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    source_id: str | None
    run_id: str | None
    category: str
    title: str
    summary: str
    source_urls_json: list[str]
    confidence: float
    is_contradiction: bool
    created_at: datetime


class ResearchFindingListResponse(BaseModel):
    items: list[ResearchFindingResponse]
    total: int


ResearchRunResponse = ResearchReport
