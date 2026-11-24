import json

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import (
    get_artifact_store,
    get_model_router,
    get_settings,
    get_youtube_provider,
)
from app.main import create_app
from content_studio.config.settings import Settings
from content_studio.database.models.enums import SourceStatus
from content_studio.database.repositories import (
    ProjectRepository,
    ResearchRepository,
    UsageRepository,
)
from content_studio.database.session import get_db_session
from content_studio.providers.llm import (
    BaseLLMProvider,
    LLMRequest,
    LLMResponse,
    ModelRouter,
    ProviderHealth,
)
from content_studio.providers.youtube import BaseYouTubeProvider, YouTubeVideoMetadata
from content_studio.services.web_extractor import compute_url_hash
from content_studio.storage.artifact_store import ArtifactStore


class _MockM5LLM(BaseLLMProvider):
    provider_name = "ollama"
    is_cloud = False

    async def generate(self, request: LLMRequest) -> LLMResponse:
        text = request.messages[-1].content
        if "Public Competitor Videos" in text:
            payload = {
                "summary": "Competitors skip SQL performance tuning demos.",
                "common_topics": ["SQL basics"],
                "content_gaps": ["Execution plan analysis"],
                "differentiation_opportunities": ["Show EXPLAIN ANALYZE step by step"],
                "recommended_positioning": "Practical SQL tuning for data engineers.",
                "video_topics": [
                    {"youtube_video_id": "sqlVid12345", "topics_covered": ["SQL basics"]}
                ],
            }
        else:
            payload = {
                "overall_assessment": "Claim grounded in official PostgreSQL docs.",
                "claims": [
                    {
                        "statement": "Window functions preserve individual input rows.",
                        "verdict": "VERIFIED",
                        "confidence": 0.94,
                        "risk_level": "low",
                        "rationale": "Confirmed by docs.",
                        "evidence": [
                            {
                                "source_url": "https://www.postgresql.org/docs/window",
                                "stance": "SUPPORTS",
                            }
                        ],
                    }
                ],
                "high_risk_warnings": [],
            }
        return LLMResponse(provider="ollama", model=request.model, content=json.dumps(payload))

    async def health_check(self) -> ProviderHealth:
        return ProviderHealth(provider="ollama", is_cloud=False, available=True)


class _MockYouTube(BaseYouTubeProvider):
    provider_name = "mock_yt"

    async def search_videos(
        self, _query: str, *, max_results: int = 5
    ) -> list[YouTubeVideoMetadata]:
        return [
            YouTubeVideoMetadata(
                youtube_video_id="sqlVid12345",
                url="https://www.youtube.com/watch?v=sqlVid12345",
                title="SQL Window Functions in 10 Minutes",
                channel_name="SQL Mastery",
                provider="mock_yt",
            )
        ][:max_results]

    async def fetch_video_by_url(self, _url: str) -> YouTubeVideoMetadata | None:
        return None


@pytest.mark.asyncio
async def test_fact_check_and_competitor_api_routes(
    test_settings: Settings,
    db_session: AsyncSession,
    artifact_store: ArtifactStore,
) -> None:
    router = ModelRouter(
        app_settings=test_settings,
        local_provider=_MockM5LLM(),
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
    app.dependency_overrides[get_youtube_provider] = lambda: _MockYouTube()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        project = (
            await client.post("/api/projects", json={"topic": "SQL Window Functions Deep Dive"})
        ).json()

        # Seed an extracted source for fact-check grounding
        research_repo = ResearchRepository(db_session)
        src_url = "https://www.postgresql.org/docs/window"
        src = await research_repo.create_source(
            project_id=project["id"],
            url=src_url,
            normalized_url=src_url,
            url_hash=compute_url_hash(src_url),
            title="PostgreSQL Window Functions",
            domain="postgresql.org",
            provider="manual",
            status=SourceStatus.EXTRACTED,
        )
        await research_repo.create_document(
            project_id=project["id"],
            source_id=src.id,
            word_count=20,
            excerpt="A window function performs a calculation across rows without collapsing them.",
        )

        # Run Competitor Analysis
        comp_resp = await client.post(
            f"/api/projects/{project['id']}/competitors/run",
            json={"queries": ["SQL window functions"], "max_results": 3},
        )
        assert comp_resp.status_code == 200
        assert comp_resp.json()["videos_analyzed"] == 1

        list_comp = await client.get(f"/api/projects/{project['id']}/competitors")
        assert list_comp.status_code == 200
        assert list_comp.json()["total"] == 1

        # Run Fact Check (with Gate 2 research approval creation)
        fc_resp = await client.post(
            f"/api/projects/{project['id']}/fact-check/run",
            json={"request_research_approval": True},
        )
        assert fc_resp.status_code == 200
        fc_data = fc_resp.json()
        assert fc_data["verified_count"] == 1
        assert fc_data["approval_id"] is not None

        claims_resp = await client.get(
            f"/api/projects/{project['id']}/fact-check/claims",
            params={"verdict": "VERIFIED"},
        )
        assert claims_resp.status_code == 200
        assert claims_resp.json()["total"] == 1

        # Approve Gate 2 research approval
        approve_resp = await client.patch(
            f"/api/approvals/{fc_data['approval_id']}",
            json={"status": "APPROVED", "reviewer": "Santosh", "comments": "Ready for scripting"},
        )
        assert approve_resp.status_code == 200
        assert approve_resp.json()["status"] == "APPROVED"
