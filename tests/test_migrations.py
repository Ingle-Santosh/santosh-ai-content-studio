import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config

from content_studio.config.settings import settings


def _list_tables(db_path: Path) -> set[str]:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        return {row[0] for row in rows}
    finally:
        conn.close()


def test_alembic_upgrade_and_downgrade_roundtrip(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "migration_test.db"
    db_url = f"sqlite+aiosqlite:///{db_path.as_posix()}"

    monkeypatch.setattr(settings, "DATABASE_URL", db_url)
    monkeypatch.setattr(settings, "DATA_DIR", tmp_path)
    monkeypatch.setattr(settings, "PROJECTS_DIR", tmp_path / "projects")

    alembic_cfg = Config(str(settings.BASE_DIR / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(settings.BASE_DIR / "alembic"))

    command.upgrade(alembic_cfg, "head")
    tables_at_head = _list_tables(db_path)
    assert {
        "alembic_version",
        "projects",
        "workflow_runs",
        "artifacts",
        "llm_usage_logs",
        "approvals",
        "channel_guidelines",
        "agent_runs",
        "sources",
        "research_documents",
        "research_findings",
        "claims",
        "claim_sources",
        "competitor_videos",
        "scripts",
        "script_versions",
        "scenes",
        "evaluations",
        "registered_models",
    }.issubset(tables_at_head)

    command.downgrade(alembic_cfg, "0006_evaluations")
    tables_at_0006 = _list_tables(db_path)
    assert "evaluations" in tables_at_0006
    assert "registered_models" not in tables_at_0006

    command.downgrade(alembic_cfg, "0005_scripts_and_storyboard")
    tables_at_0005 = _list_tables(db_path)
    assert {"scripts", "script_versions", "scenes"}.issubset(tables_at_0005)
    assert "evaluations" not in tables_at_0005

    command.downgrade(alembic_cfg, "0004_fact_check_competitors")
    tables_at_0004 = _list_tables(db_path)
    assert {"claims", "claim_sources", "competitor_videos"}.issubset(tables_at_0004)
    assert "scripts" not in tables_at_0004
    assert "script_versions" not in tables_at_0004
    assert "scenes" not in tables_at_0004

    command.downgrade(alembic_cfg, "0001_initial_schema")
    tables_at_0001 = _list_tables(db_path)
    assert {"projects", "workflow_runs", "artifacts", "llm_usage_logs"}.issubset(tables_at_0001)
    assert "approvals" not in tables_at_0001

    command.upgrade(alembic_cfg, "head")
    assert {"scripts", "script_versions", "scenes", "evaluations"}.issubset(_list_tables(db_path))
