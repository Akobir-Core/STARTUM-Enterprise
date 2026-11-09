from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

class TargetedWebsiteAdminRepairTests(unittest.TestCase):
    def test_official_telegram_channel_is_in_footer_socials_not_header(self):
        html = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
        self.assertIn('href="https://t.me/StartumEducation"', html)
        self.assertIn('class="footer-social-link"', html)
        header = html.split('<header class="topbar', 1)[1].split('</header>', 1)[0]
        self.assertNotIn('StartumEducation', header)

    def test_application_label_removed_but_form_preserved(self):
        html = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
        self.assertNotIn("STARTUM / APPLICATION", html)
        self.assertIn('id="leadForm"', html)

    def test_dark_teacher_photo_overlay_reduced(self):
        css = (ROOT / "frontend/style.css").read_text(encoding="utf-8")
        self.assertIn("rgba(3, 16, 20, 0.34)", css)
        self.assertNotIn("rgba(3, 16, 20, 0.85)", css)

    def test_submit_button_theme_tokens_have_single_source(self):
        css = (ROOT / "frontend/style.css").read_text(encoding="utf-8")
        light = (ROOT / "frontend/lightmode-aeline.css").read_text(encoding="utf-8")
        design = (ROOT / "frontend/design-system.css").read_text(encoding="utf-8")
        self.assertIn("background: var(--action-bg)", css)
        self.assertIn("--action-bg: #123b46", css)
        self.assertNotIn(".btn-mint {", light)
        self.assertNotIn("box-shadow: none;", design.split(".btn {", 1)[1].split("}", 1)[0])


    def test_admin_creation_is_ceo_only_and_protects_owner_ids(self):
        api = (ROOT / "backend/api.py").read_text(encoding="utf-8")
        self.assertIn('actor: str = Depends(require_roles("ceo"))', api)
        self.assertIn('protected_admin_ids = {config.ceo_owner_id, config.owner_telegram_id}', api)
        self.assertIn('le=9_223_372_036_854_775_807', api)

    def test_admin_creation_stages_bot_role_without_upserting_existing_privileges(self):
        db = (ROOT / "backend/database/db.py").read_text(encoding="utf-8")
        method = db.split('async def create_web_admin(', 1)[1].split('async def rotate_web_admin_password(', 1)[0]
        self.assertIn('INSERT INTO admins(telegram_id,role,active,pending_link,created_at,created_by)', method)
        self.assertIn('if existing is None:', method)
        self.assertNotIn('ON CONFLICT(telegram_id) DO UPDATE', method)
        self.assertIn('INSERT INTO web_admin_users', method)

    def test_admin_dialog_posts_only_after_confirmation_and_refreshes_list(self):
        js = (ROOT / "backend/admin_panel/admin.js").read_text(encoding="utf-8")
        self.assertIn("if (!accountReviewStep || accountReviewStep.hidden) return", js)
        self.assertIn("api('/api/admin/accounts'", js)
        self.assertIn("await loadAccounts();", js)
        self.assertIn("await loadAudit();", js)

    def test_social_telegram_label_exists_in_all_three_locales(self):
        js = (ROOT / "frontend/script.js").read_text(encoding="utf-8")
        self.assertEqual(js.count('"footer.telegramLink"'), 3)

    def test_admin_creation_dialog_and_review_stage_exist(self):
        html = (ROOT / "backend/admin_panel/index.html").read_text(encoding="utf-8")
        js = (ROOT / "backend/admin_panel/admin.js").read_text(encoding="utf-8")
        self.assertIn('id="adminCreateDialog"', html)
        self.assertIn('id="accountReviewStep"', html)
        self.assertIn("/api/admin/accounts", js)
        self.assertIn("currentRole !== 'ceo'", js)

if __name__ == "__main__":
    unittest.main()
