from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from content_studio.database.models.approval import Approval
from content_studio.database.models.enums import ApprovalGate, ApprovalStatus


class ApprovalRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        project_id: str,
        gate: ApprovalGate | str,
        run_id: str | None = None,
        artifact_id: str | None = None,
        comments: str | None = None,
    ) -> Approval:
        gate_val = gate.value if isinstance(gate, ApprovalGate) else gate
        approval = Approval(
            project_id=project_id,
            run_id=run_id,
            artifact_id=artifact_id,
            gate=gate_val,
            status=ApprovalStatus.PENDING.value,
            comments=comments,
        )
        self._session.add(approval)
        await self._session.commit()
        await self._session.refresh(approval)
        return approval

    async def get_by_id(self, approval_id: str) -> Approval | None:
        return await self._session.get(Approval, approval_id)

    async def list_approvals(
        self,
        *,
        project_id: str | None = None,
        status: ApprovalStatus | str | None = None,
        gate: ApprovalGate | str | None = None,
        limit: int = 100,
    ) -> Sequence[Approval]:
        stmt = select(Approval).order_by(Approval.requested_at.desc())
        if project_id is not None:
            stmt = stmt.where(Approval.project_id == project_id)
        if status is not None:
            status_val = status.value if isinstance(status, ApprovalStatus) else status
            stmt = stmt.where(Approval.status == status_val)
        if gate is not None:
            gate_val = gate.value if isinstance(gate, ApprovalGate) else gate
            stmt = stmt.where(Approval.gate == gate_val)
        stmt = stmt.limit(limit)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def decide(
        self,
        approval: Approval,
        *,
        status: ApprovalStatus | str,
        reviewer: str | None = None,
        comments: str | None = None,
    ) -> Approval:
        now = datetime.now(UTC)
        approval.status = status.value if isinstance(status, ApprovalStatus) else status
        if reviewer is not None:
            approval.reviewer = reviewer
        if comments is not None:
            approval.comments = comments
        approval.decided_at = now
        approval.updated_at = now
        await self._session.commit()
        await self._session.refresh(approval)
        return approval
