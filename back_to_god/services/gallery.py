from __future__ import annotations

import sqlite3
from werkzeug.datastructures import FileStorage

from back_to_god.core.db import connect_database, get_db
from back_to_god.core.security import utc_now
from back_to_god.services.users import normalize_text


IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
VIDEO_TYPES = {"video/mp4", "video/webm", "video/ogg"}
MAX_IMAGE_BYTES = 12 * 1024 * 1024
MAX_VIDEO_BYTES = 512 * 1024 * 1024
DEFAULT_CATEGORIES = ["Services", "Choir", "Youth", "Outreach", "Fellowship"]


def can_manage_gallery(role: str) -> bool:
    return role in {"super_admin", "admin"}


def _media_kind(mime_type: str) -> str | None:
    base_type = (mime_type or "").split(";")[0].lower()
    if base_type in IMAGE_TYPES:
        return "image"
    if base_type in VIDEO_TYPES:
        return "video"
    return None


def _validate_media(file: FileStorage) -> tuple[str, str, bytes]:
    data = file.read()
    mime_type = (file.mimetype or "").split(";")[0].lower()
    media_kind = _media_kind(mime_type)
    if media_kind is None:
        raise ValueError("Only image and video files are supported in the gallery.")
    if not data:
        raise ValueError("Uploaded gallery media is empty.")
    if media_kind == "image" and len(data) > MAX_IMAGE_BYTES:
        raise ValueError("Gallery images must be 12 MB or smaller.")
    if media_kind == "video" and len(data) > MAX_VIDEO_BYTES:
        raise ValueError("Gallery videos must be 512 MB or smaller.")
    return media_kind, mime_type, data


def ensure_default_categories() -> None:
    for category in DEFAULT_CATEGORIES:
        ensure_category(category)


def ensure_category(name: str) -> int:
    compact_name = normalize_text(name, 80) or "General"
    db = get_db()
    existing = db.execute(
        """
        SELECT id
        FROM gallery_categories
        WHERE lower(name) = lower(?)
        """,
        (compact_name,),
    ).fetchone()
    if existing is not None:
        return int(existing["id"])

    cursor = db.execute(
        """
        INSERT INTO gallery_categories (name, created_at)
        VALUES (?, ?)
        """,
        (compact_name, utc_now()),
    )
    db.commit()
    return int(cursor.lastrowid)


def list_categories() -> list[sqlite3.Row]:
    ensure_default_categories()
    return get_db().execute(
        """
        SELECT gallery_categories.*, COUNT(gallery_media.id) AS media_count
        FROM gallery_categories
        LEFT JOIN gallery_media
          ON gallery_media.category_id = gallery_categories.id
         AND gallery_media.deleted_at IS NULL
        GROUP BY gallery_categories.id
        ORDER BY gallery_categories.name COLLATE NOCASE
        """
    ).fetchall()


