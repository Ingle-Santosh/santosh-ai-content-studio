from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.schemas.artifact import ArtifactResponse
from app.api.schemas.production import (
    LatestProductionExportResponse,
    ProductionPackageBuildRequest,
    ProductionPackageBuildResponse,
    YouTubeMetadataGenerateRequest,
    YouTubeMetadataGenerateResponse,
)
from app.dependencies import get_production_service, get_youtube_strategy_service
from content_studio.providers.llm import LLMError
from content_studio.services import (
    ProductionService,
    ResourceNotFoundError,
    YouTubeStrategyService,
)

router = APIRouter(prefix="/api/projects/{project_id}/production", tags=["production"])


@router.post("/youtube-metadata", response_model=YouTubeMetadataGenerateResponse)
async def generate_youtube_metadata(
    project_id: str,
    payload: YouTubeMetadataGenerateRequest,
    service: Annotated[YouTubeStrategyService, Depends(get_youtube_strategy_service)],
) -> YouTubeMetadataGenerateResponse:
    try:
        return await service.generate_metadata(project_id, run_id=payload.run_id)
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except LLMError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.post("/package", response_model=ProductionPackageBuildResponse)
async def build_production_package(
    project_id: str,
    payload: ProductionPackageBuildRequest,
    service: Annotated[ProductionService, Depends(get_production_service)],
) -> ProductionPackageBuildResponse:
    try:
        return await service.build_production_package(
            project_id,
            include_youtube_metadata=payload.include_youtube_metadata,
            request_final_approval=payload.request_final_approval,
            run_id=payload.run_id,
        )
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except LLMError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.get("/latest", response_model=LatestProductionExportResponse)
async def get_latest_production_export(
    project_id: str,
    service: Annotated[ProductionService, Depends(get_production_service)],
) -> LatestProductionExportResponse:
    try:
        export_art = await service.get_latest_export(project_id)
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    if export_art is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No production export bundle exists yet for project '{project_id}'.",
        )
    meta = export_art.metadata_json or {}
    return LatestProductionExportResponse(
        export_artifact=ArtifactResponse.model_validate(export_art),
        publishing_mode=str(meta.get("publishing_mode", "MANUAL_ONLY")),
        included_files=list(meta.get("included_files") or []),
    )
