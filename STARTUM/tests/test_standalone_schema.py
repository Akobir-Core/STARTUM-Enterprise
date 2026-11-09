from __future__ import annotations

import ast
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_SOURCE = ROOT / "backend" / "database" / "db.py"


def load_schema() -> str:
    tree = ast.parse(DB_SOURCE.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "SCHEMA" for target in node.targets
        ):
            value = ast.literal_eval(node.value)
            assert isinstance(value, str)
            return value
    raise AssertionError("SCHEMA constant was not found")


def fresh_database() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(load_schema())
    return conn


def test_standalone_schema_builds_all_application_and_learning_tables():
    conn = fresh_database()
    try:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        expected = {
            "users", "admins", "courses", "applications", "web_applications", "web_admin_users",
            "web_admin_sessions", "admin_audit", "teacher_managers", "learning_resources",
            "quiz_questions", "quiz_attempts", "user_favorites", "notification_outbox",
            "support_notification_outbox", "application_status_notification_outbox",
        }
        assert expected <= tables
        user_columns = {row[1] for row in conn.execute("PRAGMA table_info(users)")}
        assert {"telegram_id", "first_name", "last_name", "language"} <= user_columns
    finally:
        conn.close()


def test_resource_question_and_outbox_round_trip_with_foreign_keys():
    conn = fresh_database()
    try:
        now = "2026-10-18T00:00:00+00:00"
        course_id = conn.execute(
            "INSERT INTO courses(name_uz,name_ru,name_en,created_at) VALUES(?,?,?,?)",
            ("Ingliz tili", "Английский", "English", now),
        ).lastrowid
        resource_id = conn.execute(
            "INSERT INTO learning_resources(category,course_id,title,description,content,media_type,created_at) VALUES(?,?,?,?,?,?,?)",
            ("quiz", course_id, "A1 test", "Boshlang‘ich", "", "text", now),
        ).lastrowid
        conn.execute(
            "INSERT INTO quiz_questions(resource_id,position,question_text,options_json,correct_index,explanation,created_at) VALUES(?,?,?,?,?,?,?)",
            (resource_id, 1, "Choose a greeting", '["Hello", "Goodbye"]', 0, "Greeting for meeting", now),
        )
        app_id = conn.execute(
            "INSERT INTO web_applications(full_name,phone,telegram_username,course_id,created_at) VALUES(?,?,?,?,?)",
            ("Test User", "+998901234567", "@test_user", course_id, now),
        ).lastrowid
        conn.execute(
            "INSERT INTO notification_outbox(application_id,source,recipient_telegram_id,message_text,created_at) VALUES(?,?,?,?,?)",
            (app_id, "website", 12345, "New website application", now),
        )
        conn.commit()
        assert conn.execute("SELECT COUNT(*) FROM quiz_questions WHERE resource_id=?", (resource_id,)).fetchone()[0] == 1
        assert conn.execute("SELECT status FROM notification_outbox WHERE application_id=?", (app_id,)).fetchone()[0] == "pending"
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        conn.close()


def test_invalid_resource_categories_and_invalid_outbox_sources_are_rejected():
    conn = fresh_database()
    try:
        now = "2026-10-18T00:00:00+00:00"
        course_id = conn.execute(
            "INSERT INTO courses(name_uz,name_ru,name_en,created_at) VALUES(?,?,?,?)",
            ("Ingliz tili", "Английский", "English", now),
        ).lastrowid
        try:
            conn.execute(
                "INSERT INTO learning_resources(category,course_id,title,created_at) VALUES(?,?,?,?)",
                ("unknown", course_id, "Invalid", now),
            )
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("Unknown learning-resource category was accepted")
        try:
            conn.execute(
                "INSERT INTO notification_outbox(application_id,source,recipient_telegram_id,message_text,created_at) VALUES(?,?,?,?,?)",
                (1, "unknown", 12345, "invalid source", now),
            )
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("Unknown notification source was accepted")
    finally:
        conn.close()


