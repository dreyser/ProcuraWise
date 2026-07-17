import pytest
from pydantic import ValidationError

from procurawise.shared.config import Settings


def test_settings_defaults() -> None:
    settings = Settings(_env_file=None)
    assert settings.environment == "local"
    assert settings.log_level == "info"
    assert settings.mongodb_uri == "mongodb://localhost:27017"
    assert settings.mongodb_db_name == "procurawise_local"
    assert settings.storage_connection_string == "UseDevelopmentStorage=true"
    assert settings.storage_api_version == "2025-01-05"
    assert settings.queue_backend == "memory"


def test_settings_reads_env_override(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "test")
    settings = Settings(_env_file=None)
    assert settings.environment == "test"


def test_settings_storage_api_version_env_override(monkeypatch) -> None:
    monkeypatch.setenv("AZURE_STORAGE_API_VERSION", "2024-08-04")
    settings = Settings(_env_file=None)
    assert settings.storage_api_version == "2024-08-04"


def test_settings_storage_api_version_can_be_set_by_field_name() -> None:
    # populate_by_name=True: direct construction (as used by tests/fixtures) still
    # works via the Python field name, not just the AZURE_STORAGE_API_VERSION alias.
    settings = Settings(_env_file=None, storage_api_version="2024-08-04")
    assert settings.storage_api_version == "2024-08-04"


def test_settings_production_rejects_memory_queue() -> None:
    with pytest.raises(ValidationError, match="queue_backend=memory"):
        Settings(_env_file=None, environment="production", queue_backend="memory")


def test_settings_production_allows_service_bus_queue() -> None:
    settings = Settings(_env_file=None, environment="production", queue_backend="service_bus")
    assert settings.queue_backend == "service_bus"
