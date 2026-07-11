from __future__ import annotations

import sqlite3

from back_to_god.core.db import get_db
from back_to_god.core.security import today_date, utc_now
from back_to_god.core.validators import is_valid_email, validate_sa_id
from back_to_god.services.notifications import (
    notify_admins_membership_request,
    notify_admins_visitor_follow_up,
)
from back_to_god.services.users import (
    normalize_foreign_id,
    normalize_identity_type,
    normalize_nationality,
    normalize_text,
)


def clean_visitor_form(form) -> dict[str, object]:
    full_name = normalize_text(form.get("full_name", ""), 120)
    email = normalize_text(form.get("email", "").lower(), 120)
    identity_type = normalize_identity_type(form.get("identity_type", "sa_id"))
    clean_id = ""
    clean_foreign_id = ""
    date_of_birth = form.get("date_of_birth", "").strip()

    if not full_name:
        raise ValueError("Add the visitor's name before saving.")
    if email and not is_valid_email(email):
        raise ValueError("Add a valid email address.")

    if identity_type == "sa_id":
        valid_id, clean_id, dob_or_error = validate_sa_id(form.get("id_number", ""))
        if not valid_id:
            raise ValueError(dob_or_error)
        if clean_id:
            date_of_birth = dob_or_error
    else:
        clean_foreign_id = normalize_foreign_id(form.get("foreign_id_number", ""))
        if not clean_foreign_id:
            raise ValueError("Add a passport, permit, or foreign ID number.")

    follow_up_requested = form.get("follow_up_requested") == "on"
    membership_requested = form.get("membership_requested") == "on"
    if membership_requested and not email:
        raise ValueError("Add an email address so admins can create the membership account.")

    consent_to_contact = form.get("consent_to_contact") == "on" or follow_up_requested or membership_requested
    return {
        "full_name": full_name,
        "phone": normalize_text(form.get("phone", ""), 40),
        "email": email,
        "identity_type": identity_type,
        "id_number": clean_id,
        "foreign_id_number": clean_foreign_id,
        "nationality": normalize_nationality(identity_type, form.get("nationality", "")),
        "date_of_birth": date_of_birth,
        "visit_date": form.get("visit_date", "").strip() or today_date(),
        "visit_type": normalize_text(form.get("visit_type", ""), 40) or "First time",
        "age_group": normalize_text(form.get("age_group", ""), 40) or "Adult",
        "invited_by": normalize_text(form.get("invited_by", ""), 120),
        "home_area": normalize_text(form.get("home_area", ""), 120),
        "prayer_request": normalize_text(form.get("prayer_request", ""), 420),
        "notes": normalize_text(form.get("notes", ""), 420),
        "service_rating": normalize_text(form.get("service_rating", ""), 40),
        "service_feedback": normalize_text(form.get("service_feedback", ""), 700),
        "consent_to_contact": 1 if consent_to_contact else 0,
        "follow_up_requested": 1 if follow_up_requested else 0,
        "follow_up_status": "follow_up" if follow_up_requested else "new",
        "membership_requested": 1 if membership_requested else 0,
        "membership_status": "pending" if membership_requested else "none",
    }


