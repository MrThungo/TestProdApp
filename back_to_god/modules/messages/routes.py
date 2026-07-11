from __future__ import annotations

from flask import Blueprint, Response, abort, g, jsonify, redirect, render_template, request, url_for

from back_to_god.core.permissions import login_required
from back_to_god.core.security import validate_csrf
from back_to_god.services.messages import (
    delete_attachment_for_user,
    delete_message,
    edit_message,
    get_attachment_for_user,
    last_message_by_user,
    list_thread_changes,
    list_thread,
    presence_state,
    send_message,
    unread_by_sender,
)
from back_to_god.services.users import get_user_by_id, list_messageable_users, touch_presence


bp = Blueprint("messages", __name__, url_prefix="/messages")


def _message_payload(row) -> dict:
    attachment_id = row["attachment_id"] if "attachment_id" in row.keys() else None
    updated_at = row["updated_at"] if "updated_at" in row.keys() and row["updated_at"] else row["created_at"]
    deleted_at = row["deleted_at"] if "deleted_at" in row.keys() else None
    edited_at = row["edited_at"] if "edited_at" in row.keys() else None
    return {
        "id": row["id"],
        "body": row["body"],
        "senderId": row["sender_id"],
        "recipientId": row["recipient_id"],
        "senderName": row["sender_name"],
        "createdAt": row["created_at"],
        "updatedAt": updated_at,
        "editedAt": edited_at,
        "deletedAt": deleted_at,
        "timeLabel": _chat_time(row["created_at"]),
        "mine": row["sender_id"] == g.user["id"],
        "editUrl": url_for("messages.edit", message_id=row["id"]),
        "deleteUrl": url_for("messages.delete", message_id=row["id"]),
        "attachment": {
            "id": attachment_id,
            "kind": row["media_kind"],
            "mimeType": row["mime_type"],
            "sizeBytes": row["size_bytes"],
            "url": url_for("messages.attachment", attachment_id=attachment_id),
            "viewUrl": url_for("messages.attachment_view", attachment_id=attachment_id),
            "deleteUrl": url_for("messages.delete_attachment", attachment_id=attachment_id),
        }
        if attachment_id and not deleted_at
        else None,
    }


def _chat_time(value: str | None) -> str:
    from back_to_god.core.formatting import chat_timestamp

    return chat_timestamp(value)


def _uploaded_file(name: str):
    file = request.files.get(name)
    return file if file and file.filename else None


@bp.get("/")
@login_required
def index():
    last_messages = last_message_by_user(g.user["id"])
    users = sorted(
        list_messageable_users(g.user["id"]),
        key=lambda user: last_messages.get(user["id"])["created_at"]
        if last_messages.get(user["id"])
        else "",
        reverse=True,
    )
    return render_template(
        "messages/index.html",
        users=users,
        unread_counts=unread_by_sender(g.user["id"]),
        last_messages=last_messages,
        presence_state=presence_state,
    )


@bp.get("/<int:user_id>")
@login_required
def thread(user_id: int):
    other_user = get_user_by_id(user_id)
    if other_user is None or other_user["deleted_at"] is not None or not other_user["is_active"]:
        abort(404)
    messages = list_thread(g.user["id"], user_id)
    return render_template(
        "messages/thread.html",
        other_user=other_user,
        messages=messages,
        presence=presence_state(other_user["last_seen_at"]),
    )


@bp.post("/<int:user_id>/send")
@login_required
def send(user_id: int):
    validate_csrf()
    other_user = get_user_by_id(user_id)
    if other_user is None or other_user["deleted_at"] is not None or not other_user["is_active"]:
        abort(404)
    data = request.get_json(silent=True) or {}
    body = (request.form.get("body") or data.get("body") or "").strip()
    media_file = None
    media_kind = None
    for field, kind in (
        ("image", "image"),
        ("voice_note", "voice"),
        ("video", "video"),
        ("attachment", "file"),
    ):
        candidate = _uploaded_file(field)
        if candidate is not None:
            media_file = candidate
            media_kind = kind
            break

    try:
        message_id = send_message(g.user["id"], user_id, body, media_file, media_kind)
    except ValueError as error:
        return jsonify({"ok": False, "error": str(error)}), 400

    rows = list_thread(g.user["id"], user_id, message_id - 1)
    return jsonify({"ok": True, "messages": [_message_payload(row) for row in rows]})


@bp.get("/<int:user_id>/poll")
@login_required
def poll(user_id: int):
    other_user = get_user_by_id(user_id)
    if other_user is None:
        abort(404)
    after_id = request.args.get("after", "0", type=int) or 0
    since = (request.args.get("since") or "").strip()
    rows = list_thread(g.user["id"], user_id, after_id)
    changed_rows = list_thread_changes(g.user["id"], user_id, since, after_id)
    return jsonify(
        {
            "ok": True,
            "messages": [_message_payload(row) for row in rows],
            "changedMessages": [_message_payload(row) for row in changed_rows],
            "presence": presence_state(other_user["last_seen_at"]),
        }
    )


@bp.post("/message/<int:message_id>/edit")
@login_required
def edit(message_id: int):
    validate_csrf()
    data = request.get_json(silent=True) or {}
    body = (request.form.get("body") or data.get("body") or "").strip()
    try:
        edit_message(message_id, g.user["id"], body)
    except PermissionError:
        abort(403)
    except ValueError as error:
        return jsonify({"ok": False, "error": str(error)}), 400

    return jsonify({"ok": True})


@bp.post("/message/<int:message_id>/delete")
@login_required
def delete(message_id: int):
    validate_csrf()
    try:
        delete_message(message_id, g.user["id"])
    except PermissionError:
        abort(403)
    return jsonify({"ok": True})


@bp.post("/presence")
@login_required
def presence():
    validate_csrf()
    touch_presence(g.user["id"])
    return jsonify({"ok": True})


@bp.get("/attachment/<int:attachment_id>")
@login_required
def attachment(attachment_id: int):
    item = get_attachment_for_user(attachment_id, g.user["id"])
    if item is None:
        abort(404)
    headers = {
        "Cache-Control": "private, max-age=86400",
        "Content-Length": str(item["size_bytes"]),
        "Content-Disposition": f"inline; filename=\"{item['original_name'] or 'message-media'}\"",
    }
    return Response(item["data"], mimetype=item["mime_type"], headers=headers)


@bp.get("/attachment/<int:attachment_id>/view")
@login_required
def attachment_view(attachment_id: int):
    item = get_attachment_for_user(attachment_id, g.user["id"])
    if item is None:
        abort(404)
    return render_template("messages/attachment.html", item=item)


@bp.post("/attachment/<int:attachment_id>/delete")
@login_required
def delete_attachment(attachment_id: int):
    validate_csrf()
    item = get_attachment_for_user(attachment_id, g.user["id"])
    if item is None:
        abort(404)
    try:
        delete_attachment_for_user(attachment_id, g.user["id"])
    except PermissionError:
        abort(403)
    if "application/json" in (request.headers.get("Accept") or ""):
        return jsonify({"ok": True})
    thread_user_id = item["recipient_id"] if item["sender_id"] == g.user["id"] else item["sender_id"]
    return redirect(url_for("messages.thread", user_id=thread_user_id))
