"""Add claims, claim_sources, and competitor_videos tables.

Revision ID: 0004_fact_check_competitors
Revises: 0003_research_engine
Create Date: 2026-11-24 08:25:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_fact_check_competitors"
down_revision: str | Sequence[str] | None = "0003_research_engine"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "claims",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=True),
        sa.Column("finding_id", sa.String(length=36), nullable=True),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("verdict", sa.String(length=50), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("risk_level", sa.String(length=20), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("evidence_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["workflow_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["finding_id"], ["research_findings.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_claims_project_id", "claims", ["project_id"], unique=False)
    op.create_index("ix_claims_run_id", "claims", ["run_id"], unique=False)
    op.create_index("ix_claims_finding_id", "claims", ["finding_id"], unique=False)
    op.create_index("ix_claims_verdict", "claims", ["verdict"], unique=False)
    op.create_index("ix_claims_risk_level", "claims", ["risk_level"], unique=False)

    op.create_table(
        "claim_sources",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("claim_id", sa.String(length=36), nullable=False),
        sa.Column("source_id", sa.String(length=36), nullable=False),
        sa.Column("stance", sa.String(length=30), nullable=False),
        sa.Column("excerpt", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["claim_id"], ["claims.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("claim_id", "source_id", name="uq_claim_sources_claim_source"),
    )
    op.create_index("ix_claim_sources_claim_id", "claim_sources", ["claim_id"], unique=False)
    op.create_index("ix_claim_sources_source_id", "claim_sources", ["source_id"], unique=False)

    op.create_table(
        "competitor_videos",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("youtube_video_id", sa.String(length=32), nullable=False),
        sa.Column("url", sa.String(length=500), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("channel_name", sa.String(length=255), nullable=False),
        sa.Column("published_at", sa.String(length=50), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("view_count", sa.Integer(), nullable=True),
        sa.Column("like_count", sa.Integer(), nullable=True),
        sa.Column("comment_count", sa.Integer(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("topics_covered_json", sa.JSON(), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id", "youtube_video_id", name="uq_competitor_videos_project_yt_id"
        ),
    )
    op.create_index(
        "ix_competitor_videos_project_id", "competitor_videos", ["project_id"], unique=False
    )
    op.create_index(
        "ix_competitor_videos_youtube_video_id",
        "competitor_videos",
        ["youtube_video_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_competitor_videos_youtube_video_id", table_name="competitor_videos")
    op.drop_index("ix_competitor_videos_project_id", table_name="competitor_videos")
    op.drop_table("competitor_videos")

    op.drop_index("ix_claim_sources_source_id", table_name="claim_sources")
    op.drop_index("ix_claim_sources_claim_id", table_name="claim_sources")
    op.drop_table("claim_sources")

    op.drop_index("ix_claims_risk_level", table_name="claims")
    op.drop_index("ix_claims_verdict", table_name="claims")
    op.drop_index("ix_claims_finding_id", table_name="claims")
    op.drop_index("ix_claims_run_id", table_name="claims")
    op.drop_index("ix_claims_project_id", table_name="claims")
    op.drop_table("claims")
