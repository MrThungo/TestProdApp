from __future__ import annotations

from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from back_to_god.core.pagination import build_pagination, current_page
from back_to_god.core.permissions import can_approve_membership, role_required
from back_to_god.core.security import validate_csrf
from back_to_god.services.audit import log_event
from back_to_god.services.email import send_account_created_email
from back_to_god.services.members import (
    approve_membership_request,
    count_members,
    list_members,
    list_pending_membership_requests,
    member_directory_count,
)


bp = Blueprint("members", __name__, url_prefix="/members")


@bp.get("/")
@role_required("super_admin", "admin", "pastor")
def index():
    search_query = request.args.get("q", "").strip()
    pagination = build_pagination(member_directory_count(search_query), current_page(), 10)
    return render_template(
        "members/index.html",
        members=list_members(pagination["per_page"], pagination["offset"], search_query),
        pending_requests=list_pending_membership_requests(),
        member_counts=count_members(),
        pagination=pagination,
        search_query=search_query,
        can_approve_membership=can_approve_membership(),
    )


@bp.post("/requests/<int:visitor_id>/approve")
@role_required("super_admin", "admin")
def approve_request(visitor_id: int):
    validate_csrf()
    notes = request.form.get("membership_notes", "").strip()
    try:
        member, password, created = approve_membership_request(visitor_id, g.user["id"], notes)
    except ValueError as error:
        flash(str(error), "error")
        return redirect(url_for("members.index", _anchor=f"membership-request-{visitor_id}"))

    log_event("membership_request_approved", g.user["id"], "visitor", visitor_id, member["email"])
    if created:
        email_sent = send_account_created_email(member["email"], member["full_name"], password)
        if email_sent:
            flash("Membership approved. The new member login details were emailed.", "success")
        else:
            flash("Membership approved, but email could not be sent. Check the email outbox for the temporary password.", "warning")
    else:
        flash("Membership request approved and linked to the existing member account.", "success")
    return redirect(url_for("members.index"))
