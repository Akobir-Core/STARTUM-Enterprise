from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS))
from catalog_ui_acceptance import make_document  # reuse the isolated fixture and API mock base

VIEWPORTS = [320, 360, 375, 390, 414, 430, 480, 768, 1024, 1280, 1440]


def run() -> None:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        print(json.dumps({"status": "NOT TESTED", "reason": f"Playwright unavailable: {exc}"}))
        raise SystemExit(0)

    mobile_css = (ROOT / "frontend" / "mobile-experience.css").read_text(encoding="utf-8")
    document = make_document().replace("</head>", f"<style>{mobile_css}</style></head>")
    errors: list[str] = []
    results: list[dict] = []

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(
                headless=True,
                executable_path="/usr/bin/chromium",
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
        except Exception as exc:
            print(json.dumps({"status": "NOT TESTED", "reason": f"Chromium unavailable: {exc}"}))
            raise SystemExit(0)

        page = browser.new_page(viewport={"width": 390, "height": 844})
        page_errors: list[str] = []
        page.on("pageerror", lambda exc: page_errors.append(str(exc)))

        def mock_api(route):
            url = route.request.url
            if url.endswith("/catalog"):
                payload = {
                    "courses": [
                        {"id": 1, "slug": "english", "kind": "subject", "name_uz": "Ingliz tili", "name_ru": "Английский язык", "name_en": "English", "description_uz": "CEFR", "description_ru": "CEFR", "description_en": "CEFR", "icon": "EN", "active": 1, "created_at": "2026-01-01T10:00:00+00:00"}
                    ],
                    "teachers": [],
                }
            else:
                payload = {"items": [], "total": 0}
            route.fulfill(status=200, content_type="application/json", body=json.dumps(payload, ensure_ascii=False))

        page.route("https://mock.startum.test/api/**", mock_api)
        page.set_content(document, wait_until="domcontentloaded")
        page.wait_for_timeout(650)

        required_targets = ["home", "subjects", "special", "teachers", "about", "schedule", "contact"]
        for target in required_targets:
            if page.locator(f"#{target}").count() != 1:
                errors.append(f"missing internal navigation target #{target}")
        for link in page.locator(".footer-grid a[href^='#']").all():
            href = link.get_attribute("href") or ""
            target = href[1:]
            if target and page.locator(f"#{target}").count() != 1:
                errors.append(f"footer link points to missing section: {href}")
        if page.locator('.footer-social-link[href*="instagram.com"]').count() != 1:
            errors.append("Instagram footer link is missing")
        if page.locator('.footer-social-link[href*="t.me/StartumEducation"]').count() != 1:
            errors.append("Telegram footer link is missing")
        if page.locator('.footer-grid a[href="privacy.html"]').count() != 1:
            errors.append("Privacy Policy footer link is missing")

        # Real mobile menu interaction in the available browser engine.
        page.set_viewport_size({"width": 390, "height": 844})
        menu = page.locator("#menuBtn")
        nav = page.locator("#mainNav")
        menu.click()
        if menu.get_attribute("aria-expanded") != "true" or not nav.evaluate("el => el.classList.contains('mobile-open')"):
            errors.append("mobile navigation did not open")
        page.keyboard.press("Escape")
        # Existing script may close the drawer on Escape; verify via button state.
        if menu.get_attribute("aria-expanded") == "true":
            errors.append("Escape did not close mobile navigation")

        # Responsive viewport, both themes, footer order and overflow checks.
        for theme in ("light", "dark"):
            page.evaluate("(t) => document.documentElement.setAttribute('data-theme', t)", theme)
            for width in VIEWPORTS:
                page.set_viewport_size({"width": width, "height": 844})
                page.wait_for_timeout(55)
                metrics = page.evaluate("""() => {
                  const root = document.documentElement;
                  const footer = document.querySelector('.footer');
                  const grid = footer?.querySelector('.footer-grid');
                  const columns = grid ? getComputedStyle(grid).gridTemplateColumns.split(' ').length : 0;
                  const footerChildren = grid ? [...grid.children].map(el => {
                    const r = el.getBoundingClientRect();
                    return {top:r.top, bottom:r.bottom, left:r.left, right:r.right, width:r.width};
                  }) : [];
                  const controls = [...document.querySelectorAll('.premium-topbar .top-actions > button, .premium-topbar .language-picker-trigger')]
                    .filter(el => el.getClientRects().length > 0)
                    .map(el => { const r=el.getBoundingClientRect(); return {x:r.x,right:r.right,width:r.width,height:r.height}; });
                  return {viewport:innerWidth, documentWidth:root.scrollWidth, bodyWidth:document.body.scrollWidth,
                    columns, footerChildren, controls,
                    footerSocialCount:document.querySelectorAll('.footer-social-link').length};
                }""")
                if metrics["documentWidth"] > width or metrics["bodyWidth"] > width:
                    errors.append(f"horizontal overflow at {width}px {theme}: {metrics}")
                if width <= 640 and metrics["columns"] != 1:
                    errors.append(f"mobile footer is not stacked at {width}px {theme}: {metrics['columns']} columns")
                for child in metrics["footerChildren"]:
                    if child["left"] < -1 or child["right"] > width + 1:
                        errors.append(f"footer child clipped at {width}px {theme}: {child}")
                if width <= 480:
                    for control in metrics["controls"]:
                        if control["height"] < 40 or control["x"] < -1 or control["right"] > width + 1:
                            errors.append(f"header control outside/tiny at {width}px {theme}: {control}")
                results.append({"width": width, "theme": theme, "footer_columns": metrics["columns"], "document_width": metrics["documentWidth"]})

        if page_errors:
            errors.extend("page error: " + error for error in page_errors)
        browser.close()

    print(json.dumps({"status": "FAILED" if errors else "PASSED", "results": results, "errors": errors}, ensure_ascii=False, indent=2))
    raise SystemExit(1 if errors else 0)


if __name__ == "__main__":
    run()
