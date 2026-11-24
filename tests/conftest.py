from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_artifact_store, get_settings
from app.main import create_app
from content_studio.config.settings import Settings
from content_studio.database.models import Base
from content_studio.database.session import (
    build_async_engine,
    build_session_factory,
    get_db_session,
)
from content_studio.storage.artifact_store import ArtifactStore


@pytest.fixture
def test_settings(tmp_path: Path) -> Settings:
    cfg = Settings(
        APP_ENV="test",
        LOCAL_ONLY=True,
        DATA_DIR=tmp_path / "data",
    )
    cfg.ensure_directories()
    return cfg


@pytest.fixture
def artifact_store(test_settings: Settings) -> ArtifactStore:
    return ArtifactStore(projects_dir=test_settings.resolved_projects_dir)


@pytest.fixture
async def db_session(test_settings: Settings) -> AsyncGenerator[AsyncSession, None]:
    engine = build_async_engine(test_settings.resolved_database_url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = build_session_factory(engine)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.fixture
async def api_client(
    test_settings: Settings,
    db_session: AsyncSession,
    artifact_store: ArtifactStore,
) -> AsyncGenerator[AsyncClient, None]:
    app = create_app()

    async def _override_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_settings] = lambda: test_settings
    app.dependency_overrides[get_db_session] = _override_db
    app.dependency_overrides[get_artifact_store] = lambda: artifact_store

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
