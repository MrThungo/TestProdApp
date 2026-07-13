from __future__ import annotations

import sqlite3

from back_to_god.constants import ROLE_LABELS
from back_to_god.core.db import get_db
from back_to_god.core.security import utc_now
from back_to_god.services.users import (
    create_user,
    get_user_by_email,
    identity_exists,
    normalize_text,
)


def count_members() -> dict[str, int]:
    db = get_db()
    member_counts = db.execute(
        """
        SELECT
            COUNT(*) AS all_members,
            COALESCE(SUM(CASE WHEN is_active = 1 THEN 1 ELSE 0 END), 0) AS active,
            COALESCE(SUM(CASE WHEN is_active = 0 THEN 1 ELSE 0 END), 0) AS inactive
        FROM users
        WHERE role = 'member' AND deleted_at IS NULL
        """
    ).fetchone()
    request_counts = db.execute(
        """
        SELECT
            COALESCE(SUM(CASE WHEN membership_status = 'pending' THEN 1 ELSE 0 END), 0) AS pending_requests,
            COALESCE(SUM(CASE WHEN membership_status = 'approved' THEN 1 ELSE 0 END), 0) AS approved_from_visitors
        FROM visitors
        WHERE membership_requested = 1
        """
    ).fetchone()
    return {
        "all": int(member_counts["all_members"]),
        "active": int(member_counts["active"]),
        "inactive": int(member_counts["inactive"]),
        "pending_requests": int(request_counts["pending_requests"]),
        "approved_from_visitors": int(request_counts["approved_from_visitors"]),
    }


def _member_filter(query: str = "") -> tuple[str, list[object]]:
    where = "users.role = 'member' AND users.deleted_at IS NULL"
    params: list[object] = []
    compact_query = normalize_text(query, 80)
    if compact_query:
        like = f"%{compact_query}%"
        where += """
            AND (
                users.full_name LIKE ?
                OR users.email LIKE ?
                OR users.phone LIKE ?
                OR users.home_area LIKE ?
                OR users.id_number LIKE ?
                OR users.foreign_id_number LIKE ?
                OR users.nationality LIKE ?
            )
        """
        params.extend([like, like, like, like, like, like, like])
    return where, params


def member_directory_count(query: str = "") -> int:
    where, params = _member_filter(query)
    row = get_db().execute(
        f"SELECT COUNT(*) AS count FROM users WHERE {where}",
        tuple(params),
    ).fetchone()
    return int(row["count"])


def list_members(limit: int = 10, offset: int = 0, query: str = "") -> list[sqlite3.Row]:
    where, params = _member_filter(query)
    params.extend([limit, offset])
    return get_db().execute(
        f"""
        SELECT
            users.id, users.full_name, users.email, users.is_active, users.phone,
            users.home_area, users.identity_type, users.id_number, users.foreign_id_number,
            users.nationality, users.date_of_birth, users.created_at, users.last_login_at,
            users.last_seen_at,
            visitors.id AS source_visitor_id,
            visitors.visit_date AS source_visit_date,
            visitors.membership_reviewed_at AS member_approved_at,
            reviewer.full_name AS approved_by_name
        FROM users
        LEFT JOIN visitors
          ON visitors.id = (
            SELECT MAX(v2.id)
            FROM visitors AS v2
            WHERE v2.member_user_id = users.id
              AND v2.membership_status = 'approved'
          )
        LEFT JOIN users AS reviewer ON reviewer.id = visitors.membership_reviewed_by
        WHERE {where}
        ORDER BY users.full_name COLLATE NOCASE
        LIMIT ? OFFSET ?
        """,
        tuple(params),
    ).fetchall()


def list_pending_membership_requests(limit: int = 20) -> list[sqlite3.Row]:
    return get_db().execute(
        """
        SELECT
            visitors.*,
            captured.full_name AS captured_by_name
        FROM visitors
        LEFT JOIN users AS captured ON captured.id = visitors.captured_by
        WHERE visitors.membership_requested = 1
          AND visitors.membership_status = 'pending'
        ORDER BY datetime(visitors.membership_requested_at) ASC, visitors.id ASC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()


def approve_membership_request(
    visitor_id: int,
    approved_by: int,
    notes: str = "",
) -> tuple[sqlite3.Row, str, bool]:
    db = get_db()
    visitor = db.execute(
        """
        SELECT *
        FROM visitors
        WHERE id = ?
          AND membership_requested = 1
          AND membership_status = 'pending'
        """,
        (visitor_id,),
    ).fetchone()
    if visitor is None:
        raise ValueError("That membership request is no longer pending.")

    email = normalize_text(visitor["email"], 120).lower()
    if not email:
        raise ValueError("Add an email address to the visitor before approving membership.")

    member = get_user_by_email(email, include_deleted=True)
    password = ""
    created = False
    if member is not None:
        if member["deleted_at"]:
            raise ValueError("This email belongs to a user in the recycle bin. Restore that account first.")
        if not member["is_active"]:
            raise ValueError("This email belongs to a deactivated user. Activate that account first.")
        if member["role"] != "member":
            role_label = ROLE_LABELS.get(member["role"], member["role"].replace("_", " ").title())
            raise ValueError(f"This email already belongs to a {role_label} account.")
    else:
        if identity_exists(
            id_number=visitor["id_number"] or "",
            foreign_id_number=visitor["foreign_id_number"] or "",
        ):
            raise ValueError("Another user already has this visitor's identity number.")
        try:
            password = create_user(
                visitor["full_name"],
                email,
                "member",
                approved_by,
                visitor["id_number"] or "",
                visitor["date_of_birth"] or "",
                visitor["identity_type"] or "sa_id",
                visitor["foreign_id_number"] or "",
                visitor["nationality"] or "",
                phone=visitor["phone"] or "",
                home_area=visitor["home_area"] or "",
            )
        except sqlite3.IntegrityError as error:
            raise ValueError("Could not create the member account because the details already exist.") from error

        member = get_user_by_email(email)
        if member is None:
            raise RuntimeError("The member account was created but could not be loaded.")
        created = True

    now = utc_now()
    db.execute(
        """
        UPDATE visitors
        SET membership_status = 'approved',
            membership_reviewed_at = ?,
            membership_reviewed_by = ?,
            member_user_id = ?,
            membership_notes = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (
            now,
            approved_by,
            member["id"],
            normalize_text(notes, 420),
            now,
            visitor_id,
        ),
    )
    db.commit()
    return member, password, created
