import logging
from datetime import UTC, datetime, timedelta

from pymongo.errors import DuplicateKeyError

from procurawise.audit.models import AuditAction
from procurawise.audit.service import AuditEventService
from procurawise.identity.service import ActorNotFoundError, IdentityService
from procurawise.notifications.exceptions import NotificationNotFoundError
from procurawise.notifications.models import EmailMessage, Notification, NotificationEvent
from procurawise.notifications.provider import NotificationEmailProvider
from procurawise.notifications.repository import NotificationRepository
from procurawise.shared.messaging import MessageBus

logger = logging.getLogger("procurawise.notifications")

JOB_TOPIC = "notification-email"

# How many due retries to reclaim per worker-loop iteration - narrow and
# cheap, same bound-per-tick discipline as every other time_based_tasks
# candidate (shared/worker_loop.py's own docstring).
_RETRY_SWEEP_BATCH_SIZE = 20


class NotificationService:
    """Fase 24 (ADR 0024). notify()/list_for_recipient()/mark_read()/
    mark_all_read() are called by domain services and by the API router;
    process_email_delivery_job()/requeue_due_email_retries() are called by
    the worker's dispatch loop (never by the API directly, per ADR 0001/0005
    - same "worker calls the same code a synchronous call would use"
    principle already applied to ai.service/AIService and reports.service/
    ReportService)."""

    def __init__(
        self,
        notifications: NotificationRepository,
        email_provider: NotificationEmailProvider,
        message_bus: MessageBus,
        audit: AuditEventService,
        identity: IdentityService,
        *,
        retention_days: int,
        max_attempts: int,
        retry_delay_minutes_1: int,
        retry_delay_minutes_2: int,
    ) -> None:
        self._notifications = notifications
        self._email_provider = email_provider
        self._message_bus = message_bus
        self._audit = audit
        self._identity = identity
        self._retention_days = retention_days
        self._max_attempts = max_attempts
        self._retry_delay_minutes_1 = retry_delay_minutes_1
        self._retry_delay_minutes_2 = retry_delay_minutes_2

    def notify(
        self,
        tenant_id: str,
        *,
        recipient_membership_id: str,
        event: NotificationEvent,
        resource_type: str,
        resource_id: str,
        evaluation_id: str | None,
        title: str,
        body: str,
    ) -> None:
        """Best-effort by default (mirrors AuditEventService.record()) -
        except a DuplicateKeyError on the deterministic id, which is treated
        as an idempotent-retry success, not a failure. This is what makes it
        safe to call unwrapped even from a non-best-effort, idempotent call
        site like evaluations.service._finish_publish - a retry after a
        crash produces the exact same Notification.id, so the second insert
        simply no-ops here instead of logging a spurious error.

        `title`/`body` are the full precomputed content (same discipline as
        AuditEvent.metadata) - for vendor_invited, the invitation link
        (built from the raw token, which exists in plaintext only in the
        caller's own call stack) is embedded directly into `body` here, so
        the worker never needs to regenerate it later: it always resolves
        the recipient's real email address and reuses this same title/body
        as the email's subject/plain_text at send time."""
        notification = Notification.create(
            tenant_id=tenant_id,
            recipient_membership_id=recipient_membership_id,
            event=event,
            resource_type=resource_type,
            resource_id=resource_id,
            evaluation_id=evaluation_id,
            title=title,
            body=body,
            retention_days=self._retention_days,
        )
        try:
            self._notifications.insert(tenant_id, notification.to_document())
        except DuplicateKeyError:
            return  # already recorded by a prior attempt - idempotent retry
        except Exception:  # noqa: BLE001 - best-effort, same principle as AuditEventService.record()
            logger.error(
                "notification_create_failed",
                exc_info=True,
                extra={"tenant_id": tenant_id, "event": event, "resource_id": resource_id},
            )
            return

        try:
            self._message_bus.publish(
                JOB_TOPIC, {"tenant_id": tenant_id, "notification_id": notification.id}
            )
        except Exception:  # noqa: BLE001 - never let a queue publish failure break the caller's transaction
            logger.error(
                "notification_email_job_publish_failed",
                exc_info=True,
                extra={"tenant_id": tenant_id, "notification_id": notification.id},
            )

    def list_for_recipient(
        self, tenant_id: str, recipient_membership_id: str, *, limit: int = 20
    ) -> tuple[list[Notification], int]:
        docs = self._notifications.list_for_recipient(
            tenant_id, recipient_membership_id, limit=limit
        )
        unread_count = self._notifications.count_unread(tenant_id, recipient_membership_id)
        return [Notification.from_document(d) for d in docs], unread_count

    def mark_read(
        self, tenant_id: str, notification_id: str, *, recipient_membership_id: str
    ) -> None:
        """The filter itself (recipient_membership_id, not just _id) is the
        identity-based authorization boundary - see
        NotificationRepository.mark_read. A membership can never mark
        another recipient's Notification as read, even within the same
        tenant; that case collapses to the same 404 as "does not exist"."""
        matched = self._notifications.mark_read(
            tenant_id, notification_id, recipient_membership_id, datetime.now(UTC)
        )
        if not matched:
            raise NotificationNotFoundError(notification_id)

    def mark_all_read(self, tenant_id: str, *, recipient_membership_id: str) -> int:
        return self._notifications.mark_all_read(
            tenant_id, recipient_membership_id, datetime.now(UTC)
        )

    def _build_email_message(self, notification: Notification) -> EmailMessage | None:
        resolved = self._identity.resolve_recipient_email(notification.recipient_membership_id)
        if resolved is None:
            return None
        email, display_name = resolved
        return EmailMessage(
            to_address=email,
            to_display_name=display_name,
            subject=notification.title,
            plain_text=notification.body,
        )

    def process_email_delivery_job(self, tenant_id: str, notification_id: str) -> None:
        doc = self._notifications.find_by_id(tenant_id, notification_id)
        if doc is None:
            logger.error(
                "notification_not_found_for_job", extra={"notification_id": notification_id}
            )
            return
        notification = Notification.from_document(doc)
        if notification.email_status != "pending":
            # Idempotency guard (ADR 0005: every job must be retryable
            # idempotently) - a redelivered/duplicate message for an
            # already-sending/sent/exhausted notification is a no-op.
            return
        if not self._notifications.transition_email_status(
            tenant_id, notification_id, "pending", "sending"
        ):
            return

        message = self._build_email_message(notification)
        if message is None:
            # Recipient's Membership/User no longer resolves - nothing
            # sendable, but not a transient failure either; mark exhausted
            # directly rather than burning retry attempts on something that
            # can never succeed.
            self._notifications.transition_email_status(
                tenant_id,
                notification_id,
                "sending",
                "exhausted",
                {"email_last_error": "recipient no longer resolves"},
            )
            self._record_delivery_audit(
                tenant_id, notification, "notification_email_delivery_exhausted"
            )
            return

        try:
            self._email_provider.send_email(message)
        except Exception as exc:  # noqa: BLE001 - any send failure lands the job in pending-retry or exhausted, never crashes the worker loop
            self._handle_send_failure(tenant_id, notification, str(exc))
            return

        self._notifications.transition_email_status(tenant_id, notification_id, "sending", "sent")
        self._record_delivery_audit(
            tenant_id, notification, "notification_email_delivery_succeeded"
        )

    def _handle_send_failure(self, tenant_id: str, notification: Notification, error: str) -> None:
        next_attempts = notification.email_attempts + 1
        if next_attempts >= self._max_attempts:
            self._notifications.transition_email_status(
                tenant_id,
                notification.id,
                "sending",
                "exhausted",
                {"email_attempts": next_attempts, "email_last_error": error[:500]},
            )
            self._record_delivery_audit(
                tenant_id, notification, "notification_email_delivery_exhausted"
            )
            return

        delay_minutes = (
            self._retry_delay_minutes_1 if next_attempts == 1 else self._retry_delay_minutes_2
        )
        self._notifications.transition_email_status(
            tenant_id,
            notification.id,
            "sending",
            "pending",
            {
                "email_attempts": next_attempts,
                "email_last_error": error[:500],
                "email_next_attempt_at": datetime.now(UTC) + timedelta(minutes=delay_minutes),
            },
        )
        self._record_delivery_audit(tenant_id, notification, "notification_email_delivery_failed")

    def requeue_due_email_retries(self) -> None:
        """shared.worker_loop's time_based_tasks entrypoint - re-publishes
        every notification whose scheduled retry is due, since no message
        bus in this project redelivers on its own (ServiceBusMessageBus.
        consume() completes the message before the handler runs). Clears
        email_next_attempt_at as part of claiming each row so the same due
        retry is not re-published on the next tick before the republished
        job is actually processed."""
        due = self._notifications.find_due_email_retries(
            before=datetime.now(UTC), limit=_RETRY_SWEEP_BATCH_SIZE
        )
        for doc in due:
            notification = Notification.from_document(doc)
            claimed = self._notifications.transition_email_status(
                notification.tenant_id,
                notification.id,
                "pending",
                "pending",
                {"email_next_attempt_at": None},
            )
            if not claimed:
                continue
            try:
                self._message_bus.publish(
                    JOB_TOPIC,
                    {"tenant_id": notification.tenant_id, "notification_id": notification.id},
                )
            except Exception:  # noqa: BLE001 - one bad publish must never stop the sweep
                logger.error(
                    "notification_email_retry_publish_failed",
                    exc_info=True,
                    extra={"notification_id": notification.id},
                )

    def _record_delivery_audit(
        self, tenant_id: str, notification: Notification, action: AuditAction
    ) -> None:
        """The worker process has no HTTP-resolved ActorContext of its own -
        same pattern as ai.service.AIService._resolve_requester/
        reports.service.ReportService._resolve_requester: resolve the
        notification's own recipient as the audit actor, and skip the
        (best-effort) audit call entirely if that Membership no longer
        resolves."""
        try:
            actor = self._identity.resolve_actor_context(notification.recipient_membership_id)
        except ActorNotFoundError:
            logger.warning(
                "notification_recipient_not_found_for_audit",
                extra={"notification_id": notification.id},
            )
            return
        self._audit.record(
            tenant_id=tenant_id,
            actor=actor,
            action=action,
            resource_type="notification",
            resource_id=notification.id,
            evaluation_id=notification.evaluation_id,
            metadata={"event": notification.event},
        )
