from __future__ import annotations

from html import escape
import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import config
from application_statuses import ALL_APPLICATION_STATUSES, application_status_label
from database.db import Database
from admin_authorization import resolve_telegram_admin_role
from admin_commands import sync_admin_commands, sync_teacher_commands
from keyboards.admin import (
    admin_panel, application_actions, web_application_actions, course_admin_menu,
    message_actions, admin_management_keyboard, admin_role_choice_keyboard,
    admin_confirm_keyboard, admin_add_confirmation_keyboard,
    user_search_results_keyboard, user_management_keyboard,
    user_suspend_duration_keyboard, user_moderation_confirm_keyboard,
)
from states.admin import (
    AddTeacherState, AddCourseState, ReplyMessageState, AddLearningResourceState,
    UserManagementState, AdminAddState,
)
from states.education import (
    JoinGroupState, CreateGroupState, CreateHomeworkState, SubmitHomeworkState,
    ReviewSubmissionState, CreateAnnouncementState,
)

router = Router()
logger = logging.getLogger(__name__)


async def _edit_or_send_callback_text(
    callback: CallbackQuery,
    text: str,
    *,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    """Edit a callback's message when possible; otherwise send a visible fallback.

    The original traceback for the historical webapps error was not available, so
    this handles Telegram's documented bad-edit cases without swallowing failures.
    """
    message = callback.message
    if not isinstance(message, Message):
        await callback.bot.send_message(callback.from_user.id, text, reply_markup=reply_markup)
        return

    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as exc:
        if "message is not modified" in str(exc).casefold():
            return
        logger.warning(
            "Admin callback message edit failed; sending fallback response (%s).",
            type(exc).__name__,
        )
        await message.answer(text, reply_markup=reply_markup)


def _is_owner_id(telegram_id: int) -> bool:
    return int(telegram_id) == int(config.owner_telegram_id)


async def require_admin(message: Message, db: Database) -> bool:
    if not message.from_user:
        await message.answer("⛔ Telegram foydalanuvchisi aniqlanmadi.")
        return False
    role = await resolve_telegram_admin_role(db, message.from_user.id, config.owner_telegram_id)
    if role is None:
        await message.answer("⛔ Sizda faol administrator huquqi yo‘q.")
        return False
    return True


async def require_role(message: Message, db: Database, roles: tuple[str, ...]) -> bool:
    if not await require_admin(message, db):
        return False
    if _is_owner_id(message.from_user.id):
        return True
    role = await resolve_telegram_admin_role(db, message.from_user.id, config.owner_telegram_id)
    if role not in roles:
        await message.answer("⛔ Bu amal uchun administrator rolingiz yetarli emas.")
        return False
    return True


def _is_private_message(message: Message | None) -> bool:
    if message is None:
        return False
    chat = getattr(message, "chat", None)
    chat_type = getattr(chat, "type", None)
    return getattr(chat_type, "value", str(chat_type)) == "private"


def _is_private_callback(callback: CallbackQuery) -> bool:
    return _is_private_message(callback.message if isinstance(callback.message, Message) else None)


async def _admin_text(
    message: Message, db: Database, *, minimum: int = 1, maximum: int = 1000,
    roles: tuple[str, ...] | None = None,
) -> str | None:
    """Read bounded text only after re-checking current permissions for every FSM step."""
    if roles:
        if not await require_role(message, db, roles):
            return None
    elif not await require_admin(message, db):
        return None
    if not message.text:
        await message.answer("Matn ko‘rinishidagi xabar yuboring.")
        return None
    value = message.text.strip()
    if len(value) < minimum:
        await message.answer("Ma’lumot juda qisqa. Qayta kiriting.")
        return None
    if len(value) > maximum:
        await message.answer(f"Matn {maximum} belgidan oshmasin.")
        return None
    return value


@router.message(Command("admin"))
async def admin_command(message: Message, db: Database):
    if not await require_admin(message, db):
        return
    if not _is_private_message(message):
        await message.answer("Admin panelni maxfiy ma’lumotlar uchun bot bilan shaxsiy chatda oching.")
        return
    role = await resolve_telegram_admin_role(db, message.from_user.id, config.owner_telegram_id)
    await message.answer(
        "🛡 <b>STARTUM ADMIN CONTROL CENTER</b>\n\n"
        "Bu panel faqat tasdiqlangan adminlar uchun.",
        reply_markup=admin_panel(role),
    )


@router.callback_query(F.data == "adm:home")
async def adm_home(callback: CallbackQuery, db: Database):
    if not await _cb_admin(callback, db):
        return
    await callback.answer()
    role = await resolve_telegram_admin_role(db, callback.from_user.id, config.owner_telegram_id)
    await callback.message.edit_text("🛡 <b>STARTUM ADMIN CONTROL CENTER</b>", reply_markup=admin_panel(role))


async def _cb_admin(callback: CallbackQuery, db: Database, roles: tuple[str, ...] | None = None) -> bool:
    # All dashboard callbacks are private; group chat is not an admin workspace.
    if not _is_private_callback(callback):
        await callback.answer("Admin boshqaruvi faqat shaxsiy chatda ishlaydi.", show_alert=True)
        return False
    if _is_owner_id(callback.from_user.id):
        return True
    role = await resolve_telegram_admin_role(db, callback.from_user.id, config.owner_telegram_id)
    if role is None:
        await callback.answer("⛔ Ruxsat yo‘q.", show_alert=True)
        return False
    if roles and role not in roles:
        await callback.answer("⛔ Bu amal uchun ruxsat yetarli emas.", show_alert=True)
        return False
    return True


@router.callback_query(F.data == "adm:applications")
async def applications(callback: CallbackQuery, db: Database):
    if not await _cb_admin(callback, db):
        return
    if not _is_private_callback(callback):
        await callback.answer("Ariza ma’lumotlari faqat shaxsiy chatda ko‘rsatiladi.", show_alert=True)
        return
    rows = await db.applications(limit=15)
    await callback.answer()
    if not rows:
        await callback.message.edit_text("📝 Hozircha arizalar yo‘q.", reply_markup=admin_panel())
        return
    text = "📝 <b>So‘nggi arizalar</b>\n\n"
    for row in rows:
        text += f"#{row['id']} · <b>{escape(row['full_name'])}</b> · {escape(row['course_name'])} · {row['status']}\n"
    await callback.message.edit_text(text, reply_markup=admin_panel())
    for row in rows[:5]:
        details = (
            f"📝 <b>ARIZA #{row['id']}</b>\n\n"
            f"👤 {escape(row['full_name'])}\n"
            f"📱 <code>{escape(row['phone'])}</code>\n"
            f"📚 {escape(row['course_name'])}\n"
            f"🎚 {escape(row['level'])}\n"
            f"🕒 {escape(row['preferred_time'])}\n"
            f"💬 {escape(row['message'] or '-') }\n"
            f"📌 Holat: <b>{escape(row['status'])}</b>\n"
            f"🆔 <code>{row['telegram_id']}</code>"
        )
        await callback.message.answer(details, reply_markup=application_actions(row['id']))


@router.callback_query(F.data.startswith("appstatus:"))
async def app_status(callback: CallbackQuery, db: Database):
    if not await _cb_admin(callback, db):
        return
    if not _is_private_callback(callback):
        await callback.answer("Ariza holatini faqat shaxsiy chatda o‘zgartiring.", show_alert=True)
        return
    try:
        _, app_id, status = callback.data.split(":", 2)
        app_id_int = int(app_id)
    except (ValueError, TypeError):
        await callback.answer("⛔ Noto‘g‘ri ariza ma’lumoti.", show_alert=True)
        return
    if app_id_int < 1 or status not in ALL_APPLICATION_STATUSES:
        await callback.answer("⛔ Noto‘g‘ri ariza holati.", show_alert=True)
        return
    application = await db.application(app_id_int)
    if not application:
        await callback.answer("Ariza topilmadi.", show_alert=True)
        return
    change = await db.change_application_status(
        "bot", app_id_int, status, actor=f"telegram:{callback.from_user.id}",
    )
    if not change:
        await callback.answer("Ariza topilmadi.", show_alert=True)
        return
    old_status = change["old_status"]
    await db.write_admin_audit(
        f"telegram:{callback.from_user.id}", "application_status_updated",
        entity_type="bot_application", entity_id=app_id_int,
        details=f"{old_status}->{status}",
    )
    if old_status != status:
        await db.enqueue_application_status_notification(
            source="bot", application_id=app_id_int,
            recipient_telegram_id=int(application["telegram_id"]), status=status,
            message_text=f"📌 <b>Ariza #{app_id_int}</b> holati yangilandi: <b>{escape(application_status_label(status))}</b>",
        )
    await callback.answer("✅ Status yangilandi. Foydalanuvchiga xabar navbatga qo‘yildi.")
    await callback.message.edit_reply_markup(reply_markup=application_actions(app_id_int))


@router.callback_query(F.data == "adm:webapps")
async def webapps(callback: CallbackQuery, db: Database):
    if not await _cb_admin(callback, db):
        return
    if not _is_private_callback(callback):
        await callback.answer("Sayt arizalari faqat shaxsiy chatda ko‘rsatiladi.", show_alert=True)
        return
    rows = await db.web_applications(limit=15)
    await callback.answer()
    if not rows:
        await _edit_or_send_callback_text(
            callback,
            "🌐 Hozircha saytdan arizalar yo‘q.",
            reply_markup=admin_panel(),
        )
        return
    text = "🌐 <b>SAYT ARIZALARI</b>\n\n"
    for row in rows:
        text += f"#{row['id']} · <b>{escape(row['full_name'])}</b> · {escape(row['course_name'])} · {escape(row['status'])}\n"
    await callback.message.edit_text(text[:4000], reply_markup=admin_panel())
    for row in rows[:5]:
        optional_details = []
        if row['level']:
            optional_details.append(f"🎚 Daraja: {escape(row['level'])}")
        if row['preferred_time']:
            optional_details.append(f"🕒 Qulay vaqt: {escape(row['preferred_time'])}")
        details = "\n".join([
            f"🌐 <b>SAYT ARIZASI #{row['id']}</b>",
            "",
            f"👤 {escape(row['full_name'])}",
            f"📱 <code>{escape(row['phone'])}</code>",
            f"🔗 {escape(row['telegram_username'] or '-')}",
            f"📚 {escape(row['course_name'])}",
            *optional_details,
            f"💬 {escape(row['message'] or '-')}",
            f"📌 Holat: <b>{escape(row['status'])}</b>",
        ])
        await callback.message.answer(details, reply_markup=web_application_actions(row['id']))


@router.callback_query(F.data.startswith("webappstatus:"))
async def webapp_status(callback: CallbackQuery, db: Database):
    if not await _cb_admin(callback, db):
        return
    if not _is_private_callback(callback):
        await callback.answer("Ariza holatini faqat shaxsiy chatda o‘zgartiring.", show_alert=True)
        return
    try:
        _, app_id, status = callback.data.split(":", 2)
        app_id_int = int(app_id)
    except (ValueError, TypeError):
        await callback.answer("⛔ Noto‘g‘ri ariza ma’lumoti.", show_alert=True)
        return
    if app_id_int < 1 or status not in ALL_APPLICATION_STATUSES:
        await callback.answer("⛔ Noto‘g‘ri ariza holati.", show_alert=True)
        return
    old_row = await db.web_application(app_id_int)
    if not old_row:
        await callback.answer("Sayt arizasi topilmadi.", show_alert=True)
        return
    change = await db.change_application_status(
        "website", app_id_int, status, actor=f"telegram:{callback.from_user.id}",
    )
    if not change:
        await callback.answer("Sayt arizasi topilmadi.", show_alert=True)
        return
    old_status = change["old_status"]
    await db.write_admin_audit(
        f"telegram:{callback.from_user.id}", "application_status_updated",
        entity_type="website_application", entity_id=app_id_int,
        details=f"{old_status}->{status}",
    )
    if old_status != status:
        identity_provider = old_row["identity_provider"] if "identity_provider" in old_row.keys() else ""
        external_user_id = old_row["external_user_id"] if "external_user_id" in old_row.keys() else ""
        if str(identity_provider or "").lower() == "telegram":
            try:
                recipient_id = int(external_user_id or 0)
            except (TypeError, ValueError):
                recipient_id = 0
            if recipient_id > 0:
                await db.enqueue_application_status_notification(
                    source="website", application_id=app_id_int,
                    recipient_telegram_id=recipient_id, status=status,
                    message_text=f"📌 <b>Sayt arizasi #{app_id_int}</b> holati yangilandi: <b>{escape(application_status_label(status))}</b>",
                )
    await callback.answer("✅ Sayt arizasi holati yangilandi")
    try:
        await callback.message.edit_reply_markup(reply_markup=web_application_actions(app_id_int))
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).casefold():
            logger.warning("Sayt arizasi #%s uchun tugmalar yangilanmadi (%s).", app_id_int, type(exc).__name__)


