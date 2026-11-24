from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.schemas.artifact import (
    ArtifactContentResponse,
    ArtifactCreateRequest,
    ArtifactIntegrityResponse,
    ArtifactListResponse,
    ArtifactResponse,
    ArtifactStatusUpdateRequest,
)
from app.dependencies import get_artifact_service
from content_studio.database.models.enums import ArtifactType
from content_studio.services import (
    ArtifactFileMissingError,
    ArtifactService,
    ResourceNotFoundError,
)

router = APIRouter(prefix="/api/projects/{project_id}/artifacts", tags=["artifacts"])


@router.post("", response_model=ArtifactResponse, status_code=status.HTTP_201_CREATED)
async def create_artifact(
    project_id: str,
    payload: ArtifactCreateRequest,
    service: Annotated[ArtifactService, Depends(get_artifact_service)],
) -> ArtifactResponse:
    try:
        artifact = await service.save_text(
            project_id=project_id,
            stage=payload.stage,
            artifact_type=payload.artifact_type,
            name=payload.name,
            content=payload.content,
            relative_path=payload.relative_path,
            run_id=payload.run_id,
            status=payload.status,
            metadata_json=payload.metadata_json,
            supersede_previous_drafts=payload.supersede_previous_drafts,
        )
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ArtifactResponse.model_validate(artifact)


@router.get("", response_model=ArtifactListResponse)
async def list_artifacts(
    project_id: str,
    service: Annotated[ArtifactService, Depends(get_artifact_service)],
    stage: Annotated[str | None, Query()] = None,
    artifact_type: Annotated[ArtifactType | None, Query()] = None,
) -> ArtifactListResponse:
    try:
        artifacts = await service.list_artifacts(
            project_id,
            stage=stage,
            artifact_type=artifact_type,
        )
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    items = [ArtifactResponse.model_validate(item) for item in artifacts]
    return ArtifactListResponse(items=items, total=len(items))


@router.get("/{artifact_id}", response_model=ArtifactResponse)
async def get_artifact(
    project_id: str,
    artifact_id: str,
    service: Annotated[ArtifactService, Depends(get_artifact_service)],
) -> ArtifactResponse:
    try:
        artifact = await service.get_artifact(project_id, artifact_id)
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return ArtifactResponse.model_validate(artifact)


@router.get("/{artifact_id}/content", response_model=ArtifactContentResponse)
async def get_artifact_content(
    project_id: str,
    artifact_id: str,
    service: Annotated[ArtifactService, Depends(get_artifact_service)],
) -> ArtifactContentResponse:
    try:
        artifact, text = await service.read_artifact_text(project_id, artifact_id)
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ArtifactFileMissingError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Artifact content is binary and cannot be decoded as UTF-8 text.",
        ) from exc
    return ArtifactContentResponse(
        artifact=ArtifactResponse.model_validate(artifact),
        content=text,
    )


@router.get("/{artifact_id}/verify", response_model=ArtifactIntegrityResponse)
async def verify_artifact_integrity(
    project_id: str,
    artifact_id: str,
    service: Annotated[ArtifactService, Depends(get_artifact_service)],
) -> ArtifactIntegrityResponse:
    try:
        report = await service.verify_integrity(project_id, artifact_id)
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return ArtifactIntegrityResponse.model_validate(report.model_dump())


@router.patch("/{artifact_id}", response_model=ArtifactResponse)
async def update_artifact_status(
    project_id: str,
    artifact_id: str,
    payload: ArtifactStatusUpdateRequest,
    service: Annotated[ArtifactService, Depends(get_artifact_service)],
) -> ArtifactResponse:
    try:
        updated = await service.update_status(project_id, artifact_id, payload.status)
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return ArtifactResponse.model_validate(updated)
