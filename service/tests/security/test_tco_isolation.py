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
    tenant_ids,
    unique_actor_by_role,
    vendor_bearer_headers_for,
)

pytestmark = pytest.mark.docker


def _create_second_vendor_contact(mongo_test_db, tenant_id: str) -> str:
    """Same pattern as test_vendor_isolation.py's helper - a second,
    genuinely different VendorOrganization under the same buyer tenant, with
    both Agreements pre-accepted so the isolation check exercises the
    vendor_org_id boundary specifically, not the Agreement gate."""
    users = UserRepository(mongo_test_db)
    vendor_orgs = VendorOrganizationRepository(mongo_test_db)
    memberships = MembershipRepository(mongo_test_db)

    user = User.create(display_name="Vendor Contact B", email="vendor.b.tco-isolation@dev.local")
    users.insert(user.to_document())
    vendor_org = VendorOrganization.create(tenant_id=tenant_id, name="Proveedor Dos (tco)")
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


def _setup_draft_proposal(client, seeded_actors, mongo_test_settings):
    tenant_a, vendor_membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    vendor_dev_headers = {DEV_ACTOR_HEADER: vendor_membership_id}
    vendor_org_id = client.get("/api/v1/me", headers=vendor_dev_headers).json()["vendor_org_id"]
    vendor_headers = vendor_bearer_headers_for(vendor_membership_id, mongo_test_settings)

    evaluation_id = client.post(
        "/api/v1/evaluations",
        json={"name": "TCO isolation RFP", "description": ""},
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
    approver_membership_id = seeded_actors[(tenant_a, "approver")]
    approver_headers = bearer_headers_for(approver_membership_id, mongo_test_settings)
    approve_and_publish(
        client, owner_headers, approver_membership_id, approver_headers, evaluation_id
    )
    return tenant_a, evaluation_id, proposal_id, owner_headers, vendor_headers


def test_vendor_cannot_add_cost_item_to_another_vendor_orgs_proposal(
    client, seeded_actors, mongo_test_db, mongo_test_settings
) -> None:
    tenant_a, _evaluation_id, proposal_id, _owner_headers, _vendor_a_headers = (
        _setup_draft_proposal(client, seeded_actors, mongo_test_settings)
    )
    vendor_b_membership_id = _create_second_vendor_contact(mongo_test_db, tenant_a)
    vendor_b_headers = vendor_bearer_headers_for(vendor_b_membership_id, mongo_test_settings)

    response = client.post(
        f"/api/v1/vendor-portal/proposals/{proposal_id}/cost-items",
        json={
            "concept": "Intruso",
            "category": "recurring",
            "billing_unit": "usuario",
            "quantity": "1",
            "unit_price": "1",
            "currency": "MXN",
            "frequency_per_year": "1",
            "year_start": 1,
            "year_end": 1,
            "cost_type": "recurring",
            "expected_version": 1,
        },
        headers=vendor_b_headers,
    )
    assert response.status_code == 404

    # No mutation happened - vendor A's proposal still has zero cost items.
    doc = mongo_test_db["proposals"].find_one({"_id": proposal_id})
    assert doc["cost_items"] == []


def test_vendor_cannot_preview_tco_of_another_vendor_orgs_proposal(
    client, seeded_actors, mongo_test_db, mongo_test_settings
) -> None:
    tenant_a, _evaluation_id, proposal_id, _owner_headers, _vendor_a_headers = (
        _setup_draft_proposal(client, seeded_actors, mongo_test_settings)
    )
    vendor_b_membership_id = _create_second_vendor_contact(mongo_test_db, tenant_a)
    vendor_b_headers = vendor_bearer_headers_for(vendor_b_membership_id, mongo_test_settings)

    response = client.get(
        f"/api/v1/vendor-portal/proposals/{proposal_id}/tco-preview", headers=vendor_b_headers
    )
    assert response.status_code == 404


def test_owner_of_other_tenant_cannot_read_tco_result(
    client, seeded_actors, mongo_test_settings
) -> None:
    _tenant_a, evaluation_id, proposal_id, _owner_headers, _vendor_headers = _setup_draft_proposal(
        client, seeded_actors, mongo_test_settings
    )
    _tenant_a2, tenant_b = tenant_ids(seeded_actors)
    other_owner_headers = bearer_headers_for(
        seeded_actors[(tenant_b, "evaluation_owner")], mongo_test_settings
    )

    response = client.get(
        f"/api/v1/evaluations/{evaluation_id}/proposals/{proposal_id}/tco",
        headers=other_owner_headers,
    )
    assert response.status_code == 404
