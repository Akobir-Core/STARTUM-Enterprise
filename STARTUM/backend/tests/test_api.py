from __future__ import annotations


def valid_application(**overrides):
    payload = {
        "name": "Akobir Tuygunov",
        "phone": "+998 90 123 45 67",
        "telegram": "@akobir_test",
        "course": "math",
        "message": "Kurs haqida ma’lumot kerak.",
    }
    payload.update(overrides)
    return payload


def test_health_endpoint(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "startum-backend", "database": "ok"}
    assert response.headers["x-content-type-options"] == "nosniff"


def test_catalog_returns_seeded_courses(client):
    response = client.get("/api/catalog")
    assert response.status_code == 200
    catalog = response.json()
    assert any(course["slug"] == "math" for course in catalog["courses"])
    assert "teachers" in catalog


def test_application_rejects_invalid_telegram_username(client):
    response = client.post("/api/applications", json=valid_application(telegram="akobir"))
    assert response.status_code == 422


def test_application_accepts_optional_telegram_username(client):
    response = client.post("/api/applications", json=valid_application(telegram=""))
    assert response.status_code == 201
    assert response.json()["ok"] is True


def test_application_accepts_missing_telegram_username(client):
    payload = valid_application()
    payload.pop("telegram")
    response = client.post("/api/applications", json=payload)
    assert response.status_code == 201
    assert response.json()["ok"] is True


def test_application_rejects_invalid_phone(client):
    response = client.post("/api/applications", json=valid_application(phone="abc123456"))
    assert response.status_code == 422


def test_application_rejects_unknown_course(client):
    response = client.post("/api/applications", json=valid_application(course="not-a-real-course"))
    assert response.status_code == 404


def test_application_is_saved_and_telegram_notification_is_queued(client):
    response = client.post("/api/applications", json=valid_application())
    assert response.status_code == 201
    body = response.json()
    assert body["ok"] is True
    assert body["status"] == "new"
    assert body["notification_status"] == "queued"
    assert "saqlandi" in body["message"].lower()


def test_admin_endpoints_require_a_session(client):
    response = client.get("/api/admin/overview")
    assert response.status_code == 401


def test_admin_login_status_change_and_audit_log(client):
    app_response = client.post("/api/applications", json=valid_application())
    application_id = app_response.json()["id"]

    login_response = client.post("/api/admin/login", json={
        "username": "test-admin",
        "password": "TestOnlyStrongPassword!2026",
    }, headers={"X-STARTUM-Admin": "1"})
    assert login_response.status_code == 200
    assert "httponly" in login_response.headers["set-cookie"].lower()
    assert "samesite=strict" in login_response.headers["set-cookie"].lower()

    overview = client.get("/api/admin/overview")
    assert overview.status_code == 200
    assert overview.json()["web_applications"] == 1

    denied_csrf = client.patch(
        f"/api/admin/applications/website/{application_id}", json={"status": "accepted"}
    )
    assert denied_csrf.status_code == 403

    changed = client.patch(
        f"/api/admin/applications/website/{application_id}",
        json={"status": "accepted"},
        headers={"X-STARTUM-Admin": "1"},
    )
    assert changed.status_code == 200
    assert changed.json()["status"] == "accepted"

    audit = client.get("/api/admin/audit?limit=10")
    assert audit.status_code == 200
    actions = [row["action"] for row in audit.json()["items"]]
    assert "login" in actions
    assert "application_status_updated" in actions


def test_application_workflow_supports_five_requested_states_and_status_history(client):
    submitted = client.post("/api/applications", json=valid_application())
    application_id = submitted.json()["id"]
    login = client.post("/api/admin/login", json={
        "username": "test-admin", "password": "TestOnlyStrongPassword!2026",
    }, headers={"X-STARTUM-Admin": "1"})
    assert login.status_code == 200

    for status in ("in_review", "contacted", "accepted", "rejected"):
        changed = client.patch(
            f"/api/admin/applications/website/{application_id}",
            json={"status": status}, headers={"X-STARTUM-Admin": "1"},
        )
        assert changed.status_code == 200
        assert changed.json()["status"] == status

    filtered = client.get("/api/admin/applications?source=website&status=rejected")
    assert filtered.status_code == 200
    assert [item["status"] for item in filtered.json()["items"]] == ["rejected"]
    history = client.get(f"/api/admin/applications/website/{application_id}/history")
    assert history.status_code == 200
    changes = history.json()["items"]
    assert [(item["old_status"], item["new_status"]) for item in reversed(changes)] == [
        ("new", "in_review"), ("in_review", "contacted"),
        ("contacted", "accepted"), ("accepted", "rejected"),
    ]
    assert all(item["actor"] == "test-admin" and item["created_at"] for item in changes)


def test_application_submission_is_rate_limited(client):
    for _ in range(5):
        client.post("/api/applications", json=valid_application(course="unknown-course"))
    response = client.post("/api/applications", json=valid_application(course="unknown-course"))
    assert response.status_code == 429


