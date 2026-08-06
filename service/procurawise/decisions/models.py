from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

# Fase 22 - mirrors evaluations.models.ApprovalStatus exactly (same 4 values,
# same "rejected is not terminal" semantics: request_approval is valid from
# both "not_requested" and "rejected", looping back to "pending"). Kept as
# its own Literal (not imported from evaluations) because Decision's
# approval act is deliberately independent from Evaluation's publication
# approval (plan Bloqueante #1, Opcion B) - the two must never be able to
# drift into sharing a type by accident.
DecisionStatus = Literal["not_requested", "pending", "approved", "rejected"]

# "selected" = a vendor was chosen; "void" = the owner explicitly declared
# the process deserted (no vendor selected). There is no third option and no
# multi-vendor selection - see plan section 10, decision 2 (single vendor +
# explicit void, no product signal for multi-award).
DecisionOutcome = Literal["selected", "void"]


def new_id() -> str:
    """Unused today (Decision.id is deterministic, == evaluation_id) - kept
    for parity with every other models.py in this codebase in case a future
    phase needs a non-deterministic id here."""
    from uuid import uuid4

    return uuid4().hex


@dataclass(frozen=True)
class Decision:
    """One Decision per Evaluation (1:1, same grain as EvaluationSnapshot).
    `id` is deterministic (== evaluation_id): at most one Decision can ever
    exist per evaluation, so there is no separate uniqueness index to
    maintain - the natural key of the collection is `_id` itself.

    `approver_membership_id` is a field of its own, never copied from or
    written back to Evaluation.approver_membership_id (plan Bloqueante #1,
    Opcion B, resolved by the founder): the publication approval (Fase 12)
    and the decision approval (Fase 22) are two independent acts with their
    own actor, state and timestamps."""

    id: str
    tenant_id: str
    evaluation_id: str
    status: DecisionStatus
    outcome: DecisionOutcome | None
    selected_vendor_org_id: str | None
    selected_proposal_id: str | None
    selected_proposal_snapshot_id: str | None
    void_reason: str | None
    justification: str | None
    approver_membership_id: str | None
    created_by_membership_id: str
    created_at: datetime
    updated_at: datetime
    approval_requested_at: datetime | None
    approval_requested_by_membership_id: str | None
    approval_decided_at: datetime | None
    approval_decided_by_membership_id: str | None
    approval_comment: str | None
    decision_snapshot_id: str | None

    @staticmethod
    def create(*, tenant_id: str, evaluation_id: str, created_by_membership_id: str) -> "Decision":
        now = datetime.now(UTC)
        return Decision(
            id=evaluation_id,
            tenant_id=tenant_id,
            evaluation_id=evaluation_id,
            status="not_requested",
            outcome=None,
            selected_vendor_org_id=None,
            selected_proposal_id=None,
            selected_proposal_snapshot_id=None,
            void_reason=None,
            justification=None,
            approver_membership_id=None,
            created_by_membership_id=created_by_membership_id,
            created_at=now,
            updated_at=now,
            approval_requested_at=None,
            approval_requested_by_membership_id=None,
            approval_decided_at=None,
            approval_decided_by_membership_id=None,
            approval_comment=None,
            decision_snapshot_id=None,
        )

    def to_document(self) -> dict[str, Any]:
        return {
            "_id": self.id,
            "tenant_id": self.tenant_id,
            "evaluation_id": self.evaluation_id,
            "status": self.status,
            "outcome": self.outcome,
            "selected_vendor_org_id": self.selected_vendor_org_id,
            "selected_proposal_id": self.selected_proposal_id,
            "selected_proposal_snapshot_id": self.selected_proposal_snapshot_id,
            "void_reason": self.void_reason,
            "justification": self.justification,
            "approver_membership_id": self.approver_membership_id,
            "created_by_membership_id": self.created_by_membership_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "approval_requested_at": self.approval_requested_at,
            "approval_requested_by_membership_id": self.approval_requested_by_membership_id,
            "approval_decided_at": self.approval_decided_at,
            "approval_decided_by_membership_id": self.approval_decided_by_membership_id,
            "approval_comment": self.approval_comment,
            "decision_snapshot_id": self.decision_snapshot_id,
        }

    @staticmethod
    def from_document(doc: dict[str, Any]) -> "Decision":
        return Decision(
            id=doc["_id"],
            tenant_id=doc["tenant_id"],
            evaluation_id=doc["evaluation_id"],
            status=doc["status"],
            outcome=doc.get("outcome"),
            selected_vendor_org_id=doc.get("selected_vendor_org_id"),
            selected_proposal_id=doc.get("selected_proposal_id"),
            selected_proposal_snapshot_id=doc.get("selected_proposal_snapshot_id"),
            void_reason=doc.get("void_reason"),
            justification=doc.get("justification"),
            approver_membership_id=doc.get("approver_membership_id"),
            created_by_membership_id=doc["created_by_membership_id"],
            created_at=doc["created_at"],
            updated_at=doc["updated_at"],
            approval_requested_at=doc.get("approval_requested_at"),
            approval_requested_by_membership_id=doc.get("approval_requested_by_membership_id"),
            approval_decided_at=doc.get("approval_decided_at"),
            approval_decided_by_membership_id=doc.get("approval_decided_by_membership_id"),
            approval_comment=doc.get("approval_comment"),
            decision_snapshot_id=doc.get("decision_snapshot_id"),
        )


