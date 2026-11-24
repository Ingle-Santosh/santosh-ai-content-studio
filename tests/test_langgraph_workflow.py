import json

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from content_studio.config.settings import Settings
from content_studio.database.models.enums import (
    ApprovalGate,
    ApprovalStatus,
    ProjectStatus,
    RunStatus,
    ScriptSectionType,
)
from content_studio.database.repositories import (
    AgentRunRepository,
    ApprovalRepository,
    ArtifactRepository,
    ChannelGuidelineRepository,
    CompetitorRepository,
    FactCheckRepository,
    ProjectRepository,
    ResearchRepository,
    RunRepository,
    SceneRepository,
    ScriptRepository,
    UsageRepository,
)
from content_studio.providers.llm import (
    BaseLLMProvider,
    LLMRequest,
    LLMResponse,
    ModelRouter,
    ProviderHealth,
)
from content_studio.providers.search import BaseSearchProvider, SearchResult
from content_studio.providers.youtube import BaseYouTubeProvider, YouTubeVideoMetadata
from content_studio.services import (
    ApprovalService,
    ArtifactService,
    ChannelGuidelineService,
    CompetitorService,
    FactCheckService,
    ResearchService,
    ScriptwriterService,
    StoryboardService,
    TopicStrategistService,
    WebExtractor,
)
from content_studio.services.script_validator import REQUIRED_SECTIONS
from content_studio.storage.artifact_store import ArtifactStore
from content_studio.workflows import PipelineServices, WorkflowOrchestrator


class _WorkflowStubSearch(BaseSearchProvider):
    provider_name = "stub"

    def __init__(self) -> None:
        self.calls = 0

    async def search(self, _query: str, *, max_results: int = 5) -> list[SearchResult]:
        self.calls += 1
        return [
            SearchResult(
                title="LangGraph Persistence Guide",
                url="https://docs.example.com/langgraph-checkpoints",
                snippet="LangGraph persists checkpoints per thread_id in SQLite.",
                provider="stub",
            )
        ][:max_results]


class _WorkflowStubYouTube(BaseYouTubeProvider):
    provider_name = "stub_yt"

    def __init__(self) -> None:
        self.calls = 0

    async def search_videos(
        self, _query: str, *, max_results: int = 5
    ) -> list[YouTubeVideoMetadata]:
        self.calls += 1
        return [
            YouTubeVideoMetadata(
                youtube_video_id="lgVid123456",
                url="https://www.youtube.com/watch?v=lgVid123456",
                title="LangGraph Tutorial",
                channel_name="AI Builders",
                description="Overview of LangGraph nodes.",
                provider="stub_yt",
            )
        ][:max_results]

    async def fetch_video_by_url(self, _url: str) -> YouTubeVideoMetadata | None:
        return None


