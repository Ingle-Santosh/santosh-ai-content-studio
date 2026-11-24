from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from content_studio.contracts.fact_check import FactCheckReport


class FactCheckRunRequest(BaseModel):
    custom_claims: list[str] | None = Field(default=None, max_length=25)
    request_research_approval: bool = True
    run_id: str | None = None


class ClaimSourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source_id: str
    stance: str
    excerpt: str | None


class ClaimResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    run_id: str | None
    finding_id: str | None
    statement: str
    verdict: str
    confidence: float
    risk_level: str
    rationale: str
    evidence_summary: str | None
    claim_sources: list[ClaimSourceResponse] = Field(default_factory=list)
    created_at: datetime


class ClaimListResponse(BaseModel):
    items: list[ClaimResponse]
    total: int


FactCheckRunResponse = FactCheckReport