def test_admin_can_add_course_and_teacher(client):
    login_response = client.post("/api/admin/login", json={
        "username": "test-admin",
        "password": "TestOnlyStrongPassword!2026",
    }, headers={"X-STARTUM-Admin": "1"})
    assert login_response.status_code == 200

    course_response = client.post("/api/admin/courses", json={
        "kind": "subject",
        "name_uz": "Robototexnika",
        "name_ru": "Робототехника",
        "name_en": "Robotics",
        "description_uz": "Amaliy robototexnika.",
        "description_ru": "Практическая робототехника.",
        "description_en": "Applied robotics.",
        "icon": "🤖",
    }, headers={"X-STARTUM-Admin": "1"})
    assert course_response.status_code == 201
    assert course_response.json()["slug"] == "robototexnika"

    duplicate = client.post("/api/admin/courses", json={
        "kind": "subject", "name_uz": "Robototexnika", "name_ru": "Робототехника", "name_en": "Robotics",
    }, headers={"X-STARTUM-Admin": "1"})
    assert duplicate.status_code == 409

    teacher_response = client.post("/api/admin/teachers", json={
        "full_name": "Sinov Ustoz",
        "subject": "Robototexnika",
        "experience": "5 yil",
        "bio": "Test uchun yaratilgan profil.",
    }, headers={"X-STARTUM-Admin": "1"})
    assert teacher_response.status_code == 201
    catalog = client.get("/api/admin/catalog")
    assert any(item["name_uz"] == "Robototexnika" for item in catalog.json()["courses"])
    assert any(item["full_name"] == "Sinov Ustoz" for item in catalog.json()["teachers"])


def test_web_admin_logout_revokes_server_session(client):
    login = client.post("/api/admin/login", json={
        "username": "test-admin", "password": "TestOnlyStrongPassword!2026",
    }, headers={"X-STARTUM-Admin": "1"})
    assert login.status_code == 200
    assert client.get("/api/admin/session").status_code == 200

    logout = client.post("/api/admin/logout", json={}, headers={"X-STARTUM-Admin": "1"})
    assert logout.status_code == 200
    assert client.get("/api/admin/session").status_code == 401


def test_admin_rejects_forged_session_cookie(client):
    client.cookies.set("startum_admin_session", "forged.payload")
    response = client.get("/api/admin/overview")
    assert response.status_code == 401


def test_admin_login_requires_custom_header_and_throttles_failures(client):
    missing_header = client.post("/api/admin/login", json={
        "username": "test-admin", "password": "wrong-password",
    })
    assert missing_header.status_code == 403

    for _ in range(8):
        result = client.post("/api/admin/login", json={
            "username": "test-admin", "password": "wrong-password",
        }, headers={"X-STARTUM-Admin": "1"})
        assert result.status_code == 401
    blocked = client.post("/api/admin/login", json={
        "username": "test-admin", "password": "TestOnlyStrongPassword!2026",
    }, headers={"X-STARTUM-Admin": "1"})
    assert blocked.status_code == 429


def test_admin_login_throttles_by_account_even_when_ip_fingerprints_change(client, monkeypatch):
    import secrets
    import api as api_module

    monkeypatch.setattr(api_module, "_LOGIN_MAX_FAILURES", 2)
    monkeypatch.setattr(api_module, "_client_fingerprint", lambda _ip: secrets.token_hex(16))
    headers = {"X-STARTUM-Admin": "1"}
    for _ in range(2):
        result = client.post(
            "/api/admin/login",
            json={"username": "account-throttle", "password": "wrong-password"},
            headers=headers,
        )
        assert result.status_code == 401
    blocked = client.post(
        "/api/admin/login",
        json={"username": "account-throttle", "password": "TestOnlyStrongPassword!2026"},
        headers=headers,
    )
    assert blocked.status_code == 429


def test_admin_panel_is_served_with_security_headers(client):
    response = client.get("/admin/")
    assert response.status_code == 200
    assert "STARTUM" in response.text
    assert response.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]


def test_application_rejects_blank_or_overlong_fields(client):
    blank_name = client.post("/api/applications", json=valid_application(name="   "))
    assert blank_name.status_code == 422
    long_message = client.post("/api/applications", json=valid_application(message="x" * 1001))
    assert long_message.status_code == 422


def test_admin_can_add_course_with_non_latin_title(client):
    login = client.post("/api/admin/login", json={
        "username": "test-admin", "password": "TestOnlyStrongPassword!2026",
    }, headers={"X-STARTUM-Admin": "1"})
    assert login.status_code == 200
    response = client.post("/api/admin/courses", json={
        "kind": "subject", "name_uz": "Робототехника",
        "name_ru": "Робототехника", "name_en": "Robotics",
        "description_uz": "Robototexnika kursi.", "icon": "🤖",
    }, headers={"X-STARTUM-Admin": "1"})
    assert response.status_code == 201
    assert response.json()["slug"].startswith("course-")




def _stage_telegram_admin(telegram_id, role="junior_admin"):
    import asyncio
    import api as api_module
    asyncio.run(api_module.db.add_telegram_admin(telegram_id, role, 123456789, active=False))


def _admin_login(client, username="test-admin", password="TestOnlyStrongPassword!2026"):
    return client.post(
        "/api/admin/login",
        json={"username": username, "password": password},
        headers={"X-STARTUM-Admin": "1"},
    )


