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
    unique_actor_by_role,
    vendor_bearer_headers_for,
)

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


def _create_collecting_proposal(
    client,
    owner_headers: dict,
    vendor_org_id: str,
    *,
    seeded_actors,
    tenant_id,
    mongo_test_settings,
) -> tuple[str, str, str]:
    evaluation_id = client.post(
        "/api/v1/evaluations",
        json={"name": "RFP con preguntas", "description": ""},
        headers=owner_headers,
    ).json()["id"]
    requirement_id = client.post(
        f"/api/v1/evaluations/{evaluation_id}/requirements",
        json=_requirement_payload("functional", 40.0),
        headers=owner_headers,
    ).json()["id"]
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
    return evaluation_id, proposal_id, requirement_id


def _create_second_vendor_contact_with_agreements(mongo_test_db, tenant_id: str) -> str:
    users = UserRepository(mongo_test_db)
    vendor_orgs = VendorOrganizationRepository(mongo_test_db)
    memberships = MembershipRepository(mongo_test_db)
    user = User.create(display_name="Vendor Qna B", email="vendor.qna.b@dev.local")
    users.insert(user.to_document())
    vendor_org = VendorOrganization.create(tenant_id=tenant_id, name="Proveedor Qna Dos")
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


@pytest.fixture
def vendor_setup(client, seeded_actors, mongo_test_settings):
    tenant_id, vendor_membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_id, "evaluation_owner")], mongo_test_settings
    )
    vendor_headers = vendor_bearer_headers_for(vendor_membership_id, mongo_test_settings)
    vendor_dev_headers = {DEV_ACTOR_HEADER: vendor_membership_id}
    vendor_org_id = client.get("/api/v1/me", headers=vendor_dev_headers).json()["vendor_org_id"]
    evaluation_id, proposal_id, requirement_id = _create_collecting_proposal(
        client,
        owner_headers,
        vendor_org_id,
        seeded_actors=seeded_actors,
        tenant_id=tenant_id,
        mongo_test_settings=mongo_test_settings,
    )
    return {
        "tenant_id": tenant_id,
        "owner_headers": owner_headers,
        "vendor_headers": vendor_headers,
        "vendor_org_id": vendor_org_id,
        "evaluation_id": evaluation_id,
        "proposal_id": proposal_id,
        "requirement_id": requirement_id,
    }


def _qna_url(proposal_id: str, suffix: str = "") -> str:
    return f"/api/v1/vendor-portal/proposals/{proposal_id}/questions{suffix}"


def test_vendor_without_agreements_is_blocked_from_qna(
    client, vendor_setup, mongo_test_db, mongo_test_settings
) -> None:
    users = UserRepository(mongo_test_db)
    vendor_orgs = VendorOrganizationRepository(mongo_test_db)
    memberships = MembershipRepository(mongo_test_db)
    user = User.create(display_name="No Agreements Qna Vendor", email="no.agreements.qna@dev.local")
    users.insert(user.to_document())
    vendor_org = VendorOrganization.create(
        tenant_id=vendor_setup["tenant_id"], name="Proveedor Sin Agreements Qna"
    )
    vendor_orgs.insert(vendor_setup["tenant_id"], vendor_org.to_document())
    membership = Membership.create(
        tenant_id=vendor_setup["tenant_id"],
        user_id=user.id,
        role="vendor_contact",
        vendor_org_id=vendor_org.id,
    )
    memberships.insert(membership.to_document())
    headers = vendor_bearer_headers_for(membership.id, mongo_test_settings)

    response = client.post(
        _qna_url(vendor_setup["proposal_id"]),
        json={"scope": "general", "body": "Cuando cierra el RFP?"},
        headers=headers,
    )
    assert response.status_code == 403
    assert response.json()["detail"]["detail"] == "agreements_required"


