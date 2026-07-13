from __future__ import annotations

import sqlite3
import hashlib
import secrets
from datetime import date, datetime, timedelta

from werkzeug.security import generate_password_hash

from back_to_god.constants import ROLE_LABELS
from back_to_god.core.db import get_db
from back_to_god.core.security import generate_password, utc_now
from back_to_god.core.validators import only_digits


QUICK_LOGIN_USERS = {
    "super_admin": ("Quick Super Admin", "quick.superadmin@backtogod.local"),
    "admin": ("Quick Admin", "quick.admin@backtogod.local"),
    "pastor": ("Quick Pastor", "quick.pastor@backtogod.local"),
    "usher": ("Quick Usher", "quick.usher@backtogod.local"),
    "videographer": ("Quick Videographer", "quick.videographer@backtogod.local"),
    "treasurer": ("Quick Treasurer", "quick.treasurer@backtogod.local"),
    "member": ("Quick Member", "quick.member@backtogod.local"),
}

ROLE_ORDER = ("super_admin", "admin", "pastor", "usher", "videographer", "treasurer", "member")


def normalize_text(value: str, limit: int = 180) -> str:
    return " ".join((value or "").split())[:limit]


def normalize_identity_type(value: str) -> str:
    return "foreign" if value == "foreign" else "sa_id"


def normalize_foreign_id(value: str) -> str:
    return normalize_text((value or "").upper(), 60)


def normalize_nationality(identity_type: str, nationality: str = "") -> str:
    return "South Africa" if normalize_identity_type(identity_type) == "sa_id" else normalize_text(nationality, 80)


def identity_exists(
    *,
    id_number: str = "",
    foreign_id_number: str = "",
    exclude_user_id: int | None = None,
) -> bool:
    clauses = []
    params: list[object] = []
    clean_id = only_digits(id_number, 13)
    clean_foreign_id = normalize_foreign_id(foreign_id_number)
    if clean_id:
        clauses.append("id_number = ?")
        params.append(clean_id)
    if clean_foreign_id:
        clauses.append("foreign_id_number = ?")
        params.append(clean_foreign_id)
    if not clauses:
        return False
    query = f"SELECT id FROM users WHERE ({' OR '.join(clauses)})"
    if exclude_user_id is not None:
        query += " AND id != ?"
        params.append(exclude_user_id)
    query += " LIMIT 1"
    return get_db().execute(query, tuple(params)).fetchone() is not None


def _age_value(date_of_birth: str | None) -> int | None:
    if not date_of_birth:
        return None
    try:
        born = date.fromisoformat(date_of_birth[:10])
    except ValueError:
        return None
    today = date.today()
    age = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
    return age if age >= 0 else None


