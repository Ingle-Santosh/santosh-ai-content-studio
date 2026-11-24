import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, DateTime, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from content_studio.database.models.enums import ProjectStatus
from content_studio.database.session import Base

if TYPE_CHECKING:
    from content_studio.database.models.agent_run import AgentRun
    from content_studio.database.models.approval import Approval
    from content_studio.database.models.artifact import Artifact
    from content_studio.database.models.llm_usage_log import LLMUsageLog
    from content_studio.database.models.workflow_run import WorkflowRun


def _utc_now() -> datetime:
    return datetime.now(UTC)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    topic: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), default=ProjectStatus.CREATED.value, nullable=False
    )
    current_stage: Mapped[str | None] = mapped_column(String(50), nullable=True)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    budget_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    spent_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, onupdate=_utc_now, nullable=False
    )

    runs: Mapped[list["WorkflowRun"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    artifacts: Mapped[list["Artifact"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    usage_logs: Mapped[list["LLMUsageLog"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    approvals: Mapped[list["Approval"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    agent_runs: Mapped[list["AgentRun"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
