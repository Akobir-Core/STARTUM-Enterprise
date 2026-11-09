from __future__ import annotations

import re
import logging
import hashlib
from datetime import datetime, timezone
from html import escape


from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, FSInputFile

from database.db import Database
from notifications import deliver_pending_notifications
from keyboards.common import back_home, course_keyboard, language_keyboard, main_menu, more_menu
from keyboards.admin import admin_panel
from admin_commands import sync_admin_commands
from states.user import RegistrationState, SearchState, SupportState, QuizState

router = Router()
logger = logging.getLogger(__name__)
ASSET_DIR = __import__("pathlib").Path(__file__).resolve().parents[1] / "assets"


def asset(name: str) -> FSInputFile:
    # Keep legacy handler names working while using the real files present in assets/.
    aliases = {
        "startum-welcome.png": "startum-welcome.jpg",
        "startum-courses.png": "startum-courses.jpg",
    }
    filename = aliases.get(name, name)
    path = (ASSET_DIR / filename).resolve()
    if path.parent != ASSET_DIR.resolve() or not path.is_file():
        raise FileNotFoundError(f"STARTUM bot asset topilmadi: {filename}")
    return FSInputFile(path)


TEXT = {
    "uz": {
        "welcome": "🎓 <b>STARTUM</b>\n\nBilim — kelajak kaliti. Bir markaz, ko‘p yo‘nalish.",
        "courses": "📚 <b>Kurslar</b>\n\nYo‘nalishni tanlang:",
        "subjects": "📘 Asosiy fanlar",
        "special": "🎯 Maxsus dasturlar",
        "back": "⬅️ Orqaga",
        "apply": "📝 <b>Ro‘yxatdan o‘tish</b>\n\nIsm-familiyangizni yozing:",
        "phone": "📱 Telefon raqamingizni kiriting:\nMasalan: +998901234567",
        "level": "🎚 Darajangizni yozing:\nMasalan: Boshlang‘ich, O‘rta, Yuqori yoki Bilmayman",
        "time": "🕒 Qaysi vaqtda o‘qish qulay?",
        "message": "💬 Qo‘shimcha izoh yozing yoki <code>-</code> yuboring.",
        "success": "✅ <b>Arizangiz qabul qilindi.</b>\n\nAriza raqami: <code>#{}</code>\nAdministrator bilan bog‘lanish jarayoni boshlandi.",
        "invalid_phone": "❌ Telefon raqami noto‘g‘ri. +998XXXXXXXXX ko‘rinishida yuboring.",
        "search": "🔎 Kurs, ustoz yoki o‘quv materiali nomini yozing:",
        "no_results": "🔎 Hech narsa topilmadi. Boshqa nom bilan urinib ko‘ring.",
        "search_courses": "📚 <b>Kurslar</b>",
        "search_teachers": "👨‍🏫 <b>Ustozlar</b>",
        "search_materials": "📖 <b>Siz uchun ochiq materiallar</b>",
        "search_open_library": "Kutubxonani ochish",
        "teachers": "👨‍🏫 <b>Ustozlar</b>",
        "no_teachers": "Hozircha ustozlar ma’lumoti qo‘shilmagan.",
        "location": "📍 <b>STARTUM manzili</b>\n\nG‘uzor, Qashqadaryo viloyati",
        "contact": "💬 <b>Aloqa</b>\n\nSavol yoki taklifingizni yozing. U faqat administratorlarga yuboriladi.",
        "faq": "❓ <b>Ko‘p so‘raladigan savollar</b>",
        "about": "ℹ️ <b>STARTUM</b> — turli yo‘nalishlar bo‘yicha ta’lim olish uchun yagona markaz.\n\nFanlar, maxsus tayyorlov dasturlari va maqsadga yo‘naltirilgan o‘quv yo‘nalishlari.",
        "navigator": "🎯 <b>STARTUM Navigator</b>\n\nMaqsadingizga eng mos yo‘nalishni topish uchun qisqa savollar javob bering.",
        "schedule": "📅 <b>Haftalik jadval</b>\n\nAniq jadval administrator tomonidan yangilanadi. Hozircha kurs tanlaganingizdan keyin qulay vaqtni arizada ko‘rsatishingiz mumkin.",
        "language": "🌐 Tilni tanlang:",
        "support_saved": "✅ Xabaringiz administratorga yuborish uchun saqlandi. Murojaat raqami: #{}",
        "applications": "🧾 <b>Mening arizalarim</b>",
        "profile": "👤 <b>STARTUM profilingiz</b>\n\nIsm: {name}\nUsername: {username}\nTelegram ID: <code>{telegram_id}</code>\nTil: {language}\nArizalar soni: {count}\nTestlar: {test_count} · Eng yaxshi natija: {best_score}%\nO‘quv ketma-ketligi: {streak} kun\nRo‘yxatdan o‘tgan: {created_at}",
        "help": "🧭 <b>STARTUM yordam</b>\n\n/start — bosh menyu\n/profile — profilingiz\n/help — yordam\n\nMenyudan kurs tanlash, ariza qoldirish, materiallarni ko‘rish, test ishlash va murojaat yuborish mumkin.",
        "daily": "🎯 <b>Kun vazifasi</b>",
        "daily.none": "🎯 <b>Kun vazifasi</b>\n\nHozircha e’lon qilingan test topilmadi. Yangi testlar O‘quv kutubxonasida paydo bo‘lgach, shu yerdan boshlashingiz mumkin.",
        "daily.start": "🚀 Testni boshlash",
        "daily.ready": "🎯 Kun vazifasi boshlandi. Savollarga javob bering.",
        "menu.more": "☰ <b>Boshqa bo‘limlar</b>\n\nUstozlar, jadval, test natijalari va yordam bo‘limlari.",
    },
    "ru": {
        "welcome": "🎓 <b>STARTUM</b>\n\nЗнания — ключ к будущему. Один центр, много направлений.",
        "courses": "📚 <b>Курсы</b>\n\nВыберите направление:",
        "subjects": "📘 Основные предметы",
        "special": "🎯 Специальные программы",
        "back": "⬅️ Назад",
        "apply": "📝 <b>Заявка</b>\n\nВведите имя и фамилию:",
        "phone": "📱 Введите номер телефона:\nНапример: +998901234567",
        "level": "🎚 Ваш уровень:\nНапример: Начальный, Средний, Высокий или Не знаю",
        "time": "🕒 В какое время вам удобно заниматься?",
        "message": "💬 Добавьте комментарий или отправьте <code>-</code>.",
        "success": "✅ <b>Заявка принята.</b>\n\nНомер заявки: <code>#{}</code>\nМы передали её администраторам.",
        "invalid_phone": "❌ Неверный номер. Используйте формат +998XXXXXXXXX.",
        "search": "🔎 Введите название курса, преподавателя или учебного материала:",
        "no_results": "🔎 Ничего не найдено.",
        "search_courses": "📚 <b>Курсы</b>",
        "search_teachers": "👨‍🏫 <b>Преподаватели</b>",
        "search_materials": "📖 <b>Доступные вам материалы</b>",
        "search_open_library": "Открыть библиотеку",
        "teachers": "👨‍🏫 <b>Преподаватели</b>",
        "no_teachers": "Данные о преподавателях пока не добавлены.",
        "location": "📍 <b>Адрес STARTUM</b>\n\nГузар, Кашкадарьинская область",
        "contact": "💬 <b>Связь</b>\n\nНапишите вопрос или предложение. Оно будет отправлено только администраторам.",
        "faq": "❓ <b>Частые вопросы</b>",
        "about": "ℹ️ <b>STARTUM</b> — единый центр для обучения по разным направлениям.",
        "navigator": "🎯 <b>STARTUM Navigator</b>\n\nОтветьте на несколько вопросов, чтобы найти подходящее направление.",
        "schedule": "📅 <b>Расписание</b>\n\nАктуальное расписание обновляется администратором.",
        "language": "🌐 Выберите язык:",
        "support_saved": "✅ Сообщение сохранено. Номер обращения: #{}",
        "applications": "🧾 <b>Мои заявки</b>",
        "profile": "👤 <b>Ваш профиль STARTUM</b>\n\nИмя: {name}\nUsername: {username}\nTelegram ID: <code>{telegram_id}</code>\nЯзык: {language}\nЗаявок: {count}\nТестов: {test_count} · Лучший результат: {best_score}%\nУчебная серия: {streak} дн.\nРегистрация: {created_at}",
        "help": "🧭 <b>Помощь STARTUM</b>\n\n/start — главное меню\n/profile — ваш профиль\n/help — помощь\n\nВ меню можно выбрать курс, отправить заявку, открыть материалы, пройти тест и связаться с центром.",
        "daily": "🎯 <b>Задание дня</b>",
        "daily.none": "🎯 <b>Задание дня</b>\n\nОпубликованных тестов пока нет. Когда тест появится в учебной библиотеке, его можно будет открыть здесь.",
        "daily.start": "🚀 Начать тест",
        "daily.ready": "🎯 Задание дня началось. Ответьте на вопросы.",
        "menu.more": "☰ <b>Другие разделы</b>\n\nПреподаватели, расписание, результаты тестов и помощь.",
    },
    "en": {
        "welcome": "🎓 <b>STARTUM</b>\n\nKnowledge is the key to the future. One center, many directions.",
        "courses": "📚 <b>Courses</b>\n\nChoose a direction:",
        "subjects": "📘 Main Subjects",
        "special": "🎯 Special Programs",
        "back": "⬅️ Back",
        "apply": "📝 <b>Application</b>\n\nEnter your full name:",
        "phone": "📱 Enter your phone number:\nExample: +998901234567",
        "level": "🎚 Your level:\nFor example: Beginner, Intermediate, Advanced or Not sure",
        "time": "🕒 What study time is convenient for you?",
        "message": "💬 Add a note or send <code>-</code>.",
        "success": "✅ <b>Application received.</b>\n\nApplication ID: <code>#{}</code>\nIt has been routed to administrators.",
        "invalid_phone": "❌ Invalid phone. Use +998XXXXXXXXX format.",
        "search": "🔎 Enter a course, teacher or learning material name:",
        "no_results": "🔎 Nothing found. Try another name.",
        "search_courses": "📚 <b>Courses</b>",
        "search_teachers": "👨‍🏫 <b>Teachers</b>",
        "search_materials": "📖 <b>Materials available to you</b>",
        "search_open_library": "Open library",
        "teachers": "👨‍🏫 <b>Teachers</b>",
        "no_teachers": "Teacher information has not been added yet.",
        "location": "📍 <b>STARTUM Location</b>\n\nGuzar, Qashqadaryo Region",
        "contact": "💬 <b>Contact</b>\n\nWrite a question or suggestion. It will be sent only to administrators.",
        "faq": "❓ <b>Frequently Asked Questions</b>",
        "about": "ℹ️ <b>STARTUM</b> is one center for learning across multiple directions.",
        "navigator": "🎯 <b>STARTUM Navigator</b>\n\nAnswer a few questions to find the most suitable direction.",
        "schedule": "📅 <b>Schedule</b>\n\nThe current schedule is managed by administrators.",
        "language": "🌐 Choose a language:",
        "support_saved": "✅ Message saved. Ticket ID: #{}",
        "applications": "🧾 <b>My applications</b>",
        "profile": "👤 <b>Your STARTUM profile</b>\n\nName: {name}\nUsername: {username}\nTelegram ID: <code>{telegram_id}</code>\nLanguage: {language}\nApplications: {count}\nTests completed: {test_count} · Best score: {best_score}%\nLearning streak: {streak} days\nJoined: {created_at}",
        "help": "🧭 <b>STARTUM help</b>\n\n/start — main menu\n/profile — your profile\n/help — help\n\nUse the menu to explore courses, apply, open learning materials, take quizzes or contact the centre.",
        "daily": "🎯 <b>Daily challenge</b>",
        "daily.none": "🎯 <b>Daily challenge</b>\n\nThere are no published quizzes yet. Once a quiz is added to the learning library, you can start it here.",
        "daily.start": "🚀 Start quiz",
        "daily.ready": "🎯 Your daily challenge has started. Answer the questions.",
        "menu.more": "☰ <b>More sections</b>\n\nTeachers, schedule, test results and help.",
    },
}


