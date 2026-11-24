from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class AssetCategory(StrEnum):
    DIAGRAM = "diagram"
    ANIMATION = "animation"
    IMAGE = "image"
    SCREENSHOT = "screenshot"
    CODE_DEMO = "code_demo"


class PlannedAssetItem(BaseModel):
    asset_key: str = Field(min_length=2, max_length=120)
    scene_id: str | None = None
    scene_number: int = Field(ge=1)
    category: AssetCategory
    title: str = Field(min_length=2, max_length=200)
    description: str = Field(default="")
    filename: str = Field(min_length=3, max_length=120)
    priority: int = Field(default=1, ge=1, le=5)


class AssetPlan(BaseModel):
    project_id: str
    total_scenes: int = 0
    items: list[PlannedAssetItem] = Field(default_factory=list)
    plan_artifact_id: str | None = None
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class DiagramLLMOutput(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    diagram_type: Literal["flowchart", "sequence", "state", "er", "class"] = "flowchart"
    mermaid_code: str = Field(min_length=10)
    caption: str = Field(default="")


class AnimationStep(BaseModel):
    label: str = Field(min_length=2, max_length=120)
    description: str = Field(min_length=5, max_length=500)
    highlight_text: str | None = Field(default=None, max_length=300)


class AnimationSpecLLMOutput(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    subtitle: str = Field(default="")
    steps: list[AnimationStep] = Field(min_length=2, max_length=10)


class CodeDemoLLMOutput(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    language: Literal["python", "sql"] = "python"
    filename: str = Field(min_length=3, max_length=120)
    code: str = Field(min_length=10)
    explanation: str = Field(default="")
    expected_output_hint: str | None = None


class CodeExecutionResult(BaseModel):
    language: Literal["python", "sql"]
    passed: bool
    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""
    blocked_reasons: list[str] = Field(default_factory=list)
    duration_ms: int = 0


class ScreenshotAnnotation(BaseModel):
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    label: str = Field(min_length=1, max_length=120)
    color: str = Field(default="#ff5722", max_length=20)


class ScreenshotProvenance(BaseModel):
    source_origin: Literal["user_upload", "authorized_capture"] = "user_upload"
    captured_by: str = Field(min_length=1, max_length=120)
    source_url: str | None = Field(default=None, max_length=500)
    captured_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    notes: str | None = Field(default=None, max_length=500)


class GeneratedAssetOutcome(BaseModel):
    asset_key: str
    scene_number: int
    category: AssetCategory
    title: str
    status: Literal["SUCCEEDED", "FAILED", "SKIPPED"]
    artifact_ids: list[str] = Field(default_factory=list)
    error: str | None = None
    validation_passed: bool = True


class AssetGenerationBatchReport(BaseModel):
    project_id: str
    total_planned: int = 0
    succeeded_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    outcomes: list[GeneratedAssetOutcome] = Field(default_factory=list)
    qa_report_id: str | None = None
    approval_id: str | None = None
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AssetQACheckItem(BaseModel):
    artifact_id: str
    name: str
    artifact_type: str
    relative_path: str
    passed: bool
    checksum_valid: bool
    issues: list[str] = Field(default_factory=list)


class AssetQAReport(BaseModel):
    project_id: str
    passed: bool
    total_assets: int = 0
    passed_count: int = 0
    failed_count: int = 0
    blocking_issues: list[str] = Field(default_factory=list)
    items: list[AssetQACheckItem] = Field(default_factory=list)
    report_artifact_id: str | None = None
    approval_id: str | None = None
    checked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
