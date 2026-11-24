from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.schemas.health import HealthResponse
from app.dependencies import get_settings
from content_studio.config.settings import Settings

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health_check(
    app_settings: Annotated[Settings, Depends(get_settings)],
) -> HealthResponse:
    return HealthResponse(
        status="ok",
        env=app_settings.APP_ENV,
        local_only=app_settings.LOCAL_ONLY,
        data_dir=str(app_settings.resolved_data_dir),
        ollama_base_url=app_settings.OLLAMA_BASE_URL,
        default_model=app_settings.OLLAMA_DEFAULT_MODEL,
    )
