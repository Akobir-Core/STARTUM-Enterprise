from __future__ import annotations

from datetime import datetime
from pathlib import Path
from html import escape
import logging
from zoneinfo import ZoneInfo

from aiogram import BaseMiddleware, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import config
from database.db import Database
from education_access import actor_role, is_admin_actor, is_owner
from education_i18n import announcement_preview, et
from states.admin import AddLearningResourceState
from states.education import (
    JoinGroupState, CreateGroupState, CreateHomeworkState,
    SubmitHomeworkState, ReviewSubmissionState, CreateAnnouncementState,
)
from keyboards.common import language_keyboard

router = Router(name="education")
logger = logging.getLogger(__name__)
_TZ = ZoneInfo("Asia/Tashkent")


def _is_private_callback(callback: CallbackQuery) -> bool:
    """Fail closed for callbacks without a regular private-chat message."""
    message = callback.message if isinstance(callback.message, Message) else None
    if message is None:
        return False
    chat_type = getattr(message.chat, "type", None)
    return getattr(chat_type, "value", str(chat_type)) == "private"


class PrivateEducationChatMiddleware(BaseMiddleware):
    """Keep student, teacher, admin and OWNER education cabinets in private chat."""

    async def __call__(self, handler, event, data):
        if isinstance(event, Message):
            chat = event.chat
        elif isinstance(event, CallbackQuery) and isinstance(event.message, Message):
            chat = event.message.chat
        else:
            return await handler(event, data)
        chat_type = getattr(chat.type, "value", str(chat.type))
        if chat_type != "private":
            if isinstance(event, Message):
                await event.answer("STARTUM ta’lim kabineti maxfiylik uchun bot bilan shaxsiy chatda ishlaydi.")
            else:
                await event.answer("Bu kabinet faqat shaxsiy chatda ishlaydi.", show_alert=True)
            return None
        return await handler(event, data)


# Education dashboards can expose student/group records and must stay in DM.
router.message.outer_middleware(PrivateEducationChatMiddleware())
router.callback_query.outer_middleware(PrivateEducationChatMiddleware())


def _lang(row) -> str:
    value = str(row["language"] or "uz") if row else "uz"
    return value if value in {"uz", "ru", "en"} else "uz"


async def _user_lang(db: Database, telegram_id: int) -> str:
    row = await db.fetchone("SELECT language FROM users WHERE telegram_id=?", (int(telegram_id),))
    return _lang(row)


def _back(text: str, callback: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=text, callback_data=callback)]])


def _student_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=et(lang, "groups"), callback_data="edu:student:groups"),
         InlineKeyboardButton(text=et(lang, "join"), callback_data="edu:student:join")],
        [InlineKeyboardButton(text=et(lang, "materials"), callback_data="edu:student:materials"),
         InlineKeyboardButton(text=et(lang, "homework"), callback_data="edu:student:homework")],
        [InlineKeyboardButton(text=et(lang, "attendance"), callback_data="edu:student:attendance"),
         InlineKeyboardButton(text=et(lang, "progress"), callback_data="edu:student:progress")],
        [InlineKeyboardButton(text=et(lang, "assigned_tests"), callback_data="edu:student:tests")],
        [InlineKeyboardButton(text=et(lang, "edu_calendar"), callback_data="edu:student:calendar"),
         InlineKeyboardButton(text=et(lang, "edu_notifications"), callback_data="edu:student:notifications")],
        [InlineKeyboardButton(text=et(lang, "certificates"), callback_data="edu:student:certificates"),
         InlineKeyboardButton(text=et(lang, "settings"), callback_data="edu:student:settings")],
        [InlineKeyboardButton(text=et(lang, "back"), callback_data="nav:home")],
    ])


def _owner_keyboard(lang: str = "uz") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Statistika", callback_data="edu:owner:stats"),
         InlineKeyboardButton(text=et(lang, "admins"), callback_data="edu:owner:admins")],
        [InlineKeyboardButton(text=et(lang, "create_group"), callback_data="edu:owner:groups:create")],
        [InlineKeyboardButton(text=et(lang, "assign"), callback_data="edu:owner:teachers"),
         InlineKeyboardButton(text=et(lang, "admin_pending"), callback_data="edu:owner:memberships")],
        [InlineKeyboardButton(text=et(lang, "resource_pending"), callback_data="edu:owner:resources")],
        [InlineKeyboardButton(text="📣 E’lon tayyorlash", callback_data="edu:admin:announce")],
        [InlineKeyboardButton(text=et(lang, "audit"), callback_data="edu:owner:audit")],
    ])


def _admin_education_keyboard(lang: str = "uz") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Guruhlarni boshqarish", callback_data="edu:admin:groups")],
        [InlineKeyboardButton(text=et(lang, "admin_pending"), callback_data="edu:admin:memberships")],
        [InlineKeyboardButton(text=et(lang, "resource_pending"), callback_data="edu:admin:resources")],
        [InlineKeyboardButton(text="📣 E’lon yuborish", callback_data="edu:admin:announce")],
        [InlineKeyboardButton(text=et(lang, "back"), callback_data="adm:home")],
    ])


async def _admin_message_targets(db: Database) -> tuple[int, ...]:
    ids = set(await db.active_admin_ids())
    ids.add(int(config.owner_telegram_id))
    return tuple(sorted(ids))


@router.message(Command("student"))
async def student_command(message: Message, db: Database):
    row, _ = await db.ensure_user(message.from_user)
    lang = _lang(row)
    await message.answer(et(lang, "student_title"), reply_markup=_student_keyboard(lang))


@router.callback_query(F.data == "edu:student:home")
async def student_home(callback: CallbackQuery, db: Database):
    row, _ = await db.ensure_user(callback.from_user)
    lang = _lang(row)
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(et(lang, "student_title"), reply_markup=_student_keyboard(lang))


@router.callback_query(F.data == "edu:student:groups")
async def student_groups(callback: CallbackQuery, db: Database):
    lang = await _user_lang(db, callback.from_user.id)
    rows = await db.student_groups(callback.from_user.id)
    lines = [et(lang, "groups"), ""]
    for row in rows:
        course_key = {"uz": "course_name", "ru": "course_name_ru", "en": "course_name_en"}[lang]
        schedule = f"\n   {escape(row['schedule_text'])}" if row["schedule_text"] else ""
        lines.append(f"• <b>{escape(row['name'])}</b> — {escape(row[course_key])}{schedule}")
    await callback.answer()
    if callback.message:
        await callback.message.edit_text("\n".join(lines) if rows else et(lang, "no_groups"),
                                         reply_markup=_back(et(lang, "back"), "edu:student:home"))


@router.callback_query(F.data == "edu:student:join")
async def student_join_start(callback: CallbackQuery, state: FSMContext, db: Database):
    lang = await _user_lang(db, callback.from_user.id)
    await state.clear()
    await state.set_state(JoinGroupState.code)
    await callback.answer()
    if callback.message:
        await callback.message.answer(et(lang, "enter_code"),
                                      reply_markup=_back(et(lang, "cancel"), "edu:student:home"))


@router.message(JoinGroupState.code)
async def student_join_code(message: Message, state: FSMContext, db: Database):
    if not message.from_user or not message.text:
        await message.answer("Kod matn ko‘rinishida yuborilishi kerak.")
        return
    lang = await _user_lang(db, message.from_user.id)
    try:
        result = await db.request_group_membership(message.from_user.id, message.text)
    except ValueError:
        await message.answer(et(lang, "bad_code"))
        return
    await state.clear()
    if result == "active":
        await message.answer(et(lang, "already"), reply_markup=_student_keyboard(lang))
        return
    if result == "pending":
        notice = et(lang, "pending")
        for admin_id in await _admin_message_targets(db):
            try:
                await message.bot.send_message(admin_id, f"🧑‍🎓 Guruhga qo‘shilish uchun yangi so‘rov. Telegram ID: <code>{message.from_user.id}</code>")
            except Exception:
                continue
        await message.answer(notice, reply_markup=_student_keyboard(lang))


