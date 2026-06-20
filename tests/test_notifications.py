import pytest

from src.monitoring.notifications import (
    ENV_ALERT_EMAIL_TO,
    ENV_GMAIL_ADDRESS,
    ENV_GMAIL_APP_PASSWORD,
    NotificationError,
    any_channel_configured,
    configured_channel,
    email_is_configured,
    send_alert,
    send_email,
)

ALL_ENV = (
    ENV_GMAIL_ADDRESS,
    ENV_GMAIL_APP_PASSWORD,
    ENV_ALERT_EMAIL_TO,
)


@pytest.fixture
def clean_env(monkeypatch):
    for name in ALL_ENV:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_send_email_dry_run_does_not_send() -> None:
    result = send_email(
        "subj",
        "body",
        to_address="me@example.com",
        from_address="bot@gmail.com",
        app_password="pw",
        dry_run=True,
    )
    assert result.channel == "email"
    assert result.sent is False
    assert result.dry_run is True
    assert result.recipient == "me@example.com"


def test_send_email_defaults_recipient_to_sender_in_dry_run(clean_env) -> None:
    result = send_email("s", "b", from_address="bot@gmail.com", app_password="pw", dry_run=True)
    assert result.recipient == "bot@gmail.com"


def test_send_email_missing_config_raises(clean_env) -> None:
    with pytest.raises(NotificationError):
        send_email("s", "b")


def test_email_configured_needs_address_and_password(clean_env) -> None:
    assert email_is_configured() is False
    clean_env.setenv(ENV_GMAIL_ADDRESS, "bot@gmail.com")
    assert email_is_configured() is False
    clean_env.setenv(ENV_GMAIL_APP_PASSWORD, "pw")
    assert email_is_configured() is True
    assert configured_channel() == "email"


def test_send_alert_prefers_email(clean_env) -> None:
    clean_env.setenv(ENV_GMAIL_ADDRESS, "bot@gmail.com")
    clean_env.setenv(ENV_GMAIL_APP_PASSWORD, "pw")
    result = send_alert("subj", "body", dry_run=True)
    assert result.channel == "email"
    assert result.dry_run is True


def test_send_alert_no_channel_dry_run_returns_none(clean_env) -> None:
    assert any_channel_configured() is False
    result = send_alert("subj", "body", dry_run=True)
    assert result.channel == "none"
    assert result.sent is False


def test_send_alert_no_channel_raises_when_not_dry_run(clean_env) -> None:
    with pytest.raises(NotificationError):
        send_alert("subj", "body")
