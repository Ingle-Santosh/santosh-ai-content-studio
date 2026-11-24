import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from content_studio.config.settings import Settings
from content_studio.database.models.enums import (
    ArtifactType,
    ClaimVerdict,
    SourceStatus,
)
from content_studio.database.repositories import (
    ArtifactRepository,
    EvaluationRepository,
    FactCheckRepository,
    ProjectRepository,
    ResearchRepository,
    SceneRepository,
    ScriptRepository,
    UsageRepository,
)
from content_studio.evaluation import (
    EvaluationDimensionScores,
    EvaluationService,
    EvaluationWeights,
    compute_weighted_score,
)
from content_studio.providers.llm import (
    BaseLLMProvider,
    LLMRequest,
    LLMResponse,
    ModelRouter,
    ProviderHealth,
)
from content_studio.services.artifact_service import ArtifactService
from content_studio.storage.artifact_store import ArtifactStore


class _FakeJudgeProvider(BaseLLMProvider):
    provider_name = "ollama"
    is_cloud = False

    async def generate(self, request: LLMRequest) -> LLMResponse:
        payload = {
            "teaching_clarity_score": 92.0,
            "script_quality_score": 88.0,
            "feedback": "Clear Hinglish technical walkthrough with grounded examples.",
        }
        return LLMResponse(
            content=json.dumps(payload),
            provider="ollama",
            model=request.model,
            prompt_tokens=120,
            completion_tokens=45,
            estimated_cost_usd=0.0,
            latency_ms=85,
        )

    async def health_check(self) -> ProviderHealth:
        return ProviderHealth(provider="ollama", reachable=True, models=["qwen2.5:14b"])


def test_evaluation_weights_and_weighted_score() -> None:
    default_weights = EvaluationWeights()
    scores = EvaluationDimensionScores(
        factual_accuracy=100.0,
        research_quality=80.0,
        script_quality=90.0,
        teaching_clarity=80.0,
        visual_relevance=70.0,
        channel_guideline_compliance=100.0,
        production_readiness=100.0,
    )
    # 25 + 12 + 18 + 12 + 7 + 10 + 5 = 89.0
    assert compute_weighted_score(scores, default_weights) == 89.0

    with pytest.raises(ValidationError, match="sum to 1.0"):
        EvaluationWeights(factual_accuracy=0.5, research_quality=0.5, script_quality=0.5)


