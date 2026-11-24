import json
from collections.abc import AsyncGenerator
from pathlib import Path

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_artifact_store, get_model_router, get_settings
from app.main import create_app
from content_studio.config.settings import Settings
from content_studio.database.models.enums import (
    ClaimVerdict,
    SourceStatus,
)
from content_studio.database.repositories import (
    FactCheckRepository,
    ProjectRepository,
    ResearchRepository,
    SceneRepository,
    ScriptRepository,
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
from content_studio.storage.artifact_store import ArtifactStore


class _RegressionFakeProvider(BaseLLMProvider):
    """Deterministic local LLM stub that answers asset & YouTube strategy calls."""

    provider_name = "ollama"
    is_cloud = False

    async def generate(self, request: LLMRequest) -> LLMResponse:
        props = set((request.json_schema or {}).get("properties", {}).keys())
        if "editing_summary" in props:
            body = {
                "editing_summary": (
                    "Clean technical walkthrough pairing narration with architecture diagrams."
                ),
                "pacing_and_audio_notes": [
                    "Keep intro under 30s and normalize narration to -14 LUFS."
                ],
                "b_roll_and_overlay_cues": ["Overlay RAG vs CAG flowchart at 00:30."],
                "recording_checklist": ["Verify microphone levels and 1080p screen capture."],
                "post_production_checklist": ["Export 1080p60 MP4 and review chapter timestamps."],
            }
        elif "title_options" in props:
            body = {
                "title_options": [
                    "RAG vs CAG Explained for Data Engineers",
                    "Stop Using RAG Everywhere: CAG Architecture",
                    "RAG vs Cache-Augmented Generation Deep Dive",
                ],
                "recommended_title": "RAG vs CAG Explained for Data Engineers",
                "description": (
                    "Is video mein hum RAG vs CAG architecture compare karenge.\n"
                    "Santosh Analytics — practical Data & AI engineering with 8+ years experience."
                ),
                "chapters": [
                    {"timestamp": "00:00", "title": "Intro & Problem"},
                    {"timestamp": "01:00", "title": "Architecture & Demo"},
                ],
                "tags": ["RAG", "CAG", "AI Engineering", "LLM Architecture", "Hinglish"],
                "hashtags": ["#RAG", "#CAG", "#AIEngineering"],
                "pinned_comment": (
                    "Aap production mein RAG use karte ho ya CAG? Comment mein batao!"
                ),
                "thumbnail_concepts": [
                    {
                        "concept_name": "Split Architecture",
                        "headline_text": "RAG vs CAG",
                        "visual_composition": "Split architecture diagram with KV cache focus",
                        "color_palette": "Navy & Cyan",
                    },
                    {
                        "concept_name": "Zero Vector DB",
                        "headline_text": "ZERO VECTOR DB?",
                        "visual_composition": "Clean diagram contrasting vector search vs cache",
                        "color_palette": "Dark slate & Amber",
                    },
                ],
            }
        else:
            body = {
                "title": "RAG vs CAG Flow",
                "mermaid_code": "flowchart LR\n  A[User Query] --> B[KV Cache]\n  B --> C[Answer]",
                "caption": "Comparison flow.",
            }

        return LLMResponse(
            content=json.dumps(body),
            provider="ollama",
            model=request.model,
            prompt_tokens=200,
            completion_tokens=150,
            estimated_cost_usd=0.0,
            latency_ms=95,
        )

    async def health_check(self) -> ProviderHealth:
        return ProviderHealth(provider="ollama", reachable=True, models=["qwen2.5:14b"])


async def test_request_id_middleware_and_error_handlers(api_client: AsyncClient) -> None:
    resp = await api_client.get("/health", headers={"X-Request-ID": "req-test-123"})
    assert resp.status_code == 200
    assert resp.headers.get("X-Request-ID") == "req-test-123"

    # Auto-generated request ID & clean JSON 404 for missing project
    missing = await api_client.get("/api/projects/does-not-exist/evaluations")
    assert missing.status_code == 404
    assert missing.headers.get("X-Request-ID")
    assert "detail" in missing.json()


async def test_end_to_end_pipeline_regression_and_system_metrics(
    test_settings: Settings,
    db_session: AsyncSession,
    artifact_store: ArtifactStore,
) -> None:
    app = create_app()

    async def _override_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    usage_repo = UsageRepository(db_session)
    project_repo = ProjectRepository(db_session)
    fake_router = ModelRouter(
        app_settings=test_settings,
        local_provider=_RegressionFakeProvider(),
        usage_repo=usage_repo,
        project_repo=project_repo,
    )

    app.dependency_overrides[get_settings] = lambda: test_settings
    app.dependency_overrides[get_db_session] = _override_db
    app.dependency_overrides[get_artifact_store] = lambda: artifact_store
    app.dependency_overrides[get_model_router] = lambda: fake_router

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Create Project
        proj_resp = await client.post(
            "/api/projects",
            json={
                "topic": "RAG vs CAG Architecture Trade-offs",
                "title": "RAG vs CAG Deep Dive",
            },
        )
        assert proj_resp.status_code == 201
        project_id = proj_resp.json()["id"]

        # 2. Seed grounded research, verified claim, approved script, & storyboard scenes
        research_repo = ResearchRepository(db_session)
        fact_repo = FactCheckRepository(db_session)
        script_repo = ScriptRepository(db_session)
        scene_repo = SceneRepository(db_session)

        for idx in range(3):
            url = f"https://arxiv.org/abs/2501.0000{idx}"
            await research_repo.create_source(
                project_id=project_id,
                url=url,
                normalized_url=url,
                url_hash=f"reg-hash-{idx}",
                title=f"Paper {idx}",
                domain="arxiv.org",
                provider="duckduckgo",
                status=SourceStatus.EXTRACTED,
            )
        await research_repo.create_finding(
            project_id=project_id,
            title="CAG eliminates online vector lookup",
            summary="Static knowledge bases fit in long-context KV cache.",
            source_urls=["https://arxiv.org/abs/2501.00000"],
        )
        await fact_repo.create_claim(
            project_id=project_id,
            statement="CAG eliminates online vector lookup for static corpora.",
            verdict=ClaimVerdict.VERIFIED,
            confidence=0.92,
            rationale="Grounded in arxiv paper.",
        )

        script = await script_repo.get_or_create_script(
            project_id=project_id,
            title="RAG vs CAG Deep Dive",
        )
        version = await script_repo.create_version(
            script,
            project_id=project_id,
            language="Hinglish",
            total_estimated_duration_seconds=720,
            word_count=1100,
            sections_json=[
                {
                    "section_type": "hook",
                    "title": "Hook",
                    "narration": "Kya RAG har jagah zaroori hai?",
                    "estimated_duration_seconds": 30,
                },
                {
                    "section_type": "practical_demonstration",
                    "title": "Demo",
                    "narration": "Ab architecture diagram aur metrics dekhte hain.",
                    "estimated_duration_seconds": 120,
                    "code_demo_references": ["demo.py"],
                },
            ],
            validation_report_json={"score": 96.0, "is_valid": True, "errors": [], "warnings": []},
        )
        await script_repo.approve_version(script, version)

        await scene_repo.replace_for_project(
            project_id,
            script_version_id=version.id,
            run_id=None,
            scenes_data=[
                {
                    "scene_number": 1,
                    "title": "RAG vs CAG Diagram",
                    "estimated_duration_seconds": 60,
                    "narration": "Here is the side-by-side flow.",
                    "visual_type": "diagram",
                    "related_script_section": "practical_demonstration",
                    "asset_requirements": [
                        {
                            "asset_type": "diagram",
                            "title": "RAG vs CAG Flow",
                            "description": "Mermaid flowchart comparing RAG and CAG.",
                        }
                    ],
                }
            ],
        )

        # 3. Generate Assets + QA
        asset_resp = await client.post(
            f"/api/projects/{project_id}/assets/generate",
            json={"run_qa": True, "request_assets_approval": True},
        )
        assert asset_resp.status_code == 200
        assert asset_resp.json()["succeeded_count"] >= 1
        assert asset_resp.json()["failed_count"] == 0
        assert asset_resp.json()["qa_report_id"] is not None
        assert asset_resp.json()["approval_id"] is not None

        # 4. Build Production Package + YouTube Strategy + Export ZIP
        prod_resp = await client.post(
            f"/api/projects/{project_id}/production/package",
            json={"include_youtube_metadata": True, "request_final_approval": True},
        )
        assert prod_resp.status_code == 200
        prod_data = prod_resp.json()
        assert prod_data["publishing_mode"] == "MANUAL_ONLY"
        assert prod_data["export_zip_file_count"] >= 4
        assert Path(
            test_settings.resolved_projects_dir / project_id / prod_data["export_zip_relative_path"]
        ).is_file()

        # 5. Run 7-Dimension Evaluation via API
        eval_resp = await client.post(
            f"/api/projects/{project_id}/evaluations/run",
            json={"use_llm_judge": False},
        )
        assert eval_resp.status_code == 200
        ev = eval_resp.json()
        assert ev["overall_score"] >= 90.0
        assert ev["human_review_required"] is True
        assert ev["latency_cost_summary"]["total_llm_calls"] >= 2

        list_eval = await client.get(f"/api/projects/{project_id}/evaluations")
        assert list_eval.status_code == 200
        assert list_eval.json()["total"] == 1

        # 6. Verify /api/system/metrics telemetry
        metrics_resp = await client.get("/api/system/metrics")
        assert metrics_resp.status_code == 200
        metrics = metrics_resp.json()
        assert metrics["total_projects"] == 1
        assert metrics["pending_approvals"] >= 2
        assert metrics["total_llm_calls"] >= 2
        assert metrics["total_estimated_cost_usd"] == 0.0