def create_gallery_media(
    title: str,
    description: str,
    category_name: str,
    event_at: str,
    files: list[FileStorage],
    uploaded_by: int,
) -> list[int]:
    compact_title = normalize_text(title, 120)
    compact_description = normalize_text(description, 900)
    compact_event_at = normalize_text(event_at, 30)
    usable_files = [file for file in files if file and file.filename]
    if not compact_title:
        raise ValueError("Add a title for the gallery upload.")
    if not usable_files:
        raise ValueError("Choose at least one picture or video.")

    category_id = ensure_category(category_name)
    now = utc_now()
    media_ids: list[int] = []
    db = get_db()
    for file in usable_files:
        media_kind, mime_type, data = _validate_media(file)
        cursor = db.execute(
            """
            INSERT INTO gallery_media (
                category_id, title, description, event_at, media_kind, mime_type,
                original_name, size_bytes, data, uploaded_by, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                category_id,
                compact_title,
                compact_description,
                compact_event_at,
                media_kind,
                mime_type,
                normalize_text(file.filename, 160),
                len(data),
                data,
                uploaded_by,
                now,
                now,
            ),
        )
        media_ids.append(int(cursor.lastrowid))
    db.commit()
    return media_ids


def _gallery_where(
    query: str,
    media_kind: str,
    category_id: int,
) -> tuple[str, list[object]]:
    compact_query = normalize_text(query, 80)
    compact_kind = media_kind if media_kind in {"image", "video"} else ""
    params: list[object] = []
    where = "gallery_media.deleted_at IS NULL"

    if compact_kind:
        where += " AND gallery_media.media_kind = ?"
        params.append(compact_kind)
    if category_id > 0:
        where += " AND gallery_media.category_id = ?"
        params.append(category_id)
    if compact_query:
        like = f"%{compact_query}%"
        where += """
            AND (
                gallery_media.title LIKE ?
                OR gallery_media.description LIKE ?
                OR gallery_media.original_name LIKE ?
                OR gallery_categories.name LIKE ?
                OR users.full_name LIKE ?
            )
        """
        params.extend([like, like, like, like, like])

    return where, params


def gallery_media_count(
    query: str = "",
    media_kind: str = "",
    category_id: int = 0,
) -> int:
    where, params = _gallery_where(query, media_kind, category_id)
    row = get_db().execute(
        f"""
        SELECT COUNT(*) AS count
        FROM gallery_media
        JOIN gallery_categories ON gallery_categories.id = gallery_media.category_id
        JOIN users ON users.id = gallery_media.uploaded_by
        WHERE {where}
        """,
        tuple(params),
    ).fetchone()
    return int(row["count"])


def latest_gallery_update() -> str:
    row = get_db().execute(
        "SELECT COALESCE(MAX(updated_at), '') AS latest_update FROM gallery_media"
    ).fetchone()
    return row["latest_update"] if row else ""


def gallery_summary() -> dict[str, int | str]:
    row = get_db().execute(
        """
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN media_kind = 'image' THEN 1 ELSE 0 END) AS photos,
            SUM(CASE WHEN media_kind = 'video' THEN 1 ELSE 0 END) AS videos,
            COUNT(DISTINCT category_id) AS categories,
            COALESCE(MAX(updated_at), '') AS latest_update
        FROM gallery_media
        WHERE deleted_at IS NULL
        """
    ).fetchone()
    return {
        "total": int(row["total"] or 0),
        "photos": int(row["photos"] or 0),
        "videos": int(row["videos"] or 0),
        "categories": int(row["categories"] or 0),
        "latest_update": row["latest_update"] or "",
    }


def list_gallery_media(
    query: str = "",
    media_kind: str = "",
    category_id: int = 0,
    limit: int = 18,
    offset: int = 0,
) -> list[sqlite3.Row]:
    where, params = _gallery_where(query, media_kind, category_id)
    params.extend([limit, offset])
    return get_db().execute(
        f"""
        SELECT
            gallery_media.id,
            gallery_media.category_id,
            gallery_media.title,
            gallery_media.description,
            gallery_media.event_at,
            gallery_media.media_kind,
            gallery_media.mime_type,
            gallery_media.original_name,
            gallery_media.size_bytes,
            gallery_media.created_at,
            gallery_categories.name AS category_name,
            users.full_name AS uploaded_by_name
        FROM gallery_media
        JOIN gallery_categories ON gallery_categories.id = gallery_media.category_id
        JOIN users ON users.id = gallery_media.uploaded_by
        WHERE {where}
        ORDER BY
            datetime(COALESCE(NULLIF(gallery_media.event_at, ''), gallery_media.created_at)) DESC,
            gallery_media.id DESC
        LIMIT ? OFFSET ?
        """,
        tuple(params),
    ).fetchall()


def list_gallery_slideshow() -> list[sqlite3.Row]:
    return get_db().execute(
        """
        SELECT
            gallery_media.id,
            gallery_media.title,
            gallery_media.description,
            gallery_media.event_at,
            gallery_media.media_kind,
            gallery_media.mime_type,
            gallery_media.created_at,
            gallery_categories.name AS category_name,
            users.full_name AS uploaded_by_name,
            gallery_slideshow_items.caption AS slideshow_caption,
            gallery_slideshow_items.sort_order AS slideshow_sort_order
        FROM gallery_slideshow_items
        JOIN gallery_media ON gallery_media.id = gallery_slideshow_items.media_id
        JOIN gallery_categories ON gallery_categories.id = gallery_media.category_id
        JOIN users ON users.id = gallery_media.uploaded_by
        WHERE gallery_slideshow_items.is_active = 1
          AND gallery_media.deleted_at IS NULL
        ORDER BY gallery_slideshow_items.sort_order, gallery_slideshow_items.id
        """
    ).fetchall()


def list_gallery_slideshow_picker(limit: int = 120) -> list[sqlite3.Row]:
    return get_db().execute(
        """
        SELECT
            gallery_media.id,
            gallery_media.title,
            gallery_media.media_kind,
            gallery_media.event_at,
            gallery_media.created_at,
            gallery_categories.name AS category_name,
            gallery_slideshow_items.caption AS slideshow_caption,
            gallery_slideshow_items.sort_order AS slideshow_sort_order,
            CASE WHEN gallery_slideshow_items.id IS NULL THEN 0 ELSE 1 END AS is_selected
        FROM gallery_media
        JOIN gallery_categories ON gallery_categories.id = gallery_media.category_id
        LEFT JOIN gallery_slideshow_items
          ON gallery_slideshow_items.media_id = gallery_media.id
         AND gallery_slideshow_items.is_active = 1
        WHERE gallery_media.deleted_at IS NULL
        ORDER BY
            is_selected DESC,
            COALESCE(gallery_slideshow_items.sort_order, 9999),
            datetime(COALESCE(NULLIF(gallery_media.event_at, ''), gallery_media.created_at)) DESC,
            gallery_media.id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()


