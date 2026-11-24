from typing import Literal

from pydantic import BaseModel, Field

NarrationLanguage = Literal["Hinglish", "English"]
AudienceLevel = Literal[
    "Beginner",
    "Intermediate (Data/AI Engineers)",
    "Advanced",
]


LLMProviderPreference = Literal[
    "default",
    "ollama",
    "cloud",
    "gemini",
    "openai",
    "anthropic",
    "openai_compatible",
]


class ProjectConfig(BaseModel):
    duration_minutes: int = Field(default=15, ge=5, le=60)
    language: NarrationLanguage = "Hinglish"
    audience_level: AudienceLevel = "Intermediate (Data/AI Engineers)"
    include_code_demo: bool = True
    include_animations: bool = True
    cloud_fallback_enabled: bool = False
    auto_approve: bool = False
    llm_provider: LLMProviderPreference = "default"
    llm_model: str | None = Field(default=None, max_length=120)
