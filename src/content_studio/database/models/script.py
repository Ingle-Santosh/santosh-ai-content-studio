import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from content_studio.database.models.enums import ArtifactStatus, ScriptStatus
from content_studio.database.session import Base

if TYPE_CHECKING:
    from content_studio.database.models.project import Project


def _utc_now() -> datetime:
    return datetime.now(UTC)


class Script(Base):
    __tablename__ = "scripts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    current_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    approved_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(
        String(50), default=ScriptStatus.DRAFT.value, index=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, onupdate=_utc_now, nullable=False
    )

    project: Mapped["Project"] = relationship(back_populates="scripts")
    versions: Mapped[list["ScriptVersion"]] = relationship(
        back_populates="script",
        cascade="all, delete-orphan",
        order_by="ScriptVersion.version_number.desc()",
    )


class ScriptVersion(Base):
    __tablename__ = "script_versions"
    __table_args__ = (
        UniqueConstraint("script_id", "version_number", name="uq_script_versions_script_ver"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    script_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("scripts.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
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
    artifact_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("artifacts.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), default=ArtifactStatus.DRAFT.value, index=True, nullable=False
    )
    language: Mapped[str] = mapped_column(String(50), default="Hinglish", nullable=False)
    total_estimated_duration_seconds: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    word_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sections_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    validation_report_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    revision_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, nullable=False
    )

    script: Mapped["Script"] = relationship(back_populates="versions")
