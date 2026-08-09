"""Fase 25 (billing/admin, ADR 0025, plan Bloqueante #2 Opcion b): the one
new platform_admin cross-tenant endpoint this phase adds
(GET /admin/purchases), following the exact 4-part boundary pattern already
established for /admin/evaluations, /admin/curated-sources, /admin/fx-rates:
buyer token rejected, tenant_admin token rejected (an "admin"-named role
still has zero cross-tenant reach), unauthenticated rejected, and a
cross-tenant read is individually audited with the operator's reason."""

import pytest

from procurawise.dev_seed import DEV_ADMIN_EMAIL, DEV_ADMIN_PASSWORD
from tests.conftest import bearer_headers_for, tenant_ids, unique_actor_by_role

pytestmark = pytest.mark.docker


def _admin_headers(client) -> dict[str, str]:
    response = client.post(
        "/api/v1/admin/auth/login",
        json={"email": DEV_ADMIN_EMAIL, "password": DEV_ADMIN_PASSWORD},
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _create_evaluation(client, owner_headers: dict, name: str) -> str:
    return client.post(
        "/api/v1/evaluations", json={"name": name, "description": ""}, headers=owner_headers
    ).json()["id"]


def _create_purchase(client, tenant_admin_headers: dict, evaluation_id: str) -> dict:
    response = client.post(
        "/api/v1/billing/checkout-sessions",
        json={"evaluation_id": evaluation_id},
        headers=tenant_admin_headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_buyer_token_cannot_access_purchases_admin_route(
    client, seeded_actors, mongo_test_settings
) -> None:
    tenant_a, _tenant_b = tenant_ids(seeded_actors)
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    response = client.get("/api/v1/admin/purchases", params={"reason": "x"}, headers=owner_headers)
    assert response.status_code == 401


def test_tenant_admin_token_cannot_access_purchases_admin_route(
    client, seeded_actors, mongo_test_settings
) -> None:
    """tenant_admin can create a checkout session for its own tenant
    (BILLING_WRITE_ROLES), but that is a completely different authority than
    platform_admin's cross-tenant read - the two must never be confused."""
    _tenant_id, tenant_admin_membership_id = unique_actor_by_role(seeded_actors, "tenant_admin")
    tenant_admin_headers = bearer_headers_for(tenant_admin_membership_id, mongo_test_settings)
    response = client.get(
        "/api/v1/admin/purchases", params={"reason": "x"}, headers=tenant_admin_headers
    )
    assert response.status_code == 401


def test_unauthenticated_request_is_rejected(client) -> None:
    response = client.get("/api/v1/admin/purchases", params={"reason": "x"})
    assert response.status_code == 401


def test_list_purchases_requires_reason(client) -> None:
    admin_headers = _admin_headers(client)
    response = client.get("/api/v1/admin/purchases", headers=admin_headers)
    assert response.status_code == 422


def test_list_purchases_spans_multiple_tenants_and_is_audited_per_record(
    client, seeded_actors, mongo_test_settings
) -> None:
    tenant_a, tenant_admin_a_membership_id = unique_actor_by_role(seeded_actors, "tenant_admin")
    tenant_admin_a_headers = bearer_headers_for(tenant_admin_a_membership_id, mongo_test_settings)
    owner_a_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )

    eval_a_id = _create_evaluation(client, owner_a_headers, "Admin billing cross-tenant A")
    purchase_a = _create_purchase(client, tenant_admin_a_headers, eval_a_id)

    admin_headers = _admin_headers(client)
    response = client.get(
        "/api/v1/admin/purchases",
        params={"reason": "auditoria de cumplimiento", "limit": 100},
        headers=admin_headers,
    )
    assert response.status_code == 200
    items = response.json()["items"]
    returned_ids = {item["id"] for item in items}
    assert purchase_a["id"] in returned_ids
    matching = next(item for item in items if item["id"] == purchase_a["id"])
    assert matching["tenant_id"] == tenant_a
    assert matching["tenant_name"]
    assert matching["evaluation_id"] == eval_a_id
    assert matching["status"] == "pending"

    audit_response = client.get(
        f"/api/v1/evaluations/{eval_a_id}/audit-events", headers=owner_a_headers
    )
    assert audit_response.status_code == 200
    admin_events = [
        item
        for item in audit_response.json()["items"]
        if item["action"] == "platform_admin_cross_tenant_read"
        and item["resource_id"] == purchase_a["id"]
    ]
    assert len(admin_events) == 1
    assert admin_events[0]["actor_role"] == "platform_admin"
    assert admin_events[0]["metadata"]["reason"] == "auditoria de cumplimiento"
