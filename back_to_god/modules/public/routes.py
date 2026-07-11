from __future__ import annotations

from flask import Blueprint, jsonify, render_template


bp = Blueprint("public", __name__)


@bp.get("/")
def landing():
    return render_template("public/landing.html")


@bp.get("/healthz")
def healthz():
    return jsonify(status="ok")
