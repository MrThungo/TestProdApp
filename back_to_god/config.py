from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path


def _load_local_env() -> None:
    project_root = Path(__file__).resolve().parent.parent
    env_path = project_root / ".env"
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        normalized_value = value.replace("\\", "/")
        var_data_unavailable = os.name == "nt" or not Path("/var/data").exists()
        if key in {"INSTANCE_DIR", "DATABASE_PATH"} and normalized_value.startswith("/var/data") and var_data_unavailable:
            continue
        if key == "DATABASE_URL" and "sqlite:////var/data" in normalized_value and var_data_unavailable:
            continue
        if key:
            os.environ.setdefault(key, value)


_load_local_env()


class Config:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent
    INSTANCE_DIR = Path(os.environ.get("INSTANCE_DIR", PROJECT_ROOT / "instance")).resolve()
    DATABASE = Path(os.environ.get("DATABASE_PATH", INSTANCE_DIR / "back_to_god.sqlite3")).resolve()
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", f"sqlite:///{DATABASE.as_posix()}")
    INITIAL_CREDENTIALS_FILE = INSTANCE_DIR / "initial-super-admin.txt"
    EXTERNAL_NOTIFICATION_KEY_FILE = INSTANCE_DIR / "external-notification-api-key.txt"
    EMAIL_OUTBOX_FILE = INSTANCE_DIR / "email-outbox.log"
    PROFILE_UPLOAD_DIR = INSTANCE_DIR / "uploads" / "profile_pictures"
    MAX_CONTENT_LENGTH = None
    SECRET_KEY = os.environ.get("SECRET_KEY", "change-this-before-production")
    INITIAL_SUPER_ADMIN_NAME = os.environ.get("INITIAL_SUPER_ADMIN_NAME", "Back to God Super Admin")
    INITIAL_SUPER_ADMIN_EMAIL = os.environ.get("INITIAL_SUPER_ADMIN_EMAIL", "superadmin@backtogod.local")
    INITIAL_SUPER_ADMIN_PASSWORD = os.environ.get("INITIAL_SUPER_ADMIN_PASSWORD", "")
    EXTERNAL_NOTIFICATION_API_KEY = os.environ.get("EXTERNAL_NOTIFICATION_API_KEY", "")
    EMAIL_FROM = os.environ.get("EMAIL_FROM", "no-reply@backtogod.local")
    EMAIL_FROM_NAME = os.environ.get("EMAIL_FROM_NAME", "No-Reply@CityCentreAOG")
    SMTP_HOST = os.environ.get("SMTP_HOST", "")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
    SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "")
    SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
    SMTP_USE_TLS = os.environ.get("SMTP_USE_TLS", "1") == "1"
    SMTP_USE_SSL = os.environ.get("SMTP_USE_SSL", "") == "1"
    ENABLE_QUICK_LOGIN = os.environ.get("ENABLE_QUICK_LOGIN", "1") == "1"
    PERMANENT_SESSION_LIFETIME = timedelta(days=30)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "0") == "1"
