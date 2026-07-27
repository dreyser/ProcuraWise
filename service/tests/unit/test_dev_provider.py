import pytest
from fastapi import HTTPException

from procurawise.identity.dev_provider import require_dev_environment
from procurawise.shared.config import Settings


def test_require_dev_environment_allows_local() -> None:
    require_dev_environment(Settings(_env_file=None, environment="local"))


def test_require_dev_environment_allows_test() -> None:
    require_dev_environment(Settings(_env_file=None, environment="test"))


def test_require_dev_environment_rejects_production() -> None:
    settings = Settings(_env_file=None, environment="production", queue_backend="service_bus")
    with pytest.raises(HTTPException) as exc_info:
        require_dev_environment(settings)
    assert exc_info.value.status_code == 404
