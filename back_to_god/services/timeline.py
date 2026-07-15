from __future__ import annotations

import sqlite3
from werkzeug.datastructures import FileStorage

from back_to_god.core.db import connect_database, get_db
from back_to_god.core.security import utc_now
from back_to_god.services.users import normalize_text


IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
VIDEO_TYPES = {"video/mp4", "video/webm", "video/ogg"}
MAX_IMAGE_BYTES = 12 * 1024 * 1024
MAX_VIDEO_BYTES = 48 * 1024 * 1024
TIMELINE_MANAGER_ROLES = {"super_admin", "admin"}


def _media_kind(mime_type: str) -> str | None:
    base_type = (mime_type or "").split(";")[0].lower()
    if base_type in IMAGE_TYPES:
        return "image"
    if base_type in VIDEO_TYPES:
        return "video"
    return None


def _validate_media(file: FileStorage, allow_unlimited_video: bool = False) -> tuple[str, str, bytes]:
    data = file.read()
    mime_type = (file.mimetype or "").split(";")[0].lower()
    media_kind = _media_kind(mime_type)
    if media_kind is None:
        raise ValueError("Only image and video files are supported on the timeline.")
    if not data:
        raise ValueError("Uploaded media is empty.")
    if media_kind == "image" and len(data) > MAX_IMAGE_BYTES:
        raise ValueError("Images must be 12 MB or smaller.")
    if media_kind == "video" and not allow_unlimited_video and len(data) > MAX_VIDEO_BYTES:
        raise ValueError("Videos must be 48 MB or smaller.")
    return media_kind, mime_type, data


def _visible_post_clause(user_id: int, role: str) -> tuple[str, list[object]]:
    if role == "super_admin":
        return "", []
    return (
        """
        AND (
            timeline_posts.visibility = 'everyone'
            OR timeline_posts.author_id = ?
            OR EXISTS (
                SELECT 1
                FROM timeline_post_viewers
                WHERE timeline_post_viewers.post_id = timeline_posts.id
                  AND timeline_post_viewers.user_id = ?
            )
        )
        """,
        [user_id, user_id],
    )


def list_viewer_options(current_user_id: int) -> list[sqlite3.Row]:
    return get_db().execute(
        """
        SELECT id, full_name, email, role, profile_photo
        FROM users
        WHERE id != ?
          AND is_active = 1
          AND deleted_at IS NULL
        ORDER BY full_name COLLATE NOCASE
        """,
        (current_user_id,),
    ).fetchall()


def _clean_viewer_ids(viewer_ids: list[str] | tuple[str, ...], author_id: int) -> list[int]:
    clean_ids = sorted(
        {
            int(viewer_id)
            for viewer_id in viewer_ids
            if str(viewer_id).strip().isdigit() and int(viewer_id) != author_id
        }
    )
    if not clean_ids:
        return []
    placeholders = ",".join("?" for _ in clean_ids)
    rows = get_db().execute(
        f"""
        SELECT id
        FROM users
        WHERE id IN ({placeholders})
          AND is_active = 1
          AND deleted_at IS NULL
        """,
        tuple(clean_ids),
    ).fetchall()
    return [int(row["id"]) for row in rows]


