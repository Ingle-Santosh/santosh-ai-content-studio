from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.schemas.fact_check import (
    ClaimListResponse,
    ClaimResponse,
    FactCheckRunRequest,
    FactCheckRunResponse,
)
from app.dependencies import get_fact_check_service
from content_studio.database.models.enums import ClaimVerdict
from content_studio.providers.llm import LLMError
from content_studio.services import FactCheckService, ResourceNotFoundError

router = APIRouter(prefix="/api/projects/{project_id}/fact-check", tags=["fact-check"])


@router.post("/run", response_model=FactCheckRunResponse)
async def run_fact_check(
    project_id: str,
    payload: FactCheckRunRequest,
    service: Annotated[FactCheckService, Depends(get_fact_check_service)],
) -> FactCheckRunResponse:
    try:
        return await service.run_fact_check(
            project_id,
            custom_claims=payload.custom_claims,
            request_research_approval=payload.request_research_approval,
            run_id=payload.run_id,
        )
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except LLMError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.get("/claims", response_model=ClaimListResponse)
async def list_claims(
    project_id: str,
    service: Annotated[FactCheckService, Depends(get_fact_check_service)],
    verdict: Annotated[ClaimVerdict | None, Query()] = None,
) -> ClaimListResponse:
    try:
        claims = await service.list_claims(project_id, verdict=verdict)
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    items = [ClaimResponse.model_validate(item) for item in claims]
    return ClaimListResponse(items=items, total=len(items))