def test_ceo_can_create_pending_admin_from_website_without_bot_preregistration(client):
    import asyncio
    import api as api_module

    assert _admin_login(client).status_code == 200
    response = client.post(
        "/api/admin/accounts",
        json={
            "username": "website-added-admin",
            "password": "WebsiteAdminPassword2026!",
            "telegram_id": 223456788,
            "role": "junior_admin",
        },
        headers={"X-STARTUM-Admin": "1"},
    )
    assert response.status_code == 201
    assert response.json()["role"] == "junior_admin"
    assert asyncio.run(api_module.db.admin_role(223456788)) is None
    staged = asyncio.run(api_module.db.fetchone(
        "SELECT role,active,pending_link FROM admins WHERE telegram_id=?", (223456788,)
    ))
    assert staged is not None
    assert staged["role"] == "junior_admin"
    assert int(staged["active"]) == 0
    assert int(staged["pending_link"]) == 1

    duplicate = client.post(
        "/api/admin/accounts",
        json={
            "username": "website-added-admin-2",
            "password": "WebsiteAdminPassword2026!",
            "telegram_id": 223456788,
            "role": "junior_admin",
        },
        headers={"X-STARTUM-Admin": "1"},
    )
    assert duplicate.status_code == 409


def test_web_admin_roles_are_enforced_server_side(client):
    root_login = _admin_login(client)
    assert root_login.status_code == 200
    assert root_login.json()["role"] == "ceo"

    _stage_telegram_admin(223456701, "senior_admin")
    senior = client.post(
        "/api/admin/accounts",
        json={"username": "staff-senior", "password": "SeniorPassword2026!", "telegram_id": 223456701, "role": "senior_admin"},
        headers={"X-STARTUM-Admin": "1"},
    )
    assert senior.status_code == 201

    _stage_telegram_admin(223456702, "junior_admin")
    junior = client.post(
        "/api/admin/accounts",
        json={"username": "staff-junior", "password": "JuniorPassword2026!", "telegram_id": 223456702, "role": "junior_admin"},
        headers={"X-STARTUM-Admin": "1"},
    )
    assert junior.status_code == 201

    senior_login = _admin_login(client, "staff-senior", "SeniorPassword2026!")
    assert senior_login.status_code == 200
    assert senior_login.json()["role"] == "senior_admin"

    # Only the CEO can manage administrator accounts.
    created_junior = client.post(
        "/api/admin/accounts",
        json={"username": "junior-by-senior", "password": "JuniorAccess2026!", "telegram_id": 223456703, "role": "junior_admin"},
        headers={"X-STARTUM-Admin": "1"},
    )
    assert created_junior.status_code == 403
    denied_senior = client.post(
        "/api/admin/accounts",
        json={"username": "senior-by-senior", "password": "SeniorAccess2026!", "telegram_id": 223456704, "role": "senior_admin"},
        headers={"X-STARTUM-Admin": "1"},
    )
    assert denied_senior.status_code == 403
    assert client.get("/api/admin/accounts").status_code == 403

    junior_login = _admin_login(client, "staff-junior", "JuniorPassword2026!")
    assert junior_login.status_code == 200
    assert client.get("/api/admin/users").status_code == 200
    assert client.get("/api/admin/overview").status_code == 200
    assert client.get("/api/admin/audit").status_code == 403
    denied_course = client.post(
        "/api/admin/courses",
        json={"kind": "subject", "name_uz": "Junior test", "name_ru": "Junior test", "name_en": "Junior test"},
        headers={"X-STARTUM-Admin": "1"},
    )
    assert denied_course.status_code == 403


def test_deactivating_web_admin_invalidates_existing_session(client):
    assert _admin_login(client).status_code == 200
    _stage_telegram_admin(223456705, "junior_admin")
    created = client.post(
        "/api/admin/accounts",
        json={"username": "temporary-admin", "password": "TemporaryPassword2026!", "telegram_id": 223456705, "role": "junior_admin"},
        headers={"X-STARTUM-Admin": "1"},
    )
    assert created.status_code == 201

    # Keep an independent root session while the first client logs in as the junior admin.
    root_cookie = client.cookies.get("startum_admin_session")
    assert _admin_login(client, "temporary-admin", "TemporaryPassword2026!").status_code == 200
    from fastapi.testclient import TestClient
    import api as api_module
    with TestClient(api_module.app) as root_client:
        root_client.cookies.set("startum_admin_session", root_cookie)
        assert root_client.get("/api/admin/session").status_code == 200
        response = root_client.patch(
            "/api/admin/accounts/temporary-admin/active",
            json={"active": False},
            headers={"X-STARTUM-Admin": "1"},
        )
        assert response.status_code == 200
    assert client.get("/api/admin/overview").status_code == 401
    import asyncio
    import api as api_module
    assert asyncio.run(api_module.db.admin_role(223456705)) is None


def test_catalog_activation_and_search_pagination(client):
    assert _admin_login(client).status_code == 200
    created = client.post(
        "/api/admin/courses",
        json={"kind": "subject", "name_uz": "Robototexnika", "name_ru": "Робототехника", "name_en": "Robotics", "icon": "🤖"},
        headers={"X-STARTUM-Admin": "1"},
    )
    assert created.status_code == 201
    course_id = created.json()["id"]

    inactive = client.patch(
        f"/api/admin/courses/{course_id}/active", json={"active": False}, headers={"X-STARTUM-Admin": "1"}
    )
    assert inactive.status_code == 200
    assert all(c["id"] != course_id for c in client.get("/api/catalog").json()["courses"])
    catalog = client.get("/api/admin/catalog").json()["courses"]
    assert next(c for c in catalog if c["id"] == course_id)["active"] == 0

    for idx in range(3):
        response = client.post(
            "/api/applications",
            json=valid_application(name=f"Akobir Sample {idx}", phone=f"+998 90 123 4{idx} 67"),
        )
        assert response.status_code == 201
    page = client.get("/api/admin/applications?source=website&q=Akobir%20Sample&limit=1&offset=1")
    assert page.status_code == 200
    assert page.json()["total"] == 3
    assert len(page.json()["items"]) == 1
    assert page.json()["offset"] == 1
    assert page.json()["has_more"] is True


