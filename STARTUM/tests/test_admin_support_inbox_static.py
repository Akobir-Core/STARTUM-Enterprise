from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_hero_top_actions_do_not_repeat_about_or_application_links():
    html = read("frontend/index.html")
    hero = html.split('<section class="hero"', 1)[1].split('</section>', 1)[0]
    assert 'href="#about"' not in hero
    assert 'class="hero-apply-light"' not in hero
    assert 'id="contact"' in html
    assert 'href="#about"' in html  # About remains elsewhere, not deleted.


def test_web_admin_support_inbox_is_server_protected_and_uses_existing_messages():
    api = read("backend/api.py")
    db = read("backend/database/db.py")
    html = read("backend/admin_panel/index.html")
    js = read("backend/admin_panel/admin.js")
    assert '@app.get("/api/admin/messages")' in api
    route = api.split('@app.get("/api/admin/messages")', 1)[1].split('@app.get("/api/admin/applications")', 1)[0]
    assert 'Depends(require_admin)' in route
    assert 'db.message_list(limit=limit, status=status, search=q.strip())' in route
    assert 'async def message_list(' in db
    assert 'data-view="messages"' in html
    assert 'data-panel="messages"' in html
    assert 'loadMessages' in js
    assert '/api/admin/messages?' in js


def test_support_inbox_query_is_parameterized_and_bounded():
    db = read("backend/database/db.py")
    block = db.split('async def message_list(', 1)[1].split('async def enqueue_support_notifications(', 1)[0]
    assert 'max(1, min(int(limit), 100))' in block
    assert 'WHERE (? IS NULL OR m.status=?)' in block
    assert 'ORDER BY m.id DESC LIMIT ?' in block
    assert 'self.fetchall(' in block