def create_user(
    full_name: str,
    email: str,
    role: str,
    created_by: int | None = None,
    id_number: str = "",
    date_of_birth: str = "",
    identity_type: str = "sa_id",
    foreign_id_number: str = "",
    nationality: str = "",
    must_change_password: bool = True,
    phone: str = "",
    home_area: str = "",
) -> str:
    password = generate_password()
    now = utc_now()
    identity_type = normalize_identity_type(identity_type)
    clean_id = only_digits(id_number, 13) if identity_type == "sa_id" else ""
    clean_foreign_id = normalize_foreign_id(foreign_id_number) if identity_type == "foreign" else ""
    clean_nationality = normalize_nationality(identity_type, nationality)
    get_db().execute(
        """
        INSERT INTO users (
            full_name, email, role, password_hash, must_change_password, created_by,
            identity_type, id_number, foreign_id_number, nationality, date_of_birth,
            phone, home_area, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            normalize_text(full_name, 120),
            email.lower().strip(),
            role,
            generate_password_hash(password),
            1 if must_change_password else 0,
            created_by,
            identity_type,
            clean_id,
            clean_foreign_id,
            clean_nationality,
            date_of_birth,
            normalize_text(phone, 40),
            normalize_text(home_area, 120),
            now,
            now,
        ),
    )
    get_db().commit()
    return password


def signup_member(
    full_name: str,
    email: str,
    phone: str,
    home_area: str,
    id_number: str = "",
    date_of_birth: str = "",
    identity_type: str = "sa_id",
    foreign_id_number: str = "",
    nationality: str = "",
) -> str:
    password = generate_password()
    now = utc_now()
    identity_type = normalize_identity_type(identity_type)
    clean_id = only_digits(id_number, 13) if identity_type == "sa_id" else ""
    clean_foreign_id = normalize_foreign_id(foreign_id_number) if identity_type == "foreign" else ""
    clean_nationality = normalize_nationality(identity_type, nationality)
    get_db().execute(
        """
        INSERT INTO users (
            full_name, email, role, password_hash, must_change_password,
            phone, identity_type, id_number, foreign_id_number, nationality, date_of_birth,
            home_area, created_at, updated_at
        )
        VALUES (?, ?, 'member', ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            normalize_text(full_name, 120),
            email.lower().strip(),
            generate_password_hash(password),
            normalize_text(phone, 40),
            identity_type,
            clean_id,
            clean_foreign_id,
            clean_nationality,
            date_of_birth,
            normalize_text(home_area, 120),
            now,
            now,
        ),
    )
    get_db().commit()
    return password


def get_or_create_quick_user(role: str) -> sqlite3.Row:
    if role not in QUICK_LOGIN_USERS or role not in ROLE_LABELS:
        raise ValueError("Unknown quick login role.")

    full_name, email = QUICK_LOGIN_USERS[role]
    user = get_user_by_email(email, include_deleted=True)
    if user is None:
        create_user(full_name, email, role, None, must_change_password=False)
        user = get_user_by_email(email)
    elif user["deleted_at"] or not user["is_active"]:
        return user
    else:
        get_db().execute(
            """
            UPDATE users
            SET must_change_password = 0, updated_at = ?
            WHERE id = ?
            """,
            (utc_now(), user["id"]),
        )
        get_db().commit()
        user = get_user_by_id(user["id"])

    if user is None:
        raise RuntimeError("Could not create quick login user.")
    return user


def get_user_by_email(email: str, include_deleted: bool = False) -> sqlite3.Row | None:
    query = "SELECT * FROM users WHERE email = ?"
    params: tuple = (email.lower().strip(),)
    if not include_deleted:
        query += " AND deleted_at IS NULL"
    return get_db().execute(query, params).fetchone()


def get_user_by_id(user_id: int) -> sqlite3.Row | None:
    return get_db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def get_user_profile(user_id: int) -> sqlite3.Row | None:
    return get_user_by_id(user_id)


