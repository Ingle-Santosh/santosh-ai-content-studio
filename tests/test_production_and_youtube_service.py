import io
import json
import zipfile

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from content_studio.config.settings import Settings
from content_studio.database.models.enums import ApprovalGate, ApprovalStatus, ArtifactType
from content_studio.database.repositories import (
    AgentRunRepository,
    ApprovalRepository,
    ArtifactRepository,
    ChannelGuidelineRepository,
    CompetitorRepository,
    ProjectRepository,
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
from content_studio.services import (
    ApprovalService,
    ArtifactService,
    ChannelGuidelineService,
    ProductionService,
    YouTubeStrategyService,
    format_timestamp,
)
from content_studio.storage.artifact_store import ArtifactStore


class _ProdStubLLM(BaseLLMProvider):
    provider_name = "ollama"
    is_cloud = False

    async def generate(self, request: LLMRequest) -> LLMResponse:
        prompt = request.messages[-1].content
        if "YouTube packaging metadata" in prompt:
            # Deliberately omit "8+ years" to test deterministic bio-note enforcement!
            payload = {
                "title_options": [
                    "RAG vs CAG Explained with Python Demo",
                    "Stop Guessing: RAG vs CAG Architecture Trade-offs",
                    "Production RAG vs CAG in 15 Minutes (Hinglish)",
                ],
                "recommended_title": "RAG vs CAG Explained with Python Demo",
                "description": (
                    "In this practical walkthrough we compare RAG and CAG trade-offs with code."
                ),
                "chapters": [
                    {"timestamp": "00:00", "title": "Intro & Problem"},
                    {"timestamp": "00:45", "title": "Architecture Comparison"},
                ],
                "tags": ["RAG", "CAG", "GenAI", "Agentic AI", "Santosh Analytics"],
                "hashtags": ["#GenAI", "#DataEngineering"],
                "thumbnail_concepts": [
                    {
                        "concept_name": "Split Trade-off",
                        "headline_text": "RAG vs CAG",
                        "visual_composition": (
                            "Creator on left pointing to side-by-side latency chart."
                        ),
                        "color_palette": "Navy slate + cyan + amber",
                    },
                    {
                        "concept_name": "Architecture Blueprint",
                        "headline_text": "Which One Wins?",
                        "visual_composition": "Clean flowchart behind medium close-up.",
                        "color_palette": "Dark slate + emerald",
                    },
                ],
                "pinned_comment": (
                    "Are you using RAG or CAG in production? Share your latency numbers!"
                ),
            }
        else:
            payload = {
                "editing_summary": "Tight jump cuts on face-cam with full-screen SVG overlays.",
                "pacing_and_audio_notes": ["Normalize voiceover to -14 LUFS"],
                "b_roll_and_overlay_cues": ["Scene 2: Overlay rag_flow.svg at 00:45"],
                "recording_checklist": ["Set VS Code font size to 18px"],
                "post_production_checklist": ["Verify chapter timestamps match final cut"],
            }
        return LLMResponse(provider="ollama", model=request.model, content=json.dumps(payload))

    async def health_check(self) -> ProviderHealth:
        return ProviderHealth(provider="ollama", is_cloud=False, available=True)


def test_format_timestamp_helper() -> None:
    assert format_timestamp(0) == "00:00"
    assert format_timestamp(95) == "01:35"
    assert format_timestamp(3725) == "1:02:05"


@pytest.mark.asyncio
async def test_production_package_zip_youtube_bio_guard_and_gate5(
    test_settings: Settings,
    db_session: AsyncSession,
    artifact_store: ArtifactStore,
) -> None:
    project_repo = ProjectRepository(db_session)
    artifact_repo = ArtifactRepository(db_session)
    script_repo = ScriptRepository(db_session)
    scene_repo = SceneRepository(db_session)
    competitor_repo = CompetitorRepository(db_session)
    guideline_repo = ChannelGuidelineRepository(db_session)
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
    guideline_service = ChannelGuidelineService(guideline_repo)
    router = ModelRouter(
        app_settings=test_settings,
        local_provider=_ProdStubLLM(),
        usage_repo=usage_repo,
        project_repo=project_repo,
    )

    project = await project_repo.create(
        title="RAG vs CAG Masterclass",
        topic="RAG vs CAG Architectural Trade-offs",
    )
    await artifact_store.ainit_project_dirs(project.id)

    # Seed script, storyboard, research, and visual assets
    await artifact_service.save_text(
        project_id=project.id,
        stage="script",
        artifact_type=ArtifactType.SCRIPT,
        name="script_v1.md",
        content="# Script\nNamaste devs!",
    )
    await artifact_service.save_text(
        project_id=project.id,
        stage="outline",
        artifact_type=ArtifactType.STORYBOARD,
        name="storyboard.md",
        content="# Storyboard\nScene 1 & 2",
    )
    await artifact_service.save_text(
        project_id=project.id,
        stage="visuals",
        artifact_type=ArtifactType.DIAGRAM_SVG,
        name="rag_flow.svg",
        content="<svg xmlns='http://www.w3.org/2000/svg'></svg>",
        metadata_json={"scene_number": 2},
    )
    await scene_repo.replace_for_project(
        project.id,
        script_version_id=None,
        run_id=None,
        scenes_data=[
            {
                "scene_number": 1,
                "title": "Intro Hook",
                "estimated_duration_seconds": 45,
                "narration": "Namaste devs!",
                "visual_type": "face_cam",
                "related_script_section": "hook",
            },
            {
                "scene_number": 2,
                "title": "Architecture Flowchart",
                "estimated_duration_seconds": 90,
                "narration": "Compare retrieval vs preloaded context.",
                "visual_type": "diagram",
                "related_script_section": "main_explanation",
            },
        ],
    )

    yt_service = YouTubeStrategyService(
        app_settings=test_settings,
        project_repo=project_repo,
        script_repo=script_repo,
        scene_repo=scene_repo,
        competitor_repo=competitor_repo,
        guideline_service=guideline_service,
        artifact_service=artifact_service,
        model_router=router,
        agent_run_repo=agent_run_repo,
    )
    prod_service = ProductionService(
        app_settings=test_settings,
        project_repo=project_repo,
        script_repo=script_repo,
        scene_repo=scene_repo,
        artifact_service=artifact_service,
        youtube_strategy_service=yt_service,
        model_router=router,
        approval_service=approval_service,
        agent_run_repo=agent_run_repo,
    )

    pkg = await prod_service.build_production_package(
        project.id,
        include_youtube_metadata=True,
        request_final_approval=True,
    )

    assert pkg.publishing_mode == "MANUAL_ONLY"
    assert pkg.total_estimated_duration_seconds == 135
    assert [s.start_timestamp for s in pkg.scene_sequence] == ["00:00", "00:45"]
    assert pkg.scene_sequence[1].linked_asset_paths != []
    assert pkg.youtube_metadata is not None
    # Deterministic guideline guardrail injected 8+ years experience bio note
    assert "8+ years" in pkg.youtube_metadata.description.lower()
    assert pkg.export_zip_artifact_id is not None
    assert pkg.approval_id is not None

    # Inspect actual ZIP contents from ArtifactStore
    _art, zip_bytes = await artifact_service.read_artifact_bytes(
        project.id, pkg.export_zip_artifact_id
    )
    with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
        names = set(zf.namelist())
        assert "README_PRODUCTION.md" in names
        assert "manifest.json" in names
        assert any(n.startswith("script/") for n in names)
        assert any(n.startswith("storyboard/") for n in names)
        assert any(n.startswith("assets/") for n in names)
        assert any(n.startswith("youtube/") for n in names)

        manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
        assert manifest["manual_publishing_only"] is True

    # Gate 5 approval created
    gate5 = await approval_repo.list_approvals(
        project_id=project.id, gate=ApprovalGate.PRODUCTION_PACKAGE
    )
    assert len(gate5) == 1
    assert gate5[0].status == ApprovalStatus.PENDING.value
