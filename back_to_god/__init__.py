from __future__ import annotations

import time

from flask import Flask, current_app, g, redirect, render_template, request, session, url_for
from werkzeug.exceptions import HTTPException

from .config import Config
from .core.db import close_db, get_db, init_db
from .core.security import csrf_token, validate_same_origin
from .constants import CAN_MANAGE_FINANCE_ROLES
from .extensions import create_model_tables, init_sqlalchemy
from .services.audit import log_event
from .services.finance import approved_visible_deposit_slip_count
from .services.messages import unread_message_count
from .services.notifications import unread_count
from .services.users import touch_presence


PRESENCE_WRITE_INTERVAL_SECONDS = 180
REMINDER_DISPATCH_INTERVAL_SECONDS = 300
HIGH_FREQUENCY_ENDPOINTS = {
    "announcements.poll",
    "gallery.media",
    "gallery.poll",
    "live.engagement",
    "live.recording_upload",
    "live.signal",
    "live.signals",
    "live.status",
    "messages.attachment",
    "messages.poll",
    "messages.presence",
    "notifications.poll",
    "profile.photo",
    "timeline.poll",
}


def create_app(config: type[Config] = Config) -> Flask:
    app = Flask(__name__, instance_path=str(config.INSTANCE_DIR), template_folder="templates")
    app.config.from_object(config)

    init_sqlalchemy(app)
    app.teardown_appcontext(close_db)
    app.jinja_env.globals["csrf_token"] = csrf_token

    register_filters(app)
    register_error_handlers(app)
    register_request_hooks(app)
    register_blueprints(app)

    with app.app_context():
        init_db()
        create_model_tables()
        from .modules.api.routes import ensure_external_notification_api_key

        ensure_external_notification_api_key()

    return app


def register_filters(app: Flask) -> None:
    from .core.formatting import age_from_dob, bits_size, chat_timestamp, pretty_date
    from .core.pagination import page_url

    app.add_template_filter(pretty_date)
    app.add_template_filter(chat_timestamp)
    app.add_template_filter(age_from_dob)
    app.add_template_filter(bits_size)
    app.jinja_env.globals["page_url"] = page_url


def register_error_handlers(app: Flask) -> None:
    error_copy = {
        400: ("Request blocked", "The app could not verify that request. Please go back and try again."),
        401: ("Sign in required", "Please sign in before opening this page."),
        403: ("Access blocked", "You do not have permission to open this page."),
        404: ("Page not found", "That page could not be found."),
        405: ("Action not available", "This page does not support that action."),
        413: ("Upload too large", "That upload is too large for this request."),
    }

    def rollback_open_sessions() -> None:
        db = g.get("db")
        if db is not None:
            try:
                db.rollback()
            except Exception:
                current_app.logger.debug("SQLite rollback failed while rendering an error page.", exc_info=True)

        sqlalchemy_session = current_app.extensions.get("sqlalchemy_session")
        if sqlalchemy_session is not None:
            try:
                sqlalchemy_session.rollback()
            except Exception:
                current_app.logger.debug("SQLAlchemy rollback failed while rendering an error page.", exc_info=True)

    def render_error_page(code: int, title: str, message: str):
        endpoint = "dashboard.index" if getattr(g, "user", None) else "public.landing"
        return (
            render_template(
                "errors/error.html",
                code=code,
                title=title,
                message=message,
                home_url=url_for(endpoint),
            ),
            code,
        )

    @app.errorhandler(HTTPException)
    def http_error(error: HTTPException):
        code = error.code or 500
        title, message = error_copy.get(
            code,
            ("Something went wrong", "The app could not complete that request."),
        )
        return render_error_page(code, title, message)

    @app.errorhandler(Exception)
    def unexpected_error(error: Exception):
        rollback_open_sessions()
        current_app.logger.exception("Unhandled exception while handling request")
        return render_error_page(500, "Something went wrong", "The app could not complete that request.")


