from pathlib import Path

import pytest

from content_studio.contracts.project import ProjectConfig
from content_studio.storage.artifact_store import PROJECT_STAGE_DIRS, ArtifactStore


def test_init_project_dirs_creates_stage_folders(tmp_path: Path) -> None:
    store = ArtifactStore(projects_dir=tmp_path / "projects")
    root = store.init_project_dirs("proj-123")

    assert root.is_dir()
    for stage in PROJECT_STAGE_DIRS:
        assert (root / stage).is_dir()


def test_write_and_read_text_and_json(tmp_path: Path) -> None:
    store = ArtifactStore(projects_dir=tmp_path / "projects")
    store.init_project_dirs("proj-123")

    saved_md = store.write_text("proj-123", "01_research/brief.md", "# Research Brief\n")
    assert saved_md.relative_path == "01_research/brief.md"
    assert saved_md.size_bytes == len(b"# Research Brief\n")
    assert len(saved_md.checksum_sha256) == 64
    assert store.read_text("proj-123", "01_research/brief.md") == "# Research Brief\n"

    config = ProjectConfig(duration_minutes=20, language="Hinglish")
    saved_json = store.write_json("proj-123", "02_outline/config.json", config)
    assert store.exists("proj-123", saved_json.relative_path)
    assert '"duration_minutes": 20' in store.read_text("proj-123", saved_json.relative_path)


def test_path_traversal_is_blocked(tmp_path: Path) -> None:
    store = ArtifactStore(projects_dir=tmp_path / "projects")
    store.init_project_dirs("proj-123")

    with pytest.raises(ValueError, match="escapes project directory"):
        store.write_text("proj-123", "../escape.txt", "bad")

    with pytest.raises(ValueError, match="must be relative"):
        store.resolve_artifact_path("proj-123", tmp_path / "abs.txt")

    with pytest.raises(ValueError, match="Invalid project_id"):
        store.project_dir("../evil")


@pytest.mark.asyncio
async def test_async_wrappers_and_delete(tmp_path: Path) -> None:
    store = ArtifactStore(projects_dir=tmp_path / "projects")
    root = await store.ainit_project_dirs("proj-async")
    await store.awrite_text("proj-async", "03_script/teleprompter.md", "Namaste devs!")
    content = await store.aread_text("proj-async", "03_script/teleprompter.md")
    assert content == "Namaste devs!"

    await store.adelete_project_dir("proj-async")
    assert not root.exists()
