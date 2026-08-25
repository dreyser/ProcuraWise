import pytest

from tests.conftest import bearer_headers_for, unique_actor_by_role

pytestmark = pytest.mark.docker


def _requirement_payload(dimension: str, weight: float) -> dict:
    return {
        "dimension": dimension,
        "category": "c",
        "title": f"{dimension} requirement",
        "description": "d",
        "priority": "important",
        "response_type": "text",
        "weight": weight,
        "required": False,
        "display_order": 1,
    }


def _draft_ready_evaluation(client, owner_headers: dict, vendor_org_id: str) -> str:
    """Creates an evaluation with valid weights + one linked vendor - the
    shared draft-readiness precondition for both the review and approval
    stages (ADR 0026)."""
    evaluation_id = client.post(
        "/api/v1/evaluations",
        json={"name": "R2 RFP", "description": ""},
        headers=owner_headers,
    ).json()["id"]
    client.post(
        f"/api/v1/evaluations/{evaluation_id}/requirements",
        json=_requirement_payload("functional", 40.0),
        headers=owner_headers,
    )
    client.post(
        f"/api/v1/evaluations/{evaluation_id}/requirements",
        json=_requirement_payload("technical", 20.0),
        headers=owner_headers,
    )
    client.post(
        f"/api/v1/evaluations/{evaluation_id}/vendors",
        json={"vendor_org_id": vendor_org_id},
        headers=owner_headers,
    )
    return evaluation_id


@pytest.fixture
def review_actors(client, seeded_actors, mongo_test_settings) -> dict:
    tenant_a, vendor_membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    reviewer_membership_id = seeded_actors[(tenant_a, "internal_collaborator")]
    reviewer_headers = bearer_headers_for(reviewer_membership_id, mongo_test_settings)
    approver_membership_id = seeded_actors[(tenant_a, "approver")]
    approver_headers = bearer_headers_for(approver_membership_id, mongo_test_settings)
    from procurawise.identity.dev_provider import DEV_ACTOR_HEADER

    vendor_org_id = client.get(
        "/api/v1/me", headers={DEV_ACTOR_HEADER: vendor_membership_id}
    ).json()["vendor_org_id"]
    return {
        "tenant_id": tenant_a,
        "owner_headers": owner_headers,
        "reviewer_membership_id": reviewer_membership_id,
        "reviewer_headers": reviewer_headers,
        "approver_membership_id": approver_membership_id,
        "approver_headers": approver_headers,
        "vendor_org_id": vendor_org_id,
    }


def test_review_approval_journey_auto_chains_to_pending_approver(client, review_actors) -> None:
    """ADR 0026 (R2) core journey: Owner assigns reviewer+approver, requests
    review; the reviewer's approval auto-chains into "pending approver" in
    the same action (blocking question #2, no second manual owner step);
    the approver then approves and publication proceeds exactly like the
    one-step flow already did."""
    owner_headers = review_actors["owner_headers"]
    evaluation_id = _draft_ready_evaluation(client, owner_headers, review_actors["vendor_org_id"])

    reviewer_set = client.post(
        f"/api/v1/evaluations/{evaluation_id}/reviewer",
        json={"reviewer_membership_id": review_actors["reviewer_membership_id"]},
        headers=owner_headers,
    )
    assert reviewer_set.status_code == 200, reviewer_set.text

    approver_set = client.post(
        f"/api/v1/evaluations/{evaluation_id}/approver",
        json={"approver_membership_id": review_actors["approver_membership_id"]},
        headers=owner_headers,
    )
    assert approver_set.status_code == 200, approver_set.text

    deadline_set = client.patch(
        f"/api/v1/evaluations/{evaluation_id}",
        json={"response_deadline": "2030-01-01T00:00:00Z"},
        headers=owner_headers,
    )
    assert deadline_set.status_code == 200, deadline_set.text

    readiness_before = client.get(
        f"/api/v1/evaluations/{evaluation_id}/publication-readiness", headers=owner_headers
    ).json()
    assert readiness_before["can_request_review"] is True
    # Reviewer is assigned but hasn't approved yet - approval must stay
    # blocked on the review gate even though approver+deadline are set.
    assert readiness_before["can_request_approval"] is False
    assert any("review" in reason for reason in readiness_before["request_approval_reasons"])

    request_review = client.post(
        f"/api/v1/evaluations/{evaluation_id}/request-review", headers=owner_headers
    )
    assert request_review.status_code == 200, request_review.text
    assert request_review.json()["review_status"] == "pending"

    review_approve = client.post(
        f"/api/v1/evaluations/{evaluation_id}/review/approve",
        json={"comment": "se ve bien"},
        headers=review_actors["reviewer_headers"],
    )
    assert review_approve.status_code == 200, review_approve.text
    body = review_approve.json()
    assert body["review_status"] == "approved"
    # Auto-chain (blocking question #2): approval_status is already
    # "pending" without the owner calling request-approval separately.
    assert body["approval_status"] == "pending"

    approve = client.post(
        f"/api/v1/evaluations/{evaluation_id}/approve",
        json={},
        headers=review_actors["approver_headers"],
    )
    assert approve.status_code == 200, approve.text
    assert approve.json()["approval_status"] == "approved"

    publish = client.post(
        f"/api/v1/evaluations/{evaluation_id}/start-collection", headers=owner_headers
    )
    assert publish.status_code == 200, publish.text


