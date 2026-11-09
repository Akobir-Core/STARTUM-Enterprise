from __future__ import annotations

import base64
import csv
import io
from contextlib import asynccontextmanager
import hashlib
import hmac
import json
import logging
import re
import secrets
import sys
import time
from html import escape
from pathlib import Path
from typing import Any, Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import config
from application_statuses import ALL_APPLICATION_STATUSES, application_status_label
from database.db import Database
from admin_commands import sync_admin_commands
from admin_authorization import resolve_web_admin_role
from notifications import deliver_pending_notifications

logger = logging.getLogger(__name__)

ADMIN_DIR = Path(__file__).resolve().parent / "admin_panel"
ADMIN_COOKIE = "startum_admin_session"
db = Database(config.database_path)
_LOGIN_WINDOW_SECONDS = config.admin_login_window_seconds
_LOGIN_MAX_FAILURES = config.admin_login_max_failures
_ALLOWED_STATUSES = set(ALL_APPLICATION_STATUSES)
_ROLE_LABELS = {"ceo": "CEO", "senior_admin": "Katta administrator", "junior_admin": "Kichik administrator"}
_PASSWORD_ITERATIONS = 390_000


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # main.py initializes before starting the bot and API concurrently; direct ASGI startup still initializes here.
    if not getattr(_app.state, "database_initialized", False):
        await db.init(
            config.ceo_owner_id,
            config.admin_ids,
            web_admin_username=config.web_admin_username,
            web_admin_password_hash=config.web_admin_password_hash,
        )
        _app.state.database_initialized = True
    yield


_production = config.app_env == "production"
app = FastAPI(
    title="STARTUM Backend API",
    version="1.2.0",
    lifespan=lifespan,
    docs_url=None if _production else "/docs",
    redoc_url=None if _production else "/redoc",
    openapi_url=None if _production else "/openapi.json",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(config.cors_origins),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Content-Type", "X-STARTUM-Admin", "Authorization"],
)


class ApplicationIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    phone: str = Field(min_length=9, max_length=24)
    telegram: str = Field(default="", max_length=33)
    course: str = Field(min_length=2, max_length=160)
    message: str = Field(default="", max_length=1000)
    level: str = Field(default="", max_length=60)
    preferred_time: str = Field(default="", max_length=120)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = " ".join(value.split())
        if len(value) < 2 or not any(char.isalpha() for char in value):
            raise ValueError("Ism-familiyani tekshiring.")
        if any(ord(char) < 32 for char in value):
            raise ValueError("Ism-familiyada boshqaruv belgisi bo‘lishi mumkin emas.")
        return value

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str) -> str:
        value = value.strip()
        if not re.fullmatch(r"[+0-9()\- .]{9,24}", value):
            raise ValueError("Telefon raqamida ruxsat etilmagan belgilar bor.")
        digits = re.sub(r"\D", "", value)
        if not 9 <= len(digits) <= 15:
            raise ValueError("Telefon raqami 9–15 ta raqamdan iborat bo‘lishi kerak.")
        return value

    @field_validator("telegram")
    @classmethod
    def validate_telegram(cls, value: str) -> str:
        value = value.strip()
        if not value:
            return ""
        if not re.fullmatch(r"@[A-Za-z0-9_]{5,32}", value):
            raise ValueError("Telegram username @ bilan boshlanib, 5–32 belgidan iborat bo‘lishi kerak.")
        return value

    @field_validator("course", "message", "level", "preferred_time")
    @classmethod
    def trim_text(cls, value: str) -> str:
        return value.strip()


class AdminLoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=256)


class ApplicationStatusIn(BaseModel):
    status: Literal["new", "in_review", "contacted", "accepted", "rejected", "in_progress", "closed"]


class ApplicationStatusLookupIn(BaseModel):
    tracking_code: str = Field(min_length=12, max_length=64)

    @field_validator("tracking_code")
    @classmethod
    def validate_tracking_code(cls, value: str) -> str:
        value = value.strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]{12,64}", value):
            raise ValueError("Kuzatuv kodini tekshiring.")
        return value


class CourseIn(BaseModel):
    kind: Literal["subject", "special"]
    name_uz: str = Field(min_length=2, max_length=120)
    name_ru: str = Field(min_length=2, max_length=160)
    name_en: str = Field(min_length=2, max_length=160)
    description_uz: str = Field(default="", max_length=1000)
    description_ru: str = Field(default="", max_length=1000)
    description_en: str = Field(default="", max_length=1000)
    icon: str = Field(default="📚", max_length=8)

    @field_validator("name_uz", "name_ru", "name_en")
    @classmethod
    def validate_course_names(cls, value: str) -> str:
        value = " ".join(value.split())
        if len(value) < 2:
            raise ValueError("Kurs nomini kiriting.")
        return value

    @field_validator("description_uz", "description_ru", "description_en", "icon")
    @classmethod
    def trim_course_text(cls, value: str) -> str:
        return value.strip()


class TeacherIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    subject: str = Field(min_length=2, max_length=120)
    experience: str = Field(default="", max_length=80)
    bio: str = Field(default="", max_length=1000)

    @field_validator("full_name", "subject")
    @classmethod
    def trim_required_teacher_fields(cls, value: str) -> str:
        value = " ".join(value.split())
        if len(value) < 2:
            raise ValueError("Maydonni tekshiring.")
        return value

    @field_validator("experience", "bio")
    @classmethod
    def trim_teacher_text(cls, value: str) -> str:
        return value.strip()


def _validate_admin_password(value: str) -> str:
    if value.strip() != value or len(value) < 12:
        raise ValueError("Parol kamida 12 belgidan iborat bo‘lsin va bosh/oxirida bo‘sh joy bo‘lmasin.")
    if not any(char.isalpha() for char in value) or not any(char.isdigit() for char in value):
        raise ValueError("Parolda kamida bitta harf va bitta raqam bo‘lishi kerak.")
    return value


class WebAdminCreateIn(BaseModel):
    username: str = Field(min_length=3, max_length=40)
    password: str = Field(min_length=12, max_length=256)
    telegram_id: int = Field(gt=0, le=9_223_372_036_854_775_807)
    role: Literal["senior_admin", "junior_admin"]

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        value = value.strip()
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{2,39}", value):
            raise ValueError("Login harf bilan boshlansin; 3–40 ta lotin harfi, raqam, nuqta, _ yoki - ishlatilsin.")
        return value

    @field_validator("password")
    @classmethod
    def validate_new_password(cls, value: str) -> str:
        return _validate_admin_password(value)


class WebAdminActiveIn(BaseModel):
    active: bool


class EducationGroupCreateIn(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    course_id: int = Field(gt=0)
    schedule_text: str = Field(default="", max_length=240)

    @field_validator("name", "schedule_text")
    @classmethod
    def normalize_group_text(cls, value: str) -> str:
        return " ".join(value.split())


class EducationGroupTeacherIn(BaseModel):
    telegram_id: int = Field(gt=0, le=9_223_372_036_854_775_807)
    group_id: int = Field(gt=0)


class CalendarEventIn(BaseModel):
    titles: dict[str, str]
    descriptions: dict[str, str] = Field(default_factory=dict)
    category: Literal["lesson", "exam", "holiday", "event", "deadline", "schedule_change"] = "event"
    starts_at: str = Field(min_length=10, max_length=64)
    ends_at: str | None = Field(default=None, max_length=64)
    location: str = Field(default="", max_length=180)
    target_group_id: int | None = Field(default=None, ge=1)
    status: Literal["draft", "published", "archived"] = "draft"
    reminder_24h: bool = True

    @field_validator("titles")
    @classmethod
    def validate_titles(cls, value: dict[str, str]) -> dict[str, str]:
        normalized = {lang: " ".join(str(value.get(lang, "")).split()) for lang in ("uz", "ru", "en")}
        if any(len(normalized[lang]) < 2 for lang in normalized):
            raise ValueError("Sarlavha UZ, RU va EN tillarida kiritilishi kerak.")
        return normalized


class AdminPasswordChangeIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=12, max_length=256)

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, value: str) -> str:
        return _validate_admin_password(value)


class AdminPasswordResetIn(BaseModel):
    password: str = Field(min_length=12, max_length=256)

    @field_validator("password")
    @classmethod
    def validate_new_password(cls, value: str) -> str:
        return _validate_admin_password(value)


class CatalogActiveIn(BaseModel):
    active: bool


class UserModerationIn(BaseModel):
    status: Literal["active", "suspended"]
    reason: str = Field(default="", max_length=500)
    duration_minutes: int | None = Field(default=None, ge=1, le=525600)

    @field_validator("reason")
    @classmethod
    def trim_moderation_reason(cls, value: str) -> str:
        return " ".join(value.split())


