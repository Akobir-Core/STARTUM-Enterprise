"""Static guard regression tests for Telegram role-gated entry points.

These verify critical authorization branches exist in source. They do not replace
end-to-end aiogram callback tests, which require the Telegram runtime.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

class EducationAccessGuardTests(unittest.TestCase):
    def test_owner_assign_teacher_command_uses_owner_id_gate(self):
        source = (ROOT / "backend/handlers/education.py").read_text(encoding="utf-8")
        self.assertIn('if command_name == "owner_assign_teacher":', source)
        self.assertIn('permitted = await is_owner(db, actor_id)', source)

    def test_owner_router_checks_owner_identity_and_private_chat(self):
        source = (ROOT / "backend/handlers/education.py").read_text(encoding="utf-8")
        self.assertIn('async def _require_owner_callback', source)
        self.assertIn('if await is_owner(db, callback.from_user.id) and callback.message and chat_type == "private":', source)

    def test_teacher_database_assignment_rejects_existing_admin_records(self):
        source = (ROOT / "backend/database/education_methods.py").read_text(encoding="utf-8")
        self.assertIn('SELECT 1 FROM admins WHERE telegram_id=? LIMIT 1', source)

    def test_announcement_send_requires_private_authorized_actor(self):
        source = (ROOT / "backend/handlers/education.py").read_text(encoding="utf-8")
        self.assertIn('if not _is_private_callback(callback) or not await is_admin_actor(db, callback.from_user.id, ("ceo", "senior_admin")):', source)

    def test_education_cabinets_are_private_chat_only(self):
        source = (ROOT / "backend/handlers/education.py").read_text(encoding="utf-8")
        self.assertIn("class PrivateEducationChatMiddleware(BaseMiddleware):", source)
        self.assertIn("router.message.outer_middleware(PrivateEducationChatMiddleware())", source)
        self.assertIn("router.callback_query.outer_middleware(PrivateEducationChatMiddleware())", source)

    def test_admin_dashboard_callbacks_are_private_chat_only(self):
        source = (ROOT / "backend/handlers/admin.py").read_text(encoding="utf-8")
        start = source.index("async def _cb_admin(")
        end = source.index("@router.callback_query", start)
        self.assertIn("if not _is_private_callback(callback):", source[start:end])

    def test_admin_creation_uses_atomic_insert_not_role_upsert(self):
        handler = (ROOT / "backend/handlers/admin.py").read_text(encoding="utf-8")
        database = (ROOT / "backend/database/db.py").read_text(encoding="utf-8")
        self.assertIn("await db.create_telegram_admin(target_id, role, callback.from_user.id)", handler)
        start = database.index("async def create_telegram_admin(")
        end = database.index("async def set_telegram_admin_active(", start)
        method = database[start:end]
        self.assertIn("SELECT role FROM admins WHERE telegram_id=?", method)
        self.assertIn("INSERT INTO admins", method)
        self.assertNotIn("ON CONFLICT", method)

    def test_owner_backup_is_private_and_uses_verified_readonly_helper(self):
        source = (ROOT / "backend/handlers/education.py").read_text(encoding="utf-8")
        start = source.index("async def owner_backup_command(")
        end = source.index('@router.message(Command("owner"))', start)
        block = source[start:end]
        self.assertIn("is_owner_from_message(message)", block)
        self.assertIn('message.chat.type', block)
        self.assertIn("backup_database(Path(config.database_path), backup_path)", block)

if __name__ == "__main__":
    unittest.main(verbosity=2)
