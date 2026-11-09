from __future__ import annotations

"""Small SQLite-backed aiogram FSM storage.

Conversation state is persisted across bot process restarts. Payloads are limited
to JSON-safe values and expire after a short retention window to avoid keeping
 incomplete forms indefinitely. Each operation opens its own SQLite connection,
 runs it in a worker thread and closes it immediately.
"""

import asyncio
import json
import logging
import sqlite3
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from aiogram.fsm.storage.base import BaseStorage, StorageKey, StateType

logger = logging.getLogger(__name__)


class SQLiteFSMStorage(BaseStorage):
    def __init__(self, database_path: str | Path, *, ttl_days: int = 7, busy_timeout_ms: int = 5000):
        self.database_path = str(Path(database_path).expanduser().resolve())
        self.ttl_days = max(1, min(int(ttl_days), 30))
        self.busy_timeout_ms = max(1000, min(int(busy_timeout_ms), 30000))

    @staticmethod
    def _key(key: StorageKey) -> str:
        # Include all StorageKey dimensions so bot/thread/business conversations
        # cannot overwrite each other.
        payload = [
            int(getattr(key, "bot_id", 0) or 0),
            int(getattr(key, "chat_id", 0) or 0),
            int(getattr(key, "user_id", 0) or 0),
            getattr(key, "thread_id", None),
            getattr(key, "business_connection_id", None),
            str(getattr(key, "destiny", "default") or "default"),
        ]
        return json.dumps(payload, ensure_ascii=True, separators=(",", ":"))

    async def _run(self, operation, *, write: bool = False):
        def execute():
            connection = sqlite3.connect(self.database_path, timeout=self.busy_timeout_ms / 1000)
            connection.row_factory = sqlite3.Row
            try:
                connection.execute(f"PRAGMA busy_timeout={self.busy_timeout_ms}")
                result = operation(connection)
                if write:
                    connection.commit()
                return result
            except Exception:
                if write:
                    connection.rollback()
                raise
            finally:
                connection.close()
        return await asyncio.to_thread(execute)

    @staticmethod
    def _reject_json_constant(value: str):
        raise ValueError(f"FSM JSON contains unsupported constant: {value}")

    @classmethod
    def _decode_json(cls, value: str | None) -> Any:
        return json.loads(value or "{}", parse_constant=cls._reject_json_constant)

    def _cutoff(self) -> str:
        return (datetime.now(timezone.utc) - timedelta(days=self.ttl_days)).isoformat()

    async def get_state(self, key: StorageKey) -> str | None:
        storage_key = self._key(key)
        cutoff = self._cutoff()

        def operation(connection):
            row = connection.execute(
                "SELECT state,updated_at FROM fsm_storage WHERE storage_key=?",
                (storage_key,),
            ).fetchone()
            if row is None:
                return None
            if str(row["updated_at"]) < cutoff:
                # Conditional deletion avoids removing a conversation another
                # update refreshed after this read.
                connection.execute(
                    "DELETE FROM fsm_storage WHERE storage_key=? AND updated_at < ?",
                    (storage_key, cutoff),
                )
                connection.commit()
                return None
            return row["state"]

        return await self._run(operation)

    async def set_state(self, key: StorageKey, state: StateType = None) -> None:
        storage_key = self._key(key)
        value = getattr(state, "state", state) if state is not None else None
        if value is not None:
            value = str(value)
        now = datetime.now(timezone.utc).isoformat()

        def operation(connection):
            connection.execute(
                "INSERT INTO fsm_storage(storage_key,state,data_json,updated_at) VALUES(?,?, '{}',?) "
                "ON CONFLICT(storage_key) DO UPDATE SET "
                "state=excluded.state, "
                "data_json=CASE WHEN fsm_storage.updated_at < ? THEN '{}' ELSE fsm_storage.data_json END, "
                "updated_at=excluded.updated_at",
                (storage_key, value, now, self._cutoff()),
            )

        await self._run(operation, write=True)

    async def get_data(self, key: StorageKey) -> dict[str, Any]:
        storage_key = self._key(key)
        cutoff = self._cutoff()

        def operation(connection):
            row = connection.execute(
                "SELECT data_json,updated_at FROM fsm_storage WHERE storage_key=?",
                (storage_key,),
            ).fetchone()
            if row is None:
                return {}
            if str(row["updated_at"]) < cutoff:
                connection.execute(
                    "DELETE FROM fsm_storage WHERE storage_key=? AND updated_at < ?",
                    (storage_key, cutoff),
                )
                connection.commit()
                return {}
            try:
                data = self._decode_json(row["data_json"])
            except (TypeError, ValueError):
                data = None
            if not isinstance(data, dict):
                logger.warning("FSM storage ma’lumoti buzilgan; suhbat ma’lumoti tozalandi.")
                connection.execute(
                    "DELETE FROM fsm_storage WHERE storage_key=? AND updated_at=?",
                    (storage_key, row["updated_at"]),
                )
                connection.commit()
                return {}
            return data

        return await self._run(operation)

    async def set_data(self, key: StorageKey, data: Mapping[str, Any]) -> None:
        storage_key = self._key(key)
        if not isinstance(data, Mapping):
            raise TypeError("FSM ma’lumoti dict yoki Mapping bo‘lishi kerak.")
        try:
            encoded = json.dumps(
                dict(data), ensure_ascii=False, separators=(",", ":"), allow_nan=False
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("FSM ma’lumoti qat’iy JSON ko‘rinishida saqlanishi kerak.") from exc
        now = datetime.now(timezone.utc).isoformat()

        cutoff = self._cutoff()

        def operation(connection):
            if encoded == "{}":
                connection.execute(
                    "DELETE FROM fsm_storage WHERE storage_key=? AND updated_at < ?",
                    (storage_key, cutoff),
                )
                connection.execute(
                    "DELETE FROM fsm_storage WHERE storage_key=? AND state IS NULL",
                    (storage_key,),
                )
                connection.execute(
                    "UPDATE fsm_storage SET data_json='{}',updated_at=? WHERE storage_key=?",
                    (now, storage_key),
                )
            else:
                connection.execute(
                    "INSERT INTO fsm_storage(storage_key,state,data_json,updated_at) VALUES(?,NULL,?,?) "
                    "ON CONFLICT(storage_key) DO UPDATE SET "
                    "state=CASE WHEN fsm_storage.updated_at < ? THEN NULL ELSE fsm_storage.state END, "
                    "data_json=excluded.data_json,updated_at=excluded.updated_at",
                    (storage_key, encoded, now, cutoff),
                )

        await self._run(operation, write=True)

    async def update_data(self, key: StorageKey, data: Mapping[str, Any]) -> dict[str, Any]:
        """Atomically merge FSM data to prevent concurrent updates being lost."""
        if not isinstance(data, Mapping):
            raise TypeError("FSM ma’lumoti dict yoki Mapping bo‘lishi kerak.")

        try:
            updates = dict(data)
            # Validate the incoming payload before opening a write transaction.
            json.dumps(updates, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ValueError("FSM ma’lumoti qat’iy JSON ko‘rinishida saqlanishi kerak.") from exc

        storage_key = self._key(key)
        cutoff = self._cutoff()
        now = datetime.now(timezone.utc).isoformat()

        def operation(connection):
            # BEGIN IMMEDIATE serializes read/merge/write across concurrent
            # handlers and even across multiple processes sharing this SQLite DB.
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT state,data_json,updated_at FROM fsm_storage WHERE storage_key=?",
                (storage_key,),
            ).fetchone()

            if row is not None and str(row["updated_at"]) < cutoff:
                connection.execute("DELETE FROM fsm_storage WHERE storage_key=?", (storage_key,))
                row = None

            current: dict[str, Any] = {}
            state = row["state"] if row is not None else None
            if row is not None:
                try:
                    decoded = self._decode_json(row["data_json"])
                    current = decoded if isinstance(decoded, dict) else {}
                except (TypeError, ValueError):
                    logger.warning("FSM storage ma’lumoti buzilgan; suhbat yozuvi tozalandi.")
                    connection.execute("DELETE FROM fsm_storage WHERE storage_key=?", (storage_key,))
                    row = None
                    state = None
                    current = {}

            current.update(updates)
            if not current and state is None:
                if row is not None:
                    connection.execute("DELETE FROM fsm_storage WHERE storage_key=?", (storage_key,))
                return {}

            encoded = json.dumps(
                current, ensure_ascii=False, separators=(",", ":"), allow_nan=False
            )
            connection.execute(
                "INSERT INTO fsm_storage(storage_key,state,data_json,updated_at) VALUES(?,?,?,?) "
                "ON CONFLICT(storage_key) DO UPDATE SET "
                "state=excluded.state,data_json=excluded.data_json,updated_at=excluded.updated_at",
                (storage_key, state, encoded, now),
            )
            return current.copy()

        return await self._run(operation, write=True)

    async def close(self) -> None:
        # Connections are short-lived and closed after each operation.
        return None
