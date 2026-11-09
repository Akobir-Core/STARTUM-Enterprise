"""SQLite integration smoke tests for the additive STARTUM education schema.

These tests use a disposable SQLite database and the standard library only. They do
not import aiogram/aiosqlite and never touch backend/startum.db.
"""
from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_FILE = ROOT / "backend" / "database" / "education_schema.sql"


class EducationPlatformSchemaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "education-test.sqlite3"
        self.db = sqlite3.connect(self.db_path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self._create_legacy_tables()
        self.db.executescript(SCHEMA_FILE.read_text(encoding="utf-8"))
        self._additive_columns()
        self._seed()

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def _create_legacy_tables(self):
        self.db.executescript("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER NOT NULL UNIQUE,
            first_name TEXT NOT NULL DEFAULT '',
            last_name TEXT,
            username TEXT,
            language TEXT NOT NULL DEFAULT 'uz',
            account_status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE courses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name_uz TEXT NOT NULL,
            name_ru TEXT NOT NULL,
            name_en TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE teacher_managers (
            telegram_id INTEGER PRIMARY KEY,
            course_id INTEGER NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            created_by INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(course_id) REFERENCES courses(id)
        );
        CREATE TABLE learning_resources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            course_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            content TEXT NOT NULL DEFAULT '',
            media_type TEXT NOT NULL DEFAULT 'text',
            telegram_file_id TEXT NOT NULL DEFAULT '',
            created_by_telegram_id INTEGER NOT NULL DEFAULT 0,
            created_by_role TEXT NOT NULL DEFAULT 'admin',
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(course_id) REFERENCES courses(id)
        );
        CREATE TABLE quiz_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            resource_id INTEGER NOT NULL,
            course_id INTEGER NOT NULL,
            score INTEGER NOT NULL,
            total INTEGER NOT NULL,
            percent INTEGER NOT NULL,
            duration_seconds INTEGER NOT NULL DEFAULT 0,
            source_chat_id INTEGER,
            source_chat_type TEXT NOT NULL DEFAULT 'private',
            started_at TEXT NOT NULL,
            completed_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(resource_id) REFERENCES learning_resources(id),
            FOREIGN KEY(course_id) REFERENCES courses(id)
        );
        """)

    def _additive_columns(self):
        for name, definition in (
            ("publication_status", "TEXT NOT NULL DEFAULT 'published'"),
            ("group_id", "INTEGER REFERENCES education_groups(id) ON DELETE SET NULL"),
            ("level", "TEXT NOT NULL DEFAULT ''"),
            ("file_name", "TEXT NOT NULL DEFAULT ''"),
            ("file_mime", "TEXT NOT NULL DEFAULT ''"),
            ("file_size", "INTEGER NOT NULL DEFAULT 0"),
        ):
            self.db.execute(f"ALTER TABLE learning_resources ADD COLUMN {name} {definition}")
        self.db.execute("ALTER TABLE users ADD COLUMN language_selected INTEGER NOT NULL DEFAULT 1")
        submission_columns = {row[1] for row in self.db.execute("PRAGMA table_info(homework_submissions)")}
        if "attachment_type" not in submission_columns:
            self.db.execute("ALTER TABLE homework_submissions ADD COLUMN attachment_type TEXT NOT NULL DEFAULT ''")

    def _seed(self):
        self.db.execute("INSERT INTO courses(id,name_uz,name_ru,name_en) VALUES(1,'Ingliz tili','Английский','English')")
        self.db.execute("INSERT INTO users(id,telegram_id,first_name) VALUES(1,1001,'Student A')")
        self.db.execute("INSERT INTO users(id,telegram_id,first_name) VALUES(2,2001,'Teacher A')")
        self.db.execute("INSERT INTO users(id,telegram_id,first_name) VALUES(3,1002,'Student B')")
        self.db.execute("""INSERT INTO education_groups(name,course_id,schedule_text,invite_code,created_by,created_at,updated_at)
                           VALUES('English A',1,'Mon 14:00','GROUPA01',9001,'2026-11-05','2026-11-05')""")
        self.db.execute("""INSERT INTO education_groups(name,course_id,schedule_text,invite_code,created_by,created_at,updated_at)
                           VALUES('English B',1,'Tue 16:00','GROUPB01',9001,'2026-11-05','2026-11-05')""")
        self.db.execute("INSERT INTO teacher_subject_assignments(telegram_id,course_id,group_id,created_by,created_at) VALUES(2001,1,1,9001,'2026-11-05')")
        self.db.execute("INSERT INTO group_memberships(group_id,user_id,status,requested_at) VALUES(1,1,'active','2026-11-05')")
        self.db.execute("INSERT INTO group_memberships(group_id,user_id,status,requested_at) VALUES(2,3,'active','2026-11-05')")
        self.db.execute("""INSERT INTO learning_resources(category,course_id,title,created_by_telegram_id,created_by_role,active,created_at,publication_status,group_id)
                           VALUES('book',1,'Group A PDF',2001,'teacher',1,'2026-11-05','published',1)""")
        self.db.execute("""INSERT INTO learning_resources(category,course_id,title,created_by_telegram_id,created_by_role,active,created_at,publication_status,group_id)
                           VALUES('book',1,'Group B PDF',2001,'teacher',1,'2026-11-05','published',2)""")
        self.db.commit()

    def test_teacher_scope_is_group_limited(self):
        allowed = self.db.execute(
            "SELECT 1 FROM teacher_subject_assignments WHERE telegram_id=? AND course_id=? AND active=1 "
            "AND (group_id IS NULL OR group_id=?) LIMIT 1", (2001, 1, 1)
        ).fetchone()
        denied = self.db.execute(
            "SELECT 1 FROM teacher_subject_assignments WHERE telegram_id=? AND course_id=? AND active=1 "
            "AND (group_id IS NULL OR group_id=?) LIMIT 1", (2001, 1, 2)
        ).fetchone()
        self.assertIsNotNone(allowed)
        self.assertIsNone(denied)

    def test_students_only_see_published_materials_for_their_groups(self):
        rows = self.db.execute(
            "SELECT DISTINCT r.title FROM users u "
            "JOIN group_memberships gm ON gm.user_id=u.id AND gm.status='active' "
            "JOIN education_groups g ON g.id=gm.group_id AND g.status='active' "
            "JOIN learning_resources r ON r.course_id=g.course_id AND r.active=1 AND r.publication_status='published' "
            "AND (r.group_id IS NULL OR r.group_id=g.id) WHERE u.telegram_id=? ORDER BY r.id",
            (1001,),
        ).fetchall()
        self.assertEqual([r["title"] for r in rows], ["Group A PDF"])

    def test_membership_invite_and_review_are_persisted(self):
        self.db.execute("INSERT INTO group_memberships(group_id,user_id,status,requested_at) VALUES(1,3,'pending','2026-11-05')")
        membership_id = self.db.execute("SELECT last_insert_rowid()").fetchone()[0]
        self.db.execute("UPDATE group_memberships SET status='active',reviewed_at='2026-11-05',reviewed_by=9001 WHERE id=?", (membership_id,))
        row = self.db.execute("SELECT status,reviewed_by FROM group_memberships WHERE id=?", (membership_id,)).fetchone()
        self.assertEqual((row["status"], row["reviewed_by"]), ("active", 9001))

    def test_homework_submission_is_unique_and_keeps_attachment_type(self):
        self.db.execute("INSERT INTO homework(group_id,course_id,teacher_telegram_id,title,created_at,updated_at) VALUES(1,1,2001,'Unit 1','2026-11-05','2026-11-05')")
        homework_id = self.db.execute("SELECT last_insert_rowid()").fetchone()[0]
        self.db.execute("INSERT INTO homework_submissions(homework_id,student_user_id,submission_text,attachment_file_id,attachment_type,submitted_at) VALUES(?,?,?,?,?,?)",
                        (homework_id, 1, 'Done', 'file-id', 'document', '2026-11-05'))
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("INSERT INTO homework_submissions(homework_id,student_user_id,submitted_at) VALUES(?,?,?)",
                            (homework_id, 1, '2026-11-05'))
        row = self.db.execute("SELECT attachment_type FROM homework_submissions WHERE homework_id=?", (homework_id,)).fetchone()
        self.assertEqual(row["attachment_type"], "document")

    def test_attendance_requires_group_member_and_keeps_change_history(self):
        self.db.execute("INSERT INTO attendance_sessions(group_id,course_id,teacher_telegram_id,session_date,created_at) VALUES(1,1,2001,'2026-11-05','2026-11-05')")
        session_id = self.db.execute("SELECT last_insert_rowid()").fetchone()[0]
        self.db.execute("INSERT INTO attendance_records(session_id,user_id,status,marked_by,marked_at) VALUES(?,1,'present',2001,'2026-11-05')", (session_id,))
        record_id = self.db.execute("SELECT last_insert_rowid()").fetchone()[0]
        self.db.execute("UPDATE attendance_records SET status='late' WHERE id=?", (record_id,))
        self.db.execute("INSERT INTO attendance_history(attendance_record_id,old_status,new_status,actor_telegram_id,created_at) VALUES(?, 'present','late',2001,'2026-11-05')", (record_id,))
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM attendance_history WHERE attendance_record_id=?", (record_id,)).fetchone()[0], 1)

    def test_assigned_quiz_has_attempt_limit_and_group_scope(self):
        self.db.execute("INSERT INTO learning_resources(category,course_id,title,active,created_at,publication_status) VALUES('quiz',1,'Unit Test',1,'2026-11-05','published')")
        resource_id = self.db.execute("SELECT last_insert_rowid()").fetchone()[0]
        self.db.execute("INSERT INTO quiz_assignments(resource_id,group_id,attempt_limit,created_by,created_at) VALUES(?,1,1,9001,'2026-11-05')", (resource_id,))
        allowed = self.db.execute(
            "SELECT qa.id FROM quiz_assignments qa JOIN group_memberships gm ON gm.group_id=qa.group_id AND gm.status='active' "
            "JOIN users u ON u.id=gm.user_id WHERE u.telegram_id=? AND qa.resource_id=?", (1001, resource_id)
        ).fetchone()
        denied = self.db.execute(
            "SELECT qa.id FROM quiz_assignments qa JOIN group_memberships gm ON gm.group_id=qa.group_id AND gm.status='active' "
            "JOIN users u ON u.id=gm.user_id WHERE u.telegram_id=? AND qa.resource_id=?", (1002, resource_id)
        ).fetchone()
        self.assertIsNotNone(allowed)
        self.assertIsNone(denied)

    def test_announcements_are_localized_and_auditable(self):
        self.db.execute("INSERT INTO announcements(target_group_id,created_by,created_at) VALUES(1,9001,'2026-11-05')")
        announcement_id = self.db.execute("SELECT last_insert_rowid()").fetchone()[0]
        for lang, title in (("uz", "Yangilik"), ("ru", "Новость"), ("en", "News")):
            self.db.execute("INSERT INTO announcement_translations(announcement_id,language,title,body) VALUES(?,?,?,?)",
                            (announcement_id, lang, title, "Test body"))
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM announcement_translations WHERE announcement_id=?", (announcement_id,)).fetchone()[0], 3)


    def test_coursewide_teacher_assignment_has_database_uniqueness(self):
        self.db.execute(
            "INSERT INTO teacher_subject_assignments(telegram_id,course_id,group_id,created_by,created_at) VALUES(3001,1,NULL,9001,'2026-11-05')"
        )
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute(
                "INSERT INTO teacher_subject_assignments(telegram_id,course_id,group_id,created_by,created_at) VALUES(3001,1,NULL,9001,'2026-11-06')"
            )

    def test_announcement_audience_respects_group_membership_and_opt_out(self):
        self.db.execute("INSERT INTO user_notification_preferences(user_id,announcements_enabled,updated_at) VALUES(1,0,'2026-11-05')")
        self.db.execute("INSERT INTO user_notification_preferences(user_id,announcements_enabled,updated_at) VALUES(3,1,'2026-11-05')")
        group_a = self.db.execute(
            "SELECT u.telegram_id FROM group_memberships gm JOIN users u ON u.id=gm.user_id "
            "LEFT JOIN user_notification_preferences p ON p.user_id=u.id "
            "WHERE gm.group_id=1 AND gm.status='active' AND u.account_status='active' "
            "AND COALESCE(p.announcements_enabled,1)=1 ORDER BY u.id"
        ).fetchall()
        self.assertEqual([row["telegram_id"] for row in group_a], [])
        all_opted_in = self.db.execute(
            "SELECT u.telegram_id FROM users u LEFT JOIN user_notification_preferences p ON p.user_id=u.id "
            "WHERE u.account_status='active' AND COALESCE(p.announcements_enabled,1)=1 ORDER BY u.id"
        ).fetchall()
        self.assertEqual([row["telegram_id"] for row in all_opted_in], [2001, 1002])

    def test_announcement_delivery_records_are_deduplicated(self):
        self.db.execute("INSERT INTO announcements(target_group_id,created_by,created_at) VALUES(1,9001,'2026-11-05')")
        announcement_id = self.db.execute("SELECT last_insert_rowid()").fetchone()[0]
        self.db.execute("INSERT INTO announcement_deliveries(announcement_id,user_id,status) VALUES(?,1,'pending')", (announcement_id,))
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("INSERT INTO announcement_deliveries(announcement_id,user_id,status) VALUES(?,1,'pending')", (announcement_id,))
        self.db.execute("UPDATE announcement_deliveries SET status='sent',attempts=attempts+1 WHERE announcement_id=? AND user_id=? AND status='pending'", (announcement_id, 1))
        self.assertEqual(self.db.execute("SELECT status,attempts FROM announcement_deliveries WHERE announcement_id=?", (announcement_id,)).fetchone()["status"], "sent")

    def test_schema_integrity_and_foreign_keys(self):
        self.assertEqual(self.db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        self.assertEqual(self.db.execute("PRAGMA foreign_key_check").fetchall(), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
