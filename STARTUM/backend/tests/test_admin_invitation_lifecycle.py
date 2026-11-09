from __future__ import annotations

import asyncio
from types import SimpleNamespace

from admin_authorization import resolve_telegram_admin_role, resolve_web_admin_role
from database.db import Database


OWNER_ID = 991_000_001
NEW_ADMIN_ID = 991_000_002


def _run(coro):
    return asyncio.run(coro)


def test_bot_invitation_is_accepted_by_exact_telegram_user_and_survives_restart(tmp_path):
    async def scenario():
        db = Database(tmp_path / "invitation.sqlite3")
        await db.init(owner_id=OWNER_ID)
        await db.create_telegram_admin(NEW_ADMIN_ID, "senior_admin", OWNER_ID)

        pending = await db.fetchone(
            "SELECT telegram_id,role,active,pending_link,bot_invite_pending FROM admins WHERE telegram_id=?",
            (NEW_ADMIN_ID,),
        )
        assert int(pending["telegram_id"]) == NEW_ADMIN_ID
        assert pending["role"] == "senior_admin"
        assert pending["active"] == 0
        assert pending["pending_link"] == 1
        assert pending["bot_invite_pending"] == 1
        assert await db.admin_role(NEW_ADMIN_ID) is None

        role = await db.activate_telegram_admin_invitation(str(NEW_ADMIN_ID))
        assert role == "senior_admin"
        assert await db.admin_role(int(NEW_ADMIN_ID)) == "senior_admin"
        assert await resolve_telegram_admin_role(db, NEW_ADMIN_ID, OWNER_ID) == "senior_admin"

        # Invitation is one-shot and does not implicitly create a Website Admin login.
        assert await db.activate_telegram_admin_invitation(NEW_ADMIN_ID) is None
        assert await db.web_admin_by_telegram_id(NEW_ADMIN_ID) is None

        accepted = await db.fetchone(
            "SELECT active,pending_link,bot_invite_pending FROM admins WHERE telegram_id=?",
            (NEW_ADMIN_ID,),
        )
        assert accepted["active"] == 1
        assert accepted["pending_link"] == 1
        assert accepted["bot_invite_pending"] == 0

        # A normal application restart must preserve an accepted Bot-only admin.
        await db.init(owner_id=OWNER_ID)
        assert await db.admin_role(NEW_ADMIN_ID) == "senior_admin"

        audit = await db.fetchall(
            "SELECT action FROM admin_audit WHERE entity_id=? ORDER BY id",
            (NEW_ADMIN_ID,),
        )
        assert [row["action"] for row in audit].count("telegram_admin_created") == 1
        assert [row["action"] for row in audit].count("telegram_admin_invitation_accepted") == 1

    _run(scenario())


def test_website_admin_link_is_separate_and_requires_password_login_link_step(tmp_path):
    async def scenario():
        db = Database(tmp_path / "website-link.sqlite3")
        await db.init(owner_id=OWNER_ID)
        await db.create_telegram_admin(NEW_ADMIN_ID, "junior_admin", OWNER_ID)
        await db.activate_telegram_admin_invitation(NEW_ADMIN_ID)

        await db.create_web_admin(
            username="new-staff",
            password_hash="test-only-hash-not-a-real-password",
            role="junior_admin",
            created_by="bootstrap-owner",
            telegram_id=NEW_ADMIN_ID,
            created_by_telegram_id=OWNER_ID,
        )
        web_user = await db.web_admin("new-staff")
        assert web_user is not None
        assert int(web_user["active"]) == 1
        assert int(web_user["telegram_verified"]) == 0
        assert await resolve_web_admin_role(db, web_user, OWNER_ID) is None

        linked_telegram_id = await db.mark_telegram_admin_verified("new-staff")
        assert linked_telegram_id == NEW_ADMIN_ID
        web_user = await db.web_admin("new-staff")
        assert int(web_user["telegram_verified"]) == 1
        assert await resolve_web_admin_role(db, web_user, OWNER_ID) == "junior_admin"
        assert await db.admin_role(NEW_ADMIN_ID) == "junior_admin"

    _run(scenario())


