from __future__ import annotations

from datetime import datetime
import re
import sqlite3

from back_to_god.core.db import get_db
from back_to_god.core.security import today_date, utc_now
from back_to_god.services.users import normalize_text


SLIP_TYPES = {"image/jpeg", "image/png", "image/webp", "application/pdf"}
MAX_SLIP_BYTES = 16 * 1024 * 1024


def money_to_cents(value: str) -> int:
    clean = re.sub(r"[^0-9.]", "", value or "")
    if not clean:
        return 0
    parts = clean.split(".")
    rands = int(parts[0] or "0")
    cents = int((parts[1][:2] if len(parts) > 1 else "0").ljust(2, "0"))
    return (rands * 100) + cents


def cents_to_money(cents: int) -> str:
    return f"R {cents / 100:,.2f}"


def local_datetime_to_utc(value: str) -> str:
    if not value:
        return ""
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone().replace(tzinfo=None)
    return parsed.isoformat(timespec="seconds")


def expire_visible_deposit_slips() -> int:
    cursor = get_db().execute(
        """
        UPDATE deposit_slips
        SET is_visible = 0, updated_at = ?
        WHERE is_visible = 1
          AND deleted_at IS NULL
          AND approval_status = 'approved'
          AND visible_until IS NOT NULL
          AND visible_until != ''
          AND visible_until <= ?
        """,
        (utc_now(), utc_now()),
    )
    changed = int(cursor.rowcount or 0)
    if changed:
        get_db().commit()
    return changed


def validate_slip(file_storage) -> tuple[str, str, bytes]:
    if not file_storage or not file_storage.filename:
        raise ValueError("Upload the bank deposit slip.")

    data = file_storage.read()
    mime_type = (file_storage.mimetype or "").lower()
    if mime_type not in SLIP_TYPES:
        raise ValueError("Deposit slip must be a PDF, JPG, PNG, or WEBP file.")
    if not data:
        raise ValueError("The deposit slip file is empty.")
    if len(data) > MAX_SLIP_BYTES:
        raise ValueError("Deposit slip is too large. Keep it under 16 MB.")

    return mime_type, normalize_text(file_storage.filename, 160), data


def create_deposit_slip(form, file_storage, created_by: int) -> int:
    mime_type, original_name, data = validate_slip(file_storage)
    now = utc_now()
    visible_until = local_datetime_to_utc(form.get("visible_until", "").strip())
    requested_visibility = form.get("is_visible") == "on" and bool(visible_until)
    approval_status = "pending" if requested_visibility else "draft"
    cursor = get_db().execute(
        """
        INSERT INTO deposit_slips (
            title, bank_name, reference, amount_cents, deposit_date,
            is_visible, visible_from, visible_until, approval_status, original_name, mime_type,
            size_bytes, data, created_by, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            normalize_text(form.get("title", ""), 120) or "Bank deposit slip",
            normalize_text(form.get("bank_name", ""), 80),
            normalize_text(form.get("reference", ""), 80),
            money_to_cents(form.get("amount", "")),
            form.get("deposit_date", "").strip() or today_date(),
            0,
            "",
            visible_until,
            approval_status,
            original_name,
            mime_type,
            len(data),
            data,
            created_by,
            now,
            now,
        ),
    )
    get_db().commit()
    return int(cursor.lastrowid)


def list_deposit_slip_options() -> list[sqlite3.Row]:
    return get_db().execute(
        """
        SELECT id, title, deposit_date, amount_cents
        FROM deposit_slips
        WHERE deleted_at IS NULL
        ORDER BY date(deposit_date) DESC, datetime(created_at) DESC
        LIMIT 80
        """
    ).fetchall()


def create_offering(form, captured_by: int) -> int:
    amount_cents = money_to_cents(form.get("amount", ""))
    if amount_cents <= 0:
        raise ValueError("Add the offering amount.")
    offering_type = normalize_text(form.get("offering_type", ""), 80) or "Offering"
    deposit_slip_id = form.get("deposit_slip_id", "").strip()
    linked_slip_id = int(deposit_slip_id) if deposit_slip_id.isdigit() else None
    if linked_slip_id is not None and get_deposit_slip(linked_slip_id) is None:
        raise ValueError("Choose a valid deposit slip to link.")

    now = utc_now()
    cursor = get_db().execute(
        """
        INSERT INTO finance_offerings (
            offering_date, offering_type, amount_cents, note, deposit_slip_id,
            captured_by, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            form.get("offering_date", "").strip() or today_date(),
            offering_type,
            amount_cents,
            normalize_text(form.get("note", ""), 220),
            linked_slip_id,
            captured_by,
            now,
            now,
        ),
    )
    get_db().commit()
    return int(cursor.lastrowid)


