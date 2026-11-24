from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.schemas.llm import (
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
from content_studio.config.settings import Settings
from content_studio.database.repositories import ProjectRepository, UsageRepository
from content_studio.providers.llm import ModelRouter

router = APIRouter(tags=["llm"])


@router.get("/api/llm/status", response_model=LLMStatusResponse)
async def get_llm_status(
    app_settings: Annotated[Settings, Depends(get_settings)],
    router_svc: Annotated[ModelRouter, Depends(get_model_router)],
    usage_repo: Annotated[UsageRepository, Depends(get_usage_repository)],
) -> LLMStatusResponse:
    providers = await router_svc.check_providers_health()
    global_spend = await usage_repo.total_spend_all()
    return LLMStatusResponse(
        local_only=app_settings.LOCAL_ONLY,
        max_budget_usd=app_settings.MAX_BUDGET_USD,
        current_global_spend_usd=global_spend,
        providers=providers,
        routing_table=router_svc.describe_routing_table(),
    )


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
