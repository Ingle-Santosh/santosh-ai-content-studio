import json

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from content_studio.config.settings import Settings
from content_studio.database.models.enums import (
    ApprovalGate,
    ApprovalStatus,
    ArtifactStatus,
    ScriptSectionType,
    ScriptStatus,
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
    ScriptNotApprovedError,
    ScriptwriterService,
    StoryboardService,
)
from content_studio.services.script_validator import REQUIRED_SECTIONS
from content_studio.storage.artifact_store import ArtifactStore


def _make_script_payload(title: str, suffix: str = "") -> dict:
    return {
        "title": title,
        "language": "Hinglish",
        "sections": [
            {
                "section_type": sec.value,
                "title": f"{sec.value.replace('_', ' ').title()}{suffix}",
                "narration": (
                    "Namaste dosto! Aaj hum Agentic AI aur practical MLOps workflow ko "
                    "step by step architecture diagram aur code demo ke saath samjhenge."
                ),
                "visual_instructions": "Show architecture diagram and highlight flow.",
                "screen_recording_requirements": (
                    "VS Code walkthrough"
                    if sec == ScriptSectionType.PRACTICAL_DEMONSTRATION
                    else None
                ),
                "code_demo_references": (
                    ["agent_demo.py"] if sec == ScriptSectionType.PRACTICAL_DEMONSTRATION else []
                ),
                "estimated_duration_seconds": 100,
                "source_urls": [],
            }
            for sec in REQUIRED_SECTIONS
        ],
    }


def _make_storyboard_payload() -> dict:
    return {
        "summary": "Balanced mix of face-cam intro, architecture diagram, and live Python demo.",
        "scenes": [
            {
                "scene_number": 1,
                "title": "High-Impact Hook",
                "estimated_duration_seconds": 40,
                "narration": (
                    "Namaste dosto! Kya aapne kabhi socha hai RAG aur CAG mein kya farak hai?"
                ),
                "on_screen_text": "RAG vs CAG: Production Trade-offs",
                "visual_type": "face_cam",
                "asset_requirements": [],
                "camera_or_screen_instructions": "Medium close-up, energetic delivery.",
                "transition_instructions": "Cut to architecture overview.",
                "related_script_section": "hook",
            },
            {
                "scene_number": 2,
                "title": "Architecture Comparison Diagram",
                "estimated_duration_seconds": 90,
                "narration": (
                    "Chaliye architecture diagram se latency aur memory trade-offs dekhte hain."
                ),
                "on_screen_text": "Retrieval vs Preloaded KV Cache",
                "visual_type": "diagram",
                "asset_requirements": [
                    {
                        "asset_type": "diagram",
                        "title": "RAG vs CAG Architecture Flowchart",
                        "description": "Side-by-side Mermaid flowchart comparing query paths.",
                    }
                ],
                "camera_or_screen_instructions": "Picture-in-picture bottom right.",
                "transition_instructions": "Fade into IDE screen recording.",
                "related_script_section": "main_explanation",
            },
        ],
    }


class _ScriptedLLM(BaseLLMProvider):
    provider_name = "ollama"
    is_cloud = False

    def __init__(self, payloads: list[dict]) -> None:
        self._payloads = list(payloads)
        self.prompts: list[str] = []

    async def generate(self, request: LLMRequest) -> LLMResponse:
        self.prompts.append(request.messages[-1].content)
        return LLMResponse(
            provider="ollama",
            model=request.model,
            content=json.dumps(self._payloads.pop(0)),
        )

    async def health_check(self) -> ProviderHealth:
        return ProviderHealth(provider="ollama", is_cloud=False, available=True)


@pytest.mark.asyncio
async def test_script_versioning_approval_and_storyboard_gating(
    test_settings: Settings,
    db_session: AsyncSession,
    artifact_store: ArtifactStore,
) -> None:
    project_repo = ProjectRepository(db_session)
    artifact_repo = ArtifactRepository(db_session)
    script_repo = ScriptRepository(db_session)
    scene_repo = SceneRepository(db_session)
    research_repo = ResearchRepository(db_session)
    fact_check_repo = FactCheckRepository(db_session)
    competitor_repo = CompetitorRepository(db_session)
    approval_repo = ApprovalRepository(db_session)
    guideline_repo = ChannelGuidelineRepository(db_session)
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

    project = await project_repo.create(
        title="RAG vs CAG",
        topic="RAG vs CAG Production Trade-offs",
        config={"duration_minutes": 15, "language": "Hinglish", "include_code_demo": True},
    )
    await artifact_store.ainit_project_dirs(project.id)

    llm = _ScriptedLLM(
        [
            _make_script_payload("RAG vs CAG Draft 1"),
            _make_script_payload("RAG vs CAG Revised 2", suffix=" (Updated)"),
            _make_storyboard_payload(),
        ]
    )
    router = ModelRouter(
        app_settings=test_settings,
        local_provider=llm,
        usage_repo=usage_repo,
        project_repo=project_repo,
    )
    script_service = ScriptwriterService(
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
    )
    storyboard_service = StoryboardService(
        app_settings=test_settings,
        project_repo=project_repo,
        script_repo=script_repo,
        scene_repo=scene_repo,
        guideline_service=guideline_service,
        artifact_service=artifact_service,
        model_router=router,
        agent_run_repo=agent_run_repo,
    )

    # 1. Generate v1 -> uses channel guidelines and passes deterministic validation
    v1 = await script_service.generate_script(project.id)
    assert v1.version_number == 1
    assert v1.validation.passed is True
    assert v1.approval_id is not None
    assert "8+ years of experience" in llm.prompts[0]

    # 2. Storyboarding is blocked until script is approved
    with pytest.raises(ScriptNotApprovedError):
        await storyboard_service.generate_storyboard(project.id, require_approved_script=True)

    # 3. Revise to v2 -> v1 is preserved as SUPERSEDED
    v2 = await script_service.generate_script(
        project.id,
        revision_notes="Make the hook sharper for data engineers.",
    )
    assert v2.version_number == 2
    assert "Make the hook sharper" in llm.prompts[1]

    versions = await script_repo.list_versions(project.id)
    assert len(versions) == 2
    by_num = {v.version_number: v for v in versions}
    assert by_num[1].status == ArtifactStatus.SUPERSEDED.value
    assert by_num[2].status == ArtifactStatus.DRAFT.value

    # 4. Approve v2 -> marks script APPROVED and resolves Gate 3 approval
    approved = await script_service.approve_version(project.id, 2, reviewer="Santosh")
    assert approved.status == ArtifactStatus.APPROVED.value

    script_row = await script_repo.get_for_project(project.id)
    assert script_row is not None
    assert script_row.status == ScriptStatus.APPROVED.value
    assert script_row.approved_version == 2

    gate3 = await approval_repo.list_approvals(project_id=project.id, gate=ApprovalGate.SCRIPT)
    assert all(a.status == ApprovalStatus.APPROVED.value for a in gate3)

    # 5. Storyboarding now succeeds from approved v2
    sb = await storyboard_service.generate_storyboard(project.id, require_approved_script=True)
    assert sb.script_version_number == 2
    assert sb.total_scenes == 2
    assert sb.total_asset_requirements == 1
    assert sb.storyboard_markdown_artifact_id is not None

    scenes = await storyboard_service.list_scenes(project.id)
    assert [s.scene_number for s in scenes] == [1, 2]
    assert scenes[1].asset_requirements_json[0]["asset_type"] == "diagram"
