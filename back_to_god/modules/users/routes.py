from __future__ import annotations

import csv
import sqlite3
from io import StringIO

from flask import Blueprint, Response, abort, flash, g, redirect, render_template, request, url_for

from back_to_god.constants import ROLE_LABELS
from back_to_god.core.formatting import age_from_dob
from back_to_god.core.pagination import build_pagination, current_page
from back_to_god.core.permissions import allowed_roles_for_current_user, can_manage_user, role_required
from back_to_god.core.security import utc_now, validate_csrf
from back_to_god.core.validators import is_valid_email, validate_sa_id
from back_to_god.services.audit import log_event
from back_to_god.services.email import send_account_created_email
from back_to_god.services.users import (
    create_user,
    deleted_user_count,
    directory_user_count,
    get_user_by_id,
    identity_exists,
    list_deleted_users,
    list_users_for_report,
    list_users,
    normalize_foreign_id,
    normalize_identity_type,
    reset_password as reset_user_password,
    restore_user,
    set_active,
    soft_delete_user,
    update_user_role,
    user_analytics,
)


bp = Blueprint("users", __name__, url_prefix="/users")


def _report_filename(name: str) -> str:
    stamp = utc_now().replace(":", "").replace("-", "")[:13]
    return f"back-to-god-{name}-{stamp}.csv"


def _csv_response(filename: str, headers: list[str], rows: list[list[object]]) -> Response:
    output = StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(headers)
    writer.writerows(rows)
    response = Response("\ufeff" + output.getvalue(), mimetype="text/csv; charset=utf-8")
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def _users_report(include_deleted: bool = False) -> Response:
    can_see_age = g.user["role"] in {"super_admin", "pastor"}
    headers = [
        "Full name",
        "Email",
        "Role",
        "Status",
        "Password status",
        "Phone",
        "Home area",
        "Emergency contact",
        "Emergency phone",
        "Emergency relationship",
        "Created",
        "Last login",
        "Last seen",
    ]
    if can_see_age:
        headers[3:3] = ["Identity type", "SA ID", "Foreign ID", "Nationality", "Date of birth", "Age"]
    if include_deleted:
        headers.extend(["Deleted at", "Deleted by"])

    rows = []
    for user in list_users_for_report(include_deleted):
        row = [
            user["full_name"],
            user["email"],
            ROLE_LABELS.get(user["role"], user["role"].replace("_", " ").title()),
            "Active" if user["is_active"] else "Inactive",
            "Must change password" if user["must_change_password"] else "Set",
            user["phone"] or "",
            user["home_area"] or "",
            user["emergency_contact_name"] or "",
            user["emergency_contact_phone"] or "",
            user["emergency_contact_relationship"] or "",
            user["created_at"] or "",
            user["last_login_at"] or "",
            user["last_seen_at"] or "",
        ]
        if can_see_age:
            row[3:3] = [
                user["identity_type"] or "sa_id",
                user["id_number"] or "",
                user["foreign_id_number"] or "",
                user["nationality"] or "",
                user["date_of_birth"] or "",
                age_from_dob(user["date_of_birth"]),
            ]
        if include_deleted:
            row.extend([user["deleted_at"] or "", user["deleted_by_name"] or ""])
        rows.append(row)

    report_name = "deleted-users-report" if include_deleted else "users-directory-report"
    log_event(f"{report_name}_downloaded", g.user["id"], "report", None, str(len(rows)))
    return _csv_response(_report_filename(report_name), headers, rows)


@bp.route("/", methods=("GET", "POST"))
@role_required("super_admin", "admin", "pastor")
def index():
    allowed_roles = allowed_roles_for_current_user()
    can_create_users = bool(allowed_roles)
    search_query = request.args.get("q", "").strip()
    role_filter = request.args.get("role", "").strip()

    if request.method == "POST":
        if not can_create_users:
            abort(403)
        validate_csrf()
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        role = request.form.get("role", "").strip()
        identity_type = normalize_identity_type(request.form.get("identity_type", "sa_id"))
        id_number = request.form.get("id_number", "").strip()
        foreign_id_number = normalize_foreign_id(request.form.get("foreign_id_number", ""))
        nationality = request.form.get("nationality", "").strip()
        date_of_birth = request.form.get("date_of_birth", "").strip()
        valid_id = True
        clean_id = ""
        dob_or_error = date_of_birth
        if identity_type == "sa_id":
            valid_id, clean_id, dob_or_error = validate_sa_id(id_number, required=True)
            foreign_id_number = ""
        elif not foreign_id_number:
            valid_id = False
            dob_or_error = "Add a passport, permit, or foreign ID number."
        elif not date_of_birth:
            valid_id = False
            dob_or_error = "Add the date of birth for the foreign national."

        if not full_name or not email:
            flash("Add a name and email.", "error")
        elif not is_valid_email(email):
            flash("Add a valid email address.", "error")
        elif role not in allowed_roles:
            flash("You cannot create that role.", "error")
        elif not valid_id:
            flash(dob_or_error, "error")
        elif identity_exists(id_number=clean_id, foreign_id_number=foreign_id_number):
            flash("Another user already has that identity number.", "error")
        else:
            try:
                password = create_user(
                    full_name,
                    email,
                    role,
                    g.user["id"],
                    clean_id,
                    dob_or_error,
                    identity_type,
                    foreign_id_number,
                    nationality,
                )
                send_account_created_email(email, full_name, password)
                log_event("user_created", g.user["id"], "user", None, email)
                flash("Account created. The temporary password has been emailed.", "success")
                return redirect(url_for("users.index"))
            except sqlite3.IntegrityError:
                flash("An account with that email already exists.", "error")

    can_see_age = g.user["role"] in {"super_admin", "pastor"}
    pagination = build_pagination(directory_user_count(search_query, role_filter), current_page(), 10)
    return render_template(
        "users/index.html",
        users=list_users(pagination["per_page"], pagination["offset"], search_query, role_filter),
        allowed_roles=allowed_roles,
        can_create_users=can_create_users,
        role_labels=ROLE_LABELS,
        pagination=pagination,
        can_see_age=can_see_age,
        deleted_users=deleted_user_count(),
        analytics=user_analytics(can_see_age),
        search_query=search_query,
        role_filter=role_filter,
    )