def test_account_validation_and_protected_bootstrap_account(client):
    assert _admin_login(client).status_code == 200
    _stage_telegram_admin(223456706, "junior_admin")
    invalid_password = client.post(
        "/api/admin/accounts",
        json={"username": "weak-password", "password": "short", "telegram_id": 223456706, "role": "junior_admin"},
        headers={"X-STARTUM-Admin": "1"},
    )
    assert invalid_password.status_code == 422
    protected = client.patch(
        "/api/admin/accounts/test-admin/active",
        json={"active": False},
        headers={"X-STARTUM-Admin": "1"},
    )
    assert protected.status_code == 409


def test_bootstrap_password_rotation_revokes_existing_sessions(client, monkeypatch):
    import asyncio
    import hashlib
    from dataclasses import replace
    import api as api_module

    login = _admin_login(client, "test-admin", "TestOnlyStrongPassword!2026")
    assert login.status_code == 200
    assert client.get("/api/admin/session").status_code == 200

    new_password = "RotatedTestPassword!2026"
    salt = "pytest-rotation-salt"
    digest = hashlib.pbkdf2_hmac("sha256", new_password.encode(), salt.encode(), 120_000).hex()
    new_hash = f"pbkdf2_sha256$120000${salt}${digest}"
    rotated_config = replace(api_module.config, web_admin_password_hash=new_hash)
    monkeypatch.setattr(api_module, "config", rotated_config)
    asyncio.run(api_module.db.init(
        rotated_config.ceo_owner_id,
        rotated_config.admin_ids,
        web_admin_username="test-admin",
        web_admin_password_hash=new_hash,
    ))

    assert client.get("/api/admin/session").status_code == 401
    new_login = _admin_login(client, "test-admin", new_password)
    assert new_login.status_code == 200
    assert client.get("/api/admin/session").status_code == 200


def test_bootstrap_username_rotation_deactivates_old_account(client, monkeypatch):
    import asyncio
    import hashlib
    from dataclasses import replace
    import api as api_module

    assert _admin_login(client).status_code == 200
    new_username = "new-bootstrap"
    new_password = "NewBootstrapPassword!2026"
    salt = "pytest-username-rotation"
    digest = hashlib.pbkdf2_hmac("sha256", new_password.encode(), salt.encode(), 120_000).hex()
    new_hash = f"pbkdf2_sha256$120000${salt}${digest}"
    rotated_config = replace(
        api_module.config,
        web_admin_username=new_username,
        web_admin_password_hash=new_hash,
    )
    monkeypatch.setattr(api_module, "config", rotated_config)
    asyncio.run(api_module.db.init(
        rotated_config.ceo_owner_id,
        rotated_config.admin_ids,
        web_admin_username=new_username,
        web_admin_password_hash=new_hash,
    ))

    assert client.get("/api/admin/session").status_code == 401
    assert _admin_login(client, "test-admin", "TestOnlyStrongPassword!2026").status_code == 401
    assert _admin_login(client, new_username, new_password).status_code == 200
    accounts = client.get("/api/admin/accounts").json()["items"]
    old = next(item for item in accounts if item["username"] == "test-admin")
    assert old["active"] == 0



def test_duplicate_application_for_same_phone_and_course_is_rejected(client):
    first = client.post("/api/applications", json=valid_application())
    assert first.status_code == 201
    duplicate = client.post("/api/applications", json=valid_application(phone="998-90-123-45-67"))
    assert duplicate.status_code == 409
    assert f"#{first.json()['id']}" in duplicate.json()["detail"]


def test_profile_application_count_is_scoped_to_one_telegram_user(client):
    import asyncio
    from types import SimpleNamespace
    import api as api_module

    async def scenario():
        # Use the API fixture DB through the module's patched database instance.
        first = SimpleNamespace(id=70001, first_name="A", last_name="One", username="a_one")
        second = SimpleNamespace(id=70002, first_name="B", last_name="Two", username="b_two")
        user_a, _ = await api_module.db.ensure_user(first)
        user_b, _ = await api_module.db.ensure_user(second)
        course = await api_module.db.fetchone("SELECT id FROM courses WHERE slug='math'")
        for uid in (int(user_a["id"]), int(user_a["id"]), int(user_b["id"])):
            await api_module.db.create_application(uid, {"full_name":"Test", "phone":"+998901234567", "course_id":int(course["id"]), "level":"", "preferred_time":"", "message":""})
        assert await api_module.db.user_application_count(int(user_a["id"])) == 2
        assert await api_module.db.user_application_count(int(user_b["id"])) == 1

    asyncio.run(scenario())


