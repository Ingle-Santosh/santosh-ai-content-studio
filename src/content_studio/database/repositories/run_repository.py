from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from content_studio.database.models.enums import RunStatus
from content_studio.database.models.workflow_run import WorkflowRun


class RunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        project_id: str,
        thread_id: str,
        status: RunStatus | str = RunStatus.PENDING,
        current_stage: str | None = None,
    ) -> WorkflowRun:
        run = WorkflowRun(
            project_id=project_id,
            thread_id=thread_id,
            status=status.value if isinstance(status, RunStatus) else status,
            current_stage=current_stage,
        )
        self._session.add(run)
        await self._session.commit()
        await self._session.refresh(run)
        return run

    async def get_by_id(self, run_id: str) -> WorkflowRun | None:
        return await self._session.get(WorkflowRun, run_id)

    async def get_by_thread_id(self, thread_id: str) -> WorkflowRun | None:
        stmt = select(WorkflowRun).where(WorkflowRun.thread_id == thread_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_project(self, project_id: str) -> Sequence[WorkflowRun]:
        stmt = (
            select(WorkflowRun)
            .where(WorkflowRun.project_id == project_id)
            .order_by(WorkflowRun.started_at.desc())
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def update_status(
        self,
        run: WorkflowRun,
        *,
        status: RunStatus | str,
        current_stage: str | None = None,
        error_message: str | None = None,
        mark_completed: bool = False,
    ) -> WorkflowRun:
        run.status = status.value if isinstance(status, RunStatus) else status
        if current_stage is not None:
            run.current_stage = current_stage
        if error_message is not None:
            run.error_message = error_message
        if mark_completed:
            run.completed_at = datetime.now(UTC)
        await self._session.commit()
        await self._session.refresh(run)
        return run
