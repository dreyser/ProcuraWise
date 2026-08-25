from datetime import datetime
from typing import Literal

from pydantic import Field

from procurawise.evaluations.models import (
    ApprovalStatus,
    EvaluationStatus,
    Priority,
    RequirementDimension,
    ResponseType,
)
from procurawise.shared.api_models import APIModel

# Fase 19 - same MXN/USD pair as proposals.service._CURRENCY_CODES /
# tco.models.TCO_CURRENCIES, duplicated locally rather than imported: this
# module intentionally does not depend on `tco` (plan §11.9's currency
# constant lives with the module that owns the concept it validates).
EvaluationCurrency = Literal["MXN", "USD"]


class EvaluationCreateRequest(APIModel):
    name: str
    description: str = ""


class EvaluationUpdateRequest(APIModel):
    name: str | None = None
    description: str | None = None
    response_deadline: datetime | None = None
    # Fase 19 (plan §9 R9): TCO config for the evaluation, same "optional,
    # only applied if not None" convention as the fields above.
    base_currency: EvaluationCurrency | None = None
    tco_horizon_years: int | None = Field(default=None, ge=1, le=5)


class RequirementCreateRequest(APIModel):
    dimension: RequirementDimension
    category: str
    title: str
    description: str
    priority: Priority
    response_type: ResponseType
    weight: float
    required: bool
    display_order: int
    buyer_guidance: str | None = None
    options: list[str] | None = None


class RequirementUpdateRequest(APIModel):
    dimension: RequirementDimension | None = None
    category: str | None = None
    title: str | None = None
    description: str | None = None
    priority: Priority | None = None
    response_type: ResponseType | None = None
    weight: float | None = None
    required: bool | None = None
    display_order: int | None = None
    buyer_guidance: str | None = None
    options: list[str] | None = None


class VendorLinkRequest(APIModel):
    vendor_org_id: str


class EconomicCriteriaWeightsResponse(APIModel):
    """Fase 20 (ADR 0009) - the 5 keys within each group are fixed across
    every evaluation (plan §9 Pregunta Bloqueante #1); only the values are
    owner-editable before publish."""

    commercial: dict[str, float]
    risk: dict[str, float]


class UpdateEconomicCriteriaWeightsRequest(APIModel):
    """Both groups are required (a full replace, not a partial patch) so a
    caller can never submit a group that doesn't sum to 100 by omission -
    validated in evaluations.service, not here (same convention as the rest
    of this module: schemas describe shape, services validate business
    rules)."""

    commercial: dict[str, float]
    risk: dict[str, float]


class RequirementResponse(APIModel):
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


class EvaluationSummaryResponse(APIModel):
    id: str
    name: str
    status: EvaluationStatus
    linked_vendor_count: int
    created_at: datetime
    updated_at: datetime


class EvaluationDetailResponse(APIModel):
    id: str
    name: str
    description: str
    status: EvaluationStatus
    requirements: list[RequirementResponse]
    linked_vendor_count: int
    created_by_membership_id: str
    created_at: datetime
    updated_at: datetime
    collecting_responses_started_at: datetime | None
    evaluating_started_at: datetime | None
    completed_at: datetime | None
    approval_status: ApprovalStatus
    approver_membership_id: str | None
    response_deadline: datetime | None
    approval_requested_at: datetime | None
    approval_requested_by_membership_id: str | None
    approval_decided_at: datetime | None
    approval_decided_by_membership_id: str | None
    approval_comment: str | None
    approval_snapshot_id: str | None
    base_currency: str
    tco_horizon_years: int
    economic_criteria_weights: EconomicCriteriaWeightsResponse
    # ADR 0026 (R2) - review stage is optional per evaluation; None/
    # "not_requested" for every evaluation that never assigns a reviewer.
    reviewer_membership_id: str | None
    review_status: ApprovalStatus
    review_requested_at: datetime | None
    review_requested_by_membership_id: str | None
    review_decided_at: datetime | None
    review_decided_by_membership_id: str | None
    review_comment: str | None


class SetApproverRequest(APIModel):
    approver_membership_id: str


class ApprovalDecisionRequest(APIModel):
    comment: str | None = None


class RequirementNoteRequest(APIModel):
    """ADR 0026 (R2) - a per-requirement comment attached to a "solicitar
    cambios" decision (blocking question resolved 2026-08-24: preserved
    individually, never collapsed into the single evaluation-level
    `comment`)."""

    requirement_id: str
    comment: str


class RejectionRequest(APIModel):
    comment: str
    # ADR 0026 (R2) - both fields are additive/optional so this schema keeps
    # working unchanged for every caller that predates R2 (the reject body
    # they already send). `kind` never changes what gets persisted
    # (approval_status/review_status always become "rejected" either way) -
    # it only changes which AuditAction is recorded, so "solicitud de
    # cambios" and "rechazo genérico" are never the same, indistinguishable
    # audit event.
    kind: Literal["rejected", "changes_requested"] = "rejected"
    requirement_notes: list[RequirementNoteRequest] | None = None


class SetReviewerRequest(APIModel):
    reviewer_membership_id: str


class PublicationReadinessResponse(APIModel):
    can_request_approval: bool
    request_approval_reasons: list[str]
    can_publish: bool
    publish_reasons: list[str]
    approval_status: ApprovalStatus
    approver_membership_id: str | None
    response_deadline: datetime | None
    # ADR 0026 (R2) - mirrors the approval readiness fields above for the
    # review stage. can_request_review/request_review_reasons are always
    # meaningful (an evaluation with no reviewer assigned simply has an
    # empty reasons list and can_request_review=False until one is set,
    # same shape as approval before an approver is assigned).
    can_request_review: bool
    request_review_reasons: list[str]
    review_status: ApprovalStatus
    reviewer_membership_id: str | None


class EvaluationSnapshotResponse(APIModel):
    snapshot_id: str
    evaluation_id: str
    taken_at: datetime
    evaluation_name: str
    evaluation_description: str
    requirements: list[RequirementResponse]
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
    economic_criteria_weights: EconomicCriteriaWeightsResponse
