from datetime import UTC, datetime
from typing import Any

from pymongo.errors import DuplicateKeyError

from procurawise.audit.service import AuditEventService
from procurawise.decisions.exceptions import (
    ApproverMembershipNotFoundError,
    ApproverRoleMismatchError,
    DecisionAlreadyExistsError,
    DecisionNotFoundError,
    DecisionPreconditionError,
    DecisionSnapshotNotFoundError,
    EvaluationNotCompletedError,
    InvalidDecisionStateError,
    NotAssignedApproverError,
    SelectedProposalNotFoundError,
    SelfApprovalError,
)
from procurawise.decisions.models import Decision, DecisionOutcome, DecisionSnapshot
from procurawise.decisions.repository import DecisionRepository
from procurawise.decisions.snapshot_repository import DecisionSnapshotRepository
from procurawise.evaluations.exceptions import EvaluationNotFoundError
from procurawise.evaluations.repository import EvaluationRepository
from procurawise.identity.repository import MembershipRepository, VendorOrganizationRepository
from procurawise.proposals.models import Proposal
from procurawise.proposals.repository import ProposalRepository
from procurawise.scoring.service import ScoringService
from procurawise.shared.context import ActorContext

_MIN_JUSTIFICATION_LENGTH = 20


class DecisionService:
    def __init__(
        self,
        decisions: DecisionRepository,
        snapshots: DecisionSnapshotRepository,
        evaluations: EvaluationRepository,
        proposals: ProposalRepository,
        vendor_orgs: VendorOrganizationRepository,
        memberships: MembershipRepository,
        scoring: ScoringService,
        audit: AuditEventService,
    ) -> None:
        self._decisions = decisions
        self._snapshots = snapshots
        self._evaluations = evaluations
        self._proposals = proposals
        self._vendor_orgs = vendor_orgs
        self._memberships = memberships
        self._scoring = scoring
        self._audit = audit

    def _get_evaluation_doc(self, tenant_id: str, evaluation_id: str) -> dict[str, Any]:
        doc = self._evaluations.find_by_id(tenant_id, evaluation_id)
        if doc is None:
            raise EvaluationNotFoundError(evaluation_id)
        return doc

    def get_or_none(self, tenant_id: str, evaluation_id: str) -> Decision | None:
        doc = self._decisions.find_by_evaluation_id(tenant_id, evaluation_id)
        return Decision.from_document(doc) if doc is not None else None

    def get(self, tenant_id: str, evaluation_id: str) -> Decision:
        decision = self.get_or_none(tenant_id, evaluation_id)
        if decision is None:
            raise DecisionNotFoundError(evaluation_id)
        return decision

    def _resolve_selection(
        self,
        tenant_id: str,
        evaluation_id: str,
        outcome: DecisionOutcome | None,
        selected_vendor_org_id: str | None,
        void_reason: str | None,
    ) -> tuple[str | None, str | None, str | None, str | None]:
        """Returns (selected_vendor_org_id, selected_proposal_id,
        selected_proposal_snapshot_id, void_reason) - proposal_id/snapshot_id
        are always server-derived from the vendor's current (vigente)
        Proposal snapshot, never accepted from the client (plan section 14
        readiness matrix)."""
        if outcome == "void":
            return None, None, None, void_reason
        if outcome == "selected":
            if selected_vendor_org_id is None:
                return None, None, None, None
            proposal_doc = self._proposals.find_one_by_evaluation_and_vendor(
                tenant_id, evaluation_id, selected_vendor_org_id
            )
            if proposal_doc is None:
                raise SelectedProposalNotFoundError(selected_vendor_org_id)
            proposal = Proposal.from_document(proposal_doc)
            if proposal.status != "submitted" or proposal.current_snapshot is None:
                raise SelectedProposalNotFoundError(selected_vendor_org_id)
            return (
                selected_vendor_org_id,
                proposal.id,
                proposal.current_snapshot.snapshot_id,
                None,
            )
        return None, None, None, None

    def _approval_readiness_reasons(self, decision: Decision) -> list[str]:
        reasons: list[str] = []
        if decision.outcome is None:
            reasons.append("an outcome (a selected vendor, or void) must be chosen")
        elif decision.outcome == "selected" and decision.selected_vendor_org_id is None:
            reasons.append("a vendor must be selected")
        elif decision.outcome == "void" and not decision.void_reason:
            reasons.append("a void_reason must be provided")
        if not decision.justification or len(decision.justification.strip()) < (
            _MIN_JUSTIFICATION_LENGTH
        ):
            reasons.append(f"justification must be at least {_MIN_JUSTIFICATION_LENGTH} characters")
        if decision.approver_membership_id is None:
            reasons.append("an approver must be assigned")
        return reasons

    def readiness(self, tenant_id: str, evaluation_id: str) -> dict[str, Any]:
        """Backend-authoritative, re-derived fresh on every call, never
        cached - same principle as evaluations.service.publication_readiness.
        `suggested_approver_membership_id` is informative only (plan
        Bloqueante #1 UX detail): the frontend may prefill a form with it,
        but nothing here ever writes it into Decision.approver_membership_id
        automatically."""
        evaluation_doc = self._get_evaluation_doc(tenant_id, evaluation_id)
        evaluation_completed = evaluation_doc["status"] == "completed"
        decision = self.get_or_none(tenant_id, evaluation_id)

        if not evaluation_completed:
            request_approval_reasons = ["evaluation must be completed before deciding"]
        elif decision is None:
            request_approval_reasons = ["a decision must be created first"]
        else:
            request_approval_reasons = self._approval_readiness_reasons(decision)

        can_edit = decision is not None and decision.status in ("not_requested", "rejected")
        return {
            "evaluation_completed": evaluation_completed,
            "decision_exists": decision is not None,
            "decision_status": decision.status if decision is not None else None,
            "can_create": evaluation_completed and decision is None,
            "can_edit": can_edit,
            "can_request_approval": (
                evaluation_completed and can_edit and not request_approval_reasons
            ),
            "request_approval_reasons": request_approval_reasons,
            "can_approve_or_reject": decision is not None and decision.status == "pending",
            "suggested_approver_membership_id": evaluation_doc.get("approver_membership_id"),
        }

    def create(self, tenant_id: str, evaluation_id: str, *, actor: ActorContext) -> Decision:
        evaluation_doc = self._get_evaluation_doc(tenant_id, evaluation_id)
        if evaluation_doc["status"] != "completed":
            raise EvaluationNotCompletedError(evaluation_id)
        if self._decisions.find_by_evaluation_id(tenant_id, evaluation_id) is not None:
            raise DecisionAlreadyExistsError(evaluation_id)

        decision = Decision.create(
            tenant_id=tenant_id,
            evaluation_id=evaluation_id,
            created_by_membership_id=actor.membership_id,
        )
        self._decisions.insert(tenant_id, decision.to_document())
        self._audit.record(
            tenant_id=tenant_id,
            actor=actor,
            action="decision_created",
            resource_type="decision",
            resource_id=decision.id,
            evaluation_id=evaluation_id,
            metadata={},
        )
        return decision

    def update_selection(
        self,
        tenant_id: str,
        evaluation_id: str,
        *,
        outcome: DecisionOutcome | None,
        selected_vendor_org_id: str | None,
        void_reason: str | None,
        justification: str | None,
        fields_set: set[str],
        actor: ActorContext,
    ) -> Decision:
        """`fields_set` (mirrors Pydantic's `exclude_unset`) distinguishes
        "field not provided" from "field explicitly cleared to None" - only
        provided fields override the current value before validating the
        resultant selection as one consistent unit (same "merge current with
        patch, then validate the resultant" principle as
        evaluations.models.validate_requirement_patch)."""
        decision = self.get(tenant_id, evaluation_id)
        if decision.status not in ("not_requested", "rejected"):
            raise InvalidDecisionStateError(evaluation_id)

        resultant_outcome = outcome if "outcome" in fields_set else decision.outcome
        resultant_vendor = (
            selected_vendor_org_id
            if "selected_vendor_org_id" in fields_set
            else decision.selected_vendor_org_id
        )
        resultant_void_reason = void_reason if "void_reason" in fields_set else decision.void_reason
        resultant_justification = (
            justification if "justification" in fields_set else decision.justification
        )

        vendor_org_id, proposal_id, snapshot_id, void_reason_resolved = self._resolve_selection(
            tenant_id, evaluation_id, resultant_outcome, resultant_vendor, resultant_void_reason
        )
        field_updates = {
            "outcome": resultant_outcome,
            "selected_vendor_org_id": vendor_org_id,
            "selected_proposal_id": proposal_id,
            "selected_proposal_snapshot_id": snapshot_id,
            "void_reason": void_reason_resolved,
            "justification": resultant_justification,
        }
        matched = self._decisions.update_selection(tenant_id, evaluation_id, field_updates)
        if not matched:
            raise InvalidDecisionStateError(evaluation_id)
        self._audit.record(
            tenant_id=tenant_id,
            actor=actor,
            action="decision_updated",
            resource_type="decision",
            resource_id=decision.id,
            evaluation_id=evaluation_id,
            metadata={"fields_changed": sorted(fields_set)},
        )
        return self.get(tenant_id, evaluation_id)

    def set_approver(
        self,
        tenant_id: str,
        evaluation_id: str,
        approver_membership_id: str,
        *,
        actor: ActorContext,
    ) -> Decision:
        decision = self.get(tenant_id, evaluation_id)
        if decision.status not in ("not_requested", "rejected"):
            raise InvalidDecisionStateError(evaluation_id)

        candidate = self._memberships.find_by_id_and_tenant(approver_membership_id, tenant_id)
        if candidate is None:
            raise ApproverMembershipNotFoundError(approver_membership_id)
        if candidate["role"] != "approver":
            raise ApproverRoleMismatchError(candidate["role"])
        if candidate["user_id"] == actor.user_id:
            raise SelfApprovalError(approver_membership_id)

        matched = self._decisions.set_approver(tenant_id, evaluation_id, approver_membership_id)
        if not matched:
            raise InvalidDecisionStateError(evaluation_id)
        self._audit.record(
            tenant_id=tenant_id,
            actor=actor,
            action="decision_approver_set",
            resource_type="decision",
            resource_id=decision.id,
            evaluation_id=evaluation_id,
            metadata={"approver_membership_id": approver_membership_id},
        )
        return self.get(tenant_id, evaluation_id)

    def request_approval(
        self, tenant_id: str, evaluation_id: str, *, actor: ActorContext
    ) -> Decision:
        decision = self.get(tenant_id, evaluation_id)
        if decision.status not in ("not_requested", "rejected"):
            raise InvalidDecisionStateError(evaluation_id)

        reasons = self._approval_readiness_reasons(decision)
        if reasons:
            raise DecisionPreconditionError("; ".join(reasons))

        now = datetime.now(UTC)
        matched = self._decisions.transition_status(
            tenant_id,
            evaluation_id,
            ("not_requested", "rejected"),
            "pending",
            {
                "approval_requested_at": now,
                "approval_requested_by_membership_id": actor.membership_id,
                "approval_decided_at": None,
                "approval_decided_by_membership_id": None,
                "approval_comment": None,
            },
        )
        if not matched:
            raise InvalidDecisionStateError(evaluation_id)
        self._audit.record(
            tenant_id=tenant_id,
            actor=actor,
            action="decision_approval_requested",
            resource_type="decision",
            resource_id=decision.id,
            evaluation_id=evaluation_id,
            metadata={"approver_membership_id": decision.approver_membership_id},
        )
        return self.get(tenant_id, evaluation_id)

    def withdraw_approval_request(
        self, tenant_id: str, evaluation_id: str, *, actor: ActorContext
    ) -> Decision:
        decision = self.get(tenant_id, evaluation_id)
        matched = self._decisions.transition_status(
            tenant_id, evaluation_id, ("pending",), "not_requested"
        )
        if not matched:
            raise InvalidDecisionStateError(evaluation_id)
        self._audit.record(
            tenant_id=tenant_id,
            actor=actor,
            action="decision_approval_withdrawn",
            resource_type="decision",
            resource_id=decision.id,
            evaluation_id=evaluation_id,
            metadata={},
        )
        return self.get(tenant_id, evaluation_id)

    def _assigned_approver_or_raise(self, decision: Decision, actor: ActorContext) -> None:
        if actor.membership_id != decision.approver_membership_id:
            raise NotAssignedApproverError(decision.id)

    def _build_snapshot(
        self, tenant_id: str, decision: Decision, *, actor: ActorContext
    ) -> DecisionSnapshot:
        # Every field below is guaranteed set by the time approve() reaches
        # this point: the readiness reasons checked by request_approval()
        # are a hard precondition of ever reaching "pending", and approve()
        # always writes approval_decided_at/_by together (see approve()).
        assert decision.outcome is not None
        assert decision.justification is not None
        assert decision.approver_membership_id is not None
        assert decision.approval_decided_at is not None
        assert decision.approval_decided_by_membership_id is not None

        vendor_name = None
        if decision.selected_vendor_org_id is not None:
            vendor_doc = self._vendor_orgs.find_by_id(tenant_id, decision.selected_vendor_org_id)
            vendor_name = vendor_doc["name"] if vendor_doc is not None else None

        results = self._scoring.get_results(tenant_id, decision.evaluation_id)

        return DecisionSnapshot(
            snapshot_id=decision.evaluation_id,
            tenant_id=tenant_id,
            evaluation_id=decision.evaluation_id,
            outcome=decision.outcome,
            selected_vendor_org_id=decision.selected_vendor_org_id,
            selected_vendor_org_name=vendor_name,
            selected_proposal_id=decision.selected_proposal_id,
            selected_proposal_snapshot_id=decision.selected_proposal_snapshot_id,
            void_reason=decision.void_reason,
            justification=decision.justification,
            approver_membership_id=decision.approver_membership_id,
            decided_at=decision.approval_decided_at,
            decided_by_membership_id=decision.approval_decided_by_membership_id,
            proposal_results=list(results["proposals"]),
            taken_at=datetime.now(UTC),
        )

    def _finish_approve(self, tenant_id: str, decision: Decision, *, actor: ActorContext) -> None:
        """Snapshot creation + decision_snapshot_id backfill + audit -
        deliberately NOT best-effort for the snapshot/backfill steps, unlike
        audit (same reasoning as evaluations.service._finish_publish). Both
        non-audit steps are individually idempotent, so a client retrying an
        identical approve() call after a timeout or crash always converges to
        exactly one snapshot and a consistent decision_snapshot_id,
        regardless of which step a prior attempt died at. The audit action is
        recorded here (not in approve()) so it only fires when this method
        actually runs - the full-success-retry short circuit in approve()
        returns before ever calling this, so a plain retry never double-logs."""
        snapshot = self._build_snapshot(tenant_id, decision, actor=actor)
        try:
            self._snapshots.insert(tenant_id, snapshot.to_document())
        except DuplicateKeyError:
            pass  # already recorded by a prior attempt - idempotent retry
        self._decisions.backfill_snapshot_id(
            tenant_id, decision.evaluation_id, snapshot.snapshot_id
        )
        self._audit.record(
            tenant_id=tenant_id,
            actor=actor,
            action="decision_approved",
            resource_type="decision",
            resource_id=decision.id,
            evaluation_id=decision.evaluation_id,
            snapshot_id=snapshot.snapshot_id,
            metadata={
                "outcome": decision.outcome,
                "selected_vendor_org_id": decision.selected_vendor_org_id,
            },
        )

    def approve(
        self, tenant_id: str, evaluation_id: str, comment: str | None, *, actor: ActorContext
    ) -> Decision:
        decision = self.get(tenant_id, evaluation_id)
        self._assigned_approver_or_raise(decision, actor)

        if decision.status == "approved":
            # Idempotent short-circuit (mirrors
            # evaluations.service.start_collection's "collecting_responses
            # already reached" branch): a full-success retry (snapshot
            # already recorded) is a no-op; a crash-recovery resume (status
            # transition committed, snapshot step never completed) picks up
            # exactly where it left off.
            if decision.decision_snapshot_id is not None:
                return decision
            self._finish_approve(tenant_id, decision, actor=actor)
            return self.get(tenant_id, evaluation_id)

        now = datetime.now(UTC)
        matched = self._decisions.transition_status(
            tenant_id,
            evaluation_id,
            ("pending",),
            "approved",
            {
                "approval_decided_at": now,
                "approval_decided_by_membership_id": actor.membership_id,
                "approval_comment": comment,
            },
        )
        if not matched:
            raise InvalidDecisionStateError(evaluation_id)

        decision = self.get(tenant_id, evaluation_id)
        self._finish_approve(tenant_id, decision, actor=actor)
        return self.get(tenant_id, evaluation_id)

    def reject(
        self, tenant_id: str, evaluation_id: str, comment: str, *, actor: ActorContext
    ) -> Decision:
        decision = self.get(tenant_id, evaluation_id)
        self._assigned_approver_or_raise(decision, actor)

        now = datetime.now(UTC)
        matched = self._decisions.transition_status(
            tenant_id,
            evaluation_id,
            ("pending",),
            "rejected",
            {
                "approval_decided_at": now,
                "approval_decided_by_membership_id": actor.membership_id,
                "approval_comment": comment,
            },
        )
        if not matched:
            raise InvalidDecisionStateError(evaluation_id)
        self._audit.record(
            tenant_id=tenant_id,
            actor=actor,
            action="decision_rejected",
            resource_type="decision",
            resource_id=decision.id,
            evaluation_id=evaluation_id,
            metadata={"has_comment": True},
        )
        return self.get(tenant_id, evaluation_id)

    def get_snapshot(self, tenant_id: str, evaluation_id: str) -> DecisionSnapshot:
        doc = self._snapshots.find_by_evaluation_id(tenant_id, evaluation_id)
        if doc is None:
            raise DecisionSnapshotNotFoundError(evaluation_id)
        return DecisionSnapshot.from_document(doc)
