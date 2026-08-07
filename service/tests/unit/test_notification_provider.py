"""Fase 24 - LoggingNotificationEmailProvider never raises (routine domain
mutations must never fail because email delivery isn't configured), and
resolve_notification_email_provider falls back to it whenever
notifications_email_enabled is False (the default outside production)."""

import logging

from procurawise.notifications.models import EmailMessage
from procurawise.notifications.provider import (
    LoggingNotificationEmailProvider,
    resolve_notification_email_provider,
)
from procurawise.shared.config import Settings


def test_logging_provider_never_raises_and_logs_the_message(caplog) -> None:
    provider = LoggingNotificationEmailProvider()
    message = EmailMessage(
        to_address="vendor@example.com",
        to_display_name="Vendor Contact",
        subject="Has sido invitado",
        plain_text="Usa este enlace...",
    )

    with caplog.at_level(logging.INFO, logger="procurawise.notifications.provider"):
        provider.send_email(message)  # must not raise

    assert any("notification_email_logged_not_sent" in r.message for r in caplog.records)
    assert provider.ping() is True


def test_resolve_returns_logging_provider_when_disabled() -> None:
    settings = Settings(_env_file=None, notifications_email_enabled=False)
    provider = resolve_notification_email_provider(settings)
    assert isinstance(provider, LoggingNotificationEmailProvider)


def test_resolve_falls_back_to_logging_provider_when_acs_not_configured() -> None:
    settings = Settings(
        _env_file=None,
        notifications_email_enabled=True,
        acs_connection_string=None,
        acs_sender_address=None,
    )
    provider = resolve_notification_email_provider(settings)
    assert isinstance(provider, LoggingNotificationEmailProvider)
