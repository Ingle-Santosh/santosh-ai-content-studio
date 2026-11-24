from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from content_studio.database.models.llm_usage_log import LLMUsageLog


class UsageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        project_id: str,
        provider: str,
        model: str,
        node_name: str,
        run_id: str | None = None,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        estimated_cost_usd: float = 0.0,
        latency_ms: int = 0,
    ) -> LLMUsageLog:
        entry = LLMUsageLog(
            project_id=project_id,
            run_id=run_id,
            provider=provider,
            model=model,
            node_name=node_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            estimated_cost_usd=estimated_cost_usd,
            latency_ms=latency_ms,
        )
        self._session.add(entry)
        await self._session.commit()
        await self._session.refresh(entry)
        return entry

    async def list_for_project(self, project_id: str) -> Sequence[LLMUsageLog]:
        stmt = (
            select(LLMUsageLog)
            .where(LLMUsageLog.project_id == project_id)
            .order_by(LLMUsageLog.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def total_spend_for_project(self, project_id: str) -> float:
        stmt = select(func.coalesce(func.sum(LLMUsageLog.estimated_cost_usd), 0.0)).where(
            LLMUsageLog.project_id == project_id
        )
        result = await self._session.execute(stmt)
        return float(result.scalar() or 0.0)

    async def total_spend_all(self) -> float:
        stmt = select(func.coalesce(func.sum(LLMUsageLog.estimated_cost_usd), 0.0))
        result = await self._session.execute(stmt)
        return float(result.scalar() or 0.0)