def register_request_hooks(app: Flask) -> None:
    @app.before_request
    def load_current_user():
        if (
            request.method in {"POST", "PUT", "PATCH", "DELETE"}
            and request.endpoint != "api.send_external_notification"
        ):
            validate_same_origin()

        g.unread_notifications = 0
        g.unread_messages = 0
        g.show_finance_tab = False
        if request.endpoint == "static":
            g.user = None
            return

        user_id = session.get("user_id")
        if user_id is None:
            g.user = None
            return

        g.user = get_db().execute(
            """
            SELECT
                id, full_name, email, role, password_hash, is_active, phone, home_area, bio,
                profile_photo, must_change_password, id_number, date_of_birth,
                created_at, last_login_at, last_seen_at, deleted_at
            FROM users
            WHERE id = ? AND deleted_at IS NULL
            """,
            (user_id,),
        ).fetchone()

        if g.user is not None and not g.user["is_active"]:
            session.clear()
            g.user = None
            return

        if g.user is None:
            session.clear()
            return

        now_seconds = int(time.time())
        high_frequency_request = request.endpoint in HIGH_FREQUENCY_ENDPOINTS

        if (
            not high_frequency_request
            and now_seconds - int(session.get("last_seen_write", 0)) > PRESENCE_WRITE_INTERVAL_SECONDS
        ):
            touch_presence(g.user["id"])
            session["last_seen_write"] = now_seconds

        if (
            not high_frequency_request
            and now_seconds - int(session.get("last_announcement_reminder_check", 0)) > REMINDER_DISPATCH_INTERVAL_SECONDS
        ):
            from .services.announcements import dispatch_due_announcement_reminders

            dispatch_due_announcement_reminders()
            session["last_announcement_reminder_check"] = now_seconds

        allowed_endpoints = {
            "auth.change_password",
            "auth.logout",
            "static",
        }
        if g.user["must_change_password"] and request.endpoint not in allowed_endpoints:
            return redirect(url_for("auth.change_password"))

        if high_frequency_request:
            g.show_finance_tab = g.user["role"] in CAN_MANAGE_FINANCE_ROLES
            return

        g.unread_notifications = unread_count(g.user["id"])
        g.unread_messages = unread_message_count(g.user["id"])
        g.show_finance_tab = (
            g.user["role"] in CAN_MANAGE_FINANCE_ROLES
            or approved_visible_deposit_slip_count() > 0
        )

    @app.after_request
    def audit_request(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        camera_policy = "camera=(self)" if request.endpoint == "live.studio" else "camera=()"
        microphone_policy = (
            "microphone=(self)"
            if request.endpoint in {"live.studio", "messages.thread"}
            else "microphone=()"
        )
        response.headers.setdefault(
            "Permissions-Policy",
            f"geolocation=(), {camera_policy}, {microphone_policy}, fullscreen=(self)",
        )
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.tailwindcss.com; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data: blob:; "
            "media-src 'self' blob:; "
            "connect-src 'self'; "
            "frame-ancestors 'self'; "
            "base-uri 'self'; "
            "form-action 'self'",
        )
        if getattr(g, "user", None) is None:
            return response
        if response.status_code >= 500:
            return response
        skipped = {
            "static",
            "messages.poll",
            "messages.presence",
            "notifications.poll",
            "announcements.poll",
            "gallery.media",
            "gallery.poll",
            "timeline.poll",
            "live.engagement",
            "live.status",
            "live.recording_upload",
            "live.signals",
            "live.signal",
            "messages.attachment",
            "profile.photo",
        }
        if request.endpoint not in skipped and not request.path.startswith("/static/"):
            log_event(
                "request",
                g.user["id"],
                "endpoint",
                None,
                f"{request.method} {request.path} {response.status_code}",
            )
        return response


def register_blueprints(app: Flask) -> None:
    from .modules.announcements.routes import bp as announcements_bp
    from .modules.api.routes import bp as api_bp
    from .modules.audit.routes import bp as audit_bp
    from .modules.auth.routes import bp as auth_bp
    from .modules.committees.routes import bp as committees_bp
    from .modules.dashboard.routes import bp as dashboard_bp
    from .modules.finance.routes import bp as finance_bp
    from .modules.gallery.routes import bp as gallery_bp
    from .modules.live.routes import bp as live_bp
    from .modules.members.routes import bp as members_bp
    from .modules.messages.routes import bp as messages_bp
    from .modules.notifications.routes import bp as notifications_bp
    from .modules.profile.routes import bp as profile_bp
    from .modules.public.routes import bp as public_bp
    from .modules.search.routes import bp as search_bp
    from .modules.timeline.routes import bp as timeline_bp
    from .modules.users.routes import bp as users_bp
    from .modules.visitors.routes import bp as visitors_bp

    app.register_blueprint(public_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(announcements_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(audit_bp)
    app.register_blueprint(committees_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(finance_bp)
    app.register_blueprint(gallery_bp)
    app.register_blueprint(live_bp)
    app.register_blueprint(members_bp)
    app.register_blueprint(messages_bp)
    app.register_blueprint(notifications_bp)
    app.register_blueprint(profile_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(visitors_bp)
    app.register_blueprint(timeline_bp)
    app.register_blueprint(search_bp)