class LearningResourceIn(BaseModel):
    category: Literal["book", "vocabulary", "movie", "music"]
    course_id: int = Field(gt=0)
    title: str = Field(min_length=2, max_length=180)
    description: str = Field(default="", max_length=1200)
    content: str = Field(min_length=1, max_length=10000)
    media_type: Literal["text", "url"] = "text"

    @field_validator("title")
    @classmethod
    def clean_resource_title(cls, value: str) -> str:
        value = " ".join(value.split())
        if len(value) < 2:
            raise ValueError("Material nomini kiriting.")
        return value

    @field_validator("content")
    @classmethod
    def clean_resource_content(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Material matni yoki havolasini kiriting.")
        return value

    @field_validator("description")
    @classmethod
    def clean_resource_description(cls, value: str) -> str:
        return value.strip()


def _password_matches(password: str, encoded: str) -> bool:
    """Verify pbkdf2_sha256$iterations$salt$hex-digest password hashes."""
    try:
        algorithm, iterations_raw, salt, expected = encoded.split("$", 3)
        iterations = int(iterations_raw)
        if algorithm != "pbkdf2_sha256" or not 100_000 <= iterations <= 2_000_000:
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations).hex()
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def _hash_password(password: str) -> str:
    salt = secrets.token_urlsafe(18)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), _PASSWORD_ITERATIONS
    ).hex()
    return f"pbkdf2_sha256${_PASSWORD_ITERATIONS}${salt}${digest}"


def _password_hash_looks_valid(encoded: str) -> bool:
    try:
        algorithm, iterations_raw, salt, digest = encoded.split("$", 3)
        iterations = int(iterations_raw)
        return algorithm == "pbkdf2_sha256" and 100_000 <= iterations <= 2_000_000 and bool(salt) and bool(re.fullmatch(r"[0-9a-f]{64}", digest))
    except (TypeError, ValueError):
        return False


def _admin_setup_ready() -> bool:
    return (
        bool(config.web_admin_username)
        and _password_hash_looks_valid(config.web_admin_password_hash)
        and len(config.admin_session_secret) >= 32
        and config.admin_session_secret != "replace_with_random_secret"
    )


