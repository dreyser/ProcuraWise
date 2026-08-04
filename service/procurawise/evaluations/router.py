from fastapi import APIRouter, Depends, HTTPException

from procurawise.audit.repository import AuditEventRepository
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
from procurawise.evaluations.models import Evaluation, EvaluationSnapshot, Requirement
from procurawise.evaluations.repository import EvaluationRepository
from procurawise.evaluations.schemas import (
    ApprovalDecisionRequest,
    EvaluationCreateRequest,
    EvaluationDetailResponse,
    EvaluationSnapshotResponse,
    EvaluationSummaryResponse,
    EvaluationUpdateRequest,
    PublicationReadinessResponse,
    RejectionRequest,
    RequirementCreateRequest,
    RequirementResponse,
    RequirementUpdateRequest,
    SetApproverRequest,
    VendorLinkRequest,
)
from procurawise.evaluations.service import EvaluationService
from procurawise.evaluations.snapshot_repository import EvaluationSnapshotRepository
from procurawise.identity.repository import MembershipRepository, VendorOrganizationRepository
from procurawise.proposals.repository import ProposalRepository
from procurawise.proposals.schemas import ProposalSummaryResponse
from procurawise.shared.config import Settings, get_settings
from procurawise.shared.context import ActorContext, require_role
from procurawise.shared.mongo import get_database
from procurawise.shared.roles import BUYER_READ_ROLES, OWNER_ONLY

router = APIRouter(prefix="/evaluations", tags=["evaluations"])

# Computed once at module import time (not inside a route's argument default,
# which ruff/bugbear (B008) flags as a function call in a mutable default) -
# FastAPI still resolves this dependency fresh on every request.
require_buyer_read = require_role(*BUYER_READ_ROLES)
require_owner = require_role(*OWNER_ONLY)
# Fase 12: approve/reject are restricted further, in the service layer, to
# the evaluation's own approver_membership_id - this only gates "holds the
# approver role at all" (plan §17).
require_approver = require_role("approver")


def get_evaluation_service(settings: Settings = Depends(get_settings)) -> EvaluationService:
    db = get_database(settings)
    return EvaluationService(
        evaluations=EvaluationRepository(db),
        proposals=ProposalRepository(db),
        vendor_orgs=VendorOrganizationRepository(db),
        memberships=MembershipRepository(db),
        snapshots=EvaluationSnapshotRepository(db),
        audit=AuditEventService(AuditEventRepository(db), settings),
    )


def _requirement_response(requirement: Requirement) -> RequirementResponse:
    return RequirementResponse(
        id=requirement.id,
        dimension=requirement.dimension,
        category=requirement.category,
        title=requirement.title,
        description=requirement.description,
        priority=requirement.priority,
        response_type=requirement.response_type,
        weight=requirement.weight,
        required=requirement.required,
        buyer_guidance=requirement.buyer_guidance,
        display_order=requirement.display_order,
        options=requirement.options,
        created_at=requirement.created_at,
        updated_at=requirement.updated_at,
    )


def _evaluation_detail(evaluation: Evaluation) -> EvaluationDetailResponse:
    return EvaluationDetailResponse(
        id=evaluation.id,
        name=evaluation.name,
        description=evaluation.description,
        status=evaluation.status,
        requirements=[_requirement_response(r) for r in evaluation.requirements],
        linked_vendor_count=evaluation.linked_vendor_count,
        created_by_membership_id=evaluation.created_by_membership_id,
        created_at=evaluation.created_at,
        updated_at=evaluation.updated_at,
        collecting_responses_started_at=evaluation.collecting_responses_started_at,
        evaluating_started_at=evaluation.evaluating_started_at,
        completed_at=evaluation.completed_at,
        approval_status=evaluation.approval_status,
        approver_membership_id=evaluation.approver_membership_id,
        response_deadline=evaluation.response_deadline,
        approval_requested_at=evaluation.approval_requested_at,
        approval_requested_by_membership_id=evaluation.approval_requested_by_membership_id,
        approval_decided_at=evaluation.approval_decided_at,
        approval_decided_by_membership_id=evaluation.approval_decided_by_membership_id,
        approval_comment=evaluation.approval_comment,
        approval_snapshot_id=evaluation.approval_snapshot_id,
        base_currency=evaluation.base_currency,
        tco_horizon_years=evaluation.tco_horizon_years,
    )


@router.post("", response_model=EvaluationDetailResponse, status_code=201)
def create_evaluation(
    body: EvaluationCreateRequest,
    context: ActorContext = Depends(require_owner),
    service: EvaluationService = Depends(get_evaluation_service),
) -> EvaluationDetailResponse:
    evaluation = service.create_evaluation(
        context.tenant_id, context.membership_id, body.name, body.description, actor=context
    )
    return _evaluation_detail(evaluation)