class _WorkflowMockLLM(BaseLLMProvider):
    provider_name = "ollama"
    is_cloud = False

    def __init__(self) -> None:
        self.call_log: list[str] = []

    async def generate(self, request: LLMRequest) -> LLMResponse:
        prompt = request.messages[-1].content
        if "ContentBrief" in prompt:
            self.call_log.append("topic_strategist")
            payload = {
                "content_angle": "Production-grade LangGraph checkpointing and HITL interrupts.",
                "target_audience": "Intermediate Python & AI Engineers",
                "problem_hook": "Why naive agent loops lose work when restarted.",
                "key_takeaways": ["SQLite checkpointing", "Human approval interrupts"],
                "proposed_outline": ["Hook", "Architecture", "Live Demo"],
                "search_queries": ["LangGraph SQLite checkpointer"],
                "competitor_queries": ["LangGraph tutorial"],
                "differentiation_hook": "Full local-first Hinglish walkthrough with runnable code.",
            }
        elif "Public Competitor Videos" in prompt:
            self.call_log.append("competitor_analyst")
            payload = {
                "summary": "Competitors skip real SQLite resume demos.",
                "common_topics": ["StateGraph basics"],
                "content_gaps": ["Process-restart resume demo"],
                "differentiation_opportunities": ["Show real SQLite checkpoint recovery"],
                "recommended_positioning": "Production HITL LangGraph engineering.",
                "video_topics": [
                    {"youtube_video_id": "lgVid123456", "topics_covered": ["StateGraph basics"]}
                ],
            }
        elif "Existing Research Findings to Audit" in prompt:
            self.call_log.append("fact_checker")
            payload = {
                "overall_assessment": "All claims grounded in extracted docs.",
                "claims": [
                    {
                        "statement": "LangGraph persists state checkpoints per thread_id.",
                        "verdict": "VERIFIED",
                        "confidence": 0.95,
                        "risk_level": "low",
                        "rationale": "Confirmed by docs.",
                        "evidence": [
                            {
                                "source_url": "https://docs.example.com/langgraph-checkpoints",
                                "stance": "SUPPORTS",
                            }
                        ],
                    }
                ],
                "high_risk_warnings": [],
            }
        elif "Synthesize a structured research report" in prompt:
            self.call_log.append("research_agent")
            payload = {
                "executive_summary": "LangGraph checkpoints enable reliable pause and resume.",
                "key_definitions": ["Checkpointer: Persists graph snapshots per thread_id."],
                "findings": [
                    {
                        "category": "concept",
                        "title": "Thread-scoped SQLite Checkpoints",
                        "summary": "AsyncSqliteSaver saves graph state after each superstep.",
                        "source_urls": ["https://docs.example.com/langgraph-checkpoints"],
                        "confidence": 0.93,
                        "is_contradiction": False,
                    }
                ],
            }
        elif "Approved Script Sections" in prompt:
            self.call_log.append("storyboard")
            payload = {
                "summary": "Concise 2-scene storyboard with diagram and code demo.",
                "scenes": [
                    {
                        "scene_number": 1,
                        "title": "Intro Hook",
                        "estimated_duration_seconds": 40,
                        "narration": "Namaste dosto, aaj LangGraph checkpointing seekhenge.",
                        "on_screen_text": "Resumable Agent Workflows",
                        "visual_type": "face_cam",
                        "asset_requirements": [],
                        "related_script_section": "hook",
                    },
                    {
                        "scene_number": 2,
                        "title": "Checkpointer Flow Diagram",
                        "estimated_duration_seconds": 80,
                        "narration": "Dekhiye SQLite checkpoints kaise state save karte hain.",
                        "on_screen_text": "AsyncSqliteSaver + interrupt()",
                        "visual_type": "diagram",
                        "asset_requirements": [
                            {
                                "asset_type": "diagram",
                                "title": "HITL Interrupt Flow",
                                "description": "Flowchart showing pause/resume via Command.",
                            }
                        ],
                        "related_script_section": "main_explanation",
                    },
                ],
            }
        else:
            self.call_log.append("scriptwriter")
            payload = {
                "title": "LangGraph Checkpointing & Human Approval Deep Dive",
                "language": "Hinglish",
                "sections": [
                    {
                        "section_type": sec.value,
                        "title": sec.value.replace("_", " ").title(),
                        "narration": (
                            "Namaste devs, aaj hum LangGraph checkpoints aur human-in-the-loop "
                            "interrupts ko practical Python demo ke saath samjhenge."
                        ),
                        "visual_instructions": "Architecture diagram + IDE walkthrough.",
                        "screen_recording_requirements": (
                            "Run pytest workflow demo"
                            if sec == ScriptSectionType.PRACTICAL_DEMONSTRATION
                            else None
                        ),
                        "code_demo_references": (
                            ["checkpoint_demo.py"]
                            if sec == ScriptSectionType.PRACTICAL_DEMONSTRATION
                            else []
                        ),
                        "estimated_duration_seconds": 100,
                        "source_urls": ["https://docs.example.com/langgraph-checkpoints"],
                    }
                    for sec in REQUIRED_SECTIONS
                ],
            }
        return LLMResponse(provider="ollama", model=request.model, content=json.dumps(payload))

    async def health_check(self) -> ProviderHealth:
        return ProviderHealth(provider="ollama", is_cloud=False, available=True)