def test_disabled_admin_loses_bot_and_website_access_then_owner_can_reinvite(tmp_path):
    async def scenario():
        db = Database(tmp_path / "revocation.sqlite3")
        await db.init(owner_id=OWNER_ID)
        await db.create_telegram_admin(NEW_ADMIN_ID, "senior_admin", OWNER_ID)
        await db.activate_telegram_admin_invitation(NEW_ADMIN_ID)
        await db.create_web_admin(
            username="reinvite-user",
            password_hash="test-only-hash-not-a-real-password",
            role="senior_admin",
            created_by="bootstrap-owner",
            telegram_id=NEW_ADMIN_ID,
            created_by_telegram_id=OWNER_ID,
        )
        await db.mark_telegram_admin_verified("reinvite-user")
        await db.create_web_admin_session("test-token-hash", "reinvite-user", 4_000_000_000, "127.0.0.1")

        assert await db.set_telegram_admin_active(NEW_ADMIN_ID, False) is True
        assert await db.admin_role(NEW_ADMIN_ID) is None
        assert await db.web_admin_session_active("test-token-hash", "reinvite-user") is False

        role = await db.reissue_telegram_admin_invitation(NEW_ADMIN_ID, OWNER_ID)
        assert role == "senior_admin"
        pending = await db.fetchone(
            "SELECT active,pending_link,bot_invite_pending FROM admins WHERE telegram_id=?",
            (NEW_ADMIN_ID,),
        )
        assert tuple(pending) == (0, 1, 1)
        web_user = await db.web_admin("reinvite-user")
        assert int(web_user["active"]) == 0
        assert int(web_user["telegram_verified"]) == 0

        # Duplicate reissue is rejected while the first invitation is still pending.
        try:
            await db.reissue_telegram_admin_invitation(NEW_ADMIN_ID, OWNER_ID)
        except ValueError as exc:
            assert "kutilmoqda" in str(exc)
        else:
            raise AssertionError("Duplicate pending invitation was not rejected")

        assert await db.activate_telegram_admin_invitation(NEW_ADMIN_ID) == "senior_admin"
        assert await db.admin_role(NEW_ADMIN_ID) == "senior_admin"
        assert await db.activate_telegram_admin_invitation(NEW_ADMIN_ID) is None

    _run(scenario())


def test_web_role_mismatch_fails_closed():
    class FakeDB:
        async def admin_role(self, telegram_id):
            return "junior_admin"

    fake_user = {
        "active": 1,
        "telegram_id": NEW_ADMIN_ID,
        "telegram_verified": 1,
        "role": "senior_admin",
    }
    assert _run(resolve_web_admin_role(FakeDB(), fake_user, OWNER_ID)) is None


def test_schema_v7_upgrade_adds_bot_invite_flag_without_deleting_existing_admin(tmp_path):
    import sqlite3
    from database.db import utcnow

    database_path = tmp_path / "legacy-v8.sqlite3"
    connection = sqlite3.connect(database_path)
    connection.executescript(
        "CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);"
        "INSERT INTO schema_migrations(version, applied_at) VALUES(8, '2026-01-01T00:00:00+00:00');"
        "CREATE TABLE admins(telegram_id INTEGER PRIMARY KEY, role TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1, "
        "pending_link INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, created_by INTEGER);"
    )
    connection.execute(
        "INSERT INTO admins(telegram_id,role,active,pending_link,created_at,created_by) VALUES(?,?,?,?,?,?)",
        (NEW_ADMIN_ID, "senior_admin", 0, 1, utcnow(), OWNER_ID),
    )
    connection.commit()
    connection.close()

    async def scenario():
        db = Database(database_path)
        await db.init(owner_id=OWNER_ID)
        columns = {row[1] for row in await db.fetchall("PRAGMA table_info(admins)")}
        assert "bot_invite_pending" in columns
        record = await db.fetchone(
            "SELECT telegram_id,role,active,pending_link,bot_invite_pending FROM admins WHERE telegram_id=?",
            (NEW_ADMIN_ID,),
        )
        assert tuple(record) == (NEW_ADMIN_ID, "senior_admin", 0, 1, 0)
        backups = list((tmp_path / "backups").glob("legacy-v8_pre_v9_*.sqlite3"))
        assert backups, "the pre-migration backup was not created"

    _run(scenario())