@dataclass(frozen=True)
class DecisionSnapshot:
    """Immutable "memo de cierre" (plan section 15), taken once at the
    pending -> approved transition. Lives in its own collection
    (decisions.snapshot_repository), never embedded on Decision - mirrors
    evaluations.models.EvaluationSnapshot. `snapshot_id == evaluation_id`
    (deterministic, not a fresh uuid): DecisionStatus never regresses out of
    "approved", so at most one snapshot can ever exist per evaluation, and
    the deterministic id makes the insert step naturally idempotent under
    retry (a repeat insert raises DuplicateKeyError, treated as already-done,
    same pattern as EvaluationSnapshot).

    `proposal_results` is a verbatim copy (not a reference) of
    ScoringService.get_results()["proposals"] taken at approval time - a
    Score or FXRate that changes afterwards must never be able to alter an
    already-approved memo de cierre retroactively."""

    snapshot_id: str
    tenant_id: str
    evaluation_id: str
    outcome: DecisionOutcome
    selected_vendor_org_id: str | None
    selected_vendor_org_name: str | None
    selected_proposal_id: str | None
    selected_proposal_snapshot_id: str | None
    void_reason: str | None
    justification: str
    approver_membership_id: str
    decided_at: datetime
    decided_by_membership_id: str
    proposal_results: list[dict[str, Any]]
    taken_at: datetime

    def to_document(self) -> dict[str, Any]:
        return {
            "_id": self.snapshot_id,
            "tenant_id": self.tenant_id,
            "evaluation_id": self.evaluation_id,
            "outcome": self.outcome,
            "selected_vendor_org_id": self.selected_vendor_org_id,
            "selected_vendor_org_name": self.selected_vendor_org_name,
            "selected_proposal_id": self.selected_proposal_id,
            "selected_proposal_snapshot_id": self.selected_proposal_snapshot_id,
            "void_reason": self.void_reason,
            "justification": self.justification,
            "approver_membership_id": self.approver_membership_id,
            "decided_at": self.decided_at,
            "decided_by_membership_id": self.decided_by_membership_id,
            "proposal_results": self.proposal_results,
            "taken_at": self.taken_at,
        }

    @staticmethod
    def from_document(doc: dict[str, Any]) -> "DecisionSnapshot":
        return DecisionSnapshot(
            snapshot_id=doc["_id"],
            tenant_id=doc["tenant_id"],
            evaluation_id=doc["evaluation_id"],
            outcome=doc["outcome"],
            selected_vendor_org_id=doc.get("selected_vendor_org_id"),
            selected_vendor_org_name=doc.get("selected_vendor_org_name"),
            selected_proposal_id=doc.get("selected_proposal_id"),
            selected_proposal_snapshot_id=doc.get("selected_proposal_snapshot_id"),
            void_reason=doc.get("void_reason"),
            justification=doc["justification"],
            approver_membership_id=doc["approver_membership_id"],
            decided_at=doc["decided_at"],
            decided_by_membership_id=doc["decided_by_membership_id"],
            proposal_results=doc.get("proposal_results", []),
            taken_at=doc["taken_at"],
        )
