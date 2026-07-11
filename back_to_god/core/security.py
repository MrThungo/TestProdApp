from __future__ import annotations

import secrets
from datetime import datetime
from urllib.parse import urlparse

from flask import abort, request, session


PASSWORD_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"


def utc_now() -> str:
    return datetime.now().isoformat(timespec="milliseconds")


def today_date() -> str:
    return datetime.now().date().isoformat()


def generate_password(groups: int = 4, group_size: int = 4) -> str:
    return "-".join(
        "".join(secrets.choice(PASSWORD_ALPHABET) for _ in range(group_size))
        for _ in range(groups)
    )


def csrf_token() -> str:
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return token


def validate_csrf() -> None:
    submitted_token = request.form.get("_csrf_token") or request.headers.get("X-CSRFToken")
    if not submitted_token and request.is_json:
        submitted_token = (request.get_json(silent=True) or {}).get("_csrf_token")

    if submitted_token != session.get("_csrf_token"):
        abort(400)


def validate_same_origin() -> None:
    origin = request.headers.get("Origin") or request.headers.get("Referer")
    if not origin:
        return

    parsed = urlparse(origin)
    if not parsed.scheme or not parsed.netloc:
        abort(400)

    if parsed.scheme != request.scheme or parsed.netloc != request.host:
        abort(400)