def tr(lang: str, key: str) -> str:
    return TEXT.get(lang, TEXT["uz"]).get(key, key)


def lang_of(row) -> str:
    return row["language"] if row and row["language"] in TEXT else "uz"


async def edit_message(callback: CallbackQuery, text: str, reply_markup=None) -> None:
    if callback.message and callback.message.photo:
        await callback.message.edit_caption(caption=text, reply_markup=reply_markup)
    else:
        await callback.message.edit_text(text, reply_markup=reply_markup)


async def show_home(message: Message, db: Database) -> None:
    row, _ = await db.ensure_user(message.from_user)
    lang = lang_of(row)
    photo = asset("startum-welcome.png")
    markup = main_menu(lang, teacher=bool(await db.teacher_manager(message.from_user.id)))
    await message.answer_photo(photo=photo, caption=tr(lang, "welcome"), reply_markup=markup)


@router.message(CommandStart())
async def start(message: Message, db: Database, state: FSMContext):
    await state.clear()
    args = (message.text or "").split(maxsplit=1)
    payload = args[1].strip() if len(args) > 1 else ""
    first_user_row, _ = await db.ensure_user(message.from_user)
    accepted_admin_role = await db.activate_telegram_admin_invitation(int(message.from_user.id))
    if accepted_admin_role:
        await sync_admin_commands(message.bot, int(message.from_user.id), accepted_admin_role)
        await message.answer(
            "✅ <b>Administrator taklifi qabul qilindi.</b>\n\n"
            "OWNER sizga STARTUM Telegram Bot boshqaruv huquqini berdi. Endi <code>/admin</code> buyrug‘i orqali bot admin panelini ochishingiz mumkin. "
            "Website Admin hisobi bu huquqdan alohida boshqariladi.",
            reply_markup=admin_panel(accepted_admin_role),
        )
        # Do not let the ordinary student welcome flow immediately replace the
        # newly granted administrator menu in the same /start update.
        return
    try:
        language_selected = bool(first_user_row["language_selected"])
    except (KeyError, IndexError):
        language_selected = True
    if not language_selected:
        await state.update_data(pending_start_payload=payload)
        await message.answer(
            "🎓 <b>STARTUM’ga xush kelibsiz!</b>\nDavom etish uchun tilni tanlang.",
            reply_markup=language_keyboard(),
        )
        return
    if payload.startswith("quiz_"):
        try:
            resource_id = int(payload[5:])
        except ValueError:
            await message.answer("Test havolasi noto‘g‘ri. Kutubxonadan testni qayta tanlang.")
            return
        resource = await db.learning_resource(resource_id, active_only=True)
        if not resource or resource["category"] != "quiz":
            await message.answer("Bu test mavjud emas yoki hozir faol emas.")
            return
        questions = await db.quiz_questions(resource_id)
        if not questions:
            await message.answer("Bu testda hali savollar yo‘q.")
            return
        user_row, _ = await db.ensure_user(message.from_user)
        try:
            session = await db.start_or_resume_quiz_session(
                telegram_id=int(message.from_user.id), user_id=int(user_row["id"]),
                resource_id=resource_id, question_total=len(questions),
            )
        except ValueError as exc:
            await message.answer(escape(str(exc)))
            return
        await message.answer(
            f"🚀 <b>{escape(resource['title'])}</b> ochildi. Test shaxsiy chatda bajariladi; "
            "javoblaringiz va natijangiz faqat sizning hisobingizga yoziladi."
        )
        await _send_resumed_quiz(message, state, resource, questions, session)
        try:
            await deliver_pending_notifications(message.bot, db, recipient_id=message.from_user.id, limit=50, retry_exhausted=True)
        except Exception as exc:
            logger.warning("Quiz deep-link bildirishnomalarini qayta yuborish bajarilmadi (%s).", type(exc).__name__)
        return
    if payload == "explore":
        row, _ = await db.ensure_user(message.from_user)
        lang = lang_of(row)
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"📘 {tr(lang,'subjects')}", callback_data="courses:subject")],
            [InlineKeyboardButton(text=f"🎯 {tr(lang,'special')}", callback_data="courses:special")],
            [InlineKeyboardButton(text=tr(lang,"back"), callback_data="nav:home")],
        ])
        await message.answer_photo(photo=asset("startum-courses.png"), caption=tr(lang, "courses"), reply_markup=kb)
        try:
            await deliver_pending_notifications(message.bot, db, recipient_id=message.from_user.id, limit=50, retry_exhausted=True)
        except Exception as exc:
            logger.warning("/start explore bildirishnomalarini qayta yuborish bajarilmadi (%s).", type(exc).__name__)
        return
    if payload == "apply":
        row, _ = await db.ensure_user(message.from_user)
        lang = lang_of(row)
        await state.set_state(RegistrationState.full_name)
        await message.answer(tr(lang, "apply"))
        try:
            await deliver_pending_notifications(message.bot, db, recipient_id=message.from_user.id, limit=50, retry_exhausted=True)
        except Exception as exc:
            logger.warning("/start apply bildirishnomalarini qayta yuborish bajarilmadi (%s).", type(exc).__name__)
        return
    if payload.startswith("apply_"):
        slug = payload[6:].strip()
        course = await db.course_by_slug(slug)
        if course:
            row, _ = await db.ensure_user(message.from_user)
            lang = lang_of(row)
            await state.update_data(course_id=course["id"])
            await state.set_state(RegistrationState.full_name)
            name_key = {"uz":"name_uz","ru":"name_ru","en":"name_en"}[lang]
            await message.answer(f"📝 <b>{escape(course[name_key])}</b>\n\n" + tr(lang, "apply"))
            return
    await show_home(message, db)
    # Once a recipient opens the bot, retry any website form notifications that were not deliverable earlier.
    try:
        await deliver_pending_notifications(message.bot, db, recipient_id=message.from_user.id, limit=50, retry_exhausted=True)
    except Exception as exc:
        logger.warning("/start bildirishnomalarini qayta yuborish bajarilmadi (%s).", type(exc).__name__)


