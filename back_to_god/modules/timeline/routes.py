from __future__ import annotations

from urllib.parse import urlparse

from flask import Blueprint, abort, flash, g, jsonify, redirect, render_template, request, url_for

from back_to_god.core.db import get_db
from back_to_god.core.media import inline_disposition, media_response
from back_to_god.core.pagination import build_pagination, current_page
from back_to_god.core.permissions import login_required
from back_to_god.core.security import validate_csrf
from back_to_god.services.audit import log_event
from back_to_god.services.timeline import (
    add_comment,
    comments_for_posts,
    create_post,
    deleted_post_count,
    get_media,
    latest_visible_update,
    list_deleted_posts,
    list_posts,
    list_viewer_options,
    media_bytes,
    media_for_posts,
    my_reactions,
    post_count,
    restore_post,
    soft_delete_post,
    toggle_like,
    update_post,
    viewer_ids_for_posts,
)


bp = Blueprint("timeline", __name__, url_prefix="/timeline")


def _feed_return_base(query: str, page: int) -> str:
    args: dict[str, str | int] = {}
    if query:
        args["q"] = query
    if page > 1:
        args["page"] = page
    return url_for("timeline.index", **args)


def _safe_back_url(value: str | None) -> str:
    if not value:
        return ""
    parsed = urlparse(value)
    if parsed.scheme or parsed.netloc:
        if parsed.netloc != request.host:
            return ""
    path = parsed.path or ""
    if not path.startswith("/"):
        return ""
    query = f"?{parsed.query}" if parsed.query else ""
    fragment = f"#{parsed.fragment}" if parsed.fragment else ""
    return f"{path}{query}{fragment}"


def _feed_context(query: str, page: int = 1) -> dict:
    pagination = build_pagination(post_count(query, g.user["id"], g.user["role"]), page, 8)
    posts = list_posts(
        query,
        pagination["per_page"],
        pagination["offset"],
        current_user_id=g.user["id"],
        current_role=g.user["role"],
    )
    post_ids = [int(post["id"]) for post in posts]
    return {
        "posts": posts,
        "query": query,
        "pagination": pagination,
        "pagination_endpoint": "timeline.index",
        "timeline_return_base": _feed_return_base(query, int(pagination["page"])),
        "media_by_post": media_for_posts(post_ids),
        "comments_by_post": comments_for_posts(post_ids),
        "my_reactions": my_reactions(post_ids, g.user["id"]),
        "viewer_ids_by_post": viewer_ids_for_posts(post_ids),
        "viewer_options": list_viewer_options(g.user["id"]),
        "deleted_posts": deleted_post_count(g.user["id"], g.user["role"]),
        "latest_update": latest_visible_update(query, g.user["id"], g.user["role"]),
    }


@bp.route("/", methods=("GET", "POST"))
@login_required
def index():
    if request.method == "POST":
        validate_csrf()
        try:
            post_id = create_post(
                g.user["id"],
                request.form.get("title", ""),
                request.form.get("body", ""),
                request.form.get("event_date", ""),
                request.files.getlist("media"),
                request.form.get("visibility", "everyone"),
                request.form.getlist("viewer_ids"),
            )
        except ValueError as error:
            flash(str(error), "error")
            return redirect(url_for("timeline.index"))
        log_event("timeline_created", g.user["id"], "timeline", post_id, request.form.get("title", ""))
        flash("Timeline post shared.", "success")
        return redirect(url_for("timeline.index"))

    query = (request.args.get("q") or "").strip()
    context = _feed_context(query, current_page())
    return render_template(
        "timeline/index.html",
        **context,
    )


@bp.get("/poll")
@login_required
def poll():
    query = (request.args.get("q") or "").strip()
    page = current_page()
    since = (request.args.get("since") or "").strip()
    if " " in since and "+" not in since:
        since = since.replace(" ", "+")
    latest_update = latest_visible_update(query, g.user["id"], g.user["role"])
    if latest_update <= since or (not latest_update and not since):
        return jsonify({"ok": True, "changed": False, "latestUpdate": latest_update})
    context = _feed_context(query, page)
    return jsonify(
        {
            "ok": True,
            "changed": True,
            "latestUpdate": context["latest_update"],
            "html": render_template("timeline/_feed.html", **context),
        }
    )


