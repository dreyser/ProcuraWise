import logging

from procurawise.shared.config import get_settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("procurawise.worker")


def main() -> None:
    settings = get_settings()
    logger.info(
        "worker ready (environment=%s) - no queue backend configured in this phase, exiting",
        settings.environment,
    )


if __name__ == "__main__":
    main()