@router.callback_query(F.data == "adm:messages")
async def messages(callback: CallbackQuery, db: Database):
    if not await _cb_admin(callback, db):
        return
    if not _is_private_callback(callback):
        await callback.answer("Murojaatlar faqat shaxsiy chatda ko‘rsatiladi.", show_alert=True)
        return
    rows = await db.message_list(limit=15)
    await callback.answer()
    if not rows:
        await callback.message.edit_text("💬 Yangi murojaatlar yo‘q.", reply_markup=admin_panel())
        return
    text = "💬 <b>So‘nggi murojaatlar</b>\n\n"
    for row in rows:
        text += f"#{row['id']} · {escape(row['topic'])} · {escape(row['first_name'])}\n"
    await callback.message.edit_text(text, reply_markup=admin_panel())
    for row in rows[:5]:
        await callback.message.answer(
            f"💬 <b>#{row['id']}</b>\n👤 {escape(row['first_name'])}\n🆔 <code>{row['telegram_id']}</code>\n📌 {escape(row['topic'])}\n\n{escape(row['message_text'])}",
            reply_markup=message_actions(row['id'])
        )


@router.callback_query(F.data == "courseadm:add")
async def course_add_start(callback: CallbackQuery, state: FSMContext, db: Database):
    if not await _cb_admin(callback, db, ("ceo", "senior_admin")):
        return
    await state.set_state(AddCourseState.kind)
    await callback.answer()
    await callback.message.edit_text("1/8 — Turi: subject yoki special")


@router.message(AddCourseState.kind)
async def course_add_kind(message: Message, state: FSMContext, db: Database):
    value = await _admin_text(message, db, roles=("ceo", "senior_admin"), maximum=20)
    if value is None:
        return
    value = value.lower()
    if value not in {"subject", "special"}:
        await message.answer("subject yoki special yozing.")
        return
    await state.update_data(kind=value)
    await state.set_state(AddCourseState.name_uz)
    await message.answer("2/8 — O‘zbekcha nomi:")


@router.message(AddCourseState.name_uz)
async def course_add_uz(message: Message, state: FSMContext, db: Database):
    value = await _admin_text(message, db, roles=("ceo", "senior_admin"), minimum=2, maximum=120)
    if value is None: return
    await state.update_data(name_uz=value)
    await state.set_state(AddCourseState.name_ru)
    await message.answer("3/8 — Ruscha nomi:")


@router.message(AddCourseState.name_ru)
async def course_add_ru(message: Message, state: FSMContext, db: Database):
    value = await _admin_text(message, db, roles=("ceo", "senior_admin"), minimum=2, maximum=160)
    if value is None: return
    await state.update_data(name_ru=value)
    await state.set_state(AddCourseState.name_en)
    await message.answer("4/8 — Inglizcha nomi:")


@router.message(AddCourseState.name_en)
async def course_add_en(message: Message, state: FSMContext, db: Database):
    value = await _admin_text(message, db, roles=("ceo", "senior_admin"), minimum=2, maximum=160)
    if value is None: return
    await state.update_data(name_en=value)
    await state.set_state(AddCourseState.description_uz)
    await message.answer("5/8 — O‘zbekcha tavsif:")


@router.message(AddCourseState.description_uz)
async def course_add_duz(message: Message, state: FSMContext, db: Database):
    value = await _admin_text(message, db, roles=("ceo", "senior_admin"), maximum=1000)
    if value is None: return
    await state.update_data(description_uz=value)
    await state.set_state(AddCourseState.description_ru)
    await message.answer("6/8 — Ruscha tavsif:")


@router.message(AddCourseState.description_ru)
async def course_add_dru(message: Message, state: FSMContext, db: Database):
    value = await _admin_text(message, db, roles=("ceo", "senior_admin"), maximum=1000)
    if value is None: return
    await state.update_data(description_ru=value)
    await state.set_state(AddCourseState.description_en)
    await message.answer("7/8 — Inglizcha tavsif:")


@router.message(AddCourseState.description_en)
async def course_add_den(message: Message, state: FSMContext, db: Database):
    value = await _admin_text(message, db, roles=("ceo", "senior_admin"), maximum=1000)
    if value is None: return
    await state.update_data(description_en=value)
    await state.set_state(AddCourseState.icon)
    await message.answer("8/8 — Ikonka belgisi (masalan: 📚 yoki ∑):")


@router.message(AddCourseState.icon)
async def course_add_icon(message: Message, state: FSMContext, db: Database):
    value = await _admin_text(message, db, roles=("ceo", "senior_admin"), minimum=1, maximum=8)
    if value is None: return
    await state.update_data(icon=value)
    data = await state.get_data()
    try:
        course_id = await db.add_course(**data)
    except ValueError as exc:
        await state.clear()
        await message.answer(f"❌ {escape(str(exc))}", reply_markup=course_admin_menu())
        return
    await state.clear()
    await message.answer(f"✅ Kurs qo‘shildi. ID: <code>{course_id}</code>", reply_markup=course_admin_menu())


@router.callback_query(F.data == "adm:courses")
async def courses_admin(callback: CallbackQuery, db: Database):
    if not await _cb_admin(callback, db, ("ceo", "senior_admin")):
        return
    courses = await db.courses()
    await callback.answer()
    text = "📚 <b>Faol kurslar</b>\n\n" + "\n".join(f"{c['id']}. {c['icon']} {escape(c['name_uz'])} · <code>{escape(c['slug'])}</code>" for c in courses)
    await callback.message.edit_text(text[:4000], reply_markup=course_admin_menu())


@router.callback_query(F.data == "adm:teachers")
async def teachers_admin(callback: CallbackQuery, db: Database):
    if not await _cb_admin(callback, db, ("ceo", "senior_admin")):
        return
    teachers = await db.teachers()
    await callback.answer()
    text = "👨‍🏫 <b>Ustozlar</b>\n\n"
    text += "\n".join(f"{t['id']}. {escape(t['full_name'])} — {escape(t['subject'])}" for t in teachers) if teachers else "Hozircha ustoz yo‘q."
    await callback.message.edit_text(text, reply_markup=admin_panel())
    await callback.message.answer("➕ Ustoz qo‘shish uchun: /add_teacher")


@router.message(Command("add_teacher"))
async def add_teacher_start(message: Message, state: FSMContext, db: Database):
    if not await require_role(message, db, ("ceo", "senior_admin")):
        return
    await state.set_state(AddTeacherState.name)
    await message.answer("1/4 — Ustozning ism-familiyasini yozing:")


@router.message(AddTeacherState.name)
async def add_teacher_name(message: Message, state: FSMContext, db: Database):
    value = await _admin_text(message, db, roles=("ceo", "senior_admin"), minimum=2, maximum=120)
    if value is None: return
    await state.update_data(name=value)
    await state.set_state(AddTeacherState.subject)
    await message.answer("2/4 — Yo‘nalishi/fani:")


@router.message(AddTeacherState.subject)
async def add_teacher_subject(message: Message, state: FSMContext, db: Database):
    value = await _admin_text(message, db, roles=("ceo", "senior_admin"), minimum=2, maximum=120)
    if value is None: return
    await state.update_data(subject=value)
    await state.set_state(AddTeacherState.experience)
    await message.answer("3/4 — Tajribasi. Masalan: 5 yil")


@router.message(AddTeacherState.experience)
async def add_teacher_experience(message: Message, state: FSMContext, db: Database):
    value = await _admin_text(message, db, roles=("ceo", "senior_admin"), maximum=80)
    if value is None: return
    await state.update_data(experience=value)
    await state.set_state(AddTeacherState.bio)
    await message.answer("4/4 — Qisqa bio:")


@router.message(AddTeacherState.bio)
async def add_teacher_bio(message: Message, state: FSMContext, db: Database):
    value = await _admin_text(message, db, roles=("ceo", "senior_admin"), maximum=1000)
    if value is None: return
    await state.update_data(bio=value)
    data = await state.get_data()
    try:
        teacher_id = await db.add_teacher(data["name"], data["subject"], data.get("experience", ""), data.get("bio", ""))
    except ValueError as exc:
        await state.clear()
        await message.answer(f"❌ {escape(str(exc))}", reply_markup=admin_panel())
        return
    await state.clear()
    await message.answer(f"✅ Ustoz qo‘shildi. ID: <code>{teacher_id}</code>", reply_markup=admin_panel())


@router.callback_query(F.data.startswith("msgreply:"))
async def msg_reply_start(callback: CallbackQuery, state: FSMContext, db: Database):
    if not await _cb_admin(callback, db): return
    if not _is_private_callback(callback):
        await callback.answer("Murojaatga javobni faqat shaxsiy chatda yozing.", show_alert=True)
        return
    try:
        message_id = int(callback.data.split(":", 1)[1])
    except (ValueError, TypeError, IndexError):
        await callback.answer("Murojaat ID noto‘g‘ri.", show_alert=True)
        return
    if message_id < 1:
        await callback.answer("Murojaat ID noto‘g‘ri.", show_alert=True)
        return
    item=await db.message(message_id)
    if not item:
        await callback.answer("Murojaat topilmadi.",show_alert=True); return
    await state.update_data(message_id=message_id); await state.set_state(ReplyMessageState.answer)
    await callback.answer()
    await callback.message.answer(f"↩️ Murojaat #{message_id} uchun javobni yozing:")

@router.message(ReplyMessageState.answer)
async def msg_reply_finish(message: Message, state: FSMContext, db: Database):
    if not await require_admin(message, db): return
    data=await state.get_data(); item=await db.message(int(data["message_id"]))
    if not item:
        await state.clear(); await message.answer("❌ Murojaat topilmadi."); return
    if not message.text:
        await message.answer("Iltimos, matn ko‘rinishida javob yuboring.")
        return
    answer=message.text.strip()
    if len(answer) < 2 or len(answer) > 4000:
        await message.answer("Javobni batafsilroq yozing."); return
    await db.reply_message(int(data["message_id"]), answer); await state.clear()
    try:
        await message.bot.send_message(item["telegram_id"], f"💬 <b>STARTUM javobi</b>\n\n{escape(answer)}\n\nMurojaat #{item['id']}")
    except Exception as exc:
        logger.warning("Murojaat #%s javobi saqlandi, ammo foydalanuvchiga yetkazilmadi (%s).", item["id"], type(exc).__name__)
        await message.answer(
            "⚠️ Javob bazada saqlandi, ammo foydalanuvchiga Telegram orqali yetkazilmadi. "
            "Bot foydalanuvchiga xabar yubora olishini tekshiring.",
            reply_markup=admin_panel(),
        )
    else:
        await message.answer("✅ Javob foydalanuvchiga yuborildi.", reply_markup=admin_panel())

@router.callback_query(F.data.startswith("msgclose:"))
async def msg_close(callback: CallbackQuery, db: Database):
    if not await _cb_admin(callback, db): return
    if not _is_private_callback(callback):
        await callback.answer("Murojaatni faqat shaxsiy chatda yoping.", show_alert=True)
        return
    try:
        message_id = int(callback.data.split(":", 1)[1])
    except (ValueError, TypeError, IndexError):
        await callback.answer("Murojaat ID noto‘g‘ri.", show_alert=True)
        return
    if message_id < 1 or not await db.message(message_id):
        await callback.answer("Murojaat topilmadi.", show_alert=True)
        return
    await db.execute("UPDATE messages SET status='closed' WHERE id=?", (message_id,))
    await callback.answer("✅ Yopildi")
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).casefold():
            logger.warning("Murojaat #%s yopildi, ammo tugmalar yangilanmadi (%s).", message_id, type(exc).__name__)

