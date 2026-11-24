from datetime import UTC, datetime

from pydantic import BaseModel, Field, model_validator

EVALUATION_PROMPT_VERSION = "v1.0"


class EvaluationWeights(BaseModel):
    """Configurable 7-dimension quality rubric weights summing to 1.0 (Section 13)."""

    factual_accuracy: float = Field(default=0.25, ge=0.0, le=1.0)
    research_quality: float = Field(default=0.15, ge=0.0, le=1.0)
    script_quality: float = Field(default=0.20, ge=0.0, le=1.0)
    teaching_clarity: float = Field(default=0.15, ge=0.0, le=1.0)
    visual_relevance: float = Field(default=0.10, ge=0.0, le=1.0)
    channel_guideline_compliance: float = Field(default=0.10, ge=0.0, le=1.0)
    production_readiness: float = Field(default=0.05, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _validate_sum(self) -> "EvaluationWeights":
        total = round(
            self.factual_accuracy
            + self.research_quality
            + self.script_quality
            + self.teaching_clarity
            + self.visual_relevance
            + self.channel_guideline_compliance
            + self.production_readiness,
            4,
        )
        if abs(total - 1.0) > 0.001:
            raise ValueError(f"Evaluation weights must sum to 1.0 (got {total}).")
        return self


class EvaluationDimensionScores(BaseModel):
    factual_accuracy: float = Field(ge=0.0, le=100.0)
    research_quality: float = Field(ge=0.0, le=100.0)
    script_quality: float = Field(ge=0.0, le=100.0)
    teaching_clarity: float = Field(ge=0.0, le=100.0)
    visual_relevance: float = Field(ge=0.0, le=100.0)
    channel_guideline_compliance: float = Field(ge=0.0, le=100.0)
    production_readiness: float = Field(ge=0.0, le=100.0)


class LatencyCostSummary(BaseModel):
    total_llm_calls: int = 0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_estimated_cost_usd: float = 0.0
    avg_latency_ms: float = 0.0
    max_latency_ms: int = 0


class LLMJudgeOutput(BaseModel):
    teaching_clarity_score: float = Field(ge=0.0, le=100.0)
    script_quality_score: float = Field(ge=0.0, le=100.0)
    feedback: str = Field(min_length=10)


class EvaluationReport(BaseModel):
    evaluation_id: str
    project_id: str
    evaluator: str
    model: str | None = None
    evaluation_prompt_version: str = EVALUATION_PROMPT_VERSION
    weights: EvaluationWeights
    dimension_scores: EvaluationDimensionScores
    overall_score: float = Field(ge=0.0, le=100.0)
    feedback: str
    latency_cost_summary: LatencyCostSummary
    human_review_required: bool = True
    report_artifact_id: str | None = None
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


def compute_weighted_score(
    scores: EvaluationDimensionScores,
    weights: EvaluationWeights,
) -> float:
    weighted = (
        scores.factual_accuracy * weights.factual_accuracy
        + scores.research_quality * weights.research_quality
        + scores.script_quality * weights.script_quality
        + scores.teaching_clarity * weights.teaching_clarity
        + scores.visual_relevance * weights.visual_relevance
        + scores.channel_guideline_compliance * weights.channel_guideline_compliance
        + scores.production_readiness * weights.production_readiness
    )
    return round(max(0.0, min(100.0, weighted)), 2)
