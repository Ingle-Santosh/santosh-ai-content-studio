from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from content_studio.config.settings import Settings, settings
from content_studio.database.repositories import (
    ArtifactRepository,
    ProjectRepository,
    RunRepository,
    UsageRepository,
)
from content_studio.database.session import get_db_session
from content_studio.storage.artifact_store import ArtifactStore


def get_settings() -> Settings:
    return settings


def get_artifact_store(
    app_settings: Annotated[Settings, Depends(get_settings)],
) -> ArtifactStore:
    return ArtifactStore(projects_dir=app_settings.resolved_projects_dir)


def get_project_repository(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ProjectRepository:
    return ProjectRepository(session)


def get_artifact_repository(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ArtifactRepository:
    return ArtifactRepository(session)


def get_run_repository(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> RunRepository:
    return RunRepository(session)


def get_usage_repository(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> UsageRepository:
    return UsageRepository(session)
