from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.schemas.approval import (
    ApprovalCreateRequest,
    ApprovalDecisionRequest,
    ApprovalListResponse,
    ApprovalResponse,
)
from app.dependencies import get_approval_service
from content_studio.database.models.enums import ApprovalGate, ApprovalStatus
from content_studio.services import ApprovalService, ResourceNotFoundError

router = APIRouter(tags=["approvals"])


@router.post(
    "/api/projects/{project_id}/approvals",
    response_model=ApprovalResponse,
    status_code=status.HTTP_201_CREATED,
)
async def request_approval(
    project_id: str,
    payload: ApprovalCreateRequest,
    service: Annotated[ApprovalService, Depends(get_approval_service)],
) -> ApprovalResponse:
    try:
        approval = await service.request_approval(
            project_id=project_id,
            gate=payload.gate,
            run_id=payload.run_id,
            artifact_id=payload.artifact_id,
            comments=payload.comments,
        )
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return ApprovalResponse.model_validate(approval)


@router.get("/api/approvals", response_model=ApprovalListResponse)
async def list_approvals(
    service: Annotated[ApprovalService, Depends(get_approval_service)],
    project_id: Annotated[str | None, Query()] = None,
    status_filter: Annotated[ApprovalStatus | None, Query(alias="status")] = None,
    gate: Annotated[ApprovalGate | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> ApprovalListResponse:
    approvals = await service.list_approvals(
        project_id=project_id,
        status=status_filter,
        gate=gate,
        limit=limit,
    )
    items = [ApprovalResponse.model_validate(item) for item in approvals]
    return ApprovalListResponse(items=items, total=len(items))


@router.patch("/api/approvals/{approval_id}", response_model=ApprovalResponse)
async def decide_approval(
    approval_id: str,
    payload: ApprovalDecisionRequest,
    service: Annotated[ApprovalService, Depends(get_approval_service)],
) -> ApprovalResponse:
    try:
        updated = await service.decide_approval(
            approval_id,
            status=payload.status,
            reviewer=payload.reviewer,
            comments=payload.comments,
        )
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ApprovalResponse.model_validate(updated)
