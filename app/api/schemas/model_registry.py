from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

RegistryProviderName = Literal[
    "ollama",
    "openrouter",
    "groq",
    "gemini",
    "openai",
    "anthropic",
    "openai_compatible",
]
ModelTierName = Literal["local_small", "cloud_free", "cloud_powerful"]


class RegisteredModelCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    provider: RegistryProviderName
    model_id: str = Field(min_length=1, max_length=180)
    base_url: str | None = Field(default=None, max_length=300)
    api_key: str | None = Field(default=None, max_length=400)
    tier: ModelTierName | None = None
    input_cost_per_1m: float = Field(default=0.0, ge=0.0)
    output_cost_per_1m: float = Field(default=0.0, ge=0.0)
    notes: str | None = Field(default=None, max_length=1000)


class RegisteredModelUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    provider: RegistryProviderName | None = None
    model_id: str | None = Field(default=None, min_length=1, max_length=180)
    base_url: str | None = Field(default=None, max_length=300)
    api_key: str | None = Field(default=None, max_length=400)
    tier: ModelTierName | None = None
    input_cost_per_1m: float | None = Field(default=None, ge=0.0)
    output_cost_per_1m: float | None = Field(default=None, ge=0.0)
    is_active: bool | None = None
    notes: str | None = Field(default=None, max_length=1000)


class RegisteredModelResponse(BaseModel):
    id: str
    name: str
    provider: str
    model_id: str
    base_url: str
    tier: str
    is_cloud: bool
    input_cost_per_1m: float
    output_cost_per_1m: float
    is_active: bool
    notes: str | None = None
    has_api_key: bool = False
    api_key_hint: str | None = None
    created_at: datetime
    updated_at: datetime


class ModelRegistryListResponse(BaseModel):
    items: list[RegisteredModelResponse]
    total: int
    presets: list[dict[str, Any]] = Field(default_factory=list)


class ModelTestResponse(BaseModel):
    registry_id: str
    name: str
    provider: str
    model_id: str
    ok: bool
    latency_ms: int = 0
    reply_preview: str | None = None
    error: str | None = None
