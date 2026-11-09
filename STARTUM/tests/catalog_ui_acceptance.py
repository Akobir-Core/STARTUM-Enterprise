"""Browser acceptance for STARTUM's language picker and course catalogue.

The site is loaded into an isolated browser document and the existing /api/catalog
contract is represented by a deterministic test fixture. This verifies frontend
interactions and responsive behavior; it does not claim to verify a live SQLite DB.
"""
from __future__ import annotations

from pathlib import Path
import json
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
VIEWPORTS = [320, 375, 390, 430, 768, 1024, 1280, 1440]
CATALOG_FIXTURE = {
    "courses": [
        {
            "id": 1, "slug": "english", "kind": "subject",
            "name_uz": "Ingliz tili", "name_ru": "Английский язык", "name_en": "English",
            "description_uz": "Kundalik ingliz tili va CEFR tayyorlov",
            "description_ru": "Английский язык и подготовка CEFR",
            "description_en": "Everyday English and CEFR preparation",
            "icon": "EN", "active": 1, "created_at": "2026-01-02T10:00:00+00:00",
        },
        {
            "id": 2, "slug": "math", "kind": "subject",
            "name_uz": "Matematika", "name_ru": "Математика", "name_en": "Mathematics",
            "description_uz": "Mantiq va masalalar", "description_ru": "Логика и задачи",
            "description_en": "Logic and problem solving", "icon": "∑", "active": 1,
            "created_at": "2026-02-02T10:00:00+00:00",
        },
        {
            "id": 3, "slug": "ielts-cefr", "kind": "special",
            "name_uz": "IELTS / CEFR / Multi-level", "name_ru": "IELTS / CEFR / Multi-level",
            "name_en": "IELTS / CEFR / Multi-level", "description_uz": "Til imtihonlariga tayyorlov",
            "description_ru": "Подготовка к языковым экзаменам",
            "description_en": "Language exam preparation", "icon": "IELTS", "active": 1,
            "created_at": "2026-03-02T10:00:00+00:00",
        },
        {
            "id": 4, "slug": "korean", "kind": "subject",
            "name_uz": "Koreys tili", "name_ru": "Корейский язык", "name_en": "Korean",
            "description_uz": "Koreys tili va yozuv", "description_ru": "Корейский язык и письмо",
            "description_en": "Korean language and writing", "icon": "KR", "active": 1,
            "created_at": "2026-04-02T10:00:00+00:00",
        },
    ],
    "teachers": [],
}


def make_document() -> str:
    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    styles = "\n".join(
        f"<style>\n{(ROOT / 'frontend' / filename).read_text(encoding='utf-8')}\n</style>"
        for filename in ("style.css", "lightmode-aeline.css", "design-system.css", "premium-experience.css")
    )
    html = re.sub(r'<link[^>]+rel="stylesheet"[^>]*>', "", html)
    html = html.replace("</head>", styles + "\n</head>")
    script = (ROOT / "frontend" / "script.js").read_text(encoding="utf-8")
    inline_scripts = (
        "<script>window.STARTUM_CONFIG = Object.freeze({apiBaseUrl: 'https://mock.startum.test/api'});</script>"
        f"<script>\n{script}\n</script>"
    )
    html = html.replace(
        '<script src="startum.config.js" defer></script>\n    <script src="script.js" defer></script>',
        inline_scripts,
    )
    return html


