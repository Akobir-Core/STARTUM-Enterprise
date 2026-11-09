from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def sync_admin_commands(bot: Any, telegram_id: int, role: str | None = None) -> None:
    """Keep Telegram's per-chat command menu aligned with server-side admin access."""
    if bot is None or int(telegram_id) <= 0:
        return
    try:
        # Import lazily so API-only test processes can load without the Telegram SDK.
        from aiogram.types import BotCommand, BotCommandScopeChat

        commands = [
            BotCommand(command="start", description="STARTUM bosh sahifasi"),
            BotCommand(command="help", description="Yordam"),
            BotCommand(command="profile", description="STARTUM profilingiz"),
        ]
        if role in {"ceo", "senior_admin", "junior_admin"}:
            commands.extend([
                BotCommand(command="admin", description="Admin panel"),
                BotCommand(command="users", description="Foydalanuvchilarni qidirish"),
            ])
        if role == "ceo":
            commands.append(BotCommand(command="admins", description="Administratorlar ro‘yxati"))
        if role in {"ceo", "senior_admin"}:
            commands.extend([
                BotCommand(command="add_teacher", description="Ustoz profili qo‘shish"),
                BotCommand(command="share_test", description="Testni guruhga ulashish"),
                BotCommand(command="assign_quiz", description="Testni o‘quv guruhiga tayinlash"),
                BotCommand(command="announce", description="Uch tilli e’lon tayyorlash"),
                BotCommand(command="assign_teacher", description="Ustozni fan/guruhga biriktirish"),
                BotCommand(command="revoke_teacher_assignment", description="Ustoz biriktiruvini bekor qilish"),
            ])
        if role == "ceo":
            commands.extend([
                BotCommand(command="add_admin", description="Administrator qo‘shish"),
                BotCommand(command="remove_admin", description="Administratorni faolsizlantirish"),
                BotCommand(command="add_teacher_manager", description="Ustozga yo‘nalish berish"),
                BotCommand(command="remove_teacher_manager", description="Ustoz huquqini bekor qilish"),
            ])
        await bot.set_my_commands(commands, scope=BotCommandScopeChat(chat_id=int(telegram_id)))
    except Exception as exc:
        # Database authorization remains authoritative if Telegram's menu API is unavailable.
        logger.warning("Telegram command menu sync failed for ID %s (%s).", telegram_id, type(exc).__name__)


async def sync_teacher_commands(bot: Any, telegram_id: int) -> None:
    """Teachers have learning-content commands but never receive the admin command."""
    if bot is None or int(telegram_id) <= 0:
        return
    try:
        from aiogram.types import BotCommand, BotCommandScopeChat
        await bot.set_my_commands([
            BotCommand(command="start", description="STARTUM bosh sahifasi"),
            BotCommand(command="help", description="Yordam"),
            BotCommand(command="profile", description="STARTUM profilingiz"),
            BotCommand(command="teacher", description="Ustoz kabineti"),
            BotCommand(command="share_test", description="O‘z yo‘nalishi testini guruhga yuborish"),
            BotCommand(command="assign_quiz", description="Testni biriktirilgan guruhga tayinlash"),
        ], scope=BotCommandScopeChat(chat_id=int(telegram_id)))
    except Exception as exc:
        logger.warning("Teacher command menu sync failed for ID %s (%s).", telegram_id, type(exc).__name__)


async def sync_owner_commands(bot: Any, telegram_id: int) -> None:
    """Expose private owner commands only in the configured owner's chat scope."""
    if bot is None or int(telegram_id) <= 0:
        return
    try:
        from aiogram.types import BotCommand, BotCommandScopeChat
        await bot.set_my_commands([
            BotCommand(command="start", description="STARTUM bosh sahifasi"),
            BotCommand(command="owner", description="Maxfiy OWNER kabineti"),
            BotCommand(command="admin", description="Boshqaruv paneli"),
            BotCommand(command="admins", description="Administratorlar ro‘yxati"),
            BotCommand(command="add_admin", description="Administrator qo‘shish"),
            BotCommand(command="remove_admin", description="Administratorni faolsizlantirish"),
            BotCommand(command="owner_assign_teacher", description="Ustozni fan/guruhga biriktirish"),
            BotCommand(command="assign_quiz", description="Testni guruhga tayinlash"),
            BotCommand(command="revoke_teacher_assignment", description="Ustoz biriktiruvini bekor qilish"),
            BotCommand(command="announce", description="Uch tilli e’lon tayyorlash"),
            BotCommand(command="owner_backup", description="Bazadan maxfiy backup olish"),
        ], scope=BotCommandScopeChat(chat_id=int(telegram_id)))
    except Exception as exc:
        logger.warning("OWNER command menu sync failed (%s).", type(exc).__name__)
