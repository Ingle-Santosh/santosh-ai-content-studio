import io
import zipfile

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_artifact_store, get_model_router, get_settings
from app.main import create_app
from content_studio.config.settings import Settings
from content_studio.database.repositories import ProjectRepository, UsageRepository
from content_studio.database.session import get_db_session
from content_studio.providers.llm import ModelRouter
from content_studio.storage.artifact_store import ArtifactStore
from tests.test_production_and_youtube_service import _ProdStubLLM


@pytest.mark.asyncio
async def test_production_and_youtube_api_routes_and_zip_download(
    test_settings: Settings,
    db_session: AsyncSession,
    artifact_store: ArtifactStore,
) -> None:
    router = ModelRouter(
        app_settings=test_settings,
        local_provider=_ProdStubLLM(),
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
            await client.post("/api/projects", json={"topic": "MLOps Production Packaging"})
        ).json()

        # Before building -> /latest returns 404
        missing_latest = await client.get(f"/api/projects/{project['id']}/production/latest")
        assert missing_latest.status_code == 404

        # Generate standalone YouTube metadata
        yt_resp = await client.post(
            f"/api/projects/{project['id']}/production/youtube-metadata",
            json={},
        )
        assert yt_resp.status_code == 200
        assert yt_resp.json()["publishing_mode"] == "MANUAL_ONLY"
        assert "8+ years" in yt_resp.json()["metadata"]["description"].lower()

        # Build full production package + ZIP bundle
        pkg_resp = await client.post(
            f"/api/projects/{project['id']}/production/package",
            json={"include_youtube_metadata": True, "request_final_approval": True},
        )
        assert pkg_resp.status_code == 200
        pkg = pkg_resp.json()
        assert pkg["publishing_mode"] == "MANUAL_ONLY"
        assert pkg["export_zip_artifact_id"] is not None
        assert pkg["approval_id"] is not None

        # Fetch latest export info
        latest_resp = await client.get(f"/api/projects/{project['id']}/production/latest")
        assert latest_resp.status_code == 200
        latest = latest_resp.json()
        assert latest["publishing_mode"] == "MANUAL_ONLY"
        assert "manifest.json" in latest["included_files"]

        # Download actual ZIP bytes via binary download endpoint
        dl_resp = await client.get(
            f"/api/projects/{project['id']}/artifacts/{pkg['export_zip_artifact_id']}/download"
        )
        assert dl_resp.status_code == 200
        assert dl_resp.headers["content-type"] == "application/zip"
        with zipfile.ZipFile(io.BytesIO(dl_resp.content), "r") as zf:
            assert "README_PRODUCTION.md" in zf.namelist()
            assert "manifest.json" in zf.namelist()
