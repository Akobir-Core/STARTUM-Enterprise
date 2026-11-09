from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

try:
    from aiogram import Bot, Dispatcher, Router
    from aiogram.filters import StateFilter
    from aiogram.fsm.context import FSMContext
    from aiogram.fsm.state import State, StatesGroup
    from aiogram.fsm.storage.memory import SimpleEventIsolation
    from aiogram.types import Message, Update
    from database.fsm_storage import SQLiteFSMStorage
except ImportError as dependency_error:  # pragma: no cover - depends on runtime environment
    AIROGRAM_AVAILABLE = False
    AIROGRAM_IMPORT_ERROR = dependency_error
else:
    AIROGRAM_AVAILABLE = True
    AIROGRAM_IMPORT_ERROR = None

    class Registration(StatesGroup):
        waiting_for_phone = State()


class AiogramFSMRestartIntegrationTests(unittest.TestCase):
    @unittest.skipUnless(AIROGRAM_AVAILABLE, "Requires the pinned aiogram package; runtime unavailable.")
    def test_dispatcher_restart_restores_state_and_continues_handler(self):
        with tempfile.TemporaryDirectory(prefix="startum-aiogram-fsm-") as temp_dir:
            database_path = Path(temp_dir) / "startum-fsm.sqlite3"
            with sqlite3.connect(database_path) as connection:
                connection.execute(
                    """CREATE TABLE fsm_storage (
                        storage_key TEXT PRIMARY KEY,
                        state TEXT,
                        data_json TEXT NOT NULL DEFAULT '{}',
                        updated_at TEXT NOT NULL
                    )"""
                )

            async def scenario():
                bot = Bot(token="123456:TEST_ONLY_FAKE_TOKEN")
                chat_id = 100100
                user_id = 200200
                first_dispatcher = Dispatcher(
                    storage=SQLiteFSMStorage(database_path),
                    events_isolation=SimpleEventIsolation(),
                )
                first_context = first_dispatcher.fsm.get_context(
                    bot=bot, chat_id=chat_id, user_id=user_id
                )
                await first_context.set_state(Registration.waiting_for_phone)
                await first_context.update_data(name="Test student", course="English")
                await first_dispatcher.fsm.close()

                # A new Dispatcher and a new storage instance simulate process restart.
                second_dispatcher = Dispatcher(
                    storage=SQLiteFSMStorage(database_path),
                    events_isolation=SimpleEventIsolation(),
                )
                second_context = second_dispatcher.fsm.get_context(
                    bot=bot, chat_id=chat_id, user_id=user_id
                )
                self.assertEqual(
                    await second_context.get_state(), Registration.waiting_for_phone.state
                )
                self.assertEqual(
                    await second_context.get_data(),
                    {"name": "Test student", "course": "English"},
                )

                continued: list[dict[str, str]] = []
                router = Router(name="fsm-restart-integration-test")

                @router.message(StateFilter(Registration.waiting_for_phone))
                async def continue_registration(message: Message, state: FSMContext):
                    previous = await state.get_data()
                    await state.update_data(phone=message.text or "")
                    continued.append(await state.get_data())
                    self.assertEqual(previous["name"], "Test student")
                    await state.clear()

                second_dispatcher.include_router(router)
                now = int(datetime.now(timezone.utc).timestamp())
                update = Update.model_validate(
                    {
                        "update_id": 1,
                        "message": {
                            "message_id": 1,
                            "date": now,
                            "chat": {"id": chat_id, "type": "private"},
                            "from": {
                                "id": user_id,
                                "is_bot": False,
                                "first_name": "Test",
                            },
                            "text": "+998900000000",
                        },
                    },
                    context={"bot": bot},
                )
                await second_dispatcher.feed_update(bot, update)

                self.assertEqual(
                    continued,
                    [{
                        "name": "Test student",
                        "course": "English",
                        "phone": "+998900000000",
                    }],
                )
                self.assertIsNone(await second_context.get_state())
                self.assertEqual(await second_context.get_data(), {})

                await second_dispatcher.fsm.close()
                await bot.session.close()

            asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
