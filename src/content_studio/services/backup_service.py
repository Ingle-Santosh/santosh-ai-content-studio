import json
import sqlite3
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from content_studio.utils.hashing import sha256_bytes


class BackupSummary(BaseModel):
    backup_path: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    file_count: int
    total_size_bytes: int
    databases_included: list[str] = Field(default_factory=list)


class BackupVerificationResult(BaseModel):
    backup_path: str
    is_valid: bool
    verified_files: int = 0
    errors: list[str] = Field(default_factory=list)


def _online_sqlite_snapshot(source_db: Path, target_db: Path) -> None:
    """Safely snapshot a SQLite database (including WAL journals) using SQLite backup API."""
    src = sqlite3.connect(source_db)
    dst = sqlite3.connect(target_db)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


def create_backup(data_dir: Path, output_zip_path: Path) -> BackupSummary:
    """Create a checksummed ZIP backup of SQLite databases and project artifacts."""
    resolved_data = data_dir.resolve()
    resolved_out = output_zip_path.resolve()
    resolved_out.parent.mkdir(parents=True, exist_ok=True)

    checksums: dict[str, str] = {}
    dbs_included: list[str] = []

    with (
        tempfile.TemporaryDirectory(prefix="studio_backup_") as tmp,
        zipfile.ZipFile(resolved_out, mode="w", compression=zipfile.ZIP_DEFLATED) as zf,
    ):
        tmp_dir = Path(tmp)

        for db_name in ("content_studio.db", "checkpoints.db"):
            db_path = resolved_data / db_name
            if db_path.is_file() and db_path.stat().st_size > 0:
                snap_path = tmp_dir / db_name
                _online_sqlite_snapshot(db_path, snap_path)
                raw = snap_path.read_bytes()
                arcname = f"db/{db_name}"
                zf.writestr(arcname, raw)
                checksums[arcname] = sha256_bytes(raw)
                dbs_included.append(db_name)

        projects_dir = resolved_data / "projects"
        if projects_dir.is_dir():
            for file_path in sorted(projects_dir.rglob("*")):
                if not file_path.is_file():
                    continue
                rel = file_path.relative_to(projects_dir).as_posix()
                arcname = f"projects/{rel}"
                raw = file_path.read_bytes()
                zf.writestr(arcname, raw)
                checksums[arcname] = sha256_bytes(raw)

        manifest = {
            "format_version": "1.0",
            "created_at": datetime.now(UTC).isoformat(),
            "databases": dbs_included,
            "checksums": checksums,
        }
        zf.writestr(
            "backup_manifest.json",
            json.dumps(manifest, indent=2, ensure_ascii=False).encode("utf-8"),
        )

    return BackupSummary(
        backup_path=str(resolved_out),
        file_count=len(checksums),
        total_size_bytes=resolved_out.stat().st_size,
        databases_included=dbs_included,
    )


def verify_backup(backup_zip_path: Path) -> BackupVerificationResult:
    """Verify backup ZIP structure, path safety, and SHA-256 checksums."""
    resolved = backup_zip_path.resolve()
    if not resolved.is_file():
        return BackupVerificationResult(
            backup_path=str(resolved),
            is_valid=False,
            errors=[f"Backup file does not exist: {resolved}"],
        )

    errors: list[str] = []
    verified = 0

    try:
        with zipfile.ZipFile(resolved, mode="r") as zf:
            names = set(zf.namelist())
            if "backup_manifest.json" not in names:
                return BackupVerificationResult(
                    backup_path=str(resolved),
                    is_valid=False,
                    errors=["Missing backup_manifest.json in archive."],
                )
            manifest = json.loads(zf.read("backup_manifest.json").decode("utf-8"))
            checksums = manifest.get("checksums") or {}

            for arcname, expected_sha in checksums.items():
                rel_path = Path(arcname)
                if rel_path.is_absolute() or ".." in rel_path.parts:
                    errors.append(f"Unsafe path in archive: {arcname!r}")
                    continue
                if arcname not in names:
                    errors.append(f"Missing archived file: {arcname}")
                    continue
                actual_sha = sha256_bytes(zf.read(arcname))
                if actual_sha != expected_sha:
                    errors.append(f"Checksum mismatch for {arcname}")
                else:
                    verified += 1
    except (zipfile.BadZipFile, ValueError, KeyError) as exc:
        errors.append(f"Invalid backup archive: {exc}")

    return BackupVerificationResult(
        backup_path=str(resolved),
        is_valid=len(errors) == 0,
        verified_files=verified,
        errors=errors,
    )


def restore_backup(
    backup_zip_path: Path,
    target_data_dir: Path,
    *,
    overwrite: bool = False,
) -> BackupVerificationResult:
    """Verify and restore SQLite databases and project artifacts safely into target_data_dir."""
    verification = verify_backup(backup_zip_path)
    if not verification.is_valid:
        raise ValueError("Backup verification failed: " + "; ".join(verification.errors))

    target_root = target_data_dir.resolve()
    if target_root.exists() and any(target_root.iterdir()) and not overwrite:
        raise FileExistsError(
            f"Target data directory {target_root} is not empty. Pass overwrite=True to replace."
        )
    target_root.mkdir(parents=True, exist_ok=True)
    (target_root / "projects").mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(backup_zip_path.resolve(), mode="r") as zf:
        manifest = json.loads(zf.read("backup_manifest.json").decode("utf-8"))
        for arcname in manifest.get("checksums", {}):
            rel_path = Path(arcname)
            if rel_path.is_absolute() or ".." in rel_path.parts:
                raise ValueError(f"Refusing to extract unsafe archive path: {arcname!r}")

            if arcname.startswith("db/"):
                dest = (target_root / rel_path.name).resolve()
            elif arcname.startswith("projects/"):
                sub_rel = Path(*rel_path.parts[1:])
                dest = (target_root / "projects" / sub_rel).resolve()
            else:
                continue

            if not dest.is_relative_to(target_root):
                raise ValueError(f"Extraction path escapes target directory: {arcname!r}")
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(zf.read(arcname))

    return verification
