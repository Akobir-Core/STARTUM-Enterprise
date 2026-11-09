from __future__ import annotations

from html import escape

TEXT = {
    "uz": {
        "student_title": "🎓 <b>O‘quvchi kabineti</b>", "groups": "👥 Guruhlarim", "join": "🔑 Guruhga qo‘shilish",
        "materials": "📚 O‘quv materiallari", "homework": "📝 Uy vazifalari", "attendance": "📅 Davomatim",
        "assigned_tests": "🧪 Menga tayinlangan testlar", "start_test": "Testni boshlash", "quiz_unavailable": "Bu test hozir mavjud emas yoki urinishlar tugagan.",
        "progress": "📈 O‘zlashtirishim", "certificates": "🏅 Sertifikatlar", "settings": "⚙️ Sozlamalar",
        "teacher_title": "👨‍🏫 <b>Ustoz kabineti</b>", "subjects": "Fanlarim", "groups_short": "Guruhlar",
        "review": "Topshiriqlarni tekshirish", "new_homework": "Uy vazifasi berish", "take_attendance": "Davomat olish",
        "owner_title": "🔐 <b>STARTUM OWNER CABINET</b>", "owner_desc": "Faqat OWNER uchun maxfiy boshqaruv paneli.",
        "admins": "Administratorlar", "create_group": "Guruh yaratish", "audit": "Audit jurnali", "assign": "Ustoz tayinlash",
        "back": "⬅️ Orqaga", "cancel": "Bekor qilish", "choose_course": "Kurs/fanni tanlang:",
        "no_groups": "Hozircha faol guruhlaringiz yo‘q.", "no_subjects": "Sizga fan yoki guruh biriktirilmagan.",
        "enter_code": "Guruh taklif kodini yuboring:", "pending": "So‘rov yuborildi. Administrator tasdiqlashini kuting.",
        "already": "Siz bu guruhga avval so‘rov yuborgansiz yoki a’zosiz.", "bad_code": "Kod noto‘g‘ri yoki guruh faol emas.",
        "no_materials": "Guruhlaringiz uchun e’lon qilingan material topilmadi.", "no_homework": "Hozircha faol uy vazifalari yo‘q.",
        "no_attendance": "Davomat yozuvlari topilmadi.", "no_certificates": "Sizga sertifikat hali berilmagan.",
        "name_group": "Guruh nomini yuboring (2–100 belgi):", "schedule": "Jadvalni aniq matn bilan kiriting. Bilinmasa bo‘sh yuborish uchun /skip:",
        "group_created": "Guruh yaratildi. Taklif kodi:", "homework_title": "Uy vazifasi nomini yuboring:",
        "homework_instructions": "Topshiriq ko‘rsatmasini yuboring yoki /skip:", "homework_created": "Uy vazifasi guruhga e’lon qilindi.",
        "select_group": "Guruhni tanlang:", "submission_prompt": "Javob matni yoki hujjat/foto/video yuboring:",
        "submission_saved": "Topshirig‘ingiz saqlandi.", "permission_denied": "Bu amal uchun ruxsatingiz yo‘q.",
        "empty": "Hozircha ma’lumot yo‘q.", "student_panel": "O‘quvchi kabineti", "join_ok": "Guruhga qo‘shilish so‘rovi yuborildi.",
        "admin_pending": "Tasdiqlash kutilayotgan guruh so‘rovlari", "approve": "Tasdiqlash", "reject": "Rad etish",
        "resource_pending": "Moderatsiya kutilayotgan materiallar", "published": "Material e’lon qilindi.",
        "draft_saved": "E’lon uch tilda qoralama sifatida saqlandi. Hali yuborilmadi.", "language": "Tilni tanlang:",
        "edu_calendar": "📅 Akademik kalendar", "edu_notifications": "🔔 Bildirishnomalar",
        "no_calendar": "Yaqin sanalarda e’lon qilingan tadbir yo‘q.",
        "no_notifications": "Hozircha bildirishnomalar yo‘q.",
        "mark_all_read": "Barchasini o‘qilgan qilish", "all_read": "Barcha bildirishnomalar o‘qilgan deb belgilandi.",
        "notification_read": "Bildirishnoma o‘qilgan deb belgilandi.",
    },
    "ru": {
        "student_title": "🎓 <b>Кабинет ученика</b>", "groups": "👥 Мои группы", "join": "🔑 Присоединиться к группе",
        "materials": "📚 Учебные материалы", "homework": "📝 Домашние задания", "attendance": "📅 Моя посещаемость",
        "assigned_tests": "🧪 Назначенные мне тесты", "start_test": "Начать тест", "quiz_unavailable": "Тест недоступен или попытки закончились.",
        "progress": "📈 Мой прогресс", "certificates": "🏅 Сертификаты", "settings": "⚙️ Настройки",
        "teacher_title": "👨‍🏫 <b>Кабинет преподавателя</b>", "subjects": "Мои предметы", "groups_short": "Группы",
        "review": "Проверка работ", "new_homework": "Создать задание", "take_attendance": "Отметить посещаемость",
        "owner_title": "🔐 <b>КАБИНЕТ ВЛАДЕЛЬЦА STARTUM</b>", "owner_desc": "Закрытая панель только для владельца.",
        "admins": "Администраторы", "create_group": "Создать группу", "audit": "Журнал аудита", "assign": "Назначить преподавателя",
        "back": "⬅️ Назад", "cancel": "Отмена", "choose_course": "Выберите курс/предмет:",
        "no_groups": "У вас пока нет активных групп.", "no_subjects": "Вам пока не назначены предметы или группы.",
        "enter_code": "Отправьте код приглашения в группу:", "pending": "Запрос отправлен. Ожидайте подтверждения администратора.",
        "already": "Вы уже отправляли запрос или состоите в этой группе.", "bad_code": "Код неверен или группа неактивна.",
        "no_materials": "Опубликованные материалы для ваших групп не найдены.", "no_homework": "Активных домашних заданий пока нет.",
        "no_attendance": "Записи посещаемости не найдены.", "no_certificates": "Сертификаты пока не выданы.",
        "name_group": "Отправьте название группы (2–100 символов):", "schedule": "Укажите подтверждённое расписание или /skip:",
        "group_created": "Группа создана. Код приглашения:", "homework_title": "Отправьте название задания:",
        "homework_instructions": "Отправьте инструкцию или /skip:", "homework_created": "Задание опубликовано для группы.",
        "select_group": "Выберите группу:", "submission_prompt": "Отправьте ответ текстом или фото/документ/видео:",
        "submission_saved": "Ваш ответ сохранён.", "permission_denied": "Недостаточно прав для этого действия.",
        "empty": "Пока нет данных.", "student_panel": "Кабинет ученика", "join_ok": "Запрос на вступление отправлен.",
        "admin_pending": "Запросы на вступление, ожидающие подтверждения", "approve": "Подтвердить", "reject": "Отклонить",
        "resource_pending": "Материалы на модерации", "published": "Материал опубликован.",
        "draft_saved": "Объявление сохранено как черновик на трёх языках. Оно ещё не отправлено.", "language": "Выберите язык:",
        "edu_calendar": "📅 Академический календарь", "edu_notifications": "🔔 Уведомления",
        "no_calendar": "На ближайшие даты опубликованных событий нет.",
        "no_notifications": "Пока уведомлений нет.",
        "mark_all_read": "Отметить всё прочитанным", "all_read": "Все уведомления отмечены прочитанными.",
        "notification_read": "Уведомление отмечено прочитанным.",
    },
    "en": {
        "student_title": "🎓 <b>Student cabinet</b>", "groups": "👥 My groups", "join": "🔑 Join a group",
        "materials": "📚 Learning materials", "homework": "📝 Homework", "attendance": "📅 My attendance",
        "assigned_tests": "🧪 Tests assigned to me", "start_test": "Start test", "quiz_unavailable": "This test is unavailable or your attempts are exhausted.",
        "progress": "📈 My progress", "certificates": "🏅 Certificates", "settings": "⚙️ Settings",
        "teacher_title": "👨‍🏫 <b>Teacher cabinet</b>", "subjects": "My subjects", "groups_short": "Groups",
        "review": "Review submissions", "new_homework": "Create homework", "take_attendance": "Take attendance",
        "owner_title": "🔐 <b>STARTUM OWNER CABINET</b>", "owner_desc": "Private control panel for the OWNER only.",
        "admins": "Administrators", "create_group": "Create group", "audit": "Audit log", "assign": "Assign teacher",
        "back": "⬅️ Back", "cancel": "Cancel", "choose_course": "Choose a course/subject:",
        "no_groups": "You have no active groups yet.", "no_subjects": "No subjects or groups are assigned to you.",
        "enter_code": "Send the group invitation code:", "pending": "Your request was sent. Wait for administrator approval.",
        "already": "You have already requested membership or joined this group.", "bad_code": "The code is invalid or the group is inactive.",
        "no_materials": "No published materials were found for your groups.", "no_homework": "There are no active homework tasks yet.",
        "no_attendance": "No attendance records were found.", "no_certificates": "No certificates have been issued to you yet.",
        "name_group": "Send a group name (2–100 characters):", "schedule": "Enter a verified schedule, or send /skip:",
        "group_created": "Group created. Invitation code:", "homework_title": "Send the homework title:",
        "homework_instructions": "Send instructions or /skip:", "homework_created": "Homework was published to the group.",
        "select_group": "Choose a group:", "submission_prompt": "Send your answer as text, photo, document or video:",
        "submission_saved": "Your submission was saved.", "permission_denied": "You are not allowed to perform this action.",
        "empty": "No data is available yet.", "student_panel": "Student cabinet", "join_ok": "Your group membership request was sent.",
        "admin_pending": "Pending group membership requests", "approve": "Approve", "reject": "Reject",
        "resource_pending": "Materials awaiting moderation", "published": "The material was published.",
        "draft_saved": "The announcement draft was saved in all three languages. It was not sent.", "language": "Choose a language:",
        "edu_calendar": "📅 Academic calendar", "edu_notifications": "🔔 Notifications",
        "no_calendar": "There are no published events coming up.",
        "no_notifications": "There are no notifications yet.",
        "mark_all_read": "Mark all as read", "all_read": "All notifications were marked as read.",
        "notification_read": "Notification marked as read.",
    },
}


