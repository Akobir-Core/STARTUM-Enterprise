from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
BACKEND = ROOT / "backend"


def test_website_form_posts_to_api_and_shows_only_a_localized_success_message():
    script = (FRONTEND / "script.js").read_text(encoding="utf-8")
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    api = (BACKEND / "api.py").read_text(encoding="utf-8")
    assert 'fetch(`${API_BASE_URL}/applications`' in script
    assert "\"form.success\": 'Arizangiz muvaffaqiyatli yuborildi.'," in script
    assert "\"form.success\": 'Ваша заявка успешно отправлена.'," in script
    assert "\"form.success\": 'Your application has been submitted successfully.'," in script
    assert 'id="formStatus"' in html and 'id="applicationReceipt"' not in html
    assert 'tracking_code' in api and 'enqueue_application_notifications(' in api
    assert 'data.tracking_code' not in script and 'data.id' not in script


def test_application_delivery_is_durable_and_has_retry_worker():
    api = (BACKEND / "api.py").read_text(encoding="utf-8")
    db = (BACKEND / "database" / "db.py").read_text(encoding="utf-8")
    main = (BACKEND / "main.py").read_text(encoding="utf-8")
    notifications = (BACKEND / "notifications.py").read_text(encoding="utf-8")
    assert "enqueue_application_notifications(" in api
    assert "notification_outbox" in db
    assert "asyncio.sleep(60)" in main
    assert "_delivery_lock" in notifications
    assert "reset_exhausted_notifications" in notifications
    assert "_notification_retry_worker" in main


def test_bot_has_direction_scoped_materials_interactive_quizzes_and_group_sharing():
    user = (BACKEND / "handlers" / "user.py").read_text(encoding="utf-8")
    admin = (BACKEND / "handlers" / "admin.py").read_text(encoding="utf-8")
    db = (BACKEND / "database" / "db.py").read_text(encoding="utf-8")
    for category in ('"book"', '"vocabulary"', '"movie"', '"music"', '"quiz"'):
        assert category in db
    for feature in ("user:library", "quiz:start:", "quiz:answer:", "QuizState.answering"):
        assert feature in user
    for feature in ("/add_teacher_manager", "/share_test", "AddLearningResourceState.question", "quiz_publish"):
        assert feature in admin
    assert "teacher_manager" in user and "_can_manage_course" in admin


def test_web_and_bot_admin_areas_are_server_protected_and_no_admin_menu_link_is_public():
    html = (BACKEND / "admin_panel" / "index.html").read_text(encoding="utf-8")
    api = (BACKEND / "api.py").read_text(encoding="utf-8")
    bot_admin = (BACKEND / "handlers" / "admin.py").read_text(encoding="utf-8")
    assert 'id="loginStage"' in html and 'id="workspace" hidden' in html
    assert "Depends(require_admin)" in api and 'Depends(require_roles("ceo"))' in api
    assert '@app.get("/api/admin/notifications")' in api
    assert '@app.patch("/api/admin/notifications/{notification_id}/retry")' in api
    assert "data-retry-notification" in (BACKEND / "admin_panel" / "admin.js").read_text(encoding="utf-8")
    assert '@router.message(Command("admin"))' in bot_admin and "require_admin(message, db)" in bot_admin
    assert 'href="/admin' not in (FRONTEND / "index.html").read_text(encoding="utf-8")


def test_bot_admin_add_confirmation_matches_keyboard_payload_and_is_private_and_audited():
    admin = (BACKEND / "handlers" / "admin.py").read_text(encoding="utf-8")
    keyboards = (BACKEND / "keyboards" / "admin.py").read_text(encoding="utf-8")
    commands = (BACKEND / "admin_commands.py").read_text(encoding="utf-8")
    assert 'callback_data=f"admadmin:add-confirm:{telegram_id}:{role}"' in keyboards
    assert 'callback.data.split(":", 3)' in admin
    assert 'prefix != "admadmin" or command != "add-confirm"' in admin
    assert 'if not _is_private_callback(callback):' in admin
    assert '"telegram_admin_created"' in admin
    assert 'Command("admins")' in admin
    assert 'BotCommand(command="admins"' in commands


