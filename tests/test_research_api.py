import json

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
)
from app.main import create_app
from content_studio.config.settings import Settings
from content_studio.database.repositories import ProjectRepository, UsageRepository
from content_studio.database.session import get_db_session
from content_studio.providers.llm import (
    BaseLLMProvider,
    LLMRequest,
    LLMResponse,
    ModelRouter,
    ProviderHealth,
)
from content_studio.providers.search import BaseSearchProvider, SearchResult
from content_studio.services import WebExtractor
from content_studio.storage.artifact_store import ArtifactStore


class _MockSearch(BaseSearchProvider):
    provider_name = "mock"

    async def search(self, _query: str, *, max_results: int = 5) -> list[SearchResult]:
        return [
            SearchResult(
                title="MLOps Guide",
                url="https://mlops.example.com/guide",
                snippet="MLOps automates ML lifecycles.",
                provider="mock",
            )
        ][:max_results]


class _MockLLM(BaseLLMProvider):
    provider_name = "ollama"
    is_cloud = False

    async def generate(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(
            provider="ollama",
            model=request.model,
            content=json.dumps(
                {
                    "executive_summary": "MLOps brings CI/CD rigor to machine learning systems.",
                    "key_definitions": ["MLOps: Machine Learning Operations"],
                    "findings": [
                        {
                            "category": "definition",
                            "title": "MLOps Definition",
                            "summary": "MLOps automates training, deployment, and monitoring.",
                            "source_urls": ["https://mlops.example.com/guide"],
                            "confidence": 0.9,
                            "is_contradiction": False,
                        }
                    ],
                }
            ),
        )

    async def health_check(self) -> ProviderHealth:
        return ProviderHealth(provider="ollama", is_cloud=False, available=True)


@pytest.mark.asyncio
async def test_research_api_endpoints(
    test_settings: Settings,
    db_session: AsyncSession,
    artifact_store: ArtifactStore,
) -> None:
    html_page = (
        "<html><head><title>MLOps Guide</title></head><body><article>"
        "<p>MLOps automates training, deployment, and model monitoring in production.</p>"
        "</article></body></html>"
    )
    extractor = WebExtractor(
        transport=httpx.MockTransport(
            lambda _req: httpx.Response(200, headers={"content-type": "text/html"}, text=html_page)
        )
    )
    router = ModelRouter(
        app_settings=test_settings,
        local_provider=_MockLLM(),
        usage_repo=UsageRepository(db_session),
        project_repo=ProjectRepository(db_session),
    )

    app = create_app()

    async def _override_db():
        yield db_session

    app.dependency_overrides[get_settings] = lambda: test_settings
    app.dependency_overrides[get_db_session] = _override_db
    app.dependency_overrides[get_artifact_store] = lambda: artifact_store
    app.dependency_overrides[get_search_provider] = lambda: _MockSearch()
    app.dependency_overrides[get_web_extractor] = lambda: extractor
    app.dependency_overrides[get_model_router] = lambda: router

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        project = (
            await client.post("/api/projects", json={"topic": "MLOps Lifecycle Explained"})
        ).json()

        run_resp = await client.post(
            f"/api/projects/{project['id']}/research/run",
            json={"queries": ["MLOps guide"], "max_results_per_query": 3},
        )
        assert run_resp.status_code == 200
        report = run_resp.json()
        assert report["sources_extracted"] == 1
        assert len(report["synthesis"]["findings"]) == 1

        sources_resp = await client.get(f"/api/projects/{project['id']}/research/sources")
        assert sources_resp.status_code == 200
        assert sources_resp.json()["total"] == 1

        findings_resp = await client.get(f"/api/projects/{project['id']}/research/findings")
        assert findings_resp.status_code == 200
        assert findings_resp.json()["total"] == 1
        assert findings_resp.json()["items"][0]["source_urls_json"] == [
            "https://mlops.example.com/guide"
        ]

        missing = await client.get("/api/projects/unknown-id/research/sources")
        assert missing.status_code == 404
