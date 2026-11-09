from __future__ import annotations

from config import config


ADMIN_ROLES = {"ceo", "senior_admin", "junior_admin"}


async def actor_role(db, telegram_id: int) -> str:
    """Resolve role from trusted server-side sources; never trust callback payloads."""
    telegram_id = int(telegram_id)
    if telegram_id == int(config.owner_telegram_id):
        return "owner"
    role = await db.admin_role(telegram_id)
    if role in ADMIN_ROLES:
        return role
    if await db.is_teacher(telegram_id):
        return "teacher"
    user = await db.fetchone(
        "SELECT 1 FROM users WHERE telegram_id=? AND account_status='active'", (telegram_id,)
    )
    return "student" if user else "guest"


async def is_owner(db, telegram_id: int) -> bool:
    # OWNER is an immutable configuration identity, not a DB-assigned role.
    return int(telegram_id) == int(config.owner_telegram_id)


async def is_admin_actor(db, telegram_id: int, allowed: tuple[str, ...] = ("ceo", "senior_admin")) -> bool:
    if await is_owner(db, telegram_id):
        return True
    role = await db.admin_role(int(telegram_id))
    return role in set(allowed)


async def require_teacher_scope(db, telegram_id: int, course_id: int, group_id: int | None = None) -> bool:
    return await db.teacher_has_scope(int(telegram_id), int(course_id), group_id)
