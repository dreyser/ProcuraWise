import pytest

from tests.conftest import bearer_headers_for, unique_actor_by_role

pytestmark = pytest.mark.docker


def test_internal_collaborator_can_read_but_not_create_evaluation(
    client, seeded_actors, mongo_test_settings
) -> None:
    tenant_a, _membership_id = unique_actor_by_role(seeded_actors, "internal_collaborator")
    headers = bearer_headers_for(
        seeded_actors[(tenant_a, "internal_collaborator")], mongo_test_settings
    )

    read_response = client.get("/api/v1/evaluations", headers=headers)
    assert read_response.status_code == 200

    create_response = client.post(
        "/api/v1/evaluations",
        json={"name": "Intento no autorizado", "description": ""},
        headers=headers,
    )
    assert create_response.status_code == 403


def test_approver_can_read_but_not_add_requirement(
    client, seeded_actors, mongo_test_settings
) -> None:
    # "approver" itself isn't unique across tenants (owner_b also holds an
    # approver Membership under tenant_b, demonstrating roles acumulables) -
    # resolve tenant_a via internal_collaborator instead, which dev_seed.py
    # only seeds once, under tenant_a.
    tenant_a, _membership_id = unique_actor_by_role(seeded_actors, "internal_collaborator")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    approver_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "approver")], mongo_test_settings
    )

    created = client.post(
        "/api/v1/evaluations",
        json={"name": "Evaluacion para aprobador", "description": ""},
        headers=owner_headers,
    )
    evaluation_id = created.json()["id"]

    read_response = client.get(f"/api/v1/evaluations/{evaluation_id}", headers=approver_headers)
    assert read_response.status_code == 200

    add_requirement_response = client.post(
        f"/api/v1/evaluations/{evaluation_id}/requirements",
        json={
            "dimension": "functional",
            "category": "Cat",
            "title": "T",
            "description": "D",
            "priority": "important",
            "response_type": "compliant_status",
            "weight": 10.0,
            "required": True,
            "display_order": 1,
        },
        headers=approver_headers,
    )
    assert add_requirement_response.status_code == 403


def test_evaluator_economic_has_buyer_read_access(
    client, seeded_actors, mongo_test_settings
) -> None:
    tenant_a, _membership_id = unique_actor_by_role(seeded_actors, "evaluator_economic")
    headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluator_economic")], mongo_test_settings
    )

    response = client.get("/api/v1/evaluations", headers=headers)
    assert response.status_code == 200


def test_tenant_admin_cannot_read_buyer_evaluations(
    client, seeded_actors, mongo_test_settings
) -> None:
    # tenant_admin (Administrador del cliente) manages users/roles/config for
    # its own org, not evaluation content - it is deliberately excluded from
    # BUYER_READ_ROLES (shared.roles), so this must 403 like any other
    # unrelated role.
    tenant_a, _membership_id = unique_actor_by_role(seeded_actors, "tenant_admin")
    headers = bearer_headers_for(seeded_actors[(tenant_a, "tenant_admin")], mongo_test_settings)

    response = client.get("/api/v1/evaluations", headers=headers)
    assert response.status_code == 403