def test_admin_user_management_search_detail_suspend_restore_and_protect_admins(client):
    import asyncio
    from types import SimpleNamespace
    import api as api_module

    async def create_users():
        student, _ = await api_module.db.ensure_user(
            SimpleNamespace(id=73001, first_name="Dilnoza", last_name="Test", username="dilnoza_student")
        )
        owner, _ = await api_module.db.ensure_user(
            SimpleNamespace(id=123456789, first_name="Admin", last_name="Owner", username="startum_owner")
        )
        return int(student["id"]), int(owner["id"])

    student_id, owner_internal_id = asyncio.run(create_users())
    assert client.get("/api/admin/users").status_code == 401
    assert _admin_login(client).status_code == 200
    headers = {"X-STARTUM-Admin": "1"}

    results = client.get("/api/admin/users?q=dilnoza_student")
    assert results.status_code == 200
    assert results.json()["total"] == 1
    assert results.json()["items"][0]["id"] == student_id
    assert results.json()["items"][0]["account_status"] == "active"

    details = client.get(f"/api/admin/users/{student_id}")
    assert details.status_code == 200
    assert details.json()["user"]["telegram_id"] == 73001
    assert details.json()["applications"] == []
    assert details.json()["moderation_actions"] == []

    suspended = client.patch(
        f"/api/admin/users/{student_id}/status",
        json={"status": "suspended", "reason": "Takroriy spam", "duration_minutes": 60},
        headers=headers,
    )
    assert suspended.status_code == 200
    assert suspended.json()["status"] == "suspended"
    assert suspended.json()["suspended_until"]
    assert asyncio.run(api_module.db.user_access_is_suspended(73001)) is True

    details = client.get(f"/api/admin/users/{student_id}").json()
    assert details["user"]["account_status"] == "suspended"
    assert details["moderation_actions"][0]["actor"] == "test-admin"
    assert details["moderation_actions"][0]["reason"] == "Takroriy spam"

    restored = client.patch(
        f"/api/admin/users/{student_id}/status",
        json={"status": "active", "reason": "Tekshirildi"},
        headers=headers,
    )
    assert restored.status_code == 200
    assert restored.json()["status"] == "active"
    assert asyncio.run(api_module.db.user_access_is_suspended(73001)) is False

    protected_admin = client.patch(
        f"/api/admin/users/{owner_internal_id}/status",
        json={"status": "suspended"},
        headers=headers,
    )
    assert protected_admin.status_code == 409
    audit = client.get("/api/admin/audit?limit=20").json()["items"]
    assert {item["action"] for item in audit} >= {"user_suspend", "user_restore"}


def test_bot_application_status_changes_are_queued_for_durable_delivery(client):
    import asyncio
    from types import SimpleNamespace
    import api as api_module

    async def create_bot_application():
        telegram_user = SimpleNamespace(
            id=712345678, first_name="Sinov", last_name="Foydalanuvchi", username="startum_test_user"
        )
        user_row, _ = await api_module.db.ensure_user(telegram_user)
        course = await api_module.db.fetchone("SELECT id FROM courses WHERE slug='math'")
        application_id, state = await api_module.db.create_application_if_new(
            int(user_row["id"]),
            {
                "full_name": "Sinov Foydalanuvchi", "phone": "+998901112233",
                "course_id": int(course["id"]), "level": "", "preferred_time": "",
                "message": "",
            },
        )
        assert state == "created" and application_id
        return int(application_id)

    application_id = asyncio.run(create_bot_application())
    assert _admin_login(client).status_code == 200
    headers = {"X-STARTUM-Admin": "1"}

    changed = client.patch(
        f"/api/admin/applications/bot/{application_id}",
        json={"status": "accepted"}, headers=headers,
    )
    assert changed.status_code == 200

    async def read_outbox():
        rows = await api_module.db.pending_application_status_notifications(limit=20)
        return [dict(row) for row in rows]

    queued = asyncio.run(read_outbox())
    assert len(queued) == 1
    assert queued[0]["application_id"] == application_id
    assert queued[0]["recipient_telegram_id"] == 712345678
    assert queued[0]["status_name"] == "accepted"

    # Repeating the same status is idempotent and must not send a duplicate notice.
    repeated = client.patch(
        f"/api/admin/applications/bot/{application_id}",
        json={"status": "accepted"}, headers=headers,
    )
    assert repeated.status_code == 200
    assert len(asyncio.run(read_outbox())) == 1


def test_website_status_notification_requires_explicit_telegram_link(client):
    import asyncio
    import api as api_module

    submitted = client.post("/api/applications", json=valid_application())
    assert submitted.status_code == 201
    application_id = int(submitted.json()["id"])

    async def link_telegram_identity():
        await api_module.db.execute(
            "UPDATE web_applications SET identity_provider=?, external_user_id=? WHERE id=?",
            ("telegram", "712345679", application_id),
        )

    asyncio.run(link_telegram_identity())
    assert _admin_login(client).status_code == 200
    changed = client.patch(
        f"/api/admin/applications/website/{application_id}",
        json={"status": "accepted"}, headers={"X-STARTUM-Admin": "1"},
    )
    assert changed.status_code == 200

    async def read_outbox():
        return [dict(row) for row in await api_module.db.pending_application_status_notifications(limit=20)]

    queued = asyncio.run(read_outbox())
    assert len(queued) == 1
    assert queued[0]["source"] == "website"
    assert queued[0]["recipient_telegram_id"] == 712345679


def test_status_notification_outbox_tracks_failed_and_successful_delivery(client):
    import asyncio
    import api as api_module

    async def scenario():
        notification_id = await api_module.db.enqueue_application_status_notification(
            source="bot", application_id=991, recipient_telegram_id=712345678,
            status="in_progress", message_text="Status test",
        )
        first = await api_module.db.pending_application_status_notifications(limit=5)
        assert any(int(row["id"]) == notification_id for row in first)

        await api_module.db.mark_application_status_notification_failed(notification_id, "TimeoutError")
        retry = await api_module.db.pending_application_status_notifications(limit=5)
        row = next(item for item in retry if int(item["id"]) == notification_id)
        assert int(row["attempts"]) == 1
        assert row["last_error"] == "TimeoutError"

        await api_module.db.mark_application_status_notification_sent(notification_id)
        pending = await api_module.db.pending_application_status_notifications(limit=5)
        assert not any(int(item["id"]) == notification_id for item in pending)

    asyncio.run(scenario())