@router.callback_query(F.data == "adm:stats")
async def stats(callback: CallbackQuery, db: Database):
    if not await _cb_admin(callback, db):
        return
    data = await db.stats()
    await callback.answer()
    await callback.message.edit_text(
        "📊 <b>STARTUM STATISTIKA</b>\n\n"
        f"👥 Foydalanuvchilar: <b>{data['users']}</b>\n"
        f"📚 Faol kurslar: <b>{data['courses']}</b>\n"
        f"👨‍🏫 Ustozlar: <b>{data['teachers']}</b>\n"
        f"📝 Arizalar: <b>{data['applications']}</b>\n"
        f"🟡 Yangi arizalar: <b>{data['new_applications']}</b>\n"
        f"💬 Yangi murojaatlar: <b>{data['messages']}</b>\n"
        f"🌐 Sayt arizalari: <b>{data['web_applications']}</b>\n"
        f"🟡 Yangi sayt arizalari: <b>{data['new_web_applications']}</b>",
        reply_markup=admin_panel(),
    )


async def _send_user_search_results(message: Message, db: Database, query: str) -> None:
    search = " ".join(query.split())[:120]
    rows = await db.search_users(search, limit=10)
    total = await db.count_users(search)
    if not rows:
        await message.answer("Foydalanuvchi topilmadi. Telegram ID, ichki ID, ism yoki username bilan qidiring.")
        return
    suffix = f"\nBirinchi {len(rows)} ta natija ko‘rsatilmoqda (jami {total} ta)." if total > len(rows) else ""
    await message.answer(
        "🔎 <b>FOYDALANUVCHILAR</b>\n\nNatijani tanlang:" + suffix,
        reply_markup=user_search_results_keyboard(rows),
    )


@router.callback_query(F.data == "adm:users")
async def user_search_start(callback: CallbackQuery, db: Database, state: FSMContext):
    if not await _cb_admin(callback, db):
        return
    if not callback.message or getattr(callback.message.chat.type, "value", str(callback.message.chat.type)) != "private":
        await callback.answer("Foydalanuvchi ma’lumotlarini ko‘rish uchun bot bilan shaxsiy chatni oching.", show_alert=True)
        return
    await state.clear()
    await state.set_state(UserManagementState.search)
    await callback.answer()
    await callback.message.answer("Telegram ID, ichki ID, ism yoki username yozing. Bekor qilish uchun /cancel yuboring:")


@router.message(Command("users"))
@router.message(Command("user"))
async def user_search_command(message: Message, db: Database, state: FSMContext):
    if not await require_admin(message, db):
        return
    if getattr(message.chat.type, "value", str(message.chat.type)) != "private":
        await message.answer("Foydalanuvchi ma’lumotlarini ko‘rish uchun bot bilan shaxsiy chatdan foydalaning.")
        return
    parts = (message.text or "").split(maxsplit=1)
    query = parts[1].strip() if len(parts) == 2 else ""
    if query:
        await state.clear()
        await _send_user_search_results(message, db, query)
    else:
        await state.clear()
        await state.set_state(UserManagementState.search)
        await message.answer("Telegram ID, ichki ID, ism yoki username yozing. Bekor qilish uchun /cancel yuboring:")


@router.message(UserManagementState.search)
async def user_search_received(message: Message, db: Database, state: FSMContext):
    if not await require_admin(message, db):
        await state.clear()
        return
    if not message.text:
        await message.answer("Telegram ID, ism yoki username kabi matn yuboring.")
        return
    query = message.text.strip()
    if query.casefold() in {"/cancel", "bekor", "cancel"}:
        await state.clear()
        await message.answer("Qidiruv bekor qilindi.", reply_markup=admin_panel())
        return
    await state.clear()
    await _send_user_search_results(message, db, query)


@router.callback_query(F.data.startswith("admuser:view:"))
async def user_detail_view(callback: CallbackQuery, db: Database, state: FSMContext):
    if not await _cb_admin(callback, db):
        return
    if not callback.message or getattr(callback.message.chat.type, "value", str(callback.message.chat.type)) != "private":
        await callback.answer("Foydalanuvchi ma’lumotlari faqat shaxsiy chatda ochiladi.", show_alert=True)
        return
    try:
        user_id = int(callback.data.rsplit(":", 1)[1])
    except (ValueError, TypeError):
        await callback.answer("Foydalanuvchi ID noto‘g‘ri.", show_alert=True)
        return
    details = await db.user_details(user_id)
    if not details:
        await callback.answer("Foydalanuvchi topilmadi.", show_alert=True)
        return
    await state.clear()
    user = details["user"]
    name = " ".join(part for part in (str(user["first_name"] or ""), str(user["last_name"] or "")) if part).strip()
    name = name or (f"@{user['username']}" if user["username"] else str(user["telegram_id"]))
    status = str(user["account_status"])
    lines = [
        "👤 <b>FOYDALANUVCHI KARTASI</b>", "",
        f"Ism: <b>{escape(name[:100])}</b>",
        f"Ichki ID: <code>{int(user['id'])}</code>",
        f"Telegram ID: <code>{int(user['telegram_id'])}</code>",
        f"Username: {escape('@' + str(user['username']) if user['username'] else '—')}",
        f"Ro‘yxatdan o‘tgan: {escape(str(user['created_at'])[:16].replace('T',' '))}",
        f"STARTUM holati: <b>{'Cheklangan' if status == 'suspended' else 'Faol'}</b>" + (f" · {escape(str(user['suspended_until'])[:16].replace('T',' '))}" if user.get("suspended_until") else ""),
        "",
        f"Arizalar: <b>{len(details['applications'])}</b>",
    ]
    for item in details["applications"][:5]:
        lines.append(f"• {escape(str(item['course_name'])[:60])} · {escape(str(item['status']))} · {escape(str(item['created_at'])[:10])}")
    lines.extend(["", f"Test urinishlari: <b>{len(details['quiz_attempts'])}</b>"])
    for attempt in details["quiz_attempts"][:5]:
        lines.append(f"• {escape(str(attempt['quiz_title'])[:60])} · {int(attempt['score'])}/{int(attempt['total'])} ({int(attempt['percent'])}%)")
    lines.extend(["", "<b>Cheklovlar tarixi</b>"])
    if details["moderation_actions"]:
        for item in details["moderation_actions"][:5]:
            lines.append(f"• {escape(str(item['action']))} · {escape(str(item['created_at'])[:16].replace('T',' '))} · {escape(str(item['reason'] or 'Sababsiz')[:100])}")
    else:
        lines.append("Cheklov amallari yo‘q.")
    role = await db.admin_role(callback.from_user.id)
    await callback.answer()
    await callback.message.answer(
        "\n".join(lines)[:3900],
        reply_markup=user_management_keyboard(
            user_id, status, can_moderate=role in {"ceo", "senior_admin"},
        ),
    )


@router.callback_query(F.data.startswith("admuser:action:"))
async def user_moderation_start(callback: CallbackQuery, db: Database, state: FSMContext):
    if not await _cb_admin(callback, db, ("ceo", "senior_admin")):
        return
    if not callback.message or getattr(callback.message.chat.type, "value", str(callback.message.chat.type)) != "private":
        await callback.answer("Foydalanuvchi cheklovini faqat bot bilan shaxsiy chatda boshqaring.", show_alert=True)
        return
    try:
        _, _, raw_id, action = callback.data.split(":", 3)
        user_id = int(raw_id)
    except (ValueError, TypeError):
        await callback.answer("Foydalanuvchi amali noto‘g‘ri.", show_alert=True)
        return
    if action not in {"suspend", "restore"} or not await db.user_by_internal_id(user_id):
        await callback.answer("Foydalanuvchi topilmadi yoki amal noto‘g‘ri.", show_alert=True)
        return
    await state.clear()
    await state.update_data(user_id=user_id, action=action)
    await callback.answer()
    if action == "suspend":
        await callback.message.answer(
            "Cheklov muddatini tanlang. Bu foydalanuvchining faqat STARTUM botidagi kirishiga ta’sir qiladi:",
            reply_markup=user_suspend_duration_keyboard(user_id),
        )
        return
    await state.update_data(duration_minutes=None)
    await state.set_state(UserManagementState.reason)
    await callback.message.answer("Tiklash sababini yozing yoki <code>-</code> yuboring:")


@router.callback_query(F.data.startswith("admuser:duration:"))
async def user_moderation_duration(callback: CallbackQuery, db: Database, state: FSMContext):
    if not await _cb_admin(callback, db, ("ceo", "senior_admin")):
        return
    try:
        _, _, raw_id, raw_minutes = callback.data.split(":", 3)
        user_id, minutes = int(raw_id), int(raw_minutes)
    except (ValueError, TypeError):
        await callback.answer("Cheklov muddati noto‘g‘ri.", show_alert=True)
        return
    data = await state.get_data()
    if int(data.get("user_id", 0)) != user_id or data.get("action") != "suspend" or minutes not in {0, 60, 1440, 10080}:
        await callback.answer("Cheklov oynasi eskirgan. Qaytadan boshlang.", show_alert=True)
        await state.clear()
        return
    await state.update_data(duration_minutes=minutes or None)
    await state.set_state(UserManagementState.reason)
    await callback.answer()
    await callback.message.answer("Cheklov sababini yozing yoki <code>-</code> yuboring:")


@router.message(UserManagementState.reason)
async def user_moderation_reason(message: Message, db: Database, state: FSMContext):
    if not await require_role(message, db, ("ceo", "senior_admin")):
        await state.clear()
        return
    if not message.text:
        await message.answer("Sabab matn ko‘rinishida bo‘lsin yoki - yuboring.")
        return
    reason = " ".join(message.text.split())
    if reason.casefold() in {"-", "skip"}:
        reason = ""
    if len(reason) > 500:
        await message.answer("Sabab 500 belgidan oshmasin.")
        return
    data = await state.get_data()
    if not data.get("user_id") or data.get("action") not in {"suspend", "restore"}:
        await state.clear()
        await message.answer("Tasdiqlash ma’lumoti topilmadi. Amalni qaytadan boshlang.")
        return
    await state.update_data(reason=reason)
    await state.set_state(UserManagementState.confirm)
    target = await db.user_by_internal_id(int(data["user_id"]))
    if not target:
        await state.clear()
        await message.answer("Foydalanuvchi topilmadi.")
        return
    action_text = "STARTUM botida cheklash" if data["action"] == "suspend" else "STARTUM botiga kirishni tiklash"
    duration_text = f"{data['duration_minutes']} daqiqa" if data.get("duration_minutes") else "muddatsiz"
    await message.answer(
        f"⚠️ <b>Tasdiqlash</b>\n\nTelegram ID: <code>{int(target['telegram_id'])}</code>\n"
        f"Amal: <b>{action_text}</b>\n"
        f"Muddat: <b>{duration_text if data['action'] == 'suspend' else '—'}</b>\n"
        f"Sabab: {escape(reason or 'ko‘rsatilmagan')}\n\nDavom etasizmi?",
        reply_markup=user_moderation_confirm_keyboard(),
    )


@router.callback_query(F.data == "admuser:confirm")
async def user_moderation_confirm(callback: CallbackQuery, db: Database, state: FSMContext):
    if not await _cb_admin(callback, db, ("ceo", "senior_admin")):
        return
    data = await state.get_data()
    if await state.get_state() != UserManagementState.confirm.state or not data.get("user_id"):
        await callback.answer("Tasdiqlash ma’lumoti eskirgan. Amalni boshidan boshlang.", show_alert=True)
        await state.clear()
        return
    action = str(data.get("action"))
    try:
        result = await db.moderate_user(
            int(data["user_id"]),
            action=action,
            actor=f"tg:{callback.from_user.id}",
            reason=str(data.get("reason") or ""),
            duration_minutes=data.get("duration_minutes"),
        )
    except ValueError as exc:
        await callback.answer(str(exc)[:180], show_alert=True)
        await state.clear()
        return
    await state.clear()
    await callback.answer("✅ Amal bajarildi.")
    if callback.message:
        await callback.message.answer(
            f"✅ <code>{result['telegram_id']}</code> foydalanuvchining STARTUM botidagi holati {result['status']} qilindi.",
            reply_markup=admin_panel(),
        )


@router.callback_query(F.data == "admuser:cancel")
async def user_moderation_cancel(callback: CallbackQuery, db: Database, state: FSMContext):
    if not await _cb_admin(callback, db):
        return
    await state.clear()
    await callback.answer("Amal bekor qilindi.")
    if callback.message:
        await callback.message.answer("Amal bekor qilindi.", reply_markup=admin_panel())