def run() -> None:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        print(json.dumps({"status": "NOT TESTED", "reason": f"Playwright unavailable: {exc}"}, ensure_ascii=False))
        raise SystemExit(0)

    results: list[dict] = []
    errors: list[str] = []
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(
                headless=True,
                executable_path="/usr/bin/chromium",
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
        except Exception as exc:
            print(json.dumps({"status": "NOT TESTED", "reason": f"Chromium unavailable: {exc}"}, ensure_ascii=False))
            raise SystemExit(0)

        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page_errors: list[str] = []
        page.on("pageerror", lambda exc: page_errors.append(str(exc)))

        def mock_api(route):
            if route.request.url.endswith("/catalog"):
                payload = CATALOG_FIXTURE
            else:
                payload = {"items": [], "total": 0}
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(payload, ensure_ascii=False),
                headers={"Access-Control-Allow-Origin": "*"},
            )

        page.route("https://mock.startum.test/api/**", mock_api)
        page.set_content(make_document(), wait_until="domcontentloaded")
        page.wait_for_timeout(700)

        # The backend catalogue is mapped into separate subject and programme lists.
        subject_count = page.locator("#subjectsGrid .subject-card").count()
        special_count = page.locator("#specialGrid .special-card").count()
        results.append({"catalog_fixture": {"subjects": subject_count, "special_programs": special_count}})
        if subject_count != 3 or special_count != 1:
            errors.append(f"catalogue response was not rendered as expected: subjects={subject_count}, special={special_count}")
        if page.locator("#subjectEmpty").is_visible():
            errors.append("empty state remained visible while catalogue results existed")

        # Language menu: open, select, escape, and outside click.
        picker_button = page.locator("#languagePickerButton")
        picker_menu = page.locator("#languagePickerMenu")
        picker_button.click()
        if not picker_menu.is_visible() or page.locator("[data-language-option]").count() != 3:
            errors.append("language menu did not open with exactly three languages")
        page.locator('[data-language-option="ru"]').click()
        if page.locator("html").get_attribute("lang") != "ru" or page.locator("#languagePickerCurrent").inner_text() != "RU":
            errors.append("Russian language option did not update the selected language")
        if not picker_menu.is_hidden():
            errors.append("language menu did not close after selecting a language")
        picker_button.click()
        page.keyboard.press("Escape")
        if not picker_menu.is_hidden():
            errors.append("Escape did not close the language menu")
        picker_button.click()
        page.locator("#home").click(position={"x": 10, "y": 10})
        if not picker_menu.is_hidden():
            errors.append("outside click did not close the language menu")
        picker_button.click()
        page.locator('[data-language-option="uz"]').click()
        picker_button.click()
        page.locator('[data-language-option="en"]').click()
        if page.locator("html").get_attribute("lang") != "en" or page.locator("#languagePickerCurrent").inner_text() != "EN":
            errors.append("English language option did not update the selected language")
        picker_button.click()
        page.locator('[data-language-option="uz"]').click()
        results.append({"language_picker": "PASS" if not errors else "CHECK"})

        # Complete, partial, case-insensitive and Cyrillic name search.
        search = page.locator("#subjectSearch")
        search.fill("Ingliz tili")
        page.wait_for_timeout(230)
        names = page.locator("#subjectsGrid .subject-card:visible h3").all_inner_texts()
        if names != ["Ingliz tili"]:
            errors.append(f"full Uzbek course name search returned {names}")
        search.fill("INGLIZ")
        page.wait_for_timeout(230)
        names = page.locator("#subjectsGrid .subject-card:visible h3").all_inner_texts()
        if names != ["Ingliz tili"]:
            errors.append(f"case-insensitive partial search returned {names}")
        search.fill("англий")
        page.wait_for_timeout(230)
        names = page.locator("#subjectsGrid .subject-card:visible h3").all_inner_texts()
        if names != ["Ingliz tili"]:
            errors.append(f"Russian localized name search did not find the Uzbek course record: {names}")
        search.fill("Mathematics")
        page.wait_for_timeout(230)
        names = page.locator("#subjectsGrid .subject-card:visible h3").all_inner_texts()
        if names != ["Matematika"]:
            errors.append(f"English localized name search did not find the Uzbek course record: {names}")
        search.fill("CEFR")
        page.wait_for_timeout(230)
        special_names = page.locator("#specialGrid .special-card:visible strong").all_inner_texts()
        if special_names != ["IELTS / CEFR / Multi-level"]:
            errors.append(f"special-program name/keyword search returned {special_names}")
        results.append({"course_search": "PASS" if len(errors) == 0 else "CHECK"})

        # Scope and category filters work together; special programs are distinct.
        page.locator("#catalogReset").click()
        page.locator("#globalSearchKind").select_option("courses")
        if page.locator("#subjectsGrid .subject-card:visible").count() != 0 or page.locator("#specialGrid .special-card:visible").count() != 1:
            errors.append("course scope did not isolate the special-program list")
        page.locator("#catalogReset").click()
        page.locator('[data-filter="language"]').click()
        if page.locator("#subjectsGrid .subject-card:visible").count() != 2 or page.locator("#specialGrid .special-card:visible").count() != 0:
            errors.append("language category did not filter the subject list correctly")
        page.locator("#catalogReset").click()
        page.locator("#globalSearchSort").select_option("az")
        sorted_names = page.locator("#subjectsGrid .subject-card:visible h3").all_inner_texts()
        if sorted_names != sorted(sorted_names, key=str.casefold):
            errors.append(f"alphabetical sorting returned incorrect order: {sorted_names}")
        page.locator("#globalSearchSort").select_option("newest")
        newest_names = page.locator("#subjectsGrid .subject-card:visible h3").all_inner_texts()
        if newest_names[:2] != ["Koreys tili", "Matematika"]:
            errors.append(f"newest sorting did not respect created_at: {newest_names}")
        results.append({"filters_and_sorting": "PASS" if len(errors) == 0 else "CHECK"})

        # Empty results and a full reset.
        search.fill("no_such_course_987")
        page.wait_for_timeout(230)
        if not page.locator("#subjectEmpty").is_visible():
            errors.append("empty search state was not displayed")
        page.locator("#catalogReset").click()
        if search.input_value() or page.locator("#globalSearchKind").input_value() != "all" or page.locator("#globalSearchSort").input_value() != "relevance":
            errors.append("clear filters did not restore default controls")
        if page.locator("#subjectsGrid .subject-card:visible").count() != 3 or page.locator("#specialGrid .special-card:visible").count() != 1:
            errors.append("clear filters did not restore all catalogue entries")
        if page.locator("#subjectEmpty").is_visible():
            errors.append("empty state was not hidden after clearing filters")
        results.append({"empty_and_reset": "PASS" if len(errors) == 0 else "CHECK"})

        # Check viewport overflow and dropdown placement in both visual themes.
        for theme in ("light", "dark"):
            page.evaluate("(theme) => {document.documentElement.dataset.theme = theme;}", theme)
            for width in VIEWPORTS:
                page.set_viewport_size({"width": width, "height": 900})
                page.wait_for_timeout(70)
                dimensions = page.evaluate("""() => {
                  const selectors = ['.search-main-control', 'label[for="globalSearchKind"]', 'label[for="globalSearchSort"]', '#catalogReset'];
                  const boxes = selectors.map((selector) => {
                    const rect = document.querySelector(selector).getBoundingClientRect();
                    return {selector, x: rect.x, y: rect.y, right: rect.right, bottom: rect.bottom, width: rect.width, height: rect.height};
                  });
                  const searchInput = document.querySelector('#subjectSearch').getBoundingClientRect();
                  return {
                    width: innerWidth,
                    documentWidth: document.documentElement.scrollWidth,
                    bodyWidth: document.body.scrollWidth,
                    searchInputWidth: searchInput.width,
                    controls: boxes
                  };
                }""")
                if dimensions["documentWidth"] > width or dimensions["bodyWidth"] > width:
                    errors.append(f"horizontal overflow at {width}px ({theme}): {dimensions}")
                if dimensions["searchInputWidth"] < 120:
                    errors.append(f"search input is too narrow at {width}px ({theme}): {dimensions}")
                for left_index, left in enumerate(dimensions["controls"]):
                    for right in dimensions["controls"][left_index + 1:]:
                        intersects = left["x"] < right["right"] and left["right"] > right["x"] and left["y"] < right["bottom"] and left["bottom"] > right["y"]
                        if intersects:
                            errors.append(f"search controls overlap at {width}px ({theme}): {left['selector']} / {right['selector']}")
                picker_button.click()
                box = picker_menu.bounding_box()
                if not box or box["x"] < 0 or box["x"] + box["width"] > width + 1:
                    errors.append(f"language menu clipped at {width}px ({theme}): {box}")
                page.keyboard.press("Escape")
                results.append({"viewport": width, "theme": theme, "dimensions": dimensions, "menu_box": box})

        if page_errors:
            errors.extend("page error: " + error for error in page_errors)
        browser.close()
    print(json.dumps({"status": "FAILED" if errors else "PASSED", "results": results, "errors": errors}, ensure_ascii=False, indent=2))
    raise SystemExit(1 if errors else 0)


if __name__ == "__main__":
    run()
