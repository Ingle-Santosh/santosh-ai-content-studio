import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from content_studio.database.models.enums import EvidenceStance
from content_studio.database.session import Base

if TYPE_CHECKING:
    from content_studio.database.models.claim import Claim


def _utc_now() -> datetime:
    return datetime.now(UTC)


class ClaimSource(Base):
    __tablename__ = "claim_sources"
    __table_args__ = (
        UniqueConstraint("claim_id", "source_id", name="uq_claim_sources_claim_source"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    claim_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("claims.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    source_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("sources.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    stance: Mapped[str] = mapped_column(
        String(30), default=EvidenceStance.SUPPORTS.value, nullable=False
    )
    excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, nullable=False
    )

    claim: Mapped["Claim"] = relationship(back_populates="claim_sources")
