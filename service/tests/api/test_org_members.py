import pytest

from tests.conftest import bearer_headers_for, unique_actor_by_role

pytestmark = pytest.mark.docker


def test_tenant_admin_can_list_own_org_members(client, seeded_actors, mongo_test_settings) -> None:
    tenant_a, _membership_id = unique_actor_by_role(seeded_actors, "tenant_admin")
    tenant_admin_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "tenant_admin")], mongo_test_settings
    )

    response = client.get("/api/v1/org/members", headers=tenant_admin_headers)

    assert response.status_code == 200
    roles = {item["role"] for item in response.json()["items"]}
    assert "evaluation_owner" in roles
    assert "tenant_admin" in roles


def test_tenant_admin_never_sees_other_tenants_members(
    client, seeded_actors, mongo_test_settings
) -> None:
    tenant_a, _membership_id = unique_actor_by_role(seeded_actors, "tenant_admin")
    other_tenants = {tenant_id for (tenant_id, _role) in seeded_actors if tenant_id != tenant_a}
    tenant_admin_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "tenant_admin")], mongo_test_settings
    )

    response = client.get("/api/v1/org/members", headers=tenant_admin_headers)

    returned_membership_ids = {item["membership_id"] for item in response.json()["items"]}
    other_tenant_membership_ids = {
        membership_id
        for (tenant_id, _role), membership_id in seeded_actors.items()
        if tenant_id in other_tenants
    }
    assert returned_membership_ids.isdisjoint(other_tenant_membership_ids)


def test_evaluation_owner_can_also_list_own_org_members(
    client, seeded_actors, mongo_test_settings
) -> None:
    # evaluation_owner is deliberately also allowed - it needs this to pick
    # which evaluator Membership to assign to a section (Fase 9 Block 5).
    tenant_a, _membership_id = unique_actor_by_role(seeded_actors, "tenant_admin")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )

    response = client.get("/api/v1/org/members", headers=owner_headers)

    assert response.status_code == 200


def test_other_roles_cannot_list_org_members(client, seeded_actors, mongo_test_settings) -> None:
    tenant_a, _membership_id = unique_actor_by_role(seeded_actors, "tenant_admin")
    collaborator_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "internal_collaborator")], mongo_test_settings
    )

    response = client.get("/api/v1/org/members", headers=collaborator_headers)

    assert response.status_code == 403