@router.get("", response_model=list[EvaluationSummaryResponse])
def list_evaluations(
    context: ActorContext = Depends(require_buyer_read),
    service: EvaluationService = Depends(get_evaluation_service),
) -> list[EvaluationSummaryResponse]:
    return [
        EvaluationSummaryResponse(
            id=e.id,
            name=e.name,
            status=e.status,
            linked_vendor_count=e.linked_vendor_count,
            created_at=e.created_at,
            updated_at=e.updated_at,
        )
        for e in service.list_evaluations(context.tenant_id)
    ]


@router.get("/{evaluation_id}", response_model=EvaluationDetailResponse)
def get_evaluation(
    evaluation_id: str,
    context: ActorContext = Depends(require_buyer_read),
    service: EvaluationService = Depends(get_evaluation_service),
) -> EvaluationDetailResponse:
    try:
        evaluation = service.get_evaluation(context.tenant_id, evaluation_id)
    except EvaluationNotFoundError:
        raise HTTPException(status_code=404) from None
    return _evaluation_detail(evaluation)


@router.patch("/{evaluation_id}", response_model=EvaluationDetailResponse)
def update_evaluation(
    evaluation_id: str,
    body: EvaluationUpdateRequest,
    context: ActorContext = Depends(require_owner),
    service: EvaluationService = Depends(get_evaluation_service),
) -> EvaluationDetailResponse:
    try:
        evaluation = service.update_evaluation(
            context.tenant_id,
            evaluation_id,
            body.name,
            body.description,
            body.response_deadline,
            body.base_currency,
            body.tco_horizon_years,
            actor=context,
        )
    except EvaluationNotFoundError:
        raise HTTPException(status_code=404) from None
    except InvalidTransitionError:
        raise HTTPException(status_code=409, detail="evaluation is not draft") from None
    return _evaluation_detail(evaluation)


@router.post("/{evaluation_id}/approver", response_model=EvaluationDetailResponse)
def set_approver(
    evaluation_id: str,
    body: SetApproverRequest,
    context: ActorContext = Depends(require_owner),
    service: EvaluationService = Depends(get_evaluation_service),
) -> EvaluationDetailResponse:
    try:
        evaluation = service.set_approver(
            context.tenant_id, evaluation_id, body.approver_membership_id, actor=context
        )
    except EvaluationNotFoundError:
        raise HTTPException(status_code=404) from None
    except ApproverMembershipNotFoundError:
        raise HTTPException(status_code=404, detail="approver membership not found") from None
    except ApproverRoleMismatchError:
        raise HTTPException(
            status_code=400, detail="target membership does not hold the approver role"
        ) from None
    except SelfApprovalError:
        raise HTTPException(
            status_code=400, detail="the evaluation owner may not be their own approver"
        ) from None
    except InvalidTransitionError:
        raise HTTPException(
            status_code=409, detail="evaluation is not draft or approval is already in progress"
        ) from None
    return _evaluation_detail(evaluation)


@router.post("/{evaluation_id}/request-approval", response_model=EvaluationDetailResponse)
def request_approval(
    evaluation_id: str,
    context: ActorContext = Depends(require_owner),
    service: EvaluationService = Depends(get_evaluation_service),
) -> EvaluationDetailResponse:
    try:
        evaluation = service.request_approval(context.tenant_id, evaluation_id, actor=context)
    except EvaluationNotFoundError:
        raise HTTPException(status_code=404) from None
    except InvalidTransitionError:
        raise HTTPException(status_code=409, detail="evaluation is not draft") from None
    except ApprovalPreconditionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return _evaluation_detail(evaluation)


@router.delete("/{evaluation_id}/request-approval", status_code=204)
def withdraw_approval_request(
    evaluation_id: str,
    context: ActorContext = Depends(require_owner),
    service: EvaluationService = Depends(get_evaluation_service),
) -> None:
    try:
        service.withdraw_approval_request(context.tenant_id, evaluation_id, actor=context)
    except EvaluationNotFoundError:
        raise HTTPException(status_code=404) from None
    except InvalidTransitionError:
        raise HTTPException(status_code=409, detail="approval is not pending") from None


