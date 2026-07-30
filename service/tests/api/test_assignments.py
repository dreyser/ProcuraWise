import pytest

from tests.conftest import bearer_headers_for, unique_actor_by_role

pytestmark = pytest.mark.docker


def _create_evaluation_with_functional_requirement(client, owner_headers) -> tuple[str, str]:
    created = client.post(
        "/api/v1/evaluations",
        json={"name": "Evaluacion con secciones", "description": ""},
        headers=owner_headers,
    )
    evaluation_id = created.json()["id"]
    client.post(
        f"/api/v1/evaluations/{evaluation_id}/requirements",
        json={
            "dimension": "functional",
            "category": "Seccion Alfa",
            "title": "T",
            "description": "D",
            "priority": "important",
            "response_type": "compliant_status",
            "weight": 10.0,
            "required": True,
            "display_order": 1,
        },
        headers=owner_headers,
    )
    return evaluation_id, "Seccion Alfa"


def test_owner_can_assign_evaluator_to_matching_section(
    client, seeded_actors, mongo_test_settings
) -> None:
    tenant_a, _membership_id = unique_actor_by_role(seeded_actors, "evaluator_functional")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    evaluation_id, section = _create_evaluation_with_functional_requirement(client, owner_headers)
    evaluator_membership_id = seeded_actors[(tenant_a, "evaluator_functional")]

    response = client.post(
        f"/api/v1/evaluations/{evaluation_id}/assignments",
        json={
            "dimension": "functional",
            "section": section,
            "evaluator_membership_id": evaluator_membership_id,
        },
        headers=owner_headers,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["dimension"] == "functional"
    assert body["section"] == section
    assert body["evaluator_membership_id"] == evaluator_membership_id
    assert body["status"] == "not_started"


def test_assigning_evaluator_with_wrong_sub_role_is_rejected(
    client, seeded_actors, mongo_test_settings
) -> None:
    # "evaluator_technical" itself isn't unique across tenants - resolve
    # tenant_a via "evaluator_functional" instead, which dev_seed.py only
    # seeds once, under tenant_a.
    tenant_a, _membership_id = unique_actor_by_role(seeded_actors, "evaluator_functional")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    evaluation_id, section = _create_evaluation_with_functional_requirement(client, owner_headers)
    wrong_role_membership_id = seeded_actors[(tenant_a, "evaluator_technical")]

    response = client.post(
        f"/api/v1/evaluations/{evaluation_id}/assignments",
        json={
            "dimension": "functional",
            "section": section,
            "evaluator_membership_id": wrong_role_membership_id,
        },
        headers=owner_headers,
    )

    assert response.status_code == 400


def test_assigning_unknown_section_is_rejected(client, seeded_actors, mongo_test_settings) -> None:
    tenant_a, _membership_id = unique_actor_by_role(seeded_actors, "evaluator_functional")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    evaluation_id, _section = _create_evaluation_with_functional_requirement(client, owner_headers)
    evaluator_membership_id = seeded_actors[(tenant_a, "evaluator_functional")]

    response = client.post(
        f"/api/v1/evaluations/{evaluation_id}/assignments",
        json={
            "dimension": "functional",
            "section": "Seccion Que No Existe",
            "evaluator_membership_id": evaluator_membership_id,
        },
        headers=owner_headers,
    )

    assert response.status_code == 400


def test_duplicate_assignment_is_rejected(client, seeded_actors, mongo_test_settings) -> None:
    tenant_a, _membership_id = unique_actor_by_role(seeded_actors, "evaluator_functional")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    evaluation_id, section = _create_evaluation_with_functional_requirement(client, owner_headers)
    evaluator_membership_id = seeded_actors[(tenant_a, "evaluator_functional")]
    payload = {
        "dimension": "functional",
        "section": section,
        "evaluator_membership_id": evaluator_membership_id,
    }
    client.post(
        f"/api/v1/evaluations/{evaluation_id}/assignments", json=payload, headers=owner_headers
    )

    response = client.post(
        f"/api/v1/evaluations/{evaluation_id}/assignments", json=payload, headers=owner_headers
    )

    assert response.status_code == 409


def test_non_owner_cannot_create_assignment(client, seeded_actors, mongo_test_settings) -> None:
    tenant_a, _membership_id = unique_actor_by_role(seeded_actors, "internal_collaborator")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    collaborator_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "internal_collaborator")], mongo_test_settings
    )
    evaluation_id, section = _create_evaluation_with_functional_requirement(client, owner_headers)
    evaluator_membership_id = seeded_actors[(tenant_a, "evaluator_functional")]

    response = client.post(
        f"/api/v1/evaluations/{evaluation_id}/assignments",
        json={
            "dimension": "functional",
            "section": section,
            "evaluator_membership_id": evaluator_membership_id,
        },
        headers=collaborator_headers,
    )

    assert response.status_code == 403


def test_assigned_evaluator_can_update_own_progress_but_others_cannot(
    client, seeded_actors, mongo_test_settings
) -> None:
    tenant_a, _membership_id = unique_actor_by_role(seeded_actors, "evaluator_functional")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    evaluation_id, section = _create_evaluation_with_functional_requirement(client, owner_headers)
    evaluator_membership_id = seeded_actors[(tenant_a, "evaluator_functional")]
    created = client.post(
        f"/api/v1/evaluations/{evaluation_id}/assignments",
        json={
            "dimension": "functional",
            "section": section,
            "evaluator_membership_id": evaluator_membership_id,
        },
        headers=owner_headers,
    )
    assignment_id = created.json()["id"]

    evaluator_headers = bearer_headers_for(evaluator_membership_id, mongo_test_settings)
    own_update = client.patch(
        f"/api/v1/evaluations/{evaluation_id}/assignments/{assignment_id}/status",
        json={"status": "in_progress"},
        headers=evaluator_headers,
    )
    assert own_update.status_code == 200
    assert own_update.json()["status"] == "in_progress"

    other_evaluator_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluator_technical")], mongo_test_settings
    )
    other_update = client.patch(
        f"/api/v1/evaluations/{evaluation_id}/assignments/{assignment_id}/status",
        json={"status": "completed"},
        headers=other_evaluator_headers,
    )
    assert other_update.status_code == 403


def test_owner_can_delete_assignment(client, seeded_actors, mongo_test_settings) -> None:
    tenant_a, _membership_id = unique_actor_by_role(seeded_actors, "evaluator_functional")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    evaluation_id, section = _create_evaluation_with_functional_requirement(client, owner_headers)
    evaluator_membership_id = seeded_actors[(tenant_a, "evaluator_functional")]
    created = client.post(
        f"/api/v1/evaluations/{evaluation_id}/assignments",
        json={
            "dimension": "functional",
            "section": section,
            "evaluator_membership_id": evaluator_membership_id,
        },
        headers=owner_headers,
    )
    assignment_id = created.json()["id"]

    delete_response = client.delete(
        f"/api/v1/evaluations/{evaluation_id}/assignments/{assignment_id}", headers=owner_headers
    )
    assert delete_response.status_code == 204

    list_response = client.get(
        f"/api/v1/evaluations/{evaluation_id}/assignments", headers=owner_headers
    )
    assert list_response.json()["items"] == []
