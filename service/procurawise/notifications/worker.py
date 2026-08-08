import logging
from collections.abc import Callable
from typing import Any

from procurawise.notifications.service import JOB_TOPIC, NotificationService

logger = logging.getLogger("procurawise.notifications.worker")


def process_message(payload: dict[str, Any], *, notification_service: NotificationService) -> None:
    """Fase 24 (ADR 0001/0005): calls `notifications.service` directly, never
    internal HTTP - same shape as `ai.worker.process_message`/
    `reports.worker.process_message`."""
    notification_service.process_email_delivery_job(
        tenant_id=payload["tenant_id"],
        notification_id=payload["notification_id"],
    )


def build_dispatch_table(
    notification_service: NotificationService,
) -> dict[str, Callable[[dict[str, Any]], None]]:
    return {
        JOB_TOPIC: lambda payload: process_message(
            payload, notification_service=notification_service
        )
    }