@router.post("/{evaluation_id}/approve", response_model=EvaluationDetailResponse)
def approve_evaluation(
    evaluation_id: str,
    body: ApprovalDecisionRequest,
    context: ActorContext = Depends(require_approver),
    service: EvaluationService = Depends(get_evaluation_service),
) -> EvaluationDetailResponse:
    try:
        evaluation = service.approve(context.tenant_id, evaluation_id, body.comment, actor=context)
    except EvaluationNotFoundError:
        raise HTTPException(status_code=404) from None
    except NotAssignedApproverError:
        raise HTTPException(
            status_code=403, detail="only the assigned approver may decide this evaluation"
        ) from None
    except InvalidTransitionError:
        raise HTTPException(status_code=409, detail="approval is not pending") from None
    return _evaluation_detail(evaluation)


@router.post("/{evaluation_id}/reject", response_model=EvaluationDetailResponse)
def reject_evaluation(
    evaluation_id: str,
    body: RejectionRequest,
    context: ActorContext = Depends(require_approver),
    service: EvaluationService = Depends(get_evaluation_service),
) -> EvaluationDetailResponse:
    try:
        evaluation = service.reject(context.tenant_id, evaluation_id, body.comment, actor=context)
    except EvaluationNotFoundError:
        raise HTTPException(status_code=404) from None
    except NotAssignedApproverError:
        raise HTTPException(
            status_code=403, detail="only the assigned approver may decide this evaluation"
        ) from None
    except InvalidTransitionError:
        raise HTTPException(status_code=409, detail="approval is not pending") from None
    return _evaluation_detail(evaluation)


@router.get("/{evaluation_id}/publication-readiness", response_model=PublicationReadinessResponse)
def publication_readiness(
    evaluation_id: str,
    context: ActorContext = Depends(require_buyer_read),
    service: EvaluationService = Depends(get_evaluation_service),
) -> PublicationReadinessResponse:
    try:
        readiness = service.publication_readiness(context.tenant_id, evaluation_id)
    except EvaluationNotFoundError:
        raise HTTPException(status_code=404) from None
    return PublicationReadinessResponse(**readiness)


def _snapshot_response(snapshot: EvaluationSnapshot) -> EvaluationSnapshotResponse:
    return EvaluationSnapshotResponse(
        snapshot_id=snapshot.snapshot_id,
        evaluation_id=snapshot.evaluation_id,
        taken_at=snapshot.taken_at,
        evaluation_name=snapshot.evaluation_name,
        evaluation_description=snapshot.evaluation_description,
        requirements=[_requirement_response(r) for r in snapshot.requirements],
        dimension_weights=snapshot.dimension_weights,
        linked_vendor_org_ids=snapshot.linked_vendor_org_ids,
        vendor_org_names=snapshot.vendor_org_names,
        response_deadline=snapshot.response_deadline,
        approver_membership_id=snapshot.approver_membership_id,
        approval_requested_at=snapshot.approval_requested_at,
        approval_requested_by_membership_id=snapshot.approval_requested_by_membership_id,
        approval_decided_at=snapshot.approval_decided_at,
        approval_decided_by_membership_id=snapshot.approval_decided_by_membership_id,
        approval_comment=snapshot.approval_comment,
        published_by_membership_id=snapshot.published_by_membership_id,
        published_at=snapshot.published_at,
    )


@router.get("/{evaluation_id}/snapshot", response_model=EvaluationSnapshotResponse)
def get_snapshot(
    evaluation_id: str,
    context: ActorContext = Depends(require_buyer_read),
    service: EvaluationService = Depends(get_evaluation_service),
) -> EvaluationSnapshotResponse:
    try:
        snapshot = service.get_snapshot(context.tenant_id, evaluation_id)
    except SnapshotNotFoundError:
        raise HTTPException(status_code=404) from None
    return _snapshot_response(snapshot)


@router.post("/{evaluation_id}/requirements", response_model=RequirementResponse, status_code=201)
def add_requirement(
    evaluation_id: str,
    body: RequirementCreateRequest,
    context: ActorContext = Depends(require_owner),
    service: EvaluationService = Depends(get_evaluation_service),
) -> RequirementResponse:
    try:
        requirement = service.add_requirement(
            context.tenant_id,
            evaluation_id,
            dimension=body.dimension,
            category=body.category,
            title=body.title,
            description=body.description,
            priority=body.priority,
            response_type=body.response_type,
            weight=body.weight,
            required=body.required,
            display_order=body.display_order,
            buyer_guidance=body.buyer_guidance,
            options=body.options,
            actor=context,
        )
    except EvaluationNotFoundError:
        raise HTTPException(status_code=404) from None
    except InvalidTransitionError:
        raise HTTPException(status_code=409, detail="evaluation is not draft") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return _requirement_response(requirement)


