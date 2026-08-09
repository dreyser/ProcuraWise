"""Fase 25 (billing/admin, ADR 0025): checkout endpoints against
LocalPaymentProvider (billing_enabled=False in test settings, same as every
other Docker test - no Stripe account/network involved). Covers role
enforcement, price-tampering rejection, tenant isolation, the "reuse a
pending session" rule, and the audit trail."""

import pytest

from tests.conftest import (
    bearer_headers_for,
    tenant_ids,
    unique_actor_by_role,
    vendor_bearer_headers_for,
)

pytestmark = pytest.mark.docker


def _create_evaluation(client, owner_headers: dict, name: str) -> str:
    return client.post(
        "/api/v1/evaluations", json={"name": name, "description": ""}, headers=owner_headers
    ).json()["id"]


def test_unauthenticated_request_is_rejected(client) -> None:
    response = client.post("/api/v1/billing/checkout-sessions", json={"evaluation_id": "x"})
    assert response.status_code == 401


def test_vendor_token_cannot_create_checkout_session(
    client, seeded_actors, mongo_test_settings
) -> None:
    """A real vendor_access token is a different token audience than the
    buyer access token this route requires - rejected outright (401) before
    role is even considered, same as every other buyer/vendor token-type
    boundary in this codebase."""
    _tenant_a, vendor_membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    vendor_headers = vendor_bearer_headers_for(vendor_membership_id, mongo_test_settings)
    response = client.post(
        "/api/v1/billing/checkout-sessions", json={"evaluation_id": "x"}, headers=vendor_headers
    )
    assert response.status_code == 401


def test_evaluation_owner_cannot_create_checkout_session(
    client, seeded_actors, mongo_test_settings
) -> None:
    """evaluation_owner is read-only for billing (BILLING_READ_ROLES) -
    only tenant_admin may initiate a real charge."""
    tenant_a, _tenant_admin = unique_actor_by_role(seeded_actors, "tenant_admin")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    evaluation_id = _create_evaluation(client, owner_headers, "Billing RFP owner-write-attempt")
    response = client.post(
        "/api/v1/billing/checkout-sessions",
        json={"evaluation_id": evaluation_id},
        headers=owner_headers,
    )
    assert response.status_code == 403


def test_checkout_session_body_rejects_client_supplied_amount_or_price(
    client, seeded_actors, mongo_test_settings
) -> None:
    """The Price is always resolved server-side from configuration - a
    client-sent amount/price_id/currency/tenant_id is a 422 (APIModel's
    extra="forbid"), never silently ignored."""
    tenant_a, tenant_admin_membership_id = unique_actor_by_role(seeded_actors, "tenant_admin")
    tenant_admin_headers = bearer_headers_for(tenant_admin_membership_id, mongo_test_settings)
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    evaluation_id = _create_evaluation(client, owner_headers, "Billing RFP tampering")

    response = client.post(
        "/api/v1/billing/checkout-sessions",
        json={"evaluation_id": evaluation_id, "amount_total": 1, "currency": "usd"},
        headers=tenant_admin_headers,
    )
    assert response.status_code == 422


def test_checkout_session_for_another_tenants_evaluation_is_404(
    client, seeded_actors, mongo_test_settings
) -> None:
    tenant_a, tenant_admin_membership_id = unique_actor_by_role(seeded_actors, "tenant_admin")
    tenant_admin_headers = bearer_headers_for(tenant_admin_membership_id, mongo_test_settings)
    tenant_b = next(t for t in tenant_ids(seeded_actors) if t != tenant_a)
    owner_b_headers = bearer_headers_for(
        seeded_actors[(tenant_b, "evaluation_owner")], mongo_test_settings
    )
    other_tenant_evaluation_id = _create_evaluation(client, owner_b_headers, "Tenant B RFP")

    response = client.post(
        "/api/v1/billing/checkout-sessions",
        json={"evaluation_id": other_tenant_evaluation_id},
        headers=tenant_admin_headers,
    )
    assert response.status_code == 404


