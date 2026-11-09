from __future__ import annotations

import asyncio
import importlib.util
import sqlite3
import sys
import types
import unittest
from dataclasses import dataclass
from pathlib import Path
from tempfile import mkdtemp


# aiogram is an optional runtime dependency in the offline QA image. These narrow
# interface stubs let the storage implementation be exercised against real SQLite.
@dataclass(frozen=True)
class _StorageKey:
    bot_id: int
    chat_id: int
    user_id: int
    thread_id: int | None = None
    business_connection_id: str | None = None
    destiny: str = "default"


class _BaseStorage:
    pass


def _load_storage_module():
    aiogram = types.ModuleType("aiogram")
    fsm = types.ModuleType("aiogram.fsm")
    storage_pkg = types.ModuleType("aiogram.fsm.storage")
    base = types.ModuleType("aiogram.fsm.storage.base")
    base.BaseStorage = _BaseStorage
    base.StorageKey = _StorageKey
    base.StateType = object
    aiogram.fsm = fsm
    fsm.storage = storage_pkg
    storage_pkg.base = base
    modules = {
        "aiogram": aiogram,
        "aiogram.fsm": fsm,
        "aiogram.fsm.storage": storage_pkg,
        "aiogram.fsm.storage.base": base,
    }
    previous = {name: sys.modules.get(name) for name in modules}
    sys.modules.update(modules)
    try:
        module_path = Path(__file__).resolve().parents[1] / "backend" / "database" / "fsm_storage.py"
        spec = importlib.util.spec_from_file_location("startum_fsm_storage_test", module_path)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)
        return module
    finally:
        for name, old in previous.items():
            if old is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = old


def _prepare_database(path: Path):
    connection = sqlite3.connect(path)
    try:
        connection.execute("""CREATE TABLE fsm_storage (
            storage_key TEXT PRIMARY KEY,
            state TEXT,
            data_json TEXT NOT NULL DEFAULT '{}',
            updated_at TEXT NOT NULL
        )""")
        connection.commit()
    finally:
        connection.close()


