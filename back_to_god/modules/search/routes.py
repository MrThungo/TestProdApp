from __future__ import annotations

from flask import Blueprint, g, render_template, request

from back_to_god.core.permissions import login_required
from back_to_god.services.live import list_recorded_sessions
from back_to_god.services.timeline import list_posts


bp = Blueprint("search", __name__, url_prefix="/search")


@bp.get("/")
@login_required
def index():
    query = (request.args.get("q") or "").strip()
    recordings = list_recorded_sessions(query, 8) if query else []
    timeline_posts = (
        list_posts(query, 12, current_user_id=g.user["id"], current_role=g.user["role"])
        if query
        else []
    )
    return render_template(
        "search/index.html",
        query=query,
        recordings=recordings,
        timeline_posts=timeline_posts,
    )
