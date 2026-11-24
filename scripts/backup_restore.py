"""Backup, verify, and restore CLI for Santosh Analytics AI Content Studio."""

import argparse
from datetime import UTC, datetime
from pathlib import Path

from content_studio.config.settings import settings
from content_studio.services.backup_service import (
    create_backup,
    restore_backup,
    verify_backup,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backup, verify, and restore Content Studio SQLite DBs and artifacts."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_backup = sub.add_parser("backup", help="Create a verified ZIP backup of data/")
    p_backup.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Target ZIP path (defaults to ./backups/studio_backup_<timestamp>.zip)",
    )

    p_verify = sub.add_parser("verify", help="Verify SHA-256 checksums inside a backup ZIP")
    p_verify.add_argument("archive", type=Path, help="Path to backup ZIP")

    p_restore = sub.add_parser("restore", help="Restore a verified backup ZIP into a data dir")
    p_restore.add_argument("archive", type=Path, help="Path to backup ZIP")
    p_restore.add_argument(
        "--target",
        type=Path,
        default=settings.resolved_data_dir,
        help="Target data directory",
    )
    p_restore.add_argument(
        "--overwrite",
        action="store_true",
        help="Allow restoring into a non-empty target directory",
    )

    args = parser.parse_args()

    if args.command == "backup":
        stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        out_path = args.output or (settings.BASE_DIR / "backups" / f"studio_backup_{stamp}.zip")
        summary = create_backup(settings.resolved_data_dir, out_path)
        print(summary.model_dump_json(indent=2))
        return 0

    if args.command == "verify":
        result = verify_backup(args.archive)
        print(result.model_dump_json(indent=2))
        return 0 if result.is_valid else 1

    if args.command == "restore":
        result = restore_backup(args.archive, args.target, overwrite=args.overwrite)
        print(result.model_dump_json(indent=2))
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
