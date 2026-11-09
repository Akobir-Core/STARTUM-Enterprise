from __future__ import annotations

import os
import subprocess
import sys
import textwrap
import unittest


class ApiRuntimeStubTests(unittest.TestCase):
    def test_public_search_and_material_routes_with_fake_async_db(self):
        script = textwrap.dedent(r'''
            import asyncio, os, sys, types
            from pathlib import Path
            backend = Path.cwd() / "backend"
            sys.path.insert(0, str(backend))
            fake_aiosqlite = types.ModuleType("aiosqlite")
            fake_aiosqlite.connect = lambda *args, **kwargs: None
            sys.modules["aiosqlite"] = fake_aiosqlite
            from fastapi.testclient import TestClient
            import api

            class FakeDB:
                CURRENT_SCHEMA_VERSION = 7
                def __init__(self): self.queries = []; self.role = "ceo"
                async def fetchone(self, sql, params=()):
                    self.queries.append((sql, params))
                    if "PRAGMA quick_check" in sql: return {0: "ok"}
                    if "COUNT(*)" in sql: return {"count": 1}
                    return {"id": 1}
                async def fetchall(self, sql, params=()):
                    self.queries.append((sql, params))
                    if "FROM courses WHERE" in sql:
                        return [{"id": 1, "slug": "math", "kind": "subject", "name_uz": "Matematika", "name_ru": "Математика", "name_en": "Mathematics", "description_uz": "Fan", "description_ru": "Предмет", "description_en": "Subject", "icon": "📘", "active": 1, "created_at": "2026-01-01T00:00:00+00:00"}]
                    if "FROM teachers WHERE" in sql:
                        return [{"id": 2, "full_name": "Ali Teacher", "subject": "English", "experience": "5 yil", "bio": "Teacher bio", "created_at": "2026-02-01T00:00:00+00:00"}]
                    if "FROM learning_resources r JOIN courses" in sql:
                        return [{"id": 3, "title": "Public PDF", "description": "Approved", "category": "book", "media_type": "document", "created_at": "2026-03-01T00:00:00+00:00", "course_id": 1}]
                    return []
                async def courses(self):
                    return [{"id": 1, "slug": "math", "kind": "subject", "name_uz": "Matematika", "name_ru": "Математика", "name_en": "Mathematics", "description_uz": "Fan", "description_ru": "Предмет", "description_en": "Subject", "icon": "📘", "active": 1, "created_at": "2026-01-01T00:00:00+00:00"}]
                async def teachers(self): return []
                async def calendar_events(self, **kwargs): return []
                async def notification_counts(self): return {"pending": 0, "failed": 0}
                async def web_admin_session_active(self, token_hash, username): return True
                async def web_admin(self, username):
                    return {"username": username, "active": 1, "role": self.role, "telegram_id": 123456789}
                async def education_groups(self, **kwargs): return []
                async def create_education_group(self, name, course_id, schedule_text, created_by):
                    return {"id": 99, "name": name, "course_id": course_id, "invite_code": "GROUP123"}
                async def create_calendar_event(self, **kwargs): return 88
                async def write_admin_audit(self, *args, **kwargs): return None

            api.db = FakeDB()
            api.app.state.database_initialized = True
            with TestClient(api.app) as client:
                health = client.get("/api/health")
                assert health.status_code == 200 and health.json()["status"] == "ok"
                catalogue = client.get("/api/catalog")
                assert catalogue.status_code == 200
                catalogue_course = catalogue.json()["courses"][0]
                assert catalogue_course["name_uz"] == "Matematika"
                assert catalogue_course["active"] == 1
                assert catalogue_course["created_at"] == "2026-01-01T00:00:00+00:00"
                resources = client.get("/api/resources?course_id=1")
                assert resources.status_code == 200
                assert resources.json()["total"] == 1
                resource_sql = next(sql for sql, _ in api.db.queries if "FROM learning_resources r JOIN courses" in sql)
                assert "publication_status='published'" in resource_sql
                assert "r.group_id IS NULL" in resource_sql
                assert "telegram_file_id" not in resource_sql
                result = client.get("/api/search?q=ma&kind=all&language=uz&sort=az&limit=10&offset=0")
                assert result.status_code == 200
                payload = result.json()
                assert payload["sort"] == "az"
                assert {item["type"] for item in payload["items"]} == {"course", "teacher", "material"}
                assert payload["items"][0]["title"] == "Ali Teacher" or payload["items"][0]["title"] == "Matematika" or payload["items"][0]["title"] == "Public PDF"
                calendar = client.get("/api/calendar?language=uz")
                assert calendar.status_code == 200 and calendar.json()["timezone"] == "Asia/Tashkent"
                # Admin operations require a valid session and server-side role.
                denied = client.get("/api/admin/calendar")
                assert denied.status_code == 401
                client.cookies.set(api.ADMIN_COOKIE, api._make_admin_cookie("test-admin"))
                diagnostics = client.get("/api/admin/diagnostics")
                assert diagnostics.status_code == 200 and diagnostics.json()["schema_version"] == 7
                groups = client.get("/api/admin/education/groups")
                assert groups.status_code == 200
                created_group = client.post("/api/admin/education/groups", headers={"X-STARTUM-Admin": "1"}, json={"name":"Test group","course_id":1,"schedule_text":"Tue 16:00"})
                assert created_group.status_code == 201 and created_group.json()["invite_code"] == "GROUP123"
                new_event = client.post("/api/admin/calendar", headers={"X-STARTUM-Admin": "1"}, json={
                    "titles":{"uz":"Tadbir","ru":"Событие","en":"Event"},
                    "descriptions":{"uz":"","ru":"","en":""}, "category":"event",
                    "starts_at":"2026-12-01T10:00:00+05:00", "ends_at":None, "location":"", "target_group_id":None,
                    "status":"draft", "reminder_24h":True
                })
                assert new_event.status_code == 201 and new_event.json()["id"] == 88
                student_export = client.get("/api/admin/export/students.csv")
                assert student_export.status_code == 200
                api.db.role = "senior_admin"
                restricted_export = client.get("/api/admin/export/students.csv")
                assert restricted_export.status_code == 403
            print("FastAPI public/admin route runtime stubs: PASS")
        ''')
        env = os.environ.copy()
        env.update({
            "BOT_TOKEN": "1234567890:TEST_ONLY_NOT_A_REAL_TOKEN",
            "CEO_OWNER_ID": "123456789",
            "OWNER_TELEGRAM_ID": "987654321",
            "DATABASE_PATH": "test-runtime.sqlite3",
            "WEB_ADMIN_USERNAME": "test-admin",
            "WEB_ADMIN_PASSWORD_HASH": "pbkdf2_sha256$120000$salt$" + "0" * 64,
            "ADMIN_SESSION_SECRET": "test-only-secret-that-is-long-enough-0123456789",
            "APP_ENV": "test",
            "ADMIN_COOKIE_SECURE": "false",
        })
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=PathLikeProject(),
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, msg=result.stdout + "\n" + result.stderr)
        self.assertIn("FastAPI public/admin route runtime stubs: PASS", result.stdout)


def PathLikeProject():
    from pathlib import Path
    return Path(__file__).resolve().parents[1]


if __name__ == "__main__":
    unittest.main(verbosity=2)
