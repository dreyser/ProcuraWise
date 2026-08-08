import logging
from typing import Protocol

from procurawise.notifications.models import EmailMessage
from procurawise.shared.config import Settings

logger = logging.getLogger("procurawise.notifications.provider")


class NotificationEmailProvider(Protocol):
    """Vendor-neutral boundary for transactional email (ADR 0024). Business
    services (`notifications.service`) depend on this Protocol only, never on
    a concrete provider - same shape as `ai.provider.AIProvider`/
    `shared.storage.BlobStorage`."""

    def send_email(self, message: EmailMessage) -> None: ...

    def ping(self) -> bool: ...


class LoggingNotificationEmailProvider:
    """Local/CI stand-in - deliberately NOT named Unconfigured...: unlike AI
    generation (a manual, opt-in action where a loud RuntimeError is
    correct), notification emails fire automatically off routine domain
    mutations every dev/CI run already exercises (every vendor invite, every
    publish) - a provider that raised on every call would break those flows
    in any environment without real ACS credentials. Logs the fully-rendered
    message instead of sending it and never raises. This is also the
    deliberate answer to ADR 0020's open Mailhog-vs-Mailpit question (ADR
    0024): no local email-capture container is added, since no ACS emulator
    exists for either to meaningfully test against."""

    def send_email(self, message: EmailMessage) -> None:
        logger.info(
            "notification_email_logged_not_sent",
            extra={
                "to_address": message.to_address,
                "to_display_name": message.to_display_name,
                "subject": message.subject,
                "plain_text": message.plain_text,
            },
        )

    def ping(self) -> bool:
        return True


def resolve_notification_email_provider(settings: Settings) -> NotificationEmailProvider:
    """Single point both `notifications.dependencies.build_notification_service`
    and `worker/main.py` call - avoids each hand-rolling its own try/except
    around AzureCommunicationServicesEmailProvider.from_settings()."""
    if not settings.notifications_email_enabled:
        return LoggingNotificationEmailProvider()

    # Imported here, not at module level: azure_acs_email_provider imports
    # the `azure.communication.email` SDK, and this module (notifications.
    # provider) is the Protocol every provider is defined against, so it must
    # not itself depend on the one concrete implementation (ADR 0024,
    # CLAUDE.md S5.1).
    from procurawise.notifications.azure_acs_email_provider import (
        AzureCommunicationServicesEmailProvider,
    )

    try:
        return AzureCommunicationServicesEmailProvider.from_settings(settings)
    except ValueError:
        logger.warning(
            "acs_not_configured - falling back to LoggingNotificationEmailProvider "
            "(notifications_email_enabled=true requires acs_connection_string/"
            "acs_sender_address)"
        )
        return LoggingNotificationEmailProvider()