@router.callback_query(F.data == "edu:student:materials")
async def student_materials(callback: CallbackQuery, db: Database):
    lang = await _user_lang(db, callback.from_user.id)
    rows = await db.student_learning_resources(callback.from_user.id, limit=50)
    if not rows:
        await callback.answer()
        if callback.message:
            await callback.message.edit_text(et(lang, "no_materials"), reply_markup=_back(et(lang, "back"), "edu:student:home"))
        return
    buttons = []
    for row in rows:
        buttons.append([InlineKeyboardButton(text=f"📄 {str(row['title'])[:45]}", callback_data=f"edu:student:material:{int(row['id'])}")])
    buttons.append([InlineKeyboardButton(text=et(lang, "back"), callback_data="edu:student:home")])
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(et(lang, "materials"), reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@router.callback_query(F.data.startswith("edu:student:material:"))
async def student_open_material(callback: CallbackQuery, db: Database):
    lang = await _user_lang(db, callback.from_user.id)
    try:
        resource_id = int(callback.data.rsplit(":", 1)[-1])
    except ValueError:
        await callback.answer("Material ID noto‘g‘ri.", show_alert=True)
        return
    rows = await db.student_learning_resources(callback.from_user.id, limit=200)
    item = next((r for r in rows if int(r["id"]) == resource_id), None)
    if not item:
        await callback.answer(et(lang, "permission_denied"), show_alert=True)
        return
    await callback.answer()
    text = f"📚 <b>{escape(item['title'])}</b>\n\n{escape(item['description'] or '')}"
    file_id = str(item["telegram_file_id"] or "")
    media_type = str(item["media_type"] or "text")
    try:
        if file_id and media_type == "photo":
            await callback.message.answer_photo(file_id, caption=text)
        elif file_id and media_type == "video":
            await callback.message.answer_video(file_id, caption=text)
        elif file_id and media_type == "audio":
            await callback.message.answer_audio(file_id, caption=text)
        elif file_id and media_type == "document":
            await callback.message.answer_document(file_id, caption=text)
        else:
            await callback.message.answer(text + (f"\n\n{escape(item['content'])}" if item["content"] else ""))
    except Exception as exc:
        logger.warning("Student material delivery failed: %s", type(exc).__name__)
        await callback.message.answer("Materialni yuborib bo‘lmadi. Keyinroq qayta urinib ko‘ring.")


@router.callback_query(F.data == "edu:student:homework")
async def student_homework(callback: CallbackQuery, db: Database):
    lang = await _user_lang(db, callback.from_user.id)
    group_ids = await db.student_group_ids(callback.from_user.id)
    tasks = await db.homework_for_groups(group_ids, published_only=True, limit=50)
    if not tasks:
        await callback.answer()
        if callback.message:
            await callback.message.edit_text(et(lang, "no_homework"), reply_markup=_back(et(lang, "back"), "edu:student:home"))
        return
    rows = [[InlineKeyboardButton(text=f"📝 {str(task['title'])[:42]} · {str(task['group_name'])[:20]}",
                                  callback_data=f"edu:student:homework:submit:{int(task['id'])}")] for task in tasks]
    rows.append([InlineKeyboardButton(text=et(lang, "back"), callback_data="edu:student:home")])
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(et(lang, "homework"), reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data.startswith("edu:student:homework:submit:"))
async def student_homework_submit_start(callback: CallbackQuery, state: FSMContext, db: Database):
    lang = await _user_lang(db, callback.from_user.id)
    try:
        homework_id = int(callback.data.rsplit(":", 1)[-1])
    except ValueError:
        await callback.answer("ID noto‘g‘ri.", show_alert=True)
        return
    group_ids = await db.student_group_ids(callback.from_user.id)
    tasks = await db.homework_for_groups(group_ids, published_only=True, limit=200)
    if not any(int(row["id"]) == homework_id for row in tasks):
        await callback.answer(et(lang, "permission_denied"), show_alert=True)
        return
    await state.clear()
    await state.update_data(homework_id=homework_id)
    await state.set_state(SubmitHomeworkState.answer)
    await callback.answer()
    if callback.message:
        await callback.message.answer(et(lang, "submission_prompt"))


@router.message(SubmitHomeworkState.answer)
async def student_homework_submit_received(message: Message, state: FSMContext, db: Database):
    if not message.from_user:
        return
    data = await state.get_data()
    text = message.text or message.caption or ""
    file_id, file_type = "", ""
    if message.document:
        file_id, file_type = message.document.file_id, "document"
    elif message.photo:
        file_id, file_type = message.photo[-1].file_id, "photo"
    elif message.video:
        file_id, file_type = message.video.file_id, "video"
    elif message.audio:
        file_id, file_type = message.audio.file_id, "audio"
    elif message.voice:
        file_id, file_type = message.voice.file_id, "voice"
    try:
        submission_id = await db.submit_homework(
            homework_id=int(data.get("homework_id", 0)), student_telegram_id=message.from_user.id,
            submission_text=text, attachment_file_id=file_id, attachment_type=file_type,
        )
    except (ValueError, PermissionError) as exc:
        lang = await _user_lang(db, message.from_user.id)
        await message.answer(escape(str(exc)) or et(lang, "permission_denied"))
        await state.clear()
        return
    await state.clear()
    lang = await _user_lang(db, message.from_user.id)
    await message.answer(f"{et(lang, 'submission_saved')}\n<code>#{submission_id}</code>",
                         reply_markup=_student_keyboard(lang))
    # Teacher receives only the submission notification; the assignment remains group-scoped.
    task = await db.fetchone("SELECT teacher_telegram_id,title FROM homework WHERE id=?", (int(data["homework_id"]),))
    if task:
        try:
            await message.bot.send_message(int(task["teacher_telegram_id"]),
                f"📝 Yangi uy vazifasi javobi: <b>{escape(task['title'])}</b>\nO‘quvchi: <code>{message.from_user.id}</code>")
        except Exception:
            pass


@router.callback_query(F.data == "edu:student:tests")
async def student_assigned_tests(callback: CallbackQuery, db: Database):
    lang = await _user_lang(db, callback.from_user.id)
    rows = await db.student_quiz_assignments(callback.from_user.id, limit=50)
    buttons = [[InlineKeyboardButton(
        text=f"🧪 {str(row['title'])[:40]} · {int(row['attempts_done'])}/{int(row['attempt_limit'])}",
        callback_data=f"edu:student:quiz:{int(row['resource_id'])}:{int(row['group_id'])}",
    )] for row in rows]
    buttons.append([InlineKeyboardButton(text=et(lang, "back"), callback_data="edu:student:home")])
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(
            et(lang, "assigned_tests") + ("\n\nHozir sizga tayinlangan faol test yo‘q." if not rows else ""),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        )


@router.callback_query(F.data.startswith("edu:student:quiz:"))
async def student_assigned_quiz_detail(callback: CallbackQuery, db: Database):
    lang = await _user_lang(db, callback.from_user.id)
    try:
        _, _, _, resource_raw, group_raw = callback.data.split(":", 4)
        resource_id, group_id = int(resource_raw), int(group_raw)
    except (ValueError, TypeError):
        await callback.answer("Test ma’lumoti noto‘g‘ri.", show_alert=True)
        return
    access = await db.quiz_assignment_access(callback.from_user.id, resource_id)
    rows = await db.student_quiz_assignments(callback.from_user.id, limit=200)
    assignment = next((row for row in rows if int(row["resource_id"]) == resource_id and int(row["group_id"]) == group_id), None)
    if not access["allowed"] or not assignment:
        await callback.answer(et(lang, "quiz_unavailable"), show_alert=True)
        return
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(
            f"🧪 <b>{escape(assignment['title'])}</b>\nGuruh: {escape(assignment['group_name'])}\n"
            f"Urinishlar: {int(assignment['attempts_done'])}/{int(assignment['attempt_limit'])}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=et(lang, "start_test"), callback_data=f"quiz:start:{resource_id}")],
                [InlineKeyboardButton(text=et(lang, "back"), callback_data="edu:student:tests")],
            ]),
        )


@router.callback_query(F.data == "edu:student:attendance")
async def student_attendance(callback: CallbackQuery, db: Database):
    lang = await _user_lang(db, callback.from_user.id)
    rows = await db.student_attendance(callback.from_user.id, limit=30)
    lines = [et(lang, "attendance"), ""]
    status_map = {"present": "✅", "late": "🕒", "absent": "❌", "excused": "🟡"}
    for row in rows:
        lines.append(f"{row['session_date']} · {escape(row['group_name'])} · {status_map.get(row['status'], '•')} {escape(row['status'])}")
    await callback.answer()
    if callback.message:
        await callback.message.edit_text("\n".join(lines) if rows else et(lang, "no_attendance"),
                                         reply_markup=_back(et(lang, "back"), "edu:student:home"))


@router.callback_query(F.data == "edu:student:progress")
async def student_progress(callback: CallbackQuery, db: Database):
    lang = await _user_lang(db, callback.from_user.id)
    user = await db.fetchone("SELECT id FROM users WHERE telegram_id=?", (int(callback.from_user.id),))
    if not user:
        await callback.answer(et(lang, "empty"), show_alert=True)
        return
    quiz = await db.user_quiz_stats(int(user["id"]))
    submissions = await db.student_homework_submissions(callback.from_user.id, limit=200)
    attendance = await db.student_attendance(callback.from_user.id, limit=200)
    graded = [row for row in submissions if row["grade"] is not None]
    average = sum(float(row["grade"]) for row in graded) / len(graded) if graded else 0
    text = (
        f"📈 <b>{et(lang, 'progress')}</b>\n\n"
        f"🧪 Testlar: {int(quiz['attempts'])}\n"
        f"⭐ Eng yaxshi natija: {int(quiz['best_percent'])}%\n"
        f"📝 Topshirilgan vazifalar: {len(submissions)}\n"
        f"✅ Baholangan vazifalar: {len(graded)}\n"
        f"📊 Vazifalar bo‘yicha o‘rtacha baho: {average:.1f}%\n"
        f"📅 Davomat yozuvlari: {len(attendance)}"
    )
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(text, reply_markup=_back(et(lang, "back"), "edu:student:home"))


@router.callback_query(F.data == "edu:student:certificates")
async def student_certificates(callback: CallbackQuery, db: Database):
    lang = await _user_lang(db, callback.from_user.id)
    rows = await db.student_certificates(callback.from_user.id)
    lines = [et(lang, "certificates"), ""]
    for item in rows:
        lines.append(f"• {escape(item['course_name'])} · <code>{escape(item['certificate_code'])}</code> · {escape(item['status'])}")
    await callback.answer()
    if callback.message:
        await callback.message.edit_text("\n".join(lines) if rows else et(lang, "no_certificates"),
                                         reply_markup=_back(et(lang, "back"), "edu:student:home"))


