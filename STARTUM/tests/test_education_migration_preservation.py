from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DB = ROOT / "backend" / "startum.db"
EDUCATION_SCHEMA = ROOT / "backend" / "database" / "education_schema.sql"


class EducationMigrationPreservationTests(unittest.TestCase):
    def test_additive_education_schema_preserves_existing_rows(self):
        self.assertTrue(SOURCE_DB.is_file())
        self.assertTrue(EDUCATION_SCHEMA.is_file())
        fd, temp_path = tempfile.mkstemp(suffix=".sqlite3")
        os.close(fd)
        try:
            shutil.copy2(SOURCE_DB, temp_path)
            connection = sqlite3.connect(temp_path)
            connection.execute("PRAGMA foreign_keys=ON")
            baseline = {
                table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in ("users", "admins", "courses", "applications")
            }
            connection.executescript(EDUCATION_SCHEMA.read_text(encoding="utf-8"))

            def columns(table: str) -> set[str]:
                return {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}

            additions = {
                "users": [("language_selected", "INTEGER NOT NULL DEFAULT 1")],
                "learning_resources": [
                    ("publication_status", "TEXT NOT NULL DEFAULT 'published'"),
                    ("group_id", "INTEGER REFERENCES education_groups(id) ON DELETE SET NULL"),
                    ("level", "TEXT NOT NULL DEFAULT ''"),
                    ("file_name", "TEXT NOT NULL DEFAULT ''"),
                    ("file_mime", "TEXT NOT NULL DEFAULT ''"),
                    ("file_size", "INTEGER NOT NULL DEFAULT 0"),
                ],
                "homework_submissions": [("attachment_type", "TEXT NOT NULL DEFAULT ''")],
            }
            for table, table_additions in additions.items():
                existing = columns(table)
                for name, definition in table_additions:
                    if name not in existing:
                        connection.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")

            after = {
                table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in baseline
            }
            self.assertEqual(after, baseline)
            self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
            new_tables = connection.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name IN "
                "('education_groups','teacher_subject_assignments','group_memberships','homework',"
                "'homework_submissions','attendance_sessions','attendance_records','quiz_assignments',"
                "'announcements','announcement_translations','announcement_deliveries','student_certificates',"
                "'education_audit_log','academic_calendar_events','user_notifications')"
            ).fetchone()[0]
            self.assertEqual(new_tables, 15)
            connection.close()
        finally:
            Path(temp_path).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