def create_post(
    author_id: int,
    title: str,
    body: str,
    event_date: str,
    media_files: list[FileStorage],
    visibility: str = "everyone",
    viewer_ids: list[str] | tuple[str, ...] | None = None,
) -> int:
    compact_title = normalize_text(title, 120)
    compact_body = normalize_text(body, 900)
    compact_event_date = normalize_text(event_date, 30)
    compact_visibility = "specific" if visibility == "specific" else "everyone"
    selected_viewers = _clean_viewer_ids(list(viewer_ids or []), author_id)
    if compact_visibility == "specific" and not selected_viewers:
        raise ValueError("Choose at least one person for a specific-audience post.")
    usable_files = [file for file in media_files if file and file.filename]
    if not compact_title and usable_files:
        compact_title = "Church moment"
    if not compact_title:
        raise ValueError("Add a short title for the timeline post.")

    author = get_db().execute("SELECT role FROM users WHERE id = ?", (author_id,)).fetchone()
    allow_unlimited_video = author is not None and author["role"] == "videographer"
    validated_media = []
    for index, file in enumerate(usable_files[:8]):
        media_kind, mime_type, data = _validate_media(file, allow_unlimited_video)
        validated_media.append(
            (
                index,
                media_kind,
                mime_type,
                normalize_text(file.filename, 140),
                len(data),
                data,
            )
        )

    now = utc_now()
    cursor = get_db().execute(
        """
        INSERT INTO timeline_posts (
            author_id, title, body, event_date, visibility, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            author_id,
            compact_title,
            compact_body,
            compact_event_date,
            compact_visibility,
            now,
            now,
        ),
    )
    post_id = int(cursor.lastrowid)
    if compact_visibility == "specific":
        for viewer_id in selected_viewers:
            get_db().execute(
                """
                INSERT INTO timeline_post_viewers (post_id, user_id, created_at)
                VALUES (?, ?, ?)
                """,
                (post_id, viewer_id, now),
            )

    for index, media_kind, mime_type, original_name, size_bytes, data in validated_media:
        get_db().execute(
            """
            INSERT INTO timeline_media (
                post_id, media_kind, mime_type, original_name, size_bytes,
                data, sort_order, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                post_id,
                media_kind,
                mime_type,
                original_name,
                size_bytes,
                data,
                index,
                now,
            ),
        )

    get_db().commit()
    return post_id


def _can_manage_post(post: sqlite3.Row, user_id: int, role: str) -> bool:
    return role in TIMELINE_MANAGER_ROLES or int(post["author_id"]) == int(user_id)


def get_post(post_id: int, include_deleted: bool = False) -> sqlite3.Row | None:
    query = """
        SELECT timeline_posts.*, users.full_name AS author_name
        FROM timeline_posts
        JOIN users ON users.id = timeline_posts.author_id
        WHERE timeline_posts.id = ?
    """
    if not include_deleted:
        query += " AND timeline_posts.deleted_at IS NULL"
    return get_db().execute(query, (post_id,)).fetchone()


def viewer_ids_for_posts(post_ids: list[int]) -> dict[int, set[int]]:
    if not post_ids:
        return {}
    placeholders = ",".join("?" for _ in post_ids)
    rows = get_db().execute(
        f"""
        SELECT post_id, user_id
        FROM timeline_post_viewers
        WHERE post_id IN ({placeholders})
        """,
        tuple(post_ids),
    ).fetchall()
    grouped: dict[int, set[int]] = {}
    for row in rows:
        grouped.setdefault(int(row["post_id"]), set()).add(int(row["user_id"]))
    return grouped


def update_post(
    post_id: int,
    user_id: int,
    role: str,
    title: str,
    body: str,
    event_date: str,
    visibility: str = "everyone",
    viewer_ids: list[str] | tuple[str, ...] | None = None,
) -> sqlite3.Row | None:
    post = get_post(post_id)
    if post is None:
        return None
    if not _can_manage_post(post, user_id, role):
        raise PermissionError("You cannot edit this post.")

    compact_title = normalize_text(title, 120)
    compact_body = normalize_text(body, 900)
    compact_event_date = normalize_text(event_date, 30)
    compact_visibility = "specific" if visibility == "specific" else "everyone"
    selected_viewers = _clean_viewer_ids(list(viewer_ids or []), int(post["author_id"]))
    if compact_visibility == "specific" and not selected_viewers:
        raise ValueError("Choose at least one person for a specific-audience post.")
    if not compact_title:
        raise ValueError("Add a short title for the timeline post.")

    now = utc_now()
    get_db().execute(
        """
        UPDATE timeline_posts
        SET title = ?, body = ?, event_date = ?, visibility = ?, updated_at = ?
        WHERE id = ?
        """,
        (
            compact_title,
            compact_body,
            compact_event_date,
            compact_visibility,
            now,
            post_id,
        ),
    )
    get_db().execute("DELETE FROM timeline_post_viewers WHERE post_id = ?", (post_id,))
    if compact_visibility == "specific":
        for viewer_id in selected_viewers:
            get_db().execute(
                """
                INSERT INTO timeline_post_viewers (post_id, user_id, created_at)
                VALUES (?, ?, ?)
                """,
                (post_id, viewer_id, now),
            )
    get_db().commit()
    return get_post(post_id)


