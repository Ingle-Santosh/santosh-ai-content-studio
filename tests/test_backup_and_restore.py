import json
import sqlite3
import zipfile
from pathlib import Path

import pytest

from content_studio.services.backup_service import (
    create_backup,
    restore_backup,
    verify_backup,
)


def _seed_sqlite(db_path: Path, value: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, label TEXT NOT NULL)")
        conn.execute("INSERT INTO items (label) VALUES (?)", (value,))
        conn.commit()
    finally:
        conn.close()


def _read_sqlite(db_path: Path) -> list[str]:
    conn = sqlite3.connect(db_path)
    try:
        return [row[0] for row in conn.execute("SELECT label FROM items").fetchall()]
    finally:
        conn.close()


def test_backup_verify_tamper_detection_and_restore(tmp_path: Path) -> None:
    source_data = tmp_path / "data"
    projects_dir = source_data / "projects" / "proj-1" / "03_script"
    projects_dir.mkdir(parents=True)

    _seed_sqlite(source_data / "content_studio.db", "primary-record")
    _seed_sqlite(source_data / "checkpoints.db", "checkpoint-record")
    script_file = projects_dir / "script_v1.md"
    script_file.write_text("# Hinglish Script\nNamaste engineers!\n", encoding="utf-8")

    backup_zip = tmp_path / "backups" / "studio_backup.zip"
    summary = create_backup(source_data, backup_zip)

    assert backup_zip.is_file()
    assert summary.file_count == 3
    assert set(summary.databases_included) == {"content_studio.db", "checkpoints.db"}

    verification = verify_backup(backup_zip)
    assert verification.is_valid is True
    assert verification.verified_files == 3
    assert verification.errors == []

    # Restore into clean target directory
    restored_dir = tmp_path / "restored_data"
    restore_result = restore_backup(backup_zip, restored_dir)
    assert restore_result.is_valid is True
    assert _read_sqlite(restored_dir / "content_studio.db") == ["primary-record"]
    assert _read_sqlite(restored_dir / "checkpoints.db") == ["checkpoint-record"]
    restored_script = restored_dir / "projects" / "proj-1" / "03_script" / "script_v1.md"
    assert restored_script.read_text(encoding="utf-8") == "# Hinglish Script\nNamaste engineers!\n"

    # Restoring again without overwrite=True must fail safely
    with pytest.raises(FileExistsError):
        restore_backup(backup_zip, restored_dir, overwrite=False)

    # Tamper with an archived artifact and verify checksum failure
    tampered_zip = tmp_path / "backups" / "tampered.zip"
    with (
        zipfile.ZipFile(backup_zip, "r") as zin,
        zipfile.ZipFile(tampered_zip, "w", compression=zipfile.ZIP_DEFLATED) as zout,
    ):
        for name in zin.namelist():
            if name == "projects/proj-1/03_script/script_v1.md":
                zout.writestr(name, b"TAMPERED CONTENT")
            else:
                zout.writestr(name, zin.read(name))

    tampered_check = verify_backup(tampered_zip)
    assert tampered_check.is_valid is False
    assert any("Checksum mismatch" in err for err in tampered_check.errors)

    with pytest.raises(ValueError, match="verification failed"):
        restore_backup(tampered_zip, tmp_path / "never_restored")


def test_backup_rejects_zip_slip_traversal(tmp_path: Path) -> None:
    malicious_zip = tmp_path / "zip_slip.zip"
    manifest = {
        "format_version": "1.0",
        "databases": [],
        "checksums": {"projects/../../evil.txt": "deadbeef"},
    }
    with zipfile.ZipFile(malicious_zip, "w") as zf:
        zf.writestr("backup_manifest.json", json.dumps(manifest))
        zf.writestr("projects/../../evil.txt", b"pwned")

    res = verify_backup(malicious_zip)
    assert res.is_valid is False
    assert any("Unsafe path" in err for err in res.errors)
