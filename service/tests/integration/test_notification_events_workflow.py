"""Fase 24 (plan Bloqueante #1 Opcion A): walks a single evaluation through
every one of the 8 wired events (vendor_invited, evaluation_published,
approval_requested x2, qna_question_received, qna_answer_published,
proposal_submitted, proposal_reopened, evaluation_completed) via the real
HTTP API, asserting a Notification with the right event/recipient exists
after each step - not just that the underlying domain action itself still
succeeds (already covered by each module's own integration tests)."""

from datetime import UTC, datetime

import pytest

from procurawise.agreements.repository import AgreementRepository
from procurawise.agreements.service import AgreementService
from procurawise.identity.models import Membership, User
from procurawise.identity.repository import MembershipRepository, UserRepository
from procurawise.notifications.repository import NotificationRepository
from tests.conftest import (
    approve_and_publish,
    bearer_headers_for,
    unique_actor_by_role,
    vendor_bearer_headers_for,
)

pytestmark = pytest.mark.docker

_COMMERCIAL_KEYS = [
    "payment_terms",
    "price_protection",
    "contractual_flexibility",
    "discounts_incentives",
    "billing_transparency",
]
_RISK_KEYS = [
    "variable_cost_exposure",
    "increases_indexation",
    "assumptions_exclusions",
    "fx_fiscal_regulatory",
    "exit_portability_lockin",
]


def _max_scores_body() -> dict:
    return {
        "commercial_scores": [
            {"criterion_key": k, "score": 5, "comment": "Excelente"} for k in _COMMERCIAL_KEYS
        ],
        "risk_scores": [
            {"criterion_key": k, "score": 5, "comment": "Excelente"} for k in _RISK_KEYS
        ],
    }


def _create_approver(mongo_test_db, tenant_id: str, *, email: str, display_name: str) -> str:
    users = UserRepository(mongo_test_db)
    memberships = MembershipRepository(mongo_test_db)
    user = User.create(display_name=display_name, email=email)
    users.insert(user.to_document())
    membership = Membership.create(tenant_id=tenant_id, user_id=user.id, role="approver")
    memberships.insert(membership.to_document())
    return membership.id


def _events_for(notifications: NotificationRepository, tenant_id: str, membership_id: str) -> set:
    return {
        n["event"] for n in notifications.list_for_recipient(tenant_id, membership_id, limit=100)
    }


