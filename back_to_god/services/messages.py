from __future__ import annotations

from datetime import datetime
import sqlite3

from back_to_god.core.db import get_db
from back_to_god.core.security import utc_now
from back_to_god.services.users import normalize_text


ONLINE_SECONDS = 75
MAX_IMAGE_BYTES = 12 * 1024 * 1024
MAX_VOICE_BYTES = 16 * 1024 * 1024
MAX_VIDEO_BYTES = 48 * 1024 * 1024
MAX_FILE_BYTES = 24 * 1024 * 1024
IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
VOICE_TYPES = {"audio/webm", "audio/ogg", "audio/mpeg", "audio/mp4", "audio/wav"}
VIDEO_TYPES = {"video/mp4", "video/webm", "video/ogg"}
FILE_TYPES = {
    "application/pdf",
    "text/plain",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def presence_state(last_seen_at: str | None) -> dict[str, str | bool]:
    if not last_seen_at:
        return {"online": False, "label": "Offline"}
    try:
        last_seen = datetime.fromisoformat(last_seen_at)
        if last_seen.tzinfo is not None:
            last_seen = last_seen.astimezone().replace(tzinfo=None)
    except ValueError:
        return {"online": False, "label": "Offline"}

    seconds = (datetime.now() - last_seen).total_seconds()
    if seconds <= ONLINE_SECONDS:
        return {"online": True, "label": "Online"}
    if seconds < 3600:
        minutes = max(1, int(seconds // 60))
        return {"online": False, "label": f"Last seen {minutes} min ago"}
    return {"online": False, "label": f"Last seen {last_seen.strftime('%d %b %H:%M')}"}


def _validate_attachment(
    file_storage,
    media_kind: str,
    allow_unlimited_video: bool = False,
) -> tuple[str, str, bytes]:
    if media_kind not in {"image", "voice", "video", "file"}:
        raise ValueError("Unsupported media type.")
    if not file_storage or not file_storage.filename:
        raise ValueError("No media file was attached.")

    data = file_storage.read()
    if not data:
        raise ValueError("The attached media file is empty.")

    mime_type = (file_storage.mimetype or "").lower()
    if media_kind == "image":
        if mime_type not in IMAGE_TYPES:
            raise ValueError("Upload a JPG, PNG, WEBP, or GIF image.")
        if len(data) > MAX_IMAGE_BYTES:
            raise ValueError("Image is too large. Keep it under 12 MB.")
    if media_kind == "voice":
        if mime_type not in VOICE_TYPES:
            raise ValueError("Voice note format is not supported.")
        if len(data) > MAX_VOICE_BYTES:
            raise ValueError("Voice note is too large. Keep it under 16 MB.")
    if media_kind == "video":
        if mime_type not in VIDEO_TYPES:
            raise ValueError("Upload an MP4, WEBM, or OGG video.")
        if not allow_unlimited_video and len(data) > MAX_VIDEO_BYTES:
            raise ValueError("Video is too large. Keep it under 48 MB.")
    if media_kind == "file":
        if mime_type not in FILE_TYPES:
            raise ValueError("Upload a PDF, text, Word, or Excel document.")
        if len(data) > MAX_FILE_BYTES:
            raise ValueError("Attachment is too large. Keep it under 24 MB.")

    return mime_type, normalize_text(file_storage.filename, 140), data


def send_message(
    sender_id: int,
    recipient_id: int,
    body: str,
    media_file=None,
    media_kind: str | None = None,
) -> int:
    compact_body = normalize_text(body, 900)
    sender = get_db().execute(
        "SELECT full_name, role FROM users WHERE id = ?",
        (sender_id,),
    ).fetchone()
    attachment = None
    if media_file is not None and media_kind:
        attachment = _validate_attachment(
            media_file,
            media_kind,
            allow_unlimited_video=media_kind == "video" and sender is not None and sender["role"] == "videographer",
        )
    if not compact_body and attachment is None:
        raise ValueError("Message cannot be empty.")

    now = utc_now()
    cursor = get_db().execute(
        """
        INSERT INTO messages (sender_id, recipient_id, body, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (sender_id, recipient_id, compact_body, now, now),
    )
    message_id = int(cursor.lastrowid)
    if attachment is not None and media_kind:
        mime_type, original_name, data = attachment
        get_db().execute(
            """
            INSERT INTO message_attachments (
                message_id, media_kind, mime_type, original_name, size_bytes, data, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (message_id, media_kind, mime_type, original_name, len(data), data, now),
        )

    get_db().commit()
    return message_id


def list_thread(current_user_id: int, other_user_id: int, after_id: int = 0) -> list[sqlite3.Row]:
    rows = get_db().execute(
        """
        SELECT
            messages.*,
            sender.full_name AS sender_name,
            message_attachments.id AS attachment_id,
            message_attachments.media_kind,
            message_attachments.mime_type,
            message_attachments.original_name,
            message_attachments.size_bytes,
            message_attachments.deleted_at AS attachment_deleted_at
        FROM messages
        JOIN users AS sender ON sender.id = messages.sender_id
        LEFT JOIN message_attachments
          ON message_attachments.message_id = messages.id
         AND message_attachments.deleted_at IS NULL
        WHERE messages.id > ?
          AND (
            (messages.sender_id = ? AND messages.recipient_id = ?)
            OR
            (messages.sender_id = ? AND messages.recipient_id = ?)
          )
        ORDER BY messages.id
        """,
        (after_id, current_user_id, other_user_id, other_user_id, current_user_id),
    ).fetchall()
    mark_thread_read(current_user_id, other_user_id)
    return rows


def mark_thread_read(current_user_id: int, other_user_id: int) -> None:
    get_db().execute(
        """
        UPDATE messages
        SET is_read = 1
        WHERE recipient_id = ? AND sender_id = ? AND is_read = 0
        """,
        (current_user_id, other_user_id),
    )
    get_db().commit()


def unread_message_count(user_id: int) -> int:
    row = get_db().execute(
        """
        SELECT COUNT(*) AS count
        FROM messages
        WHERE recipient_id = ? AND is_read = 0
        """,
        (user_id,),
    ).fetchone()
    return int(row["count"])


def unread_by_sender(user_id: int) -> dict[int, int]:
    rows = get_db().execute(
        """
        SELECT sender_id, COUNT(*) AS count
        FROM messages
        WHERE recipient_id = ? AND is_read = 0
        GROUP BY sender_id
        """,
        (user_id,),
    ).fetchall()
    return {int(row["sender_id"]): int(row["count"]) for row in rows}


def last_message_by_user(user_id: int) -> dict[int, sqlite3.Row]:
    rows = get_db().execute(
        """
        SELECT
            messages.*,
            message_attachments.id AS attachment_id,
            message_attachments.media_kind,
            message_attachments.mime_type,
            message_attachments.original_name,
            message_attachments.size_bytes,
            message_attachments.deleted_at AS attachment_deleted_at
        FROM messages
        LEFT JOIN message_attachments
          ON message_attachments.message_id = messages.id
         AND message_attachments.deleted_at IS NULL
        WHERE messages.id IN (
            SELECT MAX(id)
            FROM messages
            WHERE sender_id = ? OR recipient_id = ?
            GROUP BY CASE WHEN sender_id = ? THEN recipient_id ELSE sender_id END
        )
        """,
        (user_id, user_id, user_id),
    ).fetchall()
    last_messages = {}
    for row in rows:
        other_id = row["recipient_id"] if row["sender_id"] == user_id else row["sender_id"]
        last_messages[int(other_id)] = row
    return last_messages


def list_thread_changes(
    current_user_id: int,
    other_user_id: int,
    since: str,
    known_until_id: int,
) -> list[sqlite3.Row]:
    if not since:
        return []
    rows = get_db().execute(
        """
        SELECT
            messages.*,
            sender.full_name AS sender_name,
            message_attachments.id AS attachment_id,
            message_attachments.media_kind,
            message_attachments.mime_type,
            message_attachments.original_name,
            message_attachments.size_bytes,
            message_attachments.deleted_at AS attachment_deleted_at
        FROM messages
        JOIN users AS sender ON sender.id = messages.sender_id
        LEFT JOIN message_attachments
          ON message_attachments.message_id = messages.id
         AND message_attachments.deleted_at IS NULL
        WHERE messages.id <= ?
          AND COALESCE(messages.updated_at, messages.created_at) > ?
          AND (
            (messages.sender_id = ? AND messages.recipient_id = ?)
            OR
            (messages.sender_id = ? AND messages.recipient_id = ?)
          )
        ORDER BY messages.id
        """,
        (
            known_until_id,
            since,
            current_user_id,
            other_user_id,
            other_user_id,
            current_user_id,
        ),
    ).fetchall()
    return rows


def get_attachment_for_user(attachment_id: int, user_id: int) -> sqlite3.Row | None:
    return get_db().execute(
        """
        SELECT
            message_attachments.id,
            message_attachments.message_id,
            message_attachments.media_kind,
            message_attachments.mime_type,
            message_attachments.original_name,
            message_attachments.size_bytes,
            message_attachments.created_at,
            message_attachments.deleted_at,
            message_attachments.deleted_by,
            messages.sender_id,
            messages.recipient_id
        FROM message_attachments
        JOIN messages ON messages.id = message_attachments.message_id
        WHERE message_attachments.id = ?
          AND (messages.sender_id = ? OR messages.recipient_id = ?)
          AND message_attachments.deleted_at IS NULL
        """,
        (attachment_id, user_id, user_id),
    ).fetchone()


def attachment_bytes(attachment_id: int, user_id: int, start: int = 0, length: int | None = None):
    if length is None:
        row = get_db().execute(
            """
            SELECT message_attachments.data
            FROM message_attachments
            JOIN messages ON messages.id = message_attachments.message_id
            WHERE message_attachments.id = ?
              AND (messages.sender_id = ? OR messages.recipient_id = ?)
              AND message_attachments.deleted_at IS NULL
            """,
            (attachment_id, user_id, user_id),
        ).fetchone()
    else:
        row = get_db().execute(
            """
            SELECT substr(message_attachments.data, ?, ?) AS data
            FROM message_attachments
            JOIN messages ON messages.id = message_attachments.message_id
            WHERE message_attachments.id = ?
              AND (messages.sender_id = ? OR messages.recipient_id = ?)
              AND message_attachments.deleted_at IS NULL
            """,
            (start + 1, length, attachment_id, user_id, user_id),
        ).fetchone()
    if row:
        yield row["data"]


def get_message_for_user(message_id: int, user_id: int) -> sqlite3.Row | None:
    return get_db().execute(
        """
        SELECT *
        FROM messages
        WHERE id = ?
          AND (sender_id = ? OR recipient_id = ?)
        """,
        (message_id, user_id, user_id),
    ).fetchone()


def edit_message(message_id: int, user_id: int, body: str) -> None:
    message = get_message_for_user(message_id, user_id)
    if message is None:
        raise PermissionError("Message was not found.")
    if message["sender_id"] != user_id:
        raise PermissionError("Only the sender can edit this message.")
    if message["deleted_at"]:
        raise ValueError("Deleted messages cannot be edited.")

    compact_body = normalize_text(body, 900)
    if not compact_body:
        raise ValueError("Message cannot be empty.")
    now = utc_now()
    get_db().execute(
        """
        UPDATE messages
        SET body = ?, edited_at = ?, updated_at = ?
        WHERE id = ?
        """,
        (compact_body, now, now, message_id),
    )
    get_db().commit()


def delete_message(message_id: int, user_id: int) -> None:
    message = get_message_for_user(message_id, user_id)
    if message is None:
        raise PermissionError("Message was not found.")
    if message["sender_id"] != user_id:
        raise PermissionError("Only the sender can delete this message.")

    now = utc_now()
    get_db().execute(
        """
        UPDATE messages
        SET body = '', deleted_at = ?, deleted_by = ?, updated_at = ?
        WHERE id = ?
        """,
        (now, user_id, now, message_id),
    )
    get_db().execute(
        """
        UPDATE message_attachments
        SET data = X'', size_bytes = 0, deleted_at = ?, deleted_by = ?
        WHERE message_id = ? AND deleted_at IS NULL
        """,
        (now, user_id, message_id),
    )
    get_db().commit()


def delete_attachment_for_user(attachment_id: int, user_id: int) -> None:
    attachment = get_attachment_for_user(attachment_id, user_id)
    if attachment is None:
        raise PermissionError("Attachment was not found.")

    now = utc_now()
    get_db().execute(
        """
        UPDATE message_attachments
        SET data = X'', size_bytes = 0, deleted_at = ?, deleted_by = ?
        WHERE id = ?
        """,
        (now, user_id, attachment_id),
    )
    get_db().execute(
        "UPDATE messages SET updated_at = ? WHERE id = ?",
        (now, attachment["message_id"]),
    )
    get_db().commit()