def list_offerings(limit: int = 12, offset: int = 0) -> list[sqlite3.Row]:
    return get_db().execute(
        """
        SELECT
            finance_offerings.*,
            users.full_name AS captured_by_name,
            deposit_slips.title AS deposit_slip_title
        FROM finance_offerings
        JOIN users ON users.id = finance_offerings.captured_by
        LEFT JOIN deposit_slips ON deposit_slips.id = finance_offerings.deposit_slip_id
        WHERE finance_offerings.deleted_at IS NULL
        ORDER BY date(finance_offerings.offering_date) DESC, datetime(finance_offerings.created_at) DESC
        LIMIT ? OFFSET ?
        """,
        (limit, offset),
    ).fetchall()


def list_offerings_for_slip(slip_id: int) -> list[sqlite3.Row]:
    return get_db().execute(
        """
        SELECT
            finance_offerings.*,
            users.full_name AS captured_by_name
        FROM finance_offerings
        JOIN users ON users.id = finance_offerings.captured_by
        WHERE finance_offerings.deleted_at IS NULL
          AND finance_offerings.deposit_slip_id = ?
        ORDER BY date(finance_offerings.offering_date) DESC, datetime(finance_offerings.created_at) DESC
        """,
        (slip_id,),
    ).fetchall()


def offering_count() -> int:
    row = get_db().execute(
        "SELECT COUNT(*) AS count FROM finance_offerings WHERE deleted_at IS NULL"
    ).fetchone()
    return int(row["count"])


def list_offerings_for_report() -> list[sqlite3.Row]:
    return get_db().execute(
        """
        SELECT
            finance_offerings.*,
            users.full_name AS captured_by_name,
            deposit_slips.title AS deposit_slip_title,
            deposit_slips.reference AS deposit_reference
        FROM finance_offerings
        JOIN users ON users.id = finance_offerings.captured_by
        LEFT JOIN deposit_slips ON deposit_slips.id = finance_offerings.deposit_slip_id
        WHERE finance_offerings.deleted_at IS NULL
        ORDER BY date(finance_offerings.offering_date) DESC, datetime(finance_offerings.created_at) DESC
        """
    ).fetchall()


def link_offering_to_slip(offering_id: int, slip_id: int) -> None:
    if get_deposit_slip(slip_id) is None:
        raise ValueError("Choose a valid deposit slip.")
    cursor = get_db().execute(
        """
        UPDATE finance_offerings
        SET deposit_slip_id = ?, updated_at = ?
        WHERE id = ? AND deleted_at IS NULL
        """,
        (slip_id, utc_now(), offering_id),
    )
    if not cursor.rowcount:
        raise ValueError("Offering could not be found.")
    get_db().commit()


def update_deposit_slip(slip_id: int, form) -> None:
    now = utc_now()
    visible_until = local_datetime_to_utc(form.get("visible_until", "").strip())
    requested_visibility = form.get("is_visible") == "on" and bool(visible_until)
    approval_status = "pending" if requested_visibility else "draft"
    get_db().execute(
        """
        UPDATE deposit_slips
        SET title = ?,
            bank_name = ?,
            reference = ?,
            amount_cents = ?,
            deposit_date = ?,
            is_visible = 0,
            visible_from = '',
            visible_until = ?,
            approval_status = ?,
            approved_by = NULL,
            approved_at = NULL,
            updated_at = ?
        WHERE id = ? AND deleted_at IS NULL
        """,
        (
            normalize_text(form.get("title", ""), 120) or "Bank deposit slip",
            normalize_text(form.get("bank_name", ""), 80),
            normalize_text(form.get("reference", ""), 80),
            money_to_cents(form.get("amount", "")),
            form.get("deposit_date", "").strip() or today_date(),
            visible_until,
            approval_status,
            now,
            slip_id,
        ),
    )
    get_db().commit()


