import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import (
    get_artifact_store,
    get_model_router,
    get_search_provider,
    get_settings,
    get_web_extractor,
    get_youtube_provider,
)
from app.main import create_app
from content_studio.config.settings import Settings
from content_studio.database.repositories import ProjectRepository, UsageRepository
from content_studio.database.session import get_db_session
from content_studio.providers.llm import ModelRouter
from content_studio.services import WebExtractor
from content_studio.storage.artifact_store import ArtifactStore
from tests.test_langgraph_workflow import (
    _WorkflowMockLLM,
    _WorkflowStubSearch,
    _WorkflowStubYouTube,
)


@pytest.mark.asyncio
async def test_workflows_api_start_status_resume_and_list(
    test_settings: Settings,
    db_session: AsyncSession,
    artifact_store: ArtifactStore,
) -> None:
    html_page = (
        "<html><head><title>LangGraph Checkpoints</title></head><body><article>"
        "<p>LangGraph persists state checkpoints per thread_id in SQLite.</p>"
        "</article></body></html>"
    )
    router = ModelRouter(
        app_settings=test_settings,
        local_provider=_WorkflowMockLLM(),
        usage_repo=UsageRepository(db_session),
        project_repo=ProjectRepository(db_session),
    )

    app = create_app()

    async def _override_db():
        yield db_session

    app.dependency_overrides[get_settings] = lambda: test_settings
    app.dependency_overrides[get_db_session] = _override_db
    app.dependency_overrides[get_artifact_store] = lambda: artifact_store
    app.dependency_overrides[get_model_router] = lambda: router
    app.dependency_overrides[get_search_provider] = lambda: _WorkflowStubSearch()
    app.dependency_overrides[get_youtube_provider] = lambda: _WorkflowStubYouTube()
    app.dependency_overrides[get_web_extractor] = lambda: WebExtractor(
        transport=httpx.MockTransport(
            lambda _req: httpx.Response(200, headers={"content-type": "text/html"}, text=html_page)
        )
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        project = (
            await client.post(
                "/api/projects",
                json={"topic": "LangGraph Orchestration in Python"},
            )
        ).json()

        # Start workflow -> pauses at Gate 1 (brief)
        start_resp = await client.post(
            f"/api/projects/{project['id']}/workflows/start",
            json={"auto_approve": False},
        )
        assert start_resp.status_code == 201
        snap1 = start_resp.json()
        run_id = snap1["run_id"]
        assert snap1["status"] == "INTERRUPTED"
        assert snap1["pending_interrupt"]["gate"] == "brief"

        # Status endpoint returns checkpoint state
        status_resp = await client.get(f"/api/workflows/{run_id}")
        assert status_resp.status_code == 200
        assert status_resp.json()["pending_interrupt"]["gate"] == "brief"

        # Resume Gate 1 -> Gate 2 (research)
        res1 = await client.post(
            f"/api/workflows/{run_id}/resume",
            json={"decision": "APPROVED", "reviewer": "Santosh"},
        )
        assert res1.status_code == 200
        assert res1.json()["pending_interrupt"]["gate"] == "research"

        # Cancel mid-flight
        cancel_resp = await client.post(f"/api/workflows/{run_id}/cancel")
        assert cancel_resp.status_code == 200
        assert cancel_resp.json()["status"] == "CANCELLED"

        # Resuming a cancelled run returns 409 Conflict
        bad_resume = await client.post(
            f"/api/workflows/{run_id}/resume",
            json={"decision": "APPROVED"},
        )
        assert bad_resume.status_code == 409

        # List project workflow history
        hist_resp = await client.get(f"/api/projects/{project['id']}/workflows")
        assert hist_resp.status_code == 200
        assert hist_resp.json()["total"] == 1
