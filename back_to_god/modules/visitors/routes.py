from __future__ import annotations

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from back_to_god.constants import VISITOR_STATUS_LABELS
from back_to_god.core.pagination import build_pagination, current_page
from back_to_god.core.permissions import can_approve_membership, can_capture_visitors, can_update_visitors, role_required
from back_to_god.core.security import today_date, validate_csrf
from back_to_god.services.audit import log_event
from back_to_god.services.visitors import (
    count_visitors,
    create_visitor,
    get_visitor,
    list_recent_visitors,
    mark_follow_up_made,
    update_status,
    visitor_list_count,
)


bp = Blueprint("visitors", __name__, url_prefix="/visitors")


@bp.route("/", methods=("GET", "POST"))
@role_required("super_admin", "admin", "pastor")
def index():
    if request.method == "POST":
        validate_csrf()
        if not can_capture_visitors():
            abort(403)
        else:
            try:
                visitor_id = create_visitor(request.form, g.user["id"])
            except ValueError as error:
                flash(str(error), "error")
                return redirect(url_for("visitors.index"))
            log_event("visitor_created", g.user["id"], "visitor", visitor_id, request.form.get("full_name", ""))
            flash("Visitor information saved.", "success")
            return redirect(url_for("visitors.index"))

    pagination = build_pagination(visitor_list_count(), current_page(), 10)
    return render_template(
        "visitors/index.html",
        visitors=list_recent_visitors(pagination["per_page"], pagination["offset"]),
        visitor_counts=count_visitors(),
        status_labels=VISITOR_STATUS_LABELS,
        can_capture_visitors=can_capture_visitors(),
        can_update_visitors=can_update_visitors(),
        can_approve_membership=can_approve_membership(),
        today=today_date(),
        pagination=pagination,
    )


@bp.post("/<int:visitor_id>/status")
@role_required("super_admin", "admin", "pastor")
def update_visitor_status(visitor_id: int):
    validate_csrf()
    if not can_update_visitors():
        abort(403)

    status = request.form.get("follow_up_status", "").strip()
    if status not in VISITOR_STATUS_LABELS:
        flash("Choose a valid follow-up status.", "error")
        return redirect(url_for("visitors.index"))

    if get_visitor(visitor_id) is None:
        abort(404)

    update_status(visitor_id, status)
    log_event("visitor_status", g.user["id"], "visitor", visitor_id, status)
    flash("Visitor follow-up updated.", "success")
    return redirect(url_for("visitors.index"))


@bp.post("/<int:visitor_id>/follow-up")
@role_required("super_admin", "admin", "pastor")
def complete_follow_up(visitor_id: int):
    validate_csrf()
    if not can_update_visitors():
        abort(403)
    if get_visitor(visitor_id) is None:
        abort(404)

    notes = request.form.get("follow_up_notes", "").strip()
    mark_follow_up_made(visitor_id, g.user["id"], notes)
    log_event("visitor_follow_up_made", g.user["id"], "visitor", visitor_id, notes)
    flash("Follow-up marked as made.", "success")
    return redirect(url_for("visitors.index"))
