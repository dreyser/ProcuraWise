from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

EvaluationStatus = Literal["draft", "collecting_responses", "evaluating", "completed"]

# Fase 12: gates the existing draft -> collecting_responses transition
# (EvaluationStatus itself is unchanged - founder decision, plan §9.A).
# `rejected` is not terminal: request_approval is valid from both
# not_requested and rejected, looping back to pending (plan §14/§15).
ApprovalStatus = Literal["not_requested", "pending", "approved", "rejected"]

Dimension = Literal["functional", "technical", "economic"]
# Fase 20: Requirement authoring is intentionally narrower than the general
# Dimension - a Requirement can never be "economic" (economic assessment has
# no Requirement rows at all, see scoring.models.EconomicAssessment). Defense
# in depth at the type level, not just a runtime check.
RequirementDimension = Literal["functional", "technical"]
Priority = Literal["mandatory", "important", "desirable"]
ResponseType = Literal[
    "compliant_status",
    "text",
    "single_choice",
    "multi_choice",
    "number",
    "percentage",
    "date",
    "url",
    "comment",
    "currency",
]

# Global product weights (PRD §7.1): functional 40%, technical 20%, economic 40%
# of a 100-point model. VS-2B only implements functional+technical - requirement
# weights within a dimension are expressed directly on this global scale (they
# must sum to exactly the dimension's allocation), not renormalized to 100 each.
#
# Fase 20 deliberately does NOT add an "economic" key here: economic scoring
# has no Requirement rows at all (it's a fixed 10-criterion rubric, see
# EconomicAssessment in scoring/models.py), so nothing should ever validate a
# sum of Requirement weights for it. ECONOMIC_MAX_POINTS stays a separate
# constant for exactly that reason - see evaluations.service._draft_readiness_
# reasons, which iterates DIMENSION_MAX_POINTS.items() to validate Requirement
# weight sums and must never be asked to do that for "economic".
DIMENSION_MAX_POINTS: dict[Dimension, float] = {"functional": 40.0, "technical": 20.0}
ECONOMIC_MAX_POINTS = 40.0
PARTIAL_RESULT_MAX_POINTS = sum(DIMENSION_MAX_POINTS.values())  # 60 - functional+technical only

MAX_LINKED_VENDORS = 6

# Fase 20 (ADR 0009): default sub-weights for the two human-scored economic
# rubrics, within their own 15%/15% slice of the 40% economic dimension - the
# founder confirmed these criteria (the dict keys) are fixed across every
# evaluation; only the numeric weights are owner-editable before publish
# (plan §9 Pregunta Bloqueante #1, Opción 1). Each group must sum to 100.0.
DEFAULT_COMMERCIAL_WEIGHTS: dict[str, float] = {
    "payment_terms": 25.0,
    "price_protection": 25.0,
    "contractual_flexibility": 20.0,
    "discounts_incentives": 15.0,
    "billing_transparency": 15.0,
}
DEFAULT_RISK_WEIGHTS: dict[str, float] = {
    "variable_cost_exposure": 30.0,
    "increases_indexation": 25.0,
    "assumptions_exclusions": 20.0,
    "fx_fiscal_regulatory": 15.0,
    "exit_portability_lockin": 10.0,
}


@dataclass(frozen=True)
class EconomicCriteriaWeights:
    """Fase 20 (ADR 0009) - the owner-configurable weights for the two
    fixed-criteria economic rubrics. `commercial`/`risk` always carry exactly
    the same 5 keys as DEFAULT_COMMERCIAL_WEIGHTS/DEFAULT_RISK_WEIGHTS (no
    endpoint exists to add/remove/rename a criterion); each dict's values
    must sum to 100.0, validated in evaluations.service before a write, never
    in this dataclass itself (same "validation lives in the service, not the
    model" convention as the rest of this module)."""

    commercial: dict[str, float]
    risk: dict[str, float]

    @staticmethod
    def defaults() -> "EconomicCriteriaWeights":
        return EconomicCriteriaWeights(
            commercial=dict(DEFAULT_COMMERCIAL_WEIGHTS), risk=dict(DEFAULT_RISK_WEIGHTS)
        )

    def to_document(self) -> dict[str, Any]:
        return {"commercial": dict(self.commercial), "risk": dict(self.risk)}

    @staticmethod
    def from_document(doc: dict[str, Any] | None) -> "EconomicCriteriaWeights":
        if doc is None:
            return EconomicCriteriaWeights.defaults()
        return EconomicCriteriaWeights(commercial=dict(doc["commercial"]), risk=dict(doc["risk"]))


