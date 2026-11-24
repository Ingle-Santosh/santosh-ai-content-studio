from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.schemas.script import (
    ScriptApproveRequest,
    ScriptGenerateRequest,
    ScriptGenerateResponse,
    ScriptManualRevisionRequest,
    ScriptResponse,
    ScriptVersionResponse,
)
from app.dependencies import get_scriptwriter_service
from content_studio.providers.llm import LLMError
from content_studio.services import (
    ResourceNotFoundError,
    ScriptwriterService,
    WorkflowGateError,
)

router = APIRouter(prefix="/api/projects/{project_id}/scripts", tags=["scripts"])


@router.post("/generate", response_model=ScriptGenerateResponse)
async def generate_script(
    project_id: str,
    payload: ScriptGenerateRequest,
    service: Annotated[ScriptwriterService, Depends(get_scriptwriter_service)],
) -> ScriptGenerateResponse:
    try:
        return await service.generate_script(
            project_id,
            revision_notes=payload.revision_notes,
            require_approved_research=payload.require_approved_research,
            request_script_approval=payload.request_script_approval,
            run_id=payload.run_id,
        )
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except WorkflowGateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except LLMError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.post(
    "/revisions",
    response_model=ScriptGenerateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def save_manual_revision(
    project_id: str,
    payload: ScriptManualRevisionRequest,
    service: Annotated[ScriptwriterService, Depends(get_scriptwriter_service)],
) -> ScriptGenerateResponse:
    try:
        return await service.save_manual_revision(
            project_id,
            title=payload.title,
            language=payload.language,
            sections=payload.sections,
            revision_notes=payload.revision_notes,
            request_script_approval=payload.request_script_approval,
        )
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("", response_model=ScriptResponse)
async def get_script(
    project_id: str,
    service: Annotated[ScriptwriterService, Depends(get_scriptwriter_service)],
) -> ScriptResponse:
    try:
        script = await service.get_script(project_id)
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if script is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No script exists yet for project '{project_id}'.",
        )
    return ScriptResponse.model_validate(script)


@router.post(
    "/versions/{version_number}/approve",
    response_model=ScriptVersionResponse,
)
async def approve_script_version(
    project_id: str,
    version_number: int,
    payload: ScriptApproveRequest,
    service: Annotated[ScriptwriterService, Depends(get_scriptwriter_service)],
) -> ScriptVersionResponse:
    try:
        approved = await service.approve_version(
            project_id,
            version_number,
            reviewer=payload.reviewer,
            comments=payload.comments,
        )
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return ScriptVersionResponse.model_validate(approved)
