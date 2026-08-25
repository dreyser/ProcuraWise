import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

# Fase 24 (backlog.md fila 24, spec S11, plan Bloqueante #1 Opcion A): 8 of
# the spec's 9 events - "Fecha proxima/vencida" is out of scope (the only one
# with no existing synchronous call site, would need a scheduled sweep).
NotificationEvent = Literal[
    "vendor_invited",
    "evaluation_published",
    "qna_question_received",
    "qna_answer_published",
    "proposal_submitted",
    "proposal_reopened",
    "approval_requested",
    "evaluation_completed",
    # ADR 0026 (R2) - mirrors approval_requested for the optional review
    # stage ahead of it. There is no "review_rejected"/"review_changes_
    # requested" notification, matching the existing precedent: the
    # approver's own reject() below never notifies the owner either.
    "review_requested",
    # Fase 25 (billing/admin, ADR 0025, plan Bloqueante #1 Opcion A): the
    # only billing notification - "payment_failed" is deliberately absent, a
    # declined card never completes the Checkout Session (Stripe's own
    # hosted page handles that), so no webhook event maps to it.
    "payment_succeeded",
]

# "pending" covers both "not yet attempted" (email_next_attempt_at is None)
# and "a prior attempt failed, awaiting a scheduled retry"
# (email_next_attempt_at set in the future) - a single failed attempt is
# never its own persisted status, only an audit action
# (notification_email_delivery_failed) and an incremented email_attempts/
# email_last_error; "exhausted" is the only terminal failure state, reached
# once email_attempts hits notification_email_max_attempts.
EmailStatus = Literal["not_applicable", "pending", "sending", "sent", "exhausted"]


def notification_id(
    tenant_id: str, event: NotificationEvent, resource_id: str, recipient_membership_id: str
) -> str:
    """Deterministic, not uuid4() (unlike AuditEvent/Report) - makes notify()
    safe to call from a non-best-effort, idempotent-retry call site like
    evaluations.service._finish_publish: a retry after a crash produces the
    same id, insert_one raises DuplicateKeyError, and
    NotificationService.notify() treats that as an idempotent success, same
    idiom _finish_publish already uses for its own snapshot insert."""
    raw = f"{tenant_id}:{event}:{resource_id}:{recipient_membership_id}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class EmailMessage:
    """Provider-independent email payload - the notifications-module analog
    of ai.models.AIRequest/AIResponse."""

    to_address: str
    to_display_name: str
    subject: str
    plain_text: str


@dataclass(frozen=True)
class Notification:
    """One document per (tenant_id, recipient_membership_id, event
    occurrence) - never a fan-out inside a single document, same
    actor-centric, single-row-per-view grain as AuditEvent. `read_at` is
    deliberately mutable (unlike AuditEvent/Report's insert-only shape) -
    "read" is inherently a post-creation, per-recipient state, updated via a
    single-field $set (NotificationRepository.mark_read), never a full
    document replace. `title`/`body` are precomputed at the call site (same
    discipline as AuditEvent.metadata - never a {event, params} pair
    re-rendered later), so no template engine is needed."""

    id: str
    tenant_id: str
    recipient_membership_id: str
    event: NotificationEvent
    resource_type: str
    resource_id: str
    evaluation_id: str | None
    title: str
    body: str
    created_at: datetime
    read_at: datetime | None
    expires_at: datetime
    email_status: EmailStatus
    email_attempts: int
    email_last_error: str | None
    email_next_attempt_at: datetime | None

    @staticmethod
    def create(
        *,
        tenant_id: str,
        recipient_membership_id: str,
        event: NotificationEvent,
        resource_type: str,
        resource_id: str,
        evaluation_id: str | None,
        title: str,
        body: str,
        retention_days: int,
    ) -> "Notification":
        now = datetime.now(UTC)
        return Notification(
            id=notification_id(tenant_id, event, resource_id, recipient_membership_id),
            tenant_id=tenant_id,
            recipient_membership_id=recipient_membership_id,
            event=event,
            resource_type=resource_type,
            resource_id=resource_id,
            evaluation_id=evaluation_id,
            title=title,
            body=body,
            created_at=now,
            read_at=None,
            expires_at=now + timedelta(days=retention_days),
            email_status="pending",
            email_attempts=0,
            email_last_error=None,
            email_next_attempt_at=None,
        )

    def to_document(self) -> dict[str, Any]:
        return {
            "_id": self.id,
            "tenant_id": self.tenant_id,
            "recipient_membership_id": self.recipient_membership_id,
            "event": self.event,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "evaluation_id": self.evaluation_id,
            "title": self.title,
            "body": self.body,
            "created_at": self.created_at,
            "read_at": self.read_at,
            "expires_at": self.expires_at,
            "email_status": self.email_status,
            "email_attempts": self.email_attempts,
            "email_last_error": self.email_last_error,
            "email_next_attempt_at": self.email_next_attempt_at,
        }

    @staticmethod
    def from_document(doc: dict[str, Any]) -> "Notification":
        return Notification(
            id=doc["_id"],
            tenant_id=doc["tenant_id"],
            recipient_membership_id=doc["recipient_membership_id"],
            event=doc["event"],
            resource_type=doc["resource_type"],
            resource_id=doc["resource_id"],
            evaluation_id=doc.get("evaluation_id"),
            title=doc["title"],
            body=doc["body"],
            created_at=doc["created_at"],
            read_at=doc.get("read_at"),
            expires_at=doc["expires_at"],
            email_status=doc.get("email_status", "not_applicable"),
            email_attempts=doc.get("email_attempts", 0),
            email_last_error=doc.get("email_last_error"),
            email_next_attempt_at=doc.get("email_next_attempt_at"),
        )
