from __future__ import annotations

from flask import Blueprint, abort, flash, g, jsonify, redirect, render_template, request, url_for

from back_to_god.constants import CAN_POST_ANNOUNCEMENT_ROLES
from back_to_god.core.pagination import build_pagination, current_page
from back_to_god.core.permissions import login_required
from back_to_god.core.security import validate_csrf
from back_to_god.services.announcements import (
    announcement_count,
    create_announcement,
    latest_announcement_update,
    list_announcements,
    set_announcement_pin,
    soft_delete_announcement,
)
from back_to_god.services.audit import log_event


bp = Blueprint("announcements", __name__, url_prefix="/announcements")


def can_post_announcements() -> bool:
    return g.user is not None and g.user["role"] in CAN_POST_ANNOUNCEMENT_ROLES


@bp.route("/", methods=("GET", "POST"))
@login_required
def index():
    if request.method == "POST":
        if not can_post_announcements():
            abort(403)
        validate_csrf()
        try:
            announcement_id = create_announcement(
                request.form.get("title", ""),
                request.form.get("body", ""),
                g.user["id"],
                request.form.get("event_at", ""),
                request.form.get("reminder_at", ""),
                request.form.get("is_pinned") == "on",
            )
        except ValueError as error:
            flash(str(error), "error")
            return redirect(url_for("announcements.index"))
        log_event(
            "announcement_created",
            g.user["id"],
            "announcement",
            announcement_id,
            request.form.get("title", ""),
        )
        flash("Announcement posted. Members have been notified.", "success")
        return redirect(url_for("announcements.index", _anchor=f"announcement-{announcement_id}"))

    pagination = build_pagination(announcement_count(), current_page(), 8)
    return render_template(
        "announcements/index.html",
        announcements=list_announcements(pagination["per_page"], pagination["offset"]),
        pagination=pagination,
        can_post_announcements=can_post_announcements(),
        latest_update=latest_announcement_update(),
    )


@bp.get("/poll")
@login_required
def poll():
    since = (request.args.get("since") or "").strip()
    latest_update = latest_announcement_update()
    if latest_update == since:
        return jsonify({"ok": True, "changed": False, "latestUpdate": latest_update})
    pagination = build_pagination(announcement_count(), current_page(), 8)
    return jsonify(
        {
            "ok": True,
            "changed": True,
            "latestUpdate": latest_update,
            "html": render_template(
                "announcements/_list.html",
                announcements=list_announcements(pagination["per_page"], pagination["offset"]),
                pagination=pagination,
                can_post_announcements=can_post_announcements(),
                latest_update=latest_update,
            ),
        }
    )


@bp.post("/<int:announcement_id>/delete")
@login_required
def delete(announcement_id: int):
    if not can_post_announcements():
        abort(403)
    validate_csrf()
    announcement = soft_delete_announcement(announcement_id, g.user["id"])
    if announcement is None:
        abort(404)
    log_event(
        "announcement_deleted",
        g.user["id"],
        "announcement",
        announcement_id,
        announcement["title"],
    )
    flash("Announcement removed from the board.", "success")
    return redirect(url_for("announcements.index"))


@bp.post("/<int:announcement_id>/pin")
@login_required
def pin(announcement_id: int):
    if not can_post_announcements():
        abort(403)
    validate_csrf()
    is_pinned = request.form.get("is_pinned") == "1"
    announcement = set_announcement_pin(announcement_id, is_pinned)
    if announcement is None:
        abort(404)
    log_event(
        "announcement_pin_updated",
        g.user["id"],
        "announcement",
        announcement_id,
        "pinned" if is_pinned else "unpinned",
    )
    flash("Announcement pin updated.", "success")
    return redirect(url_for("announcements.index", _anchor=f"announcement-{announcement_id}"))