def test_full_lifecycle_produces_all_8_wired_events(
    client, seeded_actors, mongo_test_settings, mongo_test_db
) -> None:
    notifications = NotificationRepository(mongo_test_db)
    # unique_actor_by_role("vendor_contact") deterministically lands on the
    # tenant where the approver is a genuinely distinct user from the owner
    # (the other seeded tenant reuses the owner's own user for a second,
    # approver Membership, which would trip SelfApprovalError below).
    tenant_id, _vendor_contact_membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    owner_membership_id = seeded_actors[(tenant_id, "evaluation_owner")]
    owner_headers = bearer_headers_for(owner_membership_id, mongo_test_settings)

    # 1. vendor_invited - owner creates a brand new vendor org (not the
    # pre-seeded one) so the invited Membership starts with an empty inbox.
    created = client.post(
        "/api/v1/vendor-organizations",
        json={
            "name": f"Proveedor Notificaciones {datetime.now(UTC).timestamp()}",
            "contact_email": f"vendor.notifications.{datetime.now(UTC).timestamp()}@dev.local",
            "contact_display_name": "Contacto Notificaciones",
        },
        headers=owner_headers,
    )
    assert created.status_code == 201, created.text
    vendor_org_id = created.json()["id"]
    vendor_membership_id = created.json()["invitation"]["membership_id"]
    assert "vendor_invited" in _events_for(notifications, tenant_id, vendor_membership_id)
    vendor_headers = vendor_bearer_headers_for(vendor_membership_id, mongo_test_settings)

    # vendor_portal routes touching a Proposal/Question all require the
    # agreements gate (require_agreements_accepted) - a freshly-invited
    # contact hasn't accepted anything yet, unlike dev_seed's pre-accepted
    # vendor_contact.
    membership_doc = MembershipRepository(mongo_test_db).find_by_id(vendor_membership_id)
    assert membership_doc is not None
    agreements = AgreementService(AgreementRepository(mongo_test_db))
    for agreement_type in ("nda", "conflict_of_interest"):
        agreements.accept(
            tenant_id,
            membership_doc["user_id"],
            vendor_membership_id,
            agreement_type,
            ip="127.0.0.1",
            user_agent="test",
        )

    # 2. Build a publishable evaluation with 2 optional requirements
    # (avoids needing full vendor answers before submit) and link the vendor.
    evaluation_id = client.post(
        "/api/v1/evaluations",
        json={"name": "RFP notificaciones", "description": ""},
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

    # 3. approval_requested (evaluation) + evaluation_published.
    approver_membership_id = seeded_actors[(tenant_id, "approver")]
    approver_headers = bearer_headers_for(approver_membership_id, mongo_test_settings)
    approve_and_publish(
        client, owner_headers, approver_membership_id, approver_headers, evaluation_id
    )
    assert "approval_requested" in _events_for(notifications, tenant_id, approver_membership_id)
    assert "evaluation_published" in _events_for(notifications, tenant_id, owner_membership_id)

    # 4. qna_question_received (owner) + 5. qna_answer_published (vendor).
    question_id = client.post(
        f"/api/v1/vendor-portal/proposals/{proposal_id}/questions",
        json={"scope": "general", "body": "¿Aceptan pagos en USD?"},
        headers=vendor_headers,
    ).json()["id"]
    assert "qna_question_received" in _events_for(notifications, tenant_id, owner_membership_id)
    client.put(
        f"/api/v1/evaluations/{evaluation_id}/questions/{question_id}/answer",
        json={"body": "Sí, aceptamos USD.", "visibility": "private", "expected_version": 1},
        headers=owner_headers,
    )
    assert "qna_answer_published" in _events_for(notifications, tenant_id, vendor_membership_id)

    # A nonzero cost item (currency == the evaluation's default base_currency
    # MXN, no FXRate needed) makes TCO "available" rather than
    # "no_comparable" - required for /complete below (Fase 20).
    cost_item = client.post(
        f"/api/v1/vendor-portal/proposals/{proposal_id}/cost-items",
        json={
            "concept": "Licencia anual",
            "category": "recurring",
            "billing_unit": "usuario",
            "quantity": "10",
            "unit_price": "100",
            "currency": "MXN",
            "frequency_per_year": "1",
            "year_start": 1,
            "year_end": 1,
            "cost_type": "recurring",
            "expected_version": 1,
        },
        headers=vendor_headers,
    )
    assert cost_item.status_code == 200, cost_item.text

    # 6. proposal_submitted (vendor + owner).
    submit = client.post(
        f"/api/v1/vendor-portal/proposals/{proposal_id}/submit",
        json={"expected_version": 2},
        headers=vendor_headers,
    )
    assert submit.status_code == 200, submit.text
    assert "proposal_submitted" in _events_for(notifications, tenant_id, vendor_membership_id)
    assert "proposal_submitted" in _events_for(notifications, tenant_id, owner_membership_id)

    # 7. proposal_reopened (vendor + owner), then the vendor resubmits so the
    # evaluation can proceed to completion below.
    reopen = client.post(
        f"/api/v1/evaluations/{evaluation_id}/proposals/{proposal_id}/reopen",
        json={
            "reason": "Necesitamos aclarar una respuesta.",
            "response_deadline": "2031-01-01T00:00:00Z",
        },
        headers=owner_headers,
    )
    assert reopen.status_code == 200, reopen.text
    assert "proposal_reopened" in _events_for(notifications, tenant_id, vendor_membership_id)
    assert "proposal_reopened" in _events_for(notifications, tenant_id, owner_membership_id)
    reopened_version = reopen.json()["version"]
    resubmit = client.post(
        f"/api/v1/vendor-portal/proposals/{proposal_id}/submit",
        json={"expected_version": reopened_version},
        headers=vendor_headers,
    )
    assert resubmit.status_code == 200, resubmit.text

    # 8. evaluation_completed (owner) - start evaluation, score everything,
    # complete.
    start_eval = client.post(
        f"/api/v1/evaluations/{evaluation_id}/start-evaluation", headers=owner_headers
    )
    assert start_eval.status_code == 200, start_eval.text
    for requirement in client.get(
        f"/api/v1/evaluations/{evaluation_id}", headers=owner_headers
    ).json()["requirements"]:
        response = client.put(
            f"/api/v1/evaluations/{evaluation_id}/proposals/{proposal_id}/scores/{requirement['id']}",
            json={"score": 5, "comment": None},
            headers=owner_headers,
        )
        assert response.status_code == 200, response.text
    econ = client.put(
        f"/api/v1/evaluations/{evaluation_id}/proposals/{proposal_id}/economic-assessment",
        json=_max_scores_body(),
        headers=owner_headers,
    )
    assert econ.status_code == 200, econ.text
    complete = client.post(f"/api/v1/evaluations/{evaluation_id}/complete", headers=owner_headers)
    assert complete.status_code == 200, complete.text
    assert "evaluation_completed" in _events_for(notifications, tenant_id, owner_membership_id)

    # Bonus: approval_requested (decision) - the decision's own approver,
    # deliberately a distinct Membership from the publication approver
    # (Fase 22 plan Bloqueante #1 Opcion B).
    decision_approver_id = _create_approver(
        mongo_test_db,
        tenant_id,
        email="decision.approver.notifications@dev.local",
        display_name="Aprobador Decisión Notificaciones",
    )
    client.post(f"/api/v1/evaluations/{evaluation_id}/decision", headers=owner_headers)
    client.patch(
        f"/api/v1/evaluations/{evaluation_id}/decision",
        json={
            "outcome": "selected",
            "selected_vendor_org_id": vendor_org_id,
            "justification": "El proveedor cumple todos los requisitos y su TCO es el menor.",
        },
        headers=owner_headers,
    )
    client.post(
        f"/api/v1/evaluations/{evaluation_id}/decision/approver",
        json={"approver_membership_id": decision_approver_id},
        headers=owner_headers,
    )
    request_approval = client.post(
        f"/api/v1/evaluations/{evaluation_id}/decision/request-approval", headers=owner_headers
    )
    assert request_approval.status_code == 200, request_approval.text
    assert "approval_requested" in _events_for(notifications, tenant_id, decision_approver_id)
