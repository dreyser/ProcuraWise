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

Dimension = Literal["functional", "technical"]
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
DIMENSION_MAX_POINTS: dict[Dimension, float] = {"functional": 40.0, "technical": 20.0}
ECONOMIC_MAX_POINTS = 40.0
PARTIAL_RESULT_MAX_POINTS = sum(DIMENSION_MAX_POINTS.values())  # 60 - functional+technical only

MAX_LINKED_VENDORS = 6


def new_id() -> str:
    return uuid4().hex


@dataclass(frozen=True)
class Requirement:
    """Embedded in Evaluation.requirements. `required` (must the vendor answer
    before submit) is independent of `priority == "mandatory"` (generates a
    non-blocking alert in results when scored low) - two distinct concepts
    from PRD §6.3, not one field wearing two hats."""

    id: str
    dimension: Dimension
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
        dimension: Dimension,
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
    # Fase 19 (ADR 0008, plan §9 R9): TCO config lives on the Evaluation
    # (like weights/response_deadline), not per-Proposal - every vendor's
    # CostItems are compared against the same base currency/horizon.
    # Defaulted (never backfilled) so evaluations persisted before Fase 19
    # deserialize safely - see from_document.
    base_currency: str
    tco_horizon_years: int

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
            base_currency="MXN",
            tco_horizon_years=1,
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
            "base_currency": self.base_currency,
            "tco_horizon_years": self.tco_horizon_years,
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
            # Fase 19 - evaluations persisted before this phase have neither
            # key; MXN/1 year are the safe defaults (plan §17 N239-241, no
            # backfill).
            base_currency=doc.get("base_currency", "MXN"),
            tco_horizon_years=doc.get("tco_horizon_years", 1),
        )

    def approval_invalidation_extra_set(self) -> dict[str, Any]:
        """Plan §32 Blocker 3 (soft-invalidation, confirmed by founder):
        merged into the same atomic write as the edit itself, not a
        separate follow-up write - the mutation and the invalidation land
        together or not at all. Callers outside evaluations.service (e.g.
        knowledge_templates.service applying a template onto a draft
        evaluation, Fase 11) reuse this instead of reimplementing the rule."""
        if self.approval_status not in INVALIDATED_BY_APPROVAL_EDIT:
            return {}
        return {
            "approval_status": "not_requested",
            "approval_decided_at": None,
            "approval_decided_by_membership_id": None,
            "approval_comment": None,
        }


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
        )
