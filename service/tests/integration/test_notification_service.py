"""Fase 24 (ADR 0024). Exercises NotificationService's own lifecycle against
real Mongo: notify() creates an in-app row and queues an email job,
process_email_delivery_job() (the worker-equivalent call, same pattern
tests/integration/test_report_generation_workflow.py already uses for
Report) delivers it via LoggingNotificationEmailProvider (the default
outside production, ADR 0024), retries on failure with backoff, exhausts
after max_attempts, and requeue_due_email_retries() (the
shared.worker_loop.time_based_tasks entrypoint) re-publishes due retries."""

import pytest

from procurawise.notifications.dependencies import build_notification_service
from procurawise.notifications.models import EmailMessage
from procurawise.notifications.repository import NotificationRepository
from procurawise.notifications.service import JOB_TOPIC, NotificationService
from procurawise.shared.messaging import InMemoryMessageBus
from tests.conftest import tenant_ids

pytestmark = pytest.mark.docker


def _owner(seeded_actors: dict[tuple[str, str], str]) -> tuple[str, str]:
    """(tenant_id, membership_id) for `evaluation_owner` - unlike
    `vendor_contact`, both seeded tenants have one, so
    `unique_actor_by_role` (which asserts exactly one match across the whole
    fixture) doesn't apply here; any one arbitrary tenant's owner is fine
    since these tests never need to compare across tenants."""
    tenant_a, _tenant_b = tenant_ids(seeded_actors)
    return tenant_a, seeded_actors[(tenant_a, "evaluation_owner")]


class _FailingEmailProvider:
    def __init__(self) -> None:
        self.attempts = 0

    def send_email(self, message: EmailMessage) -> None:
        self.attempts += 1
        raise RuntimeError("simulated ACS failure")

    def ping(self) -> bool:
        return False


def _service_with_provider(
    mongo_test_settings, mongo_test_db, provider, *, message_bus: InMemoryMessageBus | None = None
) -> NotificationService:
    from procurawise.audit.repository import AuditEventRepository
    from procurawise.audit.service import AuditEventService
    from procurawise.identity.repository import (
        MembershipRepository,
        TenantRepository,
        UserRepository,
    )
    from procurawise.identity.service import IdentityService

    return NotificationService(
        notifications=NotificationRepository(mongo_test_db),
        email_provider=provider,
        message_bus=message_bus if message_bus is not None else InMemoryMessageBus(),
        audit=AuditEventService(AuditEventRepository(mongo_test_db), mongo_test_settings),
        identity=IdentityService(
            tenants=TenantRepository(mongo_test_db),
            users=UserRepository(mongo_test_db),
            memberships=MembershipRepository(mongo_test_db),
        ),
        retention_days=90,
        max_attempts=2,
        retry_delay_minutes_1=0,
        retry_delay_minutes_2=0,
    )


def test_notify_creates_an_in_app_row_and_queues_an_email_job(
    mongo_test_settings, mongo_test_db, seeded_actors
) -> None:
    tenant_id, owner_membership_id = _owner(seeded_actors)
    service = build_notification_service(mongo_test_settings)
    # dev_seed.py's own fixture setup seeds a published evaluation for this
    # same owner (to demo the approval/publication UI), which already
    # produces one real "evaluation_published" Notification - baseline
    # against that instead of assuming an empty inbox.
    _, baseline_unread_count = service.list_for_recipient(tenant_id, owner_membership_id)

    service.notify(
        tenant_id,
        recipient_membership_id=owner_membership_id,
        event="evaluation_published",
        resource_type="evaluation",
        resource_id="eval-test-1",
        evaluation_id="eval-test-1",
        title="t",
        body="b",
    )

    items, unread_count = service.list_for_recipient(tenant_id, owner_membership_id)
    assert unread_count == baseline_unread_count + 1
    matching = [n for n in items if n.resource_id == "eval-test-1"]
    assert len(matching) == 1
    assert matching[0].email_status == "pending"
    assert matching[0].read_at is None


def test_notify_is_idempotent_on_retry_after_a_crash(
    mongo_test_settings, mongo_test_db, seeded_actors
) -> None:
    tenant_id, owner_membership_id = _owner(seeded_actors)
    service = build_notification_service(mongo_test_settings)
    kwargs = dict(
        recipient_membership_id=owner_membership_id,
        event="evaluation_published",
        resource_type="evaluation",
        resource_id="eval-test-idempotent",
        evaluation_id="eval-test-idempotent",
        title="t",
        body="b",
    )

    service.notify(tenant_id, **kwargs)
    service.notify(tenant_id, **kwargs)  # simulates a retried call after a crash

    items, _ = service.list_for_recipient(tenant_id, owner_membership_id, limit=100)
    matching = [n for n in items if n.resource_id == "eval-test-idempotent"]
    assert len(matching) == 1  # never duplicated


def test_process_email_delivery_job_succeeds_with_logging_provider(
    mongo_test_settings, mongo_test_db, seeded_actors
) -> None:
    tenant_id, owner_membership_id = _owner(seeded_actors)
    service = build_notification_service(mongo_test_settings)
    service.notify(
        tenant_id,
        recipient_membership_id=owner_membership_id,
        event="evaluation_completed",
        resource_type="evaluation",
        resource_id="eval-test-2",
        evaluation_id="eval-test-2",
        title="t",
        body="b",
    )
    items, _ = service.list_for_recipient(tenant_id, owner_membership_id, limit=100)
    notification_id = next(n.id for n in items if n.resource_id == "eval-test-2")

    service.process_email_delivery_job(tenant_id, notification_id)

    items, _ = service.list_for_recipient(tenant_id, owner_membership_id, limit=100)
    updated = next(n for n in items if n.id == notification_id)
    assert updated.email_status == "sent"


