from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from content_studio.config.settings import Settings, settings
from content_studio.database.repositories import (
    AgentRunRepository,
    ApprovalRepository,
    ArtifactRepository,
    ChannelGuidelineRepository,
    ProjectRepository,
    RunRepository,
    UsageRepository,
)
from content_studio.database.session import get_db_session
from content_studio.services import (
    ApprovalService,
    ArtifactService,
    ChannelGuidelineService,
)
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


def get_approval_repository(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ApprovalRepository:
    return ApprovalRepository(session)


def get_guideline_repository(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ChannelGuidelineRepository:
    return ChannelGuidelineRepository(session)


def get_agent_run_repository(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AgentRunRepository:
    return AgentRunRepository(session)


def get_artifact_service(
    project_repo: Annotated[ProjectRepository, Depends(get_project_repository)],
    artifact_repo: Annotated[ArtifactRepository, Depends(get_artifact_repository)],
    store: Annotated[ArtifactStore, Depends(get_artifact_store)],
) -> ArtifactService:
    return ArtifactService(
        project_repo=project_repo,
        artifact_repo=artifact_repo,
        store=store,
    )


def get_guideline_service(
    repo: Annotated[ChannelGuidelineRepository, Depends(get_guideline_repository)],
) -> ChannelGuidelineService:
    return ChannelGuidelineService(repo)


def get_approval_service(
    project_repo: Annotated[ProjectRepository, Depends(get_project_repository)],
    approval_repo: Annotated[ApprovalRepository, Depends(get_approval_repository)],
    artifact_repo: Annotated[ArtifactRepository, Depends(get_artifact_repository)],
) -> ApprovalService:
    return ApprovalService(
        project_repo=project_repo,
        approval_repo=approval_repo,
        artifact_repo=artifact_repo,
    )
