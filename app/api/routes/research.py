from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.schemas.research import (
    ResearchFindingListResponse,
    ResearchFindingResponse,
    ResearchRunRequest,
    ResearchRunResponse,
    SourceListResponse,
    SourceResponse,
)
from app.dependencies import get_research_service
from content_studio.database.models.enums import SourceStatus
from content_studio.providers.llm import LLMError
from content_studio.services import ResearchService, ResourceNotFoundError

router = APIRouter(prefix="/api/projects/{project_id}/research", tags=["research"])


@router.post("/run", response_model=ResearchRunResponse)
async def run_research(
    project_id: str,
    payload: ResearchRunRequest,
    service: Annotated[ResearchService, Depends(get_research_service)],
) -> ResearchRunResponse:
    try:
        return await service.run_research(
            project_id,
            queries=payload.queries,
            seed_urls=payload.seed_urls,
            max_results_per_query=payload.max_results_per_query,
            synthesize_with_llm=payload.synthesize_with_llm,
            run_id=payload.run_id,
        )
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except LLMError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.get("/sources", response_model=SourceListResponse)
async def list_sources(
    project_id: str,
    service: Annotated[ResearchService, Depends(get_research_service)],
    status_filter: Annotated[SourceStatus | None, Query(alias="status")] = None,
) -> SourceListResponse:
    try:
        sources = await service.list_sources(project_id, status=status_filter)
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    items = [SourceResponse.model_validate(item) for item in sources]
    return SourceListResponse(items=items, total=len(items))


@router.get("/findings", response_model=ResearchFindingListResponse)
async def list_findings(
    project_id: str,
    service: Annotated[ResearchService, Depends(get_research_service)],
) -> ResearchFindingListResponse:
    try:
        findings = await service.list_findings(project_id)
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    items = [ResearchFindingResponse.model_validate(item) for item in findings]
    return ResearchFindingListResponse(items=items, total=len(items))
