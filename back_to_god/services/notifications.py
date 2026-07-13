from __future__ import annotations

import sqlite3

from back_to_god.core.db import get_db
from back_to_god.core.security import utc_now
from back_to_god.services.users import normalize_text


VISIBLE_NOTIFICATION_FILTER = "COALESCE(category, '') != 'message'"


def create_notification(
    user_id: int,
    title: str,
    message: str,
    target_url: str = "",
    category: str = "general",
) -> None:
    get_db().execute(
        """
        INSERT INTO notifications (user_id, title, message, target_url, category, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            normalize_text(title, 80),
            normalize_text(message, 220),
            normalize_text(target_url, 140),
            normalize_text(category, 40),
            utc_now(),
        ),
    )


def notify_live_started(live_session_id: int, title: str, started_by: int) -> None:
    db = get_db()
    db.execute(
        """
        INSERT INTO notifications (user_id, title, message, target_url, category, created_at)
        SELECT id, ?, ?, ?, 'live', ?
        FROM users
        WHERE is_active = 1
          AND deleted_at IS NULL
          AND id != ?
        """,
        (
            "Live now",
            normalize_text(f"{title} has started.", 220),
            f"/live/{live_session_id}",
            utc_now(),
            started_by,
        ),
    )
    db.commit()


def notify_admins_visitor_follow_up(visitor_id: int, visitor_name: str) -> None:
    db = get_db()
    db.execute(
        """
        INSERT INTO notifications (user_id, title, message, target_url, category, created_at)
        SELECT id, 'Visitor follow-up', ?, ?, 'visitor', ?
        FROM users
        WHERE role = 'admin'
          AND is_active = 1
          AND deleted_at IS NULL
        """,
        (
            normalize_text(f"{visitor_name} requested follow-up.", 220),
            f"/visitors/#visitor-{visitor_id}",
            utc_now(),
        ),
    )
    db.commit()


def notify_admins_membership_request(visitor_id: int, visitor_name: str) -> None:
    db = get_db()
    db.execute(
        """
        INSERT INTO notifications (user_id, title, message, target_url, category, created_at)
        SELECT id, 'Membership request', ?, ?, 'membership', ?
        FROM users
        WHERE role IN ('super_admin', 'admin')
          AND is_active = 1
          AND deleted_at IS NULL
        """,
        (
            normalize_text(f"{visitor_name} asked to become a member.", 220),
            f"/members/#membership-request-{visitor_id}",
            utc_now(),
        ),
    )
    db.commit()


def notification_count(user_id: int) -> int:
    row = get_db().execute(
        f"SELECT COUNT(*) AS count FROM notifications WHERE user_id = ? AND {VISIBLE_NOTIFICATION_FILTER}",
        (user_id,),
    ).fetchone()
    return int(row["count"])


def list_notifications(user_id: int, limit: int = 12, offset: int = 0) -> list[sqlite3.Row]:
    return get_db().execute(
        """
        SELECT id, title, message, target_url, category, is_read, created_at
        FROM notifications
        WHERE user_id = ? AND COALESCE(category, '') != 'message'
        ORDER BY datetime(created_at) DESC, id DESC
        LIMIT ? OFFSET ?
        """,
        (user_id, limit, offset),
    ).fetchall()


def unread_count(user_id: int) -> int:
    row = get_db().execute(
        """
        SELECT COUNT(*) AS count
        FROM notifications
        WHERE user_id = ? AND is_read = 0 AND COALESCE(category, '') != 'message'
        """,
        (user_id,),
    ).fetchone()
    return int(row["count"])


def mark_all_read(user_id: int) -> None:
    get_db().execute(
        "UPDATE notifications SET is_read = 1 WHERE user_id = ? AND COALESCE(category, '') != 'message'",
        (user_id,),
    )
    get_db().commit()


def get_notification(user_id: int, notification_id: int) -> sqlite3.Row | None:
    return get_db().execute(
        """
        SELECT id, target_url
        FROM notifications
        WHERE id = ? AND user_id = ? AND COALESCE(category, '') != 'message'
        """,
        (notification_id, user_id),
    ).fetchone()


def mark_read(user_id: int, notification_id: int) -> None:
    get_db().execute(
        """
        UPDATE notifications
        SET is_read = 1
        WHERE id = ? AND user_id = ? AND COALESCE(category, '') != 'message'
        """,
        (notification_id, user_id),
    )
    get_db().commit()


def delete_notification(user_id: int, notification_id: int) -> None:
    get_db().execute(
        "DELETE FROM notifications WHERE id = ? AND user_id = ? AND COALESCE(category, '') != 'message'",
        (notification_id, user_id),
    )
    get_db().commit()


def clear_notifications(user_id: int) -> None:
    get_db().execute(
        "DELETE FROM notifications WHERE user_id = ? AND COALESCE(category, '') != 'message'",
        (user_id,),
    )
    get_db().commit()