def create_visitor(form, captured_by: int | None) -> int:
    now = utc_now()
    data = clean_visitor_form(form)
    cursor = get_db().execute(
        """
        INSERT INTO visitors (
            full_name, phone, email, identity_type, id_number, foreign_id_number, nationality,
            date_of_birth, visit_date, visit_type, age_group,
            invited_by, home_area, prayer_request, notes, service_rating, service_feedback,
            consent_to_contact, follow_up_status, follow_up_requested,
            membership_requested, membership_status, membership_requested_at,
            captured_by, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            data["full_name"],
            data["phone"],
            data["email"],
            data["identity_type"],
            data["id_number"],
            data["foreign_id_number"],
            data["nationality"],
            data["date_of_birth"],
            data["visit_date"],
            data["visit_type"],
            data["age_group"],
            data["invited_by"],
            data["home_area"],
            data["prayer_request"],
            data["notes"],
            data["service_rating"],
            data["service_feedback"],
            data["consent_to_contact"],
            data["follow_up_status"],
            data["follow_up_requested"],
            data["membership_requested"],
            data["membership_status"],
            now if data["membership_requested"] else None,
            captured_by,
            now,
            now,
        ),
    )
    visitor_id = int(cursor.lastrowid)
    if data["follow_up_requested"]:
        notify_admins_visitor_follow_up(visitor_id, str(data["full_name"]))
    if data["membership_requested"]:
        notify_admins_membership_request(visitor_id, str(data["full_name"]))
    if not data["follow_up_requested"] and not data["membership_requested"]:
        get_db().commit()
    return visitor_id


def count_visitors() -> dict[str, int]:
    db = get_db()
    return {
        "all": db.execute("SELECT COUNT(*) AS count FROM visitors").fetchone()["count"],
        "new": db.execute(
            "SELECT COUNT(*) AS count FROM visitors WHERE follow_up_status = 'new'"
        ).fetchone()["count"],
        "follow_up": db.execute(
            """
            SELECT COUNT(*) AS count
            FROM visitors
            WHERE follow_up_requested = 1 OR follow_up_status = 'follow_up'
            """
        ).fetchone()["count"],
        "connected": db.execute(
            "SELECT COUNT(*) AS count FROM visitors WHERE follow_up_status = 'connected'"
        ).fetchone()["count"],
        "follow_up_done": db.execute(
            "SELECT COUNT(*) AS count FROM visitors WHERE follow_up_made_at IS NOT NULL"
        ).fetchone()["count"],
        "membership_pending": db.execute(
            """
            SELECT COUNT(*) AS count
            FROM visitors
            WHERE membership_requested = 1 AND membership_status = 'pending'
            """
        ).fetchone()["count"],
        "open": db.execute(
            """
            SELECT COUNT(*) AS count
            FROM visitors
            WHERE (follow_up_requested = 1 OR follow_up_status = 'follow_up')
              AND follow_up_made_at IS NULL
            """
        ).fetchone()["count"],
    }


def visitor_analytics() -> dict:
    db = get_db()
    monthly = db.execute(
        """
        SELECT substr(visit_date, 1, 7) AS month, COUNT(*) AS count
        FROM visitors
        GROUP BY substr(visit_date, 1, 7)
        ORDER BY month DESC
        LIMIT 8
        """
    ).fetchall()
    status = db.execute(
        """
        SELECT follow_up_status AS label, COUNT(*) AS count
        FROM visitors
        GROUP BY follow_up_status
        ORDER BY count DESC
        """
    ).fetchall()
    identity = db.execute(
        """
        SELECT COALESCE(NULLIF(identity_type, ''), 'sa_id') AS label, COUNT(*) AS count
        FROM visitors
        GROUP BY COALESCE(NULLIF(identity_type, ''), 'sa_id')
        ORDER BY count DESC
        """
    ).fetchall()
    by_type = db.execute(
        """
        SELECT visit_type AS label, COUNT(*) AS count
        FROM visitors
        GROUP BY visit_type
        ORDER BY count DESC
        LIMIT 6
        """
    ).fetchall()
    return {
        "monthly": list(reversed(monthly)),
        "max_monthly": max([int(row["count"]) for row in monthly] or [1]),
        "status": status,
        "max_status": max([int(row["count"]) for row in status] or [1]),
        "identity": identity,
        "max_identity": max([int(row["count"]) for row in identity] or [1]),
        "by_type": by_type,
        "max_type": max([int(row["count"]) for row in by_type] or [1]),
    }


def visitor_list_count() -> int:
    row = get_db().execute("SELECT COUNT(*) AS count FROM visitors").fetchone()
    return int(row["count"])


def list_recent_visitors(limit: int = 10, offset: int = 0) -> list[sqlite3.Row]:
    return get_db().execute(
        """
        SELECT
            visitors.*,
            captured.full_name AS captured_by_name,
            follow_up_user.full_name AS follow_up_by_name
        FROM visitors
        LEFT JOIN users AS captured ON captured.id = visitors.captured_by
        LEFT JOIN users AS follow_up_user ON follow_up_user.id = visitors.follow_up_made_by
        ORDER BY date(visitors.visit_date) DESC, datetime(visitors.created_at) DESC
        LIMIT ? OFFSET ?
        """,
        (limit, offset),
    ).fetchall()


def get_visitor(visitor_id: int) -> sqlite3.Row | None:
    return get_db().execute("SELECT id FROM visitors WHERE id = ?", (visitor_id,)).fetchone()


def update_status(visitor_id: int, status: str) -> None:
    get_db().execute(
        """
        UPDATE visitors
        SET follow_up_status = ?,
            follow_up_requested = CASE WHEN ? = 'follow_up' THEN 1 ELSE follow_up_requested END,
            updated_at = ?
        WHERE id = ?
        """,
        (status, status, utc_now(), visitor_id),
    )
    if status == "follow_up":
        visitor = get_db().execute(
            "SELECT full_name FROM visitors WHERE id = ?",
            (visitor_id,),
        ).fetchone()
        notify_admins_visitor_follow_up(visitor_id, visitor["full_name"] if visitor else "A visitor")
    else:
        get_db().commit()


def mark_follow_up_made(visitor_id: int, made_by: int, notes: str = "") -> None:
    now = utc_now()
    get_db().execute(
        """
        UPDATE visitors
        SET follow_up_requested = 1,
            follow_up_status = 'connected',
            follow_up_made_at = ?,
            follow_up_made_by = ?,
            follow_up_notes = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (now, made_by, normalize_text(notes, 420), now, visitor_id),
    )
    get_db().commit()