def _make_admin_cookie(username: str) -> str:
    issued = int(time.time())
    payload = json.dumps(
        {"sub": username, "iat": issued, "exp": issued + config.admin_session_ttl, "jti": secrets.token_urlsafe(18)},
        separators=(",", ":"),
    ).encode("utf-8")
    body = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
    signature = hmac.new(config.admin_session_secret.encode(), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{signature}"


def _decode_admin_cookie(token: str) -> dict[str, Any] | None:
    try:
        body, signature = token.split(".", 1)
        expected = hmac.new(config.admin_session_secret.encode(), body.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return None
        raw = base64.urlsafe_b64decode(body + "=" * (-len(body) % 4))
        payload = json.loads(raw.decode("utf-8"))
        now = int(time.time())
        if (
            not isinstance(payload.get("sub"), str)
            or not payload.get("sub", "").strip()
            or len(payload.get("sub", "")) > 80
            or int(payload.get("exp", 0)) <= now
            or int(payload.get("iat", 0)) <= 0
            or int(payload.get("iat", 0)) > now + 60
            or not isinstance(payload.get("jti"), str)
            or len(payload.get("jti", "")) < 16
        ):
            return None
        return payload
    except (ValueError, TypeError, KeyError, json.JSONDecodeError):
        return None


def _check_admin_origin(request: Request) -> None:
    # Mutating web-admin API calls must carry a custom header, which a cross-site
    # HTML form cannot add. SameSite cookies provide an additional CSRF barrier.
    if request.method not in {"GET", "HEAD", "OPTIONS"} and request.headers.get("x-startum-admin") != "1":
        raise HTTPException(status_code=403, detail="Admin so‘rovi uchun himoya sarlavhasi talab qilinadi.")


def _client_fingerprint(client_ip: str) -> str:
    # Keyed hashing avoids keeping a raw client IP in the rate-limit table.
    return hashlib.sha256((config.admin_session_secret + ":" + (client_ip or "unknown")).encode("utf-8")).hexdigest()


async def require_admin(request: Request) -> str:
    if not _admin_setup_ready():
        raise HTTPException(status_code=503, detail="Veb-admin sozlanmagan. README dagi sozlash qadamlarini bajaring.")
    _check_admin_origin(request)
    token = request.cookies.get(ADMIN_COOKIE, "")
    session = _decode_admin_cookie(token) if token else None
    if not session:
        raise HTTPException(status_code=401, detail="Admin sessiyasi tugagan yoki mavjud emas.")
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    if not await db.web_admin_session_active(token_hash, str(session["sub"])):
        raise HTTPException(status_code=401, detail="Admin sessiyasi bekor qilingan yoki mavjud emas.")
    username = str(session["sub"])
    user = await db.web_admin(username)
    authoritative_role = await resolve_web_admin_role(db, user, config.ceo_owner_id)
    if authoritative_role is None:
        raise HTTPException(status_code=403, detail="Website Admin hisobi faol Telegram administrator bilan tasdiqlanmagan yoki roli mos emas.")
    return username


def require_roles(*allowed_roles: str):
    async def role_guard(actor: str = Depends(require_admin)) -> str:
        user = await db.web_admin(actor)
        authoritative_role = await resolve_web_admin_role(db, user, config.ceo_owner_id)
        if authoritative_role is None:
            raise HTTPException(status_code=401, detail="Admin hisobi faol emas yoki markaziy ruxsat yozuvi bilan mos emas.")
        if authoritative_role not in allowed_roles:
            raise HTTPException(status_code=403, detail="Bu amal uchun ruxsat yetarli emas.")
        return actor
    return role_guard


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    if request.url.path.startswith("/admin"):
        response.headers.setdefault("X-Robots-Tag", "noindex, nofollow, noarchive")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
            "connect-src 'self'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'",
        )
    if _production:
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


@app.get("/api/health")
async def health() -> dict[str, Any]:
    """Public liveness/readiness signal; exposes no secrets or private diagnostics."""
    try:
        row = await db.fetchone("PRAGMA quick_check")
        database_ok = bool(row and str(row[0]).lower() == "ok")
    except Exception as exc:
        logger.warning("Health check DB xatosi (%s).", type(exc).__name__)
        database_ok = False
    ready = database_ok and bool(getattr(app.state, "database_initialized", False))
    return {
        "status": "ok" if ready else "degraded",
        "service": "startum-backend",
        "database": "ok" if database_ok else "unavailable",
    }


@app.get("/api/admin/diagnostics")
async def admin_diagnostics(_: str = Depends(require_roles("ceo", "senior_admin"))) -> dict[str, Any]:
    """Protected operational checks without exposing credentials or user content."""
    database_state = "ok"
    try:
        integrity = await db.fetchone("PRAGMA quick_check")
        database_state = "ok" if integrity and str(integrity[0]).lower() == "ok" else "degraded"
    except Exception as exc:
        database_state = f"error:{type(exc).__name__}"
    pending = await db.notification_counts()
    bot = getattr(app.state, "bot", None)
    return {
        "database": database_state,
        "bot": "connected" if bot is not None else "not_connected",
        "application_notification_outbox": pending,
        "schema_version": int(getattr(db, "CURRENT_SCHEMA_VERSION", 0)),
        "environment": config.app_env,
    }


@app.get("/api/catalog")
async def catalog() -> dict[str, Any]:
    courses = await db.courses()
    teachers = await db.teachers()
    return {
        "courses": [
            {
                "id": c["id"], "slug": c["slug"], "kind": c["kind"],
                "name_uz": c["name_uz"], "name_ru": c["name_ru"], "name_en": c["name_en"],
                "description_uz": c["description_uz"], "description_ru": c["description_ru"],
                "description_en": c["description_en"], "icon": c["icon"],
                "active": c["active"], "created_at": c["created_at"],
            }
            for c in courses
        ],
        "teachers": [
            {"id": t["id"], "full_name": t["full_name"], "subject": t["subject"],
             "experience": t["experience"], "bio": t["bio"]}
            for t in teachers
        ],
    }


@app.get("/api/search")
async def public_search(
    q: str = Query(default="", min_length=1, max_length=80),
    kind: Literal["all", "courses", "teachers", "materials"] = "all",
    language: Literal["uz", "ru", "en"] = "uz",
    sort: Literal["relevance", "newest", "az"] = "relevance",
    limit: int = Query(default=10, ge=1, le=25),
    offset: int = Query(default=0, ge=0, le=5000),
) -> dict[str, Any]:
    """Paginated public search; only active catalogue and published public materials are discoverable."""
    query = " ".join(q.split())
    if len(query) < 2:
        return {"query": query, "items": [], "total": 0, "offset": offset, "limit": limit, "has_more": False}
    like = f"%{query}%"
    parts: list[tuple[str, str, tuple[Any, ...], str]] = []
    if kind in {"all", "courses"}:
        where = "active=1 AND (name_uz LIKE ? OR name_ru LIKE ? OR name_en LIKE ? OR description_uz LIKE ? OR description_ru LIKE ? OR description_en LIKE ?)"
        params = (like, like, like, like, like, like)
        total = await db.fetchone(f"SELECT COUNT(*) AS count FROM courses WHERE {where}", params)
        course_order = ("created_at DESC,id DESC" if sort == "newest" else
                        f"name_{language} COLLATE NOCASE,id" if sort == "az" else "id")
        rows = await db.fetchall(
            f"SELECT id,slug,kind,name_uz,name_ru,name_en,description_uz,description_ru,description_en,icon,created_at FROM courses WHERE {where} ORDER BY {course_order} LIMIT ? OFFSET ?",
            (*params, offset + limit, 0),
        )
        parts.append(("course", "courses", rows, str(int(total["count"] if total else 0))))
    if kind in {"all", "teachers"}:
        where = "active=1 AND (full_name LIKE ? OR subject LIKE ? OR bio LIKE ?)"
        params = (like, like, like)
        total = await db.fetchone(f"SELECT COUNT(*) AS count FROM teachers WHERE {where}", params)
        teacher_order = ("created_at DESC,id DESC" if sort == "newest" else
                         "full_name COLLATE NOCASE,id" if sort == "az" else "id DESC")
        rows = await db.fetchall(
            f"SELECT id,full_name,subject,experience,bio,created_at FROM teachers WHERE {where} ORDER BY {teacher_order} LIMIT ? OFFSET ?",
            (*params, offset + limit, 0),
        )
        parts.append(("teacher", "teachers", rows, str(int(total["count"] if total else 0))))
    if kind in {"all", "materials"}:
        where = "r.active=1 AND r.publication_status='published' AND c.active=1 AND r.group_id IS NULL AND (r.title LIKE ? OR r.description LIKE ? OR c.name_uz LIKE ? OR c.name_ru LIKE ? OR c.name_en LIKE ?)"
        params = (like, like, like, like, like)
        total = await db.fetchone(
            f"SELECT COUNT(*) AS count FROM learning_resources r JOIN courses c ON c.id=r.course_id WHERE {where}", params
        )
        material_order = "r.title COLLATE NOCASE,r.id" if sort == "az" else "r.created_at DESC,r.id DESC"
        rows = await db.fetchall(
            f"SELECT r.id,r.title,r.description,r.category,r.media_type,r.created_at,c.id AS course_id FROM learning_resources r JOIN courses c ON c.id=r.course_id WHERE {where} ORDER BY {material_order} LIMIT ? OFFSET ?",
            (*params, offset + limit, 0),
        )
        parts.append(("material", "materials", rows, str(int(total["count"] if total else 0))))

    # Keep the existing catalogue-first ordering and apply pagination after merging types.
    all_items: list[dict[str, Any]] = []
    type_totals: dict[str, int] = {}
    for item_type, key, rows, count in parts:
        type_totals[key] = int(count)
        for row in rows:
            if item_type == "course":
                all_items.append({"type": item_type, "id": int(row["id"]), "slug": row["slug"],
                                  "title": row[f"name_{language}"], "description": row[f"description_{language}"],
                                  "icon": row["icon"], "href": "#subjects", "_sort_at": str(row["created_at"]),
                                  "_sort_title": str(row[f"name_{language}"]).casefold()})
            elif item_type == "teacher":
                all_items.append({"type": item_type, "id": int(row["id"]), "title": row["full_name"],
                                  "description": row["subject"], "detail": row["experience"], "href": "#teachers",
                                  "_sort_at": str(row["created_at"]), "_sort_title": str(row["full_name"]).casefold()})
            else:
                all_items.append({"type": item_type, "id": int(row["id"]), "title": row["title"],
                                  "description": row["description"], "category": row["category"],
                                  "media_type": row["media_type"], "href": "#subjects",
                                  "_sort_at": str(row["created_at"]), "_sort_title": str(row["title"]).casefold()})
    if sort == "newest":
        all_items.sort(key=lambda item: item["_sort_at"], reverse=True)
    elif sort == "az":
        all_items.sort(key=lambda item: item["_sort_title"])
    total = sum(type_totals.values())
    page = all_items[offset:offset + limit]
    for item in page:
        item.pop("_sort_at", None)
        item.pop("_sort_title", None)
    return {"query": query, "items": page, "total": total, "offset": offset,
            "limit": limit, "sort": sort, "has_more": offset + len(page) < total,
            "type_totals": type_totals}


@app.get("/api/calendar")
async def public_calendar(
    language: Literal["uz", "ru", "en"] = "uz",
    limit: int = Query(default=30, ge=1, le=100),
) -> dict[str, Any]:
    rows = await db.calendar_events(language=language, public_only=True, limit=limit)
    return {"items": [dict(row) for row in rows], "total": len(rows), "timezone": "Asia/Tashkent"}


@app.post("/api/applications", status_code=201)
async def create_application(payload: ApplicationIn, request: Request) -> dict[str, Any]:
    client_ip = request.client.host if request.client else "unknown"
    fingerprint = _client_fingerprint(client_ip)
    if not await db.try_consume_rate_limit("application", fingerprint, 600, 5):
        raise HTTPException(status_code=429, detail="Juda ko‘p ariza yuborildi. 10 daqiqadan keyin qayta urinib ko‘ring.")

    course = await db.course_by_slug(payload.course)
    if not course:
        course = await db.fetchone(
            "SELECT * FROM courses WHERE active=1 AND name_uz=? LIMIT 1", (payload.course,)
        )
    if not course:
        raise HTTPException(status_code=404, detail="Kurs topilmadi.")

    tracking_code = secrets.token_urlsafe(12)
    tracking_token_hash = hashlib.sha256(tracking_code.encode("utf-8")).hexdigest()
    application_id, duplicate_id, creation_status = await db.create_web_application_if_new(
        name=payload.name,
        phone=payload.phone,
        telegram=payload.telegram,
        course_id=int(course["id"]),
        level=payload.level,
        preferred_time=payload.preferred_time,
        message=payload.message,
        within_seconds=600,
        tracking_token_hash=tracking_token_hash,
    )
    if creation_status == "duplicate":
        raise HTTPException(
            status_code=409,
            detail=f"Bu telefon raqami bilan yaqinda ariza yuborilgansiz (#{duplicate_id}). 10 daqiqadan keyin qayta urinib ko‘ring.",
        )
    if creation_status == "inactive" or application_id is None:
        raise HTTPException(status_code=404, detail="Tanlangan kurs hozir mavjud emas.")
    item = await db.web_application(application_id)

    notification_lines = [
        f"📝 <b>YANGI SAYT ARIZASI #{application_id}</b>",
        "",
        f"👤 Ism: <b>{escape(payload.name)}</b>",
        f"📱 Telefon: <code>{escape(payload.phone)}</code>",
        f"🔗 Telegram: {escape(payload.telegram or '-')}",
        f"📚 Kurs: <b>{escape(item['course_name'])}</b>",
    ]
    # Older clients may still send these optional legacy fields. Preserve them
    # when supplied, but the simplified public form no longer asks for them.
    if payload.level:
        notification_lines.append(f"🎚 Daraja: {escape(payload.level)}")
    if payload.preferred_time:
        notification_lines.append(f"🕒 Vaqt: {escape(payload.preferred_time)}")
    notification_lines.extend([
        f"💬 Izoh: {escape(payload.message or '-')}",
        "",
        "🌐 Manba: STARTUM website",
    ])
    notify = "\n".join(notification_lines)

    active_admin_ids = await db.active_admin_ids()
    queued = await db.enqueue_application_notifications(
        application_id, notify, active_admin_ids, source="website"
    )

    # Delivery is owned by the bot's durable retry worker. The public HTTP
    # response must never wait for Telegram/network availability.
    if not active_admin_ids or not queued:
        notification_status = "not_configured"
        message = "Ariza saqlandi, ammo faol Telegram administratorlari sozlanmagan."
    else:
        notification_status = "queued"
        message = "Ariza saqlandi. Telegram xabari navbatga qo‘yildi va bot qayta urinish qiladi."

    return {
        "ok": True,
        "id": application_id,
        "status": "new",
        "tracking_code": tracking_code,
        "notification_status": notification_status,
        "message": message,
    }


@app.post("/api/application-status")
async def application_status_lookup(payload: ApplicationStatusLookupIn, request: Request) -> dict[str, Any]:
    """Look up only public status fields using the one-time bearer code."""
    client_ip = request.client.host if request.client else "unknown"
    fingerprint = _client_fingerprint(client_ip)
    if not await db.try_consume_rate_limit("application_tracking", fingerprint, 60, 10):
        raise HTTPException(status_code=429, detail="Juda ko‘p urinish. Bir daqiqadan keyin qayta urinib ko‘ring.")

    token_hash = hashlib.sha256(payload.tracking_code.encode("utf-8")).hexdigest()
    item = await db.web_application_by_tracking_hash(token_hash)
    if not item:
        # Keep invalid and unknown codes indistinguishable.
        raise HTTPException(status_code=404, detail="Ariza topilmadi. Kuzatuv kodini tekshiring.")
    return {
        "ok": True,
        "status": str(item["status"]),
        "course": str(item["course_name"]),
        "created_at": str(item["created_at"]),
    }


@app.post("/api/admin/login")
async def admin_login(payload: AdminLoginIn, request: Request, response: Response) -> dict[str, Any]:
    _check_admin_origin(request)
    if not _admin_setup_ready():
        raise HTTPException(status_code=503, detail="Veb-admin sozlanmagan. README dagi sozlash qadamlarini bajaring.")
    client = request.client.host if request.client else "unknown"
    fingerprint = _client_fingerprint(client)
    account_fingerprint = hashlib.sha256(
        (config.admin_session_secret + ":account:" + payload.username.strip().casefold()).encode("utf-8")
    ).hexdigest()
    ip_allowed = await db.try_consume_rate_limit(
        "admin_login_ip", fingerprint, _LOGIN_WINDOW_SECONDS, _LOGIN_MAX_FAILURES
    )
    account_allowed = await db.try_consume_rate_limit(
        "admin_login_account", account_fingerprint, _LOGIN_WINDOW_SECONDS, _LOGIN_MAX_FAILURES
    )
    if not (ip_allowed and account_allowed):
        wait_minutes = max(1, (_LOGIN_WINDOW_SECONDS + 59) // 60)
        raise HTTPException(status_code=429, detail=f"Juda ko‘p urinish. {wait_minutes} daqiqadan keyin qayta urinib ko‘ring.")

    entered_username = payload.username.strip()
    admin_user = await db.web_admin(entered_username)
    hash_to_check = str(admin_user["password_hash"]) if admin_user else config.web_admin_password_hash
    valid_password = _password_matches(payload.password, hash_to_check)
    valid_user = bool(admin_user and int(admin_user["active"]))
    if not (valid_user and valid_password):
        raise HTTPException(status_code=401, detail="Login yoki parol noto‘g‘ri.")

    await db.clear_rate_limit("admin_login_ip", fingerprint)
    await db.clear_rate_limit("admin_login_account", account_fingerprint)
    username = str(admin_user["username"])
    token = _make_admin_cookie(username)
    decoded = _decode_admin_cookie(token)
    if not decoded:
        raise HTTPException(status_code=500, detail="Admin sessiyasini yaratib bo‘lmadi.")
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    await db.create_web_admin_session(token_hash, username, int(decoded["exp"]), client)
    # A Website Admin login completes the optional website-account link. Bot-only invitation
    # acceptance is handled independently by the exact Telegram user's /start update.
    try:
        verified_telegram_id = await db.mark_telegram_admin_verified(username)
    except Exception as exc:
        await db.revoke_web_admin_session(token_hash)
        logger.exception("Telegram admin linkage verification failed (%s).", type(exc).__name__)
        raise HTTPException(status_code=500, detail="Administrator ruxsatlarini faollashtirib bo‘lmadi.") from exc
    if str(admin_user["role"]) != "ceo" and verified_telegram_id is None:
        await db.revoke_web_admin_session(token_hash)
        raise HTTPException(
            status_code=403,
            detail="Bu Website Admin hisobi OWNER tasdiqlagan faol Telegram admin ID bilan bog‘lanmagan. CEO Telegram taklifini yoki Website Admin bog‘lanishini tekshirishi kerak.",
        )
    if verified_telegram_id is not None:
        await sync_admin_commands(getattr(app.state, "bot", None), verified_telegram_id, str(admin_user["role"]))
    await db.write_admin_audit(username, "login", details="Muvaffaqiyatli kirish", ip_address=client)
    response.set_cookie(
        key=ADMIN_COOKIE,
        value=token,
        max_age=config.admin_session_ttl,
        httponly=True,
        secure=config.admin_cookie_secure,
        samesite="strict",
        path="/",
    )
    role = str(admin_user["role"])
    return {"ok": True, "username": username, "role": role, "role_label": _ROLE_LABELS.get(role, role), "expires_in": config.admin_session_ttl}


@app.post("/api/admin/logout")
async def admin_logout(request: Request, response: Response) -> dict[str, bool]:
    _check_admin_origin(request)
    token = request.cookies.get(ADMIN_COOKIE, "")
    session = _decode_admin_cookie(token) if token else None
    if session:
        await db.revoke_web_admin_session(hashlib.sha256(token.encode("utf-8")).hexdigest())
        await db.write_admin_audit(str(session["sub"]), "logout", details="Tizimdan chiqish", ip_address=request.client.host if request.client else "")
    response.delete_cookie(ADMIN_COOKIE, path="/", httponly=True, secure=config.admin_cookie_secure, samesite="strict")
    return {"ok": True}


@app.get("/api/admin/session")
async def admin_session(username: str = Depends(require_admin)) -> dict[str, Any]:
    user = await db.web_admin(username)
    role = str(user["role"]) if user else ""
    return {"authenticated": True, "username": username, "role": role, "role_label": _ROLE_LABELS.get(role, role)}


@app.get("/api/admin/overview")
async def admin_overview(_: str = Depends(require_admin)) -> dict[str, Any]:
    return await db.stats()


@app.get("/api/admin/users")
async def admin_users(
    q: str = Query(default="", max_length=120),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=1_000_000),
    _: str = Depends(require_roles("ceo", "senior_admin", "junior_admin")),
) -> dict[str, Any]:
    search = q.strip()
    rows = await db.search_users(search, limit=limit, offset=offset)
    total = await db.count_users(search)
    return {
        "items": [dict(row) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": offset + len(rows) < total,
    }


@app.get("/api/admin/users/{user_id}")
async def admin_user_detail(
    user_id: int,
    _: str = Depends(require_roles("ceo", "senior_admin", "junior_admin")),
) -> dict[str, Any]:
    if user_id < 1:
        raise HTTPException(status_code=422, detail="Foydalanuvchi ID noto‘g‘ri.")
    details = await db.user_details(user_id)
    if not details:
        raise HTTPException(status_code=404, detail="Foydalanuvchi topilmadi.")
    return details


@app.patch("/api/admin/users/{user_id}/status")
async def admin_set_user_status(
    user_id: int,
    payload: UserModerationIn,
    request: Request,
    actor: str = Depends(require_roles("ceo", "senior_admin")),
) -> dict[str, Any]:
    if user_id < 1:
        raise HTTPException(status_code=422, detail="Foydalanuvchi ID noto‘g‘ri.")
    if payload.status == "active" and payload.duration_minutes is not None:
        raise HTTPException(status_code=422, detail="Tiklash amalida muddat berilmaydi.")
    try:
        result = await db.moderate_user(
            user_id,
            action="suspend" if payload.status == "suspended" else "restore",
            actor=actor,
            reason=payload.reason,
            duration_minutes=payload.duration_minutes,
            ip_address=request.client.host if request.client else "",
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if detail == "Foydalanuvchi topilmadi." else 409
        raise HTTPException(status_code=status_code, detail=detail) from exc
    return {"ok": True, **result}


@app.get("/api/admin/messages")
async def admin_messages(
    status: Literal["new", "answered"] | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    q: str = Query(default="", max_length=120),
    _: str = Depends(require_admin),
) -> dict[str, Any]:
    """Shared read-only support inbox for Web Admin; replies remain in the Telegram Admin workflow."""
    rows = await db.message_list(limit=limit, status=status, search=q.strip())
    return {"items": [dict(row) for row in rows], "limit": limit}


@app.get("/api/admin/applications")
async def admin_applications(
    source: Literal["website", "bot"] = "website",
    status: Literal["new", "in_review", "contacted", "accepted", "rejected", "in_progress", "closed"] | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=1_000_000),
    q: str = Query(default="", max_length=120),
    _: str = Depends(require_admin),
) -> dict[str, Any]:
    q = q.strip()
    if source == "website":
        rows = await db.web_applications(status=status, limit=limit, offset=offset, search=q)
        total = await db.count_web_applications(status=status, search=q)
    else:
        rows = await db.applications(status=status, limit=limit, offset=offset, search=q)
        total = await db.count_applications(status=status, search=q)
    items = []
    for row in rows:
        item = dict(row)
        item.pop("tracking_token_hash", None)
        items.append(item)
    return {"source": source, "items": items, "total": total, "limit": limit, "offset": offset, "has_more": offset + len(rows) < total}


@app.get("/api/admin/applications/{source}/{application_id}/history")
async def admin_application_status_history(
    source: Literal["website", "bot"], application_id: int,
    _: str = Depends(require_admin),
) -> dict[str, Any]:
    if application_id < 1:
        raise HTTPException(status_code=422, detail="Ariza ID noto‘g‘ri.")
    item = await db.web_application(application_id) if source == "website" else await db.application(application_id)
    if not item:
        raise HTTPException(status_code=404, detail="Ariza topilmadi.")
    history = await db.application_status_history(source, application_id)
    return {"items": [dict(row) for row in history]}


@app.get("/api/admin/applications/export.csv")
async def admin_export_applications(
    source: Literal["website", "bot"] = "website",
    status: Literal["new", "in_review", "contacted", "accepted", "rejected", "in_progress", "closed"] | None = None,
    q: str = Query(default="", max_length=120),
    actor: str = Depends(require_roles("ceo", "senior_admin")),
) -> Response:
    """Export a bounded, filtered application snapshot for authorized senior admins."""
    search = q.strip()
    total = (
        await db.count_web_applications(status=status, search=search)
        if source == "website"
        else await db.count_applications(status=status, search=search)
    )
    export_limit = 5000
    row_limit = min(total, export_limit)
    rows: list[dict[str, Any]] = []
    offset = 0
    while offset < row_limit:
        page_size = min(100, row_limit - offset)
        page = (
            await db.web_applications(status=status, limit=page_size, offset=offset, search=search)
            if source == "website"
            else await db.applications(status=status, limit=page_size, offset=offset, search=search)
        )
        if not page:
            break
        rows.extend(dict(item) for item in page)
        offset += len(page)
        if len(page) < page_size:
            break

    def safe_cell(value: Any) -> str:
        text = "" if value is None else str(value)
        # Neutralize spreadsheet formula prefixes without changing ordinary text.
        if text.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")):
            return "'" + text
        return text

    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(("manba", "ariza_id", "sana", "ism_familiya", "telefon", "telegram", "kurs", "daraja", "holat"))
    for item in rows:
        telegram = (
            item.get("telegram_username") or ""
            if source == "website"
            else (f"@{item['username']}" if item.get("username") else item.get("telegram_id", ""))
        )
        writer.writerow(safe_cell(value) for value in (
            source,
            item.get("id"),
            item.get("created_at"),
            item.get("full_name"),
            item.get("phone"),
            telegram,
            item.get("course_name"),
            item.get("level"),
            item.get("status"),
        ))

    generated = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    filename = f"startum-arizalar-{source}-{generated}.csv"
    await db.write_admin_audit(
        actor,
        "applications_exported",
        entity_type=source,
        details=f"rows={len(rows)}; truncated={total > export_limit}",
    )
    return Response(
        content="\ufeff" + buffer.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
            "X-Export-Count": str(len(rows)),
            "X-Export-Truncated": "true" if total > export_limit else "false",
        },
    )


@app.get("/api/admin/export/{dataset}.csv")
async def admin_export_dataset(
    dataset: Literal["courses", "teachers", "groups", "attendance", "homework", "quiz-results", "students"],
    request: Request,
    q: str = Query(default="", max_length=100),
    limit: int = Query(default=5000, ge=1, le=5000),
    actor: str = Depends(require_roles("ceo", "senior_admin")),
) -> Response:
    """Bounded CSV exports. Personal student records require CEO authorization."""
    role_user = await db.web_admin(actor)
    if dataset == "students" and (not role_user or role_user["role"] != "ceo"):
        raise HTTPException(status_code=403, detail="O‘quvchi shaxsiy ma’lumotlarini eksport qilish uchun CEO ruxsati kerak.")
    search = f"%{' '.join(q.split())}%"
    queries: dict[str, tuple[str, tuple[Any, ...], tuple[str, ...]]] = {
        "courses": ("SELECT id,slug,kind,name_uz,name_ru,name_en,active,created_at FROM courses WHERE active=1 AND (name_uz LIKE ? OR name_ru LIKE ? OR name_en LIKE ?) ORDER BY id LIMIT ?", (search, search, search, limit), ("id","slug","kind","name_uz","name_ru","name_en","active","created_at")),
        "teachers": ("SELECT id,full_name,subject,experience,active,created_at FROM teachers WHERE active=1 AND (full_name LIKE ? OR subject LIKE ?) ORDER BY id LIMIT ?", (search, search, limit), ("id","full_name","subject","experience","active","created_at")),
        "groups": ("SELECT g.id,g.name,c.name_uz AS course,g.schedule_text,g.status,COUNT(gm.user_id) AS active_students,g.created_at FROM education_groups g JOIN courses c ON c.id=g.course_id LEFT JOIN group_memberships gm ON gm.group_id=g.id AND gm.status='active' WHERE g.name LIKE ? GROUP BY g.id ORDER BY g.id LIMIT ?", (search, limit), ("id","name","course","schedule_text","status","active_students","created_at")),
        "attendance": ("SELECT ar.id,g.name AS group_name,u.telegram_id,u.first_name,u.last_name,s.session_date,s.lesson_ref,ar.status,ar.note,ar.marked_at FROM attendance_records ar JOIN attendance_sessions s ON s.id=ar.session_id JOIN education_groups g ON g.id=s.group_id JOIN users u ON u.id=ar.user_id WHERE g.name LIKE ? OR u.first_name LIKE ? OR u.last_name LIKE ? ORDER BY s.session_date DESC LIMIT ?", (search, search, search, limit), ("id","group_name","telegram_id","first_name","last_name","session_date","lesson_ref","status","note","marked_at")),
        "homework": ("SELECT h.id,h.title,g.name AS group_name,c.name_uz AS course,h.status,h.deadline_at,h.created_at FROM homework h JOIN education_groups g ON g.id=h.group_id JOIN courses c ON c.id=h.course_id WHERE h.title LIKE ? OR g.name LIKE ? ORDER BY h.created_at DESC LIMIT ?", (search, search, limit), ("id","title","group_name","course","status","deadline_at","created_at")),
        "quiz-results": ("SELECT qa.id,u.telegram_id,u.first_name,u.last_name,c.name_uz AS course,r.title,qa.score,qa.total,qa.percent,qa.duration_seconds,qa.completed_at FROM quiz_attempts qa JOIN users u ON u.id=qa.user_id JOIN courses c ON c.id=qa.course_id JOIN learning_resources r ON r.id=qa.resource_id WHERE u.first_name LIKE ? OR c.name_uz LIKE ? OR r.title LIKE ? ORDER BY qa.completed_at DESC LIMIT ?", (search, search, search, limit), ("id","telegram_id","first_name","last_name","course","title","score","total","percent","duration_seconds","completed_at")),
        "students": ("SELECT u.id,u.telegram_id,u.first_name,u.last_name,u.username,u.language,u.account_status,u.created_at FROM users u WHERE u.first_name LIKE ? OR u.last_name LIKE ? OR CAST(u.telegram_id AS TEXT) LIKE ? ORDER BY u.id LIMIT ?", (search, search, search, limit), ("id","telegram_id","first_name","last_name","username","language","account_status","created_at")),
    }
    sql, params, columns = queries[dataset]
    rows = await db.fetchall(sql, params)
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(columns)
    for row in rows:
        values = []
        for key in columns:
            value = "" if row[key] is None else str(row[key])
            if value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")):
                value = "'" + value
            values.append(value)
        writer.writerow(values)
    await db.write_admin_audit(actor, "dataset_exported", entity_type=dataset, details=f"rows={len(rows)};limit={limit}",
                               ip_address=request.client.host if request.client else "")
    filename = f"startum-{dataset}-{time.strftime('%Y%m%d-%H%M%S', time.gmtime())}.csv"
    return Response(content="\ufeff" + buffer.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"',
                             "Cache-Control": "no-store", "X-Export-Count": str(len(rows))})