def test_notification_worker_delivers_status_outbox_with_a_bot_adapter(client, monkeypatch):
    import asyncio
    import importlib
    import sys
    from types import ModuleType
    import api as api_module

    keyboard_adapter = ModuleType("keyboards.admin")
    keyboard_adapter.application_actions = lambda _application_id: None
    keyboard_adapter.web_application_actions = lambda _application_id: None
    monkeypatch.setitem(sys.modules, "keyboards.admin", keyboard_adapter)

    class FakeBot:
        def __init__(self):
            self.messages = []

        async def send_message(self, recipient, text, **kwargs):
            self.messages.append((recipient, text))

    bot = FakeBot()

    async def scenario():
        await api_module.db.enqueue_application_status_notification(
            source="bot", application_id=992, recipient_telegram_id=712345679,
            status="accepted", message_text="Arizangiz qabul qilindi.",
        )
        delivery_module = importlib.import_module("notifications")
        result = await delivery_module.deliver_pending_notifications(bot, api_module.db, limit=5)
        assert result["sent"] == 1
        assert result["failed"] == 0
        assert bot.messages == [(712345679, "Arizangiz qabul qilindi.")]
        assert await api_module.db.pending_application_status_notifications(limit=5) == []

    asyncio.run(scenario())


def test_admin_can_edit_catalog_records_and_audit_changes(client):
    assert _admin_login(client).status_code == 200
    course = client.post("/api/admin/courses", json={
        "kind": "subject", "name_uz": "Robototexnika", "name_ru": "Робототехника", "name_en": "Robotics",
        "description_uz": "Boshlang‘ich", "description_ru": "Начальный", "description_en": "Beginner", "icon": "🤖",
    }, headers={"X-STARTUM-Admin": "1"})
    assert course.status_code == 201
    course_id = course.json()["id"]
    updated_course = client.patch(f"/api/admin/courses/{course_id}", json={
        "kind": "special", "name_uz": "Robototexnika Pro", "name_ru": "Робототехника Pro", "name_en": "Robotics Pro",
        "description_uz": "Yangilandi", "description_ru": "Обновлено", "description_en": "Updated", "icon": "🤖",
    }, headers={"X-STARTUM-Admin": "1"})
    assert updated_course.status_code == 200
    assert updated_course.json()["name_uz"] == "Robototexnika Pro"

    teacher = client.post("/api/admin/teachers", json={
        "full_name": "Test Ustoz", "subject": "Matematika", "experience": "3 yil", "bio": "Eski ma’lumot",
    }, headers={"X-STARTUM-Admin": "1"})
    assert teacher.status_code == 201
    teacher_id = teacher.json()["id"]
    updated_teacher = client.patch(f"/api/admin/teachers/{teacher_id}", json={
        "full_name": "Test Ustoz Yangilandi", "subject": "Robototexnika", "experience": "5 yil", "bio": "Yangi ma’lumot",
    }, headers={"X-STARTUM-Admin": "1"})
    assert updated_teacher.status_code == 200
    data = client.get("/api/admin/catalog").json()
    assert next(item for item in data["courses"] if item["id"] == course_id)["name_uz"] == "Robototexnika Pro"
    assert next(item for item in data["teachers"] if item["id"] == teacher_id)["full_name"] == "Test Ustoz Yangilandi"
    audit_actions = [item["action"] for item in client.get("/api/admin/audit?limit=50").json()["items"]]
    assert "course_updated" in audit_actions
    assert "teacher_updated" in audit_actions


def test_admin_catalog_edit_permissions_are_enforced_server_side(client):
    assert _admin_login(client).status_code == 200
    create = client.post("/api/admin/courses", json={
        "kind": "subject", "name_uz": "Robototexnika", "name_ru": "Робототехника", "name_en": "Robotics",
    }, headers={"X-STARTUM-Admin": "1"})
    assert create.status_code == 201
    _stage_telegram_admin(223456709, "junior_admin")
    created = client.post("/api/admin/accounts", json={
        "username": "catalog-junior", "password": "CatalogPassword2026!", "telegram_id": 223456709, "role": "junior_admin",
    }, headers={"X-STARTUM-Admin": "1"})
    assert created.status_code == 201
    assert _admin_login(client, "catalog-junior", "CatalogPassword2026!").status_code == 200
    response = client.patch(f"/api/admin/courses/{create.json()['id']}", json={
        "kind": "subject", "name_uz": "Robototexnika Yangi", "name_ru": "Робототехника Новая", "name_en": "Robotics New",
    }, headers={"X-STARTUM-Admin": "1"})
    assert response.status_code == 403


def test_web_account_link_enables_telegram_admin_only_with_individual_password(client):
    import asyncio
    import api as api_module

    assert _admin_login(client).status_code == 200
    _stage_telegram_admin(223456799, "junior_admin")
    response = client.post(
        "/api/admin/accounts",
        json={
            "username": "linked-admin",
            "password": "LinkedAdminPassword2026!",
            "telegram_id": 223456799,
            "role": "junior_admin",
        },
        headers={"X-STARTUM-Admin": "1"},
    )
    assert response.status_code == 201
    assert asyncio.run(api_module.db.admin_role(223456799)) is None
    linked = asyncio.run(api_module.db.web_admin_by_telegram_id(223456799))
    assert linked is not None and int(linked["active"]) == 1
    assert int(linked["telegram_verified"]) == 0
    assert _admin_login(client, "linked-admin", "LinkedAdminPassword2026!").status_code == 200
    assert asyncio.run(api_module.db.admin_role(223456799)) == "junior_admin"


