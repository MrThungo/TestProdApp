from __future__ import annotations

from flask import Blueprint, g, render_template

from back_to_god.constants import CAN_POST_ANNOUNCEMENT_ROLES, ROLE_DESCRIPTIONS, ROLE_LABELS
from back_to_god.core.permissions import (
    allowed_roles_for_current_user,
    can_capture_visitors,
    can_go_live,
    can_manage_finance,
    login_required,
)
from back_to_god.services.finance import finance_summary, list_visible_deposit_slips
from back_to_god.services.live import count_active_sessions, list_active_sessions
from back_to_god.services.members import count_members
from back_to_god.services.announcements import list_recent_announcements
from back_to_god.services.timeline import deleted_post_count
from back_to_god.services.users import count_users, list_recent_users
from back_to_god.services.visitors import count_visitors, visitor_analytics


bp = Blueprint("dashboard", __name__, url_prefix="/dashboard")


@bp.get("/")
@login_required
def index():
    role = g.user["role"] if hasattr(g, "user") else "member"
    can_manage = bool(allowed_roles_for_current_user())
    show_user_counts = role in {"super_admin", "admin"}
    show_visitor_counts = role in {"super_admin", "admin", "pastor"}
    show_member_tracking = role in {"super_admin", "admin", "pastor"}
    show_finance = can_manage_finance()
    users = count_users() if show_user_counts else {}
    member_counts = count_members() if show_member_tracking else {"all": 0, "pending_requests": 0}
    visitors = count_visitors() if show_visitor_counts else {"all": 0, "open": 0}
    counts = {
        **users,
        "members": users.get("members", member_counts["all"]),
        "membership_requests": member_counts["pending_requests"],
        "visitors": visitors["all"],
        "visitor_followups": visitors["open"],
        "live_now": count_active_sessions(),
    }
    return render_template(
        "dashboard/index.html",
        counts=counts,
        recent_users=list_recent_users() if can_manage else [],
        recent_announcements=list_recent_announcements(3),
        active_live_sessions=list_active_sessions(),
        visible_slips=list_visible_deposit_slips(4),
        finance_summary=finance_summary() if show_finance else None,
        role_labels=ROLE_LABELS,
        role_descriptions=ROLE_DESCRIPTIONS,
        can_manage=can_manage,
        can_capture_visitors=can_capture_visitors(),
        can_manage_finance=show_finance,
        can_start_live=can_go_live(),
        can_post_announcements=role in CAN_POST_ANNOUNCEMENT_ROLES,
        show_user_counts=show_user_counts,
        show_visitor_counts=show_visitor_counts,
        show_member_tracking=show_member_tracking,
        visitor_analytics=visitor_analytics() if show_visitor_counts else None,
        deleted_timeline_posts=deleted_post_count(g.user["id"], role),
    )
