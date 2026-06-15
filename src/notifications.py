"""Alert delivery for barrier triggers.

Channels are pluggable and configured purely through environment variables (which
map onto GitHub Actions secrets). ``send_alert`` picks the first configured
channel, preferring email.

Email (Gmail SMTP) - recommended, standard library only:
    GMAIL_ADDRESS        - sender Gmail address
    GMAIL_APP_PASSWORD   - Gmail App Password (needs 2FA enabled on the account)
    ALERT_EMAIL_TO       - recipient; optional, defaults to GMAIL_ADDRESS

SMS (Twilio) - optional fallback:
    TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER, ALERT_TO_NUMBER

Use ``dry_run=True`` to format without sending.
"""

from __future__ import annotations

import base64
import os
import smtplib
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from email.message import EmailMessage


# Email (Gmail SMTP) config.
ENV_GMAIL_ADDRESS = "GMAIL_ADDRESS"
ENV_GMAIL_APP_PASSWORD = "GMAIL_APP_PASSWORD"
ENV_ALERT_EMAIL_TO = "ALERT_EMAIL_TO"
GMAIL_SMTP_HOST = "smtp.gmail.com"
GMAIL_SMTP_PORT = 587

# SMS (Twilio) config.
ENV_ACCOUNT_SID = "TWILIO_ACCOUNT_SID"
ENV_AUTH_TOKEN = "TWILIO_AUTH_TOKEN"
ENV_FROM_NUMBER = "TWILIO_FROM_NUMBER"
ENV_TO_NUMBER = "ALERT_TO_NUMBER"
TWILIO_MESSAGES_URL = "https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"


class NotificationError(RuntimeError):
    """Raised when an alert cannot be sent (missing config or delivery failure)."""


@dataclass(frozen=True)
class AlertResult:
    channel: str  # "email" | "sms" | "none"
    sent: bool
    recipient: str
    dry_run: bool = False
    detail: str | None = None
    provider_id: str | None = None


def _config(name: str, override: str | None = None) -> str | None:
    value = override if override is not None else os.environ.get(name)
    if value is not None:
        value = value.strip()
    return value or None


# --- channel configuration checks -------------------------------------------


def email_is_configured() -> bool:
    # Recipient defaults to the sender, so only address + app password are required.
    return bool(_config(ENV_GMAIL_ADDRESS) and _config(ENV_GMAIL_APP_PASSWORD))


def sms_is_configured() -> bool:
    return all(
        _config(name)
        for name in (ENV_ACCOUNT_SID, ENV_AUTH_TOKEN, ENV_FROM_NUMBER, ENV_TO_NUMBER)
    )


def any_channel_configured() -> bool:
    return email_is_configured() or sms_is_configured()


def configured_channel() -> str | None:
    if email_is_configured():
        return "email"
    if sms_is_configured():
        return "sms"
    return None


# --- dispatcher --------------------------------------------------------------


def send_alert(subject: str, body: str, *, dry_run: bool = False, timeout: float = 15.0) -> AlertResult:
    """Send an alert via the first configured channel (email preferred)."""

    if email_is_configured():
        return send_email(subject, body, dry_run=dry_run, timeout=timeout)
    if sms_is_configured():
        return send_sms(body, dry_run=dry_run, timeout=timeout)
    if dry_run:
        return AlertResult(
            channel="none",
            sent=False,
            recipient="<unset>",
            dry_run=True,
            detail="no channel configured (dry-run)",
        )
    raise NotificationError(
        "no alert channel configured: set GMAIL_ADDRESS + GMAIL_APP_PASSWORD (email) "
        "or TWILIO_* + ALERT_TO_NUMBER (sms)"
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


# --- sms channel (Twilio) ----------------------------------------------------


def send_sms(
    body: str,
    *,
    to_number: str | None = None,
    from_number: str | None = None,
    account_sid: str | None = None,
    auth_token: str | None = None,
    dry_run: bool = False,
    timeout: float = 15.0,
) -> AlertResult:
    sid = _config(ENV_ACCOUNT_SID, account_sid)
    token = _config(ENV_AUTH_TOKEN, auth_token)
    sender = _config(ENV_FROM_NUMBER, from_number)
    recipient = _config(ENV_TO_NUMBER, to_number)

    if dry_run:
        return AlertResult(
            channel="sms",
            sent=False,
            recipient=recipient or "<unset>",
            dry_run=True,
            detail="dry-run: not sent",
        )

    missing = [
        name
        for name, value in (
            (ENV_ACCOUNT_SID, sid),
            (ENV_AUTH_TOKEN, token),
            (ENV_FROM_NUMBER, sender),
            (ENV_TO_NUMBER, recipient),
        )
        if not value
    ]
    if missing:
        raise NotificationError(f"missing SMS config: {', '.join(missing)}")

    payload = urllib.parse.urlencode({"From": sender, "To": recipient, "Body": body}).encode()
    request = urllib.request.Request(TWILIO_MESSAGES_URL.format(sid=sid), data=payload, method="POST")
    credentials = base64.b64encode(f"{sid}:{token}".encode()).decode()
    request.add_header("Authorization", f"Basic {credentials}")
    request.add_header("Content-Type", "application/x-www-form-urlencoded")

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode()
    except urllib.error.HTTPError as error:  # pragma: no cover - network path
        detail = error.read().decode(errors="replace") if error.fp else str(error)
        raise NotificationError(f"Twilio returned {error.code}: {detail}") from error
    except urllib.error.URLError as error:  # pragma: no cover - network path
        raise NotificationError(f"could not reach Twilio: {error.reason}") from error

    return AlertResult(channel="sms", sent=True, recipient=recipient, detail="sent", provider_id=_extract_message_sid(raw))


def _extract_message_sid(raw_json: str) -> str | None:
    import json

    try:
        return json.loads(raw_json).get("sid")
    except (ValueError, AttributeError):  # pragma: no cover - defensive
        return None
