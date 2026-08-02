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


_VALID_PRODUCTION_AUTH_OVERRIDES = {
    "jwt_secret": "x" * 32,
    "oidc_microsoft_client_id": "mid",
    "oidc_microsoft_client_secret": "msecret",
    "oidc_google_client_id": "gid",
    "oidc_google_client_secret": "gsecret",
    "azure_openai_endpoint": "https://example.openai.azure.com",
    "azure_openai_api_key": "aikey",
    "azure_openai_deployment": "gpt-test-deployment",
}


def test_settings_production_rejects_memory_queue() -> None:
    # Valid auth config alongside, so only the queue-backend check is
    # exercised here - the auth validator has its own tests below.
    with pytest.raises(ValidationError, match="queue_backend=memory"):
        Settings(
            _env_file=None,
            environment="production",
            queue_backend="memory",
            **_VALID_PRODUCTION_AUTH_OVERRIDES,
        )


def test_settings_production_allows_service_bus_queue() -> None:
    settings = Settings(
        _env_file=None,
        environment="production",
        queue_backend="service_bus",
        **_VALID_PRODUCTION_AUTH_OVERRIDES,
    )
    assert settings.queue_backend == "service_bus"


def test_settings_local_allows_default_jwt_secret() -> None:
    settings = Settings(_env_file=None)
    assert settings.jwt_secret  # default present, no error outside production


def test_settings_production_rejects_default_jwt_secret() -> None:
    overrides = {**_VALID_PRODUCTION_AUTH_OVERRIDES}
    del overrides["jwt_secret"]
    with pytest.raises(ValidationError, match="jwt_secret"):
        Settings(_env_file=None, environment="production", queue_backend="service_bus", **overrides)


def test_settings_production_rejects_short_jwt_secret() -> None:
    overrides = {**_VALID_PRODUCTION_AUTH_OVERRIDES, "jwt_secret": "too-short"}
    with pytest.raises(ValidationError, match="jwt_secret"):
        Settings(_env_file=None, environment="production", queue_backend="service_bus", **overrides)


def test_settings_production_requires_oidc_credentials() -> None:
    with pytest.raises(ValidationError, match="oidc"):
        Settings(
            _env_file=None,
            environment="production",
            queue_backend="service_bus",
            jwt_secret="x" * 32,
        )


def test_settings_local_allows_missing_azure_openai_config() -> None:
    settings = Settings(_env_file=None)
    assert settings.azure_openai_endpoint is None
    assert settings.azure_openai_api_key is None
    assert settings.azure_openai_deployment is None


def test_settings_production_requires_azure_openai_config() -> None:
    overrides = {**_VALID_PRODUCTION_AUTH_OVERRIDES}
    del overrides["azure_openai_endpoint"]
    del overrides["azure_openai_api_key"]
    del overrides["azure_openai_deployment"]
    with pytest.raises(ValidationError, match="Azure OpenAI"):
        Settings(_env_file=None, environment="production", queue_backend="service_bus", **overrides)


def test_settings_production_allows_complete_azure_openai_config() -> None:
    settings = Settings(
        _env_file=None,
        environment="production",
        queue_backend="service_bus",
        **_VALID_PRODUCTION_AUTH_OVERRIDES,
    )
    assert settings.azure_openai_deployment == "gpt-test-deployment"


# Fase 14 (ResearchProvider completo, ADR 0011): FoundryWebSearchProvider
# stays off by default in every environment - the fail-closed gate below
# runs regardless of `environment`, unlike the azure_openai/oidc validators
# above which only fire in production.


def test_settings_foundry_disabled_by_default() -> None:
    settings = Settings(_env_file=None)
    assert settings.foundry_web_search_enabled is False
    assert settings.foundry_legal_approval_reference is None


def test_settings_local_allows_foundry_disabled_with_no_other_config() -> None:
    settings = Settings(_env_file=None, environment="local")
    assert settings.foundry_web_search_enabled is False


def test_settings_rejects_foundry_enabled_with_no_other_config_in_any_environment() -> None:
    with pytest.raises(ValidationError, match="foundry_web_search_enabled=true"):
        Settings(_env_file=None, environment="local", foundry_web_search_enabled=True)


def test_settings_rejects_foundry_enabled_missing_approval_reference_in_production() -> None:
    overrides = {**_VALID_PRODUCTION_AUTH_OVERRIDES}
    with pytest.raises(ValidationError, match="foundry_legal_approval_reference"):
        Settings(
            _env_file=None,
            environment="production",
            queue_backend="service_bus",
            foundry_web_search_enabled=True,
            foundry_web_search_endpoint="https://example.services.ai.azure.com/api/projects/p",
            foundry_web_search_agent_name="agent",
            **overrides,
        )


def test_settings_rejects_foundry_enabled_missing_endpoint() -> None:
    with pytest.raises(ValidationError, match="foundry_web_search_endpoint"):
        Settings(
            _env_file=None,
            foundry_web_search_enabled=True,
            foundry_legal_approval_reference="LEGAL-2026-001",
            foundry_web_search_agent_name="agent",
        )


def test_settings_rejects_foundry_enabled_missing_agent_name() -> None:
    with pytest.raises(ValidationError, match="foundry_web_search_agent_name"):
        Settings(
            _env_file=None,
            foundry_web_search_enabled=True,
            foundry_legal_approval_reference="LEGAL-2026-001",
            foundry_web_search_endpoint="https://example.services.ai.azure.com/api/projects/p",
        )


def test_settings_allows_foundry_enabled_with_complete_config() -> None:
    settings = Settings(
        _env_file=None,
        foundry_web_search_enabled=True,
        foundry_legal_approval_reference="LEGAL-2026-001",
        foundry_web_search_endpoint="https://example.services.ai.azure.com/api/projects/p",
        foundry_web_search_agent_name="agent",
    )
    assert settings.foundry_web_search_enabled is True