@router.message(Command("profile"))
async def show_profile(message: Message, db: Database):
    row, _ = await db.ensure_user(message.from_user)
    lang = lang_of(row)
    full_name = " ".join(part for part in [row["first_name"], row["last_name"]] if part).strip() or "—"
    language_names = {"uz": "O‘zbekcha", "ru": "Русский", "en": "English"}
    apps_count = await db.user_application_count(int(row["id"]))
    quiz_stats = await db.user_quiz_stats(int(row["id"]))
    streak = await db.user_learning_streak(int(row["id"]))
    created_at = str(row["created_at"] or "—")[:10]
    template = tr(lang, "profile")
    await message.answer(template.format(
        name=escape(full_name),
        username=escape("@" + row["username"] if row["username"] else "—"),
        telegram_id=int(message.from_user.id),
        language=escape(language_names.get(lang, language_names["uz"])),
        count=apps_count,
        test_count=quiz_stats["attempts"],
        best_score=quiz_stats["best_percent"],
        streak=streak,
        created_at=escape(created_at),
    ))


@router.callback_query(F.data == "user:profile")
async def show_profile_callback(callback: CallbackQuery, db: Database):
    row, _ = await db.ensure_user(callback.from_user)
    lang = lang_of(row)
    full_name = " ".join(part for part in [row["first_name"], row["last_name"]] if part).strip() or "—"
    language_names = {"uz": "O‘zbekcha", "ru": "Русский", "en": "English"}
    apps_count = await db.user_application_count(int(row["id"]))
    quiz_stats = await db.user_quiz_stats(int(row["id"]))
    streak = await db.user_learning_streak(int(row["id"]))
    created_at = str(row["created_at"] or "—")[:10]
    template = tr(lang, "profile")
    text = template.format(
        name=escape(full_name),
        username=escape("@" + row["username"] if row["username"] else "—"),
        telegram_id=int(callback.from_user.id),
        language=escape(language_names.get(lang, language_names["uz"])),
        count=apps_count,
        test_count=quiz_stats["attempts"],
        best_score=quiz_stats["best_percent"],
        streak=streak,
        created_at=escape(created_at),
    )
    await callback.answer()
    await edit_message(callback, text, reply_markup=main_menu(lang, teacher=bool(await db.teacher_manager(callback.from_user.id))))


@router.message(Command("help"))
async def help_command(message: Message, db: Database):
    row, _ = await db.ensure_user(message.from_user)
    lang = lang_of(row)
    await message.answer(
        tr(lang, "help"),
        reply_markup=main_menu(lang, teacher=bool(await db.teacher_manager(message.from_user.id))),
    )


@router.callback_query(F.data == "nav:home")
async def home_cb(callback: CallbackQuery, db: Database):
    await callback.answer()
    row, _ = await db.ensure_user(callback.from_user)
    lang = lang_of(row)
    await edit_message(callback, tr(lang, "welcome"), reply_markup=main_menu(lang, teacher=bool(await db.teacher_manager(callback.from_user.id))))


@router.callback_query(F.data == "user:menu:more")
async def more_menu_cb(callback: CallbackQuery, db: Database):
    row, _ = await db.ensure_user(callback.from_user)
    lang = lang_of(row)
    await callback.answer()
    teacher = bool(await db.teacher_manager(callback.from_user.id))
    await edit_message(callback, tr(lang, "menu.more"), reply_markup=more_menu(lang, teacher=teacher))


@router.callback_query(F.data == "user:language")
async def language_cb(callback: CallbackQuery, db: Database):
    row, _ = await db.ensure_user(callback.from_user)
    await callback.answer()
    await edit_message(callback, tr(lang_of(row), "language"), reply_markup=language_keyboard())


@router.callback_query(F.data.startswith("lang:"))
async def lang_change(callback: CallbackQuery, db: Database, state: FSMContext):
    language = callback.data.split(":", 1)[1]
    if language not in {"uz", "ru", "en"}:
        await callback.answer("Unsupported", show_alert=True)
        return
    await db.set_language(callback.from_user.id, language)
    data = await state.get_data()
    pending_payload = data.get("pending_start_payload")
    if pending_payload is not None:
        await state.clear()
        await callback.answer("✅")
        payload = str(pending_payload).strip()
        if payload == "explore":
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=f"📘 {tr(language,'subjects')}", callback_data="courses:subject")],
                [InlineKeyboardButton(text=f"🎯 {tr(language,'special')}", callback_data="courses:special")],
                [InlineKeyboardButton(text=tr(language,"back"), callback_data="nav:home")],
            ])
            await callback.message.answer_photo(photo=asset("startum-courses.png"), caption=tr(language, "courses"), reply_markup=keyboard)
            return
        if payload == "apply":
            await state.set_state(RegistrationState.full_name)
            await callback.message.answer(tr(language, "apply"))
            return
        if payload.startswith("apply_"):
            course = await db.course_by_slug(payload[6:].strip())
            if course:
                await state.update_data(course_id=int(course["id"]))
                await state.set_state(RegistrationState.full_name)
                name_key = {"uz":"name_uz","ru":"name_ru","en":"name_en"}[language]
                await callback.message.answer(f"📝 <b>{escape(course[name_key])}</b>\n\n" + tr(language, "apply"))
                return
        if payload.startswith("quiz_"):
            try:
                resource_id = int(payload[5:])
            except ValueError:
                resource_id = 0
            resource = await db.learning_resource(resource_id, active_only=True) if resource_id else None
            if resource and resource["category"] == "quiz":
                questions = await db.quiz_questions(resource_id)
                if questions:
                    user_row, _ = await db.ensure_user(callback.from_user)
                    try:
                        session = await db.start_or_resume_quiz_session(
                            telegram_id=int(callback.from_user.id), user_id=int(user_row["id"]),
                            resource_id=resource_id, question_total=len(questions),
                        )
                    except ValueError as exc:
                        await callback.message.answer(escape(str(exc)))
                    else:
                        await callback.message.answer(f"🚀 <b>{escape(resource['title'])}</b> ochildi.")
                        await _send_resumed_quiz(callback.message, state, resource, questions, session)
                        return
        await callback.message.answer(tr(language, "welcome"), reply_markup=main_menu(language, teacher=bool(await db.teacher_manager(callback.from_user.id))))
        return
    await callback.answer("✅")
    await edit_message(callback, tr(language, "welcome"), reply_markup=main_menu(language, teacher=bool(await db.teacher_manager(callback.from_user.id))))


@router.callback_query(F.data == "user:courses")
async def courses_cb(callback: CallbackQuery, db: Database):
    row, _ = await db.ensure_user(callback.from_user)
    lang = lang_of(row)
    await callback.answer()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"📘 {tr(lang,'subjects')}", callback_data="courses:subject")],
        [InlineKeyboardButton(text=f"🎯 {tr(lang,'special')}", callback_data="courses:special")],
        [InlineKeyboardButton(text=tr(lang,"back"), callback_data="nav:home")],
    ])
    await callback.message.delete()
    await callback.message.answer_photo(photo=asset("startum-courses.png"), caption=tr(lang, "courses"), reply_markup=kb)


@router.callback_query(F.data.startswith("courses:"))
async def course_list(callback: CallbackQuery, db: Database):
    row, _ = await db.ensure_user(callback.from_user)
    lang = lang_of(row)
    kind = callback.data.split(":", 1)[1]
    if kind not in {"subject", "special"}:
        await callback.answer("Kurs kategoriyasi noto‘g‘ri.", show_alert=True)
        return
    courses = await db.courses(kind)
    await callback.answer()
    await callback.message.delete()
    await callback.message.answer_photo(photo=asset("startum-courses.png"), caption=tr(lang,"courses"), reply_markup=course_keyboard(courses, lang))


@router.callback_query(F.data.startswith("course:"))
async def course_detail(callback: CallbackQuery, db: Database):
    row, _ = await db.ensure_user(callback.from_user)
    lang = lang_of(row)
    try:
        course_id = int(callback.data.split(":", 1)[1])
    except (ValueError, IndexError, TypeError):
        await callback.answer("Kurs ma’lumoti noto‘g‘ri.", show_alert=True)
        return
    course = await db.course(course_id)
    await callback.answer()
    if not course:
        await callback.message.answer("❌ Kurs topilmadi.")
        return
    name_key = {"uz":"name_uz","ru":"name_ru","en":"name_en"}[lang]
    desc_key = {"uz":"description_uz","ru":"description_ru","en":"description_en"}[lang]
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Ariza berish", callback_data=f"applycourse:{course_id}")],
        [InlineKeyboardButton(text=tr(lang,"back"), callback_data=f"courses:{course['kind']}")],
    ])
    await edit_message(callback, f"{course['icon']} <b>{escape(course[name_key])}</b>\n\n{escape(course[desc_key])}", reply_markup=kb)