@router.callback_query(F.data == "adm:admins")
async def admins(callback: CallbackQuery, db: Database):
    if not await _cb_admin(callback, db, ("ceo",)):
        return
    if not _is_private_callback(callback):
        await callback.answer("Adminlar ro‘yxati faqat shaxsiy chatda ko‘rsatiladi.", show_alert=True)
        return
    rows = await db.admins(include_inactive=True)
    await callback.answer()
    role_labels = {"ceo": "CEO", "owner": "CEO", "senior_admin": "Katta admin", "admin": "Katta admin", "junior_admin": "Kichik admin"}
    lines = []
    for row in rows[:15]:
        linked = await db.web_admin_by_telegram_id(int(row["telegram_id"]))
        if linked and int(linked["active"]) and int(linked["telegram_verified"] or 0):
            link_state = "sayt va bot hisobi faol"
        elif linked and int(linked["active"]):
            link_state = "sayt hisobi faol, bot uchun kirish kutilmoqda"
        elif linked:
            link_state = "parol hisobi bor, CEO faollashtirishi kerak"
        else:
            link_state = "parol hisobi ulanmagan"
        if int(row["bot_invite_pending"] or 0):
            bot_state = "Botda /start kutilyapti"
        elif int(row["active"] or 0):
            bot_state = "Botda faol"
        else:
            bot_state = "Bot huquqi bloklangan/qayta ulash kutilmoqda"
        lines.append(f"<code>{int(row['telegram_id'])}</code> — {role_labels.get(row['role'], escape(row['role']))} · {bot_state} · {link_state}")
    commands = (
        "\n\n<b>Admin boshqaruvi</b>\n"
        "Yangi admin ID: <code>/add_admin TELEGRAM_ID senior_admin|junior_admin</code>\n"
        "Adminni bloklash: <code>/remove_admin TELEGRAM_ID</code>\n\n"
        "OWNER taklifni tasdiqlagach, aynan shu Telegram ID egasi botni ochib <code>/start</code> yuborsa, <b>bot administratori</b> faollashadi. Website Admin hisobi alohida yaratiladi va o‘z paroli bilan tasdiqlanadi; bot taklifi saytga kirish huquqini bermaydi."
    )
    if len(rows) > 15:
        lines.append(f"… va yana {len(rows) - 15} ta administrator. Ro‘yxatning dastlabki 15 tasi ko‘rsatilmoqda.")
    visible_rows = rows[:15]
    await callback.message.edit_text(
        "👥 <b>TELEGRAM ADMINLARI</b>\n\n" + ("\n".join(lines) or "Adminlar yo‘q.") + commands,
        reply_markup=admin_management_keyboard(visible_rows),
    )


@router.callback_query(F.data.startswith("admadmin:role:"))
async def admin_choose_role(callback: CallbackQuery, db: Database):
    if not await _cb_admin(callback, db, ("ceo",)):
        return
    if not _is_private_callback(callback):
        await callback.answer("Admin boshqaruvi faqat shaxsiy chatda ishlaydi.", show_alert=True)
        return
    try:
        telegram_id = int(callback.data.rsplit(":", 1)[1])
    except (ValueError, TypeError, IndexError):
        await callback.answer("Telegram ID noto‘g‘ri.", show_alert=True)
        return
    target = await db.fetchone("SELECT telegram_id,role FROM admins WHERE telegram_id=?", (telegram_id,))
    if not target or str(target["role"]) in {"ceo", "owner"} or telegram_id in {config.ceo_owner_id, config.owner_telegram_id}:
        await callback.answer("Bu administrator rolini o‘zgartirib bo‘lmaydi.", show_alert=True)
        return
    await callback.answer()
    await _edit_or_send_callback_text(
        callback,
        f"👤 <b>Admin {telegram_id}</b> uchun yangi rolni tanlang.\nJoriy rol: <b>{escape(str(target['role']))}</b>.\n\nTasdiqlangach, eski sessiyalar bekor qilinadi. CEO veb-admin hisobini qayta faollashtirishi, admin esa parol bilan qayta kirishi kerak.",
        reply_markup=admin_role_choice_keyboard(telegram_id),
    )


@router.callback_query(F.data.startswith("admadmin:role-select:"))
async def admin_role_selected(callback: CallbackQuery, db: Database):
    if not await _cb_admin(callback, db, ("ceo",)):
        return
    if not _is_private_callback(callback):
        await callback.answer("Admin boshqaruvi faqat shaxsiy chatda ishlaydi.", show_alert=True)
        return
    try:
        _, _, raw_id, role = callback.data.split(":", 3)
        telegram_id = int(raw_id)
    except (ValueError, TypeError):
        await callback.answer("Rol yoki ID noto‘g‘ri.", show_alert=True)
        return
    if telegram_id < 1 or role not in {"senior_admin", "junior_admin"} or telegram_id in {config.ceo_owner_id, config.owner_telegram_id}:
        await callback.answer("Bu administrator rolini o‘zgartirib bo‘lmaydi.", show_alert=True)
        return
    target = await db.fetchone("SELECT role FROM admins WHERE telegram_id=?", (telegram_id,))
    if not target or str(target["role"]) in {"ceo", "owner"}:
        await callback.answer("Administrator topilmadi yoki bu ID himoyalangan.", show_alert=True)
        return
    await callback.answer()
    await _edit_or_send_callback_text(
        callback,
        f"⚠️ <b>Tasdiqlash</b>\nAdmin <code>{telegram_id}</code> rolini <b>{'Katta administrator' if role == 'senior_admin' else 'Kichik administrator'}</b> qilib o‘zgartirasizmi?\n\nMavjud web-sessiyalar bekor qilinadi. Bot huquqi qayta parol bilan kirilgandan keyin faollashadi.",
        reply_markup=admin_confirm_keyboard(telegram_id, action="role", role=role),
    )


@router.callback_query(F.data.startswith("admadmin:role-confirm:"))
async def admin_role_confirmed(callback: CallbackQuery, db: Database):
    if not await _cb_admin(callback, db, ("ceo",)):
        return
    if not _is_private_callback(callback):
        await callback.answer("Admin boshqaruvi faqat shaxsiy chatda ishlaydi.", show_alert=True)
        return
    try:
        _, _, raw_id, role = callback.data.split(":", 3)
        telegram_id = int(raw_id)
    except (ValueError, TypeError):
        await callback.answer("Rol yoki ID noto‘g‘ri.", show_alert=True)
        return
    target = await db.fetchone("SELECT role FROM admins WHERE telegram_id=?", (telegram_id,))
    if telegram_id < 1 or role not in {"senior_admin", "junior_admin"} or not target or str(target["role"]) in {"ceo", "owner"} or telegram_id in {config.ceo_owner_id, config.owner_telegram_id}:
        await callback.answer("Administratorni yangilab bo‘lmadi.", show_alert=True)
        return
    previous_role = str(target["role"])
    if previous_role == role:
        await callback.answer("Rol o‘zgarmadi.")
        return
    try:
        await db.add_telegram_admin(telegram_id, role, callback.from_user.id, active=False)
    except ValueError as exc:
        await callback.answer(str(exc)[:180], show_alert=True)
        return
    await sync_admin_commands(callback.bot, telegram_id, None)
    await db.write_admin_audit(
        str(callback.from_user.id), "telegram_admin_role_changed",
        entity_type="telegram_admin", entity_id=telegram_id,
        details=f"old_role={previous_role}; new_role={role}",
    )
    await callback.answer("✅ Rol yangilandi; eski sessiyalar bekor qilindi.")
    await _edit_or_send_callback_text(
        callback,
        f"✅ Admin <code>{telegram_id}</code> roli yangilandi. CEO veb-admin hisobini qayta faollashtirsin; admin parol bilan qayta kirgach bot huquqlari tiklanadi.",
        reply_markup=admin_panel(),
    )


@router.callback_query(F.data.startswith("admadmin:toggle:"))
async def admin_toggle_prompt(callback: CallbackQuery, db: Database):
    if not await _cb_admin(callback, db, ("ceo",)):
        return
    if not _is_private_callback(callback):
        await callback.answer("Admin boshqaruvi faqat shaxsiy chatda ishlaydi.", show_alert=True)
        return
    try:
        telegram_id = int(callback.data.rsplit(":", 1)[1])
    except (ValueError, TypeError, IndexError):
        await callback.answer("Telegram ID noto‘g‘ri.", show_alert=True)
        return
    target = await db.fetchone("SELECT role,active FROM admins WHERE telegram_id=?", (telegram_id,))
    if not target or str(target["role"]) in {"ceo", "owner"} or telegram_id in {config.ceo_owner_id, config.owner_telegram_id}:
        await callback.answer("Bu administrator holatini o‘zgartirib bo‘lmaydi.", show_alert=True)
        return
    action = "deactivate" if int(target["active"] or 0) else "activate"
    action_text = "vaqtincha bloklash" if action == "deactivate" else "qayta faollashtirish bosqichini boshlash"
    await callback.answer()
    await _edit_or_send_callback_text(
        callback,
        f"⚠️ <b>Tasdiqlash</b>\nAdmin <code>{telegram_id}</code> hisobini {action_text}ni tasdiqlaysizmi?\n\nQayta faollashtirish uchun bog‘langan web-admin hisobi kerak bo‘ladi; bot ruxsati yangi parol bilan kirilgandan keyin tiklanadi.",
        reply_markup=admin_confirm_keyboard(telegram_id, action=action),
    )


@router.callback_query(F.data.startswith("admadmin:toggle-confirm:"))
async def admin_toggle_confirmed(callback: CallbackQuery, db: Database):
    if not await _cb_admin(callback, db, ("ceo",)):
        return
    if not _is_private_callback(callback):
        await callback.answer("Admin boshqaruvi faqat shaxsiy chatda ishlaydi.", show_alert=True)
        return
    try:
        _, _, raw_id, action = callback.data.split(":", 3)
        telegram_id = int(raw_id)
    except (ValueError, TypeError):
        await callback.answer("Amal yoki ID noto‘g‘ri.", show_alert=True)
        return
    target = await db.fetchone("SELECT role,active FROM admins WHERE telegram_id=?", (telegram_id,))
    if telegram_id < 1 or action not in {"activate", "deactivate"} or not target or str(target["role"]) in {"ceo", "owner"} or telegram_id in {config.ceo_owner_id, config.owner_telegram_id}:
        await callback.answer("Administratorni yangilab bo‘lmadi.", show_alert=True)
        return
    if action == "deactivate":
        changed = await db.set_telegram_admin_active(telegram_id, False)
        if not changed:
            await callback.answer("Administrator topilmadi.", show_alert=True)
            return
        status_text = "vaqtincha bloklandi"
    else:
        linked = await db.web_admin_by_telegram_id(telegram_id)
        if not linked:
            await callback.answer("Avval web-admin panelida ushbu ID uchun parol hisobini yarating.", show_alert=True)
            return
        changed = await db.set_web_admin_active(str(linked["username"]), True)
        if not changed:
            await callback.answer("Web-admin hisobini faollashtirib bo‘lmadi.", show_alert=True)
            return
        status_text = "qayta faollashtirish bosqichiga o‘tdi; yangi parol bilan kirish talab qilinadi"
    await sync_admin_commands(callback.bot, telegram_id, None)
    await db.write_admin_audit(
        str(callback.from_user.id),
        "telegram_admin_deactivated" if action == "deactivate" else "telegram_admin_reactivation_started",
        entity_type="telegram_admin", entity_id=telegram_id,
    )
    await callback.answer("✅ Amal bajarildi.")
    await _edit_or_send_callback_text(
        callback,
        f"✅ Admin <code>{telegram_id}</code> {status_text}.",
        reply_markup=admin_panel(),
    )


