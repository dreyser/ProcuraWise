"""Fase 26 (Hardening, plan Bloque 2): in-process rate limiting, no Redis.

ADR 0020 retired Redis from the local/dev architecture ("reintroducirlo
requiere justificación propia"), and NFR-003 (50 concurrent users, global,
not per-tenant) does not constitute that justification - see plan Decisión
recomendada #2. A single fixed-window counter, guarded by a lock, lives in
process memory. It does not coordinate across multiple API replicas; that is
an accepted, documented limitation (threat-model.md) while Azure Container
Apps runs a single replica (Fase 27 has not provisioned real infra yet) -
revisit if a future deployment scales out under load that would exploit
this gap.
"""

import threading
import time
from collections.abc import Callable

from fastapi import Depends, HTTPException

from procurawise.shared.config import Settings, get_settings
from procurawise.shared.context import ActorContext


class _FixedWindowRateLimiter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._windows: dict[str, tuple[int, float]] = {}

    def hit(self, key: str, max_requests: int, window_seconds: int) -> bool:
        """Records one request against `key` and returns whether it is
        allowed (True) or exceeds `max_requests` within the current
        `window_seconds` window (False)."""
        now = time.monotonic()
        with self._lock:
            count, window_start = self._windows.get(key, (0, now))
            if now - window_start >= window_seconds:
                count, window_start = 0, now
            count += 1
            self._windows[key] = (count, window_start)
        return count <= max_requests

    def count(self, key: str, window_seconds: int) -> int:
        """Current count within the active window, *without* recording a
        new hit - used by the login-failure counter below, where whether a
        given call counts as a hit at all depends on something (credential
        validity) not known until after this check has already happened."""
        now = time.monotonic()
        with self._lock:
            count, window_start = self._windows.get(key, (0, now))
            if now - window_start >= window_seconds:
                return 0
            return count

    def record(self, key: str, window_seconds: int) -> None:
        """Records one hit against `key`, independent of any threshold."""
        now = time.monotonic()
        with self._lock:
            count, window_start = self._windows.get(key, (0, now))
            if now - window_start >= window_seconds:
                count, window_start = 0, now
            self._windows[key] = (count + 1, window_start)


# Module-level singleton, deliberately not per-request - the whole point is
# to remember state *across* requests within this process.
_limiter = _FixedWindowRateLimiter()


def reset_rate_limits() -> None:
    """Test-only escape hatch (tests/conftest.py's `client` fixture calls
    this before every test) - without it, the process-wide singleton above
    would leak hit counts between unrelated test functions sharing the same
    pytest session (e.g. test_auth_router.py alone calls /auth/login more
    than rate_limit_login_max_attempts times across its own test functions),
    causing spurious 429s unrelated to what any single test is verifying."""
    with _limiter._lock:
        _limiter._windows.clear()


def enforce_rate_limit(key: str, max_requests: int, window_seconds: int) -> None:
    if not _limiter.hit(key, max_requests, window_seconds):
        raise HTTPException(status_code=429, detail="rate limit exceeded")


def enforce_login_not_locked_out(key: str, max_failures: int, window_seconds: int) -> None:
    """Login-specific: checks *without* recording a hit - a request only
    counts toward lockout if the credentials it carries turn out to be
    wrong (see `record_login_failure` below, called from the endpoint body
    after the actual check). A blanket "every request counts" limiter
    (`enforce_rate_limit` above) is the wrong shape for login specifically:
    it would also throttle a legitimate account logging in successfully
    many times in a row (this app's own E2E suite does exactly that -
    dev_seed.py's small, fixed roster of named accounts gets reused across
    most of its 18 specs), while a real brute force is characterized by
    repeated *failures*, not successes."""
    if _limiter.count(key, window_seconds) >= max_failures:
        raise HTTPException(status_code=429, detail="rate limit exceeded")


def record_login_failure(key: str, window_seconds: int) -> None:
    _limiter.record(key, window_seconds)


def rate_limit_by_tenant(
    bucket: str,
    max_requests: Callable[[Settings], int],
    window_seconds: Callable[[Settings], int],
    auth_dependency: Callable[..., ActorContext],
) -> Callable[..., None]:
    """Dependency factory for authenticated endpoints (AI triggers, billing
    checkout) - keyed by the server-resolved `tenant_id`, never a
    client-supplied value (CLAUDE.md S4). `auth_dependency` should be the
    exact same `require_*` callable the endpoint itself already depends on
    (e.g. `require_owner`) so FastAPI's per-request dependency cache
    resolves it once, not twice."""

    def _dependency(
        context: ActorContext = Depends(auth_dependency),
        settings: Settings = Depends(get_settings),
    ) -> None:
        enforce_rate_limit(
            f"{bucket}:{context.tenant_id}", max_requests(settings), window_seconds(settings)
        )

    return _dependency
