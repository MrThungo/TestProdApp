from __future__ import annotations

import json

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)

from back_to_god.constants import CAN_GO_LIVE_ROLES
from back_to_god.core.media import inline_disposition, media_response
from back_to_god.core.pagination import build_pagination, current_page
from back_to_god.core.permissions import can_go_live, login_required
from back_to_god.core.security import validate_csrf
from back_to_god.services.audit import log_event
from back_to_god.services.live import (
    active_viewer_count,
    add_live_comment,
    add_signal,
    end_live_session,
    get_live_session,
    get_live_session_basic,
    get_recording_meta,
    list_live_comments,
    list_active_sessions,
    list_recorded_sessions,
    list_recent_sessions,
    recorded_session_count,
    list_signals_for_streamer,
    list_signals_for_viewer,
    reaction_counts,
    record_live_viewer,
    recording_bytes,
    save_live_recording,
    set_live_reaction,
    soft_delete_recording,
    start_live_session,
    user_reaction,
)


bp = Blueprint("live", __name__, url_prefix="/live")


def _can_manage_session(session) -> bool:
    if g.user is None:
        return False
    return g.user["id"] == session["started_by"] or g.user["role"] in {"super_admin", "admin"}


def _ice_servers() -> list[dict]:
    servers: list[dict] = []
    stun_urls = [
        value.strip()
        for value in str(current_app.config.get("WEBRTC_STUN_URLS", "")).split(",")
        if value.strip()
    ]
    if stun_urls:
        servers.append({"urls": stun_urls})

    turn_urls = [
        value.strip()
        for value in str(current_app.config.get("WEBRTC_TURN_URLS", "")).split(",")
        if value.strip()
    ]
    if turn_urls:
        turn_server = {"urls": turn_urls}
        username = str(current_app.config.get("WEBRTC_TURN_USERNAME", "")).strip()
        credential = str(current_app.config.get("WEBRTC_TURN_CREDENTIAL", "")).strip()
        if username and credential:
            turn_server["username"] = username
            turn_server["credential"] = credential
        servers.append(turn_server)
    return servers or [{"urls": ["stun:stun.l.google.com:19302"]}]


def _recording_filename(live_id: int, session) -> str:
    title = "".join(
        character.lower() if character.isalnum() else "-"
        for character in str(session["title"] or f"live-{live_id}")
    ).strip("-")
    compact_title = "-".join(part for part in title.split("-") if part)[:80] or f"live-{live_id}"
    return f"back-to-god-{compact_title}-{live_id}.webm"


def _signal_rows(rows) -> list[dict]:
    return [
        {
            "id": row["id"],
            "viewerToken": row["viewer_token"],
            "senderRole": row["sender_role"],
            "type": row["signal_type"],
            "payload": json.loads(row["payload"]),
        }
        for row in rows
    ]


def _comment_rows(rows) -> list[dict]:
    return [
        {
            "id": row["id"],
            "body": row["body"],
            "userId": row["user_id"],
            "name": row["full_name"],
            "createdAt": row["created_at"],
        }
        for row in rows
    ]


@bp.get("/")
@login_required
def index():
    active_sessions = list_active_sessions()
    recent_sessions = list_recent_sessions()
    live_ids = {int(row["id"]) for row in active_sessions + recent_sessions}
    return render_template(
        "live/index.html",
        active_sessions=active_sessions,
        recent_sessions=recent_sessions,
        viewer_counts={live_id: active_viewer_count(live_id) for live_id in live_ids},
        can_start_live=can_go_live(),
    )


@bp.get("/recordings")
@login_required
def recordings():
    query = (request.args.get("q") or "").strip()
    pagination = build_pagination(recorded_session_count(query), current_page(), 9)
    return render_template(
        "live/recordings.html",
        recordings=list_recorded_sessions(query, pagination["per_page"], pagination["offset"]),
        query=query,
        pagination=pagination,
    )


@bp.post("/start")
@login_required
def start():
    validate_csrf()
    if not can_go_live():
        abort(403)

    title = request.form.get("title", "").strip() or "Back to God live"
    description = request.form.get("description", "").strip()
    live_id = start_live_session(title, description, g.user["id"])
    log_event("live_started", g.user["id"], "live", live_id, title)
    flash("Live session started. Members have been notified.", "success")
    return redirect(url_for("live.studio", live_id=live_id))


@bp.get("/<int:live_id>")
@login_required
def watch(live_id: int):
    session = get_live_session(live_id)
    if session is None:
        abort(404)
    return render_template(
        "live/watch.html",
        live=session,
        can_manage_session=_can_manage_session(session),
        comments=list_live_comments(live_id, 0, 30),
        reactions=reaction_counts(live_id),
        my_reaction=user_reaction(live_id, g.user["id"]),
        viewer_count=active_viewer_count(live_id),
        ice_servers=_ice_servers(),
    )


