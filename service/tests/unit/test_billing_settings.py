"""Fase 25 (billing/admin, ADR 0025) - Settings validators: production
requires the three Stripe credentials only when billing_enabled=true (same
prod-only-when-enabled shape as notifications), and a non-sk_test_ secret key
is rejected outside production regardless of billing_enabled."""

import pytest
from pydantic import ValidationError

from procurawise.shared.config import Settings

# Everything else _require_real_*_config_in_production/
# _reject_memory_queue_in_production needs, so only the billing validator
# under test is actually exercised - mirrors test_config.py's
# _VALID_PRODUCTION_AUTH_OVERRIDES.
_VALID_PRODUCTION_OVERRIDES = {
    "queue_backend": "service_bus",
    "jwt_secret": "x" * 32,
    "oidc_microsoft_client_id": "mid",
    "oidc_microsoft_client_secret": "msecret",
    "oidc_google_client_id": "gid",
    "oidc_google_client_secret": "gsecret",
    "azure_openai_endpoint": "https://example.openai.azure.com",
    "azure_openai_api_key": "aikey",
    "azure_openai_deployment": "gpt-test-deployment",
}


def test_billing_disabled_never_requires_stripe_credentials_in_production() -> None:
    Settings(
        _env_file=None,
        environment="production",
        billing_enabled=False,
        **_VALID_PRODUCTION_OVERRIDES,
    )


def test_billing_enabled_requires_all_three_stripe_credentials_in_production() -> None:
    with pytest.raises(ValidationError, match="faltan credenciales de Stripe"):
        Settings(
            _env_file=None,
            environment="production",
            billing_enabled=True,
            **_VALID_PRODUCTION_OVERRIDES,
        )


def test_billing_enabled_with_full_config_is_accepted_in_production() -> None:
    settings = Settings(
        _env_file=None,
        environment="production",
        billing_enabled=True,
        stripe_secret_key="sk_live_1",
        stripe_webhook_secret="whsec_1",
        stripe_price_id_evaluation="price_1",
        **_VALID_PRODUCTION_OVERRIDES,
    )
    assert settings.stripe_secret_key == "sk_live_1"


def test_non_sk_test_secret_key_is_rejected_outside_production() -> None:
    with pytest.raises(ValidationError, match="sk_test_"):
        Settings(_env_file=None, environment="local", stripe_secret_key="sk_live_leaked")


def test_sk_test_secret_key_is_accepted_outside_production() -> None:
    settings = Settings(_env_file=None, environment="local", stripe_secret_key="sk_test_fine")
    assert settings.stripe_secret_key == "sk_test_fine"


def test_sk_live_secret_key_is_accepted_in_production() -> None:
    settings = Settings(
        _env_file=None,
        environment="production",
        billing_enabled=True,
        stripe_secret_key="sk_live_1",
        stripe_webhook_secret="whsec_1",
        stripe_price_id_evaluation="price_1",
        **_VALID_PRODUCTION_OVERRIDES,
    )
    assert settings.stripe_secret_key == "sk_live_1"


def test_billing_disabled_by_default_outside_production() -> None:
    settings = Settings(_env_file=None)
    assert settings.billing_enabled is False
    assert settings.stripe_secret_key is None