def soft_delete_post(post_id: int, user_id: int, role: str) -> sqlite3.Row | None:
    post = get_post(post_id)
    if post is None:
        return None
    if not _can_manage_post(post, user_id, role):
        raise PermissionError("You cannot delete this post.")

    now = utc_now()
    get_db().execute(
        """
        UPDATE timeline_posts
        SET deleted_at = ?, deleted_by = ?, updated_at = ?
        WHERE id = ?
        """,
        (now, user_id, now, post_id),
    )
    get_db().commit()
    return post


def restore_post(post_id: int, user_id: int, role: str) -> sqlite3.Row | None:
    post = get_post(post_id, include_deleted=True)
    if post is None or post["deleted_at"] is None:
        return None
    if not _can_manage_post(post, user_id, role):
        raise PermissionError("You cannot restore this post.")

    now = utc_now()
    get_db().execute(
        """
        UPDATE timeline_posts
        SET deleted_at = NULL, deleted_by = NULL, updated_at = ?
        WHERE id = ?
        """,
        (now, post_id),
    )
    get_db().commit()
    return post


def deleted_post_count(user_id: int, role: str) -> int:
    params: list[object] = []
    where = "timeline_posts.deleted_at IS NOT NULL"
    if role not in TIMELINE_MANAGER_ROLES:
        where += " AND timeline_posts.author_id = ?"
        params.append(user_id)
    row = get_db().execute(
        f"SELECT COUNT(*) AS count FROM timeline_posts WHERE {where}",
        tuple(params),
    ).fetchone()
    return int(row["count"])


def list_deleted_posts(
    user_id: int,
    role: str,
    limit: int = 10,
    offset: int = 0,
) -> list[sqlite3.Row]:
    params: list[object] = []
    where = "timeline_posts.deleted_at IS NOT NULL"
    if role not in TIMELINE_MANAGER_ROLES:
        where += " AND timeline_posts.author_id = ?"
        params.append(user_id)
    params.extend([limit, offset])
    return get_db().execute(
        f"""
        SELECT
            timeline_posts.*,
            users.full_name AS author_name,
            deleter.full_name AS deleted_by_name,
            COALESCE(media_counts.media_count, 0) AS media_count,
            COALESCE(media_counts.image_count, 0) AS image_count,
            COALESCE(media_counts.video_count, 0) AS video_count
        FROM timeline_posts
        JOIN users ON users.id = timeline_posts.author_id
        LEFT JOIN users AS deleter ON deleter.id = timeline_posts.deleted_by
        LEFT JOIN (
            SELECT
                post_id,
                COUNT(*) AS media_count,
                SUM(CASE WHEN media_kind = 'image' THEN 1 ELSE 0 END) AS image_count,
                SUM(CASE WHEN media_kind = 'video' THEN 1 ELSE 0 END) AS video_count
            FROM timeline_media
            GROUP BY post_id
        ) AS media_counts ON media_counts.post_id = timeline_posts.id
        WHERE {where}
        ORDER BY datetime(timeline_posts.deleted_at) DESC, timeline_posts.id DESC
        LIMIT ? OFFSET ?
        """,
        tuple(params),
    ).fetchall()