def visible_deposit_slip_count() -> int:
    expire_visible_deposit_slips()
    row = get_db().execute(
        """
        SELECT COUNT(*) AS count
        FROM deposit_slips
        WHERE is_visible = 1
          AND deleted_at IS NULL
          AND approval_status = 'approved'
          AND visible_until IS NOT NULL
          AND visible_until != ''
          AND visible_until > ?
        """,
        (utc_now(),),
    ).fetchone()
    return int(row["count"])


def deposit_slip_count() -> int:
    row = get_db().execute(
        "SELECT COUNT(*) AS count FROM deposit_slips WHERE deleted_at IS NULL"
    ).fetchone()
    return int(row["count"])


def list_visible_deposit_slips(limit: int = 6, offset: int = 0) -> list[sqlite3.Row]:
    expire_visible_deposit_slips()
    return get_db().execute(
        """
        SELECT deposit_slips.*, users.full_name AS created_by_name
        FROM deposit_slips
        JOIN users ON users.id = deposit_slips.created_by
        WHERE deposit_slips.is_visible = 1
          AND deposit_slips.deleted_at IS NULL
          AND deposit_slips.approval_status = 'approved'
          AND deposit_slips.visible_until IS NOT NULL
          AND deposit_slips.visible_until != ''
          AND deposit_slips.visible_until > ?
        ORDER BY date(deposit_slips.deposit_date) DESC, datetime(deposit_slips.created_at) DESC
        LIMIT ? OFFSET ?
        """,
        (utc_now(), limit, offset),
    ).fetchall()


def list_deposit_slips(limit: int = 10, offset: int = 0) -> list[sqlite3.Row]:
    expire_visible_deposit_slips()
    return get_db().execute(
        """
        SELECT deposit_slips.*, users.full_name AS created_by_name
        FROM deposit_slips
        JOIN users ON users.id = deposit_slips.created_by
        WHERE deposit_slips.deleted_at IS NULL
        ORDER BY date(deposit_slips.deposit_date) DESC, datetime(deposit_slips.created_at) DESC
        LIMIT ? OFFSET ?
        """,
        (limit, offset),
    ).fetchall()


def get_deposit_slip(slip_id: int, include_deleted: bool = False) -> sqlite3.Row | None:
    query = """
        SELECT
            deposit_slips.*,
            creator.full_name AS created_by_name,
            approver.full_name AS approved_by_name
        FROM deposit_slips
        JOIN users AS creator ON creator.id = deposit_slips.created_by
        LEFT JOIN users AS approver ON approver.id = deposit_slips.approved_by
        WHERE deposit_slips.id = ?
    """
    if not include_deleted:
        query += " AND deposit_slips.deleted_at IS NULL"
    return get_db().execute(query, (slip_id,)).fetchone()


def can_view_slip(slip: sqlite3.Row, can_manage: bool) -> bool:
    expire_visible_deposit_slips()
    if can_manage:
        return True
    return bool(
        slip["is_visible"]
        and slip["approval_status"] == "approved"
        and slip["visible_until"]
        and slip["visible_until"] > utc_now()
    )


def approve_deposit_slip(slip_id: int, approved_by: int) -> None:
    now = utc_now()
    get_db().execute(
        """
        UPDATE deposit_slips
        SET approval_status = 'approved',
            is_visible = CASE WHEN visible_until IS NOT NULL AND visible_until != '' THEN 1 ELSE 0 END,
            visible_from = ?,
            approved_by = ?,
            approved_at = ?,
            updated_at = ?
        WHERE id = ? AND deleted_at IS NULL
        """,
        (now, approved_by, now, now, slip_id),
    )
    get_db().commit()


def reject_deposit_slip(slip_id: int, approved_by: int) -> None:
    now = utc_now()
    get_db().execute(
        """
        UPDATE deposit_slips
        SET approval_status = 'rejected',
            is_visible = 0,
            approved_by = ?,
            approved_at = ?,
            updated_at = ?
        WHERE id = ? AND deleted_at IS NULL
        """,
        (approved_by, now, now, slip_id),
    )
    get_db().commit()


def revoke_deposit_slip_visibility(slip_id: int, revoked_by: int) -> None:
    now = utc_now()
    get_db().execute(
        """
        UPDATE deposit_slips
        SET is_visible = 0,
            visible_until = '',
            approved_by = ?,
            approved_at = ?,
            updated_at = ?
        WHERE id = ? AND deleted_at IS NULL
        """,
        (revoked_by, now, now, slip_id),
    )
    get_db().commit()


