import json

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from content_studio.config.settings import Settings
from content_studio.database.models.enums import AgentRunStatus, SourceStatus
from content_studio.database.repositories import (
    AgentRunRepository,
    ArtifactRepository,
    ProjectRepository,
    ResearchRepository,
    UsageRepository,
)
from content_studio.providers.llm import (
    BaseLLMProvider,
    LLMRequest,
    LLMResponse,
    LLMUsage,
    ModelRouter,
    ProviderHealth,
)
from content_studio.providers.search import BaseSearchProvider, SearchResult
from content_studio.services import ArtifactService, ResearchService, WebExtractor
from content_studio.storage.artifact_store import ArtifactStore


class _StubSearchProvider(BaseSearchProvider):
    provider_name = "stub_search"

    def __init__(self, results: list[SearchResult]) -> None:
        self._results = results

    async def search(self, _query: str, *, max_results: int = 5) -> list[SearchResult]:
        return self._results[:max_results]


class _StubLLMProvider(BaseLLMProvider):
    provider_name = "ollama"
    is_cloud = False

    def __init__(self, payload: dict) -> None:
        self._payload = payload

    async def generate(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(
            provider="ollama",
            model=request.model,
            content=json.dumps(self._payload),
            usage=LLMUsage(prompt_tokens=300, completion_tokens=150, latency_ms=120),
        )

    async def health_check(self) -> ProviderHealth:
        return ProviderHealth(provider="ollama", is_cloud=False, available=True)


@pytest.mark.asyncio
async def test_research_service_dedup_errors_and_source_traceability(
    test_settings: Settings,
    db_session: AsyncSession,
    artifact_store: ArtifactStore,
) -> None:
    project_repo = ProjectRepository(db_session)
    artifact_repo = ArtifactRepository(db_session)
    research_repo = ResearchRepository(db_session)
    usage_repo = UsageRepository(db_session)
    agent_run_repo = AgentRunRepository(db_session)
    artifact_service = ArtifactService(
        project_repo=project_repo,
        artifact_repo=artifact_repo,
        store=artifact_store,
    )

    project = await project_repo.create(
        title="RAG vs CAG",
        topic="RAG vs CAG Architecture",
        config={"language": "Hinglish", "audience_level": "Intermediate (Data/AI Engineers)"},
    )
    await artifact_store.ainit_project_dirs(project.id)

    article_a = (
        "<html><head><title>RAG Deep Dive</title></head><body><article>"
        "<h1>RAG Deep Dive</h1>"
        "<p>RAG retrieves relevant chunks dynamically from a vector database at query time.</p>"
        "</article></body></html>"
    )

    def http_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path in {"/rag", "/rag-mirror"}:
            return httpx.Response(200, headers={"content-type": "text/html"}, text=article_a)
        if request.url.path == "/broken":
            return httpx.Response(500, text="server error")
        return httpx.Response(404)

    search_results = [
        SearchResult(
            title="RAG Deep Dive",
            url="https://docs.example.com/rag?utm_source=google",
            snippet="Vector retrieval",
            provider="stub_search",
        ),
        # Duplicate URL after normalization (different tracking param)
        SearchResult(
            title="RAG Deep Dive Tracking Dup",
            url="https://docs.example.com/rag?fbclid=xyz",
            snippet="Duplicate URL",
            provider="stub_search",
        ),
        # Mirror URL serving identical content -> caught by checksum deduplication
        SearchResult(
            title="RAG Mirror",
            url="https://docs.example.com/rag-mirror",
            snippet="Mirror content",
            provider="stub_search",
        ),
        # Broken URL -> recorded as FAILED
        SearchResult(
            title="Broken Source",
            url="https://docs.example.com/broken",
            snippet="Will 500",
            provider="stub_search",
        ),
    ]

    llm_payload = {
        "executive_summary": "RAG retrieves external context dynamically to ground responses.",
        "key_definitions": ["RAG: Retrieval-Augmented Generation"],
        "findings": [
            {
                "category": "concept",
                "title": "Dynamic Vector Retrieval",
                "summary": "RAG fetches chunks from a vector store at inference time.",
                "source_urls": [
                    "https://docs.example.com/rag",
                    "https://fabricated.example.com/hallucinated",
                ],
                "confidence": 0.92,
                "is_contradiction": False,
            },
            {
                "category": "fact",
                "title": "Hallucinated Finding",
                "summary": "This finding only cites a non-existent source URL.",
                "source_urls": ["https://nonexistent.example.com/made-up"],
                "confidence": 0.4,
                "is_contradiction": False,
            },
        ],
        "contradictions": [],
        "recommended_angles": ["Compare latency vs freshness trade-offs"],
        "open_questions": ["When is CAG cheaper than RAG?"],
    }

    router = ModelRouter(
        app_settings=test_settings,
        local_provider=_StubLLMProvider(llm_payload),
        usage_repo=usage_repo,
        project_repo=project_repo,
    )
    service = ResearchService(
        app_settings=test_settings,
        project_repo=project_repo,
        research_repo=research_repo,
        artifact_service=artifact_service,
        search_provider=_StubSearchProvider(search_results),
        extractor=WebExtractor(transport=httpx.MockTransport(http_handler)),
        model_router=router,
        agent_run_repo=agent_run_repo,
    )

    report = await service.run_research(
        project.id,
        queries=["RAG vs CAG"],
        max_results_per_query=5,
    )

    assert report.sources_discovered == 3  # 1 tracking-param URL duplicate skipped
    assert report.sources_extracted == 1
    assert report.sources_failed == 1
    assert report.duplicates_skipped == 2  # 1 URL duplicate + 1 content-checksum duplicate
    assert report.ungrounded_findings_dropped == 1
    assert report.synthesis is not None
    assert len(report.synthesis.findings) == 1
    assert report.synthesis.findings[0].source_urls == ["https://docs.example.com/rag"]
    assert report.report_json_artifact_id is not None
    assert report.report_markdown_artifact_id is not None

    # Persisted DB records match
    sources = await research_repo.list_sources(project.id)
    statuses = {s.normalized_url: s.status for s in sources}
    assert statuses["https://docs.example.com/rag"] == SourceStatus.EXTRACTED.value
    assert statuses["https://docs.example.com/rag-mirror"] == SourceStatus.DUPLICATE.value
    assert statuses["https://docs.example.com/broken"] == SourceStatus.FAILED.value

    findings = await research_repo.list_findings(project.id)
    assert len(findings) == 1
    assert findings[0].source_urls_json == ["https://docs.example.com/rag"]

    # AgentRun and LLMUsageLog recorded
    agent_runs = await agent_run_repo.list_for_project(project.id)
    assert len(agent_runs) == 1
    assert agent_runs[0].status == AgentRunStatus.COMPLETED.value
    assert len(await usage_repo.list_for_project(project.id)) == 1

    # Re-running with same search results skips all previously seen URLs
    second_report = await service.run_research(
        project.id,
        queries=["RAG vs CAG"],
        synthesize_with_llm=False,
    )
    assert second_report.sources_discovered == 0
    assert second_report.duplicates_skipped == 4
