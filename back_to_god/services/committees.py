from __future__ import annotations

import sqlite3

from back_to_god.core.db import get_db
from back_to_god.core.security import utc_now
from back_to_god.services.users import normalize_text


def can_manage_committees(role: str) -> bool:
    return role in {"super_admin", "admin"}


def create_committee(name: str, description: str, created_by: int) -> int:
    compact_name = normalize_text(name, 120)
    if not compact_name:
        raise ValueError("Add a committee name.")

    now = utc_now()
    cursor = get_db().execute(
        """
        INSERT INTO committees (name, description, created_by, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (compact_name, normalize_text(description, 700), created_by, now, now),
    )
    get_db().commit()
    return int(cursor.lastrowid)


def get_committee(committee_id: int) -> sqlite3.Row | None:
    return get_db().execute(
        """
        SELECT *
        FROM committees
        WHERE id = ? AND deleted_at IS NULL
        """,
        (committee_id,),
    ).fetchone()


def list_committee_user_options() -> list[sqlite3.Row]:
    return get_db().execute(
        """
        SELECT id, full_name, email, role, profile_photo
        FROM users
        WHERE is_active = 1 AND deleted_at IS NULL
        ORDER BY full_name COLLATE NOCASE
        """
    ).fetchall()


def list_committees() -> list[dict]:
    committees = get_db().execute(
        """
        SELECT committees.*, creator.full_name AS created_by_name
        FROM committees
        LEFT JOIN users AS creator ON creator.id = committees.created_by
        WHERE committees.deleted_at IS NULL
        ORDER BY committees.name COLLATE NOCASE
        """
    ).fetchall()

    results: list[dict] = []
    for committee in committees:
        members = get_db().execute(
            """
            SELECT
                committee_members.id AS membership_id,
                committee_members.title AS committee_title,
                committee_members.sort_order,
                users.id,
                users.full_name,
                users.email,
                users.role,
                users.phone,
                users.home_area,
                users.profile_photo
            FROM committee_members
            JOIN users ON users.id = committee_members.user_id
            WHERE committee_members.committee_id = ?
              AND users.deleted_at IS NULL
              AND users.is_active = 1
            ORDER BY committee_members.sort_order, users.full_name COLLATE NOCASE
            """,
            (committee["id"],),
        ).fetchall()
        results.append({"committee": committee, "members": members})
    return results


def add_committee_member(
    committee_id: int,
    user_id: int,
    title: str,
    sort_order: int,
) -> None:
    if get_committee(committee_id) is None:
        raise ValueError("That committee could not be found.")

    user = get_db().execute(
        """
        SELECT id
        FROM users
        WHERE id = ? AND is_active = 1 AND deleted_at IS NULL
        """,
        (user_id,),
    ).fetchone()
    if user is None:
        raise ValueError("Choose an active user for the committee.")

    now = utc_now()
    get_db().execute(
        """
        INSERT INTO committee_members (
            committee_id, user_id, title, sort_order, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(committee_id, user_id) DO UPDATE SET
            title = excluded.title,
            sort_order = excluded.sort_order,
            updated_at = excluded.updated_at
        """,
        (committee_id, user_id, normalize_text(title, 120), sort_order, now, now),
    )
    get_db().execute(
        "UPDATE committees SET updated_at = ? WHERE id = ?",
        (now, committee_id),
    )
    get_db().commit()


def remove_committee_member(membership_id: int) -> sqlite3.Row | None:
    row = get_db().execute(
        """
        SELECT committee_members.*, users.full_name
        FROM committee_members
        JOIN users ON users.id = committee_members.user_id
        WHERE committee_members.id = ?
        """,
        (membership_id,),
    ).fetchone()
    if row is None:
        return None

    now = utc_now()
    get_db().execute("DELETE FROM committee_members WHERE id = ?", (membership_id,))
    get_db().execute(
        "UPDATE committees SET updated_at = ? WHERE id = ?",
        (now, row["committee_id"]),
    )
    get_db().commit()
    return row


def soft_delete_committee(committee_id: int, deleted_by: int) -> sqlite3.Row | None:
    committee = get_committee(committee_id)
    if committee is None:
        return None

    now = utc_now()
    get_db().execute(
        """
        UPDATE committees
        SET deleted_at = ?, deleted_by = ?, updated_at = ?
        WHERE id = ?
        """,
        (now, deleted_by, now, committee_id),
    )
    get_db().commit()
    return committee