def test_site_and_admin_have_reduced_motion_accessible_focus_and_light_mode():
    site_css = (FRONTEND / "style.css").read_text(encoding="utf-8")
    admin_css = (BACKEND / "admin_panel" / "admin.css").read_text(encoding="utf-8")
    admin_js = (BACKEND / "admin_panel" / "admin.js").read_text(encoding="utf-8")
    html = (BACKEND / "admin_panel" / "index.html").read_text(encoding="utf-8")
    assert "@media (prefers-reduced-motion: reduce)" in site_css
    assert "@media (prefers-reduced-motion: reduce)" in admin_css
    assert ':root[data-admin-theme="light"]' in admin_css
    assert 'document.documentElement.dataset.adminTheme = next' in admin_js
    assert 'class="nav-icon"' in html and 'viewBox="0 0 24 24"' in html


def test_package_contains_only_standalone_site_backend_and_test_parts():
    assert (ROOT / "frontend" / "index.html").exists()
    assert (BACKEND / "main.py").exists()
    visible_directories = {
        item.name for item in ROOT.iterdir()
        if item.is_dir()
        and not item.name.startswith(".")
        and not item.name.lower().startswith("startum-release-")
    }
    assert visible_directories == {"frontend", "backend", "tests", "docs", "reports"}


def test_completed_quiz_results_are_persisted_and_exposed_to_admin_and_teacher():
    db = (BACKEND / "database" / "db.py").read_text(encoding="utf-8")
    user = (BACKEND / "handlers" / "user.py").read_text(encoding="utf-8")
    admin = (BACKEND / "handlers" / "admin.py").read_text(encoding="utf-8")
    api = (BACKEND / "api.py").read_text(encoding="utf-8")
    panel = (BACKEND / "admin_panel" / "admin.js").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS quiz_attempts" in db
    assert "CREATE TABLE IF NOT EXISTS user_favorites" in db
    assert "quiz_session(" in user and "complete_quiz_session(" in user and "user_quiz_stats(" in user
    assert 'Command("quiz_results")' in admin
    assert '@app.get("/api/admin/quiz-results")' in api
    assert "loadQuizResults" in panel


def test_database_path_is_resolved_relative_to_backend_not_process_working_directory():
    config_source = (BACKEND / "config.py").read_text(encoding="utf-8")
    assert "if not database_path.is_absolute():" in config_source
    assert "database_path = ROOT / database_path" in config_source


def test_group_shared_quiz_opens_private_deep_link_and_keeps_results_per_user():
    user = (BACKEND / "handlers" / "user.py").read_text(encoding="utf-8")
    admin = (BACKEND / "handlers" / "admin.py").read_text(encoding="utf-8")
    assert 'payload.startswith("quiz_")' in user
    assert 'deep_link = f"https://t.me/{username}?start=quiz_{resource_id}"' in user
    assert 'callback.message.chat.type' in user
    assert 'private_test_url = f"https://t.me/{bot_username}?start=quiz_{resource_id}"' in admin
    assert 'text="🧪 Testni shaxsiy chatda boshlash", url=private_test_url' in admin
    assert 'quiz_user_id=int(session["user_id"])' in user
    assert 'await db.complete_quiz_session(' in user


def test_footer_contains_instagram_and_telegram_social_links_safely():
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    footer = html.split("<footer class=\"footer\">", 1)[1].split("</footer>", 1)[0]
    social = footer.split('<div class="footer-social">', 1)[1].split('</div>', 1)[0]
    assert footer.count('href="https://www.instagram.com/startum_education1/"') == 1
    assert social.count('href="https://t.me/StartumEducation"') == 1
    for url in ('https://www.instagram.com/startum_education1/', 'https://t.me/StartumEducation'):
        link_start = social.index(f'href="{url}"')
        link_end = social.index(">", link_start)
        opening_tag = social[link_start:link_end]
        assert 'target="_blank"' in opening_tag
        assert 'rel="noopener noreferrer"' in opening_tag
        assert 'aria-label=' in opening_tag
    assert social.count('class="footer-social-icon"') == 2


