"""Fase 25 (billing/admin, ADR 0025): the webhook endpoint against
LocalPaymentProvider's fixed dev signature scheme (billing_enabled=False in
test settings, same as every other Docker test) - real Stripe HMAC signature
verification is covered directly against StripePaymentProvider in
tests/unit/test_stripe_webhook_signature.py, offline. This file covers: no
JWT required, signature rejection, idempotency/replay (assert counts, not
just existence), the payment_status guard, and unknown-session handling."""

from uuid import uuid4

import pytest

from procurawise.notifications.repository import NotificationRepository
from tests.conftest import bearer_headers_for, unique_actor_by_role

pytestmark = pytest.mark.docker

_LOCAL_DEV_SIGNATURE = "local-dev-signature"


def _create_evaluation(client, owner_headers: dict, name: str) -> str:
    return client.post(
        "/api/v1/evaluations", json={"name": name, "description": ""}, headers=owner_headers
    ).json()["id"]


def _create_pending_purchase(client, tenant_admin_headers: dict, evaluation_id: str) -> dict:
    created = client.post(
        "/api/v1/billing/checkout-sessions",
        json={"evaluation_id": evaluation_id},
        headers=tenant_admin_headers,
    ).json()
    session_id = created["checkout_url"].rsplit("/", 1)[-1]
    return {**created, "stripe_checkout_session_id": session_id}


def _checkout_completed_event(
    *, event_id: str, session_id: str, payment_status: str = "paid", tenant_id: str | None = None
) -> dict:
    return {
        "event_id": event_id,
        "event_type": "checkout.session.completed",
        "session_id": session_id,
        "payment_status": payment_status,
        "amount_total": 150000,
        "currency": "mxn",
        "payment_intent_id": f"pi_{event_id}",
        "metadata": {"tenant_id": tenant_id} if tenant_id else {},
    }


def test_webhook_requires_no_jwt(client) -> None:
    """A well-formed-but-signature-rejected request with zero auth headers
    still reaches the handler (400 for bad signature, never 401/403) -
    proving this route has no auth dependency of its own."""
    response = client.post(
        "/api/v1/billing/stripe/webhook",
        content=b"{}",
        headers={"Stripe-Signature": "wrong"},
    )
    assert response.status_code == 400


def test_missing_or_wrong_signature_is_rejected_without_side_effects(
    client, seeded_actors, mongo_test_settings
) -> None:
    tenant_a, tenant_admin_membership_id = unique_actor_by_role(seeded_actors, "tenant_admin")
    tenant_admin_headers = bearer_headers_for(tenant_admin_membership_id, mongo_test_settings)
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    evaluation_id = _create_evaluation(client, owner_headers, "Webhook bad signature")
    purchase = _create_pending_purchase(client, tenant_admin_headers, evaluation_id)

    event = _checkout_completed_event(
        event_id=f"evt_{uuid4().hex}", session_id=purchase["stripe_checkout_session_id"]
    )
    response = client.post(
        "/api/v1/billing/stripe/webhook",
        json=event,
        headers={"Stripe-Signature": "not-the-right-signature"},
    )
    assert response.status_code == 400

    unchanged = client.get(
        f"/api/v1/billing/purchases/{purchase['id']}", headers=tenant_admin_headers
    ).json()
    assert unchanged["status"] == "pending"

    audit_response = client.get(
        f"/api/v1/evaluations/{evaluation_id}/audit-events", headers=owner_headers
    )
    actions = {item["action"] for item in audit_response.json()["items"]}
    assert "billing_payment_succeeded" not in actions


def test_valid_checkout_completed_event_marks_purchase_paid_audits_and_notifies(
    client, seeded_actors, mongo_test_settings, mongo_test_db
) -> None:
    tenant_a, tenant_admin_membership_id = unique_actor_by_role(seeded_actors, "tenant_admin")
    tenant_admin_headers = bearer_headers_for(tenant_admin_membership_id, mongo_test_settings)
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    evaluation_id = _create_evaluation(client, owner_headers, "Webhook happy path")
    purchase = _create_pending_purchase(client, tenant_admin_headers, evaluation_id)

    event = _checkout_completed_event(
        event_id=f"evt_{uuid4().hex}",
        session_id=purchase["stripe_checkout_session_id"],
        tenant_id=tenant_a,
    )
    response = client.post(
        "/api/v1/billing/stripe/webhook",
        json=event,
        headers={"Stripe-Signature": _LOCAL_DEV_SIGNATURE},
    )
    assert response.status_code == 200, response.text

    paid = client.get(
        f"/api/v1/billing/purchases/{purchase['id']}", headers=tenant_admin_headers
    ).json()
    assert paid["status"] == "paid"
    assert paid["amount_total"] == 150000
    assert paid["currency"] == "mxn"

    audit_response = client.get(
        f"/api/v1/evaluations/{evaluation_id}/audit-events", headers=owner_headers
    )
    actions = {item["action"] for item in audit_response.json()["items"]}
    assert "billing_payment_succeeded" in actions

    notifications = NotificationRepository(mongo_test_db)
    items = notifications.list_for_recipient(tenant_a, tenant_admin_membership_id, limit=100)
    matching = [
        n for n in items if n["event"] == "payment_succeeded" and n["resource_id"] == purchase["id"]
    ]
    assert len(matching) == 1


