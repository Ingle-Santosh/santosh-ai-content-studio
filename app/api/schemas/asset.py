from pydantic import BaseModel, Field

from content_studio.contracts.assets import (
    AssetGenerationBatchReport,
    AssetPlan,
    AssetQAReport,
    ScreenshotAnnotation,
    ScreenshotProvenance,
)


class AssetGenerateRequest(BaseModel):
    asset_keys: list[str] | None = Field(default=None, max_length=50)
    run_qa: bool = False
    request_assets_approval: bool = False
    run_id: str | None = None


class AssetQARunRequest(BaseModel):
    request_assets_approval: bool = True
    run_id: str | None = None


class ScreenshotUploadRequest(BaseModel):
    filename: str = Field(min_length=3, max_length=200)
    content_base64: str = Field(min_length=4)
    provenance: ScreenshotProvenance
    scene_number: int | None = Field(default=None, ge=1)
    annotations: list[ScreenshotAnnotation] = Field(default_factory=list)
    run_id: str | None = None


class ScreenshotUploadResponse(BaseModel):
    screenshot_artifact_id: str
    overlay_artifact_id: str | None = None
    relative_path: str
    checksum_sha256: str | None = None


AssetPlanResponse = AssetPlan
AssetGenerateResponse = AssetGenerationBatchReport
AssetQAResponse = AssetQAReport