def test_footer_social_links_keep_instagram_and_official_telegram_channel():
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    script = (FRONTEND / "script.js").read_text(encoding="utf-8")
    css = (FRONTEND / "style.css").read_text(encoding="utf-8")
    footer = html.split('<footer class="footer">', 1)[1].split('</footer>', 1)[0]
    assert script.count('"footer.instagramLink":') == 3
    assert script.count('"footer.telegramLink":') == 3
    assert 'https://t.me/StartumEducation' in footer
    assert 'https://www.instagram.com/startum_education1/' in footer
    header = html.split('<header class="topbar', 1)[1].split('</header>', 1)[0]
    assert 't.me/' not in header
    assert ".footer-social-links" in css
    assert ".footer-social-icon" in css
    assert '@media (prefers-reduced-motion: reduce)' in css


def test_contact_phone_uses_the_configured_real_tel_link_and_old_duplicate_telegram_shortcut_is_removed():
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    config = (FRONTEND / "startum.config.js").read_text(encoding="utf-8")
    script = (FRONTEND / "script.js").read_text(encoding="utf-8")
    assert 'href="tel:+998932483441"' in html
    assert 'contactPhone: "+998 93 248 34 41"' in config
    assert 'telegramUrl:' not in config
    assert 'data-contact-telegram' not in html
    assert 'function startumBotUrl(course = "")' not in script
    assert 'botUsername:' not in config
    assert 'data-course-modal-enroll' in html
    assert 'href="#contact" class="btn btn-mint" data-course-modal-enroll' in html
    assert 'window.open(link, "_blank", "noopener")' not in script


def test_empty_website_applications_use_a_logged_fallback_when_telegram_cannot_edit_the_callback_message():
    admin = (BACKEND / "handlers" / "admin.py").read_text(encoding="utf-8")
    assert "async def _edit_or_send_callback_text(" in admin
    assert "except TelegramBadRequest as exc:" in admin
    assert "sending fallback response" in admin
    assert 'await _edit_or_send_callback_text(' in admin
    helper = admin.split("async def _edit_or_send_callback_text(", 1)[1].split("async def require_admin(", 1)[0]
    assert "except Exception" not in helper


def test_telegram_startup_failures_retry_without_discarding_pending_updates_or_stopping_api():
    main = (BACKEND / "main.py").read_text(encoding="utf-8")
    assert "async def _run_bot_session() -> None:" in main
    assert "async def run_bot() -> None:" in main
    assert "while True:" in main.split("async def run_bot() -> None:", 1)[1].split("async def main()", 1)[0]
    assert "asyncio.sleep(15)" in main
    assert "await bot.delete_webhook(drop_pending_updates=False)" in main
    assert "await asyncio.gather(run_api(), run_bot())" in main


def test_hero_and_classroom_images_use_existing_assets():
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    script = (FRONTEND / "script.js").read_text(encoding="utf-8")
    image_dir = FRONTEND / "assets" / "images"
    assert 'assets/images/startum-day-hero.webp' in html
    assert 'assets/images/startum-dark-hero.webp' in script
    assert 'assets/images/startum-classroom.webp' in html
    assert (image_dir / "startum-day-hero.webp").is_file()
    assert (image_dir / "startum-dark-hero.webp").is_file()
    assert (image_dir / "startum-aeline-student.jpg").is_file()  # protected original retained
    assert (image_dir / "startum-classroom.webp").is_file()
    assert "startum-hero.webp" not in html


def test_i18n_updates_footer_label_spans_without_replacing_social_icons():
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    footer = html.split("<footer class=\"footer\">", 1)[1].split("</footer>", 1)[0]
    assert 'data-i18n="footer.telegramLink"' in footer
    assert 'data-i18n="footer.instagramLink"' in footer
    assert footer.count('class="footer-social-icon"') == 2


def test_bot_legacy_asset_names_resolve_to_files_that_exist():
    user = (BACKEND / "handlers" / "user.py").read_text(encoding="utf-8")
    assets = BACKEND / "assets"
    assert '"startum-welcome.png": "startum-welcome.jpg"' in user
    assert '"startum-courses.png": "startum-courses.jpg"' in user
    assert (assets / "startum-welcome.jpg").is_file()
    assert (assets / "startum-courses.jpg").is_file()
    assert (assets / "startum-navigator.png").is_file()


