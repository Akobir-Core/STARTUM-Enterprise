from __future__ import annotations

import asyncio
import sqlite3
from types import SimpleNamespace

from database.db import Database


def test_legacy_database_is_backed_up_before_additive_migration_and_only_once(tmp_path):
    path = tmp_path / "legacy.sqlite3"
    connection = sqlite3.connect(path)
    connection.execute(
        """CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER NOT NULL UNIQUE,
            first_name TEXT NOT NULL DEFAULT '',
            last_name TEXT,
            username TEXT,
            language TEXT NOT NULL DEFAULT 'uz',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )"""
    )
    connection.execute(
        "INSERT INTO users(telegram_id,first_name,created_at,updated_at) VALUES(?,?,?,?)",
        (44556677, "Legacy student", "2025-01-01T00:00:00+00:00", "2025-01-01T00:00:00+00:00"),
    )
    connection.commit()
    connection.close()

    database = Database(path)
    asyncio.run(database.init(owner_id=123456789))

    backups = list((tmp_path / "backups").glob("legacy_pre_v*.sqlite3"))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as backup:
        assert backup.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        backup_columns = {row[1] for row in backup.execute("PRAGMA table_info(users)")}
        assert "account_status" not in backup_columns
        assert backup.execute("SELECT telegram_id,first_name FROM users").fetchone() == (44556677, "Legacy student")

    with sqlite3.connect(path) as upgraded:
        columns = {row[1] for row in upgraded.execute("PRAGMA table_info(users)")}
        assert {"account_status", "suspended_until"} <= columns
        assert upgraded.execute("SELECT telegram_id,first_name,account_status FROM users").fetchone() == (
            44556677, "Legacy student", "active"
        )
        assert upgraded.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] == Database.CURRENT_SCHEMA_VERSION

    asyncio.run(database.init(owner_id=123456789))
    assert len(list((tmp_path / "backups").glob("legacy_pre_v*.sqlite3"))) == 1


def test_quiz_session_resumes_after_reopening_database_and_completes_once(tmp_path):
    path = tmp_path / "quiz.sqlite3"
    database = Database(path)
    asyncio.run(database.init(owner_id=123456789))

    async def run_quiz_session():
        user, _ = await database.ensure_user(SimpleNamespace(
            id=44556678, first_name="Quiz", last_name="Student", username="quiz_student", language_code="en"
        ))
        course = await database.fetchone("SELECT id FROM courses WHERE kind='subject' ORDER BY id LIMIT 1")
        resource_id = await database.add_learning_resource(
            category="quiz", course_id=int(course["id"]), title="Restart-safe test",
            description="", content="", media_type="text", telegram_file_id="",
            created_by_telegram_id=123456789, created_by_role="ceo",
        )
        await database.add_quiz_question(resource_id, "First?", ["A", "B"], 0)
        await database.add_quiz_question(resource_id, "Second?", ["C", "D"], 1)
        session = await database.start_or_resume_quiz_session(
            telegram_id=44556678, user_id=int(user["id"]), resource_id=resource_id, question_total=2,
        )
        assert session["current_index"] == 0
        first = await database.advance_quiz_session(
            telegram_id=44556678, resource_id=resource_id, expected_index=0, correct=True,
        )
        assert first["score"] == 1 and first["current_index"] == 1

        restarted = Database(path)
        resumed = await restarted.quiz_session(44556678, resource_id)
        assert resumed["current_index"] == 1 and resumed["score"] == 1
        duplicate = await restarted.advance_quiz_session(
            telegram_id=44556678, resource_id=resource_id, expected_index=0, correct=True,
        )
        assert duplicate is None
        finished = await restarted.advance_quiz_session(
            telegram_id=44556678, resource_id=resource_id, expected_index=1, correct=False,
        )
        assert finished["current_index"] == 2 and finished["score"] == 1

        result = await restarted.complete_quiz_session(
            telegram_id=44556678, resource_id=resource_id,
            source_chat_id=44556678, source_chat_type="private",
        )
        assert result["score"] == 1 and result["total"] == 2 and result["percent"] == 50
        assert await restarted.quiz_session(44556678, resource_id) is None
        assert await restarted.complete_quiz_session(telegram_id=44556678, resource_id=resource_id) is None
        attempts = await restarted.quiz_attempts(limit=10, resource_id=resource_id)
        assert len(attempts) == 1 and attempts[0]["percent"] == 50

    asyncio.run(run_quiz_session())