def new_id() -> str:
    return uuid4().hex


@dataclass(frozen=True)
class Requirement:
    """Embedded in Evaluation.requirements. `required` (must the vendor answer
    before submit) is independent of `priority == "mandatory"` (generates a
    non-blocking alert in results when scored low) - two distinct concepts
    from PRD §6.3, not one field wearing two hats."""

    id: str
    dimension: RequirementDimension
    category: str
    title: str
    description: str
    priority: Priority
    response_type: ResponseType
    weight: float
    required: bool
    buyer_guidance: str | None
    display_order: int
    options: list[str] | None
    created_at: datetime
    updated_at: datetime

    @staticmethod
    def create(
        dimension: RequirementDimension,
        category: str,
        title: str,
        description: str,
        priority: Priority,
        response_type: ResponseType,
        weight: float,
        required: bool,
        display_order: int,
        buyer_guidance: str | None = None,
        options: list[str] | None = None,
    ) -> "Requirement":
        if response_type in ("single_choice", "multi_choice") and not options:
            raise ValueError(f"response_type={response_type!r} requires non-empty options")
        now = datetime.now(UTC)
        return Requirement(
            id=new_id(),
            dimension=dimension,
            category=category,
            title=title,
            description=description,
            priority=priority,
            response_type=response_type,
            weight=weight,
            required=required,
            buyer_guidance=buyer_guidance,
            display_order=display_order,
            options=options,
            created_at=now,
            updated_at=now,
        )

    def to_document(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "dimension": self.dimension,
            "category": self.category,
            "title": self.title,
            "description": self.description,
            "priority": self.priority,
            "response_type": self.response_type,
            "weight": self.weight,
            "required": self.required,
            "buyer_guidance": self.buyer_guidance,
            "display_order": self.display_order,
            "options": self.options,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @staticmethod
    def from_document(doc: dict[str, Any]) -> "Requirement":
        return Requirement(
            id=doc["id"],
            dimension=doc["dimension"],
            category=doc["category"],
            title=doc["title"],
            description=doc["description"],
            priority=doc["priority"],
            response_type=doc["response_type"],
            weight=doc["weight"],
            required=doc["required"],
            buyer_guidance=doc.get("buyer_guidance"),
            display_order=doc["display_order"],
            options=doc.get("options"),
            created_at=doc["created_at"],
            updated_at=doc["updated_at"],
        )


def validate_requirement_patch(current: Requirement, field_updates: dict[str, Any]) -> None:
    """Validate the *resultant* requirement (current fields merged with this
    patch), not just the fields the patch happens to touch - otherwise a
    patch could leave single_choice/multi_choice without options, a state
    `Requirement.create` already refuses to produce. Shared by
    evaluations.service.update_requirement and knowledge_templates.service's
    equivalent item-patch method (Fase 11) so the rule cannot drift between
    the two call sites."""
    resultant_response_type = field_updates.get("response_type", current.response_type)
    resultant_options = field_updates["options"] if "options" in field_updates else current.options
    if resultant_response_type in ("single_choice", "multi_choice") and not resultant_options:
        raise ValueError(f"response_type={resultant_response_type!r} requires non-empty options")


# Fase 12: approval_status values a successful draft-gated edit invalidates
# (plan §14/§32 Blocker 3): editing while "pending" or "approved" forces a
# fresh, honest approval cycle rather than letting an approver's decision go
# stale without notice. "not_requested"/"rejected" already require a fresh
# request_approval call, so editing in those states is a no-op here.
INVALIDATED_BY_APPROVAL_EDIT: tuple[str, ...] = ("pending", "approved")


@dataclass(frozen=True)
class Evaluation:
    """`linked_vendor_count` is an atomic reservation counter (see
    evaluations.repository.reserve_vendor_slot) enforcing the 6-vendor cap
    under concurrent linking - it is not derived by counting Proposal
    documents on every read. `Proposal` is the sole representation of the
    Evaluation<->VendorOrganization association; there is no separate
    evaluation_vendors collection."""

    id: str
    tenant_id: str
    name: str
    description: str
    status: EvaluationStatus
    requirements: list[Requirement]
    linked_vendor_count: int
    created_by_membership_id: str
    created_at: datetime
    updated_at: datetime
    collecting_responses_started_at: datetime | None
    evaluating_started_at: datetime | None
    completed_at: datetime | None
    # Fase 12 (plan §23) - approval_status only meaningful while status ==
    # "draft"; gates the draft -> collecting_responses transition. See
    # evaluations.service for the transitions that mutate these fields -
    # nothing outside EvaluationRepository.transition_approval_status /
    # set_approver / request_approval / etc. writes them directly.
    approval_status: ApprovalStatus
    approver_membership_id: str | None
    response_deadline: datetime | None
    approval_requested_at: datetime | None
    approval_requested_by_membership_id: str | None
    approval_decided_at: datetime | None
    approval_decided_by_membership_id: str | None
    approval_comment: str | None
    approval_snapshot_id: str | None
    # ADR 0026 (R2, UAT-06/07/08): an optional review stage ahead of the
    # approver decision above. Reuses the same ApprovalStatus type and the
    # same "Membership designated per-evaluation" shape as approver_
    # fields - a Reviewer is not a new Role, it's an internal_collaborator
    # Membership designated as this evaluation's reviewer. None/
    # "not_requested" for every evaluation that never assigns a reviewer -
    # for those, the approval flow is byte-for-byte identical to before ADR
    # 0026 (no reviewer means no review gate, see
    # EvaluationService._approval_readiness_reasons).
    reviewer_membership_id: str | None
    review_status: ApprovalStatus
    review_requested_at: datetime | None
    review_requested_by_membership_id: str | None
    review_decided_at: datetime | None
    review_decided_by_membership_id: str | None
    review_comment: str | None
    # Fase 19 (ADR 0008, plan §9 R9): TCO config lives on the Evaluation
    # (like weights/response_deadline), not per-Proposal - every vendor's
    # CostItems are compared against the same base currency/horizon.
    # Defaulted (never backfilled) so evaluations persisted before Fase 19
    # deserialize safely - see from_document.
    base_currency: str
    tco_horizon_years: int
    # Fase 20 (ADR 0009): owner-editable before publish, frozen into
    # EvaluationSnapshot.economic_criteria_weights at publish time - same
    # "config lives on Evaluation, not per-Proposal" reasoning as
    # base_currency/tco_horizon_years above.
    economic_criteria_weights: EconomicCriteriaWeights

    @staticmethod
    def create(
        tenant_id: str, name: str, description: str, created_by_membership_id: str
    ) -> "Evaluation":
        now = datetime.now(UTC)
        return Evaluation(
            id=new_id(),
            tenant_id=tenant_id,
            name=name,
            description=description,
            status="draft",
            requirements=[],
            linked_vendor_count=0,
            created_by_membership_id=created_by_membership_id,
            created_at=now,
            updated_at=now,
            collecting_responses_started_at=None,
            evaluating_started_at=None,
            completed_at=None,
            approval_status="not_requested",
            approver_membership_id=None,
            response_deadline=None,
            approval_requested_at=None,
            approval_requested_by_membership_id=None,
            approval_decided_at=None,
            approval_decided_by_membership_id=None,
            approval_comment=None,
            approval_snapshot_id=None,
            reviewer_membership_id=None,
            review_status="not_requested",
            review_requested_at=None,
            review_requested_by_membership_id=None,
            review_decided_at=None,
            review_decided_by_membership_id=None,
            review_comment=None,
            base_currency="MXN",
            tco_horizon_years=1,
            economic_criteria_weights=EconomicCriteriaWeights.defaults(),
        )

    def to_document(self) -> dict[str, Any]:
        return {
            "_id": self.id,
            "tenant_id": self.tenant_id,
            "name": self.name,
            "description": self.description,
            "status": self.status,
            "requirements": [r.to_document() for r in self.requirements],
            "linked_vendor_count": self.linked_vendor_count,
            "created_by_membership_id": self.created_by_membership_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "collecting_responses_started_at": self.collecting_responses_started_at,
            "evaluating_started_at": self.evaluating_started_at,
            "completed_at": self.completed_at,
            "approval_status": self.approval_status,
            "approver_membership_id": self.approver_membership_id,
            "response_deadline": self.response_deadline,
            "approval_requested_at": self.approval_requested_at,
            "approval_requested_by_membership_id": self.approval_requested_by_membership_id,
            "approval_decided_at": self.approval_decided_at,
            "approval_decided_by_membership_id": self.approval_decided_by_membership_id,
            "approval_comment": self.approval_comment,
            "approval_snapshot_id": self.approval_snapshot_id,
            "reviewer_membership_id": self.reviewer_membership_id,
            "review_status": self.review_status,
            "review_requested_at": self.review_requested_at,
            "review_requested_by_membership_id": self.review_requested_by_membership_id,
            "review_decided_at": self.review_decided_at,
            "review_decided_by_membership_id": self.review_decided_by_membership_id,
            "review_comment": self.review_comment,
            "base_currency": self.base_currency,
            "tco_horizon_years": self.tco_horizon_years,
            "economic_criteria_weights": self.economic_criteria_weights.to_document(),
        }

    @staticmethod
    def from_document(doc: dict[str, Any]) -> "Evaluation":
        return Evaluation(
            id=doc["_id"],
            tenant_id=doc["tenant_id"],
            name=doc["name"],
            description=doc["description"],
            status=doc["status"],
            requirements=[Requirement.from_document(r) for r in doc.get("requirements", [])],
            linked_vendor_count=doc.get("linked_vendor_count", 0),
            created_by_membership_id=doc["created_by_membership_id"],
            created_at=doc["created_at"],
            updated_at=doc["updated_at"],
            collecting_responses_started_at=doc.get("collecting_responses_started_at"),
            evaluating_started_at=doc.get("evaluating_started_at"),
            completed_at=doc.get("completed_at"),
            # .get(..., default) throughout - evaluations persisted before
            # Fase 12 have none of these keys (plan §29: no backfill).
            approval_status=doc.get("approval_status", "not_requested"),
            approver_membership_id=doc.get("approver_membership_id"),
            response_deadline=doc.get("response_deadline"),
            approval_requested_at=doc.get("approval_requested_at"),
            approval_requested_by_membership_id=doc.get("approval_requested_by_membership_id"),
            approval_decided_at=doc.get("approval_decided_at"),
            approval_decided_by_membership_id=doc.get("approval_decided_by_membership_id"),
            approval_comment=doc.get("approval_comment"),
            approval_snapshot_id=doc.get("approval_snapshot_id"),
            # ADR 0026 - evaluations persisted before R2 have none of these
            # keys; no backfill needed, "not_requested"/None means "this
            # evaluation never used the review stage", which is also its
            # correct meaning for every evaluation created after R2 that
            # simply never assigns a reviewer (ADR 0026: optional per
            # evaluation).
            reviewer_membership_id=doc.get("reviewer_membership_id"),
            review_status=doc.get("review_status", "not_requested"),
            review_requested_at=doc.get("review_requested_at"),
            review_requested_by_membership_id=doc.get("review_requested_by_membership_id"),
            review_decided_at=doc.get("review_decided_at"),
            review_decided_by_membership_id=doc.get("review_decided_by_membership_id"),
            review_comment=doc.get("review_comment"),
            # Fase 19 - evaluations persisted before this phase have neither
            # key; MXN/1 year are the safe defaults (plan §17 N239-241, no
            # backfill).
            base_currency=doc.get("base_currency", "MXN"),
            tco_horizon_years=doc.get("tco_horizon_years", 1),
            # Fase 20 - evaluations persisted before this phase have no key;
            # ADR 0009 defaults are the safe fallback (no backfill).
            economic_criteria_weights=EconomicCriteriaWeights.from_document(
                doc.get("economic_criteria_weights")
            ),
        )

    def approval_invalidation_extra_set(self) -> dict[str, Any]:
        """Plan §32 Blocker 3 (soft-invalidation, confirmed by founder):
        merged into the same atomic write as the edit itself, not a
        separate follow-up write - the mutation and the invalidation land
        together or not at all. Callers outside evaluations.service (e.g.
        knowledge_templates.service applying a template onto a draft
        evaluation, Fase 11) reuse this instead of reimplementing the rule.

        ADR 0026 (R2): the same trigger also resets review_status when it is
        "pending"/"approved" - an edit after the reviewer decided must
        invalidate that decision exactly like it already invalidates the
        approver's, otherwise a Reviewer's approval could silently survive a
        content change it never actually reviewed. Both resets are folded
        into the one dict this method returns so every existing call site
        (evaluations.service, ai.service, knowledge_templates.service,
        reports.import_service) gets the review reset for free, with no
        change required at any of them."""
        extra: dict[str, Any] = {}
        if self.approval_status in INVALIDATED_BY_APPROVAL_EDIT:
            extra.update(
                {
                    "approval_status": "not_requested",
                    "approval_decided_at": None,
                    "approval_decided_by_membership_id": None,
                    "approval_comment": None,
                }
            )
        if self.review_status in INVALIDATED_BY_APPROVAL_EDIT:
            extra.update(
                {
                    "review_status": "not_requested",
                    "review_decided_at": None,
                    "review_decided_by_membership_id": None,
                    "review_comment": None,
                }
            )
        return extra


@dataclass(frozen=True)
class EvaluationSnapshot:
    """Immutable record of exactly what was approved and published, taken
    once at the draft -> collecting_responses transition (plan §21/§22).
    Lives in its own collection (evaluations.snapshot_repository), never
    embedded on Evaluation - requirements are unbounded, unlike the capped
    MAX_LINKED_VENDORS vendor list. snapshot_id == evaluation_id
    (deterministic, not a fresh uuid): EvaluationStatus never regresses to
    draft, so at most one snapshot can ever exist per evaluation, and the
    deterministic id makes the insert step naturally idempotent under retry
    (a repeat insert raises DuplicateKeyError, treated as already-done)."""

    snapshot_id: str
    tenant_id: str
    evaluation_id: str
    taken_at: datetime
    evaluation_name: str
    evaluation_description: str
    requirements: list[Requirement]
    dimension_weights: dict[str, float]
    linked_vendor_org_ids: list[str]
    vendor_org_names: dict[str, str]
    response_deadline: datetime
    approver_membership_id: str
    approval_requested_at: datetime
    approval_requested_by_membership_id: str
    approval_decided_at: datetime
    approval_decided_by_membership_id: str
    approval_comment: str | None
    published_by_membership_id: str
    published_at: datetime
    # Fase 20 (ADR 0009): frozen at the same moment as dimension_weights -
    # changing weights after publish requires the new-version flow (ADR
    # 0013, Fase 21), not a direct edit.
    economic_criteria_weights: EconomicCriteriaWeights

    def to_document(self) -> dict[str, Any]:
        return {
            "_id": self.snapshot_id,
            "tenant_id": self.tenant_id,
            "evaluation_id": self.evaluation_id,
            "taken_at": self.taken_at,
            "evaluation_name": self.evaluation_name,
            "evaluation_description": self.evaluation_description,
            "requirements": [r.to_document() for r in self.requirements],
            "dimension_weights": self.dimension_weights,
            "linked_vendor_org_ids": self.linked_vendor_org_ids,
            "vendor_org_names": self.vendor_org_names,
            "response_deadline": self.response_deadline,
            "approver_membership_id": self.approver_membership_id,
            "approval_requested_at": self.approval_requested_at,
            "approval_requested_by_membership_id": self.approval_requested_by_membership_id,
            "approval_decided_at": self.approval_decided_at,
            "approval_decided_by_membership_id": self.approval_decided_by_membership_id,
            "approval_comment": self.approval_comment,
            "published_by_membership_id": self.published_by_membership_id,
            "published_at": self.published_at,
            "economic_criteria_weights": self.economic_criteria_weights.to_document(),
        }

    @staticmethod
    def from_document(doc: dict[str, Any]) -> "EvaluationSnapshot":
        return EvaluationSnapshot(
            snapshot_id=doc["_id"],
            tenant_id=doc["tenant_id"],
            evaluation_id=doc["evaluation_id"],
            taken_at=doc["taken_at"],
            evaluation_name=doc["evaluation_name"],
            evaluation_description=doc["evaluation_description"],
            requirements=[Requirement.from_document(r) for r in doc.get("requirements", [])],
            dimension_weights=doc["dimension_weights"],
            linked_vendor_org_ids=doc["linked_vendor_org_ids"],
            vendor_org_names=doc["vendor_org_names"],
            response_deadline=doc["response_deadline"],
            approver_membership_id=doc["approver_membership_id"],
            approval_requested_at=doc["approval_requested_at"],
            approval_requested_by_membership_id=doc["approval_requested_by_membership_id"],
            approval_decided_at=doc["approval_decided_at"],
            approval_decided_by_membership_id=doc["approval_decided_by_membership_id"],
            approval_comment=doc.get("approval_comment"),
            published_by_membership_id=doc["published_by_membership_id"],
            published_at=doc["published_at"],
            # Fase 20 - snapshots taken before this phase have no key; ADR
            # 0009 defaults are the safe fallback (no backfill).
            economic_criteria_weights=EconomicCriteriaWeights.from_document(
                doc.get("economic_criteria_weights")
            ),
        )
