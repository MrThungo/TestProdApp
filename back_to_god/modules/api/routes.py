from __future__ import annotations

import secrets
import time
from hmac import compare_digest
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request

from back_to_god.constants import ROLE_LABELS
from back_to_god.core.db import get_db
from back_to_god.core.security import utc_now
from back_to_god.services.users import normalize_text


bp = Blueprint("api", __name__, url_prefix="/api")

_WINDOW_SECONDS = 60
_MAX_REQUESTS_PER_WINDOW = 30
_rate_windows: dict[str, list[float]] = {}


def ensure_external_notification_api_key() -> str:
    configured = (current_app.config.get("EXTERNAL_NOTIFICATION_API_KEY") or "").strip()
    if configured:
        return configured

    key_path: Path = current_app.config["EXTERNAL_NOTIFICATION_KEY_FILE"]
    key_path.parent.mkdir(parents=True, exist_ok=True)
    if key_path.exists():
        existing = key_path.read_text(encoding="utf-8").strip()
        if existing:
            return existing

    generated = secrets.token_urlsafe(32)
    key_path.write_text(generated + "\n", encoding="utf-8")
    return generated


def _submitted_api_key() -> str:
    auth_header = request.headers.get("Authorization", "")
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()
    return (request.headers.get("X-API-Key") or "").strip()


def _authorized() -> bool:
    expected = ensure_external_notification_api_key()
    submitted = _submitted_api_key()
    return bool(submitted and compare_digest(submitted, expected))


def _rate_limited() -> bool:
    now = time.time()
    ip_address = request.headers.get("X-Forwarded-For", request.remote_addr or "unknown").split(",")[0].strip()
    window = [stamp for stamp in _rate_windows.get(ip_address, []) if now - stamp < _WINDOW_SECONDS]
    if len(window) >= _MAX_REQUESTS_PER_WINDOW:
        _rate_windows[ip_address] = window
        return True
    window.append(now)
    _rate_windows[ip_address] = window
    return False


def _safe_target_url(value: str) -> str:
    target = normalize_text(value, 140)
    if target.startswith("/") and not target.startswith("//"):
        return target
    return ""


def _target_users(payload: dict) -> list[int]:
    db = get_db()
    raw_ids = payload.get("user_ids")
    if isinstance(raw_ids, list) and raw_ids:
        clean_ids = [int(item) for item in raw_ids if str(item).isdigit()]
        if not clean_ids:
            return []
        placeholders = ",".join("?" for _ in clean_ids)
        rows = db.execute(
            f"""
            SELECT id
            FROM users
            WHERE id IN ({placeholders})
              AND is_active = 1
              AND deleted_at IS NULL
            """,
            clean_ids,
        ).fetchall()
        return [int(row["id"]) for row in rows]

    role = normalize_text(str(payload.get("role") or ""), 40)
    if role:
        if role not in ROLE_LABELS:
            return []
        rows = db.execute(
            """
            SELECT id
            FROM users
            WHERE role = ?
              AND is_active = 1
              AND deleted_at IS NULL
            """,
            (role,),
        ).fetchall()
        return [int(row["id"]) for row in rows]

    rows = db.execute(
        """
        SELECT id
        FROM users
        WHERE is_active = 1
          AND deleted_at IS NULL
        """
    ).fetchall()
    return [int(row["id"]) for row in rows]


@bp.post("/notifications/send")
def send_external_notification():
    if not _authorized():
        return jsonify({"ok": False, "error": "Unauthorized"}), 401
    if _rate_limited():
        return jsonify({"ok": False, "error": "Rate limit exceeded"}), 429
    if not request.is_json:
        return jsonify({"ok": False, "error": "Send JSON"}), 415

    payload = request.get_json(silent=True) or {}
    title = normalize_text(str(payload.get("title") or ""), 80)
    message = normalize_text(str(payload.get("message") or ""), 220)
    if not title or not message:
        return jsonify({"ok": False, "error": "title and message are required"}), 400

    user_ids = _target_users(payload)
    if not user_ids:
        return jsonify({"ok": False, "error": "No active users matched"}), 404

    target_url = _safe_target_url(str(payload.get("target_url") or ""))
    category = normalize_text(str(payload.get("category") or "external"), 40) or "external"
    now = utc_now()
    db = get_db()
    for user_id in user_ids:
        db.execute(
            """
            INSERT INTO notifications (user_id, title, message, target_url, category, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, title, message, target_url, category, now),
        )
    db.commit()
    return jsonify({"ok": True, "sent": len(user_ids)})
