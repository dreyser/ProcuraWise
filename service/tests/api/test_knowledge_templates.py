import pytest

from tests.conftest import approve_and_publish, bearer_headers_for, unique_actor_by_role

pytestmark = pytest.mark.docker


def _create_template(client, owner_headers, name: str = "Plantilla estándar") -> str:
    created = client.post(
        "/api/v1/knowledge-templates",
        json={"name": name, "description": "d"},
        headers=owner_headers,
    )
    assert created.status_code == 201
    return created.json()["id"]


def _add_item(
    client,
    owner_headers,
    template_id: str,
    *,
    dimension: str = "functional",
    display_order: int = 1,
) -> str:
    response = client.post(
        f"/api/v1/knowledge-templates/{template_id}/items",
        json={
            "dimension": dimension,
            "category": "Core",
            "title": "T",
            "description": "D",
            "priority": "important",
            "response_type": "text",
            "weight": 10.0,
            "required": True,
            "display_order": display_order,
        },
        headers=owner_headers,
    )
    assert response.status_code == 201
    return response.json()["id"]


def _create_evaluation(client, owner_headers) -> str:
    created = client.post(
        "/api/v1/evaluations",
        json={"name": "RFP", "description": ""},
        headers=owner_headers,
    )
    assert created.status_code == 201
    return created.json()["id"]


def test_owner_can_create_and_get_template(client, seeded_actors, mongo_test_settings) -> None:
    tenant_a, _ = unique_actor_by_role(seeded_actors, "evaluator_functional")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )

    template_id = _create_template(client, owner_headers)

    detail = client.get(f"/api/v1/knowledge-templates/{template_id}", headers=owner_headers)
    assert detail.status_code == 200
    body = detail.json()
    assert body["name"] == "Plantilla estándar"
    assert body["items"] == []


def test_get_unknown_template_is_404(client, seeded_actors, mongo_test_settings) -> None:
    tenant_a, _ = unique_actor_by_role(seeded_actors, "evaluator_functional")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )

    response = client.get("/api/v1/knowledge-templates/does-not-exist", headers=owner_headers)
    assert response.status_code == 404


def test_list_templates_returns_summaries_with_item_count(
    client, seeded_actors, mongo_test_settings
) -> None:
    tenant_a, _ = unique_actor_by_role(seeded_actors, "evaluator_functional")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    template_id = _create_template(client, owner_headers)
    _add_item(client, owner_headers, template_id)

    response = client.get("/api/v1/knowledge-templates", headers=owner_headers)
    assert response.status_code == 200
    summaries = {item["id"]: item for item in response.json()["items"]}
    assert summaries[template_id]["item_count"] == 1


def test_owner_can_update_template_metadata(client, seeded_actors, mongo_test_settings) -> None:
    tenant_a, _ = unique_actor_by_role(seeded_actors, "evaluator_functional")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    template_id = _create_template(client, owner_headers)

    updated = client.patch(
        f"/api/v1/knowledge-templates/{template_id}",
        json={"name": "Nuevo nombre"},
        headers=owner_headers,
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Nuevo nombre"


def test_owner_can_delete_template(client, seeded_actors, mongo_test_settings) -> None:
    tenant_a, _ = unique_actor_by_role(seeded_actors, "evaluator_functional")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    template_id = _create_template(client, owner_headers)

    delete_response = client.delete(
        f"/api/v1/knowledge-templates/{template_id}", headers=owner_headers
    )
    assert delete_response.status_code == 204

    get_response = client.get(f"/api/v1/knowledge-templates/{template_id}", headers=owner_headers)
    assert get_response.status_code == 404


def test_non_owner_cannot_create_update_or_delete_template(
    client, seeded_actors, mongo_test_settings
) -> None:
    tenant_a, _ = unique_actor_by_role(seeded_actors, "internal_collaborator")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    collaborator_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "internal_collaborator")], mongo_test_settings
    )
    template_id = _create_template(client, owner_headers)

    create_response = client.post(
        "/api/v1/knowledge-templates",
        json={"name": "x", "description": ""},
        headers=collaborator_headers,
    )
    assert create_response.status_code == 403

    update_response = client.patch(
        f"/api/v1/knowledge-templates/{template_id}",
        json={"name": "x"},
        headers=collaborator_headers,
    )
    assert update_response.status_code == 403

    delete_response = client.delete(
        f"/api/v1/knowledge-templates/{template_id}", headers=collaborator_headers
    )
    assert delete_response.status_code == 403


