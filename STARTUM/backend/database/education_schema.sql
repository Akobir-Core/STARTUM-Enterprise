-- STARTUM Education Platform extension (additive, database schema version 6).
-- Existing application, user, course, teacher and quiz records are preserved.
CREATE TABLE IF NOT EXISTS education_groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    course_id INTEGER NOT NULL,
    schedule_text TEXT NOT NULL DEFAULT '',
    invite_code TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','archived')),
    created_by INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(course_id) REFERENCES courses(id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS idx_education_groups_course_status
    ON education_groups(course_id, status, id);
CREATE INDEX IF NOT EXISTS idx_education_groups_creator
    ON education_groups(created_by, created_at DESC);

CREATE TABLE IF NOT EXISTS teacher_subject_assignments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL,
    course_id INTEGER NOT NULL,
    group_id INTEGER,
    active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
    created_by INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(telegram_id, course_id, group_id),
    FOREIGN KEY(course_id) REFERENCES courses(id) ON DELETE RESTRICT,
    FOREIGN KEY(group_id) REFERENCES education_groups(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_teacher_assignments_teacher
    ON teacher_subject_assignments(telegram_id, active, course_id);
CREATE INDEX IF NOT EXISTS idx_teacher_assignments_group
    ON teacher_subject_assignments(group_id, active);
CREATE UNIQUE INDEX IF NOT EXISTS idx_teacher_assignments_coursewide_unique
    ON teacher_subject_assignments(telegram_id, course_id) WHERE group_id IS NULL;

CREATE TABLE IF NOT EXISTS group_memberships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','active','rejected','left')),
    requested_at TEXT NOT NULL,
    reviewed_at TEXT,
    reviewed_by INTEGER,
    UNIQUE(group_id, user_id),
    FOREIGN KEY(group_id) REFERENCES education_groups(id) ON DELETE CASCADE,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_group_memberships_user
    ON group_memberships(user_id, status, group_id);
CREATE INDEX IF NOT EXISTS idx_group_memberships_group
    ON group_memberships(group_id, status, requested_at);

CREATE TABLE IF NOT EXISTS homework (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id INTEGER NOT NULL,
    course_id INTEGER NOT NULL,
    teacher_telegram_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    instructions TEXT NOT NULL DEFAULT '',
    attachment_file_id TEXT NOT NULL DEFAULT '',
    deadline_at TEXT,
    status TEXT NOT NULL DEFAULT 'published' CHECK(status IN ('draft','published','archived')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(group_id) REFERENCES education_groups(id) ON DELETE CASCADE,
    FOREIGN KEY(course_id) REFERENCES courses(id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS idx_homework_group_status_deadline
    ON homework(group_id, status, deadline_at);

CREATE TABLE IF NOT EXISTS homework_submissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    homework_id INTEGER NOT NULL,
    student_user_id INTEGER NOT NULL,
    submission_text TEXT NOT NULL DEFAULT '',
    attachment_file_id TEXT NOT NULL DEFAULT '',
    attachment_type TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'submitted' CHECK(status IN ('submitted','under_review','revision_required','graded')),
    grade REAL,
    feedback TEXT NOT NULL DEFAULT '',
    reviewed_by INTEGER,
    submitted_at TEXT NOT NULL,
    reviewed_at TEXT,
    UNIQUE(homework_id, student_user_id),
    FOREIGN KEY(homework_id) REFERENCES homework(id) ON DELETE CASCADE,
    FOREIGN KEY(student_user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_homework_submissions_student
    ON homework_submissions(student_user_id, submitted_at DESC);
CREATE INDEX IF NOT EXISTS idx_homework_submissions_status
    ON homework_submissions(status, homework_id);

CREATE TABLE IF NOT EXISTS homework_submission_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    submission_id INTEGER NOT NULL,
    actor_telegram_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    old_status TEXT,
    new_status TEXT,
    details TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY(submission_id) REFERENCES homework_submissions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS attendance_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id INTEGER NOT NULL,
    course_id INTEGER NOT NULL,
    teacher_telegram_id INTEGER NOT NULL,
    session_date TEXT NOT NULL,
    lesson_ref TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','locked','cancelled')),
    created_at TEXT NOT NULL,
    UNIQUE(group_id, session_date, lesson_ref),
    FOREIGN KEY(group_id) REFERENCES education_groups(id) ON DELETE CASCADE,
    FOREIGN KEY(course_id) REFERENCES courses(id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS idx_attendance_sessions_group_date
    ON attendance_sessions(group_id, session_date DESC);

CREATE TABLE IF NOT EXISTS attendance_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('present','late','absent','excused')),
    note TEXT NOT NULL DEFAULT '',
    marked_by INTEGER NOT NULL,
    marked_at TEXT NOT NULL,
    UNIQUE(session_id, user_id),
    FOREIGN KEY(session_id) REFERENCES attendance_sessions(id) ON DELETE CASCADE,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_attendance_records_user
    ON attendance_records(user_id, session_id);

CREATE TABLE IF NOT EXISTS attendance_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    attendance_record_id INTEGER NOT NULL,
    old_status TEXT,
    new_status TEXT NOT NULL,
    actor_telegram_id INTEGER NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY(attendance_record_id) REFERENCES attendance_records(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS quiz_assignments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    resource_id INTEGER NOT NULL,
    group_id INTEGER NOT NULL,
    available_from TEXT,
    deadline_at TEXT,
    attempt_limit INTEGER NOT NULL DEFAULT 1 CHECK(attempt_limit BETWEEN 1 AND 20),
    results_visible INTEGER NOT NULL DEFAULT 0 CHECK(results_visible IN (0,1)),
    created_by INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(resource_id, group_id),
    FOREIGN KEY(resource_id) REFERENCES learning_resources(id) ON DELETE CASCADE,
    FOREIGN KEY(group_id) REFERENCES education_groups(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_quiz_assignments_group
    ON quiz_assignments(group_id, deadline_at);

CREATE TABLE IF NOT EXISTS announcements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    target_group_id INTEGER,
    status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','scheduled','sending','sent','cancelled')),
    send_at TEXT,
    created_by INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    sent_at TEXT,
    FOREIGN KEY(target_group_id) REFERENCES education_groups(id) ON DELETE SET NULL
);
CREATE TABLE IF NOT EXISTS announcement_translations (
    announcement_id INTEGER NOT NULL,
    language TEXT NOT NULL CHECK(language IN ('uz','ru','en')),
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    PRIMARY KEY(announcement_id, language),
    FOREIGN KEY(announcement_id) REFERENCES announcements(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS announcement_deliveries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    announcement_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','sent','failed','skipped')),
    error_type TEXT NOT NULL DEFAULT '',
    attempts INTEGER NOT NULL DEFAULT 0,
    sent_at TEXT,
    UNIQUE(announcement_id, user_id),
    FOREIGN KEY(announcement_id) REFERENCES announcements(id) ON DELETE CASCADE,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_announcement_deliveries_status
    ON announcement_deliveries(announcement_id, status);

CREATE TABLE IF NOT EXISTS user_notification_preferences (
    user_id INTEGER PRIMARY KEY,
    announcements_enabled INTEGER NOT NULL DEFAULT 1 CHECK(announcements_enabled IN (0,1)),
    lesson_reminders_enabled INTEGER NOT NULL DEFAULT 1 CHECK(lesson_reminders_enabled IN (0,1)),
    homework_enabled INTEGER NOT NULL DEFAULT 1 CHECK(homework_enabled IN (0,1)),
    results_enabled INTEGER NOT NULL DEFAULT 1 CHECK(results_enabled IN (0,1)),
    updated_at TEXT NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS student_certificates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    certificate_code TEXT NOT NULL UNIQUE,
    user_id INTEGER NOT NULL,
    course_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','issued','revoked')),
    issued_by INTEGER,
    file_path TEXT NOT NULL DEFAULT '',
    telegram_file_id TEXT NOT NULL DEFAULT '',
    issue_date TEXT,
    created_at TEXT NOT NULL,
    revoked_at TEXT,
    revoke_reason TEXT NOT NULL DEFAULT '',
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY(course_id) REFERENCES courses(id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS idx_student_certificates_user
    ON student_certificates(user_id, status, created_at DESC);

CREATE TABLE IF NOT EXISTS education_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_telegram_id INTEGER NOT NULL,
    actor_role TEXT NOT NULL,
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id INTEGER,
    details TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_education_audit_actor
    ON education_audit_log(actor_telegram_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_education_audit_entity
    ON education_audit_log(entity_type, entity_id, created_at DESC);

-- Schema v6: academic calendar and an in-app notification inbox.
-- Both tables are additive; existing education and application data is preserved.
CREATE TABLE IF NOT EXISTS academic_calendar_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title_uz TEXT NOT NULL,
    title_ru TEXT NOT NULL,
    title_en TEXT NOT NULL,
    description_uz TEXT NOT NULL DEFAULT '',
    description_ru TEXT NOT NULL DEFAULT '',
    description_en TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT 'event' CHECK(category IN ('lesson','exam','holiday','event','deadline','schedule_change')),
    starts_at TEXT NOT NULL,
    ends_at TEXT,
    location TEXT NOT NULL DEFAULT '',
    target_group_id INTEGER,
    status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','published','archived')),
    reminder_24h INTEGER NOT NULL DEFAULT 1 CHECK(reminder_24h IN (0,1)),
    created_by INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(target_group_id) REFERENCES education_groups(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_calendar_published_start
    ON academic_calendar_events(status, starts_at);
CREATE INDEX IF NOT EXISTS idx_calendar_group_start
    ON academic_calendar_events(target_group_id, status, starts_at);

CREATE TABLE IF NOT EXISTS user_notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    category TEXT NOT NULL CHECK(category IN ('announcements','lesson_reminders','homework','results','system')),
    title TEXT NOT NULL,
    body TEXT NOT NULL DEFAULT '',
    link_type TEXT NOT NULL DEFAULT '',
    link_id INTEGER,
    dedupe_key TEXT NOT NULL,
    read_at TEXT,
    delivery_status TEXT NOT NULL DEFAULT 'pending' CHECK(delivery_status IN ('pending','sent','failed','skipped')),
    delivery_attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT NOT NULL DEFAULT '',
    delivered_at TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(user_id, dedupe_key),
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_user_notifications_inbox
    ON user_notifications(user_id, read_at, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_user_notifications_delivery
    ON user_notifications(delivery_status, created_at);

