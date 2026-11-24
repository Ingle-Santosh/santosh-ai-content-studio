from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.schemas.guideline import (
    ChannelGuidelineListResponse,
    ChannelGuidelineResponse,
    ChannelGuidelineUpsertRequest,
)
from app.dependencies import get_guideline_service
from content_studio.services import ChannelGuidelineService

router = APIRouter(prefix="/api/guidelines", tags=["guidelines"])


@router.get("", response_model=ChannelGuidelineListResponse)
async def list_guidelines(
    service: Annotated[ChannelGuidelineService, Depends(get_guideline_service)],
) -> ChannelGuidelineListResponse:
    records = await service.list_guidelines()
    items = [ChannelGuidelineResponse.model_validate(record) for record in records]
    return ChannelGuidelineListResponse(items=items, total=len(items))


@router.get("/active", response_model=ChannelGuidelineResponse)
async def get_active_guideline(
    service: Annotated[ChannelGuidelineService, Depends(get_guideline_service)],
) -> ChannelGuidelineResponse:
    record = await service.get_or_create_active()
    return ChannelGuidelineResponse.model_validate(record)


@router.put("/{slug}", response_model=ChannelGuidelineResponse)
async def upsert_guideline(
    slug: str,
    payload: ChannelGuidelineUpsertRequest,
    service: Annotated[ChannelGuidelineService, Depends(get_guideline_service)],
) -> ChannelGuidelineResponse:
    try:
        record = await service.upsert_guideline(
            slug=slug,
            channel_name=payload.channel_name,
            guidelines=payload.guidelines,
            is_active=payload.is_active,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ChannelGuidelineResponse.model_validate(record)
