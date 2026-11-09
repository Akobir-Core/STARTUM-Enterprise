from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_header_has_compact_navigation_language_theme_and_application_actions():
    html = read("frontend/index.html")
    nav = html.split('<nav class="main-nav" id="mainNav"', 1)[1].split("</nav>", 1)[0]
    assert 'class="topbar premium-topbar"' in html
    assert 'href="#about"' in nav
    assert 'href="#telegramExperience"' not in nav
    assert 'data-i18n="nav.telegram"' not in nav
    assert 'data-i18n="nav.signup"' in nav
    assert 'id="languageSelect"' in html and 'id="themeToggle"' in html
    assert 'id="menuBtn"' in html and 'id="contact"' in html


def test_removed_course_finder_is_not_referenced_but_navigator_remains():
    html = read("frontend/index.html")
    js = read("frontend/script.js")
    assert 'id="courseFinderForm"' not in html
    assert 'id="fit"' in html
    assert "function setupCourseFinder()" not in js
    assert "function buildStudyPlan(" not in js
    assert "finder." not in js


def test_teacher_profiles_use_only_supplied_facts_and_symbolic_placeholders():
    js = read("frontend/script.js")
    assert 'name: "Islombek Soatqulov"' in js
    assert 'subject: "Turk tili va Tarix"' in js
    assert 'credential: "A+"' in js
    assert 'name: "Komil Nomozov"' in js
    assert 'credential: "B2"' in js
    assert 'name: "Rus tili o‘qituvchisi"' in js
    assert 'name: "Ingliz tili o‘qituvchisi"' in js
    assert (ROOT / "frontend/assets/images/ustoz-islombek-soatqulov.jpg").is_file()
    assert (ROOT / "frontend/assets/images/teacher-profile-placeholder.svg").is_file()


def test_teacher_placeholder_is_explicitly_not_a_real_portrait():
    svg = read("frontend/assets/images/teacher-profile-placeholder.svg")
    assert "not a real teacher portrait" in svg


def test_telegram_help_and_daily_challenge_are_real_handlers():
    user = read("backend/handlers/user.py")
    keyboards = read("backend/keyboards/common.py")
    assert '@router.message(Command("help"))' in user
    assert '@router.callback_query(F.data == "user:daily")' in user
    assert '@router.callback_query(F.data.startswith("daily:start:"))' in user
    assert 'callback_data="user:daily"' in keyboards


def test_learning_streak_is_computed_from_saved_quiz_attempts():
    db = read("backend/database/db.py")
    assert "async def user_learning_streak(self, user_id: int) -> int:" in db
    assert "FROM quiz_attempts WHERE user_id=? ORDER BY activity_date DESC" in db


def test_admin_login_hides_workspace_navigation_until_session_is_verified():
    html = read("backend/admin_panel/index.html")
    js = read("backend/admin_panel/admin.js")
    css = read("backend/admin_panel/admin.css")
    assert '<div class="app-shell is-logged-out" id="appShell">' in html
    assert "#appShell')?.classList.add('is-logged-out')" in js
    assert "#appShell')?.classList.remove('is-logged-out')" in js
    assert ".app-shell.is-logged-out > .sidebar" in css


def test_admin_password_visibility_is_accessible_and_does_not_persist_password():
    html = read("backend/admin_panel/index.html")
    js = read("backend/admin_panel/admin.js")
    assert 'id="toggleAdminPassword"' in html
    assert 'aria-controls="adminPasswordInput"' in html
    assert "passwordInput.type = reveal ? 'text' : 'password'" in js
    assert "localStorage.setItem('adminPassword'" not in js


def test_backend_env_example_contains_no_live_token_or_owner_identifier():
    import re
    sample = read("backend/.env.example")
    assert not re.search(r"(?<![A-Za-z0-9])\d{8,}:[A-Za-z0-9_-]{25,}(?![A-Za-z0-9])", sample)
    for key in ("BOT_TOKEN=", "CEO_OWNER_ID=", "WEB_ADMIN_PASSWORD_HASH=", "ADMIN_SESSION_SECRET="):
        assert key in sample


def test_bot_menu_is_compact_and_keeps_secondary_routes_in_more_screen():
    keyboard = read("backend/keyboards/common.py")
    user = read("backend/handlers/user.py")
    main = keyboard.split("def main_menu", 1)[1].split("def more_menu", 1)[0]
    more = keyboard.split("def more_menu", 1)[1].split("def back_home", 1)[0]
    assert main.count("callback_data=") == 8
    assert 'callback_data="user:profile"' in main
    assert 'callback_data="user:menu:more"' in main
    assert 'callback_data="teacher:panel"' not in main
    assert 'if teacher:' in more and 'callback_data="edu:teacher:home"' in more
    assert '@router.callback_query(F.data == "user:menu:more")' in user
    assert '@router.callback_query(F.data == "user:profile")' in user
    for callback in (
        "user:courses", "user:teachers", "user:navigator", "user:apply", "user:search",
        "user:applications", "user:schedule", "user:library", "user:favorites", "user:stats",
        "user:daily", "user:faq", "user:contact", "user:location", "user:language", "user:about",
    ):
        assert callback in keyboard
