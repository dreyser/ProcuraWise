import pytest

from tests.conftest import bearer_headers_for, tenant_ids

pytestmark = pytest.mark.docker


@pytest.fixture(autouse=True)
def _clean_knowledge_templates(mongo_test_db):
    yield
    mongo_test_db["knowledge_templates"].delete_many({})


def _create_template(client, owner_headers) -> str:
    created = client.post(
        "/api/v1/knowledge-templates",
        json={"name": "Plantilla tenant A", "description": ""},
        headers=owner_headers,
    )
    assert created.status_code == 201
    return created.json()["id"]


def _add_item(client, owner_headers, template_id: str) -> str:
    response = client.post(
        f"/api/v1/knowledge-templates/{template_id}/items",
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


def test_owner_of_other_tenant_gets_404_reading_template(
    client, seeded_actors, mongo_test_settings
) -> None:
    tenant_a, tenant_b = tenant_ids(seeded_actors)
    owner_a_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    owner_b_headers = bearer_headers_for(
        seeded_actors[(tenant_b, "evaluation_owner")], mongo_test_settings
    )
    template_id = _create_template(client, owner_a_headers)

    response = client.get(f"/api/v1/knowledge-templates/{template_id}", headers=owner_b_headers)
    assert response.status_code == 404


def test_owner_of_other_tenant_gets_404_listing_template_omits_cross_tenant_data(
    client, seeded_actors, mongo_test_settings
) -> None:
    tenant_a, tenant_b = tenant_ids(seeded_actors)
    owner_a_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    owner_b_headers = bearer_headers_for(
        seeded_actors[(tenant_b, "evaluation_owner")], mongo_test_settings
    )
    template_id = _create_template(client, owner_a_headers)

    listed = client.get("/api/v1/knowledge-templates", headers=owner_b_headers)
    assert listed.status_code == 200
    assert template_id not in {item["id"] for item in listed.json()["items"]}


def test_owner_of_other_tenant_gets_404_updating_template(
    client, seeded_actors, mongo_test_settings
) -> None:
    tenant_a, tenant_b = tenant_ids(seeded_actors)
    owner_a_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    owner_b_headers = bearer_headers_for(
        seeded_actors[(tenant_b, "evaluation_owner")], mongo_test_settings
    )
    template_id = _create_template(client, owner_a_headers)

    response = client.patch(
        f"/api/v1/knowledge-templates/{template_id}",
        json={"name": "hijacked"},
        headers=owner_b_headers,
    )
    assert response.status_code == 404


def test_owner_of_other_tenant_gets_404_deleting_template(
    client, seeded_actors, mongo_test_settings
) -> None:
    tenant_a, tenant_b = tenant_ids(seeded_actors)
    owner_a_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    owner_b_headers = bearer_headers_for(
        seeded_actors[(tenant_b, "evaluation_owner")], mongo_test_settings
    )
    template_id = _create_template(client, owner_a_headers)

    response = client.delete(f"/api/v1/knowledge-templates/{template_id}", headers=owner_b_headers)
    assert response.status_code == 404


def test_owner_of_other_tenant_gets_404_adding_item(
    client, seeded_actors, mongo_test_settings
) -> None:
    tenant_a, tenant_b = tenant_ids(seeded_actors)
    owner_a_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    owner_b_headers = bearer_headers_for(
        seeded_actors[(tenant_b, "evaluation_owner")], mongo_test_settings
    )
    template_id = _create_template(client, owner_a_headers)

    response = client.post(
        f"/api/v1/knowledge-templates/{template_id}/items",
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
        headers=owner_b_headers,
    )
    assert response.status_code == 404


def test_cannot_apply_a_template_from_another_tenant_to_own_evaluation(
    client, seeded_actors, mongo_test_settings
) -> None:
    tenant_a, tenant_b = tenant_ids(seeded_actors)
    owner_a_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    owner_b_headers = bearer_headers_for(
        seeded_actors[(tenant_b, "evaluation_owner")], mongo_test_settings
    )
    template_id = _create_template(client, owner_a_headers)
    _add_item(client, owner_a_headers, template_id)
    evaluation_b_id = _create_evaluation(client, owner_b_headers)

    response = client.post(
        f"/api/v1/evaluations/{evaluation_b_id}/apply-knowledge-template",
        json={"knowledge_template_id": template_id},
        headers=owner_b_headers,
    )
    assert response.status_code == 404

    # The cross-tenant attempt must not have mutated tenant B's evaluation.
    evaluation_b = client.get(f"/api/v1/evaluations/{evaluation_b_id}", headers=owner_b_headers)
    assert evaluation_b.json()["requirements"] == []


def test_cannot_apply_own_template_to_another_tenants_evaluation(
    client, seeded_actors, mongo_test_settings
) -> None:
    tenant_a, tenant_b = tenant_ids(seeded_actors)
    owner_a_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    owner_b_headers = bearer_headers_for(
        seeded_actors[(tenant_b, "evaluation_owner")], mongo_test_settings
    )
    template_id = _create_template(client, owner_a_headers)
    _add_item(client, owner_a_headers, template_id)
    evaluation_b_id = _create_evaluation(client, owner_b_headers)

    # owner_a attempting to apply their own template onto tenant B's
    # evaluation id must 404 on the evaluation lookup (tenant-scoped),
    # never reach the template at all.
    response = client.post(
        f"/api/v1/evaluations/{evaluation_b_id}/apply-knowledge-template",
        json={"knowledge_template_id": template_id},
        headers=owner_a_headers,
    )
    assert response.status_code == 404