def soft_delete_deposit_slip(slip_id: int, deleted_by: int) -> None:
    now = utc_now()
    get_db().execute(
        """
        UPDATE deposit_slips
        SET is_visible = 0,
            deleted_at = ?,
            deleted_by = ?,
            updated_at = ?
        WHERE id = ? AND deleted_at IS NULL
        """,
        (now, deleted_by, now, slip_id),
    )
    get_db().commit()


def deleted_deposit_slip_count() -> int:
    row = get_db().execute(
        "SELECT COUNT(*) AS count FROM deposit_slips WHERE deleted_at IS NOT NULL"
    ).fetchone()
    return int(row["count"])


def list_deleted_deposit_slips(limit: int = 10, offset: int = 0) -> list[sqlite3.Row]:
    return get_db().execute(
        """
        SELECT
            deposit_slips.*,
            creator.full_name AS created_by_name,
            deleter.full_name AS deleted_by_name
        FROM deposit_slips
        JOIN users AS creator ON creator.id = deposit_slips.created_by
        LEFT JOIN users AS deleter ON deleter.id = deposit_slips.deleted_by
        WHERE deposit_slips.deleted_at IS NOT NULL
        ORDER BY datetime(deposit_slips.deleted_at) DESC, deposit_slips.id DESC
        LIMIT ? OFFSET ?
        """,
        (limit, offset),
    ).fetchall()


def restore_deposit_slip(slip_id: int, restored_by: int) -> None:
    now = utc_now()
    get_db().execute(
        """
        UPDATE deposit_slips
        SET deleted_at = NULL,
            deleted_by = NULL,
            is_visible = 0,
            visible_from = '',
            approval_status = 'draft',
            approved_by = NULL,
            approved_at = NULL,
            updated_at = ?
        WHERE id = ? AND deleted_at IS NOT NULL
        """,
        (now, slip_id),
    )
    get_db().commit()


def approved_visible_deposit_slip_count() -> int:
    expire_visible_deposit_slips()
    row = get_db().execute(
        """
        SELECT COUNT(*) AS count
        FROM deposit_slips
        WHERE is_visible = 1
          AND deleted_at IS NULL
          AND approval_status = 'approved'
          AND visible_until IS NOT NULL
          AND visible_until != ''
          AND visible_until > ?
        """,
        (utc_now(),),
    ).fetchone()
    return int(row["count"])