@router.callback_query(F.data == "edu:student:settings")
async def student_settings(callback: CallbackQuery, db: Database):
    lang = await _user_lang(db, callback.from_user.id)
    prefs = await db.notification_preferences(callback.from_user.id)
    keys = [
        ("announcements", {"uz": "E’lonlar", "ru": "Объявления", "en": "Announcements"}),
        ("lesson_reminders", {"uz": "Dars eslatmalari", "ru": "Напоминания об уроках", "en": "Lesson reminders"}),
        ("homework", {"uz": "Uy vazifalari", "ru": "Домашние задания", "en": "Homework"}),
        ("results", {"uz": "Natijalar", "ru": "Результаты", "en": "Results"}),
    ]
    rows = []
    for key, labels in keys:
        state_text = "✅" if prefs[key] else "🔕"
        rows.append([InlineKeyboardButton(text=f"{state_text} {labels[lang]}", callback_data=f"edu:student:pref:{key}:{0 if prefs[key] else 1}")])
    rows.extend([
        [InlineKeyboardButton(text=et(lang, "language"), callback_data="user:language")],
        [InlineKeyboardButton(text=et(lang, "back"), callback_data="edu:student:home")],
    ])
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(et(lang, "settings"), reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data.startswith("edu:student:pref:"))
async def student_toggle_preference(callback: CallbackQuery, db: Database):
    lang = await _user_lang(db, callback.from_user.id)
    try:
        _, _, _, key, value = callback.data.split(":")
        if value not in {"0", "1"}:
            raise ValueError
        await db.set_notification_preference(callback.from_user.id, key, value == "1")
    except (ValueError, TypeError):
        await callback.answer("Sozlama noto‘g‘ri.", show_alert=True)
        return
    await callback.answer("✅")
    # Refresh the preferences view without acknowledging the callback twice.
    prefs = await db.notification_preferences(callback.from_user.id)
    labels = {
        "announcements": {"uz": "E’lonlar", "ru": "Объявления", "en": "Announcements"},
        "lesson_reminders": {"uz": "Dars eslatmalari", "ru": "Напоминания об уроках", "en": "Lesson reminders"},
        "homework": {"uz": "Uy vazifalari", "ru": "Домашние задания", "en": "Homework"},
        "results": {"uz": "Natijalar", "ru": "Результаты", "en": "Results"},
    }
    rows = [[InlineKeyboardButton(text=f"{'✅' if prefs[key] else '🔕'} {value[lang]}", callback_data=f"edu:student:pref:{key}:{0 if prefs[key] else 1}")] for key, value in labels.items()]
    rows.extend([[InlineKeyboardButton(text=et(lang, "language"), callback_data="user:language")],
                  [InlineKeyboardButton(text=et(lang, "back"), callback_data="edu:student:home")]])
    if callback.message:
        await callback.message.edit_text(et(lang, "settings"), reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


async def _calendar_message_text(db: Database, telegram_id: int, lang: str) -> str:
    rows = await db.calendar_events(language=lang, public_only=True, telegram_id=telegram_id, limit=12)
    if not rows:
        return et(lang, "no_calendar")
    lines = [et(lang, "edu_calendar"), ""]
    for item in rows:
        try:
            starts = datetime.fromisoformat(str(item["starts_at"]).replace("Z", "+00:00")).astimezone(_TZ)
            when = starts.strftime("%d.%m.%Y · %H:%M")
        except ValueError:
            when = str(item["starts_at"])
        lines.append(f"• <b>{escape(str(item['title']))}</b>\n  {escape(when)}")
        if item["location"]:
            lines.append(f"  📍 {escape(str(item['location']))}")
        if item["description"]:
            lines.append(f"  {escape(str(item['description'])[:300])}")
        lines.append("")
    return "\n".join(lines).strip()


@router.message(Command("calendar"))
async def calendar_command(message: Message, db: Database):
    row, _ = await db.ensure_user(message.from_user)
    lang = _lang(row)
    await message.answer(await _calendar_message_text(db, message.from_user.id, lang),
                         reply_markup=_back(et(lang, "back"), "edu:student:home"))


@router.callback_query(F.data == "edu:student:calendar")
async def student_calendar(callback: CallbackQuery, db: Database):
    lang = await _user_lang(db, callback.from_user.id)
    text = await _calendar_message_text(db, callback.from_user.id, lang)
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(text, reply_markup=_back(et(lang, "back"), "edu:student:home"))


async def _notification_list_text(db: Database, telegram_id: int, lang: str):
    rows = await db.user_notifications(telegram_id, unread_only=False, limit=15)
    if not rows:
        return et(lang, "no_notifications"), InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=et(lang, "back"), callback_data="edu:student:home")]
        ])
    lines = [et(lang, "edu_notifications"), ""]
    buttons = []
    for item in rows:
        marker = "✅" if item["read_at"] else "🔔"
        lines.append(f"{marker} <b>{escape(str(item['title']))}</b>")
        if item["body"]:
            lines.append(escape(str(item["body"])[:360]))
        lines.append("")
        if not item["read_at"]:
            buttons.append([InlineKeyboardButton(
                text=f"✓ {str(item['title'])[:35]}", callback_data=f"edu:student:notification:read:{int(item['id'])}"
            )])
    if any(not item["read_at"] for item in rows):
        buttons.append([InlineKeyboardButton(text=et(lang, "mark_all_read"), callback_data="edu:student:notifications:all-read")])
    buttons.append([InlineKeyboardButton(text=et(lang, "back"), callback_data="edu:student:home")])
    return "\n".join(lines).strip(), InlineKeyboardMarkup(inline_keyboard=buttons)


@router.message(Command("notifications"))
async def notifications_command(message: Message, db: Database):
    row, _ = await db.ensure_user(message.from_user)
    lang = _lang(row)
    text, markup = await _notification_list_text(db, message.from_user.id, lang)
    await message.answer(text, reply_markup=markup)


@router.callback_query(F.data == "edu:student:notifications")
async def student_notifications(callback: CallbackQuery, db: Database):
    lang = await _user_lang(db, callback.from_user.id)
    text, markup = await _notification_list_text(db, callback.from_user.id, lang)
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(text, reply_markup=markup)


@router.callback_query(F.data.startswith("edu:student:notification:read:"))
async def student_notification_read(callback: CallbackQuery, db: Database):
    lang = await _user_lang(db, callback.from_user.id)
    try:
        notification_id = int(callback.data.rsplit(":", 1)[-1])
    except ValueError:
        await callback.answer(et(lang, "permission_denied"), show_alert=True)
        return
    if not await db.mark_user_notification_read(callback.from_user.id, notification_id):
        await callback.answer(et(lang, "permission_denied"), show_alert=True)
        return
    text, markup = await _notification_list_text(db, callback.from_user.id, lang)
    await callback.answer(et(lang, "notification_read"))
    if callback.message:
        await callback.message.edit_text(text, reply_markup=markup)


@router.callback_query(F.data == "edu:student:notifications:all-read")
async def student_notifications_all_read(callback: CallbackQuery, db: Database):
    lang = await _user_lang(db, callback.from_user.id)
    await db.mark_all_user_notifications_read(callback.from_user.id)
    text, markup = await _notification_list_text(db, callback.from_user.id, lang)
    await callback.answer(et(lang, "all_read"))
    if callback.message:
        await callback.message.edit_text(text, reply_markup=markup)


@router.message(Command("teacher"))
async def teacher_command(message: Message, db: Database):
    await _send_teacher_home(message, db)


async def _send_teacher_home(target, db: Database):
    telegram_id = target.from_user.id
    lang = await _user_lang(db, telegram_id)
    assignments = await db.teacher_assignments(telegram_id)
    if not assignments:
        if isinstance(target, Message):
            await target.answer(et(lang, "permission_denied"))
        else:
            await target.answer(et(lang, "permission_denied"), show_alert=True)
        return
    rows = []
    for item in assignments[:30]:
        course_name = item["course_name_uz"] if lang == "uz" else item["course_name_ru"] if lang == "ru" else item["course_name_en"]
        rows.append([InlineKeyboardButton(text=f"📘 {str(course_name)[:45]}", callback_data=f"edu:teacher:course:{int(item['course_id'])}")])
    rows.extend([
        [InlineKeyboardButton(text=et(lang, "new_homework"), callback_data="edu:teacher:create-homework")],
        [InlineKeyboardButton(text=et(lang, "review"), callback_data="edu:teacher:submissions")],
        [InlineKeyboardButton(text=et(lang, "take_attendance"), callback_data="edu:teacher:attendance")],
        [InlineKeyboardButton(text=et(lang, "materials"), callback_data="edu:teacher:materials")],
        [InlineKeyboardButton(text=et(lang, "back"), callback_data="nav:home")],
    ])
    markup = InlineKeyboardMarkup(inline_keyboard=rows)
    if isinstance(target, Message):
        await target.answer(et(lang, "teacher_title"), reply_markup=markup)
    elif target.message:
        await target.message.edit_text(et(lang, "teacher_title"), reply_markup=markup)


@router.callback_query(F.data == "edu:teacher:home")
async def teacher_home_callback(callback: CallbackQuery, db: Database):
    await callback.answer()
    await _send_teacher_home(callback, db)


@router.callback_query(F.data.startswith("edu:teacher:course:"))
async def teacher_course_detail(callback: CallbackQuery, db: Database):
    lang = await _user_lang(db, callback.from_user.id)
    try:
        course_id = int(callback.data.rsplit(":", 1)[-1])
    except ValueError:
        await callback.answer("ID noto‘g‘ri.", show_alert=True)
        return
    assignments = await db.teacher_assignments(callback.from_user.id)
    if not any(int(row["course_id"]) == course_id for row in assignments):
        await callback.answer(et(lang, "permission_denied"), show_alert=True)
        return
    groups = await db.education_groups(course_id=course_id, teacher_id=callback.from_user.id)
    course = await db.course(course_id)
    course_name = (course or {}).get("name_uz", "") if isinstance(course, dict) else (course["name_uz"] if course else "")
    rows = [[InlineKeyboardButton(text=f"👥 {str(group['name'])[:40]} · {int(group['student_count'])} ",
                                  callback_data=f"edu:teacher:group:{int(group['id'])}")] for group in groups]
    rows.append([InlineKeyboardButton(text=et(lang, "back"), callback_data="edu:teacher:home")])
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(f"📘 <b>{escape(course_name)}</b>\n\n{et(lang, 'groups_short')}",
                                         reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data.startswith("edu:teacher:group:"))
async def teacher_group_detail(callback: CallbackQuery, db: Database):
    lang = await _user_lang(db, callback.from_user.id)
    try:
        group_id = int(callback.data.rsplit(":", 1)[-1])
    except ValueError:
        await callback.answer("ID noto‘g‘ri.", show_alert=True)
        return
    group = await db.fetchone("SELECT id,name,course_id,schedule_text FROM education_groups WHERE id=? AND status='active'", (group_id,))
    if not group or not await db.teacher_has_scope(callback.from_user.id, int(group["course_id"]), group_id):
        await callback.answer(et(lang, "permission_denied"), show_alert=True)
        return
    students = await db.group_students(group_id, actor_telegram_id=callback.from_user.id)
    lines = [f"👥 <b>{escape(group['name'])}</b>", escape(group["schedule_text"] or ""), "", f"O‘quvchilar: {len(students)}"]
    for student in students[:40]:
        full_name = " ".join(part for part in [student["first_name"], student["last_name"]] if part).strip() or str(student["telegram_id"])
        lines.append(f"• {escape(full_name)} · <code>{int(student['telegram_id'])}</code>")
    await callback.answer()
    if callback.message:
        await callback.message.edit_text("\n".join(lines), reply_markup=_back(et(lang, "back"), f"edu:teacher:course:{int(group['course_id'])}"))


