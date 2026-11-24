from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from content_studio.database.models.enums import ProjectStatus
from content_studio.database.models.project import Project


class ProjectRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        title: str,
        topic: str,
        config: dict[str, Any] | None = None,
        budget_usd: float = 0.0,
    ) -> Project:
        project = Project(
            title=title,
            topic=topic,
            status=ProjectStatus.CREATED.value,
            config=config or {},
            budget_usd=budget_usd,
        )
        self._session.add(project)
        await self._session.commit()
        await self._session.refresh(project)
        return project

    async def get_by_id(self, project_id: str) -> Project | None:
        return await self._session.get(Project, project_id)

    async def list_projects(
        self,
        *,
        status: ProjectStatus | str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[Project]:
        stmt = select(Project).order_by(Project.created_at.desc())
        if status is not None:
            status_val = status.value if isinstance(status, ProjectStatus) else status
            stmt = stmt.where(Project.status == status_val)
        stmt = stmt.limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def update(
        self,
        project: Project,
        *,
        title: str | None = None,
        topic: str | None = None,
        status: ProjectStatus | str | None = None,
        current_stage: str | None = None,
        config: dict[str, Any] | None = None,
        budget_usd: float | None = None,
        spent_usd: float | None = None,
        error_message: str | None = None,
    ) -> Project:
        if title is not None:
            project.title = title
        if topic is not None:
            project.topic = topic
        if status is not None:
            project.status = status.value if isinstance(status, ProjectStatus) else status
        if current_stage is not None:
            project.current_stage = current_stage
        if config is not None:
            project.config = config
        if budget_usd is not None:
            project.budget_usd = budget_usd
        if spent_usd is not None:
            project.spent_usd = spent_usd
        if error_message is not None:
            project.error_message = error_message or None

        project.updated_at = datetime.now(UTC)
        await self._session.commit()
        await self._session.refresh(project)
        return project

    async def delete(self, project: Project) -> None:
        await self._session.delete(project)
        await self._session.commit()
