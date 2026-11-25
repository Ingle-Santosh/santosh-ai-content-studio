from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from content_studio.config.settings import Settings
from content_studio.database.repositories import (
    ModelRegistryRepository,
    ProjectRepository,
    UsageRepository,
)
from content_studio.providers.llm import ModelRouter, TaskType
from content_studio.services import ModelRegistryService


async def test_model_registry_api_crud_and_secret_isolation(
    api_client: AsyncClient,
    test_settings: Settings,
) -> None:
    # 1. Register a free OpenRouter model with an API token
    create_resp = await api_client.post(
        "/api/models/registry",
        json={
            "name": "OpenRouter Llama 3.3 70B Free",
            "provider": "openrouter",
            "model_id": "meta-llama/llama-3.3-70b-instruct:free",
            "base_url": "https://openrouter.ai/api/v1",
            "api_key": "sk-or-v1-super-secret-token-9999",
            "tier": "cloud_free",
            "input_cost_per_1m": 0.0,
            "output_cost_per_1m": 0.0,
        },
    )
    assert create_resp.status_code == 201
    created = create_resp.json()
    assert created["provider"] == "openrouter"
    assert created["has_api_key"] is True
    assert created["api_key_hint"] == "sk-or...9999"
    assert "super-secret" not in create_resp.text

    # 2. List registry includes presets & masked entry
    list_resp = await api_client.get("/api/models/registry")
    assert list_resp.status_code == 200
    payload = list_resp.json()
    assert payload["total"] == 1
    assert len(payload["presets"]) >= 5
    assert "super-secret" not in list_resp.text

    # 3. Duplicate display name rejected with 409
    dup_resp = await api_client.post(
        "/api/models/registry",
        json={
            "name": "OpenRouter Llama 3.3 70B Free",
            "provider": "openrouter",
            "model_id": "meta-llama/llama-3.3-70b-instruct:free",
        },
    )
    assert dup_resp.status_code == 409

    # 4. Delete removes both DB row and local key-vault entry
    del_resp = await api_client.delete(f"/api/models/registry/{created['id']}")
    assert del_resp.status_code == 204
    key_vault = test_settings.resolved_data_dir / ".model_registry_keys.json"
    assert created["id"] not in key_vault.read_text(encoding="utf-8")


async def test_router_selects_registered_local_small_and_free_openrouter_models(
    test_settings: Settings,
    db_session: AsyncSession,
) -> None:
    registry_service = ModelRegistryService(
        app_settings=test_settings,
        registry_repo=ModelRegistryRepository(db_session),
    )
    project_repo = ProjectRepository(db_session)
    usage_repo = UsageRepository(db_session)

    local_small = await registry_service.register_model(
        name="Local Qwen 2.5 3B",
        provider="ollama",
        model_id="qwen2.5:3b",
        tier="local_small",
    )
    openrouter_free = await registry_service.register_model(
        name="OpenRouter DeepSeek Free",
        provider="openrouter",
        model_id="deepseek/deepseek-chat-v3-0324:free",
        api_key="sk-or-test-key",
        tier="cloud_free",
        input_cost_per_1m=0.0,
        output_cost_per_1m=0.0,
    )

    # Configure Hybrid Tiered mode with $0.00 budget (free OpenRouter model still allowed!)
    test_settings.LOCAL_ONLY = False
    test_settings.PREFER_CLOUD_DEFAULT = False
    test_settings.MAX_BUDGET_USD = 0.0
    test_settings.SMALL_MODEL_ID = local_small.id
    test_settings.POWERFUL_MODEL_ID = openrouter_free.id
    test_settings.CLOUD_TASKS = ["scriptwriting", "fact_check"]

    project = await project_repo.create(
        title="Hybrid Registry Video",
        topic="Apache Superset RBAC",
        budget_usd=0.0,
    )
    router = ModelRouter(
        app_settings=test_settings,
        usage_repo=usage_repo,
        project_repo=project_repo,
        registry_service=registry_service,
    )

    # Easy task -> registered small local Ollama model
    easy_route = await router.resolve_route(TaskType.QA_REVIEW, project_id=project.id)
    assert easy_route.provider == "ollama"
    assert easy_route.model == "qwen2.5:3b"
    assert easy_route.is_cloud is False

    # Important task -> registered free OpenRouter model (even at $0.00 budget)
    imp_route = await router.resolve_route(TaskType.SCRIPTWRITING, project_id=project.id)
    assert imp_route.provider == "openrouter"
    assert imp_route.model == "deepseek/deepseek-chat-v3-0324:free"
    assert imp_route.is_cloud is True

    # Per-project registered_model_id override takes highest precedence
    await project_repo.update(
        project,
        config={"registered_model_id": openrouter_free.id},
    )
    override_route = await router.resolve_route(TaskType.QA_REVIEW, project_id=project.id)
    assert override_route.provider == "openrouter"
    assert override_route.model == "deepseek/deepseek-chat-v3-0324:free"
