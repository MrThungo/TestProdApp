from __future__ import annotations

from functools import wraps

import sqlite3
from flask import abort, g, redirect, url_for

from back_to_god.constants import (
    CAN_APPROVE_FINANCE_ROLES,
    CAN_CAPTURE_VISITOR_ROLES,
    CAN_GO_LIVE_ROLES,
    CAN_MANAGE_FINANCE_ROLES,
    CAN_UPLOAD_FINANCE_ROLES,
    MANAGED_BY_ADMIN_ROLES,
)


def login_required(view):
    @wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            return redirect(url_for("auth.login"))
        return view(**kwargs)

    return wrapped_view


def role_required(*roles: str):
    def decorator(view):
        @wraps(view)
        def wrapped_view(**kwargs):
            if g.user is None:
                return redirect(url_for("auth.login"))
            if g.user["role"] not in roles:
                abort(403)
            return view(**kwargs)

        return wrapped_view

    return decorator


def allowed_roles_for_current_user() -> list[str]:
    if g.user is None:
        return []
    if g.user["role"] == "super_admin":
        return ["super_admin", "admin", "pastor", "usher", "videographer", "treasurer", "member"]
    if g.user["role"] == "admin":
        return ["admin", "pastor", "usher", "videographer", "treasurer", "member"]
    return []


def can_manage_user(target: sqlite3.Row) -> bool:
    if g.user is None:
        return False
    if g.user["role"] == "super_admin":
        return True
    return g.user["role"] == "admin" and target["role"] in MANAGED_BY_ADMIN_ROLES


def can_update_visitors() -> bool:
    return can_capture_visitors()


def can_capture_visitors() -> bool:
    return g.user is not None and g.user["role"] in CAN_CAPTURE_VISITOR_ROLES


def can_go_live() -> bool:
    return g.user is not None and g.user["role"] in CAN_GO_LIVE_ROLES


def can_manage_finance() -> bool:
    return g.user is not None and g.user["role"] in CAN_MANAGE_FINANCE_ROLES


def can_upload_finance() -> bool:
    return g.user is not None and g.user["role"] in CAN_UPLOAD_FINANCE_ROLES


def can_approve_finance() -> bool:
    return g.user is not None and g.user["role"] in CAN_APPROVE_FINANCE_ROLES
