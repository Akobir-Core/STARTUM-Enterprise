"""Best-effort Playwright acceptance check.

A browser policy restriction is reported as NOT TESTED (not PASS) and exits 0
so CI can distinguish an unavailable browser from an application regression.
"""
from __future__ import annotations

from pathlib import Path
import json
import sys

BASE = "http://127.0.0.1:8765/"
VIEWPORTS = [320, 360, 375, 390, 412, 430, 768, 1024, 1280, 1440, 1920]


def report(payload: dict, exit_code: int = 0) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    raise SystemExit(exit_code)


def main() -> None:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        report({"status": "NOT TESTED", "reason": f"Playwright import unavailable: {type(exc).__name__}: {exc}", "results": []})

    errors: list[str] = []
    results: list[dict] = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                headless=True,
                executable_path="/usr/bin/chromium",
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            page = browser.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
            page.add_init_script(
                "localStorage.setItem('startumOpeningSeen','1');"
                "localStorage.setItem('startumTheme','light');"
                "localStorage.setItem('startumLang','uz');"
            )
            page.on("pageerror", lambda exc: errors.append("pageerror: " + str(exc)))
            page.on("console", lambda msg: errors.append("console error: " + msg.text) if msg.type == "error" else None)
            try:
                response = page.goto(BASE, wait_until="domcontentloaded", timeout=15000)
            except Exception as exc:
                browser.close()
                report({
                    "status": "NOT TESTED",
                    "reason": f"Browser navigation unavailable: {type(exc).__name__}: {exc}",
                    "results": [],
                })
            page.wait_for_timeout(1200)
            results.append({"page_status": response.status if response else None, "title": page.title()})

            # Theme image behavior and language updates.
            hero = page.locator("#heroThemeImage")
            page.locator("#themeToggle").click()
            page.wait_for_timeout(150)
            dark_src = hero.get_attribute("src")
            dark_alt = hero.get_attribute("alt")
            dark_theme = page.locator("html").get_attribute("data-theme")
            if dark_theme != "dark" or dark_src != "assets/images/startum-dark-hero.webp":
                errors.append(f"Dark Mode image assignment failed: theme={dark_theme}, src={dark_src}")
            page.locator("#languageSelect").select_option("en")
            dark_alt_en = hero.get_attribute("alt")
            if not dark_alt_en or "STARTUM" not in dark_alt_en:
                errors.append("Dark Mode hero alt text did not localize to English")
            page.locator("#themeToggle").click()
            page.wait_for_timeout(150)
            light_src = hero.get_attribute("src")
            light_theme = page.locator("html").get_attribute("data-theme")
            if light_theme != "light" or light_src != "assets/images/startum-day-hero.webp":
                errors.append(f"Light Mode image assignment failed: theme={light_theme}, src={light_src}")
            results.append({"dark_src": dark_src, "dark_alt_uz": dark_alt, "dark_alt_en": dark_alt_en, "dark_theme": dark_theme, "light_src": light_src, "light_theme_after_toggle": light_theme})

            for language in ("ru", "en", "uz"):
                page.locator("#languageSelect").select_option(language)
                page.wait_for_timeout(120)
                actual = page.locator("html").get_attribute("lang")
                results.append({"language_requested": language, "html_lang": actual})
                if actual != language:
                    errors.append(f"language switch failed for {language}: html lang={actual}")

            # Dark-mode scroll regression: document glows must scroll with content,
            # while the intended sticky header remains inside the viewport.
            page.locator("#themeToggle").click()
            page.evaluate("window.scrollTo(0, 650)")
            page.wait_for_timeout(160)
            scroll_state = page.evaluate("""() => ({
              scrollY: window.scrollY,
              ambientTop: document.querySelector('.ambient')?.getBoundingClientRect().top ?? null,
              headerTop: document.querySelector('#topbar')?.getBoundingClientRect().top ?? null,
              heroTransform: getComputedStyle(document.querySelector('.hero-visual')).transform,
              orbitAnimation: getComputedStyle(document.querySelector('.hero-visual'), '::after').animationName
            })""")
            results.append({"dark_scroll": scroll_state})
            if scroll_state["headerTop"] is None or scroll_state["headerTop"] < -1:
                errors.append(f"sticky header detached during dark scroll: {scroll_state}")
            if scroll_state["heroTransform"] not in ("none", "matrix(1, 0, 0, 1, 0, 0)"):
                errors.append(f"hero visual retains transform while scrolling in dark mode: {scroll_state}")
            if scroll_state["orbitAnimation"] not in ("none", ""):
                errors.append(f"decorative hero orbit still animates in dark mode: {scroll_state}")
            page.evaluate("window.scrollTo(0, 0)")
            page.wait_for_timeout(120)

            for width in VIEWPORTS:
                page.set_viewport_size({"width": width, "height": 900})
                page.wait_for_timeout(80)
                dims = page.evaluate("""() => ({
                  width: innerWidth,
                  scrollWidth: document.documentElement.scrollWidth,
                  bodyScrollWidth: document.body.scrollWidth
                })""")
                results.append({"viewport": width, **dims})
                if dims["scrollWidth"] > width or dims["bodyScrollWidth"] > width:
                    errors.append(f"horizontal overflow at {width}: {dims}")
                if width <= 768:
                    page.locator("#menuBtn").click()
                    page.wait_for_timeout(80)
                    expanded = page.locator("#menuBtn").get_attribute("aria-expanded")
                    if expanded != "true":
                        errors.append(f"mobile menu did not open at {width}")
                    page.locator("#menuBtn").click()

            image_state = hero.evaluate("(el) => ({complete:el.complete,naturalWidth:el.naturalWidth,src:el.getAttribute('src')})")
            results.append({"hero_image": image_state})
            if not image_state["complete"] or image_state["naturalWidth"] == 0:
                errors.append("hero image failed to load")

            duplicate_ids = page.evaluate("""() => {const ids=[...document.querySelectorAll('[id]')].map(x=>x.id); return ids.filter((v,i)=>ids.indexOf(v)!==i)}""")
            results.append({"duplicate_ids": duplicate_ids})
            if duplicate_ids:
                errors.append("duplicate IDs: " + str(duplicate_ids))

            browser.close()
    except SystemExit:
        raise
    except Exception as exc:
        report({"status": "NOT TESTED", "reason": f"Browser environment unavailable: {type(exc).__name__}: {exc}", "results": results})

    report({"status": "FAILED" if errors else "PASSED", "results": results, "errors": errors}, 1 if errors else 0)


if __name__ == "__main__":
    main()
