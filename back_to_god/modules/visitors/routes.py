from __future__ import annotations

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from back_to_god.constants import VISITOR_STATUS_LABELS
from back_to_god.core.pagination import build_pagination, current_page
from back_to_god.core.permissions import can_capture_visitors, can_update_visitors, role_required
from back_to_god.core.security import today_date, validate_csrf
from back_to_god.core.validators import validate_sa_id
from back_to_god.services.audit import log_event
from back_to_god.services.users import normalize_foreign_id, normalize_identity_type
from back_to_god.services.visitors import (
    count_visitors,
    create_visitor,
    get_visitor,
    list_recent_visitors,
    update_status,
    visitor_list_count,
)


bp = Blueprint("visitors", __name__, url_prefix="/visitors")


@bp.route("/", methods=("GET", "POST"))
@role_required("super_admin", "admin", "pastor", "usher")
def index():
    if request.method == "POST":
        validate_csrf()
        if not can_capture_visitors():
            abort(403)
        elif not request.form.get("full_name", "").strip():
            flash("Add the visitor's name before saving.", "error")
        else:
            form = request.form.copy()
            identity_type = normalize_identity_type(form.get("identity_type", "sa_id"))
            form["identity_type"] = identity_type
            if identity_type == "sa_id":
                valid_id, clean_id, dob_or_error = validate_sa_id(form.get("id_number", ""))
                if not valid_id:
                    flash(dob_or_error, "error")
                    return redirect(url_for("visitors.index"))
                form["id_number"] = clean_id
                form["foreign_id_number"] = ""
                form["date_of_birth"] = dob_or_error
            elif not normalize_foreign_id(form.get("foreign_id_number", "")):
                flash("Add a passport, permit, or foreign ID number.", "error")
                return redirect(url_for("visitors.index"))
            create_visitor(form, g.user["id"])
            log_event("visitor_created", g.user["id"], "visitor", None, form.get("full_name", ""))
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
        today=today_date(),
        pagination=pagination,
    )


@bp.post("/<int:visitor_id>/status")
@role_required("super_admin", "admin", "pastor", "usher")
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