@router.callback_query(F.data.startswith("applycourse:"))
async def apply_course(callback: CallbackQuery, state: FSMContext, db: Database):
    row, _ = await db.ensure_user(callback.from_user)
    lang = lang_of(row)
    try:
        course_id = int(callback.data.split(":", 1)[1])
    except (ValueError, IndexError, TypeError):
        await callback.answer("Kurs ma’lumoti noto‘g‘ri.", show_alert=True)
        return
    if not await db.course(course_id):
        await callback.answer("Bu kurs hozir faol emas.", show_alert=True)
        return
    await state.clear()
    await state.update_data(course_id=course_id)
    await state.set_state(RegistrationState.full_name)
    await callback.answer()
    await edit_message(callback, tr(lang,"apply"))


@router.callback_query(F.data == "user:apply")
async def apply_start(callback: CallbackQuery, state: FSMContext, db: Database):
    row, _ = await db.ensure_user(callback.from_user)
    lang = lang_of(row)
    await state.clear()
    await state.set_state(RegistrationState.full_name)
    await callback.answer()
    await edit_message(callback, tr(lang,"apply"))


@router.message(RegistrationState.full_name)
async def reg_name(message: Message, state: FSMContext, db: Database):
    if not message.text:
        await message.answer("Iltimos, ism-familiyangizni matn ko‘rinishida yuboring.")
        return
    text = " ".join(message.text.split())
    if len(text) < 2 or len(text) > 120 or any(ord(char) < 32 for char in text):
        await message.answer("❌ Ismni to‘g‘ri kiriting.")
        return
    await state.update_data(full_name=text)
    row, _ = await db.ensure_user(message.from_user)
    lang = lang_of(row)
    await state.set_state(RegistrationState.phone)
    await message.answer(tr(lang,"phone"))


@router.message(RegistrationState.phone)
async def reg_phone(message: Message, state: FSMContext, db: Database):
    row, _ = await db.ensure_user(message.from_user)
    lang = lang_of(row)
    if not message.text:
        await message.answer("Iltimos, telefon raqamini matn ko‘rinishida yuboring.")
        return
    phone = re.sub(r"[\s().-]", "", message.text.strip())
    digits = re.sub(r"\D", "", phone)
    if not re.fullmatch(r"\+?\d{9,15}", phone) or not 9 <= len(digits) <= 15:
        await message.answer(tr(lang,"invalid_phone"))
        return
    if not phone.startswith("+"):
        phone = "+" + phone
    await state.update_data(phone=phone)
    data = await state.get_data()
    if data.get("course_id"):
        await state.set_state(RegistrationState.level)
        await message.answer(tr(lang,"level"))
        return
    await state.set_state(RegistrationState.course)
    courses = await db.courses()
    await message.answer("📚 Kursni tanlang:", reply_markup=course_keyboard(courses, lang, prefix="regcourse"))


@router.callback_query(RegistrationState.course, F.data.startswith("regcourse:"))
async def reg_course(callback: CallbackQuery, state: FSMContext, db: Database):
    row, _ = await db.ensure_user(callback.from_user)
    lang = lang_of(row)
    try:
        course_id = int(callback.data.split(":", 1)[1])
    except (ValueError, IndexError, TypeError):
        await callback.answer("Kurs ma’lumoti noto‘g‘ri.", show_alert=True)
        return
    if not await db.course(course_id):
        await callback.answer("Bu kurs hozir faol emas.", show_alert=True)
        return
    await state.update_data(course_id=course_id)
    await state.set_state(RegistrationState.level)
    await callback.answer()
    await edit_message(callback, tr(lang,"level"))


@router.message(RegistrationState.level)
async def reg_level(message: Message, state: FSMContext, db: Database):
    if not message.text or not message.text.strip() or len(message.text.strip()) > 60:
        await message.answer("Darajangizni 1–60 belgi oralig‘ida matn bilan yozing.")
        return
    await state.update_data(level=message.text.strip())
    row, _ = await db.ensure_user(message.from_user)
    lang = lang_of(row)
    await state.set_state(RegistrationState.preferred_time)
    await message.answer(tr(lang,"time"))


@router.message(RegistrationState.preferred_time)
async def reg_time(message: Message, state: FSMContext, db: Database):
    if not message.text or not message.text.strip() or len(message.text.strip()) > 120:
        await message.answer("Qulay vaqtni 1–120 belgi oralig‘ida matn bilan yozing.")
        return
    await state.update_data(preferred_time=message.text.strip())
    row, _ = await db.ensure_user(message.from_user)
    lang = lang_of(row)
    await state.set_state(RegistrationState.message)
    await message.answer(tr(lang,"message"))


@router.message(RegistrationState.message)
async def reg_message(message: Message, state: FSMContext, db: Database):
    if not message.text:
        await message.answer("Izohni matn ko‘rinishida yuboring yoki izohsiz davom etish uchun - yuboring.")
        return
    if len(message.text.strip()) > 1000:
        await message.answer("Izoh 1000 belgidan oshmasligi kerak.")
        return
    row, _ = await db.ensure_user(message.from_user)
    lang = lang_of(row)
    data = await state.update_data(message="" if message.text.strip() == "-" else message.text.strip())
    data = await state.get_data()
    if not data.get("course_id"):
        await state.clear()
        await message.answer("❌ Kurs tanlanmagan.")
        return
    user = row
    if not await db.try_consume_rate_limit("bot_apply", str(message.from_user.id), 600, 3):
        await state.clear()
        await message.answer("Juda ko‘p ariza yuborildi. 10 daqiqadan keyin qayta urinib ko‘ring.")
        return
    app_id, creation_status = await db.create_application_if_new(int(user["id"]), data, within_seconds=600)
    if creation_status == "inactive":
        await state.clear()
        await message.answer("Tanlangan kurs hozir faol emas. Kurslar ro‘yxatidan boshqa yo‘nalishni tanlang.")
        return
    if creation_status == "duplicate":
        await state.clear()
        await message.answer(f"Siz bu kursga yaqinda ariza yuborgansiz (#{app_id}). Administrator javobini kuting.")
        return
    if app_id is None:
        await state.clear()
        await message.answer("Arizani saqlashda xatolik yuz berdi. Qayta urinib ko‘ring.")
        return
    application = await db.application(app_id)
    await state.clear()

    await message.answer(tr(lang,"success").format(app_id), reply_markup=main_menu(lang, teacher=bool(await db.teacher_manager(message.from_user.id))))

    application_text = (
        f"📝 <b>YANGI STARTUM ARIZA #{app_id}</b>\n\n"
        f"👤 Ism: <b>{escape(application['full_name'])}</b>\n"
        f"📱 Telefon: <code>{escape(application['phone'])}</code>\n"
        f"📚 Kurs: <b>{escape(application['course_name'])}</b>\n"
        f"🎚 Daraja: {escape(application['level'] or '-') }\n"
        f"🕒 Vaqt: {escape(application['preferred_time'] or '-') }\n"
        f"💬 Izoh: {escape(application['message'] or '-') }\n\n"
        f"🆔 Telegram ID: <code>{application['telegram_id']}</code>\n"
        f"🔗 Username: @{escape(application['username']) if application['username'] else '-'}"
    )
    # Keep notification delivery durable instead of silently dropping failures.
    admin_ids = await db.active_admin_ids()
    await db.enqueue_application_notifications(app_id, application_text, admin_ids, source="bot")
    # The retry worker sends queued notices separately; user-facing registration
    # must not wait for Telegram delivery.


@router.callback_query(F.data == "user:teachers")
async def teachers_cb(callback: CallbackQuery, db: Database):
    row, _ = await db.ensure_user(callback.from_user)
    lang = lang_of(row)
    teachers = await db.teachers()
    await callback.answer()
    if not teachers:
        await edit_message(callback, tr(lang,"teachers")+"\n\n"+tr(lang,"no_teachers"), reply_markup=back_home(lang))
        return
    text = tr(lang,"teachers") + "\n\n"
    for teacher in teachers:
        text += f"👨‍🏫 <b>{escape(teacher['full_name'])}</b>\n📚 {escape(teacher['subject'])}\n⏳ {escape(teacher['experience'] or '-')}\n{escape(teacher['bio'] or '')}\n\n"
    await edit_message(callback, text, reply_markup=back_home(lang))


@router.callback_query(F.data == "user:search")
async def search_start(callback: CallbackQuery, state: FSMContext, db: Database):
    row, _ = await db.ensure_user(callback.from_user)
    lang = lang_of(row)
    await state.set_state(SearchState.query)
    await callback.answer()
    await edit_message(callback, tr(lang,"search"), reply_markup=back_home(lang))