def test_ceo_can_view_bot_admin_assignments_and_reissue_pending_invitation(client):
    import asyncio
    import api as api_module

    assert _admin_login(client).status_code == 200
    telegram_id = 223456777
    asyncio.run(api_module.db.add_telegram_admin(telegram_id, "junior_admin", 123456789, active=False))

    listing = client.get("/api/admin/telegram-admins")
    assert listing.status_code == 200
    item = next(row for row in listing.json()["items"] if int(row["telegram_id"]) == telegram_id)
    assert item["role"] == "junior_admin"
    assert int(item["active"]) == 0
    assert int(item["bot_invite_pending"]) == 0

    invited = client.post(f"/api/admin/telegram-admins/{telegram_id}/invite", json={}, headers={"X-STARTUM-Admin": "1"})
    assert invited.status_code == 200
    assert invited.json()["status"] == "invitation_pending"
    pending = asyncio.run(api_module.db.fetchone(
        "SELECT active,pending_link,bot_invite_pending FROM admins WHERE telegram_id=?", (telegram_id,)
    ))
    assert tuple(pending) == (0, 1, 1)
    assert asyncio.run(api_module.db.admin_role(telegram_id)) is None


def test_non_ceo_website_admin_cannot_list_or_reissue_bot_admins(client):
    import asyncio
    import api as api_module

    assert _admin_login(client).status_code == 200
    telegram_id = 223456778
    asyncio.run(api_module.db.create_telegram_admin(telegram_id, "senior_admin", 123456789))
    asyncio.run(api_module.db.activate_telegram_admin_invitation(telegram_id))
    asyncio.run(api_module.db.create_web_admin(
        "bot-list-staff", api_module._hash_password("BotListPassword2026!"), "senior_admin",
        "test-admin", telegram_id, 123456789,
    ))
    asyncio.run(api_module.db.mark_telegram_admin_verified("bot-list-staff"))

    from fastapi.testclient import TestClient
    with TestClient(api_module.app) as staff:
        assert _admin_login(staff, "bot-list-staff", "BotListPassword2026!").status_code == 200
        assert staff.get("/api/admin/telegram-admins").status_code == 403
        denied = staff.post(
            f"/api/admin/telegram-admins/{telegram_id}/invite", json={}, headers={"X-STARTUM-Admin": "1"}
        )
        assert denied.status_code == 403


def test_bot_admin_stays_inactive_until_password_account_is_linked(client):
    import asyncio
    import api as api_module

    _stage_telegram_admin(223456798, "junior_admin")
    assert asyncio.run(api_module.db.admin_role(223456798)) is None

    assert _admin_login(client).status_code == 200
    response = client.post(
        "/api/admin/accounts",
        json={
            "username": "pending-linked-admin",
            "password": "PendingLinkedPassword2026!",
            "telegram_id": 223456798,
            "role": "junior_admin",
        },
        headers={"X-STARTUM-Admin": "1"},
    )
    assert response.status_code == 201
    assert asyncio.run(api_module.db.admin_role(223456798)) is None
    assert _admin_login(client, "pending-linked-admin", "PendingLinkedPassword2026!").status_code == 200
    assert asyncio.run(api_module.db.admin_role(223456798)) == "junior_admin"


def test_admin_can_change_own_password_and_bot_access_is_reverified(client):
    import asyncio
    import api as api_module

    assert _admin_login(client).status_code == 200
    _stage_telegram_admin(223456711, "junior_admin")
    created = client.post(
        "/api/admin/accounts",
        json={"username": "password-owner", "password": "OriginalPassword2026!", "telegram_id": 223456711, "role": "junior_admin"},
        headers={"X-STARTUM-Admin": "1"},
    )
    assert created.status_code == 201
    assert _admin_login(client, "password-owner", "OriginalPassword2026!").status_code == 200

    changed = client.post(
        "/api/admin/password/change",
        json={"current_password": "OriginalPassword2026!", "new_password": "ChangedPassword2026!"},
        headers={"X-STARTUM-Admin": "1"},
    )
    assert changed.status_code == 200
    assert client.get("/api/admin/session").status_code == 401
    assert _admin_login(client, "password-owner", "OriginalPassword2026!").status_code == 401
    assert asyncio.run(api_module.db.admin_role(223456711)) is None
    assert _admin_login(client, "password-owner", "ChangedPassword2026!").status_code == 200
    assert asyncio.run(api_module.db.admin_role(223456711)) == "junior_admin"


def test_ceo_password_reset_revokes_sessions_and_requires_new_login(client):
    from fastapi.testclient import TestClient
    import api as api_module

    assert _admin_login(client).status_code == 200
    _stage_telegram_admin(223456712, "junior_admin")
    created = client.post(
        "/api/admin/accounts",
        json={"username": "reset-target", "password": "BeforeResetPassword2026!", "telegram_id": 223456712, "role": "junior_admin"},
        headers={"X-STARTUM-Admin": "1"},
    )
    assert created.status_code == 201
    root_cookie = client.cookies.get("startum_admin_session")
    assert _admin_login(client, "reset-target", "BeforeResetPassword2026!").status_code == 200

    with TestClient(api_module.app) as root_client:
        root_client.cookies.set("startum_admin_session", root_cookie)
        reset = root_client.patch(
            "/api/admin/accounts/reset-target/password",
            json={"password": "AfterResetPassword2026!"},
            headers={"X-STARTUM-Admin": "1"},
        )
        assert reset.status_code == 200
        assert root_client.get("/api/admin/session").status_code == 200

    assert client.get("/api/admin/session").status_code == 401
    assert _admin_login(client, "reset-target", "BeforeResetPassword2026!").status_code == 401
    assert _admin_login(client, "reset-target", "AfterResetPassword2026!").status_code == 200


