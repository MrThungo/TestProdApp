from __future__ import annotations

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from back_to_god.constants import ROLE_LABELS
from back_to_god.core.permissions import login_required
from back_to_god.core.security import validate_csrf
from back_to_god.services.audit import log_event
from back_to_god.services.committees import (
    add_committee_member,
    can_manage_committees,
    create_committee,
    list_committee_user_options,
    list_committees,
    remove_committee_member,
    soft_delete_committee,
)


bp = Blueprint("committees", __name__, url_prefix="/committees")


def _can_manage_committees() -> bool:
    return g.user is not None and can_manage_committees(g.user["role"])


@bp.get("/")
@login_required
def index():
    return render_template(
        "committees/index.html",
        committees=list_committees(),
        user_options=list_committee_user_options() if _can_manage_committees() else [],
        can_manage_committees=_can_manage_committees(),
        role_labels=ROLE_LABELS,
    )


@bp.post("/")
@login_required
def create():
    if not _can_manage_committees():
        abort(403)
    validate_csrf()
    try:
        committee_id = create_committee(
            request.form.get("name", ""),
            request.form.get("description", ""),
            g.user["id"],
        )
    except ValueError as error:
        flash(str(error), "error")
        return redirect(url_for("committees.index"))

    log_event("committee_created", g.user["id"], "committee", committee_id, request.form.get("name", ""))
    flash("Committee created.", "success")
    return redirect(url_for("committees.index", _anchor=f"committee-{committee_id}"))


@bp.post("/<int:committee_id>/members")
@login_required
def add_member(committee_id: int):
    if not _can_manage_committees():
        abort(403)
    validate_csrf()
    try:
        user_id = int(request.form.get("user_id", "0"))
    except ValueError:
        user_id = 0
    try:
        sort_order = int(request.form.get("sort_order", "0"))
    except ValueError:
        sort_order = 0

    try:
        add_committee_member(
            committee_id,
            user_id,
            request.form.get("title", ""),
            sort_order,
        )
    except ValueError as error:
        flash(str(error), "error")
        return redirect(url_for("committees.index", _anchor=f"committee-{committee_id}"))

    log_event("committee_member_added", g.user["id"], "committee", committee_id, str(user_id))
    flash("Committee member saved.", "success")
    return redirect(url_for("committees.index", _anchor=f"committee-{committee_id}"))


@bp.post("/members/<int:membership_id>/remove")
@login_required
def remove_member(membership_id: int):
    if not _can_manage_committees():
        abort(403)
    validate_csrf()
    row = remove_committee_member(membership_id)
    if row is None:
        abort(404)

    log_event("committee_member_removed", g.user["id"], "committee", row["committee_id"], row["full_name"])
    flash("Committee member removed.", "success")
    return redirect(url_for("committees.index", _anchor=f"committee-{row['committee_id']}"))


@bp.post("/<int:committee_id>/delete")
@login_required
def delete(committee_id: int):
    if not _can_manage_committees():
        abort(403)
    validate_csrf()
    committee = soft_delete_committee(committee_id, g.user["id"])
    if committee is None:
        abort(404)

    log_event("committee_deleted", g.user["id"], "committee", committee_id, committee["name"])
    flash("Committee removed.", "success")
    return redirect(url_for("committees.index"))