@router.message(SearchState.query)
async def search_run(message: Message, state: FSMContext, db: Database):
    if not message.text:
        row, _ = await db.ensure_user(message.from_user)
        await message.answer(tr(lang_of(row), "search"))
        return
    query = " ".join(message.text.split())[:120]
    if len(query) < 2:
        row, _ = await db.ensure_user(message.from_user)
        await message.answer(tr(lang_of(row), "search"))
        return
    row, _ = await db.ensure_user(message.from_user)
    lang = lang_of(row)
    results = await db.search_student_content(message.from_user.id, query, limit=5)
    await state.clear()
    total = sum(len(results.get(key, [])) for key in ("courses", "teachers", "materials"))
    if not total:
        await message.answer(tr(lang, "no_results"), reply_markup=back_home(lang))
        return

    if results["courses"]:
        heading = tr(lang, "search_courses")
        await message.answer(heading, reply_markup=course_keyboard(results["courses"], lang))
    if results["teachers"]:
        lines = [tr(lang, "search_teachers"), ""]
        for teacher in results["teachers"]:
            lines.append(
                f"👨‍🏫 <b>{escape(str(teacher['full_name']))}</b>\n"
                f"📚 {escape(str(teacher['subject']))}\n"
                f"⏳ {escape(str(teacher['experience'] or '-'))}"
            )
        await message.answer("\n\n".join(lines), reply_markup=back_home(lang))
    if results["materials"]:
        lines = [tr(lang, "search_materials"), ""]
        for material in results["materials"]:
            lines.append(
                f"• <b>{escape(str(material['title']))}</b>\n"
                f"{escape(str(material['course_name'] or ''))} · {escape(str(material['category']))}"
            )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=tr(lang, "search_open_library"), callback_data="edu:student:materials")],
            [InlineKeyboardButton(text=tr(lang, "back"), callback_data="nav:home")],
        ])
        await message.answer("\n\n".join(lines), reply_markup=keyboard)
    await message.answer(f"🔎 {total} {('ta natija' if lang == 'uz' else 'результат(а)' if lang == 'ru' else 'results')}.",
                         reply_markup=back_home(lang))


@router.callback_query(F.data == "user:navigator")
async def navigator(callback: CallbackQuery, db: Database):
    row, _ = await db.ensure_user(callback.from_user)
    lang = lang_of(row)
    await callback.answer()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎯 Maqsadni tanlash", callback_data="navq:goal")],
        [InlineKeyboardButton(text=tr(lang,"back"), callback_data="nav:home")],
    ])
    await callback.message.delete()
    await callback.message.answer_photo(photo=asset("startum-navigator.png"), caption=tr(lang,"navigator")+"\n\n1️⃣ Maqsadni belgilang.\n2️⃣ Fan yoki tilni tanlang.\n3️⃣ Darajangizni ayting.\n4️⃣ Mos kursni ko‘ring.", reply_markup=kb)


@router.callback_query(F.data == "navq:goal")
async def navigator_goal(callback: CallbackQuery, db: Database):
    row, _ = await db.ensure_user(callback.from_user)
    lang = lang_of(row)
    await callback.answer()
    courses = await db.courses("special")
    if not courses:
        await edit_message(callback, tr(lang,"no_results"), reply_markup=back_home(lang))
        return
    await edit_message(callback, "🎯 Maxsus dasturlardan maqsadingizga yaqinini tanlang:", reply_markup=course_keyboard(courses, lang))


@router.callback_query(F.data == "user:schedule")
async def schedule_cb(callback: CallbackQuery, db: Database):
    row, _ = await db.ensure_user(callback.from_user)
    lang = lang_of(row)
    await callback.answer()
    await edit_message(callback, tr(lang,"schedule"), reply_markup=back_home(lang))


FAQS = {
    "uz": [
        ("Kursga qanday yozilaman?", "📚 Kursni tanlang va <b>Ariza berish</b> tugmasini bosing. Ma’lumotlar faqat administratorlarga yuboriladi."),
        ("Arizam kimga boradi?", "🔐 Ariza bazaga saqlanadi va faqat sozlangan administrator/CEO Telegram ID lariga yuboriladi."),
        ("Kurs vaqtini o‘zim tanlay olamanmi?", "🕒 Arizada o‘zingizga qulay vaqtni ko‘rsatishingiz mumkin."),
        ("Telegram username majburiymi?", "✅ Yo‘q. Ariza telefon va ism asosida ham qabul qilinadi. Telegram username bo‘lsa, admin xabarida ko‘rsatiladi."),
    ],
    "ru": [
        ("Как записаться на курс?", "📚 Выберите курс и нажмите <b>Заявка</b>. Данные отправляются только администраторам."),
        ("Кому приходит заявка?", "🔐 Заявка сохраняется в базе и отправляется только настроенным администраторам/CEO."),
        ("Можно указать удобное время?", "🕒 Да, укажите желаемое время в заявке."),
        ("Нужен ли Telegram username?", "✅ Нет. Заявку можно отправить по имени и телефону."),
    ],
    "en": [
        ("How do I enroll?", "📚 Choose a course and press <b>Apply</b>. The data is routed only to administrators."),
        ("Who receives my application?", "🔐 It is stored in the database and sent only to configured admins/CEO."),
        ("Can I choose a preferred time?", "🕒 Yes. Add your preferred time in the application."),
        ("Is a Telegram username required?", "✅ No. Name and phone are enough."),
    ],
}


@router.callback_query(F.data == "user:faq")
async def faq_cb(callback: CallbackQuery, db: Database):
    row, _ = await db.ensure_user(callback.from_user)
    lang = lang_of(row)
    await callback.answer()
    buttons = []
    for i,(q,_) in enumerate(FAQS[lang]):
        buttons.append([InlineKeyboardButton(text=f"{i+1:02d} · {q}", callback_data=f"faq:{i}")])
    buttons.append([InlineKeyboardButton(text=tr(lang,"back"), callback_data="nav:home")])
    await edit_message(callback, tr(lang,"faq"), reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@router.callback_query(F.data.startswith("faq:"))
async def faq_item(callback: CallbackQuery, db: Database):
    row, _ = await db.ensure_user(callback.from_user)
    lang = lang_of(row)
    try:
        index = int(callback.data.split(":", 1)[1])
    except (ValueError, IndexError, TypeError):
        await callback.answer("Savol ma’lumoti noto‘g‘ri.", show_alert=True)
        return
    if not 0 <= index < len(FAQS[lang]):
        await callback.answer("Savol topilmadi.", show_alert=True)
        return
    q,a = FAQS[lang][index]
    await callback.answer()
    await edit_message(callback, f"❓ <b>{escape(q)}</b>\n\n{a}", reply_markup=back_home(lang))


@router.callback_query(F.data == "user:location")
async def location_cb(callback: CallbackQuery, db: Database):
    row, _ = await db.ensure_user(callback.from_user)
    lang = lang_of(row)
    await callback.answer()
    maps = "https://www.google.com/maps/dir/?api=1&destination=38.6188213,66.2506405"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗺 Google Maps", url=maps)],
        [InlineKeyboardButton(text=tr(lang,"back"), callback_data="nav:home")],
    ])
    await edit_message(callback, tr(lang,"location"), reply_markup=kb)


@router.callback_query(F.data == "user:applications")
async def applications_cb(callback: CallbackQuery, db: Database):
    row, _ = await db.ensure_user(callback.from_user)
    lang = lang_of(row)
    rows = await db.user_applications(callback.from_user.id)
    await callback.answer()
    if not rows:
        await edit_message(callback, tr(lang, "applications") + "\n\nHozircha arizangiz yo‘q.", reply_markup=back_home(lang))
        return
    text = tr(lang, "applications") + "\n\n"
    for item in rows:
        text += f"<b>#{item['id']}</b> · {escape(item['course_name'])} · <b>{escape(item['status'])}</b>\n📅 {escape(item['created_at'][:10])}\n\n"
    await edit_message(callback, text, reply_markup=back_home(lang))


@router.callback_query(F.data == "user:about")
async def about_cb(callback: CallbackQuery, db: Database):
    row, _ = await db.ensure_user(callback.from_user)
    lang = lang_of(row)
    await callback.answer()
    await edit_message(callback, tr(lang,"about"), reply_markup=back_home(lang))


@router.callback_query(F.data == "user:contact")
async def contact_start(callback: CallbackQuery, state: FSMContext, db: Database):
    row, _ = await db.ensure_user(callback.from_user)
    lang = lang_of(row)
    await state.set_state(SupportState.topic)
    await callback.answer()
    await edit_message(callback, tr(lang,"contact")+"\n\nMavzu: <code>taklif</code>, <code>savol</code>, <code>muammo</code> yoki <code>boshqa</code> deb yozing.")