def _build_orchestrator(
    *,
    test_settings: Settings,
    db_session: AsyncSession,
    artifact_store: ArtifactStore,
    search: _WorkflowStubSearch,
    yt: _WorkflowStubYouTube,
    llm: _WorkflowMockLLM,
) -> WorkflowOrchestrator:
    project_repo = ProjectRepository(db_session)
    run_repo = RunRepository(db_session)
    artifact_repo = ArtifactRepository(db_session)
    approval_repo = ApprovalRepository(db_session)
    guideline_repo = ChannelGuidelineRepository(db_session)
    research_repo = ResearchRepository(db_session)
    fact_check_repo = FactCheckRepository(db_session)
    competitor_repo = CompetitorRepository(db_session)
    script_repo = ScriptRepository(db_session)
    scene_repo = SceneRepository(db_session)
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
    guideline_service = ChannelGuidelineService(guideline_repo)
    router = ModelRouter(
        app_settings=test_settings,
        local_provider=llm,
        usage_repo=usage_repo,
        project_repo=project_repo,
    )
    html_page = (
        "<html><head><title>LangGraph Checkpoints</title></head><body><article>"
        "<p>LangGraph persists state checkpoints per thread_id using AsyncSqliteSaver.</p>"
        "</article></body></html>"
    )
    extractor = WebExtractor(
        transport=httpx.MockTransport(
            lambda _req: httpx.Response(200, headers={"content-type": "text/html"}, text=html_page)
        )
    )

    services = PipelineServices(
        topic_strategist=TopicStrategistService(
            app_settings=test_settings,
            project_repo=project_repo,
            guideline_service=guideline_service,
            artifact_service=artifact_service,
            model_router=router,
            approval_service=approval_service,
            agent_run_repo=agent_run_repo,
        ),
        research=ResearchService(
            app_settings=test_settings,
            project_repo=project_repo,
            research_repo=research_repo,
            artifact_service=artifact_service,
            search_provider=search,
            extractor=extractor,
            model_router=router,
            agent_run_repo=agent_run_repo,
        ),
        competitor=CompetitorService(
            app_settings=test_settings,
            project_repo=project_repo,
            competitor_repo=competitor_repo,
            artifact_service=artifact_service,
            youtube_provider=yt,
            model_router=router,
            agent_run_repo=agent_run_repo,
        ),
        fact_checker=FactCheckService(
            app_settings=test_settings,
            project_repo=project_repo,
            research_repo=research_repo,
            fact_check_repo=fact_check_repo,
            artifact_service=artifact_service,
            model_router=router,
            approval_service=approval_service,
            agent_run_repo=agent_run_repo,
        ),
        scriptwriter=ScriptwriterService(
            app_settings=test_settings,
            project_repo=project_repo,
            script_repo=script_repo,
            research_repo=research_repo,
            fact_check_repo=fact_check_repo,
            competitor_repo=competitor_repo,
            guideline_service=guideline_service,
            artifact_service=artifact_service,
            model_router=router,
            approval_service=approval_service,
            agent_run_repo=agent_run_repo,
        ),
        storyboard=StoryboardService(
            app_settings=test_settings,
            project_repo=project_repo,
            script_repo=script_repo,
            scene_repo=scene_repo,
            guideline_service=guideline_service,
            artifact_service=artifact_service,
            model_router=router,
            agent_run_repo=agent_run_repo,
        ),
        approval=approval_service,
    )
    return WorkflowOrchestrator(
        app_settings=test_settings,
        project_repo=project_repo,
        run_repo=run_repo,
        services=services,
        agent_run_repo=agent_run_repo,
    )


