"""Fase 24 - model-level coverage for Notification: safe defaults on
create(), a lossless to_document/from_document round trip, and the
deterministic id that makes notify() safe to call from an idempotent-retry
call site like evaluations.service._finish_publish."""

from datetime import UTC, datetime

from procurawise.notifications.models import Notification, notification_id


def test_notification_create_defaults_to_pending_email_unread() -> None:
    notification = Notification.create(
        tenant_id="tenant-1",
        recipient_membership_id="m-owner",
        event="evaluation_published",
        resource_type="evaluation",
        resource_id="eval-1",
        evaluation_id="eval-1",
        title="Evaluación publicada",
        body="Tu evaluación ya está publicada.",
        retention_days=90,
    )
    assert notification.read_at is None
    assert notification.email_status == "pending"
    assert notification.email_attempts == 0
    assert notification.email_last_error is None
    assert notification.email_next_attempt_at is None


def test_notification_id_is_deterministic_not_random() -> None:
    first = Notification.create(
        tenant_id="tenant-1",
        recipient_membership_id="m-owner",
        event="evaluation_published",
        resource_type="evaluation",
        resource_id="eval-1",
        evaluation_id="eval-1",
        title="t",
        body="b",
        retention_days=90,
    )
    second = Notification.create(
        tenant_id="tenant-1",
        recipient_membership_id="m-owner",
        event="evaluation_published",
        resource_type="evaluation",
        resource_id="eval-1",
        evaluation_id="eval-1",
        title="t (retry attempt, different text)",
        body="b (retry attempt, different text)",
        retention_days=90,
    )
    assert first.id == second.id
    assert first.id == notification_id("tenant-1", "evaluation_published", "eval-1", "m-owner")

    different_recipient = Notification.create(
        tenant_id="tenant-1",
        recipient_membership_id="m-other",
        event="evaluation_published",
        resource_type="evaluation",
        resource_id="eval-1",
        evaluation_id="eval-1",
        title="t",
        body="b",
        retention_days=90,
    )
    assert different_recipient.id != first.id


def test_notification_document_round_trip_is_lossless() -> None:
    now = datetime.now(UTC)
    notification = Notification(
        id="notif-1",
        tenant_id="tenant-1",
        recipient_membership_id="m-owner",
        event="qna_answer_published",
        resource_type="qna_question",
        resource_id="question-1",
        evaluation_id="eval-1",
        title="Respuesta publicada",
        body="El comprador respondió tu pregunta.",
        created_at=now,
        read_at=now,
        expires_at=now,
        email_status="sent",
        email_attempts=1,
        email_last_error=None,
        email_next_attempt_at=None,
    )
    restored = Notification.from_document(notification.to_document())
    assert restored == notification


def test_notification_document_round_trip_tolerates_missing_optional_keys() -> None:
    now = datetime.now(UTC)
    minimal_doc = {
        "_id": "notif-1",
        "tenant_id": "tenant-1",
        "recipient_membership_id": "m-owner",
        "event": "vendor_invited",
        "resource_type": "vendor_organization",
        "resource_id": "vendor-org-1",
        "title": "t",
        "body": "b",
        "created_at": now,
        "expires_at": now,
    }
    notification = Notification.from_document(minimal_doc)
    assert notification.evaluation_id is None
    assert notification.read_at is None
    assert notification.email_status == "not_applicable"
    assert notification.email_attempts == 0
