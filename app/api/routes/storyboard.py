from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.schemas.storyboard import (
    SceneListResponse,
    SceneResponse,
    StoryboardGenerateRequest,
    StoryboardGenerateResponse,
)
from app.dependencies import get_storyboard_service
from content_studio.providers.llm import LLMError
from content_studio.services import (
    ResourceNotFoundError,
    StoryboardService,
    WorkflowGateError,
)

router = APIRouter(prefix="/api/projects/{project_id}/storyboard", tags=["storyboard"])


@router.post("/generate", response_model=StoryboardGenerateResponse)
async def generate_storyboard(
    project_id: str,
    payload: StoryboardGenerateRequest,
    service: Annotated[StoryboardService, Depends(get_storyboard_service)],
) -> StoryboardGenerateResponse:
    try:
        return await service.generate_storyboard(
            project_id,
            script_version_number=payload.script_version_number,
            require_approved_script=payload.require_approved_script,
            run_id=payload.run_id,
        )
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except WorkflowGateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except LLMError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.get("/scenes", response_model=SceneListResponse)
async def list_scenes(
    project_id: str,
    service: Annotated[StoryboardService, Depends(get_storyboard_service)],
) -> SceneListResponse:
    try:
        scenes = await service.list_scenes(project_id)
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    items = [SceneResponse.model_validate(item) for item in scenes]
    return SceneListResponse(items=items, total=len(items))
