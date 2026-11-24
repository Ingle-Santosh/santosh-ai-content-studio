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
    }.issubset(tables_at_head)

    command.downgrade(alembic_cfg, "0003_research_engine")
    tables_at_0003 = _list_tables(db_path)
    assert {"sources", "research_documents", "research_findings"}.issubset(tables_at_0003)
    assert "claims" not in tables_at_0003
    assert "claim_sources" not in tables_at_0003
    assert "competitor_videos" not in tables_at_0003

    command.downgrade(alembic_cfg, "0001_initial_schema")
    tables_at_0001 = _list_tables(db_path)
    assert {"projects", "workflow_runs", "artifacts", "llm_usage_logs"}.issubset(tables_at_0001)
    assert "approvals" not in tables_at_0001

    command.upgrade(alembic_cfg, "head")
    assert {"claims", "claim_sources", "competitor_videos"}.issubset(_list_tables(db_path))