def test_create_template_rejects_unknown_field(client, seeded_actors, mongo_test_settings) -> None:
    tenant_a, _ = unique_actor_by_role(seeded_actors, "evaluator_functional")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )

    response = client.post(
        "/api/v1/knowledge-templates",
        json={"name": "x", "description": "", "tenant_id": "sneaky"},
        headers=owner_headers,
    )
    assert response.status_code == 422


def test_owner_can_add_update_and_delete_item(client, seeded_actors, mongo_test_settings) -> None:
    tenant_a, _ = unique_actor_by_role(seeded_actors, "evaluator_functional")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    template_id = _create_template(client, owner_headers)
    item_id = _add_item(client, owner_headers, template_id)

    update_response = client.patch(
        f"/api/v1/knowledge-templates/{template_id}/items/{item_id}",
        json={"title": "Nuevo título"},
        headers=owner_headers,
    )
    assert update_response.status_code == 200
    assert update_response.json()["title"] == "Nuevo título"

    delete_response = client.delete(
        f"/api/v1/knowledge-templates/{template_id}/items/{item_id}", headers=owner_headers
    )
    assert delete_response.status_code == 204

    detail = client.get(f"/api/v1/knowledge-templates/{template_id}", headers=owner_headers)
    assert detail.json()["items"] == []


def test_update_item_to_single_choice_without_options_is_rejected(
    client, seeded_actors, mongo_test_settings
) -> None:
    tenant_a, _ = unique_actor_by_role(seeded_actors, "evaluator_functional")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    template_id = _create_template(client, owner_headers)
    item_id = _add_item(client, owner_headers, template_id)

    response = client.patch(
        f"/api/v1/knowledge-templates/{template_id}/items/{item_id}",
        json={"response_type": "single_choice"},
        headers=owner_headers,
    )
    assert response.status_code == 400


def test_add_item_to_unknown_template_is_404(client, seeded_actors, mongo_test_settings) -> None:
    tenant_a, _ = unique_actor_by_role(seeded_actors, "evaluator_functional")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )

    response = client.post(
        "/api/v1/knowledge-templates/does-not-exist/items",
        json={
            "dimension": "functional",
            "category": "Core",
            "title": "T",
            "description": "D",
            "priority": "important",
            "response_type": "text",
            "weight": 10.0,
            "required": True,
            "display_order": 1,
        },
        headers=owner_headers,
    )
    assert response.status_code == 404


def test_apply_template_adds_every_item_to_draft_evaluation(
    client, seeded_actors, mongo_test_settings
) -> None:
    tenant_a, _ = unique_actor_by_role(seeded_actors, "evaluator_functional")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    template_id = _create_template(client, owner_headers)
    _add_item(client, owner_headers, template_id, dimension="functional", display_order=1)
    _add_item(client, owner_headers, template_id, dimension="technical", display_order=2)
    evaluation_id = _create_evaluation(client, owner_headers)

    response = client.post(
        f"/api/v1/evaluations/{evaluation_id}/apply-knowledge-template",
        json={"knowledge_template_id": template_id},
        headers=owner_headers,
    )
    assert response.status_code == 201
    assert len(response.json()["added_requirements"]) == 2

    evaluation = client.get(f"/api/v1/evaluations/{evaluation_id}", headers=owner_headers)
    assert len(evaluation.json()["requirements"]) == 2