def test_new_application_returns_private_tracking_code_and_lookup_exposes_minimal_status(client):
    response = client.post("/api/applications", json=valid_application())
    assert response.status_code == 201
    body = response.json()
    code = body["tracking_code"]
    assert len(code) >= 12
    assert "tracking_token_hash" not in body

    lookup = client.post("/api/application-status", json={"tracking_code": code})
    assert lookup.status_code == 200
    result = lookup.json()
    assert result["ok"] is True
    assert result["status"] == "new"
    assert result["course"]
    assert set(result) == {"ok", "status", "course", "created_at"}
    assert "Akobir" not in str(result)
    assert "+998" not in str(result)


def test_application_tracking_reflects_admin_status_changes(client):
    submitted = client.post("/api/applications", json=valid_application())
    code = submitted.json()["tracking_code"]
    application_id = submitted.json()["id"]

    login = client.post("/api/admin/login", json={
        "username": "test-admin",
        "password": "TestOnlyStrongPassword!2026",
    }, headers={"X-STARTUM-Admin": "1"})
    assert login.status_code == 200
    updated = client.patch(
        f"/api/admin/applications/website/{application_id}",
        json={"status": "accepted"},
        headers={"X-STARTUM-Admin": "1"},
    )
    assert updated.status_code == 200

    lookup = client.post("/api/application-status", json={"tracking_code": code})
    assert lookup.status_code == 200
    assert lookup.json()["status"] == "accepted"


def test_application_tracking_rejects_unknown_codes_and_rate_limits(client):
    invalid = client.post("/api/application-status", json={"tracking_code": "short"})
    assert invalid.status_code == 422
    unknown = client.post("/api/application-status", json={"tracking_code": "A1b2C3d4E5f6G7h8"})
    assert unknown.status_code == 404

    for _ in range(9):
        client.post("/api/application-status", json={"tracking_code": "A1b2C3d4E5f6G7h8"})
    limited = client.post("/api/application-status", json={"tracking_code": "A1b2C3d4E5f6G7h8"})
    assert limited.status_code == 429


def test_tracking_hash_is_not_in_web_admin_application_payload(client):
    submitted = client.post("/api/applications", json=valid_application())
    application_id = submitted.json()["id"]
    login = client.post("/api/admin/login", json={
        "username": "test-admin",
        "password": "TestOnlyStrongPassword!2026",
    }, headers={"X-STARTUM-Admin": "1"})
    assert login.status_code == 200
    response = client.get("/api/admin/applications?source=website")
    assert response.status_code == 200
    rows = response.json()["items"]
    target = next(row for row in rows if row["id"] == application_id)
    assert "tracking_token_hash" not in target


def test_application_csv_export_is_bounded_audited_and_role_restricted(client):
    """Senior roles may export; junior roles and anonymous visitors may not."""
    from fastapi.testclient import TestClient
    import api as api_module

    created = client.post("/api/applications", json=valid_application())
    assert created.status_code == 201
    assert client.get("/api/admin/applications/export.csv?source=website").status_code == 401

    assert _admin_login(client).status_code == 200  # test CEO account
    exported = client.get("/api/admin/applications/export.csv?source=website")
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("text/csv")
    assert exported.headers["x-export-count"] == "1"
    assert "Akobir Tuygunov" in exported.text
    # A + leading phone number is neutralized for spreadsheet software.
    assert "'+998 90 123 45 67" in exported.text

    audit = client.get("/api/admin/audit?limit=10")
    assert audit.status_code == 200
    assert any(row["action"] == "applications_exported" for row in audit.json()["items"])

    _stage_telegram_admin(223456731, "senior_admin")
    senior_create = client.post(
        "/api/admin/accounts",
        json={
            "username": "export-senior",
            "password": "SeniorExportPassword2026!",
            "telegram_id": 223456731,
            "role": "senior_admin",
        },
        headers={"X-STARTUM-Admin": "1"},
    )
    assert senior_create.status_code == 201
    with TestClient(api_module.app) as senior_client:
        senior_login = _admin_login(senior_client, "export-senior", "SeniorExportPassword2026!")
        assert senior_login.status_code == 200
        assert senior_client.get("/api/admin/applications/export.csv?source=website").status_code == 200

    _stage_telegram_admin(223456732, "junior_admin")
    junior_create = client.post(
        "/api/admin/accounts",
        json={
            "username": "export-junior",
            "password": "JuniorExportPassword2026!",
            "telegram_id": 223456732,
            "role": "junior_admin",
        },
        headers={"X-STARTUM-Admin": "1"},
    )
    assert junior_create.status_code == 201
    with TestClient(api_module.app) as junior_client:
        junior_login = _admin_login(junior_client, "export-junior", "JuniorExportPassword2026!")
        assert junior_login.status_code == 200
        assert junior_client.get("/api/admin/applications/export.csv?source=website").status_code == 403
