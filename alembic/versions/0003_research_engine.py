"""Add sources, research_documents, and research_findings tables.

Revision ID: 0003_research_engine
Revises: 0002_shared_persistence
Create Date: 2026-11-24 08:10:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_research_engine"
down_revision: str | Sequence[str] | None = "0002_shared_persistence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sources",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("url", sa.String(length=1000), nullable=False),
        sa.Column("normalized_url", sa.String(length=1000), nullable=False),
        sa.Column("url_hash", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("domain", sa.String(length=255), nullable=False),
        sa.Column("snippet", sa.Text(), nullable=True),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "url_hash", name="uq_sources_project_url_hash"),
    )
    op.create_index("ix_sources_project_id", "sources", ["project_id"], unique=False)
    op.create_index("ix_sources_url_hash", "sources", ["url_hash"], unique=False)
    op.create_index("ix_sources_domain", "sources", ["domain"], unique=False)
    op.create_index("ix_sources_status", "sources", ["status"], unique=False)

    op.create_table(
        "research_documents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("source_id", sa.String(length=36), nullable=False),
        sa.Column("artifact_id", sa.String(length=36), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("author", sa.String(length=255), nullable=True),
        sa.Column("published_date", sa.String(length=50), nullable=True),
        sa.Column("language", sa.String(length=20), nullable=True),
        sa.Column("word_count", sa.Integer(), nullable=False),
        sa.Column("content_checksum_sha256", sa.String(length=64), nullable=True),
        sa.Column("excerpt", sa.Text(), nullable=True),
        sa.Column("extraction_method", sa.String(length=50), nullable=False),
        sa.Column("extraction_error", sa.Text(), nullable=True),
        sa.Column("extracted_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["artifact_id"], ["artifacts.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_research_documents_project_id", "research_documents", ["project_id"], unique=False
    )
    op.create_index(
        "ix_research_documents_source_id", "research_documents", ["source_id"], unique=False
    )
    op.create_index(
        "ix_research_documents_artifact_id", "research_documents", ["artifact_id"], unique=False
    )
    op.create_index(
        "ix_research_documents_content_checksum_sha256",
        "research_documents",
        ["content_checksum_sha256"],
        unique=False,
    )

    op.create_table(
        "research_findings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("source_id", sa.String(length=36), nullable=True),
        sa.Column("run_id", sa.String(length=36), nullable=True),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("source_urls_json", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("is_contradiction", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["run_id"], ["workflow_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_research_findings_project_id", "research_findings", ["project_id"], unique=False
    )
    op.create_index(
        "ix_research_findings_source_id", "research_findings", ["source_id"], unique=False
    )
    op.create_index("ix_research_findings_run_id", "research_findings", ["run_id"], unique=False)
    op.create_index(
        "ix_research_findings_category", "research_findings", ["category"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_research_findings_category", table_name="research_findings")
    op.drop_index("ix_research_findings_run_id", table_name="research_findings")
    op.drop_index("ix_research_findings_source_id", table_name="research_findings")
    op.drop_index("ix_research_findings_project_id", table_name="research_findings")
    op.drop_table("research_findings")

    op.drop_index("ix_research_documents_content_checksum_sha256", table_name="research_documents")
    op.drop_index("ix_research_documents_artifact_id", table_name="research_documents")
    op.drop_index("ix_research_documents_source_id", table_name="research_documents")
    op.drop_index("ix_research_documents_project_id", table_name="research_documents")
    op.drop_table("research_documents")

    op.drop_index("ix_sources_status", table_name="sources")
    op.drop_index("ix_sources_domain", table_name="sources")
    op.drop_index("ix_sources_url_hash", table_name="sources")
    op.drop_index("ix_sources_project_id", table_name="sources")
    op.drop_table("sources")
