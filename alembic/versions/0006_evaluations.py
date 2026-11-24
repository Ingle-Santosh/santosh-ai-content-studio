"""Add evaluations table for 7-dimension project quality scoring.

Revision ID: 0006_evaluations
Revises: 0005_scripts_and_storyboard
Create Date: 2026-11-24 17:05:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_evaluations"
down_revision: str | Sequence[str] | None = "0005_scripts_and_storyboard"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "evaluations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("evaluator", sa.String(length=80), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=True),
        sa.Column("evaluation_prompt_version", sa.String(length=40), nullable=False),
        sa.Column("weights_json", sa.JSON(), nullable=False),
        sa.Column("dimension_scores_json", sa.JSON(), nullable=False),
        sa.Column("overall_score", sa.Float(), nullable=False),
        sa.Column("feedback", sa.Text(), nullable=False),
        sa.Column("latency_cost_summary_json", sa.JSON(), nullable=False),
        sa.Column("human_review_required", sa.Boolean(), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_evaluations_project_id", "evaluations", ["project_id"], unique=False)
    op.create_index("ix_evaluations_evaluated_at", "evaluations", ["evaluated_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_evaluations_evaluated_at", table_name="evaluations")
    op.drop_index("ix_evaluations_project_id", table_name="evaluations")
    op.drop_table("evaluations")