def test_process_email_delivery_job_is_idempotent_on_redelivery(
    mongo_test_settings, mongo_test_db, seeded_actors
) -> None:
    tenant_id, owner_membership_id = _owner(seeded_actors)
    service = build_notification_service(mongo_test_settings)
    service.notify(
        tenant_id,
        recipient_membership_id=owner_membership_id,
        event="evaluation_completed",
        resource_type="evaluation",
        resource_id="eval-test-redelivery",
        evaluation_id="eval-test-redelivery",
        title="t",
        body="b",
    )
    items, _ = service.list_for_recipient(tenant_id, owner_membership_id, limit=100)
    notification_id = next(n.id for n in items if n.resource_id == "eval-test-redelivery")

    service.process_email_delivery_job(tenant_id, notification_id)
    service.process_email_delivery_job(tenant_id, notification_id)  # redelivered message

    items, _ = service.list_for_recipient(tenant_id, owner_membership_id, limit=100)
    updated = next(n for n in items if n.id == notification_id)
    assert updated.email_status == "sent"
    assert updated.email_attempts == 0  # never touched the failure path


def test_failed_delivery_retries_then_exhausts_after_max_attempts(
    mongo_test_settings, mongo_test_db, seeded_actors
) -> None:
    tenant_id, owner_membership_id = _owner(seeded_actors)
    provider = _FailingEmailProvider()
    service = _service_with_provider(mongo_test_settings, mongo_test_db, provider)
    service.notify(
        tenant_id,
        recipient_membership_id=owner_membership_id,
        event="evaluation_completed",
        resource_type="evaluation",
        resource_id="eval-test-retry",
        evaluation_id="eval-test-retry",
        title="t",
        body="b",
    )
    items, _ = service.list_for_recipient(tenant_id, owner_membership_id, limit=100)
    notification_id = next(n.id for n in items if n.resource_id == "eval-test-retry")

    # Attempt 1: fails, schedules a retry (max_attempts=2 in _service_with_provider).
    service.process_email_delivery_job(tenant_id, notification_id)
    items, _ = service.list_for_recipient(tenant_id, owner_membership_id, limit=100)
    after_first = next(n for n in items if n.id == notification_id)
    assert after_first.email_status == "pending"
    assert after_first.email_attempts == 1
    assert after_first.email_last_error is not None

    # Attempt 2: fails again, exhausts (attempts == max_attempts).
    service.process_email_delivery_job(tenant_id, notification_id)
    items, _ = service.list_for_recipient(tenant_id, owner_membership_id, limit=100)
    after_second = next(n for n in items if n.id == notification_id)
    assert after_second.email_status == "exhausted"
    assert after_second.email_attempts == 2
    assert provider.attempts == 2


def test_requeue_due_email_retries_republishes_and_the_retry_then_succeeds(
    mongo_test_settings, mongo_test_db, seeded_actors
) -> None:
    tenant_id, owner_membership_id = _owner(seeded_actors)
    provider = _FailingEmailProvider()
    message_bus = InMemoryMessageBus()
    service = _service_with_provider(
        mongo_test_settings, mongo_test_db, provider, message_bus=message_bus
    )
    service.notify(
        tenant_id,
        recipient_membership_id=owner_membership_id,
        event="evaluation_completed",
        resource_type="evaluation",
        resource_id="eval-test-requeue",
        evaluation_id="eval-test-requeue",
        title="t",
        body="b",
    )
    items, _ = service.list_for_recipient(tenant_id, owner_membership_id, limit=100)
    notification_id = next(n.id for n in items if n.resource_id == "eval-test-requeue")
    message_bus.consume(JOB_TOPIC)  # drain the initial notify() publish, unrelated to the retry

    # First attempt fails - retry_delay_minutes_1=0 means it's immediately due.
    service.process_email_delivery_job(tenant_id, notification_id)

    # The retry sweep re-publishes it to the message bus...
    service.requeue_due_email_retries()
    message = message_bus.consume(JOB_TOPIC)
    assert message is not None
    assert message.payload["notification_id"] == notification_id

    # ...and a provider that now succeeds delivers it on the next attempt.
    provider.send_email = lambda message: None  # type: ignore[method-assign]
    service.process_email_delivery_job(tenant_id, notification_id)
    items, _ = service.list_for_recipient(tenant_id, owner_membership_id, limit=100)
    updated = next(n for n in items if n.id == notification_id)
    assert updated.email_status == "sent"


def test_mark_read_and_mark_all_read_update_unread_count(
    mongo_test_settings, mongo_test_db, seeded_actors
) -> None:
    tenant_id, owner_membership_id = _owner(seeded_actors)
    service = build_notification_service(mongo_test_settings)
    for resource_id in ("eval-test-read-1", "eval-test-read-2"):
        service.notify(
            tenant_id,
            recipient_membership_id=owner_membership_id,
            event="evaluation_completed",
            resource_type="evaluation",
            resource_id=resource_id,
            evaluation_id=resource_id,
            title="t",
            body="b",
        )
    items, _ = service.list_for_recipient(tenant_id, owner_membership_id, limit=100)
    first_id = next(n.id for n in items if n.resource_id == "eval-test-read-1")

    service.mark_read(tenant_id, first_id, recipient_membership_id=owner_membership_id)
    _, unread_after_one = service.list_for_recipient(tenant_id, owner_membership_id, limit=100)
    assert unread_after_one >= 1  # the second notification (and any prior test's) still unread

    marked = service.mark_all_read(tenant_id, recipient_membership_id=owner_membership_id)
    assert marked >= 1
    _, unread_after_all = service.list_for_recipient(tenant_id, owner_membership_id, limit=100)
    assert unread_after_all == 0
