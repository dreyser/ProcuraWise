from datetime import UTC, datetime
from typing import Any

from pymongo.errors import DuplicateKeyError

from procurawise.audit.service import AuditEventService
from procurawise.evaluations.exceptions import (
    ApprovalPreconditionError,
    ApproverMembershipNotFoundError,
    ApproverRoleMismatchError,
    EvaluationNotFoundError,
    InvalidTransitionError,
    NotAssignedApproverError,
    RequirementNotFoundError,
    SelfApprovalError,
    SnapshotNotFoundError,
    StartCollectionPreconditionError,
    VendorAlreadyLinkedError,
    VendorLimitExceededError,
    VendorNotLinkedError,
    VendorOrganizationNotFoundError,
)
from procurawise.evaluations.models import (
    DIMENSION_MAX_POINTS,
    Evaluation,
    EvaluationSnapshot,
    Requirement,
    validate_requirement_patch,
)
from procurawise.evaluations.repository import EvaluationRepository
from procurawise.evaluations.snapshot_repository import EvaluationSnapshotRepository
from procurawise.identity.repository import MembershipRepository, VendorOrganizationRepository
from procurawise.proposals.models import Proposal
from procurawise.proposals.repository import ProposalRepository
from procurawise.shared.context import ActorContext

_WEIGHT_TOLERANCE = 1e-6


