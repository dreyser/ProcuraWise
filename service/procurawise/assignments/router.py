from fastapi import APIRouter, Depends, HTTPException

from procurawise.assignments.exceptions import (
    AssignmentNotFoundError,
    AssignmentUpdateNotPermittedError,
    DuplicateAssignmentError,
    EvaluatorMembershipNotFoundError,
    EvaluatorRoleMismatchError,
    SectionNotFoundError,
)
from procurawise.assignments.models import Assignment
from procurawise.assignments.repository import AssignmentRepository
from procurawise.assignments.schemas import (
    AssignmentCreateRequest,
    AssignmentListResponse,
    AssignmentResponse,
    AssignmentStatusUpdateRequest,
)
from procurawise.assignments.service import AssignmentService
from procurawise.audit.repository import AuditEventRepository
from procurawise.audit.service import AuditEventService
from procurawise.evaluations.exceptions import EvaluationNotFoundError
from procurawise.evaluations.repository import EvaluationRepository
from procurawise.identity.repository import MembershipRepository
from procurawise.shared.config import Settings, get_settings
from procurawise.shared.context import ActorContext, require_role
from procurawise.shared.mongo import get_database
from procurawise.shared.roles import BUYER_READ_ROLES, OWNER_ONLY

router = APIRouter(prefix="/evaluations/{evaluation_id}/assignments", tags=["assignments"])

require_buyer_read = require_role(*BUYER_READ_ROLES)
require_owner = require_role(*OWNER_ONLY)


def get_assignment_service(settings: Settings = Depends(get_settings)) -> AssignmentService:
    db = get_database(settings)
    return AssignmentService(
        assignments=AssignmentRepository(db),
        evaluations=EvaluationRepository(db),
        memberships=MembershipRepository(db),
        audit=AuditEventService(AuditEventRepository(db), settings),
    )


def _response(assignment: Assignment) -> AssignmentResponse:
    return AssignmentResponse(
        id=assignment.id,
        evaluation_id=assignment.evaluation_id,
        dimension=assignment.dimension,
        section=assignment.section,
        evaluator_membership_id=assignment.evaluator_membership_id,
        assigned_by_membership_id=assignment.assigned_by_membership_id,
        status=assignment.status,
        created_at=assignment.created_at,
        updated_at=assignment.updated_at,
    )


@router.post("", response_model=AssignmentResponse, status_code=201)
def create_assignment(
    evaluation_id: str,
    body: AssignmentCreateRequest,
    context: ActorContext = Depends(require_owner),
    service: AssignmentService = Depends(get_assignment_service),
) -> AssignmentResponse:
    try:
        assignment = service.create_assignment(
            context.tenant_id,
            evaluation_id,
            body.dimension,
            body.section,
            body.evaluator_membership_id,
            actor=context,
        )
    except EvaluationNotFoundError:
        raise HTTPException(status_code=404) from None
    except (
        SectionNotFoundError,
        EvaluatorMembershipNotFoundError,
        EvaluatorRoleMismatchError,
    ) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    except DuplicateAssignmentError:
        raise HTTPException(status_code=409, detail="evaluator already assigned") from None
    return _response(assignment)


@router.get("", response_model=AssignmentListResponse)
def list_assignments(
    evaluation_id: str,
    context: ActorContext = Depends(require_buyer_read),
    service: AssignmentService = Depends(get_assignment_service),
) -> AssignmentListResponse:
    try:
        assignments = service.list_for_evaluation(context.tenant_id, evaluation_id)
    except EvaluationNotFoundError:
        raise HTTPException(status_code=404) from None
    return AssignmentListResponse(items=[_response(a) for a in assignments])


@router.patch("/{assignment_id}/status", response_model=AssignmentResponse)
def update_assignment_status(
    evaluation_id: str,
    assignment_id: str,
    body: AssignmentStatusUpdateRequest,
    context: ActorContext = Depends(require_buyer_read),
    service: AssignmentService = Depends(get_assignment_service),
) -> AssignmentResponse:
    try:
        assignment = service.update_status(
            context.tenant_id, evaluation_id, assignment_id, body.status, actor=context
        )
    except AssignmentNotFoundError:
        raise HTTPException(status_code=404) from None
    except AssignmentUpdateNotPermittedError:
        raise HTTPException(
            status_code=403, detail="not permitted to update this assignment"
        ) from None
    return _response(assignment)


@router.delete("/{assignment_id}", status_code=204)
def delete_assignment(
    evaluation_id: str,
    assignment_id: str,
    context: ActorContext = Depends(require_owner),
    service: AssignmentService = Depends(get_assignment_service),
) -> None:
    try:
        service.delete_assignment(context.tenant_id, evaluation_id, assignment_id, actor=context)
    except AssignmentNotFoundError:
        raise HTTPException(status_code=404) from None
