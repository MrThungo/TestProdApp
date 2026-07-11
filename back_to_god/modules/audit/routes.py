from __future__ import annotations

from flask import Blueprint, render_template

from back_to_god.core.pagination import build_pagination, current_page
from back_to_god.core.permissions import role_required
from back_to_god.services.audit import audit_log_count, list_audit_logs


bp = Blueprint("audit", __name__, url_prefix="/audit")


@bp.get("/")
@role_required("super_admin")
def index():
    pagination = build_pagination(audit_log_count(), current_page(), 10)
    return render_template(
        "audit/index.html",
        logs=list_audit_logs(pagination["per_page"], pagination["offset"]),
        pagination=pagination,
    )