@router.callback_query(F.data.startswith("admadmin:invite:"))
async def admin_invite_reissue_prompt(callback: CallbackQuery, db: Database):
    if not await _cb_admin(callback, db, ("ceo",)):
        return
    if not _is_private_callback(callback):
        await callback.answer("Taklifni boshqarish faqat shaxsiy chatda ishlaydi.", show_alert=True)
        return
    try:
        telegram_id = int(callback.data.rsplit(":", 1)[1])
    except (ValueError, TypeError, IndexError):
        await callback.answer("Telegram ID noto‘g‘ri.", show_alert=True)
        return
    target = await db.fetchone("SELECT role,active,bot_invite_pending FROM admins WHERE telegram_id=?", (telegram_id,))
    if (not target or str(target["role"]).strip().casefold() in {"ceo", "owner"}
            or int(target["active"] or 0) or int(target["bot_invite_pending"] or 0)):
        await callback.answer("Bu hisobga bot taklifini qayta berib bo‘lmaydi.", show_alert=True)
        return
    await callback.answer()
    await _edit_or_send_callback_text(
        callback,
        f"✉️ <b>Bot taklifini qayta yoqish</b>\n\nTelegram ID: <code>{telegram_id}</code>\n\nTasdiqlansa, oldingi Website Admin sessiyalari bekor qilinadi. Foydalanuvchi botni o‘zi ochib <code>/start</code> yuborishi kerak. Website Admin kirishi alohida qoladi.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Taklifni qayta yoqish", callback_data=f"admadmin:invite-confirm:{telegram_id}")],
            [InlineKeyboardButton(text="Bekor qilish", callback_data="adm:admins")],
        ]),
    )


@router.callback_query(F.data.startswith("admadmin:invite-confirm:"))
async def admin_invite_reissued(callback: CallbackQuery, db: Database):
    if not await _cb_admin(callback, db, ("ceo",)):
        return
    if not _is_private_callback(callback):
        await callback.answer("Taklifni qayta yoqish faqat shaxsiy chatda ishlaydi.", show_alert=True)
        return
    try:
        telegram_id = int(callback.data.rsplit(":", 1)[1])
        role = await db.reissue_telegram_admin_invitation(telegram_id, callback.from_user.id)
    except (ValueError, TypeError, IndexError) as exc:
        await callback.answer(str(exc)[:180], show_alert=True)
        return
    await sync_admin_commands(callback.bot, telegram_id, None)
    await callback.answer("Taklif qayta yoqildi.")
    await _edit_or_send_callback_text(
        callback,
        f"✅ <code>{telegram_id}</code> uchun bot taklifi qayta yoqildi. Foydalanuvchi <code>/start</code> yuborganda bot huquqi faollashadi. Website Admin hisobi alohida qoladi.",
        reply_markup=admin_panel("ceo"),
    )


@router.callback_query(F.data == "admadmin:add")
async def add_admin_button(callback: CallbackQuery, db: Database, state: FSMContext):
    if not await _cb_admin(callback, db, ("ceo",)):
        return
    if not _is_private_callback(callback):
        await callback.answer("Admin qo‘shish faqat shaxsiy chatda ishlaydi.", show_alert=True)
        return
    await state.clear()
    await state.set_state(AdminAddState.telegram_id)
    await callback.answer()
    await _edit_or_send_callback_text(callback, "➕ <b>Administrator qo‘shish</b>\n\nYangi administratorning Telegram raqamli ID sini yuboring. Bekor qilish: /cancel")


@router.message(AdminAddState.telegram_id)
async def add_admin_read_telegram_id(message: Message, db: Database, state: FSMContext):
    if not await require_role(message, db, ("ceo",)):
        await state.clear()
        return
    if not _is_private_message(message) or not message.text:
        await message.answer("Telegram ID ni oddiy raqamli matn sifatida yuboring.")
        return
    raw = message.text.strip()
    if not raw.isdigit() or not 1 <= len(raw) <= 16 or int(raw) <= 0:
        await message.answer("Telegram ID musbat raqam bo‘lishi kerak. Qayta kiriting.")
        return
    target_id = int(raw)
    if target_id in {config.ceo_owner_id, config.owner_telegram_id}:
        await message.answer("Bu ID himoyalangan OWNER/CEO hisobiga tegishli.")
        return
    if await db.fetchone("SELECT 1 FROM admins WHERE telegram_id=?", (target_id,)):
        await message.answer("Bu Telegram ID adminlar ro‘yxatida allaqachon mavjud.")
        return
    await state.update_data(target_id=target_id, actor_id=message.from_user.id)
    await state.set_state(AdminAddState.role)
    await message.answer(
        f"Telegram ID: <code>{target_id}</code>\n\nRolni tanlang:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Katta Admin", callback_data="admadmin:role-choice:senior_admin")],
            [InlineKeyboardButton(text="Kichik Admin", callback_data="admadmin:role-choice:junior_admin")],
            [InlineKeyboardButton(text="Bekor qilish", callback_data="admadmin:add-cancel")],
        ]),
    )


@router.callback_query(F.data.startswith("admadmin:role-choice:"))
async def add_admin_choose_role(callback: CallbackQuery, db: Database, state: FSMContext):
    if not await _cb_admin(callback, db, ("ceo",)):
        return
    if not _is_private_callback(callback) or await state.get_state() != AdminAddState.role.state:
        await callback.answer("Qo‘shish jarayoni eskirgan. Qaytadan boshlang.", show_alert=True)
        return
    role = callback.data.rsplit(":", 1)[-1]
    data = await state.get_data()
    target_id = int(data.get("target_id", 0))
    if role not in {"senior_admin", "junior_admin"} or target_id <= 0:
        await callback.answer("Rol yoki ID noto‘g‘ri.", show_alert=True)
        await state.clear()
        return
    await state.update_data(role=role, actor_id=callback.from_user.id)
    await state.set_state(AdminAddState.confirm)
    label = "Katta Admin" if role == "senior_admin" else "Kichik Admin"
    await callback.answer()
    await _edit_or_send_callback_text(
        callback,
        f"⚠️ <b>Administrator qo‘shishni tasdiqlang</b>\n\nTelegram ID: <code>{target_id}</code>\nRol: <b>{label}</b>\n\nTasdiqlangach taklif kutish holatiga tushadi. Aynan shu Telegram akkaunt <code>/start</code> yuborganda bot huquqi faollashadi. Website Admin kirishi alohida boshqariladi.",
        reply_markup=admin_add_confirmation_keyboard(target_id, role),
    )


@router.message(Command("cancel"))
async def cancel_admin_creation(message: Message, db: Database, state: FSMContext):
    current = await state.get_state()
    admin_states = {AdminAddState.telegram_id.state, AdminAddState.role.state, AdminAddState.confirm.state}
    if current in admin_states:
        if await require_role(message, db, ("ceo",)):
            await state.clear()
            await message.answer("Administrator qo‘shish bekor qilindi.", reply_markup=admin_panel("ceo"))
        return
    resource_states = {
        AddLearningResourceState.title.state, AddLearningResourceState.description.state,
        AddLearningResourceState.content.state, AddLearningResourceState.question.state,
        AddLearningResourceState.options.state, AddLearningResourceState.correct.state,
        AddLearningResourceState.explanation.state, AddLearningResourceState.next_question.state,
    }
    education_states = {
        JoinGroupState.code.state,
        CreateGroupState.name.state, CreateGroupState.course.state, CreateGroupState.schedule.state,
        CreateHomeworkState.group.state, CreateHomeworkState.title.state, CreateHomeworkState.instructions.state,
        SubmitHomeworkState.homework.state, SubmitHomeworkState.answer.state,
        ReviewSubmissionState.grade.state, ReviewSubmissionState.feedback.state,
        CreateAnnouncementState.title_uz.state, CreateAnnouncementState.title_ru.state,
        CreateAnnouncementState.title_en.state, CreateAnnouncementState.body_uz.state,
        CreateAnnouncementState.body_ru.state, CreateAnnouncementState.body_en.state,
    }
    if current in resource_states:
        is_teacher = await db.is_teacher(message.from_user.id)
        is_admin = await require_admin(message, db) if not is_teacher and not _is_owner_id(message.from_user.id) else False
        if _is_owner_id(message.from_user.id) or is_admin or is_teacher:
            await state.clear()
            await message.answer("Ta’lim materiali jarayoni bekor qilindi.")
        return
    if current in education_states:
        await state.clear()
        await message.answer("Joriy ta’lim jarayoni bekor qilindi. /start orqali menyuga qayting.")
        return
    await message.answer("Bekor qilinadigan faol jarayon topilmadi.")


@router.message(Command("add_admin"))
@router.message(Command("addadmin"))
async def add_admin_command(message: Message, db: Database, state: FSMContext):
    if not await require_admin(message, db):
        return
    if not _is_private_message(message):
        await message.answer("Admin ID va tasdiqlash ma’lumotlari faqat shaxsiy chatda yuboriladi.")
        return
    actor_id = message.from_user.id
    actor_role = await db.admin_role(actor_id)
    if actor_role != "ceo" and not _is_owner_id(actor_id):
        await message.answer("⛔ Faqat OWNER yoki CEO yangi admin qo‘sha oladi.")
        return
    parts = (message.text or "").split()
    if len(parts) != 3:
        await message.answer("Format: <code>/add_admin TELEGRAM_ID senior_admin|junior_admin</code>")
        return
    try:
        target_id = int(parts[1])
    except ValueError:
        await message.answer("⛔ Telegram ID faqat raqam bo‘lishi kerak.")
        return
    target_role = parts[2].lower()
    if target_id <= 0 or target_role not in {"senior_admin", "junior_admin"}:
        await message.answer("⛔ ID yoki rol noto‘g‘ri. Rol: senior_admin yoki junior_admin.")
        return
    if target_id in {config.ceo_owner_id, config.owner_telegram_id}:
        await message.answer("⛔ OWNER/CEO hisobining rolini bu buyruq bilan o‘zgartirib bo‘lmaydi.")
        return
    existing_record = await db.fetchone("SELECT role FROM admins WHERE telegram_id=?", (target_id,))
    if existing_record:
        await message.answer("⛔ Bu Telegram ID administratorlar ro‘yxatida allaqachon bor. Mavjud hisobni /admins panelida boshqaring.")
        return
    await state.clear()
    await state.update_data(target_id=target_id, role=target_role, actor_id=actor_id)
    await state.set_state(AdminAddState.confirm)
    await message.answer(
        f"⚠️ <b>Administrator qo‘shishni tasdiqlang</b>\n\nTelegram ID: <code>{target_id}</code>\n"
        f"Rol: <b>{'Katta administrator' if target_role == 'senior_admin' else 'Kichik administrator'}</b>\n\n"
        "Tasdiqlansa, Bot taklifi yaratiladi. Aynan shu Telegram akkaunt botni ochib <code>/start</code> yuborganda Bot admin huquqi faollashadi. Website Admin hisobi alohida yaratiladi.",
        reply_markup=admin_add_confirmation_keyboard(target_id, target_role),
    )


@router.callback_query(F.data.startswith("admadmin:add-confirm:"))
async def add_admin_confirmed(callback: CallbackQuery, db: Database, state: FSMContext):
    if not await _cb_admin(callback, db, ("ceo",)):
        return
    if not _is_private_callback(callback):
        await callback.answer("Admin qo‘shish faqat shaxsiy chatda tasdiqlanadi.", show_alert=True)
        return
    try:
        prefix, command, raw_id, role = callback.data.split(":", 3)
        if prefix != "admadmin" or command != "add-confirm":
            raise ValueError("unexpected callback")
        target_id = int(raw_id)
    except (ValueError, TypeError):
        await callback.answer("Telegram ID yoki rol noto‘g‘ri.", show_alert=True)
        return
    data = await state.get_data()
    if (
        await state.get_state() != AdminAddState.confirm.state
        or int(data.get("target_id", 0)) != target_id
        or data.get("role") != role
        or role not in {"senior_admin", "junior_admin"}
        or target_id < 1
        or target_id in {config.ceo_owner_id, config.owner_telegram_id}
    ):
        await callback.answer("Tasdiqlash oynasi eskirgan. /add_admin buyrug‘ini qaytadan yuboring.", show_alert=True)
        await state.clear()
        return
    if await db.fetchone("SELECT 1 FROM admins WHERE telegram_id=?", (target_id,)):
        await callback.answer("Bu Telegram ID allaqachon ro‘yxatda bor.", show_alert=True)
        await state.clear()
        return
    try:
        await db.create_telegram_admin(target_id, role, callback.from_user.id)
    except ValueError as exc:
        await callback.answer(str(exc)[:180], show_alert=True)
        await state.clear()
        return
    await state.clear()
    await sync_admin_commands(callback.bot, target_id, None)
    await callback.answer("✅ Telegram administratori uchun taklif yaratildi.")
    await _edit_or_send_callback_text(
        callback,
        f"✅ <code>{target_id}</code> uchun administrator taklifi yaratildi. Aynan shu foydalanuvchi botni ochib <code>/start</code> yuborganda bot huquqi faollashadi. Website Admin hisobi alohida yaratiladi; parolni Telegram chatiga yubormang.",
        reply_markup=admin_panel("ceo"),
    )


