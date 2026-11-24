from pydantic import BaseModel

from app.api.schemas.artifact import ArtifactResponse
from content_studio.contracts.production import (
    ProductionPackageReport,
    YouTubeMetadataReport,
)


class YouTubeMetadataGenerateRequest(BaseModel):
    run_id: str | None = None


class ProductionPackageBuildRequest(BaseModel):
    include_youtube_metadata: bool = True
    request_final_approval: bool = True
    run_id: str | None = None


class LatestProductionExportResponse(BaseModel):
    export_artifact: ArtifactResponse
    publishing_mode: str = "MANUAL_ONLY"
    included_files: list[str]


YouTubeMetadataGenerateResponse = YouTubeMetadataReport
ProductionPackageBuildResponse = ProductionPackageReport