def test_notification_admin_query_joins_application_and_course_and_retry_resets_failed_row():
    conn = fresh_database()
    try:
        now = "2026-10-18T00:00:00+00:00"
        course_id = conn.execute(
            "INSERT INTO courses(name_uz,name_ru,name_en,created_at) VALUES(?,?,?,?)",
            ("Ingliz tili", "Английский", "English", now),
        ).lastrowid
        user_id = conn.execute(
            "INSERT INTO users(telegram_id,first_name,created_at,updated_at) VALUES(?,?,?,?)",
            (70001, "Bot User", now, now),
        ).lastrowid
        bot_app_id = conn.execute(
            "INSERT INTO applications(user_id,full_name,phone,course_id,created_at) VALUES(?,?,?,?,?)",
            (user_id, "Bot User", "+998901234567", course_id, now),
        ).lastrowid
        web_app_id = conn.execute(
            "INSERT INTO web_applications(full_name,phone,telegram_username,course_id,created_at) VALUES(?,?,?,?,?)",
            ("Website User", "+998901234568", "@website_user", course_id, now),
        ).lastrowid
        conn.execute(
            "INSERT INTO notification_outbox(application_id,source,recipient_telegram_id,message_text,status,attempts,last_error,created_at) VALUES(?,?,?,?,?,?,?,?)",
            (bot_app_id, "bot", 70001, "Bot application", "sent", 1, "", now),
        )
        failed_id = conn.execute(
            "INSERT INTO notification_outbox(application_id,source,recipient_telegram_id,message_text,status,attempts,last_error,created_at) VALUES(?,?,?,?,?,?,?,?)",
            (web_app_id, "website", 70002, "Website application", "failed", 12, "TelegramBadRequest", now),
        ).lastrowid
        rows = conn.execute(
            "SELECT n.id,n.source,COALESCE(w.full_name,a.full_name,'—') AS applicant,COALESCE(c.name_uz,'—') AS course_name "
            "FROM notification_outbox n "
            "LEFT JOIN web_applications w ON n.source='website' AND w.id=n.application_id "
            "LEFT JOIN applications a ON n.source='bot' AND a.id=n.application_id "
            "LEFT JOIN courses c ON c.id=COALESCE(w.course_id,a.course_id) "
            "ORDER BY n.id DESC LIMIT ?",
            (100,),
        ).fetchall()
        by_id = {row["id"]: row for row in rows}
        assert by_id[failed_id]["applicant"] == "Website User"
        assert by_id[failed_id]["course_name"] == "Ingliz tili"
        bot_row = next(row for row in rows if row["source"] == "bot")
        assert bot_row["applicant"] == "Bot User"

        changed = conn.execute(
            "UPDATE notification_outbox SET status='pending',attempts=0,last_error='' WHERE id=? AND status IN ('pending','failed')",
            (failed_id,),
        ).rowcount
        conn.commit()
        assert changed == 1
        retried = conn.execute("SELECT status,attempts,last_error FROM notification_outbox WHERE id=?", (failed_id,)).fetchone()
        assert tuple(retried) == ("pending", 0, "")
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        conn.close()


def test_quiz_attempt_and_favorite_rows_round_trip():
    conn = fresh_database()
    try:
        now = "2026-10-18T00:00:00+00:00"
        course_id = conn.execute(
            "INSERT INTO courses(name_uz,name_ru,name_en,created_at) VALUES(?,?,?,?)",
            ("Ingliz tili", "Английский", "English", now),
        ).lastrowid
        user_id = conn.execute(
            "INSERT INTO users(telegram_id,first_name,created_at,updated_at) VALUES(?,?,?,?)",
            (777001, "Test Student", now, now),
        ).lastrowid
        resource_id = conn.execute(
            "INSERT INTO learning_resources(category,course_id,title,created_at) VALUES(?,?,?,?)",
            ("quiz", course_id, "A1 quiz", now),
        ).lastrowid
        conn.execute(
            "INSERT INTO quiz_attempts(user_id,resource_id,course_id,score,total,percent,duration_seconds,source_chat_id,source_chat_type,started_at,completed_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (user_id, resource_id, course_id, 4, 5, 80, 42, 777001, "private", now, now),
        )
        conn.execute(
            "INSERT INTO user_favorites(user_id,resource_id,created_at) VALUES(?,?,?)",
            (user_id, resource_id, now),
        )
        conn.commit()
        result = conn.execute(
            "SELECT qa.score,qa.total,qa.percent,u.telegram_id,r.title,c.name_uz FROM quiz_attempts qa "
            "JOIN users u ON u.id=qa.user_id JOIN learning_resources r ON r.id=qa.resource_id "
            "JOIN courses c ON c.id=qa.course_id"
        ).fetchone()
        assert tuple(result) == (4, 5, 80, 777001, "A1 quiz", "Ingliz tili")
        assert conn.execute("SELECT COUNT(*) FROM user_favorites WHERE user_id=?", (user_id,)).fetchone()[0] == 1
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        conn.close()


