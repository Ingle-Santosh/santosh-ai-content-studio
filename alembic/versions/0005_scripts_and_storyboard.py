"""Add scripts, script_versions, and scenes tables.

Revision ID: 0005_scripts_and_storyboard
Revises: 0004_fact_check_competitors
Create Date: 2026-11-24 08:45:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_scripts_and_storyboard"
down_revision: str | Sequence[str] | None = "0004_fact_check_competitors"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "scripts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("current_version", sa.Integer(), nullable=False),
        sa.Column("approved_version", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_scripts_project_id", "scripts", ["project_id"], unique=False)
    op.create_index("ix_scripts_status", "scripts", ["status"], unique=False)

    op.create_table(
        "script_versions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("script_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=True),
        sa.Column("artifact_id", sa.String(length=36), nullable=True),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("language", sa.String(length=50), nullable=False),
        sa.Column("total_estimated_duration_seconds", sa.Integer(), nullable=False),
        sa.Column("word_count", sa.Integer(), nullable=False),
        sa.Column("sections_json", sa.JSON(), nullable=False),
        sa.Column("validation_report_json", sa.JSON(), nullable=False),
        sa.Column("revision_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["script_id"], ["scripts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["workflow_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["artifact_id"], ["artifacts.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("script_id", "version_number", name="uq_script_versions_script_ver"),
    )
    op.create_index("ix_script_versions_script_id", "script_versions", ["script_id"], unique=False)
    op.create_index(
        "ix_script_versions_project_id", "script_versions", ["project_id"], unique=False
    )
    op.create_index("ix_script_versions_run_id", "script_versions", ["run_id"], unique=False)
    op.create_index(
        "ix_script_versions_artifact_id", "script_versions", ["artifact_id"], unique=False
    )
    op.create_index("ix_script_versions_status", "script_versions", ["status"], unique=False)

    op.create_table(
        "scenes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("script_version_id", sa.String(length=36), nullable=True),
        sa.Column("run_id", sa.String(length=36), nullable=True),
        sa.Column("scene_number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("estimated_duration_seconds", sa.Integer(), nullable=False),
        sa.Column("narration", sa.Text(), nullable=False),
        sa.Column("on_screen_text", sa.Text(), nullable=True),
        sa.Column("visual_type", sa.String(length=50), nullable=False),
        sa.Column("asset_requirements_json", sa.JSON(), nullable=False),
        sa.Column("camera_or_screen_instructions", sa.Text(), nullable=True),
        sa.Column("transition_instructions", sa.Text(), nullable=True),
        sa.Column("related_script_section", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["script_version_id"], ["script_versions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["run_id"], ["workflow_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_scenes_project_id", "scenes", ["project_id"], unique=False)
    op.create_index("ix_scenes_script_version_id", "scenes", ["script_version_id"], unique=False)
    op.create_index("ix_scenes_run_id", "scenes", ["run_id"], unique=False)
    op.create_index("ix_scenes_scene_number", "scenes", ["scene_number"], unique=False)
    op.create_index("ix_scenes_visual_type", "scenes", ["visual_type"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_scenes_visual_type", table_name="scenes")
    op.drop_index("ix_scenes_scene_number", table_name="scenes")
    op.drop_index("ix_scenes_run_id", table_name="scenes")
    op.drop_index("ix_scenes_script_version_id", table_name="scenes")
    op.drop_index("ix_scenes_project_id", table_name="scenes")
    op.drop_table("scenes")

    op.drop_index("ix_script_versions_status", table_name="script_versions")
    op.drop_index("ix_script_versions_artifact_id", table_name="script_versions")
    op.drop_index("ix_script_versions_run_id", table_name="script_versions")
    op.drop_index("ix_script_versions_project_id", table_name="script_versions")
    op.drop_index("ix_script_versions_script_id", table_name="script_versions")
    op.drop_table("script_versions")

    op.drop_index("ix_scripts_status", table_name="scripts")
    op.drop_index("ix_scripts_project_id", table_name="scripts")
    op.drop_table("scripts")