@app.patch("/api/admin/applications/{source}/{application_id}")
async def admin_update_application(
    source: Literal["website", "bot"],
    application_id: int,
    payload: ApplicationStatusIn,
    request: Request,
    actor: str = Depends(require_admin),
) -> dict[str, Any]:
    if payload.status not in _ALLOWED_STATUSES:
        raise HTTPException(status_code=422, detail="Ariza holati noto‘g‘ri.")
    if application_id < 1:
        raise HTTPException(status_code=422, detail="Ariza ID noto‘g‘ri.")
    if source == "website":
        item = await db.web_application(application_id)
        if not item:
            raise HTTPException(status_code=404, detail="Sayt arizasi topilmadi.")
        recipient_id = 0
        identity_provider = item["identity_provider"] if "identity_provider" in item.keys() else ""
        external_user_id = item["external_user_id"] if "external_user_id" in item.keys() else ""
        if str(identity_provider or "").lower() == "telegram":
            try:
                recipient_id = int(external_user_id or 0)
            except (TypeError, ValueError):
                recipient_id = 0
    else:
        item = await db.application(application_id)
        if not item:
            raise HTTPException(status_code=404, detail="Bot arizasi topilmadi.")
        recipient_id = int(item["telegram_id"] or 0)

    change = await db.change_application_status(
        source, application_id, payload.status,
        actor=actor, ip_address=request.client.host if request.client else "",
    )
    if not change:
        raise HTTPException(status_code=404, detail="Ariza topilmadi.")
    old_status = change["old_status"]
    if old_status != payload.status and recipient_id > 0:
        await db.enqueue_application_status_notification(
            source=source,
            application_id=application_id,
            recipient_telegram_id=recipient_id,
            status=payload.status,
            message_text=(
                f"📌 <b>Ariza #{application_id}</b> holati yangilandi: "
                f"<b>{escape(application_status_label(payload.status))}</b>"
            ),
        )
    await db.write_admin_audit(
        actor, "application_status_updated", entity_type=source, entity_id=application_id,
        details=f"{old_status}->{payload.status}", ip_address=request.client.host if request.client else "",
    )
    return {"ok": True, "source": source, "id": application_id, "status": payload.status}


