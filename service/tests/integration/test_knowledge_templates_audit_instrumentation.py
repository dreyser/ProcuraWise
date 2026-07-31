import pytest

from tests.conftest import bearer_headers_for, unique_actor_by_role

pytestmark = pytest.mark.docker


@pytest.fixture(autouse=True)
def _clean(mongo_test_db):
    yield
    mongo_test_db["audit_events"].delete_many({})
    mongo_test_db["knowledge_templates"].delete_many({})


def _events_for_template(mongo_test_db, template_id: str) -> list[dict]:
    return list(
        mongo_test_db["audit_events"]
        .find({"resource_type": "knowledge_template", "resource_id": template_id})
        .sort("occurred_at", 1)
    )


def test_template_and_item_mutations_generate_exactly_the_expected_audit_events(
    client, seeded_actors, mongo_test_settings, mongo_test_db
) -> None:
    tenant_a, _ = unique_actor_by_role(seeded_actors, "evaluator_functional")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )

    created = client.post(
        "/api/v1/knowledge-templates",
        json={"name": "Plantilla", "description": ""},
        headers=owner_headers,
    )
    template_id = created.json()["id"]

    updated = client.patch(
        f"/api/v1/knowledge-templates/{template_id}",
        json={"name": "Plantilla renombrada"},
        headers=owner_headers,
    )
    assert updated.status_code == 200

    item = client.post(
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
    item_id = item.json()["id"]

    item_updated = client.patch(
        f"/api/v1/knowledge-templates/{template_id}/items/{item_id}",
        json={"title": "T renombrado"},
        headers=owner_headers,
    )
    assert item_updated.status_code == 200

    item_deleted = client.delete(
        f"/api/v1/knowledge-templates/{template_id}/items/{item_id}", headers=owner_headers
    )
    assert item_deleted.status_code == 204

    deleted = client.delete(f"/api/v1/knowledge-templates/{template_id}", headers=owner_headers)
    assert deleted.status_code == 204

    events = _events_for_template(mongo_test_db, template_id)
    actions = [e["action"] for e in events]
    assert actions == [
        "knowledge_template_created",
        "knowledge_template_updated",
        "knowledge_template_item_added",
        "knowledge_template_item_updated",
        "knowledge_template_item_removed",
        "knowledge_template_deleted",
    ]
    for event in events:
        assert event["resource_id"] == template_id
        assert event["evaluation_id"] is None


def test_apply_generates_exactly_one_audit_event_for_the_whole_batch(
    client, seeded_actors, mongo_test_settings, mongo_test_db
) -> None:
    tenant_a, _ = unique_actor_by_role(seeded_actors, "evaluator_functional")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )

    template_id = client.post(
        "/api/v1/knowledge-templates",
        json={"name": "Plantilla", "description": ""},
        headers=owner_headers,
    ).json()["id"]
    for offset in range(2):
        client.post(
            f"/api/v1/knowledge-templates/{template_id}/items",
            json={
                "dimension": "functional" if offset == 0 else "technical",
                "category": "Core",
                "title": f"T{offset}",
                "description": "D",
                "priority": "important",
                "response_type": "text",
                "weight": 10.0,
                "required": True,
                "display_order": offset + 1,
            },
            headers=owner_headers,
        )
    evaluation_id = client.post(
        "/api/v1/evaluations", json={"name": "RFP", "description": ""}, headers=owner_headers
    ).json()["id"]

    response = client.post(
        f"/api/v1/evaluations/{evaluation_id}/apply-knowledge-template",
        json={"knowledge_template_id": template_id},
        headers=owner_headers,
    )
    assert response.status_code == 201
    assert len(response.json()["added_requirements"]) == 2

    events = list(
        mongo_test_db["audit_events"].find(
            {"evaluation_id": evaluation_id, "action": "requirements_applied_from_template"}
        )
    )
    assert len(events) == 1
    assert events[0]["metadata"]["count"] == 2
    assert events[0]["metadata"]["knowledge_template_id"] == template_id