def test_faq_callback_validates_numeric_index_and_bounds():
    user = (BACKEND / "handlers" / "user.py").read_text(encoding="utf-8")
    faq_handler = user.split('@router.callback_query(F.data.startswith("faq:"))', 1)[1].split(
        '@router.callback_query(F.data == "user:location")', 1
    )[0]
    assert "except (ValueError, IndexError, TypeError)" in faq_handler
    assert "0 <= index < len(FAQS[lang])" in faq_handler


def test_application_status_notifications_are_durable_for_bot_and_linked_website_users():
    db = (BACKEND / "database" / "db.py").read_text(encoding="utf-8")
    notifications = (BACKEND / "notifications.py").read_text(encoding="utf-8")
    api = (BACKEND / "api.py").read_text(encoding="utf-8")
    admin = (BACKEND / "handlers" / "admin.py").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS application_status_notification_outbox" in db
    assert "enqueue_application_status_notification(" in api
    assert 'source="bot"' in admin and 'source="website"' in admin
    assert "pending_application_status_notifications" in notifications
    assert "mark_application_status_notification_failed" in notifications


def test_environment_example_does_not_contain_live_credentials():
    import re
    sample = (BACKEND / ".env.example").read_text(encoding="utf-8")
    assert not re.search(r"(?<![A-Za-z0-9])\d{8,}:[A-Za-z0-9_-]{25,}(?![A-Za-z0-9])", sample)
    for line in sample.splitlines():
        stripped = line.strip()
        if stripped.startswith(("BOT_TOKEN=", "CEO_OWNER_ID=", "WEB_ADMIN_PASSWORD_HASH=", "ADMIN_SESSION_SECRET=")):
            assert stripped.endswith("=")


def test_bot_admin_list_supports_confirmed_role_changes_and_session_safe_block_reactivation():
    admin = (BACKEND / "handlers" / "admin.py").read_text(encoding="utf-8")
    keyboards = (BACKEND / "keyboards" / "admin.py").read_text(encoding="utf-8")
    assert 'F.data.startswith("admadmin:role:")' in admin
    assert 'F.data.startswith("admadmin:role-select:")' in admin
    assert 'F.data.startswith("admadmin:role-confirm:")' in admin
    assert 'F.data.startswith("admadmin:toggle:")' in admin
    assert 'F.data.startswith("admadmin:toggle-confirm:")' in admin
    assert "admin_confirm_keyboard" in admin and "admin_management_keyboard" in admin
    assert 'await db.add_telegram_admin(telegram_id, role, callback.from_user.id, active=False)' in admin
    assert 'await db.set_telegram_admin_active(telegram_id, False)' in admin
    assert 'await db.set_web_admin_active(str(linked["username"]), True)' in admin
    assert 'text="Bekor qilish"' in keyboards


def test_light_theme_is_the_default_and_public_page_has_a_single_primary_heading():
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    script = (FRONTEND / "script.js").read_text(encoding="utf-8")
    assert '<html lang="uz" data-theme="light">' in html
    assert 'localStorage.getItem("startumTheme") || "light"' in script
    assert html.count("<h1") == 1
    assert 'name="color-scheme" content="light"' in html


def test_production_api_disables_public_schema_docs_and_requires_secure_admin_cookie():
    api = (BACKEND / "api.py").read_text(encoding="utf-8")
    config = (BACKEND / "config.py").read_text(encoding="utf-8")
    assert 'docs_url=None if _production else "/docs"' in api
    assert 'openapi_url=None if _production else "/openapi.json"' in api
    assert 'if app_env == "production" and not admin_cookie_secure:' in config
    assert 'Strict-Transport-Security' in api
    assert 'X-Robots-Tag' in api