@router.callback_query(F.data == "admadmin:add-cancel")
async def add_admin_cancelled(callback: CallbackQuery, db: Database, state: FSMContext):
    if not await _cb_admin(callback, db, ("ceo",)):
        return
    if not _is_private_callback(callback):
        await callback.answer("Admin qo‘shishni bekor qilish faqat shaxsiy chatda ishlaydi.", show_alert=True)
        return
    await state.clear()
    await callback.answer("Qo‘shish bekor qilindi.")
    if callback.message:
        await _edit_or_send_callback_text(callback, "Admin qo‘shish bekor qilindi.", reply_markup=admin_panel("ceo"))


@router.message(Command("remove_admin"))
@router.message(Command("removeadmin"))
async def remove_admin_command(message: Message, db: Database):
    if not await require_admin(message, db):
        return
    if not _is_private_message(message):
        await message.answer("Administratorlarni boshqarish faqat shaxsiy chatda ishlaydi.")
        return
    actor_id = message.from_user.id
    actor_role = await db.admin_role(actor_id)
    if actor_role != "ceo" and not _is_owner_id(actor_id):
        await message.answer("⛔ Faqat OWNER yoki CEO adminni bloklashi mumkin.")
        return
    parts = (message.text or "").split()
    if len(parts) != 2:
        await message.answer("Format: <code>/remove_admin TELEGRAM_ID</code>")
        return
    try:
        target_id = int(parts[1])
    except ValueError:
        await message.answer("⛔ Telegram ID faqat raqam bo‘lishi kerak.")
        return
    if target_id <= 0 or target_id == actor_id or target_id in {config.ceo_owner_id, config.owner_telegram_id}:
        await message.answer("⛔ Bu ID ni ushbu buyruq bilan faolsizlantirib bo‘lmaydi.")
        return
    target_record = await db.fetchone("SELECT role FROM admins WHERE telegram_id=?", (target_id,))
    target_role = str(target_record["role"]) if target_record else None
    if target_role is None:
        await message.answer("⛔ Administrator ID topilmadi.")
        return
    if target_role in {"ceo", "owner"}:
        await message.answer("⛔ CEO hisobini o‘chirish mumkin emas.")
        return
    await message.answer(
        f"⚠️ <code>{target_id}</code> administratorni vaqtincha bloklashni tasdiqlang.",
        reply_markup=admin_confirm_keyboard(target_id, action="deactivate"),
    )


@router.message(Command("admins"))
async def admins_command(message: Message, db: Database):
    if not await require_role(message, db, ("ceo",)):
        return
    if not _is_private_message(message):
        await message.answer("Adminlar ro‘yxati faqat shaxsiy chatda ko‘rsatiladi.")
        return
    rows = await db.admins(include_inactive=True)
    role_labels = {"ceo": "CEO", "owner": "CEO", "senior_admin": "Katta admin", "admin": "Katta admin", "junior_admin": "Kichik admin"}
    lines = [
        f"<code>{int(row['telegram_id'])}</code> — {role_labels.get(str(row['role']), escape(str(row['role'])))} · "
        f"{'/start kutilmoqda' if int(row['bot_invite_pending'] or 0) else ('Botda faol' if int(row['active'] or 0) else 'Bloklangan')}"
        for row in rows[:50]
    ]
    more = f"\n… va yana {len(rows) - 50} ta." if len(rows) > 50 else ""
    await message.answer(
        "👥 <b>TELEGRAM ADMINLARI</b>\n\n" + ("\n".join(lines) or "Adminlar yo‘q.") + more,
        reply_markup=admin_panel("ceo"),
    )


# -------------------- Learning resources and teacher-scoped permissions --------------------
RESOURCE_LABELS = {
    "book": "📚 Kitoblar",
    "vocabulary": "📖 Lug‘atlar",
    "movie": "🎬 Kino va videolar",
    "music": "🎵 Musiqa",
    "quiz": "🧪 Testlar",
}


def _resource_category_keyboard(course_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=RESOURCE_LABELS[key], callback_data=f"res:category:{course_id}:{key}")]
        for key in ("book", "vocabulary", "movie", "music", "quiz")
    ] + [[InlineKeyboardButton(text="⬅️ Orqaga", callback_data="adm:resources")]])


async def _can_manage_course(telegram_id: int, db: Database, course_id: int) -> bool:
    role = await db.admin_role(telegram_id)
    if _is_owner_id(telegram_id) or role in {"ceo", "senior_admin"}:
        course = await db.fetchone("SELECT id FROM courses WHERE id=? AND active=1", (course_id,))
        return bool(course)
    return await db.teacher_has_scope(telegram_id, int(course_id))


async def _can_manage_resource_scope(
    telegram_id: int, db: Database, course_id: int, group_id: int | None = None,
) -> bool:
    """Re-check the exact course/group scope on every material FSM step."""
    role = await db.admin_role(int(telegram_id))
    if _is_owner_id(telegram_id) or role in {"ceo", "senior_admin"}:
        course = await db.fetchone("SELECT id FROM courses WHERE id=? AND active=1", (int(course_id),))
        if not course:
            return False
        if group_id is None:
            return True
        group = await db.fetchone(
            "SELECT id FROM education_groups WHERE id=? AND course_id=? AND status='active'",
            (int(group_id), int(course_id)),
        )
        return bool(group)
    return await db.teacher_has_scope(
        int(telegram_id), int(course_id), int(group_id) if group_id is not None else None
    )


async def _can_manage_resource(telegram_id: int, db: Database, resource) -> bool:
    if not resource:
        return False
    return await _can_manage_resource_scope(
        telegram_id, db, int(resource["course_id"]),
        int(resource["group_id"]) if resource["group_id"] is not None else None,
    )


@router.callback_query(F.data == "adm:quizresults")
async def admin_quiz_results(callback: CallbackQuery, db: Database):
    if not await _cb_admin(callback, db, ("ceo", "senior_admin")):
        return
    if not _is_private_callback(callback):
        await callback.answer("Test natijalari faqat shaxsiy chatda ko‘rsatiladi.", show_alert=True)
        return
    rows = await db.quiz_attempts(limit=20)
    await callback.answer()
    if not rows:
        await callback.message.edit_text("📊 Hozircha test natijalari saqlanmagan.", reply_markup=admin_panel())
        return
    lines = ["📊 <b>SO‘NGGI TEST NATIJALARI</b>", ""]
    for row in rows:
        name = " ".join(part for part in [str(row["first_name"] or ""), str(row["last_name"] or "")] if part).strip() or str(row["username"] or row["telegram_id"])
        lines.append(f"• {escape(name[:50])} — {escape(str(row['quiz_title'])[:60])}: <b>{int(row['score'])}/{int(row['total'])} ({int(row['percent'])}%)</b>")
    await callback.message.edit_text("\n".join(lines)[:3900], reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="↻ Yangilash", callback_data="adm:quizresults")],
        [InlineKeyboardButton(text="⬅️ Admin panel", callback_data="adm:home")],
    ]))


@router.callback_query(F.data == "adm:resources")
async def admin_resources_home(callback: CallbackQuery, db: Database, state: FSMContext):
    if not await _cb_admin(callback, db, ("ceo", "senior_admin")):
        return
    await state.clear()
    await callback.answer()
    counts = {}
    for category in RESOURCE_LABELS:
        rows = await db.learning_resources(category=category, include_inactive=True, limit=200)
        counts[category] = len(rows)
    text = "🎒 <b>O‘QUV MATERIALLARI</b>\n\n"
    text += "\n".join(f"{RESOURCE_LABELS[key]}: <b>{counts[key]}</b>" for key in RESOURCE_LABELS)
    text += "\n\nMateriallar yo‘nalish bilan bog‘lanadi. Testda savollar va javoblar botning o‘zida tuziladi."
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Material qo‘shish", callback_data="res:add")],
        [InlineKeyboardButton(text="📋 Materiallar ro‘yxati", callback_data="res:list:all")],
        [InlineKeyboardButton(text="🧪 Testlar", callback_data="res:list:quiz")],
        [InlineKeyboardButton(text="👨‍🏫 Ustozga yo‘nalish biriktirish", callback_data="res:teacher:help")],
        [InlineKeyboardButton(text="⬅️ Admin panel", callback_data="adm:home")],
    ])
    await callback.message.edit_text(text, reply_markup=markup)


@router.callback_query(F.data == "res:teacher:help")
async def teacher_manager_help(callback: CallbackQuery, db: Database):
    if not await _cb_admin(callback, db, ("ceo",)):
        return
    await callback.answer()
    rows = await db.teacher_managers(include_inactive=True)
    text = "👨‍🏫 <b>YO‘NALISHGA BIRIKTIRILGAN USTOZLAR</b>\n\n"
    text += "\n".join(
        f"<code>{int(r['telegram_id'])}</code> · {escape(r['course_name'])} · {'Faol' if r['active'] else 'Faolsiz'}"
        for r in rows
    ) or "Hozircha biriktirilgan ustoz yo‘q."
    text += "\n\nUstoz qo‘shish: <code>/add_teacher_manager TELEGRAM_ID COURSE_ID</code>\n"
    text += "Huquqni bekor qilish: <code>/remove_teacher_manager TELEGRAM_ID</code>\n\n"
    text += "Ustoz faqat biriktirilgan yo‘nalish uchun kitob, lug‘at, kino, musiqa va test qo‘sha oladi."
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📚 Yo‘nalishlar ID’lari", callback_data="res:courseids")],
        [InlineKeyboardButton(text="⬅️ Materiallar", callback_data="adm:resources")],
    ]))


@router.callback_query(F.data == "res:courseids")
async def show_resource_course_ids(callback: CallbackQuery, db: Database):
    if not await _cb_admin(callback, db, ("ceo",)):
        return
    courses = await db.courses()
    text = "📚 <b>FAOL YO‘NALISHLAR</b>\n\n" + "\n".join(
        f"ID <code>{int(c['id'])}</code> — {escape(c['name_uz'])}" for c in courses
    )
    await callback.answer()
    await callback.message.edit_text(text[:3900], reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="res:teacher:help")]
    ]))


