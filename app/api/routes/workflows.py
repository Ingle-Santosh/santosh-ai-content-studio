from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.schemas.workflow import (
    WorkflowResumeRequest,
    WorkflowRunListResponse,
    WorkflowRunSnapshotResponse,
    WorkflowRunSummaryResponse,
    WorkflowStartRequest,
)
from app.dependencies import get_workflow_orchestrator
from content_studio.providers.llm import LLMError
from content_studio.services import ResourceNotFoundError
from content_studio.workflows import WorkflowOrchestrator, WorkflowStateError

router = APIRouter(tags=["workflows"])


@router.post(
    "/api/projects/{project_id}/workflows/start",
    response_model=WorkflowRunSnapshotResponse,
    status_code=status.HTTP_201_CREATED,
)
async def start_workflow(
    project_id: str,
    payload: WorkflowStartRequest,
    orchestrator: Annotated[WorkflowOrchestrator, Depends(get_workflow_orchestrator)],
) -> WorkflowRunSnapshotResponse:
    try:
        return await orchestrator.start_workflow(
            project_id,
            seed_urls=payload.seed_urls,
            max_results_per_query=payload.max_results_per_query,
            auto_approve=payload.auto_approve,
        )
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except LLMError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.get(
    "/api/projects/{project_id}/workflows",
    response_model=WorkflowRunListResponse,
)
async def list_project_workflows(
    project_id: str,
    orchestrator: Annotated[WorkflowOrchestrator, Depends(get_workflow_orchestrator)],
) -> WorkflowRunListResponse:
    try:
        runs = await orchestrator.list_project_runs(project_id)
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    items = [WorkflowRunSummaryResponse.model_validate(item) for item in runs]
    return WorkflowRunListResponse(items=items, total=len(items))


@router.get(
    "/api/workflows/{run_id}",
    response_model=WorkflowRunSnapshotResponse,
)
async def get_workflow_status(
    run_id: str,
    orchestrator: Annotated[WorkflowOrchestrator, Depends(get_workflow_orchestrator)],
) -> WorkflowRunSnapshotResponse:
    try:
        return await orchestrator.get_workflow_status(run_id)
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post(
    "/api/workflows/{run_id}/resume",
    response_model=WorkflowRunSnapshotResponse,
)
async def resume_workflow(
    run_id: str,
    payload: WorkflowResumeRequest,
    orchestrator: Annotated[WorkflowOrchestrator, Depends(get_workflow_orchestrator)],
) -> WorkflowRunSnapshotResponse:
    try:
        return await orchestrator.resume_workflow(
            run_id,
            decision=payload.decision,
            reviewer=payload.reviewer,
            comments=payload.comments,
        )
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except WorkflowStateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except LLMError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.post(
    "/api/workflows/{run_id}/cancel",
    response_model=WorkflowRunSnapshotResponse,
)
async def cancel_workflow(
    run_id: str,
    orchestrator: Annotated[WorkflowOrchestrator, Depends(get_workflow_orchestrator)],
) -> WorkflowRunSnapshotResponse:
    try:
        return await orchestrator.cancel_workflow(run_id)
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
