import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from content_studio.database.models.enums import ClaimVerdict, RiskLevel
from content_studio.database.session import Base

if TYPE_CHECKING:
    from content_studio.database.models.claim_source import ClaimSource
    from content_studio.database.models.project import Project


def _utc_now() -> datetime:
    return datetime.now(UTC)


class Claim(Base):
    __tablename__ = "claims"

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
    finding_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("research_findings.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    verdict: Mapped[str] = mapped_column(
        String(50), default=ClaimVerdict.UNCERTAIN.value, index=True, nullable=False
    )
    confidence: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    risk_level: Mapped[str] = mapped_column(
        String(20), default=RiskLevel.MEDIUM.value, index=True, nullable=False
    )
    rationale: Mapped[str] = mapped_column(Text, default="", nullable=False)
    evidence_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, onupdate=_utc_now, nullable=False
    )

    project: Mapped["Project"] = relationship(back_populates="claims")
    claim_sources: Mapped[list["ClaimSource"]] = relationship(
        back_populates="claim", cascade="all, delete-orphan"
    )