@app.post("/api/admin/courses", status_code=201)
async def admin_create_course(payload: CourseIn, request: Request, actor: str = Depends(require_roles("ceo", "senior_admin"))) -> dict[str, Any]:
    try:
        course_id = await db.add_course(
            kind=payload.kind, name_uz=payload.name_uz, name_ru=payload.name_ru, name_en=payload.name_en,
            description_uz=payload.description_uz, description_ru=payload.description_ru,
            description_en=payload.description_en, icon=payload.icon or "📚",
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await db.write_admin_audit(
        actor, "course_created", entity_type="course", entity_id=course_id,
        details=f"kind={payload.kind}; name_uz={payload.name_uz}",
        ip_address=request.client.host if request.client else "",
    )
    return {"ok": True, "id": course_id, "slug": (await db.course(course_id))["slug"]}


@app.post("/api/admin/teachers", status_code=201)
async def admin_create_teacher(payload: TeacherIn, request: Request, actor: str = Depends(require_roles("ceo", "senior_admin"))) -> dict[str, Any]:
    teacher_id = await db.add_teacher(payload.full_name, payload.subject, payload.experience, payload.bio)
    await db.write_admin_audit(
        actor, "teacher_created", entity_type="teacher", entity_id=teacher_id,
        details=f"subject={payload.subject}", ip_address=request.client.host if request.client else "",
    )
    return {"ok": True, "id": teacher_id}


@app.get("/api/admin/quiz-results")
async def admin_quiz_results(
    limit: int = Query(default=100, ge=1, le=200),
    course_id: int | None = Query(default=None, ge=1),
    resource_id: int | None = Query(default=None, ge=1),
    _: str = Depends(require_roles("ceo", "senior_admin")),
) -> dict[str, Any]:
    rows = await db.quiz_attempts(limit=limit, course_id=course_id, resource_id=resource_id)
    return {"items": [dict(row) for row in rows], "total": len(rows), "limit": limit, "course_id": course_id, "resource_id": resource_id}


@app.get("/api/admin/audit")
async def admin_audit(limit: int = 20, _: str = Depends(require_roles("ceo", "senior_admin"))) -> dict[str, Any]:
    rows = await db.admin_audit_entries(max(1, min(limit, 100)))
    return {"items": [dict(row) for row in rows]}


@app.get("/api/admin/catalog")
async def admin_catalog(_: str = Depends(require_admin)) -> dict[str, Any]:
    courses = await db.courses(include_inactive=True)
    teachers = await db.teachers(include_inactive=True)
    return {
        "courses": [dict(row) for row in courses],
        "teachers": [dict(row) for row in teachers],
    }


@app.patch("/api/admin/courses/{course_id}")
async def admin_update_course(
    course_id: int, payload: CourseIn, request: Request,
    actor: str = Depends(require_roles("ceo", "senior_admin")),
) -> dict[str, Any]:
    if course_id < 1:
        raise HTTPException(status_code=422, detail="Kurs ID noto‘g‘ri.")
    try:
        updated = await db.update_course(course_id, payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not updated:
        raise HTTPException(status_code=404, detail="Kurs topilmadi.")
    await db.write_admin_audit(
        actor, "course_updated", entity_type="course", entity_id=course_id,
        details=f"name_uz={payload.name_uz}", ip_address=request.client.host if request.client else "",
    )
    return {"ok": True, "id": course_id, "name_uz": payload.name_uz}


@app.patch("/api/admin/teachers/{teacher_id}")
async def admin_update_teacher(
    teacher_id: int, payload: TeacherIn, request: Request,
    actor: str = Depends(require_roles("ceo", "senior_admin")),
) -> dict[str, Any]:
    if teacher_id < 1:
        raise HTTPException(status_code=422, detail="Ustoz ID noto‘g‘ri.")
    updated = await db.update_teacher(teacher_id, payload.model_dump())
    if not updated:
        raise HTTPException(status_code=404, detail="Ustoz topilmadi.")
    await db.write_admin_audit(
        actor, "teacher_updated", entity_type="teacher", entity_id=teacher_id,
        details=f"full_name={payload.full_name}", ip_address=request.client.host if request.client else "",
    )
    return {"ok": True, "id": teacher_id, "full_name": payload.full_name}


@app.patch("/api/admin/courses/{course_id}/active")
async def admin_set_course_active(
    course_id: int, payload: CatalogActiveIn, request: Request,
    actor: str = Depends(require_roles("ceo", "senior_admin")),
) -> dict[str, Any]:
    if course_id < 1:
        raise HTTPException(status_code=422, detail="Kurs ID noto‘g‘ri.")
    if not await db.set_course_active(course_id, payload.active):
        exists = await db.fetchone("SELECT id FROM courses WHERE id=?", (course_id,))
        if not exists:
            raise HTTPException(status_code=404, detail="Kurs topilmadi.")
    await db.write_admin_audit(actor, "course_activation_changed", entity_type="course", entity_id=course_id,
                               details=f"active={payload.active}", ip_address=request.client.host if request.client else "")
    return {"ok": True, "id": course_id, "active": payload.active}


@app.patch("/api/admin/teachers/{teacher_id}/active")
async def admin_set_teacher_active(
    teacher_id: int, payload: CatalogActiveIn, request: Request,
    actor: str = Depends(require_roles("ceo", "senior_admin")),
) -> dict[str, Any]:
    if teacher_id < 1:
        raise HTTPException(status_code=422, detail="Ustoz ID noto‘g‘ri.")
    if not await db.set_teacher_active(teacher_id, payload.active):
        exists = await db.fetchone("SELECT id FROM teachers WHERE id=?", (teacher_id,))
        if not exists:
            raise HTTPException(status_code=404, detail="Ustoz topilmadi.")
    await db.write_admin_audit(actor, "teacher_activation_changed", entity_type="teacher", entity_id=teacher_id,
                               details=f"active={payload.active}", ip_address=request.client.host if request.client else "")
    return {"ok": True, "id": teacher_id, "active": payload.active}


@app.get("/api/resources")
async def public_learning_resources(
    course_id: int = Query(gt=0),
    category: Literal["book", "vocabulary", "movie", "music", "quiz"] | None = None,
) -> dict[str, Any]:
    if not await db.fetchone("SELECT id FROM courses WHERE id=? AND active=1", (course_id,)):
        raise HTTPException(status_code=404, detail="Yo‘nalish topilmadi.")
    # Public responses expose only approved, course-wide materials. Group-targeted
    # and pending moderation records remain available through the bot's guarded flows.
    where = [
        "r.course_id=?", "r.active=1", "r.publication_status='published'",
        "r.group_id IS NULL", "c.active=1",
    ]
    params: list[Any] = [course_id]
    if category:
        where.append("r.category=?")
        params.append(category)
    params.append(100)
    rows = await db.fetchall(
        "SELECT r.id,r.category,r.course_id,r.title,r.description,r.content,r.media_type,"
        "r.created_at,r.publication_status,r.level,r.file_name,r.file_mime,r.file_size,"
        "c.name_uz AS course_name,c.slug AS course_slug "
        "FROM learning_resources r JOIN courses c ON c.id=r.course_id WHERE "
        + " AND ".join(where) + " ORDER BY r.id DESC LIMIT ?",
        tuple(params),
    )
    items = [dict(row) for row in rows]
    return {"items": items, "total": len(items)}


@app.get("/api/admin/resources")
async def admin_learning_resources(_: str = Depends(require_admin)) -> dict[str, Any]:
    rows = await db.learning_resources(include_inactive=True, limit=200)
    items = []
    for row in rows:
        item = dict(row)
        item.pop("telegram_file_id", None)
        items.append(item)
    return {"items": items}


@app.post("/api/admin/resources", status_code=201)
async def admin_create_learning_resource(
    payload: LearningResourceIn, request: Request,
    actor: str = Depends(require_roles("ceo", "senior_admin")),
) -> dict[str, Any]:
    if payload.media_type == "url" and not re.match(r"^https?://", payload.content, flags=re.IGNORECASE):
        raise HTTPException(status_code=422, detail="Havola http:// yoki https:// bilan boshlanishi kerak.")
    try:
        resource_id = await db.add_learning_resource(
            category=payload.category, course_id=payload.course_id, title=payload.title,
            description=payload.description, content=payload.content, media_type=payload.media_type,
            created_by_telegram_id=0, created_by_role="web_admin",
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await db.write_admin_audit(
        actor, "learning_resource_created", entity_type="learning_resource", entity_id=resource_id,
        details=f"category={payload.category}; course_id={payload.course_id}",
        ip_address=request.client.host if request.client else "",
    )
    return {"ok": True, "id": resource_id}


@app.patch("/api/admin/resources/{resource_id}/active")
async def admin_set_learning_resource_active(
    resource_id: int, payload: CatalogActiveIn, request: Request,
    actor: str = Depends(require_roles("ceo", "senior_admin")),
) -> dict[str, Any]:
    if resource_id < 1:
        raise HTTPException(status_code=422, detail="Material ID noto‘g‘ri.")
    changed = await db.set_learning_resource_active(resource_id, payload.active)
    if not changed:
        raise HTTPException(status_code=404, detail="Material topilmadi.")
    await db.write_admin_audit(
        actor, "learning_resource_activation_changed", entity_type="learning_resource", entity_id=resource_id,
        details=f"active={payload.active}", ip_address=request.client.host if request.client else "",
    )
    return {"ok": True, "id": resource_id, "active": payload.active}


@app.get("/api/admin/education/groups")
async def admin_education_groups(
    limit: int = Query(default=150, ge=1, le=200),
    _: str = Depends(require_roles("ceo", "senior_admin")),
) -> dict[str, Any]:
    rows = await db.education_groups(active_only=False, limit=limit)
    assignments = await db.fetchall(
        "SELECT tsa.id,tsa.telegram_id,tsa.course_id,tsa.group_id,tsa.active,c.name_uz AS course_name,g.name AS group_name "
        "FROM teacher_subject_assignments tsa JOIN courses c ON c.id=tsa.course_id "
        "LEFT JOIN education_groups g ON g.id=tsa.group_id WHERE tsa.active=1 ORDER BY tsa.id DESC LIMIT 300"
    )
    return {"items": [dict(row) for row in rows], "assignments": [dict(row) for row in assignments], "total": len(rows)}


@app.post("/api/admin/education/groups", status_code=201)
async def admin_create_education_group(
    payload: EducationGroupCreateIn, request: Request,
    actor: str = Depends(require_roles("ceo", "senior_admin")),
) -> dict[str, Any]:
    admin_record = await db.web_admin(actor)
    if not admin_record:
        raise HTTPException(status_code=401, detail="Admin hisobi topilmadi.")
    created_by = int(admin_record["telegram_id"] or config.ceo_owner_id)
    try:
        group = await db.create_education_group(payload.name, payload.course_id, payload.schedule_text, created_by)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await db.write_admin_audit(actor, "education_group_created_from_web", entity_type="education_group",
                               entity_id=int(group["id"]), details=f"course_id={payload.course_id};name={payload.name}",
                               ip_address=request.client.host if request.client else "")
    return {"ok": True, **group}


@app.post("/api/admin/education/teacher-assignments", status_code=201)
async def admin_assign_education_teacher(
    payload: EducationGroupTeacherIn, request: Request,
    actor: str = Depends(require_roles("ceo", "senior_admin")),
) -> dict[str, Any]:
    admin_record = await db.web_admin(actor)
    if not admin_record:
        raise HTTPException(status_code=401, detail="Admin hisobi topilmadi.")
    user = await db.fetchone("SELECT telegram_id FROM users WHERE telegram_id=? AND account_status='active'", (payload.telegram_id,))
    if not user:
        raise HTTPException(status_code=404, detail="Ustoz Telegram botda /start orqali ro‘yxatdan o‘tmagan.")
    group = await db.fetchone("SELECT id,course_id FROM education_groups WHERE id=? AND status='active'", (payload.group_id,))
    if not group:
        raise HTTPException(status_code=404, detail="Faol guruh topilmadi.")
    created_by = int(admin_record["telegram_id"] or config.ceo_owner_id)
    try:
        assignment_id = await db.assign_teacher_subject(payload.telegram_id, int(group["course_id"]), created_by, payload.group_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await db.write_admin_audit(actor, "teacher_assigned_to_education_group", entity_type="teacher_subject_assignment",
                               entity_id=assignment_id, details=f"teacher={payload.telegram_id};group={payload.group_id}",
                               ip_address=request.client.host if request.client else "")
    return {"ok": True, "assignment_id": assignment_id, "telegram_id": payload.telegram_id, "group_id": payload.group_id}


@app.delete("/api/admin/education/teacher-assignments/{assignment_id}")
async def admin_revoke_education_teacher(
    assignment_id: int, request: Request,
    actor: str = Depends(require_roles("ceo", "senior_admin")),
) -> dict[str, bool]:
    admin_record = await db.web_admin(actor)
    if not admin_record:
        raise HTTPException(status_code=401, detail="Admin hisobi topilmadi.")
    changed = await db.revoke_teacher_assignment(assignment_id, int(admin_record["telegram_id"] or config.ceo_owner_id))
    if not changed:
        raise HTTPException(status_code=404, detail="Faol tayinlov topilmadi.")
    await db.write_admin_audit(actor, "teacher_assignment_revoked_from_web", entity_type="teacher_subject_assignment",
                               entity_id=assignment_id, ip_address=request.client.host if request.client else "")
    return {"ok": True}


@app.get("/api/admin/calendar")
async def admin_calendar_events(
    limit: int = Query(default=100, ge=1, le=200),
    _: str = Depends(require_roles("ceo", "senior_admin")),
) -> dict[str, Any]:
    # The manager needs all translation columns; this route is role-protected.
    full = await db.fetchall(
        "SELECT e.*,g.name AS group_name FROM academic_calendar_events e "
        "LEFT JOIN education_groups g ON g.id=e.target_group_id ORDER BY e.starts_at DESC LIMIT ?", (limit,)
    )
    return {"items": [dict(item) for item in full], "total": len(full)}


@app.post("/api/admin/calendar", status_code=201)
async def admin_create_calendar_event(
    payload: CalendarEventIn, request: Request,
    actor: str = Depends(require_roles("ceo", "senior_admin")),
) -> dict[str, Any]:
    try:
        event_id = await db.create_calendar_event(
            titles=payload.titles, descriptions=payload.descriptions, category=payload.category,
            starts_at=payload.starts_at, ends_at=payload.ends_at, location=payload.location,
            target_group_id=payload.target_group_id, status=payload.status,
            reminder_24h=payload.reminder_24h, created_by=int((await db.web_admin(actor))["telegram_id"] or config.ceo_owner_id),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await db.write_admin_audit(actor, "calendar_event_created", entity_type="calendar_event", entity_id=event_id,
                               details=f"category={payload.category};status={payload.status}",
                               ip_address=request.client.host if request.client else "")
    return {"ok": True, "id": event_id}


@app.patch("/api/admin/calendar/{event_id}")
async def admin_update_calendar_event(
    event_id: int, payload: CalendarEventIn, request: Request,
    actor: str = Depends(require_roles("ceo", "senior_admin")),
) -> dict[str, Any]:
    try:
        changed = await db.update_calendar_event(
            event_id, titles=payload.titles, descriptions=payload.descriptions, category=payload.category,
            starts_at=payload.starts_at, ends_at=payload.ends_at, location=payload.location,
            target_group_id=payload.target_group_id, status=payload.status, reminder_24h=payload.reminder_24h,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not changed:
        raise HTTPException(status_code=404, detail="Tadbir topilmadi.")
    await db.write_admin_audit(actor, "calendar_event_updated", entity_type="calendar_event", entity_id=event_id,
                               details=f"status={payload.status}",
                               ip_address=request.client.host if request.client else "")
    return {"ok": True, "id": event_id}


@app.get("/api/admin/notifications")
async def admin_notifications(
    status: Literal["pending", "sent", "failed"] | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
    _: str = Depends(require_roles("ceo", "senior_admin")),
) -> dict[str, Any]:
    rows = await db.notifications(status=status, limit=limit)
    return {"items": [dict(row) for row in rows], "total": len(rows)}


@app.patch("/api/admin/notifications/{notification_id}/retry")
async def admin_retry_notification(
    notification_id: int, request: Request,
    actor: str = Depends(require_roles("ceo", "senior_admin")),
) -> dict[str, Any]:
    if notification_id < 1:
        raise HTTPException(status_code=422, detail="Bildirishnoma ID noto‘g‘ri.")
    if not await db.retry_notification(notification_id):
        raise HTTPException(status_code=404, detail="Qayta yuboriladigan xabar topilmadi yoki allaqachon yuborilgan.")
    delivery = {"sent": 0, "failed": 0, "checked": 0}
    bot = getattr(app.state, "bot", None)
    if bot:
        delivery = await deliver_pending_notifications(bot, db, limit=200)
    await db.write_admin_audit(
        actor, "telegram_notification_retry", entity_type="notification", entity_id=notification_id,
        details=f"sent={delivery['sent']}; failed={delivery['failed']}; checked={delivery['checked']}",
        ip_address=request.client.host if request.client else "",
    )
    return {"ok": True, "id": notification_id, "delivery": delivery}


@app.post("/api/admin/password/change")
async def admin_change_own_password(
    payload: AdminPasswordChangeIn, request: Request,
    actor: str = Depends(require_roles("ceo", "senior_admin", "junior_admin")),
) -> dict[str, bool]:
    user = await db.web_admin(actor)
    if not user:
        raise HTTPException(status_code=401, detail="Admin hisobi topilmadi.")
    if str(user["role"]) == "ceo" or str(user["created_by"]) == "bootstrap":
        raise HTTPException(status_code=409, detail="CEO paroli backend/.env dagi WEB_ADMIN_PASSWORD_HASH orqali o‘zgartiriladi.")
    if not _password_matches(payload.current_password, str(user["password_hash"])):
        raise HTTPException(status_code=401, detail="Joriy parol noto‘g‘ri.")
    if payload.new_password == payload.current_password:
        raise HTTPException(status_code=422, detail="Yangi parol joriy paroldan farq qilishi kerak.")
    try:
        await db.rotate_web_admin_password(actor, _hash_password(payload.new_password), allow_pending=False)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if user["telegram_id"] is not None:
        await sync_admin_commands(getattr(app.state, "bot", None), int(user["telegram_id"]), None)
    await db.write_admin_audit(actor, "web_admin_password_changed", entity_type="web_admin",
                               details="Admin o‘z parolini almashtirdi",
                               ip_address=request.client.host if request.client else "")
    return {"ok": True}


@app.get("/api/admin/accounts")
async def admin_list_accounts(_: str = Depends(require_roles("ceo"))) -> dict[str, Any]:
    rows = await db.web_admins()
    items = []
    for row in rows:
        item = dict(row)
        item["is_bootstrap"] = item["username"].casefold() == config.web_admin_username.casefold()
        items.append(item)
    return {"items": items}


@app.get("/api/admin/telegram-admins")
async def admin_list_telegram_accounts(_: str = Depends(require_roles("ceo"))) -> dict[str, Any]:
    """List the canonical Bot admin assignments and their optional Website Admin links."""
    rows = await db.telegram_admin_accounts()
    return {"items": [dict(row) for row in rows]}


@app.post("/api/admin/telegram-admins/{telegram_id}/invite")
async def admin_reissue_telegram_invitation(
    telegram_id: int, request: Request,
    actor: str = Depends(require_roles("ceo")),
) -> dict[str, Any]:
    actor_user = await db.web_admin(actor)
    if not actor_user or telegram_id in {config.ceo_owner_id, config.owner_telegram_id}:
        raise HTTPException(status_code=409, detail="CEO/OWNER hisobiga taklif qayta berilmaydi.")
    actor_telegram_id = int(actor_user["telegram_id"] or config.ceo_owner_id)
    try:
        role = await db.reissue_telegram_admin_invitation(telegram_id, actor_telegram_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await sync_admin_commands(getattr(app.state, "bot", None), telegram_id, None)
    return {
        "ok": True,
        "telegram_id": telegram_id,
        "role": role,
        "status": "invitation_pending",
        "message": "Bot taklifi qayta yoqildi. Foydalanuvchi Telegram Botda /start yuborishi kerak.",
    }


@app.post("/api/admin/accounts", status_code=201)
async def admin_create_account(
    payload: WebAdminCreateIn, request: Request,
    actor: str = Depends(require_roles("ceo")),
) -> dict[str, Any]:
    creator = await db.web_admin(actor)
    if not creator:
        raise HTTPException(status_code=401, detail="Admin hisobi topilmadi.")
    protected_admin_ids = {config.ceo_owner_id, config.owner_telegram_id}
    if payload.telegram_id in protected_admin_ids:
        raise HTTPException(status_code=409, detail="CEO yoki OWNER Telegram ID’sini boshqa administrator hisobiga biriktirib bo‘lmaydi.")
    if payload.username.casefold() == config.web_admin_username.casefold():
        raise HTTPException(status_code=409, detail="Bu login bootstrap CEO hisobiga tegishli.")
    try:
        await db.create_web_admin(
            payload.username, _hash_password(payload.password), payload.role, actor,
            payload.telegram_id, int(creator["telegram_id"] or config.ceo_owner_id),
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await db.write_admin_audit(actor, "web_admin_created", entity_type="web_admin", details=f"username={payload.username}; role={payload.role}; telegram_id={payload.telegram_id}",
                               ip_address=request.client.host if request.client else "")
    return {"ok": True, "username": payload.username, "role": payload.role, "role_label": _ROLE_LABELS[payload.role]}


@app.patch("/api/admin/accounts/{username}/password")
async def admin_reset_account_password(
    username: str, payload: AdminPasswordResetIn, request: Request,
    actor: str = Depends(require_roles("ceo")),
) -> dict[str, Any]:
    target = await db.web_admin(username)
    if not target:
        raise HTTPException(status_code=404, detail="Administrator topilmadi.")
    if username.casefold() == actor.casefold() or username.casefold() == config.web_admin_username.casefold() or target["role"] == "ceo":
        raise HTTPException(status_code=409, detail="CEO o‘z parolini backend/.env orqali boshqaradi; bu amal boshqa adminlar uchun.")
    try:
        await db.rotate_web_admin_password(str(target["username"]), _hash_password(payload.password), allow_pending=True)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if target["telegram_id"] is not None:
        await sync_admin_commands(getattr(app.state, "bot", None), int(target["telegram_id"]), None)
    await db.write_admin_audit(actor, "web_admin_password_reset", entity_type="web_admin",
                               details=f"username={target['username']}; telegram_id={target['telegram_id']}",
                               ip_address=request.client.host if request.client else "")
    return {"ok": True, "username": target["username"]}


@app.patch("/api/admin/accounts/{username}/active")
async def admin_set_account_active(
    username: str, payload: WebAdminActiveIn, request: Request,
    actor: str = Depends(require_roles("ceo")),
) -> dict[str, Any]:
    actor_user = await db.web_admin(actor)
    target = await db.web_admin(username)
    if not actor_user:
        raise HTTPException(status_code=401, detail="Admin hisobi topilmadi.")
    if not target:
        raise HTTPException(status_code=404, detail="Administrator topilmadi.")
    if username.casefold() == actor.casefold():
        raise HTTPException(status_code=409, detail="O‘zingizning hisobingizni o‘zgartira olmaysiz.")
    if username.casefold() == config.web_admin_username.casefold():
        raise HTTPException(status_code=409, detail="Bootstrap CEO hisobini bu paneldan faolsizlantirib bo‘lmaydi.")
    if payload.active and target["role"] != "ceo" and target["telegram_id"] is None:
        raise HTTPException(
            status_code=409,
            detail="Bu eski hisob Telegram ID bilan bog‘lanmagan. Uni faollashtirish o‘rniga botda /add_admin orqali ID qo‘shib, yangi bog‘langan hisob yarating.",
        )
    if target["role"] == "ceo" and not payload.active and await db.count_active_web_admins("ceo") <= 1:
        raise HTTPException(status_code=409, detail="Kamida bitta faol CEO hisobi qolishi kerak.")
    await db.set_web_admin_active(username, payload.active)
    if target["telegram_id"] is not None and target["role"] != "ceo":
        # Re-enabling the website account only stages it; a fresh password login is required for bot rights.
        await sync_admin_commands(getattr(app.state, "bot", None), int(target["telegram_id"]), None)
    await db.write_admin_audit(actor, "web_admin_activation_changed", entity_type="web_admin",
                               details=f"username={target['username']}; active={payload.active}",
                               ip_address=request.client.host if request.client else "")
    return {"ok": True, "username": target["username"], "active": payload.active}


@app.get("/admin", include_in_schema=False)
@app.get("/admin/", include_in_schema=False)
async def admin_panel_page() -> FileResponse:
    return FileResponse(ADMIN_DIR / "index.html")


if ADMIN_DIR.exists():
    app.mount("/admin/assets", StaticFiles(directory=ADMIN_DIR), name="admin-assets")
