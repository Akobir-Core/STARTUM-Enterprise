from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import secrets
from typing import Any, Sequence
from zoneinfo import ZoneInfo


def _education_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class EducationDatabaseMixin:
    """Additive education-platform persistence methods for the existing Database class.

    Authorization is still checked by the service/handler before calling these methods.
    Methods that affect teacher-scoped data additionally verify assignments in SQL.
    """

    async def is_teacher(self, telegram_id: int) -> bool:
        return bool(await self.fetchone(
            "SELECT 1 FROM teacher_subject_assignments WHERE telegram_id=? AND active=1 "
            "UNION SELECT 1 FROM teacher_managers WHERE telegram_id=? AND active=1 LIMIT 1",
            (int(telegram_id), int(telegram_id)),
        ))

    async def teacher_assignments(self, telegram_id: int):
        return await self.fetchall(
            "SELECT * FROM ("
            "SELECT tsa.id,tsa.telegram_id,tsa.course_id,tsa.group_id,tsa.active,tsa.created_by,tsa.created_at,"
            "c.name_uz AS course_name,c.name_ru AS course_name_ru,c.name_en AS course_name_en,g.name AS group_name "
            "FROM teacher_subject_assignments tsa JOIN courses c ON c.id=tsa.course_id "
            "LEFT JOIN education_groups g ON g.id=tsa.group_id "
            "WHERE tsa.telegram_id=? AND tsa.active=1 AND c.active=1 "
            "UNION ALL "
            "SELECT -tm.telegram_id AS id,tm.telegram_id,tm.course_id,NULL AS group_id,tm.active,tm.created_by,tm.created_at,"
            "c.name_uz,c.name_ru,c.name_en,NULL AS group_name FROM teacher_managers tm JOIN courses c ON c.id=tm.course_id "
            "WHERE tm.telegram_id=? AND tm.active=1 AND c.active=1 AND NOT EXISTS ("
            "SELECT 1 FROM teacher_subject_assignments x WHERE x.telegram_id=tm.telegram_id AND x.course_id=tm.course_id AND x.active=1)"
            ") ORDER BY course_id,group_id",
            (int(telegram_id), int(telegram_id)),
        )

    async def teacher_has_scope(self, telegram_id: int, course_id: int, group_id: int | None = None) -> bool:
        if group_id is None:
            return bool(await self.fetchone(
                "SELECT 1 FROM teacher_subject_assignments WHERE telegram_id=? AND course_id=? AND active=1 AND group_id IS NULL "
                "UNION SELECT 1 FROM teacher_managers WHERE telegram_id=? AND course_id=? AND active=1 LIMIT 1",
                (int(telegram_id), int(course_id), int(telegram_id), int(course_id)),
            ))
        return bool(await self.fetchone(
            "SELECT 1 FROM teacher_subject_assignments WHERE telegram_id=? AND course_id=? AND active=1 "
            "AND (group_id IS NULL OR group_id=?) "
            "UNION SELECT 1 FROM teacher_managers WHERE telegram_id=? AND course_id=? AND active=1 LIMIT 1",
            (int(telegram_id), int(course_id), int(group_id), int(telegram_id), int(course_id)),
        ))

    async def assign_teacher_subject(
        self, telegram_id: int, course_id: int, created_by: int, group_id: int | None = None,
    ) -> int:
        telegram_id, course_id, created_by = int(telegram_id), int(course_id), int(created_by)
        if telegram_id <= 0 or created_by <= 0:
            raise ValueError("Telegram ID musbat bo‘lishi kerak.")
        if await self.fetchone("SELECT 1 FROM admins WHERE telegram_id=? LIMIT 1", (telegram_id,)):
            raise ValueError("Administratorni ustoz sifatida tayinlab bo‘lmaydi.")
        if not await self.fetchone("SELECT id FROM courses WHERE id=? AND active=1", (course_id,)):
            raise ValueError("Faol fan topilmadi.")
        if group_id is not None:
            group = await self.fetchone(
                "SELECT id,course_id FROM education_groups WHERE id=? AND status='active'", (int(group_id),)
            )
            if not group or int(group["course_id"]) != course_id:
                raise ValueError("Guruh tanlangan fanga tegishli emas.")
        now = _education_now()
        async with self.connect() as db:
            if group_id is None:
                existing = await (await db.execute(
                    "SELECT id FROM teacher_subject_assignments WHERE telegram_id=? AND course_id=? AND group_id IS NULL",
                    (telegram_id, course_id),
                )).fetchone()
            else:
                existing = await (await db.execute(
                    "SELECT id FROM teacher_subject_assignments WHERE telegram_id=? AND course_id=? AND group_id=?",
                    (telegram_id, course_id, int(group_id)),
                )).fetchone()
            if existing:
                assignment_id = int(existing["id"])
                await db.execute(
                    "UPDATE teacher_subject_assignments SET active=1,created_by=?,created_at=? WHERE id=?",
                    (created_by, now, assignment_id),
                )
            else:
                cur = await db.execute(
                    "INSERT INTO teacher_subject_assignments(telegram_id,course_id,group_id,active,created_by,created_at) "
                    "VALUES(?,?,?,1,?,?)",
                    (telegram_id, course_id, int(group_id) if group_id is not None else None, created_by, now),
                )
                assignment_id = int(cur.lastrowid)
            await db.execute(
                "INSERT INTO education_audit_log(actor_telegram_id,actor_role,action,entity_type,entity_id,details,created_at) "
                "VALUES(?, 'admin', 'teacher_subject_assigned', 'teacher_subject_assignment', ?, ?, ?)",
                (created_by, assignment_id, f"teacher={telegram_id};course={course_id};group={group_id or ''}", now),
            )
        return assignment_id

    async def revoke_teacher_assignment(self, assignment_id: int, actor_id: int) -> bool:
        now = _education_now()
        async with self.connect() as db:
            row = await (await db.execute(
                "SELECT telegram_id,course_id,group_id FROM teacher_subject_assignments WHERE id=? AND active=1",
                (int(assignment_id),),
            )).fetchone()
            if not row:
                return False
            await db.execute("UPDATE teacher_subject_assignments SET active=0 WHERE id=?", (int(assignment_id),))
            await db.execute(
                "INSERT INTO education_audit_log(actor_telegram_id,actor_role,action,entity_type,entity_id,details,created_at) "
                "VALUES(?, 'admin', 'teacher_assignment_revoked', 'teacher_subject_assignment', ?, ?, ?)",
                (int(actor_id), int(assignment_id), f"teacher={row['telegram_id']};course={row['course_id']};group={row['group_id'] or ''}", now),
            )
        return True

    async def create_education_group(self, name: str, course_id: int, schedule_text: str, created_by: int) -> dict[str, Any]:
        clean_name = " ".join((name or "").split())[:100]
        clean_schedule = " ".join((schedule_text or "").split())[:240]
        if not 2 <= len(clean_name) <= 100:
            raise ValueError("Guruh nomi 2–100 belgi bo‘lishi kerak.")
        course_id = int(course_id)
        if not await self.fetchone("SELECT id FROM courses WHERE id=? AND active=1", (course_id,)):
            raise ValueError("Faol fan topilmadi.")
        now = _education_now()
        for _ in range(5):
            invite_code = secrets.token_urlsafe(6).replace("-", "").replace("_", "").upper()[:8]
            try:
                group_id = await self.execute(
                    "INSERT INTO education_groups(name,course_id,schedule_text,invite_code,created_by,created_at,updated_at) "
                    "VALUES(?,?,?,?,?,?,?)",
                    (clean_name, course_id, clean_schedule, invite_code, int(created_by), now, now),
                )
                await self.write_education_audit(int(created_by), "admin", "group_created", "education_group", int(group_id), f"name={clean_name};course_id={course_id}")
                return {"id": int(group_id), "name": clean_name, "course_id": course_id, "invite_code": invite_code}
            except Exception as exc:
                if "UNIQUE" not in str(exc).upper():
                    raise
        raise RuntimeError("Taklif kodi yaratilmadi; qayta urinib ko‘ring.")

    async def education_groups(
        self, *, course_id: int | None = None, teacher_id: int | None = None,
        active_only: bool = True, limit: int = 100,
    ):
        clauses: list[str] = []
        params: list[Any] = []
        if active_only:
            clauses.append("g.status='active'")
        if course_id is not None:
            clauses.append("g.course_id=?")
            params.append(int(course_id))
        if teacher_id is not None:
            clauses.append("(EXISTS (SELECT 1 FROM teacher_subject_assignments tsa WHERE tsa.telegram_id=? AND tsa.course_id=g.course_id AND tsa.active=1 AND (tsa.group_id IS NULL OR tsa.group_id=g.id)) "
                            "OR EXISTS (SELECT 1 FROM teacher_managers tm WHERE tm.telegram_id=? AND tm.course_id=g.course_id AND tm.active=1))")
            params.extend((int(teacher_id), int(teacher_id)))
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        params.append(max(1, min(int(limit), 200)))
        return await self.fetchall(
            "SELECT g.*,c.name_uz AS course_name,c.name_ru AS course_name_ru,c.name_en AS course_name_en,"
            "(SELECT COUNT(*) FROM group_memberships gm WHERE gm.group_id=g.id AND gm.status='active') AS student_count "
            "FROM education_groups g JOIN courses c ON c.id=g.course_id" + where + " ORDER BY g.id DESC LIMIT ?",
            tuple(params),
        )

    async def request_group_membership(self, telegram_id: int, invite_code: str) -> str:
        code = "".join((invite_code or "").split()).upper()
        if not 6 <= len(code) <= 10:
            raise ValueError("Guruh kodi noto‘g‘ri.")
        user = await self.fetchone(
            "SELECT id FROM users WHERE telegram_id=? AND account_status='active'", (int(telegram_id),)
        )
        if not user:
            raise ValueError("Avval /start orqali profil yarating.")
        group = await self.fetchone(
            "SELECT id FROM education_groups WHERE invite_code=? AND status='active'", (code,)
        )
        if not group:
            raise ValueError("Guruh kodi topilmadi yoki guruh faol emas.")
        now = _education_now()
        async with self.connect() as db:
            existing = await (await db.execute(
                "SELECT status FROM group_memberships WHERE group_id=? AND user_id=?",
                (int(group["id"]), int(user["id"])),
            )).fetchone()
            if existing and str(existing["status"]) == "active":
                return "active"
            if existing and str(existing["status"]) == "pending":
                return "pending"
            await db.execute(
                "INSERT INTO group_memberships(group_id,user_id,status,requested_at) VALUES(?,?,'pending',?) "
                "ON CONFLICT(group_id,user_id) DO UPDATE SET status='pending',requested_at=excluded.requested_at,reviewed_at=NULL,reviewed_by=NULL",
                (int(group["id"]), int(user["id"]), now),
            )
            await db.execute(
                "INSERT INTO education_audit_log(actor_telegram_id,actor_role,action,entity_type,entity_id,details,created_at) "
                "VALUES(?, 'student', 'group_join_requested', 'education_group', ?, ?, ?)",
                (int(telegram_id), int(group["id"]), f"user_id={int(user['id'])}", now),
            )
        return "pending"

    async def review_group_membership(self, membership_id: int, actor_id: int, approve: bool) -> bool:
        now = _education_now()
        status = "active" if approve else "rejected"
        async with self.connect() as db:
            row = await (await db.execute(
                "SELECT group_id,user_id,status FROM group_memberships WHERE id=?", (int(membership_id),)
            )).fetchone()
            if not row or str(row["status"]) != "pending":
                return False
            await db.execute(
                "UPDATE group_memberships SET status=?,reviewed_at=?,reviewed_by=? WHERE id=?",
                (status, now, int(actor_id), int(membership_id)),
            )
            await db.execute(
                "INSERT INTO education_audit_log(actor_telegram_id,actor_role,action,entity_type,entity_id,details,created_at) "
                "VALUES(?, 'admin', ?, 'group_membership', ?, ?, ?)",
                (int(actor_id), "group_membership_approved" if approve else "group_membership_rejected",
                 int(membership_id), f"group={int(row['group_id'])};user={int(row['user_id'])}", now),
            )
        return True

    async def student_groups(self, telegram_id: int):
        return await self.fetchall(
            "SELECT g.id,g.name,g.schedule_text,g.course_id,c.name_uz AS course_name,c.name_ru AS course_name_ru,"
            "c.name_en AS course_name_en,gm.status AS membership_status FROM group_memberships gm "
            "JOIN users u ON u.id=gm.user_id JOIN education_groups g ON g.id=gm.group_id "
            "JOIN courses c ON c.id=g.course_id WHERE u.telegram_id=? AND gm.status='active' AND g.status='active' "
            "ORDER BY g.name COLLATE NOCASE", (int(telegram_id),),
        )

    async def group_memberships_pending(self, limit: int = 50):
        return await self.fetchall(
            "SELECT gm.id,gm.group_id,gm.user_id,gm.requested_at,u.telegram_id,u.first_name,u.last_name,u.username,"
            "g.name AS group_name,c.name_uz AS course_name FROM group_memberships gm JOIN users u ON u.id=gm.user_id "
            "JOIN education_groups g ON g.id=gm.group_id JOIN courses c ON c.id=g.course_id "
            "WHERE gm.status='pending' ORDER BY gm.requested_at LIMIT ?",
            (max(1, min(int(limit), 100)),),
        )

    async def student_learning_resources(self, telegram_id: int, limit: int = 100):
        return await self.fetchall(
            "SELECT DISTINCT r.id,r.category,r.course_id,r.title,r.description,r.content,r.media_type,r.telegram_file_id,"
            "r.group_id,r.level,r.created_at,c.name_uz AS course_name,g.name AS group_name "
            "FROM users u JOIN group_memberships gm ON gm.user_id=u.id AND gm.status='active' "
            "JOIN education_groups g ON g.id=gm.group_id AND g.status='active' "
            "JOIN learning_resources r ON r.course_id=g.course_id AND r.active=1 AND r.publication_status='published' "
            "AND (r.group_id IS NULL OR r.group_id=g.id) JOIN courses c ON c.id=r.course_id "
            "WHERE u.telegram_id=? ORDER BY r.id DESC LIMIT ?",
            (int(telegram_id), max(1, min(int(limit), 200))),
        )

    async def group_students(self, group_id: int, *, actor_telegram_id: int, limit: int = 200):
        group = await self.fetchone("SELECT course_id FROM education_groups WHERE id=? AND status='active'", (int(group_id),))
        if not group or not await self.teacher_has_scope(int(actor_telegram_id), int(group["course_id"]), int(group_id)):
            raise PermissionError("Bu guruh ma’lumotlarini ko‘rish huquqi yo‘q.")
        return await self.fetchall(
            "SELECT u.id,u.telegram_id,u.first_name,u.last_name,u.username,gm.requested_at AS joined_at FROM group_memberships gm "
            "JOIN users u ON u.id=gm.user_id WHERE gm.group_id=? AND gm.status='active' "
            "ORDER BY u.first_name,u.last_name LIMIT ?",
            (int(group_id), max(1, min(int(limit), 300))),
        )

    async def teacher_homework_submissions(self, teacher_telegram_id: int, limit: int = 100):
        return await self.fetchall(
            "SELECT hs.id,hs.status,hs.submitted_at,hs.grade,hs.feedback,hs.submission_text,hs.attachment_file_id,hs.attachment_type,"
            "u.telegram_id,u.first_name,u.last_name,h.title AS homework_title,h.group_id,g.name AS group_name,c.id AS course_id,c.name_uz AS course_name "
            "FROM homework_submissions hs JOIN homework h ON h.id=hs.homework_id JOIN education_groups g ON g.id=h.group_id "
            "JOIN courses c ON c.id=h.course_id JOIN users u ON u.id=hs.student_user_id "
            "WHERE (EXISTS (SELECT 1 FROM teacher_subject_assignments tsa WHERE tsa.telegram_id=? AND tsa.course_id=h.course_id AND tsa.active=1 AND (tsa.group_id IS NULL OR tsa.group_id=h.group_id)) "
            "OR EXISTS (SELECT 1 FROM teacher_managers tm WHERE tm.telegram_id=? AND tm.course_id=h.course_id AND tm.active=1)) "
            "ORDER BY hs.submitted_at DESC LIMIT ?",
            (int(teacher_telegram_id), int(teacher_telegram_id), max(1, min(int(limit), 200))),
        )

    async def create_homework(
        self, *, group_id: int, teacher_telegram_id: int, title: str, instructions: str = "",
        deadline_at: str | None = None, attachment_file_id: str = "", status: str = "published",
    ) -> int:
        clean_title = " ".join((title or "").split())[:180]
        if not 2 <= len(clean_title) <= 180 or status not in {"draft", "published"}:
            raise ValueError("Vazifa nomi yoki holati noto‘g‘ri.")
        group = await self.fetchone(
            "SELECT id,course_id FROM education_groups WHERE id=? AND status='active'", (int(group_id),)
        )
        if not group:
            raise ValueError("Faol guruh topilmadi.")
        if not await self.teacher_has_scope(int(teacher_telegram_id), int(group["course_id"]), int(group_id)):
            raise PermissionError("Bu guruh sizga biriktirilmagan.")
        now = _education_now()
        homework_id = int(await self.execute(
            "INSERT INTO homework(group_id,course_id,teacher_telegram_id,title,instructions,attachment_file_id,deadline_at,status,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?)",
            (int(group_id), int(group["course_id"]), int(teacher_telegram_id), clean_title,
             (instructions or "").strip()[:3000], (attachment_file_id or "").strip()[:255], deadline_at, status, now, now),
        ))
        if status == "published":
            localized = {
                "uz": {"title": "Yangi uy vazifasi", "body": clean_title},
                "ru": {"title": "Новое домашнее задание", "body": clean_title},
                "en": {"title": "New homework", "body": clean_title},
            }
            await self.notify_group_members(
                int(group_id), category="homework", localized=localized,
                dedupe_prefix=f"homework:{homework_id}", link_type="homework", link_id=homework_id,
            )
        return homework_id

    async def homework_for_groups(self, group_ids: Sequence[int], *, published_only: bool = True, limit: int = 100):
        ids = [int(value) for value in group_ids if int(value) > 0]
        if not ids:
            return []
        placeholders = ",".join("?" for _ in ids)
        where = " AND h.status='published'" if published_only else ""
        return await self.fetchall(
            "SELECT h.*,g.name AS group_name,c.name_uz AS course_name FROM homework h "
            "JOIN education_groups g ON g.id=h.group_id JOIN courses c ON c.id=h.course_id "
            f"WHERE h.group_id IN ({placeholders}){where} ORDER BY COALESCE(h.deadline_at,'9999-12-31') ASC,h.id DESC LIMIT ?",
            tuple(ids + [max(1, min(int(limit), 200))]),
        )

    async def submit_homework(
        self, *, homework_id: int, student_telegram_id: int, submission_text: str = "", attachment_file_id: str = "", attachment_type: str = "",
    ) -> int:
        user = await self.fetchone(
            "SELECT id FROM users WHERE telegram_id=? AND account_status='active'", (int(student_telegram_id),)
        )
        if not user:
            raise ValueError("Faol foydalanuvchi topilmadi.")
        homework_row = await self.fetchone(
            "SELECT id,group_id,status FROM homework WHERE id=?", (int(homework_id),)
        )
        if not homework_row or str(homework_row["status"]) != "published":
            raise ValueError("Vazifa mavjud emas yoki e’lon qilinmagan.")
        membership = await self.fetchone(
            "SELECT 1 FROM group_memberships WHERE group_id=? AND user_id=? AND status='active'",
            (int(homework_row["group_id"]), int(user["id"])),
        )
        if not membership:
            raise PermissionError("Bu vazifa sizning faol guruhingizga tegishli emas.")
        if not ((submission_text or "").strip() or (attachment_file_id or "").strip()):
            raise ValueError("Matn yoki qo‘llab-quvvatlanadigan fayl yuboring.")
        now = _education_now()
        async with self.connect() as db:
            existing = await (await db.execute(
                "SELECT id,status FROM homework_submissions WHERE homework_id=? AND student_user_id=?",
                (int(homework_id), int(user["id"])),
            )).fetchone()
            if existing and str(existing["status"]) == "graded":
                raise ValueError("Baholangan vazifani qayta yuborib bo‘lmaydi.")
            if existing:
                submission_id = int(existing["id"])
                await db.execute(
                    "UPDATE homework_submissions SET submission_text=?,attachment_file_id=?,attachment_type=?,status='submitted',submitted_at=?,reviewed_by=NULL,reviewed_at=NULL WHERE id=?",
                    ((submission_text or "").strip()[:5000], (attachment_file_id or "").strip()[:255], (attachment_type or "")[:24], now, submission_id),
                )
                action = "resubmitted"
            else:
                cur = await db.execute(
                    "INSERT INTO homework_submissions(homework_id,student_user_id,submission_text,attachment_file_id,attachment_type,status,submitted_at) VALUES(?,?,?,?,?,'submitted',?)",
                    (int(homework_id), int(user["id"]), (submission_text or "").strip()[:5000], (attachment_file_id or "").strip()[:255], (attachment_type or "")[:24], now),
                )
                submission_id, action = int(cur.lastrowid), "submitted"
            await db.execute(
                "INSERT INTO homework_submission_history(submission_id,actor_telegram_id,action,new_status,created_at) VALUES(?,?,?,?,?)",
                (submission_id, int(student_telegram_id), action, "submitted", now),
            )
        return submission_id

    async def review_homework_submission(
        self, *, submission_id: int, teacher_telegram_id: int, status: str,
        grade: float | None = None, feedback: str = "",
    ) -> bool:
        if status not in {"under_review", "revision_required", "graded"}:
            raise ValueError("Tekshiruv holati noto‘g‘ri.")
        if grade is not None and not 0 <= float(grade) <= 100:
            raise ValueError("Baho 0–100 oralig‘ida bo‘lishi kerak.")
        now = _education_now()
        async with self.connect() as db:
            row = await (await db.execute(
                "SELECT hs.status,h.group_id,h.course_id FROM homework_submissions hs "
                "JOIN homework h ON h.id=hs.homework_id WHERE hs.id=?", (int(submission_id),)
            )).fetchone()
            if not row:
                return False
            assignment = await (await db.execute(
                "SELECT 1 FROM teacher_subject_assignments WHERE telegram_id=? AND course_id=? AND active=1 AND (group_id IS NULL OR group_id=?) "
                "UNION SELECT 1 FROM teacher_managers WHERE telegram_id=? AND course_id=? AND active=1 LIMIT 1",
                (int(teacher_telegram_id), int(row["course_id"]), int(row["group_id"]), int(teacher_telegram_id), int(row["course_id"])),
            )).fetchone()
            if not assignment:
                raise PermissionError("Bu guruh sizga biriktirilmagan.")
            await db.execute(
                "UPDATE homework_submissions SET status=?,grade=?,feedback=?,reviewed_by=?,reviewed_at=? WHERE id=?",
                (status, grade, (feedback or "").strip()[:2000], int(teacher_telegram_id), now if status == "graded" else None, int(submission_id)),
            )
            await db.execute(
                "INSERT INTO homework_submission_history(submission_id,actor_telegram_id,action,old_status,new_status,details,created_at) VALUES(?,?,?,?,?,?,?)",
                (int(submission_id), int(teacher_telegram_id), "reviewed", str(row["status"]), status, f"grade={grade}", now),
            )
            student = await (await db.execute(
                "SELECT u.id,u.language FROM homework_submissions hs JOIN users u ON u.id=hs.student_user_id WHERE hs.id=?",
                (int(submission_id),),
            )).fetchone()
            if student:
                lang = str(student["language"] or "uz")
                labels = {
                    "uz": {"title": "Uy vazifasi tekshirildi", "body": f"Holat: {status}. Baho: {grade if grade is not None else '—'}. {(feedback or '').strip()[:500]}"},
                    "ru": {"title": "Домашнее задание проверено", "body": f"Статус: {status}. Оценка: {grade if grade is not None else '—'}. {(feedback or '').strip()[:500]}"},
                    "en": {"title": "Homework reviewed", "body": f"Status: {status}. Grade: {grade if grade is not None else '—'}. {(feedback or '').strip()[:500]}"},
                }
                item = labels.get(lang, labels["uz"])
                pref_col = "results_enabled" if status == "graded" else "homework_enabled"
                await db.execute(
                    "INSERT OR IGNORE INTO user_notifications(user_id,category,title,body,link_type,link_id,dedupe_key,delivery_status,created_at) "
                    "SELECT ?,?,?,?,?,?,?, 'pending',? WHERE COALESCE((SELECT " + pref_col + " FROM user_notification_preferences WHERE user_id=?),1)=1",
                    (int(student["id"]), "results" if status == "graded" else "homework", item["title"], item["body"],
                     "homework_submission", int(submission_id), f"homework-review:{int(submission_id)}:{status}", now, int(student["id"])),
                )
        return True

    async def create_attendance_session(self, *, group_id: int, teacher_telegram_id: int, session_date: str, lesson_ref: str = "") -> int:
        group = await self.fetchone(
            "SELECT course_id FROM education_groups WHERE id=? AND status='active'", (int(group_id),)
        )
        if not group:
            raise ValueError("Faol guruh topilmadi.")
        if not await self.teacher_has_scope(int(teacher_telegram_id), int(group["course_id"]), int(group_id)):
            raise PermissionError("Bu guruh sizga biriktirilmagan.")
        try:
            date.fromisoformat(session_date)
        except ValueError as exc:
            raise ValueError("Sana YYYY-MM-DD formatida bo‘lishi kerak.") from exc
        try:
            return int(await self.execute(
                "INSERT INTO attendance_sessions(group_id,course_id,teacher_telegram_id,session_date,lesson_ref,created_at) VALUES(?,?,?,?,?,?)",
                (int(group_id), int(group["course_id"]), int(teacher_telegram_id), session_date, lesson_ref.strip()[:80], _education_now()),
            ))
        except Exception as exc:
            if "UNIQUE" in str(exc).upper():
                raise ValueError("Bu guruh uchun ushbu sanada davomat allaqachon yaratilgan.") from exc
            raise

    async def mark_attendance(self, *, session_id: int, actor_telegram_id: int, student_user_id: int, status: str, reason: str = "") -> bool:
        if status not in {"present", "late", "absent", "excused"}:
            raise ValueError("Davomat holati noto‘g‘ri.")
        now = _education_now()
        async with self.connect() as db:
            session = await (await db.execute(
                "SELECT group_id,course_id,status FROM attendance_sessions WHERE id=?", (int(session_id),)
            )).fetchone()
            if not session or str(session["status"]) != "open":
                raise ValueError("Davomat sessiyasi topilmadi yoki yopilgan.")
            assignment = await (await db.execute(
                "SELECT 1 FROM teacher_subject_assignments WHERE telegram_id=? AND course_id=? AND active=1 AND (group_id IS NULL OR group_id=?) "
                "UNION SELECT 1 FROM teacher_managers WHERE telegram_id=? AND course_id=? AND active=1 LIMIT 1",
                (int(actor_telegram_id), int(session["course_id"]), int(session["group_id"]), int(actor_telegram_id), int(session["course_id"])),
            )).fetchone()
            if not assignment:
                raise PermissionError("Davomat belgilash huquqi yo‘q.")
            member = await (await db.execute(
                "SELECT 1 FROM group_memberships WHERE group_id=? AND user_id=? AND status='active'",
                (int(session["group_id"]), int(student_user_id)),
            )).fetchone()
            if not member:
                raise PermissionError("O‘quvchi ushbu guruh a’zosi emas.")
            existing = await (await db.execute(
                "SELECT id,status FROM attendance_records WHERE session_id=? AND user_id=?",
                (int(session_id), int(student_user_id)),
            )).fetchone()
            if existing:
                await db.execute(
                    "UPDATE attendance_records SET status=?,note=?,marked_by=?,marked_at=? WHERE id=?",
                    (status, (reason or "").strip()[:500], int(actor_telegram_id), now, int(existing["id"])),
                )
                await db.execute(
                    "INSERT INTO attendance_history(attendance_record_id,old_status,new_status,actor_telegram_id,reason,created_at) VALUES(?,?,?,?,?,?)",
                    (int(existing["id"]), str(existing["status"]), status, int(actor_telegram_id), (reason or "").strip()[:500], now),
                )
            else:
                await db.execute(
                    "INSERT INTO attendance_records(session_id,user_id,status,note,marked_by,marked_at) VALUES(?,?,?,?,?,?)",
                    (int(session_id), int(student_user_id), status, (reason or "").strip()[:500], int(actor_telegram_id), now),
                )
        return True

    async def student_attendance(self, telegram_id: int, limit: int = 100):
        return await self.fetchall(
            "SELECT ar.status,ar.note,ar.marked_at,s.session_date,s.lesson_ref,g.name AS group_name,c.name_uz AS course_name "
            "FROM attendance_records ar JOIN attendance_sessions s ON s.id=ar.session_id JOIN education_groups g ON g.id=s.group_id "
            "JOIN courses c ON c.id=s.course_id JOIN users u ON u.id=ar.user_id WHERE u.telegram_id=? ORDER BY s.session_date DESC LIMIT ?",
            (int(telegram_id), max(1, min(int(limit), 200))),
        )

    async def student_homework_submissions(self, telegram_id: int, limit: int = 100):
        return await self.fetchall(
            "SELECT hs.id,hs.status,hs.grade,hs.feedback,hs.submitted_at,h.title,h.deadline_at,g.name AS group_name,c.name_uz AS course_name "
            "FROM homework_submissions hs JOIN homework h ON h.id=hs.homework_id JOIN education_groups g ON g.id=h.group_id "
            "JOIN courses c ON c.id=h.course_id JOIN users u ON u.id=hs.student_user_id WHERE u.telegram_id=? ORDER BY hs.submitted_at DESC LIMIT ?",
            (int(telegram_id), max(1, min(int(limit), 200))),
        )

    async def create_quiz_assignment(
        self, *, resource_id: int, group_id: int, created_by: int, available_from: str | None = None,
        deadline_at: str | None = None, attempt_limit: int = 1,
        actor_teacher_id: int | None = None,
    ) -> int:
        if not 1 <= int(attempt_limit) <= 20:
            raise ValueError("Urinish soni 1–20 oralig‘ida bo‘lishi kerak.")
        resource = await self.learning_resource(int(resource_id), active_only=True)
        group = await self.fetchone("SELECT id,course_id FROM education_groups WHERE id=? AND status='active'", (int(group_id),))
        if not resource or resource["category"] != "quiz" or not group or int(resource["course_id"]) != int(group["course_id"]):
            raise ValueError("Test va guruh mosligi tasdiqlanmadi.")
        if actor_teacher_id is not None and not await self.teacher_has_scope(
            int(actor_teacher_id), int(group["course_id"]), int(group_id)
        ):
            raise PermissionError("Bu guruh uchun test tayinlash huquqi yo‘q.")
        now = _education_now()
        async with self.connect() as db:
            existing = await (await db.execute(
                "SELECT id FROM quiz_assignments WHERE resource_id=? AND group_id=?", (int(resource_id), int(group_id))
            )).fetchone()
            if existing:
                await db.execute(
                    "UPDATE quiz_assignments SET available_from=?,deadline_at=?,attempt_limit=?,created_by=? WHERE id=?",
                    (available_from, deadline_at, int(attempt_limit), int(created_by), int(existing["id"])),
                )
                return int(existing["id"])
            cur = await db.execute(
                "INSERT INTO quiz_assignments(resource_id,group_id,available_from,deadline_at,attempt_limit,created_by,created_at) VALUES(?,?,?,?,?,?,?)",
                (int(resource_id), int(group_id), available_from, deadline_at, int(attempt_limit), int(created_by), now),
            )
            return int(cur.lastrowid)

    async def student_quiz_assignments(self, telegram_id: int, limit: int = 100):
        now = _education_now()
        return await self.fetchall(
            "SELECT qa.id,qa.resource_id,qa.group_id,qa.available_from,qa.deadline_at,qa.attempt_limit,qa.results_visible,"
            "r.title,r.course_id,g.name AS group_name,c.name_uz AS course_name,"
            "(SELECT COUNT(*) FROM quiz_attempts a JOIN users au ON au.id=a.user_id "
            " WHERE au.telegram_id=? AND a.resource_id=qa.resource_id) AS attempts_done "
            "FROM quiz_assignments qa JOIN learning_resources r ON r.id=qa.resource_id "
            "JOIN education_groups g ON g.id=qa.group_id JOIN courses c ON c.id=r.course_id "
            "JOIN group_memberships gm ON gm.group_id=g.id AND gm.status='active' "
            "JOIN users u ON u.id=gm.user_id WHERE u.telegram_id=? AND r.active=1 AND r.publication_status='published' "
            "AND (qa.available_from IS NULL OR qa.available_from<=?) "
            "AND (qa.deadline_at IS NULL OR qa.deadline_at>=?) "
            "AND (SELECT COUNT(*) FROM quiz_attempts a JOIN users au ON au.id=a.user_id "
            " WHERE au.telegram_id=? AND a.resource_id=qa.resource_id)<qa.attempt_limit "
            "ORDER BY COALESCE(qa.deadline_at,'9999-12-31'),qa.id DESC LIMIT ?",
            (int(telegram_id), int(telegram_id), now, now, int(telegram_id), max(1, min(int(limit), 200))),
        )

    async def quiz_assignment_access(self, telegram_id: int, resource_id: int) -> dict[str, Any]:
        """Return a student's access to an assigned quiz; legacy unassigned quizzes remain available."""
        now = _education_now()
        assigned = await self.fetchone(
            "SELECT COUNT(*) AS total FROM quiz_assignments WHERE resource_id=?", (int(resource_id),)
        )
        if not assigned or int(assigned["total"] or 0) == 0:
            return {"allowed": True, "assigned": False, "attempts_done": 0, "attempt_limit": None}
        row = await self.fetchone(
            "SELECT qa.id,qa.group_id,qa.attempt_limit,qa.available_from,qa.deadline_at,"
            "(SELECT COUNT(*) FROM quiz_attempts a JOIN users au ON au.id=a.user_id "
            " WHERE au.telegram_id=? AND a.resource_id=qa.resource_id) AS attempts_done "
            "FROM quiz_assignments qa JOIN group_memberships gm ON gm.group_id=qa.group_id AND gm.status='active' "
            "JOIN users u ON u.id=gm.user_id WHERE u.telegram_id=? AND qa.resource_id=? "
            "AND (qa.available_from IS NULL OR qa.available_from<=?) "
            "AND (qa.deadline_at IS NULL OR qa.deadline_at>=?) ORDER BY qa.id DESC LIMIT 1",
            (int(telegram_id), int(telegram_id), int(resource_id), now, now),
        )
        if not row:
            return {"allowed": False, "assigned": True, "attempts_done": 0, "attempt_limit": 0}
        attempts_done = int(row["attempts_done"] or 0)
        attempt_limit = int(row["attempt_limit"] or 1)
        return {"allowed": attempts_done < attempt_limit, "assigned": True,
                "attempts_done": attempts_done, "attempt_limit": attempt_limit,
                "group_id": int(row["group_id"])}

    async def set_resource_publication(self, resource_id: int, status: str, actor_id: int) -> bool:
        if status not in {"published", "rejected", "archived"}:
            raise ValueError("Material holati noto‘g‘ri.")
        now = _education_now()
        async with self.connect() as db:
            row = await (await db.execute("SELECT id FROM learning_resources WHERE id=?", (int(resource_id),))).fetchone()
            if not row:
                return False
            await db.execute(
                "UPDATE learning_resources SET publication_status=?,active=? WHERE id=?",
                (status, 1 if status == "published" else 0, int(resource_id)),
            )
            await db.execute(
                "INSERT INTO education_audit_log(actor_telegram_id,actor_role,action,entity_type,entity_id,details,created_at) VALUES(?, 'admin', ?, 'learning_resource', ?, ?, ?)",
                (int(actor_id), f"resource_{status}", int(resource_id), status, now),
            )
        return True

    async def pending_learning_resources(self, limit: int = 100):
        return await self.fetchall(
            "SELECT r.id,r.category,r.course_id,r.title,r.description,r.media_type,r.created_by_telegram_id,r.created_at,c.name_uz AS course_name "
            "FROM learning_resources r JOIN courses c ON c.id=r.course_id WHERE r.publication_status='pending' ORDER BY r.id LIMIT ?",
            (max(1, min(int(limit), 200)),),
        )

    async def issue_certificate(self, user_id: int, course_id: int, actor_id: int) -> dict[str, Any]:
        user = await self.fetchone("SELECT id FROM users WHERE id=?", (int(user_id),))
        course = await self.fetchone("SELECT id FROM courses WHERE id=? AND active=1", (int(course_id),))
        if not user or not course:
            raise ValueError("O‘quvchi yoki faol kurs topilmadi.")
        code = "ST-" + secrets.token_hex(5).upper()
        now = _education_now()
        cert_id = await self.execute(
            "INSERT INTO student_certificates(certificate_code,user_id,course_id,status,issued_by,issue_date,created_at) VALUES(?,?,?,'issued',?,?,?)",
            (code, int(user_id), int(course_id), int(actor_id), now[:10], now),
        )
        await self.write_education_audit(int(actor_id), "admin", "certificate_issued", "certificate", int(cert_id), f"user_id={int(user_id)};course_id={int(course_id)}")
        return {"id": int(cert_id), "certificate_code": code}

    async def student_certificates(self, telegram_id: int):
        return await self.fetchall(
            "SELECT sc.id,sc.certificate_code,sc.status,sc.issue_date,c.name_uz AS course_name FROM student_certificates sc "
            "JOIN users u ON u.id=sc.user_id JOIN courses c ON c.id=sc.course_id WHERE u.telegram_id=? ORDER BY sc.id DESC",
            (int(telegram_id),),
        )

    async def write_education_audit(
        self, actor_telegram_id: int, actor_role: str, action: str, entity_type: str,
        entity_id: int | None = None, details: str = "",
    ) -> None:
        await self.execute(
            "INSERT INTO education_audit_log(actor_telegram_id,actor_role,action,entity_type,entity_id,details,created_at) VALUES(?,?,?,?,?,?,?)",
            (int(actor_telegram_id), actor_role[:32], action[:80], entity_type[:80], entity_id, (details or "")[:1200], _education_now()),
        )

    async def education_audit(self, limit: int = 50):
        return await self.fetchall(
            "SELECT * FROM education_audit_log ORDER BY id DESC LIMIT ?", (max(1, min(int(limit), 200)),)
        )

    async def search_student_content(self, telegram_id: int, query: str, limit: int = 5):
        """Search public catalogue data plus only the published materials visible to this student."""
        query = " ".join(str(query or "").split())[:120]
        if len(query) < 2:
            return {"courses": [], "teachers": [], "materials": []}
        take = max(1, min(int(limit), 10))
        like = f"%{query}%"
        courses = await self.fetchall(
            "SELECT id,slug,name_uz,name_ru,name_en,icon,description_uz,description_ru,description_en "
            "FROM courses WHERE active=1 AND (name_uz LIKE ? OR name_ru LIKE ? OR name_en LIKE ? "
            "OR description_uz LIKE ? OR description_ru LIKE ? OR description_en LIKE ?) ORDER BY id LIMIT ?",
            (like, like, like, like, like, like, take),
        )
        teachers = await self.fetchall(
            "SELECT id,full_name,subject,experience,bio FROM teachers WHERE active=1 "
            "AND (full_name LIKE ? OR subject LIKE ? OR bio LIKE ?) ORDER BY id DESC LIMIT ?",
            (like, like, like, take),
        )
        group_ids = await self.student_group_ids(int(telegram_id))
        if group_ids:
            marks = ",".join("?" for _ in group_ids)
            material_scope = f"(r.group_id IS NULL OR r.group_id IN ({marks}))"
            scope_params: tuple[Any, ...] = tuple(group_ids)
        else:
            material_scope = "r.group_id IS NULL"
            scope_params = ()
        materials = await self.fetchall(
            "SELECT r.id,r.title,r.description,r.category,r.media_type,r.content,r.telegram_file_id,"
            "r.group_id,c.name_uz AS course_name FROM learning_resources r "
            "JOIN courses c ON c.id=r.course_id WHERE r.active=1 AND r.publication_status='published' "
            f"AND c.active=1 AND {material_scope} AND (r.title LIKE ? OR r.description LIKE ? "
            "OR c.name_uz LIKE ? OR c.name_ru LIKE ? OR c.name_en LIKE ?) ORDER BY r.id DESC LIMIT ?",
            (*scope_params, like, like, like, like, like, take),
        )
        return {"courses": courses, "teachers": teachers, "materials": materials}

    async def student_group_ids(self, telegram_id: int) -> list[int]:
        rows = await self.fetchall(
            "SELECT gm.group_id FROM group_memberships gm JOIN users u ON u.id=gm.user_id "
            "WHERE u.telegram_id=? AND gm.status='active' ORDER BY gm.group_id", (int(telegram_id),)
        )
        return [int(row["group_id"]) for row in rows]

    async def create_announcement(self, *, created_by: int, translations: dict[str, dict[str, str]], group_id: int | None = None) -> int:
        for lang in ("uz", "ru", "en"):
            row = translations.get(lang) or {}
            if not (str(row.get("title", "")).strip() and str(row.get("body", "")).strip()):
                raise ValueError("E’lonning UZ, RU va EN tarjimalari to‘liq bo‘lishi kerak.")
        if group_id is not None and not await self.fetchone("SELECT id FROM education_groups WHERE id=? AND status='active'", (int(group_id),)):
            raise ValueError("Faol guruh topilmadi.")
        now = _education_now()
        async with self.connect() as db:
            cur = await db.execute(
                "INSERT INTO announcements(target_group_id,status,created_by,created_at) VALUES(?,'draft',?,?)",
                (int(group_id) if group_id is not None else None, int(created_by), now),
            )
            announcement_id = int(cur.lastrowid)
            for lang in ("uz", "ru", "en"):
                row = translations[lang]
                await db.execute(
                    "INSERT INTO announcement_translations(announcement_id,language,title,body) VALUES(?,?,?,?)",
                    (announcement_id, lang, str(row["title"]).strip()[:180], str(row["body"]).strip()[:3000]),
                )
        await self.write_education_audit(int(created_by), "admin", "announcement_drafted", "announcement", announcement_id)
        return announcement_id

    async def prepare_announcement_delivery(self, announcement_id: int, actor_id: int):
        """Atomically lock a draft and create a deduplicated queue for opted-in users."""
        now = _education_now()
        async with self.connect() as db:
            announcement = await (await db.execute(
                "SELECT target_group_id,status FROM announcements WHERE id=?", (int(announcement_id),)
            )).fetchone()
            if not announcement or str(announcement["status"]) != "draft":
                raise ValueError("E’lon topilmadi yoki allaqachon yuborish boshlangan.")
            translations = await (await db.execute(
                "SELECT language,title,body FROM announcement_translations WHERE announcement_id=?",
                (int(announcement_id),),
            )).fetchall()
            localized = {str(row["language"]): {"title": str(row["title"]), "body": str(row["body"])} for row in translations}
            if set(localized) != {"uz", "ru", "en"}:
                raise ValueError("E’lonning uchala tarjimasi to‘liq emas.")
            group_id = announcement["target_group_id"]
            if group_id is None:
                recipients = await (await db.execute(
                    "SELECT u.id AS user_id,u.telegram_id,u.language FROM users u "
                    "LEFT JOIN user_notification_preferences p ON p.user_id=u.id "
                    "WHERE u.account_status='active' AND COALESCE(p.announcements_enabled,1)=1 ORDER BY u.id"
                )).fetchall()
            else:
                recipients = await (await db.execute(
                    "SELECT DISTINCT u.id AS user_id,u.telegram_id,u.language FROM group_memberships gm "
                    "JOIN users u ON u.id=gm.user_id LEFT JOIN user_notification_preferences p ON p.user_id=u.id "
                    "WHERE gm.group_id=? AND gm.status='active' AND u.account_status='active' "
                    "AND COALESCE(p.announcements_enabled,1)=1 ORDER BY u.id", (int(group_id),)
                )).fetchall()
            locked = await db.execute("UPDATE announcements SET status='sending' WHERE id=? AND status='draft'", (int(announcement_id),))
            if locked.rowcount != 1:
                raise ValueError("E’lonni yuborish boshqa sessiyada boshlangan.")
            for recipient in recipients:
                await db.execute(
                    "INSERT OR IGNORE INTO announcement_deliveries(announcement_id,user_id,status,error_type,attempts) "
                    "VALUES(?,?,'pending','',0)", (int(announcement_id), int(recipient["user_id"]))
                )
            await db.execute(
                "INSERT INTO education_audit_log(actor_telegram_id,actor_role,action,entity_type,entity_id,details,created_at) "
                "VALUES(?, 'admin', 'announcement_delivery_started', 'announcement', ?, ?, ?)",
                (int(actor_id), int(announcement_id), f"recipient_count={len(recipients)};group_id={group_id or ''}", now),
            )
        return [dict(row) for row in recipients], localized

    async def record_announcement_delivery(self, announcement_id: int, user_id: int, status: str, error_type: str = "") -> bool:
        if status not in {"sent", "failed", "skipped"}:
            raise ValueError("Yetkazish holati noto‘g‘ri.")
        now = _education_now()
        async with self.connect() as db:
            cur = await db.execute(
                "UPDATE announcement_deliveries SET status=?,error_type=?,attempts=attempts+1,sent_at=? "
                "WHERE announcement_id=? AND user_id=? AND status='pending'",
                (status, (error_type or "")[:80], now if status == "sent" else None, int(announcement_id), int(user_id)),
            )
            return cur.rowcount > 0

    async def complete_announcement_delivery(self, announcement_id: int, actor_id: int) -> dict[str, int]:
        now = _education_now()
        async with self.connect() as db:
            row = await (await db.execute(
                "SELECT status FROM announcements WHERE id=?", (int(announcement_id),)
            )).fetchone()
            if not row or str(row["status"]) != "sending":
                raise ValueError("Yuborilayotgan e’lon topilmadi.")
            counts = await (await db.execute(
                "SELECT status,COUNT(*) AS total FROM announcement_deliveries WHERE announcement_id=? GROUP BY status",
                (int(announcement_id),),
            )).fetchall()
            result = {"sent": 0, "failed": 0, "skipped": 0, "pending": 0}
            for item in counts:
                result[str(item["status"])] = int(item["total"])
            # A delivery can remain pending only after an unexpected process interruption.
            await db.execute(
                "UPDATE announcement_deliveries SET status='failed',error_type='interrupted' "
                "WHERE announcement_id=? AND status='pending'", (int(announcement_id),)
            )
            result["failed"] += result["pending"]
            result["pending"] = 0
            await db.execute(
                "UPDATE announcements SET status='sent',sent_at=? WHERE id=? AND status='sending'",
                (now, int(announcement_id)),
            )
            await db.execute(
                """INSERT OR IGNORE INTO user_notifications(
                    user_id,category,title,body,link_type,link_id,dedupe_key,delivery_status,delivered_at,created_at
                )
                SELECT d.user_id,'announcements',t.title,t.body,'announcement',?,
                       'announcement:' || ? || ':' || d.user_id,'sent',?,?
                FROM announcement_deliveries d
                JOIN users u ON u.id=d.user_id
                JOIN announcement_translations t ON t.announcement_id=d.announcement_id AND t.language=CASE WHEN u.language IN ('ru','en') THEN u.language ELSE 'uz' END
                WHERE d.announcement_id=? AND d.status='sent'""",
                (int(announcement_id), int(announcement_id), now, now, int(announcement_id)),
            )
            await db.execute(
                "INSERT INTO education_audit_log(actor_telegram_id,actor_role,action,entity_type,entity_id,details,created_at) "
                "VALUES(?, 'admin', 'announcement_delivery_completed', 'announcement', ?, ?, ?)",
                (int(actor_id), int(announcement_id), f"sent={result['sent']};failed={result['failed']};skipped={result['skipped']}", now),
            )
            return result

    async def cancel_announcement(self, announcement_id: int, actor_id: int) -> bool:
        now = _education_now()
        async with self.connect() as db:
            cur = await db.execute(
                "UPDATE announcements SET status='cancelled' WHERE id=? AND created_by=? AND status='draft'",
                (int(announcement_id), int(actor_id)),
            )
            if cur.rowcount:
                await db.execute(
                    "INSERT INTO education_audit_log(actor_telegram_id,actor_role,action,entity_type,entity_id,created_at) "
                    "VALUES(?, 'admin', 'announcement_cancelled', 'announcement', ?, ?)",
                    (int(actor_id), int(announcement_id), now),
                )
            return cur.rowcount > 0

    async def set_notification_preference(self, telegram_id: int, key: str, enabled: bool) -> bool:
        columns = {
            "announcements": "announcements_enabled", "lesson_reminders": "lesson_reminders_enabled",
            "homework": "homework_enabled", "results": "results_enabled",
        }
        column = columns.get(key)
        if not column:
            raise ValueError("Bildirishnoma sozlamasi noto‘g‘ri.")
        user = await self.fetchone("SELECT id FROM users WHERE telegram_id=?", (int(telegram_id),))
        if not user:
            return False
        now = _education_now()
        async with self.connect() as db:
            await db.execute(
                "INSERT OR IGNORE INTO user_notification_preferences(user_id,updated_at) VALUES(?,?)",
                (int(user["id"]), now),
            )
            await db.execute(
                f"UPDATE user_notification_preferences SET {column}=?,updated_at=? WHERE user_id=?",
                (1 if enabled else 0, now, int(user["id"])),
            )
        return True

    async def notification_preferences(self, telegram_id: int) -> dict[str, bool]:
        row = await self.fetchone(
            "SELECT p.announcements_enabled,p.lesson_reminders_enabled,p.homework_enabled,p.results_enabled "
            "FROM user_notification_preferences p JOIN users u ON u.id=p.user_id WHERE u.telegram_id=?",
            (int(telegram_id),),
        )
        if not row:
            return {"announcements": True, "lesson_reminders": True, "homework": True, "results": True}
        return {
            "announcements": bool(row["announcements_enabled"]),
            "lesson_reminders": bool(row["lesson_reminders_enabled"]),
            "homework": bool(row["homework_enabled"]),
            "results": bool(row["results_enabled"]),
        }

    async def mark_resource_pending(self, resource_id: int, actor_id: int) -> bool:
        now = _education_now()
        async with self.connect() as db:
            row = await (await db.execute(
                "SELECT id FROM learning_resources WHERE id=?", (int(resource_id),)
            )).fetchone()
            if not row:
                return False
            await db.execute(
                "UPDATE learning_resources SET active=0,publication_status='pending' WHERE id=?",
                (int(resource_id),),
            )
            await db.execute(
                "INSERT INTO education_audit_log(actor_telegram_id,actor_role,action,entity_type,entity_id,details,created_at) "
                "VALUES(?, 'teacher', 'resource_submitted_for_moderation', 'learning_resource', ?, '', ?)",
                (int(actor_id), int(resource_id), now),
            )
        return True

    # ------------------------------------------------------------------
    # Academic calendar and user notification center (schema v6)
    # ------------------------------------------------------------------

    @staticmethod
    def _iso_utc(value: str, *, optional: bool = False) -> str | None:
        raw = (value or "").strip()
        if not raw and optional:
            return None
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("Sana-vaqt ISO 8601 formatida bo‘lishi kerak.") from exc
        if parsed.tzinfo is None:
            raise ValueError("Sana-vaqt vaqt zonasi bilan yuborilishi kerak.")
        return parsed.astimezone(timezone.utc).isoformat(timespec="seconds")

    async def create_calendar_event(
        self, *, titles: dict[str, str], descriptions: dict[str, str] | None = None,
        category: str = "event", starts_at: str, ends_at: str | None = None,
        location: str = "", target_group_id: int | None = None,
        status: str = "draft", reminder_24h: bool = True, created_by: int,
    ) -> int:
        allowed_categories = {"lesson", "exam", "holiday", "event", "deadline", "schedule_change"}
        if category not in allowed_categories or status not in {"draft", "published", "archived"}:
            raise ValueError("Tadbir turi yoki holati noto‘g‘ri.")
        clean_titles = {lang: " ".join(str((titles or {}).get(lang, "")).split())[:180] for lang in ("uz", "ru", "en")}
        if any(len(clean_titles[lang]) < 2 for lang in clean_titles):
            raise ValueError("Sarlavha UZ, RU va EN tillarida to‘liq bo‘lishi kerak.")
        descriptions = descriptions or {}
        clean_descriptions = {lang: str(descriptions.get(lang, "")).strip()[:1800] for lang in ("uz", "ru", "en")}
        start = self._iso_utc(starts_at)
        end = self._iso_utc(ends_at or "", optional=True)
        if end and end <= start:
            raise ValueError("Tugash vaqti boshlanish vaqtidan keyin bo‘lishi kerak.")
        group_id = int(target_group_id) if target_group_id is not None else None
        if group_id is not None and not await self.fetchone(
            "SELECT id FROM education_groups WHERE id=? AND status='active'", (group_id,)
        ):
            raise ValueError("Faol guruh topilmadi.")
        now = _education_now()
        return int(await self.execute(
            """INSERT INTO academic_calendar_events(
                title_uz,title_ru,title_en,description_uz,description_ru,description_en,
                category,starts_at,ends_at,location,target_group_id,status,reminder_24h,
                created_by,created_at,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (clean_titles["uz"], clean_titles["ru"], clean_titles["en"],
             clean_descriptions["uz"], clean_descriptions["ru"], clean_descriptions["en"],
             category, start, end, (location or "").strip()[:180], group_id, status,
             1 if reminder_24h else 0, int(created_by), now, now),
        ))

    async def update_calendar_event(self, event_id: int, *, titles: dict[str, str],
                                    descriptions: dict[str, str] | None = None,
                                    category: str, starts_at: str, ends_at: str | None = None,
                                    location: str = "", target_group_id: int | None = None,
                                    status: str = "draft", reminder_24h: bool = True) -> bool:
        allowed_categories = {"lesson", "exam", "holiday", "event", "deadline", "schedule_change"}
        if category not in allowed_categories or status not in {"draft", "published", "archived"}:
            raise ValueError("Tadbir turi yoki holati noto‘g‘ri.")
        clean_titles = {lang: " ".join(str((titles or {}).get(lang, "")).split())[:180] for lang in ("uz", "ru", "en")}
        if any(len(clean_titles[lang]) < 2 for lang in clean_titles):
            raise ValueError("Sarlavha UZ, RU va EN tillarida to‘liq bo‘lishi kerak.")
        descriptions = descriptions or {}
        clean_descriptions = {lang: str(descriptions.get(lang, "")).strip()[:1800] for lang in ("uz", "ru", "en")}
        start = self._iso_utc(starts_at)
        end = self._iso_utc(ends_at or "", optional=True)
        if end and end <= start:
            raise ValueError("Tugash vaqti boshlanish vaqtidan keyin bo‘lishi kerak.")
        group_id = int(target_group_id) if target_group_id is not None else None
        if group_id is not None and not await self.fetchone(
            "SELECT id FROM education_groups WHERE id=? AND status='active'", (group_id,)
        ):
            raise ValueError("Faol guruh topilmadi.")
        now = _education_now()
        changed = await self.execute(
            """UPDATE academic_calendar_events SET title_uz=?,title_ru=?,title_en=?,
               description_uz=?,description_ru=?,description_en=?,category=?,starts_at=?,ends_at=?,
               location=?,target_group_id=?,status=?,reminder_24h=?,updated_at=? WHERE id=?""",
            (clean_titles["uz"], clean_titles["ru"], clean_titles["en"],
             clean_descriptions["uz"], clean_descriptions["ru"], clean_descriptions["en"],
             category, start, end, (location or "").strip()[:180], group_id, status,
             1 if reminder_24h else 0, now, int(event_id)),
        )
        return bool(changed)

    async def calendar_events(self, *, language: str = "uz", public_only: bool = True,
                              telegram_id: int | None = None, limit: int = 100):
        language = language if language in {"uz", "ru", "en"} else "uz"
        ids: list[int] = []
        if telegram_id is not None:
            ids = await self.student_group_ids(int(telegram_id))
        title_col = f"title_{language}"
        desc_col = f"description_{language}"
        where = ["status='published'"] if public_only else []
        params: list[Any] = []
        if public_only:
            now = _education_now()
            where.append("starts_at>=?")
            params.append(now)
        if telegram_id is not None:
            if ids:
                marks = ",".join("?" for _ in ids)
                where.append(f"(target_group_id IS NULL OR target_group_id IN ({marks}))")
                params.extend(ids)
            else:
                where.append("target_group_id IS NULL")
        elif public_only:
            where.append("target_group_id IS NULL")
        clause = " WHERE " + " AND ".join(where) if where else ""
        params.append(max(1, min(int(limit), 200)))
        return await self.fetchall(
            f"SELECT id,{title_col} AS title,{desc_col} AS description,category,starts_at,ends_at,location,target_group_id,status "
            f"FROM academic_calendar_events{clause} ORDER BY starts_at ASC LIMIT ?", tuple(params),
        )

    async def create_user_notification(
        self, telegram_id: int, *, category: str, title: str, body: str = "",
        dedupe_key: str, link_type: str = "", link_id: int | None = None,
        delivery_status: str = "pending",
    ) -> bool:
        preference_columns = {
            "announcements": "announcements_enabled", "lesson_reminders": "lesson_reminders_enabled",
            "homework": "homework_enabled", "results": "results_enabled", "system": None,
        }
        if category not in preference_columns or delivery_status not in {"pending", "sent", "failed", "skipped"}:
            raise ValueError("Bildirishnoma turi yoki yetkazish holati noto‘g‘ri.")
        user = await self.fetchone(
            "SELECT id,account_status FROM users WHERE telegram_id=?", (int(telegram_id),)
        )
        if not user or str(user["account_status"]) != "active":
            return False
        now = _education_now()
        pref = preference_columns[category]
        async with self.connect() as conn:
            if pref:
                pref_value = await (await conn.execute(
                    f"SELECT COALESCE((SELECT {pref} FROM user_notification_preferences WHERE user_id=?),1)",
                    (int(user["id"]),),
                )).fetchone()
                if not bool(pref_value[0]):
                    return False
            cur = await conn.execute(
                """INSERT OR IGNORE INTO user_notifications(
                    user_id,category,title,body,link_type,link_id,dedupe_key,delivery_status,delivered_at,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (int(user["id"]), category, str(title).strip()[:180], str(body).strip()[:1800],
                 (link_type or "")[:40], int(link_id) if link_id is not None else None,
                 str(dedupe_key)[:180], delivery_status, now if delivery_status == "sent" else None, now),
            )
            return cur.rowcount > 0

    async def notify_group_members(
        self, group_id: int, *, category: str, localized: dict[str, dict[str, str]],
        dedupe_prefix: str, link_type: str = "", link_id: int | None = None,
        delivery_status: str = "pending",
    ) -> int:
        if category not in {"announcements", "lesson_reminders", "homework", "results", "system"}:
            raise ValueError("Bildirishnoma kategoriyasi noto‘g‘ri.")
        pref_col = {"announcements": "announcements_enabled", "lesson_reminders": "lesson_reminders_enabled",
                    "homework": "homework_enabled", "results": "results_enabled", "system": None}[category]
        now = _education_now()
        inserted = 0
        async with self.connect() as conn:
            pref_join = "LEFT JOIN user_notification_preferences p ON p.user_id=u.id"
            pref_filter = f"AND COALESCE(p.{pref_col},1)=1" if pref_col else ""
            users = await (await conn.execute(
                "SELECT u.id,u.telegram_id,u.language FROM group_memberships gm JOIN users u ON u.id=gm.user_id "
                f"{pref_join} WHERE gm.group_id=? AND gm.status='active' AND u.account_status='active' {pref_filter}",
                (int(group_id),),
            )).fetchall()
            for user in users:
                lang = str(user["language"] or "uz")
                lang = lang if lang in {"uz", "ru", "en"} else "uz"
                item = localized.get(lang) or localized.get("uz") or {}
                cur = await conn.execute(
                    """INSERT OR IGNORE INTO user_notifications(
                       user_id,category,title,body,link_type,link_id,dedupe_key,delivery_status,created_at
                    ) VALUES(?,?,?,?,?,?,?,?,?)""",
                    (int(user["id"]), category, str(item.get("title", "STARTUM"))[:180],
                     str(item.get("body", ""))[:1800], (link_type or "")[:40],
                     int(link_id) if link_id is not None else None,
                     f"{dedupe_prefix}:{int(user['id'])}"[:180], delivery_status, now),
                )
                inserted += max(0, int(cur.rowcount or 0))
        return inserted

    async def user_notifications(self, telegram_id: int, *, unread_only: bool = False, limit: int = 30):
        where = " AND n.read_at IS NULL" if unread_only else ""
        return await self.fetchall(
            "SELECT n.id,n.category,n.title,n.body,n.link_type,n.link_id,n.read_at,n.created_at "
            "FROM user_notifications n JOIN users u ON u.id=n.user_id "
            "WHERE u.telegram_id=?" + where + " ORDER BY n.created_at DESC,n.id DESC LIMIT ?",
            (int(telegram_id), max(1, min(int(limit), 100))),
        )

    async def unread_notification_count(self, telegram_id: int) -> int:
        row = await self.fetchone(
            "SELECT COUNT(*) AS total FROM user_notifications n JOIN users u ON u.id=n.user_id "
            "WHERE u.telegram_id=? AND n.read_at IS NULL", (int(telegram_id),)
        )
        return int(row["total"] if row else 0)

    async def mark_user_notification_read(self, telegram_id: int, notification_id: int) -> bool:
        result = await self.execute(
            "UPDATE user_notifications SET read_at=? WHERE id=? AND user_id=(SELECT id FROM users WHERE telegram_id=?) AND read_at IS NULL",
            (_education_now(), int(notification_id), int(telegram_id)),
        )
        return bool(result)

    async def mark_all_user_notifications_read(self, telegram_id: int) -> int:
        result = await self.execute(
            "UPDATE user_notifications SET read_at=? WHERE user_id=(SELECT id FROM users WHERE telegram_id=?) AND read_at IS NULL",
            (_education_now(), int(telegram_id)),
        )
        return int(result or 0)

    async def pending_user_notifications(self, limit: int = 100):
        return await self.fetchall(
            "SELECT n.id,n.category,n.title,n.body,u.telegram_id FROM user_notifications n "
            "JOIN users u ON u.id=n.user_id WHERE n.delivery_status='pending' AND n.delivery_attempts<5 "
            "AND u.account_status='active' ORDER BY n.id LIMIT ?", (max(1, min(int(limit), 300)),)
        )

    async def mark_user_notification_delivery(self, notification_id: int, *, success: bool, error: str = "", permanent: bool = False) -> None:
        await self.execute(
            """UPDATE user_notifications
               SET delivery_status=CASE WHEN ?=1 THEN 'sent' WHEN ?=1 OR delivery_attempts+1>=5 THEN 'failed' ELSE 'pending' END,
                   delivery_attempts=delivery_attempts+1,last_error=?,
                   delivered_at=CASE WHEN ?=1 THEN ? ELSE delivered_at END
               WHERE id=? AND delivery_status='pending'""",
            (1 if success else 0, 1 if permanent else 0, (error or "")[:120],
             1 if success else 0, _education_now(), int(notification_id)),
        )

    async def queue_due_calendar_reminders(self, *, now: datetime | None = None) -> int:
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            raise ValueError("Reminder scheduler requires timezone-aware datetime.")
        lower = (current.astimezone(timezone.utc) + timedelta(hours=23)).isoformat(timespec="seconds")
        upper = (current.astimezone(timezone.utc) + timedelta(hours=25)).isoformat(timespec="seconds")
        events = await self.fetchall(
            "SELECT * FROM academic_calendar_events WHERE status='published' AND reminder_24h=1 AND starts_at>=? AND starts_at<?",
            (lower, upper),
        )
        created = 0
        for event in events:
            if event["target_group_id"] is None:
                users = await self.fetchall(
                    "SELECT u.telegram_id,u.language FROM users u LEFT JOIN user_notification_preferences p ON p.user_id=u.id "
                    "WHERE u.account_status='active' AND COALESCE(p.lesson_reminders_enabled,1)=1"
                )
            else:
                users = await self.fetchall(
                    "SELECT u.telegram_id,u.language FROM group_memberships gm JOIN users u ON u.id=gm.user_id "
                    "LEFT JOIN user_notification_preferences p ON p.user_id=u.id "
                    "WHERE gm.group_id=? AND gm.status='active' AND u.account_status='active' AND COALESCE(p.lesson_reminders_enabled,1)=1",
                    (int(event["target_group_id"]),),
                )
            try:
                local_start = datetime.fromisoformat(str(event["starts_at"]).replace("Z", "+00:00")).astimezone(ZoneInfo("Asia/Tashkent"))
                local_time = local_start.strftime("%d.%m.%Y · %H:%M")
            except (TypeError, ValueError):
                local_time = str(event["starts_at"])
            localized = {
                "uz": (str(event["title_uz"]), f"Tadbir 24 soatdan keyin boshlanadi: {local_time} (Toshkent vaqti)"),
                "ru": (str(event["title_ru"]), f"Событие начнётся через 24 часа: {local_time} (время Ташкента)"),
                "en": (str(event["title_en"]), f"This event starts in 24 hours: {local_time} (Tashkent time)"),
            }
            for user in users:
                lang = str(user["language"] or "uz")
                title, body = localized.get(lang, localized["uz"])
                created += int(await self.create_user_notification(
                    int(user["telegram_id"]), category="lesson_reminders", title=title, body=body,
                    dedupe_key=f"calendar:{int(event['id'])}:24h", link_type="calendar", link_id=int(event["id"]),
                ))
        return created
