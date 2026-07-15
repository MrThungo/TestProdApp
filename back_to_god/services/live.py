from __future__ import annotations

import json
import sqlite3

from back_to_god.core.db import connect_database, get_db
from back_to_god.core.security import utc_now
from back_to_god.services.notifications import notify_live_started
from back_to_god.services.users import normalize_text


MAX_SIGNAL_BYTES = 70000
MAX_RECORDING_BYTES = 950 * 1024 * 1024
VIDEO_TYPES = {"video/webm", "video/mp4", "video/ogg"}
REACTION_TYPES = {"like", "heart", "amen", "clap", "fire"}


def _live_select() -> str:
    return """
        live_sessions.*,
        users.full_name AS streamer_name,
        CASE
            WHEN live_sessions.recording_deleted_at IS NULL
                THEN COALESCE(recordings.recording_count, 0)
            ELSE 0
        END AS recording_available,
        CASE
            WHEN live_sessions.recording_deleted_at IS NULL
                THEN COALESCE(recordings.total_bytes, 0)
            ELSE 0
        END AS recording_bytes
    """


def _recording_join() -> str:
    return """
        LEFT JOIN (
            SELECT
                live_session_id,
                1 AS recording_count,
                size_bytes AS total_bytes
            FROM live_recordings
            WHERE deleted_at IS NULL
        ) AS recordings ON recordings.live_session_id = live_sessions.id
    """


def list_active_sessions() -> list[sqlite3.Row]:
    return get_db().execute(
        f"""
        SELECT {_live_select()}
        FROM live_sessions
        JOIN users ON users.id = live_sessions.started_by
        {_recording_join()}
        WHERE live_sessions.status = 'active'
        ORDER BY datetime(live_sessions.started_at) DESC
        """
    ).fetchall()


def list_recent_sessions(limit: int = 8) -> list[sqlite3.Row]:
    return get_db().execute(
        f"""
        SELECT {_live_select()}
        FROM live_sessions
        JOIN users ON users.id = live_sessions.started_by
        {_recording_join()}
        ORDER BY datetime(live_sessions.started_at) DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()


def _recorded_where(query: str = "") -> tuple[str, list[object]]:
    compact_query = normalize_text(query, 90)
    params: list[object] = []
    where = """
        live_sessions.status = 'ended'
        AND live_sessions.recording_deleted_at IS NULL
        AND COALESCE(recordings.recording_count, 0) > 0
    """
    if compact_query:
        like = f"%{compact_query}%"
        where += """
            AND (
                live_sessions.title LIKE ?
                OR live_sessions.description LIKE ?
                OR users.full_name LIKE ?
            )
        """
        params.extend([like, like, like])
    return where, params


def recorded_session_count(query: str = "") -> int:
    where, params = _recorded_where(query)
    row = get_db().execute(
        f"""
        SELECT COUNT(*) AS count
        FROM live_sessions
        JOIN users ON users.id = live_sessions.started_by
        {_recording_join()}
        WHERE {where}
        """,
        tuple(params),
    ).fetchone()
    return int(row["count"])


def list_recorded_sessions(query: str = "", limit: int = 30, offset: int = 0) -> list[sqlite3.Row]:
    where, params = _recorded_where(query)
    params.append(limit)
    params.append(offset)
    return get_db().execute(
        f"""
        SELECT {_live_select()}
        FROM live_sessions
        JOIN users ON users.id = live_sessions.started_by
        {_recording_join()}
        WHERE {where}
        ORDER BY datetime(live_sessions.started_at) DESC
        LIMIT ? OFFSET ?
        """,
        tuple(params),
    ).fetchall()


def count_active_sessions() -> int:
    row = get_db().execute(
        "SELECT COUNT(*) AS count FROM live_sessions WHERE status = 'active'"
    ).fetchone()
    return int(row["count"])


def get_live_session(live_id: int) -> sqlite3.Row | None:
    return get_db().execute(
        f"""
        SELECT {_live_select()}
        FROM live_sessions
        JOIN users ON users.id = live_sessions.started_by
        {_recording_join()}
        WHERE live_sessions.id = ?
        """,
        (live_id,),
    ).fetchone()


def get_live_session_basic(live_id: int) -> sqlite3.Row | None:
    return get_db().execute(
        """
        SELECT live_sessions.*, users.full_name AS streamer_name
        FROM live_sessions
        JOIN users ON users.id = live_sessions.started_by
        WHERE live_sessions.id = ?
        """,
        (live_id,),
    ).fetchone()


def start_live_session(title: str, description: str, started_by: int) -> int:
    now = utc_now()
    cursor = get_db().execute(
        """
        INSERT INTO live_sessions (title, description, started_by, started_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            normalize_text(title or "Back to God live", 90),
            normalize_text(description, 260),
            started_by,
            now,
            now,
        ),
    )
    live_id = int(cursor.lastrowid)
    notify_live_started(live_id, title or "Back to God live", started_by)
    get_db().commit()
    return live_id


