from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from content_studio.providers.llm.types import ProviderHealth


class LLMStatusResponse(BaseModel):
    local_only: bool
    max_budget_usd: float
    current_global_spend_usd: float
    providers: list[ProviderHealth]
    routing_table: dict[str, dict[str, Any]]


class UsageLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    run_id: str | None
    provider: str
    model: str
    node_name: str
    prompt_tokens: int
    completion_tokens: int
    estimated_cost_usd: float
    latency_ms: int
    created_at: datetime


class ProjectUsageSummaryResponse(BaseModel):
    project_id: str
    total_calls: int
    total_prompt_tokens: int
    total_completion_tokens: int
    total_estimated_cost_usd: float
    items: list[UsageLogResponse]
