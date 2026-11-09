from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu(lang: str = "uz", *, teacher: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text={"uz":"📚 Kurslar","ru":"📚 Курсы","en":"📚 Courses"}.get(lang,"📚 Courses"), callback_data="user:courses"), InlineKeyboardButton(text={"uz":"🎯 Yo‘nalish tanlash","ru":"🎯 Выбрать направление","en":"🎯 Find a course"}.get(lang,"🎯 Find a course"), callback_data="user:navigator")],
        [InlineKeyboardButton(text={"uz":"📝 Ariza qoldirish","ru":"📝 Оставить заявку","en":"📝 Apply"}.get(lang,"📝 Apply"), callback_data="user:apply"), InlineKeyboardButton(text={"uz":"🎒 Kutubxona","ru":"🎒 Библиотека","en":"🎒 Library"}.get(lang,"🎒 Library"), callback_data="user:library")],
        [InlineKeyboardButton(text={"uz":"🎯 Kun vazifasi","ru":"🎯 Задание дня","en":"🎯 Daily challenge"}.get(lang,"🎯 Daily challenge"), callback_data="user:daily"), InlineKeyboardButton(text={"uz":"🧾 Mening arizalarim","ru":"🧾 Мои заявки","en":"🧾 My applications"}.get(lang,"🧾 My applications"), callback_data="user:applications")],
        [InlineKeyboardButton(text={"uz":"👤 Profilim","ru":"👤 Мой профиль","en":"👤 My profile"}.get(lang,"👤 My profile"), callback_data="user:profile"), InlineKeyboardButton(text={"uz":"☰ Boshqa bo‘limlar","ru":"☰ Ещё разделы","en":"☰ More"}.get(lang,"☰ More"), callback_data="user:menu:more")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def more_menu(lang: str = "uz", *, teacher: bool = False) -> InlineKeyboardMarkup:
    labels = {
        "uz": ["👨‍🏫 Ustozlar", "🔎 Kurs qidirish", "📅 Jadval", "⭐ Sevimli materiallar", "📈 Test natijalarim", "❓ Savollar", "💬 Aloqa", "📍 Manzil", "🌐 Til", "ℹ️ STARTUM", "👨‍🏫 Ustoz paneli", "🎓 O‘quvchi kabineti"],
        "ru": ["👨‍🏫 Преподаватели", "🔎 Поиск курса", "📅 Расписание", "⭐ Избранное", "📈 Мои результаты", "❓ Вопросы", "💬 Связь", "📍 Адрес", "🌐 Язык", "ℹ️ О STARTUM", "👨‍🏫 Кабинет преподавателя", "🎓 Кабинет ученика"],
        "en": ["👨‍🏫 Teachers", "🔎 Search courses", "📅 Schedule", "⭐ Favorites", "📈 Test results", "❓ FAQ", "💬 Contact", "📍 Location", "🌐 Language", "ℹ️ About STARTUM", "👨‍🏫 Teacher panel", "🎓 Student cabinet"],
    }
    l = labels.get(lang, labels["uz"])
    destinations = [
        [(0, "user:teachers"), (1, "user:search")],
        [(2, "user:schedule"), (3, "user:favorites")],
        [(4, "user:stats"), (5, "user:faq")],
        [(6, "user:contact"), (7, "user:location")],
        [(8, "user:language"), (9, "user:about")],
        [(11, "edu:student:home")],
    ]
    rows = [[InlineKeyboardButton(text=l[i], callback_data=callback) for i, callback in group] for group in destinations]
    if teacher:
        rows.insert(4, [InlineKeyboardButton(text=l[10], callback_data="edu:teacher:home")])
    rows.append([InlineKeyboardButton(text={"uz":"🏠 Bosh menyu","ru":"🏠 Главное меню","en":"🏠 Main menu"}.get(lang,"🏠 Main menu"), callback_data="nav:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def back_home(lang: str = "uz") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text={"uz":"🏠 Bosh sahifa","ru":"🏠 Главная","en":"🏠 Home"}.get(lang,"🏠 Home"), callback_data="nav:home")]])


def language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🇺🇿 O‘zbekcha", callback_data="lang:uz")], [InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang:ru")], [InlineKeyboardButton(text="🇬🇧 English", callback_data="lang:en")]])


def course_keyboard(courses, lang: str, prefix: str = "course") -> InlineKeyboardMarkup:
    rows = []
    key = {"uz":"name_uz","ru":"name_ru","en":"name_en"}.get(lang,"name_uz")
    for course in courses:
        rows.append([InlineKeyboardButton(text=f"{course['icon']} {course[key]}", callback_data=f"{prefix}:{course['id']}")])
    rows.append([InlineKeyboardButton(text="⬅️", callback_data="nav:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