async def test_evaluation_service_deterministic_repeatability_and_telemetry(
    test_settings: Settings,
    db_session: AsyncSession,
    artifact_store: ArtifactStore,
) -> None:
    project_repo = ProjectRepository(db_session)
    research_repo = ResearchRepository(db_session)
    fact_check_repo = FactCheckRepository(db_session)
    script_repo = ScriptRepository(db_session)
    scene_repo = SceneRepository(db_session)
    usage_repo = UsageRepository(db_session)
    evaluation_repo = EvaluationRepository(db_session)
    artifact_service = ArtifactService(
        project_repo=project_repo,
        artifact_repo=ArtifactRepository(db_session),
        store=artifact_store,
    )

    project = await project_repo.create(topic="RAG vs CAG Evaluation", title="RAG vs CAG Eval")

    # Seed extracted sources, grounded findings, verified claims, script, scene, visual, & usage
    for idx in range(3):
        url = f"https://docs.example.com/rag-{idx}"
        await research_repo.create_source(
            project_id=project.id,
            url=url,
            normalized_url=url,
            url_hash=f"hash-{idx}",
            title=f"Doc {idx}",
            domain="docs.example.com",
            provider="duckduckgo",
            status=SourceStatus.EXTRACTED,
        )
    await research_repo.create_finding(
        project_id=project.id,
        title="Cache-Augmented Generation removes retrieval latency",
        summary="Preloading static docs into KV cache cuts online vector search latency.",
        source_urls=["https://docs.example.com/rag-0"],
    )
    await fact_check_repo.create_claim(
        project_id=project.id,
        statement="CAG preloads static context into the KV cache.",
        verdict=ClaimVerdict.VERIFIED,
        confidence=0.95,
        rationale="Supported by primary source.",
    )
    script = await script_repo.get_or_create_script(project_id=project.id, title=project.title)
    ver = await script_repo.create_version(
        script,
        project_id=project.id,
        language="Hinglish",
        total_estimated_duration_seconds=600,
        word_count=900,
        sections_json=[
            {
                "section_type": "examples",
                "title": "Real-World Example",
                "narration": "Aaj dekhte hain CAG ka real example.",
                "code_demo_references": ["demo_cag.py"],
            }
        ],
        validation_report_json={"score": 94.0, "is_valid": True, "errors": [], "warnings": []},
    )
    await script_repo.approve_version(script, ver)

    await scene_repo.replace_for_project(
        project.id,
        script_version_id=ver.id,
        run_id=None,
        scenes_data=[
            {
                "scene_number": 1,
                "title": "Architecture Overview",
                "estimated_duration_seconds": 60,
                "narration": "Let us compare RAG and CAG.",
                "visual_type": "diagram",
                "related_script_section": "examples",
            }
        ],
    )
    await artifact_service.save_text(
        project_id=project.id,
        stage="visuals",
        artifact_type=ArtifactType.DIAGRAM_SVG,
        name="arch.svg",
        relative_path=Path("04_visuals/diagrams/arch.svg"),
        content="<svg xmlns='http://www.w3.org/2000/svg'></svg>",
    )
    await artifact_service.save_text(
        project_id=project.id,
        stage="export",
        artifact_type=ArtifactType.YOUTUBE_METADATA,
        name="youtube_metadata.json",
        relative_path=Path("06_export/youtube_metadata.json"),
        content='{"recommended_title": "RAG vs CAG"}',
    )
    await artifact_service.save_bytes(
        project_id=project.id,
        stage="export",
        artifact_type=ArtifactType.EXPORT_BUNDLE,
        name="package.zip",
        relative_path=Path("06_export/package.zip"),
        content=b"PK\x05\x06" + b"\x00" * 18,
    )
    await usage_repo.create(
        project_id=project.id,
        provider="ollama",
        model="qwen2.5:14b",
        node_name="scriptwriter",
        prompt_tokens=500,
        completion_tokens=300,
        estimated_cost_usd=0.0,
        latency_ms=1200,
    )

    service = EvaluationService(
        app_settings=test_settings,
        project_repo=project_repo,
        research_repo=research_repo,
        fact_check_repo=fact_check_repo,
        script_repo=script_repo,
        scene_repo=scene_repo,
        usage_repo=usage_repo,
        evaluation_repo=evaluation_repo,
        artifact_service=artifact_service,
        model_router=ModelRouter(
            app_settings=test_settings,
            local_provider=_FakeJudgeProvider(),
            usage_repo=usage_repo,
            project_repo=project_repo,
        ),
    )

    run1 = await service.evaluate_project(project.id, use_llm_judge=False)
    run2 = await service.evaluate_project(project.id, use_llm_judge=False)

    assert run1.overall_score == run2.overall_score
    assert run1.dimension_scores == run2.dimension_scores
    assert run1.overall_score >= 90.0
    assert run1.human_review_required is True
    assert run1.evaluator == "deterministic_rubric"
    assert run1.latency_cost_summary.total_llm_calls == 1
    assert run1.latency_cost_summary.avg_latency_ms == 1200.0
    assert run1.report_artifact_id is not None

    # Verify optional LLM-as-a-judge mode blends scores and logs additional usage
    judge_run = await service.evaluate_project(project.id, use_llm_judge=True)
    assert judge_run.evaluator == "hybrid_llm_judge"
    assert judge_run.model is not None and judge_run.model.startswith("ollama/")
    assert judge_run.human_review_required is True
    assert judge_run.latency_cost_summary.total_llm_calls == 2
    assert "LLM Judge:" in judge_run.feedback

    history = await service.list_evaluations(project.id)
    assert len(history) == 3
