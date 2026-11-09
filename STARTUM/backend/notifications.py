from __future__ import annotations

import asyncio
import logging
from typing import Any

from database.db import Database

logger = logging.getLogger(__name__)
_delivery_lock = asyncio.Lock()


async def deliver_pending_notifications(
    bot: Any,
    db: Database,
    recipient_id: int | None = None,
    *,
    limit: int = 100,
    retry_exhausted: bool = False,
) -> dict[str, int]:
    """Deliver queued notices safely; keep failed rows so an admin can retry by opening the bot."""
    from keyboards.admin import application_actions, web_application_actions

    async with _delivery_lock:
        if retry_exhausted and recipient_id is not None:
            await db.reset_exhausted_notifications(recipient_id)
            await db.reset_exhausted_status_notifications(recipient_id)
        sent = failed = 0
        rows = await db.pending_notifications(recipient_id=recipient_id, limit=limit)
        for row in rows:
            try:
                markup = None
                app_id = int(row["application_id"])
                if row["source"] == "website":
                    if await db.web_application(app_id):
                        markup = web_application_actions(app_id)
                elif await db.application(app_id):
                    markup = application_actions(app_id)
                await bot.send_message(int(row["recipient_telegram_id"]), str(row["message_text"]), reply_markup=markup)
                await db.mark_notification_sent(int(row["id"]))
                sent += 1
            except Exception as exc:  # Telegram may reject users who have not opened the bot yet.
                await db.mark_notification_failed(int(row["id"]), type(exc).__name__)
                logger.warning(
                    "Telegram bildirishnomasi #%s/%s yetkazilmadi (%s).",
                    row["source"], row["application_id"], type(exc).__name__,
                )
                failed += 1

        remaining = max(0, limit - len(rows))
        status_rows = await db.pending_application_status_notifications(
            recipient_id=recipient_id, limit=remaining
        ) if remaining else []
        for row in status_rows:
            try:
                await bot.send_message(
                    int(row["recipient_telegram_id"]), str(row["message_text"])
                )
                await db.mark_application_status_notification_sent(int(row["id"]))
                sent += 1
            except Exception as exc:
                await db.mark_application_status_notification_failed(int(row["id"]), type(exc).__name__)
                logger.warning(
                    "Ariza holati bildirishnomasi #%s/%s yetkazilmadi (%s).",
                    row["source"], row["application_id"], type(exc).__name__,
                )
                failed += 1

        # Support requests use their own durable outbox because they are not applications.
        remaining = max(0, limit - len(rows) - len(status_rows))
        support_rows = await db.pending_support_notifications(limit=remaining) if remaining else []
        for row in support_rows:
            try:
                await bot.send_message(
                    int(row["recipient_telegram_id"]), str(row["message_text"])
                )
                await db.mark_support_notification_sent(int(row["id"]))
                sent += 1
            except Exception as exc:
                await db.mark_support_notification_failed(int(row["id"]), type(exc).__name__)
                logger.warning(
                    "STARTUM murojaati #%s Telegram adminiga yetkazilmadi (%s).",
                    row["message_id"], type(exc).__name__,
                )
                failed += 1
    return {
        "sent": sent,
        "failed": failed,
        "checked": len(rows) + len(status_rows) + len(support_rows),
    }
