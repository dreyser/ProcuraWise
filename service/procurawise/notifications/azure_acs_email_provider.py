import logging

from azure.communication.email import EmailClient

from procurawise.notifications.models import EmailMessage
from procurawise.shared.config import Settings

logger = logging.getLogger("procurawise.notifications.azure_acs_email")


class AzureCommunicationServicesEmailProvider:
    """First (and, for Fase 24, only) implementation of
    `notifications.provider.NotificationEmailProvider` (ADR 0024). Wraps the
    official `azure-communication-email` SDK - no ACS-specific concept leaks
    past this module into `notifications.service` or any domain code, which
    depends on the Protocol only. `send_email` blocks synchronously
    (`.result()` on the LRO poller) - correct here because this only ever
    runs inside the worker's synchronous job handler
    (`process_email_delivery_job`), never inside an API request path, same
    constraint `AzureOpenAIProvider.generate()`/`AzureBlobStorage.upload()`
    already operate under."""

    def __init__(self, connection_string: str, sender_address: str) -> None:
        self._client = EmailClient.from_connection_string(connection_string)
        self._sender_address = sender_address

    @classmethod
    def from_settings(cls, settings: Settings) -> "AzureCommunicationServicesEmailProvider":
        if not (settings.acs_connection_string and settings.acs_sender_address):
            raise ValueError(
                "acs_connection_string/acs_sender_address must be configured to construct "
                "AzureCommunicationServicesEmailProvider"
            )
        return cls(
            connection_string=settings.acs_connection_string,
            sender_address=settings.acs_sender_address,
        )

    def send_email(self, message: EmailMessage) -> None:
        payload = {
            "senderAddress": self._sender_address,
            "recipients": {
                "to": [{"address": message.to_address, "displayName": message.to_display_name}]
            },
            "content": {
                "subject": message.subject,
                "plainText": message.plain_text,
            },
        }
        poller = self._client.begin_send(payload)
        poller.result()

    def ping(self) -> bool:
        # No lightweight "are you there" call exists on EmailClient beyond
        # send itself - constructing the client already validates the
        # connection string's shape; a real send failure surfaces through
        # the normal try/except-and-mark-failed path in
        # NotificationService.process_email_delivery_job instead.
        return True