def test_checkout_session_created_successfully_and_audited(
    client, seeded_actors, mongo_test_settings
) -> None:
    tenant_a, tenant_admin_membership_id = unique_actor_by_role(seeded_actors, "tenant_admin")
    tenant_admin_headers = bearer_headers_for(tenant_admin_membership_id, mongo_test_settings)
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    evaluation_id = _create_evaluation(client, owner_headers, "Billing RFP happy path")

    response = client.post(
        "/api/v1/billing/checkout-sessions",
        json={"evaluation_id": evaluation_id},
        headers=tenant_admin_headers,
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "pending"
    assert body["checkout_url"].startswith("/api/v1/billing/local-checkout/")
    assert body["evaluation_id"] == evaluation_id

    audit_response = client.get(
        f"/api/v1/evaluations/{evaluation_id}/audit-events", headers=owner_headers
    )
    actions = {item["action"] for item in audit_response.json()["items"]}
    assert "billing_checkout_session_created" in actions


def test_second_checkout_attempt_reuses_the_pending_session(
    client, seeded_actors, mongo_test_settings
) -> None:
    tenant_a, tenant_admin_membership_id = unique_actor_by_role(seeded_actors, "tenant_admin")
    tenant_admin_headers = bearer_headers_for(tenant_admin_membership_id, mongo_test_settings)
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    evaluation_id = _create_evaluation(client, owner_headers, "Billing RFP duplicate click")

    first = client.post(
        "/api/v1/billing/checkout-sessions",
        json={"evaluation_id": evaluation_id},
        headers=tenant_admin_headers,
    ).json()
    second = client.post(
        "/api/v1/billing/checkout-sessions",
        json={"evaluation_id": evaluation_id},
        headers=tenant_admin_headers,
    ).json()

    assert first["id"] == second["id"]
    assert first["checkout_url"] == second["checkout_url"]


def test_checkout_attempt_after_already_paid_is_409(
    client, seeded_actors, mongo_test_settings
) -> None:
    tenant_a, tenant_admin_membership_id = unique_actor_by_role(seeded_actors, "tenant_admin")
    tenant_admin_headers = bearer_headers_for(tenant_admin_membership_id, mongo_test_settings)
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    evaluation_id = _create_evaluation(client, owner_headers, "Billing RFP already paid")

    created = client.post(
        "/api/v1/billing/checkout-sessions",
        json={"evaluation_id": evaluation_id},
        headers=tenant_admin_headers,
    ).json()
    # Drive the dev-only local simulator directly (no client redirect follow
    # needed) to move the Purchase to "paid".
    client.get(created["checkout_url"], headers=tenant_admin_headers, follow_redirects=False)

    response = client.post(
        "/api/v1/billing/checkout-sessions",
        json={"evaluation_id": evaluation_id},
        headers=tenant_admin_headers,
    )
    assert response.status_code == 409


def test_get_purchase_for_another_tenant_is_404(client, seeded_actors, mongo_test_settings) -> None:
    tenant_a, tenant_admin_membership_id = unique_actor_by_role(seeded_actors, "tenant_admin")
    tenant_admin_headers = bearer_headers_for(tenant_admin_membership_id, mongo_test_settings)
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    evaluation_id = _create_evaluation(client, owner_headers, "Billing RFP isolation")
    purchase_id = client.post(
        "/api/v1/billing/checkout-sessions",
        json={"evaluation_id": evaluation_id},
        headers=tenant_admin_headers,
    ).json()["id"]

    tenant_b = next(t for t in tenant_ids(seeded_actors) if t != tenant_a)
    owner_b_headers = bearer_headers_for(
        seeded_actors[(tenant_b, "evaluation_owner")], mongo_test_settings
    )
    response = client.get(f"/api/v1/billing/purchases/{purchase_id}", headers=owner_b_headers)
    assert response.status_code == 404
