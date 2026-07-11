from __future__ import annotations

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for

from back_to_god.core.security import today_date, validate_csrf
from back_to_god.services.audit import log_event
from back_to_god.services.visitors import create_visitor

bp = Blueprint("public", __name__)


@bp.get("/")
def landing():
    return render_template("public/landing.html")


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