def test_web_applications_are_deduplicated_inside_a_serialized_database_transaction():
    db = (BACKEND / "database" / "db.py").read_text(encoding="utf-8")
    api = (BACKEND / "api.py").read_text(encoding="utf-8")
    assert 'async def create_web_application_if_new(' in db
    assert 'async def create_application_if_new(' in db
    assert db.count('await db.execute("BEGIN IMMEDIATE")') >= 3
    assert 'create_web_application_if_new(' in api
    application_handler = api.split('async def create_application(', 1)[1].split('async def ', 1)[0]
    assert 'deliver_pending_notifications(' not in application_handler


def test_bot_fsm_text_handlers_validate_non_text_updates_and_support_messages_are_queued():
    user = (BACKEND / "handlers" / "user.py").read_text(encoding="utf-8")
    db = (BACKEND / "database" / "db.py").read_text(encoding="utf-8")
    notifications = (BACKEND / "notifications.py").read_text(encoding="utf-8")
    for handler in ("reg_name", "reg_phone", "reg_message", "search_run", "support_topic", "support_message"):
        region = user.split(f"async def {handler}(", 1)[1].split("\n@router", 1)[0]
        assert "message.text" in region
    assert "support_notification_outbox" in db
    assert "pending_support_notifications" in notifications
    assert "enqueue_support_notifications(msg_id" in user


def test_public_and_admin_assets_are_noindexed_where_appropriate_and_seo_metadata_is_present():
    public_html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    admin_html = (BACKEND / "admin_panel" / "index.html").read_text(encoding="utf-8")
    assert 'rel="canonical" href="https://startum.uz/"' in public_html
    assert 'property="og:image"' in public_html
    assert 'application/ld+json' in public_html
    assert 'name="robots" content="noindex, nofollow, noarchive"' in admin_html


def test_public_asset_references_resolve_to_local_files():
    import re
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    for match in re.findall(r'(?:src|href|poster)="([^"]+)"', html):
        if match.startswith(("https://", "http://", "#", "tel:", "mailto:", "/api")):
            continue
        if match.startswith("data:"):
            continue
        assert (FRONTEND / match.split("?", 1)[0]).is_file(), match


def test_support_outbox_table_and_api_test_fixture_isolation_are_in_place():
    db = (BACKEND / "database" / "db.py").read_text(encoding="utf-8")
    fixture = (BACKEND / "tests" / "conftest.py").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS support_notification_outbox" in db
    assert 'monkeypatch.setattr(api_module.app.state, "database_initialized", False, raising=False)' in fixture
    assert "CREATE INDEX IF NOT EXISTS idx_support_outbox_status" in db


def test_public_homepage_removes_private_utility_panels_but_keeps_server_application_tracking():
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    script = (FRONTEND / "script.js").read_text(encoding="utf-8")
    api = (BACKEND / "api.py").read_text(encoding="utf-8")
    db = (BACKEND / "database" / "db.py").read_text(encoding="utf-8")
    for obsolete_id in ('id="learningHub"', 'id="applicationTracker"', 'id="reviews"', 'id="courseFinderForm"', 'id="studyPlanPanel"'):
        assert obsolete_id not in html
    for obsolete_function in ("function setupLearningHub()", "function setupApplicationTracker()", "function setupCourseFinder()", "function buildStudyPlan("):
        assert obsolete_function not in script
    assert 'id="leadForm"' in html and 'id="formStatus"' in html
    assert 'id="applicationReceiptCode"' not in html
    assert 'Kodni nusxalash' not in html
    assert '"form.success":' in script
    assert '@app.post("/api/application-status")' in api
    assert "tracking_token_hash" in db
    assert "web_application_by_tracking_hash" in db
    assert "function setupApplicationReceipt()" not in script


def test_application_tracking_uses_hashed_bearer_codes_and_does_not_expose_hash_in_admin_api():
    api = (BACKEND / "api.py").read_text(encoding="utf-8")
    db = (BACKEND / "database" / "db.py").read_text(encoding="utf-8")
    assert 'hashlib.sha256(tracking_code.encode("utf-8")).hexdigest()' in api
    assert 'hashlib.sha256(payload.tracking_code.encode("utf-8")).hexdigest()' in api
    assert 'item.pop("tracking_token_hash", None)' in api
    assert 'CREATE UNIQUE INDEX IF NOT EXISTS idx_web_applications_tracking_hash' in db


