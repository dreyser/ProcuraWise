"""Fase 22 (plan Bloqueante #1, Opcion B) - model-level coverage for
Decision/DecisionSnapshot: safe defaults on create(), and a lossless
to_document/from_document round trip for both dataclasses."""

from datetime import UTC, datetime

from procurawise.decisions.models import Decision, DecisionSnapshot


def test_decision_create_defaults_to_not_requested_with_deterministic_id() -> None:
    decision = Decision.create(
        tenant_id="tenant-1", evaluation_id="eval-1", created_by_membership_id="m-owner"
    )
    assert decision.id == "eval-1"
    assert decision.evaluation_id == "eval-1"
    assert decision.status == "not_requested"
    assert decision.outcome is None
    assert decision.selected_vendor_org_id is None
    assert decision.selected_proposal_id is None
    assert decision.selected_proposal_snapshot_id is None
    assert decision.void_reason is None
    assert decision.justification is None
    assert decision.approver_membership_id is None
    assert decision.created_by_membership_id == "m-owner"
    assert decision.decision_snapshot_id is None


def test_decision_document_round_trip_is_lossless() -> None:
    now = datetime.now(UTC)
    decision = Decision(
        id="eval-1",
        tenant_id="tenant-1",
        evaluation_id="eval-1",
        status="pending",
        outcome="selected",
        selected_vendor_org_id="vendor-1",
        selected_proposal_id="proposal-1",
        selected_proposal_snapshot_id="snap-0",
        void_reason=None,
        justification="El proveedor cumple todos los requisitos obligatorios y su TCO es el menor.",
        approver_membership_id="m-approver",
        created_by_membership_id="m-owner",
        created_at=now,
        updated_at=now,
        approval_requested_at=now,
        approval_requested_by_membership_id="m-owner",
        approval_decided_at=None,
        approval_decided_by_membership_id=None,
        approval_comment=None,
        decision_snapshot_id=None,
    )
    restored = Decision.from_document(decision.to_document())
    assert restored == decision


def test_decision_document_round_trip_tolerates_missing_optional_keys() -> None:
    """A document written before some future phase adds a new optional field
    must still deserialize safely (same "no backfill, .get(..., default)"
    convention as every other models.py in this codebase)."""
    now = datetime.now(UTC)
    minimal_doc = {
        "_id": "eval-1",
        "tenant_id": "tenant-1",
        "evaluation_id": "eval-1",
        "status": "not_requested",
        "created_by_membership_id": "m-owner",
        "created_at": now,
        "updated_at": now,
    }
    decision = Decision.from_document(minimal_doc)
    assert decision.outcome is None
    assert decision.selected_vendor_org_id is None
    assert decision.approver_membership_id is None
    assert decision.decision_snapshot_id is None


def test_decision_snapshot_document_round_trip_is_lossless() -> None:
    now = datetime.now(UTC)
    snapshot = DecisionSnapshot(
        snapshot_id="eval-1",
        tenant_id="tenant-1",
        evaluation_id="eval-1",
        outcome="selected",
        selected_vendor_org_id="vendor-1",
        selected_vendor_org_name="Proveedor Uno",
        selected_proposal_id="proposal-1",
        selected_proposal_snapshot_id="snap-0",
        void_reason=None,
        justification="El proveedor cumple todos los requisitos obligatorios y su TCO es el menor.",
        approver_membership_id="m-approver",
        decided_at=now,
        decided_by_membership_id="m-approver",
        proposal_results=[{"proposal_id": "proposal-1", "final_result": {"total_points": 100.0}}],
        taken_at=now,
    )
    restored = DecisionSnapshot.from_document(snapshot.to_document())
    assert restored == snapshot


def test_decision_snapshot_void_outcome_has_no_vendor_reference() -> None:
    now = datetime.now(UTC)
    snapshot = DecisionSnapshot(
        snapshot_id="eval-1",
        tenant_id="tenant-1",
        evaluation_id="eval-1",
        outcome="void",
        selected_vendor_org_id=None,
        selected_vendor_org_name=None,
        selected_proposal_id=None,
        selected_proposal_snapshot_id=None,
        void_reason="Ningun proveedor cumplio el presupuesto maximo autorizado.",
        justification="Se declara desierto por exceder el presupuesto en todos los casos.",
        approver_membership_id="m-approver",
        decided_at=now,
        decided_by_membership_id="m-approver",
        proposal_results=[],
        taken_at=now,
    )
    restored = DecisionSnapshot.from_document(snapshot.to_document())
    assert restored == snapshot
    assert restored.selected_vendor_org_id is None