@router.message(SupportState.topic)
async def support_topic(message: Message, state: FSMContext, db: Database):
    if not message.text:
        await message.answer("Murojaat mavzusini matn ko‘rinishida yuboring.")
        return
    topic = " ".join(message.text.split())[:50]
    if not topic:
        await message.answer("Murojaat mavzusini kiriting.")
        return
    await state.update_data(topic=topic)
    row, _ = await db.ensure_user(message.from_user)
    lang = lang_of(row)
    await state.set_state(SupportState.message)
    await message.answer("💬 Xabaringizni yozing:")


@router.message(SupportState.message)
async def support_message(message: Message, state: FSMContext, db: Database):
    if not message.text or not message.text.strip():
        await message.answer("Murojaat matnini yuboring.")
        return
    if len(message.text.strip()) > 1000:
        await message.answer("Murojaat 1000 belgidan oshmasligi kerak.")
        return
    if not await db.try_consume_rate_limit("bot_support", str(message.from_user.id), 600, 3):
        await state.clear()
        await message.answer("Murojaatlar soni vaqtincha cheklangan. 10 daqiqadan keyin urinib ko‘ring.")
        return
    data = await state.update_data(message=message.text.strip())
    data = await state.get_data()
    row, _ = await db.ensure_user(message.from_user)
    lang = lang_of(row)
    msg_id = await db.create_message(int(row["id"]), data.get("topic", "boshqa"), data.get("message", ""))
    await state.clear()
    await message.answer(tr(lang,"support_saved").format(msg_id), reply_markup=main_menu(lang, teacher=bool(await db.teacher_manager(message.from_user.id))))

    text = (
        f"💬 <b>YANGI MUROJAAT #{msg_id}</b>\n\n"
        f"👤 {escape(message.from_user.full_name)}\n"
        f"🆔 <code>{message.from_user.id}</code>\n"
        f"📌 Mavzu: {escape(data.get('topic','boshqa'))}\n\n"
        f"{escape(data.get('message',''))}"
    )
    admin_ids = await db.active_admin_ids()
    await db.enqueue_support_notifications(msg_id, text, admin_ids)
    # The background retry worker delivers persisted support notices when Telegram is reachable.


# -------------------- Direction-based learning library and interactive tests --------------------
LIBRARY_CATEGORIES = {
    "book": "📚 Kitoblar",
    "vocabulary": "📖 Lug‘atlar",
    "movie": "🎬 Kino va videolar",
    "music": "🎵 Musiqa",
    "quiz": "🧪 Testlar",
}


def _library_back(callback_data: str = "user:library") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Orqaga", callback_data=callback_data)]])


def _resource_actions(resource_id: int, favorite: bool, back_callback: str) -> InlineKeyboardMarkup:
    favorite_label = "⭐ Sevimlidan olib tashlash" if favorite else "☆ Sevimlilarga qo‘shish"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=favorite_label, callback_data=f"fav:toggle:{resource_id}:{'f' if back_callback == 'user:favorites' else 'l'}")],
        [InlineKeyboardButton(text="⬅️ Orqaga", callback_data=back_callback)],
    ])


async def _render_quiz_question(message: Message, resource, questions: list, index: int) -> None:
    from html import escape
    item = questions[index]
    rows = [[InlineKeyboardButton(
        text=f"{chr(65 + option_index)}. {str(option)[:70]}",
        callback_data=f"quiz:answer:{int(resource['id'])}:{index}:{option_index}",
    )] for option_index, option in enumerate(item["options"])]
    await message.answer(
        f"🧪 <b>{escape(str(resource['title']))}</b>\n"
        f"Savol {index + 1}/{len(questions)}\n\n{escape(str(item['question_text']))}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


def _quiz_submit_keyboard(resource_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Natijani saqlash", callback_data=f"quiz:submit:{resource_id}")],
        [InlineKeyboardButton(text="🎒 Kutubxona", callback_data="user:library")],
    ])


async def _load_quiz_fsm(state: FSMContext, session: dict) -> None:
    await state.set_state(QuizState.answering)
    await state.update_data(
        quiz_resource_id=int(session["resource_id"]),
        quiz_index=int(session["current_index"]),
        quiz_score=int(session["score"]),
        quiz_total=int(session["question_total"]),
        quiz_user_id=int(session["user_id"]),
        quiz_started_at=float(session["started_at_epoch"]),
    )


async def _send_resumed_quiz(message: Message, state: FSMContext, resource, questions: list, session: dict) -> None:
    await _load_quiz_fsm(state, session)
    index = int(session["current_index"])
    if index >= len(questions):
        await message.answer(
            f"✅ <b>{escape(str(resource['title']))}</b> savollari tugadi. Natijani saqlang:",
            reply_markup=_quiz_submit_keyboard(int(resource["id"])),
        )
        return
    await _render_quiz_question(message, resource, questions, index)


async def _complete_quiz_from_callback(callback: CallbackQuery, db: Database, state: FSMContext, resource_id: int) -> None:
    if not callback.message:
        return
    try:
        result = await db.complete_quiz_session(
            telegram_id=int(callback.from_user.id),
            resource_id=resource_id,
            source_chat_id=callback.message.chat.id,
            source_chat_type=getattr(callback.message.chat.type, "value", str(callback.message.chat.type)),
        )
    except Exception as exc:
        logger.exception("Test natijasini saqlashda xato (%s).", type(exc).__name__)
        session = await db.quiz_session(int(callback.from_user.id), resource_id)
        if session and int(session["current_index"]) == int(session["question_total"]):
            await _load_quiz_fsm(state, session)
            await callback.message.answer(
                "⚠️ Natijani hozir saqlab bo‘lmadi. Aloqa tiklangach quyidagi tugmani bosing:",
                reply_markup=_quiz_submit_keyboard(resource_id),
            )
        else:
            await state.clear()
            await callback.message.answer("⚠️ Test natijasi saqlanmadi. Iltimos, testni qaytadan boshlang.")
        return
    if not result:
        await state.clear()
        await callback.message.answer("Bu test allaqachon yakunlangan yoki faol test topilmadi.")
        return
    await state.clear()
    total = result["total"]
    score = result["score"]
    percent = result["percent"]
    duration_seconds = result["duration_seconds"]
    resource = await db.learning_resource(resource_id, active_only=False)
    title = escape(str(resource["title"])) if resource else f"#{resource_id}"
    result_text = (
        f"🏁 <b>TEST YAKUNLANDI</b>\n\n"
        f"👤 {escape(callback.from_user.full_name)}\n"
        f"🧪 {title}\n"
        f"✅ Natija: <b>{score}/{total}</b> ({percent}%)\n"
        f"⏱ Vaqt: {duration_seconds // 60} daqiqa {duration_seconds % 60} soniya\n"
        f"💾 Natija saqlandi.\n\n"
        f"{'Ajoyib natija!' if percent >= 80 else 'Yaxshi urinish! Yana mashq qilib ko‘ring.' if percent >= 50 else 'Materialni qayta ko‘rib, yana urinib ko‘ring.'}"
    )
    await callback.message.answer(result_text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔁 Qayta ishlash", callback_data=f"quiz:start:{resource_id}")],
        [InlineKeyboardButton(text="🎒 Kutubxona", callback_data="user:library")],
    ]))


@router.callback_query(F.data == "user:library")
async def learning_library(callback: CallbackQuery, db: Database):
    await db.ensure_user(callback.from_user)
    courses = await db.courses()
    await callback.answer()
    if not courses:
        await edit_message(callback, "🎒 Hozircha faol yo‘nalishlar mavjud emas.", reply_markup=back_home())
        return
    rows = [[InlineKeyboardButton(text=f"{c['icon']} {c['name_uz']}", callback_data=f"library:course:{int(c['id'])}")] for c in courses]
    rows.append([InlineKeyboardButton(text="🏠 Bosh sahifa", callback_data="nav:home")])
    await edit_message(callback, "🎒 <b>STARTUM O‘QUV KUTUBXONASI</b>\n\nO‘zingiz o‘qiyotgan yo‘nalishni tanlang. Faqat shu yo‘nalishga mos materiallar ko‘rsatiladi:", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data == "user:favorites")
async def user_favorites(callback: CallbackQuery, db: Database):
    user, _ = await db.ensure_user(callback.from_user)
    rows = await db.user_favorites(int(user["id"]), limit=50)
    await callback.answer()
    if not rows:
        await edit_message(callback, "⭐ <b>Sevimli materiallar</b>\n\nHozircha saqlangan material yo‘q. Kutubxonadan material ochib, sevimlilarga qo‘shishingiz mumkin.", reply_markup=_library_back("user:library"))
        return
    keyboard = [[InlineKeyboardButton(text=f"{LIBRARY_CATEGORIES.get(row['category'], '📘')} {str(row['title'])[:55]}", callback_data=f"library:item:{int(row['id'])}")] for row in rows]
    keyboard.append([InlineKeyboardButton(text="🎒 Kutubxona", callback_data="user:library")])
    await edit_message(callback, "⭐ <b>Sevimli materiallar</b>\n\nKerakli materialni tanlang:", reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))


