import pytest

from procurawise.identity.dev_provider import DEV_ACTOR_HEADER
from tests.conftest import bearer_headers_for, unique_actor_by_role

pytestmark = pytest.mark.docker


@pytest.fixture(autouse=True)
def _clean_audit_events(mongo_test_db):
    yield
    mongo_test_db["audit_events"].delete_many({})


def _events_for(mongo_test_db, evaluation_id: str) -> list[dict]:
    return list(
        mongo_test_db["audit_events"].find({"evaluation_id": evaluation_id}).sort("occurred_at", 1)
    )


def test_autosave_never_generates_an_audit_event_only_submit_does(
    client, seeded_actors, mongo_test_settings, mongo_test_db
) -> None:
    """Founder decision §18.2: ProposalAnswer autosave is high-frequency and
    deliberately not audited - only the terminal PROPOSAL_SUBMITTED event
    (with a snapshot reference, never the answer content) satisfies the
    acceptance criterion for the proposals bounded context."""
    tenant_a, vendor_membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    vendor_headers = {DEV_ACTOR_HEADER: vendor_membership_id}
    vendor_org_id = client.get("/api/v1/me", headers=vendor_headers).json()["vendor_org_id"]

    evaluation_id = client.post(
        "/api/v1/evaluations",
        json={"name": "Proposal Audit RFP", "description": ""},
        headers=owner_headers,
    ).json()["id"]

    requirement_id = client.post(
        f"/api/v1/evaluations/{evaluation_id}/requirements",
        json={
            "dimension": "functional",
            "category": "Core",
            "title": "Req 1",
            "description": "d",
            "priority": "important",
            "response_type": "text",
            "weight": 40.0,
            "required": True,
            "display_order": 1,
        },
        headers=owner_headers,
    ).json()["id"]
    client.post(
        f"/api/v1/evaluations/{evaluation_id}/requirements",
        json={
            "dimension": "technical",
            "category": "Core",
            "title": "Req 2",
            "description": "d",
            "priority": "important",
            "response_type": "text",
            "weight": 20.0,
            "required": False,
            "display_order": 2,
        },
        headers=owner_headers,
    )

    link = client.post(
        f"/api/v1/evaluations/{evaluation_id}/vendors",
        json={"vendor_org_id": vendor_org_id},
        headers=owner_headers,
    )
    proposal_id = link.json()["id"]

    client.post(f"/api/v1/evaluations/{evaluation_id}/start-collection", headers=owner_headers)

    # Three autosave writes - none of these should ever produce an AuditEvent.
    for i, value in enumerate(["draft-1", "draft-2", "final answer"]):
        response = client.put(
            f"/api/v1/vendor-portal/proposals/{proposal_id}/answers/{requirement_id}",
            json={"value": value, "expected_version": i + 1},
            headers=vendor_headers,
        )
        assert response.status_code == 200

    events_before_submit = _events_for(mongo_test_db, evaluation_id)
    actions_before_submit = [e["action"] for e in events_before_submit]
    # vendor_linked legitimately has resource_type="proposal" (it's the
    # Proposal created by linking); what must be absent is any event tied to
    # the 3 autosave writes above.
    assert "proposal_submitted" not in actions_before_submit
    assert actions_before_submit.count("vendor_linked") == 1

    submitted = client.post(
        f"/api/v1/vendor-portal/proposals/{proposal_id}/submit",
        json={"expected_version": 4},
        headers=vendor_headers,
    )
    assert submitted.status_code == 200
    # VendorProposalDetailResponse deliberately has no top-level snapshot_id
    # (vendor-portal schemas never expose that field) - read it from the
    # persisted document instead, just to cross-check the audited value.
    snapshot_id = mongo_test_db["proposals"].find_one({"_id": proposal_id})["snapshot"][
        "snapshot_id"
    ]

    events_after_submit = _events_for(mongo_test_db, evaluation_id)
    submit_events = [e for e in events_after_submit if e["action"] == "proposal_submitted"]
    assert len(submit_events) == 1

    submit_event = submit_events[0]
    assert submit_event["resource_type"] == "proposal"
    assert submit_event["resource_id"] == proposal_id
    assert submit_event["proposal_id"] == proposal_id
    assert submit_event["snapshot_id"] == snapshot_id
    assert submit_event["version"] == 5
    assert submit_event["actor_type"] == "vendor_contact"
    assert submit_event["actor_vendor_org_id"] == vendor_org_id
    assert submit_event["metadata"] == {"requirements_answered_count": 1}

    # Never the answer content, vendor comments, or pricing - only counts/ids.
    metadata_values = str(submit_event["metadata"])
    assert "final answer" not in metadata_values
    assert "draft-1" not in metadata_values


def test_rejected_submit_does_not_generate_an_audit_event(
    client, seeded_actors, mongo_test_settings, mongo_test_db
) -> None:
    """A stale-version submit (409) must not leave a proposal_submitted
    event behind - plan §9: rejected mutations never produce a success
    event."""
    tenant_a, vendor_membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    vendor_headers = {DEV_ACTOR_HEADER: vendor_membership_id}
    vendor_org_id = client.get("/api/v1/me", headers=vendor_headers).json()["vendor_org_id"]

    evaluation_id = client.post(
        "/api/v1/evaluations",
        json={"name": "Reject Submit RFP", "description": ""},
        headers=owner_headers,
    ).json()["id"]
    client.post(
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
    client.post(
        f"/api/v1/evaluations/{evaluation_id}/requirements",
        json={
            "dimension": "technical",
            "category": "Core",
            "title": "Req 2",
            "description": "d",
            "priority": "important",
            "response_type": "text",
            "weight": 20.0,
            "required": False,
            "display_order": 2,
        },
        headers=owner_headers,
    )
    proposal_id = client.post(
        f"/api/v1/evaluations/{evaluation_id}/vendors",
        json={"vendor_org_id": vendor_org_id},
        headers=owner_headers,
    ).json()["id"]
    client.post(f"/api/v1/evaluations/{evaluation_id}/start-collection", headers=owner_headers)

    rejected = client.post(
        f"/api/v1/vendor-portal/proposals/{proposal_id}/submit",
        json={"expected_version": 999},
        headers=vendor_headers,
    )
    assert rejected.status_code == 409

    events = _events_for(mongo_test_db, evaluation_id)
    assert "proposal_submitted" not in [e["action"] for e in events]
