ROLE_LABELS = {
    "super_admin": "Super Admin",
    "admin": "Admin",
    "pastor": "Pastor",
    "usher": "Usher",
    "videographer": "Videographer",
    "treasurer": "Treasurer",
    "member": "Member",
}

ROLE_DESCRIPTIONS = {
    "super_admin": "Full control of church access and account recovery.",
    "admin": "Creates pastors and members, and supports church operations.",
    "pastor": "Pastoral care, follow-up, and ministry coordination.",
    "usher": "Welcomes people and supports live moments.",
    "videographer": "Runs live video moments and media for the church.",
    "treasurer": "Manages deposit slips and finance visibility windows.",
    "member": "Member access for church life and communication.",
}

ROLE_ICONS = {
    "super_admin": "admin_panel_settings",
    "admin": "manage_accounts",
    "pastor": "church",
    "usher": "diversity_3",
    "videographer": "videocam",
    "treasurer": "account_balance",
    "member": "groups",
}

CAN_GO_LIVE_ROLES = {"super_admin", "admin", "usher", "videographer"}
CAN_CAPTURE_VISITOR_ROLES = {"super_admin", "admin", "pastor"}
CAN_TRACK_MEMBERS_ROLES = {"super_admin", "admin", "pastor"}
CAN_APPROVE_MEMBERSHIP_ROLES = {"super_admin", "admin"}
CAN_POST_ANNOUNCEMENT_ROLES = {"super_admin", "admin"}
CAN_UPLOAD_FINANCE_ROLES = {"super_admin", "treasurer"}
CAN_APPROVE_FINANCE_ROLES = {"super_admin", "admin", "pastor"}
CAN_MANAGE_FINANCE_ROLES = CAN_UPLOAD_FINANCE_ROLES | CAN_APPROVE_FINANCE_ROLES
MANAGED_BY_ADMIN_ROLES = {"admin", "pastor", "usher", "videographer", "treasurer", "member"}

VISITOR_STATUS_LABELS = {
    "new": "New",
    "follow_up": "Follow up",
    "connected": "Connected",
    "not_reached": "Not reached",
}