def test_public_contact_config_uses_the_defined_startum_config_object():
    script = (FRONTEND / "script.js").read_text(encoding="utf-8")
    assert "STARTUM_CONFIG.contactPhone" in script
    assert "config.contactPhone" not in script


def test_public_telegram_channel_is_only_in_footer_socials_without_touching_the_bot():
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    css = (FRONTEND / "premium-experience.css").read_text(encoding="utf-8")
    script = (FRONTEND / "script.js").read_text(encoding="utf-8")
    bot = (BACKEND / "handlers" / "user.py").read_text(encoding="utf-8")
    config = (FRONTEND / "startum.config.js").read_text(encoding="utf-8")
    assert 'id="telegramExperience"' not in html
    assert 'href="#telegramExperience"' not in html
    footer = html.split('<footer class="footer">', 1)[1].split('</footer>', 1)[0]
    social = footer.split('<div class="footer-social">', 1)[1].split('</div>', 1)[0]
    header = html.split('<header class="topbar', 1)[1].split('</header>', 1)[0]
    assert 'href="https://t.me/StartumEducation"' in social
    assert 't.me/' not in header
    assert ".telegram-workflow-card" not in css
    assert "@media (max-width: 680px)" in css
    assert "@media (prefers-reduced-motion: reduce)" in css
    assert ":focus-visible" in css
    assert 'function startumBotUrl(course = "")' not in script
    assert 'botUsername:' not in config
    assert 'payload == "explore"' in bot and 'payload == "apply"' in bot
    # The canonical channel belongs in both Schema.org sameAs metadata and one visible footer link.
    assert html.count('href="https://t.me/StartumEducation"') == 1
    assert '"sameAs": ["https://t.me/StartumEducation"]' in html
    assert 'https://t.me/StartumEducation' not in script


def test_supplied_video_is_restored_in_the_existing_hero_modal_with_local_assets_and_safe_controls():
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    script = (FRONTEND / "script.js").read_text(encoding="utf-8")
    css = (FRONTEND / "style.css").read_text(encoding="utf-8")
    video = FRONTEND / "assets" / "video" / "startum-motion-optimized.mp4"
    original_video = FRONTEND / "assets" / "video" / "startum-motion.mp4"
    poster = FRONTEND / "assets" / "images" / "startum-motion-poster.jpg"
    assert 'id="videoModal"' in html and 'data-open-video' in html
    assert 'data-src="assets/video/startum-motion-optimized.mp4"' in html
    assert 'poster="assets/images/startum-motion-poster.jpg"' in html
    assert 'controls' in html and 'playsinline' in html and 'preload="none"' in html
    assert video.is_file() and original_video.is_file() and poster.is_file()
    assert "function openModalVideo()" in script and "function closeModalVideo()" in script
    assert 'addEventListener("error"' in script and 'addEventListener("waiting"' in script
    assert 'video.src = video.dataset.src' in script and 'video.removeAttribute("src")' in script
    assert 'addEventListener("playing"' in script and 'data-close-video' in html
    assert ".video-modal" in css and "aspect-ratio: 9 / 16" in css
    assert "@media (prefers-reduced-motion: reduce)" in css
    review = (ROOT / "docs" / "release-review" / "README.md").read_text(encoding="utf-8")
    assert "Before production publication" in review and "frame-by-frame" in review


def test_obsolete_course_finder_is_removed_but_startum_navigator_remains():
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    script = (FRONTEND / "script.js").read_text(encoding="utf-8")
    css = (FRONTEND / "style.css").read_text(encoding="utf-8") + (FRONTEND / "design-system.css").read_text(encoding="utf-8")
    assert 'id="courseFinderForm"' not in html
    assert 'id="fit"' in html and 'STARTUM NAVIGATOR' in html
    assert "function setupCourseFinder()" not in script
    assert "function buildStudyPlan(" not in script
    assert "course-finder" not in css and "study-plan-" not in css
    assert 'id="subjectsGrid"' in html and 'id="subjectSearch"' in html


