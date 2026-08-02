import pytest

from procurawise.identity.dev_provider import DEV_ACTOR_HEADER
from tests.conftest import (
    approve_and_publish,
    bearer_headers_for,
    unique_actor_by_role,
    vendor_bearer_headers_for,
)

pytestmark = pytest.mark.docker


def _create_scoreable_proposal(
    client,
    owner_headers: dict,
    vendor_membership_id: str,
    *,
    tenant_id: str,
    seeded_actors: dict,
    mongo_test_settings,
) -> tuple[str, str, str]:
    """Owner creates an evaluation with one optional functional requirement,
    links the vendor, starts collection, the vendor submits without
    answering anything, and the owner starts evaluation - leaving a
    proposal that's ready to be scored. Returns
    (evaluation_id, proposal_id, requirement_id)."""
    vendor_dev_headers = {DEV_ACTOR_HEADER: vendor_membership_id}
    vendor_org_id = client.get("/api/v1/me", headers=vendor_dev_headers).json()["vendor_org_id"]
    vendor_headers = vendor_bearer_headers_for(vendor_membership_id, mongo_test_settings)

    evaluation_id = client.post(
        "/api/v1/evaluations",
        json={"name": "Scoring por seccion", "description": ""},
        headers=owner_headers,
    ).json()["id"]
    requirement_id = client.post(
        f"/api/v1/evaluations/{evaluation_id}/requirements",
        json={
            "dimension": "functional",
            "category": "Seccion Restringida",
            "title": "T",
            "description": "D",
            "priority": "important",
            "response_type": "text",
            "weight": 40.0,
            "required": False,
            "display_order": 1,
        },
        headers=owner_headers,
    ).json()["id"]
    # start-collection requires both a functional and a technical requirement
    # whose weights sum exactly to DIMENSION_MAX_POINTS - this technical one
    # only exists to satisfy that precondition, it is never scored below.
    client.post(
        f"/api/v1/evaluations/{evaluation_id}/requirements",
        json={
            "dimension": "technical",
            "category": "Seccion Tecnica",
            "title": "T2",
            "description": "D2",
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
    approver_membership_id = seeded_actors[(tenant_id, "approver")]
    approver_headers = bearer_headers_for(approver_membership_id, mongo_test_settings)
    approve_and_publish(
        client, owner_headers, approver_membership_id, approver_headers, evaluation_id
    )
    client.post(
        f"/api/v1/vendor-portal/proposals/{proposal_id}/submit",
        json={"expected_version": 1},
        headers=vendor_headers,
    )
    client.post(f"/api/v1/evaluations/{evaluation_id}/start-evaluation", headers=owner_headers)
    return evaluation_id, proposal_id, requirement_id


def test_assigned_evaluator_can_score_own_section_others_are_rejected(
    client, seeded_actors, mongo_test_settings
) -> None:
    tenant_a, vendor_membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    evaluation_id, proposal_id, requirement_id = _create_scoreable_proposal(
        client,
        owner_headers,
        vendor_membership_id,
        tenant_id=tenant_a,
        seeded_actors=seeded_actors,
        mongo_test_settings=mongo_test_settings,
    )

    assigned_membership_id = seeded_actors[(tenant_a, "evaluator_functional")]
    client.post(
        f"/api/v1/evaluations/{evaluation_id}/assignments",
        json={
            "dimension": "functional",
            "section": "Seccion Restringida",
            "evaluator_membership_id": assigned_membership_id,
        },
        headers=owner_headers,
    )

    assigned_headers = bearer_headers_for(assigned_membership_id, mongo_test_settings)
    assigned_response = client.put(
        f"/api/v1/evaluations/{evaluation_id}/proposals/{proposal_id}/scores/{requirement_id}",
        json={"score": 4},
        headers=assigned_headers,
    )
    assert assigned_response.status_code == 200

    other_evaluator_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluator_technical")], mongo_test_settings
    )
    other_response = client.put(
        f"/api/v1/evaluations/{evaluation_id}/proposals/{proposal_id}/scores/{requirement_id}",
        json={"score": 3},
        headers=other_evaluator_headers,
    )
    assert other_response.status_code == 403


def test_unassigned_section_still_scoreable_by_any_evaluator(
    client, seeded_actors, mongo_test_settings
) -> None:
    # No Assignment has been created for this section at all - Fase 9 keeps
    # today's (pre-Assignment) behavior for sections nobody has claimed yet.
    tenant_a, vendor_membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    evaluation_id, proposal_id, requirement_id = _create_scoreable_proposal(
        client,
        owner_headers,
        vendor_membership_id,
        tenant_id=tenant_a,
        seeded_actors=seeded_actors,
        mongo_test_settings=mongo_test_settings,
    )

    evaluator_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluator_technical")], mongo_test_settings
    )
    response = client.put(
        f"/api/v1/evaluations/{evaluation_id}/proposals/{proposal_id}/scores/{requirement_id}",
        json={"score": 5},
        headers=evaluator_headers,
    )
    assert response.status_code == 200


def test_internal_collaborator_cannot_write_scores(
    client, seeded_actors, mongo_test_settings
) -> None:
    # Fase 9 narrows scoring writes to owner + evaluator sub-roles only -
    # internal_collaborator/approver are in BUYER_READ_ROLES (can read) but
    # are deliberately excluded from SCORE_WRITE_ROLES.
    tenant_a, vendor_membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    evaluation_id, proposal_id, requirement_id = _create_scoreable_proposal(
        client,
        owner_headers,
        vendor_membership_id,
        tenant_id=tenant_a,
        seeded_actors=seeded_actors,
        mongo_test_settings=mongo_test_settings,
    )

    collaborator_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "internal_collaborator")], mongo_test_settings
    )
    response = client.put(
        f"/api/v1/evaluations/{evaluation_id}/proposals/{proposal_id}/scores/{requirement_id}",
        json={"score": 2},
        headers=collaborator_headers,
    )
    assert response.status_code == 403