@bp.get("/<int:user_id>")
@role_required("super_admin", "admin", "pastor")
def profile(user_id: int):
    target = get_user_by_id(user_id)
    if target is None:
        abort(404)
    if g.user["role"] != "super_admin" and not can_manage_user(target) and g.user["role"] != "pastor":
        abort(403)
    return render_template(
        "users/profile.html",
        user=target,
        role_labels=ROLE_LABELS,
        can_see_age=g.user["role"] in {"super_admin", "pastor"},
    )


@bp.get("/reports/directory.csv")
@role_required("super_admin", "admin", "pastor")
def directory_report():
    return _users_report(False)


@bp.get("/reports/recycle-bin.csv")
@role_required("super_admin", "admin")
def recycle_bin_report():
    return _users_report(True)


@bp.post("/<int:user_id>/reset-password")
@role_required("super_admin", "admin")
def reset_password(user_id: int):
    validate_csrf()
    target = get_user_by_id(user_id)
    if target is None:
        abort(404)
    if not can_manage_user(target):
        abort(403)

    password = reset_user_password(user_id)
    send_account_created_email(target["email"], target["full_name"], password)
    log_event("password_reset", g.user["id"], "user", user_id, target["email"])
    flash("A new temporary password was emailed to the user.", "success")
    return redirect(url_for("users.index"))


@bp.post("/<int:user_id>/role")
@role_required("super_admin")
def change_role(user_id: int):
    validate_csrf()
    target = get_user_by_id(user_id)
    if target is None:
        abort(404)
    if user_id == g.user["id"]:
        flash("You cannot change your own role.", "error")
        return redirect(url_for("users.index"))
    new_role = request.form.get("role", "").strip()
    if new_role not in ROLE_LABELS:
        flash("Choose a valid role.", "error")
        return redirect(url_for("users.index"))
    update_user_role(user_id, new_role)
    log_event("user_role_changed", g.user["id"], "user", user_id, f"{target['role']} to {new_role}")
    flash("User role updated.", "success")
    return redirect(request.referrer or url_for("users.index"))


@bp.post("/<int:user_id>/toggle-active")
@role_required("super_admin", "admin")
def toggle_active(user_id: int):
    validate_csrf()
    if user_id == g.user["id"]:
        flash("You cannot deactivate your own account.", "error")
        return redirect(url_for("users.index"))

    target = get_user_by_id(user_id)
    if target is None:
        abort(404)
    if not can_manage_user(target):
        abort(403)

    set_active(user_id, not bool(target["is_active"]))
    log_event("user_status", g.user["id"], "user", user_id, "active" if not target["is_active"] else "inactive")
    flash("Account status updated.", "success")
    return redirect(url_for("users.index"))


@bp.post("/<int:user_id>/soft-delete")
@role_required("super_admin", "admin")
def soft_delete(user_id: int):
    validate_csrf()
    if user_id == g.user["id"]:
        flash("You cannot move your own account to the recycle bin.", "error")
        return redirect(url_for("users.index"))

    target = get_user_by_id(user_id)
    if target is None:
        abort(404)
    if not can_manage_user(target):
        abort(403)

    soft_delete_user(user_id, g.user["id"])
    log_event("user_soft_deleted", g.user["id"], "user", user_id, target["email"])
    flash("Account moved to the recycle bin.", "success")
    return redirect(url_for("users.index"))


@bp.get("/recycle-bin")
@role_required("super_admin", "admin")
def recycle_bin():
    pagination = build_pagination(deleted_user_count(), current_page(), 10)
    return render_template(
        "users/recycle_bin.html",
        users=list_deleted_users(pagination["per_page"], pagination["offset"]),
        role_labels=ROLE_LABELS,
        pagination=pagination,
        can_see_age=g.user["role"] in {"super_admin", "pastor"},
        deleted_users=deleted_user_count(),
    )


@bp.post("/<int:user_id>/restore")
@role_required("super_admin", "admin")
def restore(user_id: int):
    validate_csrf()
    target = get_user_by_id(user_id)
    if target is None:
        abort(404)
    if not can_manage_user(target):
        abort(403)

    restore_user(user_id)
    log_event("user_restored", g.user["id"], "user", user_id, target["email"])
    flash("Account restored.", "success")
    return redirect(url_for("users.recycle_bin"))
