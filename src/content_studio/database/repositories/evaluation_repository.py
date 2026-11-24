from collections.abc import Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from content_studio.database.models.evaluation import Evaluation


class EvaluationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        project_id: str,
        evaluator: str,
        evaluation_prompt_version: str,
        weights_json: dict[str, float],
        dimension_scores_json: dict[str, float],
        overall_score: float,
        feedback: str,
        latency_cost_summary_json: dict[str, Any],
        model: str | None = None,
    ) -> Evaluation:
        record = Evaluation(
            project_id=project_id,
            evaluator=evaluator,
            model=model,
            evaluation_prompt_version=evaluation_prompt_version,
            weights_json=weights_json,
            dimension_scores_json=dimension_scores_json,
            overall_score=overall_score,
            feedback=feedback,
            latency_cost_summary_json=latency_cost_summary_json,
            human_review_required=True,
        )
        self._session.add(record)
        await self._session.commit()
        await self._session.refresh(record)
        return record

    async def list_for_project(self, project_id: str) -> Sequence[Evaluation]:
        stmt = (
            select(Evaluation)
            .where(Evaluation.project_id == project_id)
            .order_by(Evaluation.evaluated_at.desc())
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()
