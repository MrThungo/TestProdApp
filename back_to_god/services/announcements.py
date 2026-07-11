from __future__ import annotations

import sqlite3
from datetime import datetime

from back_to_god.core.db import get_db
from back_to_god.core.security import utc_now
from back_to_god.services.users import normalize_text


def create_announcement(
    title: str,
    body: str,
    author_id: int,
    event_at: str = "",
    reminder_at: str = "",
    is_pinned: bool = False,
) -> int:
    compact_title = normalize_text(title, 120)
    compact_body = normalize_text(body, 1200)
    compact_event_at = normalize_text(event_at, 30)
    compact_reminder_at = normalize_text(reminder_at, 30)
    if not compact_title:
        raise ValueError("Add a title for the announcement.")
    if not compact_body:
        raise ValueError("Add announcement details.")

    now = utc_now()
    db = get_db()
    cursor = db.execute(
        """
        INSERT INTO announcements (
            title, body, event_at, reminder_at, is_pinned, created_by, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            compact_title,
            compact_body,
            compact_event_at,
            compact_reminder_at,
            1 if is_pinned else 0,
            author_id,
            now,
            now,
        ),
    )
    announcement_id = int(cursor.lastrowid)

    users = db.execute(
        """
        SELECT id
        FROM users
        WHERE is_active = 1
          AND deleted_at IS NULL
          AND id != ?
        """,
        (author_id,),
    ).fetchall()
    for user in users:
        db.execute(
            """
            INSERT INTO notifications (
                user_id, title, message, target_url, category, created_at
            )
            VALUES (?, ?, ?, ?, 'announcement', ?)
            """,
            (
                user["id"],
                "New announcement",
                compact_title,
                f"/announcements/#announcement-{announcement_id}",
                now,
            ),
        )

    db.commit()
    return announcement_id


def dispatch_due_announcement_reminders() -> int:
    now_local = datetime.now().isoformat(timespec="minutes")
    now = utc_now()
    db = get_db()
    due = db.execute(
        """
        SELECT id, title, reminder_at
        FROM announcements
        WHERE deleted_at IS NULL
          AND reminder_at IS NOT NULL
          AND reminder_at != ''
          AND reminder_sent_at IS NULL
          AND reminder_at <= ?
        ORDER BY datetime(reminder_at), id
        LIMIT 20
        """,
        (now_local,),
    ).fetchall()
    if not due:
        return 0

    users = db.execute(
        """
        SELECT id
        FROM users
        WHERE is_active = 1 AND deleted_at IS NULL
        """
    ).fetchall()
    for announcement in due:
        for user in users:
            db.execute(
                """
                INSERT INTO notifications (
                    user_id, title, message, target_url, category, created_at
                )
                VALUES (?, ?, ?, ?, 'announcement_reminder', ?)
                """,
                (
                    user["id"],
                    "Announcement reminder",
                    announcement["title"],
                    f"/announcements/#announcement-{announcement['id']}",
                    now,
                ),
            )
        db.execute(
            """
            UPDATE announcements
            SET reminder_sent_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (now, now, announcement["id"]),
        )

    db.commit()
    return len(due)


def announcement_count() -> int:
    row = get_db().execute(
        "SELECT COUNT(*) AS count FROM announcements WHERE deleted_at IS NULL"
    ).fetchone()
    return int(row["count"])


def list_announcements(limit: int = 10, offset: int = 0) -> list[sqlite3.Row]:
    return get_db().execute(
        """
        SELECT
            announcements.*,
            users.full_name AS author_name,
            users.profile_photo AS author_photo
        FROM announcements
        JOIN users ON users.id = announcements.created_by
        WHERE announcements.deleted_at IS NULL
        ORDER BY announcements.is_pinned DESC, datetime(announcements.created_at) DESC, announcements.id DESC
        LIMIT ? OFFSET ?
        """,
        (limit, offset),
    ).fetchall()


def list_recent_announcements(limit: int = 3) -> list[sqlite3.Row]:
    return list_announcements(limit, 0)


def latest_announcement_update() -> str:
    row = get_db().execute(
        "SELECT COALESCE(MAX(updated_at), '') AS latest_update FROM announcements"
    ).fetchone()
    return row["latest_update"] if row else ""


def get_announcement(announcement_id: int) -> sqlite3.Row | None:
    return get_db().execute(
        """
        SELECT *
        FROM announcements
        WHERE id = ? AND deleted_at IS NULL
        """,
        (announcement_id,),
    ).fetchone()


def soft_delete_announcement(
    announcement_id: int,
    deleted_by: int,
) -> sqlite3.Row | None:
    announcement = get_announcement(announcement_id)
    if announcement is None:
        return None
    now = utc_now()
    get_db().execute(
        """
        UPDATE announcements
        SET deleted_at = ?, deleted_by = ?, updated_at = ?
        WHERE id = ?
        """,
        (now, deleted_by, now, announcement_id),
    )
    get_db().commit()
    return announcement


def set_announcement_pin(
    announcement_id: int,
    is_pinned: bool,
) -> sqlite3.Row | None:
    announcement = get_announcement(announcement_id)
    if announcement is None:
        return None
    get_db().execute(
        """
        UPDATE announcements
        SET is_pinned = ?, updated_at = ?
        WHERE id = ?
        """,
        (1 if is_pinned else 0, utc_now(), announcement_id),
    )
    get_db().commit()
    return announcement
