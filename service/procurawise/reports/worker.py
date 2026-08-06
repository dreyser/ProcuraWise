import logging
from collections.abc import Callable
from typing import Any

from procurawise.reports.service import JOB_TOPIC, ReportService

logger = logging.getLogger("procurawise.reports.worker")


def process_message(payload: dict[str, Any], *, report_service: ReportService) -> None:
    """Fase 23 (ADR 0001/0005): calls `reports.service` directly, never
    internal HTTP - same code path `reports.router` would call synchronously,
    run out-of-band instead (same shape as ai.worker.process_message)."""
    report_service.process_generation_job(
        tenant_id=payload["tenant_id"],
        evaluation_id=payload["evaluation_id"],
        report_id=payload["report_id"],
    )


def build_dispatch_table(
    report_service: ReportService,
) -> dict[str, Callable[[dict[str, Any]], None]]:
    return {JOB_TOPIC: lambda payload: process_message(payload, report_service=report_service)}
