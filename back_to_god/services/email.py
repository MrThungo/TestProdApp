from __future__ import annotations

import smtplib
from email.message import EmailMessage

from flask import current_app

from back_to_god.core.security import utc_now


def send_email(to_email: str, subject: str, body: str) -> bool:
    recipient = (to_email or "").strip()
    if not recipient:
        return False

    message = EmailMessage()
    message["From"] = current_app.config["EMAIL_FROM"]
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)

    host = current_app.config.get("SMTP_HOST", "")
    if host:
        try:
            with smtplib.SMTP(host, current_app.config["SMTP_PORT"], timeout=12) as server:
                if current_app.config.get("SMTP_USE_TLS", True):
                    server.starttls()
                username = current_app.config.get("SMTP_USERNAME", "")
                password = current_app.config.get("SMTP_PASSWORD", "")
                if username and password:
                    server.login(username, password)
                server.send_message(message)
            return True
        except OSError:
            pass

    outbox = current_app.config["EMAIL_OUTBOX_FILE"]
    outbox.parent.mkdir(parents=True, exist_ok=True)
    with outbox.open("a", encoding="utf-8") as handle:
        handle.write("\n" + ("=" * 72) + "\n")
        handle.write(f"Created: {utc_now()}\n")
        handle.write(f"To: {recipient}\n")
        handle.write(f"Subject: {subject}\n\n")
        handle.write(body.strip() + "\n")
    return False


def send_account_created_email(to_email: str, full_name: str, password: str) -> None:
    send_email(
        to_email,
        "Your Back to God AOG app account",
        "\n".join(
            [
                f"Hello {full_name},",
                "",
                "Your Back to God AOG City Centre app account has been created.",
                f"Email: {to_email}",
                f"Temporary password: {password}",
                "",
                "On first login, the app will ask you to change this password.",
            ]
        ),
    )


def send_password_reset_link(to_email: str, full_name: str, reset_url: str) -> None:
    send_email(
        to_email,
        "Reset your Back to God AOG password",
        "\n".join(
            [
                f"Hello {full_name},",
                "",
                "Use this link to reset your Back to God AOG app password:",
                reset_url,
                "",
                "This link expires in 5 minutes.",
                "If you did not request this, you can ignore this email.",
            ]
        ),
    )


def send_password_changed_email(to_email: str, full_name: str) -> None:
    send_email(
        to_email,
        "Your Back to God AOG password changed",
        "\n".join(
            [
                f"Hello {full_name},",
                "",
                "Your Back to God AOG app password was changed.",
                "If this was not you, contact a church administrator immediately.",
            ]
        ),
    )
