import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Float, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from content_studio.database.session import Base


class RegisteredModel(Base):
    """User-registered LLM endpoint (local or cloud). API tokens live outside SQLite."""

    __tablename__ = "registered_models"
    __table_args__ = (Index("ix_registered_models_provider", "provider"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    model_id: Mapped[str] = mapped_column(String(180), nullable=False)
    base_url: Mapped[str] = mapped_column(String(300), nullable=False)
    tier: Mapped[str] = mapped_column(String(40), default="local_small", nullable=False)
    is_cloud: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    input_cost_per_1m: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    output_cost_per_1m: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )
