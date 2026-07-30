from contextvars import ContextVar
from uuid import uuid4

# Request-scoped correlation id (plan §7/§18 risk mitigation): no request-id
# middleware existed anywhere in the app before Fase 8. Set once per request
# by api.main's CorrelationIdMiddleware, read by audit.service when recording
# an AuditEvent - a plain module-level ContextVar is enough here (single
# ASGI process, no cross-process propagation needed in this phase).
_correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)


def new_correlation_id() -> str:
    return uuid4().hex


def set_correlation_id(value: str) -> None:
    _correlation_id.set(value)


def get_correlation_id() -> str | None:
    return _correlation_id.get()
