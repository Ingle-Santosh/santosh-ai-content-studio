from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from content_studio.evaluation.rubric import EvaluationReport, EvaluationWeights


class EvaluationRunRequest(BaseModel):
    weights: EvaluationWeights | None = None
    use_llm_judge: bool = False


class EvaluationRecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    evaluator: str
    model: str | None
    evaluation_prompt_version: str
    weights_json: dict[str, float]
    dimension_scores_json: dict[str, float]
    overall_score: float
    feedback: str
    latency_cost_summary_json: dict[str, Any]
    human_review_required: bool
    evaluated_at: datetime


class EvaluationListResponse(BaseModel):
    items: list[EvaluationRecordResponse]
    total: int


class SystemMetricsResponse(BaseModel):
    total_projects: int
    projects_by_status: dict[str, int]
    pending_approvals: int
    total_llm_calls: int
    total_tokens: int
    total_estimated_cost_usd: float
    avg_llm_latency_ms: float


EvaluationRunResponse = EvaluationReport
