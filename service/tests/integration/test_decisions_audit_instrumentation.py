"""Fase 22 - every Decision mutation must generate exactly the AuditEvent
described in decisions.service, with server-derived actor/tenant fields and
only allowlisted metadata (never the full justification text, CLAUDE.md's
sensitive-data rule)."""

import pytest

from procurawise.identity.dev_provider import DEV_ACTOR_HEADER
from procurawise.identity.models import Membership, User
from procurawise.identity.repository import MembershipRepository, UserRepository
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
_JUSTIFICATION = "El proveedor cumple todos los requisitos obligatorios y su TCO es el menor."


@pytest.fixture(autouse=True)
def _clean_audit_events(mongo_test_db):
    yield
    mongo_test_db["audit_events"].delete_many({})


def _events_for(mongo_test_db, evaluation_id: str) -> list[dict]:
    return list(
        mongo_test_db["audit_events"]
        .find({"evaluation_id": evaluation_id, "resource_type": "decision"})
        .sort("occurred_at", 1)
    )


def _max_scores_body() -> dict:
    return {
        "commercial_scores": [
            {"criterion_key": k, "score": 5, "comment": "Excelente"} for k in _COMMERCIAL_KEYS
        ],
        "risk_scores": [
            {"criterion_key": k, "score": 5, "comment": "Excelente"} for k in _RISK_KEYS
        ],
    }


def _create_approver(mongo_test_db, tenant_id: str) -> str:
    users = UserRepository(mongo_test_db)
    memberships = MembershipRepository(mongo_test_db)
    user = User.create(display_name="Aprobador Audit", email="decision.approver.audit@dev.local")
    users.insert(user.to_document())
    membership = Membership.create(tenant_id=tenant_id, user_id=user.id, role="approver")
    memberships.insert(membership.to_document())
    return membership.id


def test_decision_lifecycle_generates_exactly_the_expected_audit_events(
    client, seeded_actors, mongo_test_settings, mongo_test_db
) -> None:
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
        json={"name": "Audit Decision RFP", "description": ""},
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
    client.post(
        f"/api/v1/vendor-portal/proposals/{proposal_id}/submit",
        json={"expected_version": cost_item.json()["version"]},
        headers=vendor_headers,
    )
    client.post(f"/api/v1/evaluations/{evaluation_id}/start-evaluation", headers=owner_headers)
    for requirement_id in (functional_id, technical_id):
        client.put(
            f"/api/v1/evaluations/{evaluation_id}/proposals/{proposal_id}/scores/{requirement_id}",
            json={"score": 5, "comment": None},
            headers=owner_headers,
        )
    client.put(
        f"/api/v1/evaluations/{evaluation_id}/proposals/{proposal_id}/economic-assessment",
        json=_max_scores_body(),
        headers=owner_headers,
    )
    client.post(f"/api/v1/evaluations/{evaluation_id}/complete", headers=owner_headers)

    decision_approver_id = _create_approver(mongo_test_db, tenant_a)
    decision_approver_headers = bearer_headers_for(decision_approver_id, mongo_test_settings)

    # The setup above (evaluation lifecycle) already emitted its own audit
    # events with resource_type != "decision" - _events_for filters those
    # out, so only the Decision-specific ones below are asserted.
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
    client.post(
        f"/api/v1/evaluations/{evaluation_id}/decision/approve",
        json={"comment": "Aprobado"},
        headers=decision_approver_headers,
    )

    events = _events_for(mongo_test_db, evaluation_id)
    actions = [e["action"] for e in events]
    assert actions == [
        "decision_created",
        "decision_updated",
        "decision_approver_set",
        "decision_approval_requested",
        "decision_approved",
    ]

    for event in events:
        assert event["tenant_id"] == tenant_a
        assert event["resource_id"] == evaluation_id
        # Never the full justification text - only an allowlisted metadata
        # shape (CLAUDE.md's sensitive-data rule).
        assert "justification" not in event["metadata"]
        for value in event["metadata"].values():
            if isinstance(value, str):
                assert _JUSTIFICATION not in value

    approved_event = events[-1]
    assert approved_event["actor_membership_id"] == decision_approver_id
    assert approved_event["snapshot_id"] == evaluation_id


def test_rejected_decision_emits_decision_rejected_action(
    client, seeded_actors, mongo_test_settings, mongo_test_db
) -> None:
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
        json={"name": "Audit Reject RFP", "description": ""},
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
    client.post(
        f"/api/v1/vendor-portal/proposals/{proposal_id}/submit",
        json={"expected_version": cost_item.json()["version"]},
        headers=vendor_headers,
    )
    client.post(f"/api/v1/evaluations/{evaluation_id}/start-evaluation", headers=owner_headers)
    for requirement_id in (functional_id, technical_id):
        client.put(
            f"/api/v1/evaluations/{evaluation_id}/proposals/{proposal_id}/scores/{requirement_id}",
            json={"score": 5, "comment": None},
            headers=owner_headers,
        )
    client.put(
        f"/api/v1/evaluations/{evaluation_id}/proposals/{proposal_id}/economic-assessment",
        json=_max_scores_body(),
        headers=owner_headers,
    )
    client.post(f"/api/v1/evaluations/{evaluation_id}/complete", headers=owner_headers)

    decision_approver_id = _create_approver(mongo_test_db, tenant_a)
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
    client.post(
        f"/api/v1/evaluations/{evaluation_id}/decision/reject",
        json={"comment": "Falta evidencia"},
        headers=decision_approver_headers,
    )

    events = _events_for(mongo_test_db, evaluation_id)
    assert events[-1]["action"] == "decision_rejected"
    assert events[-1]["actor_membership_id"] == decision_approver_id
