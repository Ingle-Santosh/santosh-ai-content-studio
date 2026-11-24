from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.schemas.competitor import (
    CompetitorRunRequest,
    CompetitorRunResponse,
    CompetitorVideoListResponse,
    CompetitorVideoResponse,
)
from app.dependencies import get_competitor_service
from content_studio.providers.llm import LLMError
from content_studio.services import CompetitorService, ResourceNotFoundError

router = APIRouter(prefix="/api/projects/{project_id}/competitors", tags=["competitors"])


@router.post("/run", response_model=CompetitorRunResponse)
async def run_competitor_analysis(
    project_id: str,
    payload: CompetitorRunRequest,
    service: Annotated[CompetitorService, Depends(get_competitor_service)],
) -> CompetitorRunResponse:
    try:
        return await service.run_analysis(
            project_id,
            queries=payload.queries,
            video_urls=payload.video_urls,
            max_results=payload.max_results,
            analyze_with_llm=payload.analyze_with_llm,
            run_id=payload.run_id,
        )
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except LLMError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.get("", response_model=CompetitorVideoListResponse)
async def list_competitors(
    project_id: str,
    service: Annotated[CompetitorService, Depends(get_competitor_service)],
) -> CompetitorVideoListResponse:
    try:
        videos = await service.list_competitors(project_id)
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    items = [CompetitorVideoResponse.model_validate(item) for item in videos]
    return CompetitorVideoListResponse(items=items, total=len(items))