def test_apply_template_rejects_unknown_item_ids_field(
    client, seeded_actors, mongo_test_settings
) -> None:
    """Founder decision: subset selection is removed entirely - item_ids is
    not part of the request shape at all, so sending it must 422 like any
    other stray field (extra="forbid")."""
    tenant_a, _ = unique_actor_by_role(seeded_actors, "evaluator_functional")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    template_id = _create_template(client, owner_headers)
    evaluation_id = _create_evaluation(client, owner_headers)

    response = client.post(
        f"/api/v1/evaluations/{evaluation_id}/apply-knowledge-template",
        json={"knowledge_template_id": template_id, "item_ids": ["x"]},
        headers=owner_headers,
    )
    assert response.status_code == 422


def test_apply_template_to_non_draft_evaluation_is_rejected(
    client, seeded_actors, mongo_test_settings
) -> None:
    tenant_a, _ = unique_actor_by_role(seeded_actors, "evaluator_functional")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    template_id = _create_template(client, owner_headers)
    _add_item(client, owner_headers, template_id)
    evaluation_id = _create_evaluation(client, owner_headers)
    client.post(
        f"/api/v1/evaluations/{evaluation_id}/requirements",
        json={
            "dimension": "functional",
            "category": "Core",
            "title": "T",
            "description": "D",
            "priority": "important",
            "response_type": "text",
            "weight": 40.0,
            "required": True,
            "display_order": 1,
        },
        headers=owner_headers,
    )
    client.post(
        f"/api/v1/evaluations/{evaluation_id}/requirements",
        json={
            "dimension": "technical",
            "category": "Core",
            "title": "T2",
            "description": "D",
            "priority": "important",
            "response_type": "text",
            "weight": 20.0,
            "required": True,
            "display_order": 2,
        },
        headers=owner_headers,
    )
    vendor_orgs = client.get("/api/v1/vendor-organizations", headers=owner_headers).json()["items"]
    client.post(
        f"/api/v1/evaluations/{evaluation_id}/vendors",
        json={"vendor_org_id": vendor_orgs[0]["id"]},
        headers=owner_headers,
    )
    approver_membership_id = seeded_actors[(tenant_a, "approver")]
    approver_headers = bearer_headers_for(approver_membership_id, mongo_test_settings)
    approve_and_publish(
        client, owner_headers, approver_membership_id, approver_headers, evaluation_id
    )

    response = client.post(
        f"/api/v1/evaluations/{evaluation_id}/apply-knowledge-template",
        json={"knowledge_template_id": template_id},
        headers=owner_headers,
    )
    assert response.status_code == 409


def test_apply_unknown_template_is_404(client, seeded_actors, mongo_test_settings) -> None:
    tenant_a, _ = unique_actor_by_role(seeded_actors, "evaluator_functional")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    evaluation_id = _create_evaluation(client, owner_headers)

    response = client.post(
        f"/api/v1/evaluations/{evaluation_id}/apply-knowledge-template",
        json={"knowledge_template_id": "does-not-exist"},
        headers=owner_headers,
    )
    assert response.status_code == 404


def test_apply_template_to_unknown_evaluation_is_404(
    client, seeded_actors, mongo_test_settings
) -> None:
    tenant_a, _ = unique_actor_by_role(seeded_actors, "evaluator_functional")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    template_id = _create_template(client, owner_headers)

    response = client.post(
        "/api/v1/evaluations/does-not-exist/apply-knowledge-template",
        json={"knowledge_template_id": template_id},
        headers=owner_headers,
    )
    assert response.status_code == 404


def test_non_owner_cannot_apply_template(client, seeded_actors, mongo_test_settings) -> None:
    tenant_a, _ = unique_actor_by_role(seeded_actors, "internal_collaborator")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    collaborator_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "internal_collaborator")], mongo_test_settings
    )
    template_id = _create_template(client, owner_headers)
    evaluation_id = _create_evaluation(client, owner_headers)

    response = client.post(
        f"/api/v1/evaluations/{evaluation_id}/apply-knowledge-template",
        json={"knowledge_template_id": template_id},
        headers=collaborator_headers,
    )
    assert response.status_code == 403