def update_profile(
    user_id: int,
    full_name: str,
    phone: str,
    home_area: str,
    bio: str,
    emergency_contact_name: str,
    emergency_contact_phone: str,
    emergency_contact_relationship: str,
    id_number: str = "",
    date_of_birth: str = "",
    identity_type: str = "sa_id",
    foreign_id_number: str = "",
    nationality: str = "",
    profile_photo: str | None = None,
) -> None:
    full_name = normalize_text(full_name, 120)
    phone = normalize_text(phone, 40)
    home_area = normalize_text(home_area, 120)
    bio = normalize_text(bio, 420)
    emergency_contact_name = normalize_text(emergency_contact_name, 120)
    emergency_contact_phone = normalize_text(emergency_contact_phone, 40)
    emergency_contact_relationship = normalize_text(emergency_contact_relationship, 80)
    identity_type = normalize_identity_type(identity_type)
    clean_id = only_digits(id_number, 13) if identity_type == "sa_id" else ""
    clean_foreign_id = normalize_foreign_id(foreign_id_number) if identity_type == "foreign" else ""
    nationality = normalize_nationality(identity_type, nationality)

    if profile_photo:
        get_db().execute(
            """
            UPDATE users
            SET full_name = ?, phone = ?, identity_type = ?, id_number = ?,
                foreign_id_number = ?, nationality = ?, date_of_birth = ?,
                home_area = ?, bio = ?, emergency_contact_name = ?,
                emergency_contact_phone = ?, emergency_contact_relationship = ?,
                profile_photo = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                full_name,
                phone,
                identity_type,
                clean_id,
                clean_foreign_id,
                nationality,
                date_of_birth,
                home_area,
                bio,
                emergency_contact_name,
                emergency_contact_phone,
                emergency_contact_relationship,
                profile_photo,
                utc_now(),
                user_id,
            ),
        )
    else:
        get_db().execute(
            """
            UPDATE users
            SET full_name = ?, phone = ?, identity_type = ?, id_number = ?,
                foreign_id_number = ?, nationality = ?, date_of_birth = ?,
                home_area = ?, bio = ?, emergency_contact_name = ?,
                emergency_contact_phone = ?, emergency_contact_relationship = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                full_name,
                phone,
                identity_type,
                clean_id,
                clean_foreign_id,
                nationality,
                date_of_birth,
                home_area,
                bio,
                emergency_contact_name,
                emergency_contact_phone,
                emergency_contact_relationship,
                utc_now(),
                user_id,
            ),
        )
    get_db().commit()


def record_login(user_id: int) -> None:
    now = utc_now()
    get_db().execute(
        "UPDATE users SET last_login_at = ?, last_seen_at = ?, updated_at = ? WHERE id = ?",
        (now, now, now, user_id),
    )
    get_db().commit()


def touch_presence(user_id: int) -> None:
    get_db().execute(
        "UPDATE users SET last_seen_at = ? WHERE id = ?",
        (utc_now(), user_id),
    )
    get_db().commit()


