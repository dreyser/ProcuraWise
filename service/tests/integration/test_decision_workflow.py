"""Fase 22 acceptance criterion (backlog.md fila 22): "Decision requiere
aprobador humano explicito; nunca hay adjudicacion automatica." Exercises the
full Decision workflow against real Mongo: readiness gating on
Evaluation.status == "completed", draft selection/justification, a decision
approver assignment independent from the evaluation's publication approver
(plan Bloqueante #1, Opcion B), request/withdraw/approve/reject, the
immutable DecisionSnapshot ("memo de cierre"), and the crash-recovery/retry
safety of approve()."""

from datetime import UTC, datetime

import pytest

from procurawise.decisions.repository import DecisionRepository
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


def _max_scores_body() -> dict:
    return {
        "commercial_scores": [
            {"criterion_key": k, "score": 5, "comment": "Excelente"} for k in _COMMERCIAL_KEYS
        ],
        "risk_scores": [
            {"criterion_key": k, "score": 5, "comment": "Excelente"} for k in _RISK_KEYS
        ],
    }


def _add_cost_item(client, vendor_headers, proposal_id: str, *, expected_version: int) -> int:
    """The economic component of a result stays "not_available" until every
    submitted proposal has both an EconomicAssessment and a frozen
    tco_result (Fase 19/20) - a proposal with zero cost items has no
    tco_result at all, same precondition test_economic_scoring_results.py's
    own helper exists to satisfy."""
    response = client.post(
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
            "expected_version": expected_version,
        },
        headers=vendor_headers,
    )
    assert response.status_code == 200, response.text
    return response.json()["version"]


def _create_approver(mongo_test_db, tenant_id: str, *, email: str, display_name: str) -> str:
    """A second, independent "approver"-role Membership on tenant_id -
    dev_seed only ever seeds one per tenant (unique_actor_by_role asserts
    exactly one), and plan Bloqueante #1 (Opcion B) requires proving the
    decision's own approver can be a genuinely different person from the
    evaluation's publication approver."""
    users = UserRepository(mongo_test_db)
    memberships = MembershipRepository(mongo_test_db)
    user = User.create(display_name=display_name, email=email)
    users.insert(user.to_document())
    membership = Membership.create(tenant_id=tenant_id, user_id=user.id, role="approver")
    memberships.insert(membership.to_document())
    return membership.id


