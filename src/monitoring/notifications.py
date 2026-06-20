"""Alert delivery for barrier triggers.

The single delivery channel is email (Gmail SMTP), configured purely through
environment variables (which map onto GitHub Actions secrets):

    GMAIL_ADDRESS        - sender Gmail address
    GMAIL_APP_PASSWORD   - Gmail App Password (needs 2FA enabled on the account)
    ALERT_EMAIL_TO       - recipient; optional, defaults to GMAIL_ADDRESS

Use ``dry_run=True`` to format without sending.
"""

from __future__ import annotations

import os
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage


# Email (Gmail SMTP) config.
ENV_GMAIL_ADDRESS = "GMAIL_ADDRESS"
ENV_GMAIL_APP_PASSWORD = "GMAIL_APP_PASSWORD"
ENV_ALERT_EMAIL_TO = "ALERT_EMAIL_TO"
GMAIL_SMTP_HOST = "smtp.gmail.com"
GMAIL_SMTP_PORT = 587


class NotificationError(RuntimeError):
    """Raised when an alert cannot be sent (missing config or delivery failure)."""


@dataclass(frozen=True)
class AlertResult:
    channel: str  # "email" | "none"
    sent: bool
    recipient: str
    dry_run: bool = False
    detail: str | None = None


def _config(name: str, override: str | None = None) -> str | None:
    value = override if override is not None else os.environ.get(name)
    if value is not None:
        value = value.strip()
    return value or None


# --- channel configuration checks -------------------------------------------


def email_is_configured() -> bool:
    # Recipient defaults to the sender, so only address + app password are required.
    return bool(_config(ENV_GMAIL_ADDRESS) and _config(ENV_GMAIL_APP_PASSWORD))


def any_channel_configured() -> bool:
    return email_is_configured()


def configured_channel() -> str | None:
    return "email" if email_is_configured() else None


# --- dispatcher --------------------------------------------------------------


def send_alert(subject: str, body: str, *, dry_run: bool = False, timeout: float = 15.0) -> AlertResult:
    """Send an alert via email (the only delivery channel)."""

    if email_is_configured():
        return send_email(subject, body, dry_run=dry_run, timeout=timeout)
    if dry_run:
        return AlertResult(
            channel="none",
            sent=False,
            recipient="<unset>",
            dry_run=True,
            detail="no channel configured (dry-run)",
        )
    raise NotificationError(
        "no alert channel configured: set GMAIL_ADDRESS + GMAIL_APP_PASSWORD"
    )


# --- email channel -----------------------------------------------------------


def send_email(
    subject: str,
    body: str,
    *,
    to_address: str | None = None,
    from_address: str | None = None,
    app_password: str | None = None,
    dry_run: bool = False,
    timeout: float = 15.0,
) -> AlertResult:
    sender = _config(ENV_GMAIL_ADDRESS, from_address)
    password = _config(ENV_GMAIL_APP_PASSWORD, app_password)
    recipient = _config(ENV_ALERT_EMAIL_TO, to_address) or sender

    if dry_run:
        return AlertResult(
            channel="email",
            sent=False,
            recipient=recipient or "<unset>",
            dry_run=True,
            detail="dry-run: not sent",
        )

    missing = [
        name
        for name, value in ((ENV_GMAIL_ADDRESS, sender), (ENV_GMAIL_APP_PASSWORD, password))
        if not value
    ]
    if missing:
        raise NotificationError(f"missing email config: {', '.join(missing)}")

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = recipient
    message.set_content(body)

    try:
        with smtplib.SMTP(GMAIL_SMTP_HOST, GMAIL_SMTP_PORT, timeout=timeout) as server:
            server.starttls()
            server.login(sender, password)
            server.send_message(message)
    except (smtplib.SMTPException, OSError) as error:  # pragma: no cover - network path
        raise NotificationError(f"could not send email: {error}") from error

    return AlertResult(channel="email", sent=True, recipient=recipient, detail="sent")
