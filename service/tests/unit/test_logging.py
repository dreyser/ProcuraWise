import json
import logging

from procurawise.shared.config import Settings
from procurawise.shared.logging import configure_logging


def test_configure_logging_emits_json_lines(capsys) -> None:
    configure_logging(Settings(_env_file=None, log_level="info"))
    logging.getLogger("procurawise.test").info("hello world", extra={"foo": "bar"})

    line = capsys.readouterr().out.strip()
    payload = json.loads(line)

    assert payload["message"] == "hello world"
    assert payload["level"] == "INFO"
    assert payload["logger"] == "procurawise.test"
    assert payload["foo"] == "bar"
    assert "timestamp" in payload


def test_configure_logging_never_logs_raw_connection_strings(capsys) -> None:
    settings = Settings(
        _env_file=None,
        mongodb_uri="mongodb://localhost:27017",
        storage_connection_string="UseDevelopmentStorage=true",
    )
    configure_logging(settings)
    logger = logging.getLogger("procurawise.test")

    logger.info("connecting to mongo")
    logger.info("connecting to blob storage")

    output = capsys.readouterr().out
    assert settings.mongodb_uri not in output
    assert settings.storage_connection_string not in output
