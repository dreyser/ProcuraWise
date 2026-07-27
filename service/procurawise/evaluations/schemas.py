from datetime import datetime

from procurawise.evaluations.models import Dimension, EvaluationStatus, Priority, ResponseType
from procurawise.shared.api_models import APIModel


class EvaluationCreateRequest(APIModel):
    name: str
    description: str = ""


class EvaluationUpdateRequest(APIModel):
    name: str | None = None
    description: str | None = None


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
