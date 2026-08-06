"""CLAUDE.md S4: every new route touching business data requires its own
negative tenant-isolation test. Covers cross-tenant 404s (never revealing
that a Decision/Evaluation exists in another tenant), role-based 403s
(vendor_contact and non-owner buyer roles), and that the decision's own
approver assignment is independent from - and never confused with - the
evaluation's publication approver."""

from datetime import UTC, datetime

import pytest

from procurawise.decisions.repository import DecisionRepository
from procurawise.evaluations.repository import EvaluationRepository
from procurawise.identity.dev_provider import DEV_ACTOR_HEADER
from procurawise.identity.models import Membership, User
from procurawise.identity.repository import MembershipRepository, UserRepository
from tests.conftest import (
    approve_and_publish,
    bearer_headers_for,
    tenant_ids,
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
_JUSTIFICATION = "El proveedor cumple todos los requisitos obligatorios y su TCO es el menor."


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


def _build_completed_evaluation_with_pending_decision(
    client, seeded_actors, mongo_test_settings, mongo_test_db
) -> dict:
    tenant_a, vendor_membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    vendor_headers = vendor_bearer_headers_for(vendor_membership_id, mongo_test_settings)
    vendor_org_id = client.get(
        "/api/v1/me", headers={DEV_ACTOR_HEADER: vendor_membership_id}
    ).json()["vendor_org_id"]

    evaluation_id = client.post(
        "/api/v1/evaluations",
        json={"name": "Isolation Decision RFP", "description": ""},
        headers=owner_headers,
    ).json()["id"]
    functional_id = client.post(
        f"/api/v1/evaluations/{evaluation_id}/requirements",
        json={
            "dimension": "functional",
            "category": "Core",
            "title": "Req funcional",
            "description": "d",
            "priority": "important",
            "response_type": "text",
            "weight": 40.0,
            "required": False,
            "display_order": 1,
        },
        headers=owner_headers,
    ).json()["id"]
    technical_id = client.post(
        f"/api/v1/evaluations/{evaluation_id}/requirements",
        json={
            "dimension": "technical",
            "category": "Core",
            "title": "Req tecnico",
            "description": "d",
            "priority": "important",
            "response_type": "text",
            "weight": 20.0,
            "required": False,
            "display_order": 2,
        },
        headers=owner_headers,
    ).json()["id"]
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
    submit = client.post(
        f"/api/v1/vendor-portal/proposals/{proposal_id}/submit",
        json={"expected_version": cost_item.json()["version"]},
        headers=vendor_headers,
    )
    assert submit.status_code == 200, submit.text

    client.post(f"/api/v1/evaluations/{evaluation_id}/start-evaluation", headers=owner_headers)
    for requirement_id in (functional_id, technical_id):
        response = client.put(
            f"/api/v1/evaluations/{evaluation_id}/proposals/{proposal_id}/scores/{requirement_id}",
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

    decision_approver_id = _create_approver(
        mongo_test_db,
        tenant_a,
        email="decision.approver.isolation@dev.local",
        display_name="Aprobador Isolation",
    )
    decision_approver_headers = bearer_headers_for(decision_approver_id, mongo_test_settings)

    client.post(f"/api/v1/evaluations/{evaluation_id}/decision", headers=owner_headers)
    client.patch(
        f"/api/v1/evaluations/{evaluation_id}/decision",
        json={
            "outcome": "selected",
            "selected_vendor_org_id": vendor_org_id,
            "justification": _JUSTIFICATION,
        },
        headers=owner_headers,
    )
    client.post(
        f"/api/v1/evaluations/{evaluation_id}/decision/approver",
        json={"approver_membership_id": decision_approver_id},
        headers=owner_headers,
    )
    client.post(
        f"/api/v1/evaluations/{evaluation_id}/decision/request-approval", headers=owner_headers
    )

    return {
        "tenant_id": tenant_a,
        "evaluation_id": evaluation_id,
        "owner_headers": owner_headers,
        "decision_approver_id": decision_approver_id,
        "decision_approver_headers": decision_approver_headers,
    }


def test_readiness_for_other_tenants_evaluation_returns_404(
    client, seeded_actors, mongo_test_settings
) -> None:
    tenant_a, tenant_b = tenant_ids(seeded_actors)
    owner_a_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    owner_b_headers = bearer_headers_for(
        seeded_actors[(tenant_b, "evaluation_owner")], mongo_test_settings
    )
    evaluation_id = client.post(
        "/api/v1/evaluations",
        json={"name": "Tenant A private RFP", "description": ""},
        headers=owner_a_headers,
    ).json()["id"]

    response = client.get(
        f"/api/v1/evaluations/{evaluation_id}/decision/readiness", headers=owner_b_headers
    )
    assert response.status_code == 404


def test_create_decision_for_other_tenants_evaluation_returns_404(
    client, seeded_actors, mongo_test_settings
) -> None:
    tenant_a, tenant_b = tenant_ids(seeded_actors)
    owner_a_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    owner_b_headers = bearer_headers_for(
        seeded_actors[(tenant_b, "evaluation_owner")], mongo_test_settings
    )
    evaluation_id = client.post(
        "/api/v1/evaluations",
        json={"name": "Tenant A private RFP 2", "description": ""},
        headers=owner_a_headers,
    ).json()["id"]

    response = client.post(f"/api/v1/evaluations/{evaluation_id}/decision", headers=owner_b_headers)
    assert response.status_code == 404


def test_vendor_contact_cannot_read_decision_endpoints(
    client, seeded_actors, mongo_test_settings
) -> None:
    tenant_a, vendor_membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    vendor_headers = bearer_headers_for(vendor_membership_id, mongo_test_settings)
    evaluation_id = client.post(
        "/api/v1/evaluations",
        json={"name": "Vendor-blocked RFP", "description": ""},
        headers=owner_headers,
    ).json()["id"]

    response = client.get(
        f"/api/v1/evaluations/{evaluation_id}/decision/readiness", headers=vendor_headers
    )
    assert response.status_code == 403


def test_non_owner_buyer_role_cannot_create_decision_but_can_read_readiness(
    client, seeded_actors, mongo_test_settings
) -> None:
    tenant_a, evaluator_membership_id = unique_actor_by_role(seeded_actors, "evaluator_functional")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    evaluator_headers = bearer_headers_for(evaluator_membership_id, mongo_test_settings)
    evaluation_id = client.post(
        "/api/v1/evaluations",
        json={"name": "Evaluator RFP", "description": ""},
        headers=owner_headers,
    ).json()["id"]

    readiness = client.get(
        f"/api/v1/evaluations/{evaluation_id}/decision/readiness", headers=evaluator_headers
    )
    assert readiness.status_code == 200

    create_attempt = client.post(
        f"/api/v1/evaluations/{evaluation_id}/decision", headers=evaluator_headers
    )
    assert create_attempt.status_code == 403


def test_cross_tenant_approver_cannot_approve_or_see_decision(
    client, seeded_actors, mongo_test_settings, mongo_test_db
) -> None:
    ctx = _build_completed_evaluation_with_pending_decision(
        client, seeded_actors, mongo_test_settings, mongo_test_db
    )
    # tenant_ids() labels its two arbitrary tenants by sorted-uuid order,
    # which carries no relation to which one _build_completed_evaluation_
    # with_pending_decision happened to build against - "the other tenant"
    # must be derived relative to ctx["tenant_id"] itself, never assumed.
    other_tenant_id = next(
        tenant_id for tenant_id, _role in seeded_actors if tenant_id != ctx["tenant_id"]
    )
    other_tenant_approver_headers = bearer_headers_for(
        seeded_actors[(other_tenant_id, "approver")], mongo_test_settings
    )

    approve_attempt = client.post(
        f"/api/v1/evaluations/{ctx['evaluation_id']}/decision/approve",
        json={},
        headers=other_tenant_approver_headers,
    )
    assert approve_attempt.status_code == 404

    read_attempt = client.get(
        f"/api/v1/evaluations/{ctx['evaluation_id']}/decision",
        headers=other_tenant_approver_headers,
    )
    assert read_attempt.status_code == 404


def test_decision_snapshot_never_exposes_across_tenants(
    client, seeded_actors, mongo_test_settings, mongo_test_db
) -> None:
    ctx = _build_completed_evaluation_with_pending_decision(
        client, seeded_actors, mongo_test_settings, mongo_test_db
    )
    approve = client.post(
        f"/api/v1/evaluations/{ctx['evaluation_id']}/decision/approve",
        json={},
        headers=ctx["decision_approver_headers"],
    )
    assert approve.status_code == 200

    other_tenant_id = next(
        tenant_id for tenant_id, _role in seeded_actors if tenant_id != ctx["tenant_id"]
    )
    other_tenant_owner_headers = bearer_headers_for(
        seeded_actors[(other_tenant_id, "evaluation_owner")], mongo_test_settings
    )
    snapshot_attempt = client.get(
        f"/api/v1/evaluations/{ctx['evaluation_id']}/decision/snapshot",
        headers=other_tenant_owner_headers,
    )
    assert snapshot_attempt.status_code == 404


def test_decision_approver_is_never_backfilled_from_evaluation_approver(
    client, seeded_actors, mongo_test_settings, mongo_test_db
) -> None:
    """Plan Bloqueante #1 (Opcion B): the two approver assignments must
    never be able to cross-contaminate, even at the raw document level."""
    tenant_a, vendor_membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    vendor_org_id = client.get(
        "/api/v1/me", headers={DEV_ACTOR_HEADER: vendor_membership_id}
    ).json()["vendor_org_id"]
    evaluation_id = client.post(
        "/api/v1/evaluations",
        json={"name": "No cross contamination RFP", "description": ""},
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
    client.post(
        f"/api/v1/evaluations/{evaluation_id}/vendors",
        json={"vendor_org_id": vendor_org_id},
        headers=owner_headers,
    )
    approver_membership_id = seeded_actors[(tenant_a, "approver")]
    approver_headers = bearer_headers_for(approver_membership_id, mongo_test_settings)
    approve_and_publish(
        client, owner_headers, approver_membership_id, approver_headers, evaluation_id
    )
    # Force the evaluation straight to "completed" at the repository level
    # (bypassing scoring) purely to unlock Decision creation for this
    # narrow document-shape check - no scores/results assertions are made.
    EvaluationRepository(mongo_test_db).transition_status(
        tenant_a, evaluation_id, "collecting_responses", "evaluating"
    )
    EvaluationRepository(mongo_test_db).transition_status(
        tenant_a, evaluation_id, "evaluating", "completed", {"completed_at": datetime.now(UTC)}
    )

    create = client.post(f"/api/v1/evaluations/{evaluation_id}/decision", headers=owner_headers)
    assert create.status_code == 201

    decision_doc = DecisionRepository(mongo_test_db).find_by_evaluation_id(tenant_a, evaluation_id)
    assert decision_doc is not None
    assert decision_doc["approver_membership_id"] is None