@bp.get("/<int:live_id>/studio")
@login_required
def studio(live_id: int):
    session = get_live_session(live_id)
    if session is None:
        abort(404)
    if not can_go_live() or not _can_manage_session(session):
        abort(403)
    return render_template(
        "live/studio.html",
        live=session,
        comments=list_live_comments(live_id, 0, 30),
        reactions=reaction_counts(live_id),
        viewer_count=active_viewer_count(live_id),
        ice_servers=_ice_servers(),
    )


@bp.post("/<int:live_id>/end")
@login_required
def end(live_id: int):
    validate_csrf()
    session = get_live_session_basic(live_id)
    if session is None:
        abort(404)
    if not _can_manage_session(session):
        abort(403)

    end_live_session(live_id)
    log_event("live_ended", g.user["id"], "live", live_id, session["title"])
    flash("Live session ended.", "success")
    return redirect(url_for("live.index"))


@bp.post("/<int:live_id>/recording-upload")
@login_required
def recording_upload(live_id: int):
    validate_csrf()
    session = get_live_session_basic(live_id)
    if session is None:
        abort(404)
    if not _can_manage_session(session):
        abort(403)

    recording_file = request.files.get("video_recording")
    if recording_file is None:
        return jsonify({"ok": False, "error": "No recording was uploaded."}), 400

    try:
        recording_id = save_live_recording(
            live_id,
            recording_file.mimetype or "video/webm",
            recording_file.read(),
        )
    except ValueError as error:
        return jsonify({"ok": False, "error": str(error)}), 400

    return jsonify({"ok": True, "id": recording_id})


@bp.get("/<int:live_id>/recording")
@login_required
def recording(live_id: int):
    session = get_live_session(live_id)
    if session is None:
        abort(404)

    meta = get_recording_meta(live_id)
    if meta is None or not meta["recording_count"]:
        abort(404)

    etag = f"live-recording-{live_id}-{meta['updated_at']}-{meta['total_bytes']}"
    return media_response(
        stream_factory=lambda: recording_bytes(live_id),
        range_factory=lambda start, length: recording_bytes(live_id, start, length),
        mime_type=meta["mime_type"] or "video/webm",
        size_bytes=int(meta["total_bytes"]),
        cache_control="private, max-age=86400",
        content_disposition=inline_disposition(f"back-to-god-live-{live_id}.webm", "live-recording.webm"),
        etag=etag,
    )


@bp.get("/<int:live_id>/recording/download")
@login_required
def recording_download(live_id: int):
    session = get_live_session(live_id)
    if session is None:
        abort(404)

    meta = get_recording_meta(live_id)
    if meta is None or not meta["recording_count"]:
        abort(404)

    etag = f"live-recording-download-{live_id}-{meta['updated_at']}-{meta['total_bytes']}"
    return media_response(
        stream_factory=lambda: recording_bytes(live_id),
        range_factory=lambda start, length: recording_bytes(live_id, start, length),
        mime_type=meta["mime_type"] or "video/webm",
        size_bytes=int(meta["total_bytes"]),
        cache_control="private, max-age=86400",
        content_disposition=f'attachment; filename="{_recording_filename(live_id, session)}"',
        etag=etag,
    )


@bp.get("/<int:live_id>/recording/view")
@login_required
def recording_view(live_id: int):
    session = get_live_session(live_id)
    if session is None:
        abort(404)
    meta = get_recording_meta(live_id)
    if meta is None or not meta["recording_count"]:
        abort(404)
    return render_template(
        "live/recording_view.html",
        live=session,
        meta=meta,
        can_manage_session=_can_manage_session(session),
        back_url=request.args.get("back") or request.referrer or url_for("live.recordings"),
    )


@bp.post("/<int:live_id>/recording/delete")
@login_required
def delete_recording(live_id: int):
    validate_csrf()
    session = get_live_session_basic(live_id)
    if session is None:
        abort(404)
    if not _can_manage_session(session):
        abort(403)
    soft_delete_recording(live_id, g.user["id"])
    log_event("live_recording_deleted", g.user["id"], "live", live_id, session["title"])
    flash("Saved live recording moved out of view.", "success")
    return redirect(url_for("live.recordings"))


@bp.post("/<int:live_id>/comment")
@login_required
def comment(live_id: int):
    validate_csrf()
    session = get_live_session_basic(live_id)
    if session is None:
        abort(404)

    data = request.get_json(silent=True) or {}
    body = (request.form.get("body") or data.get("body") or "").strip()
    try:
        comment_id = add_live_comment(live_id, g.user["id"], body)
    except ValueError as error:
        return jsonify({"ok": False, "error": str(error)}), 400

    rows = list_live_comments(live_id, comment_id - 1, 1)
    return jsonify({"ok": True, "comments": _comment_rows(rows)})


