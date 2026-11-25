from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.schemas.model_registry import (
    ModelRegistryListResponse,
    ModelTestResponse,
    RegisteredModelCreateRequest,
    RegisteredModelResponse,
    RegisteredModelUpdateRequest,
)
from app.dependencies import get_model_registry_service
from content_studio.database.models.registered_model import RegisteredModel
from content_studio.services import ModelRegistryService, ResourceNotFoundError

router = APIRouter(prefix="/api/models/registry", tags=["model_registry"])


def _to_response(
    entry: RegisteredModel,
    service: ModelRegistryService,
) -> RegisteredModelResponse:
    has_key, hint = service.key_metadata(entry.id)
    return RegisteredModelResponse(
        id=entry.id,
        name=entry.name,
        provider=entry.provider,
        model_id=entry.model_id,
        base_url=entry.base_url,
        tier=entry.tier,
        is_cloud=entry.is_cloud,
        input_cost_per_1m=entry.input_cost_per_1m,
        output_cost_per_1m=entry.output_cost_per_1m,
        is_active=entry.is_active,
        notes=entry.notes,
        has_api_key=has_key,
        api_key_hint=hint,
        created_at=entry.created_at,
        updated_at=entry.updated_at,
    )


@router.get("", response_model=ModelRegistryListResponse)
async def list_registered_models(
    service: Annotated[ModelRegistryService, Depends(get_model_registry_service)],
) -> ModelRegistryListResponse:
    rows = await service.list_models()
    items = [_to_response(row, service) for row in rows]
    return ModelRegistryListResponse(
        items=items,
        total=len(items),
        presets=service.list_presets(),
    )


@router.post("", response_model=RegisteredModelResponse, status_code=status.HTTP_201_CREATED)
async def register_model(
    payload: RegisteredModelCreateRequest,
    service: Annotated[ModelRegistryService, Depends(get_model_registry_service)],
) -> RegisteredModelResponse:
    try:
        row = await service.register_model(
            name=payload.name,
            provider=payload.provider,
            model_id=payload.model_id,
            base_url=payload.base_url,
            api_key=payload.api_key,
            tier=payload.tier,
            input_cost_per_1m=payload.input_cost_per_1m,
            output_cost_per_1m=payload.output_cost_per_1m,
            notes=payload.notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _to_response(row, service)


@router.patch("/{registry_id}", response_model=RegisteredModelResponse)
async def update_registered_model(
    registry_id: str,
    payload: RegisteredModelUpdateRequest,
    service: Annotated[ModelRegistryService, Depends(get_model_registry_service)],
) -> RegisteredModelResponse:
    try:
        row = await service.update_model(
            registry_id,
            name=payload.name,
            provider=payload.provider,
            model_id=payload.model_id,
            base_url=payload.base_url,
            api_key=payload.api_key,
            tier=payload.tier,
            input_cost_per_1m=payload.input_cost_per_1m,
            output_cost_per_1m=payload.output_cost_per_1m,
            is_active=payload.is_active,
            notes=payload.notes,
        )
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _to_response(row, service)


@router.delete("/{registry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_registered_model(
    registry_id: str,
    service: Annotated[ModelRegistryService, Depends(get_model_registry_service)],
) -> Response:
    try:
        await service.delete_model(registry_id)
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{registry_id}/test", response_model=ModelTestResponse)
async def test_registered_model(
    registry_id: str,
    service: Annotated[ModelRegistryService, Depends(get_model_registry_service)],
) -> ModelTestResponse:
    try:
        result = await service.test_model_connection(registry_id)
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return ModelTestResponse.model_validate(result.model_dump())
