from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.schemas.evaluation import (
    EvaluationListResponse,
    EvaluationRecordResponse,
    EvaluationRunRequest,
    EvaluationRunResponse,
)
from app.dependencies import get_evaluation_service
from content_studio.evaluation import EvaluationService
from content_studio.providers.llm import LLMError
from content_studio.services import ResourceNotFoundError

router = APIRouter(prefix="/api/projects/{project_id}/evaluations", tags=["evaluations"])


@router.post("/run", response_model=EvaluationRunResponse)
async def run_evaluation(
    project_id: str,
    payload: EvaluationRunRequest,
    service: Annotated[EvaluationService, Depends(get_evaluation_service)],
) -> EvaluationRunResponse:
    try:
        return await service.evaluate_project(
            project_id,
            weights=payload.weights,
            use_llm_judge=payload.use_llm_judge,
        )
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except LLMError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.get("", response_model=EvaluationListResponse)
async def list_evaluations(
    project_id: str,
    service: Annotated[EvaluationService, Depends(get_evaluation_service)],
) -> EvaluationListResponse:
    try:
        records = await service.list_evaluations(project_id)
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    items = [EvaluationRecordResponse.model_validate(item) for item in records]
    return EvaluationListResponse(items=items, total=len(items))