def change_password(user_id: int, password: str) -> None:
    get_db().execute(
        """
        UPDATE users
        SET password_hash = ?, must_change_password = 0, updated_at = ?
        WHERE id = ?
        """,
        (generate_password_hash(password), utc_now(), user_id),
    )
    get_db().commit()


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_password_reset_token(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    now = utc_now()
    expires_at = (datetime.now() + timedelta(minutes=5)).isoformat(timespec="seconds")
    get_db().execute(
        """
        INSERT INTO password_reset_tokens (user_id, token_hash, expires_at, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (user_id, _token_hash(token), expires_at, now),
    )
    get_db().commit()
    return token


def get_valid_password_reset_token(token: str) -> sqlite3.Row | None:
    if not token:
        return None
    return get_db().execute(
        """
        SELECT password_reset_tokens.*, users.email, users.full_name
        FROM password_reset_tokens
        JOIN users ON users.id = password_reset_tokens.user_id
        WHERE password_reset_tokens.token_hash = ?
          AND password_reset_tokens.used_at IS NULL
          AND password_reset_tokens.expires_at > ?
          AND users.deleted_at IS NULL
          AND users.is_active = 1
        """,
        (_token_hash(token), utc_now()),
    ).fetchone()


def reset_password_with_token(token: str, password: str) -> sqlite3.Row | None:
    reset = get_valid_password_reset_token(token)
    if reset is None:
        return None
    now = utc_now()
    get_db().execute(
        """
        UPDATE users
        SET password_hash = ?, must_change_password = 0, updated_at = ?
        WHERE id = ?
        """,
        (generate_password_hash(password), now, reset["user_id"]),
    )
    get_db().execute(
        """
        UPDATE password_reset_tokens
        SET used_at = ?
        WHERE id = ?
        """,
        (now, reset["id"]),
    )
    get_db().commit()
    return reset


def count_users() -> dict[str, int]:
    row = get_db().execute(
        """
        SELECT
            COALESCE(SUM(CASE WHEN is_active = 1 THEN 1 ELSE 0 END), 0) AS active,
            COALESCE(SUM(CASE WHEN role = 'pastor' THEN 1 ELSE 0 END), 0) AS pastors,
            COALESCE(SUM(CASE WHEN role = 'member' THEN 1 ELSE 0 END), 0) AS members,
            COALESCE(SUM(CASE WHEN role = 'usher' THEN 1 ELSE 0 END), 0) AS ushers,
            COALESCE(SUM(CASE WHEN role = 'videographer' THEN 1 ELSE 0 END), 0) AS videographers,
            COALESCE(SUM(CASE WHEN role = 'treasurer' THEN 1 ELSE 0 END), 0) AS treasurers
        FROM users
        WHERE deleted_at IS NULL
        """
    ).fetchone()
    return {
        "active": int(row["active"]),
        "pastors": int(row["pastors"]),
        "members": int(row["members"]),
        "ushers": int(row["ushers"]),
        "videographers": int(row["videographers"]),
        "treasurers": int(row["treasurers"]),
    }


def _user_filter(query: str = "", role: str = "") -> tuple[str, list[object]]:
    where = "deleted_at IS NULL"
    params: list[object] = []
    compact_query = normalize_text(query, 80)
    if compact_query:
        like = f"%{compact_query}%"
        where += """
            AND (
                full_name LIKE ?
                OR email LIKE ?
                OR phone LIKE ?
                OR id_number LIKE ?
                OR foreign_id_number LIKE ?
                OR nationality LIKE ?
            )
        """
        params.extend([like, like, like, like, like, like])
    if role and role in ROLE_LABELS:
        where += " AND role = ?"
        params.append(role)
    return where, params


def directory_user_count(query: str = "", role: str = "") -> int:
    where, params = _user_filter(query, role)
    row = get_db().execute(
        f"SELECT COUNT(*) AS count FROM users WHERE {where}",
        tuple(params),
    ).fetchone()
    return int(row["count"])


def list_users(limit: int = 10, offset: int = 0, query: str = "", role: str = "") -> list[sqlite3.Row]:
    where, params = _user_filter(query, role)
    params.extend([limit, offset])
    return get_db().execute(
        f"""
        SELECT
            id, full_name, email, role, must_change_password, is_active, phone, home_area,
            identity_type, id_number, foreign_id_number, nationality,
            profile_photo, date_of_birth, emergency_contact_name, emergency_contact_phone,
            emergency_contact_relationship, created_at, last_login_at, last_seen_at, deleted_at
        FROM users
        WHERE {where}
        ORDER BY
          CASE role
            WHEN 'super_admin' THEN 1
            WHEN 'admin' THEN 2
            WHEN 'pastor' THEN 3
            WHEN 'usher' THEN 4
            WHEN 'videographer' THEN 5
            WHEN 'treasurer' THEN 6
            ELSE 7
          END,
          full_name COLLATE NOCASE
        LIMIT ? OFFSET ?
        """
        ,
        tuple(params),
    ).fetchall()


def _percent(value: int, total: int) -> int:
    if total <= 0:
        return 0
    return round((value / total) * 100)


def user_analytics(include_age: bool = False) -> dict:
    rows = get_db().execute(
        """
        SELECT
            role, is_active, must_change_password, phone, id_number, date_of_birth,
            emergency_contact_name, emergency_contact_phone, profile_photo
        FROM users
        WHERE deleted_at IS NULL
        """
    ).fetchall()
    total = len(rows)
    active = sum(1 for row in rows if row["is_active"])
    inactive = total - active
    must_change = sum(1 for row in rows if row["must_change_password"])
    password_set = total - must_change
    emergency_complete = sum(1 for row in rows if row["emergency_contact_name"] and row["emergency_contact_phone"])
    photo_complete = sum(1 for row in rows if row["profile_photo"])
    id_complete = sum(1 for row in rows if row["id_number"])
    phone_complete = sum(1 for row in rows if row["phone"])

    role_counts = {role: 0 for role in ROLE_ORDER}
    for row in rows:
        role_counts[row["role"]] = role_counts.get(row["role"], 0) + 1

    role_breakdown = [
        {
            "role": role,
            "label": ROLE_LABELS.get(role, role.replace("_", " ").title()),
            "count": count,
            "percent": _percent(count, total),
        }
        for role, count in role_counts.items()
        if count or role in {"pastor", "member", "usher", "videographer", "treasurer"}
    ]

    profile_completion = [
        {"label": "Phone", "count": phone_complete, "percent": _percent(phone_complete, total)},
        {"label": "SA ID", "count": id_complete, "percent": _percent(id_complete, total)},
        {"label": "Emergency", "count": emergency_complete, "percent": _percent(emergency_complete, total)},
        {"label": "Photo", "count": photo_complete, "percent": _percent(photo_complete, total)},
    ]

    age_bands: list[dict] = []
    if include_age:
        band_counts = {
            "Under 18": 0,
            "18-25": 0,
            "26-35": 0,
            "36-50": 0,
            "51+": 0,
            "Not added": 0,
        }
        for row in rows:
            age = _age_value(row["date_of_birth"])
            if age is None:
                band_counts["Not added"] += 1
            elif age < 18:
                band_counts["Under 18"] += 1
            elif age <= 25:
                band_counts["18-25"] += 1
            elif age <= 35:
                band_counts["26-35"] += 1
            elif age <= 50:
                band_counts["36-50"] += 1
            else:
                band_counts["51+"] += 1
        age_bands = [
            {"label": label, "count": count, "percent": _percent(count, total)}
            for label, count in band_counts.items()
        ]

    return {
        "total": total,
        "active": active,
        "inactive": inactive,
        "deleted": deleted_user_count(),
        "must_change": must_change,
        "password_set": password_set,
        "active_percent": _percent(active, total),
        "inactive_percent": _percent(inactive, total),
        "password_percent": _percent(password_set, total),
        "must_change_percent": _percent(must_change, total),
        "role_breakdown": role_breakdown,
        "max_role_count": max([item["count"] for item in role_breakdown] or [1]),
        "profile_completion": profile_completion,
        "age_bands": age_bands,
        "max_age_count": max([item["count"] for item in age_bands] or [1]),
    }


def list_users_for_report(include_deleted: bool = False) -> list[sqlite3.Row]:
    deleted_clause = "users.deleted_at IS NOT NULL" if include_deleted else "users.deleted_at IS NULL"
    return get_db().execute(
        f"""
        SELECT
            users.id, users.full_name, users.email, users.role, users.must_change_password,
            users.is_active, users.phone, users.identity_type, users.id_number,
            users.foreign_id_number, users.nationality, users.date_of_birth,
            users.home_area, users.emergency_contact_name, users.emergency_contact_phone,
            users.emergency_contact_relationship, users.created_at, users.last_login_at,
            users.last_seen_at, users.deleted_at, deleter.full_name AS deleted_by_name
        FROM users
        LEFT JOIN users AS deleter ON deleter.id = users.deleted_by
        WHERE {deleted_clause}
        ORDER BY
          CASE users.role
            WHEN 'super_admin' THEN 1
            WHEN 'admin' THEN 2
            WHEN 'pastor' THEN 3
            WHEN 'usher' THEN 4
            WHEN 'videographer' THEN 5
            WHEN 'treasurer' THEN 6
            ELSE 7
          END,
          users.full_name COLLATE NOCASE
        """
    ).fetchall()


def list_recent_users(limit: int = 4) -> list[sqlite3.Row]:
    return get_db().execute(
        """
        SELECT full_name, email, role, created_at
        FROM users
        WHERE deleted_at IS NULL
        ORDER BY datetime(created_at) DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()


def reset_password(user_id: int) -> str:
    password = generate_password()
    get_db().execute(
        "UPDATE users SET password_hash = ?, must_change_password = 1, updated_at = ? WHERE id = ?",
        (generate_password_hash(password), utc_now(), user_id),
    )
    get_db().commit()
    return password


def set_active(user_id: int, is_active: bool) -> None:
    get_db().execute(
        "UPDATE users SET is_active = ?, updated_at = ? WHERE id = ?",
        (1 if is_active else 0, utc_now(), user_id),
    )
    get_db().commit()


def update_user_role(user_id: int, role: str) -> None:
    if role not in ROLE_LABELS:
        raise ValueError("Unknown role.")
    get_db().execute(
        "UPDATE users SET role = ?, updated_at = ? WHERE id = ?",
        (role, utc_now(), user_id),
    )
    get_db().commit()


def soft_delete_user(user_id: int, deleted_by: int) -> None:
    now = utc_now()
    get_db().execute(
        """
        UPDATE users
        SET is_active = 0, deleted_at = ?, deleted_by = ?, updated_at = ?
        WHERE id = ?
        """,
        (now, deleted_by, now, user_id),
    )
    get_db().commit()


def restore_user(user_id: int) -> None:
    get_db().execute(
        """
        UPDATE users
        SET is_active = 1, deleted_at = NULL, deleted_by = NULL, updated_at = ?
        WHERE id = ?
        """,
        (utc_now(), user_id),
    )
    get_db().commit()


def permanently_delete_user(user_id: int) -> None:
    db = get_db()
    try:
        db.execute("DELETE FROM password_reset_tokens WHERE user_id = ?", (user_id,))
        db.execute("DELETE FROM notifications WHERE user_id = ?", (user_id,))

        db.execute(
            """
            DELETE FROM message_attachments
            WHERE message_id IN (
                SELECT id FROM messages WHERE sender_id = ? OR recipient_id = ?
            )
            """,
            (user_id, user_id),
        )
        db.execute("DELETE FROM messages WHERE sender_id = ? OR recipient_id = ?", (user_id, user_id))

        db.execute(
            """
            DELETE FROM timeline_media
            WHERE post_id IN (SELECT id FROM timeline_posts WHERE author_id = ?)
            """,
            (user_id,),
        )
        db.execute(
            """
            DELETE FROM timeline_comments
            WHERE user_id = ?
               OR post_id IN (SELECT id FROM timeline_posts WHERE author_id = ?)
            """,
            (user_id, user_id),
        )
        db.execute(
            """
            DELETE FROM timeline_reactions
            WHERE user_id = ?
               OR post_id IN (SELECT id FROM timeline_posts WHERE author_id = ?)
            """,
            (user_id, user_id),
        )
        db.execute(
            """
            DELETE FROM timeline_post_viewers
            WHERE user_id = ?
               OR post_id IN (SELECT id FROM timeline_posts WHERE author_id = ?)
            """,
            (user_id, user_id),
        )
        db.execute("DELETE FROM timeline_posts WHERE author_id = ?", (user_id,))

        db.execute(
            """
            DELETE FROM live_recordings
            WHERE live_session_id IN (SELECT id FROM live_sessions WHERE started_by = ?)
            """,
            (user_id,),
        )
        db.execute(
            """
            DELETE FROM live_comments
            WHERE user_id = ?
               OR live_session_id IN (SELECT id FROM live_sessions WHERE started_by = ?)
            """,
            (user_id, user_id),
        )
        db.execute(
            """
            DELETE FROM live_reactions
            WHERE user_id = ?
               OR live_session_id IN (SELECT id FROM live_sessions WHERE started_by = ?)
            """,
            (user_id, user_id),
        )
        db.execute(
            """
            DELETE FROM webrtc_signals
            WHERE live_session_id IN (SELECT id FROM live_sessions WHERE started_by = ?)
            """,
            (user_id,),
        )
        db.execute("DELETE FROM live_sessions WHERE started_by = ?", (user_id,))

        db.execute("DELETE FROM announcements WHERE created_by = ?", (user_id,))
        db.execute(
            """
            DELETE FROM gallery_slideshow_items
            WHERE media_id IN (SELECT id FROM gallery_media WHERE uploaded_by = ?)
            """,
            (user_id,),
        )
        db.execute("DELETE FROM gallery_media WHERE uploaded_by = ?", (user_id,))
        db.execute("DELETE FROM gallery_slideshow_items WHERE added_by = ?", (user_id,))
        db.execute(
            """
            DELETE FROM committee_members
            WHERE committee_id IN (SELECT id FROM committees WHERE created_by = ?)
            """,
            (user_id,),
        )
        db.execute("DELETE FROM committees WHERE created_by = ?", (user_id,))
        db.execute(
            """
            UPDATE finance_offerings
            SET deposit_slip_id = NULL, updated_at = ?
            WHERE deposit_slip_id IN (SELECT id FROM deposit_slips WHERE created_by = ?)
            """,
            (utc_now(), user_id),
        )
        db.execute("DELETE FROM deposit_slips WHERE created_by = ?", (user_id,))
        db.execute("DELETE FROM finance_offerings WHERE captured_by = ?", (user_id,))

        optional_user_refs = (
            ("users", "created_by"),
            ("users", "deleted_by"),
            ("committees", "deleted_by"),
            ("visitors", "captured_by"),
            ("visitors", "follow_up_made_by"),
            ("visitors", "membership_reviewed_by"),
            ("visitors", "member_user_id"),
            ("live_sessions", "recording_deleted_by"),
            ("announcements", "deleted_by"),
            ("gallery_media", "deleted_by"),
            ("message_attachments", "deleted_by"),
            ("messages", "deleted_by"),
            ("live_recordings", "deleted_by"),
            ("timeline_posts", "deleted_by"),
            ("audit_logs", "user_id"),
            ("deposit_slips", "approved_by"),
            ("deposit_slips", "deleted_by"),
            ("finance_offerings", "deleted_by"),
        )
        for table, column in optional_user_refs:
            db.execute(f"UPDATE {table} SET {column} = NULL WHERE {column} = ?", (user_id,))

        db.execute("DELETE FROM committee_members WHERE user_id = ?", (user_id,))
        db.execute("DELETE FROM users WHERE id = ? AND deleted_at IS NOT NULL", (user_id,))
        db.commit()
    except Exception:
        db.rollback()
        raise


def deleted_user_count() -> int:
    row = get_db().execute(
        "SELECT COUNT(*) AS count FROM users WHERE deleted_at IS NOT NULL"
    ).fetchone()
    return int(row["count"])


def list_deleted_users(limit: int = 10, offset: int = 0) -> list[sqlite3.Row]:
    return get_db().execute(
        """
        SELECT
            users.id, users.full_name, users.email, users.role, users.deleted_at,
            users.identity_type, users.id_number, users.foreign_id_number, users.nationality,
            users.date_of_birth, users.emergency_contact_name, users.emergency_contact_phone,
            users.emergency_contact_relationship, deleter.full_name AS deleted_by_name
        FROM users
        LEFT JOIN users AS deleter ON deleter.id = users.deleted_by
        WHERE users.deleted_at IS NOT NULL
        ORDER BY datetime(users.deleted_at) DESC
        LIMIT ? OFFSET ?
        """
        ,
        (limit, offset),
    ).fetchall()


def list_messageable_users(current_user_id: int) -> list[sqlite3.Row]:
    return get_db().execute(
        """
        SELECT id, full_name, email, role, profile_photo, last_seen_at
        FROM users
        WHERE id != ?
          AND is_active = 1
          AND deleted_at IS NULL
        ORDER BY full_name COLLATE NOCASE
        """,
        (current_user_id,),
    ).fetchall()
