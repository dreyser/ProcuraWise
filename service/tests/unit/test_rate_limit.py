"""Fase 26 (Hardening, plan Bloque 2) - shared/rate_limit.py. End-to-end
login lockout behavior (identity.auth_router.login /
identity.vendor_auth_router.vendor_login, both now inline endpoint-body
logic rather than a reusable dependency) is covered at the real-endpoint
level by tests/security/test_rate_limiting.py (docker-marked); this file
covers the underlying primitives directly, so none of it needs Mongo/Docker."""

import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient

from procurawise.shared.config import Settings, get_settings
from procurawise.shared.context import ActorContext
from procurawise.shared.rate_limit import (
    _FixedWindowRateLimiter,
    enforce_login_not_locked_out,
    enforce_rate_limit,
    rate_limit_by_tenant,
    record_login_failure,
    reset_rate_limits,
)


@pytest.fixture(autouse=True)
def _reset_shared_limiter() -> None:
    """`shared/rate_limit.py`'s `_limiter` is a process-wide singleton, not
    scoped to any one test's throwaway FastAPI app - without this, hit
    counts leak between the test functions below (several intentionally
    reuse the same bucket/email, e.g. the two rate_limit_login tests both
    use "a@example.com")."""
    reset_rate_limits()


def test_fixed_window_limiter_allows_up_to_the_limit_then_blocks() -> None:
    limiter = _FixedWindowRateLimiter()

    assert limiter.hit("key", max_requests=3, window_seconds=60) is True
    assert limiter.hit("key", max_requests=3, window_seconds=60) is True
    assert limiter.hit("key", max_requests=3, window_seconds=60) is True
    assert limiter.hit("key", max_requests=3, window_seconds=60) is False


def test_fixed_window_limiter_keys_are_independent() -> None:
    limiter = _FixedWindowRateLimiter()
    for _ in range(3):
        assert limiter.hit("key-a", max_requests=3, window_seconds=60) is True

    # A different key starts its own fresh window, unaffected by key-a's count.
    assert limiter.hit("key-b", max_requests=3, window_seconds=60) is True


def test_fixed_window_limiter_resets_after_the_window_elapses() -> None:
    limiter = _FixedWindowRateLimiter()
    assert limiter.hit("key", max_requests=1, window_seconds=0) is True
    # window_seconds=0 means "always expired" - every call starts a fresh window.
    assert limiter.hit("key", max_requests=1, window_seconds=0) is True


def test_enforce_rate_limit_raises_429_once_exceeded() -> None:
    key = "enforce-test-key"
    enforce_rate_limit(key, max_requests=1, window_seconds=60)
    try:
        enforce_rate_limit(key, max_requests=1, window_seconds=60)
        raise AssertionError("expected HTTPException")
    except HTTPException as exc:
        assert exc.status_code == 429


def test_enforce_login_not_locked_out_ignores_successes() -> None:
    """A successful login must never count toward its own account's
    lockout budget - this app's own E2E suite logs the same small, fixed
    roster of dev-seeded accounts in successfully dozens of times across
    its 18 specs, which an "every request counts" limiter would wrongly
    throttle. Only `record_login_failure` (called from the endpoint body's
    invalid-credentials branch) should ever move the counter."""
    key = "login:127.0.0.1:owner@example.com"
    for _ in range(10):
        enforce_login_not_locked_out(key, max_failures=1, window_seconds=3600)
        # No record_login_failure() call here - simulates 10 successful logins.


def test_enforce_login_not_locked_out_blocks_after_recorded_failures() -> None:
    key = "login:127.0.0.1:attacker@example.com"
    enforce_login_not_locked_out(key, max_failures=2, window_seconds=3600)
    record_login_failure(key, window_seconds=3600)
    enforce_login_not_locked_out(key, max_failures=2, window_seconds=3600)
    record_login_failure(key, window_seconds=3600)

    try:
        enforce_login_not_locked_out(key, max_failures=2, window_seconds=3600)
        raise AssertionError("expected HTTPException")
    except HTTPException as exc:
        assert exc.status_code == 429


def test_enforce_login_not_locked_out_scopes_independently_per_key() -> None:
    """A blanket per-IP counter would also block legitimate rapid logins
    into many *different* accounts from the same network - keying by (IP,
    email), as identity.auth_router.login does when it builds this
    function's `key`, is what keeps a second account's budget independent
    of a first account's exhausted one."""
    key_a = "login:127.0.0.1:a@example.com"
    key_b = "login:127.0.0.1:b@example.com"
    record_login_failure(key_a, window_seconds=3600)

    try:
        enforce_login_not_locked_out(key_a, max_failures=1, window_seconds=3600)
        raise AssertionError("expected HTTPException")
    except HTTPException as exc:
        assert exc.status_code == 429

    # A different key (different email) is unaffected.
    enforce_login_not_locked_out(key_b, max_failures=1, window_seconds=3600)


def test_rate_limit_by_tenant_blocks_after_max_requests_for_same_tenant() -> None:
    app = FastAPI()

    def fake_auth() -> ActorContext:
        return ActorContext(
            membership_id="m1",
            user_id="u1",
            tenant_id="tenant-x",
            tenant_name="Tenant X",
            role="evaluation_owner",
            vendor_org_id=None,
            display_name="Owner",
        )

    dependency = rate_limit_by_tenant("tenant-bucket", lambda s: 2, lambda s: 3600, fake_auth)

    @app.get("/trigger")
    def trigger(_: None = Depends(dependency)) -> dict[str, str]:
        return {"status": "ok"}

    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None)
    client = TestClient(app)

    assert client.get("/trigger").status_code == 200
    assert client.get("/trigger").status_code == 200
    assert client.get("/trigger").status_code == 429


def test_rate_limit_by_tenant_never_trusts_a_client_supplied_tenant_id() -> None:
    """The dependency's key comes exclusively from the server-resolved
    ActorContext returned by `auth_dependency` - there is no request
    parameter it could read a client-supplied tenant_id from at all."""
    app = FastAPI()

    def fake_auth() -> ActorContext:
        return ActorContext(
            membership_id="m1",
            user_id="u1",
            tenant_id="real-tenant",
            tenant_name="Real Tenant",
            role="tenant_admin",
            vendor_org_id=None,
            display_name="Admin",
        )

    dependency = rate_limit_by_tenant("tenant-bucket-2", lambda s: 1, lambda s: 3600, fake_auth)

    @app.get("/checkout")
    def checkout(_: None = Depends(dependency)) -> dict[str, str]:
        return {"status": "ok"}

    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None)
    client = TestClient(app)
    # A forged header claiming a different tenant has no effect - the key is
    # always the resolved ActorContext.tenant_id.
    assert client.get("/checkout", headers={"X-Tenant-Id": "spoofed-tenant"}).status_code == 200
    assert client.get("/checkout", headers={"X-Tenant-Id": "spoofed-tenant"}).status_code == 429
