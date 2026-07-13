from __future__ import annotations

from flask import (
    Blueprint,
    Response,
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    stream_with_context,
    url_for,
)
from werkzeug.utils import secure_filename

from back_to_god.core.db import get_db
from back_to_god.core.security import today_date, validate_csrf
from back_to_god.services.audit import log_event
from back_to_god.services.committees import list_committees
from back_to_god.services.gallery import gallery_media_bytes, get_gallery_media, list_gallery_slideshow
from back_to_god.services.visitors import create_visitor

bp = Blueprint("public", __name__)


@bp.get("/")
def landing():
    return render_template(
        "public/landing.html",
        committees=list_committees(),
        slideshow_items=list_gallery_slideshow(),
    )


@bp.get("/slideshow-media/<int:media_id>")
def slideshow_media(media_id: int):
    item = get_gallery_media(media_id)
    if item is None:
        abort(404)
    selected = get_db().execute(
        """
        SELECT id
        FROM gallery_slideshow_items
        WHERE media_id = ? AND is_active = 1
        LIMIT 1
        """,
        (media_id,),
    ).fetchone()
    if selected is None:
        abort(404)

    etag = f"slideshow-{item['id']}-{item['updated_at']}-{item['size_bytes']}"
    headers = {
        "Cache-Control": "public, max-age=86400",
        "Content-Length": str(item["size_bytes"]),
        "Content-Disposition": f"inline; filename=\"{item['original_name'] or 'slideshow-media'}\"",
    }
    if request.if_none_match.contains(etag):
        response = Response(status=304, headers={"Cache-Control": headers["Cache-Control"]})
        response.set_etag(etag)
        return response

    response = Response(
        stream_with_context(gallery_media_bytes(media_id)),
        mimetype=item["mime_type"],
        headers=headers,
    )
    response.set_etag(etag)
    return response


@bp.get("/committee-photo/<path:filename>")
def committee_photo(filename: str):
    safe_name = secure_filename(filename)
    if safe_name != filename:
        abort(404)

    visible = get_db().execute(
        """
        SELECT users.id
        FROM committee_members
        JOIN committees ON committees.id = committee_members.committee_id
        JOIN users ON users.id = committee_members.user_id
        WHERE committees.deleted_at IS NULL
          AND users.deleted_at IS NULL
          AND users.is_active = 1
          AND users.profile_photo = ?
        LIMIT 1
        """,
        (safe_name,),
    ).fetchone()
    if visible is None:
        abort(404)
    return send_from_directory(current_app.config["PROFILE_UPLOAD_DIR"], safe_name)


@bp.route("/visitor-feedback", methods=("GET", "POST"))
def visitor_feedback():
    if request.method == "POST":
        validate_csrf()
        try:
            visitor_id = create_visitor(request.form, None)
        except ValueError as error:
            flash(str(error), "error")
            return redirect(url_for("public.visitor_feedback"))
        log_event("visitor_self_submitted", None, "visitor", visitor_id, request.form.get("full_name", ""))
        flash("Thank you. Your visitor card and feedback were received.", "success")
        return redirect(url_for("public.visitor_feedback"))

    return render_template("public/visitor_feedback.html", today=today_date())


@bp.get("/healthz")
def healthz():
    return jsonify(status="ok")
