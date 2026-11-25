from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from content_studio.providers.llm.types import ProviderHealth

CloudProviderName = Literal[
    "gemini", "openai", "anthropic", "openrouter", "groq", "openai_compatible"
]


class LLMConfigUpdateRequest(BaseModel):
    local_only: bool | None = None
    prefer_cloud_default: bool | None = None
    cloud_tasks: list[str] | None = None
    small_model_id: str | None = Field(default=None, max_length=64)
    powerful_model_id: str | None = Field(default=None, max_length=64)
    task_model_ids: dict[str, str] | None = None
    cloud_provider: CloudProviderName | None = None
    cloud_default_model: str | None = Field(default=None, max_length=160)
    cloud_base_url: str | None = Field(default=None, max_length=300)
    cloud_api_key: str | None = Field(default=None, max_length=400)
    ollama_default_model: str | None = Field(default=None, min_length=1, max_length=120)
    ollama_writing_model: str | None = Field(default=None, max_length=120)
    ollama_fast_model: str | None = Field(default=None, max_length=120)
    gemini_default_model: str | None = Field(default=None, min_length=1, max_length=120)
    gemini_api_key: str | None = Field(default=None, max_length=400)
    max_budget_usd: float | None = Field(default=None, ge=0.0)
    llm_timeout_seconds: float | None = Field(default=None, gt=0.0, le=900.0)


class LLMStatusResponse(BaseModel):
    local_only: bool
    prefer_cloud_default: bool = False
    cloud_tasks: list[str] = Field(default_factory=list)
    small_model_id: str | None = None
    powerful_model_id: str | None = None
    task_model_ids: dict[str, str] = Field(default_factory=dict)
    cloud_provider: str = "gemini"
    cloud_default_model: str = ""
    cloud_base_url: str = ""
    cloud_api_key_configured: bool = False
    max_budget_usd: float
    current_global_spend_usd: float
    ollama_default_model: str = ""
    ollama_writing_model: str | None = None
    ollama_fast_model: str | None = None
    gemini_default_model: str = ""
    gemini_api_key_configured: bool = False
    llm_timeout_seconds: float = 180.0
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
