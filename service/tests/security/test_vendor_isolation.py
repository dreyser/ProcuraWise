import pytest

from procurawise.agreements.repository import AgreementRepository
from procurawise.agreements.service import AgreementService
from procurawise.identity.dev_provider import DEV_ACTOR_HEADER
from procurawise.identity.models import Membership, User, VendorOrganization
from procurawise.identity.repository import (
    MembershipRepository,
    UserRepository,
    VendorOrganizationRepository,
)
from tests.conftest import (
    approve_and_publish,
    bearer_headers_for,
    second_vendor_collaborator_membership_id,
    unique_actor_by_role,
    vendor_bearer_headers_for,
)

pytestmark = pytest.mark.docker


def _create_second_vendor_contact(mongo_test_db, tenant_id: str) -> str:
    """Seeds a second VendorOrganization+vendor_contact under the same
    tenant, outside of dev_seed.py (which only ever seeds one org with this
    helper's pattern), and pre-accepts both Agreements (Fase 15) so tests
    using it exercise cross-vendor isolation specifically, not incidentally
    fail the Agreement gate instead - needed to prove one vendor_org_id can
    never see another's proposal even within the same buyer tenant."""
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

    agreements = AgreementService(AgreementRepository(mongo_test_db))
    for agreement_type in ("nda", "conflict_of_interest"):
        agreements.accept(
            tenant_id, user.id, membership.id, agreement_type, ip="127.0.0.1", user_agent="test"
        )
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
    client,
    owner_headers: dict,
    vendor_org_id: str,
    *,
    tenant_id: str,
    seeded_actors: dict,
    mongo_test_settings,
) -> tuple[str, str]:
    """Creates an evaluation with valid weights, links vendor_org_id, runs
    it through the Fase 12 approval workflow, and publishes - both
    requirements are optional (required=False) so the resulting Proposal
    can submit immediately without answering anything. Returns
    (evaluation_id, proposal_id)."""
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
    approver_membership_id = seeded_actors[(tenant_id, "approver")]
    approver_headers = bearer_headers_for(approver_membership_id, mongo_test_settings)
    approve_and_publish(
        client, owner_headers, approver_membership_id, approver_headers, evaluation_id
    )
    return evaluation_id, proposal_id


def test_vendor_contact_cannot_access_buyer_routes(client, seeded_actors) -> None:
    # vendor_contact only ever holds the interim dev header, which buyer
    # routes (behind shared.context.require_role, JWT-only) don't even
    # recognize as a credential - this fails at authentication (401) before
    # role-checking (403) ever runs.
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
    # Symmetric to the above: an owner's real buyer access token has
    # token_use="access", which vendor_portal's dependency (token_use=
    # "vendor_access" only, Fase 15) 401s before it can even consider role.
    tenant_a, _vendor_membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    assert client.get("/api/v1/vendor-portal/proposals", headers=owner_headers).status_code == 401


def test_vendor_dev_header_cannot_access_vendor_portal_routes(client, seeded_actors) -> None:
    # Fase 15: the interim dev-header mechanism is no longer accepted by
    # vendor_portal at all (mirrors what AUTH-PROD already did to buyer
    # routes) - a request carrying only X-Dev-Membership-Id now 401s here
    # too, even for a real vendor_contact Membership.
    _tenant_a, vendor_membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    vendor_dev_headers = {DEV_ACTOR_HEADER: vendor_membership_id}
    assert (
        client.get("/api/v1/vendor-portal/proposals", headers=vendor_dev_headers).status_code == 401
    )


def test_vendor_without_agreements_is_blocked_from_proposals(
    client, mongo_test_db, seeded_actors, mongo_test_settings
) -> None:
    # Fase 15 backlog acceptance criterion: "Proveedor no accede al
    # formulario de respuesta sin aceptar ambos Agreement". A freshly seeded
    # vendor contact (via _create_second_vendor_contact minus its
    # auto-acceptance, reproduced manually here) must be blocked.
    tenant_a, _vendor_membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    users = UserRepository(mongo_test_db)
    vendor_orgs = VendorOrganizationRepository(mongo_test_db)
    memberships = MembershipRepository(mongo_test_db)
    user = User.create(display_name="No Agreements Vendor", email="no.agreements@dev.local")
    users.insert(user.to_document())
    vendor_org = VendorOrganization.create(tenant_id=tenant_a, name="Proveedor Sin Agreements")
    vendor_orgs.insert(tenant_a, vendor_org.to_document())
    membership = Membership.create(
        tenant_id=tenant_a, user_id=user.id, role="vendor_contact", vendor_org_id=vendor_org.id
    )
    memberships.insert(membership.to_document())

    headers = vendor_bearer_headers_for(membership.id, mongo_test_settings)
    response = client.get("/api/v1/vendor-portal/proposals", headers=headers)
    assert response.status_code == 403
    body = response.json()["detail"]
    assert body["detail"] == "agreements_required"
    assert set(body["missing"]) == {"nda", "conflict_of_interest"}


