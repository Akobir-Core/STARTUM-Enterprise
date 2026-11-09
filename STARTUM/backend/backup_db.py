"""Create and verify a consistent online backup of the STARTUM SQLite database.

The source database is opened read-only; the live database is never replaced or edited.
"""
from __future__ import annotations

import argparse
import os
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import sys

BACKEND_DIR = Path(__file__).resolve().parent


def resolve_database_path(value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else (BACKEND_DIR / path).resolve()


def backup_database(source_path: Path, output_path: Path) -> Path:
    if not source_path.is_file():
        raise FileNotFoundError(f"SQLite bazasi topilmadi: {source_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.resolve() == source_path.resolve():
        raise ValueError("Backup fayli manba bazasi bilan bir xil bo‘lishi mumkin emas.")
    if output_path.exists():
        raise FileExistsError(f"Backup fayli allaqachon mavjud: {output_path}")

    source_uri = f"file:{source_path.as_posix()}?mode=ro"
    source = sqlite3.connect(source_uri, uri=True, timeout=10)
    destination = sqlite3.connect(output_path, timeout=10)
    try:
        integrity = source.execute("PRAGMA integrity_check").fetchone()
        if not integrity or integrity[0] != "ok":
            raise sqlite3.DatabaseError(f"Manba bazasi integrity_check xatosi: {integrity!r}")
        source.backup(destination)
        destination.commit()
        copied_integrity = destination.execute("PRAGMA integrity_check").fetchone()
        if not copied_integrity or copied_integrity[0] != "ok":
            raise sqlite3.DatabaseError(f"Backup integrity_check xatosi: {copied_integrity!r}")
    except Exception:
        destination.close()
        source.close()
        output_path.unlink(missing_ok=True)
        raise
    else:
        destination.close()
        source.close()
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(description="STARTUM SQLite bazasining xavfsiz online backup nusxasini yaratish.")
    parser.add_argument(
        "--database",
        default=os.getenv("DATABASE_PATH", "startum.db"),
        help="Manba SQLite yo‘li (default: DATABASE_PATH yoki backend/startum.db)",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Backup chiqish yo‘li (ixtiyoriy; default: backend/backups ichida vaqt belgisi bilan).",
    )
    args = parser.parse_args()
    source = resolve_database_path(args.database)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = Path(args.output).expanduser() if args.output else BACKEND_DIR / "backups" / f"startum_{stamp}.sqlite3"
    if not output.is_absolute():
        output = (BACKEND_DIR / output).resolve()

    try:
        result = backup_database(source, output)
    except (OSError, ValueError, sqlite3.Error) as exc:
        print(f"Backup bajarilmadi: {exc}", file=sys.stderr)
        return 1

    print(f"Backup tayyor: {result}")
    print(f"Hajmi: {result.stat().st_size:,} bayt")
    print("Integrity check: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
