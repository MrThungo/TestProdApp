from __future__ import annotations

import secrets
from pathlib import Path

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)
from werkzeug.utils import secure_filename

from back_to_god.core.permissions import login_required
from back_to_god.core.security import validate_csrf
from back_to_god.core.validators import validate_sa_id
from back_to_god.services.audit import log_event
from back_to_god.services.users import (
    get_user_profile,
    identity_exists,
    normalize_foreign_id,
    normalize_identity_type,
    update_profile,
)


bp = Blueprint("profile", __name__, url_prefix="/profile")

ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "gif"}


def allowed_image(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS


def save_profile_photo(file_storage, user_id: int) -> str | None:
    if not file_storage or not file_storage.filename:
        return None
    if not allowed_image(file_storage.filename):
        raise ValueError("Upload a JPG, PNG, WEBP, or GIF image.")

    upload_dir: Path = current_app.config["PROFILE_UPLOAD_DIR"]
    upload_dir.mkdir(parents=True, exist_ok=True)

    extension = secure_filename(file_storage.filename).rsplit(".", 1)[1].lower()
    filename = f"user-{user_id}-{secrets.token_hex(8)}.{extension}"
    file_storage.save(upload_dir / filename)
    return filename


@bp.route("/", methods=("GET", "POST"))
@login_required
def edit():
    user = get_user_profile(g.user["id"])
    if user is None:
        abort(404)

    if request.method == "POST":
        validate_csrf()
        full_name = request.form.get("full_name", "").strip()
        phone = request.form.get("phone", "").strip()
        home_area = request.form.get("home_area", "").strip()
        bio = request.form.get("bio", "").strip()
        emergency_contact_name = request.form.get("emergency_contact_name", "").strip()
        emergency_contact_phone = request.form.get("emergency_contact_phone", "").strip()
        emergency_contact_relationship = request.form.get("emergency_contact_relationship", "").strip()
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
            dob_or_error = "Add your date of birth."

        if not full_name:
            flash("Your name is required.", "error")
            return redirect(url_for("profile.edit"))
        if not valid_id:
            flash(dob_or_error, "error")
            return redirect(url_for("profile.edit"))
        if identity_exists(id_number=clean_id, foreign_id_number=foreign_id_number, exclude_user_id=g.user["id"]):
            flash("Another user already has that identity number.", "error")
            return redirect(url_for("profile.edit"))

        try:
            profile_photo = save_profile_photo(request.files.get("profile_photo"), g.user["id"])
        except ValueError as error:
            flash(str(error), "error")
            return redirect(url_for("profile.edit"))

        update_profile(
            g.user["id"],
            full_name,
            phone,
            home_area,
            bio,
            emergency_contact_name,
            emergency_contact_phone,
            emergency_contact_relationship,
            clean_id,
            dob_or_error,
            identity_type,
            foreign_id_number,
            nationality,
            profile_photo,
        )
        log_event("profile_updated", g.user["id"], "user", g.user["id"], "Profile saved")
        flash("Profile updated.", "success")
        return redirect(url_for("profile.edit"))

    return render_template("profile/edit.html", user=user)


@bp.get("/photo/<path:filename>")
@login_required
def photo(filename: str):
    safe_name = secure_filename(filename)
    if safe_name != filename:
        abort(404)
    return send_from_directory(current_app.config["PROFILE_UPLOAD_DIR"], safe_name)