def _build_completed_evaluation(client, seeded_actors, mongo_test_settings) -> dict:
    """One evaluation, 1 functional (weight 40) + 1 technical (weight 20)
    requirement, one proposal, scored to full marks and economically
    assessed, then completed - the exact precondition state a Decision may
    be created against (plan section 10, decision 1)."""
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
        json={"name": "Decision RFP", "description": ""},
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

    publication_approver_membership_id = seeded_actors[(tenant_a, "approver")]
    publication_approver_headers = bearer_headers_for(
        publication_approver_membership_id, mongo_test_settings
    )
    approve_and_publish(
        client,
        owner_headers,
        publication_approver_membership_id,
        publication_approver_headers,
        evaluation_id,
    )

    cost_item_version = _add_cost_item(client, vendor_headers, proposal_id, expected_version=1)
    submit = client.post(
        f"/api/v1/vendor-portal/proposals/{proposal_id}/submit",
        json={"expected_version": cost_item_version},
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

    economic = client.put(
        f"/api/v1/evaluations/{evaluation_id}/proposals/{proposal_id}/economic-assessment",
        json=_max_scores_body(),
        headers=owner_headers,
    )
    assert economic.status_code == 200, economic.text

    complete = client.post(f"/api/v1/evaluations/{evaluation_id}/complete", headers=owner_headers)
    assert complete.status_code == 200, complete.text
    assert complete.json()["status"] == "completed"

    return {
        "tenant_id": tenant_a,
        "evaluation_id": evaluation_id,
        "vendor_org_id": vendor_org_id,
        "proposal_id": proposal_id,
        "owner_headers": owner_headers,
        "publication_approver_membership_id": publication_approver_membership_id,
        "publication_approver_headers": publication_approver_headers,
    }


def test_readiness_and_create_are_blocked_before_evaluation_completed(
    client, seeded_actors, mongo_test_settings
) -> None:
    tenant_a, _vendor_membership_id = unique_actor_by_role(seeded_actors, "vendor_contact")
    owner_headers = bearer_headers_for(
        seeded_actors[(tenant_a, "evaluation_owner")], mongo_test_settings
    )
    evaluation_id = client.post(
        "/api/v1/evaluations",
        json={"name": "Not completed yet RFP", "description": ""},
        headers=owner_headers,
    ).json()["id"]

    readiness = client.get(
        f"/api/v1/evaluations/{evaluation_id}/decision/readiness", headers=owner_headers
    )
    assert readiness.status_code == 200
    body = readiness.json()
    assert body["evaluation_completed"] is False
    assert body["can_create"] is False
    assert body["decision_exists"] is False

    create = client.post(f"/api/v1/evaluations/{evaluation_id}/decision", headers=owner_headers)
    assert create.status_code == 409

    get_decision = client.get(
        f"/api/v1/evaluations/{evaluation_id}/decision", headers=owner_headers
    )
    assert get_decision.status_code == 404


def test_full_happy_path_with_decision_approver_distinct_from_publication_approver(
    client, seeded_actors, mongo_test_settings, mongo_test_db
) -> None:
    ctx = _build_completed_evaluation(client, seeded_actors, mongo_test_settings)

    decision_approver_membership_id = _create_approver(
        mongo_test_db,
        ctx["tenant_id"],
        email="decision.approver@dev.local",
        display_name="Aprobador de Decision",
    )
    assert decision_approver_membership_id != ctx["publication_approver_membership_id"]
    decision_approver_headers = bearer_headers_for(
        decision_approver_membership_id, mongo_test_settings
    )

    readiness_before = client.get(
        f"/api/v1/evaluations/{ctx['evaluation_id']}/decision/readiness",
        headers=ctx["owner_headers"],
    )
    assert readiness_before.json()["can_create"] is True
    assert (
        readiness_before.json()["suggested_approver_membership_id"]
        == ctx["publication_approver_membership_id"]
    )

    create = client.post(
        f"/api/v1/evaluations/{ctx['evaluation_id']}/decision", headers=ctx["owner_headers"]
    )
    assert create.status_code == 201, create.text
    assert create.json()["status"] == "not_requested"
    assert create.json()["approver_membership_id"] is None  # never auto-copied (Bloqueante #1)

    update = client.patch(
        f"/api/v1/evaluations/{ctx['evaluation_id']}/decision",
        json={
            "outcome": "selected",
            "selected_vendor_org_id": ctx["vendor_org_id"],
            "justification": _JUSTIFICATION,
        },
        headers=ctx["owner_headers"],
    )
    assert update.status_code == 200, update.text
    body = update.json()
    assert body["selected_proposal_id"] == ctx["proposal_id"]
    assert body["selected_proposal_snapshot_id"] is not None

    set_approver = client.post(
        f"/api/v1/evaluations/{ctx['evaluation_id']}/decision/approver",
        json={"approver_membership_id": decision_approver_membership_id},
        headers=ctx["owner_headers"],
    )
    assert set_approver.status_code == 200, set_approver.text
    assert set_approver.json()["approver_membership_id"] == decision_approver_membership_id

    request_approval = client.post(
        f"/api/v1/evaluations/{ctx['evaluation_id']}/decision/request-approval",
        headers=ctx["owner_headers"],
    )
    assert request_approval.status_code == 200, request_approval.text
    assert request_approval.json()["status"] == "pending"

    # The publication approver (a different person) may not decide this -
    # only the decision's own assigned approver may.
    wrong_approver_attempt = client.post(
        f"/api/v1/evaluations/{ctx['evaluation_id']}/decision/approve",
        json={},
        headers=ctx["publication_approver_headers"],
    )
    assert wrong_approver_attempt.status_code == 403

    approve = client.post(
        f"/api/v1/evaluations/{ctx['evaluation_id']}/decision/approve",
        json={"comment": "Aprobado"},
        headers=decision_approver_headers,
    )
    assert approve.status_code == 200, approve.text
    approved_body = approve.json()
    assert approved_body["status"] == "approved"
    assert approved_body["decision_snapshot_id"] == ctx["evaluation_id"]

    snapshot = client.get(
        f"/api/v1/evaluations/{ctx['evaluation_id']}/decision/snapshot",
        headers=ctx["owner_headers"],
    )
    assert snapshot.status_code == 200
    snapshot_body = snapshot.json()
    assert snapshot_body["outcome"] == "selected"
    assert snapshot_body["selected_vendor_org_id"] == ctx["vendor_org_id"]
    assert snapshot_body["justification"] == _JUSTIFICATION
    assert snapshot_body["approver_membership_id"] == decision_approver_membership_id
    assert len(snapshot_body["proposal_results"]) == 1
    assert snapshot_body["proposal_results"][0]["proposal_id"] == ctx["proposal_id"]

    # Evaluation.approver_membership_id must remain the publication
    # approver, untouched by the decision's own approver assignment.
    evaluation = client.get(
        f"/api/v1/evaluations/{ctx['evaluation_id']}", headers=ctx["owner_headers"]
    ).json()
    assert evaluation["approver_membership_id"] == ctx["publication_approver_membership_id"]

    # A retry of an already-fully-succeeded approve() is a clean no-op, not
    # a duplicate snapshot or an error.
    retry = client.post(
        f"/api/v1/evaluations/{ctx['evaluation_id']}/decision/approve",
        json={"comment": "Aprobado"},
        headers=decision_approver_headers,
    )
    assert retry.status_code == 200
    snapshots = list(
        mongo_test_db["decision_snapshots"].find({"evaluation_id": ctx["evaluation_id"]})
    )
    assert len(snapshots) == 1


def test_approve_resumes_from_crash_between_status_transition_and_snapshot(
    client, seeded_actors, mongo_test_settings, mongo_test_db
) -> None:
    """Simulates a process dying after the atomic pending -> approved write
    commits but before the snapshot step ever runs (by driving that first
    write directly through the repository, bypassing the service's approve()
    orchestration entirely) - mirrors
    test_evaluation_publication_snapshot.py's equivalent crash-recovery test
    for start-collection."""
    ctx = _build_completed_evaluation(client, seeded_actors, mongo_test_settings)
    decision_approver_membership_id = _create_approver(
        mongo_test_db,
        ctx["tenant_id"],
        email="decision.approver.crash@dev.local",
        display_name="Aprobador Crash",
    )
    decision_approver_headers = bearer_headers_for(
        decision_approver_membership_id, mongo_test_settings
    )

    client.post(
        f"/api/v1/evaluations/{ctx['evaluation_id']}/decision", headers=ctx["owner_headers"]
    )
    client.patch(
        f"/api/v1/evaluations/{ctx['evaluation_id']}/decision",
        json={
            "outcome": "selected",
            "selected_vendor_org_id": ctx["vendor_org_id"],
            "justification": _JUSTIFICATION,
        },
        headers=ctx["owner_headers"],
    )
    client.post(
        f"/api/v1/evaluations/{ctx['evaluation_id']}/decision/approver",
        json={"approver_membership_id": decision_approver_membership_id},
        headers=ctx["owner_headers"],
    )
    client.post(
        f"/api/v1/evaluations/{ctx['evaluation_id']}/decision/request-approval",
        headers=ctx["owner_headers"],
    )

    decisions = DecisionRepository(mongo_test_db)
    matched = decisions.transition_status(
        ctx["tenant_id"],
        ctx["evaluation_id"],
        ("pending",),
        "approved",
        {
            "approval_decided_at": datetime.now(UTC),
            "approval_decided_by_membership_id": decision_approver_membership_id,
            "approval_comment": None,
        },
    )
    assert matched
    assert (
        mongo_test_db["decision_snapshots"].count_documents({"evaluation_id": ctx["evaluation_id"]})
        == 0
    )

    resumed = client.post(
        f"/api/v1/evaluations/{ctx['evaluation_id']}/decision/approve",
        json={},
        headers=decision_approver_headers,
    )
    assert resumed.status_code == 200, resumed.text
    assert resumed.json()["decision_snapshot_id"] == ctx["evaluation_id"]

    snapshots = list(
        mongo_test_db["decision_snapshots"].find({"evaluation_id": ctx["evaluation_id"]})
    )
    assert len(snapshots) == 1


def test_reject_then_edit_then_reapprove(
    client, seeded_actors, mongo_test_settings, mongo_test_db
) -> None:
    ctx = _build_completed_evaluation(client, seeded_actors, mongo_test_settings)
    decision_approver_membership_id = _create_approver(
        mongo_test_db,
        ctx["tenant_id"],
        email="decision.approver.reject@dev.local",
        display_name="Aprobador Rechazo",
    )
    decision_approver_headers = bearer_headers_for(
        decision_approver_membership_id, mongo_test_settings
    )

    client.post(
        f"/api/v1/evaluations/{ctx['evaluation_id']}/decision", headers=ctx["owner_headers"]
    )
    client.patch(
        f"/api/v1/evaluations/{ctx['evaluation_id']}/decision",
        json={
            "outcome": "selected",
            "selected_vendor_org_id": ctx["vendor_org_id"],
            "justification": _JUSTIFICATION,
        },
        headers=ctx["owner_headers"],
    )
    client.post(
        f"/api/v1/evaluations/{ctx['evaluation_id']}/decision/approver",
        json={"approver_membership_id": decision_approver_membership_id},
        headers=ctx["owner_headers"],
    )
    client.post(
        f"/api/v1/evaluations/{ctx['evaluation_id']}/decision/request-approval",
        headers=ctx["owner_headers"],
    )

    reject = client.post(
        f"/api/v1/evaluations/{ctx['evaluation_id']}/decision/reject",
        json={"comment": "Falta justificacion sobre riesgos."},
        headers=decision_approver_headers,
    )
    assert reject.status_code == 200
    assert reject.json()["status"] == "rejected"

    # A rejection with no comment is a validation error at the schema level.
    reject_without_comment = client.post(
        f"/api/v1/evaluations/{ctx['evaluation_id']}/decision/reject",
        json={},
        headers=decision_approver_headers,
    )
    assert reject_without_comment.status_code == 422

    edit = client.patch(
        f"/api/v1/evaluations/{ctx['evaluation_id']}/decision",
        json={
            "justification": _JUSTIFICATION + " Ademas, su plan de mitigacion de riesgos es solido."
        },
        headers=ctx["owner_headers"],
    )
    assert edit.status_code == 200

    reapproval_request = client.post(
        f"/api/v1/evaluations/{ctx['evaluation_id']}/decision/request-approval",
        headers=ctx["owner_headers"],
    )
    assert reapproval_request.status_code == 200
    assert reapproval_request.json()["status"] == "pending"

    approve = client.post(
        f"/api/v1/evaluations/{ctx['evaluation_id']}/decision/approve",
        json={},
        headers=decision_approver_headers,
    )
    assert approve.status_code == 200
    assert approve.json()["status"] == "approved"


def test_withdraw_approval_request_returns_to_editable(
    client, seeded_actors, mongo_test_settings, mongo_test_db
) -> None:
    ctx = _build_completed_evaluation(client, seeded_actors, mongo_test_settings)
    decision_approver_membership_id = _create_approver(
        mongo_test_db,
        ctx["tenant_id"],
        email="decision.approver.withdraw@dev.local",
        display_name="Aprobador Retiro",
    )

    client.post(
        f"/api/v1/evaluations/{ctx['evaluation_id']}/decision", headers=ctx["owner_headers"]
    )
    client.patch(
        f"/api/v1/evaluations/{ctx['evaluation_id']}/decision",
        json={
            "outcome": "selected",
            "selected_vendor_org_id": ctx["vendor_org_id"],
            "justification": _JUSTIFICATION,
        },
        headers=ctx["owner_headers"],
    )
    client.post(
        f"/api/v1/evaluations/{ctx['evaluation_id']}/decision/approver",
        json={"approver_membership_id": decision_approver_membership_id},
        headers=ctx["owner_headers"],
    )
    client.post(
        f"/api/v1/evaluations/{ctx['evaluation_id']}/decision/request-approval",
        headers=ctx["owner_headers"],
    )

    withdraw = client.delete(
        f"/api/v1/evaluations/{ctx['evaluation_id']}/decision/request-approval",
        headers=ctx["owner_headers"],
    )
    assert withdraw.status_code == 204

    decision = client.get(
        f"/api/v1/evaluations/{ctx['evaluation_id']}/decision", headers=ctx["owner_headers"]
    ).json()
    assert decision["status"] == "not_requested"

    # Editable again now that it is back to not_requested.
    edit = client.patch(
        f"/api/v1/evaluations/{ctx['evaluation_id']}/decision",
        json={"justification": _JUSTIFICATION + " Version editada tras retiro."},
        headers=ctx["owner_headers"],
    )
    assert edit.status_code == 200


def test_void_outcome_declares_process_deserted(
    client, seeded_actors, mongo_test_settings, mongo_test_db
) -> None:
    ctx = _build_completed_evaluation(client, seeded_actors, mongo_test_settings)
    decision_approver_membership_id = _create_approver(
        mongo_test_db,
        ctx["tenant_id"],
        email="decision.approver.void@dev.local",
        display_name="Aprobador Desierto",
    )
    decision_approver_headers = bearer_headers_for(
        decision_approver_membership_id, mongo_test_settings
    )

    client.post(
        f"/api/v1/evaluations/{ctx['evaluation_id']}/decision", headers=ctx["owner_headers"]
    )
    update = client.patch(
        f"/api/v1/evaluations/{ctx['evaluation_id']}/decision",
        json={
            "outcome": "void",
            "void_reason": "Ningun proveedor cumplio el presupuesto maximo autorizado.",
            "justification": "Se declara desierto por exceder el presupuesto en todos los casos.",
        },
        headers=ctx["owner_headers"],
    )
    assert update.status_code == 200
    body = update.json()
    assert body["selected_vendor_org_id"] is None
    assert body["selected_proposal_id"] is None

    client.post(
        f"/api/v1/evaluations/{ctx['evaluation_id']}/decision/approver",
        json={"approver_membership_id": decision_approver_membership_id},
        headers=ctx["owner_headers"],
    )
    client.post(
        f"/api/v1/evaluations/{ctx['evaluation_id']}/decision/request-approval",
        headers=ctx["owner_headers"],
    )
    approve = client.post(
        f"/api/v1/evaluations/{ctx['evaluation_id']}/decision/approve",
        json={},
        headers=decision_approver_headers,
    )
    assert approve.status_code == 200

    snapshot = client.get(
        f"/api/v1/evaluations/{ctx['evaluation_id']}/decision/snapshot",
        headers=ctx["owner_headers"],
    ).json()
    assert snapshot["outcome"] == "void"
    assert snapshot["selected_vendor_org_id"] is None
    assert snapshot["void_reason"] == "Ningun proveedor cumplio el presupuesto maximo autorizado."


def test_self_approval_is_blocked(
    client, seeded_actors, mongo_test_settings, mongo_test_db
) -> None:
    ctx = _build_completed_evaluation(client, seeded_actors, mongo_test_settings)

    # The owner's own user, holding a second Membership with the "approver"
    # role on the same tenant (same pattern dev_seed.py uses for owner_b/
    # tenant_b: "roles acumulables", spec S4.1/FR-005).
    memberships = MembershipRepository(mongo_test_db)
    owner_membership = memberships.find_by_id(seeded_actors[(ctx["tenant_id"], "evaluation_owner")])
    assert owner_membership is not None
    self_approver = Membership.create(
        tenant_id=ctx["tenant_id"], user_id=owner_membership["user_id"], role="approver"
    )
    memberships.insert(self_approver.to_document())

    client.post(
        f"/api/v1/evaluations/{ctx['evaluation_id']}/decision", headers=ctx["owner_headers"]
    )
    attempt = client.post(
        f"/api/v1/evaluations/{ctx['evaluation_id']}/decision/approver",
        json={"approver_membership_id": self_approver.id},
        headers=ctx["owner_headers"],
    )
    assert attempt.status_code == 400
    assert "own decision approver" in attempt.json()["detail"]


def test_approver_role_mismatch_is_rejected(client, seeded_actors, mongo_test_settings) -> None:
    ctx = _build_completed_evaluation(client, seeded_actors, mongo_test_settings)
    tenant_a, evaluator_membership_id = unique_actor_by_role(seeded_actors, "evaluator_functional")
    assert tenant_a == ctx["tenant_id"]

    client.post(
        f"/api/v1/evaluations/{ctx['evaluation_id']}/decision", headers=ctx["owner_headers"]
    )
    attempt = client.post(
        f"/api/v1/evaluations/{ctx['evaluation_id']}/decision/approver",
        json={"approver_membership_id": evaluator_membership_id},
        headers=ctx["owner_headers"],
    )
    assert attempt.status_code == 400
    assert "approver role" in attempt.json()["detail"]


def test_selected_vendor_without_submitted_proposal_is_rejected(
    client, seeded_actors, mongo_test_settings, mongo_test_db
) -> None:
    ctx = _build_completed_evaluation(client, seeded_actors, mongo_test_settings)
    client.post(
        f"/api/v1/evaluations/{ctx['evaluation_id']}/decision", headers=ctx["owner_headers"]
    )
    attempt = client.patch(
        f"/api/v1/evaluations/{ctx['evaluation_id']}/decision",
        json={
            "outcome": "selected",
            "selected_vendor_org_id": "not-a-linked-vendor-org",
            "justification": _JUSTIFICATION,
        },
        headers=ctx["owner_headers"],
    )
    assert attempt.status_code == 422


def test_request_approval_requires_full_readiness(
    client, seeded_actors, mongo_test_settings
) -> None:
    ctx = _build_completed_evaluation(client, seeded_actors, mongo_test_settings)
    client.post(
        f"/api/v1/evaluations/{ctx['evaluation_id']}/decision", headers=ctx["owner_headers"]
    )

    # No outcome, no justification, no approver yet.
    attempt = client.post(
        f"/api/v1/evaluations/{ctx['evaluation_id']}/decision/request-approval",
        headers=ctx["owner_headers"],
    )
    assert attempt.status_code == 400
    detail = attempt.json()["detail"]
    assert "outcome" in detail
    assert "justification" in detail
    assert "approver" in detail
