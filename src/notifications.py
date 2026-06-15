"""SMS alerting via Twilio's REST API.

Implemented with the standard library only (``urllib``) so the project keeps a
small dependency surface. Credentials come from environment variables, which map
cleanly onto GitHub Actions secrets:

    TWILIO_ACCOUNT_SID   - Twilio account SID (starts with "AC...")
    TWILIO_AUTH_TOKEN    - Twilio auth token
    TWILIO_FROM_NUMBER   - sender number in E.164, e.g. +15555550123
    ALERT_TO_NUMBER      - your phone in E.164, e.g. +8613800138000

Use ``send_sms(..., dry_run=True)`` to format and return the request without
sending — handy locally and in CI smoke tests.
"""

from __future__ import annotations

import base64
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass


TWILIO_MESSAGES_URL = "https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"

ENV_ACCOUNT_SID = "TWILIO_ACCOUNT_SID"
ENV_AUTH_TOKEN = "TWILIO_AUTH_TOKEN"
ENV_FROM_NUMBER = "TWILIO_FROM_NUMBER"
ENV_TO_NUMBER = "ALERT_TO_NUMBER"


class NotificationError(RuntimeError):
    """Raised when an SMS cannot be sent (missing config or API failure)."""


@dataclass(frozen=True)
class SmsResult:
    sent: bool
    to_number: str
    body: str
    provider_sid: str | None = None
    dry_run: bool = False
    detail: str | None = None


def _config(name: str, override: str | None = None) -> str | None:
    value = override if override is not None else os.environ.get(name)
    if value is not None:
        value = value.strip()
    return value or None


def is_configured() -> bool:
    return all(
        _config(name)
        for name in (ENV_ACCOUNT_SID, ENV_AUTH_TOKEN, ENV_FROM_NUMBER, ENV_TO_NUMBER)
    )


def send_sms(
    body: str,
    *,
    to_number: str | None = None,
    from_number: str | None = None,
    account_sid: str | None = None,
    auth_token: str | None = None,
    dry_run: bool = False,
    timeout: float = 15.0,
) -> SmsResult:
    """Send one SMS via Twilio. With ``dry_run`` it only formats the request."""

    sid = _config(ENV_ACCOUNT_SID, account_sid)
    token = _config(ENV_AUTH_TOKEN, auth_token)
    sender = _config(ENV_FROM_NUMBER, from_number)
    recipient = _config(ENV_TO_NUMBER, to_number)

    if dry_run:
        return SmsResult(
            sent=False,
            to_number=recipient or "<unset>",
            body=body,
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
    request = urllib.request.Request(
        TWILIO_MESSAGES_URL.format(sid=sid),
        data=payload,
        method="POST",
    )
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

    provider_sid = _extract_message_sid(raw)
    return SmsResult(
        sent=True,
        to_number=recipient,
        body=body,
        provider_sid=provider_sid,
        detail="sent",
    )


def _extract_message_sid(raw_json: str) -> str | None:
    import json

    try:
        return json.loads(raw_json).get("sid")
    except (ValueError, AttributeError):  # pragma: no cover - defensive
        return None
