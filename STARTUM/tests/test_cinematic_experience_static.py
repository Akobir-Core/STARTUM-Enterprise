from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
JS = (ROOT / "frontend/script.js").read_text(encoding="utf-8")
CSS = (ROOT / "frontend/design-system.css").read_text(encoding="utf-8")


def test_opening_experience_markup_is_accessible_and_skippable():
    assert 'id="startumOpening"' in HTML
    assert 'aria-modal="true"' in HTML
    assert 'aria-labelledby="openingTitle"' in HTML
    assert 'id="skipOpening"' in HTML
    assert 'class="opening-gate opening-gate-left"' in HTML
    assert 'class="opening-gate opening-gate-right"' in HTML
    assert 'class="opening-stairway"' in HTML
    assert 'class="opening-progress"' in HTML
    assert 'id="openingTitle"' in HTML


def test_opening_experience_has_six_second_timeline_and_preview_override():
    assert 'startumOpeningV2Seen' in JS
    assert 'function setupCinematicIntro()' in JS
    assert 'setupCinematicIntro();' in JS
    assert 'params.get("intro") === "preview"' in JS
    assert 'window.setTimeout(finish, 6200)' in JS


def test_opening_restores_page_interaction_and_supports_escape():
    assert 'node.inert = true' in JS
    assert 'node.inert = previousInert[index]' in JS
    assert 'document.addEventListener("keydown", skipOnEscape)' in JS
    assert 'document.removeEventListener("keydown", skipOnEscape)' in JS


def test_opening_has_mobile_and_reduced_motion_rules():
    assert '@media (max-width: 640px)' in CSS
    assert '@media (max-width: 380px)' in CSS
    assert '@media (prefers-reduced-motion: reduce)' in CSS
    assert 'prefers-reduced-motion: reduce' in JS
    assert '.startum-opening .opening-wordmark' in CSS


def test_signature_motion_uses_css_3d_without_extra_3d_library():
    assert 'perspective: 1100px' in CSS
    assert 'rotateX(70deg)' in CSS
    assert 'opening-gate-left' in CSS
    assert 'opening-step-rise' in CSS
    assert 'three.js' not in HTML.lower()


def test_obsolete_course_finder_is_removed_while_video_and_teacher_assets_remain():
    assert 'id="courseFinderForm"' not in HTML
    assert 'id="fit"' in HTML
    assert 'id="videoModal"' in HTML
    assert 'assets/video/startum-motion-optimized.mp4' in HTML
    assert (ROOT / 'frontend/assets/video/startum-motion-optimized.mp4').is_file()
    assert (ROOT / 'frontend/assets/video/startum-motion.mp4').is_file()
    assert 'id="teachersGrid"' in HTML
    assert (ROOT / 'frontend/assets/images/ustoz-islombek-soatqulov.jpg').is_file()
    assert (ROOT / 'frontend/assets/images/startum-day-hero.webp').is_file()


def test_telegram_admin_menu_is_compact_without_changing_callbacks():
    keyboard = (ROOT / "backend/keyboards/admin.py").read_text(encoding="utf-8")
    assert 'callback_data="adm:applications"' in keyboard
    assert 'callback_data="adm:webapps"' in keyboard
    assert 'callback_data="adm:messages"' in keyboard
    assert 'callback_data="adm:resources"' in keyboard
    assert 'callback_data="adm:admins"' in keyboard
    assert 'Compact two-column command centre' in keyboard
