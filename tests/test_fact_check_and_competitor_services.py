import json

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from content_studio.config.settings import Settings
from content_studio.database.models.enums import (
    ApprovalGate,
    ApprovalStatus,
    ClaimVerdict,
    SourceStatus,
)
from content_studio.database.repositories import (
    AgentRunRepository,
    ApprovalRepository,
    ArtifactRepository,
    CompetitorRepository,
    FactCheckRepository,
    ProjectRepository,
    ResearchRepository,
    UsageRepository,
)
from content_studio.providers.llm import (
    BaseLLMProvider,
    LLMRequest,
    LLMResponse,
    ModelRouter,
    ProviderHealth,
)
from content_studio.providers.youtube import BaseYouTubeProvider, YouTubeVideoMetadata
from content_studio.services import (
    ApprovalService,
    ArtifactService,
    CompetitorService,
    FactCheckService,
)
from content_studio.services.web_extractor import compute_url_hash
from content_studio.storage.artifact_store import ArtifactStore


class _SequenceLLM(BaseLLMProvider):
    provider_name = "ollama"
    is_cloud = False

    def __init__(self, payloads: list[dict]) -> None:
        self._payloads = list(payloads)

    async def generate(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(
            provider="ollama",
            model=request.model,
            content=json.dumps(self._payloads.pop(0)),
        )

    async def health_check(self) -> ProviderHealth:
        return ProviderHealth(provider="ollama", is_cloud=False, available=True)


class _StubYouTubeProvider(BaseYouTubeProvider):
    provider_name = "stub_youtube"

    async def search_videos(
        self, _query: str, *, max_results: int = 5
    ) -> list[YouTubeVideoMetadata]:
        return [
            YouTubeVideoMetadata(
                youtube_video_id="vid11111111",
                url="https://www.youtube.com/watch?v=vid11111111",
                title="RAG Tutorial for Beginners",
                channel_name="AI Lab",
                view_count=15000,
                duration_seconds=900,
                description="Covers basic vector search without production evals.",
                provider="stub_youtube",
            ),
            # Duplicate video ID in batch -> deduplicated
            YouTubeVideoMetadata(
                youtube_video_id="vid11111111",
                url="https://www.youtube.com/watch?v=vid11111111",
                title="Duplicate Video",
                channel_name="AI Lab",
                provider="stub_youtube",
            ),
        ][:max_results]

    async def fetch_video_by_url(self, _url: str) -> YouTubeVideoMetadata | None:
        return None


@pytest.mark.asyncio
async def test_fact_check_service_enforces_evidence_guardrail_and_creates_approval(
    test_settings: Settings,
    db_session: AsyncSession,
    artifact_store: ArtifactStore,
) -> None:
    project_repo = ProjectRepository(db_session)
    artifact_repo = ArtifactRepository(db_session)
    research_repo = ResearchRepository(db_session)
    fact_check_repo = FactCheckRepository(db_session)
    approval_repo = ApprovalRepository(db_session)
    usage_repo = UsageRepository(db_session)
    agent_run_repo = AgentRunRepository(db_session)

    artifact_service = ArtifactService(
        project_repo=project_repo,
        artifact_repo=artifact_repo,
        store=artifact_store,
    )
    approval_service = ApprovalService(
        project_repo=project_repo,
        approval_repo=approval_repo,
        artifact_repo=artifact_repo,
    )

    project = await project_repo.create(title="Fact Check Demo", topic="RAG Evaluation Metrics")
    await artifact_store.ainit_project_dirs(project.id)

    url_a = "https://docs.example.com/rag-metrics"
    url_b = "https://blog.example.com/rag-benchmarks"
    src_a = await research_repo.create_source(
        project_id=project.id,
        url=url_a,
        normalized_url=url_a,
        url_hash=compute_url_hash(url_a),
        title="RAG Metrics Docs",
        domain="docs.example.com",
        provider="duckduckgo",
        status=SourceStatus.EXTRACTED,
    )
    src_b = await research_repo.create_source(
        project_id=project.id,
        url=url_b,
        normalized_url=url_b,
        url_hash=compute_url_hash(url_b),
        title="RAG Benchmarks Blog",
        domain="blog.example.com",
        provider="duckduckgo",
        status=SourceStatus.EXTRACTED,
    )
    await research_repo.create_document(
        project_id=project.id,
        source_id=src_a.id,
        word_count=40,
        excerpt=(
            "Faithfulness measures whether generated answers stay grounded in retrieved context."
        ),
    )
    await research_repo.create_document(
        project_id=project.id,
        source_id=src_b.id,
        word_count=35,
        excerpt="Some benchmarks report latency overhead under 50ms while others report 200ms.",
    )

    llm_output = {
        "overall_assessment": "One claim is verified, one lacks valid sources, one conflicts.",
        "claims": [
            {
                "statement": "Faithfulness measures answer grounding in retrieved context.",
                "verdict": "VERIFIED",
                "confidence": 0.95,
                "risk_level": "low",
                "rationale": "Explicitly stated in RAG Metrics Docs.",
                "evidence": [
                    {
                        "source_url": url_a,
                        "stance": "SUPPORTS",
                        "excerpt": "Faithfulness measures whether generated answers stay grounded.",
                    }
                ],
            },
            {
                # LLM falsely marks VERIFIED with a fabricated URL -> must downgrade to UNSUPPORTED!
                "statement": "RAG reduces cloud GPU spend by exactly 93 percent.",
                "verdict": "VERIFIED",
                "confidence": 0.85,
                "risk_level": "low",
                "rationale": "Claimed by external benchmark.",
                "evidence": [
                    {
                        "source_url": "https://hallucinated.example.com/fake-study",
                        "stance": "SUPPORTS",
                    }
                ],
            },
            {
                "statement": "Vector retrieval always adds under 50ms latency.",
                "verdict": "CONFLICTING",
                "confidence": 0.7,
                "risk_level": "high",
                "rationale": "Sources report conflicting latency numbers.",
                "evidence": [
                    {"source_url": url_a, "stance": "SUPPORTS"},
                    {"source_url": url_b, "stance": "CONTRADICTS"},
                ],
            },
        ],
        "high_risk_warnings": ["Verify benchmark latency claims before scripting."],
    }

    router = ModelRouter(
        app_settings=test_settings,
        local_provider=_SequenceLLM([llm_output]),
        usage_repo=usage_repo,
        project_repo=project_repo,
    )
    service = FactCheckService(
        app_settings=test_settings,
        project_repo=project_repo,
        research_repo=research_repo,
        fact_check_repo=fact_check_repo,
        artifact_service=artifact_service,
        model_router=router,
        approval_service=approval_service,
        agent_run_repo=agent_run_repo,
    )

    report = await service.run_fact_check(project.id, request_research_approval=True)
    assert report.total_claims == 3
    assert report.verified_count == 1
    assert report.unsupported_count == 1
    assert report.conflicting_count == 1
    assert report.downgraded_claims_count == 1
    assert report.approval_id is not None
    assert report.report_markdown_artifact_id is not None

    # Confirm downgraded claim is persisted as UNSUPPORTED with high risk
    unsupported_rows = await fact_check_repo.list_claims(
        project.id, verdict=ClaimVerdict.UNSUPPORTED
    )
    assert len(unsupported_rows) == 1
    assert unsupported_rows[0].risk_level == "high"
    assert unsupported_rows[0].claim_sources == []

    # Confirm pending Gate 2 research approval was created
    approvals = await approval_repo.list_approvals(
        project_id=project.id, gate=ApprovalGate.RESEARCH
    )
    assert len(approvals) == 1
    assert approvals[0].status == ApprovalStatus.PENDING.value


@pytest.mark.asyncio
async def test_competitor_service_deduplicates_and_generates_gap_report(
    test_settings: Settings,
    db_session: AsyncSession,
    artifact_store: ArtifactStore,
) -> None:
    project_repo = ProjectRepository(db_session)
    artifact_repo = ArtifactRepository(db_session)
    competitor_repo = CompetitorRepository(db_session)
    usage_repo = UsageRepository(db_session)
    agent_run_repo = AgentRunRepository(db_session)

    artifact_service = ArtifactService(
        project_repo=project_repo,
        artifact_repo=artifact_repo,
        store=artifact_store,
    )
    project = await project_repo.create(title="RAG Evals", topic="RAG Evaluation in Production")
    await artifact_store.ainit_project_dirs(project.id)

    gap_payload = {
        "summary": "Competitors cover setup basics but skip production evaluation metrics.",
        "common_topics": ["Vector DB basics", "Chunking"],
        "content_gaps": ["Live Python evaluation harness", "Latency vs recall trade-offs"],
        "differentiation_opportunities": [
            "Show step-by-step Hinglish walkthrough with runnable local eval code"
        ],
        "recommended_positioning": (
            "Position as the practical production-grade RAG evaluation tutorial."
        ),
        "video_topics": [
            {"youtube_video_id": "vid11111111", "topics_covered": ["Vector DB basics"]}
        ],
    }

    router = ModelRouter(
        app_settings=test_settings,
        local_provider=_SequenceLLM([gap_payload]),
        usage_repo=usage_repo,
        project_repo=project_repo,
    )
    service = CompetitorService(
        app_settings=test_settings,
        project_repo=project_repo,
        competitor_repo=competitor_repo,
        artifact_service=artifact_service,
        youtube_provider=_StubYouTubeProvider(),
        model_router=router,
        agent_run_repo=agent_run_repo,
    )

    report = await service.run_analysis(project.id, queries=["RAG evals"], max_results=5)
    assert report.videos_analyzed == 1
    assert report.duplicates_skipped == 1
    assert report.gap_analysis is not None
    assert "Live Python evaluation harness" in report.gap_analysis.content_gaps
    assert report.report_markdown_artifact_id is not None

    stored = await competitor_repo.list_for_project(project.id)
    assert len(stored) == 1
    assert stored[0].topics_covered_json == ["Vector DB basics"]