def test_review_changes_requested_persists_rejected_with_requirement_notes(
    client, review_actors
) -> None:
    """Blocking question resolved 2026-08-24: "solicitar cambios" persists
    the same review_status="rejected" as a generic reject, distinguished
    only by the audit action, with per-requirement comments preserved."""
    owner_headers = review_actors["owner_headers"]
    evaluation_id = _draft_ready_evaluation(client, owner_headers, review_actors["vendor_org_id"])
    requirement_id = client.get(
        f"/api/v1/evaluations/{evaluation_id}", headers=owner_headers
    ).json()["requirements"][0]["id"]
    client.post(
        f"/api/v1/evaluations/{evaluation_id}/reviewer",
        json={"reviewer_membership_id": review_actors["reviewer_membership_id"]},
        headers=owner_headers,
    )
    client.post(f"/api/v1/evaluations/{evaluation_id}/request-review", headers=owner_headers)

    reject = client.post(
        f"/api/v1/evaluations/{evaluation_id}/review/reject",
        json={
            "comment": "faltan detalles",
            "kind": "changes_requested",
            "requirement_notes": [{"requirement_id": requirement_id, "comment": "aclarar esto"}],
        },
        headers=review_actors["reviewer_headers"],
    )
    assert reject.status_code == 200, reject.text
    body = reject.json()
    assert body["review_status"] == "rejected"
    assert body["review_comment"] == "faltan detalles"
    # approval_status was never touched - it never left not_requested.
    assert body["approval_status"] == "not_requested"

    # The owner may request review again from "rejected" (same loop-back
    # shape as the approver's own rejected -> pending re-request).
    request_again = client.post(
        f"/api/v1/evaluations/{evaluation_id}/request-review", headers=owner_headers
    )
    assert request_again.status_code == 200, request_again.text
    assert request_again.json()["review_status"] == "pending"


def test_reviewer_never_approves_via_the_approver_endpoint(client, review_actors) -> None:
    """R2 acceptance criterion: reviewer never approves (only the assigned
    approver may call /approve, even for an evaluation this same reviewer
    was correctly assigned to review)."""
    owner_headers = review_actors["owner_headers"]
    evaluation_id = _draft_ready_evaluation(client, owner_headers, review_actors["vendor_org_id"])
    client.post(
        f"/api/v1/evaluations/{evaluation_id}/reviewer",
        json={"reviewer_membership_id": review_actors["reviewer_membership_id"]},
        headers=owner_headers,
    )
    client.post(
        f"/api/v1/evaluations/{evaluation_id}/approver",
        json={"approver_membership_id": review_actors["approver_membership_id"]},
        headers=owner_headers,
    )
    client.patch(
        f"/api/v1/evaluations/{evaluation_id}",
        json={"response_deadline": "2030-01-01T00:00:00Z"},
        headers=owner_headers,
    )
    client.post(f"/api/v1/evaluations/{evaluation_id}/request-review", headers=owner_headers)

    denied = client.post(
        f"/api/v1/evaluations/{evaluation_id}/approve",
        json={},
        headers=review_actors["reviewer_headers"],
    )
    assert denied.status_code == 403


