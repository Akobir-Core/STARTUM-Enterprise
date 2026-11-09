from __future__ import annotations

import asyncio
import logging
import sys
import socket

import uvicorn
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import SimpleEventIsolation
from aiogram.types import BotCommand, BotCommandScopeDefault
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest
from html import escape

from api import app, db as api_db
from config import config
from database.db import Database
from database.fsm_storage import SQLiteFSMStorage
from handlers import admin, education, user
from admin_commands import sync_admin_commands, sync_teacher_commands, sync_owner_commands
from notifications import deliver_pending_notifications
from user_moderation import SuspendedUserMiddleware
from startup import ApiPortInUseError, bind_api_listener


async def run_api(listener: socket.socket) -> None:
    server_config = uvicorn.Config(
        app,
        host=config.api_host,
        port=config.api_port,
        log_level=config.log_level.lower(),
    )
    server = uvicorn.Server(server_config)
    try:
        # The socket is bound once by main() before the bot is started. Passing
        # it to Uvicorn avoids its internal bind/SystemExit path on port conflicts.
        await server.serve(sockets=[listener])
    except SystemExit as exc:
        raise RuntimeError(
            f"Uvicorn API {config.api_host}:{config.api_port} ishga tushmadi."
        ) from exc


async def _notification_retry_worker(bot: Bot, db: Database) -> None:
    """Retry persisted notices while the bot is online; failures never erase applications."""
    next_fsm_cleanup = 0.0
    while True:
        await asyncio.sleep(60)
        try:
            loop_time = asyncio.get_running_loop().time()
            if loop_time >= next_fsm_cleanup:
                removed = await db.purge_expired_fsm_states(ttl_days=7)
                next_fsm_cleanup = loop_time + 24 * 60 * 60
                if removed:
                    logging.getLogger(__name__).info("%s ta eskirgan FSM yozuvi tozalandi.", removed)
            result = await deliver_pending_notifications(bot, db, limit=100)
            if result["sent"]:
                logging.getLogger(__name__).info("Navbatdan %s Telegram xabari yetkazildi.", result["sent"])
            # The calendar reminder window is idempotent (user_id + event dedupe key).
            await db.queue_due_calendar_reminders()
            inbox_rows = await db.pending_user_notifications(limit=80)
            for item in inbox_rows:
                text = f"🔔 <b>{escape(str(item['title']))}</b>"
                if item["body"]:
                    text += "\n\n" + escape(str(item["body"]))
                try:
                    await bot.send_message(int(item["telegram_id"]), text)
                    await db.mark_user_notification_delivery(int(item["id"]), success=True)
                except (TelegramForbiddenError, TelegramBadRequest) as exc:
                    await db.mark_user_notification_delivery(
                        int(item["id"]), success=False, permanent=True, error=type(exc).__name__
                    )
                except Exception as exc:
                    await db.mark_user_notification_delivery(
                        int(item["id"]), success=False, error=type(exc).__name__
                    )
        except asyncio.CancelledError:
            raise
        except Exception:
            # Keep the exception traceback in restricted server logs so the next
            # queue failure can be diagnosed; never include bot tokens or payloads.
            logging.getLogger(__name__).exception("Bildirishnomalar navbati tekshiruvi bajarilmadi.")


