from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.api.schemas.project import (
    ProjectCreateRequest,
    ProjectListResponse,
    ProjectResponse,
    ProjectUpdateRequest,
)
from app.dependencies import get_artifact_store, get_project_repository
from content_studio.database.models.enums import ProjectStatus
from content_studio.database.repositories.project_repository import ProjectRepository
from content_studio.storage.artifact_store import ArtifactStore

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: ProjectCreateRequest,
    repo: Annotated[ProjectRepository, Depends(get_project_repository)],
    store: Annotated[ArtifactStore, Depends(get_artifact_store)],
) -> ProjectResponse:
    title = payload.title or payload.topic[:255]
    project = await repo.create(
        title=title,
        topic=payload.topic,
        config=payload.config.model_dump(),
        budget_usd=payload.budget_usd,
    )
    await store.ainit_project_dirs(project.id)
    return ProjectResponse.model_validate(project)


@router.get("", response_model=ProjectListResponse)
async def list_projects(
    repo: Annotated[ProjectRepository, Depends(get_project_repository)],
    status_filter: Annotated[ProjectStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ProjectListResponse:
    projects = await repo.list_projects(
        status=status_filter,
        limit=limit,
        offset=offset,
    )
    items = [ProjectResponse.model_validate(project) for project in projects]
    return ProjectListResponse(items=items, total=len(items))


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: str,
    repo: Annotated[ProjectRepository, Depends(get_project_repository)],
) -> ProjectResponse:
    project = await repo.get_by_id(project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_id}' not found.",
        )
    return ProjectResponse.model_validate(project)


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: str,
    payload: ProjectUpdateRequest,
    repo: Annotated[ProjectRepository, Depends(get_project_repository)],
) -> ProjectResponse:
    project = await repo.get_by_id(project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_id}' not found.",
        )
    updated = await repo.update(
        project,
        title=payload.title,
        topic=payload.topic,
        status=payload.status,
        config=payload.config.model_dump() if payload.config is not None else None,
        budget_usd=payload.budget_usd,
    )
    return ProjectResponse.model_validate(updated)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: str,
    repo: Annotated[ProjectRepository, Depends(get_project_repository)],
    store: Annotated[ArtifactStore, Depends(get_artifact_store)],
) -> Response:
    project = await repo.get_by_id(project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_id}' not found.",
        )
    await repo.delete(project)
    await store.adelete_project_dir(project_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
