from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message

logger = logging.getLogger(__name__)


class SuspendedUserMiddleware(BaseMiddleware):
    """Block STARTUM bot interactions for accounts suspended by an authorized admin."""

    async def __call__(
        self,
        handler: Callable[[Any, dict[str, Any]], Awaitable[Any]],
        event: Any,
        data: dict[str, Any],
    ) -> Any:
        actor = getattr(event, "from_user", None)
        db = data.get("db")
        if not actor or db is None:
            return await handler(event, data)
        try:
            suspended = await db.user_access_is_suspended(int(actor.id))
        except Exception as exc:
            logger.error("Foydalanuvchi ruxsatini tekshirib bo‘lmadi (%s).", type(exc).__name__)
            suspended = True
        if suspended:
            message = "STARTUM botidagi profilingiz vaqtincha cheklangan. Tafsilotlar uchun markaz bilan bog‘laning."
            try:
                if isinstance(event, CallbackQuery):
                    await event.answer(message, show_alert=True)
                elif isinstance(event, Message):
                    await event.answer(message)
            except Exception as exc:
                logger.info("Cheklangan foydalanuvchiga xabar yuborilmadi (%s).", type(exc).__name__)
            return None
        return await handler(event, data)