def test_create_list_and_withdraw_question(client, vendor_setup) -> None:
    proposal_id = vendor_setup["proposal_id"]
    headers = vendor_setup["vendor_headers"]

    create = client.post(
        _qna_url(proposal_id),
        json={"scope": "general", "body": "Cuando cierra el RFP?"},
        headers=headers,
    )
    assert create.status_code == 201, create.text
    question_id = create.json()["id"]
    assert create.json()["status"] == "open"

    listing = client.get(_qna_url(proposal_id), headers=headers)
    assert listing.status_code == 200
    assert [q["id"] for q in listing.json()["items"]] == [question_id]

    withdraw = client.delete(_qna_url(proposal_id, f"/{question_id}"), headers=headers)
    assert withdraw.status_code == 204
    assert client.get(_qna_url(proposal_id), headers=headers).json()["items"] == []


def test_create_question_scoped_to_requirement(client, vendor_setup) -> None:
    proposal_id = vendor_setup["proposal_id"]
    requirement_id = vendor_setup["requirement_id"]
    headers = vendor_setup["vendor_headers"]

    create = client.post(
        _qna_url(proposal_id),
        json={"scope": "requirement", "requirement_id": requirement_id, "body": "Soportan SSO?"},
        headers=headers,
    )
    assert create.status_code == 201, create.text
    assert create.json()["requirement_id"] == requirement_id


def test_create_question_rejects_foreign_requirement_id(client, vendor_setup) -> None:
    response = client.post(
        _qna_url(vendor_setup["proposal_id"]),
        json={"scope": "requirement", "requirement_id": "does-not-exist", "body": "?"},
        headers=vendor_setup["vendor_headers"],
    )
    assert response.status_code == 404


def test_create_question_requires_requirement_id_for_requirement_scope(
    client, vendor_setup
) -> None:
    response = client.post(
        _qna_url(vendor_setup["proposal_id"]),
        json={"scope": "requirement", "body": "?"},
        headers=vendor_setup["vendor_headers"],
    )
    assert response.status_code == 422


def test_withdraw_rejected_once_evaluation_leaves_collecting_responses(
    client, vendor_setup
) -> None:
    proposal_id = vendor_setup["proposal_id"]
    evaluation_id = vendor_setup["evaluation_id"]
    headers = vendor_setup["vendor_headers"]
    question_id = client.post(
        _qna_url(proposal_id),
        json={"scope": "general", "body": "?"},
        headers=headers,
    ).json()["id"]

    client.post(
        f"/api/v1/evaluations/{evaluation_id}/start-evaluation",
        headers=vendor_setup["owner_headers"],
    )

    response = client.delete(_qna_url(proposal_id, f"/{question_id}"), headers=headers)
    assert response.status_code == 409

    create_after = client.post(
        _qna_url(proposal_id),
        json={"scope": "general", "body": "tarde"},
        headers=headers,
    )
    assert create_after.status_code == 409


def test_cross_vendor_cannot_see_or_withdraw_another_vendors_questions(
    client, vendor_setup, mongo_test_db, mongo_test_settings
) -> None:
    proposal_id = vendor_setup["proposal_id"]
    tenant_id = vendor_setup["tenant_id"]
    owner_headers = vendor_setup["vendor_headers"]
    question_id = client.post(
        _qna_url(proposal_id),
        json={"scope": "general", "body": "?"},
        headers=owner_headers,
    ).json()["id"]

    other_membership_id = _create_second_vendor_contact_with_agreements(mongo_test_db, tenant_id)
    other_headers = vendor_bearer_headers_for(other_membership_id, mongo_test_settings)

    assert client.get(_qna_url(proposal_id), headers=other_headers).status_code == 404
    assert (
        client.post(
            _qna_url(proposal_id),
            json={"scope": "general", "body": "intruso"},
            headers=other_headers,
        ).status_code
        == 404
    )
    assert (
        client.delete(_qna_url(proposal_id, f"/{question_id}"), headers=other_headers).status_code
        == 404
    )

    assert client.get(_qna_url(proposal_id), headers=owner_headers).status_code == 200