@router.callback_query(F.data == "edu:teacher:materials")
async def teacher_materials(callback: CallbackQuery, db: Database):
    lang = await _user_lang(db, callback.from_user.id)
    assignments = await db.teacher_assignments(callback.from_user.id)
    if not assignments:
        await callback.answer(et(lang, "permission_denied"), show_alert=True)
        return
    course_ids = sorted({int(row["course_id"]) for row in assignments})
    rows = []
    for course_id in course_ids:
        for resource in await db.learning_resources(course_id=course_id, include_inactive=True, limit=100):
            if int(resource["created_by_telegram_id"]) != callback.from_user.id:
                continue
            resource_group_id = int(resource["group_id"]) if resource["group_id"] is not None else None
            if await db.teacher_has_scope(callback.from_user.id, course_id, resource_group_id):
                rows.append(resource)
    rows = rows[:40]
    lines = [et(lang, "materials"), ""]
    for resource in rows:
        lines.append(f"• <code>#{int(resource['id'])}</code> {escape(resource['title'])} · {escape(resource['publication_status'])}")
    await callback.answer()
    if callback.message:
        await callback.message.edit_text("\n".join(lines) if rows else et(lang, "empty"),
                                         reply_markup=_back(et(lang, "back"), "edu:teacher:home"))


@router.callback_query(F.data == "edu:teacher:create-homework")
async def teacher_create_homework_start(callback: CallbackQuery, state: FSMContext, db: Database):
    lang = await _user_lang(db, callback.from_user.id)
    groups = await db.education_groups(teacher_id=callback.from_user.id)
    if not groups:
        await callback.answer(et(lang, "no_groups"), show_alert=True)
        return
    await state.clear()
    await state.set_state(CreateHomeworkState.group)
    rows = [[InlineKeyboardButton(text=str(group["name"])[:50], callback_data=f"edu:teacher:homework:group:{int(group['id'])}")] for group in groups]
    rows.append([InlineKeyboardButton(text=et(lang, "cancel"), callback_data="edu:teacher:home")])
    await callback.answer()
    if callback.message:
        await callback.message.answer(et(lang, "select_group"), reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data.startswith("edu:teacher:homework:group:"))
async def teacher_homework_group(callback: CallbackQuery, state: FSMContext, db: Database):
    lang = await _user_lang(db, callback.from_user.id)
    try:
        group_id = int(callback.data.rsplit(":", 1)[-1])
    except ValueError:
        await callback.answer("ID noto‘g‘ri.", show_alert=True)
        return
    group = await db.fetchone("SELECT id,course_id,name FROM education_groups WHERE id=? AND status='active'", (group_id,))
    if not group or await state.get_state() != CreateHomeworkState.group.state or not await db.teacher_has_scope(callback.from_user.id, int(group["course_id"]), group_id):
        await callback.answer(et(lang, "permission_denied"), show_alert=True)
        await state.clear()
        return
    await state.update_data(group_id=group_id)
    await state.set_state(CreateHomeworkState.title)
    await callback.answer()
    if callback.message:
        await callback.message.answer(f"{escape(group['name'])}\n{et(lang, 'homework_title')}")


@router.message(CreateHomeworkState.title)
async def teacher_homework_title(message: Message, state: FSMContext, db: Database):
    if not message.text or not 2 <= len(message.text.strip()) <= 180:
        await message.answer("Vazifa nomi 2–180 belgi bo‘lishi kerak.")
        return
    data = await state.get_data()
    group = await db.fetchone("SELECT course_id FROM education_groups WHERE id=? AND status='active'", (int(data.get("group_id", 0)),))
    if not group or not await db.teacher_has_scope(message.from_user.id, int(group["course_id"]), int(data["group_id"])):
        await state.clear()
        await message.answer(et(await _user_lang(db, message.from_user.id), "permission_denied"))
        return
    await state.update_data(title=message.text.strip())
    await state.set_state(CreateHomeworkState.instructions)
    await message.answer(et(await _user_lang(db, message.from_user.id), "homework_instructions"))


@router.message(CreateHomeworkState.instructions)
async def teacher_homework_instructions(message: Message, state: FSMContext, db: Database):
    data = await state.get_data()
    group_id = int(data.get("group_id", 0))
    group = await db.fetchone("SELECT course_id FROM education_groups WHERE id=? AND status='active'", (group_id,))
    if not group or not await db.teacher_has_scope(message.from_user.id, int(group["course_id"]), group_id):
        await state.clear()
        await message.answer(et(await _user_lang(db, message.from_user.id), "permission_denied"))
        return
    instructions = "" if (message.text or "").strip() == "/skip" else (message.text or message.caption or "")
    if len(instructions) > 3000:
        await message.answer("Ko‘rsatma 3000 belgidan oshmasin.")
        return
    try:
        homework_id = await db.create_homework(group_id=group_id, teacher_telegram_id=message.from_user.id,
                                               title=str(data["title"]), instructions=instructions)
    except (ValueError, PermissionError) as exc:
        await message.answer(escape(str(exc)))
        await state.clear()
        return
    await state.clear()
    await message.answer(f"{et(await _user_lang(db, message.from_user.id), 'homework_created')}\n<code>#{homework_id}</code>")


@router.callback_query(F.data == "edu:teacher:upload-material")
async def teacher_upload_material(callback: CallbackQuery, db: Database):
    lang = await _user_lang(db, callback.from_user.id)
    assignments = await db.teacher_assignments(callback.from_user.id)
    if not assignments:
        await callback.answer(et(lang, "permission_denied"), show_alert=True)
        return

    targets: dict[tuple[int, int], str] = {}
    for item in assignments:
        course_id = int(item["course_id"])
        course_name = item["course_name_uz"] if lang == "uz" else item["course_name_ru"] if lang == "ru" else item["course_name_en"]
        assigned_group_id = int(item["group_id"]) if item["group_id"] is not None else 0
        if assigned_group_id:
            label = f"{course_name} · {item['group_name'] or 'Guruh'}"
            targets[(course_id, assigned_group_id)] = label
            continue

        # Course-wide legacy assignment: allow a general course resource and optional group-specific resources.
        targets[(course_id, 0)] = f"{course_name} · barcha guruhlar"
        for group in await db.education_groups(course_id=course_id, teacher_id=callback.from_user.id, limit=80):
            targets[(course_id, int(group["id"]))] = f"{course_name} · {group['name']}"

    rows = [[InlineKeyboardButton(text=f"📘 {str(label)[:48]}", callback_data=f"edu:teacher:upload-target:{course_id}:{group_id}")]
            for (course_id, group_id), label in targets.items()]
    rows.append([InlineKeyboardButton(text=et(lang, "back"), callback_data="edu:teacher:home")])
    await callback.answer()
    if callback.message:
        await callback.message.edit_text("Material qaysi fan yoki guruh uchun?", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data.startswith("edu:teacher:upload-target:"))
async def teacher_upload_target(callback: CallbackQuery, state: FSMContext, db: Database):
    lang = await _user_lang(db, callback.from_user.id)
    try:
        _, _, _, course_id_raw, group_id_raw = callback.data.split(":", 4)
        course_id, group_id = int(course_id_raw), int(group_id_raw)
    except (ValueError, TypeError):
        await callback.answer("Tanlov noto‘g‘ri.", show_alert=True)
        return
    actual_group_id = group_id or None
    if not await db.teacher_has_scope(callback.from_user.id, course_id, actual_group_id):
        await callback.answer(et(lang, "permission_denied"), show_alert=True)
        return
    category_labels = {
        "book": "📚 Kitob / PDF", "vocabulary": "📖 Lug‘at", "movie": "🎬 Video",
        "music": "🎵 Audio", "quiz": "🧪 Test",
    }
    rows = [[InlineKeyboardButton(text=label, callback_data=f"edu:teacher:upload-category:{course_id}:{group_id}:{category}")]
            for category, label in category_labels.items()]
    rows.append([InlineKeyboardButton(text=et(lang, "back"), callback_data="edu:teacher:upload-material")])
    await callback.answer()
    if callback.message:
        await callback.message.edit_text("Material turini tanlang. U administrator tasdiqlashidan keyin o‘quvchilarga ko‘rinadi.",
                                         reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data.startswith("edu:teacher:upload-category:"))
async def teacher_upload_category(callback: CallbackQuery, state: FSMContext, db: Database):
    lang = await _user_lang(db, callback.from_user.id)
    try:
        _, _, _, course_raw, group_raw, category = callback.data.split(":", 5)
        course_id, group_id = int(course_raw), int(group_raw)
    except (ValueError, TypeError):
        await callback.answer("Material turi noto‘g‘ri.", show_alert=True)
        return
    if category not in {"book", "vocabulary", "movie", "music", "quiz"}:
        await callback.answer("Material turi qo‘llab-quvvatlanmaydi.", show_alert=True)
        return
    if not await db.teacher_has_scope(callback.from_user.id, course_id, group_id or None):
        await callback.answer(et(lang, "permission_denied"), show_alert=True)
        return
    await state.clear()
    await state.update_data(course_id=course_id, group_id=group_id or None, category=category, created_by_role="teacher")
    await state.set_state(AddLearningResourceState.title)
    await callback.answer()
    if callback.message:
        await callback.message.answer(f"{category.title()}\n\nMaterial nomini yuboring (2–180 belgi). /cancel — bekor qilish.")


