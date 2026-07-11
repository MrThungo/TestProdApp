from __future__ import annotations

import sqlite3

from flask import request

from back_to_god.core.db import get_db
from back_to_god.core.security import utc_now
from back_to_god.services.users import normalize_text


def log_event(
    action: str,
    user_id: int | None = None,
    entity: str = "",
    entity_id: int | None = None,
    details: str = "",
) -> None:
    get_db().execute(
        """
        INSERT INTO audit_logs (
            user_id, action, entity, entity_id, details, ip_address, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            normalize_text(action, 50),
            normalize_text(entity, 40),
            entity_id,
            normalize_text(details, 180),
            normalize_text(request.remote_addr or "", 45),
            utc_now(),
        ),
    )
    get_db().commit()


def audit_log_count() -> int:
    row = get_db().execute("SELECT COUNT(*) AS count FROM audit_logs").fetchone()
    return int(row["count"])


def list_audit_logs(limit: int = 10, offset: int = 0) -> list[sqlite3.Row]:
    return get_db().execute(
        """
        SELECT audit_logs.*, users.full_name, users.email, users.role
        FROM audit_logs
        LEFT JOIN users ON users.id = audit_logs.user_id
        ORDER BY datetime(audit_logs.created_at) DESC, audit_logs.id DESC
        LIMIT ? OFFSET ?
        """,
        (limit, offset),
    ).fetchall()