@router.callback_query(F.data == "res:add")
async def add_resource_start(callback: CallbackQuery, db: Database, state: FSMContext):
    role = await db.admin_role(callback.from_user.id)
    if role in {"ceo", "senior_admin"} or _is_owner_id(callback.from_user.id):
        courses = await db.courses()
        if not courses:
            await callback.answer("Faol yo‘nalish yo‘q.", show_alert=True)
            return
        rows = [[InlineKeyboardButton(text=f"{c['icon']} {c['name_uz']}", callback_data=f"res:course:{int(c['id'])}")] for c in courses]
        await state.clear()
        await callback.answer()
        await callback.message.edit_text("Qaysi yo‘nalish uchun material qo‘shamiz?", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
        return
    teacher = await db.teacher_manager(callback.from_user.id)
    if not teacher:
        await callback.answer("Ruxsat yo‘q.", show_alert=True)
        return
    await state.clear()
    await callback.answer()
    await callback.message.edit_text(
        f"Yo‘nalish: <b>{escape(teacher['course_name'])}</b>\nMaterial turini tanlang:",
        reply_markup=_resource_category_keyboard(int(teacher['course_id'])),
    )


@router.callback_query(F.data.startswith("res:course:"))
async def resource_course_selected(callback: CallbackQuery, db: Database, state: FSMContext):
    try:
        course_id = int(callback.data.rsplit(":", 1)[1])
    except (ValueError, TypeError):
        await callback.answer("Yo‘nalish ID noto‘g‘ri.", show_alert=True)
        return
    if not await _can_manage_course(callback.from_user.id, db, course_id):
        await callback.answer("Bu yo‘nalish uchun ruxsatingiz yo‘q.", show_alert=True)
        return
    course = await db.fetchone("SELECT name_uz FROM courses WHERE id=?", (course_id,))
    await state.clear()
    await callback.answer()
    await callback.message.edit_text(
        f"Yo‘nalish: <b>{escape(course['name_uz'])}</b>\nMaterial turini tanlang:",
        reply_markup=_resource_category_keyboard(course_id),
    )


@router.callback_query(F.data.startswith("res:category:"))
async def resource_category_selected(callback: CallbackQuery, db: Database, state: FSMContext):
    try:
        _, _, course_id_s, category = callback.data.split(":", 3)
        course_id = int(course_id_s)
    except (ValueError, TypeError):
        await callback.answer("Material turi noto‘g‘ri.", show_alert=True)
        return
    if category not in RESOURCE_LABELS or not await _can_manage_course(callback.from_user.id, db, course_id):
        await callback.answer("Ruxsat yo‘q yoki yo‘nalish faol emas.", show_alert=True)
        return
    await state.clear()
    await state.update_data(course_id=course_id, category=category)
    await state.set_state(AddLearningResourceState.title)
    await callback.answer()
    await callback.message.answer(f"{RESOURCE_LABELS[category]}\n\n1/3 — Material nomini yozing:")


@router.message(AddLearningResourceState.title)
async def resource_title_received(message: Message, state: FSMContext, db: Database):
    data = await state.get_data()
    if not data.get("course_id") or not await _can_manage_resource_scope(
        message.from_user.id, db, int(data["course_id"]),
        int(data["group_id"]) if data.get("group_id") else None,
    ):
        await state.clear()
        await message.answer("⛔ Bu yo‘nalish uchun material qo‘shish huquqingiz yo‘q.")
        return
    value = await _admin_text(message, db, minimum=2, maximum=180, roles=("ceo", "senior_admin")) if await db.admin_role(message.from_user.id) else (message.text.strip() if message.text else "")
    if await db.is_teacher(message.from_user.id):
        if not value or len(value) < 2 or len(value) > 180:
            await message.answer("Material nomi 2–180 belgi bo‘lsin.")
            return
    elif value is None:
        return
    await state.update_data(title=value)
    await state.set_state(AddLearningResourceState.description)
    await message.answer("2/3 — Qisqacha tavsifni yozing yoki <code>-</code> yuboring:")


@router.message(AddLearningResourceState.description)
async def resource_description_received(message: Message, state: FSMContext, db: Database):
    data = await state.get_data()
    if not data.get("course_id") or not await _can_manage_resource_scope(
        message.from_user.id, db, int(data["course_id"]),
        int(data["group_id"]) if data.get("group_id") else None,
    ):
        await state.clear()
        await message.answer("⛔ Ruxsat yo‘q. Jarayon bekor qilindi.")
        return
    if not message.text or len(message.text.strip()) > 1200:
        await message.answer("1 200 belgigacha matn yoki - yuboring.")
        return
    description = "" if message.text.strip() == "-" else message.text.strip()
    await state.update_data(description=description)
    if data.get("category") == "quiz":
        try:
            resource_id = await db.add_learning_resource(
                category="quiz", course_id=int(data["course_id"]), title=str(data["title"]),
                description=description, content="", created_by_telegram_id=message.from_user.id,
                created_by_role="teacher" if await db.is_teacher(message.from_user.id) else str(await db.admin_role(message.from_user.id)),
                active=False, group_id=int(data["group_id"]) if data.get("group_id") else None,
            )
        except ValueError as exc:
            await message.answer(f"❌ {escape(str(exc))}")
            await state.clear()
            return
        await state.update_data(resource_id=resource_id, question_count=0)
        await state.set_state(AddLearningResourceState.question)
        await message.answer("🧪 <b>Test yaratildi (hozircha yashirin).</b>\n\n1-savol matnini yozing:")
        return
    await state.set_state(AddLearningResourceState.content)
    await message.answer(
        "3/3 — Matn, https:// havola yoki fayl yuboring.\n"
        "📚 Kitob uchun PDF hujjat, 🎬 kino uchun video, 🎵 musiqa uchun audio fayl yuborishingiz mumkin."
    )


@router.message(AddLearningResourceState.content)
async def resource_content_received(message: Message, state: FSMContext, db: Database):
    data = await state.get_data()
    if not data.get("course_id") or not await _can_manage_resource_scope(
        message.from_user.id, db, int(data["course_id"]),
        int(data["group_id"]) if data.get("group_id") else None,
    ):
        await state.clear()
        await message.answer("⛔ Ruxsat yo‘q. Jarayon bekor qilindi.")
        return
    content = ""
    file_id = ""
    media_type = "text"
    if message.video:
        file_id, media_type = message.video.file_id, "video"
    elif message.audio:
        file_id, media_type = message.audio.file_id, "audio"
    elif message.document:
        file_id, media_type = message.document.file_id, "document"
    elif message.photo:
        file_id, media_type = message.photo[-1].file_id, "photo"
    elif message.text:
        content = message.text.strip()
        media_type = "url" if content.lower().startswith(("https://", "http://")) else "text"
    else:
        await message.answer("Matn, havola, video, audio, rasm yoki hujjat yuboring.")
        return
    try:
        resource_id = await db.add_learning_resource(
            category=str(data["category"]), course_id=int(data["course_id"]), title=str(data["title"]),
            description=str(data.get("description", "")), content=content, media_type=media_type,
            telegram_file_id=file_id, created_by_telegram_id=message.from_user.id,
            created_by_role="teacher" if await db.is_teacher(message.from_user.id) else str(await db.admin_role(message.from_user.id)),
            group_id=int(data["group_id"]) if data.get("group_id") else None,
        )
        await db.write_admin_audit(str(message.from_user.id), "learning_resource_created", entity_type="learning_resource",
                                   entity_id=resource_id, details=f"category={data['category']}; course_id={data['course_id']}")
    except ValueError as exc:
        await message.answer(f"❌ {escape(str(exc))}")
        return
    await state.clear()
    await message.answer(f"✅ Material saqlandi. ID: <code>{resource_id}</code>\nYo‘nalish: <b>{escape(str(data['course_id']))}</b>")


@router.message(AddLearningResourceState.question)
async def quiz_question_received(message: Message, state: FSMContext, db: Database):
    data = await state.get_data()
    if not data.get("resource_id") or not await _can_manage_resource_scope(
        message.from_user.id, db, int(data.get("course_id", 0)),
        int(data["group_id"]) if data.get("group_id") else None,
    ):
        await state.clear()
        await message.answer("⛔ Ruxsat yo‘q. Test yaratish bekor qilindi.")
        return
    value = message.text.strip() if message.text else ""
    if not 3 <= len(value) <= 700:
        await message.answer("Savol 3–700 belgi bo‘lsin.")
        return
    await state.update_data(question_text=value)
    await state.set_state(AddLearningResourceState.options)
    await message.answer("Variantlarni <code>|</code> bilan ajrating. Masalan:\n<code>Toshkent | Samarqand | Buxoro | Xiva</code>\n2–6 ta variant:")


@router.message(AddLearningResourceState.options)
async def quiz_options_received(message: Message, state: FSMContext, db: Database):
    data = await state.get_data()
    if not await _can_manage_resource_scope(
        message.from_user.id, db, int(data.get("course_id", 0)),
        int(data["group_id"]) if data.get("group_id") else None,
    ):
        await state.clear()
        await message.answer("⛔ Ruxsat bekor qilingan. Test yaratish to‘xtatildi.")
        return
    value = message.text or ""
    options = [option.strip() for option in value.split("|")]
    if not 2 <= len(options) <= 6 or any(not option or len(option) > 180 for option in options):
        await message.answer("2–6 ta bo‘sh bo‘lmagan variantni | bilan ajrating. Har biri 180 belgidan oshmasin.")
        return
    await state.update_data(options=options)
    await state.set_state(AddLearningResourceState.correct)
    await message.answer(f"To‘g‘ri javob variantining raqamini kiriting (1–{len(options)}):")


@router.message(AddLearningResourceState.correct)
async def quiz_correct_received(message: Message, state: FSMContext, db: Database):
    data = await state.get_data()
    if not await _can_manage_resource_scope(
        message.from_user.id, db, int(data.get("course_id", 0)),
        int(data["group_id"]) if data.get("group_id") else None,
    ):
        await state.clear()
        await message.answer("⛔ Ruxsat bekor qilingan. Test yaratish to‘xtatildi.")
        return
    try:
        correct = int((message.text or "").strip())
    except ValueError:
        await message.answer("Raqam kiriting.")
        return
    if not 1 <= correct <= len(data.get("options", [])):
        await message.answer(f"1 dan {len(data.get('options', []))} gacha raqam kiriting.")
        return
    await state.update_data(correct_index=correct - 1)
    await state.set_state(AddLearningResourceState.explanation)
    await message.answer("Izoh yozing yoki <code>-</code> yuboring:")


@router.message(AddLearningResourceState.explanation)
async def quiz_explanation_received(message: Message, state: FSMContext, db: Database):
    data = await state.get_data()
    if not await _can_manage_resource_scope(
        message.from_user.id, db, int(data.get("course_id", 0)),
        int(data["group_id"]) if data.get("group_id") else None,
    ):
        await state.clear()
        await message.answer("⛔ Ruxsat yo‘q. Jarayon bekor qilindi.")
        return
    if not message.text or len(message.text.strip()) > 700:
        await message.answer("700 belgigacha matn yoki - yuboring.")
        return
    explanation = "" if message.text.strip() == "-" else message.text.strip()
    try:
        await db.add_quiz_question(int(data["resource_id"]), str(data["question_text"]),
                                   list(data["options"]), int(data["correct_index"]), explanation)
    except ValueError as exc:
        await message.answer(f"❌ {escape(str(exc))}")
        return
    questions = await db.quiz_questions(int(data["resource_id"]))
    await state.update_data(question_count=len(questions))
    await state.set_state(AddLearningResourceState.next_question)
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Keyingi savol", callback_data=f"resquiz:more:{int(data['resource_id'])}")],
        [InlineKeyboardButton(text="✅ Testni nashr qilish", callback_data=f"resquiz:publish:{int(data['resource_id'])}")],
    ])
    await message.answer(f"✅ {len(questions)}-savol saqlandi. Yana savol qo‘shing yoki testni nashr qiling.", reply_markup=markup)


@router.callback_query(F.data.startswith("resquiz:more:"))
async def quiz_add_more(callback: CallbackQuery, state: FSMContext, db: Database):
    try:
        resource_id = int(callback.data.rsplit(":", 1)[1])
    except ValueError:
        await callback.answer("Test ID noto‘g‘ri.", show_alert=True)
        return
    data = await state.get_data()
    resource = await db.learning_resource(resource_id, active_only=False)
    if not resource or int(data.get("resource_id", 0)) != resource_id or not await _can_manage_resource(callback.from_user.id, db, resource):
        await callback.answer("Bu testni tahrirlash huquqingiz yo‘q.", show_alert=True)
        return
    await state.set_state(AddLearningResourceState.question)
    await callback.answer()
    await callback.message.answer(f"{len(await db.quiz_questions(resource_id)) + 1}-savol matnini yozing:")


@router.callback_query(F.data.startswith("resquiz:publish:"))
async def quiz_publish(callback: CallbackQuery, state: FSMContext, db: Database):
    try:
        resource_id = int(callback.data.rsplit(":", 1)[1])
    except ValueError:
        await callback.answer("Test ID noto‘g‘ri.", show_alert=True)
        return
    data = await state.get_data()
    resource = await db.learning_resource(resource_id, active_only=False)
    questions = await db.quiz_questions(resource_id)
    if not resource or int(data.get("resource_id", 0)) != resource_id or not await _can_manage_resource(callback.from_user.id, db, resource):
        await callback.answer("Bu testni nashr qilish huquqingiz yo‘q.", show_alert=True)
        return
    if not questions:
        await callback.answer("Kamida bitta savol qo‘shing.", show_alert=True)
        return
    if str(resource["created_by_role"] or "") == "teacher":
        await db.mark_resource_pending(resource_id, callback.from_user.id)
        await db.write_admin_audit(str(callback.from_user.id), "quiz_submitted_for_moderation", entity_type="learning_resource", entity_id=resource_id,
                                   details=f"questions={len(questions)}; course_id={resource['course_id']}")
        await state.clear()
        await callback.answer("Test moderatsiyaga yuborildi.")
        await callback.message.answer("✅ Test savol va javoblari bilan moderatsiyaga yuborildi. Administrator tasdiqlaganidan so‘ng o‘quvchilarga ko‘rinadi.")
        return
    await db.set_learning_resource_active(resource_id, True)
    await db.write_admin_audit(str(callback.from_user.id), "quiz_published", entity_type="learning_resource", entity_id=resource_id,
                               details=f"questions={len(questions)}; course_id={resource['course_id']}")
    await state.clear()
    await callback.answer("Test nashr qilindi")
    await callback.message.answer(
        f"🎉 <b>Test nashr qilindi!</b>\n{escape(resource['title'])}\nSavollar: {len(questions)}\nID: <code>{resource_id}</code>\n\nGuruhga yuborish: <code>/share_test {resource_id} -1001234567890</code>"
    )


