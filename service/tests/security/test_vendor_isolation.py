import pytest

from procurawise.identity.dev_provider import DEV_ACTOR_HEADER
from procurawise.identity.models import Membership, User, VendorOrganization
from procurawise.identity.repository import (
    MembershipRepository,
    UserRepository,
    VendorOrganizationRepository,
)
from tests.conftest import bearer_headers_for, unique_actor_by_role

pytestmark = pytest.mark.docker


def _create_second_vendor_contact(mongo_test_db, tenant_id: str) -> str:
    """Seeds a second VendorOrganization+vendor_contact under the same
    tenant, outside of dev_seed.py (which only ever seeds one) - needed to
    prove one vendor_org_id can never see another's proposal even within
    the same buyer tenant."""
    users = UserRepository(mongo_test_db)
    vendor_orgs = VendorOrganizationRepository(mongo_test_db)
    memberships = MembershipRepository(mongo_test_db)

    user = User.create(display_name="Vendor Contact B", email="vendor.b.isolation@dev.local")
    users.insert(user.to_document())
    vendor_org = VendorOrganization.create(tenant_id=tenant_id, name="Proveedor Dos (isolation)")
    vendor_orgs.insert(tenant_id, vendor_org.to_document())
    membership = Membership.create(
        tenant_id=tenant_id, user_id=user.id, role="vendor_contact", vendor_org_id=vendor_org.id
    )
    memberships.insert(membership.to_document())
    return membership.id


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


