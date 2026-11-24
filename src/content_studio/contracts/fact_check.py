from datetime import UTC, datetime

from pydantic import BaseModel, Field

from content_studio.database.models.enums import ClaimVerdict, EvidenceStance, RiskLevel


class ClaimEvidenceRef(BaseModel):
    source_url: str = Field(min_length=1)
    stance: EvidenceStance = EvidenceStance.SUPPORTS
    excerpt: str | None = Field(default=None, max_length=600)


class ExtractedClaimItem(BaseModel):
    statement: str = Field(min_length=8)
    verdict: ClaimVerdict = ClaimVerdict.UNCERTAIN
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    risk_level: RiskLevel = RiskLevel.MEDIUM
    rationale: str = Field(min_length=5)
    evidence: list[ClaimEvidenceRef] = Field(default_factory=list)


class FactCheckLLMOutput(BaseModel):
    overall_assessment: str = Field(min_length=10)
    claims: list[ExtractedClaimItem] = Field(default_factory=list)
    high_risk_warnings: list[str] = Field(default_factory=list)


class VerifiedClaimSummary(BaseModel):
    claim_id: str
    statement: str
    verdict: ClaimVerdict
    confidence: float
    risk_level: RiskLevel
    rationale: str
    supporting_urls: list[str] = Field(default_factory=list)
    contradicting_urls: list[str] = Field(default_factory=list)
    downgraded_reason: str | None = None


class FactCheckReport(BaseModel):
    project_id: str
    topic: str
    overall_assessment: str
    total_claims: int = 0
    verified_count: int = 0
    unsupported_count: int = 0
    conflicting_count: int = 0
    uncertain_count: int = 0
    downgraded_claims_count: int = 0
    high_risk_warnings: list[str] = Field(default_factory=list)
    claims: list[VerifiedClaimSummary] = Field(default_factory=list)
    approval_id: str | None = None
    report_json_artifact_id: str | None = None
    report_markdown_artifact_id: str | None = None
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