async def _run_bot_session() -> None:
    """Run one Telegram polling session; the API has its own independent task."""
    db = api_db
    bot = Bot(config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    app.state.bot = bot
    notification_task: asyncio.Task | None = None
    dp: Dispatcher | None = None
    try:
        dp = Dispatcher(
            storage=SQLiteFSMStorage(config.database_path, ttl_days=7),
            events_isolation=SimpleEventIsolation(),
        )
        dp["db"] = db
        suspended_user_middleware = SuspendedUserMiddleware()
        dp.message.outer_middleware(suspended_user_middleware)
        dp.callback_query.outer_middleware(suspended_user_middleware)
        dp.include_router(admin.router)
        dp.include_router(education.router)
        dp.include_router(user.router)

        user_commands = [
            BotCommand(command="start", description="STARTUM bosh sahifasi"),
            BotCommand(command="help", description="Yordam"),
            BotCommand(command="profile", description="STARTUM profilingiz"),
            BotCommand(command="student", description="O‘quvchi kabineti"),
            BotCommand(command="calendar", description="Akademik kalendar"),
            BotCommand(command="notifications", description="Bildirishnomalar"),
        ]
        await bot.set_my_commands(user_commands, scope=BotCommandScopeDefault())

        # A single administrator who cannot receive a scoped command menu must not
        # prevent the bot from serving everyone else.
        for admin_record in await db.admins(include_inactive=True):
            admin_id = int(admin_record["telegram_id"])
            role = await db.admin_role(admin_id)
            try:
                await sync_admin_commands(bot, admin_id, role)
            except Exception as exc:
                logging.getLogger(__name__).warning(
                    "Admin %s uchun buyruqlar menyusi yangilanmadi (%s).",
                    admin_id, type(exc).__name__,
                )
        for teacher in await db.teacher_managers():
            try:
                await sync_teacher_commands(bot, int(teacher["telegram_id"]))
            except Exception as exc:
                logging.getLogger(__name__).warning(
                    "Ustoz %s uchun buyruqlar menyusi yangilanmadi (%s).",
                    teacher["telegram_id"], type(exc).__name__,
                )
        await sync_owner_commands(bot, config.owner_telegram_id)

        me = await bot.get_me()
        logging.getLogger(__name__).info("STARTUM bot ishga tushdi: @%s", me.username)
        # Saved website/bot applications remain in the outbox if Telegram is unavailable.
        await deliver_pending_notifications(bot, db, limit=200)
        notification_task = asyncio.create_task(
            _notification_retry_worker(bot, db), name="startum-notification-retry"
        )
        # Preserve queued Telegram updates during a process restart.
        await bot.delete_webhook(drop_pending_updates=False)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        if notification_task is not None:
            notification_task.cancel()
            try:
                await notification_task
            except asyncio.CancelledError:
                pass
        try:
            if dp is not None:
                # Close persistent FSM storage and per-conversation locks even if
                # polling or notification delivery failed.
                await dp.fsm.close()
        except Exception:
            logging.getLogger(__name__).exception("Telegram FSM storage yopilmadi.")
        finally:
            if getattr(app.state, "bot", None) is bot:
                app.state.bot = None
            try:
                await bot.session.close()
            except Exception:
                logging.getLogger(__name__).exception("Telegram HTTP session yopilmadi.")


async def run_bot() -> None:
    """Reconnect the Telegram bot on failures without taking the website API down."""
    logger = logging.getLogger(__name__)
    while True:
        try:
            await _run_bot_session()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error(
                "Telegram bot seansi muvaffaqiyatsiz tugadi (%s); 15 soniyadan keyin qayta uriniladi.",
                type(exc).__name__,
            )
        await asyncio.sleep(15)


async def main() -> None:
    logging.basicConfig(
        level=getattr(logging, config.log_level, logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    # Bind before database migration or Telegram polling. A duplicate launch exits
    # cleanly without leaving a bot session or notification worker behind.
    listener = bind_api_listener(config.api_host, config.api_port)
    api_task: asyncio.Task | None = None
    bot_task: asyncio.Task | None = None
    try:
        await api_db.init(
            config.ceo_owner_id,
            config.admin_ids,
            web_admin_username=config.web_admin_username,
            web_admin_password_hash=config.web_admin_password_hash,
        )
        app.state.database_initialized = True
        api_task = asyncio.create_task(run_api(listener), name="startum-api")
        bot_task = asyncio.create_task(run_bot(), name="startum-telegram-bot")

        # API shutdown or a fatal API startup failure owns the application
        # lifecycle. run_bot() reconnects on transient Telegram errors itself.
        done, _pending = await asyncio.wait(
            {api_task, bot_task}, return_when=asyncio.FIRST_COMPLETED
        )
        for task in done:
            task.result()
    finally:
        for task in (bot_task, api_task):
            if task is not None and not task.done():
                task.cancel()
        remaining = [task for task in (bot_task, api_task) if task is not None]
        if remaining:
            await asyncio.gather(*remaining, return_exceptions=True)
        listener.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except ApiPortInUseError as exc:
        logging.basicConfig(level=logging.ERROR, format="%(levelname)s | %(message)s")
        logging.error("%s", exc)
        sys.exit(2)
    except KeyboardInterrupt:
        pass
