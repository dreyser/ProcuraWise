import pytest

from procurawise.shared.config import Settings
from procurawise.shared.storage import AzureBlobStorage

# Connection-string parsing/client construction happens fully offline in the SDK -
# no network call is made until an actual operation (upload/download/ping/...) runs.
# Safe to exercise without Docker/Azurite.
_LOCAL_CONNECTION_STRING = "UseDevelopmentStorage=true"


def test_from_settings_uses_configured_api_version() -> None:
    settings = Settings(_env_file=None, storage_api_version="2025-01-05")
    storage = AzureBlobStorage.from_settings(settings)

    assert storage._service_client.api_version == "2025-01-05"  # noqa: SLF001
    assert storage._container_client.api_version == "2025-01-05"  # noqa: SLF001


def test_from_settings_respects_env_override(monkeypatch) -> None:
    monkeypatch.setenv("AZURE_STORAGE_API_VERSION", "2024-08-04")
    settings = Settings(_env_file=None)
    storage = AzureBlobStorage.from_settings(settings)

    assert storage._service_client.api_version == "2024-08-04"  # noqa: SLF001


def test_exists_blob_client_inherits_configured_api_version() -> None:
    storage = AzureBlobStorage(
        connection_string=_LOCAL_CONNECTION_STRING,
        container_name="procurawise-test",
        api_version="2025-01-05",
    )
    blob_client = storage._container_client.get_blob_client("some-blob")  # noqa: SLF001

    assert blob_client.api_version == "2025-01-05"


def test_unsupported_api_version_error_does_not_leak_connection_string() -> None:
    with pytest.raises(ValueError) as exc_info:
        AzureBlobStorage(
            connection_string=_LOCAL_CONNECTION_STRING,
            container_name="procurawise-test",
            api_version="not-a-real-version",
        )

    assert _LOCAL_CONNECTION_STRING not in str(exc_info.value)
    assert "AccountKey" not in str(exc_info.value)
