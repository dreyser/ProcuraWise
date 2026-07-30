from datetime import datetime

from procurawise.assignments.models import AssignmentStatus
from procurawise.evaluations.models import Dimension
from procurawise.shared.api_models import APIModel


class AssignmentCreateRequest(APIModel):
    dimension: Dimension
    section: str
    evaluator_membership_id: str


class AssignmentStatusUpdateRequest(APIModel):
    status: AssignmentStatus


class AssignmentResponse(APIModel):
    id: str
    evaluation_id: str
    dimension: Dimension
    section: str
    evaluator_membership_id: str
    assigned_by_membership_id: str
    status: AssignmentStatus
    created_at: datetime
    updated_at: datetime


class AssignmentListResponse(APIModel):
    items: list[AssignmentResponse]
