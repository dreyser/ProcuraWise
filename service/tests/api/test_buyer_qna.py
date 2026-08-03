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
from procurawise.proposals.models import Proposal
from procurawise.proposals.repository import ProposalRepository
from tests.conftest import (
    approve_and_publish,
    bearer_headers_for,
    tenant_ids,
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
) -> tuple[str, str]:
    evaluation_id = client.post(
        "/api/v1/evaluations",
        json={"name": "RFP con preguntas (buyer)", "description": ""},
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


def _create_second_vendor_contact_with_agreements(mongo_test_db, tenant_id: str) -> tuple[str, str]:
    users = UserRepository(mongo_test_db)
    vendor_orgs = VendorOrganizationRepository(mongo_test_db)
    memberships = MembershipRepository(mongo_test_db)
    user = User.create(display_name="Vendor Qna Buyer B", email="vendor.qna.buyer.b@dev.local")
    users.insert(user.to_document())
    vendor_org = VendorOrganization.create(tenant_id=tenant_id, name="Proveedor Qna Buyer Dos")
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
    return membership.id, vendor_org.id


@pytest.fixture
def vendor_setup(client, seeded_actors, mongo_test_settings):
    tenant_id, vendor_membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_id, "evaluation_owner")], mongo_test_settings
    )
    vendor_headers = vendor_bearer_headers_for(vendor_membership_id, mongo_test_settings)
    vendor_dev_headers = {DEV_ACTOR_HEADER: vendor_membership_id}
    vendor_org_id = client.get("/api/v1/me", headers=vendor_dev_headers).json()["vendor_org_id"]
    evaluation_id, proposal_id = _create_collecting_proposal(
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
    }


def _vendor_qna_url(proposal_id: str, suffix: str = "") -> str:
    return f"/api/v1/vendor-portal/proposals/{proposal_id}/questions{suffix}"


def _buyer_qna_url(evaluation_id: str, suffix: str = "") -> str:
    return f"/api/v1/evaluations/{evaluation_id}/questions{suffix}"


def test_buyer_can_list_and_publish_answer(client, vendor_setup) -> None:
    evaluation_id = vendor_setup["evaluation_id"]
    proposal_id = vendor_setup["proposal_id"]
    question_id = client.post(
        _vendor_qna_url(proposal_id),
        json={"scope": "general", "body": "Cuando cierra el RFP?"},
        headers=vendor_setup["vendor_headers"],
    ).json()["id"]

    listing = client.get(_buyer_qna_url(evaluation_id), headers=vendor_setup["owner_headers"])
    assert listing.status_code == 200
    items = listing.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == question_id
    assert items[0]["vendor_org_id"] == vendor_setup["vendor_org_id"]
    assert items[0]["current_answer"] is None

    answer = client.put(
        _buyer_qna_url(evaluation_id, f"/{question_id}/answer"),
        json={"body": "Cierra el 30 de agosto.", "visibility": "private", "expected_version": 1},
        headers=vendor_setup["owner_headers"],
    )
    assert answer.status_code == 200, answer.text
    assert answer.json()["status"] == "answered"
    assert answer.json()["current_answer"]["visibility"] == "private"
    assert answer.json()["current_answer"]["version"] == 1


def test_republishing_creates_new_version_and_keeps_history(client, vendor_setup) -> None:
    evaluation_id = vendor_setup["evaluation_id"]
    proposal_id = vendor_setup["proposal_id"]
    question_id = client.post(
        _vendor_qna_url(proposal_id),
        json={"scope": "general", "body": "?"},
        headers=vendor_setup["vendor_headers"],
    ).json()["id"]

    client.put(
        _buyer_qna_url(evaluation_id, f"/{question_id}/answer"),
        json={"body": "v1 answer", "visibility": "private", "expected_version": 1},
        headers=vendor_setup["owner_headers"],
    )
    republished = client.put(
        _buyer_qna_url(evaluation_id, f"/{question_id}/answer"),
        json={"body": "v2 answer", "visibility": "published_anonymized", "expected_version": 2},
        headers=vendor_setup["owner_headers"],
    )
    assert republished.status_code == 200
    assert republished.json()["current_answer"]["version"] == 2
    assert republished.json()["current_answer"]["visibility"] == "published_anonymized"
    assert len(republished.json()["answer_history"]) == 1
    assert republished.json()["answer_history"][0]["body"] == "v1 answer"


