from datetime import datetime

from procurawise.evaluations.models import (
    ApprovalStatus,
    Dimension,
    EvaluationStatus,
    Priority,
    ResponseType,
)
from procurawise.shared.api_models import APIModel


class EvaluationCreateRequest(APIModel):
    name: str
    description: str = ""


class EvaluationUpdateRequest(APIModel):
    name: str | None = None
    description: str | None = None
    response_deadline: datetime | None = None


class RequirementCreateRequest(APIModel):
    dimension: Dimension
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
    dimension: Dimension | None = None
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


class RequirementResponse(APIModel):
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


class SetApproverRequest(APIModel):
    approver_membership_id: str


class ApprovalDecisionRequest(APIModel):
    comment: str | None = None


class RejectionRequest(APIModel):
    comment: str


class PublicationReadinessResponse(APIModel):
    can_request_approval: bool
    request_approval_reasons: list[str]
    can_publish: bool
    publish_reasons: list[str]
    approval_status: ApprovalStatus
    approver_membership_id: str | None
    response_deadline: datetime | None


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
