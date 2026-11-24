import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from content_studio.database.session import Base

if TYPE_CHECKING:
    from content_studio.database.models.project import Project


def _utc_now() -> datetime:
    return datetime.now(UTC)


class CompetitorVideo(Base):
    __tablename__ = "competitor_videos"
    __table_args__ = (
        UniqueConstraint(
            "project_id", "youtube_video_id", name="uq_competitor_videos_project_yt_id"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    youtube_video_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    channel_name: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    published_at: Mapped[str | None] = mapped_column(String(50), nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    view_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    like_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    comment_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    topics_covered_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    provider: Mapped[str] = mapped_column(String(50), default="public_search", nullable=False)
    retrieved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, onupdate=_utc_now, nullable=False
    )

    project: Mapped["Project"] = relationship(back_populates="competitor_videos")
