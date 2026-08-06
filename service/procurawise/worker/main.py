import logging

from procurawise.ai.provider import resolve_ai_provider
from procurawise.ai.service import build_ai_service
from procurawise.ai.worker import build_dispatch_table as build_ai_dispatch_table
from procurawise.reports.dependencies import build_report_service
from procurawise.reports.worker import build_dispatch_table as build_reports_dispatch_table
from procurawise.shared.config import get_settings
from procurawise.shared.logging import configure_logging
from procurawise.shared.messaging import get_message_bus
from procurawise.shared.worker_loop import run_worker_loop

logger = logging.getLogger("procurawise.worker")


def main() -> None:
    """Fase 13 (ADR 0021): the first real dispatch table (generalized to an
    actual `{topic: handler}` mapping in Fase 18/ADR 0022, once a second job
    type existed - see ai.worker.build_dispatch_table). Fase 23 (reports)
    adds a second *module's* dispatch table, merged here into one - the
    generic loop itself moved to shared.worker_loop so this composition root
    is the only place that needs to know about every job-producing module
    (ai.worker.run_worker_loop is untouched and still directly tested; it is
    simply no longer this process's entrypoint). `queue_backend` (memory/
    service_bus) picks the `MessageBus` implementation via `get_message_bus`
    - in local dev with the default `memory` backend, this process's
    InMemoryMessageBus is process-local and will never see anything the API
    process published (ADR 0020); use `queue_backend=service_bus` + `make
    dev-up-servicebus` to exercise the AI/reports features end-to-end
    locally."""
    settings = get_settings()
    configure_logging(settings)

    message_bus = get_message_bus(settings)
    ai_service = build_ai_service(settings, resolve_ai_provider(settings))
    report_service = build_report_service(settings)
    dispatch = {
        **build_ai_dispatch_table(ai_service),
        **build_reports_dispatch_table(report_service),
    }
    logger.info(
        "worker ready (environment=%s, queue_backend=%s) - dispatching topics: %s",
        settings.environment,
        settings.queue_backend,
        sorted(dispatch),
    )
    run_worker_loop(message_bus, dispatch)


if __name__ == "__main__":
    main()