@router.callback_query(F.data == "edu:teacher:submissions")
async def teacher_submissions(callback: CallbackQuery, db: Database):
    lang = await _user_lang(db, callback.from_user.id)
    if not await db.is_teacher(callback.from_user.id):
        await callback.answer(et(lang, "permission_denied"), show_alert=True)
        return
    submissions = await db.teacher_homework_submissions(callback.from_user.id, limit=40)
    buttons = []
    for row in submissions:
        label = f"{str(row['homework_title'])[:25]} · {str(row['first_name'] or row['telegram_id'])[:18]} · {row['status']}"
        buttons.append([InlineKeyboardButton(text=label[:60], callback_data=f"edu:teacher:submission:{int(row['id'])}")])
    buttons.append([InlineKeyboardButton(text=et(lang, "back"), callback_data="edu:teacher:home")])
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(et(lang, "review") + ("\n\nTopilmadi." if not submissions else ""),
                                         reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@router.callback_query(F.data.startswith("edu:teacher:submission:"))
async def teacher_submission_review_start(callback: CallbackQuery, state: FSMContext, db: Database):
    lang = await _user_lang(db, callback.from_user.id)
    try:
        submission_id = int(callback.data.rsplit(":", 1)[-1])
    except ValueError:
        await callback.answer("ID noto‘g‘ri.", show_alert=True)
        return
    submissions = await db.teacher_homework_submissions(callback.from_user.id, limit=200)
    item = next((row for row in submissions if int(row["id"]) == submission_id), None)
    if not item:
        await callback.answer(et(lang, "permission_denied"), show_alert=True)
        return
    text = (item["submission_text"] or "").strip() or "Matnli javob biriktirilmagan."
    await state.clear()
    await state.update_data(submission_id=submission_id)
    await state.set_state(ReviewSubmissionState.grade)
    await callback.answer()
    if callback.message:
        await callback.message.answer(
            f"📝 <b>{escape(item['homework_title'])}</b>\nGuruh: {escape(item['group_name'])}\n"
            f"O‘quvchi: <code>{int(item['telegram_id'])}</code>\n\n{escape(text)}\n\n"
            "Baho kiriting (0–100):"
        )
        if item["attachment_file_id"]:
            try:
                media_id = str(item["attachment_file_id"])
                media_type = str(item["attachment_type"] or "document")
                if media_type == "photo":
                    await callback.message.answer_photo(media_id)
                elif media_type == "video":
                    await callback.message.answer_video(media_id)
                elif media_type == "audio":
                    await callback.message.answer_audio(media_id)
                elif media_type == "voice":
                    await callback.message.answer_voice(media_id)
                else:
                    await callback.message.answer_document(media_id)
            except Exception:
                await callback.message.answer("Ilovani yuborib bo‘lmadi; fayl ID bazada saqlangan.")


@router.message(ReviewSubmissionState.grade)
async def teacher_submission_grade(message: Message, state: FSMContext):
    try:
        grade = float((message.text or "").strip().replace(",", "."))
    except ValueError:
        await message.answer("0–100 oralig‘ida raqam kiriting.")
        return
    if not 0 <= grade <= 100:
        await message.answer("Baho 0–100 oralig‘ida bo‘lishi kerak.")
        return
    await state.update_data(grade=grade)
    await state.set_state(ReviewSubmissionState.feedback)
    await message.answer("Izoh yuboring yoki /skip:")


@router.message(ReviewSubmissionState.feedback)
async def teacher_submission_feedback(message: Message, state: FSMContext, db: Database):
    data = await state.get_data()
    feedback = "" if (message.text or "").strip() == "/skip" else (message.text or "").strip()
    try:
        await db.review_homework_submission(submission_id=int(data["submission_id"]),
            teacher_telegram_id=message.from_user.id, status="graded", grade=float(data["grade"]), feedback=feedback)
    except (ValueError, PermissionError) as exc:
        await message.answer(escape(str(exc)))
        await state.clear()
        return
    await state.clear()
    await message.answer("✅ Baho saqlandi.")


@router.callback_query(F.data == "edu:teacher:attendance")
async def teacher_attendance(callback: CallbackQuery, db: Database):
    lang = await _user_lang(db, callback.from_user.id)
    groups = await db.education_groups(teacher_id=callback.from_user.id)
    buttons = [[InlineKeyboardButton(text=f"📅 {str(g['name'])[:40]}", callback_data=f"edu:teacher:attendance:create:{int(g['id'])}")] for g in groups]
    buttons.append([InlineKeyboardButton(text=et(lang, "back"), callback_data="edu:teacher:home")])
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(et(lang, "select_group"), reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@router.callback_query(F.data.startswith("edu:teacher:attendance:create:"))
async def teacher_attendance_create(callback: CallbackQuery, db: Database):
    lang = await _user_lang(db, callback.from_user.id)
    try:
        group_id = int(callback.data.rsplit(":", 1)[-1])
    except ValueError:
        await callback.answer("ID noto‘g‘ri.", show_alert=True)
        return
    try:
        session_id = await db.create_attendance_session(
            group_id=group_id, teacher_telegram_id=callback.from_user.id,
            session_date=datetime.now(_TZ).date().isoformat(),
        )
        students = await db.group_students(group_id, actor_telegram_id=callback.from_user.id)
    except (ValueError, PermissionError) as exc:
        await callback.answer(str(exc)[:180], show_alert=True)
        return
    buttons = []
    for student in students:
        name = " ".join(part for part in [student["first_name"], student["last_name"]] if part).strip() or str(student["telegram_id"])
        buttons.append([InlineKeyboardButton(text=f"✅ {name[:24]}", callback_data=f"edu:teacher:attendance:mark:{session_id}:{int(student['id'])}:present"),
                        InlineKeyboardButton(text="🕒", callback_data=f"edu:teacher:attendance:mark:{session_id}:{int(student['id'])}:late"),
                        InlineKeyboardButton(text="❌", callback_data=f"edu:teacher:attendance:mark:{session_id}:{int(student['id'])}:absent")])
    buttons.append([InlineKeyboardButton(text=et(lang, "back"), callback_data="edu:teacher:attendance")])
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(f"📅 Davomat · {datetime.now(_TZ).date().isoformat()}\nSessiya #{session_id}\nHar bir o‘quvchi uchun holatni tanlang:",
                                         reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@router.callback_query(F.data.startswith("edu:teacher:attendance:mark:"))
async def teacher_attendance_mark(callback: CallbackQuery, db: Database):
    parts = callback.data.split(":")
    if len(parts) != 7:
        await callback.answer("Davomat ma’lumoti noto‘g‘ri.", show_alert=True)
        return
    try:
        session_id, student_user_id = int(parts[4]), int(parts[5])
        status = parts[6]
        await db.mark_attendance(session_id=session_id, actor_telegram_id=callback.from_user.id,
                                 student_user_id=student_user_id, status=status)
    except (ValueError, PermissionError) as exc:
        await callback.answer(str(exc)[:180], show_alert=True)
        return
    await callback.answer("✅ Saqlandi")


@router.message(Command("assign_quiz"))
async def assign_quiz_command(message: Message, db: Database):
    if not message.from_user or getattr(message.chat.type, "value", str(message.chat.type)) != "private":
        await message.answer("Bu buyruq faqat botning shaxsiy chatida ishlaydi.")
        return
    parts = (message.text or "").split()
    if len(parts) not in {3, 4}:
        await message.answer("Format: <code>/assign_quiz RESOURCE_ID GROUP_ID [ATTEMPT_LIMIT]</code>")
        return
    try:
        resource_id, group_id = int(parts[1]), int(parts[2])
        attempt_limit = int(parts[3]) if len(parts) == 4 else 1
    except ValueError:
        await message.answer("ID va urinish soni butun son bo‘lishi kerak.")
        return
    role = await actor_role(db, message.from_user.id)
    actor_teacher_id = None
    if role == "teacher":
        resource = await db.learning_resource(resource_id, active_only=True)
        if not resource or not await db.teacher_has_scope(message.from_user.id, int(resource["course_id"]), group_id):
            await message.answer(et(await _user_lang(db, message.from_user.id), "permission_denied"))
            return
        actor_teacher_id = message.from_user.id
    elif role not in {"owner", "ceo", "senior_admin"}:
        await message.answer(et(await _user_lang(db, message.from_user.id), "permission_denied"))
        return
    try:
        assignment_id = await db.create_quiz_assignment(
            resource_id=resource_id, group_id=group_id, created_by=message.from_user.id,
            attempt_limit=attempt_limit, actor_teacher_id=actor_teacher_id,
        )
    except (ValueError, PermissionError) as exc:
        await message.answer(escape(str(exc)))
        return
    await message.answer(f"✅ Test guruhga tayinlandi. ID: <code>#{assignment_id}</code>")


@router.message(Command("owner_backup"))
async def owner_backup_command(message: Message):
    """Send a verified, read-only SQLite snapshot to the configured OWNER only."""
    if not message.from_user or not await is_owner_from_message(message):
        await message.answer("Bu buyruq mavjud emas.")
        return
    if getattr(message.chat.type, "value", str(message.chat.type)) != "private":
        await message.answer("Maxfiy backup faqat OWNER bilan shaxsiy chatda yuboriladi.")
        return
    try:
        from backup_db import backup_database
        stamp = datetime.now(_TZ).strftime("%Y%m%d-%H%M%S")
        backup_dir = Path(__file__).resolve().parents[1] / "backups"
        backup_path = backup_dir / f"startum-owner-{stamp}.sqlite3"
        result = backup_database(Path(config.database_path), backup_path)
        try:
            result.chmod(0o600)
        except OSError:
            logger.warning("Backup fayli permissionlarini cheklab bo‘lmadi.")
        await message.answer_document(
            FSInputFile(result),
            caption=f"✅ STARTUM SQLite backup tayyor.\nHajm: {result.stat().st_size:,} bayt\nIntegrity check: ok",
        )
    except Exception as exc:
        logger.exception("OWNER backup failed (%s)", type(exc).__name__)
        await message.answer("Backup yaratilmadi. Ma’lumotlar bazasi o‘zgartirilmadi; logni tekshiring.")


@router.message(Command("owner"))
async def owner_command(message: Message, db: Database):
    if not await is_owner(db, message.from_user.id):
        # Do not reveal the owner interface or its availability to other roles.
        await message.answer("Bu buyruq mavjud emas.")
        return
    if getattr(message.chat.type, "value", str(message.chat.type)) != "private":
        await message.answer("Maxfiy boshqaruv faqat shaxsiy chatda ochiladi.")
        return
    lang = await _user_lang(db, message.from_user.id)
    await message.answer(et(lang, "owner_title") + "\n\n" + et(lang, "owner_desc"), reply_markup=_owner_keyboard(lang))


async def _require_owner_callback(callback: CallbackQuery, db: Database) -> bool:
    chat_type = getattr(getattr(callback.message, "chat", None), "type", None)
    chat_type = getattr(chat_type, "value", str(chat_type))
    if await is_owner(db, callback.from_user.id) and callback.message and chat_type == "private":
        return True
    await callback.answer("Bu amal mavjud emas.", show_alert=True)
    return False


@router.callback_query(F.data.startswith("edu:owner:"))
async def owner_callbacks(callback: CallbackQuery, state: FSMContext, db: Database):
    if not await _require_owner_callback(callback, db):
        return
    lang = await _user_lang(db, callback.from_user.id)
    action = callback.data.removeprefix("edu:owner:")
    await callback.answer()
    if action == "stats":
        counts = {}
        for key, table in (("users", "users"), ("admins", "admins"), ("groups", "education_groups"),
                           ("materials", "learning_resources"), ("homework", "homework"),
                           ("submissions", "homework_submissions"), ("attendance", "attendance_records")):
            row = await db.fetchone(f"SELECT COUNT(*) AS total FROM {table}")
            counts[key] = int(row["total"] if row else 0)
        stat_labels = {"users": "Foydalanuvchilar", "admins": "Admin yozuvlari", "groups": "Guruhlar",
                       "materials": "Materiallar", "homework": "Uy vazifalari", "submissions": "Topshiriqlar", "attendance": "Davomat yozuvlari"}
        text = "📊 <b>STARTUM statistika</b>\n\n" + "\n".join(f"{label}: <b>{counts[key]}</b>" for key, label in stat_labels.items())
        await callback.message.edit_text(text, reply_markup=_back(et(lang, "back"), "owner:home"))
    elif action == "admins":
        rows = await db.admins(include_inactive=True)
        lines = [et(lang, "admins"), ""]
        for row in rows:
            lines.append(f"• <code>{int(row['telegram_id'])}</code> · {escape(str(row['role']))} · {'active' if row['active'] else 'inactive'}")
        if config.owner_telegram_id not in {int(r['telegram_id']) for r in rows}:
            lines.append(f"• <code>{config.owner_telegram_id}</code> · OWNER")
        await callback.message.edit_text("\n".join(lines), reply_markup=_back(et(lang, "back"), "owner:home"))
    elif action == "teachers":
        teachers = await db.fetchall(
            "SELECT tsa.telegram_id,COUNT(*) AS assignments,GROUP_CONCAT(c.name_uz, ', ') AS subjects "
            "FROM teacher_subject_assignments tsa JOIN courses c ON c.id=tsa.course_id WHERE tsa.active=1 GROUP BY tsa.telegram_id ORDER BY tsa.telegram_id LIMIT 50"
        )
        lines = [et(lang, "assign"), ""]
        for row in teachers:
            lines.append(f"• <code>{int(row['telegram_id'])}</code> · {int(row['assignments'])} · {escape(row['subjects'] or '')}")
        lines.append("\nUstoz tayinlash: /owner_assign_teacher TELEGRAM_ID COURSE_ID [GROUP_ID]")
        await callback.message.edit_text("\n".join(lines) if teachers else "Hozircha ustoz tayinlovi yo‘q.\n/owner_assign_teacher orqali tayinlang.", reply_markup=_back(et(lang, "back"), "owner:home"))
    elif action == "memberships":
        rows = await db.group_memberships_pending(50)
        buttons = []
        for row in rows:
            label = f"{row['group_name']} · {row['telegram_id']}"
            buttons.append([InlineKeyboardButton(text=label[:60], callback_data=f"edu:owner:membership:{int(row['id'])}")])
        buttons.append([InlineKeyboardButton(text=et(lang, "back"), callback_data="owner:home")])
        await callback.message.edit_text(et(lang, "admin_pending") + ("\n\nSo‘rov topilmadi." if not rows else ""), reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    elif action == "resources":
        rows = await db.pending_learning_resources(50)
        buttons = []
        for row in rows:
            buttons.append([InlineKeyboardButton(text=f"{row['title'][:35]} · #{int(row['id'])}", callback_data=f"edu:owner:resource:{int(row['id'])}")])
        buttons.append([InlineKeyboardButton(text=et(lang, "back"), callback_data="owner:home")])
        await callback.message.edit_text(et(lang, "resource_pending") + ("\n\nMaterial topilmadi." if not rows else ""), reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    elif action == "audit":
        rows = await db.education_audit(30)
        lines = [et(lang, "audit"), ""]
        for row in rows:
            lines.append(f"{escape(str(row['created_at']))[:16]} · <code>{int(row['actor_telegram_id'])}</code> · {escape(row['action'])}")
        await callback.message.edit_text("\n".join(lines) if rows else et(lang, "empty"), reply_markup=_back(et(lang, "back"), "owner:home"))
    elif action == "groups:create":
        courses = await db.courses()
        buttons = [[InlineKeyboardButton(text=str(c['name_uz'])[:50], callback_data=f"edu:owner:group-course:{int(c['id'])}")] for c in courses]
        buttons.append([InlineKeyboardButton(text=et(lang, "cancel"), callback_data="owner:home")])
        await state.clear()
        await callback.message.answer(et(lang, "choose_course"), reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    elif action.startswith("group-course:"):
        try:
            course_id = int(action.split(":", 1)[1])
        except ValueError:
            await callback.message.answer("Kurs ID noto‘g‘ri.")
            return
        if not await db.course(course_id):
            await callback.message.answer("Kurs topilmadi.")
            return
        await state.clear()
        await state.update_data(course_id=course_id)
        await state.set_state(CreateGroupState.name)
        await callback.message.answer(et(lang, "name_group"))
    elif action.startswith("membership:"):
        try:
            membership_id = int(action.split(":", 1)[1])
        except ValueError:
            return
        pending = next((r for r in await db.group_memberships_pending(100) if int(r['id']) == membership_id), None)
        if not pending:
            await callback.message.answer("So‘rov topilmadi yoki ko‘rib chiqilgan.")
            return
        buttons = [[InlineKeyboardButton(text=et(lang, "approve"), callback_data=f"edu:owner:membership-action:{membership_id}:yes"),
                    InlineKeyboardButton(text=et(lang, "reject"), callback_data=f"edu:owner:membership-action:{membership_id}:no")]]
        await callback.message.answer(f"Guruh: {escape(pending['group_name'])}\nTelegram ID: <code>{int(pending['telegram_id'])}</code>", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    elif action.startswith("membership-action:"):
        try:
            _, membership_id, choice = action.split(":")
            row = next((r for r in await db.group_memberships_pending(100) if int(r['id']) == int(membership_id)), None)
            if not row:
                await callback.message.answer("So‘rov allaqachon ko‘rib chiqilgan.")
                return
            approved = choice == "yes"
            success = await db.review_group_membership(int(membership_id), callback.from_user.id, approved)
            if success:
                try:
                    user_lang = await _user_lang(db, int(row['telegram_id']))
                    messages = {
                        "uz": ("✅ Guruhga qabul qilindingiz.", "Guruhga qo‘shilish so‘rovingiz rad etildi."),
                        "ru": ("✅ Вы приняты в группу.", "Ваш запрос на вступление в группу отклонён."),
                        "en": ("✅ You have joined the group.", "Your group membership request was declined."),
                    }
                    await callback.bot.send_message(int(row['telegram_id']), messages[user_lang][0 if approved else 1])
                except Exception:
                    logger.warning("Group membership notification could not be delivered.")
            await callback.message.answer("✅ Holat yangilandi." if success else "So‘rov yangilanmadi.")
        except ValueError:
            await callback.message.answer("So‘rov ma’lumoti noto‘g‘ri.")
    elif action.startswith("resource:"):
        try:
            resource_id = int(action.split(":", 1)[1])
        except ValueError:
            return
        buttons = [[InlineKeyboardButton(text="✅ Nashr qilish", callback_data=f"edu:owner:resource-action:{resource_id}:published"),
                    InlineKeyboardButton(text="⛔ Rad etish", callback_data=f"edu:owner:resource-action:{resource_id}:rejected")]]
        await callback.message.answer(f"Material #{resource_id} moderation:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    elif action.startswith("resource-action:"):
        try:
            _, resource_id, status = action.split(":")
            result = await db.set_resource_publication(int(resource_id), status, callback.from_user.id)
            await callback.message.answer(et(lang, "published") if result and status == "published" else "Material rad etildi." if result else "Material topilmadi.")
        except ValueError:
            await callback.message.answer("Holat noto‘g‘ri.")
    else:
        await callback.message.answer(et(lang, "empty"))


@router.message(CreateGroupState.name)
async def owner_group_name(message: Message, state: FSMContext, db: Database):
    if not await can_manage_groups_from_message(message, db):
        await state.clear()
        return
    name = (message.text or "").strip()
    if not 2 <= len(name) <= 100:
        await message.answer("Guruh nomi 2–100 belgi bo‘lishi kerak.")
        return
    await state.update_data(name=name)
    await state.set_state(CreateGroupState.schedule)
    await message.answer("Tasdiqlangan jadvalni yozing yoki noma’lum bo‘lsa /skip yuboring:")


async def is_owner_from_message(message: Message) -> bool:
    return bool(message.from_user and int(message.from_user.id) == int(config.owner_telegram_id)
                and getattr(message.chat.type, "value", str(message.chat.type)) == "private")


async def can_manage_groups_from_message(message: Message, db: Database) -> bool:
    if not message.from_user or getattr(message.chat.type, "value", str(message.chat.type)) != "private":
        return False
    return await is_admin_actor(db, message.from_user.id, ("ceo", "senior_admin"))


@router.message(CreateGroupState.schedule)
async def owner_group_schedule(message: Message, state: FSMContext, db: Database):
    if not await can_manage_groups_from_message(message, db):
        await state.clear()
        return
    data = await state.get_data()
    schedule = "" if (message.text or "").strip() == "/skip" else (message.text or "").strip()
    if len(schedule) > 240:
        await message.answer("Jadval 240 belgidan oshmasin.")
        return
    try:
        group = await db.create_education_group(str(data["name"]), int(data["course_id"]), schedule, message.from_user.id)
    except (ValueError, RuntimeError) as exc:
        await message.answer(escape(str(exc)))
        await state.clear()
        return
    await state.clear()
    await message.answer(f"✅ Guruh yaratildi: <b>{escape(group['name'])}</b>\nTaklif kodi: <code>{escape(group['invite_code'])}</code>\n\nKodni faqat tegishli o‘quvchilarga yuboring.")


@router.message(Command("owner_assign_teacher"))
@router.message(Command("assign_teacher"))
async def owner_assign_teacher(message: Message, db: Database):
    if not message.from_user or getattr(message.chat.type, "value", str(message.chat.type)) != "private":
        await message.answer("Bu buyruq faqat shaxsiy chatda ishlaydi.")
        return
    actor_id = int(message.from_user.id)
    command_name = (message.text or "").split(maxsplit=1)[0].split("@", 1)[0].lstrip("/").casefold()
    if command_name == "owner_assign_teacher":
        permitted = await is_owner(db, actor_id)
    else:
        permitted = await is_admin_actor(db, actor_id, ("ceo", "senior_admin"))
    if not permitted:
        await message.answer("Bu buyruq mavjud emas.")
        return
    parts = (message.text or "").split()
    if len(parts) not in {3, 4}:
        usage = "/owner_assign_teacher TELEGRAM_ID COURSE_ID [GROUP_ID]" if command_name == "owner_assign_teacher" else "/assign_teacher TELEGRAM_ID COURSE_ID [GROUP_ID]"
        await message.answer(f"Format: <code>{usage}</code>")
        return
    try:
        target_id, course_id = int(parts[1]), int(parts[2])
        group_id = int(parts[3]) if len(parts) == 4 else None
        if target_id <= 0:
            raise ValueError("Telegram ID musbat bo‘lishi kerak.")
        if target_id in {int(config.owner_telegram_id), int(config.ceo_owner_id)}:
            raise ValueError("OWNER yoki CEO hisobini ustoz sifatida tayinlab bo‘lmaydi.")
        assignment_id = await db.assign_teacher_subject(target_id, course_id, actor_id, group_id)
    except (ValueError, PermissionError) as exc:
        await message.answer(escape(str(exc)))
        return
    await message.answer(f"✅ Ustoz tayinlandi. Assignment: <code>#{assignment_id}</code> · <code>{target_id}</code>")
    from admin_commands import sync_teacher_commands
    await sync_teacher_commands(message.bot, target_id)
    try:
        await message.bot.send_message(target_id, "Sizga STARTUM’da ustoz paneli uchun fan biriktirildi. /teacher buyrug‘i orqali oching.")
    except Exception:
        pass


@router.message(Command("revoke_teacher_assignment"))
async def revoke_teacher_assignment_command(message: Message, db: Database):
    if not message.from_user or getattr(message.chat.type, "value", str(message.chat.type)) != "private":
        await message.answer("Bu buyruq faqat shaxsiy chatda ishlaydi.")
        return
    if not await is_admin_actor(db, message.from_user.id, ("ceo", "senior_admin")):
        await message.answer("Bu buyruq mavjud emas.")
        return
    parts = (message.text or "").split()
    if len(parts) != 2:
        await message.answer("Format: <code>/revoke_teacher_assignment ASSIGNMENT_ID</code>")
        return
    try:
        assignment_id = int(parts[1])
        if assignment_id <= 0:
            raise ValueError
        changed = await db.revoke_teacher_assignment(assignment_id, message.from_user.id)
    except ValueError:
        await message.answer("Assignment ID noto‘g‘ri.")
        return
    await message.answer("✅ Ustoz biriktiruvi bekor qilindi." if changed else "Faol biriktiruv topilmadi.")


@router.callback_query(F.data == "edu:admin:home")
async def admin_education_home(callback: CallbackQuery, db: Database):
    if not await is_admin_actor(db, callback.from_user.id, ("ceo", "senior_admin")):
        await callback.answer("Ruxsat yo‘q.", show_alert=True)
        return
    await callback.answer()
    if callback.message:
        await callback.message.edit_text("🎓 <b>Ta’lim boshqaruvi</b>", reply_markup=_admin_education_keyboard(await _user_lang(db, callback.from_user.id)))


@router.callback_query(F.data == "edu:admin:groups")
async def admin_groups_list(callback: CallbackQuery, db: Database):
    if not await is_admin_actor(db, callback.from_user.id, ("ceo", "senior_admin")):
        await callback.answer("Ruxsat yo‘q.", show_alert=True)
        return
    groups = await db.education_groups(active_only=False, limit=100)
    buttons = [[InlineKeyboardButton(
        text=f"{str(row['name'])[:30]} · {int(row['student_count'])} o‘quvchi",
        callback_data=f"edu:admin:group:{int(row['id'])}",
    )] for row in groups]
    buttons.append([InlineKeyboardButton(text="➕ Guruh yaratish", callback_data="edu:admin:groups:create")])
    buttons.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data="edu:admin:home")])
    await callback.answer()
    if callback.message:
        await callback.message.edit_text("👥 <b>Guruhlar</b>" + ("\n\nHozircha guruh yaratilmagan." if not groups else ""),
                                         reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@router.callback_query(F.data == "edu:admin:groups:create")
async def admin_group_create_start(callback: CallbackQuery, state: FSMContext, db: Database):
    if not await is_admin_actor(db, callback.from_user.id, ("ceo", "senior_admin")):
        await callback.answer("Ruxsat yo‘q.", show_alert=True)
        return
    courses = await db.courses()
    if not courses:
        await callback.answer("Faol fan topilmadi.", show_alert=True)
        return
    buttons = [[InlineKeyboardButton(text=str(course["name_uz"])[:50], callback_data=f"edu:admin:group-course:{int(course['id'])}")]
               for course in courses]
    buttons.append([InlineKeyboardButton(text="⬅️ Bekor qilish", callback_data="edu:admin:groups")])
    await state.clear()
    await callback.answer()
    if callback.message:
        await callback.message.edit_text("Guruh qaysi fan uchun yaratiladi?", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@router.callback_query(F.data.startswith("edu:admin:group-course:"))
async def admin_group_course_selected(callback: CallbackQuery, state: FSMContext, db: Database):
    if not await is_admin_actor(db, callback.from_user.id, ("ceo", "senior_admin")):
        await callback.answer("Ruxsat yo‘q.", show_alert=True)
        return
    try:
        course_id = int(callback.data.rsplit(":", 1)[-1])
    except ValueError:
        await callback.answer("Fan ID noto‘g‘ri.", show_alert=True)
        return
    course = await db.course(course_id)
    if not course:
        await callback.answer("Fan topilmadi.", show_alert=True)
        return
    await state.clear()
    await state.update_data(course_id=course_id)
    await state.set_state(CreateGroupState.name)
    await callback.answer()
    if callback.message:
        await callback.message.answer(et(await _user_lang(db, callback.from_user.id), "name_group"))


@router.callback_query(F.data.startswith("edu:admin:group:"))
async def admin_group_details(callback: CallbackQuery, db: Database):
    if not await is_admin_actor(db, callback.from_user.id, ("ceo", "senior_admin")):
        await callback.answer("Ruxsat yo‘q.", show_alert=True)
        return
    try:
        group_id = int(callback.data.rsplit(":", 1)[-1])
    except ValueError:
        await callback.answer("Guruh ID noto‘g‘ri.", show_alert=True)
        return
    row = await db.fetchone(
        "SELECT g.*,c.name_uz AS course_name FROM education_groups g JOIN courses c ON c.id=g.course_id WHERE g.id=?",
        (group_id,),
    )
    if not row:
        await callback.answer("Guruh topilmadi.", show_alert=True)
        return
    members = await db.fetchone("SELECT COUNT(*) AS n FROM group_memberships WHERE group_id=? AND status='active'", (group_id,))
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(
            f"👥 <b>{escape(row['name'])}</b>\nFan: {escape(row['course_name'])}\n"
            f"Jadval: {escape(row['schedule_text'] or 'Kiritilmagan')}\nA’zolar: {int(members['n'] or 0)}\n"
            f"Holat: {escape(row['status'])}\nTaklif kodi: <code>{escape(row['invite_code'])}</code>",
            reply_markup=_back("⬅️ Guruhlar", "edu:admin:groups"),
        )


@router.callback_query(F.data.startswith("edu:admin:memberships"))
async def admin_pending_memberships(callback: CallbackQuery, db: Database):
    if not await is_admin_actor(db, callback.from_user.id, ("ceo", "senior_admin")):
        await callback.answer("Ruxsat yo‘q.", show_alert=True)
        return
    rows = await db.group_memberships_pending(50)
    buttons = [[InlineKeyboardButton(text=f"{r['group_name']} · {r['telegram_id']}"[:60], callback_data=f"edu:admin:membership:{int(r['id'])}")] for r in rows]
    buttons.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data="edu:admin:home")])
    await callback.answer()
    if callback.message:
        await callback.message.edit_text("👥 <b>Tasdiqlash kutilayotgan guruh so‘rovlari</b>" + ("\n\nSo‘rov topilmadi." if not rows else ""), reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@router.callback_query(F.data.startswith("edu:admin:membership:"))
async def admin_membership_detail(callback: CallbackQuery, db: Database):
    if not await is_admin_actor(db, callback.from_user.id, ("ceo", "senior_admin")):
        await callback.answer("Ruxsat yo‘q.", show_alert=True)
        return
    try:
        membership_id = int(callback.data.rsplit(":", 1)[-1])
    except ValueError:
        await callback.answer("ID noto‘g‘ri.", show_alert=True)
        return
    row = next((r for r in await db.group_memberships_pending(100) if int(r['id']) == membership_id), None)
    if not row:
        await callback.answer("So‘rov topilmadi.", show_alert=True)
        return
    buttons = [[InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"edu:admin:membership-action:{membership_id}:yes"),
                InlineKeyboardButton(text="⛔ Rad etish", callback_data=f"edu:admin:membership-action:{membership_id}:no")],
               [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="edu:admin:memberships")]]
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(f"Guruh: {escape(row['group_name'])}\nO‘quvchi: <code>{int(row['telegram_id'])}</code>", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@router.callback_query(F.data.startswith("edu:admin:membership-action:"))
async def admin_membership_action(callback: CallbackQuery, db: Database):
    if not await is_admin_actor(db, callback.from_user.id, ("ceo", "senior_admin")):
        await callback.answer("Ruxsat yo‘q.", show_alert=True)
        return
    try:
        _, _, _, membership_id, decision = callback.data.split(":")
        row = next((r for r in await db.group_memberships_pending(100) if int(r['id']) == int(membership_id)), None)
        if not row:
            await callback.answer("So‘rov topilmadi.", show_alert=True)
            return
        approved = decision == "yes"
        done = await db.review_group_membership(int(membership_id), callback.from_user.id, approved)
        if done:
            await callback.bot.send_message(int(row['telegram_id']), "✅ Guruhga qabul qilindingiz." if approved else "Guruhga qo‘shilish so‘rovingiz rad etildi.")
        await callback.answer("Holat saqlandi." if done else "So‘rov yangilanmadi.")
    except (ValueError, IndexError):
        await callback.answer("So‘rov ma’lumoti noto‘g‘ri.", show_alert=True)


@router.callback_query(F.data == "edu:admin:resources")
async def admin_pending_resources(callback: CallbackQuery, db: Database):
    if not await is_admin_actor(db, callback.from_user.id, ("ceo", "senior_admin")):
        await callback.answer("Ruxsat yo‘q.", show_alert=True)
        return
    rows = await db.pending_learning_resources(50)
    buttons = [[InlineKeyboardButton(text=f"{r['title'][:38]} · #{int(r['id'])}", callback_data=f"edu:admin:resource:{int(r['id'])}")] for r in rows]
    buttons.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data="edu:admin:home")])
    await callback.answer()
    if callback.message:
        await callback.message.edit_text("📚 <b>Moderatsiya kutilayotgan materiallar</b>" + ("\n\nTopilmadi." if not rows else ""), reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@router.callback_query(F.data.startswith("edu:admin:resource:"))
async def admin_resource_detail(callback: CallbackQuery, db: Database):
    if not await is_admin_actor(db, callback.from_user.id, ("ceo", "senior_admin")):
        await callback.answer("Ruxsat yo‘q.", show_alert=True)
        return
    try:
        resource_id = int(callback.data.rsplit(":", 1)[-1])
    except ValueError:
        await callback.answer("ID noto‘g‘ri.", show_alert=True)
        return
    row = next((r for r in await db.pending_learning_resources(100) if int(r['id']) == resource_id), None)
    if not row:
        await callback.answer("Material topilmadi.", show_alert=True)
        return
    buttons = [[InlineKeyboardButton(text="✅ Nashr qilish", callback_data=f"edu:admin:resource-action:{resource_id}:published"),
                InlineKeyboardButton(text="⛔ Rad etish", callback_data=f"edu:admin:resource-action:{resource_id}:rejected")],
               [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="edu:admin:resources")]]
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(f"📚 <b>{escape(row['title'])}</b>\n{escape(row['description'])}\nFan: {escape(row['course_name'])}\nUstoz ID: <code>{int(row['created_by_telegram_id'])}</code>", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@router.callback_query(F.data.startswith("edu:admin:resource-action:"))
async def admin_resource_action(callback: CallbackQuery, db: Database):
    if not await is_admin_actor(db, callback.from_user.id, ("ceo", "senior_admin")):
        await callback.answer("Ruxsat yo‘q.", show_alert=True)
        return
    try:
        _, _, _, resource_id, status = callback.data.split(":")
        updated = await db.set_resource_publication(int(resource_id), status, callback.from_user.id)
    except (ValueError, IndexError):
        await callback.answer("Amal ma’lumoti noto‘g‘ri.", show_alert=True)
        return
    await callback.answer("✅ Saqlandi." if updated else "Material topilmadi.")


@router.callback_query(F.data == "edu:admin:announce")
async def admin_announcement_start(callback: CallbackQuery, state: FSMContext, db: Database):
    if not await is_admin_actor(db, callback.from_user.id, ("ceo", "senior_admin")):
        await callback.answer("Ruxsat yo‘q.", show_alert=True)
        return
    if not _is_private_callback(callback):
        await callback.answer("E’lon boshqaruvi faqat shaxsiy chatda ishlaydi.", show_alert=True)
        return
    await state.clear()
    await state.set_state(CreateAnnouncementState.title_uz)
    await callback.answer()
    if callback.message:
        await callback.message.answer("📣 E’lon sarlavhasini o‘zbek tilida yuboring. Keyin RU va EN tarjimalari so‘raladi. /cancel — bekor qilish.")


@router.message(Command("announce"))
async def announcement_command(message: Message, state: FSMContext, db: Database):
    if not message.from_user or getattr(message.chat.type, "value", str(message.chat.type)) != "private":
        await message.answer("E’lon faqat bot bilan shaxsiy chatda tayyorlanadi.")
        return
    if not await is_admin_actor(db, message.from_user.id, ("ceo", "senior_admin")):
        await message.answer(et(await _user_lang(db, message.from_user.id), "permission_denied"))
        return
    parts = (message.text or "").split()
    group_id = None
    if len(parts) > 2:
        await message.answer("Format: <code>/announce [GROUP_ID]</code>")
        return
    if len(parts) == 2:
        try:
            group_id = int(parts[1])
        except ValueError:
            await message.answer("Guruh ID raqam bo‘lishi kerak.")
            return
        if not await db.fetchone("SELECT id FROM education_groups WHERE id=? AND status='active'", (group_id,)):
            await message.answer("Faol guruh topilmadi.")
            return
    await state.clear()
    await state.update_data(group_id=group_id, translations={})
    await state.set_state(CreateAnnouncementState.title_uz)
    await message.answer("📣 E’lon sarlavhasi — O‘zbekcha (2–180 belgi):\nKeyin RU va EN. /cancel — bekor qilish.")


@router.message(CreateAnnouncementState.title_uz)
@router.message(CreateAnnouncementState.title_ru)
@router.message(CreateAnnouncementState.title_en)
@router.message(CreateAnnouncementState.body_uz)
@router.message(CreateAnnouncementState.body_ru)
@router.message(CreateAnnouncementState.body_en)
async def announcement_content_step(message: Message, state: FSMContext, db: Database):
    if not message.from_user or not await is_admin_actor(db, message.from_user.id, ("ceo", "senior_admin")):
        await state.clear()
        return
    current = await state.get_state()
    value = (message.text or "").strip()
    if not value:
        await message.answer("Matnli xabar yuboring.")
        return
    keys = {
        CreateAnnouncementState.title_uz.state: ("uz", "title", 180, CreateAnnouncementState.title_ru, "Sarlavha — Русский:"),
        CreateAnnouncementState.title_ru.state: ("ru", "title", 180, CreateAnnouncementState.title_en, "Title — English:"),
        CreateAnnouncementState.title_en.state: ("en", "title", 180, CreateAnnouncementState.body_uz, "Matn — O‘zbekcha:"),
        CreateAnnouncementState.body_uz.state: ("uz", "body", 3000, CreateAnnouncementState.body_ru, "Matn — Русский:"),
        CreateAnnouncementState.body_ru.state: ("ru", "body", 3000, CreateAnnouncementState.body_en, "Body — English:"),
        CreateAnnouncementState.body_en.state: ("en", "body", 3000, None, ""),
    }
    config_step = keys.get(current)
    if not config_step:
        await state.clear()
        return
    lang, field, max_len, next_state, prompt = config_step
    min_len = 2 if field == "title" else 5
    if not min_len <= len(value) <= max_len:
        await message.answer(f"Matn {min_len}–{max_len} belgi oralig‘ida bo‘lishi kerak.")
        return
    data = await state.get_data()
    translations = data.get("translations", {})
    translations.setdefault(lang, {})[field] = value
    await state.update_data(translations=translations)
    if next_state is not None:
        await state.set_state(next_state)
        await message.answer(prompt)
        return
    try:
        announcement_id = await db.create_announcement(
            created_by=message.from_user.id, translations=translations, group_id=data.get("group_id")
        )
    except (ValueError, RuntimeError) as exc:
        await state.clear()
        await message.answer(escape(str(exc)))
        return
    await state.clear()
    target_label = f"Guruh ID: {int(data['group_id'])}" if data.get("group_id") else "Barcha obunasi yoqilgan faol foydalanuvchilar"

    preview = announcement_preview(announcement_id, translations, target_label)
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Tasdiqlash va yuborish", callback_data=f"edu:announce:send:{announcement_id}")],
        [InlineKeyboardButton(text="Bekor qilish", callback_data=f"edu:announce:cancel:{announcement_id}")],
    ])
    await message.answer(preview, reply_markup=markup)


