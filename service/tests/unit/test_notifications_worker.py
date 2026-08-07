from unittest.mock import MagicMock

from procurawise.notifications.service import JOB_TOPIC
from procurawise.notifications.worker import build_dispatch_table, process_message


def test_process_message_calls_service_with_payload_fields() -> None:
    notification_service = MagicMock()
    payload = {"tenant_id": "tenant-a", "notification_id": "notif-1"}

    process_message(payload, notification_service=notification_service)

    notification_service.process_email_delivery_job.assert_called_once_with(
        tenant_id="tenant-a", notification_id="notif-1"
    )


def test_build_dispatch_table_registers_the_notification_email_topic() -> None:
    notification_service = MagicMock()
    dispatch = build_dispatch_table(notification_service)

    assert list(dispatch.keys()) == [JOB_TOPIC]
    dispatch[JOB_TOPIC]({"tenant_id": "t", "notification_id": "n"})
    notification_service.process_email_delivery_job.assert_called_once_with(
        tenant_id="t", notification_id="n"
    )