@bp.get("/media/<int:media_id>")
@login_required
def media(media_id: int):
    item = get_media(media_id, g.user["id"], g.user["role"])
    if item is None:
        abort(404)
    etag = f"timeline-{item['id']}-{item['created_at']}-{item['size_bytes']}"
    return media_response(
        stream_factory=lambda: media_bytes(media_id),
        range_factory=lambda start, length: media_bytes(media_id, start, length),
        mime_type=item["mime_type"],
        size_bytes=int(item["size_bytes"]),
        cache_control="private, max-age=86400",
        content_disposition=inline_disposition(item["original_name"], "timeline-media"),
        etag=etag,
    )


@bp.get("/media/<int:media_id>/view")
@login_required
def media_view(media_id: int):
    item = get_media(media_id, g.user["id"], g.user["role"])
    if item is None:
        abort(404)
    back_url = (
        _safe_back_url(request.args.get("back"))
        or _safe_back_url(request.referrer)
        or url_for("timeline.index")
    )
    return render_template("timeline/media_view.html", item=item, back_url=back_url)


@bp.post("/<int:post_id>/edit")
@login_required
def edit(post_id: int):
    validate_csrf()
    try:
        post = update_post(
            post_id,
            g.user["id"],
            g.user["role"],
            request.form.get("title", ""),
            request.form.get("body", ""),
            request.form.get("event_date", ""),
            request.form.get("visibility", "everyone"),
            request.form.getlist("viewer_ids"),
        )
    except PermissionError:
        abort(403)
    except ValueError as error:
        flash(str(error), "error")
        return redirect(request.referrer or url_for("timeline.index"))

    if post is None:
        abort(404)
    log_event("timeline_updated", g.user["id"], "timeline", post_id, post["title"])
    flash("Timeline post updated.", "success")
    return redirect(request.referrer or url_for("timeline.index", _anchor=f"timeline-post-{post_id}"))


@bp.post("/<int:post_id>/delete")
@login_required
def delete(post_id: int):
    validate_csrf()
    try:
        post = soft_delete_post(post_id, g.user["id"], g.user["role"])
    except PermissionError:
        abort(403)
    if post is None:
        abort(404)
    log_event("timeline_deleted", g.user["id"], "timeline", post_id, post["title"])
    flash("Timeline post moved to the recycle bin.", "success")
    return redirect(request.referrer or url_for("timeline.index"))


@bp.get("/recycle-bin")
@login_required
def recycle_bin():
    pagination = build_pagination(
        deleted_post_count(g.user["id"], g.user["role"]),
        current_page(),
        10,
    )
    return render_template(
        "timeline/recycle_bin.html",
        posts=list_deleted_posts(
            g.user["id"],
            g.user["role"],
            pagination["per_page"],
            pagination["offset"],
        ),
        pagination=pagination,
        deleted_posts=deleted_post_count(g.user["id"], g.user["role"]),
    )


@bp.post("/<int:post_id>/restore")
@login_required
def restore(post_id: int):
    validate_csrf()
    try:
        post = restore_post(post_id, g.user["id"], g.user["role"])
    except PermissionError:
        abort(403)
    if post is None:
        abort(404)
    log_event("timeline_restored", g.user["id"], "timeline", post_id, post["title"])
    flash("Timeline post restored.", "success")
    return redirect(url_for("timeline.recycle_bin"))


@bp.post("/<int:post_id>/like")
@login_required
def like(post_id: int):
    validate_csrf()
    try:
        liked = toggle_like(post_id, g.user["id"], g.user["role"])
    except PermissionError:
        abort(403)
    if "application/json" in (request.headers.get("Accept") or ""):
        count_row = get_db().execute(
            "SELECT COUNT(*) AS count FROM timeline_reactions WHERE post_id = ?",
            (post_id,),
        ).fetchone()
        update_row = get_db().execute(
            "SELECT updated_at FROM timeline_posts WHERE id = ?",
            (post_id,),
        ).fetchone()
        return jsonify(
            {
                "ok": True,
                "liked": liked,
                "count": int(count_row["count"]),
                "latestUpdate": update_row["updated_at"] if update_row else "",
            }
        )
    return redirect(request.referrer or url_for("timeline.index"))


@bp.post("/<int:post_id>/comment")
@login_required
def comment(post_id: int):
    validate_csrf()
    try:
        add_comment(post_id, g.user["id"], g.user["role"], request.form.get("body", ""))
    except PermissionError:
        abort(403)
    except ValueError as error:
        flash(str(error), "error")
    return redirect(request.referrer or url_for("timeline.index"))
