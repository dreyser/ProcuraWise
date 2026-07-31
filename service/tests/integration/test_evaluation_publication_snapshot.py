import pytest

from procurawise.evaluations.repository import EvaluationRepository
from procurawise.identity.dev_provider import DEV_ACTOR_HEADER
from tests.conftest import bearer_headers_for, unique_actor_by_role

pytestmark = pytest.mark.docker


def _approved_evaluation(client, seeded_actors, mongo_test_settings) -> tuple[str, str, dict]:
    """Owner builds a fully-configured, approved-but-not-yet-published
    evaluation - the exact state start-collection expects on its "commit
    point" branch (plan §22 step 2)."""
    tenant_a, vendor_membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )

    evaluation_id = client.post(
        "/api/v1/evaluations",
        json={"name": "Snapshot RFP", "description": ""},
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
    vendor_headers = {DEV_ACTOR_HEADER: vendor_membership_id}
    vendor_org_id = client.get("/api/v1/me", headers=vendor_headers).json()["vendor_org_id"]
    client.post(
        f"/api/v1/evaluations/{evaluation_id}/vendors",
        json={"vendor_org_id": vendor_org_id},
        headers=owner_headers,
    )

    approver_membership_id = seeded_actors[(tenant_a, "approver")]
    approver_headers = bearer_headers_for(approver_membership_id, mongo_test_settings)

    deadline_response = client.patch(
        f"/api/v1/evaluations/{evaluation_id}",
        json={"response_deadline": "2030-01-01T00:00:00Z"},
        headers=owner_headers,
    )
    assert deadline_response.status_code == 200
    client.post(
        f"/api/v1/evaluations/{evaluation_id}/approver",
        json={"approver_membership_id": approver_membership_id},
        headers=owner_headers,
    )
    client.post(f"/api/v1/evaluations/{evaluation_id}/request-approval", headers=owner_headers)
    client.post(f"/api/v1/evaluations/{evaluation_id}/approve", json={}, headers=approver_headers)
    return evaluation_id, tenant_a, owner_headers


def test_publish_creates_exactly_one_snapshot_and_sets_approval_snapshot_id(
    client, seeded_actors, mongo_test_settings, mongo_test_db
) -> None:
    evaluation_id, _tenant_a, owner_headers = _approved_evaluation(
        client, seeded_actors, mongo_test_settings
    )

    response = client.post(
        f"/api/v1/evaluations/{evaluation_id}/start-collection", headers=owner_headers
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "collecting_responses"
    assert body["approval_snapshot_id"] == evaluation_id

    snapshots = list(mongo_test_db["evaluation_snapshots"].find({"evaluation_id": evaluation_id}))
    assert len(snapshots) == 1
    assert snapshots[0]["_id"] == evaluation_id

    snapshot_response = client.get(
        f"/api/v1/evaluations/{evaluation_id}/snapshot", headers=owner_headers
    )
    assert snapshot_response.status_code == 200
    snapshot_body = snapshot_response.json()
    assert snapshot_body["snapshot_id"] == evaluation_id
    assert snapshot_body["dimension_weights"] == {"functional": 40.0, "technical": 20.0}
    assert len(snapshot_body["linked_vendor_org_ids"]) == 1


def test_publish_retry_after_full_success_is_a_no_op(
    client, seeded_actors, mongo_test_settings, mongo_test_db
) -> None:
    """Plan §22 step 1, full-success branch: retrying the identical publish
    call after it already fully succeeded must not create a second
    snapshot or error."""
    evaluation_id, _tenant_a, owner_headers = _approved_evaluation(
        client, seeded_actors, mongo_test_settings
    )
    first = client.post(
        f"/api/v1/evaluations/{evaluation_id}/start-collection", headers=owner_headers
    )
    assert first.status_code == 200

    retry = client.post(
        f"/api/v1/evaluations/{evaluation_id}/start-collection", headers=owner_headers
    )
    assert retry.status_code == 200
    assert retry.json()["approval_snapshot_id"] == evaluation_id

    snapshots = list(mongo_test_db["evaluation_snapshots"].find({"evaluation_id": evaluation_id}))
    assert len(snapshots) == 1


def test_publish_resumes_from_crash_between_status_transition_and_snapshot(
    client, seeded_actors, mongo_test_settings, mongo_test_db
) -> None:
    """Plan §22 step 1, crash-recovery branch: simulates a process dying
    after the atomic draft -> collecting_responses write commits but before
    the snapshot step ever runs (by driving that first write directly
    through the repository, bypassing the service's start_collection
    orchestration entirely - exactly the partial state a real crash would
    leave behind). The next call to POST start-collection must detect this
    (status == collecting_responses, approval_snapshot_id still unset) and
    finish the job, converging to exactly one snapshot."""
    evaluation_id, tenant_a, owner_headers = _approved_evaluation(
        client, seeded_actors, mongo_test_settings
    )

    evaluations = EvaluationRepository(mongo_test_db)
    matched = evaluations.transition_status(
        tenant_a, evaluation_id, "draft", "collecting_responses"
    )
    assert matched

    doc_after_simulated_crash = mongo_test_db["evaluations"].find_one({"_id": evaluation_id})
    assert doc_after_simulated_crash["status"] == "collecting_responses"
    assert doc_after_simulated_crash["approval_snapshot_id"] is None
    assert (
        mongo_test_db["evaluation_snapshots"].count_documents({"evaluation_id": evaluation_id}) == 0
    )

    resumed = client.post(
        f"/api/v1/evaluations/{evaluation_id}/start-collection", headers=owner_headers
    )
    assert resumed.status_code == 200
    assert resumed.json()["approval_snapshot_id"] == evaluation_id

    snapshots = list(mongo_test_db["evaluation_snapshots"].find({"evaluation_id": evaluation_id}))
    assert len(snapshots) == 1

    # A further retry after the resume must still be a clean no-op.
    second_retry = client.post(
        f"/api/v1/evaluations/{evaluation_id}/start-collection", headers=owner_headers
    )
    assert second_retry.status_code == 200
    snapshots_after_second_retry = list(
        mongo_test_db["evaluation_snapshots"].find({"evaluation_id": evaluation_id})
    )
    assert len(snapshots_after_second_retry) == 1


def test_publish_blocked_without_approval(client, seeded_actors, mongo_test_settings) -> None:
    tenant_a, _vendor_membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    evaluation_id = client.post(
        "/api/v1/evaluations",
        json={"name": "Unapproved RFP", "description": ""},
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
    _tenant_a2, vendor_membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    vendor_headers = {DEV_ACTOR_HEADER: vendor_membership_id}
    vendor_org_id = client.get("/api/v1/me", headers=vendor_headers).json()["vendor_org_id"]
    client.post(
        f"/api/v1/evaluations/{evaluation_id}/vendors",
        json={"vendor_org_id": vendor_org_id},
        headers=owner_headers,
    )

    # Weights + vendor are ready, but approval was never requested/granted.
    response = client.post(
        f"/api/v1/evaluations/{evaluation_id}/start-collection", headers=owner_headers
    )
    assert response.status_code == 400
    assert "approved" in response.json()["detail"]


def test_snapshot_not_found_before_publication(client, seeded_actors, mongo_test_settings) -> None:
    tenant_a, _vendor_membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    evaluation_id = client.post(
        "/api/v1/evaluations",
        json={"name": "No Snapshot Yet RFP", "description": ""},
        headers=owner_headers,
    ).json()["id"]
    response = client.get(f"/api/v1/evaluations/{evaluation_id}/snapshot", headers=owner_headers)
    assert response.status_code == 404