@router.callback_query(F.data == "user:daily")
async def daily_challenge(callback: CallbackQuery, db: Database):
    row, _ = await db.ensure_user(callback.from_user)
    lang = lang_of(row)
    resources = await db.learning_resources(category="quiz", limit=200)
    await callback.answer()
    if not resources:
        await edit_message(
            callback,
            tr(lang, "daily.none"),
            reply_markup=back_home(lang),
        )
        return
    day_key = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    seed = hashlib.sha256(f"{day_key}:{int(callback.from_user.id)}".encode("utf-8")).digest()
    resource = resources[int.from_bytes(seed[:4], "big") % len(resources)]
    back_label = {"uz": "⬅️ Orqaga", "ru": "⬅️ Назад", "en": "⬅️ Back"}.get(lang, "⬅️ Back")
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=tr(lang, "daily.start"), callback_data=f"daily:start:{int(resource['id'])}")],
        [InlineKeyboardButton(text=back_label, callback_data="nav:home")],
    ])
    title = escape(str(resource["title"]))
    course = escape(str(resource["course_name"]))
    description = escape(str(resource["description"] or "Bugungi mavjud testni bajarib, o‘z natijangizni tekshiring."))
    await edit_message(callback, f"{tr(lang, 'daily')}\n\n<b>{title}</b>\n{course}\n\n{description}", reply_markup=keyboard)


@router.callback_query(F.data.startswith("daily:start:"))
async def daily_challenge_start(callback: CallbackQuery, db: Database, state: FSMContext):
    try:
        resource_id = int(callback.data.split(":", 2)[2])
    except (ValueError, IndexError, TypeError):
        await callback.answer("Test identifikatori noto‘g‘ri.", show_alert=True)
        return
    resource = await db.learning_resource(resource_id, active_only=True)
    if not resource or resource["category"] != "quiz":
        await callback.answer("Bu test mavjud emas yoki faol emas.", show_alert=True)
        return
    questions = await db.quiz_questions(resource_id)
    if not questions:
        await callback.answer("Bu testda savollar hali yo‘q.", show_alert=True)
        return
    user_row, _ = await db.ensure_user(callback.from_user)
    lang = lang_of(user_row)
    try:
        session = await db.start_or_resume_quiz_session(
            telegram_id=int(callback.from_user.id), user_id=int(user_row["id"]),
            resource_id=resource_id, question_total=len(questions),
        )
    except ValueError as exc:
        await callback.answer(str(exc)[:180], show_alert=True)
        return
    await state.clear()
    await callback.answer()
    if callback.message:
        await callback.message.answer(f"🎯 <b>{escape(str(resource['title']))}</b>\n\n{tr(lang, 'daily.ready')}")
        await _send_resumed_quiz(callback.message, state, resource, questions, session)


@router.callback_query(F.data == "user:stats")
async def user_learning_stats(callback: CallbackQuery, db: Database):
    user, _ = await db.ensure_user(callback.from_user)
    stats = await db.user_quiz_stats(int(user["id"]))
    attempts = await db.recent_user_quiz_attempts(int(user["id"]), limit=8)
    streak = await db.user_learning_streak(int(user["id"]))
    lines = [
        "📈 <b>TEST NATIJALARIM</b>", "",
        f"Bajarilgan urinishlar: <b>{stats['attempts']}</b>",
        f"O‘rtacha natija: <b>{stats['average_percent']}%</b>",
        f"Eng yaxshi natija: <b>{stats['best_percent']}%</b>",
        f"O‘quv ketma-ketligi: <b>{streak} kun</b>", "",
    ]
    if attempts:
        lines.append("<b>Oxirgi natijalar:</b>")
        for item in attempts:
            lines.append(f"• {escape(str(item['quiz_title']))} — {int(item['score'])}/{int(item['total'])} ({int(item['percent'])}%)")
    else:
        lines.append("Hozircha saqlangan test natijasi yo‘q. Kutubxonadan test tanlab boshlang.")
    await callback.answer()
    await edit_message(callback, "\n".join(lines), reply_markup=_library_back("user:library"))


@router.callback_query(F.data.startswith("fav:toggle:"))
async def toggle_user_favorite(callback: CallbackQuery, db: Database):
    try:
        _, _, resource_id_raw, origin = callback.data.split(":", 3)
        resource_id = int(resource_id_raw)
    except (ValueError, AttributeError):
        await callback.answer("Material ma’lumoti noto‘g‘ri.", show_alert=True)
        return
    user, _ = await db.ensure_user(callback.from_user)
    resource = await db.learning_resource(resource_id, active_only=True)
    if not resource:
        await callback.answer("Material topilmadi yoki faol emas.", show_alert=True)
        return
    try:
        saved = await db.toggle_favorite(int(user["id"]), resource_id)
    except ValueError:
        await callback.answer("Materialni saqlab bo‘lmadi.", show_alert=True)
        return
    await callback.answer("⭐ Sevimlilarga saqlandi." if saved else "Sevimlilardan olib tashlandi.")
    back = "user:favorites" if origin == "f" else f"library:category:{int(resource['course_id'])}:{resource['category']}"
    favorite_label = "⭐ Sevimlidan olib tashlash" if saved else "☆ Sevimlilarga qo‘shish"
    rows = []
    if resource["category"] == "quiz":
        rows.append([InlineKeyboardButton(text="🧪 Testni boshlash", callback_data=f"quiz:start:{resource_id}")])
    elif str(resource["media_type"] or "text") == "url" or str(resource["content"] or "").lower().startswith(("https://", "http://")):
        url = str(resource["content"] or "").strip()
        if url.lower().startswith(("https://", "http://")):
            rows.append([InlineKeyboardButton(text="🔗 Materialni ochish", url=url)])
    rows.append([InlineKeyboardButton(text=favorite_label, callback_data=f"fav:toggle:{resource_id}:{origin}")])
    rows.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data=back)])
    try:
        await callback.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    except Exception as exc:
        logger.warning("Material #%s sevimli holati yangilandi, ammo tugmalarni yangilash bajarilmadi (%s).", resource_id, type(exc).__name__)


@router.callback_query(F.data.startswith("library:course:"))
async def learning_library_course(callback: CallbackQuery, db: Database):
    try:
        course_id = int(callback.data.rsplit(":", 1)[1])
    except (ValueError, TypeError):
        await callback.answer("Yo‘nalish ID noto‘g‘ri.", show_alert=True)
        return
    course = await db.fetchone("SELECT id,name_uz,active FROM courses WHERE id=? AND active=1", (course_id,))
    if not course:
        await callback.answer("Faol yo‘nalish topilmadi.", show_alert=True)
        return
    await callback.answer()
    rows = [[InlineKeyboardButton(text=label, callback_data=f"library:category:{course_id}:{category}")] for category, label in LIBRARY_CATEGORIES.items()]
    rows.append([InlineKeyboardButton(text="⬅️ Yo‘nalishlar", callback_data="user:library")])
    await edit_message(callback, f"🎓 <b>{escape(course['name_uz'])}</b>\n\nKerakli material turini tanlang:", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data.startswith("library:category:"))
async def learning_library_category(callback: CallbackQuery, db: Database):
    try:
        _, _, course_id_s, category = callback.data.split(":", 3)
        course_id = int(course_id_s)
    except (ValueError, TypeError):
        await callback.answer("So‘rov noto‘g‘ri.", show_alert=True)
        return
    if category not in LIBRARY_CATEGORIES:
        await callback.answer("Material turi noto‘g‘ri.", show_alert=True)
        return
    course = await db.fetchone("SELECT name_uz FROM courses WHERE id=? AND active=1", (course_id,))
    if not course:
        await callback.answer("Yo‘nalish topilmadi.", show_alert=True)
        return
    items = await db.learning_resources(course_id=course_id, category=category, limit=50)
    await callback.answer()
    rows = [[InlineKeyboardButton(text=f"{i + 1:02d} · {str(item['title'])[:55]}", callback_data=f"library:item:{int(item['id'])}")] for i, item in enumerate(items)]
    rows.append([InlineKeyboardButton(text="⬅️ Material turlari", callback_data=f"library:course:{course_id}")])
    text = f"{LIBRARY_CATEGORIES[category]}\n🎓 {escape(course['name_uz'])}\n\n"
    text += "Materialni tanlang:" if items else "Bu yo‘nalishda hozircha material qo‘shilmagan."
    await edit_message(callback, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data.startswith("library:item:"))
