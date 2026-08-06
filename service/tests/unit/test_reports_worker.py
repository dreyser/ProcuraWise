from unittest.mock import MagicMock

from procurawise.reports.service import JOB_TOPIC
from procurawise.reports.worker import build_dispatch_table, process_message


def test_process_message_calls_service_with_payload_fields() -> None:
    report_service = MagicMock()
    payload = {"tenant_id": "tenant-a", "evaluation_id": "eval-1", "report_id": "report-1"}

    process_message(payload, report_service=report_service)

    report_service.process_generation_job.assert_called_once_with(
        tenant_id="tenant-a", evaluation_id="eval-1", report_id="report-1"
    )


def test_build_dispatch_table_registers_the_report_generation_topic() -> None:
    report_service = MagicMock()
    dispatch = build_dispatch_table(report_service)

    assert list(dispatch.keys()) == [JOB_TOPIC]
    dispatch[JOB_TOPIC]({"tenant_id": "t", "evaluation_id": "e", "report_id": "r"})
    report_service.process_generation_job.assert_called_once_with(
        tenant_id="t", evaluation_id="e", report_id="r"
    )
