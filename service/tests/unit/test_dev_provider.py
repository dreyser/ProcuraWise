import pytest
from fastapi import HTTPException

from procurawise.identity.dev_provider import require_dev_environment
from procurawise.shared.config import Settings


def test_require_dev_environment_allows_local() -> None:
    require_dev_environment(Settings(_env_file=None, environment="local"))


def test_require_dev_environment_allows_test() -> None:
    require_dev_environment(Settings(_env_file=None, environment="test"))


def test_require_dev_environment_rejects_production() -> None:
    # Valid auth config alongside queue_backend=service_bus - this test only
    # exercises require_dev_environment(), not Settings' own production
    # validators (see test_config.py for those).
    settings = Settings(
        _env_file=None,
        environment="production",
        queue_backend="service_bus",
        jwt_secret="x" * 32,
        oidc_microsoft_client_id="mid",
        oidc_microsoft_client_secret="msecret",
        oidc_google_client_id="gid",
        oidc_google_client_secret="gsecret",
        azure_openai_endpoint="https://example.openai.azure.com",
        azure_openai_api_key="aikey",
        azure_openai_deployment="gpt-test-deployment",
    )
    with pytest.raises(HTTPException) as exc_info:
        require_dev_environment(settings)
    assert exc_info.value.status_code == 404