@pytest.mark.asyncio
async def test_langgraph_full_hitl_workflow_with_restart_and_revision_loop(
    test_settings: Settings,
    db_session: AsyncSession,
    artifact_store: ArtifactStore,
) -> None:
    project_repo = ProjectRepository(db_session)
    project = await project_repo.create(
        title="LangGraph HITL",
        topic="LangGraph Checkpointing and Human Approvals",
    )
    await artifact_store.ainit_project_dirs(project.id)

    search = _WorkflowStubSearch()
    yt = _WorkflowStubYouTube()
    llm = _WorkflowMockLLM()

    orch1 = _build_orchestrator(
        test_settings=test_settings,
        db_session=db_session,
        artifact_store=artifact_store,
        search=search,
        yt=yt,
        llm=llm,
    )

    # 1. Start workflow -> pauses at Gate 1 (brief)
    snap1 = await orch1.start_workflow(project.id)
    assert snap1.status == RunStatus.INTERRUPTED.value
    assert snap1.pending_interrupt is not None
    assert snap1.pending_interrupt.gate == ApprovalGate.BRIEF.value
    assert "topic_strategist" in snap1.completed_steps
    assert test_settings.checkpoints_db_path.is_file()

    # 2. Simulate restart: build a brand new WorkflowOrchestrator reading same checkpoints.db
    orch2 = _build_orchestrator(
        test_settings=test_settings,
        db_session=db_session,
        artifact_store=artifact_store,
        search=search,
        yt=yt,
        llm=llm,
    )

    # Approve Gate 1 -> parallel research + competitor -> merge -> fact check -> Gate 2
    snap2 = await orch2.resume_workflow(
        snap1.run_id,
        decision=ApprovalStatus.APPROVED,
        reviewer="Santosh",
        comments="Brief looks sharp!",
    )
    assert snap2.status == RunStatus.INTERRUPTED.value
    assert snap2.pending_interrupt is not None
    assert snap2.pending_interrupt.gate == ApprovalGate.RESEARCH.value
    assert {
        "topic_strategist",
        "research",
        "competitor_analysis",
        "merge_research",
        "fact_checker",
    }.issubset(set(snap2.completed_steps))
    assert search.calls == 1
    assert yt.calls == 1

    # 3. Approve Gate 2 -> Scriptwriter v1 -> Gate 3 (script)
    snap3 = await orch2.resume_workflow(
        snap1.run_id,
        decision=ApprovalStatus.APPROVED,
        reviewer="Santosh",
    )
    assert snap3.status == RunStatus.INTERRUPTED.value
    assert snap3.pending_interrupt is not None
    assert snap3.pending_interrupt.gate == ApprovalGate.SCRIPT.value
    assert snap3.artifact_refs["script_version_number"] == 1

    # 4. Request changes at Gate 3 -> loops ONLY back to Scriptwriter (creates v2)
    snap4 = await orch2.resume_workflow(
        snap1.run_id,
        decision=ApprovalStatus.CHANGES_REQUESTED,
        reviewer="Santosh",
        comments="Make the Hinglish hook punchier.",
    )
    assert snap4.status == RunStatus.INTERRUPTED.value
    assert snap4.pending_interrupt is not None
    assert snap4.pending_interrupt.gate == ApprovalGate.SCRIPT.value
    assert snap4.artifact_refs["script_version_number"] == 2
    # Confirm earlier stages were NOT repeated!
    assert llm.call_log.count("topic_strategist") == 1
    assert llm.call_log.count("research_agent") == 1
    assert llm.call_log.count("competitor_analyst") == 1
    assert llm.call_log.count("fact_checker") == 1
    assert llm.call_log.count("scriptwriter") == 2

    # 5. Approve Gate 3 -> approves Script v2 -> Storyboard -> COMPLETED!
    snap5 = await orch2.resume_workflow(
        snap1.run_id,
        decision=ApprovalStatus.APPROVED,
        reviewer="Santosh",
        comments="Approved for recording!",
    )
    assert snap5.status == RunStatus.COMPLETED.value
    assert snap5.pending_interrupt is None
    assert "storyboard" in snap5.completed_steps
    assert snap5.artifact_refs["storyboard_artifact_id"] is not None

    refreshed_project = await project_repo.get_by_id(project.id)
    assert refreshed_project is not None
    assert refreshed_project.status == ProjectStatus.COMPLETED.value


@pytest.mark.asyncio
async def test_langgraph_rejection_at_gate_cancels_workflow(
    test_settings: Settings,
    db_session: AsyncSession,
    artifact_store: ArtifactStore,
) -> None:
    project_repo = ProjectRepository(db_session)
    project = await project_repo.create(title="Rejected Topic", topic="Rejected Topic Idea")
    await artifact_store.ainit_project_dirs(project.id)

    orch = _build_orchestrator(
        test_settings=test_settings,
        db_session=db_session,
        artifact_store=artifact_store,
        search=_WorkflowStubSearch(),
        yt=_WorkflowStubYouTube(),
        llm=_WorkflowMockLLM(),
    )

    snap1 = await orch.start_workflow(project.id)
    assert snap1.status == RunStatus.INTERRUPTED.value

    snap2 = await orch.resume_workflow(
        snap1.run_id,
        decision=ApprovalStatus.REJECTED,
        comments="Pivot to a better topic.",
    )
    assert snap2.status == RunStatus.CANCELLED.value
    assert "research" not in snap2.completed_steps