def test_v2_application_status_upgrade_preserves_backup_outbox_and_records_history(tmp_path):
    path = tmp_path / "status-v2.sqlite3"
    database = Database(path)
    asyncio.run(database.init(owner_id=123456789))

    with sqlite3.connect(path) as connection:
        course_id = connection.execute("SELECT id FROM courses WHERE slug='math'").fetchone()[0]
        cursor = connection.execute(
            """INSERT INTO web_applications(
                full_name,phone,telegram_username,course_id,level,preferred_time,message,status,
                identity_provider,external_user_id,tracking_token_hash,created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            ("Legacy Applicant", "+998901234567", "@legacy", course_id, "A1", "Morning", "Please call", "in_progress", "", "", "", "2025-02-01T10:00:00+00:00"),
        )
        application_id = int(cursor.lastrowid)
        connection.execute("DROP TABLE application_status_notification_outbox")
        connection.execute("""CREATE TABLE application_status_notification_outbox (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL CHECK(source IN ('website','bot')),
            application_id INTEGER NOT NULL,
            recipient_telegram_id INTEGER NOT NULL,
            status_name TEXT NOT NULL CHECK(status_name IN ('new','in_progress','accepted','closed')),
            message_text TEXT NOT NULL,
            delivery_status TEXT NOT NULL DEFAULT 'pending' CHECK(delivery_status IN ('pending','sent','failed')),
            attempts INTEGER NOT NULL DEFAULT 0,
            last_error TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            sent_at TEXT
        )""")
        connection.execute(
            "INSERT INTO application_status_notification_outbox(source,application_id,recipient_telegram_id,status_name,message_text,created_at) VALUES(?,?,?,?,?,?)",
            ("website", application_id, 44556677, "in_progress", "Legacy notice", "2025-02-01T10:01:00+00:00"),
        )
        connection.execute("CREATE INDEX idx_application_status_outbox_status ON application_status_notification_outbox(delivery_status,attempts,id)")
        connection.execute("UPDATE schema_migrations SET version=2")

    asyncio.run(database.init(owner_id=123456789))
    backups = list((tmp_path / "backups").glob(f"status-v2_pre_v{Database.CURRENT_SCHEMA_VERSION}_*.sqlite3"))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as backup:
        assert backup.execute("SELECT status FROM web_applications WHERE id=?", (application_id,)).fetchone()[0] == "in_progress"
        assert backup.execute("SELECT status_name FROM application_status_notification_outbox").fetchone()[0] == "in_progress"

    async def verify_upgrade():
        application = await database.web_application(application_id)
        assert application["status"] == "in_review"
        preserved = await database.fetchall(
            "SELECT status_name,message_text FROM application_status_notification_outbox WHERE application_id=?",
            (application_id,),
        )
        assert len(preserved) == 1 and preserved[0]["status_name"] == "in_progress"
        assert preserved[0]["message_text"] == "Legacy notice"

        await database.enqueue_application_status_notification(
            source="website", application_id=application_id, recipient_telegram_id=44556677,
            status="rejected", message_text="Rejected notice",
        )
        change = await database.change_application_status(
            "website", application_id, "contacted", actor="test-admin", ip_address="127.0.0.1",
        )
        assert change == {"old_status": "in_review", "new_status": "contacted"}
        history = await database.application_status_history("website", application_id)
        assert len(history) == 1
        assert history[0]["actor"] == "test-admin" and history[0]["ip_address"] == "127.0.0.1"
        assert history[0]["old_status"] == "in_review" and history[0]["new_status"] == "contacted"

    asyncio.run(verify_upgrade())
