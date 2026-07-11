from __future__ import annotations

from .extensions import Base, SQLALCHEMY_AVAILABLE


if SQLALCHEMY_AVAILABLE:
    from sqlalchemy import CheckConstraint, Column, ForeignKey, Integer, LargeBinary, String, Text, UniqueConstraint
    from sqlalchemy.orm import relationship


    class User(Base):
        __tablename__ = "users"
        __table_args__ = (
            CheckConstraint(
                "role IN ('super_admin', 'admin', 'pastor', 'usher', 'videographer', 'treasurer', 'member')",
                name="ck_users_role",
            ),
        )

        id = Column(Integer, primary_key=True)
        full_name = Column(String(120), nullable=False)
        email = Column(String(180), nullable=False, unique=True)
        role = Column(String(40), nullable=False)
        password_hash = Column(String(255), nullable=False)
        must_change_password = Column(Integer, nullable=False, default=1)
        is_active = Column(Integer, nullable=False, default=1)
        created_by = Column(Integer, ForeignKey("users.id"))
        identity_type = Column(String(20), nullable=False, default="sa_id")
        phone = Column(String(40))
        id_number = Column(String(13))
        foreign_id_number = Column(String(80))
        nationality = Column(String(80))
        date_of_birth = Column(String(30))
        home_area = Column(String(120))
        bio = Column(Text)
        emergency_contact_name = Column(String(120))
        emergency_contact_phone = Column(String(40))
        emergency_contact_relationship = Column(String(80))
        profile_photo = Column(String(255))
        created_at = Column(String(40), nullable=False)
        updated_at = Column(String(40), nullable=False)
        last_login_at = Column(String(40))
        last_seen_at = Column(String(40))
        deleted_at = Column(String(40))
        deleted_by = Column(Integer, ForeignKey("users.id"))

        created_children = relationship(
            "User",
            foreign_keys=[created_by],
            remote_side=[id],
        )


    class PasswordResetToken(Base):
        __tablename__ = "password_reset_tokens"

        id = Column(Integer, primary_key=True)
        user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
        token_hash = Column(String(80), nullable=False, unique=True)
        expires_at = Column(String(40), nullable=False)
        used_at = Column(String(40))
        created_at = Column(String(40), nullable=False)


    class Visitor(Base):
        __tablename__ = "visitors"
        __table_args__ = (
            CheckConstraint(
                "follow_up_status IN ('new', 'follow_up', 'connected', 'not_reached')",
                name="ck_visitors_follow_up_status",
            ),
            CheckConstraint(
                "membership_status IN ('none', 'pending', 'approved', 'declined')",
                name="ck_visitors_membership_status",
            ),
        )

        id = Column(Integer, primary_key=True)
        full_name = Column(String(120), nullable=False)
        phone = Column(String(40))
        email = Column(String(180))
        identity_type = Column(String(20), nullable=False, default="sa_id")
        id_number = Column(String(13))
        foreign_id_number = Column(String(80))
        nationality = Column(String(80))
        date_of_birth = Column(String(30))
        visit_date = Column(String(40), nullable=False)
        visit_type = Column(String(40), nullable=False)
        age_group = Column(String(40), nullable=False)
        invited_by = Column(String(120))
        home_area = Column(String(120))
        prayer_request = Column(Text)
        notes = Column(Text)
        service_rating = Column(String(40))
        service_feedback = Column(Text)
        consent_to_contact = Column(Integer, nullable=False, default=1)
        follow_up_status = Column(String(40), nullable=False, default="new")
        follow_up_requested = Column(Integer, nullable=False, default=0)
        follow_up_made_at = Column(String(40))
        follow_up_made_by = Column(Integer, ForeignKey("users.id"))
        follow_up_notes = Column(Text)
        membership_requested = Column(Integer, nullable=False, default=0)
        membership_status = Column(String(40), nullable=False, default="none")
        membership_requested_at = Column(String(40))
        membership_reviewed_at = Column(String(40))
        membership_reviewed_by = Column(Integer, ForeignKey("users.id"))
        member_user_id = Column(Integer, ForeignKey("users.id"))
        membership_notes = Column(Text)
        captured_by = Column(Integer, ForeignKey("users.id"))
        created_at = Column(String(40), nullable=False)
        updated_at = Column(String(40), nullable=False)


    class LiveSession(Base):
        __tablename__ = "live_sessions"
        __table_args__ = (
            CheckConstraint("status IN ('active', 'ended')", name="ck_live_sessions_status"),
        )

        id = Column(Integer, primary_key=True)
        title = Column(String(160), nullable=False)
        description = Column(Text)
        status = Column(String(20), nullable=False, default="active")
        started_by = Column(Integer, ForeignKey("users.id"), nullable=False)
        started_at = Column(String(40), nullable=False)
        ended_at = Column(String(40))
        recording_deleted_at = Column(String(40))
        recording_deleted_by = Column(Integer, ForeignKey("users.id"))
        updated_at = Column(String(40), nullable=False)


    class Notification(Base):
        __tablename__ = "notifications"

        id = Column(Integer, primary_key=True)
        user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
        title = Column(String(160), nullable=False)
        message = Column(Text, nullable=False)
        target_url = Column(String(255))
        category = Column(String(40), nullable=False, default="general")
        is_read = Column(Integer, nullable=False, default=0)
        created_at = Column(String(40), nullable=False)


    class Announcement(Base):
        __tablename__ = "announcements"

        id = Column(Integer, primary_key=True)
        title = Column(String(120), nullable=False)
        body = Column(Text, nullable=False)
        event_at = Column(String(40))
        reminder_at = Column(String(40))
        reminder_sent_at = Column(String(40))
        is_pinned = Column(Integer, nullable=False, default=0)
        created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
        created_at = Column(String(40), nullable=False)
        updated_at = Column(String(40), nullable=False)
        deleted_at = Column(String(40))
        deleted_by = Column(Integer, ForeignKey("users.id"))


    class GalleryCategory(Base):
        __tablename__ = "gallery_categories"

        id = Column(Integer, primary_key=True)
        name = Column(String(80), nullable=False, unique=True)
        created_at = Column(String(40), nullable=False)


    class GalleryMedia(Base):
        __tablename__ = "gallery_media"
        __table_args__ = (
            CheckConstraint("media_kind IN ('image', 'video')", name="ck_gallery_media_media_kind"),
        )

        id = Column(Integer, primary_key=True)
        category_id = Column(Integer, ForeignKey("gallery_categories.id"), nullable=False)
        title = Column(String(120), nullable=False)
        description = Column(Text)
        event_at = Column(String(40))
        media_kind = Column(String(20), nullable=False)
        mime_type = Column(String(120), nullable=False)
        original_name = Column(String(160))
        size_bytes = Column(Integer, nullable=False)
        data = Column(LargeBinary, nullable=False)
        uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=False)
        created_at = Column(String(40), nullable=False)
        updated_at = Column(String(40), nullable=False)
        deleted_at = Column(String(40))
        deleted_by = Column(Integer, ForeignKey("users.id"))


    class WebRTCSignal(Base):
        __tablename__ = "webrtc_signals"
        __table_args__ = (
            CheckConstraint("sender_role IN ('viewer', 'streamer')", name="ck_webrtc_signals_sender_role"),
            CheckConstraint("signal_type IN ('offer', 'answer', 'ice')", name="ck_webrtc_signals_signal_type"),
        )

        id = Column(Integer, primary_key=True)
        live_session_id = Column(Integer, ForeignKey("live_sessions.id"), nullable=False)
        viewer_token = Column(String(120), nullable=False)
        sender_role = Column(String(20), nullable=False)
        signal_type = Column(String(20), nullable=False)
        payload = Column(Text, nullable=False)
        created_at = Column(String(40), nullable=False)


    class Message(Base):
        __tablename__ = "messages"

        id = Column(Integer, primary_key=True)
        sender_id = Column(Integer, ForeignKey("users.id"), nullable=False)
        recipient_id = Column(Integer, ForeignKey("users.id"), nullable=False)
        body = Column(Text, nullable=False)
        is_read = Column(Integer, nullable=False, default=0)
        created_at = Column(String(40), nullable=False)
        updated_at = Column(String(40))
        edited_at = Column(String(40))
        deleted_at = Column(String(40))
        deleted_by = Column(Integer, ForeignKey("users.id"))


    class MessageAttachment(Base):
        __tablename__ = "message_attachments"
        __table_args__ = (
            CheckConstraint("media_kind IN ('image', 'voice', 'video', 'file')", name="ck_message_attachments_media_kind"),
        )

        id = Column(Integer, primary_key=True)
        message_id = Column(Integer, ForeignKey("messages.id"), nullable=False)
        media_kind = Column(String(20), nullable=False)
        mime_type = Column(String(120), nullable=False)
        original_name = Column(String(160))
        size_bytes = Column(Integer, nullable=False)
        data = Column(LargeBinary, nullable=False)
        created_at = Column(String(40), nullable=False)
        deleted_at = Column(String(40))
        deleted_by = Column(Integer, ForeignKey("users.id"))


    class LiveRecording(Base):
        __tablename__ = "live_recordings"

        id = Column(Integer, primary_key=True)
        live_session_id = Column(Integer, ForeignKey("live_sessions.id"), nullable=False, unique=True)
        mime_type = Column(String(120), nullable=False)
        size_bytes = Column(Integer, nullable=False)
        data = Column(LargeBinary, nullable=False)
        created_at = Column(String(40), nullable=False)
        updated_at = Column(String(40), nullable=False)
        deleted_at = Column(String(40))
        deleted_by = Column(Integer, ForeignKey("users.id"))


    class LiveComment(Base):
        __tablename__ = "live_comments"

        id = Column(Integer, primary_key=True)
        live_session_id = Column(Integer, ForeignKey("live_sessions.id"), nullable=False)
        user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
        body = Column(Text, nullable=False)
        created_at = Column(String(40), nullable=False)


    class LiveReaction(Base):
        __tablename__ = "live_reactions"
        __table_args__ = (
            UniqueConstraint("live_session_id", "user_id", name="uq_live_reactions_session_user"),
            CheckConstraint("reaction_type IN ('like', 'heart', 'amen', 'clap', 'fire')", name="ck_live_reactions_reaction_type"),
        )

        id = Column(Integer, primary_key=True)
        live_session_id = Column(Integer, ForeignKey("live_sessions.id"), nullable=False)
        user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
        reaction_type = Column(String(20), nullable=False)
        created_at = Column(String(40), nullable=False)
        updated_at = Column(String(40), nullable=False)


    class TimelinePost(Base):
        __tablename__ = "timeline_posts"
        __table_args__ = (
            CheckConstraint("visibility IN ('everyone', 'specific')", name="ck_timeline_posts_visibility"),
        )

        id = Column(Integer, primary_key=True)
        author_id = Column(Integer, ForeignKey("users.id"), nullable=False)
        title = Column(String(120), nullable=False)
        body = Column(Text)
        event_date = Column(String(40))
        visibility = Column(String(20), nullable=False, default="everyone")
        created_at = Column(String(40), nullable=False)
        updated_at = Column(String(40), nullable=False)
        deleted_at = Column(String(40))
        deleted_by = Column(Integer, ForeignKey("users.id"))


    class TimelinePostViewer(Base):
        __tablename__ = "timeline_post_viewers"

        post_id = Column(Integer, ForeignKey("timeline_posts.id"), primary_key=True)
        user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
        created_at = Column(String(40), nullable=False)


    class TimelineMedia(Base):
        __tablename__ = "timeline_media"
        __table_args__ = (
            CheckConstraint("media_kind IN ('image', 'video')", name="ck_timeline_media_media_kind"),
        )

        id = Column(Integer, primary_key=True)
        post_id = Column(Integer, ForeignKey("timeline_posts.id"), nullable=False)
        media_kind = Column(String(20), nullable=False)
        mime_type = Column(String(120), nullable=False)
        original_name = Column(String(160))
        size_bytes = Column(Integer, nullable=False)
        data = Column(LargeBinary, nullable=False)
        sort_order = Column(Integer, nullable=False, default=0)
        created_at = Column(String(40), nullable=False)


    class TimelineComment(Base):
        __tablename__ = "timeline_comments"

        id = Column(Integer, primary_key=True)
        post_id = Column(Integer, ForeignKey("timeline_posts.id"), nullable=False)
        user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
        body = Column(Text, nullable=False)
        created_at = Column(String(40), nullable=False)


    class TimelineReaction(Base):
        __tablename__ = "timeline_reactions"
        __table_args__ = (
            UniqueConstraint("post_id", "user_id", name="uq_timeline_reactions_post_user"),
            CheckConstraint("reaction_type IN ('like', 'love', 'amen')", name="ck_timeline_reactions_reaction_type"),
        )

        id = Column(Integer, primary_key=True)
        post_id = Column(Integer, ForeignKey("timeline_posts.id"), nullable=False)
        user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
        reaction_type = Column(String(20), nullable=False, default="like")
        created_at = Column(String(40), nullable=False)
        updated_at = Column(String(40), nullable=False)


    class AuditLog(Base):
        __tablename__ = "audit_logs"

        id = Column(Integer, primary_key=True)
        user_id = Column(Integer, ForeignKey("users.id"))
        action = Column(String(80), nullable=False)
        entity = Column(String(80))
        entity_id = Column(Integer)
        details = Column(Text)
        ip_address = Column(String(80))
        created_at = Column(String(40), nullable=False)


    class DepositSlip(Base):
        __tablename__ = "deposit_slips"
        __table_args__ = (
            CheckConstraint("approval_status IN ('draft', 'pending', 'approved', 'rejected')", name="ck_deposit_slips_approval_status"),
        )

        id = Column(Integer, primary_key=True)
        title = Column(String(160), nullable=False)
        bank_name = Column(String(120))
        reference = Column(String(120))
        amount_cents = Column(Integer, nullable=False, default=0)
        deposit_date = Column(String(40), nullable=False)
        is_visible = Column(Integer, nullable=False, default=0)
        visible_from = Column(String(40))
        visible_until = Column(String(40))
        approval_status = Column(String(40), nullable=False, default="draft")
        approved_by = Column(Integer, ForeignKey("users.id"))
        approved_at = Column(String(40))
        original_name = Column(String(160), nullable=False)
        mime_type = Column(String(120), nullable=False)
        size_bytes = Column(Integer, nullable=False)
        data = Column(LargeBinary, nullable=False)
        created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
        deleted_at = Column(String(40))
        deleted_by = Column(Integer, ForeignKey("users.id"))
        created_at = Column(String(40), nullable=False)
        updated_at = Column(String(40), nullable=False)


    class FinanceOffering(Base):
        __tablename__ = "finance_offerings"

        id = Column(Integer, primary_key=True)
        offering_date = Column(String(40), nullable=False)
        offering_type = Column(String(80), nullable=False)
        amount_cents = Column(Integer, nullable=False, default=0)
        note = Column(Text)
        deposit_slip_id = Column(Integer, ForeignKey("deposit_slips.id"))
        captured_by = Column(Integer, ForeignKey("users.id"), nullable=False)
        created_at = Column(String(40), nullable=False)
        updated_at = Column(String(40), nullable=False)
        deleted_at = Column(String(40))
        deleted_by = Column(Integer, ForeignKey("users.id"))
else:
    User = Visitor = LiveSession = Notification = Announcement = GalleryCategory = None
    GalleryMedia = WebRTCSignal = Message = None
    MessageAttachment = LiveRecording = LiveComment = LiveReaction = None
    TimelinePost = TimelinePostViewer = TimelineMedia = TimelineComment = None
    TimelineReaction = AuditLog = DepositSlip = PasswordResetToken = FinanceOffering = None
