import base64
import json
import logging
from datetime import datetime
from typing import Any

from procurawise.audit.models import AuditAction, AuditEvent, AuditResourceType
from procurawise.audit.repository import AuditEventRepository
from procurawise.shared.config import Settings
from procurawise.shared.context import ActorContext
from procurawise.shared.request_context import get_correlation_id

logger = logging.getLogger("procurawise.audit")


class InvalidAuditEventCursorError(Exception):
    """The `cursor` query param is not a value this endpoint produced."""


def _encode_cursor(occurred_at: datetime, event_id: str) -> str:
    payload = json.dumps([occurred_at.isoformat(), event_id]).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii")


def _decode_cursor(cursor: str) -> tuple[datetime, str]:
    try:
        payload = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
        data = json.loads(payload)
        if (
            not isinstance(data, list)
            or len(data) != 2
            or not all(isinstance(part, str) for part in data)
        ):
            raise ValueError("malformed cursor payload")
        occurred_at = datetime.fromisoformat(data[0])
    except Exception as exc:
        raise InvalidAuditEventCursorError(cursor) from exc
    return occurred_at, data[1]


class AuditEventService:
    """The single point of contact between business services and the audit
    trail (plan §9/§18.1). `record()` never raises: a failure to persist the
    AuditEvent is logged as a structured ERROR and swallowed, so the business
    mutation that already succeeded is never rolled back or reported as
    failed because of an audit-write problem. This is a deliberate,
    founder-approved best-effort guarantee, not an oversight - every module
    that instruments a mutation (evaluations/proposals/scoring) calls this
    same method rather than handling audit failures itself."""

    def __init__(self, repository: AuditEventRepository, settings: Settings) -> None:
        self._repository = repository
        self._settings = settings

    def record(
        self,
        *,
        tenant_id: str,
        actor: ActorContext,
        action: AuditAction,
        resource_type: AuditResourceType,
        resource_id: str,
        evaluation_id: str | None = None,
        proposal_id: str | None = None,
        snapshot_id: str | None = None,
        version: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        correlation_id = get_correlation_id()
        try:
            event = AuditEvent.create(
                tenant_id=tenant_id,
                actor=actor,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                evaluation_id=evaluation_id,
                proposal_id=proposal_id,
                snapshot_id=snapshot_id,
                version=version,
                correlation_id=correlation_id,
                metadata=metadata,
                retention_days=self._settings.audit_event_retention_days,
            )
            self._repository.record(tenant_id, event.to_document())
        except Exception:  # noqa: BLE001 - best-effort audit write, plan §18.1
            logger.error(
                "audit_event_record_failed",
                extra={
                    "tenant_id": tenant_id,
                    "actor_id": actor.membership_id,
                    "action": action,
                    "resource_type": resource_type,
                    "resource_id": resource_id,
                    "correlation_id": correlation_id,
                },
                exc_info=True,
            )

    def list_for_evaluation(
        self, tenant_id: str, evaluation_id: str, *, limit: int, cursor: str | None
    ) -> tuple[list[AuditEvent], str | None]:
        decoded_cursor = _decode_cursor(cursor) if cursor else None
        docs = self._repository.list_for_evaluation(
            tenant_id, evaluation_id, limit=limit, cursor=decoded_cursor
        )
        events = [AuditEvent.from_document(doc) for doc in docs[:limit]]
        next_cursor = (
            _encode_cursor(events[-1].occurred_at, events[-1].id) if len(docs) > limit else None
        )
        return events, next_cursor