@bp.post("/<int:live_id>/react")
@login_required
def react(live_id: int):
    validate_csrf()
    session = get_live_session_basic(live_id)
    if session is None:
        abort(404)

    data = request.get_json(silent=True) or {}
    reaction_type = (request.form.get("reaction_type") or data.get("reactionType") or "").strip()
    try:
        set_live_reaction(live_id, g.user["id"], reaction_type)
    except ValueError as error:
        return jsonify({"ok": False, "error": str(error)}), 400

    return jsonify(
        {
            "ok": True,
            "reactions": reaction_counts(live_id),
            "myReaction": user_reaction(live_id, g.user["id"]),
        }
    )


@bp.get("/<int:live_id>/engagement")
@login_required
def engagement(live_id: int):
    session = get_live_session_basic(live_id)
    if session is None:
        abort(404)
    after_id = request.args.get("after", "0", type=int) or 0
    return jsonify(
        {
            "ok": True,
            "comments": _comment_rows(list_live_comments(live_id, after_id, 50)),
            "reactions": reaction_counts(live_id),
            "myReaction": user_reaction(live_id, g.user["id"]),
            "viewerCount": active_viewer_count(live_id),
        }
    )


@bp.post("/<int:live_id>/viewer-heartbeat")
@login_required
def viewer_heartbeat(live_id: int):
    validate_csrf()
    session = get_live_session_basic(live_id)
    if session is None:
        abort(404)
    if session["status"] != "active":
        return jsonify({"ok": False, "ended": True, "viewerCount": 0}), 409

    data = request.get_json(silent=True) or {}
    try:
        viewer_count = record_live_viewer(
            live_id,
            g.user["id"],
            str(data.get("viewerToken") or ""),
            str(data.get("connectionState") or "connecting"),
        )
    except ValueError as error:
        return jsonify({"ok": False, "error": str(error)}), 400
    return jsonify({"ok": True, "viewerCount": viewer_count})


@bp.post("/<int:live_id>/signal")
@login_required
def signal(live_id: int):
    validate_csrf()
    session = get_live_session_basic(live_id)
    if session is None:
        abort(404)
    if session["status"] != "active":
        return jsonify({"ok": False, "error": "This live session has ended."}), 409

    data = request.get_json(silent=True) or {}
    viewer_token = (data.get("viewerToken") or "").strip()
    signal_type = (data.get("type") or "").strip()
    payload = data.get("payload")
    sender_role = "streamer" if _can_manage_session(session) and data.get("senderRole") == "streamer" else "viewer"

    if not viewer_token or signal_type not in {"offer", "answer", "ice"} or payload is None:
        return jsonify({"ok": False, "error": "Invalid live signal."}), 400
    if sender_role == "streamer" and g.user["role"] not in CAN_GO_LIVE_ROLES:
        abort(403)

    try:
        signal_id = add_signal(live_id, viewer_token, sender_role, signal_type, payload)
    except ValueError as error:
        return jsonify({"ok": False, "error": str(error)}), 400

    return jsonify({"ok": True, "id": signal_id})


@bp.get("/<int:live_id>/signals")
@login_required
def signals(live_id: int):
    session = get_live_session_basic(live_id)
    if session is None:
        abort(404)

    after_id = request.args.get("after", "0", type=int) or 0
    viewer_token = (request.args.get("viewerToken") or "").strip()
    requested_role = request.args.get("role")

    if requested_role == "streamer" and _can_manage_session(session):
        rows = list_signals_for_streamer(live_id, after_id)
    elif viewer_token:
        rows = list_signals_for_viewer(live_id, viewer_token, after_id)
    else:
        return jsonify({"ok": False, "error": "Missing viewer token."}), 400

    return jsonify(
        {
            "ok": True,
            "active": session["status"] == "active",
            "signals": _signal_rows(rows),
            "viewerCount": active_viewer_count(live_id),
        }
    )


@bp.get("/<int:live_id>/status")
@login_required
def status(live_id: int):
    session = get_live_session_basic(live_id)
    if session is None:
        abort(404)
    meta = get_recording_meta(live_id) if session["status"] == "ended" else None
    return jsonify(
        {
            "ok": True,
            "status": session["status"],
            "ended": session["status"] == "ended",
            "endedAt": session["ended_at"],
            "viewerCount": active_viewer_count(live_id) if session["status"] == "active" else 0,
            "recordingUrl": url_for("live.recording", live_id=live_id)
            if meta is not None and meta["recording_count"]
            else "",
        }
    )