def list_posts(
    query: str = "",
    limit: int = 30,
    offset: int = 0,
    current_user_id: int = 0,
    current_role: str = "member",
) -> list[sqlite3.Row]:
    compact_query = normalize_text(query, 80)
    params: list[object] = []
    where = "timeline_posts.deleted_at IS NULL"
    visible_clause, visible_params = _visible_post_clause(current_user_id, current_role)
    where += visible_clause
    params.extend(visible_params)
    if compact_query:
        like = f"%{compact_query}%"
        where += """
            AND (
                timeline_posts.title LIKE ?
                OR timeline_posts.body LIKE ?
                OR users.full_name LIKE ?
            )
        """
        params.extend([like, like, like])
    params.append(limit)
    params.append(offset)
    return get_db().execute(
        f"""
        SELECT
            timeline_posts.*,
            users.full_name AS author_name,
            users.profile_photo AS author_photo,
            COALESCE(media_counts.media_count, 0) AS media_count,
            COALESCE(media_counts.image_count, 0) AS image_count,
            COALESCE(media_counts.video_count, 0) AS video_count,
            COALESCE(comment_counts.comment_count, 0) AS comment_count,
            COALESCE(reaction_counts.reaction_count, 0) AS reaction_count,
            COALESCE(viewer_counts.viewer_count, 0) AS viewer_count
        FROM timeline_posts
        JOIN users ON users.id = timeline_posts.author_id
        LEFT JOIN (
            SELECT
                post_id,
                COUNT(*) AS media_count,
                SUM(CASE WHEN media_kind = 'image' THEN 1 ELSE 0 END) AS image_count,
                SUM(CASE WHEN media_kind = 'video' THEN 1 ELSE 0 END) AS video_count
            FROM timeline_media
            GROUP BY post_id
        ) AS media_counts ON media_counts.post_id = timeline_posts.id
        LEFT JOIN (
            SELECT post_id, COUNT(*) AS comment_count
            FROM timeline_comments
            GROUP BY post_id
        ) AS comment_counts ON comment_counts.post_id = timeline_posts.id
        LEFT JOIN (
            SELECT post_id, COUNT(*) AS reaction_count
            FROM timeline_reactions
            GROUP BY post_id
        ) AS reaction_counts ON reaction_counts.post_id = timeline_posts.id
        LEFT JOIN (
            SELECT post_id, COUNT(*) AS viewer_count
            FROM timeline_post_viewers
            GROUP BY post_id
        ) AS viewer_counts ON viewer_counts.post_id = timeline_posts.id
        WHERE {where}
        ORDER BY
            CASE WHEN timeline_posts.event_date IS NULL OR timeline_posts.event_date = '' THEN 1 ELSE 0 END,
            datetime(timeline_posts.event_date) DESC,
            datetime(timeline_posts.created_at) DESC
        LIMIT ? OFFSET ?
        """,
        tuple(params),
    ).fetchall()


def post_count(
    query: str = "",
    current_user_id: int = 0,
    current_role: str = "member",
) -> int:
    compact_query = normalize_text(query, 80)
    params: list[object] = []
    where = "timeline_posts.deleted_at IS NULL"
    visible_clause, visible_params = _visible_post_clause(current_user_id, current_role)
    where += visible_clause
    params.extend(visible_params)
    if compact_query:
        like = f"%{compact_query}%"
        where += """
            AND (
                timeline_posts.title LIKE ?
                OR timeline_posts.body LIKE ?
                OR users.full_name LIKE ?
            )
        """
        params.extend([like, like, like])
    row = get_db().execute(
        f"""
        SELECT COUNT(*) AS count
        FROM timeline_posts
        JOIN users ON users.id = timeline_posts.author_id
        WHERE {where}
        """,
        tuple(params),
    ).fetchone()
    return int(row["count"])


def latest_visible_update(
    query: str = "",
    current_user_id: int = 0,
    current_role: str = "member",
) -> str:
    compact_query = normalize_text(query, 80)
    params: list[object] = []
    where = "timeline_posts.deleted_at IS NULL"
    visible_clause, visible_params = _visible_post_clause(current_user_id, current_role)
    where += visible_clause
    params.extend(visible_params)
    if compact_query:
        like = f"%{compact_query}%"
        where += """
            AND (
                timeline_posts.title LIKE ?
                OR timeline_posts.body LIKE ?
                OR users.full_name LIKE ?
            )
        """
        params.extend([like, like, like])
    row = get_db().execute(
        f"""
        SELECT COALESCE(MAX(timeline_posts.updated_at), '') AS latest_update
        FROM timeline_posts
        JOIN users ON users.id = timeline_posts.author_id
        WHERE {where}
        """,
        tuple(params),
    ).fetchone()
    return row["latest_update"] if row else ""


def media_for_posts(post_ids: list[int]) -> dict[int, list[sqlite3.Row]]:
    if not post_ids:
        return {}
    placeholders = ",".join("?" for _ in post_ids)
    rows = get_db().execute(
        f"""
        SELECT id, post_id, media_kind, mime_type, original_name, size_bytes, sort_order
        FROM timeline_media
        WHERE post_id IN ({placeholders})
        ORDER BY post_id, sort_order, id
        """,
        tuple(post_ids),
    ).fetchall()
    grouped: dict[int, list[sqlite3.Row]] = {}
    for row in rows:
        grouped.setdefault(int(row["post_id"]), []).append(row)
    return grouped