def test_application_csv_export_is_role_restricted_bounded_and_audited():
    api = (BACKEND / "api.py").read_text(encoding="utf-8")
    html = (BACKEND / "admin_panel" / "index.html").read_text(encoding="utf-8")
    script = (BACKEND / "admin_panel" / "admin.js").read_text(encoding="utf-8")
    assert '@app.get("/api/admin/applications/export.csv")' in api
    assert 'Depends(require_roles("ceo", "senior_admin"))' in api
    assert "export_limit = 5000" in api
    assert 'applications_exported' in api
    assert 'startswith(("=", "+", "-", "@", "\\t", "\\r"))' in api
    assert 'id="exportApplications"' in html
    assert "async function exportApplications()" in script
    assert "X-Export-Truncated" in script


def test_removed_telegram_ui_keys_and_application_success_translations_are_clean():
    script = (FRONTEND / "script.js").read_text(encoding="utf-8")
    for key in ('"nav.telegram":', '"telegram.title":', '"telegram.exploreText":', '"telegram.applyText":', '"tracker.receiptTitle":'):
        assert key not in script, key
    assert script.count('"footer.telegramLink":') == 3
    for key in ('"form.success":', '"form.invalid":', '"header.languageSelect":', '"header.themeDark":', '"header.menuOpen":'):
        assert script.count(key) == 3, key


def test_language_switch_does_not_fail_when_local_storage_is_unavailable():
    script = (FRONTEND / "script.js").read_text(encoding="utf-8")
    switcher = script.split("function switchLanguage(next)", 1)[1].split("function applyTheme", 1)[0]
    assert "try {" in switcher
    assert 'localStorage.setItem("startumLang", lang)' in switcher
    assert "catch (_storageError)" in switcher


def test_public_and_admin_use_the_shared_onest_inter_typography():
    site_html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    site_css = (FRONTEND / "style.css").read_text(encoding="utf-8")
    light_css = (FRONTEND / "lightmode-aeline.css").read_text(encoding="utf-8")
    design_css = (FRONTEND / "design-system.css").read_text(encoding="utf-8")
    admin_html = (BACKEND / "admin_panel" / "index.html").read_text(encoding="utf-8")
    admin_css = (BACKEND / "admin_panel" / "admin.css").read_text(encoding="utf-8")
    assert "family=Inter" in site_html and "family=Onest" in site_html
    assert "family=Inter" in admin_html and "family=Onest" in admin_html
    assert '"Onest"' in site_css and '"Inter"' in site_css
    assert '"Onest"' in light_css and '"Inter"' in light_css
    assert '"Onest"' in design_css and '"Inter"' in design_css
    assert '"Onest"' in admin_css and '"Inter"' in admin_css
    for css in (site_css, light_css, design_css, admin_css):
        assert "Manrope" not in css and "DM Sans" not in css


def test_teacher_portrait_references_include_the_supplied_german_teacher_image():
    script = (FRONTEND / "script.js").read_text(encoding="utf-8")
    image_dir = FRONTEND / "assets" / "images"
    required = (
        "ustoz-islombek-soatqulov.jpg",
        "nemis-tili-ustoz.png",
        "english-teacher.jpg.jpg",
        "russian-teacher.jpg.jpg",
        "teacher-profile-placeholder.svg",
    )
    for filename in required:
        assert (image_dir / filename).is_file()
    assert not (image_dir / "nemis-tili-ustoz.png.png").exists()
    assert not (image_dir / "turkcha-tarix-teacher.png.jpg").exists()
    assert script.count('img: "assets/images/nemis-tili-ustoz.png"') >= 2
    assert 'name: "Komil Nomozov"' in script
    assert 'credential: "B2"' in script


def test_optimized_video_is_served_and_original_is_preserved():
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    optimized = FRONTEND / "assets" / "video" / "startum-motion-optimized.mp4"
    original = FRONTEND / "assets" / "video" / "startum-motion.mp4"
    assert 'data-src="assets/video/startum-motion-optimized.mp4"' in html
    assert optimized.is_file() and original.is_file()
    assert optimized.stat().st_size < original.stat().st_size