class SQLiteFSMStorageTests(unittest.TestCase):
    def test_fsm_state_and_data_survive_storage_recreation(self):
        tmp_path = Path(mkdtemp(prefix="startum-fsm-test-"))
        module = _load_storage_module()
        path = tmp_path / "fsm.sqlite3"
        _prepare_database(path)
        key = _StorageKey(bot_id=1, chat_id=100, user_id=100)

        async def scenario():
            first = module.SQLiteFSMStorage(path)
            await first.set_state(key, "RegistrationState:phone")
            await first.set_data(key, {"name": "Test User", "phone": "+998901234567", "course_id": 7})
            second = module.SQLiteFSMStorage(path)
            assert await second.get_state(key) == "RegistrationState:phone"
            assert await second.get_data(key) == {"name": "Test User", "phone": "+998901234567", "course_id": 7}
            await second.set_state(key, None)
            await second.set_data(key, {})
            assert await first.get_state(key) is None
            assert await first.get_data(key) == {}
            connection = sqlite3.connect(path)
            try:
                assert connection.execute("SELECT COUNT(*) FROM fsm_storage").fetchone()[0] == 0
            finally:
                connection.close()
            await first.close()
            await second.close()

        asyncio.run(scenario())


    def test_fsm_keys_are_isolated_by_bot_chat_user_and_topic(self):
        tmp_path = Path(mkdtemp(prefix="startum-fsm-test-"))
        module = _load_storage_module()
        path = tmp_path / "fsm-keys.sqlite3"
        _prepare_database(path)
        key_a = _StorageKey(bot_id=1, chat_id=100, user_id=100)
        key_b = _StorageKey(bot_id=1, chat_id=100, user_id=100, thread_id=55)

        async def scenario():
            storage = module.SQLiteFSMStorage(path)
            await storage.set_state(key_a, "A")
            await storage.set_state(key_b, "B")
            assert await storage.get_state(key_a) == "A"
            assert await storage.get_state(key_b) == "B"
            await storage.set_data(key_a, {"value": "one"})
            await storage.set_data(key_b, {"value": "two"})
            assert (await storage.get_data(key_a))["value"] == "one"
            assert (await storage.get_data(key_b))["value"] == "two"

        asyncio.run(scenario())


    def test_fsm_key_isolation_includes_business_connection_and_destiny(self):
        tmp_path = Path(mkdtemp(prefix="startum-fsm-test-"))
        module = _load_storage_module()
        path = tmp_path / "fsm-full-key.sqlite3"
        _prepare_database(path)
        default_key = _StorageKey(bot_id=1, chat_id=100, user_id=100)
        business_key = _StorageKey(
            bot_id=1, chat_id=100, user_id=100, business_connection_id="business-A"
        )
        destiny_key = _StorageKey(bot_id=1, chat_id=100, user_id=100, destiny="support")
        other_bot_key = _StorageKey(bot_id=2, chat_id=100, user_id=100)

        async def scenario():
            storage = module.SQLiteFSMStorage(path)
            keys = (default_key, business_key, destiny_key, other_bot_key)
            for index, key in enumerate(keys):
                await storage.set_state(key, f"State:{index}")
            for index, key in enumerate(keys):
                self.assertEqual(await storage.get_state(key), f"State:{index}")
            await storage.close()

        asyncio.run(scenario())

    def test_setting_new_state_after_expiry_discards_old_fsm_data(self):
        tmp_path = Path(mkdtemp(prefix="startum-fsm-test-"))
        module = _load_storage_module()
        path = tmp_path / "fsm-expired-state-write.sqlite3"
        _prepare_database(path)
        key = _StorageKey(bot_id=4, chat_id=40, user_id=50)

        async def scenario():
            storage = module.SQLiteFSMStorage(path, ttl_days=7)
            await storage.set_state(key, "OldState")
            await storage.set_data(key, {"private": "old-value"})
            connection = sqlite3.connect(path)
            try:
                connection.execute(
                    "UPDATE fsm_storage SET updated_at=? WHERE storage_key=?",
                    ("2020-01-01T00:00:00+00:00", storage._key(key)),
                )
                connection.commit()
            finally:
                connection.close()

            await storage.set_state(key, "FreshState")
            self.assertEqual(await storage.get_state(key), "FreshState")
            self.assertEqual(await storage.get_data(key), {})
            await storage.close()

        asyncio.run(scenario())

    def test_setting_new_data_after_expiry_does_not_keep_old_state(self):
        tmp_path = Path(mkdtemp(prefix="startum-fsm-test-"))
        module = _load_storage_module()
        path = tmp_path / "fsm-expired-data-write.sqlite3"
        _prepare_database(path)
        key = _StorageKey(bot_id=5, chat_id=50, user_id=60)

        async def scenario():
            storage = module.SQLiteFSMStorage(path, ttl_days=7)
            await storage.set_state(key, "OldState")
            await storage.set_data(key, {"private": "old-value"})
            connection = sqlite3.connect(path)
            try:
                connection.execute(
                    "UPDATE fsm_storage SET updated_at=? WHERE storage_key=?",
                    ("2020-01-01T00:00:00+00:00", storage._key(key)),
                )
                connection.commit()
            finally:
                connection.close()

            await storage.set_data(key, {"fresh": "value"})
            self.assertIsNone(await storage.get_state(key))
            self.assertEqual(await storage.get_data(key), {"fresh": "value"})
            await storage.close()

        asyncio.run(scenario())

    def test_expired_fsm_state_is_removed_on_read(self):
        tmp_path = Path(mkdtemp(prefix="startum-fsm-test-"))
        module = _load_storage_module()
        path = tmp_path / "fsm-expiry.sqlite3"
        _prepare_database(path)
        key = _StorageKey(bot_id=1, chat_id=100, user_id=100)
        storage = module.SQLiteFSMStorage(path, ttl_days=7)
        storage_key = storage._key(key)
        connection = sqlite3.connect(path)
        try:
            connection.execute(
                "INSERT INTO fsm_storage(storage_key,state,data_json,updated_at) VALUES(?,?,?,?)",
                (storage_key, "OldState", '{"phone":"private"}', "2020-01-01T00:00:00+00:00"),
            )
            connection.commit()
        finally:
            connection.close()

        async def scenario():
            assert await storage.get_state(key) is None
            assert await storage.get_data(key) == {}
            connection = sqlite3.connect(path)
            try:
                assert connection.execute("SELECT COUNT(*) FROM fsm_storage").fetchone()[0] == 0
            finally:
                connection.close()

        asyncio.run(scenario())

    def test_corrupt_nonstandard_json_constant_is_removed_safely(self):
        tmp_path = Path(mkdtemp(prefix="startum-fsm-test-"))
        module = _load_storage_module()
        path = tmp_path / "fsm-nonstandard-json.sqlite3"
        _prepare_database(path)
        key = _StorageKey(bot_id=11, chat_id=120, user_id=130)

        connection = sqlite3.connect(path)
        try:
            connection.execute(
                "INSERT INTO fsm_storage(storage_key,state,data_json,updated_at) VALUES(?,?,?,?)",
                (module.SQLiteFSMStorage._key(key), "OldState", '{"bad":NaN}', "2099-01-01T00:00:00+00:00"),
            )
            connection.commit()
        finally:
            connection.close()

        async def scenario():
            storage = module.SQLiteFSMStorage(path)
            self.assertEqual(await storage.get_data(key), {})
            self.assertIsNone(await storage.get_state(key))
            await storage.close()

        asyncio.run(scenario())

    def test_atomic_update_data_merges_concurrent_updates_and_survives_recreation(self):
        tmp_path = Path(mkdtemp(prefix="startum-fsm-test-"))
        module = _load_storage_module()
        path = tmp_path / "fsm-atomic-update.sqlite3"
        _prepare_database(path)
        key = _StorageKey(bot_id=9, chat_id=200, user_id=300)

        async def scenario():
            first = module.SQLiteFSMStorage(path)
            await first.set_state(key, "ApplicationState:phone")
            await first.set_data(key, {"name": "Akobir"})
            updates = [{f"field_{index}": index} for index in range(20)]
            await asyncio.gather(*(first.update_data(key, item) for item in updates))

            second = module.SQLiteFSMStorage(path)
            saved = await second.get_data(key)
            assert saved["name"] == "Akobir"
            assert all(saved[f"field_{index}"] == index for index in range(20))
            assert await second.get_state(key) == "ApplicationState:phone"
            await first.close()
            await second.close()

        asyncio.run(scenario())

    def test_fsm_rejects_non_json_numbers_without_changing_saved_data(self):
        tmp_path = Path(mkdtemp(prefix="startum-fsm-test-"))
        module = _load_storage_module()
        path = tmp_path / "fsm-strict-json.sqlite3"
        _prepare_database(path)
        key = _StorageKey(bot_id=2, chat_id=20, user_id=30)

        async def scenario():
            storage = module.SQLiteFSMStorage(path)
            await storage.set_data(key, {"safe": True})
            with self.assertRaises(ValueError):
                await storage.set_data(key, {"not_json": float("nan")})
            with self.assertRaises(ValueError):
                await storage.update_data(key, {"not_json": float("inf")})
            self.assertEqual(await storage.get_data(key), {"safe": True})
            await storage.close()

        asyncio.run(scenario())

    def test_empty_atomic_update_does_not_create_empty_record(self):
        tmp_path = Path(mkdtemp(prefix="startum-fsm-test-"))
        module = _load_storage_module()
        path = tmp_path / "fsm-empty-update.sqlite3"
        _prepare_database(path)
        key = _StorageKey(bot_id=3, chat_id=30, user_id=40)

        async def scenario():
            storage = module.SQLiteFSMStorage(path)
            self.assertEqual(await storage.update_data(key, {}), {})
            connection = sqlite3.connect(path)
            try:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM fsm_storage").fetchone()[0], 0)
            finally:
                connection.close()
            await storage.close()

        asyncio.run(scenario())

    def test_fsm_table_is_added_to_version_7_base_schema_without_overwriting_records(self):
        import ast
        root = Path(__file__).resolve().parents[1]
        db_source = (root / "backend" / "database" / "db.py").read_text(encoding="utf-8")
        tree = ast.parse(db_source)
        schema_node = next(
            node.value for node in tree.body
            if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == "SCHEMA" for target in node.targets
            )
        )
        schema_sql = ast.literal_eval(schema_node)
        self.assertIn("CREATE TABLE IF NOT EXISTS fsm_storage", schema_sql)
        self.assertIn("CURRENT_SCHEMA_VERSION = 7", db_source)
        source_db = root / "backend" / "startum.db"
        before_hash = __import__("hashlib").sha256(source_db.read_bytes()).hexdigest()
        tmp_path = Path(mkdtemp(prefix="startum-fsm-schema-"))
        copy_path = tmp_path / "copy.sqlite3"
        import shutil
        shutil.copy2(source_db, copy_path)
        connection = sqlite3.connect(copy_path)
        try:
            counts_before = {
                table: connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                for table in ("users", "admins", "courses", "applications")
            }
            connection.executescript(schema_sql)
            self.assertIsNotNone(connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='fsm_storage'"
            ).fetchone())
            counts_after = {
                table: connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                for table in counts_before
            }
            self.assertEqual(counts_after, counts_before)
            self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
        finally:
            connection.close()
        self.assertEqual(__import__("hashlib").sha256(source_db.read_bytes()).hexdigest(), before_hash)
