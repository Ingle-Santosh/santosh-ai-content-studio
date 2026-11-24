import base64

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_artifact_store, get_model_router, get_settings
from app.main import create_app
from content_studio.config.settings import Settings
from content_studio.database.repositories import (
    ProjectRepository,
    SceneRepository,
    UsageRepository,
)
from content_studio.database.session import get_db_session
from content_studio.providers.llm import ModelRouter
from content_studio.storage.artifact_store import ArtifactStore
from tests.test_asset_service_and_qa import _AssetStubLLM


@pytest.mark.asyncio
async def test_assets_and_binary_download_api_routes(
    test_settings: Settings,
    db_session: AsyncSession,
    artifact_store: ArtifactStore,
) -> None:
    router = ModelRouter(
        app_settings=test_settings,
        local_provider=_AssetStubLLM(fail_first_code_demo=False),
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

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        project = (
            await client.post("/api/projects", json={"topic": "Embeddings Visual Walkthrough"})
        ).json()

        # Seed a storyboard scene with diagram + code_demo
        scene_repo = SceneRepository(db_session)
        await scene_repo.replace_for_project(
            project["id"],
            script_version_id=None,
            run_id=None,
            scenes_data=[
                {
                    "scene_number": 1,
                    "title": "RAG Architecture & Demo",
                    "estimated_duration_seconds": 60,
                    "narration": "Show flowchart and Python demo.",
                    "visual_type": "diagram",
                    "asset_requirements": [
                        {"asset_type": "diagram", "title": "RAG Flow", "description": "Flow"},
                        {
                            "asset_type": "code_demo",
                            "title": "Similarity Demo",
                            "description": "Python print demo",
                        },
                    ],
                    "related_script_section": "main_explanation",
                }
            ],
        )

        # Plan
        plan_resp = await client.post(f"/api/projects/{project['id']}/assets/plan")
        assert plan_resp.status_code == 200
        assert len(plan_resp.json()["items"]) == 2

        # Generate + QA
        gen_resp = await client.post(
            f"/api/projects/{project['id']}/assets/generate",
            json={"run_qa": True, "request_assets_approval": True},
        )
        assert gen_resp.status_code == 200
        gen_data = gen_resp.json()
        assert gen_data["succeeded_count"] == 2
        assert gen_data["approval_id"] is not None

        # Upload real PNG screenshot with provenance + annotation
        png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 24
        shot_resp = await client.post(
            f"/api/projects/{project['id']}/assets/screenshots",
            json={
                "filename": "dashboard_metrics.png",
                "content_base64": base64.b64encode(png_bytes).decode("ascii"),
                "provenance": {
                    "source_origin": "user_upload",
                    "captured_by": "Santosh",
                    "source_url": "http://localhost:8501",
                },
                "scene_number": 1,
                "annotations": [
                    {"x": 10, "y": 20, "width": 120, "height": 40, "label": "Health Check"}
                ],
            },
        )
        assert shot_resp.status_code == 201
        shot_data = shot_resp.json()
        assert shot_data["overlay_artifact_id"] is not None

        # Download binary screenshot via /artifacts/{id}/download
        dl_resp = await client.get(
            f"/api/projects/{project['id']}/artifacts/{shot_data['screenshot_artifact_id']}/download"
        )
        assert dl_resp.status_code == 200
        assert dl_resp.content == png_bytes
        assert dl_resp.headers["x-checksum-sha256"] == shot_data["checksum_sha256"]

        # Re-run QA including the newly uploaded screenshot
        qa_resp = await client.post(
            f"/api/projects/{project['id']}/assets/qa",
            json={"request_assets_approval": False},
        )
        assert qa_resp.status_code == 200
        assert qa_resp.json()["passed"] is True
