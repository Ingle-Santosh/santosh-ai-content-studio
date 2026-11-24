from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.evaluation import SystemMetricsResponse
from content_studio.database.models import Approval, LLMUsageLog, Project
from content_studio.database.models.enums import ApprovalStatus
from content_studio.database.session import get_db_session

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/metrics", response_model=SystemMetricsResponse)
async def get_system_metrics(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SystemMetricsResponse:
    status_rows = (
        await session.execute(
            select(Project.status, func.count(Project.id)).group_by(Project.status)
        )
    ).all()
    by_status = {str(status_val): int(cnt) for status_val, cnt in status_rows}
    total_projects = sum(by_status.values())

    pending_approvals = int(
        (
            await session.execute(
                select(func.count(Approval.id)).where(
                    Approval.status == ApprovalStatus.PENDING.value
                )
            )
        ).scalar()
        or 0
    )

    llm_row = (
        await session.execute(
            select(
                func.count(LLMUsageLog.id),
                func.coalesce(func.sum(LLMUsageLog.prompt_tokens), 0),
                func.coalesce(func.sum(LLMUsageLog.completion_tokens), 0),
                func.coalesce(func.sum(LLMUsageLog.estimated_cost_usd), 0.0),
                func.coalesce(func.avg(LLMUsageLog.latency_ms), 0.0),
            )
        )
    ).one()

    return SystemMetricsResponse(
        total_projects=total_projects,
        projects_by_status=by_status,
        pending_approvals=pending_approvals,
        total_llm_calls=int(llm_row[0] or 0),
        total_tokens=int(llm_row[1] or 0) + int(llm_row[2] or 0),
        total_estimated_cost_usd=round(float(llm_row[3] or 0.0), 6),
        avg_llm_latency_ms=round(float(llm_row[4] or 0.0), 2),
    )
