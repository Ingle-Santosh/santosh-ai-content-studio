import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from content_studio.database.session import Base

if TYPE_CHECKING:
    from content_studio.database.models.project import Project
    from content_studio.database.models.source import Source


def _utc_now() -> datetime:
    return datetime.now(UTC)


class ResearchDocument(Base):
    __tablename__ = "research_documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    source_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("sources.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    artifact_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("artifacts.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    author: Mapped[str | None] = mapped_column(String(255), nullable=True)
    published_date: Mapped[str | None] = mapped_column(String(50), nullable=True)
    language: Mapped[str | None] = mapped_column(String(20), nullable=True)
    word_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    content_checksum_sha256: Mapped[str | None] = mapped_column(
        String(64), index=True, nullable=True
    )
    excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    extraction_method: Mapped[str] = mapped_column(
        String(50), default="trafilatura", nullable=False
    )
    extraction_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, nullable=False
    )

    project: Mapped["Project"] = relationship(back_populates="research_documents")
    source: Mapped["Source"] = relationship(back_populates="documents")
