import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from content_studio.database.models.enums import SceneVisualType
from content_studio.database.session import Base

if TYPE_CHECKING:
    from content_studio.database.models.project import Project


def _utc_now() -> datetime:
    return datetime.now(UTC)


class Scene(Base):
    __tablename__ = "scenes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    script_version_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("script_versions.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    run_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("workflow_runs.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    scene_number: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    estimated_duration_seconds: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    narration: Mapped[str] = mapped_column(Text, nullable=False)
    on_screen_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    visual_type: Mapped[str] = mapped_column(
        String(50), default=SceneVisualType.FACE_CAM.value, index=True, nullable=False
    )
    asset_requirements_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, default=list, nullable=False
    )
    camera_or_screen_instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    transition_instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    related_script_section: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, onupdate=_utc_now, nullable=False
    )

    project: Mapped["Project"] = relationship(back_populates="scenes")