@router.callback_query(F.data.startswith("res:list:"))
async def resource_list(callback: CallbackQuery, db: Database):
    if not await _cb_admin(callback, db, ("ceo", "senior_admin")):
        return
    category = callback.data.rsplit(":", 1)[1]
    if category == "all":
        rows = await db.learning_resources(include_inactive=True, limit=40)
    elif category in RESOURCE_LABELS:
        rows = await db.learning_resources(category=category, include_inactive=True, limit=40)
    else:
        await callback.answer("Filtr noto‘g‘ri.", show_alert=True)
        return
    await callback.answer()
    lines = []
    for row in rows:
        status = "Faol" if row["active"] else "Nofaol"
        question_count = len(await db.quiz_questions(int(row["id"]))) if row["category"] == "quiz" else 0
        suffix = f" · {question_count} savol" if row["category"] == "quiz" else ""
        lines.append(f"<code>{int(row['id'])}</code> · {RESOURCE_LABELS[row['category']]} · <b>{escape(row['title'])}</b> · {escape(row['course_name'])} · {status}{suffix}")
    markup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Materiallar", callback_data="adm:resources")]])
    await callback.message.edit_text("📋 <b>MATERIALLAR RO‘YXATI</b>\n\n" + ("\n".join(lines) or "Material topilmadi."), reply_markup=markup)


@router.callback_query(F.data == "teacher:panel")
async def teacher_panel(callback: CallbackQuery, db: Database, state: FSMContext):
    assignments = await db.teacher_assignments(callback.from_user.id)
    if not assignments:
        await callback.answer("Sizga ustoz paneli biriktirilmagan.", show_alert=True)
        return
    await state.clear()
    await callback.answer()
    lines = ["👨‍🏫 <b>USTOZ PANELI</b>", "", "Sizga biriktirilgan fan va guruhlar:"]
    rows = []
    for item in assignments[:30]:
        scope = f" · {escape(item['group_name'])}" if item['group_name'] else " · barcha biriktirilgan guruhlar"
        lines.append(f"• <b>{escape(item['course_name'])}</b>{scope}")
        rows.append([InlineKeyboardButton(text=f"📘 {str(item['course_name'])[:45]}", callback_data=f"edu:teacher:course:{int(item['course_id'])}")])
    rows.extend([
        [InlineKeyboardButton(text="📝 Uy vazifalari", callback_data="edu:teacher:homework")],
        [InlineKeyboardButton(text="📅 Davomat", callback_data="edu:teacher:attendance")],
        [InlineKeyboardButton(text="📚 Materiallar", callback_data="edu:teacher:materials")],
        [InlineKeyboardButton(text="➕ Material yuklash", callback_data="edu:teacher:upload-material")],
        [InlineKeyboardButton(text="🏠 Bosh sahifa", callback_data="nav:home")],
    ])
    await callback.message.edit_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data == "teacher:resources:add")
async def teacher_add_resource(callback: CallbackQuery, db: Database, state: FSMContext):
    teacher = await db.teacher_manager(callback.from_user.id)
    if not teacher:
        await callback.answer("Ruxsat yo‘q.", show_alert=True)
        return
    await state.clear()
    await callback.answer()
    await callback.message.edit_text(
        f"Yo‘nalish: <b>{escape(teacher['course_name'])}</b>\nMaterial turini tanlang:",
        reply_markup=_resource_category_keyboard(int(teacher['course_id'])),
    )


@router.callback_query(F.data == "teacher:resources:list")
async def teacher_list_resources(callback: CallbackQuery, db: Database):
    teacher = await db.teacher_manager(callback.from_user.id)
    if not teacher:
        await callback.answer("Ruxsat yo‘q.", show_alert=True)
        return
    rows = await db.learning_resources(course_id=int(teacher["course_id"]), include_inactive=True, limit=40)
    lines = [f"<code>{int(r['id'])}</code> · {RESOURCE_LABELS[r['category']]} · <b>{escape(r['title'])}</b> · {'Faol' if r['active'] else 'Nofaol'}" for r in rows]
    await callback.answer()
    await callback.message.edit_text(
        f"📋 <b>{escape(teacher['course_name'])} materiallari</b>\n\n" + ("\n".join(lines) or "Material topilmadi."),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Ustoz paneli", callback_data="teacher:panel")]])
    )


@router.message(Command("add_teacher_manager"))
async def add_teacher_manager_command(message: Message, db: Database):
    if not await require_role(message, db, ("ceo",)):
        return
    parts = (message.text or "").split()
    if len(parts) != 3:
        await message.answer("Format: <code>/add_teacher_manager TELEGRAM_ID COURSE_ID</code>")
        return
    try:
        telegram_id, course_id = int(parts[1]), int(parts[2])
        if telegram_id <= 0 or telegram_id in {config.ceo_owner_id, config.owner_telegram_id}:
            raise ValueError("Telegram ID noto‘g‘ri.")
        await db.add_teacher_manager(telegram_id, course_id, message.from_user.id)
    except ValueError as exc:
        await message.answer(f"❌ {escape(str(exc))}")
        return
    await db.write_admin_audit(str(message.from_user.id), "teacher_manager_added", entity_type="teacher_manager", entity_id=telegram_id,
                               details=f"course_id={course_id}")
    await sync_teacher_commands(message.bot, telegram_id)
    await message.answer(
        f"✅ <code>{telegram_id}</code> ustoz sifatida faqat <code>{course_id}</code>-yo‘nalishga biriktirildi.\n"
        "Ustoz STARTUM botini ochib /start bossa, bosh sahifada Ustoz paneli chiqadi."
    )


@router.message(Command("remove_teacher_manager"))
async def remove_teacher_manager_command(message: Message, db: Database):
    if not await require_role(message, db, ("ceo",)):
        return
    parts = (message.text or "").split()
    if len(parts) != 2:
        await message.answer("Format: <code>/remove_teacher_manager TELEGRAM_ID</code>")
        return
    try:
        telegram_id = int(parts[1])
    except ValueError:
        await message.answer("Telegram ID raqam bo‘lishi kerak.")
        return
    if not await db.remove_teacher_manager(telegram_id):
        await message.answer("Faol ustoz biriktirmasi topilmadi.")
        return
    await db.write_admin_audit(str(message.from_user.id), "teacher_manager_removed", entity_type="teacher_manager", entity_id=telegram_id)
    await sync_admin_commands(message.bot, telegram_id, await db.admin_role(telegram_id))
    await message.answer(f"✅ <code>{telegram_id}</code> ustozning material boshqarish huquqi bekor qilindi.")


@router.message(Command("share_test"))
async def share_test_command(message: Message, db: Database):
    role = await db.admin_role(message.from_user.id)
    teacher = await db.teacher_manager(message.from_user.id)
    if role not in {"ceo", "senior_admin"} and not teacher:
        await message.answer("⛔ Test ulashish huquqingiz yo‘q.")
        return
    parts = (message.text or "").split()
    if len(parts) != 3:
        await message.answer("Format: <code>/share_test TEST_ID -1001234567890</code>")
        return
    try:
        resource_id, chat_id = int(parts[1]), int(parts[2])
    except ValueError:
        await message.answer("Test ID va guruh chat ID raqam bo‘lishi kerak.")
        return
    if chat_id >= 0:
        await message.answer("Guruh chat ID odatda manfiy son bo‘ladi. Botni guruhga qo‘shib, ID’ni tekshiring.")
        return
    resource = await db.learning_resource(resource_id, active_only=True)
    if not resource or resource["category"] != "quiz":
        await message.answer("Faol test topilmadi.")
        return
    if role not in {"ceo", "senior_admin"} and (not teacher or int(teacher["course_id"]) != int(resource["course_id"])):
        await message.answer("⛔ Ustoz faqat o‘z yo‘nalishining testini ulasha oladi.")
        return
    questions = await db.quiz_questions(resource_id)
    if not questions:
        await message.answer("Testda savollar yo‘q. Kamida bitta savol qo‘shib, qayta nashr qiling.")
        return
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    caption = (
        f"🧪 <b>STARTUM TESTI</b>\n\n<b>{escape(resource['title'])}</b>\n"
        f"📚 Yo‘nalish: {escape(resource['course_name'])}\n"
        f"❓ Savollar: {len(questions)}\n\n{escape(resource['description'] or 'Bilimingizni sinab ko‘ring!')}"
    )
    try:
        bot_info = await message.bot.get_me()
        bot_username = getattr(bot_info, "username", None)
        if not bot_username:
            await message.answer("⛔ Bot username aniqlanmadi. Telegram bot sozlamalarini tekshiring.")
            return
        private_test_url = f"https://t.me/{bot_username}?start=quiz_{resource_id}"
        await message.bot.send_message(
            chat_id, caption,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="🧪 Testni shaxsiy chatda boshlash", url=private_test_url)
            ]]),
        )
    except Exception as exc:
        await message.answer(f"Guruhga yuborib bo‘lmadi ({type(exc).__name__}). Bot guruhda ekanini va xabar yuborish huquqini tekshiring.")
        return
    await db.write_admin_audit(str(message.from_user.id), "quiz_shared_to_group", entity_type="learning_resource", entity_id=resource_id,
                               details=f"chat_id={chat_id}")
    await message.answer("✅ Test guruhga yuborildi. Guruh a’zolari tugma orqali testni boshlashi mumkin.")


@router.message(Command("quiz_results"))
async def quiz_results_command(message: Message, db: Database):
    """Show persisted quiz results to admins or to a teacher for their assigned course only."""
    if not message.from_user:
        return
    role = await db.admin_role(message.from_user.id)
    teacher = await db.teacher_manager(message.from_user.id)
    if role not in {"ceo", "senior_admin"} and not teacher:
        await message.answer("⛔ Test natijalarini ko‘rish huquqingiz yo‘q.")
        return
    parts = (message.text or "").split()
    if len(parts) > 2:
        await message.answer("Format: <code>/quiz_results [TEST_ID]</code>")
        return
    resource_id = None
    if len(parts) == 2:
        try:
            resource_id = int(parts[1])
            if resource_id < 1:
                raise ValueError
        except ValueError:
            await message.answer("Test ID musbat raqam bo‘lishi kerak.")
            return
    course_id = int(teacher["course_id"]) if teacher and role not in {"ceo", "senior_admin"} else None
    if resource_id is not None:
        resource = await db.learning_resource(resource_id, active_only=False)
        if not resource or resource["category"] != "quiz":
            await message.answer("Test topilmadi.")
            return
        if course_id is not None and int(resource["course_id"]) != course_id:
            await message.answer("⛔ Bu test sizga biriktirilgan yo‘nalishga tegishli emas.")
            return
    rows = await db.quiz_attempts(limit=25, course_id=course_id, resource_id=resource_id)
    if not rows:
        await message.answer("📊 Hozircha saqlangan test natijalari yo‘q.")
        return
    lines = ["📊 <b>TEST NATIJALARI</b>", ""]
    for row in rows:
        name = " ".join(part for part in [str(row["first_name"] or ""), str(row["last_name"] or "")] if part).strip() or str(row["username"] or row["telegram_id"])
        lines.append(
            f"• <b>{escape(name[:60])}</b> — {escape(str(row['quiz_title'])[:70])}: "
            f"<b>{int(row['score'])}/{int(row['total'])} ({int(row['percent'])}%)</b> · "
            f"{escape(str(row['completed_at'])[:16].replace('T', ' '))}"
        )
    await message.answer("\n".join(lines)[:3900])
