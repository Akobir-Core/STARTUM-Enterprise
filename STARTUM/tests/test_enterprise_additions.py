from __future__ import annotations

import hashlib
import os
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "backend" / "startum.db"
EDU_SCHEMA = ROOT / "backend" / "database" / "education_schema.sql"


class EnterpriseAdditionTests(unittest.TestCase):
    def test_schema_v6_applies_to_a_copy_without_changing_existing_records(self):
        self.assertTrue(DB_PATH.is_file())
        before_hash = hashlib.sha256(DB_PATH.read_bytes()).hexdigest()
        with tempfile.TemporaryDirectory(prefix="startum-enterprise-migration-") as temp_dir:
            copy_path = Path(temp_dir) / "startum-copy.sqlite3"
            shutil.copy2(DB_PATH, copy_path)
            connection = sqlite3.connect(copy_path)
            connection.execute("PRAGMA foreign_keys=ON")
            counts_before = {
                table: connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                for table in ("users", "admins", "courses", "applications")
            }
            connection.executescript(EDU_SCHEMA.read_text(encoding="utf-8"))

            def columns(table: str) -> set[str]:
                return {row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')}

            if "language_selected" not in columns("users"):
                connection.execute("ALTER TABLE users ADD COLUMN language_selected INTEGER NOT NULL DEFAULT 1")
            if "attachment_type" not in columns("homework_submissions"):
                connection.execute("ALTER TABLE homework_submissions ADD COLUMN attachment_type TEXT NOT NULL DEFAULT ''")
            resource_columns = columns("learning_resources")
            additions = (
                ("publication_status", "TEXT NOT NULL DEFAULT 'published'"),
                ("group_id", "INTEGER REFERENCES education_groups(id) ON DELETE SET NULL"),
                ("level", "TEXT NOT NULL DEFAULT ''"),
                ("file_name", "TEXT NOT NULL DEFAULT ''"),
                ("file_mime", "TEXT NOT NULL DEFAULT ''"),
                ("file_size", "INTEGER NOT NULL DEFAULT 0"),
            )
            for name, definition in additions:
                if name not in resource_columns:
                    connection.execute(f"ALTER TABLE learning_resources ADD COLUMN {name} {definition}")
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_learning_resources_publication "
                "ON learning_resources(publication_status,active,course_id)"
            )

            counts_after = {
                table: connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                for table in counts_before
            }
            self.assertEqual(counts_after, counts_before)
            new_tables = {
                row[0] for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            self.assertTrue({"academic_calendar_events", "user_notifications", "education_groups", "group_memberships"} <= new_tables)
            self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
            connection.close()
        self.assertEqual(hashlib.sha256(DB_PATH.read_bytes()).hexdigest(), before_hash)

    def test_protected_dark_mode_image_has_expected_sha256(self):
        image = ROOT / "frontend" / "assets" / "images" / "startum-aeline-student.jpg"
        self.assertTrue(image.is_file())
        digest = hashlib.sha256(image.read_bytes()).hexdigest()
        self.assertEqual(digest, "fbb43b62abaf5f393c82172e1ad29e9eeef2adc7d7aaf52b8d4652474d4832b5")

    def test_public_material_endpoints_enforce_publication_and_group_scope(self):
        api = (ROOT / "backend" / "api.py").read_text(encoding="utf-8")
        self.assertIn("r.publication_status='published'", api)
        self.assertIn("r.group_id IS NULL", api)
        self.assertIn("c.active=1", api)
        # Search and resource endpoints must not return Telegram's private file IDs.
        self.assertNotIn("telegram_file_id", api[api.index("async def public_learning_resources"):api.index("@app.get(\"/api/admin/resources\")")])

    def test_public_material_query_excludes_pending_and_group_scoped_rows_in_real_sqlite(self):
        before_hash = hashlib.sha256(DB_PATH.read_bytes()).hexdigest()
        with tempfile.TemporaryDirectory(prefix="startum-public-resource-scope-") as temp_dir:
            copy_path = Path(temp_dir) / "scope.sqlite3"
            shutil.copy2(DB_PATH, copy_path)
            con = sqlite3.connect(copy_path)
            con.row_factory = sqlite3.Row
            con.execute("PRAGMA foreign_keys=ON")
            con.executescript(EDU_SCHEMA.read_text(encoding="utf-8"))
            cols = {row[1] for row in con.execute("PRAGMA table_info(users)")}
            if "language_selected" not in cols:
                con.execute("ALTER TABLE users ADD COLUMN language_selected INTEGER NOT NULL DEFAULT 1")
            resource_cols = {row[1] for row in con.execute("PRAGMA table_info(learning_resources)")}
            additions = (
                ("publication_status", "TEXT NOT NULL DEFAULT 'published'"),
                ("group_id", "INTEGER REFERENCES education_groups(id) ON DELETE SET NULL"),
                ("level", "TEXT NOT NULL DEFAULT ''"),
                ("file_name", "TEXT NOT NULL DEFAULT ''"),
                ("file_mime", "TEXT NOT NULL DEFAULT ''"),
                ("file_size", "INTEGER NOT NULL DEFAULT 0"),
            )
            for col, definition in additions:
                if col not in resource_cols:
                    con.execute(f"ALTER TABLE learning_resources ADD COLUMN {col} {definition}")
            course = con.execute("SELECT id FROM courses WHERE active=1 ORDER BY id LIMIT 1").fetchone()
            self.assertIsNotNone(course)
            course_id = int(course["id"])
            now = "2026-11-05T12:00:00+00:00"
            group_cursor = con.execute(
                "INSERT INTO education_groups(name,course_id,schedule_text,invite_code,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                ("Private group", course_id, "", "PRIV-GROUP-TEST", 123456789, now, now),
            )
            group_id = int(group_cursor.lastrowid)
            common = ("book", course_id, "Material", "Description", "", "document", "TELEGRAM_FILE_SECRET", 123456789, "teacher", 1, now)
            con.execute(
                "INSERT INTO learning_resources(category,course_id,title,description,content,media_type,telegram_file_id,created_by_telegram_id,created_by_role,active,created_at,publication_status,group_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (*common, "published", None),
            )
            con.execute(
                "INSERT INTO learning_resources(category,course_id,title,description,content,media_type,telegram_file_id,created_by_telegram_id,created_by_role,active,created_at,publication_status,group_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (*common, "pending", None),
            )
            con.execute(
                "INSERT INTO learning_resources(category,course_id,title,description,content,media_type,telegram_file_id,created_by_telegram_id,created_by_role,active,created_at,publication_status,group_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (*common, "published", group_id),
            )
            sql = (
                "SELECT r.id,r.category,r.course_id,r.title,r.description,r.content,r.media_type,"
                "r.created_at,r.publication_status,r.level,r.file_name,r.file_mime,r.file_size,"
                "c.name_uz AS course_name,c.slug AS course_slug "
                "FROM learning_resources r JOIN courses c ON c.id=r.course_id "
                "WHERE r.course_id=? AND r.active=1 AND r.publication_status='published' "
                "AND r.group_id IS NULL AND c.active=1 ORDER BY r.id DESC LIMIT ?"
            )
            rows = con.execute(sql, (course_id, 100)).fetchall()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["title"], "Material")
            self.assertNotIn("telegram_file_id", rows[0].keys())
            self.assertEqual(con.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(con.execute("PRAGMA foreign_key_check").fetchall(), [])
            con.close()
        self.assertEqual(hashlib.sha256(DB_PATH.read_bytes()).hexdigest(), before_hash)

    def test_public_privacy_page_is_multilingual_and_pwa_cached_safely(self):
        html = (ROOT / "frontend" / "privacy.html").read_text(encoding="utf-8")
        index = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
        worker = (ROOT / "frontend" / "sw.js").read_text(encoding="utf-8")
        sitemap = (ROOT / "frontend" / "sitemap.xml").read_text(encoding="utf-8")
        for lang in ("uz", "ru", "en"):
            self.assertIn(f'data-panel="{lang}"', html)
        self.assertIn('href="privacy.html"', index)
        self.assertIn("'./privacy.html'", worker)
        self.assertIn("/privacy.html", sitemap)
        self.assertIn("automatically removed after 7 days", html)
        script = (ROOT / "frontend" / "script.js").read_text(encoding="utf-8")
        self.assertEqual(script.count('"form.privacyLink":'), 3)
        self.assertEqual(script.count('"footer.privacy":'), 3)
        self.assertIn('"sameAs": ["https://t.me/StartumEducation"]', index)
        robots = (ROOT / "frontend" / "robots.txt").read_text(encoding="utf-8")
        for private_prefix in ("/api", "/admin", "/auth", "/private", "/uploads"):
            self.assertIn(f"Disallow: {private_prefix}", robots)

    def test_public_search_has_real_filters_sort_and_pagination(self):
        api = (ROOT / "backend" / "api.py").read_text(encoding="utf-8")
        frontend = (ROOT / "frontend" / "script.js").read_text(encoding="utf-8")
        html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
        for value in ('"courses"', '"teachers"', '"materials"', '"newest"', '"az"', 'offset: int'):
            self.assertIn(value, api)
        self.assertIn('id="languagePickerMenu"', html)
        self.assertIn('data-language-option="en"', html)
        self.assertIn('id="subjectSearchSubmit"', html)
        self.assertIn('id="globalSearchKind"', html)
        self.assertIn('value="subjects"', html)
        self.assertIn('value="courses"', html)
        self.assertIn('id="globalSearchSort"', html)
        self.assertIn('data-filter="special"', html)
        self.assertIn("function applyCatalogFilters()", frontend)
        self.assertIn('timer = window.setTimeout(() => applyCatalogFilters(), 180)', frontend)
        self.assertIn('fetch(`${API_BASE_URL}/catalog`', frontend)
        self.assertIn('"created_at": c["created_at"]', api)
        self.assertIn('"active": c["active"]', api)
        self.assertNotIn('value="packages"', html)

    def test_pwa_never_caches_private_routes_or_uploads(self):
        worker = (ROOT / "frontend" / "sw.js").read_text(encoding="utf-8")
        self.assertIn("api|admin|auth|private|sessions?|uploads", worker)
        self.assertIn("isShellAsset", worker)
        self.assertIn("isPublicBrandAsset", worker)
        self.assertIn("User uploads and arbitrary media paths are network-only", worker)
        self.assertNotIn("caches.open('startum-private", worker)

    def test_security_sensitive_routes_have_server_side_role_guards(self):
        api = (ROOT / "backend" / "api.py").read_text(encoding="utf-8")
        self.assertIn('"/api/admin/diagnostics"', api)
        self.assertIn('"/api/admin/education/groups"', api)
        self.assertIn('"/api/admin/calendar"', api)
        self.assertIn('"/api/admin/export/{dataset}.csv"', api)
        self.assertIn('Depends(require_roles("ceo", "senior_admin"))', api)
        self.assertIn('dataset == "students"', api)
        self.assertIn('role_user["role"] != "ceo"', api)

    def test_bot_uses_one_polling_session_and_has_calendar_notification_search(self):
        main = (ROOT / "backend" / "main.py").read_text(encoding="utf-8")
        education = (ROOT / "backend" / "handlers" / "education.py").read_text(encoding="utf-8")
        user = (ROOT / "backend" / "handlers" / "user.py").read_text(encoding="utf-8")
        self.assertEqual(main.count("Bot(config.bot_token"), 1)
        self.assertEqual(main.count("dp.start_polling("), 1)
        self.assertIn('Command("calendar")', education)
        self.assertIn('Command("notifications")', education)
        self.assertIn("search_student_content", user)

    def test_multilingual_search_and_privacy_copy_exist_in_all_languages(self):
        script = (ROOT / "frontend" / "script.js").read_text(encoding="utf-8")
        self.assertEqual(script.count('"search.scope":'), 3)
        self.assertEqual(script.count('"search.sort":'), 3)
        self.assertEqual(script.count('"form.privacyNote":'), 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
