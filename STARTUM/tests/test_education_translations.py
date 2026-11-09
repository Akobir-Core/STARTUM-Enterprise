from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from education_i18n import TEXT, announcement_preview  # noqa: E402


class EducationTranslationTests(unittest.TestCase):
    def test_all_languages_have_identical_nonempty_keys(self):
        expected = set(TEXT["uz"])
        self.assertTrue(expected)
        self.assertEqual(set(TEXT), {"uz", "ru", "en"})
        for language in ("ru", "en"):
            self.assertEqual(set(TEXT[language]), expected)
        for language, dictionary in TEXT.items():
            for key, value in dictionary.items():
                with self.subTest(language=language, key=key):
                    self.assertTrue(str(value).strip())

    def test_announcement_preview_is_below_telegram_limit_for_escaped_content(self):
        translations = {
            lang: {"title": "&" * 180, "body": "<&>" * 1000}
            for lang in ("uz", "ru", "en")
        }
        preview = announcement_preview(17, translations, "&" * 100)
        self.assertLess(len(preview), 3900)
        self.assertIn("UZ —", preview)
        self.assertIn("RU —", preview)
        self.assertIn("EN —", preview)
        self.assertNotIn("&" * 100, preview)

    def test_preview_does_not_mutate_full_announcement_translations(self):
        translations = {
            lang: {"title": f"Title {lang}", "body": "x" * 3000}
            for lang in ("uz", "ru", "en")
        }
        original = {lang: dict(value) for lang, value in translations.items()}
        preview = announcement_preview(1, translations, "All active users")
        self.assertTrue(preview.endswith("Yuborishni tasdiqlaysizmi?"))
        self.assertEqual(translations, original)
        self.assertEqual(len(translations["uz"]["body"]), 3000)


if __name__ == "__main__":
    unittest.main(verbosity=2)
