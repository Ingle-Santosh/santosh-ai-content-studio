import base64
import binascii
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.schemas.asset import (
    AssetGenerateRequest,
    AssetGenerateResponse,
    AssetPlanResponse,
    AssetQAResponse,
    AssetQARunRequest,
    ScreenshotUploadRequest,
    ScreenshotUploadResponse,
)
from app.dependencies import get_asset_generation_service, get_asset_qa_service
from content_studio.providers.llm import LLMError
from content_studio.services import (
    AssetGenerationService,
    AssetQAService,
    ResourceNotFoundError,
)

router = APIRouter(prefix="/api/projects/{project_id}/assets", tags=["assets"])


@router.post("/plan", response_model=AssetPlanResponse)
async def plan_assets(
    project_id: str,
    service: Annotated[AssetGenerationService, Depends(get_asset_generation_service)],
) -> AssetPlanResponse:
    try:
        return await service.plan_assets(project_id)
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/generate", response_model=AssetGenerateResponse)
async def generate_assets(
    project_id: str,
    payload: AssetGenerateRequest,
    service: Annotated[AssetGenerationService, Depends(get_asset_generation_service)],
    qa_service: Annotated[AssetQAService, Depends(get_asset_qa_service)],
) -> AssetGenerateResponse:
    try:
        report = await service.generate_assets(
            project_id,
            asset_keys=payload.asset_keys,
            run_id=payload.run_id,
        )
        if payload.run_qa:
            qa = await qa_service.run_qa(
                project_id,
                request_assets_approval=payload.request_assets_approval,
                run_id=payload.run_id,
            )
            report.qa_report_id = qa.report_artifact_id
            report.approval_id = qa.approval_id
        return report
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except LLMError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.post(
    "/screenshots",
    response_model=ScreenshotUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_screenshot(
    project_id: str,
    payload: ScreenshotUploadRequest,
    service: Annotated[AssetGenerationService, Depends(get_asset_generation_service)],
) -> ScreenshotUploadResponse:
    try:
        raw_bytes = base64.b64decode(payload.content_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid base64 image payload.",
        ) from exc

    try:
        shot_art, overlay_art = await service.register_screenshot(
            project_id,
            filename=payload.filename,
            content=raw_bytes,
            provenance=payload.provenance,
            scene_number=payload.scene_number,
            annotations=payload.annotations,
            run_id=payload.run_id,
        )
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return ScreenshotUploadResponse(
        screenshot_artifact_id=shot_art.id,
        overlay_artifact_id=overlay_art.id if overlay_art else None,
        relative_path=shot_art.relative_path,
        checksum_sha256=shot_art.checksum_sha256,
    )


@router.post("/qa", response_model=AssetQAResponse)
async def run_asset_qa(
    project_id: str,
    payload: AssetQARunRequest,
    qa_service: Annotated[AssetQAService, Depends(get_asset_qa_service)],
) -> AssetQAResponse:
    try:
        return await qa_service.run_qa(
            project_id,
            request_assets_approval=payload.request_assets_approval,
            run_id=payload.run_id,
        )
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
