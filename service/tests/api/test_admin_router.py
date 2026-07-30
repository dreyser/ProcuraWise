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


def test_admin_login_rejects_wrong_password(client) -> None:
    response = client.post(
        "/api/v1/admin/auth/login",
        json={"email": DEV_ADMIN_EMAIL, "password": "wrong-password"},
    )
    assert response.status_code == 401


def test_admin_login_rejects_unknown_email(client) -> None:
    response = client.post(
        "/api/v1/admin/auth/login",
        json={"email": "not-an-admin@example.com", "password": "anything"},
    )
    assert response.status_code == 401


def test_list_evaluations_requires_reason(client) -> None:
    admin_headers = _admin_headers(client)
    response = client.get("/api/v1/admin/evaluations", headers=admin_headers)
    assert response.status_code == 422


def test_list_evaluations_spans_multiple_tenants(
    client, seeded_actors, mongo_test_settings
) -> None:
    tenant_a, tenant_b = tenant_ids(seeded_actors)
    owner_a_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    owner_b_headers = bearer_headers_for(
        seeded_actors[(tenant_b, "evaluation_owner")], mongo_test_settings
    )
    eval_a_id = client.post(
        "/api/v1/evaluations",
        json={"name": "Admin cross-tenant A", "description": ""},
        headers=owner_a_headers,
    ).json()["id"]
    eval_b_id = client.post(
        "/api/v1/evaluations",
        json={"name": "Admin cross-tenant B", "description": ""},
        headers=owner_b_headers,
    ).json()["id"]

    admin_headers = _admin_headers(client)
    response = client.get(
        "/api/v1/admin/evaluations",
        params={"reason": "auditoria de cumplimiento", "limit": 100},
        headers=admin_headers,
    )

    assert response.status_code == 200
    returned_ids = {item["id"] for item in response.json()["items"]}
    assert eval_a_id in returned_ids
    assert eval_b_id in returned_ids
    returned_tenant_ids = {item["tenant_id"] for item in response.json()["items"]}
    assert {tenant_a, tenant_b}.issubset(returned_tenant_ids)


def test_cross_tenant_read_is_audited_per_tenant(
    client, seeded_actors, mongo_test_settings
) -> None:
    tenant_a, _tenant_b = tenant_ids(seeded_actors)
    owner_a_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    evaluation_id = client.post(
        "/api/v1/evaluations",
        json={"name": "Admin audit trail", "description": ""},
        headers=owner_a_headers,
    ).json()["id"]

    admin_headers = _admin_headers(client)
    client.get(
        "/api/v1/admin/evaluations",
        params={"reason": "revision de soporte", "limit": 100},
        headers=admin_headers,
    )

    audit_response = client.get(
        f"/api/v1/evaluations/{evaluation_id}/audit-events", headers=owner_a_headers
    )
    assert audit_response.status_code == 200
    actions = {item["action"] for item in audit_response.json()["items"]}
    assert "platform_admin_cross_tenant_read" in actions
    admin_event = next(
        item
        for item in audit_response.json()["items"]
        if item["action"] == "platform_admin_cross_tenant_read"
    )
    assert admin_event["actor_role"] == "platform_admin"
    assert admin_event["metadata"]["reason"] == "revision de soporte"


def test_admin_token_cannot_access_buyer_routes(client, seeded_actors) -> None:
    admin_headers = _admin_headers(client)
    response = client.get("/api/v1/evaluations", headers=admin_headers)
    assert response.status_code == 401


def test_buyer_token_cannot_access_admin_routes(client, seeded_actors, mongo_test_settings) -> None:
    tenant_a, _vendor_membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    response = client.get(
        "/api/v1/admin/evaluations", params={"reason": "x"}, headers=owner_headers
    )
    assert response.status_code == 401
