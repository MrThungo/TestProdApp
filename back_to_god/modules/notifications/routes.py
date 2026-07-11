from __future__ import annotations

from flask import Blueprint, abort, flash, g, jsonify, redirect, render_template, url_for

from back_to_god.core.pagination import build_pagination, current_page
from back_to_god.core.permissions import login_required
from back_to_god.core.security import validate_csrf
from back_to_god.services.messages import unread_message_count
from back_to_god.services.notifications import (
    clear_notifications,
    delete_notification,
    get_notification,
    list_notifications,
    mark_all_read,
    mark_read,
    notification_count,
    unread_count,
)


bp = Blueprint("notifications", __name__, url_prefix="/notifications")


@bp.get("/")
@login_required
def index():
    pagination = build_pagination(notification_count(g.user["id"]), current_page(), 10)
    return render_template(
        "notifications/index.html",
        notifications=list_notifications(g.user["id"], pagination["per_page"], pagination["offset"]),
        pagination=pagination,
    )


@bp.post("/read")
@login_required
def read_all():
    validate_csrf()
    mark_all_read(g.user["id"])
    return redirect(url_for("notifications.index"))


@bp.post("/clear")
@login_required
def clear_all():
    validate_csrf()
    clear_notifications(g.user["id"])
    flash("Notifications cleared.", "success")
    return redirect(url_for("notifications.index"))


@bp.post("/<int:notification_id>/delete")
@login_required
def delete(notification_id: int):
    validate_csrf()
    item = get_notification(g.user["id"], notification_id)
    if item is None:
        abort(404)
    delete_notification(g.user["id"], notification_id)
    flash("Notification deleted.", "success")
    return redirect(url_for("notifications.index"))


@bp.get("/<int:notification_id>/open")
@login_required
def open_notification(notification_id: int):
    item = get_notification(g.user["id"], notification_id)
    if item is None:
        abort(404)
    mark_read(g.user["id"], notification_id)
    return redirect(item["target_url"] or url_for("notifications.index"))


@bp.get("/poll")
@login_required
def poll():
    latest = list_notifications(g.user["id"], 4)
    return jsonify(
        {
            "ok": True,
            "unread": unread_count(g.user["id"]),
            "unreadMessages": unread_message_count(g.user["id"]),
            "items": [
                {
                    "id": item["id"],
                    "title": item["title"],
                    "message": item["message"],
                    "targetUrl": url_for("notifications.open_notification", notification_id=item["id"]),
                    "isRead": bool(item["is_read"]),
                }
                for item in latest
            ],
        }
    )
