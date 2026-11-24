from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.schemas.llm import (
    LLMConfigUpdateRequest,
    LLMStatusResponse,
    ProjectUsageSummaryResponse,
    UsageLogResponse,
)
from app.dependencies import (
    get_model_router,
    get_project_repository,
    get_settings,
    get_usage_repository,
)
from content_studio.config.runtime_llm_config import save_runtime_llm_config
from content_studio.config.settings import Settings
from content_studio.database.repositories import ProjectRepository, UsageRepository
from content_studio.providers.llm import ModelRouter, TaskType

router = APIRouter(tags=["llm"])


async def _build_llm_status(
    app_settings: Settings,
    router_svc: ModelRouter,
    usage_repo: UsageRepository,
) -> LLMStatusResponse:
    providers = await router_svc.check_providers_health()
    global_spend = await usage_repo.total_spend_all()
    active_cloud_provider = app_settings.CLOUD_LLM_PROVIDER.strip().lower()
    active_cloud_key = ModelRouter._resolve_cloud_api_key(app_settings, active_cloud_provider)
    active_cloud_url = ModelRouter._resolve_cloud_base_url(app_settings, active_cloud_provider)
    active_cloud_model = router_svc.cloud_model_for_task(TaskType.GENERAL)
    return LLMStatusResponse(
        local_only=app_settings.LOCAL_ONLY,
        prefer_cloud_default=app_settings.PREFER_CLOUD_DEFAULT,
        cloud_tasks=list(app_settings.CLOUD_TASKS),
        cloud_provider=active_cloud_provider,
        cloud_default_model=active_cloud_model,
        cloud_base_url=active_cloud_url,
        cloud_api_key_configured=bool(active_cloud_key),
        max_budget_usd=app_settings.MAX_BUDGET_USD,
        current_global_spend_usd=global_spend,
        ollama_default_model=app_settings.OLLAMA_DEFAULT_MODEL,
        ollama_writing_model=app_settings.OLLAMA_WRITING_MODEL,
        ollama_fast_model=app_settings.OLLAMA_FAST_MODEL,
        gemini_default_model=app_settings.GEMINI_DEFAULT_MODEL,
        gemini_api_key_configured=bool((app_settings.GEMINI_API_KEY or "").strip()),
        llm_timeout_seconds=app_settings.LLM_TIMEOUT_SECONDS,
        providers=providers,
        routing_table=router_svc.describe_routing_table(),
    )


@router.get("/api/llm/status", response_model=LLMStatusResponse)
async def get_llm_status(
    app_settings: Annotated[Settings, Depends(get_settings)],
    router_svc: Annotated[ModelRouter, Depends(get_model_router)],
    usage_repo: Annotated[UsageRepository, Depends(get_usage_repository)],
) -> LLMStatusResponse:
    return await _build_llm_status(app_settings, router_svc, usage_repo)


@router.patch("/api/llm/config", response_model=LLMStatusResponse)
async def update_llm_config(
    payload: LLMConfigUpdateRequest,
    app_settings: Annotated[Settings, Depends(get_settings)],
    project_repo: Annotated[ProjectRepository, Depends(get_project_repository)],
    usage_repo: Annotated[UsageRepository, Depends(get_usage_repository)],
) -> LLMStatusResponse:
    if payload.local_only is not None:
        app_settings.LOCAL_ONLY = payload.local_only
    if payload.prefer_cloud_default is not None:
        app_settings.PREFER_CLOUD_DEFAULT = payload.prefer_cloud_default
    if payload.cloud_tasks is not None:
        valid_tasks = {t.value for t in TaskType}
        app_settings.CLOUD_TASKS = [
            t.strip().lower() for t in payload.cloud_tasks if t.strip().lower() in valid_tasks
        ]
    if payload.cloud_provider is not None:
        app_settings.CLOUD_LLM_PROVIDER = payload.cloud_provider
    if payload.cloud_default_model is not None:
        cleaned_model = payload.cloud_default_model.strip()
        app_settings.CLOUD_DEFAULT_MODEL = cleaned_model or None
        if cleaned_model:
            prov = app_settings.CLOUD_LLM_PROVIDER.strip().lower()
            if prov == "gemini":
                app_settings.GEMINI_DEFAULT_MODEL = cleaned_model
            elif prov == "openai":
                app_settings.OPENAI_DEFAULT_MODEL = cleaned_model
            elif prov == "anthropic":
                app_settings.ANTHROPIC_DEFAULT_MODEL = cleaned_model
    if payload.cloud_base_url is not None:
        app_settings.CLOUD_BASE_URL = payload.cloud_base_url.strip() or None
    if payload.cloud_api_key is not None and payload.cloud_api_key.strip():
        cleaned_key = payload.cloud_api_key.strip()
        app_settings.CLOUD_API_KEY = cleaned_key
        prov = app_settings.CLOUD_LLM_PROVIDER.strip().lower()
        if prov == "gemini":
            app_settings.GEMINI_API_KEY = cleaned_key
        elif prov == "openai":
            app_settings.OPENAI_API_KEY = cleaned_key
        elif prov == "anthropic":
            app_settings.ANTHROPIC_API_KEY = cleaned_key
    if payload.ollama_default_model is not None:
        app_settings.OLLAMA_DEFAULT_MODEL = payload.ollama_default_model.strip()
    if payload.ollama_writing_model is not None:
        app_settings.OLLAMA_WRITING_MODEL = payload.ollama_writing_model.strip() or None
    if payload.ollama_fast_model is not None:
        app_settings.OLLAMA_FAST_MODEL = payload.ollama_fast_model.strip() or None
    if payload.gemini_default_model is not None:
        app_settings.GEMINI_DEFAULT_MODEL = payload.gemini_default_model.strip()
    if payload.gemini_api_key is not None and payload.gemini_api_key.strip():
        app_settings.GEMINI_API_KEY = payload.gemini_api_key.strip()
    if payload.max_budget_usd is not None:
        app_settings.MAX_BUDGET_USD = payload.max_budget_usd
    if payload.llm_timeout_seconds is not None:
        app_settings.LLM_TIMEOUT_SECONDS = payload.llm_timeout_seconds

    save_runtime_llm_config(app_settings)

    fresh_router = ModelRouter(
        app_settings=app_settings,
        usage_repo=usage_repo,
        project_repo=project_repo,
    )
    return await _build_llm_status(app_settings, fresh_router, usage_repo)


@router.get("/api/projects/{project_id}/usage", response_model=ProjectUsageSummaryResponse)
async def get_project_usage(
    project_id: str,
    project_repo: Annotated[ProjectRepository, Depends(get_project_repository)],
    usage_repo: Annotated[UsageRepository, Depends(get_usage_repository)],
) -> ProjectUsageSummaryResponse:
    project = await project_repo.get_by_id(project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_id}' not found.",
        )

    logs = await usage_repo.list_for_project(project_id)
    items = [UsageLogResponse.model_validate(entry) for entry in logs]
    return ProjectUsageSummaryResponse(
        project_id=project_id,
        total_calls=len(items),
        total_prompt_tokens=sum(item.prompt_tokens for item in items),
        total_completion_tokens=sum(item.completion_tokens for item in items),
        total_estimated_cost_usd=round(sum(item.estimated_cost_usd for item in items), 8),
        items=items,
    )
