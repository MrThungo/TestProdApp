from __future__ import annotations

import sqlite3

from back_to_god.core.db import get_db
from back_to_god.core.security import today_date, utc_now
from back_to_god.core.validators import only_digits
from back_to_god.services.users import (
    normalize_foreign_id,
    normalize_identity_type,
    normalize_nationality,
    normalize_text,
)


def create_visitor(form, captured_by: int) -> None:
    now = utc_now()
    identity_type = normalize_identity_type(form.get("identity_type", "sa_id"))
    get_db().execute(
        """
        INSERT INTO visitors (
            full_name, phone, email, identity_type, id_number, foreign_id_number, nationality,
            date_of_birth, visit_date, visit_type, age_group,
            invited_by, home_area, prayer_request, notes, consent_to_contact,
            captured_by, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            normalize_text(form.get("full_name", ""), 120),
            normalize_text(form.get("phone", ""), 40),
            normalize_text(form.get("email", "").lower(), 120),
            identity_type,
            only_digits(form.get("id_number", ""), 13) if identity_type == "sa_id" else "",
            normalize_foreign_id(form.get("foreign_id_number", "")) if identity_type == "foreign" else "",
            normalize_nationality(identity_type, form.get("nationality", "")),
            form.get("date_of_birth", "").strip(),
            form.get("visit_date", "").strip() or today_date(),
            normalize_text(form.get("visit_type", ""), 40) or "First time",
            normalize_text(form.get("age_group", ""), 40) or "Adult",
            normalize_text(form.get("invited_by", ""), 120),
            normalize_text(form.get("home_area", ""), 120),
            normalize_text(form.get("prayer_request", ""), 420),
            normalize_text(form.get("notes", ""), 420),
            1 if form.get("consent_to_contact") == "on" else 0,
            captured_by,
            now,
            now,
        ),
    )
    get_db().commit()


def count_visitors() -> dict[str, int]:
    db = get_db()
    return {
        "all": db.execute("SELECT COUNT(*) AS count FROM visitors").fetchone()["count"],
        "new": db.execute(
            "SELECT COUNT(*) AS count FROM visitors WHERE follow_up_status = 'new'"
        ).fetchone()["count"],
        "follow_up": db.execute(
            "SELECT COUNT(*) AS count FROM visitors WHERE follow_up_status = 'follow_up'"
        ).fetchone()["count"],
        "connected": db.execute(
            "SELECT COUNT(*) AS count FROM visitors WHERE follow_up_status = 'connected'"
        ).fetchone()["count"],
        "open": db.execute(
            "SELECT COUNT(*) AS count FROM visitors WHERE follow_up_status IN ('new', 'follow_up')"
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
        SELECT visitors.*, users.full_name AS captured_by_name
        FROM visitors
        LEFT JOIN users ON users.id = visitors.captured_by
        ORDER BY date(visitors.visit_date) DESC, datetime(visitors.created_at) DESC
        LIMIT ? OFFSET ?
        """,
        (limit, offset),
    ).fetchall()


def get_visitor(visitor_id: int) -> sqlite3.Row | None:
    return get_db().execute("SELECT id FROM visitors WHERE id = ?", (visitor_id,)).fetchone()


def update_status(visitor_id: int, status: str) -> None:
    get_db().execute(
        "UPDATE visitors SET follow_up_status = ?, updated_at = ? WHERE id = ?",
        (status, utc_now(), visitor_id),
    )
    get_db().commit()
