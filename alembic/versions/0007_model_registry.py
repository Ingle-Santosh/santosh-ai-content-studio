"""Add registered_models table for the Model Registry.

Revision ID: 0007_model_registry
Revises: 0006_evaluations
Create Date: 2026-11-24 21:35:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_model_registry"
down_revision: str | Sequence[str] | None = "0006_evaluations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "registered_models",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("model_id", sa.String(length=180), nullable=False),
        sa.Column("base_url", sa.String(length=300), nullable=False),
        sa.Column("tier", sa.String(length=40), nullable=False),
        sa.Column("is_cloud", sa.Boolean(), nullable=False),
        sa.Column("input_cost_per_1m", sa.Float(), nullable=False),
        sa.Column("output_cost_per_1m", sa.Float(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index(
        "ix_registered_models_provider", "registered_models", ["provider"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_registered_models_provider", table_name="registered_models")
    op.drop_table("registered_models")
