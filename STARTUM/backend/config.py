from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import re
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class Config:
    bot_token: str
    database_path: str
    ceo_owner_id: int
    owner_telegram_id: int
    admin_ids: tuple[int, ...]
    bot_username: str
    default_language: str
    log_level: str
    api_host: str
    api_port: int
    cors_origins: tuple[str, ...]
    web_admin_username: str
    web_admin_password_hash: str
    admin_session_secret: str
    admin_session_ttl: int
    admin_login_window_seconds: int
    admin_login_max_failures: int
    admin_cookie_secure: bool
    app_env: str


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"{name} topilmadi. .env fayliga qiymat yozing.")
    return value


def _int_list(value: str) -> tuple[int, ...]:
    result: list[int] = []
    for raw in value.split(","):
        raw = raw.strip()
        if not raw:
            continue
        try:
            number = int(raw)
        except ValueError as exc:
            raise ValueError(f"Telegram ID noto‘g‘ri: {raw}") from exc
        if number > 0:
            result.append(number)
    return tuple(dict.fromkeys(result))


def from_env() -> Config:
    token = _required("BOT_TOKEN")
    owner = int(_required("CEO_OWNER_ID"))
    owner_raw = os.getenv("OWNER_TELEGRAM_ID", "").strip()
    try:
        owner_telegram_id = int(owner_raw) if owner_raw else owner
    except ValueError as exc:
        raise ValueError("OWNER_TELEGRAM_ID musbat Telegram ID bo‘lishi kerak.") from exc
    if owner_telegram_id <= 0:
        raise ValueError("OWNER_TELEGRAM_ID musbat bo‘lishi kerak.")
    # ADMIN_IDS is intentionally ignored: administrator access is granted in the bot
    # and linked to an individual, password-protected web-admin account.
    all_admins = (owner,)

    language = os.getenv("DEFAULT_LANGUAGE", "uz").strip().lower()
    if language not in {"uz", "ru", "en"}:
        language = "uz"

    try:
        api_port = int(os.getenv("API_PORT", "8000"))
    except ValueError as exc:
        raise ValueError("API_PORT raqam bo‘lishi kerak.") from exc
    if not 1 <= api_port <= 65535:
        raise ValueError("API_PORT 1 dan 65535 gacha bo‘lishi kerak.")
    api_host = os.getenv("API_HOST", "127.0.0.1").strip() or "127.0.0.1"
    raw_origins = os.getenv("CORS_ORIGINS", "http://127.0.0.1:5500,http://localhost:5500")
    cors_origins = tuple(x.strip().rstrip("/") for x in raw_origins.split(",") if x.strip())
    try:
        admin_session_ttl = max(300, min(int(os.getenv("ADMIN_SESSION_TTL", "3600")), 86400))
    except ValueError as exc:
        raise ValueError("ADMIN_SESSION_TTL raqam bo‘lishi kerak.") from exc
    try:
        admin_login_window_seconds = int(os.getenv("ADMIN_LOGIN_WINDOW_SECONDS", "300"))
        admin_login_max_failures = int(os.getenv("ADMIN_LOGIN_MAX_FAILURES", "8"))
    except ValueError as exc:
        raise ValueError("Admin login cheklovi uchun butun sonli qiymat kiriting.") from exc
    if not 30 <= admin_login_window_seconds <= 3600:
        raise ValueError("ADMIN_LOGIN_WINDOW_SECONDS 30–3600 oralig‘ida bo‘lishi kerak.")
    if not 3 <= admin_login_max_failures <= 20:
        raise ValueError("ADMIN_LOGIN_MAX_FAILURES 3–20 oralig‘ida bo‘lishi kerak.")
    admin_cookie_secure = os.getenv("ADMIN_COOKIE_SECURE", "false").strip().lower() in {"1", "true", "yes", "on"}
    app_env = os.getenv("APP_ENV", "development").strip().lower() or "development"
    if app_env not in {"development", "test", "production"}:
        raise ValueError("APP_ENV development, test yoki production bo‘lishi kerak.")
    if app_env == "production" and not admin_cookie_secure:
        raise ValueError("Production muhitida ADMIN_COOKIE_SECURE=true bo‘lishi shart.")
    web_admin_username = os.getenv("WEB_ADMIN_USERNAME", "admin").strip() or "admin"
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{2,39}", web_admin_username):
        raise ValueError("WEB_ADMIN_USERNAME 3–40 ta ruxsat etilgan lotin belgilaridan iborat bo‘lsin va harf bilan boshlansin.")

    raw_database_path = os.getenv("DATABASE_PATH", "startum.db").strip() or "startum.db"
    database_path = Path(raw_database_path).expanduser()
    if not database_path.is_absolute():
        database_path = ROOT / database_path

    return Config(
        bot_token=token,
        database_path=str(database_path.resolve()),
        ceo_owner_id=owner,
        owner_telegram_id=owner_telegram_id,
        admin_ids=all_admins,
        bot_username=os.getenv("BOT_USERNAME", "").strip().lstrip("@"),
        default_language=language,
        log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper(),
        api_host=api_host,
        api_port=api_port,
        cors_origins=cors_origins,
        web_admin_username=web_admin_username,
        web_admin_password_hash=os.getenv("WEB_ADMIN_PASSWORD_HASH", "").strip(),
        admin_session_secret=os.getenv("ADMIN_SESSION_SECRET", "").strip(),
        admin_session_ttl=admin_session_ttl,
        admin_login_window_seconds=admin_login_window_seconds,
        admin_login_max_failures=admin_login_max_failures,
        admin_cookie_secure=admin_cookie_secure,
        app_env=app_env,
    )


config = from_env()
