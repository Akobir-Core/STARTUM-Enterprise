from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from backup_db import backup_database  # noqa: E402


class BackupDatabaseTests(unittest.TestCase):
    def test_readonly_backup_preserves_source_and_is_integrity_checked(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "startum.sqlite3"
            output = Path(tmp) / "backups" / "startum-copy.sqlite3"
            with sqlite3.connect(source) as connection:
                connection.executescript("CREATE TABLE users(id INTEGER PRIMARY KEY, name TEXT); INSERT INTO users VALUES(1,'Student');")
            source_bytes_before = source.read_bytes()
            result = backup_database(source, output)
            self.assertTrue(result.is_file())
            self.assertEqual(source.read_bytes(), source_bytes_before)
            with sqlite3.connect(output) as backup:
                self.assertEqual(backup.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                self.assertEqual(backup.execute("SELECT * FROM users").fetchall(), [(1, "Student")])

    def test_backup_rejects_overwriting_the_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "startum.sqlite3"
            with sqlite3.connect(source) as connection:
                connection.execute("CREATE TABLE t(id INTEGER)")
            with self.assertRaises(ValueError):
                backup_database(source, source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