def update_gallery_slideshow(form, updated_by: int) -> int:
    selected_ids: list[int] = []
    for value in form.getlist("slideshow_media_id"):
        try:
            media_id = int(value)
        except (TypeError, ValueError):
            continue
        if media_id > 0 and media_id not in selected_ids:
            selected_ids.append(media_id)

    db = get_db()
    now = utc_now()
    db.execute("DELETE FROM gallery_slideshow_items")
    saved = 0
    for position, media_id in enumerate(selected_ids, start=1):
        media = db.execute(
            "SELECT id FROM gallery_media WHERE id = ? AND deleted_at IS NULL",
            (media_id,),
        ).fetchone()
        if media is None:
            continue

        try:
            sort_order = int(form.get(f"slideshow_order_{media_id}", position))
        except (TypeError, ValueError):
            sort_order = position
        caption = normalize_text(form.get(f"slideshow_caption_{media_id}", ""), 180)
        db.execute(
            """
            INSERT INTO gallery_slideshow_items (
                media_id, caption, sort_order, is_active, added_by, created_at, updated_at
            )
            VALUES (?, ?, ?, 1, ?, ?, ?)
            """,
            (media_id, caption, sort_order, updated_by, now, now),
        )
        saved += 1

    db.commit()
    return saved


def list_gallery_category_groups(
    query: str = "",
    media_kind: str = "",
) -> list[dict]:
    where, params = _gallery_where(query, media_kind, 0)
    rows = get_db().execute(
        f"""
        WITH ranked_media AS (
            SELECT
                gallery_media.id,
                gallery_media.category_id,
                gallery_media.title,
                gallery_media.media_kind,
                gallery_categories.name AS category_name,
                COALESCE(NULLIF(gallery_media.event_at, ''), gallery_media.created_at) AS latest_at,
                ROW_NUMBER() OVER (
                    PARTITION BY gallery_media.category_id
                    ORDER BY datetime(COALESCE(NULLIF(gallery_media.event_at, ''), gallery_media.created_at)) DESC,
                             gallery_media.id DESC
                ) AS row_number,
                COUNT(*) OVER (PARTITION BY gallery_media.category_id) AS media_count,
                SUM(CASE WHEN gallery_media.media_kind = 'image' THEN 1 ELSE 0 END)
                    OVER (PARTITION BY gallery_media.category_id) AS image_count,
                SUM(CASE WHEN gallery_media.media_kind = 'video' THEN 1 ELSE 0 END)
                    OVER (PARTITION BY gallery_media.category_id) AS video_count
            FROM gallery_media
            JOIN gallery_categories ON gallery_categories.id = gallery_media.category_id
            JOIN users ON users.id = gallery_media.uploaded_by
            WHERE {where}
        )
        SELECT
            category_id AS id,
            category_name AS name,
            media_count,
            image_count,
            video_count,
            id AS preview_media_id,
            media_kind AS preview_media_kind,
            title AS preview_title,
            latest_at
        FROM ranked_media
        WHERE row_number = 1
        ORDER BY datetime(latest_at) DESC, id DESC
        """,
        tuple(params),
    ).fetchall()
    return [dict(row) for row in rows]


def get_gallery_media(media_id: int) -> sqlite3.Row | None:
    return get_db().execute(
        """
        SELECT
            gallery_media.*,
            gallery_categories.name AS category_name,
            users.full_name AS uploaded_by_name
        FROM gallery_media
        JOIN gallery_categories ON gallery_categories.id = gallery_media.category_id
        JOIN users ON users.id = gallery_media.uploaded_by
        WHERE gallery_media.id = ? AND gallery_media.deleted_at IS NULL
        """,
        (media_id,),
    ).fetchone()


def gallery_media_bytes(media_id: int, start: int = 0, length: int | None = None):
    connection = connect_database()
    try:
        if length is None:
            row = connection.execute(
                "SELECT data FROM gallery_media WHERE id = ? AND deleted_at IS NULL",
                (media_id,),
            ).fetchone()
        else:
            row = connection.execute(
                """
                SELECT substr(data, ?, ?) AS data
                FROM gallery_media
                WHERE id = ? AND deleted_at IS NULL
                """,
                (start + 1, length, media_id),
            ).fetchone()
        if row:
            yield row[0]
    finally:
        connection.close()


def soft_delete_gallery_media(media_id: int, deleted_by: int) -> sqlite3.Row | None:
    item = get_gallery_media(media_id)
    if item is None:
        return None
    now = utc_now()
    get_db().execute(
        """
        UPDATE gallery_media
        SET deleted_at = ?, deleted_by = ?, updated_at = ?
        WHERE id = ?
        """,
        (now, deleted_by, now, media_id),
    )
    get_db().commit()
    return item
