import logging

from procurawise.shared.config import get_settings
from procurawise.shared.logging import configure_logging
from procurawise.shared.messaging import InMemoryMessageBus

logger = logging.getLogger("procurawise.worker")


def main() -> None:
    settings = get_settings()
    configure_logging(settings)

    # InMemoryMessageBus here only proves the MessageBus protocol wiring - it is
    # process-local, so it never receives anything published by the API process.
    # A real dispatch table arrives with the first async job (Fase 13+).
    InMemoryMessageBus()
    logger.info(
        "worker ready (environment=%s, queue_backend=%s) - no jobs dispatched in this phase",
        settings.environment,
        settings.queue_backend,
    )


if __name__ == "__main__":
    main()