def et(lang: str, key: str) -> str:
    lang = lang if lang in TEXT else "uz"
    return TEXT[lang].get(key, TEXT["uz"].get(key, key))


def announcement_preview(announcement_id: int, translations: dict, target_label: str) -> str:
    """Build a Telegram-safe tri-lingual preview without truncating stored content.

    Each title/body excerpt is deliberately short because HTML escaping can
    expand a single source character into several rendered characters.
    The full translation remains persisted and is sent after confirmation.
    """
    sections = [f"👁 <b>E’lon ko‘rib chiqish · #{int(announcement_id)}</b>"]
    for code, lang in (("UZ", "uz"), ("RU", "ru"), ("EN", "en")):
        item = translations[lang]
        title = str(item.get("title", "")).strip()
        body = str(item.get("body", "")).strip()
        title_excerpt = title[:60]
        body_excerpt = body[:100]
        if len(title) > len(title_excerpt):
            title_excerpt = title_excerpt.rstrip() + "…"
        if len(body) > len(body_excerpt):
            body_excerpt = body_excerpt.rstrip() + "…"
        sections.append(f"<b>{code} — {escape(title_excerpt)}</b>\n{escape(body_excerpt)}")
    sections.append(
        f"Qabul qiluvchilar: {escape(str(target_label)[:60])}\n"
        "Yuborishni tasdiqlaysizmi?"
    )
    preview = "\n\n".join(sections)
    # Defensive bound if labels or future fixed copy grows. Never send malformed
    # HTML: the deliberately bounded excerpts above should keep this < 4096.
    if len(preview) >= 3900:
        raise ValueError("E’lon preview’i Telegram xabar limitiga sig‘madi.")
    return preview
