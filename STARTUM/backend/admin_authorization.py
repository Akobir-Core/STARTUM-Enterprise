"""Shared server-side identity and role checks for Bot and Website Admin.

The ``admins`` table is the authoritative Telegram permission record. Website
accounts are separate password identities and must be explicitly linked to an
active Telegram administrator before their sessions can access protected APIs.
"""

from __future__ import annotations

from typing import Any

ROLE_ALIASES = {
    "owner": "ceo",
    "admin": "senior_admin",
}
ADMIN_ROLES = {"ceo", "senior_admin", "junior_admin"}


def normalize_admin_role(value: Any) -> str | None:
    role = str(value or "").strip().casefold()
    if not role:
        return None
    role = ROLE_ALIASES.get(role, role)
    return role if role in ADMIN_ROLES else None


async def resolve_telegram_admin_role(db: Any, telegram_id: int, owner_telegram_id: int = 0) -> str | None:
    """Resolve an active Bot role using only trusted IDs and the canonical DB record."""
    try:
        telegram_id = int(telegram_id)
    except (TypeError, ValueError):
        return None
    if telegram_id <= 0:
        return None
    if owner_telegram_id > 0 and telegram_id == int(owner_telegram_id):
        return "ceo"
    return normalize_admin_role(await db.admin_role(telegram_id))


async def resolve_web_admin_role(db: Any, user: Any, bootstrap_owner_id: int) -> str | None:
    """Require a password account to match the active canonical Telegram admin role.

    Bot invitation acceptance does not grant Website Admin access: the website
    account must exist, be active, and have completed its own password login/link.
    """
    if not user or not bool(int(user["active"] or 0)):
        return None
    telegram_id = user["telegram_id"]
    if telegram_id is None:
        return None
    try:
        telegram_id = int(telegram_id)
    except (TypeError, ValueError):
        return None
    if telegram_id <= 0 or not bool(int(user["telegram_verified"] or 0)):
        return None
    web_role = normalize_admin_role(user["role"])
    if web_role is None:
        return None
    canonical_role = normalize_admin_role(await db.admin_role(telegram_id))
    if canonical_role != web_role:
        return None
    if web_role == "ceo" and telegram_id != int(bootstrap_owner_id):
        return None
    return canonical_role
