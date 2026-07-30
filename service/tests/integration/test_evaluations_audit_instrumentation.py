import pytest

from tests.conftest import bearer_headers_for, tenant_ids, unique_actor_by_role

pytestmark = pytest.mark.docker


@pytest.fixture(autouse=True)
def _clean_audit_events(mongo_test_db):
    yield
    mongo_test_db["audit_events"].delete_many({})


def _events_for(mongo_test_db, evaluation_id: str) -> list[dict]:
    return list(
        mongo_test_db["audit_events"].find({"evaluation_id": evaluation_id}).sort("occurred_at", 1)
    )


def test_evaluation_lifecycle_generates_exactly_the_expected_audit_events(
    client, seeded_actors, mongo_test_settings, mongo_test_db
) -> None:
    """Plan §6/§13: every one of the 9 evaluations mutations must generate
    exactly the AuditEvent described in the instrumentation matrix - no more,
    no fewer - with server-derived actor/tenant fields and only the
    allowlisted metadata (never raw field values)."""
    # dev_seed only seeds a VendorOrganization/vendor_contact under one
    # tenant (see tests/api/test_vertical_slice_happy_path.py) - resolve that
    # tenant by role rather than tenant_ids()'s arbitrary sorted pair, or the
    # vendor-organizations catalog lookup below could come back empty.
    tenant_a, _vendor_membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    owner_membership_id = seeded_actors[(tenant_a, "evaluation_owner")]
    owner_headers = bearer_headers_for(owner_membership_id, mongo_test_settings)

    created = client.post(
        "/api/v1/evaluations",
        json={"name": "Audit RFP", "description": "desc"},
        headers=owner_headers,
    )
    assert created.status_code == 201
    evaluation_id = created.json()["id"]

    updated = client.patch(
        f"/api/v1/evaluations/{evaluation_id}",
        json={"name": "Audit RFP Renamed"},
        headers=owner_headers,
    )
    assert updated.status_code == 200

    requirement = client.post(
        f"/api/v1/evaluations/{evaluation_id}/requirements",
        json={
            "dimension": "functional",
            "category": "Core",
            "title": "Req 1",
            "description": "d",
            "priority": "important",
            "response_type": "text",
            "weight": 40.0,
            "required": False,
            "display_order": 1,
        },
        headers=owner_headers,
    )
    assert requirement.status_code == 201
    requirement_id = requirement.json()["id"]

    requirement_updated = client.patch(
        f"/api/v1/evaluations/{evaluation_id}/requirements/{requirement_id}",
        json={"title": "Req 1 renamed"},
        headers=owner_headers,
    )
    assert requirement_updated.status_code == 200

    technical_requirement = client.post(
        f"/api/v1/evaluations/{evaluation_id}/requirements",
        json={
            "dimension": "technical",
            "category": "Core",
            "title": "Req 2 (to delete)",
            "description": "d",
            "priority": "important",
            "response_type": "text",
            "weight": 20.0,
            "required": False,
            "display_order": 2,
        },
        headers=owner_headers,
    )
    assert technical_requirement.status_code == 201
    technical_requirement_id = technical_requirement.json()["id"]

    deleted = client.delete(
        f"/api/v1/evaluations/{evaluation_id}/requirements/{technical_requirement_id}",
        headers=owner_headers,
    )
    assert deleted.status_code == 204

    # Re-add a technical requirement so start-collection's dimension
    # precondition (>=1 functional + >=1 technical, weights summing to
    # 40/20) is satisfiable after the delete above.
    technical_requirement_2 = client.post(
        f"/api/v1/evaluations/{evaluation_id}/requirements",
        json={
            "dimension": "technical",
            "category": "Core",
            "title": "Req 2b",
            "description": "d",
            "priority": "important",
            "response_type": "text",
            "weight": 20.0,
            "required": False,
            "display_order": 2,
        },
        headers=owner_headers,
    )
    assert technical_requirement_2.status_code == 201

    vendor_orgs = client.get("/api/v1/vendor-organizations?limit=1", headers=owner_headers).json()[
        "items"
    ]
    vendor_org_id = vendor_orgs[0]["id"]

    linked = client.post(
        f"/api/v1/evaluations/{evaluation_id}/vendors",
        json={"vendor_org_id": vendor_org_id},
        headers=owner_headers,
    )
    assert linked.status_code == 201

    unlinked = client.delete(
        f"/api/v1/evaluations/{evaluation_id}/vendors/{vendor_org_id}", headers=owner_headers
    )
    assert unlinked.status_code == 204

    # Re-link so start-collection's "at least one vendor linked" precondition holds.
    relinked = client.post(
        f"/api/v1/evaluations/{evaluation_id}/vendors",
        json={"vendor_org_id": vendor_org_id},
        headers=owner_headers,
    )
    assert relinked.status_code == 201

    started_collection = client.post(
        f"/api/v1/evaluations/{evaluation_id}/start-collection", headers=owner_headers
    )
    assert started_collection.status_code == 200

    started_evaluation = client.post(
        f"/api/v1/evaluations/{evaluation_id}/start-evaluation", headers=owner_headers
    )
    assert started_evaluation.status_code == 200

    events = _events_for(mongo_test_db, evaluation_id)
    actions = [e["action"] for e in events]

    assert actions == [
        "evaluation_created",
        "evaluation_updated",
        "requirement_added",
        "requirement_updated",
        "requirement_added",
        "requirement_deleted",
        "requirement_added",
        "vendor_linked",
        "vendor_unlinked",
        "vendor_linked",
        "evaluation_collection_started",
        "evaluation_scoring_started",
    ]

    # Every event: server-derived actor/tenant fields, never trusted from a body.
    for event in events:
        assert event["tenant_id"] == tenant_a
        assert event["actor_membership_id"] == owner_membership_id
        assert event["actor_role"] == "evaluation_owner"
        assert event["actor_type"] == "buyer"
        assert event["outcome"] == "success"

    created_event = events[0]
    assert created_event["metadata"] == {"name": "Audit RFP"}
    assert created_event["resource_type"] == "evaluation"
    assert created_event["resource_id"] == evaluation_id

    updated_event = events[1]
    assert updated_event["metadata"] == {"fields_changed": ["name"]}

    requirement_added_event = events[2]
    assert requirement_added_event["resource_type"] == "requirement"
    assert requirement_added_event["metadata"] == {"requirement_id": requirement_id}

    requirement_updated_event = events[3]
    assert requirement_updated_event["metadata"] == {
        "requirement_id": requirement_id,
        "fields_changed": ["title"],
    }

    requirement_deleted_event = events[5]
    assert requirement_deleted_event["action"] == "requirement_deleted"
    assert requirement_deleted_event["metadata"] == {"requirement_id": technical_requirement_id}

    vendor_linked_event = events[7]
    assert vendor_linked_event["resource_type"] == "proposal"
    assert vendor_linked_event["metadata"] == {"vendor_org_id": vendor_org_id}
    assert vendor_linked_event["proposal_id"] is not None

    vendor_unlinked_event = events[8]
    assert vendor_unlinked_event["action"] == "vendor_unlinked"
    assert vendor_unlinked_event["metadata"] == {"vendor_org_id": vendor_org_id}

    collection_started_event = events[10]
    assert collection_started_event["metadata"] == {
        "from_status": "draft",
        "to_status": "collecting_responses",
    }

    evaluation_started_event = events[11]
    assert evaluation_started_event["action"] == "evaluation_scoring_started"
    assert evaluation_started_event["metadata"] == {
        "from_status": "collecting_responses",
        "to_status": "evaluating",
    }


def test_rejected_mutation_does_not_generate_an_audit_event(
    client, seeded_actors, mongo_test_settings, mongo_test_db
) -> None:
    """A 409 (invalid transition) must not leave a success AuditEvent behind
    - plan §9/§15: rejected mutations never produce an event."""
    tenant_a, _tenant_b = tenant_ids(seeded_actors)
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )

    created = client.post(
        "/api/v1/evaluations",
        json={"name": "Reject RFP", "description": ""},
        headers=owner_headers,
    )
    evaluation_id = created.json()["id"]

    # start-evaluation is only valid from collecting_responses; this
    # evaluation is still draft, so it must 409 and record no event.
    rejected = client.post(
        f"/api/v1/evaluations/{evaluation_id}/start-evaluation", headers=owner_headers
    )
    assert rejected.status_code == 409

    events = _events_for(mongo_test_db, evaluation_id)
    actions = [e["action"] for e in events]
    assert "evaluation_scoring_started" not in actions
    assert actions == ["evaluation_created"]
