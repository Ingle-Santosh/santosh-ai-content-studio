import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_artifact_store, get_model_router, get_settings
from app.main import create_app
from content_studio.config.settings import Settings
from content_studio.database.repositories import ProjectRepository, UsageRepository
from content_studio.database.session import get_db_session
from content_studio.providers.llm import ModelRouter, OllamaProvider
from content_studio.storage.artifact_store import ArtifactStore


@pytest.mark.asyncio
async def test_llm_status_and_project_usage_endpoints(
    test_settings: Settings,
    db_session: AsyncSession,
    artifact_store: ArtifactStore,
) -> None:
    def ollama_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "qwen2.5-coder:14b"}]})
        return httpx.Response(404)

    mock_router = ModelRouter(
        app_settings=test_settings,
        local_provider=OllamaProvider(
            base_url=test_settings.OLLAMA_BASE_URL,
            transport=httpx.MockTransport(ollama_handler),
        ),
        usage_repo=UsageRepository(db_session),
        project_repo=ProjectRepository(db_session),
    )

    app = create_app()

    async def _override_db():
        yield db_session

    app.dependency_overrides[get_settings] = lambda: test_settings
    app.dependency_overrides[get_db_session] = _override_db
    app.dependency_overrides[get_artifact_store] = lambda: artifact_store
    app.dependency_overrides[get_model_router] = lambda: mock_router

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        status_resp = await client.get("/api/llm/status")
        assert status_resp.status_code == 200
        status_data = status_resp.json()
        assert status_data["local_only"] is True
        assert status_data["max_budget_usd"] == 0.0
        assert status_data["providers"][0]["provider"] == "ollama"
        assert status_data["providers"][0]["available"] is True
        assert "scriptwriting" in status_data["routing_table"]

        # Unknown project usage returns 404
        missing_resp = await client.get("/api/projects/does-not-exist/usage")
        assert missing_resp.status_code == 404

        # Create project & log usage -> verify summary endpoint
        project = (
            await client.post("/api/projects", json={"topic": "LLM Routing Architecture"})
        ).json()
        usage_repo = UsageRepository(db_session)
        await usage_repo.create(
            project_id=project["id"],
            provider="ollama",
            model="qwen2.5-coder:14b",
            node_name="research_node",
            prompt_tokens=400,
            completion_tokens=200,
            estimated_cost_usd=0.0,
            latency_ms=550,
        )
        usage_resp = await client.get(f"/api/projects/{project['id']}/usage")
        assert usage_resp.status_code == 200
        summary = usage_resp.json()
        assert summary["total_calls"] == 1
        assert summary["total_prompt_tokens"] == 400
        assert summary["total_completion_tokens"] == 200
        assert summary["total_estimated_cost_usd"] == 0.0

        # PATCH /api/llm/config updates active models/provider without leaking API keys
        patch_resp = await client.patch(
            "/api/llm/config",
            json={
                "local_only": False,
                "prefer_cloud_default": True,
                "ollama_default_model": "qwen3.5:9b",
                "gemini_default_model": "gemini-2.5-pro",
                "gemini_api_key": "test-secret-key",
                "max_budget_usd": 5.0,
                "llm_timeout_seconds": 240.0,
            },
        )
        assert patch_resp.status_code == 200
        patched = patch_resp.json()
        assert patched["local_only"] is False
        assert patched["prefer_cloud_default"] is True
        assert patched["ollama_default_model"] == "qwen3.5:9b"
        assert patched["gemini_default_model"] == "gemini-2.5-pro"
        assert patched["gemini_api_key_configured"] is True
        assert patched["max_budget_usd"] == 5.0
        assert patched["llm_timeout_seconds"] == 240.0
        assert "test-secret-key" not in patch_resp.text

        # Non-secret config persisted to data/llm_runtime_config.json without any API key
        cfg_file = test_settings.resolved_data_dir / "llm_runtime_config.json"
        assert cfg_file.is_file()
        cfg_text = cfg_file.read_text(encoding="utf-8")
        assert "qwen3.5:9b" in cfg_text
        assert "test-secret-key" not in cfg_text
