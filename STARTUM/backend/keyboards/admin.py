from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def admin_panel(role: str | None = None) -> InlineKeyboardMarkup:
    """Compact command centre; CEO-only administrator controls are role-filtered."""
    rows = [
        [
            InlineKeyboardButton(text="📝 Bot arizalari", callback_data="adm:applications"),
            InlineKeyboardButton(text="🌐 Sayt arizalari", callback_data="adm:webapps"),
        ],
        [
            InlineKeyboardButton(text="💬 Murojaatlar", callback_data="adm:messages"),
            InlineKeyboardButton(text="📚 Kurslar", callback_data="adm:courses"),
        ],
        [
            InlineKeyboardButton(text="🎒 Materiallar", callback_data="adm:resources"),
            InlineKeyboardButton(text="📊 Testlar", callback_data="adm:quizresults"),
        ],
        [
            InlineKeyboardButton(text="👨‍🏫 Ustozlar", callback_data="adm:teachers"),
            InlineKeyboardButton(text="📈 Statistika", callback_data="adm:stats"),
        ],
        [InlineKeyboardButton(text="🎓 Ta’lim tizimi", callback_data="edu:admin:home")],
        [InlineKeyboardButton(text="🔎 Foydalanuvchilar", callback_data="adm:users")],
        [InlineKeyboardButton(text="🏠 Bosh sahifa", callback_data="nav:home")],
    ]
    if str(role or "").strip().casefold() in {"ceo", "owner"}:
        rows.insert(4, [InlineKeyboardButton(text="👥 Adminlar", callback_data="adm:admins")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def application_actions(app_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🟡 Ko‘rib chiqilmoqda", callback_data=f"appstatus:{app_id}:in_review")],
        [InlineKeyboardButton(text="📞 Bog‘lanildi", callback_data=f"appstatus:{app_id}:contacted")],
        [InlineKeyboardButton(text="🟢 Qabul qilindi", callback_data=f"appstatus:{app_id}:accepted")],
        [InlineKeyboardButton(text="🔴 Rad etildi", callback_data=f"appstatus:{app_id}:rejected")],
    ])


def web_application_actions(app_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🟡 Ko‘rib chiqilmoqda", callback_data=f"webappstatus:{app_id}:in_review")],
        [InlineKeyboardButton(text="📞 Bog‘lanildi", callback_data=f"webappstatus:{app_id}:contacted")],
        [InlineKeyboardButton(text="🟢 Qabul qilindi", callback_data=f"webappstatus:{app_id}:accepted")],
        [InlineKeyboardButton(text="🔴 Rad etildi", callback_data=f"webappstatus:{app_id}:rejected")],
    ])


def course_admin_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Kurs qo‘shish", callback_data="courseadm:add")],
        [InlineKeyboardButton(text="📋 Kurslar ro‘yxati", callback_data="adm:courses")],
        [InlineKeyboardButton(text="⬅️ Admin panel", callback_data="adm:home")],
    ])


def message_actions(message_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="↩️ Javob berish", callback_data=f"msgreply:{message_id}")],
        [InlineKeyboardButton(text="✅ Yopish", callback_data=f"msgclose:{message_id}")],
    ])


