from datetime import UTC, datetime

from pydantic import BaseModel, Field

from content_studio.database.models.enums import ScriptSectionType


class ScriptSectionItem(BaseModel):
    section_type: ScriptSectionType
    title: str = Field(min_length=2, max_length=200)
    narration: str = Field(min_length=10)
    visual_instructions: str = Field(default="")
    screen_recording_requirements: str | None = None
    code_demo_references: list[str] = Field(default_factory=list)
    estimated_duration_seconds: int = Field(default=60, ge=5, le=3600)
    source_urls: list[str] = Field(default_factory=list)


class ScriptLLMOutput(BaseModel):
    title: str = Field(min_length=3, max_length=300)
    language: str = Field(default="Hinglish")
    sections: list[ScriptSectionItem] = Field(min_length=1)


class ScriptValidationReport(BaseModel):
    passed: bool
    score: float = Field(ge=0.0, le=100.0)
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    missing_sections: list[str] = Field(default_factory=list)
    total_words: int = 0
    total_duration_seconds: int = 0
    target_duration_seconds: int = 900


class GeneratedScriptReport(BaseModel):
    script_id: str
    script_version_id: str
    project_id: str
    title: str
    version_number: int
    language: str
    status: str
    total_estimated_duration_seconds: int
    word_count: int
    sections: list[ScriptSectionItem]
    validation: ScriptValidationReport
    approval_id: str | None = None
    script_markdown_artifact_id: str | None = None
    script_json_artifact_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
