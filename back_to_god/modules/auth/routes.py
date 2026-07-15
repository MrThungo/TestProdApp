from __future__ import annotations

import sqlite3

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash

from back_to_god.constants import ROLE_ICONS, ROLE_LABELS
from back_to_god.core.permissions import login_required
from back_to_god.core.rate_limit import clear_attempts, is_limited, record_attempt
from back_to_god.core.security import validate_csrf
from back_to_god.core.validators import is_valid_email, validate_password_strength, validate_sa_id
from back_to_god.services.audit import log_event
from back_to_god.services.email import (
    send_account_created_email,
    send_password_changed_email,
    send_password_reset_link,
)
from back_to_god.services.users import (
    QUICK_LOGIN_USERS,
    change_password as update_user_password,
    create_password_reset_token,
    get_valid_password_reset_token,
    get_or_create_quick_user,
    get_user_by_email,
    identity_exists,
    normalize_foreign_id,
    normalize_identity_type,
    record_login,
    reset_password_with_token,
    signup_member,
)


bp = Blueprint("auth", __name__)

LOGIN_LIMIT = 8
LOGIN_WINDOW_SECONDS = 15 * 60
RESET_LIMIT = 5
RESET_WINDOW_SECONDS = 15 * 60
QUICK_LOGIN_LIMIT = 20
QUICK_LOGIN_WINDOW_SECONDS = 60