@router.patch("/{evaluation_id}/requirements/{requirement_id}", response_model=RequirementResponse)
def update_requirement(
    evaluation_id: str,
    requirement_id: str,
    body: RequirementUpdateRequest,
    context: ActorContext = Depends(require_owner),
    service: EvaluationService = Depends(get_evaluation_service),
) -> RequirementResponse:
    field_updates = body.model_dump(exclude_unset=True)
    try:
        requirement = service.update_requirement(
            context.tenant_id, evaluation_id, requirement_id, field_updates, actor=context
        )
    except EvaluationNotFoundError:
        raise HTTPException(status_code=404) from None
    except RequirementNotFoundError:
        raise HTTPException(status_code=404) from None
    except InvalidTransitionError:
        raise HTTPException(status_code=409, detail="evaluation is not draft") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return _requirement_response(requirement)


@router.delete("/{evaluation_id}/requirements/{requirement_id}", status_code=204)
def delete_requirement(
    evaluation_id: str,
    requirement_id: str,
    context: ActorContext = Depends(require_owner),
    service: EvaluationService = Depends(get_evaluation_service),
) -> None:
    try:
        service.delete_requirement(context.tenant_id, evaluation_id, requirement_id, actor=context)
    except EvaluationNotFoundError:
        raise HTTPException(status_code=404) from None
    except RequirementNotFoundError:
        raise HTTPException(status_code=404) from None
    except InvalidTransitionError:
        raise HTTPException(status_code=409, detail="evaluation is not draft") from None


@router.post("/{evaluation_id}/vendors", response_model=ProposalSummaryResponse, status_code=201)
def link_vendor(
    evaluation_id: str,
    body: VendorLinkRequest,
    context: ActorContext = Depends(require_owner),
    service: EvaluationService = Depends(get_evaluation_service),
) -> ProposalSummaryResponse:
    try:
        proposal = service.link_vendor(
            context.tenant_id, evaluation_id, body.vendor_org_id, actor=context
        )
    except EvaluationNotFoundError:
        raise HTTPException(status_code=404) from None
    except VendorOrganizationNotFoundError:
        raise HTTPException(status_code=404) from None
    except InvalidTransitionError:
        raise HTTPException(status_code=409, detail="evaluation is not draft") from None
    except VendorLimitExceededError:
        raise HTTPException(status_code=400, detail="maximum of 6 linked vendors reached") from None
    except VendorAlreadyLinkedError:
        raise HTTPException(status_code=409, detail="vendor already linked") from None
    return ProposalSummaryResponse(
        id=proposal.id,
        evaluation_id=proposal.evaluation_id,
        vendor_org_id=proposal.vendor_org_id,
        status=proposal.status,
        version=proposal.version,
        created_at=proposal.created_at,
        updated_at=proposal.updated_at,
        submitted_at=proposal.submitted_at,
    )


@router.delete("/{evaluation_id}/vendors/{vendor_org_id}", status_code=204)
def unlink_vendor(
    evaluation_id: str,
    vendor_org_id: str,
    context: ActorContext = Depends(require_owner),
    service: EvaluationService = Depends(get_evaluation_service),
) -> None:
    try:
        service.unlink_vendor(context.tenant_id, evaluation_id, vendor_org_id, actor=context)
    except VendorNotLinkedError:
        raise HTTPException(status_code=404) from None
    except InvalidTransitionError:
        raise HTTPException(status_code=409) from None


@router.post("/{evaluation_id}/start-collection", response_model=EvaluationDetailResponse)
def start_collection(
    evaluation_id: str,
    context: ActorContext = Depends(require_owner),
    service: EvaluationService = Depends(get_evaluation_service),
) -> EvaluationDetailResponse:
    try:
        evaluation = service.start_collection(context.tenant_id, evaluation_id, actor=context)
    except EvaluationNotFoundError:
        raise HTTPException(status_code=404) from None
    except InvalidTransitionError:
        raise HTTPException(status_code=409, detail="evaluation is not draft") from None
    except StartCollectionPreconditionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return _evaluation_detail(evaluation)


@router.post("/{evaluation_id}/start-evaluation", response_model=EvaluationDetailResponse)
def start_evaluation(
    evaluation_id: str,
    context: ActorContext = Depends(require_owner),
    service: EvaluationService = Depends(get_evaluation_service),
) -> EvaluationDetailResponse:
    try:
        evaluation = service.start_evaluation(context.tenant_id, evaluation_id, actor=context)
    except EvaluationNotFoundError:
        raise HTTPException(status_code=404) from None
    except InvalidTransitionError:
        raise HTTPException(
            status_code=409, detail="evaluation is not collecting_responses"
        ) from None
    return _evaluation_detail(evaluation)
