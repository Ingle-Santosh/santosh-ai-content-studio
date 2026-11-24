import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from content_studio.database.session import Base

if TYPE_CHECKING:
    from content_studio.database.models.project import Project


def _utc_now() -> datetime:
    return datetime.now(UTC)


class Evaluation(Base):
    __tablename__ = "evaluations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    evaluator: Mapped[str] = mapped_column(String(80), nullable=False)
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    evaluation_prompt_version: Mapped[str] = mapped_column(
        String(40), default="v1.0", nullable=False
    )
    weights_json: Mapped[dict[str, float]] = mapped_column(JSON, default=dict, nullable=False)
    dimension_scores_json: Mapped[dict[str, float]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    overall_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    feedback: Mapped[str] = mapped_column(Text, default="", nullable=False)
    latency_cost_summary_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    human_review_required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    evaluated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, index=True, nullable=False
    )

    project: Mapped["Project"] = relationship(back_populates="evaluations")