@router.callback_query(F.data.startswith("edu:announce:send:"))
async def announcement_send_confirmed(callback: CallbackQuery, db: Database):
    if not _is_private_callback(callback) or not await is_admin_actor(db, callback.from_user.id, ("ceo", "senior_admin")):
        await callback.answer("Ruxsat yo‘q.", show_alert=True)
        return
    try:
        announcement_id = int(callback.data.rsplit(":", 1)[-1])
        recipients, translations = await db.prepare_announcement_delivery(announcement_id, callback.from_user.id)
    except (ValueError, RuntimeError) as exc:
        await callback.answer(str(exc)[:180], show_alert=True)
        return
    await callback.answer("Yuborish boshlandi.")
    from asyncio import sleep
    sent = failed = 0
    for recipient in recipients:
        language = str(recipient["language"] or "uz")
        content = translations.get(language, translations["uz"])
        try:
            await callback.bot.send_message(
                int(recipient["telegram_id"]),
                f"📣 <b>{escape(content['title'])}</b>\n\n{escape(content['body'])}",
                disable_web_page_preview=True,
            )
            await db.record_announcement_delivery(announcement_id, int(recipient["user_id"]), "sent")
            sent += 1
        except Exception as exc:
            await db.record_announcement_delivery(announcement_id, int(recipient["user_id"]), "failed", type(exc).__name__)
            failed += 1
        await sleep(0.05)
    try:
        summary = await db.complete_announcement_delivery(announcement_id, callback.from_user.id)
    except ValueError as exc:
        await callback.message.answer(escape(str(exc)))
        return
    await callback.message.edit_text(
        f"✅ <b>E’lon yuborish yakunlandi.</b>\nYuborildi: {summary['sent']}\nXatolar: {summary['failed']}\nJami qabul qiluvchilar: {len(recipients)}"
    )


@router.callback_query(F.data.startswith("edu:announce:cancel:"))
async def announcement_cancel(callback: CallbackQuery, db: Database):
    if not _is_private_callback(callback) or not await is_admin_actor(db, callback.from_user.id, ("ceo", "senior_admin")):
        await callback.answer("Ruxsat yo‘q.", show_alert=True)
        return
    try:
        announcement_id = int(callback.data.rsplit(":", 1)[-1])
        changed = await db.cancel_announcement(announcement_id, callback.from_user.id)
    except (ValueError, RuntimeError):
        await callback.answer("E’lon ma’lumoti noto‘g‘ri.", show_alert=True)
        return
    await callback.answer("Bekor qilindi." if changed else "E’lonni bekor qilib bo‘lmadi.", show_alert=not bool(changed))
    if changed and callback.message:
        await callback.message.edit_text("E’lon bekor qilindi.")


@router.callback_query(F.data == "owner:home")
async def owner_home_callback(callback: CallbackQuery, db: Database):
    if not await _require_owner_callback(callback, db):
        return
    lang = await _user_lang(db, callback.from_user.id)
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(et(lang, "owner_title") + "\n\n" + et(lang, "owner_desc"), reply_markup=_owner_keyboard(lang))