async def learning_library_item(callback: CallbackQuery, db: Database):
    try:
        resource_id = int(callback.data.rsplit(":", 1)[1])
    except (ValueError, TypeError):
        await callback.answer("Material ID noto‘g‘ri.", show_alert=True)
        return
    resource = await db.learning_resource(resource_id, active_only=True)
    if not resource:
        await callback.answer("Material topilmadi yoki faol emas.", show_alert=True)
        return
    await callback.answer()
    text = f"{LIBRARY_CATEGORIES.get(resource['category'], '📘 Material')}\n\n<b>{escape(resource['title'])}</b>\n"
    text += f"🎓 Yo‘nalish: {escape(resource['course_name'])}\n\n{escape(resource['description'] or '')}"
    if resource["category"] == "quiz":
        questions = await db.quiz_questions(resource_id)
        if not questions:
            await callback.message.answer(text + "\n\n⚠️ Testda hozircha savol yo‘q.", reply_markup=_library_back(f"library:category:{int(resource['course_id'])}:quiz"))
            return
        user_row, _ = await db.ensure_user(callback.from_user)
        is_saved = await db.is_favorite(int(user_row["id"]), resource_id)
        favorite_label = "⭐ Sevimlidan olib tashlash" if is_saved else "☆ Sevimlilarga qo‘shish"
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🧪 Testni boshlash", callback_data=f"quiz:start:{resource_id}")],
            [InlineKeyboardButton(text=favorite_label, callback_data=f"fav:toggle:{resource_id}:l")],
            [InlineKeyboardButton(text="⬅️ Testlarga qaytish", callback_data=f"library:category:{int(resource['course_id'])}:quiz")],
        ])
        await callback.message.answer(text + f"\n\n❓ Savollar: {len(questions)}", reply_markup=markup)
        return

    file_id = str(resource["telegram_file_id"] or "")
    media_type = str(resource["media_type"] or "text")
    if file_id:
        caption = text[:1000]
        try:
            if media_type == "video":
                await callback.message.answer_video(video=file_id, caption=caption)
            elif media_type == "audio":
                await callback.message.answer_audio(audio=file_id, caption=caption)
            elif media_type == "document":
                await callback.message.answer_document(document=file_id, caption=caption)
            elif media_type == "photo":
                await callback.message.answer_photo(photo=file_id, caption=caption)
            else:
                await callback.message.answer(text)
        except Exception as exc:
            logger.warning("Material #%s fayli yuborilmadi (%s).", resource_id, type(exc).__name__)
            await callback.message.answer(text + "\n\n⚠️ Fayl yuborilmadi. Ustoz yoki administratorga xabar bering.")
    elif media_type == "url" or str(resource["content"] or "").lower().startswith(("https://", "http://")):
        url = str(resource["content"] or "").strip()
        if not url.lower().startswith(("https://", "http://")):
            await callback.message.answer(text, reply_markup=_library_back(f"library:category:{int(resource['course_id'])}:{resource['category']}"))
            return
        user_row, _ = await db.ensure_user(callback.from_user)
        is_saved = await db.is_favorite(int(user_row["id"]), resource_id)
        favorite_label = "⭐ Sevimlidan olib tashlash" if is_saved else "☆ Sevimlilarga qo‘shish"
        await callback.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔗 Materialni ochish", url=url)],
            [InlineKeyboardButton(text=favorite_label, callback_data=f"fav:toggle:{resource_id}:l")],
            [InlineKeyboardButton(text="⬅️ Orqaga", callback_data=f"library:category:{int(resource['course_id'])}:{resource['category']}")],
        ]))
        return
    else:
        body = str(resource["content"] or "")
        await callback.message.answer(text + ("\n\n" + escape(body[:2500]) if body else ""))
    user_row, _ = await db.ensure_user(callback.from_user)
    is_saved = await db.is_favorite(int(user_row["id"]), resource_id)
    await callback.message.answer(
        "Material amallari:",
        reply_markup=_resource_actions(resource_id, is_saved, f"library:category:{int(resource['course_id'])}:{resource['category']}"),
    )


@router.callback_query(F.data.startswith("quiz:start:"))
async def quiz_start(callback: CallbackQuery, state: FSMContext, db: Database):
    try:
        resource_id = int(callback.data.rsplit(":", 1)[1])
    except (ValueError, TypeError):
        await callback.answer("Test ID noto‘g‘ri.", show_alert=True)
        return
    resource = await db.learning_resource(resource_id, active_only=True)
    if not resource or resource["category"] != "quiz":
        await callback.answer("Faol test topilmadi.", show_alert=True)
        return
    access = await db.quiz_assignment_access(callback.from_user.id, resource_id)
    if not access["allowed"]:
        await callback.answer("Bu test sizga tayinlanmagan, muddati tugagan yoki urinishlar soni yakunlangan.", show_alert=True)
        return
    if callback.message and getattr(callback.message.chat.type, "value", str(callback.message.chat.type)) != "private":
        try:
            bot_info = await callback.bot.get_me()
            username = getattr(bot_info, "username", None)
            if not username:
                await callback.answer("Bot username sozlanmagan. Administratorga xabar bering.", show_alert=True)
                return
            deep_link = f"https://t.me/{username}?start=quiz_{resource_id}"
            await callback.answer("Testni shaxsiy chatda boshlang.", show_alert=True)
            await callback.message.answer(
                "🔒 Test javoblari va natijalari maxfiy bo‘lishi uchun testni botning shaxsiy chatida bajaring.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="🧪 Testni shaxsiy chatda boshlash", url=deep_link)
                ]]),
            )
        except Exception as exc:
            logger.warning("Guruh testini shaxsiy chatga yo‘naltirish bajarilmadi (%s).", type(exc).__name__)
            try:
                await callback.answer("Test havolasini hozir ochib bo‘lmadi. Birozdan so‘ng qayta urinib ko‘ring.", show_alert=True)
            except Exception:
                pass
        return
    questions = await db.quiz_questions(resource_id)
    if not questions:
        await callback.answer("Testda savol yo‘q.", show_alert=True)
        return
    user_row, _ = await db.ensure_user(callback.from_user)
    try:
        session = await db.start_or_resume_quiz_session(
            telegram_id=int(callback.from_user.id), user_id=int(user_row["id"]),
            resource_id=resource_id, question_total=len(questions),
        )
    except ValueError as exc:
        await callback.answer(str(exc)[:180], show_alert=True)
        return
    await state.clear()
    await callback.answer("Test boshlandi")
    if callback.message:
        await callback.message.answer(f"🚀 {escape(resource['title'])} boshlandi yoki davom ettirildi. Javoblaringiz har bir foydalanuvchi uchun alohida hisoblanadi.")
        await _send_resumed_quiz(callback.message, state, resource, questions, session)


@router.callback_query(F.data.startswith("quiz:answer:"))
async def quiz_answer(callback: CallbackQuery, state: FSMContext, db: Database):
    try:
        _, _, resource_id_s, index_s, option_s = callback.data.split(":", 4)
        resource_id, index, option_index = int(resource_id_s), int(index_s), int(option_s)
    except (ValueError, TypeError):
        await callback.answer("Javob formati noto‘g‘ri.", show_alert=True)
        return
    session = await db.quiz_session(int(callback.from_user.id), resource_id)
    if not session:
        await callback.answer("Test urinishini qayta ochish uchun test havolasini bosing.", show_alert=True)
        return
    await _load_quiz_fsm(state, session)
    if index != int(session["current_index"]):
        await callback.answer("Bu savolga javob berilgan yoki savol eskirgan.", show_alert=True)
        return
    resource = await db.learning_resource(resource_id, active_only=False)
    questions = await db.quiz_questions(resource_id)
    if not resource or not 0 <= index < len(questions):
        await state.clear()
        await callback.answer("Test topilmadi.", show_alert=True)
        return
    question = questions[index]
    if not 0 <= option_index < len(question["options"]):
        await callback.answer("Variant noto‘g‘ri.", show_alert=True)
        return
    correct = option_index == int(question["correct_index"])
    updated = await db.advance_quiz_session(
        telegram_id=int(callback.from_user.id), resource_id=resource_id,
        expected_index=index, correct=correct,
    )
    if not updated:
        await callback.answer("Bu savolga javob berilgan yoki savol eskirgan.", show_alert=True)
        return
    next_index = int(updated["current_index"])
    await _load_quiz_fsm(state, updated)
    feedback = "✅ To‘g‘ri javob!" if correct else "❌ Javob qabul qilindi."
    await callback.answer(feedback[:190], show_alert=not correct)
    if next_index < len(questions):
        if callback.message:
            await _render_quiz_question(callback.message, resource, questions, next_index)
        return
    await _complete_quiz_from_callback(callback, db, state, resource_id)


@router.callback_query(F.data.startswith("quiz:submit:"))
async def quiz_submit(callback: CallbackQuery, state: FSMContext, db: Database):
    try:
        resource_id = int(callback.data.rsplit(":", 1)[1])
    except (ValueError, TypeError):
        await callback.answer("Test ID noto‘g‘ri.", show_alert=True)
        return
    session = await db.quiz_session(int(callback.from_user.id), resource_id)
    if not session or int(session["current_index"]) != int(session["question_total"]):
        await callback.answer("Test tugallanmagan yoki allaqachon saqlangan.", show_alert=True)
        return
    await _load_quiz_fsm(state, session)
    await callback.answer("Natijani saqlayapman…")
    await _complete_quiz_from_callback(callback, db, state, resource_id)
