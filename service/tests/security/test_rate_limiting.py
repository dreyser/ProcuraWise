"""Fase 26 (Hardening, plan Bloque 2) - rate limiting end-to-end against the
real routers (identity/auth_router.py, ai/router.py, billing/router.py),
not just the unit-level dependency factories covered by
tests/unit/test_rate_limit.py."""

import time

import pytest

from procurawise.api.main import app
from procurawise.dev_seed import DEV_BUYER_PASSWORD
from procurawise.shared.config import Settings, get_settings
from tests.conftest import TEST_MONGO_DB_NAME, bearer_headers_for, unique_actor_by_role

VENDOR_A_EMAIL = "vendor.a@dev.procurawise.local"

pytestmark = pytest.mark.docker


def test_login_brute_force_returns_429_after_max_attempts(client) -> None:
    """Uses the real default (rate_limit_login_max_attempts=5) - the client
    fixture resets the limiter before this test runs (tests/conftest.py)."""
    for _ in range(5):
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "owner.a@dev.procurawise.local", "password": "wrong-password"},
        )
        assert response.status_code == 401

    blocked = client.post(
        "/api/v1/auth/login",
        json={"email": "owner.a@dev.procurawise.local", "password": "wrong-password"},
    )
    assert blocked.status_code == 429


def test_login_rate_limit_is_scoped_by_email_not_just_ip(client) -> None:
    """Exhausting the limit against one account from this IP must not block
    a *different* account from the same IP - a blanket per-IP-only counter
    would also throttle legitimate rapid logins into many different
    accounts sharing one network (this app routinely has several
    roles/tenants doing exactly that; its own E2E suite alone drives 30+
    logins across distinct accounts within a few minutes)."""
    for _ in range(5):
        client.post(
            "/api/v1/auth/login",
            json={"email": "owner.a@dev.procurawise.local", "password": "wrong-password"},
        )
    still_blocked_for_owner_a = client.post(
        "/api/v1/auth/login",
        json={"email": "owner.a@dev.procurawise.local", "password": "wrong-password"},
    )
    assert still_blocked_for_owner_a.status_code == 429

    still_allowed_for_owner_b = client.post(
        "/api/v1/auth/login",
        json={"email": "owner.b@dev.procurawise.local", "password": DEV_BUYER_PASSWORD},
    )
    assert still_allowed_for_owner_b.status_code == 200


def test_vendor_login_brute_force_returns_429_after_max_attempts(client) -> None:
    """Same defense as buyer login (identity.auth_router.rate_limit_login),
    applied to the separate vendor-auth endpoint/credential
    (identity.vendor_auth_router.rate_limit_vendor_login)."""
    for _ in range(5):
        response = client.post(
            "/api/v1/vendor-auth/login",
            json={"email": VENDOR_A_EMAIL, "password": "wrong-password"},
        )
        assert response.status_code == 401

    blocked = client.post(
        "/api/v1/vendor-auth/login",
        json={"email": VENDOR_A_EMAIL, "password": "wrong-password"},
    )
    assert blocked.status_code == 429


@pytest.fixture
def tight_login_window_settings() -> Settings:
    return Settings(
        _env_file=None,
        mongodb_db_name=TEST_MONGO_DB_NAME,
        rate_limit_login_max_attempts=1,
        rate_limit_login_window_seconds=1,
    )


def test_login_rate_limit_resets_after_the_window_elapses(
    client, tight_login_window_settings
) -> None:
    app.dependency_overrides[get_settings] = lambda: tight_login_window_settings
    try:
        first = client.post(
            "/api/v1/auth/login",
            json={"email": "owner.a@dev.procurawise.local", "password": "wrong-password"},
        )
        assert first.status_code == 401

        second = client.post(
            "/api/v1/auth/login",
            json={"email": "owner.a@dev.procurawise.local", "password": "wrong-password"},
        )
        assert second.status_code == 429

        time.sleep(1.1)

        third = client.post(
            "/api/v1/auth/login",
            json={"email": "owner.a@dev.procurawise.local", "password": "wrong-password"},
        )
        assert third.status_code == 401
    finally:
        del app.dependency_overrides[get_settings]


@pytest.fixture
def tight_ai_rate_limit_settings() -> Settings:
    return Settings(
        _env_file=None,
        mongodb_db_name=TEST_MONGO_DB_NAME,
        rate_limit_ai_max_requests=1,
        rate_limit_ai_window_seconds=3600,
    )


def test_ai_trigger_rate_limit_is_scoped_by_tenant(
    client, tight_ai_rate_limit_settings, seeded_actors, mongo_test_settings
) -> None:
    tenant_a, _tenant_b = unique_actor_by_role(seeded_actors, "evaluator_functional")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    created = client.post(
        "/api/v1/evaluations", json={"name": "RFP", "description": ""}, headers=owner_headers
    )
    assert created.status_code == 201
    evaluation_id = created.json()["id"]

    app.dependency_overrides[get_settings] = lambda: tight_ai_rate_limit_settings
    try:
        first = client.post(
            f"/api/v1/evaluations/{evaluation_id}/ai/requirement-suggestions",
            json={"dimension": "functional", "description": "We need reporting"},
            headers=owner_headers,
        )
        assert first.status_code == 202

        second = client.post(
            f"/api/v1/evaluations/{evaluation_id}/ai/requirement-suggestions",
            json={"dimension": "functional", "description": "We need reporting"},
            headers=owner_headers,
        )
        assert second.status_code == 429
    finally:
        del app.dependency_overrides[get_settings]


@pytest.fixture
def tight_billing_rate_limit_settings() -> Settings:
    return Settings(
        _env_file=None,
        mongodb_db_name=TEST_MONGO_DB_NAME,
        rate_limit_billing_checkout_max_requests=1,
        rate_limit_billing_checkout_window_seconds=3600,
    )


def test_billing_checkout_rate_limit_is_scoped_by_tenant(
    client, tight_billing_rate_limit_settings, seeded_actors, mongo_test_settings
) -> None:
    tenant_a, _tenant_b = unique_actor_by_role(seeded_actors, "tenant_admin")
    admin_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "tenant_admin")], mongo_test_settings
    )
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    created = client.post(
        "/api/v1/evaluations", json={"name": "RFP", "description": ""}, headers=owner_headers
    )
    assert created.status_code == 201
    evaluation_id = created.json()["id"]

    app.dependency_overrides[get_settings] = lambda: tight_billing_rate_limit_settings
    try:
        first = client.post(
            "/api/v1/billing/checkout-sessions",
            json={"evaluation_id": evaluation_id},
            headers=admin_headers,
        )
        assert first.status_code == 201

        second = client.post(
            "/api/v1/billing/checkout-sessions",
            json={"evaluation_id": evaluation_id},
            headers=admin_headers,
        )
        assert second.status_code == 429
    finally:
        del app.dependency_overrides[get_settings]
