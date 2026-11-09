from __future__ import annotations

import ast
from datetime import datetime, timezone
from pathlib import Path
import unittest

from backend.database.education_methods import EducationDatabaseMixin

ROOT = Path(__file__).resolve().parents[1]


class _ReminderDatabase(EducationDatabaseMixin):
    def __init__(self):
        self.notifications: list[dict] = []

    async def fetchall(self, query: str, params=()):
        if "FROM academic_calendar_events" in query:
            return [{
                "id": 41,
                "title_uz": "Matematika darsi",
                "title_ru": "Урок математики",
                "title_en": "Mathematics lesson",
                "starts_at": "2026-11-09T12:00:00+00:00",
                "target_group_id": None,
            }]
        if "FROM users u LEFT JOIN user_notification_preferences" in query:
            return [{"telegram_id": 123456, "language": "uz"}]
        raise AssertionError(f"Unexpected query in reminder test: {query}")

    async def create_user_notification(self, telegram_id: int, **kwargs):
        self.notifications.append({"telegram_id": telegram_id, **kwargs})
        return True


class EducationMethodRegressionTests(unittest.IsolatedAsyncioTestCase):
    async def test_24_hour_calendar_reminder_runs_and_creates_localized_notification(self):
        db = _ReminderDatabase()
        now = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)

        created = await db.queue_due_calendar_reminders(now=now)

        self.assertEqual(created, 1)
        self.assertEqual(len(db.notifications), 1)
        self.assertEqual(db.notifications[0]["telegram_id"], 123456)
        self.assertEqual(db.notifications[0]["dedupe_key"], "calendar:41:24h")
        self.assertIn("24 soatdan keyin", db.notifications[0]["body"])


    def test_notification_worker_keeps_traceback_for_unexpected_queue_failures(self):
        path = ROOT / "backend" / "main.py"
        source = path.read_text(encoding="utf-8")
        worker = source.split("async def _notification_retry_worker(", 1)[1].split(
            "async def _run_bot_session(", 1
        )[0]
        self.assertIn("logging.getLogger(__name__).exception(", worker)
        self.assertIn("except Exception:\n            # Keep the exception traceback", worker)

    def test_education_router_defines_its_own_private_callback_guard(self):
        path = ROOT / "backend" / "handlers" / "education.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        definitions = [
            node for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "_is_private_callback"
        ]
        self.assertEqual(len(definitions), 1)
        self.assertEqual(sum(1 for _ in ast.walk(tree) if isinstance(_, ast.Name) and _.id == "_is_private_callback"), 3)
        function_source = ast.get_source_segment(path.read_text(encoding="utf-8"), definitions[0]) or ""
        self.assertIn("return False", function_source)
        self.assertIn('== "private"', function_source)


if __name__ == "__main__":
    unittest.main()