class EvaluationService:
    def __init__(
        self,
        evaluations: EvaluationRepository,
        proposals: ProposalRepository,
        vendor_orgs: VendorOrganizationRepository,
        memberships: MembershipRepository,
        snapshots: EvaluationSnapshotRepository,
        audit: AuditEventService,
    ) -> None:
        self._evaluations = evaluations
        self._proposals = proposals
        self._vendor_orgs = vendor_orgs
        self._memberships = memberships
        self._snapshots = snapshots
        self._audit = audit

    def create_evaluation(
        self,
        tenant_id: str,
        membership_id: str,
        name: str,
        description: str,
        *,
        actor: ActorContext,
    ) -> Evaluation:
        evaluation = Evaluation.create(
            tenant_id=tenant_id,
            name=name,
            description=description,
            created_by_membership_id=membership_id,
        )
        self._evaluations.insert(tenant_id, evaluation.to_document())
        self._audit.record(
            tenant_id=tenant_id,
            actor=actor,
            action="evaluation_created",
            resource_type="evaluation",
            resource_id=evaluation.id,
            evaluation_id=evaluation.id,
            metadata={"name": name},
        )
        return evaluation

    def get_evaluation(self, tenant_id: str, evaluation_id: str) -> Evaluation:
        doc = self._evaluations.find_by_id(tenant_id, evaluation_id)
        if doc is None:
            raise EvaluationNotFoundError(evaluation_id)
        return Evaluation.from_document(doc)

    def list_evaluations(self, tenant_id: str) -> list[Evaluation]:
        return [Evaluation.from_document(doc) for doc in self._evaluations.find_many(tenant_id)]

    def update_evaluation(
        self,
        tenant_id: str,
        evaluation_id: str,
        name: str | None,
        description: str | None,
        response_deadline: datetime | None = None,
        base_currency: str | None = None,
        tco_horizon_years: int | None = None,
        *,
        actor: ActorContext,
    ) -> Evaluation:
        evaluation = self.get_evaluation(tenant_id, evaluation_id)
        updates: dict[str, Any] = {}
        if name is not None:
            updates["name"] = name
        if description is not None:
            updates["description"] = description
        if response_deadline is not None:
            updates["response_deadline"] = response_deadline
        if base_currency is not None:
            updates["base_currency"] = base_currency
        if tco_horizon_years is not None:
            updates["tco_horizon_years"] = tco_horizon_years
        fields_changed = sorted(updates.keys())
        updates.update(evaluation.approval_invalidation_extra_set())
        matched = self._evaluations.update_metadata(tenant_id, evaluation_id, updates)
        self._require_matched(matched, tenant_id, evaluation_id)
        self._audit.record(
            tenant_id=tenant_id,
            actor=actor,
            action="evaluation_updated",
            resource_type="evaluation",
            resource_id=evaluation_id,
            evaluation_id=evaluation_id,
            metadata={"fields_changed": fields_changed},
        )
        return self.get_evaluation(tenant_id, evaluation_id)

    def add_requirement(
        self,
        tenant_id: str,
        evaluation_id: str,
        *,
        dimension: str,
        category: str,
        title: str,
        description: str,
        priority: str,
        response_type: str,
        weight: float,
        required: bool,
        display_order: int,
        buyer_guidance: str | None,
        options: list[str] | None,
        actor: ActorContext,
    ) -> Requirement:
        evaluation = self.get_evaluation(tenant_id, evaluation_id)
        requirement = Requirement.create(
            dimension=dimension,  # type: ignore[arg-type]
            category=category,
            title=title,
            description=description,
            priority=priority,  # type: ignore[arg-type]
            response_type=response_type,  # type: ignore[arg-type]
            weight=weight,
            required=required,
            display_order=display_order,
            buyer_guidance=buyer_guidance,
            options=options,
        )
        matched = self._evaluations.add_requirement(
            tenant_id,
            evaluation_id,
            requirement.to_document(),
            evaluation.approval_invalidation_extra_set(),
        )
        self._require_draft_matched(matched, tenant_id, evaluation_id)
        self._audit.record(
            tenant_id=tenant_id,
            actor=actor,
            action="requirement_added",
            resource_type="requirement",
            resource_id=requirement.id,
            evaluation_id=evaluation_id,
            metadata={"requirement_id": requirement.id},
        )
        return requirement

    def update_requirement(
        self,
        tenant_id: str,
        evaluation_id: str,
        requirement_id: str,
        field_updates: dict,
        *,
        actor: ActorContext,
    ) -> Requirement:
        evaluation = self.get_evaluation(tenant_id, evaluation_id)
        if evaluation.status != "draft":
            raise InvalidTransitionError(evaluation_id)

        current = next((r for r in evaluation.requirements if r.id == requirement_id), None)
        if current is None:
            raise RequirementNotFoundError(requirement_id)

        validate_requirement_patch(current, field_updates)

        matched = self._evaluations.update_requirement(
            tenant_id,
            evaluation_id,
            requirement_id,
            field_updates,
            evaluation.approval_invalidation_extra_set(),
        )
        if not matched:
            # draft status and requirement existence were already confirmed
            # above; only a concurrent transition away from draft between
            # that read and this write can still land here.
            raise InvalidTransitionError(evaluation_id)

        self._audit.record(
            tenant_id=tenant_id,
            actor=actor,
            action="requirement_updated",
            resource_type="requirement",
            resource_id=requirement_id,
            evaluation_id=evaluation_id,
            metadata={
                "requirement_id": requirement_id,
                "fields_changed": sorted(field_updates.keys()),
            },
        )

        evaluation = self.get_evaluation(tenant_id, evaluation_id)
        for requirement in evaluation.requirements:
            if requirement.id == requirement_id:
                return requirement
        raise RequirementNotFoundError(requirement_id)

    def delete_requirement(
        self, tenant_id: str, evaluation_id: str, requirement_id: str, *, actor: ActorContext
    ) -> None:
        evaluation = self.get_evaluation(tenant_id, evaluation_id)
        if evaluation.status != "draft":
            raise InvalidTransitionError(evaluation_id)
        if not any(r.id == requirement_id for r in evaluation.requirements):
            raise RequirementNotFoundError(requirement_id)
        self._evaluations.delete_requirement(
            tenant_id,
            evaluation_id,
            requirement_id,
            evaluation.approval_invalidation_extra_set(),
        )
        self._audit.record(
            tenant_id=tenant_id,
            actor=actor,
            action="requirement_deleted",
            resource_type="requirement",
            resource_id=requirement_id,
            evaluation_id=evaluation_id,
            metadata={"requirement_id": requirement_id},
        )

    def link_vendor(
        self, tenant_id: str, evaluation_id: str, vendor_org_id: str, *, actor: ActorContext
    ) -> Proposal:
        evaluation = self.get_evaluation(tenant_id, evaluation_id)
        invalidation = evaluation.approval_invalidation_extra_set()
        outcome = self._evaluations.reserve_vendor_slot(tenant_id, evaluation_id, invalidation)
        if outcome == "not_found":
            raise EvaluationNotFoundError(evaluation_id)
        if outcome == "not_draft":
            raise InvalidTransitionError(evaluation_id)
        if outcome == "limit_reached":
            raise VendorLimitExceededError(evaluation_id)

        vendor_org_doc = self._vendor_orgs.find_by_id(tenant_id, vendor_org_id)
        if vendor_org_doc is None:
            self._evaluations.release_vendor_slot(tenant_id, evaluation_id)
            raise VendorOrganizationNotFoundError(vendor_org_id)

        proposal = Proposal.create(
            tenant_id=tenant_id, evaluation_id=evaluation_id, vendor_org_id=vendor_org_id
        )
        try:
            self._proposals.insert(tenant_id, proposal.to_document())
        except DuplicateKeyError:
            self._evaluations.release_vendor_slot(tenant_id, evaluation_id)
            raise VendorAlreadyLinkedError(vendor_org_id) from None
        except Exception:
            self._evaluations.release_vendor_slot(tenant_id, evaluation_id)
            raise
        self._audit.record(
            tenant_id=tenant_id,
            actor=actor,
            action="vendor_linked",
            resource_type="proposal",
            resource_id=proposal.id,
            evaluation_id=evaluation_id,
            proposal_id=proposal.id,
            metadata={"vendor_org_id": vendor_org_id},
        )
        return proposal

    def unlink_vendor(
        self, tenant_id: str, evaluation_id: str, vendor_org_id: str, *, actor: ActorContext
    ) -> None:
        proposal_doc = self._proposals.find_one_by_evaluation_and_vendor(
            tenant_id, evaluation_id, vendor_org_id
        )
        if proposal_doc is None:
            raise VendorNotLinkedError(vendor_org_id)
        deleted = self._proposals.delete(tenant_id, proposal_doc["_id"])
        if not deleted:
            raise InvalidTransitionError(evaluation_id)
        # Non-raising lookup (unlike get_evaluation): this router doesn't
        # catch EvaluationNotFoundError, and a missing evaluation here would
        # already have failed the proposal lookup above - this is purely to
        # compute the invalidation extra_set, not a precondition gate.
        evaluation_doc = self._evaluations.find_by_id(tenant_id, evaluation_id)
        invalidation = (
            Evaluation.from_document(evaluation_doc).approval_invalidation_extra_set()
            if evaluation_doc is not None
            else {}
        )
        self._evaluations.release_vendor_slot(tenant_id, evaluation_id, invalidation)
        self._audit.record(
            tenant_id=tenant_id,
            actor=actor,
            action="vendor_unlinked",
            resource_type="proposal",
            resource_id=proposal_doc["_id"],
            evaluation_id=evaluation_id,
            proposal_id=proposal_doc["_id"],
            metadata={"vendor_org_id": vendor_org_id},
        )

    def _draft_readiness_reasons(self, evaluation: Evaluation) -> list[str]:
        """Weight-completeness + vendor-linked preconditions (plan §16
        "draft readiness") - the same rules start_collection enforces,
        factored out so request_approval and the publication-readiness
        endpoint share one source of truth rather than re-deriving it."""
        reasons: list[str] = []
        by_dimension: dict[str, float] = {"functional": 0.0, "technical": 0.0}
        for requirement in evaluation.requirements:
            by_dimension[requirement.dimension] = (
                by_dimension.get(requirement.dimension, 0.0) + requirement.weight
            )
        if by_dimension["functional"] == 0.0 or by_dimension["technical"] == 0.0:
            reasons.append("at least one functional and one technical requirement are required")
        else:
            for dimension, max_points in DIMENSION_MAX_POINTS.items():
                if abs(by_dimension[dimension] - max_points) > _WEIGHT_TOLERANCE:
                    reasons.append(
                        f"{dimension} requirement weights must sum to {max_points}, got "
                        f"{by_dimension[dimension]}"
                    )
        if evaluation.linked_vendor_count == 0:
            reasons.append("at least one vendor must be linked")
        return reasons

    def _approval_readiness_reasons(self, evaluation: Evaluation) -> list[str]:
        """Plan §16 "approval readiness" = draft readiness + approver +
        response_deadline."""
        reasons = self._draft_readiness_reasons(evaluation)
        if evaluation.approver_membership_id is None:
            reasons.append("an approver must be assigned")
        if evaluation.response_deadline is None:
            reasons.append("a response deadline must be set")
        return reasons

    def publication_readiness(self, tenant_id: str, evaluation_id: str) -> dict[str, Any]:
        """Backend-authoritative readiness (plan §16) - the frontend's
        evaluationReadiness.ts is a client-side preview only; this is the
        real source of truth, re-derived fresh on every call, never cached."""
        evaluation = self.get_evaluation(tenant_id, evaluation_id)
        approval_reasons = self._approval_readiness_reasons(evaluation)
        publish_reasons = list(approval_reasons)
        if evaluation.approval_status != "approved":
            publish_reasons.append("evaluation must be approved before publication")
        return {
            "can_request_approval": not approval_reasons,
            "request_approval_reasons": approval_reasons,
            "can_publish": not publish_reasons,
            "publish_reasons": publish_reasons,
            "approval_status": evaluation.approval_status,
            "approver_membership_id": evaluation.approver_membership_id,
            "response_deadline": evaluation.response_deadline,
        }

    def set_approver(
        self,
        tenant_id: str,
        evaluation_id: str,
        approver_membership_id: str,
        *,
        actor: ActorContext,
    ) -> Evaluation:
        evaluation = self.get_evaluation(tenant_id, evaluation_id)
        if evaluation.status != "draft" or evaluation.approval_status not in (
            "not_requested",
            "rejected",
        ):
            raise InvalidTransitionError(evaluation_id)

        candidate = self._memberships.find_by_id_and_tenant(approver_membership_id, tenant_id)
        if candidate is None:
            raise ApproverMembershipNotFoundError(approver_membership_id)
        if candidate["role"] != "approver":
            raise ApproverRoleMismatchError(candidate["role"])

        creator = self._memberships.find_by_id_and_tenant(
            evaluation.created_by_membership_id, tenant_id
        )
        if creator is not None and candidate["user_id"] == creator["user_id"]:
            raise SelfApprovalError(approver_membership_id)

        matched = self._evaluations.set_approver(tenant_id, evaluation_id, approver_membership_id)
        self._require_matched(matched, tenant_id, evaluation_id)
        self._audit.record(
            tenant_id=tenant_id,
            actor=actor,
            action="evaluation_approver_set",
            resource_type="evaluation",
            resource_id=evaluation_id,
            evaluation_id=evaluation_id,
            metadata={"approver_membership_id": approver_membership_id},
        )
        return self.get_evaluation(tenant_id, evaluation_id)

    def request_approval(
        self, tenant_id: str, evaluation_id: str, *, actor: ActorContext
    ) -> Evaluation:
        evaluation = self.get_evaluation(tenant_id, evaluation_id)
        if evaluation.status != "draft":
            raise InvalidTransitionError(evaluation_id)

        reasons = self._approval_readiness_reasons(evaluation)
        if reasons:
            raise ApprovalPreconditionError("; ".join(reasons))

        now = datetime.now(UTC)
        matched = self._evaluations.transition_approval_status(
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
            raise InvalidTransitionError(evaluation_id)
        self._audit.record(
            tenant_id=tenant_id,
            actor=actor,
            action="evaluation_approval_requested",
            resource_type="evaluation",
            resource_id=evaluation_id,
            evaluation_id=evaluation_id,
            metadata={
                "approver_membership_id": evaluation.approver_membership_id,
                "response_deadline": (
                    evaluation.response_deadline.isoformat()
                    if evaluation.response_deadline
                    else None
                ),
            },
        )
        return self.get_evaluation(tenant_id, evaluation_id)

    def withdraw_approval_request(
        self, tenant_id: str, evaluation_id: str, *, actor: ActorContext
    ) -> Evaluation:
        matched = self._evaluations.transition_approval_status(
            tenant_id, evaluation_id, ("pending",), "not_requested"
        )
        self._require_matched(matched, tenant_id, evaluation_id)
        self._audit.record(
            tenant_id=tenant_id,
            actor=actor,
            action="evaluation_approval_withdrawn",
            resource_type="evaluation",
            resource_id=evaluation_id,
            evaluation_id=evaluation_id,
            metadata={},
        )
        return self.get_evaluation(tenant_id, evaluation_id)

    def _assigned_approver_or_raise(self, evaluation: Evaluation, actor: ActorContext) -> None:
        if actor.membership_id != evaluation.approver_membership_id:
            raise NotAssignedApproverError(evaluation.id)

    def approve(
        self, tenant_id: str, evaluation_id: str, comment: str | None, *, actor: ActorContext
    ) -> Evaluation:
        evaluation = self.get_evaluation(tenant_id, evaluation_id)
        self._assigned_approver_or_raise(evaluation, actor)

        now = datetime.now(UTC)
        matched = self._evaluations.transition_approval_status(
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
            raise InvalidTransitionError(evaluation_id)
        self._audit.record(
            tenant_id=tenant_id,
            actor=actor,
            action="evaluation_approved",
            resource_type="evaluation",
            resource_id=evaluation_id,
            evaluation_id=evaluation_id,
            metadata={"has_comment": comment is not None},
        )
        return self.get_evaluation(tenant_id, evaluation_id)

    def reject(
        self, tenant_id: str, evaluation_id: str, comment: str, *, actor: ActorContext
    ) -> Evaluation:
        evaluation = self.get_evaluation(tenant_id, evaluation_id)
        self._assigned_approver_or_raise(evaluation, actor)

        now = datetime.now(UTC)
        matched = self._evaluations.transition_approval_status(
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
            raise InvalidTransitionError(evaluation_id)
        self._audit.record(
            tenant_id=tenant_id,
            actor=actor,
            action="evaluation_rejected",
            resource_type="evaluation",
            resource_id=evaluation_id,
            evaluation_id=evaluation_id,
            metadata={"has_comment": True},
        )
        return self.get_evaluation(tenant_id, evaluation_id)

    def _build_snapshot(
        self, tenant_id: str, evaluation: Evaluation, *, actor: ActorContext
    ) -> EvaluationSnapshot:
        """Reads the now-permanently-frozen evaluation (every draft-gated
        mutation is blocked once status != draft) and the Proposals linking
        it to vendors - Proposal is the sole Evaluation<->VendorOrganization
        association (evaluations.models.Evaluation docstring), there is no
        separate evaluation_vendors list to read. Vendor org names are
        copied verbatim (mutable, not versioned elsewhere), matching
        ProposalSnapshot.vendor_org_name's precedent (plan §21)."""
        proposal_docs = self._proposals.find_by_evaluation(tenant_id, evaluation.id)
        vendor_org_ids = [doc["vendor_org_id"] for doc in proposal_docs]
        vendor_org_names: dict[str, str] = {}
        for vendor_org_id in vendor_org_ids:
            vendor_doc = self._vendor_orgs.find_by_id(tenant_id, vendor_org_id)
            if vendor_doc is not None:
                vendor_org_names[vendor_org_id] = vendor_doc["name"]

        # Every field below is guaranteed set by the time publish reaches
        # this point: approval_status == "approved" is a hard publish
        # precondition, and approve() always writes approver_membership_id
        # (via set_approver, a prerequisite of request_approval),
        # approval_requested_at/_by, and approval_decided_at/_by together.
        assert evaluation.approver_membership_id is not None
        assert evaluation.response_deadline is not None
        assert evaluation.approval_requested_at is not None
        assert evaluation.approval_requested_by_membership_id is not None
        assert evaluation.approval_decided_at is not None
        assert evaluation.approval_decided_by_membership_id is not None

        now = datetime.now(UTC)
        return EvaluationSnapshot(
            snapshot_id=evaluation.id,
            tenant_id=tenant_id,
            evaluation_id=evaluation.id,
            taken_at=now,
            evaluation_name=evaluation.name,
            evaluation_description=evaluation.description,
            requirements=list(evaluation.requirements),
            dimension_weights={str(k): v for k, v in DIMENSION_MAX_POINTS.items()},
            linked_vendor_org_ids=vendor_org_ids,
            vendor_org_names=vendor_org_names,
            response_deadline=evaluation.response_deadline,
            approver_membership_id=evaluation.approver_membership_id,
            approval_requested_at=evaluation.approval_requested_at,
            approval_requested_by_membership_id=evaluation.approval_requested_by_membership_id,
            approval_decided_at=evaluation.approval_decided_at,
            approval_decided_by_membership_id=evaluation.approval_decided_by_membership_id,
            approval_comment=evaluation.approval_comment,
            published_by_membership_id=actor.membership_id,
            published_at=now,
        )

    def _finish_publish(
        self, tenant_id: str, evaluation: Evaluation, *, actor: ActorContext
    ) -> None:
        """Snapshot creation + approval_snapshot_id backfill (plan §22 steps
        3-5) - deliberately NOT best-effort, unlike audit. Both steps are
        individually idempotent: snapshot_id is deterministic
        (== evaluation_id, safe because EvaluationStatus never regresses to
        draft, so at most one snapshot can ever exist), and the backfill's
        filter is conditioned on approval_snapshot_id being unset. A client
        retrying the identical publish call after a timeout or crash always
        converges to exactly one snapshot and a consistent
        approval_snapshot_id, regardless of which step the prior attempt
        died at."""
        snapshot = self._build_snapshot(tenant_id, evaluation, actor=actor)
        try:
            self._snapshots.insert(tenant_id, snapshot.to_document())
        except DuplicateKeyError:
            pass  # already recorded by a prior attempt - idempotent retry

        self._evaluations.backfill_approval_snapshot_id(
            tenant_id, evaluation.id, snapshot.snapshot_id
        )

        self._audit.record(
            tenant_id=tenant_id,
            actor=actor,
            action="evaluation_published",
            resource_type="evaluation",
            resource_id=evaluation.id,
            evaluation_id=evaluation.id,
            snapshot_id=snapshot.snapshot_id,
            metadata={
                "approver_membership_id": evaluation.approver_membership_id,
                "response_deadline": (
                    evaluation.response_deadline.isoformat()
                    if evaluation.response_deadline
                    else None
                ),
                "requirement_count": len(evaluation.requirements),
                "linked_vendor_count": evaluation.linked_vendor_count,
            },
        )

    def start_collection(
        self, tenant_id: str, evaluation_id: str, *, actor: ActorContext
    ) -> Evaluation:
        """This IS "publish" (founder decision, plan §9.B) - approve() and
        start_collection() are deliberately separate actions. See plan §22
        for the full failure-mode analysis behind this exact sequencing."""
        evaluation = self.get_evaluation(tenant_id, evaluation_id)

        if evaluation.status == "collecting_responses":
            # Idempotent short-circuit (plan §22 step 1): a full-success
            # retry (snapshot already recorded) is a no-op; a crash-recovery
            # resume (status transition committed, snapshot step never
            # completed) picks up exactly where it left off.
            if evaluation.approval_snapshot_id is not None:
                return evaluation
            self._finish_publish(tenant_id, evaluation, actor=actor)
            return self.get_evaluation(tenant_id, evaluation_id)

        if evaluation.status != "draft":
            raise InvalidTransitionError(evaluation_id)

        reasons = self._draft_readiness_reasons(evaluation)
        if evaluation.approval_status != "approved":
            reasons.append("evaluation must be approved before publication")
        if reasons:
            raise StartCollectionPreconditionError("; ".join(reasons))

        # Commit point (plan §22 step 2): flips status BEFORE the snapshot
        # is taken, not after - unlike ProposalRepository.submit (one
        # collection, one atomic write does both), this needs two writes
        # across two collections, and flipping status first closes the
        # window during which a draft-gated mutation could otherwise still
        # land and invalidate a not-yet-taken snapshot. No new filter
        # fields: the approval gate is the Python precondition check above,
        # not baked into the Mongo filter, so a legitimate retry behaves
        # identically to a first attempt.
        matched = self._evaluations.transition_status(
            tenant_id,
            evaluation_id,
            "draft",
            "collecting_responses",
            {"collecting_responses_started_at": datetime.now(UTC)},
        )
        if not matched:
            raise InvalidTransitionError(evaluation_id)
        self._audit.record(
            tenant_id=tenant_id,
            actor=actor,
            action="evaluation_collection_started",
            resource_type="evaluation",
            resource_id=evaluation_id,
            evaluation_id=evaluation_id,
            metadata={"from_status": "draft", "to_status": "collecting_responses"},
        )

        evaluation = self.get_evaluation(tenant_id, evaluation_id)
        self._finish_publish(tenant_id, evaluation, actor=actor)
        return self.get_evaluation(tenant_id, evaluation_id)

    def get_snapshot(self, tenant_id: str, evaluation_id: str) -> EvaluationSnapshot:
        doc = self._snapshots.find_by_evaluation_id(tenant_id, evaluation_id)
        if doc is None:
            raise SnapshotNotFoundError(evaluation_id)
        return EvaluationSnapshot.from_document(doc)

    def start_evaluation(
        self, tenant_id: str, evaluation_id: str, *, actor: ActorContext
    ) -> Evaluation:
        matched = self._evaluations.transition_status(
            tenant_id,
            evaluation_id,
            "collecting_responses",
            "evaluating",
            {"evaluating_started_at": datetime.now(UTC)},
        )
        self._require_matched(matched, tenant_id, evaluation_id)
        self._audit.record(
            tenant_id=tenant_id,
            actor=actor,
            action="evaluation_scoring_started",
            resource_type="evaluation",
            resource_id=evaluation_id,
            evaluation_id=evaluation_id,
            metadata={"from_status": "collecting_responses", "to_status": "evaluating"},
        )
        return self.get_evaluation(tenant_id, evaluation_id)

    def _require_matched(self, matched: bool, tenant_id: str, evaluation_id: str) -> None:
        if matched:
            return
        evaluation_doc = self._evaluations.find_by_id(tenant_id, evaluation_id)
        if evaluation_doc is None:
            raise EvaluationNotFoundError(evaluation_id)
        raise InvalidTransitionError(evaluation_id)

    def _require_draft_matched(self, matched: bool, tenant_id: str, evaluation_id: str) -> None:
        self._require_matched(matched, tenant_id, evaluation_id)
