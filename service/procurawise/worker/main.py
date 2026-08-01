import logging

from procurawise.ai.provider import resolve_ai_provider
from procurawise.ai.service import build_ai_service
from procurawise.ai.worker import run_worker_loop
from procurawise.shared.config import get_settings
from procurawise.shared.logging import configure_logging
from procurawise.shared.messaging import get_message_bus

logger = logging.getLogger("procurawise.worker")


def main() -> None:
    """Fase 13 (ADR 0021): the first real dispatch table. `queue_backend`
    (memory/service_bus) picks the `MessageBus` implementation via
    `get_message_bus` - in local dev with the default `memory` backend, this
    process's InMemoryMessageBus is process-local and will never see
    anything the API process published (ADR 0020); use `queue_backend=
    service_bus` + `make dev-up-servicebus` to exercise the AI feature
    end-to-end locally."""
    settings = get_settings()
    configure_logging(settings)

    message_bus = get_message_bus(settings)
    ai_service = build_ai_service(settings, resolve_ai_provider(settings))
    logger.info(
        "worker ready (environment=%s, queue_backend=%s) - dispatching "
        "ai-requirement-generation jobs",
        settings.environment,
        settings.queue_backend,
    )
    run_worker_loop(message_bus, ai_service)


if __name__ == "__main__":
    main()
