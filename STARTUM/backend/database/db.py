from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
import sqlite3
import time
from typing import Any, AsyncIterator, Sequence

import aiosqlite

from application_statuses import ALL_APPLICATION_STATUSES
from database.education_methods import EducationDatabaseMixin


SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

-- Durable aiogram FSM state. Conversation payloads expire after seven days.
CREATE TABLE IF NOT EXISTS fsm_storage (
    storage_key TEXT PRIMARY KEY,
    state TEXT,
    data_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fsm_storage_updated_at ON fsm_storage(updated_at);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL UNIQUE,
    first_name TEXT NOT NULL DEFAULT '',
    last_name TEXT,
    username TEXT,
    language TEXT NOT NULL DEFAULT 'uz',
    account_status TEXT NOT NULL DEFAULT 'active',
    suspended_until TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_moderation_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    telegram_id INTEGER NOT NULL,
    scope TEXT NOT NULL CHECK(scope IN ('startum_bot','telegram_group')),
    action TEXT NOT NULL CHECK(action IN ('suspend','restore','group_mute','group_unmute')),
    group_chat_id INTEGER,
    actor TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    expires_at TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_user_moderation_telegram_created
    ON user_moderation_actions(telegram_id, created_at DESC);

CREATE TABLE IF NOT EXISTS admins (
    telegram_id INTEGER PRIMARY KEY,
    role TEXT NOT NULL DEFAULT 'admin',
    active INTEGER NOT NULL DEFAULT 1,
    pending_link INTEGER NOT NULL DEFAULT 0,
    bot_invite_pending INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    created_by INTEGER
);

CREATE TABLE IF NOT EXISTS courses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name_uz TEXT NOT NULL,
    name_ru TEXT NOT NULL,
    name_en TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'subject',
    slug TEXT NOT NULL DEFAULT '',
    description_uz TEXT NOT NULL DEFAULT '',
    description_ru TEXT NOT NULL DEFAULT '',
    description_en TEXT NOT NULL DEFAULT '',
    icon TEXT NOT NULL DEFAULT '📚',
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS teachers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    subject TEXT NOT NULL,
    experience TEXT NOT NULL DEFAULT '',
    bio TEXT NOT NULL DEFAULT '',
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    full_name TEXT NOT NULL,
    phone TEXT NOT NULL,
    course_id INTEGER NOT NULL,
    level TEXT NOT NULL DEFAULT '',
    preferred_time TEXT NOT NULL DEFAULT '',
    message TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'new',
    identity_provider TEXT NOT NULL DEFAULT '',
    external_user_id TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY(course_id) REFERENCES courses(id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    topic TEXT NOT NULL,
    message_text TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'new',
    created_at TEXT NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS web_applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    phone TEXT NOT NULL,
    telegram_username TEXT NOT NULL,
    course_id INTEGER NOT NULL,
    level TEXT NOT NULL DEFAULT '',
    preferred_time TEXT NOT NULL DEFAULT '',
    message TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'new',
    identity_provider TEXT NOT NULL DEFAULT '',
    external_user_id TEXT NOT NULL DEFAULT '',
    tracking_token_hash TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY(course_id) REFERENCES courses(id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS bot_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_applications_status ON applications(status);
CREATE INDEX IF NOT EXISTS idx_messages_status ON messages(status);
CREATE INDEX IF NOT EXISTS idx_courses_kind ON courses(kind);
CREATE INDEX IF NOT EXISTS idx_web_applications_status ON web_applications(status);
CREATE TABLE IF NOT EXISTS admin_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL DEFAULT '',
    entity_id INTEGER,
    details TEXT NOT NULL DEFAULT '',
    ip_address TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_admin_audit_created_at ON admin_audit(created_at);
CREATE TABLE IF NOT EXISTS web_admin_users (
    username TEXT PRIMARY KEY COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    telegram_id INTEGER UNIQUE,
    telegram_verified INTEGER NOT NULL DEFAULT 0,
    role TEXT NOT NULL CHECK(role IN ('ceo','senior_admin','junior_admin')),
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    created_by TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_web_admin_users_role ON web_admin_users(role, active);
CREATE TABLE IF NOT EXISTS web_admin_sessions (
    token_hash TEXT PRIMARY KEY,
    username TEXT NOT NULL COLLATE NOCASE,
    expires_at INTEGER NOT NULL,
    revoked INTEGER NOT NULL DEFAULT 0,
    ip_address TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY(username) REFERENCES web_admin_users(username) ON UPDATE CASCADE ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_web_admin_sessions_expiry ON web_admin_sessions(expires_at);
CREATE TABLE IF NOT EXISTS rate_limit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scope TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rate_limit_scope_fingerprint_time
    ON rate_limit_events(scope, fingerprint, created_at);
CREATE TABLE IF NOT EXISTS teacher_managers (
    telegram_id INTEGER PRIMARY KEY,
    course_id INTEGER NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    created_by INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(course_id) REFERENCES courses(id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS idx_teacher_managers_course ON teacher_managers(course_id, active);
CREATE TABLE IF NOT EXISTS learning_resources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL CHECK(category IN ('book','vocabulary','movie','music','quiz')),
    course_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL DEFAULT '',
    media_type TEXT NOT NULL DEFAULT 'text' CHECK(media_type IN ('text','url','video','audio','document','photo')),
    telegram_file_id TEXT NOT NULL DEFAULT '',
    created_by_telegram_id INTEGER NOT NULL DEFAULT 0,
    created_by_role TEXT NOT NULL DEFAULT 'admin',
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    FOREIGN KEY(course_id) REFERENCES courses(id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS idx_learning_resources_course_category
    ON learning_resources(course_id, category, active, id);
CREATE TABLE IF NOT EXISTS quiz_questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    resource_id INTEGER NOT NULL,
    position INTEGER NOT NULL,
    question_text TEXT NOT NULL,
    options_json TEXT NOT NULL,
    correct_index INTEGER NOT NULL,
    explanation TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY(resource_id) REFERENCES learning_resources(id) ON DELETE CASCADE,
    UNIQUE(resource_id, position)
);
CREATE TABLE IF NOT EXISTS quiz_sessions (
    telegram_id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    resource_id INTEGER NOT NULL,
    current_index INTEGER NOT NULL DEFAULT 0 CHECK(current_index >= 0),
    question_total INTEGER NOT NULL CHECK(question_total > 0),
    score INTEGER NOT NULL DEFAULT 0 CHECK(score >= 0),
    started_at_epoch INTEGER NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY(resource_id) REFERENCES learning_resources(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS quiz_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    resource_id INTEGER NOT NULL,
    course_id INTEGER NOT NULL,
    score INTEGER NOT NULL CHECK(score >= 0),
    total INTEGER NOT NULL CHECK(total > 0),
    percent INTEGER NOT NULL CHECK(percent BETWEEN 0 AND 100),
    duration_seconds INTEGER NOT NULL DEFAULT 0 CHECK(duration_seconds >= 0),
    source_chat_id INTEGER,
    source_chat_type TEXT NOT NULL DEFAULT 'private',
    started_at TEXT NOT NULL,
    completed_at TEXT NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY(resource_id) REFERENCES learning_resources(id) ON DELETE RESTRICT,
    FOREIGN KEY(course_id) REFERENCES courses(id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS idx_quiz_attempts_user_completed ON quiz_attempts(user_id, completed_at DESC);
CREATE INDEX IF NOT EXISTS idx_quiz_attempts_course_resource ON quiz_attempts(course_id, resource_id, completed_at DESC);

CREATE TABLE IF NOT EXISTS user_favorites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    resource_id INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY(resource_id) REFERENCES learning_resources(id) ON DELETE CASCADE,
    UNIQUE(user_id, resource_id)
);
CREATE INDEX IF NOT EXISTS idx_user_favorites_user_created ON user_favorites(user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS notification_outbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    application_id INTEGER NOT NULL,
    source TEXT NOT NULL DEFAULT 'website' CHECK(source IN ('website','bot')),
    recipient_telegram_id INTEGER NOT NULL,
    message_text TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','sent','failed')),
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    sent_at TEXT,
    UNIQUE(source, application_id, recipient_telegram_id)
);
CREATE INDEX IF NOT EXISTS idx_notification_outbox_status
    ON notification_outbox(status, attempts, id);
CREATE TABLE IF NOT EXISTS support_notification_outbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id INTEGER NOT NULL,
    recipient_telegram_id INTEGER NOT NULL,
    message_text TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','sent','failed')),
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    sent_at TEXT,
    UNIQUE(message_id, recipient_telegram_id),
    FOREIGN KEY(message_id) REFERENCES messages(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_support_outbox_status
    ON support_notification_outbox(status, attempts, id);

CREATE TABLE IF NOT EXISTS application_status_notification_outbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL CHECK(source IN ('website','bot')),
    application_id INTEGER NOT NULL,
    recipient_telegram_id INTEGER NOT NULL,
    status_name TEXT NOT NULL CHECK(status_name IN ('new','in_review','contacted','accepted','rejected','in_progress','closed')),
    message_text TEXT NOT NULL,
    delivery_status TEXT NOT NULL DEFAULT 'pending' CHECK(delivery_status IN ('pending','sent','failed')),
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    sent_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_application_status_outbox_status
    ON application_status_notification_outbox(delivery_status, attempts, id);
CREATE TABLE IF NOT EXISTS application_status_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL CHECK(source IN ('website','bot')),
    application_id INTEGER NOT NULL,
    old_status TEXT NOT NULL,
    new_status TEXT NOT NULL,
    actor TEXT NOT NULL,
    ip_address TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_application_status_history_application
    ON application_status_history(source, application_id, id DESC);
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


SUBJECTS = [
    ("Matematika", "Математика", "Mathematics", "subject", "Aniq fikrlash va masalalar yechimi.", "Точное мышление и решение задач.", "Logical thinking and problem solving.", "∑"),
    ("Fizika", "Физика", "Physics", "subject", "Tabiat qonunlarini tushunish va amaliyot.", "Понимание законов природы и практика.", "Understanding laws of nature through practice.", "⚛"),
    ("Kimyo", "Химия", "Chemistry", "subject", "Moddalar, reaksiyalar va tajribalar olami.", "Мир веществ, реакций и экспериментов.", "The world of substances, reactions and experiments.", "⚗"),
    ("Biologiya", "Биология", "Biology", "subject", "Tirik tabiat va inson organizmini o‘rganish.", "Изучение живой природы и организма человека.", "Study of living systems and the human body.", "🧬"),
    ("Geografiya", "География", "Geography", "subject", "Dunyo, xaritalar va geografik jarayonlar.", "Мир, карты и географические процессы.", "The world, maps and geographic processes.", "🌍"),
    ("Tarix", "История", "History", "subject", "Voqealarni tahlil qilish va tarixiy tafakkur.", "Анализ событий и историческое мышление.", "Historical thinking and analysis.", "🏛"),
    ("Ona tili va adabiyot", "Родной язык и литература", "Native Language & Literature", "subject", "Til, matn, nutq va badiiy tafakkur.", "Язык, текст, речь и литература.", "Language, text, communication and literature.", "📖"),
    ("Ingliz tili", "Английский язык", "English", "subject", "Kundalik va akademik ingliz tili.", "Повседневный и академический английский.", "Everyday and academic English.", "EN"),
    ("Rus tili", "Русский язык", "Russian", "subject", "Rus tilida mustahkam kommunikatsiya.", "Уверенная коммуникация на русском.", "Confident communication in Russian.", "RU"),
    ("Koreys tili", "Корейский язык", "Korean", "subject", "Koreys tiliga bosqichma-bosqich kirish.", "Пошаговое освоение корейского языка.", "Step-by-step Korean learning.", "KR"),
    ("Nemis tili", "Немецкий язык", "German", "subject", "Asosiy grammatika va suhbat ko‘nikmalari.", "Базовая грамматика и разговорная практика.", "Core grammar and conversation practice.", "DE"),
    ("Turk tili", "Турецкий язык", "Turkish", "subject", "Turk tilida amaliy muloqot va grammatika.", "Практическое общение и грамматика турецкого.", "Practical Turkish communication and grammar.", "TR"),
]

SPECIALS = [
    ("IELTS / CEFR / Multi-level", "IELTS / CEFR / Multi-level", "IELTS / CEFR / Multi-level", "special", "Til darajangizni xalqaro mezonlar bo‘yicha rivojlantirish.", "Развитие уровня языка по международным стандартам.", "Build language skills against international standards.", "🎯"),
    ("Milliy sertifikat", "Национальный сертификат", "National Certificate", "special", "Sertifikat imtihonlariga yo‘naltirilgan tayyorgarlik.", "Подготовка к сертификационным экзаменам.", "Preparation focused on certification exams.", "🏅"),
    ("Prezident va ixtisoslashtirilgan maktablarga tayyorlov", "Подготовка в Президентские и специализированные школы", "Presidential & Specialized School Prep", "special", "Tanlov imtihonlari uchun maqsadli tayyorgarlik.", "Целевая подготовка к конкурсным экзаменам.", "Targeted preparation for entrance exams.", "🏫"),
    ("Mental arifmetika", "Ментальная арифметика", "Mental Arithmetic", "special", "Tez hisoblash va diqqatni rivojlantirish.", "Быстрый счёт и развитие концентрации.", "Speed calculation and concentration practice.", "🧠"),
    ("Matematika Kids", "Математика Kids", "Math Kids", "special", "Bolalar uchun qiziqarli matematika mashg‘ulotlari.", "Интересная математика для детей.", "Engaging mathematics for children.", "🔢"),
    ("Kids English", "Kids English", "Kids English", "special", "Bolalar uchun sodda va amaliy ingliz tili.", "Простой и практичный английский для детей.", "Simple, practical English for children.", "🗣"),
    ("Rus tili — Pochemuchka", "Русский язык — Pochemuchka", "Russian — Pochemuchka", "special", "Bolalar uchun rus tilida muloqot va rivojlanish.", "Общение и развитие на русском для детей.", "Russian language development for children.", "💬"),
    ("Logoped mashg‘ulotlari", "Занятия с логопедом", "Speech Therapy Sessions", "special", "Nutqni shakllantirish va mustahkamlash mashg‘ulotlari.", "Занятия по развитию и укреплению речи.", "Speech development sessions.", "🧩"),
    ("Shashka va shaxmat", "Шашки и шахматы", "Draughts & Chess", "special", "Mantiq, strategiya va diqqatni rivojlantirish.", "Логика, стратегия и концентрация.", "Logic, strategy and focus.", "♟"),
]


COURSE_SLUG_MAP = {
    "Matematika": "math", "Fizika": "physics", "Kimyo": "chemistry", "Biologiya": "biology",
    "Geografiya": "geography", "Tarix": "history", "Ona tili va adabiyot": "native-language",
    "Ingliz tili": "english", "Rus tili": "russian", "Koreys tili": "korean", "Nemis tili": "german", "Turk tili": "turkish",
    "IELTS / CEFR / Multi-level": "ielts-cefr", "Milliy sertifikat": "national-certificate",
    "Prezident va ixtisoslashtirilgan maktablarga tayyorlov": "presidential-prep", "Mental arifmetika": "mental-arithmetic",
    "Matematika Kids": "math-kids", "Kids English": "kids-english", "Rus tili — Pochemuchka": "pochemuchka",
    "Logoped mashg‘ulotlari": "speech-therapy", "Shashka va shaxmat": "chess",
}

def course_slug(name: str) -> str:
    if name in COURSE_SLUG_MAP:
        return COURSE_SLUG_MAP[name]
    import hashlib
    import re
    slug = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-")[:40]
    # Pure Cyrillic/other non-Latin names would otherwise create an empty slug.
    return slug or f"course-{hashlib.sha1(name.casefold().encode('utf-8')).hexdigest()[:10]}"


class Database(EducationDatabaseMixin):
    # Increment this when adding a schema change that needs an automatic preflight backup.
    CURRENT_SCHEMA_VERSION = 9

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _backup_before_schema_upgrade(self) -> None:
        """Create and verify an online SQLite snapshot before upgrading an existing DB.

        Older installations have no schema_migrations marker, so the first boot after
        this version creates one backup. If that backup fails, initialization stops
        before any schema mutation.
        """
        if not self.path.is_file() or self.path.stat().st_size == 0:
            return
        source = sqlite3.connect(str(self.path), timeout=10)
        destination = None
        backup_path: Path | None = None
        try:
            table_exists = source.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
            ).fetchone()
            current = 0
            if table_exists:
                row = source.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
                current = int(row[0] or 0)
            if current >= self.CURRENT_SCHEMA_VERSION:
                return

            backup_dir = self.path.parent / "backups"
            backup_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            backup_path = backup_dir / f"{self.path.stem}_pre_v{self.CURRENT_SCHEMA_VERSION}_{stamp}.sqlite3"
            destination = sqlite3.connect(str(backup_path), timeout=10)
            source.backup(destination)
            integrity = destination.execute("PRAGMA integrity_check").fetchone()
            if not integrity or integrity[0] != "ok":
                raise sqlite3.DatabaseError("Pre-migration backup integrity check failed")
            destination.commit()
        except Exception:
            if destination is not None:
                destination.close()
                destination = None
            if backup_path is not None:
                backup_path.unlink(missing_ok=True)
            raise
        finally:
            if destination is not None:
                destination.close()
            source.close()

    @asynccontextmanager
    async def connect(self) -> AsyncIterator[aiosqlite.Connection]:
        db = await aiosqlite.connect(self.path)
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys=ON")
        await db.execute("PRAGMA busy_timeout=5000")
        try:
            yield db
            await db.commit()
        except Exception:
            await db.rollback()
            raise
        finally:
            await db.close()

    async def init(
        self,
        owner_id: int,
        admin_ids: Sequence[int] = (),
        web_admin_username: str = "",
        web_admin_password_hash: str = "",
    ) -> None:
        self._backup_before_schema_upgrade()
        async with self.connect() as db:
            # WAL improves read/write concurrency; busy_timeout gives short write
            # contention a chance to clear instead of immediately failing.
            await db.execute("PRAGMA journal_mode=WAL")
            await db.execute("PRAGMA synchronous=NORMAL")
            await db.executescript(SCHEMA)
            education_schema_path = Path(__file__).with_name("education_schema.sql")
            if not education_schema_path.is_file():
                raise FileNotFoundError("STARTUM education_schema.sql migratsiya fayli topilmadi.")
            await db.executescript(education_schema_path.read_text(encoding="utf-8"))

            # Additive education-platform columns. Existing users keep their saved language; new users choose it.
            users_v4_columns = {r[1] for r in await (await db.execute("PRAGMA table_info(users)")).fetchall()}
            if "language_selected" not in users_v4_columns:
                await db.execute("ALTER TABLE users ADD COLUMN language_selected INTEGER NOT NULL DEFAULT 1")
            resource_v4_columns = {r[1] for r in await (await db.execute("PRAGMA table_info(learning_resources)")).fetchall()}
            homework_submission_columns = {r[1] for r in await (await db.execute("PRAGMA table_info(homework_submissions)")).fetchall()}
            if "attachment_type" not in homework_submission_columns:
                await db.execute("ALTER TABLE homework_submissions ADD COLUMN attachment_type TEXT NOT NULL DEFAULT ''")
            for column_name, column_definition in (
                ("publication_status", "TEXT NOT NULL DEFAULT 'published'"),
                ("group_id", "INTEGER REFERENCES education_groups(id) ON DELETE SET NULL"),
                ("level", "TEXT NOT NULL DEFAULT ''"),
                ("file_name", "TEXT NOT NULL DEFAULT ''"),
                ("file_mime", "TEXT NOT NULL DEFAULT ''"),
                ("file_size", "INTEGER NOT NULL DEFAULT 0"),
            ):
                if column_name not in resource_v4_columns:
                    await db.execute(f"ALTER TABLE learning_resources ADD COLUMN {column_name} {column_definition}")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_learning_resources_publication ON learning_resources(publication_status,active,course_id)")
            for table in ("applications", "web_applications"):
                await db.execute(f"UPDATE {table} SET status='in_review' WHERE status='in_progress'")
            outbox_definition = await (await db.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='application_status_notification_outbox'"
            )).fetchone()
            if outbox_definition and "'contacted'" not in str(outbox_definition["sql"] or ""):
                await db.execute(
                    "ALTER TABLE application_status_notification_outbox RENAME TO application_status_notification_outbox_pre_v3"
                )
                await db.execute("""CREATE TABLE application_status_notification_outbox (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL CHECK(source IN ('website','bot')),
                    application_id INTEGER NOT NULL,
                    recipient_telegram_id INTEGER NOT NULL,
                    status_name TEXT NOT NULL CHECK(status_name IN ('new','in_review','contacted','accepted','rejected','in_progress','closed')),
                    message_text TEXT NOT NULL,
                    delivery_status TEXT NOT NULL DEFAULT 'pending' CHECK(delivery_status IN ('pending','sent','failed')),
                    attempts INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    sent_at TEXT
                )""")
                await db.execute(
                    "INSERT INTO application_status_notification_outbox "
                    "SELECT id,source,application_id,recipient_telegram_id,status_name,message_text,delivery_status,attempts,last_error,created_at,sent_at "
                    "FROM application_status_notification_outbox_pre_v3"
                )
                await db.execute("DROP TABLE application_status_notification_outbox_pre_v3")
                await db.execute("CREATE INDEX IF NOT EXISTS idx_application_status_outbox_status ON application_status_notification_outbox(delivery_status, attempts, id)")
            user_columns = {r[1] for r in await (await db.execute("PRAGMA table_info(users)")).fetchall()}
            if "account_status" not in user_columns:
                await db.execute("ALTER TABLE users ADD COLUMN account_status TEXT NOT NULL DEFAULT 'active'")
            if "suspended_until" not in user_columns:
                await db.execute("ALTER TABLE users ADD COLUMN suspended_until TEXT")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_users_account_status ON users(account_status, suspended_until)")
            web_admin_columns = {r[1] for r in await (await db.execute("PRAGMA table_info(web_admin_users)")).fetchall()}
            if "telegram_id" not in web_admin_columns:
                await db.execute("ALTER TABLE web_admin_users ADD COLUMN telegram_id INTEGER")
            if "telegram_verified" not in web_admin_columns:
                await db.execute("ALTER TABLE web_admin_users ADD COLUMN telegram_verified INTEGER NOT NULL DEFAULT 0")
            admin_columns = {r[1] for r in await (await db.execute("PRAGMA table_info(admins)")).fetchall()}
            if "pending_link" not in admin_columns:
                await db.execute("ALTER TABLE admins ADD COLUMN pending_link INTEGER NOT NULL DEFAULT 0")
            if "bot_invite_pending" not in admin_columns:
                await db.execute("ALTER TABLE admins ADD COLUMN bot_invite_pending INTEGER NOT NULL DEFAULT 0")
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_admins_bot_invite_pending ON admins(bot_invite_pending, active)"
            )
            await db.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_web_admin_users_telegram_id "
                "ON web_admin_users(telegram_id) WHERE telegram_id IS NOT NULL"
            )
            columns = {r[1] for r in await (await db.execute("PRAGMA table_info(courses)")).fetchall()}
            if "slug" not in columns:
                await db.execute("ALTER TABLE courses ADD COLUMN slug TEXT NOT NULL DEFAULT ''")
            columns = {r[1] for r in await (await db.execute("PRAGMA table_info(messages)")).fetchall()}
            if "admin_reply" not in columns:
                await db.execute("ALTER TABLE messages ADD COLUMN admin_reply TEXT NOT NULL DEFAULT ''")
            if "replied_at" not in columns:
                await db.execute("ALTER TABLE messages ADD COLUMN replied_at TEXT")
            # Backward-compatible additive migrations: existing records remain untouched.
            for table, column, definition in (
                ("applications", "identity_provider", "TEXT NOT NULL DEFAULT ''"),
                ("applications", "external_user_id", "TEXT NOT NULL DEFAULT ''"),
                ("web_applications", "identity_provider", "TEXT NOT NULL DEFAULT ''"),
                ("web_applications", "external_user_id", "TEXT NOT NULL DEFAULT ''"),
            ):
                table_columns = {r[1] for r in await (await db.execute(f"PRAGMA table_info({table})")).fetchall()}
                if column not in table_columns:
                    await db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
            web_application_columns = {r[1] for r in await (await db.execute("PRAGMA table_info(web_applications)")).fetchall()}
            if "tracking_token_hash" not in web_application_columns:
                await db.execute("ALTER TABLE web_applications ADD COLUMN tracking_token_hash TEXT NOT NULL DEFAULT ''")
            await db.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_web_applications_tracking_hash "
                "ON web_applications(tracking_token_hash) WHERE tracking_token_hash <> ''"
            )
            await db.execute("CREATE INDEX IF NOT EXISTS idx_web_applications_external_user ON web_applications(identity_provider,external_user_id)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_applications_external_user ON applications(identity_provider,external_user_id)")
            now = utcnow()
            for row in [*SUBJECTS, *SPECIALS]:
                await db.execute(
                    """INSERT INTO courses(name_uz,name_ru,name_en,kind,slug,description_uz,description_ru,description_en,icon,active,created_at)
                    SELECT ?,?,?,?,?,?,?,?,?,1,? WHERE NOT EXISTS (SELECT 1 FROM courses WHERE name_uz=? AND kind=?)""",
                    (row[0], row[1], row[2], row[3], course_slug(row[0]), row[4], row[5], row[6], row[7], now, row[0], row[3]),
                )
            for name, slug in COURSE_SLUG_MAP.items():
                await db.execute("UPDATE courses SET slug=? WHERE name_uz=? AND (slug='' OR slug IS NULL)", (slug, name))

            await db.execute(
                """INSERT INTO admins(telegram_id,role,active,created_at,created_by)
                   VALUES(?,?,?,?,?)
                   ON CONFLICT(telegram_id) DO UPDATE SET role='ceo',active=1,pending_link=0""",
                (owner_id, "ceo", 1, now, owner_id),
            )
            # Migrate the previous flat roles without granting additional privileges:
            # legacy admins keep their previous operational capability as senior admins.
            await db.execute(
                "UPDATE admins SET role='senior_admin' WHERE telegram_id<>? AND role IN ('admin','owner')",
                (owner_id,),
            )
            # Other Telegram administrators are never bootstrapped from ADMIN_IDS.
            # They must be added by the owner in the bot and linked to a web account.

            # The .env account is the bootstrap CEO. Upserting lets an owner rotate
            # its password hash through .env without deleting application data.
            username = (web_admin_username or "").strip()
            password_hash = (web_admin_password_hash or "").strip()
            if username and password_hash and password_hash != "replace_with_pbkdf2_hash":
                # If the configured bootstrap login changes, deactivate only the old
                # bootstrap-owned account(s); separately-created administrator accounts
                # are not affected. Revoke old sessions in the same transaction.
                await db.execute(
                    """UPDATE web_admin_sessions SET revoked=1 WHERE username IN (
                           SELECT username FROM web_admin_users
                           WHERE created_by='bootstrap' AND username<>? COLLATE NOCASE
                       )""",
                    (username,),
                )
                await db.execute(
                    """UPDATE web_admin_users SET active=0,telegram_id=NULL,updated_at=?
                       WHERE created_by='bootstrap' AND username<>? COLLATE NOCASE""",
                    (now, username),
                )
                # The owner Telegram ID is reserved for the single bootstrap CEO account.
                await db.execute(
                    "UPDATE web_admin_users SET telegram_id=NULL WHERE telegram_id=? AND username<>? COLLATE NOCASE",
                    (owner_id, username),
                )
                existing = await (await db.execute(
                    "SELECT password_hash FROM web_admin_users WHERE username=? COLLATE NOCASE", (username,)
                )).fetchone()
                # Password rotation must invalidate every previously issued session.
                if existing and existing["password_hash"] != password_hash:
                    await db.execute(
                        "UPDATE web_admin_sessions SET revoked=1 WHERE username=? COLLATE NOCASE", (username,)
                    )
                await db.execute(
                    """INSERT INTO web_admin_users(username,password_hash,telegram_id,telegram_verified,role,active,created_at,created_by,updated_at)
                       VALUES(?,?,?,1,'ceo',1,?,'bootstrap',?)
                       ON CONFLICT(username) DO UPDATE SET
                         password_hash=excluded.password_hash,
                         telegram_id=excluded.telegram_id,
                         telegram_verified=1,
                         role='ceo', active=1, created_by='bootstrap', updated_at=excluded.updated_at""",
                    (username, password_hash, owner_id, now, now),
                )
                # API-created accounts cannot be CEO; demote legacy extra CEO rows.
                await db.execute(
                    "UPDATE web_admin_users SET role='senior_admin',updated_at=? WHERE role='ceo' AND username<>? COLLATE NOCASE",
                    (now, username),
                )

            # Exactly one website CEO account is reserved for the configured bootstrap login.
            await db.execute(
                "UPDATE web_admin_users SET role='senior_admin',active=0,telegram_verified=0,updated_at=? "
                "WHERE role='ceo' AND username<>? COLLATE NOCASE",
                (now, username),
            )

            # Disable legacy non-CEO web accounts unless they are already verified or explicitly pending from /add_admin.
            await db.execute(
                """UPDATE web_admin_users SET active=0,telegram_verified=0,updated_at=?
                   WHERE role<>'ceo' AND active=1 AND (
                     telegram_id IS NULL OR (
                       telegram_verified=0 AND telegram_id NOT IN
                         (SELECT telegram_id FROM admins WHERE pending_link=1)
                     )
                   )""",
                (now,),
            )
            await db.execute(
                "UPDATE web_admin_sessions SET revoked=1 WHERE username IN (SELECT username FROM web_admin_users WHERE active=0)"
            )

            # Keep exactly one CEO role in the Telegram admin table.
            await db.execute(
                "UPDATE admins SET role='senior_admin',active=0,pending_link=0,bot_invite_pending=0 WHERE telegram_id<>? AND role IN ('ceo','owner')",
                (owner_id,),
            )
            # Synchronize Telegram roles with active, individual-password web accounts.
            # Unlinked legacy admins are disabled (never deleted). The owner is always the only CEO.
            await db.execute(
                """UPDATE admins SET active=0 WHERE telegram_id<>? AND pending_link=0 AND bot_invite_pending=0 AND telegram_id NOT IN
                   (SELECT telegram_id FROM web_admin_users
                    WHERE telegram_id IS NOT NULL AND active=1 AND telegram_verified=1)""",
                (owner_id,),
            )
            await db.execute(
                """UPDATE admins SET active=1, bot_invite_pending=0, role=(
                       SELECT u.role FROM web_admin_users u
                       WHERE u.telegram_id=admins.telegram_id AND u.active=1 AND u.telegram_verified=1
                   ) WHERE telegram_id IN (
                       SELECT telegram_id FROM web_admin_users
                       WHERE telegram_id IS NOT NULL AND active=1 AND telegram_verified=1
                   ) AND telegram_id<>?""",
                (owner_id,),
            )
            # Record completion last so a partial initialization retries with a new backup.
            await db.execute(
                "INSERT OR IGNORE INTO schema_migrations(version,applied_at) VALUES(?,?)",
                (self.CURRENT_SCHEMA_VERSION, utcnow()),
            )

    async def ensure_user(self, tg_user: Any):
        now = utcnow()
        async with self.connect() as db:
            row = await (await db.execute("SELECT * FROM users WHERE telegram_id=?", (tg_user.id,))).fetchone()
            if row:
                await db.execute(
                    "UPDATE users SET first_name=?,last_name=?,username=?,updated_at=? WHERE telegram_id=?",
                    (tg_user.first_name or "", tg_user.last_name, tg_user.username, now, tg_user.id),
                )
                row = await (await db.execute("SELECT * FROM users WHERE telegram_id=?", (tg_user.id,))).fetchone()
                return row, False
            await db.execute(
                "INSERT INTO users(telegram_id,first_name,last_name,username,language,language_selected,created_at,updated_at) VALUES(?,?,?,?,?,0,?,?)",
                (tg_user.id, tg_user.first_name or "", tg_user.last_name, tg_user.username, "uz", now, now),
            )
            row = await (await db.execute("SELECT * FROM users WHERE telegram_id=?", (tg_user.id,))).fetchone()
            return row, True

    async def search_users(self, query: str = "", *, limit: int = 25, offset: int = 0):
        search = " ".join((query or "").split())[:120]
        pattern = f"%{search}%"
        now = utcnow()
        return await self.fetchall(
            """SELECT u.id,u.telegram_id,u.first_name,u.last_name,u.username,u.language,u.created_at,u.updated_at,
                      CASE WHEN u.account_status='suspended' AND u.suspended_until IS NOT NULL AND u.suspended_until<=?
                           THEN 'active' ELSE u.account_status END AS account_status,
                      CASE WHEN u.account_status='suspended' AND u.suspended_until IS NOT NULL AND u.suspended_until<=?
                           THEN NULL ELSE u.suspended_until END AS suspended_until,
                      COALESCE(a.application_count,0) AS application_count,
                      COALESCE(q.attempt_count,0) AS quiz_attempt_count,
                      COALESCE(q.best_percent,0) AS best_percent
               FROM users u
               LEFT JOIN (SELECT user_id,COUNT(*) AS application_count FROM applications GROUP BY user_id) a ON a.user_id=u.id
               LEFT JOIN (SELECT user_id,COUNT(*) AS attempt_count,MAX(percent) AS best_percent FROM quiz_attempts GROUP BY user_id) q ON q.user_id=u.id
               WHERE (?='' OR CAST(u.id AS TEXT) LIKE ? OR CAST(u.telegram_id AS TEXT) LIKE ?
                      OR u.first_name LIKE ? OR COALESCE(u.last_name,'') LIKE ? OR COALESCE(u.username,'') LIKE ?)
               ORDER BY u.id DESC LIMIT ? OFFSET ?""",
            (now, now, search, pattern, pattern, pattern, pattern, pattern,
             max(1, min(int(limit), 100)), max(0, int(offset))),
        )

    async def count_users(self, query: str = "") -> int:
        search = " ".join((query or "").split())[:120]
        pattern = f"%{search}%"
        row = await self.fetchone(
            """SELECT COUNT(*) AS total FROM users u
               WHERE (?='' OR CAST(u.id AS TEXT) LIKE ? OR CAST(u.telegram_id AS TEXT) LIKE ?
                      OR u.first_name LIKE ? OR COALESCE(u.last_name,'') LIKE ? OR COALESCE(u.username,'') LIKE ?)""",
            (search, pattern, pattern, pattern, pattern, pattern),
        )
        return int(row["total"] if row else 0)

    async def user_by_internal_id(self, user_id: int):
        now = utcnow()
        return await self.fetchone(
            """SELECT u.id,u.telegram_id,u.first_name,u.last_name,u.username,u.language,u.created_at,u.updated_at,
                      CASE WHEN u.account_status='suspended' AND u.suspended_until IS NOT NULL AND u.suspended_until<=?
                           THEN 'active' ELSE u.account_status END AS account_status,
                      CASE WHEN u.account_status='suspended' AND u.suspended_until IS NOT NULL AND u.suspended_until<=?
                           THEN NULL ELSE u.suspended_until END AS suspended_until
               FROM users u WHERE u.id=?""",
            (now, now, int(user_id)),
        )

    async def user_details(self, user_id: int) -> dict[str, Any] | None:
        user = await self.user_by_internal_id(user_id)
        if not user:
            return None
        telegram_id = int(user["telegram_id"])
        applications = await self.fetchall(
            """SELECT * FROM (
                   SELECT a.id,a.full_name,a.phone,a.level,a.preferred_time,a.message,a.status,a.created_at,
                          c.name_uz AS course_name,'bot' AS source
                   FROM applications a JOIN courses c ON c.id=a.course_id WHERE a.user_id=?
                   UNION ALL
                   SELECT w.id,w.full_name,w.phone,w.level,w.preferred_time,w.message,w.status,w.created_at,
                          c.name_uz AS course_name,'website' AS source
                   FROM web_applications w JOIN courses c ON c.id=w.course_id
                   WHERE w.identity_provider='telegram' AND w.external_user_id=?
               ) ORDER BY created_at DESC LIMIT 100""",
            (int(user_id), str(telegram_id)),
        )
        attempts = await self.recent_user_quiz_attempts(int(user_id), limit=50)
        moderation = await self.fetchall(
            """SELECT id,scope,action,group_chat_id,actor,reason,expires_at,created_at
               FROM user_moderation_actions WHERE telegram_id=? ORDER BY id DESC LIMIT 100""",
            (telegram_id,),
        )
        return {
            "user": dict(user),
            "applications": [dict(row) for row in applications],
            "quiz_attempts": [dict(row) for row in attempts],
            "moderation_actions": [dict(row) for row in moderation],
        }

    async def moderate_user(
        self, user_id: int, *, action: str, actor: str, reason: str = "",
        duration_minutes: int | None = None, ip_address: str = "",
    ) -> dict[str, Any]:
        if action not in {"suspend", "restore"}:
            raise ValueError("Foydalanuvchi amali noto‘g‘ri.")
        if action == "suspend" and duration_minutes is not None and not 1 <= int(duration_minutes) <= 525600:
            raise ValueError("Cheklov muddati 1 daqiqadan 365 kungacha bo‘lishi kerak.")
        if action == "restore" and duration_minutes is not None:
            raise ValueError("Tiklash amalida muddat berilmaydi.")
        reason = " ".join((reason or "").split())[:500]
        now = datetime.now(timezone.utc)
        created_at = now.isoformat(timespec="seconds")
        expires_at = (now + timedelta(minutes=int(duration_minutes))).isoformat(timespec="seconds") if action == "suspend" and duration_minutes else None
        new_status = "suspended" if action == "suspend" else "active"
        async with self.connect() as db:
            row = await (await db.execute("SELECT id,telegram_id FROM users WHERE id=?", (int(user_id),))).fetchone()
            if not row:
                raise ValueError("Foydalanuvchi topilmadi.")
            telegram_id = int(row["telegram_id"])
            privileged = await (await db.execute(
                "SELECT 1 FROM admins WHERE telegram_id=? UNION SELECT 1 FROM web_admin_users WHERE telegram_id=? LIMIT 1",
                (telegram_id, telegram_id),
            )).fetchone()
            if privileged:
                raise ValueError("Administrator hisobini foydalanuvchi boshqaruvidan cheklab bo‘lmaydi.")
            await db.execute(
                "UPDATE users SET account_status=?,suspended_until=?,updated_at=? WHERE id=?",
                (new_status, expires_at, created_at, int(user_id)),
            )
            await db.execute(
                "INSERT INTO user_moderation_actions(user_id,telegram_id,scope,action,actor,reason,expires_at,created_at) "
                "VALUES(?,?,'startum_bot',?,?,?,?,?)",
                (int(user_id), telegram_id, action, actor[:80], reason, expires_at, created_at),
            )
            await db.execute(
                "INSERT INTO admin_audit(actor,action,entity_type,entity_id,details,ip_address,created_at) VALUES(?,?,?,?,?,?,?)",
                (actor[:80], f"user_{action}", "user", int(user_id),
                 f"telegram_id={telegram_id}; duration_minutes={duration_minutes or ''}; reason={reason[:160]}",
                 ip_address[:80], created_at),
            )
        return {"user_id": int(user_id), "telegram_id": telegram_id, "status": new_status, "suspended_until": expires_at}

    async def user_access_is_suspended(self, telegram_id: int) -> bool:
        now = utcnow()
        async with self.connect() as db:
            row = await (await db.execute(
                "SELECT id,account_status,suspended_until FROM users WHERE telegram_id=?", (int(telegram_id),)
            )).fetchone()
            if not row or str(row["account_status"]) != "suspended":
                return False
            expires_at = str(row["suspended_until"] or "")
            if expires_at and expires_at <= now:
                await db.execute(
                    "UPDATE users SET account_status='active',suspended_until=NULL,updated_at=? WHERE id=?",
                    (now, int(row["id"])),
                )
                await db.execute(
                    "INSERT INTO user_moderation_actions(user_id,telegram_id,scope,action,actor,reason,created_at) "
                    "VALUES(?,?,'startum_bot','restore','system','Muvaqqat cheklov muddati tugadi.',?)",
                    (int(row["id"]), int(telegram_id), now),
                )
                await db.execute(
                    "INSERT INTO admin_audit(actor,action,entity_type,entity_id,details,created_at) VALUES('system','user_suspension_expired','user',?,?,?)",
                    (int(row["id"]), f"telegram_id={int(telegram_id)}", now),
                )
                return False
            return True

    async def set_language(self, telegram_id: int, language: str) -> None:
        if language not in {"uz", "ru", "en"}:
            raise ValueError("Til kodi noto‘g‘ri.")
        await self.execute(
            "UPDATE users SET language=?,language_selected=1,updated_at=? WHERE telegram_id=?",
            (language, utcnow(), telegram_id),
        )

    async def execute(self, sql: str, params: Sequence[Any] = ()):
        async with self.connect() as db:
            cur = await db.execute(sql, params)
            return cur.lastrowid if cur.lastrowid is not None else cur.rowcount

    async def fetchone(self, sql: str, params: Sequence[Any] = ()):
        async with self.connect() as db:
            return await (await db.execute(sql, params)).fetchone()

    async def fetchall(self, sql: str, params: Sequence[Any] = ()):
        async with self.connect() as db:
            return await (await db.execute(sql, params)).fetchall()

    async def courses(self, kind: str | None = None, *, include_inactive: bool = False):
        if kind:
            query = "SELECT * FROM courses WHERE kind=?" if include_inactive else "SELECT * FROM courses WHERE active=1 AND kind=?"
            return await self.fetchall(query + " ORDER BY active DESC, id", (kind,))
        query = "SELECT * FROM courses" if include_inactive else "SELECT * FROM courses WHERE active=1"
        return await self.fetchall(query + " ORDER BY active DESC, kind, id")

    async def set_course_active(self, course_id: int, active: bool) -> bool:
        exists = await self.fetchone("SELECT id FROM courses WHERE id=?", (course_id,))
        if not exists:
            return False
        await self.execute("UPDATE courses SET active=? WHERE id=?", (1 if active else 0, course_id))
        return True

    async def course(self, course_id: int):
        return await self.fetchone("SELECT * FROM courses WHERE id=? AND active=1", (course_id,))

    async def update_course(self, course_id: int, data: dict[str, Any]) -> bool:
        existing = await self.fetchone("SELECT id FROM courses WHERE id=?", (course_id,))
        if not existing:
            return False
        slug = course_slug(data["name_uz"])
        duplicate = await self.fetchone("SELECT id FROM courses WHERE slug=? AND id<>? LIMIT 1", (slug, course_id))
        if duplicate:
            raise ValueError("Bu nomga mos kurs allaqachon mavjud.")
        await self.execute(
            """UPDATE courses SET kind=?,name_uz=?,name_ru=?,name_en=?,slug=?,description_uz=?,description_ru=?,description_en=?,icon=? WHERE id=?""",
            (data["kind"], data["name_uz"], data["name_ru"], data["name_en"], slug,
             data.get("description_uz", ""), data.get("description_ru", ""),
             data.get("description_en", ""), data.get("icon", "📚"), course_id),
        )
        return True

    async def search_courses(self, query: str):
        like = f"%{query}%"
        return await self.fetchall(
            """SELECT * FROM courses WHERE active=1 AND (name_uz LIKE ? OR name_ru LIKE ? OR name_en LIKE ? OR description_uz LIKE ?) ORDER BY id""",
            (like, like, like, like),
        )

    async def teachers(self, *, include_inactive: bool = False):
        if include_inactive:
            return await self.fetchall("SELECT * FROM teachers ORDER BY active DESC, id DESC")
        return await self.fetchall("SELECT * FROM teachers WHERE active=1 ORDER BY id DESC")

    async def set_teacher_active(self, teacher_id: int, active: bool) -> bool:
        exists = await self.fetchone("SELECT id FROM teachers WHERE id=?", (teacher_id,))
        if not exists:
            return False
        await self.execute("UPDATE teachers SET active=? WHERE id=?", (1 if active else 0, teacher_id))
        return True

    async def add_teacher(self, full_name: str, subject: str, experience: str, bio: str) -> int:
        return int(await self.execute(
            "INSERT INTO teachers(full_name,subject,experience,bio,created_at) VALUES(?,?,?,?,?)",
            (full_name, subject, experience, bio, utcnow()),
        ))

    async def update_teacher(self, teacher_id: int, data: dict[str, Any]) -> bool:
        existing = await self.fetchone("SELECT id FROM teachers WHERE id=?", (teacher_id,))
        if not existing:
            return False
        await self.execute(
            "UPDATE teachers SET full_name=?,subject=?,experience=?,bio=? WHERE id=?",
            (data["full_name"], data["subject"], data.get("experience", ""), data.get("bio", ""), teacher_id),
        )
        return True

    async def create_application(self, user_id: int, data: dict[str, Any]) -> int:
        # Compatibility method for internal callers; the registration handler uses
        # create_application_if_new() to guarantee atomic deduplication.
        return int(await self.execute(
            """INSERT INTO applications(user_id,full_name,phone,course_id,level,preferred_time,message,status,created_at)
               VALUES(?,?,?,?,?,?,?,?,?)""",
            (user_id, data["full_name"], data["phone"], data["course_id"], data["level"], data["preferred_time"], data["message"], "new", utcnow()),
        ))

    async def create_application_if_new(
        self, user_id: int, data: dict[str, Any], *, within_seconds: int = 600,
    ) -> tuple[int | None, str]:
        """Atomically validate the active course, deduplicate and insert a bot application.

        Returns (application_id, 'created'), (None, 'duplicate'), or (None, 'inactive').
        BEGIN IMMEDIATE serializes concurrent submissions before the duplicate check.
        """
        digits = re.sub(r"\D", "", str(data.get("phone", "")))
        if len(digits) < 9:
            return None, "invalid_phone"
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=max(1, int(within_seconds)))).isoformat(timespec="seconds")
        async with self.connect() as db:
            await db.execute("BEGIN IMMEDIATE")
            course = await (await db.execute(
                "SELECT id FROM courses WHERE id=? AND active=1", (int(data["course_id"]),)
            )).fetchone()
            if not course:
                return None, "inactive"
            rows = await (await db.execute(
                "SELECT id,phone FROM applications WHERE user_id=? AND course_id=? AND created_at>=? ORDER BY id DESC LIMIT 25",
                (int(user_id), int(data["course_id"]), cutoff),
            )).fetchall()
            for row in rows:
                if re.sub(r"\D", "", str(row["phone"] or "")) == digits:
                    return int(row["id"]), "duplicate"
            cursor = await db.execute(
                """INSERT INTO applications(user_id,full_name,phone,course_id,level,preferred_time,message,status,created_at)
                   VALUES(?,?,?,?,?,?,?,?,?)""",
                (int(user_id), str(data["full_name"]), str(data["phone"]), int(data["course_id"]),
                 str(data.get("level", ""))[:60], str(data.get("preferred_time", ""))[:120],
                 str(data.get("message", ""))[:1000], "new", utcnow()),
            )
            return int(cursor.lastrowid), "created"

    async def application(self, app_id: int):
        return await self.fetchone(
            """SELECT a.*, c.name_uz AS course_name, u.telegram_id, u.username
               FROM applications a JOIN courses c ON c.id=a.course_id JOIN users u ON u.id=a.user_id WHERE a.id=?""",
            (app_id,),
        )

    async def applications(self, status: str | None = None, limit: int = 20, offset: int = 0, search: str = ""):
        return await self.fetchall(
            """SELECT a.*, c.name_uz AS course_name, u.telegram_id, u.username FROM applications a
               JOIN courses c ON c.id=a.course_id JOIN users u ON u.id=a.user_id
               WHERE (? IS NULL OR a.status=?)
                 AND (?='' OR a.full_name LIKE '%'||?||'%' OR a.phone LIKE '%'||?||'%' OR c.name_uz LIKE '%'||?||'%' OR COALESCE(u.username,'') LIKE '%'||?||'%' OR CAST(u.telegram_id AS TEXT) LIKE '%'||?||'%')
               ORDER BY a.id DESC LIMIT ? OFFSET ?""",
            (status, status, search, search, search, search, search, search, max(1, min(int(limit), 100)), max(0, int(offset))),
        )

    async def count_applications(self, status: str | None = None, search: str = "") -> int:
        row = await self.fetchone(
            """SELECT COUNT(*) AS total FROM applications a
               JOIN courses c ON c.id=a.course_id JOIN users u ON u.id=a.user_id
               WHERE (? IS NULL OR a.status=?)
                 AND (?='' OR a.full_name LIKE '%'||?||'%' OR a.phone LIKE '%'||?||'%' OR c.name_uz LIKE '%'||?||'%' OR COALESCE(u.username,'') LIKE '%'||?||'%' OR CAST(u.telegram_id AS TEXT) LIKE '%'||?||'%')""",
            (status, status, search, search, search, search, search, search),
        )
        return int(row["total"] if row else 0)


    async def user_applications(self, telegram_id: int, limit: int = 10):
        return await self.fetchall(
            """SELECT a.*, c.name_uz AS course_name
               FROM applications a
               JOIN users u ON u.id=a.user_id
               JOIN courses c ON c.id=a.course_id
               WHERE u.telegram_id=? ORDER BY a.id DESC LIMIT ?""",
            (telegram_id, limit),
        )

    async def update_application_status(self, app_id: int, status: str) -> None:
        result = await self.change_application_status(
            "bot", app_id, status, actor="system:legacy-update",
        )
        if not result:
            raise ValueError("Bot arizasi topilmadi.")

    async def update_web_application_status(self, app_id: int, status: str) -> None:
        result = await self.change_application_status(
            "website", app_id, status, actor="system:legacy-update",
        )
        if not result:
            raise ValueError("Sayt arizasi topilmadi.")

    async def change_application_status(
        self, source: str, app_id: int, status: str, *, actor: str, ip_address: str = "",
    ) -> dict[str, str] | None:
        """Atomically update a bot/site application and record who changed its status."""
        if source not in {"website", "bot"}:
            raise ValueError("Ariza manbasi noto‘g‘ri.")
        if status not in ALL_APPLICATION_STATUSES:
            raise ValueError("Noto‘g‘ri ariza holati.")
        if int(app_id) < 1:
            raise ValueError("Ariza ID noto‘g‘ri.")
        table = "web_applications" if source == "website" else "applications"
        async with self.connect() as db:
            await db.execute("BEGIN IMMEDIATE")
            row = await (await db.execute(f"SELECT status FROM {table} WHERE id=?", (int(app_id),))).fetchone()
            if not row:
                return None
            old_status = str(row["status"] or "")
            if old_status != status:
                await db.execute(f"UPDATE {table} SET status=? WHERE id=?", (status, int(app_id)))
                await db.execute(
                    "INSERT INTO application_status_history(source,application_id,old_status,new_status,actor,ip_address,created_at) "
                    "VALUES(?,?,?,?,?,?,?)",
                    (source, int(app_id), old_status, status, str(actor)[:120], str(ip_address)[:80], utcnow()),
                )
            return {"old_status": old_status, "new_status": status}

    async def application_status_history(self, source: str, app_id: int, limit: int = 50):
        if source not in {"website", "bot"}:
            raise ValueError("Ariza manbasi noto‘g‘ri.")
        return await self.fetchall(
            "SELECT id,source,application_id,old_status,new_status,actor,ip_address,created_at "
            "FROM application_status_history WHERE source=? AND application_id=? ORDER BY id DESC LIMIT ?",
            (source, int(app_id), max(1, min(int(limit), 100))),
        )

    async def enqueue_application_status_notification(
        self, *, source: str, application_id: int, recipient_telegram_id: int,
        status: str, message_text: str,
    ) -> int:
        """Persist a status-change notice so temporary Telegram failures do not lose it."""
        if source not in {"website", "bot"}:
            raise ValueError("Ariza manbasi noto‘g‘ri.")
        if status not in ALL_APPLICATION_STATUSES:
            raise ValueError("Noto‘g‘ri ariza holati.")
        if application_id < 1 or recipient_telegram_id < 1:
            raise ValueError("Ariza yoki Telegram ID noto‘g‘ri.")
        return int(await self.execute(
            """INSERT INTO application_status_notification_outbox(
                   source,application_id,recipient_telegram_id,status_name,message_text,created_at
               ) VALUES(?,?,?,?,?,?)""",
            (source, application_id, recipient_telegram_id, status, message_text[:3500], utcnow()),
        ))

    async def pending_application_status_notifications(
        self, recipient_id: int | None = None, limit: int = 100,
    ):
        query = (
            "SELECT * FROM application_status_notification_outbox "
            "WHERE delivery_status IN ('pending','failed') AND attempts<12"
        )
        params: list[Any] = []
        if recipient_id is not None:
            query += " AND recipient_telegram_id=?"
            params.append(int(recipient_id))
        query += " ORDER BY id LIMIT ?"
        params.append(max(1, min(int(limit), 200)))
        return await self.fetchall(query, tuple(params))

    async def mark_application_status_notification_sent(self, notification_id: int) -> None:
        await self.execute(
            "UPDATE application_status_notification_outbox "
            "SET delivery_status='sent',attempts=attempts+1,last_error='',sent_at=? WHERE id=?",
            (utcnow(), notification_id),
        )

    async def mark_application_status_notification_failed(self, notification_id: int, error: str) -> None:
        await self.execute(
            "UPDATE application_status_notification_outbox "
            "SET delivery_status=CASE WHEN attempts+1>=12 THEN 'failed' ELSE 'pending' END, "
            "attempts=attempts+1,last_error=? WHERE id=?",
            ((error or "delivery_failed")[:180], notification_id),
        )

    async def reset_exhausted_status_notifications(self, recipient_id: int) -> int:
        async with self.connect() as db:
            cur = await db.execute(
                "UPDATE application_status_notification_outbox "
                "SET delivery_status='pending',attempts=0,last_error='' "
                "WHERE recipient_telegram_id=? AND delivery_status='failed' AND attempts>=12",
                (int(recipient_id),),
            )
            return int(cur.rowcount or 0)

    async def try_consume_rate_limit(self, scope: str, fingerprint: str, window_seconds: int, maximum: int) -> bool:
        """Atomically persist a rate-limit event without storing a raw IP address."""
        now = int(datetime.now(timezone.utc).timestamp())
        cutoff = now - max(1, int(window_seconds))
        async with self.connect() as db:
            # Serialize count-and-insert so simultaneous requests cannot all pass the cap.
            await db.execute("BEGIN IMMEDIATE")
            # Periodic bounded cleanup keeps the table small without needing a scheduler.
            await db.execute("DELETE FROM rate_limit_events WHERE created_at < ?", (now - 86400,))
            row = await (await db.execute(
                "SELECT COUNT(*) AS total FROM rate_limit_events WHERE scope=? AND fingerprint=? AND created_at>?",
                (scope[:40], fingerprint[:64], cutoff),
            )).fetchone()
            if int(row["total"] if row else 0) >= max(1, int(maximum)):
                return False
            await db.execute(
                "INSERT INTO rate_limit_events(scope,fingerprint,created_at) VALUES(?,?,?)",
                (scope[:40], fingerprint[:64], now),
            )
            return True

    async def clear_rate_limit(self, scope: str, fingerprint: str) -> None:
        await self.execute(
            "DELETE FROM rate_limit_events WHERE scope=? AND fingerprint=?",
            (scope[:40], fingerprint[:64]),
        )

    async def create_web_admin_session(
        self, token_hash: str, username: str, expires_at: int, ip_address: str = ""
    ) -> None:
        async with self.connect() as db:
            await db.execute(
                "DELETE FROM web_admin_sessions WHERE expires_at <= ? OR revoked=1",
                (int(datetime.now(timezone.utc).timestamp()),),
            )
            await db.execute(
                "INSERT INTO web_admin_sessions(token_hash,username,expires_at,revoked,ip_address,created_at) VALUES(?,?,?,0,?,?)",
                (token_hash, username[:80], int(expires_at), ip_address[:64], utcnow()),
            )

    async def web_admin_session_active(self, token_hash: str, username: str) -> bool:
        row = await self.fetchone(
            """SELECT s.token_hash FROM web_admin_sessions s
               JOIN web_admin_users u ON u.username=s.username
               WHERE s.token_hash=? AND s.username=? AND s.revoked=0 AND s.expires_at>? AND u.active=1""",
            (token_hash, username, int(datetime.now(timezone.utc).timestamp())),
        )
        return row is not None

    async def revoke_web_admin_session(self, token_hash: str) -> None:
        await self.execute("UPDATE web_admin_sessions SET revoked=1 WHERE token_hash=?", (token_hash,))

    async def web_admin(self, username: str):
        return await self.fetchone(
            "SELECT username,password_hash,telegram_id,telegram_verified,role,active,created_at,created_by,updated_at FROM web_admin_users WHERE username=? COLLATE NOCASE",
            (username.strip(),),
        )

    async def web_admins(self):
        return await self.fetchall(
            """SELECT u.username,u.telegram_id,u.telegram_verified,
                      COALESCE(a.pending_link,0) AS pending_link,
                      COALESCE(a.active,0) AS telegram_admin_active,
                      COALESCE(a.bot_invite_pending,0) AS bot_invite_pending,
                      u.role,u.active,u.created_at,u.created_by,u.updated_at
               FROM web_admin_users u
               LEFT JOIN admins a ON a.telegram_id=u.telegram_id
               ORDER BY CASE u.role WHEN 'ceo' THEN 0 WHEN 'senior_admin' THEN 1 ELSE 2 END, u.username COLLATE NOCASE"""
        )

    async def web_admin_by_telegram_id(self, telegram_id: int):
        return await self.fetchone(
            "SELECT username,telegram_id,telegram_verified,role,active,created_at,created_by,updated_at FROM web_admin_users WHERE telegram_id=?",
            (telegram_id,),
        )

    async def create_web_admin(
        self, username: str, password_hash: str, role: str, created_by: str, telegram_id: int,
        created_by_telegram_id: int = 0,
    ) -> None:
        """Create a separate Website Admin account linked to an OWNER-authorized Telegram admin."""
        now = utcnow()
        clean_username = username.strip()
        if telegram_id <= 0 or role not in {"senior_admin", "junior_admin"}:
            raise ValueError("Telegram ID yoki administrator roli noto‘g‘ri.")
        try:
            async with self.connect() as db:
                existing = await (await db.execute(
                    "SELECT role,active,pending_link FROM admins WHERE telegram_id=?", (telegram_id,)
                )).fetchone()
                if existing:
                    if str(existing["role"]) in {"ceo", "owner"}:
                        raise ValueError("Asosiy administrator yoki OWNER Telegram ID’sini boshqa hisobga biriktirib bo‘lmaydi.")
                    if str(existing["role"]) != role:
                        raise ValueError("Tanlangan rol mavjud Telegram admin yozuvi roliga mos emas. Avval amaldagi rolni tekshiring.")
                    if not int(existing["pending_link"] or 0):
                        raise ValueError("Bu Telegram ID administratorlar ro‘yxatida allaqachon mavjud yoki faollashtirilgan.")
                existing_link = await (await db.execute(
                    "SELECT username FROM web_admin_users WHERE telegram_id=?", (telegram_id,)
                )).fetchone()
                if existing_link:
                    raise ValueError("Bu Telegram ID allaqachon web-admin hisobiga bog‘langan. Eski hisobni tekshiring.")
                await db.execute(
                    "INSERT INTO web_admin_users(username,password_hash,telegram_id,telegram_verified,role,active,created_at,created_by,updated_at) VALUES(?,?,?,0,?,1,?,?,?)",
                    (clean_username, password_hash, telegram_id, role, now, created_by[:80], now),
                )
                # Website account creation may stage a Telegram admin assignment when none exists.
                # Bot invitations created in Telegram are handled independently by /start.
                if existing is None:
                    await db.execute(
                        "INSERT INTO admins(telegram_id,role,active,pending_link,created_at,created_by) VALUES(?,?,0,1,?,?)",
                        (telegram_id, role, now, int(created_by_telegram_id) if created_by_telegram_id > 0 else 0),
                    )
        except ValueError:
            raise
        except Exception as exc:
            if "UNIQUE constraint failed" in str(exc):
                if "web_admin_users.telegram_id" in str(exc) or "idx_web_admin_users_telegram_id" in str(exc):
                    raise ValueError("Bu Telegram ID allaqachon boshqa admin hisobiga biriktirilgan.") from exc
                raise ValueError("Bu login allaqachon mavjud.") from exc
            raise

    async def rotate_web_admin_password(
        self, username: str, password_hash: str, *, allow_pending: bool = False,
    ) -> bool:
        """Rotate a linked admin password, revoke sessions, and require a fresh login."""
        now = utcnow()
        async with self.connect() as db:
            user = await (await db.execute(
                "SELECT username,telegram_id,role,active,telegram_verified FROM web_admin_users WHERE username=? COLLATE NOCASE",
                (username.strip(),),
            )).fetchone()
            if not user:
                raise ValueError("Administrator hisobi topilmadi.")
            if str(user["role"]) == "ceo":
                raise ValueError("CEO paroli backend/.env faylida boshqariladi.")
            if user["telegram_id"] is None:
                raise ValueError("Bu hisob Telegram ID bilan bog‘lanmagan. Avval botda /add_admin orqali qayta ro‘yxatdan o‘tkazing.")
            telegram_id = int(user["telegram_id"])
            admin = await (await db.execute(
                "SELECT role,active,pending_link FROM admins WHERE telegram_id=?", (telegram_id,)
            )).fetchone()
            if not admin or str(admin["role"]) in {"ceo", "owner"} or str(admin["role"]) != str(user["role"]):
                raise ValueError("Telegram ID va sayt adminining roli mos kelmaydi. CEO botdagi admin bog‘lanishini tekshirsin.")
            if allow_pending:
                if not int(admin["active"] or 0) and not int(admin["pending_link"] or 0):
                    raise ValueError("Bu admin botda faol yoki kutilayotgan holatda emas. Avval /add_admin orqali qayta ro‘yxatdan o‘tkazing.")
            elif not (int(user["active"] or 0) and int(user["telegram_verified"] or 0) and int(admin["active"] or 0)):
                raise ValueError("Parolni o‘zgartirish uchun avval faol admin hisobi bilan kirish kerak.")

            await db.execute(
                "UPDATE web_admin_users SET password_hash=?,active=1,telegram_verified=0,updated_at=? WHERE username=? COLLATE NOCASE",
                (password_hash, now, username.strip()),
            )
            await db.execute(
                "UPDATE admins SET active=0,pending_link=1,bot_invite_pending=0 WHERE telegram_id=?",
                (telegram_id,),
            )
            await db.execute(
                "UPDATE web_admin_sessions SET revoked=1 WHERE username=? COLLATE NOCASE",
                (username.strip(),),
            )
        return True

    async def set_web_admin_active(self, username: str, active: bool) -> bool:
        now = utcnow()
        async with self.connect() as db:
            row = await (await db.execute(
                "SELECT username,telegram_id,role FROM web_admin_users WHERE username=? COLLATE NOCASE",
                (username.strip(),),
            )).fetchone()
            if not row:
                return False
            await db.execute(
                "UPDATE web_admin_users SET active=?,telegram_verified=CASE WHEN role='ceo' THEN 1 ELSE 0 END,updated_at=? WHERE username=? COLLATE NOCASE",
                (1 if active else 0, now, username.strip()),
            )
            if row["telegram_id"] is not None and row["role"] != "ceo":
                # Re-enabling an account requires its owner to log in again before bot rights return.
                await db.execute(
                    "UPDATE admins SET active=0,pending_link=?,bot_invite_pending=0,role=?,created_by=COALESCE(created_by,0) WHERE telegram_id=?",
                    (1 if active else 0, str(row["role"]), int(row["telegram_id"])),
                )
            if not active:
                await db.execute(
                    "UPDATE web_admin_sessions SET revoked=1 WHERE username=? COLLATE NOCASE",
                    (username.strip(),),
                )
        return True

    async def mark_telegram_admin_verified(self, username: str) -> int | None:
        """Complete Website Admin linking after the account proves password ownership."""
        now = utcnow()
        async with self.connect() as db:
            row = await (await db.execute(
                "SELECT telegram_id,role,active,telegram_verified FROM web_admin_users WHERE username=? COLLATE NOCASE",
                (username.strip(),),
            )).fetchone()
            if not row or not int(row["active"] or 0):
                return None
            if row["telegram_id"] is None:
                if str(row["role"]) != "ceo":
                    await db.execute(
                        "UPDATE web_admin_users SET active=0,telegram_verified=0,updated_at=? WHERE username=? COLLATE NOCASE",
                        (now, username.strip()),
                    )
                    await db.execute(
                        "UPDATE web_admin_sessions SET revoked=1 WHERE username=? COLLATE NOCASE",
                        (username.strip(),),
                    )
                return None
            telegram_id = int(row["telegram_id"])
            if str(row["role"]) == "ceo":
                await db.execute(
                    "UPDATE web_admin_users SET telegram_verified=1,updated_at=? WHERE username=? COLLATE NOCASE",
                    (now, username.strip()),
                )
                return telegram_id
            existing = await (await db.execute(
                "SELECT telegram_id,role,active,pending_link FROM admins WHERE telegram_id=?", (telegram_id,)
            )).fetchone()
            if not existing:
                return None
            if (
                int(existing["active"] or 0) == 1
                and int(row["telegram_verified"] or 0) == 1
                and str(existing["role"]) == str(row["role"])
            ):
                return telegram_id
            if int(existing["pending_link"] or 0) != 1 or str(existing["role"]) != str(row["role"]):
                # Old/unlinked accounts must be explicitly re-added by the owner in Telegram.
                await db.execute(
                    "UPDATE web_admin_users SET active=0,telegram_verified=0,updated_at=? WHERE username=? COLLATE NOCASE",
                    (now, username.strip()),
                )
                await db.execute(
                    "UPDATE web_admin_sessions SET revoked=1 WHERE username=? COLLATE NOCASE",
                    (username.strip(),),
                )
                return None
            await db.execute(
                "UPDATE web_admin_users SET telegram_verified=1,updated_at=? WHERE username=? COLLATE NOCASE",
                (now, username.strip()),
            )
            await db.execute(
                "UPDATE admins SET active=1,pending_link=0,bot_invite_pending=0 WHERE telegram_id=? AND role NOT IN ('ceo','owner')",
                (telegram_id,),
            )
            return telegram_id

    async def count_active_web_admins(self, role: str) -> int:
        row = await self.fetchone(
            "SELECT COUNT(*) AS total FROM web_admin_users WHERE role=? AND active=1", (role,)
        )
        return int(row["total"] if row else 0)

    async def write_admin_audit(
        self, actor: str, action: str, *, entity_type: str = "", entity_id: int | None = None,
        details: str = "", ip_address: str = "",
    ) -> None:
        await self.execute(
            """INSERT INTO admin_audit(actor,action,entity_type,entity_id,details,ip_address,created_at)
               VALUES(?,?,?,?,?,?,?)""",
            (actor[:100], action[:100], entity_type[:80], entity_id, details[:500], ip_address[:64], utcnow()),
        )

    async def admin_audit_entries(self, limit: int = 20):
        safe_limit = max(1, min(int(limit), 100))
        return await self.fetchall(
            "SELECT id,actor,action,entity_type,entity_id,details,ip_address,created_at "
            "FROM admin_audit ORDER BY id DESC LIMIT ?", (safe_limit,)
        )

    async def create_message(self, user_id: int, topic: str, message_text: str) -> int:
        return int(await self.execute(
            "INSERT INTO messages(user_id,topic,message_text,status,created_at) VALUES(?,?,?,?,?)",
            (user_id, topic, message_text, "new", utcnow()),
        ))

    async def message_list(
        self, limit: int = 20, *, status: str | None = None, search: str = "",
    ):
        if status not in {None, "new", "answered"}:
            raise ValueError("Murojaat holati noto‘g‘ri.")
        safe_limit = max(1, min(int(limit), 100))
        term = str(search or "").strip()[:120]
        return await self.fetchall(
            """SELECT m.*, u.telegram_id, u.username, u.first_name, u.last_name
               FROM messages m JOIN users u ON u.id=m.user_id
               WHERE (? IS NULL OR m.status=?)
                 AND (?='' OR m.topic LIKE '%'||?||'%' OR m.message_text LIKE '%'||?||'%' 
                      OR u.first_name LIKE '%'||?||'%' OR COALESCE(u.last_name,'') LIKE '%'||?||'%' 
                      OR COALESCE(u.username,'') LIKE '%'||?||'%' OR CAST(u.telegram_id AS TEXT) LIKE '%'||?||'%')
               ORDER BY m.id DESC LIMIT ?""",
            (status, status, term, term, term, term, term, term, term, safe_limit),
        )

    async def enqueue_support_notifications(
        self, message_id: int, message_text: str, recipient_ids: Sequence[int],
    ) -> int:
        unique_recipients = tuple(dict.fromkeys(int(value) for value in recipient_ids if int(value) > 0))
        if not unique_recipients:
            return 0
        now = utcnow()
        async with self.connect() as db:
            for recipient_id in unique_recipients:
                await db.execute(
                    "INSERT OR IGNORE INTO support_notification_outbox "
                    "(message_id,recipient_telegram_id,message_text,status,attempts,last_error,created_at) "
                    "VALUES(?,?,?,'pending',0,'',?)",
                    (int(message_id), recipient_id, message_text[:4000], now),
                )
        return len(unique_recipients)

    async def pending_support_notifications(self, limit: int = 100):
        return await self.fetchall(
            "SELECT * FROM support_notification_outbox "
            "WHERE status IN ('pending','failed') AND attempts<12 ORDER BY id LIMIT ?",
            (max(1, min(int(limit), 200)),),
        )

    async def mark_support_notification_sent(self, notification_id: int) -> None:
        await self.execute(
            "UPDATE support_notification_outbox SET status='sent',attempts=attempts+1,last_error='',sent_at=? WHERE id=?",
            (utcnow(), int(notification_id)),
        )

    async def mark_support_notification_failed(self, notification_id: int, error: str) -> None:
        await self.execute(
            "UPDATE support_notification_outbox SET status=CASE WHEN attempts+1>=12 THEN 'failed' ELSE 'pending' END, "
            "attempts=attempts+1,last_error=? WHERE id=?",
            ((error or 'delivery_failed')[:180], int(notification_id)),
        )

    async def course_by_slug(self, slug: str):
        return await self.fetchone("SELECT * FROM courses WHERE slug=? AND active=1", (slug,))

    async def add_course(self, *, kind: str, name_uz: str, name_ru: str, name_en: str, description_uz: str, description_ru: str, description_en: str, icon: str) -> int:
        slug = course_slug(name_uz)
        existing = await self.fetchone("SELECT id FROM courses WHERE slug=?", (slug,))
        if existing:
            raise ValueError("Bu kurs allaqachon mavjud.")
        return int(await self.execute(
            """INSERT INTO courses(name_uz,name_ru,name_en,kind,slug,description_uz,description_ru,description_en,icon,active,created_at)
               VALUES(?,?,?,?,?,?,?,?,?,1,?)""",
            (name_uz,name_ru,name_en,kind,slug,description_uz,description_ru,description_en,icon,utcnow()),
        ))


    async def create_web_application(
        self, *, name: str, phone: str, telegram: str, course_id: int, level: str,
        preferred_time: str, message: str,
    ) -> int:
        return int(await self.execute(
            """INSERT INTO web_applications(full_name,phone,telegram_username,course_id,level,preferred_time,message,status,created_at)
               VALUES(?,?,?,?,?,?,?,?,?)""",
            (name, phone, telegram, course_id, level, preferred_time, message, "new", utcnow()),
        ))

    async def create_web_application_if_new(
        self, *, name: str, phone: str, telegram: str, course_id: int, level: str,
        preferred_time: str, message: str, within_seconds: int = 600,
        tracking_token_hash: str = "",
    ) -> tuple[int | None, int | None, str]:
        """Atomically deduplicate and save a public application.

        Returns (new_id, None, 'created'), (None, duplicate_id, 'duplicate'),
        or (None, None, 'inactive').
        """
        digits = re.sub(r"\D", "", phone)
        if not 9 <= len(digits) <= 15:
            return None, None, "invalid_phone"
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=max(1, int(within_seconds)))).isoformat(timespec="seconds")
        async with self.connect() as db:
            await db.execute("BEGIN IMMEDIATE")
            course = await (await db.execute(
                "SELECT id FROM courses WHERE id=? AND active=1", (int(course_id),)
            )).fetchone()
            if not course:
                return None, None, "inactive"
            rows = await (await db.execute(
                "SELECT id,phone FROM web_applications WHERE course_id=? AND created_at>=? ORDER BY id DESC LIMIT 50",
                (int(course_id), cutoff),
            )).fetchall()
            for row in rows:
                if re.sub(r"\D", "", str(row["phone"] or "")) == digits:
                    return None, int(row["id"]), "duplicate"
            cursor = await db.execute(
                """INSERT INTO web_applications(
                       full_name,phone,telegram_username,course_id,level,preferred_time,message,
                       status,tracking_token_hash,created_at
                   ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (
                    name, phone, telegram, int(course_id), level[:60], preferred_time[:120],
                    message[:1000], "new", tracking_token_hash, utcnow(),
                ),
            )
            return int(cursor.lastrowid), None, "created"

    async def web_application_by_tracking_hash(self, token_hash: str):
        """Return minimal application status data for a valid, opaque bearer code."""
        return await self.fetchone(
            """SELECT w.status, w.created_at, c.name_uz AS course_name
               FROM web_applications w
               JOIN courses c ON c.id=w.course_id
               WHERE w.tracking_token_hash=? LIMIT 1""",
            (token_hash,),
        )

    async def recent_duplicate_web_application(
        self, *, course_id: int, phone: str, within_seconds: int = 600,
    ):
        """Return a recent matching phone/course application to prevent accidental duplicates."""
        digits = re.sub(r"\D", "", phone)
        if len(digits) < 9:
            return None
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=max(1, within_seconds))).isoformat(timespec="seconds")
        rows = await self.fetchall(
            "SELECT id,phone,created_at FROM web_applications WHERE course_id=? AND created_at>=? ORDER BY id DESC LIMIT 50",
            (course_id, cutoff),
        )
        for row in rows:
            if re.sub(r"\D", "", str(row["phone"] or "")) == digits:
                return row
        return None

    async def user_application_count(self, user_id: int) -> int:
        row = await self.fetchone("SELECT COUNT(*) AS total FROM applications WHERE user_id=?", (user_id,))
        return int(row["total"] if row else 0)

    async def web_application(self, application_id: int):
        return await self.fetchone(
            """SELECT w.*, c.name_uz AS course_name FROM web_applications w
               JOIN courses c ON c.id=w.course_id WHERE w.id=?""",
            (application_id,),
        )

    async def web_applications(self, status: str | None = None, limit: int = 20, offset: int = 0, search: str = ""):
        return await self.fetchall(
            """SELECT w.*, c.name_uz AS course_name FROM web_applications w
               JOIN courses c ON c.id=w.course_id
               WHERE (? IS NULL OR w.status=?)
                 AND (?='' OR w.full_name LIKE '%'||?||'%' OR w.phone LIKE '%'||?||'%' OR c.name_uz LIKE '%'||?||'%' OR w.telegram_username LIKE '%'||?||'%')
               ORDER BY w.id DESC LIMIT ? OFFSET ?""",
            (status, status, search, search, search, search, search, max(1, min(int(limit), 100)), max(0, int(offset))),
        )

    async def count_web_applications(self, status: str | None = None, search: str = "") -> int:
        row = await self.fetchone(
            """SELECT COUNT(*) AS total FROM web_applications w JOIN courses c ON c.id=w.course_id
               WHERE (? IS NULL OR w.status=?)
                 AND (?='' OR w.full_name LIKE '%'||?||'%' OR w.phone LIKE '%'||?||'%' OR c.name_uz LIKE '%'||?||'%' OR w.telegram_username LIKE '%'||?||'%')""",
            (status, status, search, search, search, search, search),
        )
        return int(row["total"] if row else 0)

    async def message(self, message_id: int):
        return await self.fetchone(
            """SELECT m.*, u.telegram_id, u.username, u.first_name FROM messages m
               JOIN users u ON u.id=m.user_id WHERE m.id=?""", (message_id,)
        )

    async def reply_message(self, message_id: int, reply_text: str) -> None:
        await self.execute(
            "UPDATE messages SET status='answered', admin_reply=?, replied_at=? WHERE id=?",
            (reply_text, utcnow(), message_id),
        )

    async def stats(self) -> dict[str, int]:
        result = {}
        for key, query in {
            "users": "SELECT COUNT(*) c FROM users",
            "courses": "SELECT COUNT(*) c FROM courses WHERE active=1",
            "teachers": "SELECT COUNT(*) c FROM teachers WHERE active=1",
            "applications": "SELECT COUNT(*) c FROM applications",
            "new_applications": "SELECT COUNT(*) c FROM applications WHERE status='new'",
            "applications_in_review": "SELECT (SELECT COUNT(*) FROM applications WHERE status='in_review')+(SELECT COUNT(*) FROM web_applications WHERE status='in_review') c",
            "applications_contacted": "SELECT (SELECT COUNT(*) FROM applications WHERE status='contacted')+(SELECT COUNT(*) FROM web_applications WHERE status='contacted') c",
            "applications_accepted": "SELECT (SELECT COUNT(*) FROM applications WHERE status='accepted')+(SELECT COUNT(*) FROM web_applications WHERE status='accepted') c",
            "applications_rejected": "SELECT (SELECT COUNT(*) FROM applications WHERE status='rejected')+(SELECT COUNT(*) FROM web_applications WHERE status='rejected') c",
            "messages": "SELECT COUNT(*) c FROM messages WHERE status='new'",
            "web_applications": "SELECT COUNT(*) c FROM web_applications",
            "new_web_applications": "SELECT COUNT(*) c FROM web_applications WHERE status='new'",
            "resources": "SELECT COUNT(*) c FROM learning_resources WHERE active=1",
            "tests": "SELECT COUNT(*) c FROM learning_resources WHERE active=1 AND category='quiz'",
            "notifications_pending": "SELECT COUNT(*) c FROM notification_outbox WHERE status='pending'",
            "notifications_failed": "SELECT COUNT(*) c FROM notification_outbox WHERE status='failed'",
            "suspended_users": "SELECT COUNT(*) c FROM users WHERE account_status='suspended' AND (suspended_until IS NULL OR suspended_until>datetime('now'))",
        }.items():
            row = await self.fetchone(query)
            result[key] = int(row["c"])
        return result

    async def add_teacher_manager(self, telegram_id: int, course_id: int, created_by: int) -> None:
        if telegram_id <= 0:
            raise ValueError("Telegram ID musbat bo‘lishi kerak.")
        course = await self.fetchone("SELECT id FROM courses WHERE id=? AND active=1", (course_id,))
        if not course:
            raise ValueError("Faol yo‘nalish topilmadi.")
        if await self.is_admin(telegram_id):
            raise ValueError("Administratorni alohida ustoz sifatida ro‘yxatdan o‘tkazmang.")
        await self.assign_teacher_subject(telegram_id, course_id, created_by)
        # Legacy mapping remains populated for older handlers and installations.
        await self.execute(
            "INSERT INTO teacher_managers(telegram_id,course_id,active,created_by,created_at) VALUES(?,?,1,?,?) "
            "ON CONFLICT(telegram_id) DO UPDATE SET course_id=excluded.course_id,active=1,created_by=excluded.created_by,created_at=excluded.created_at",
            (telegram_id, course_id, created_by, utcnow()),
        )

    async def teacher_manager(self, telegram_id: int):
        legacy = await self.fetchone(
            "SELECT tm.telegram_id,tm.course_id,tm.active,tm.created_by,c.name_uz AS course_name,c.slug AS course_slug "
            "FROM teacher_managers tm JOIN courses c ON c.id=tm.course_id WHERE tm.telegram_id=? AND tm.active=1 AND c.active=1",
            (telegram_id,),
        )
        if legacy:
            return legacy
        return await self.fetchone(
            "SELECT tsa.telegram_id,tsa.course_id,tsa.active,tsa.created_by,c.name_uz AS course_name,c.slug AS course_slug "
            "FROM teacher_subject_assignments tsa JOIN courses c ON c.id=tsa.course_id "
            "WHERE tsa.telegram_id=? AND tsa.active=1 AND c.active=1 ORDER BY tsa.id LIMIT 1",
            (int(telegram_id),),
        )

    async def teacher_managers(self, include_inactive: bool = False):
        active_clause = "" if include_inactive else " AND tsa.active=1"
        legacy_clause = "" if include_inactive else " AND tm.active=1"
        return await self.fetchall(
            "SELECT * FROM ("
            "SELECT tm.telegram_id,tm.course_id,tm.active,tm.created_by,tm.created_at,c.name_uz AS course_name "
            "FROM teacher_managers tm JOIN courses c ON c.id=tm.course_id WHERE 1=1" + legacy_clause + " "
            "UNION ALL "
            "SELECT tsa.telegram_id,tsa.course_id,tsa.active,tsa.created_by,tsa.created_at,c.name_uz AS course_name "
            "FROM teacher_subject_assignments tsa JOIN courses c ON c.id=tsa.course_id "
            "WHERE NOT EXISTS (SELECT 1 FROM teacher_managers tm WHERE tm.telegram_id=tsa.telegram_id AND tm.course_id=tsa.course_id AND tm.active=1)" + active_clause + " "
            ") ORDER BY created_at DESC",
        )

    async def remove_teacher_manager(self, telegram_id: int) -> bool:
        legacy = await self.execute("UPDATE teacher_managers SET active=0 WHERE telegram_id=? AND active=1", (telegram_id,))
        extended = await self.execute("UPDATE teacher_subject_assignments SET active=0 WHERE telegram_id=? AND active=1", (telegram_id,))
        return bool(legacy or extended)

    async def add_learning_resource(
        self, *, category: str, course_id: int, title: str, description: str = "", content: str = "",
        media_type: str = "text", telegram_file_id: str = "", created_by_telegram_id: int = 0,
        created_by_role: str = "admin", active: bool = True, group_id: int | None = None,
        level: str = "", file_name: str = "", file_mime: str = "", file_size: int = 0,
    ) -> int:
        if category not in {"book", "vocabulary", "movie", "music", "quiz"}:
            raise ValueError("Resurs turi noto‘g‘ri.")
        course = await self.fetchone("SELECT id FROM courses WHERE id=? AND active=1", (course_id,))
        if not course:
            raise ValueError("Faol yo‘nalish topilmadi.")
        title = " ".join(title.split())
        if not 2 <= len(title) <= 180:
            raise ValueError("Resurs nomi 2–180 belgi bo‘lishi kerak.")
        if media_type not in {"text", "url", "video", "audio", "document", "photo"}:
            raise ValueError("Media turi noto‘g‘ri.")
        if category != "quiz" and not (content.strip() or telegram_file_id.strip()):
            raise ValueError("Matn, havola yoki fayl yuboring.")
        if group_id is not None:
            group = await self.fetchone("SELECT id,course_id FROM education_groups WHERE id=? AND status='active'", (int(group_id),))
            if not group or int(group["course_id"]) != int(course_id):
                raise ValueError("Guruh tanlangan yo‘nalishga tegishli emas.")
        teacher_pending = created_by_role == "teacher"
        publication_status = "pending" if teacher_pending else "published"
        is_active = 0 if teacher_pending else (1 if active else 0)
        return int(await self.execute(
            "INSERT INTO learning_resources(category,course_id,title,description,content,media_type,telegram_file_id,created_by_telegram_id,created_by_role,active,created_at,publication_status,group_id,level,file_name,file_mime,file_size) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (category, course_id, title, description.strip(), content.strip(), media_type, telegram_file_id,
             created_by_telegram_id, created_by_role, is_active, utcnow(), publication_status, group_id,
             (level or "").strip()[:80], (file_name or "").strip()[:180], (file_mime or "").strip()[:120], max(0, int(file_size))),
        ))

    async def learning_resources(self, *, course_id: int | None = None, category: str | None = None, include_inactive: bool = False, limit: int = 100):
        clauses, params = [], []
        if not include_inactive:
            clauses.append("r.active=1")
        if course_id is not None:
            clauses.append("r.course_id=?")
            params.append(course_id)
        if category is not None:
            clauses.append("r.category=?")
            params.append(category)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        params.append(max(1, min(int(limit), 200)))
        return await self.fetchall(
            "SELECT r.id,r.category,r.course_id,r.title,r.description,r.content,r.media_type,r.telegram_file_id," 
            "r.created_by_telegram_id,r.created_by_role,r.active,r.created_at,r.publication_status,r.group_id,r.level,r.file_name,r.file_mime,r.file_size,c.name_uz AS course_name,c.slug AS course_slug "
            "FROM learning_resources r JOIN courses c ON c.id=r.course_id" + where + " ORDER BY r.id DESC LIMIT ?", tuple(params)
        )

    async def learning_resource(self, resource_id: int, *, active_only: bool = True):
        clause = " AND r.active=1" if active_only else ""
        return await self.fetchone(
            "SELECT r.id,r.category,r.course_id,r.title,r.description,r.content,r.media_type,r.telegram_file_id," 
            "r.created_by_telegram_id,r.created_by_role,r.active,r.created_at,r.publication_status,r.group_id,r.level,r.file_name,r.file_mime,r.file_size,c.name_uz AS course_name,c.slug AS course_slug "
            "FROM learning_resources r JOIN courses c ON c.id=r.course_id WHERE r.id=?" + clause,
            (resource_id,),
        )

    async def set_learning_resource_active(self, resource_id: int, active: bool) -> bool:
        result = await self.execute(
            "UPDATE learning_resources SET active=?,publication_status=? WHERE id=?",
            (1 if active else 0, "published" if active else "archived", resource_id),
        )
        return bool(result)

    async def add_quiz_question(self, resource_id: int, question_text: str, options: list[str], correct_index: int, explanation: str = "") -> int:
        import json
        resource = await self.learning_resource(resource_id, active_only=False)
        if not resource or resource["category"] != "quiz":
            raise ValueError("Test topilmadi.")
        clean_options = [" ".join(str(option).split()) for option in options]
        if not 2 <= len(clean_options) <= 6 or any(not option or len(option) > 180 for option in clean_options):
            raise ValueError("Testda 2–6 ta, har biri 1–180 belgilik javob bo‘lishi kerak.")
        if not 0 <= correct_index < len(clean_options):
            raise ValueError("To‘g‘ri javob indeksi noto‘g‘ri.")
        count = await self.fetchone("SELECT COUNT(*) AS total FROM quiz_questions WHERE resource_id=?", (resource_id,))
        position = int(count["total"] if count else 0) + 1
        return int(await self.execute(
            "INSERT INTO quiz_questions(resource_id,position,question_text,options_json,correct_index,explanation,created_at) VALUES(?,?,?,?,?,?,?)",
            (resource_id, position, " ".join(question_text.split()), json.dumps(clean_options, ensure_ascii=False), correct_index, explanation.strip(), utcnow()),
        ))

    async def quiz_questions(self, resource_id: int):
        import json
        rows = await self.fetchall("SELECT * FROM quiz_questions WHERE resource_id=? ORDER BY position", (resource_id,))
        result = []
        for row in rows:
            item = dict(row)
            try:
                item["options"] = json.loads(item.pop("options_json"))
            except (ValueError, TypeError):
                item["options"] = []
                item.pop("options_json", None)
            result.append(item)
        return result

    async def start_or_resume_quiz_session(
        self, *, telegram_id: int, user_id: int, resource_id: int, question_total: int,
    ) -> dict[str, Any]:
        """Create one durable active quiz per Telegram user, or resume the same quiz."""
        if telegram_id < 1 or user_id < 1 or resource_id < 1 or question_total < 1:
            raise ValueError("Test seansi ma’lumoti noto‘g‘ri.")
        async with self.connect() as db:
            await db.execute("BEGIN IMMEDIATE")
            existing = await (await db.execute(
                "SELECT * FROM quiz_sessions WHERE telegram_id=?", (telegram_id,)
            )).fetchone()
            if existing:
                if int(existing["resource_id"]) != resource_id:
                    raise ValueError("Boshqa test yakunlanmagan. Avval boshlangan testni tugating.")
                if int(existing["user_id"]) != user_id or int(existing["question_total"]) != question_total:
                    await db.execute("DELETE FROM quiz_sessions WHERE telegram_id=?", (telegram_id,))
                else:
                    return dict(existing)
            await db.execute(
                "INSERT INTO quiz_sessions(telegram_id,user_id,resource_id,current_index,question_total,score,started_at_epoch,updated_at) "
                "VALUES(?,?,?,0,?,0,?,?)",
                (telegram_id, user_id, resource_id, question_total, int(time.time()), utcnow()),
            )
            row = await (await db.execute("SELECT * FROM quiz_sessions WHERE telegram_id=?", (telegram_id,))).fetchone()
            return dict(row)

    async def quiz_session(self, telegram_id: int, resource_id: int | None = None):
        query = "SELECT * FROM quiz_sessions WHERE telegram_id=?"
        params: tuple[Any, ...] = (int(telegram_id),)
        if resource_id is not None:
            query += " AND resource_id=?"
            params += (int(resource_id),)
        row = await self.fetchone(query, params)
        return dict(row) if row else None

    async def advance_quiz_session(
        self, *, telegram_id: int, resource_id: int, expected_index: int, correct: bool,
    ) -> dict[str, Any] | None:
        """Atomically accept one answer; a duplicate or stale callback cannot score twice."""
        async with self.connect() as db:
            await db.execute("BEGIN IMMEDIATE")
            row = await (await db.execute(
                "SELECT * FROM quiz_sessions WHERE telegram_id=? AND resource_id=?",
                (int(telegram_id), int(resource_id)),
            )).fetchone()
            if not row or int(row["current_index"]) != int(expected_index) or int(row["current_index"]) >= int(row["question_total"]):
                return None
            await db.execute(
                "UPDATE quiz_sessions SET current_index=current_index+1,score=score+?,updated_at=? "
                "WHERE telegram_id=? AND resource_id=? AND current_index=?",
                (1 if correct else 0, utcnow(), int(telegram_id), int(resource_id), int(expected_index)),
            )
            updated = await (await db.execute(
                "SELECT * FROM quiz_sessions WHERE telegram_id=? AND resource_id=?",
                (int(telegram_id), int(resource_id)),
            )).fetchone()
            return dict(updated) if updated else None

    async def complete_quiz_session(
        self, *, telegram_id: int, resource_id: int,
        source_chat_id: int | None = None, source_chat_type: str = "private",
    ) -> dict[str, int] | None:
        """Save a finished attempt and remove its active session in one transaction."""
        async with self.connect() as db:
            await db.execute("BEGIN IMMEDIATE")
            session = await (await db.execute(
                "SELECT * FROM quiz_sessions WHERE telegram_id=? AND resource_id=?",
                (int(telegram_id), int(resource_id)),
            )).fetchone()
            if not session or int(session["current_index"]) != int(session["question_total"]):
                return None
            resource = await (await db.execute(
                "SELECT course_id,category FROM learning_resources WHERE id=?", (int(resource_id),)
            )).fetchone()
            if not resource or str(resource["category"]) != "quiz":
                raise ValueError("Test topilmadi.")
            total = int(session["question_total"])
            score = int(session["score"])
            duration = max(0, min(int(time.time()) - int(session["started_at_epoch"]), 7 * 24 * 60 * 60))
            completed_at = utcnow()
            started_at = datetime.fromtimestamp(int(session["started_at_epoch"]), timezone.utc).isoformat(timespec="seconds")
            chat_type = source_chat_type if source_chat_type in {"private", "group", "supergroup", "channel", "sender_chat"} else "private"
            await db.execute(
                "INSERT INTO quiz_attempts(user_id,resource_id,course_id,score,total,percent,duration_seconds,source_chat_id,source_chat_type,started_at,completed_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (int(session["user_id"]), int(resource_id), int(resource["course_id"]), score, total,
                 round(score / total * 100), duration, int(source_chat_id) if source_chat_id is not None else None,
                 chat_type, started_at, completed_at),
            )
            await db.execute("DELETE FROM quiz_sessions WHERE telegram_id=? AND resource_id=?", (int(telegram_id), int(resource_id)))
            return {"score": score, "total": total, "percent": round(score / total * 100), "duration_seconds": duration}

    async def toggle_favorite(self, user_id: int, resource_id: int) -> bool:
        """Toggle a resource favorite for one Telegram user; return the resulting saved state."""
        now = utcnow()
        async with self.connect() as db:
            resource = await (await db.execute(
                "SELECT id FROM learning_resources WHERE id=? AND active=1", (int(resource_id),)
            )).fetchone()
            if not resource:
                raise ValueError("Faol material topilmadi.")
            existing = await (await db.execute(
                "SELECT id FROM user_favorites WHERE user_id=? AND resource_id=?",
                (int(user_id), int(resource_id)),
            )).fetchone()
            if existing:
                await db.execute("DELETE FROM user_favorites WHERE user_id=? AND resource_id=?", (int(user_id), int(resource_id)))
                return False
            await db.execute(
                "INSERT OR IGNORE INTO user_favorites(user_id,resource_id,created_at) VALUES(?,?,?)",
                (int(user_id), int(resource_id), now),
            )
            return True

    async def is_favorite(self, user_id: int, resource_id: int) -> bool:
        row = await self.fetchone(
            "SELECT 1 FROM user_favorites WHERE user_id=? AND resource_id=?",
            (int(user_id), int(resource_id)),
        )
        return bool(row)

    async def user_favorites(self, user_id: int, limit: int = 50):
        return await self.fetchall(
            "SELECT r.id,r.category,r.course_id,r.title,r.description,r.content,r.media_type,r.telegram_file_id,"
            "r.created_by_telegram_id,r.created_by_role,r.active,r.created_at,c.name_uz AS course_name,c.slug AS course_slug "
            "FROM user_favorites f JOIN learning_resources r ON r.id=f.resource_id "
            "JOIN courses c ON c.id=r.course_id WHERE f.user_id=? AND r.active=1 "
            "ORDER BY f.created_at DESC LIMIT ?",
            (int(user_id), max(1, min(int(limit), 100))),
        )

    async def record_quiz_attempt(
        self, *, user_id: int, resource_id: int, score: int, total: int,
        duration_seconds: int = 0, source_chat_id: int | None = None, source_chat_type: str = "private",
    ) -> int:
        """Persist a completed quiz result. Each completed attempt gets its own row."""
        if total < 1 or score < 0 or score > total:
            raise ValueError("Test natijasi noto‘g‘ri.")
        resource = await self.fetchone(
            "SELECT id,course_id,category FROM learning_resources WHERE id=?",
            (int(resource_id),),
        )
        if not resource or str(resource["category"]) != "quiz":
            raise ValueError("Test topilmadi.")
        user = await self.fetchone("SELECT id FROM users WHERE id=?", (int(user_id),))
        if not user:
            raise ValueError("Foydalanuvchi topilmadi.")
        completed_at = utcnow()
        safe_duration = max(0, min(int(duration_seconds), 7 * 24 * 60 * 60))
        started_at = (datetime.now(timezone.utc) - timedelta(seconds=safe_duration)).isoformat(timespec="seconds")
        chat_type = source_chat_type if source_chat_type in {"private", "group", "supergroup", "channel", "sender_chat"} else "private"
        return int(await self.execute(
            "INSERT INTO quiz_attempts(user_id,resource_id,course_id,score,total,percent,duration_seconds,source_chat_id,source_chat_type,started_at,completed_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (int(user_id), int(resource_id), int(resource["course_id"]), int(score), int(total), round(score / total * 100),
             safe_duration, int(source_chat_id) if source_chat_id is not None else None, chat_type, started_at, completed_at),
        ))

    async def user_quiz_stats(self, user_id: int) -> dict[str, int]:
        row = await self.fetchone(
            "SELECT COUNT(*) AS attempts,COALESCE(AVG(percent),0) AS average_percent,COALESCE(MAX(percent),0) AS best_percent "
            "FROM quiz_attempts WHERE user_id=?",
            (int(user_id),),
        )
        return {
            "attempts": int(row["attempts"] or 0) if row else 0,
            "average_percent": round(float(row["average_percent"] or 0)) if row else 0,
            "best_percent": int(row["best_percent"] or 0) if row else 0,
        }

    async def user_learning_streak(self, user_id: int) -> int:
        """Return consecutive UTC calendar days with a completed quiz attempt.

        A streak remains active through the current day or yesterday; older activity
        starts a new streak at zero until the user completes another quiz.
        """
        rows = await self.fetchall(
            "SELECT DISTINCT substr(completed_at,1,10) AS activity_date "
            "FROM quiz_attempts WHERE user_id=? ORDER BY activity_date DESC LIMIT 366",
            (int(user_id),),
        )
        if not rows:
            return 0
        today = datetime.now(timezone.utc).date()
        try:
            days = [datetime.strptime(str(row["activity_date"]), "%Y-%m-%d").date() for row in rows]
        except (TypeError, ValueError):
            return 0
        first_day = days[0]
        if first_day < today - timedelta(days=1) or first_day > today:
            return 0
        streak = 0
        expected = first_day
        for activity_day in days:
            if activity_day == expected:
                streak += 1
                expected -= timedelta(days=1)
            elif activity_day < expected:
                break
        return streak

    async def recent_user_quiz_attempts(self, user_id: int, limit: int = 10):
        return await self.fetchall(
            "SELECT qa.id,qa.resource_id,qa.course_id,qa.score,qa.total,qa.percent,qa.duration_seconds,qa.source_chat_type,qa.completed_at,"
            "r.title AS quiz_title,c.name_uz AS course_name FROM quiz_attempts qa "
            "JOIN learning_resources r ON r.id=qa.resource_id JOIN courses c ON c.id=qa.course_id "
            "WHERE qa.user_id=? ORDER BY qa.completed_at DESC,qa.id DESC LIMIT ?",
            (int(user_id), max(1, min(int(limit), 50))),
        )

    async def quiz_attempts(self, *, limit: int = 100, course_id: int | None = None, resource_id: int | None = None):
        clauses = []
        params: list[Any] = []
        if course_id is not None:
            clauses.append("qa.course_id=?")
            params.append(int(course_id))
        if resource_id is not None:
            clauses.append("qa.resource_id=?")
            params.append(int(resource_id))
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        params.append(max(1, min(int(limit), 200)))
        return await self.fetchall(
            "SELECT qa.id,qa.user_id,qa.resource_id,qa.course_id,qa.score,qa.total,qa.percent,qa.duration_seconds,"
            "qa.source_chat_id,qa.source_chat_type,qa.started_at,qa.completed_at,u.telegram_id,u.first_name,u.last_name,u.username,"
            "r.title AS quiz_title,c.name_uz AS course_name FROM quiz_attempts qa "
            "JOIN users u ON u.id=qa.user_id JOIN learning_resources r ON r.id=qa.resource_id "
            "JOIN courses c ON c.id=qa.course_id" + where + " ORDER BY qa.completed_at DESC,qa.id DESC LIMIT ?",
            tuple(params),
        )

    async def enqueue_application_notifications(self, application_id: int, message_text: str, recipient_ids: Sequence[int], *, source: str = "website") -> int:
        """Persist the Telegram fan-out before attempting delivery; no app data is lost on API/bot restart."""
        if source not in {"website", "bot"}:
            raise ValueError("Bildirishnoma manbasi noto‘g‘ri.")
        if not recipient_ids:
            return 0
        now = utcnow()
        unique_recipients = tuple(dict.fromkeys(int(value) for value in recipient_ids if int(value) > 0))
        async with self.connect() as db:
            for recipient_id in unique_recipients:
                await db.execute(
                    "INSERT OR IGNORE INTO notification_outbox(application_id,source,recipient_telegram_id,message_text,status,attempts,last_error,created_at) "
                    "VALUES(?,?,?,?,'pending',0,'',?)",
                    (application_id, source, recipient_id, message_text, now),
                )
        return len(unique_recipients)

    async def pending_notifications(self, recipient_id: int | None = None, limit: int = 100):
        query = "SELECT * FROM notification_outbox WHERE status IN ('pending','failed') AND attempts<12"
        params: list[Any] = []
        if recipient_id is not None:
            query += " AND recipient_telegram_id=?"
            params.append(int(recipient_id))
        query += " ORDER BY id LIMIT ?"
        params.append(max(1, min(int(limit), 200)))
        return await self.fetchall(query, tuple(params))

    async def mark_notification_sent(self, notification_id: int) -> None:
        await self.execute(
            "UPDATE notification_outbox SET status='sent',attempts=attempts+1,last_error='',sent_at=? WHERE id=?",
            (utcnow(), notification_id),
        )

    async def mark_notification_failed(self, notification_id: int, error: str) -> None:
        await self.execute(
            "UPDATE notification_outbox SET status=CASE WHEN attempts+1>=12 THEN 'failed' ELSE 'pending' END, "
            "attempts=attempts+1,last_error=? WHERE id=?",
            ((error or "delivery_failed")[:180], notification_id),
        )

    async def reset_exhausted_notifications(self, recipient_id: int) -> int:
        """Re-arm old notices when a recipient finally opens the bot, after earlier retries were exhausted."""
        async with self.connect() as db:
            cur = await db.execute(
                "UPDATE notification_outbox SET status='pending',attempts=0,last_error='' "
                "WHERE recipient_telegram_id=? AND status='failed' AND attempts>=12",
                (int(recipient_id),),
            )
            return int(cur.rowcount or 0)

    async def application_notification_delivery(self, application_id: int, source: str = "website") -> dict[str, int]:
        row = await self.fetchone(
            "SELECT COUNT(*) AS total, "
            "SUM(CASE WHEN status='sent' THEN 1 ELSE 0 END) AS sent, "
            "SUM(CASE WHEN status='pending' THEN 1 ELSE 0 END) AS pending, "
            "SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) AS failed "
            "FROM notification_outbox WHERE application_id=? AND source=?",
            (application_id, source),
        )
        return {key: int(row[key] or 0) for key in ("total", "sent", "pending", "failed")} if row else {"total":0,"sent":0,"pending":0,"failed":0}

    async def notifications(self, *, status: str | None = None, limit: int = 100):
        if status not in {None, "pending", "sent", "failed"}:
            raise ValueError("Bildirishnoma holati noto‘g‘ri.")
        where = " WHERE n.status=?" if status else ""
        params: list[Any] = [status] if status else []
        params.append(max(1, min(int(limit), 200)))
        return await self.fetchall(
            "SELECT n.id,n.application_id,n.source,n.recipient_telegram_id,n.status,n.attempts,n.last_error,"
            "n.created_at,n.sent_at,COALESCE(w.full_name,a.full_name,'—') AS applicant,"
            "COALESCE(c.name_uz,'—') AS course_name "
            "FROM notification_outbox n "
            "LEFT JOIN web_applications w ON n.source='website' AND w.id=n.application_id "
            "LEFT JOIN applications a ON n.source='bot' AND a.id=n.application_id "
            "LEFT JOIN courses c ON c.id=COALESCE(w.course_id,a.course_id)" + where + " ORDER BY n.id DESC LIMIT ?",
            tuple(params),
        )

    async def retry_notification(self, notification_id: int) -> bool:
        result = await self.execute(
            "UPDATE notification_outbox SET status='pending',attempts=0,last_error='' "
            "WHERE id=? AND status IN ('pending','failed')",
            (notification_id,),
        )
        return bool(result)

    async def notification_counts(self) -> dict[str, int]:
        pending = await self.fetchone("SELECT COUNT(*) AS n FROM notification_outbox WHERE status='pending'")
        failed = await self.fetchone("SELECT COUNT(*) AS n FROM notification_outbox WHERE status='failed'")
        return {"pending": int(pending["n"] if pending else 0), "failed": int(failed["n"] if failed else 0)}

    async def is_admin(self, telegram_id: int) -> bool:
        try:
            telegram_id = int(telegram_id)
        except (TypeError, ValueError):
            return False
        if telegram_id <= 0:
            return False
        row = await self.fetchone("SELECT 1 FROM admins WHERE telegram_id=? AND active=1", (telegram_id,))
        return bool(row)

    async def admin_role(self, telegram_id: int) -> str | None:
        try:
            telegram_id = int(telegram_id)
        except (TypeError, ValueError):
            return None
        if telegram_id <= 0:
            return None
        row = await self.fetchone("SELECT role FROM admins WHERE telegram_id=? AND active=1", (telegram_id,))
        if not row:
            return None
        role = str(row["role"] or "").strip().casefold()
        return {"owner": "ceo", "admin": "senior_admin"}.get(role, role) or None

    async def add_telegram_admin(
        self, telegram_id: int, role: str, created_by: int, *, active: bool = False,
    ) -> None:
        """Upsert an OWNER-managed admin assignment; do not create a Bot invitation."""
        if role not in {"senior_admin", "junior_admin"} or telegram_id <= 0:
            raise ValueError("Administrator ID yoki roli noto‘g‘ri.")
        now = utcnow()
        async with self.connect() as db:
            existing = await (await db.execute("SELECT role FROM admins WHERE telegram_id=?", (telegram_id,))).fetchone()
            if existing and str(existing["role"]) in {"ceo", "owner"}:
                raise ValueError("Asosiy administrator ID’sini o‘zgartirib bo‘lmaydi.")
            await db.execute(
                """INSERT INTO admins(telegram_id,role,active,pending_link,bot_invite_pending,created_at,created_by)
                   VALUES(?,?,?,1,0,?,?) ON CONFLICT(telegram_id) DO UPDATE SET
                   role=excluded.role,active=excluded.active,pending_link=1,bot_invite_pending=0,created_by=excluded.created_by""",
                (telegram_id, role, 1 if active else 0, now, created_by),
            )
            # Re-registering a Telegram ID cancels any previous web access until relinked.
            await db.execute(
                "UPDATE web_admin_users SET active=0,telegram_verified=0,role=?,updated_at=? WHERE telegram_id=? AND role<>'ceo'",
                (role, now, telegram_id),
            )
            await db.execute(
                "UPDATE web_admin_sessions SET revoked=1 WHERE username IN (SELECT username FROM web_admin_users WHERE telegram_id=?)",
                (telegram_id,),
            )

    async def create_telegram_admin(self, telegram_id: int, role: str, created_by: int) -> None:
        """Create an OWNER-approved bot invitation; web access remains separately linked."""
        telegram_id, created_by = int(telegram_id), int(created_by)
        role = str(role or "").strip().casefold()
        if telegram_id <= 0 or created_by <= 0 or role not in {"senior_admin", "junior_admin"}:
            raise ValueError("Administrator ID yoki roli noto‘g‘ri.")
        now = utcnow()
        async with self.connect() as db:
            existing = await (await db.execute(
                "SELECT role FROM admins WHERE telegram_id=?", (telegram_id,)
            )).fetchone()
            if existing:
                if str(existing["role"]).strip().casefold() in {"ceo", "owner"}:
                    raise ValueError("Asosiy administrator ID’sini o‘zgartirib bo‘lmaydi.")
                raise ValueError("Bu Telegram ID administratorlar ro‘yxatida allaqachon mavjud.")
            try:
                await db.execute(
                    "INSERT INTO admins(telegram_id,role,active,pending_link,bot_invite_pending,created_at,created_by) "
                    "VALUES(?,?,0,1,1,?,?)",
                    (telegram_id, role, now, created_by),
                )
            except aiosqlite.IntegrityError as exc:
                raise ValueError("Bu Telegram ID administratorlar ro‘yxatida allaqachon mavjud.") from exc
            # A previous Website Admin account, if any, is deliberately disabled.
            # Bot invitation acceptance never grants website login by itself.
            await db.execute(
                "UPDATE web_admin_users SET active=0,telegram_verified=0,role=?,updated_at=? "
                "WHERE telegram_id=? AND role<>'ceo'",
                (role, now, telegram_id),
            )
            await db.execute(
                "UPDATE web_admin_sessions SET revoked=1 WHERE username IN "
                "(SELECT username FROM web_admin_users WHERE telegram_id=?)",
                (telegram_id,),
            )
            await db.execute(
                "INSERT INTO admin_audit(actor,action,entity_type,entity_id,details,ip_address,created_at) "
                "VALUES(?,?,?,?,?,?,?)",
                (f"telegram:{created_by}", "telegram_admin_created", "telegram_admin", telegram_id,
                 f"role={role}; status=invitation_pending", "", now),
            )

    async def activate_telegram_admin_invitation(self, telegram_id: int) -> str | None:
        """Accept a one-time OWNER-created invitation for the exact Telegram user ID."""
        try:
            telegram_id = int(telegram_id)
        except (TypeError, ValueError):
            return None
        if telegram_id <= 0:
            return None
        now = utcnow()
        async with self.connect() as db:
            row = await (await db.execute(
                "SELECT role,created_by FROM admins WHERE telegram_id=? AND active=0 AND bot_invite_pending=1",
                (telegram_id,),
            )).fetchone()
            if not row:
                return None
            role = str(row["role"] or "").strip().casefold()
            if role not in {"senior_admin", "junior_admin"}:
                return None
            user = await (await db.execute(
                "SELECT account_status FROM users WHERE telegram_id=?", (telegram_id,)
            )).fetchone()
            if user and str(user["account_status"] or "active") != "active":
                return None
            cursor = await db.execute(
                "UPDATE admins SET active=1,bot_invite_pending=0 WHERE telegram_id=? AND active=0 AND bot_invite_pending=1",
                (telegram_id,),
            )
            if cursor.rowcount != 1:
                return None
            await db.execute(
                "INSERT INTO admin_audit(actor,action,entity_type,entity_id,details,ip_address,created_at) "
                "VALUES(?,?,?,?,?,?,?)",
                (f"telegram:{telegram_id}", "telegram_admin_invitation_accepted", "telegram_admin", telegram_id,
                 f"role={role}; invited_by={int(row['created_by'] or 0)}", "", now),
            )
            return role

    async def reissue_telegram_admin_invitation(self, telegram_id: int, actor_telegram_id: int) -> str:
        """Re-issue a bot-only invitation without enabling Website Admin access."""
        telegram_id, actor_telegram_id = int(telegram_id), int(actor_telegram_id)
        if telegram_id <= 0 or actor_telegram_id <= 0:
            raise ValueError("Telegram ID noto‘g‘ri.")
        if telegram_id == actor_telegram_id:
            raise ValueError("O‘zingizga administrator taklifini yubora olmaysiz.")
        now = utcnow()
        async with self.connect() as db:
            row = await (await db.execute(
                "SELECT role,active FROM admins WHERE telegram_id=?", (telegram_id,)
            )).fetchone()
            if not row:
                raise ValueError("Administrator topilmadi.")
            role = str(row["role"] or "").strip().casefold()
            if role not in {"senior_admin", "junior_admin"}:
                raise ValueError("OWNER/CEO hisobiga taklifni qayta yuborib bo‘lmaydi.")
            if int(row["active"] or 0):
                raise ValueError("Administrator allaqachon botda faol.")
            pending = await (await db.execute(
                "SELECT bot_invite_pending FROM admins WHERE telegram_id=?", (telegram_id,)
            )).fetchone()
            if pending and int(pending["bot_invite_pending"] or 0):
                raise ValueError("Bu administrator uchun bot taklifi allaqachon kutilmoqda.")
            await db.execute(
                "UPDATE admins SET active=0,pending_link=1,bot_invite_pending=1,created_by=? WHERE telegram_id=?",
                (actor_telegram_id, telegram_id),
            )
            await db.execute(
                "UPDATE web_admin_users SET active=0,telegram_verified=0,updated_at=? "
                "WHERE telegram_id=? AND role<>'ceo'",
                (now, telegram_id),
            )
            await db.execute(
                "UPDATE web_admin_sessions SET revoked=1 WHERE username IN "
                "(SELECT username FROM web_admin_users WHERE telegram_id=?)",
                (telegram_id,),
            )
            await db.execute(
                "INSERT INTO admin_audit(actor,action,entity_type,entity_id,details,ip_address,created_at) "
                "VALUES(?,?,?,?,?,?,?)",
                (f"telegram:{actor_telegram_id}", "telegram_admin_invitation_reissued", "telegram_admin", telegram_id,
                 f"role={role}; status=invitation_pending", "", now),
            )
            return role

    async def set_telegram_admin_active(self, telegram_id: int, active: bool) -> bool:
        now = utcnow()
        async with self.connect() as db:
            row = await (await db.execute(
                "SELECT telegram_id,role FROM admins WHERE telegram_id=?", (telegram_id,)
            )).fetchone()
            if not row or str(row["role"]) in {"ceo", "owner"}:
                return False
            await db.execute(
                "UPDATE admins SET active=0,pending_link=?,bot_invite_pending=0 WHERE telegram_id=?",
                (1 if active else 0, telegram_id),
            )
            await db.execute(
                "UPDATE web_admin_users SET active=0,telegram_verified=0,updated_at=? WHERE telegram_id=? AND role<>'ceo'",
                (now, telegram_id),
            )
            await db.execute(
                "UPDATE web_admin_sessions SET revoked=1 WHERE username IN (SELECT username FROM web_admin_users WHERE telegram_id=?)",
                (telegram_id,),
            )
        return True

    async def telegram_admin_accounts(self):
        return await self.fetchall(
            """SELECT a.telegram_id,a.role,a.active,a.pending_link,a.bot_invite_pending,a.created_at,a.created_by,
                      u.username AS web_username,u.active AS web_active,u.telegram_verified
               FROM admins a LEFT JOIN web_admin_users u ON u.telegram_id=a.telegram_id
               ORDER BY CASE a.role WHEN 'ceo' THEN 0 WHEN 'owner' THEN 0 WHEN 'senior_admin' THEN 1 ELSE 2 END,
                        a.telegram_id"""
        )

    async def active_admin_ids(self) -> tuple[int, ...]:
        rows = await self.fetchall("SELECT telegram_id FROM admins WHERE active=1 ORDER BY role,telegram_id")
        return tuple(int(row["telegram_id"]) for row in rows if int(row["telegram_id"]) > 0)

    async def count_active_telegram_admins(self, role: str) -> int:
        row = await self.fetchone("SELECT COUNT(*) AS total FROM admins WHERE role=? AND active=1", (role,))
        return int(row["total"] if row else 0)

    async def purge_expired_fsm_states(self, *, ttl_days: int = 7) -> int:
        """Remove persisted conversation state older than the configured retention window."""
        ttl_days = max(1, min(int(ttl_days), 30))
        cutoff = (datetime.now(timezone.utc) - timedelta(days=ttl_days)).isoformat()
        return await self.execute("DELETE FROM fsm_storage WHERE updated_at < ?", (cutoff,))

    async def admins(self, include_inactive: bool = False):
        query = "SELECT * FROM admins" if include_inactive else "SELECT * FROM admins WHERE active=1"
        return await self.fetchall(query + " ORDER BY CASE role WHEN 'ceo' THEN 0 WHEN 'owner' THEN 0 WHEN 'senior_admin' THEN 1 WHEN 'admin' THEN 1 ELSE 2 END, telegram_id")
