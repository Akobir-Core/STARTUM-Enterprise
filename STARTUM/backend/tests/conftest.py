from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

# Isolated test-only configuration: these are deliberately fake credentials.
os.environ["BOT_TOKEN"] = "1234567890:TEST_ONLY_NOT_A_REAL_TOKEN"
os.environ["CEO_OWNER_ID"] = "123456789"
os.environ["ADMIN_IDS"] = ""
os.environ.pop("APPLICATION_ADMIN_IDS", None)
os.environ["DATABASE_PATH"] = str(BACKEND_DIR / "test-runtime.db")
os.environ["WEB_ADMIN_USERNAME"] = "test-admin"
os.environ["ADMIN_SESSION_SECRET"] = "test-only-secret-that-is-long-enough-0123456789"
_test_password = "TestOnlyStrongPassword!2026"
_test_salt = "pytest-only-salt"
_test_digest = hashlib.pbkdf2_hmac("sha256", _test_password.encode(), _test_salt.encode(), 120_000).hex()
os.environ["WEB_ADMIN_PASSWORD_HASH"] = f"pbkdf2_sha256$120000${_test_salt}${_test_digest}"
os.environ["ADMIN_COOKIE_SECURE"] = "false"
os.environ["CORS_ORIGINS"] = "http://127.0.0.1:5500,http://localhost:5500"

import pytest
from fastapi.testclient import TestClient

import api as api_module
from database.db import Database


@pytest.fixture
def client(tmp_path, monkeypatch):
    test_db = Database(tmp_path / "startum-test.sqlite3")
    monkeypatch.setattr(api_module, "db", test_db)
    monkeypatch.setattr(api_module.app.state, "bot", None, raising=False)
    monkeypatch.setattr(api_module.app.state, "database_initialized", False, raising=False)
    with TestClient(api_module.app) as test_client:
        yield test_client