def comments_for_posts(post_ids: list[int], per_post: int = 3) -> dict[int, list[sqlite3.Row]]:
    if not post_ids:
        return {}
    placeholders = ",".join("?" for _ in post_ids)
    rows = get_db().execute(
        f"""
        SELECT timeline_comments.*, users.full_name, users.profile_photo
        FROM timeline_comments
        JOIN users ON users.id = timeline_comments.user_id
        WHERE timeline_comments.post_id IN ({placeholders})
        ORDER BY timeline_comments.post_id, timeline_comments.id DESC
        """,
        tuple(post_ids),
    ).fetchall()
    grouped: dict[int, list[sqlite3.Row]] = {}
    for row in rows:
        comments = grouped.setdefault(int(row["post_id"]), [])
        if len(comments) < per_post:
            comments.append(row)
    for post_id in grouped:
        grouped[post_id].reverse()
    return grouped


def my_reactions(post_ids: list[int], user_id: int) -> set[int]:
    if not post_ids:
        return set()
    placeholders = ",".join("?" for _ in post_ids)
    rows = get_db().execute(
        f"""
        SELECT post_id
        FROM timeline_reactions
        WHERE user_id = ? AND post_id IN ({placeholders})
        """,
        (user_id, *post_ids),
    ).fetchall()
    return {int(row["post_id"]) for row in rows}


def can_view_post(post_id: int, user_id: int, role: str) -> bool:
    visible_clause, visible_params = _visible_post_clause(user_id, role)
    row = get_db().execute(
        f"""
        SELECT timeline_posts.id
        FROM timeline_posts
        WHERE timeline_posts.id = ?
          AND timeline_posts.deleted_at IS NULL
          {visible_clause}
        """,
        (post_id, *visible_params),
    ).fetchone()
    return row is not None


def add_comment(post_id: int, user_id: int, role: str, body: str) -> None:
    if not can_view_post(post_id, user_id, role):
        raise PermissionError("You cannot comment on this post.")
    compact_body = normalize_text(body, 360)
    if not compact_body:
        raise ValueError("Comment cannot be empty.")
    now = utc_now()
    get_db().execute(
        """
        INSERT INTO timeline_comments (post_id, user_id, body, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (post_id, user_id, compact_body, now),
    )
    get_db().execute(
        "UPDATE timeline_posts SET updated_at = ? WHERE id = ?",
        (now, post_id),
    )
    get_db().commit()


def toggle_like(post_id: int, user_id: int, role: str) -> bool:
    if not can_view_post(post_id, user_id, role):
        raise PermissionError("You cannot react to this post.")
    existing = get_db().execute(
        """
        SELECT id
        FROM timeline_reactions
        WHERE post_id = ? AND user_id = ?
        """,
        (post_id, user_id),
    ).fetchone()
    now = utc_now()
    if existing:
        get_db().execute("DELETE FROM timeline_reactions WHERE id = ?", (existing["id"],))
        get_db().execute(
            "UPDATE timeline_posts SET updated_at = ? WHERE id = ?",
            (now, post_id),
        )
        get_db().commit()
        return False

    get_db().execute(
        """
        INSERT INTO timeline_reactions (
            post_id, user_id, reaction_type, created_at, updated_at
        )
        VALUES (?, ?, 'like', ?, ?)
        """,
        (post_id, user_id, now, now),
    )
    get_db().execute(
        "UPDATE timeline_posts SET updated_at = ? WHERE id = ?",
        (now, post_id),
    )
    get_db().commit()
    return True


def get_media(media_id: int, user_id: int, role: str) -> sqlite3.Row | None:
    visible_clause, visible_params = _visible_post_clause(user_id, role)
    return get_db().execute(
        f"""
        SELECT timeline_media.*
        FROM timeline_media
        JOIN timeline_posts ON timeline_posts.id = timeline_media.post_id
        WHERE timeline_media.id = ?
          AND timeline_posts.deleted_at IS NULL
          {visible_clause}
        """,
        (media_id, *visible_params),
    ).fetchone()


def media_bytes(media_id: int, start: int = 0, length: int | None = None):
    connection = connect_database()
    try:
        if length is None:
            row = connection.execute(
                "SELECT data FROM timeline_media WHERE id = ?",
                (media_id,),
            ).fetchone()
        else:
            row = connection.execute(
                "SELECT substr(data, ?, ?) AS data FROM timeline_media WHERE id = ?",
                (start + 1, length, media_id),
            ).fetchone()
        if row:
            yield row[0]
    finally:
        connection.close()