def test_replayed_event_id_produces_exactly_one_of_each_side_effect(
    client, seeded_actors, mongo_test_settings, mongo_test_db
) -> None:
    tenant_a, tenant_admin_membership_id = unique_actor_by_role(seeded_actors, "tenant_admin")
    tenant_admin_headers = bearer_headers_for(tenant_admin_membership_id, mongo_test_settings)
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    evaluation_id = _create_evaluation(client, owner_headers, "Webhook replay")
    purchase = _create_pending_purchase(client, tenant_admin_headers, evaluation_id)

    event_id = f"evt_{uuid4().hex}"
    event = _checkout_completed_event(
        event_id=event_id, session_id=purchase["stripe_checkout_session_id"]
    )
    for _ in range(2):
        response = client.post(
            "/api/v1/billing/stripe/webhook",
            json=event,
            headers={"Stripe-Signature": _LOCAL_DEV_SIGNATURE},
        )
        assert response.status_code == 200

    audit_response = client.get(
        f"/api/v1/evaluations/{evaluation_id}/audit-events", headers=owner_headers
    )
    succeeded_events = [
        item
        for item in audit_response.json()["items"]
        if item["action"] == "billing_payment_succeeded"
    ]
    assert len(succeeded_events) == 1

    notifications = NotificationRepository(mongo_test_db)
    items = notifications.list_for_recipient(tenant_a, tenant_admin_membership_id, limit=100)
    matching = [n for n in items if n["resource_id"] == purchase["id"]]
    assert len(matching) == 1


def test_payment_status_not_paid_does_not_transition_the_purchase(
    client, seeded_actors, mongo_test_settings
) -> None:
    tenant_a, tenant_admin_membership_id = unique_actor_by_role(seeded_actors, "tenant_admin")
    tenant_admin_headers = bearer_headers_for(tenant_admin_membership_id, mongo_test_settings)
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    evaluation_id = _create_evaluation(client, owner_headers, "Webhook unpaid status")
    purchase = _create_pending_purchase(client, tenant_admin_headers, evaluation_id)

    event = _checkout_completed_event(
        event_id=f"evt_{uuid4().hex}",
        session_id=purchase["stripe_checkout_session_id"],
        payment_status="unpaid",
    )
    response = client.post(
        "/api/v1/billing/stripe/webhook",
        json=event,
        headers={"Stripe-Signature": _LOCAL_DEV_SIGNATURE},
    )
    assert response.status_code == 200

    unchanged = client.get(
        f"/api/v1/billing/purchases/{purchase['id']}", headers=tenant_admin_headers
    ).json()
    assert unchanged["status"] == "pending"


def test_unknown_session_id_is_a_no_op_not_an_error(client) -> None:
    event = _checkout_completed_event(
        event_id=f"evt_{uuid4().hex}", session_id="cs_local_never_existed"
    )
    response = client.post(
        "/api/v1/billing/stripe/webhook",
        json=event,
        headers={"Stripe-Signature": _LOCAL_DEV_SIGNATURE},
    )
    assert response.status_code == 200


def test_checkout_session_expired_event_transitions_purchase_to_expired(
    client, seeded_actors, mongo_test_settings
) -> None:
    tenant_a, tenant_admin_membership_id = unique_actor_by_role(seeded_actors, "tenant_admin")
    tenant_admin_headers = bearer_headers_for(tenant_admin_membership_id, mongo_test_settings)
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    evaluation_id = _create_evaluation(client, owner_headers, "Webhook expired")
    purchase = _create_pending_purchase(client, tenant_admin_headers, evaluation_id)

    event = {
        "event_id": f"evt_{uuid4().hex}",
        "event_type": "checkout.session.expired",
        "session_id": purchase["stripe_checkout_session_id"],
        "payment_status": "unpaid",
        "amount_total": None,
        "currency": None,
        "payment_intent_id": None,
        "metadata": {},
    }
    response = client.post(
        "/api/v1/billing/stripe/webhook",
        json=event,
        headers={"Stripe-Signature": _LOCAL_DEV_SIGNATURE},
    )
    assert response.status_code == 200

    expired = client.get(
        f"/api/v1/billing/purchases/{purchase['id']}", headers=tenant_admin_headers
    ).json()
    assert expired["status"] == "expired"
