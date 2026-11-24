import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from content_studio.database.models.enums import AgentRunStatus
from content_studio.database.session import Base

if TYPE_CHECKING:
    from content_studio.database.models.project import Project


def _utc_now() -> datetime:
    return datetime.now(UTC)


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    run_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("workflow_runs.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    agent_name: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    stage: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), default=AgentRunStatus.PENDING.value, index=True, nullable=False
    )
    attempt: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    input_summary_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    output_summary_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped["Project"] = relationship(back_populates="agent_runs")