def end_live_session(live_id: int) -> None:
    now = utc_now()
    db = get_db()
    db.execute(
        """
        UPDATE live_sessions
        SET status = 'ended', ended_at = ?, updated_at = ?
        WHERE id = ?
        """,
        (now, now, live_id),
    )
    db.execute("DELETE FROM webrtc_signals WHERE live_session_id = ?", (live_id,))
    db.commit()


def add_signal(
    live_id: int,
    viewer_token: str,
    sender_role: str,
    signal_type: str,
    payload,
) -> int:
    compact_payload = json.dumps(payload, separators=(",", ":"))
    if len(compact_payload.encode("utf-8")) > MAX_SIGNAL_BYTES:
        raise ValueError("The live signal is too large.")

    cursor = get_db().execute(
        """
        INSERT INTO webrtc_signals (
            live_session_id, viewer_token, sender_role, signal_type, payload, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            live_id,
            normalize_text(viewer_token, 80),
            sender_role,
            signal_type,
            compact_payload,
            utc_now(),
        ),
    )
    get_db().commit()
    return int(cursor.lastrowid)


def list_signals_for_streamer(live_id: int, after_id: int = 0) -> list[sqlite3.Row]:
    return get_db().execute(
        """
        SELECT id, viewer_token, sender_role, signal_type, payload
        FROM webrtc_signals
        WHERE live_session_id = ? AND sender_role = 'viewer' AND id > ?
        ORDER BY id
        """,
        (live_id, after_id),
    ).fetchall()


def list_signals_for_viewer(
    live_id: int,
    viewer_token: str,
    after_id: int = 0,
) -> list[sqlite3.Row]:
    return get_db().execute(
        """
        SELECT id, viewer_token, sender_role, signal_type, payload
        FROM webrtc_signals
        WHERE live_session_id = ?
          AND viewer_token = ?
          AND sender_role = 'streamer'
          AND id > ?
        ORDER BY id
        """,
        (live_id, normalize_text(viewer_token, 80), after_id),
    ).fetchall()


def save_live_recording(live_id: int, mime_type: str, data: bytes) -> int:
    base_mime_type = (mime_type or "").split(";")[0].lower()
    if base_mime_type not in VIDEO_TYPES:
        raise ValueError("Recording format is not supported.")
    if not data:
        raise ValueError("Recording is empty.")
    if len(data) > MAX_RECORDING_BYTES:
        raise ValueError("The compressed recording is too large. Use a shorter live session or lower camera quality.")

    db = get_db()
    session = db.execute(
        "SELECT id, recording_deleted_at FROM live_sessions WHERE id = ?",
        (live_id,),
    ).fetchone()
    if session is None:
        raise ValueError("This live session was not found.")
    if session["recording_deleted_at"]:
        raise ValueError("This live recording has been deleted.")

    now = utc_now()
    cursor = db.execute(
        """
        INSERT INTO live_recordings (
            live_session_id, mime_type, size_bytes, data, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(live_session_id)
        DO UPDATE SET
            mime_type = excluded.mime_type,
            size_bytes = excluded.size_bytes,
            data = excluded.data,
            updated_at = excluded.updated_at,
            deleted_at = NULL,
            deleted_by = NULL
        """,
        (live_id, base_mime_type, len(data), data, now, now),
    )
    db.execute("UPDATE live_sessions SET updated_at = ? WHERE id = ?", (now, live_id))
    db.commit()
    return int(cursor.lastrowid or live_id)


def get_recording_meta(live_id: int) -> sqlite3.Row | None:
    finalized = get_db().execute(
        """
        SELECT
            live_recordings.live_session_id,
            live_recordings.mime_type,
            1 AS recording_count,
            live_recordings.size_bytes AS total_bytes,
            live_recordings.updated_at,
            1 AS is_finalized
        FROM live_recordings
        JOIN live_sessions ON live_sessions.id = live_recordings.live_session_id
        WHERE live_recordings.live_session_id = ?
          AND live_recordings.deleted_at IS NULL
          AND live_sessions.recording_deleted_at IS NULL
        """,
        (live_id,),
    ).fetchone()
    return finalized


def recording_bytes(live_id: int, start: int = 0, length: int | None = None):
    connection = connect_database()
    try:
        if length is None:
            finalized = connection.execute(
                """
                SELECT live_recordings.data
                FROM live_recordings
                JOIN live_sessions ON live_sessions.id = live_recordings.live_session_id
                WHERE live_recordings.live_session_id = ?
                  AND live_recordings.deleted_at IS NULL
                  AND live_sessions.recording_deleted_at IS NULL
                """,
                (live_id,),
            ).fetchone()
        else:
            finalized = connection.execute(
                """
                SELECT substr(live_recordings.data, ?, ?) AS data
                FROM live_recordings
                JOIN live_sessions ON live_sessions.id = live_recordings.live_session_id
                WHERE live_recordings.live_session_id = ?
                  AND live_recordings.deleted_at IS NULL
                  AND live_sessions.recording_deleted_at IS NULL
                """,
                (start + 1, length, live_id),
            ).fetchone()
        if finalized is not None:
            yield finalized[0]
    finally:
        connection.close()


def soft_delete_recording(live_id: int, deleted_by: int) -> None:
    now = utc_now()
    db = get_db()
    db.execute(
        """
        UPDATE live_sessions
        SET recording_deleted_at = ?, recording_deleted_by = ?, updated_at = ?
        WHERE id = ?
        """,
        (now, deleted_by, now, live_id),
    )
    db.execute(
        """
        UPDATE live_recordings
        SET deleted_at = ?, deleted_by = ?, updated_at = ?
        WHERE live_session_id = ?
        """,
        (now, deleted_by, now, live_id),
    )
    db.commit()


def add_live_comment(live_id: int, user_id: int, body: str) -> int:
    compact_body = normalize_text(body, 280)
    if not compact_body:
        raise ValueError("Comment cannot be empty.")

    cursor = get_db().execute(
        """
        INSERT INTO live_comments (live_session_id, user_id, body, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (live_id, user_id, compact_body, utc_now()),
    )
    get_db().commit()
    return int(cursor.lastrowid)


def list_live_comments(live_id: int, after_id: int = 0, limit: int = 50) -> list[sqlite3.Row]:
    return get_db().execute(
        """
        SELECT live_comments.*, users.full_name, users.profile_photo
        FROM live_comments
        JOIN users ON users.id = live_comments.user_id
        WHERE live_comments.live_session_id = ?
          AND live_comments.id > ?
        ORDER BY live_comments.id
        LIMIT ?
        """,
        (live_id, after_id, limit),
    ).fetchall()


def set_live_reaction(live_id: int, user_id: int, reaction_type: str) -> None:
    if reaction_type not in REACTION_TYPES:
        raise ValueError("Choose a valid reaction.")
    now = utc_now()
    get_db().execute(
        """
        INSERT INTO live_reactions (
            live_session_id, user_id, reaction_type, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(live_session_id, user_id)
        DO UPDATE SET reaction_type = excluded.reaction_type, updated_at = excluded.updated_at
        """,
        (live_id, user_id, reaction_type, now, now),
    )
    get_db().commit()


def reaction_counts(live_id: int) -> dict[str, int]:
    rows = get_db().execute(
        """
        SELECT reaction_type, COUNT(*) AS count
        FROM live_reactions
        WHERE live_session_id = ?
        GROUP BY reaction_type
        """,
        (live_id,),
    ).fetchall()
    counts = {reaction: 0 for reaction in REACTION_TYPES}
    for row in rows:
        counts[row["reaction_type"]] = int(row["count"])
    return counts


def user_reaction(live_id: int, user_id: int) -> str:
    row = get_db().execute(
        """
        SELECT reaction_type
        FROM live_reactions
        WHERE live_session_id = ? AND user_id = ?
        """,
        (live_id, user_id),
    ).fetchone()
    return row["reaction_type"] if row else ""
