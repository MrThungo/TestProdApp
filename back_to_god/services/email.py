from __future__ import annotations

import smtplib
from email.message import EmailMessage
from email.utils import formataddr

from flask import current_app

from back_to_god.core.security import utc_now
from back_to_god.core.validators import is_valid_email


def _clean_config(value: object) -> str:
    return str(value or "").strip().strip('"').strip("'")


def _smtp_port() -> int:
    try:
        return int(current_app.config.get("SMTP_PORT", 587))
    except (TypeError, ValueError):
        return 587


def send_email(to_email: str, subject: str, body: str) -> bool:
    recipient = (to_email or "").strip()
    if not recipient:
        return False

    username = _clean_config(current_app.config.get("SMTP_USERNAME", ""))
    password = _clean_config(current_app.config.get("SMTP_PASSWORD", ""))
    configured_sender = _clean_config(current_app.config.get("EMAIL_FROM", ""))
    sender_name = _clean_config(current_app.config.get("EMAIL_FROM_NAME", "No-Reply@CityCentreAOG"))
    sender_address = configured_sender if is_valid_email(configured_sender) else username
    if username and configured_sender == "no-reply@backtogod.local":
        sender_address = username
    sender = formataddr((sender_name, sender_address)) if sender_name and sender_address else sender_address

    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)

    host = _clean_config(current_app.config.get("SMTP_HOST", ""))
    delivery_error = ""
    if host:
        port = _smtp_port()
        use_ssl = bool(current_app.config.get("SMTP_USE_SSL")) or port == 465
        try:
            if use_ssl:
                server_context = smtplib.SMTP_SSL(host, port, timeout=20)
            else:
                server_context = smtplib.SMTP(host, port, timeout=20)

            with server_context as server:
                if not use_ssl and current_app.config.get("SMTP_USE_TLS", True):
                    server.starttls()
                if username and password:
                    server.login(username, password)
                server.send_message(message)
            return True
        except Exception as error:
            delivery_error = f"{type(error).__name__}: {error}"
            current_app.logger.warning("Email delivery failed; writing to outbox.", exc_info=True)

    outbox = current_app.config["EMAIL_OUTBOX_FILE"]
    outbox.parent.mkdir(parents=True, exist_ok=True)
    with outbox.open("a", encoding="utf-8") as handle:
        handle.write("\n" + ("=" * 72) + "\n")
        handle.write(f"Created: {utc_now()}\n")
        handle.write(f"To: {recipient}\n")
        handle.write(f"Subject: {subject}\n\n")
        if delivery_error:
            handle.write(f"Delivery error: {delivery_error}\n\n")
        handle.write(body.strip() + "\n")
    return False


def send_account_created_email(to_email: str, full_name: str, password: str) -> bool:
    return send_email(
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


def send_password_reset_link(to_email: str, full_name: str, reset_url: str) -> bool:
    return send_email(
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


def send_password_changed_email(to_email: str, full_name: str) -> bool:
    return send_email(
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