def test_support_notification_outbox_retries_and_is_unique_per_message_and_admin():
    conn = fresh_database()
    try:
        now = "2026-10-18T00:00:00+00:00"
        user_id = conn.execute(
            "INSERT INTO users(telegram_id,first_name,created_at,updated_at) VALUES(?,?,?,?)",
            (70123, "Support User", now, now),
        ).lastrowid
        message_id = conn.execute(
            "INSERT INTO messages(user_id,topic,message_text,created_at) VALUES(?,?,?,?)",
            (user_id, "savol", "Kurs haqida savol", now),
        ).lastrowid
        values = (message_id, 80123, "New support message", now)
        conn.execute(
            "INSERT INTO support_notification_outbox(message_id,recipient_telegram_id,message_text,created_at) VALUES(?,?,?,?)",
            values,
        )
        conn.execute(
            "INSERT OR IGNORE INTO support_notification_outbox(message_id,recipient_telegram_id,message_text,created_at) VALUES(?,?,?,?)",
            values,
        )
        conn.commit()
        rows = conn.execute(
            "SELECT status,attempts FROM support_notification_outbox WHERE message_id=? AND recipient_telegram_id=?",
            (message_id, 80123),
        ).fetchall()
        assert len(rows) == 1
        assert tuple(rows[0]) == ("pending", 0)
        conn.execute(
            "UPDATE support_notification_outbox SET status='pending',attempts=attempts+1,last_error=? WHERE message_id=?",
            ("TelegramNetworkError", message_id),
        )
        conn.commit()
        retry = conn.execute(
            "SELECT attempts,last_error FROM support_notification_outbox WHERE message_id=?",
            (message_id,),
        ).fetchone()
        assert tuple(retry) == (1, "TelegramNetworkError")
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        conn.close()


def test_application_status_outbox_accepts_only_valid_statuses_and_retains_retry_state():
    conn = fresh_database()
    try:
        now = "2026-11-01T00:00:00+00:00"
        cursor = conn.execute(
            "INSERT INTO application_status_notification_outbox"
            "(source,application_id,recipient_telegram_id,status_name,message_text,created_at) "
            "VALUES(?,?,?,?,?,?)",
            ("bot", 12, 70001, "accepted", "Ariza qabul qilindi", now),
        )
        notification_id = cursor.lastrowid
        conn.execute(
            "UPDATE application_status_notification_outbox "
            "SET delivery_status='pending',attempts=1,last_error='TimeoutError' WHERE id=?",
            (notification_id,),
        )
        row = conn.execute(
            "SELECT source,application_id,status_name,delivery_status,attempts,last_error "
            "FROM application_status_notification_outbox WHERE id=?",
            (notification_id,),
        ).fetchone()
        assert tuple(row) == ("bot", 12, "accepted", "pending", 1, "TimeoutError")
        try:
            conn.execute(
                "INSERT INTO application_status_notification_outbox"
                "(source,application_id,recipient_telegram_id,status_name,message_text,created_at) "
                "VALUES(?,?,?,?,?,?)",
                ("bot", 13, 70001, "unknown", "invalid", now),
            )
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("Invalid application status was accepted")
    finally:
        conn.close()
