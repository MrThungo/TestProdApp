from __future__ import annotations

from flask import Blueprint, Response, abort, flash, g, jsonify, redirect, render_template, request, stream_with_context, url_for

from back_to_god.core.pagination import build_pagination, current_page
from back_to_god.core.permissions import login_required
from back_to_god.core.security import validate_csrf
from back_to_god.services.audit import log_event
from back_to_god.services.gallery import (
    can_manage_gallery,
    create_gallery_media,
    gallery_media_bytes,
    gallery_media_count,
    get_gallery_media,
    latest_gallery_update,
    list_categories,
    list_gallery_category_groups,
    list_gallery_media,
    soft_delete_gallery_media,
)


bp = Blueprint("gallery", __name__, url_prefix="/gallery")


def _can_manage_gallery() -> bool:
    return g.user is not None and can_manage_gallery(g.user["role"])


def _gallery_return_base(query: str, media_kind: str, category_id: int, page: int) -> str:
    args: dict[str, str | int] = {}
    if query:
        args["q"] = query
    if media_kind:
        args["kind"] = media_kind
    if category_id:
        args["category"] = category_id
    if page > 1:
        args["page"] = page
    return url_for("gallery.index", **args)


@bp.route("/", methods=("GET", "POST"))
@login_required
def index():
    if request.method == "POST":
        if not _can_manage_gallery():
            abort(403)
        validate_csrf()
        try:
            media_ids = create_gallery_media(
                request.form.get("title", ""),
                request.form.get("description", ""),
                request.form.get("category_name", ""),
                request.form.get("event_at", ""),
                request.files.getlist("media"),
                g.user["id"],
            )
        except ValueError as error:
            flash(str(error), "error")
            return redirect(url_for("gallery.index"))
        log_event(
            "gallery_media_uploaded",
            g.user["id"],
            "gallery",
            media_ids[0] if media_ids else None,
            request.form.get("title", ""),
        )
        flash("Gallery media uploaded.", "success")
        return redirect(url_for("gallery.index", _anchor=f"gallery-media-{media_ids[0]}"))

    query = (request.args.get("q") or "").strip()
    media_kind = (request.args.get("kind") or "").strip()
    if media_kind not in {"image", "video"}:
        media_kind = ""
    category_id = request.args.get("category", "0", type=int) or 0
    categories = list_categories()
    if category_id not in {int(category["id"]) for category in categories}:
        category_id = 0

    pagination = build_pagination(
        gallery_media_count(query, media_kind, category_id),
        current_page(),
        18,
    )
    return render_template(
        "gallery/index.html",
        media_items=list_gallery_media(
            query,
            media_kind,
            category_id,
            pagination["per_page"],
            pagination["offset"],
        ),
        gallery_groups=list_gallery_category_groups(query, media_kind),
        categories=categories,
        query=query,
        media_kind=media_kind,
        category_id=category_id,
        can_manage_gallery=_can_manage_gallery(),
        pagination=pagination,
        latest_update=latest_gallery_update(),
        gallery_return_base=_gallery_return_base(
            query,
            media_kind,
            category_id,
            int(pagination["page"]),
        ),
    )


@bp.get("/poll")
@login_required
def poll():
    query = (request.args.get("q") or "").strip()
    media_kind = (request.args.get("kind") or "").strip()
    if media_kind not in {"image", "video"}:
        media_kind = ""
    category_id = request.args.get("category", "0", type=int) or 0
    categories = list_categories()
    if category_id not in {int(category["id"]) for category in categories}:
        category_id = 0
    since = (request.args.get("since") or "").strip()
    latest_update = latest_gallery_update()
    if latest_update == since:
        return jsonify({"ok": True, "changed": False, "latestUpdate": latest_update})

    pagination = build_pagination(
        gallery_media_count(query, media_kind, category_id),
        current_page(),
        18,
    )
    return jsonify(
        {
            "ok": True,
            "changed": True,
            "latestUpdate": latest_update,
            "html": render_template(
                "gallery/_grid.html",
                media_items=list_gallery_media(
                    query,
                    media_kind,
                    category_id,
                    pagination["per_page"],
                    pagination["offset"],
                ),
                gallery_groups=list_gallery_category_groups(query, media_kind),
                categories=categories,
                query=query,
                media_kind=media_kind,
                category_id=category_id,
                pagination=pagination,
                latest_update=latest_update,
                gallery_return_base=_gallery_return_base(query, media_kind, category_id, int(pagination["page"])),
            ),
        }
    )


@bp.get("/media/<int:media_id>")
@login_required
def media(media_id: int):
    item = get_gallery_media(media_id)
    if item is None:
        abort(404)
    headers = {
        "Cache-Control": "private, max-age=86400",
        "Content-Length": str(item["size_bytes"]),
        "Content-Disposition": f"inline; filename=\"{item['original_name'] or 'gallery-media'}\"",
    }
    return Response(
        stream_with_context(gallery_media_bytes(media_id)),
        mimetype=item["mime_type"],
        headers=headers,
    )


@bp.get("/media/<int:media_id>/view")
@login_required
def media_view(media_id: int):
    item = get_gallery_media(media_id)
    if item is None:
        abort(404)
    return render_template(
        "gallery/media_view.html",
        item=item,
        back_url=request.args.get("back") or request.referrer or url_for("gallery.index"),
        can_manage_gallery=_can_manage_gallery(),
    )


@bp.post("/media/<int:media_id>/delete")
@login_required
def delete_media(media_id: int):
    if not _can_manage_gallery():
        abort(403)
    validate_csrf()
    item = soft_delete_gallery_media(media_id, g.user["id"])
    if item is None:
        abort(404)
    log_event("gallery_media_deleted", g.user["id"], "gallery", media_id, item["title"])
    flash("Gallery media removed.", "success")
    return redirect(url_for("gallery.index"))