def admin_management_keyboard(admins) -> InlineKeyboardMarkup:
    """CEO-only action buttons for non-CEO administrators."""
    rows = []
    role_labels = {"senior_admin": "Katta admin", "admin": "Katta admin", "junior_admin": "Kichik admin"}
    for item in admins[:15]:
        telegram_id = int(item["telegram_id"])
        role = str(item["role"])
        if role in {"ceo", "owner"}:
            continue
        active = bool(item["active"])
        rows.append([
            InlineKeyboardButton(
                text=f"⚙ Rol: {role_labels.get(role, role)} · {telegram_id}",
                callback_data=f"admadmin:role:{telegram_id}",
            ),
            InlineKeyboardButton(
                text=("⛔ Bloklash" if active else "🔓 Qayta ulash"),
                callback_data=f"admadmin:toggle:{telegram_id}",
            ),
        ])
        if not active and not bool(item["bot_invite_pending"] if "bot_invite_pending" in item.keys() else 0):
            rows.append([InlineKeyboardButton(
                text=f"✉️ Bot taklifini qayta berish · {telegram_id}",
                callback_data=f"admadmin:invite:{telegram_id}",
            )])
    rows.append([InlineKeyboardButton(text="➕ Admin qo‘shish", callback_data="admadmin:add")])
    rows.append([InlineKeyboardButton(text="⬅️ Admin panel", callback_data="adm:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_role_choice_keyboard(telegram_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Katta administrator", callback_data=f"admadmin:role-select:{telegram_id}:senior_admin")],
        [InlineKeyboardButton(text="Kichik administrator", callback_data=f"admadmin:role-select:{telegram_id}:junior_admin")],
        [InlineKeyboardButton(text="⬅️ Adminlar ro‘yxati", callback_data="adm:admins")],
    ])


def admin_confirm_keyboard(telegram_id: int, *, action: str, role: str | None = None) -> InlineKeyboardMarkup:
    if action == "role" and role in {"senior_admin", "junior_admin"}:
        confirm_data = f"admadmin:role-confirm:{telegram_id}:{role}"
        confirm_text = "✅ Rolni o‘zgartirish"
    elif action in {"activate", "deactivate"}:
        confirm_data = f"admadmin:toggle-confirm:{telegram_id}:{action}"
        confirm_text = "✅ Tasdiqlash"
    else:
        raise ValueError("Administrator tasdiqlash amali noto‘g‘ri.")
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=confirm_text, callback_data=confirm_data)],
        [InlineKeyboardButton(text="Bekor qilish", callback_data="adm:admins")],
    ])


def admin_add_confirmation_keyboard(telegram_id: int, role: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Adminni qo‘shish", callback_data=f"admadmin:add-confirm:{telegram_id}:{role}")],
        [InlineKeyboardButton(text="Bekor qilish", callback_data="admadmin:add-cancel")],
    ])


def user_search_results_keyboard(users) -> InlineKeyboardMarkup:
    rows = []
    for user in users[:10]:
        internal_id = int(user["id"])
        telegram_id = int(user["telegram_id"])
        name = " ".join(part for part in (str(user["first_name"] or ""), str(user["last_name"] or "")) if part).strip()
        label = name or (f"@{user['username']}" if user["username"] else str(telegram_id))
        rows.append([InlineKeyboardButton(
            text=f"{label[:36]} · {telegram_id}",
            callback_data=f"admuser:view:{internal_id}",
        )])
    rows.append([InlineKeyboardButton(text="⬅️ Admin panel", callback_data="adm:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def user_management_keyboard(user_id: int, status: str, *, can_moderate: bool = True) -> InlineKeyboardMarkup:
    rows = []
    if can_moderate:
        action = "restore" if status == "suspended" else "suspend"
        label = "🔓 STARTUM kirishini tiklash" if action == "restore" else "⛔ STARTUM botida cheklash"
        rows.append([InlineKeyboardButton(text=label, callback_data=f"admuser:action:{user_id}:{action}")])
    rows.append([InlineKeyboardButton(text="🔎 Boshqa foydalanuvchi", callback_data="adm:users")])
    rows.append([InlineKeyboardButton(text="⬅️ Admin panel", callback_data="adm:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def user_suspend_duration_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="1 soat", callback_data=f"admuser:duration:{user_id}:60"), InlineKeyboardButton(text="24 soat", callback_data=f"admuser:duration:{user_id}:1440")],
        [InlineKeyboardButton(text="7 kun", callback_data=f"admuser:duration:{user_id}:10080"), InlineKeyboardButton(text="Muddatsiz", callback_data=f"admuser:duration:{user_id}:0")],
        [InlineKeyboardButton(text="Bekor qilish", callback_data="admuser:cancel")],
    ])


def user_moderation_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Tasdiqlash", callback_data="admuser:confirm")],
        [InlineKeyboardButton(text="Bekor qilish", callback_data="admuser:cancel")],
    ])
