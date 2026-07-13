from __future__ import annotations

import sqlite3

from flask import current_app, g
from werkzeug.security import generate_password_hash

from .security import generate_password, utc_now

SQLITE_BUSY_TIMEOUT_MS = 30000


def configure_connection(db: sqlite3.Connection, *, enable_wal: bool = False) -> None:
    db.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
    db.execute("PRAGMA foreign_keys = ON")
    db.execute("PRAGMA synchronous = NORMAL")
    db.execute("PRAGMA temp_store = MEMORY")
    db.execute("PRAGMA cache_size = -32768")
    db.execute("PRAGMA mmap_size = 268435456")
    if enable_wal:
        db.execute("PRAGMA journal_mode = WAL")


def connect_database(*, enable_wal: bool = False) -> sqlite3.Connection:
    connection = sqlite3.connect(
        current_app.config["DATABASE"],
        timeout=SQLITE_BUSY_TIMEOUT_MS / 1000,
    )
    connection.row_factory = sqlite3.Row
    configure_connection(connection, enable_wal=enable_wal)
    return connection


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = connect_database(enable_wal=True)
    return g.db


def close_db(error: Exception | None = None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db() -> None:
    current_app.config["INSTANCE_DIR"].mkdir(parents=True, exist_ok=True)
    db = get_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            role TEXT NOT NULL CHECK (role IN ('super_admin', 'admin', 'pastor', 'usher', 'videographer', 'treasurer', 'member')),
            password_hash TEXT NOT NULL,
            must_change_password INTEGER NOT NULL DEFAULT 1,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_by INTEGER,
            identity_type TEXT NOT NULL DEFAULT 'sa_id',
            phone TEXT,
            id_number TEXT,
            foreign_id_number TEXT,
            nationality TEXT,
            date_of_birth TEXT,
            home_area TEXT,
            bio TEXT,
            emergency_contact_name TEXT,
            emergency_contact_phone TEXT,
            emergency_contact_relationship TEXT,
            profile_photo TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            last_login_at TEXT,
            last_seen_at TEXT,
            deleted_at TEXT,
            deleted_by INTEGER,
            FOREIGN KEY (created_by) REFERENCES users (id)
        );

        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            token_hash TEXT NOT NULL UNIQUE,
            expires_at TEXT NOT NULL,
            used_at TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        );

        CREATE TABLE IF NOT EXISTS visitors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            phone TEXT,
            email TEXT,
            identity_type TEXT NOT NULL DEFAULT 'sa_id',
            id_number TEXT,
            foreign_id_number TEXT,
            nationality TEXT,
            date_of_birth TEXT,
            visit_date TEXT NOT NULL,
            visit_type TEXT NOT NULL,
            age_group TEXT NOT NULL,
            invited_by TEXT,
            home_area TEXT,
            prayer_request TEXT,
            notes TEXT,
            service_rating TEXT,
            service_feedback TEXT,
            consent_to_contact INTEGER NOT NULL DEFAULT 1,
            follow_up_status TEXT NOT NULL DEFAULT 'new'
                CHECK (follow_up_status IN ('new', 'follow_up', 'connected', 'not_reached')),
            follow_up_requested INTEGER NOT NULL DEFAULT 0,
            follow_up_made_at TEXT,
            follow_up_made_by INTEGER,
            follow_up_notes TEXT,
            membership_requested INTEGER NOT NULL DEFAULT 0,
            membership_status TEXT NOT NULL DEFAULT 'none'
                CHECK (membership_status IN ('none', 'pending', 'approved', 'declined')),
            membership_requested_at TEXT,
            membership_reviewed_at TEXT,
            membership_reviewed_by INTEGER,
            member_user_id INTEGER,
            membership_notes TEXT,
            captured_by INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (captured_by) REFERENCES users (id),
            FOREIGN KEY (follow_up_made_by) REFERENCES users (id),
            FOREIGN KEY (membership_reviewed_by) REFERENCES users (id),
            FOREIGN KEY (member_user_id) REFERENCES users (id)
        );

        CREATE TABLE IF NOT EXISTS live_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            status TEXT NOT NULL DEFAULT 'active'
                CHECK (status IN ('active', 'ended')),
            started_by INTEGER NOT NULL,
            started_at TEXT NOT NULL,
            ended_at TEXT,
            recording_deleted_at TEXT,
            recording_deleted_by INTEGER,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (started_by) REFERENCES users (id),
            FOREIGN KEY (recording_deleted_by) REFERENCES users (id)
        );

        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            target_url TEXT,
            category TEXT NOT NULL DEFAULT 'general',
            is_read INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        );

        CREATE TABLE IF NOT EXISTS announcements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            event_at TEXT,
            reminder_at TEXT,
            reminder_sent_at TEXT,
            is_pinned INTEGER NOT NULL DEFAULT 0,
            created_by INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            deleted_at TEXT,
            deleted_by INTEGER,
            FOREIGN KEY (created_by) REFERENCES users (id),
            FOREIGN KEY (deleted_by) REFERENCES users (id)
        );

        CREATE TABLE IF NOT EXISTS gallery_categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS gallery_media (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            event_at TEXT,
            media_kind TEXT NOT NULL CHECK (media_kind IN ('image', 'video')),
            mime_type TEXT NOT NULL,
            original_name TEXT,
            size_bytes INTEGER NOT NULL,
            data BLOB NOT NULL,
            uploaded_by INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            deleted_at TEXT,
            deleted_by INTEGER,
            FOREIGN KEY (category_id) REFERENCES gallery_categories (id),
            FOREIGN KEY (uploaded_by) REFERENCES users (id),
            FOREIGN KEY (deleted_by) REFERENCES users (id)
        );

        CREATE TABLE IF NOT EXISTS gallery_slideshow_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            media_id INTEGER NOT NULL UNIQUE,
            caption TEXT,
            sort_order INTEGER NOT NULL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 1,
            added_by INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (media_id) REFERENCES gallery_media (id),
            FOREIGN KEY (added_by) REFERENCES users (id)
        );

        CREATE TABLE IF NOT EXISTS committees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            created_by INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            deleted_at TEXT,
            deleted_by INTEGER,
            FOREIGN KEY (created_by) REFERENCES users (id),
            FOREIGN KEY (deleted_by) REFERENCES users (id)
        );

        CREATE TABLE IF NOT EXISTS committee_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            committee_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            title TEXT,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE (committee_id, user_id),
            FOREIGN KEY (committee_id) REFERENCES committees (id),
            FOREIGN KEY (user_id) REFERENCES users (id)
        );

        CREATE TABLE IF NOT EXISTS webrtc_signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            live_session_id INTEGER NOT NULL,
            viewer_token TEXT NOT NULL,
            sender_role TEXT NOT NULL CHECK (sender_role IN ('viewer', 'streamer')),
            signal_type TEXT NOT NULL CHECK (signal_type IN ('offer', 'answer', 'ice')),
            payload TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (live_session_id) REFERENCES live_sessions (id)
        );

        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id INTEGER NOT NULL,
            recipient_id INTEGER NOT NULL,
            body TEXT NOT NULL,
            is_read INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT,
            edited_at TEXT,
            deleted_at TEXT,
            deleted_by INTEGER,
            FOREIGN KEY (sender_id) REFERENCES users (id),
            FOREIGN KEY (recipient_id) REFERENCES users (id),
            FOREIGN KEY (deleted_by) REFERENCES users (id)
        );

        CREATE TABLE IF NOT EXISTS message_attachments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id INTEGER NOT NULL,
            media_kind TEXT NOT NULL CHECK (media_kind IN ('image', 'voice', 'video', 'file')),
            mime_type TEXT NOT NULL,
            original_name TEXT,
            size_bytes INTEGER NOT NULL,
            data BLOB NOT NULL,
            created_at TEXT NOT NULL,
            deleted_at TEXT,
            deleted_by INTEGER,
            FOREIGN KEY (message_id) REFERENCES messages (id),
            FOREIGN KEY (deleted_by) REFERENCES users (id)
        );

        CREATE TABLE IF NOT EXISTS live_recordings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            live_session_id INTEGER NOT NULL UNIQUE,
            mime_type TEXT NOT NULL,
            size_bytes INTEGER NOT NULL,
            data BLOB NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            deleted_at TEXT,
            deleted_by INTEGER,
            FOREIGN KEY (live_session_id) REFERENCES live_sessions (id),
            FOREIGN KEY (deleted_by) REFERENCES users (id)
        );

        CREATE TABLE IF NOT EXISTS live_comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            live_session_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            body TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (live_session_id) REFERENCES live_sessions (id),
            FOREIGN KEY (user_id) REFERENCES users (id)
        );

        CREATE TABLE IF NOT EXISTS live_reactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            live_session_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            reaction_type TEXT NOT NULL CHECK (reaction_type IN ('like', 'heart', 'amen', 'clap', 'fire')),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE (live_session_id, user_id),
            FOREIGN KEY (live_session_id) REFERENCES live_sessions (id),
            FOREIGN KEY (user_id) REFERENCES users (id)
        );

        CREATE TABLE IF NOT EXISTS timeline_posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            author_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            body TEXT,
            event_date TEXT,
            visibility TEXT NOT NULL DEFAULT 'everyone'
                CHECK (visibility IN ('everyone', 'specific')),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            deleted_at TEXT,
            deleted_by INTEGER,
            FOREIGN KEY (author_id) REFERENCES users (id),
            FOREIGN KEY (deleted_by) REFERENCES users (id)
        );

        CREATE TABLE IF NOT EXISTS timeline_post_viewers (
            post_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (post_id, user_id),
            FOREIGN KEY (post_id) REFERENCES timeline_posts (id),
            FOREIGN KEY (user_id) REFERENCES users (id)
        );

        CREATE TABLE IF NOT EXISTS timeline_media (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER NOT NULL,
            media_kind TEXT NOT NULL CHECK (media_kind IN ('image', 'video')),
            mime_type TEXT NOT NULL,
            original_name TEXT,
            size_bytes INTEGER NOT NULL,
            data BLOB NOT NULL,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY (post_id) REFERENCES timeline_posts (id)
        );

        CREATE TABLE IF NOT EXISTS timeline_comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            body TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (post_id) REFERENCES timeline_posts (id),
            FOREIGN KEY (user_id) REFERENCES users (id)
        );

        CREATE TABLE IF NOT EXISTS timeline_reactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            reaction_type TEXT NOT NULL DEFAULT 'like' CHECK (reaction_type IN ('like', 'love', 'amen')),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE (post_id, user_id),
            FOREIGN KEY (post_id) REFERENCES timeline_posts (id),
            FOREIGN KEY (user_id) REFERENCES users (id)
        );

        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action TEXT NOT NULL,
            entity TEXT,
            entity_id INTEGER,
            details TEXT,
            ip_address TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        );

        CREATE TABLE IF NOT EXISTS deposit_slips (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            bank_name TEXT,
            reference TEXT,
            amount_cents INTEGER NOT NULL DEFAULT 0,
            deposit_date TEXT NOT NULL,
            is_visible INTEGER NOT NULL DEFAULT 0,
            visible_from TEXT,
            visible_until TEXT,
            approval_status TEXT NOT NULL DEFAULT 'draft'
                CHECK (approval_status IN ('draft', 'pending', 'approved', 'rejected')),
            approved_by INTEGER,
            approved_at TEXT,
            original_name TEXT NOT NULL,
            mime_type TEXT NOT NULL,
            size_bytes INTEGER NOT NULL,
            data BLOB NOT NULL,
            created_by INTEGER NOT NULL,
            deleted_at TEXT,
            deleted_by INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (created_by) REFERENCES users (id),
            FOREIGN KEY (approved_by) REFERENCES users (id),
            FOREIGN KEY (deleted_by) REFERENCES users (id)
        );

        CREATE TABLE IF NOT EXISTS finance_offerings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            offering_date TEXT NOT NULL,
            offering_type TEXT NOT NULL,
            amount_cents INTEGER NOT NULL DEFAULT 0,
            note TEXT,
            deposit_slip_id INTEGER,
            captured_by INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            deleted_at TEXT,
            deleted_by INTEGER,
            FOREIGN KEY (deposit_slip_id) REFERENCES deposit_slips (id),
            FOREIGN KEY (captured_by) REFERENCES users (id),
            FOREIGN KEY (deleted_by) REFERENCES users (id)
        );

        CREATE INDEX IF NOT EXISTS idx_live_sessions_status
            ON live_sessions (status, started_at);
        CREATE INDEX IF NOT EXISTS idx_users_active_role
            ON users (deleted_at, is_active, role, full_name);
        CREATE INDEX IF NOT EXISTS idx_users_last_seen
            ON users (deleted_at, last_seen_at);
        CREATE INDEX IF NOT EXISTS idx_notifications_user_read
            ON notifications (user_id, is_read, created_at);
        CREATE INDEX IF NOT EXISTS idx_notifications_user_category_created
            ON notifications (user_id, category, created_at);
        CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_hash
            ON password_reset_tokens (token_hash, expires_at, used_at);
        CREATE INDEX IF NOT EXISTS idx_announcements_active
            ON announcements (deleted_at, is_pinned, created_at);
        CREATE INDEX IF NOT EXISTS idx_gallery_media_category
            ON gallery_media (deleted_at, category_id, event_at, created_at);
        CREATE INDEX IF NOT EXISTS idx_gallery_media_kind_created
            ON gallery_media (deleted_at, media_kind, created_at);
        CREATE INDEX IF NOT EXISTS idx_gallery_media_updated
            ON gallery_media (deleted_at, updated_at);
        CREATE INDEX IF NOT EXISTS idx_gallery_slideshow_order
            ON gallery_slideshow_items (is_active, sort_order, id);
        CREATE INDEX IF NOT EXISTS idx_committees_active
            ON committees (deleted_at, name);
        CREATE INDEX IF NOT EXISTS idx_committee_members_committee
            ON committee_members (committee_id, sort_order, id);
        CREATE INDEX IF NOT EXISTS idx_webrtc_signals_session
            ON webrtc_signals (live_session_id, viewer_token, id);
        CREATE INDEX IF NOT EXISTS idx_messages_pair
            ON messages (sender_id, recipient_id, id);
        CREATE INDEX IF NOT EXISTS idx_messages_recipient_unread
            ON messages (recipient_id, is_read, id);
        CREATE INDEX IF NOT EXISTS idx_messages_thread_updated
            ON messages (recipient_id, sender_id, updated_at, id);
        CREATE INDEX IF NOT EXISTS idx_message_attachments_message
            ON message_attachments (message_id);
        CREATE INDEX IF NOT EXISTS idx_live_recordings_session
            ON live_recordings (live_session_id, deleted_at);
        CREATE INDEX IF NOT EXISTS idx_live_comments_session
            ON live_comments (live_session_id, id);
        CREATE INDEX IF NOT EXISTS idx_live_reactions_session
            ON live_reactions (live_session_id, reaction_type);
        CREATE INDEX IF NOT EXISTS idx_timeline_posts_created
            ON timeline_posts (deleted_at, created_at);
        CREATE INDEX IF NOT EXISTS idx_timeline_posts_visibility_created
            ON timeline_posts (deleted_at, visibility, created_at);
        CREATE INDEX IF NOT EXISTS idx_timeline_posts_event
            ON timeline_posts (event_date, created_at);
        CREATE INDEX IF NOT EXISTS idx_timeline_post_viewers_user
            ON timeline_post_viewers (user_id, post_id);
        CREATE INDEX IF NOT EXISTS idx_timeline_media_post
            ON timeline_media (post_id, sort_order);
        CREATE INDEX IF NOT EXISTS idx_timeline_comments_post
            ON timeline_comments (post_id, id);
        CREATE INDEX IF NOT EXISTS idx_timeline_reactions_post
            ON timeline_reactions (post_id, reaction_type);
        CREATE INDEX IF NOT EXISTS idx_audit_logs_created
            ON audit_logs (created_at, user_id);
        CREATE INDEX IF NOT EXISTS idx_deposit_slips_visibility
            ON deposit_slips (is_visible, visible_until, deposit_date);
        CREATE INDEX IF NOT EXISTS idx_deposit_slips_approval_visible
            ON deposit_slips (deleted_at, approval_status, is_visible, visible_until);
        CREATE INDEX IF NOT EXISTS idx_finance_offerings_date
            ON finance_offerings (deleted_at, offering_date, deposit_slip_id);
        CREATE INDEX IF NOT EXISTS idx_visitors_membership_status
            ON visitors (membership_status, membership_requested_at);
        CREATE INDEX IF NOT EXISTS idx_visitors_follow_up
            ON visitors (follow_up_status, follow_up_requested, visit_date);
        CREATE INDEX IF NOT EXISTS idx_visitors_visit_date
            ON visitors (visit_date);
        """
    )
    db.commit()
    migrate_db()
    seed_super_admin()


def migrate_db() -> None:
    db = get_db()
    existing_columns = {
        row["name"] for row in db.execute("PRAGMA table_info(users)").fetchall()
    }
    migrations = {
        "must_change_password": "ALTER TABLE users ADD COLUMN must_change_password INTEGER NOT NULL DEFAULT 0",
        "identity_type": "ALTER TABLE users ADD COLUMN identity_type TEXT NOT NULL DEFAULT 'sa_id'",
        "phone": "ALTER TABLE users ADD COLUMN phone TEXT",
        "id_number": "ALTER TABLE users ADD COLUMN id_number TEXT",
        "foreign_id_number": "ALTER TABLE users ADD COLUMN foreign_id_number TEXT",
        "nationality": "ALTER TABLE users ADD COLUMN nationality TEXT",
        "date_of_birth": "ALTER TABLE users ADD COLUMN date_of_birth TEXT",
        "home_area": "ALTER TABLE users ADD COLUMN home_area TEXT",
        "bio": "ALTER TABLE users ADD COLUMN bio TEXT",
        "emergency_contact_name": "ALTER TABLE users ADD COLUMN emergency_contact_name TEXT",
        "emergency_contact_phone": "ALTER TABLE users ADD COLUMN emergency_contact_phone TEXT",
        "emergency_contact_relationship": "ALTER TABLE users ADD COLUMN emergency_contact_relationship TEXT",
        "profile_photo": "ALTER TABLE users ADD COLUMN profile_photo TEXT",
        "last_seen_at": "ALTER TABLE users ADD COLUMN last_seen_at TEXT",
        "deleted_at": "ALTER TABLE users ADD COLUMN deleted_at TEXT",
        "deleted_by": "ALTER TABLE users ADD COLUMN deleted_by INTEGER",
    }
    for column, statement in migrations.items():
        if column not in existing_columns:
            db.execute(statement)
    _migrate_user_role_constraint(db)
    try:
        db.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_users_id_number_unique
            ON users (id_number)
            WHERE id_number IS NOT NULL AND id_number != ''
            """
        )
    except sqlite3.IntegrityError:
        pass
    try:
        db.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_users_foreign_id_unique
            ON users (foreign_id_number)
            WHERE foreign_id_number IS NOT NULL AND foreign_id_number != ''
            """
        )
    except sqlite3.IntegrityError:
        pass
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            token_hash TEXT NOT NULL UNIQUE,
            expires_at TEXT NOT NULL,
            used_at TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_hash
            ON password_reset_tokens (token_hash, expires_at, used_at)
        """
    )
    existing_visitor_columns = {
        row["name"] for row in db.execute("PRAGMA table_info(visitors)").fetchall()
    }
    visitor_migrations = {
        "identity_type": "ALTER TABLE visitors ADD COLUMN identity_type TEXT NOT NULL DEFAULT 'sa_id'",
        "id_number": "ALTER TABLE visitors ADD COLUMN id_number TEXT",
        "foreign_id_number": "ALTER TABLE visitors ADD COLUMN foreign_id_number TEXT",
        "nationality": "ALTER TABLE visitors ADD COLUMN nationality TEXT",
        "date_of_birth": "ALTER TABLE visitors ADD COLUMN date_of_birth TEXT",
        "service_rating": "ALTER TABLE visitors ADD COLUMN service_rating TEXT",
        "service_feedback": "ALTER TABLE visitors ADD COLUMN service_feedback TEXT",
        "follow_up_requested": "ALTER TABLE visitors ADD COLUMN follow_up_requested INTEGER NOT NULL DEFAULT 0",
        "follow_up_made_at": "ALTER TABLE visitors ADD COLUMN follow_up_made_at TEXT",
        "follow_up_made_by": "ALTER TABLE visitors ADD COLUMN follow_up_made_by INTEGER",
        "follow_up_notes": "ALTER TABLE visitors ADD COLUMN follow_up_notes TEXT",
        "membership_requested": "ALTER TABLE visitors ADD COLUMN membership_requested INTEGER NOT NULL DEFAULT 0",
        "membership_status": "ALTER TABLE visitors ADD COLUMN membership_status TEXT NOT NULL DEFAULT 'none'",
        "membership_requested_at": "ALTER TABLE visitors ADD COLUMN membership_requested_at TEXT",
        "membership_reviewed_at": "ALTER TABLE visitors ADD COLUMN membership_reviewed_at TEXT",
        "membership_reviewed_by": "ALTER TABLE visitors ADD COLUMN membership_reviewed_by INTEGER",
        "member_user_id": "ALTER TABLE visitors ADD COLUMN member_user_id INTEGER",
        "membership_notes": "ALTER TABLE visitors ADD COLUMN membership_notes TEXT",
    }
    for column, statement in visitor_migrations.items():
        if column not in existing_visitor_columns:
            db.execute(statement)
    if "follow_up_requested" not in existing_visitor_columns:
        db.execute(
            """
            UPDATE visitors
            SET follow_up_requested = 1
            WHERE follow_up_status = 'follow_up'
            """
        )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_visitors_membership_status
            ON visitors (membership_status, membership_requested_at)
        """
    )

    existing_live_columns = {
        row["name"] for row in db.execute("PRAGMA table_info(live_sessions)").fetchall()
    }
    live_migrations = {
        "recording_deleted_at": "ALTER TABLE live_sessions ADD COLUMN recording_deleted_at TEXT",
        "recording_deleted_by": "ALTER TABLE live_sessions ADD COLUMN recording_deleted_by INTEGER",
    }
    for column, statement in live_migrations.items():
        if column not in existing_live_columns:
            db.execute(statement)
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS live_recordings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            live_session_id INTEGER NOT NULL UNIQUE,
            mime_type TEXT NOT NULL,
            size_bytes INTEGER NOT NULL,
            data BLOB NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            deleted_at TEXT,
            deleted_by INTEGER,
            FOREIGN KEY (live_session_id) REFERENCES live_sessions (id),
            FOREIGN KEY (deleted_by) REFERENCES users (id)
        )
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_live_recordings_session
            ON live_recordings (live_session_id, deleted_at)
        """
    )
    _migrate_live_recording_chunks(db)

    existing_message_columns = {
        row["name"] for row in db.execute("PRAGMA table_info(messages)").fetchall()
    }
    message_migrations = {
        "updated_at": "ALTER TABLE messages ADD COLUMN updated_at TEXT",
        "edited_at": "ALTER TABLE messages ADD COLUMN edited_at TEXT",
        "deleted_at": "ALTER TABLE messages ADD COLUMN deleted_at TEXT",
        "deleted_by": "ALTER TABLE messages ADD COLUMN deleted_by INTEGER",
    }
    for column, statement in message_migrations.items():
        if column not in existing_message_columns:
            db.execute(statement)

    existing_attachment_columns = {
        row["name"] for row in db.execute("PRAGMA table_info(message_attachments)").fetchall()
    }
    attachment_migrations = {
        "deleted_at": "ALTER TABLE message_attachments ADD COLUMN deleted_at TEXT",
        "deleted_by": "ALTER TABLE message_attachments ADD COLUMN deleted_by INTEGER",
    }
    for column, statement in attachment_migrations.items():
        if column not in existing_attachment_columns:
            db.execute(statement)
    _migrate_message_attachment_constraint(db)

    existing_timeline_columns = {
        row["name"] for row in db.execute("PRAGMA table_info(timeline_posts)").fetchall()
    }
    timeline_migrations = {
        "visibility": "ALTER TABLE timeline_posts ADD COLUMN visibility TEXT NOT NULL DEFAULT 'everyone'",
    }
    for column, statement in timeline_migrations.items():
        if column not in existing_timeline_columns:
            db.execute(statement)
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS timeline_post_viewers (
            post_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (post_id, user_id),
            FOREIGN KEY (post_id) REFERENCES timeline_posts (id),
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_timeline_post_viewers_user
            ON timeline_post_viewers (user_id, post_id)
        """
    )

    existing_announcement_columns = {
        row["name"] for row in db.execute("PRAGMA table_info(announcements)").fetchall()
    }
    announcement_migrations = {
        "event_at": "ALTER TABLE announcements ADD COLUMN event_at TEXT",
        "reminder_at": "ALTER TABLE announcements ADD COLUMN reminder_at TEXT",
        "reminder_sent_at": "ALTER TABLE announcements ADD COLUMN reminder_sent_at TEXT",
    }
    for column, statement in announcement_migrations.items():
        if column not in existing_announcement_columns:
            db.execute(statement)
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_announcements_reminder
            ON announcements (deleted_at, reminder_at, reminder_sent_at)
        """
    )

    db.execute(
        """
        CREATE TABLE IF NOT EXISTS gallery_categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS gallery_media (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            event_at TEXT,
            media_kind TEXT NOT NULL CHECK (media_kind IN ('image', 'video')),
            mime_type TEXT NOT NULL,
            original_name TEXT,
            size_bytes INTEGER NOT NULL,
            data BLOB NOT NULL,
            uploaded_by INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            deleted_at TEXT,
            deleted_by INTEGER,
            FOREIGN KEY (category_id) REFERENCES gallery_categories (id),
            FOREIGN KEY (uploaded_by) REFERENCES users (id),
            FOREIGN KEY (deleted_by) REFERENCES users (id)
        )
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_gallery_media_category
            ON gallery_media (deleted_at, category_id, event_at, created_at)
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS gallery_slideshow_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            media_id INTEGER NOT NULL UNIQUE,
            caption TEXT,
            sort_order INTEGER NOT NULL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 1,
            added_by INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (media_id) REFERENCES gallery_media (id),
            FOREIGN KEY (added_by) REFERENCES users (id)
        )
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_gallery_slideshow_order
            ON gallery_slideshow_items (is_active, sort_order, id)
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS committees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            created_by INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            deleted_at TEXT,
            deleted_by INTEGER,
            FOREIGN KEY (created_by) REFERENCES users (id),
            FOREIGN KEY (deleted_by) REFERENCES users (id)
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS committee_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            committee_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            title TEXT,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE (committee_id, user_id),
            FOREIGN KEY (committee_id) REFERENCES committees (id),
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_committees_active
            ON committees (deleted_at, name)
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_committee_members_committee
            ON committee_members (committee_id, sort_order, id)
        """
    )

    existing_slip_columns = {
        row["name"] for row in db.execute("PRAGMA table_info(deposit_slips)").fetchall()
    }
    slip_migrations = {
        "approval_status": "ALTER TABLE deposit_slips ADD COLUMN approval_status TEXT NOT NULL DEFAULT 'draft'",
        "approved_by": "ALTER TABLE deposit_slips ADD COLUMN approved_by INTEGER",
        "approved_at": "ALTER TABLE deposit_slips ADD COLUMN approved_at TEXT",
        "deleted_at": "ALTER TABLE deposit_slips ADD COLUMN deleted_at TEXT",
        "deleted_by": "ALTER TABLE deposit_slips ADD COLUMN deleted_by INTEGER",
    }
    for column, statement in slip_migrations.items():
        if column not in existing_slip_columns:
            db.execute(statement)
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS finance_offerings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            offering_date TEXT NOT NULL,
            offering_type TEXT NOT NULL,
            amount_cents INTEGER NOT NULL DEFAULT 0,
            note TEXT,
            deposit_slip_id INTEGER,
            captured_by INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            deleted_at TEXT,
            deleted_by INTEGER,
            FOREIGN KEY (deposit_slip_id) REFERENCES deposit_slips (id),
            FOREIGN KEY (captured_by) REFERENCES users (id),
            FOREIGN KEY (deleted_by) REFERENCES users (id)
        )
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_finance_offerings_date
            ON finance_offerings (deleted_at, offering_date, deposit_slip_id)
        """
    )
    db.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_live_sessions_status
            ON live_sessions (status, started_at);
        CREATE INDEX IF NOT EXISTS idx_users_active_role
            ON users (deleted_at, is_active, role, full_name);
        CREATE INDEX IF NOT EXISTS idx_users_last_seen
            ON users (deleted_at, last_seen_at);
        CREATE INDEX IF NOT EXISTS idx_notifications_user_read
            ON notifications (user_id, is_read, created_at);
        CREATE INDEX IF NOT EXISTS idx_notifications_user_category_created
            ON notifications (user_id, category, created_at);
        CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_hash
            ON password_reset_tokens (token_hash, expires_at, used_at);
        CREATE INDEX IF NOT EXISTS idx_announcements_active
            ON announcements (deleted_at, is_pinned, created_at);
        CREATE INDEX IF NOT EXISTS idx_announcements_reminder
            ON announcements (deleted_at, reminder_at, reminder_sent_at);
        CREATE INDEX IF NOT EXISTS idx_gallery_media_category
            ON gallery_media (deleted_at, category_id, event_at, created_at);
        CREATE INDEX IF NOT EXISTS idx_gallery_media_kind_created
            ON gallery_media (deleted_at, media_kind, created_at);
        CREATE INDEX IF NOT EXISTS idx_gallery_media_updated
            ON gallery_media (deleted_at, updated_at);
        CREATE INDEX IF NOT EXISTS idx_gallery_slideshow_order
            ON gallery_slideshow_items (is_active, sort_order, id);
        CREATE INDEX IF NOT EXISTS idx_committees_active
            ON committees (deleted_at, name);
        CREATE INDEX IF NOT EXISTS idx_committee_members_committee
            ON committee_members (committee_id, sort_order, id);
        CREATE INDEX IF NOT EXISTS idx_webrtc_signals_session
            ON webrtc_signals (live_session_id, viewer_token, id);
        CREATE INDEX IF NOT EXISTS idx_messages_pair
            ON messages (sender_id, recipient_id, id);
        CREATE INDEX IF NOT EXISTS idx_messages_recipient_unread
            ON messages (recipient_id, is_read, id);
        CREATE INDEX IF NOT EXISTS idx_messages_thread_updated
            ON messages (recipient_id, sender_id, updated_at, id);
        CREATE INDEX IF NOT EXISTS idx_message_attachments_message
            ON message_attachments (message_id);
        CREATE INDEX IF NOT EXISTS idx_live_recordings_session
            ON live_recordings (live_session_id, deleted_at);
        CREATE INDEX IF NOT EXISTS idx_live_comments_session
            ON live_comments (live_session_id, id);
        CREATE INDEX IF NOT EXISTS idx_live_reactions_session
            ON live_reactions (live_session_id, reaction_type);
        CREATE INDEX IF NOT EXISTS idx_timeline_posts_created
            ON timeline_posts (deleted_at, created_at);
        CREATE INDEX IF NOT EXISTS idx_timeline_posts_visibility_created
            ON timeline_posts (deleted_at, visibility, created_at);
        CREATE INDEX IF NOT EXISTS idx_timeline_posts_event
            ON timeline_posts (event_date, created_at);
        CREATE INDEX IF NOT EXISTS idx_timeline_post_viewers_user
            ON timeline_post_viewers (user_id, post_id);
        CREATE INDEX IF NOT EXISTS idx_timeline_media_post
            ON timeline_media (post_id, sort_order);
        CREATE INDEX IF NOT EXISTS idx_timeline_comments_post
            ON timeline_comments (post_id, id);
        CREATE INDEX IF NOT EXISTS idx_timeline_reactions_post
            ON timeline_reactions (post_id, reaction_type);
        CREATE INDEX IF NOT EXISTS idx_audit_logs_created
            ON audit_logs (created_at, user_id);
        CREATE INDEX IF NOT EXISTS idx_deposit_slips_visibility
            ON deposit_slips (is_visible, visible_until, deposit_date);
        CREATE INDEX IF NOT EXISTS idx_deposit_slips_approval_visible
            ON deposit_slips (deleted_at, approval_status, is_visible, visible_until);
        CREATE INDEX IF NOT EXISTS idx_finance_offerings_date
            ON finance_offerings (deleted_at, offering_date, deposit_slip_id);
        CREATE INDEX IF NOT EXISTS idx_visitors_membership_status
            ON visitors (membership_status, membership_requested_at);
        CREATE INDEX IF NOT EXISTS idx_visitors_follow_up
            ON visitors (follow_up_status, follow_up_requested, visit_date);
        CREATE INDEX IF NOT EXISTS idx_visitors_visit_date
            ON visitors (visit_date);
        """
    )
    db.commit()