def test_publish_answer_rejects_stale_version(client, vendor_setup) -> None:
    evaluation_id = vendor_setup["evaluation_id"]
    proposal_id = vendor_setup["proposal_id"]
    question_id = client.post(
        _vendor_qna_url(proposal_id),
        json={"scope": "general", "body": "?"},
        headers=vendor_setup["vendor_headers"],
    ).json()["id"]

    response = client.put(
        _buyer_qna_url(evaluation_id, f"/{question_id}/answer"),
        json={"body": "answer", "visibility": "private", "expected_version": 999},
        headers=vendor_setup["owner_headers"],
    )
    assert response.status_code == 409


def test_non_owner_buyer_role_cannot_publish_answer(
    client, vendor_setup, seeded_actors, mongo_test_settings
) -> None:
    evaluation_id = vendor_setup["evaluation_id"]
    proposal_id = vendor_setup["proposal_id"]
    tenant_id = vendor_setup["tenant_id"]
    question_id = client.post(
        _vendor_qna_url(proposal_id),
        json={"scope": "general", "body": "?"},
        headers=vendor_setup["vendor_headers"],
    ).json()["id"]

    evaluator_headers = bearer_headers_for(
        seeded_actors[(tenant_id, "evaluator_functional")], mongo_test_settings
    )
    # Evaluators are BUYER_READ_ROLES - they can list...
    assert client.get(_buyer_qna_url(evaluation_id), headers=evaluator_headers).status_code == 200
    # ...but only evaluation_owner can answer/publish.
    response = client.put(
        _buyer_qna_url(evaluation_id, f"/{question_id}/answer"),
        json={"body": "answer", "visibility": "private", "expected_version": 1},
        headers=evaluator_headers,
    )
    assert response.status_code == 403


def test_buyer_of_other_tenant_gets_404(
    client, vendor_setup, seeded_actors, mongo_test_settings
) -> None:
    evaluation_id = vendor_setup["evaluation_id"]
    tenant_a, tenant_b = tenant_ids(seeded_actors)
    other_tenant_id = tenant_b if tenant_a == vendor_setup["tenant_id"] else tenant_a
    other_owner_headers = bearer_headers_for(
        seeded_actors[(other_tenant_id, "evaluation_owner")], mongo_test_settings
    )

    response = client.get(_buyer_qna_url(evaluation_id), headers=other_owner_headers)
    assert response.status_code == 404


def test_published_questions_visible_to_other_vendor_without_identity_leak(
    client, vendor_setup, mongo_test_db, mongo_test_settings
) -> None:
    evaluation_id = vendor_setup["evaluation_id"]
    proposal_id = vendor_setup["proposal_id"]
    tenant_id = vendor_setup["tenant_id"]
    owner_headers = vendor_setup["owner_headers"]
    vendor_headers = vendor_setup["vendor_headers"]

    private_id = client.post(
        _vendor_qna_url(proposal_id),
        json={"scope": "general", "body": "private question"},
        headers=vendor_headers,
    ).json()["id"]
    published_id = client.post(
        _vendor_qna_url(proposal_id),
        json={"scope": "general", "body": "published question"},
        headers=vendor_headers,
    ).json()["id"]

    client.put(
        _buyer_qna_url(evaluation_id, f"/{private_id}/answer"),
        json={"body": "shh", "visibility": "private", "expected_version": 1},
        headers=owner_headers,
    )
    client.put(
        _buyer_qna_url(evaluation_id, f"/{published_id}/answer"),
        json={
            "body": "everyone sees this",
            "visibility": "published_anonymized",
            "expected_version": 1,
        },
        headers=owner_headers,
    )

    other_membership_id, other_org_id = _create_second_vendor_contact_with_agreements(
        mongo_test_db, tenant_id
    )
    other_headers = vendor_bearer_headers_for(other_membership_id, mongo_test_settings)
    # The evaluation already left "draft" (approve_and_publish already ran
    # in vendor_setup), so POST .../vendors (draft-only) is no longer an
    # option here - insert the second Proposal directly, same precedent as
    # Fase 16's cross-vendor isolation tests.
    other_proposal = Proposal.create(
        tenant_id=tenant_id, evaluation_id=evaluation_id, vendor_org_id=other_org_id
    )
    ProposalRepository(mongo_test_db).insert(tenant_id, other_proposal.to_document())
    other_proposal_id = other_proposal.id

    published = client.get(_vendor_qna_url(other_proposal_id, "/published"), headers=other_headers)
    assert published.status_code == 200
    published_ids = {q["id"] for q in published.json()["items"]}
    assert published_ids == {published_id}
    assert private_id not in published_ids

    # No vendor identity field anywhere in the serialized response, at all -
    # a structural check (PublicQuestionResponse has no such field), not
    # just "the value happens to be empty".
    serialized = published.text
    assert vendor_setup["vendor_org_id"] not in serialized
    assert "vendor_org" not in serialized
    assert "created_by_membership_id" not in serialized