def finance_summary() -> dict:
    expire_visible_deposit_slips()
    db = get_db()
    summary = db.execute(
        """
        SELECT
            COUNT(*) AS slip_count,
            COALESCE(SUM(amount_cents), 0) AS total_cents,
            COALESCE(SUM(CASE WHEN is_visible = 1 AND approval_status = 'approved' AND visible_until > ? THEN 1 ELSE 0 END), 0) AS visible_count,
            COALESCE(SUM(CASE WHEN approval_status = 'pending' THEN 1 ELSE 0 END), 0) AS pending_count,
            COALESCE(SUM(CASE WHEN approval_status = 'approved' THEN 1 ELSE 0 END), 0) AS approved_count,
            COALESCE(SUM(CASE WHEN approval_status = 'rejected' THEN 1 ELSE 0 END), 0) AS rejected_count,
            COALESCE(SUM(CASE WHEN approval_status = 'draft' THEN 1 ELSE 0 END), 0) AS draft_count,
            COALESCE(SUM(CASE WHEN approval_status = 'approved' AND is_visible = 0 AND visible_until != '' AND visible_until <= ? THEN 1 ELSE 0 END), 0) AS expired_count
        FROM deposit_slips
        WHERE deleted_at IS NULL
        """,
        (utc_now(), utc_now()),
    ).fetchone()
    monthly = db.execute(
        """
        SELECT substr(deposit_date, 1, 7) AS month, COALESCE(SUM(amount_cents), 0) AS cents
        FROM deposit_slips
        WHERE deleted_at IS NULL
        GROUP BY substr(deposit_date, 1, 7)
        ORDER BY month DESC
        LIMIT 8
        """
    ).fetchall()
    max_monthly_cents = max([int(row["cents"]) for row in monthly] or [1])
    by_bank = db.execute(
        """
        SELECT COALESCE(NULLIF(bank_name, ''), 'Bank not added') AS label,
               COUNT(*) AS count,
               COALESCE(SUM(amount_cents), 0) AS cents
        FROM deposit_slips
        WHERE deleted_at IS NULL
        GROUP BY COALESCE(NULLIF(bank_name, ''), 'Bank not added')
        ORDER BY cents DESC, count DESC
        LIMIT 6
        """
    ).fetchall()
    offerings = db.execute(
        """
        SELECT
            COUNT(*) AS offering_count,
            COALESCE(SUM(amount_cents), 0) AS offering_cents
        FROM finance_offerings
        WHERE deleted_at IS NULL
        """
    ).fetchone()
    offering_monthly = db.execute(
        """
        SELECT substr(offering_date, 1, 7) AS month, COALESCE(SUM(amount_cents), 0) AS cents
        FROM finance_offerings
        WHERE deleted_at IS NULL
        GROUP BY substr(offering_date, 1, 7)
        ORDER BY month DESC
        LIMIT 8
        """
    ).fetchall()
    offering_types = db.execute(
        """
        SELECT offering_type AS label, COUNT(*) AS count, COALESCE(SUM(amount_cents), 0) AS cents
        FROM finance_offerings
        WHERE deleted_at IS NULL
        GROUP BY offering_type
        ORDER BY cents DESC, count DESC
        LIMIT 8
        """
    ).fetchall()
    max_bank_cents = max([int(row["cents"]) for row in by_bank] or [1])
    max_offering_monthly_cents = max([int(row["cents"]) for row in offering_monthly] or [1])
    max_offering_type_cents = max([int(row["cents"]) for row in offering_types] or [1])
    status_breakdown = [
        {"label": "Visible", "count": int(summary["visible_count"])},
        {"label": "Pending", "count": int(summary["pending_count"])},
        {"label": "Approved", "count": int(summary["approved_count"])},
        {"label": "Draft", "count": int(summary["draft_count"])},
        {"label": "Rejected", "count": int(summary["rejected_count"])},
        {"label": "Expired", "count": int(summary["expired_count"])},
    ]
    max_status_count = max([item["count"] for item in status_breakdown] or [1])
    return {
        "slip_count": int(summary["slip_count"]),
        "total_cents": int(summary["total_cents"]),
        "total_money": cents_to_money(int(summary["total_cents"])),
        "offering_count": int(offerings["offering_count"]),
        "offering_cents": int(offerings["offering_cents"]),
        "offering_money": cents_to_money(int(offerings["offering_cents"])),
        "visible_count": int(summary["visible_count"]),
        "pending_count": int(summary["pending_count"]),
        "approved_count": int(summary["approved_count"]),
        "rejected_count": int(summary["rejected_count"]),
        "draft_count": int(summary["draft_count"]),
        "expired_count": int(summary["expired_count"]),
        "status_breakdown": status_breakdown,
        "max_status_count": max_status_count,
        "by_bank": by_bank,
        "max_bank_cents": max_bank_cents,
        "monthly": list(reversed(monthly)),
        "max_monthly_cents": max_monthly_cents,
        "offering_monthly": list(reversed(offering_monthly)),
        "max_offering_monthly_cents": max_offering_monthly_cents,
        "offering_types": offering_types,
        "max_offering_type_cents": max_offering_type_cents,
    }


def list_deposit_slips_for_report() -> list[sqlite3.Row]:
    expire_visible_deposit_slips()
    return get_db().execute(
        """
        SELECT
            deposit_slips.id,
            deposit_slips.title,
            deposit_slips.bank_name,
            deposit_slips.reference,
            deposit_slips.amount_cents,
            deposit_slips.deposit_date,
            deposit_slips.is_visible,
            deposit_slips.visible_from,
            deposit_slips.visible_until,
            deposit_slips.approval_status,
            deposit_slips.original_name,
            deposit_slips.mime_type,
            deposit_slips.size_bytes,
            deposit_slips.created_at,
            deposit_slips.updated_at,
            creator.full_name AS created_by_name,
            approver.full_name AS approved_by_name,
            deposit_slips.approved_at
        FROM deposit_slips
        JOIN users AS creator ON creator.id = deposit_slips.created_by
        LEFT JOIN users AS approver ON approver.id = deposit_slips.approved_by
        WHERE deposit_slips.deleted_at IS NULL
        ORDER BY date(deposit_slips.deposit_date) DESC, datetime(deposit_slips.created_at) DESC
        """
    ).fetchall()