def test_vendor_contact_cannot_see_another_vendor_orgs_proposal(
    client, seeded_actors, mongo_test_db, mongo_test_settings
) -> None:
    tenant_a, vendor_a_membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    vendor_a_dev_headers = {DEV_ACTOR_HEADER: vendor_a_membership_id}
    vendor_a_org_id = client.get("/api/v1/me", headers=vendor_a_dev_headers).json()["vendor_org_id"]
    vendor_a_headers = vendor_bearer_headers_for(vendor_a_membership_id, mongo_test_settings)

    vendor_b_membership_id = _create_second_vendor_contact(mongo_test_db, tenant_a)
    vendor_b_headers = vendor_bearer_headers_for(vendor_b_membership_id, mongo_test_settings)

    _evaluation_id, proposal_id = _create_submittable_proposal(
        client,
        owner_headers,
        vendor_a_org_id,
        tenant_id=tenant_a,
        seeded_actors=seeded_actors,
        mongo_test_settings=mongo_test_settings,
    )

    response = client.get(
        f"/api/v1/vendor-portal/proposals/{proposal_id}", headers=vendor_b_headers
    )
    assert response.status_code == 404

    list_response = client.get("/api/v1/vendor-portal/proposals", headers=vendor_b_headers)
    assert list_response.status_code == 200
    assert all(p["id"] != proposal_id for p in list_response.json())

    # Sanity check the isolation is real (not just an always-empty list):
    # vendor A, the actual owner of this proposal, does see it.
    own_response = client.get(
        f"/api/v1/vendor-portal/proposals/{proposal_id}", headers=vendor_a_headers
    )
    assert own_response.status_code == 200


def test_second_collaborator_on_same_org_must_accept_agreements_individually(
    client, seeded_actors, mongo_test_db, mongo_test_settings
) -> None:
    # Fase 15 / ADR 0014: acceptance is per-user_id, never representative of
    # the whole vendor organization - dev_seed.py's second collaborator on
    # the *same* vendor_org_id as the primary vendor actor has not accepted
    # anything, even though the primary actor already has.
    tenant_a, vendor_a_membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    vendor_a_headers = vendor_bearer_headers_for(vendor_a_membership_id, mongo_test_settings)
    assert (
        client.get("/api/v1/vendor-portal/proposals", headers=vendor_a_headers).status_code == 200
    )

    collaborator_membership_id = second_vendor_collaborator_membership_id(mongo_test_db, tenant_a)
    collaborator_headers = vendor_bearer_headers_for(
        collaborator_membership_id, mongo_test_settings
    )
    response = client.get("/api/v1/vendor-portal/proposals", headers=collaborator_headers)
    assert response.status_code == 403
    assert response.json()["detail"]["detail"] == "agreements_required"


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
    vendor_dev_headers = {DEV_ACTOR_HEADER: vendor_membership_id}
    vendor_org_id = client.get("/api/v1/me", headers=vendor_dev_headers).json()["vendor_org_id"]
    vendor_headers = vendor_bearer_headers_for(vendor_membership_id, mongo_test_settings)

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
    vendor_dev_headers = {DEV_ACTOR_HEADER: vendor_membership_id}
    vendor_org_id = client.get("/api/v1/me", headers=vendor_dev_headers).json()["vendor_org_id"]
    vendor_headers = vendor_bearer_headers_for(vendor_membership_id, mongo_test_settings)

    evaluation_id, proposal_id = _create_submittable_proposal(
        client,
        owner_headers,
        vendor_org_id,
        tenant_id=tenant_a,
        seeded_actors=seeded_actors,
        mongo_test_settings=mongo_test_settings,
    )
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
    vendor_dev_headers = {DEV_ACTOR_HEADER: vendor_membership_id}
    vendor_org_id = client.get("/api/v1/me", headers=vendor_dev_headers).json()["vendor_org_id"]
    vendor_headers = vendor_bearer_headers_for(vendor_membership_id, mongo_test_settings)

    evaluation_id, proposal_id = _create_submittable_proposal(
        client,
        owner_headers,
        vendor_org_id,
        tenant_id=tenant_a,
        seeded_actors=seeded_actors,
        mongo_test_settings=mongo_test_settings,
    )
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
    vendor_dev_headers = {DEV_ACTOR_HEADER: vendor_membership_id}
    vendor_org_id = client.get("/api/v1/me", headers=vendor_dev_headers).json()["vendor_org_id"]
    vendor_headers = vendor_bearer_headers_for(vendor_membership_id, mongo_test_settings)

    evaluation_id, proposal_id = _create_submittable_proposal(
        client,
        owner_headers,
        vendor_org_id,
        tenant_id=tenant_a,
        seeded_actors=seeded_actors,
        mongo_test_settings=mongo_test_settings,
    )
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
    vendor_dev_headers = {DEV_ACTOR_HEADER: vendor_membership_id}
    vendor_org_id = client.get("/api/v1/me", headers=vendor_dev_headers).json()["vendor_org_id"]
    vendor_headers = vendor_bearer_headers_for(vendor_membership_id, mongo_test_settings)

    evaluation_id, proposal_id = _create_submittable_proposal(
        client,
        owner_headers,
        vendor_org_id,
        tenant_id=tenant_a,
        seeded_actors=seeded_actors,
        mongo_test_settings=mongo_test_settings,
    )
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