def _migrate_live_recording_chunks(db: sqlite3.Connection) -> None:
    table = db.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'live_recording_chunks'"
    ).fetchone()
    if table is None:
        return

    now = utc_now()
    live_ids = db.execute(
        """
        SELECT DISTINCT live_session_id
        FROM live_recording_chunks
        ORDER BY live_session_id
        """
    ).fetchall()
    for live in live_ids:
        live_id = live["live_session_id"]
        existing = db.execute(
            "SELECT id FROM live_recordings WHERE live_session_id = ?",
            (live_id,),
        ).fetchone()
        if existing is not None:
            continue

        rows = db.execute(
            """
            SELECT mime_type, data
            FROM live_recording_chunks
            WHERE live_session_id = ?
            ORDER BY chunk_index, id
            """,
            (live_id,),
        ).fetchall()
        if not rows:
            continue

        data = b"".join(row["data"] for row in rows)
        if not data:
            continue

        db.execute(
            """
            INSERT INTO live_recordings (
                live_session_id, mime_type, size_bytes, data, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (live_id, rows[0]["mime_type"] or "video/webm", len(data), data, now, now),
        )

    db.execute("DROP TABLE live_recording_chunks")
    db.execute("DROP INDEX IF EXISTS idx_live_recording_chunks_session")


def _migrate_message_attachment_constraint(db: sqlite3.Connection) -> None:
    table = db.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'message_attachments'"
    ).fetchone()
    if table is None or ("'video'" in table["sql"] and "'file'" in table["sql"]):
        return

    db.executescript(
        """
        PRAGMA foreign_keys = OFF;

        CREATE TABLE message_attachments_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id INTEGER NOT NULL,
            media_kind TEXT NOT NULL CHECK (media_kind IN ('image', 'voice', 'video', 'file')),
            mime_type TEXT NOT NULL,
            original_name TEXT,
            size_bytes INTEGER NOT NULL,
            data BLOB NOT NULL,
            created_at TEXT NOT NULL,
            deleted_at TEXT,
            deleted_by INTEGER,
            FOREIGN KEY (message_id) REFERENCES messages (id),
            FOREIGN KEY (deleted_by) REFERENCES users (id)
        );

        INSERT INTO message_attachments_new (
            id, message_id, media_kind, mime_type, original_name, size_bytes,
            data, created_at, deleted_at, deleted_by
        )
        SELECT
            id, message_id, media_kind, mime_type, original_name, size_bytes,
            data, created_at, deleted_at, deleted_by
        FROM message_attachments;

        DROP TABLE message_attachments;
        ALTER TABLE message_attachments_new RENAME TO message_attachments;

        PRAGMA foreign_keys = ON;
        """
    )


def _migrate_user_role_constraint(db: sqlite3.Connection) -> None:
    table = db.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'users'"
    ).fetchone()
    if (
        table is None
        or (
            "usher" in table["sql"]
            and "videographer" in table["sql"]
            and "treasurer" in table["sql"]
        )
    ):
        return

    db.executescript(
        """
        PRAGMA foreign_keys = OFF;

        CREATE TABLE users_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            role TEXT NOT NULL CHECK (role IN ('super_admin', 'admin', 'pastor', 'usher', 'videographer', 'treasurer', 'member')),
            password_hash TEXT NOT NULL,
            must_change_password INTEGER NOT NULL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_by INTEGER,
            identity_type TEXT NOT NULL DEFAULT 'sa_id',
            phone TEXT,
            id_number TEXT,
            foreign_id_number TEXT,
            nationality TEXT,
            date_of_birth TEXT,
            home_area TEXT,
            bio TEXT,
            emergency_contact_name TEXT,
            emergency_contact_phone TEXT,
            emergency_contact_relationship TEXT,
            profile_photo TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            last_login_at TEXT,
            last_seen_at TEXT,
            deleted_at TEXT,
            deleted_by INTEGER,
            FOREIGN KEY (created_by) REFERENCES users_new (id)
        );

        INSERT INTO users_new (
            id, full_name, email, role, password_hash, must_change_password, is_active, created_by,
            identity_type, phone, id_number, foreign_id_number, nationality, date_of_birth, home_area, bio,
            emergency_contact_name, emergency_contact_phone, emergency_contact_relationship,
            profile_photo, created_at, updated_at,
            last_login_at, last_seen_at, deleted_at, deleted_by
        )
        SELECT
            id, full_name, email, role, password_hash,
            COALESCE(must_change_password, 0), is_active, created_by,
            COALESCE(identity_type, 'sa_id'), phone, id_number, foreign_id_number, nationality, date_of_birth, home_area, bio,
            emergency_contact_name, emergency_contact_phone, emergency_contact_relationship,
            profile_photo, created_at, updated_at,
            last_login_at, last_seen_at, deleted_at, deleted_by
        FROM users;

        DROP TABLE users;
        ALTER TABLE users_new RENAME TO users;

        PRAGMA foreign_keys = ON;
        """
    )


def seed_super_admin() -> None:
    db = get_db()
    existing = db.execute("SELECT COUNT(*) AS count FROM users").fetchone()["count"]
    if existing:
        return

    email = current_app.config["INITIAL_SUPER_ADMIN_EMAIL"].strip().lower()
    password = current_app.config["INITIAL_SUPER_ADMIN_PASSWORD"].strip() or generate_password()
    full_name = current_app.config["INITIAL_SUPER_ADMIN_NAME"].strip() or "Back to God Super Admin"
    now = utc_now()
    db.execute(
        """
        INSERT INTO users (
            full_name, email, role, password_hash, must_change_password, created_at, updated_at
        )
        VALUES (?, ?, 'super_admin', ?, 1, ?, ?)
        """,
        (full_name, email, generate_password_hash(password), now, now),
    )
    db.commit()

    password_source = (
        "This password came from INITIAL_SUPER_ADMIN_PASSWORD."
        if current_app.config["INITIAL_SUPER_ADMIN_PASSWORD"].strip()
        else "This password was generated automatically on first run."
    )
    current_app.config["INITIAL_CREDENTIALS_FILE"].write_text(
        "\n".join(
            [
                "Back to God AOG initial super admin",
                f"Email: {email}",
                f"Password: {password}",
                "",
                password_source,
            ]
        ),
        encoding="utf-8",
    )