def _limited_message(retry_after: int) -> str:
    minutes = max(1, (retry_after + 59) // 60)
    return f"Too many attempts. Please try again in about {minutes} minute{'s' if minutes != 1 else ''}."


def _flash_if_limited(scope: str, key: str, *, limit: int, window_seconds: int) -> bool:
    limited, retry_after = is_limited(scope, key, limit=limit, window_seconds=window_seconds)
    if limited:
        flash(_limited_message(retry_after), "error")
    return limited


@bp.route("/login", methods=("GET", "POST"))
def login():
    if g.user is not None:
        return redirect(url_for("dashboard.index"))

    if request.method == "POST":
        validate_csrf()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        remember_me = request.form.get("remember_me") == "on"
        if not _flash_if_limited("login", email or "blank", limit=LOGIN_LIMIT, window_seconds=LOGIN_WINDOW_SECONDS):
            user = get_user_by_email(email, include_deleted=True)

            if user is None or not check_password_hash(user["password_hash"], password):
                record_attempt("login", email or "blank", window_seconds=LOGIN_WINDOW_SECONDS)
                flash("The email or password is not correct.", "error")
            elif not user["is_active"] or user["deleted_at"]:
                record_attempt("login", email or "blank", window_seconds=LOGIN_WINDOW_SECONDS)
                flash("This account is inactive.", "error")
            else:
                clear_attempts("login", email or "blank")
                session.clear()
                session.permanent = remember_me
                session["user_id"] = user["id"]
                record_login(user["id"])
                log_event("login", user["id"], "user", user["id"], "Signed in")
                return redirect(url_for("dashboard.index"))

    quick_roles = [role for role in QUICK_LOGIN_USERS if role in ROLE_LABELS]
    return render_template(
        "auth/login.html",
        quick_roles=quick_roles,
        role_icons=ROLE_ICONS,
        role_labels=ROLE_LABELS,
    )


@bp.route("/signup", methods=("GET", "POST"))
def signup():
    if g.user is not None:
        return redirect(url_for("dashboard.index"))

    if request.method == "POST":
        validate_csrf()
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        home_area = request.form.get("home_area", "").strip()
        id_number = request.form.get("id_number", "").strip()
        identity_type = normalize_identity_type(request.form.get("identity_type", "sa_id"))
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
            dob_or_error = "Add your date of birth."

        if not full_name or not email:
            flash("Add your name and email to create the account.", "error")
        elif not is_valid_email(email):
            flash("Add a valid email address.", "error")
        elif not valid_id:
            flash(dob_or_error, "error")
        elif identity_exists(id_number=clean_id, foreign_id_number=foreign_id_number):
            flash("An account with that identity number already exists.", "error")
        else:
            try:
                password = signup_member(
                    full_name,
                    email,
                    phone,
                    home_area,
                    clean_id,
                    dob_or_error,
                    identity_type,
                    foreign_id_number,
                    nationality,
                )
                email_sent = send_account_created_email(email, full_name, password)
                if email_sent:
                    flash("Member account created. The temporary password has been emailed.", "success")
                else:
                    flash("Member account created, but email could not be sent. Ask an admin to check the email outbox.", "warning")
                log_event("signup", None, "user", None, email)
            except sqlite3.IntegrityError:
                flash("An account with that email already exists.", "error")

    return render_template("auth/signup.html")


@bp.route("/forgot-password", methods=("GET", "POST"))
def forgot_password():
    if g.user is not None:
        return redirect(url_for("dashboard.index"))

    if request.method == "POST":
        validate_csrf()
        email = request.form.get("email", "").strip().lower()
        if _flash_if_limited("forgot-password", email or "blank", limit=RESET_LIMIT, window_seconds=RESET_WINDOW_SECONDS):
            return render_template("auth/forgot_password.html")
        record_attempt("forgot-password", email or "blank", window_seconds=RESET_WINDOW_SECONDS)
        user = get_user_by_email(email)
        if user is not None and user["is_active"]:
            token = create_password_reset_token(user["id"])
            reset_url = url_for("auth.reset_password_token", token=token, _external=True)
            email_sent = send_password_reset_link(user["email"], user["full_name"], reset_url)
            log_event(
                "forgot_password_requested",
                user["id"],
                "user",
                user["id"],
                "Reset link sent" if email_sent else "Reset link written to outbox",
            )
        flash("If that account exists, a reset link has been sent. The link expires in 5 minutes.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/forgot_password.html")


@bp.route("/reset-password/<token>", methods=("GET", "POST"))
def reset_password_token(token: str):
    if g.user is not None:
        return redirect(url_for("dashboard.index"))
    reset = get_valid_password_reset_token(token)
    if reset is None:
        flash("That reset link is invalid or has expired.", "error")
        return redirect(url_for("auth.forgot_password"))

    if request.method == "POST":
        validate_csrf()
        if _flash_if_limited("reset-password", token[:32], limit=RESET_LIMIT, window_seconds=RESET_WINDOW_SECONDS):
            return render_template("auth/reset_password.html", token=token, reset=reset)
        record_attempt("reset-password", token[:32], window_seconds=RESET_WINDOW_SECONDS)
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        if password != confirm_password:
            flash("Passwords do not match.", "error")
        else:
            errors = validate_password_strength(password)
            if errors:
                for error in errors:
                    flash(error, "error")
            else:
                used = reset_password_with_token(token, password)
                if used is None:
                    flash("That reset link is invalid or has expired.", "error")
                    return redirect(url_for("auth.forgot_password"))
                send_password_changed_email(reset["email"], reset["full_name"])
                log_event("password_reset_by_link", reset["user_id"], "user", reset["user_id"], "Forgot password")
                clear_attempts("reset-password", token[:32])
                flash("Password changed. You can sign in now.", "success")
                return redirect(url_for("auth.login"))

    return render_template("auth/reset_password.html", token=token, reset=reset)


@bp.route("/change-password", methods=("GET", "POST"))
@login_required
def change_password():
    if request.method == "POST":
        validate_csrf()
        password_key = str(g.user["id"])
        if _flash_if_limited("change-password", password_key, limit=RESET_LIMIT, window_seconds=RESET_WINDOW_SECONDS):
            return render_template("auth/change_password.html")
        record_attempt("change-password", password_key, window_seconds=RESET_WINDOW_SECONDS)
        current_password = request.form.get("current_password", "")
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not check_password_hash(g.user["password_hash"], current_password):
            flash("Current password is not correct.", "error")
        elif password != confirm_password:
            flash("Passwords do not match.", "error")
        elif check_password_hash(g.user["password_hash"], password):
            flash("Choose a password that is different from the generated one.", "error")
        else:
            errors = validate_password_strength(password)
            if errors:
                for error in errors:
                    flash(error, "error")
            else:
                update_user_password(g.user["id"], password)
                send_password_changed_email(g.user["email"], g.user["full_name"])
                log_event("password_changed", g.user["id"], "user", g.user["id"], "First login complete")
                clear_attempts("change-password", password_key)
                flash("Password changed. You can now use the app.", "success")
                return redirect(url_for("dashboard.index"))

    return render_template("auth/change_password.html")


@bp.post("/quick-login/<role>")
def quick_login(role: str):
    if not current_app.config.get("ENABLE_QUICK_LOGIN", True):
        abort(404)
    if role not in QUICK_LOGIN_USERS:
        abort(404)

    validate_csrf()
    if _flash_if_limited("quick-login", role, limit=QUICK_LOGIN_LIMIT, window_seconds=QUICK_LOGIN_WINDOW_SECONDS):
        return redirect(url_for("auth.login"))
    record_attempt("quick-login", role, window_seconds=QUICK_LOGIN_WINDOW_SECONDS)
    user = get_or_create_quick_user(role)
    if not user["is_active"] or user["deleted_at"]:
        flash("This account is inactive.", "error")
        return redirect(url_for("auth.login"))

    session.clear()
    session.permanent = True
    session["user_id"] = user["id"]
    record_login(user["id"])
    log_event("quick_login", user["id"], "user", user["id"], role)
    flash(f"Signed in as {ROLE_LABELS[role]}.", "success")
    return redirect(url_for("dashboard.index"))


@bp.post("/logout")
@login_required
def logout():
    validate_csrf()
    session.clear()
    return redirect(url_for("public.landing"))