def test_approver_never_edits_requirements(client, review_actors) -> None:
    """R2 acceptance criterion: approver never edits - require_owner already
    gates every requirement-mutating route, this exercises it for the
    approver role specifically (the new actor this ADR introduces
    alongside)."""
    owner_headers = review_actors["owner_headers"]
    evaluation_id = _draft_ready_evaluation(client, owner_headers, review_actors["vendor_org_id"])
    denied = client.post(
        f"/api/v1/evaluations/{evaluation_id}/requirements",
        json=_requirement_payload("functional", 1.0),
        headers=review_actors["approver_headers"],
    )
    assert denied.status_code == 403


def test_non_assigned_internal_collaborator_cannot_decide_review(
    client, review_actors, mongo_test_db, mongo_test_settings
) -> None:
    """Holding the internal_collaborator role is necessary but not
    sufficient - only the specific Membership the owner designated as
    reviewer_membership_id may decide (mirrors NotAssignedApproverError)."""
    from procurawise.identity.models import Membership, User
    from procurawise.identity.repository import MembershipRepository, UserRepository

    owner_headers = review_actors["owner_headers"]
    evaluation_id = _draft_ready_evaluation(client, owner_headers, review_actors["vendor_org_id"])
    client.post(
        f"/api/v1/evaluations/{evaluation_id}/reviewer",
        json={"reviewer_membership_id": review_actors["reviewer_membership_id"]},
        headers=owner_headers,
    )
    client.post(f"/api/v1/evaluations/{evaluation_id}/request-review", headers=owner_headers)

    users = UserRepository(mongo_test_db)
    memberships = MembershipRepository(mongo_test_db)
    user = User.create(display_name="Other Reviewer", email="other.reviewer@dev.local")
    users.insert(user.to_document())
    other_membership = Membership.create(
        tenant_id=review_actors["tenant_id"],
        user_id=user.id,
        role="internal_collaborator",
    )
    memberships.insert(other_membership.to_document())

    other_headers = bearer_headers_for(other_membership.id, mongo_test_settings)
    denied = client.post(
        f"/api/v1/evaluations/{evaluation_id}/review/approve",
        json={},
        headers=other_headers,
    )
    assert denied.status_code == 403


def test_set_reviewer_rejects_non_internal_collaborator_role(client, review_actors) -> None:
    owner_headers = review_actors["owner_headers"]
    evaluation_id = _draft_ready_evaluation(client, owner_headers, review_actors["vendor_org_id"])
    denied = client.post(
        f"/api/v1/evaluations/{evaluation_id}/reviewer",
        json={"reviewer_membership_id": review_actors["approver_membership_id"]},
        headers=owner_headers,
    )
    assert denied.status_code == 400


def test_request_review_fails_without_a_reviewer_assigned(client, review_actors) -> None:
    owner_headers = review_actors["owner_headers"]
    evaluation_id = _draft_ready_evaluation(client, owner_headers, review_actors["vendor_org_id"])
    denied = client.post(
        f"/api/v1/evaluations/{evaluation_id}/request-review", headers=owner_headers
    )
    assert denied.status_code == 400


def test_evaluation_without_a_reviewer_keeps_the_pre_r2_approval_flow_unchanged(
    client, review_actors
) -> None:
    """ADR 0026 (R2), blocking question #1: the review stage is optional per
    evaluation - one that never assigns a reviewer must request/receive
    approval exactly like every pre-R2 evaluation, with no mention of review
    in its readiness reasons at all."""
    owner_headers = review_actors["owner_headers"]
    evaluation_id = _draft_ready_evaluation(client, owner_headers, review_actors["vendor_org_id"])
    client.post(
        f"/api/v1/evaluations/{evaluation_id}/approver",
        json={"approver_membership_id": review_actors["approver_membership_id"]},
        headers=owner_headers,
    )
    client.patch(
        f"/api/v1/evaluations/{evaluation_id}",
        json={"response_deadline": "2030-01-01T00:00:00Z"},
        headers=owner_headers,
    )
    readiness = client.get(
        f"/api/v1/evaluations/{evaluation_id}/publication-readiness", headers=owner_headers
    ).json()
    assert readiness["can_request_approval"] is True
    assert readiness["request_approval_reasons"] == []

    request_approval = client.post(
        f"/api/v1/evaluations/{evaluation_id}/request-approval", headers=owner_headers
    )
    assert request_approval.status_code == 200, request_approval.text
    assert request_approval.json()["approval_status"] == "pending"
