from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from content_studio.database.models.agent_run import AgentRun
from content_studio.database.models.enums import AgentRunStatus


class AgentRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        project_id: str,
        agent_name: str,
        stage: str,
        run_id: str | None = None,
        status: AgentRunStatus | str = AgentRunStatus.RUNNING,
        attempt: int = 1,
        input_summary_json: dict[str, Any] | None = None,
    ) -> AgentRun:
        entry = AgentRun(
            project_id=project_id,
            run_id=run_id,
            agent_name=agent_name,
            stage=stage,
            status=status.value if isinstance(status, AgentRunStatus) else status,
            attempt=attempt,
            input_summary_json=input_summary_json or {},
        )
        self._session.add(entry)
        await self._session.commit()
        await self._session.refresh(entry)
        return entry

    async def get_by_id(self, agent_run_id: str) -> AgentRun | None:
        return await self._session.get(AgentRun, agent_run_id)

    async def list_for_project(
        self,
        project_id: str,
        *,
        run_id: str | None = None,
        agent_name: str | None = None,
    ) -> Sequence[AgentRun]:
        stmt = (
            select(AgentRun)
            .where(AgentRun.project_id == project_id)
            .order_by(AgentRun.started_at.desc())
        )
        if run_id is not None:
            stmt = stmt.where(AgentRun.run_id == run_id)
        if agent_name is not None:
            stmt = stmt.where(AgentRun.agent_name == agent_name)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def mark_finished(
        self,
        entry: AgentRun,
        *,
        status: AgentRunStatus | str,
        output_summary_json: dict[str, Any] | None = None,
        error_message: str | None = None,
        duration_ms: int | None = None,
    ) -> AgentRun:
        entry.status = status.value if isinstance(status, AgentRunStatus) else status
        if output_summary_json is not None:
            entry.output_summary_json = output_summary_json
        if error_message is not None:
            entry.error_message = error_message
        if duration_ms is not None:
            entry.duration_ms = duration_ms
        entry.completed_at = datetime.now(UTC)
        await self._session.commit()
        await self._session.refresh(entry)
        return entry