def _create_submittable_proposal(
    client, owner_headers: dict, vendor_org_id: str
) -> tuple[str, str]:
    """Creates an evaluation with valid weights, links vendor_org_id, and
    starts collection - both requirements are optional (required=False) so
    the resulting Proposal can submit immediately without answering
    anything. Returns (evaluation_id, proposal_id)."""
    evaluation_id = client.post(
        "/api/v1/evaluations",
        json={"name": "Isolation RFP", "description": ""},
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
    proposal_id = client.post(
        f"/api/v1/evaluations/{evaluation_id}/vendors",
        json={"vendor_org_id": vendor_org_id},
        headers=owner_headers,
    ).json()["id"]
    client.post(f"/api/v1/evaluations/{evaluation_id}/start-collection", headers=owner_headers)
    return evaluation_id, proposal_id


def test_vendor_contact_cannot_access_buyer_routes(client, seeded_actors) -> None:
    # vendor_contact only ever holds the interim dev header, which buyer
    # routes (behind shared.context.require_role, now JWT-only) don't even
    # recognize as a credential - this fails at authentication (401) before
    # role-checking (403) ever runs. Stronger isolation than before, not a
    # weaker one (see vendor_portal/router.py, AUTH-PROD scope decision #1).
    _tenant_a, vendor_membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    vendor_headers = {DEV_ACTOR_HEADER: vendor_membership_id}
    assert client.get("/api/v1/evaluations", headers=vendor_headers).status_code == 401
    assert (
        client.post(
            "/api/v1/evaluations", json={"name": "x", "description": ""}, headers=vendor_headers
        ).status_code
        == 401
    )


def test_owner_cannot_access_vendor_portal_routes(
    client, seeded_actors, mongo_test_settings
) -> None:
    # Symmetric to the above: an owner's real access token has no
    # X-Dev-Membership-Id header at all, so the vendor portal's dev-header
    # dependency 401s before it can even consider the role.
    tenant_a, _vendor_membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    assert client.get("/api/v1/vendor-portal/proposals", headers=owner_headers).status_code == 401


def test_vendor_contact_cannot_see_another_vendor_orgs_proposal(
    client, seeded_actors, mongo_test_db, mongo_test_settings
) -> None:
    tenant_a, vendor_a_membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    vendor_a_headers = {DEV_ACTOR_HEADER: vendor_a_membership_id}
    vendor_a_org_id = client.get("/api/v1/me", headers=vendor_a_headers).json()["vendor_org_id"]

    vendor_b_membership_id = _create_second_vendor_contact(mongo_test_db, tenant_a)
    vendor_b_headers = {DEV_ACTOR_HEADER: vendor_b_membership_id}

    _evaluation_id, proposal_id = _create_submittable_proposal(
        client, owner_headers, vendor_a_org_id
    )

    response = client.get(
        f"/api/v1/vendor-portal/proposals/{proposal_id}", headers=vendor_b_headers
    )
    assert response.status_code == 404

    list_response = client.get("/api/v1/vendor-portal/proposals", headers=vendor_b_headers)
    assert list_response.status_code == 200
    assert all(p["id"] != proposal_id for p in list_response.json())


def test_evaluation_owner_of_other_tenant_gets_404(
    client, seeded_actors, mongo_test_settings
) -> None:
    tenant_a, _vendor_membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    tenant_b = next(t for t, _role in seeded_actors if t != tenant_a)
    owner_a_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    owner_b_headers = bearer_headers_for(
        seeded_actors[(tenant_b, "evaluation_owner")], mongo_test_settings
    )

    evaluation_id = client.post(
        "/api/v1/evaluations",
        json={"name": "Tenant A RFP", "description": ""},
        headers=owner_a_headers,
    ).json()["id"]

    assert (
        client.get(f"/api/v1/evaluations/{evaluation_id}", headers=owner_b_headers).status_code
        == 404
    )


def test_tenant_id_in_body_is_rejected(client, seeded_actors, mongo_test_settings) -> None:
    tenant_a, _vendor_membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    response = client.post(
        "/api/v1/evaluations",
        json={"name": "x", "description": "", "tenant_id": "not-mine"},
        headers=owner_headers,
    )
    assert response.status_code == 422


def test_status_field_in_evaluation_update_body_is_rejected(
    client, seeded_actors, mongo_test_settings
) -> None:
    tenant_a, _vendor_membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    evaluation_id = client.post(
        "/api/v1/evaluations", json={"name": "x", "description": ""}, headers=owner_headers
    ).json()["id"]

    response = client.patch(
        f"/api/v1/evaluations/{evaluation_id}",
        json={"name": "y", "status": "completed"},
        headers=owner_headers,
    )
    assert response.status_code == 422


def test_vendor_answer_body_rejects_status_field(
    client, seeded_actors, mongo_test_settings
) -> None:
    tenant_a, vendor_membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    vendor_headers = {DEV_ACTOR_HEADER: vendor_membership_id}
    vendor_org_id = client.get("/api/v1/me", headers=vendor_headers).json()["vendor_org_id"]

    evaluation_id = client.post(
        "/api/v1/evaluations", json={"name": "x", "description": ""}, headers=owner_headers
    ).json()["id"]
    requirement_id = client.post(
        f"/api/v1/evaluations/{evaluation_id}/requirements",
        json=_requirement_payload("functional", 40.0),
        headers=owner_headers,
    ).json()["id"]
    proposal_id = client.post(
        f"/api/v1/evaluations/{evaluation_id}/vendors",
        json={"vendor_org_id": vendor_org_id},
        headers=owner_headers,
    ).json()["id"]

    response = client.put(
        f"/api/v1/vendor-portal/proposals/{proposal_id}/answers/{requirement_id}",
        json={"value": "x", "expected_version": 1, "status": "submitted"},
        headers=vendor_headers,
    )
    assert response.status_code == 422


def test_submitted_proposal_rejects_further_answer_edits(
    client, seeded_actors, mongo_test_settings
) -> None:
    tenant_a, vendor_membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    vendor_headers = {DEV_ACTOR_HEADER: vendor_membership_id}
    vendor_org_id = client.get("/api/v1/me", headers=vendor_headers).json()["vendor_org_id"]

    evaluation_id, proposal_id = _create_submittable_proposal(client, owner_headers, vendor_org_id)
    requirement_id = client.get(
        f"/api/v1/evaluations/{evaluation_id}", headers=owner_headers
    ).json()["requirements"][0]["id"]

    submit = client.post(
        f"/api/v1/vendor-portal/proposals/{proposal_id}/submit",
        json={"expected_version": 1},
        headers=vendor_headers,
    )
    assert submit.status_code == 200
    assert submit.json()["status"] == "submitted"

    edit_after_submit = client.put(
        f"/api/v1/vendor-portal/proposals/{proposal_id}/answers/{requirement_id}",
        json={"value": "too late", "expected_version": 2},
        headers=vendor_headers,
    )
    assert edit_after_submit.status_code == 409


def test_stale_proposal_version_is_rejected(client, seeded_actors, mongo_test_settings) -> None:
    tenant_a, vendor_membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    vendor_headers = {DEV_ACTOR_HEADER: vendor_membership_id}
    vendor_org_id = client.get("/api/v1/me", headers=vendor_headers).json()["vendor_org_id"]

    evaluation_id, proposal_id = _create_submittable_proposal(client, owner_headers, vendor_org_id)
    requirement_id = client.get(
        f"/api/v1/evaluations/{evaluation_id}", headers=owner_headers
    ).json()["requirements"][0]["id"]

    stale = client.put(
        f"/api/v1/vendor-portal/proposals/{proposal_id}/answers/{requirement_id}",
        json={"value": "x", "expected_version": 999},
        headers=vendor_headers,
    )
    assert stale.status_code == 409


def test_score_cannot_reference_requirement_outside_snapshot(
    client, seeded_actors, mongo_test_settings
) -> None:
    tenant_a, vendor_membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    evaluator_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluator_functional")], mongo_test_settings
    )
    vendor_headers = {DEV_ACTOR_HEADER: vendor_membership_id}
    vendor_org_id = client.get("/api/v1/me", headers=vendor_headers).json()["vendor_org_id"]

    evaluation_id, proposal_id = _create_submittable_proposal(client, owner_headers, vendor_org_id)
    client.post(
        f"/api/v1/vendor-portal/proposals/{proposal_id}/submit",
        json={"expected_version": 1},
        headers=vendor_headers,
    )
    client.post(f"/api/v1/evaluations/{evaluation_id}/start-evaluation", headers=owner_headers)

    response = client.put(
        f"/api/v1/evaluations/{evaluation_id}/proposals/{proposal_id}/scores/does-not-exist",
        json={"score": 5},
        headers=evaluator_headers,
    )
    assert response.status_code == 400


def test_score_out_of_range_is_rejected(client, seeded_actors, mongo_test_settings) -> None:
    tenant_a, vendor_membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    evaluator_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluator_functional")], mongo_test_settings
    )
    vendor_headers = {DEV_ACTOR_HEADER: vendor_membership_id}
    vendor_org_id = client.get("/api/v1/me", headers=vendor_headers).json()["vendor_org_id"]

    evaluation_id, proposal_id = _create_submittable_proposal(client, owner_headers, vendor_org_id)
    requirement_id = client.get(
        f"/api/v1/evaluations/{evaluation_id}", headers=owner_headers
    ).json()["requirements"][0]["id"]
    client.post(
        f"/api/v1/vendor-portal/proposals/{proposal_id}/submit",
        json={"expected_version": 1},
        headers=vendor_headers,
    )
    client.post(f"/api/v1/evaluations/{evaluation_id}/start-evaluation", headers=owner_headers)

    response = client.put(
        f"/api/v1/evaluations/{evaluation_id}/proposals/{proposal_id}/scores/{requirement_id}",
        json={"score": 6},
        headers=evaluator_headers,
    )
    assert response.status_code == 400
