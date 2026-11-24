from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


class TaskType(StrEnum):
    TOPIC_STRATEGY = "topic_strategy"
    RESEARCH_SYNTHESIS = "research_synthesis"
    FACT_CHECK = "fact_check"
    SCRIPTWRITING = "scriptwriting"
    STORYBOARD = "storyboard"
    ASSET_PLANNING = "asset_planning"
    CODE_GENERATION = "code_generation"
    QA_REVIEW = "qa_review"
    METADATA = "metadata"
    GENERAL = "general"


class LLMMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1)


class LLMRequest(BaseModel):
    messages: list[LLMMessage] = Field(min_length=1)
    model: str = Field(min_length=1)
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, gt=0)
    json_mode: bool = False
    json_schema: dict[str, Any] | None = None
    timeout_seconds: float | None = Field(default=None, gt=0.0)


class LLMUsage(BaseModel):
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    estimated_cost_usd: float = Field(default=0.0, ge=0.0)
    latency_ms: int = Field(default=0, ge=0)

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class LLMResponse(BaseModel):
    provider: str
    model: str
    content: str
    usage: LLMUsage = Field(default_factory=LLMUsage)
    finish_reason: str | None = None
    raw_metadata: dict[str, Any] = Field(default_factory=dict)


class ProviderHealth(BaseModel):
    provider: str
    is_cloud: bool
    available: bool
    base_url: str | None = None
    models: list[str] = Field(default_factory=list)
    error: str | None = None


class RouteDecision(BaseModel):
    task: TaskType
    provider: str
    model: str
    is_cloud: bool
    fallback_reason: str | None = None


class LLMError(RuntimeError):
    """Base exception for all LLM provider and routing errors."""


class LLMConfigurationError(LLMError):
    """Raised when provider configuration or credentials are missing/invalid."""


class LLMProviderError(LLMError):
    """Raised on non-retryable provider errors (4xx auth/request failures, malformed responses)."""


class LLMTransientError(LLMError):
    """Raised on transient provider failures (network errors, 429, 5xx) eligible for retry."""


class LLMTimeoutError(LLMTransientError):
    """Raised when an LLM request exceeds its configured timeout."""


class StructuredOutputError(LLMError):
    """Raised when model output cannot be parsed or validated against the target Pydantic schema."""


class BudgetExceededError(LLMError):
    """Raised when a cloud LLM call is blocked by global or per-project budget caps."""
