from fastapi import APIRouter, Depends, HTTPException

from procurawise.ai.repository import AIExecutionRepository
from procurawise.assignments.repository import AssignmentRepository
from procurawise.audit.repository import AuditEventRepository
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
from procurawise.decisions.models import Decision, DecisionSnapshot
from procurawise.decisions.repository import DecisionRepository
from procurawise.decisions.schemas import (
    DecisionApprovalRequest,
    DecisionReadinessResponse,
    DecisionRejectionRequest,
    DecisionResponse,
    DecisionSnapshotResponse,
    DecisionUpdateRequest,
    SetDecisionApproverRequest,
)
from procurawise.decisions.service import DecisionService
from procurawise.decisions.snapshot_repository import DecisionSnapshotRepository
from procurawise.evaluations.exceptions import EvaluationNotFoundError
from procurawise.evaluations.repository import EvaluationRepository
from procurawise.identity.repository import MembershipRepository, VendorOrganizationRepository
from procurawise.notifications.dependencies import build_notification_service
from procurawise.proposals.repository import ProposalRepository
from procurawise.scoring.repository import EconomicAssessmentRepository, ScoreRepository
from procurawise.scoring.service import ScoringService
from procurawise.shared.config import Settings, get_settings
from procurawise.shared.context import ActorContext, require_role
from procurawise.shared.mongo import get_database
from procurawise.shared.roles import BUYER_READ_ROLES, OWNER_ONLY

router = APIRouter(prefix="/evaluations/{evaluation_id}/decision", tags=["decisions"])

require_buyer_read = require_role(*BUYER_READ_ROLES)
require_owner = require_role(*OWNER_ONLY)
# Only gates "holds the approver role at all" - the service layer further
# restricts approve/reject to the Decision's own assigned
# approver_membership_id (never Evaluation.approver_membership_id, see plan
# Bloqueante #1, Opcion B).
require_approver = require_role("approver")


def get_decision_service(settings: Settings = Depends(get_settings)) -> DecisionService:
    db = get_database(settings)
    audit = AuditEventService(AuditEventRepository(db), settings)
    notifications = build_notification_service(settings)
    scoring = ScoringService(
        scores=ScoreRepository(db),
        proposals=ProposalRepository(db),
        evaluations=EvaluationRepository(db),
        vendor_orgs=VendorOrganizationRepository(db),
        audit=audit,
        assignments=AssignmentRepository(db),
        ai_executions=AIExecutionRepository(db),
        economic_assessments=EconomicAssessmentRepository(db),
        notifications=notifications,
    )
    return DecisionService(
        decisions=DecisionRepository(db),
        snapshots=DecisionSnapshotRepository(db),
        evaluations=EvaluationRepository(db),
        proposals=ProposalRepository(db),
        vendor_orgs=VendorOrganizationRepository(db),
        memberships=MembershipRepository(db),
        scoring=scoring,
        audit=audit,
        notifications=notifications,
    )


def _decision_response(decision: Decision) -> DecisionResponse:
    return DecisionResponse(
        id=decision.id,
        evaluation_id=decision.evaluation_id,
        status=decision.status,
        outcome=decision.outcome,
        selected_vendor_org_id=decision.selected_vendor_org_id,
        selected_proposal_id=decision.selected_proposal_id,
        selected_proposal_snapshot_id=decision.selected_proposal_snapshot_id,
        void_reason=decision.void_reason,
        justification=decision.justification,
        approver_membership_id=decision.approver_membership_id,
        created_by_membership_id=decision.created_by_membership_id,
        created_at=decision.created_at,
        updated_at=decision.updated_at,
        approval_requested_at=decision.approval_requested_at,
        approval_requested_by_membership_id=decision.approval_requested_by_membership_id,
        approval_decided_at=decision.approval_decided_at,
        approval_decided_by_membership_id=decision.approval_decided_by_membership_id,
        approval_comment=decision.approval_comment,
        decision_snapshot_id=decision.decision_snapshot_id,
    )


def _snapshot_response(snapshot: DecisionSnapshot) -> DecisionSnapshotResponse:
    return DecisionSnapshotResponse(
        snapshot_id=snapshot.snapshot_id,
        evaluation_id=snapshot.evaluation_id,
        outcome=snapshot.outcome,
        selected_vendor_org_id=snapshot.selected_vendor_org_id,
        selected_vendor_org_name=snapshot.selected_vendor_org_name,
        selected_proposal_id=snapshot.selected_proposal_id,
        selected_proposal_snapshot_id=snapshot.selected_proposal_snapshot_id,
        void_reason=snapshot.void_reason,
        justification=snapshot.justification,
        approver_membership_id=snapshot.approver_membership_id,
        decided_at=snapshot.decided_at,
        decided_by_membership_id=snapshot.decided_by_membership_id,
        proposal_results=snapshot.proposal_results,
        taken_at=snapshot.taken_at,
    )


@router.get("", response_model=DecisionResponse)
def get_decision(
    evaluation_id: str,
    context: ActorContext = Depends(require_buyer_read),
    service: DecisionService = Depends(get_decision_service),
) -> DecisionResponse:
    try:
        decision = service.get(context.tenant_id, evaluation_id)
    except DecisionNotFoundError:
        raise HTTPException(status_code=404) from None
    return _decision_response(decision)


@router.get("/readiness", response_model=DecisionReadinessResponse)
def get_readiness(
    evaluation_id: str,
    context: ActorContext = Depends(require_buyer_read),
    service: DecisionService = Depends(get_decision_service),
) -> DecisionReadinessResponse:
    try:
        readiness = service.readiness(context.tenant_id, evaluation_id)
    except EvaluationNotFoundError:
        raise HTTPException(status_code=404) from None
    return DecisionReadinessResponse(**readiness)


@router.post("", response_model=DecisionResponse, status_code=201)
def create_decision(
    evaluation_id: str,
    context: ActorContext = Depends(require_owner),
    service: DecisionService = Depends(get_decision_service),
) -> DecisionResponse:
    try:
        decision = service.create(context.tenant_id, evaluation_id, actor=context)
    except EvaluationNotFoundError:
        raise HTTPException(status_code=404) from None
    except EvaluationNotCompletedError:
        raise HTTPException(status_code=409, detail="evaluation is not completed") from None
    except DecisionAlreadyExistsError:
        raise HTTPException(
            status_code=409, detail="a decision already exists for this evaluation"
        ) from None
    return _decision_response(decision)


@router.patch("", response_model=DecisionResponse)
def update_decision(
    evaluation_id: str,
    body: DecisionUpdateRequest,
    context: ActorContext = Depends(require_owner),
    service: DecisionService = Depends(get_decision_service),
) -> DecisionResponse:
    fields_set = body.model_fields_set
    try:
        decision = service.update_selection(
            context.tenant_id,
            evaluation_id,
            outcome=body.outcome,
            selected_vendor_org_id=body.selected_vendor_org_id,
            void_reason=body.void_reason,
            justification=body.justification,
            fields_set=fields_set,
            actor=context,
        )
    except DecisionNotFoundError:
        raise HTTPException(status_code=404) from None
    except InvalidDecisionStateError:
        raise HTTPException(
            status_code=409, detail="decision cannot be edited in its current status"
        ) from None
    except SelectedProposalNotFoundError:
        raise HTTPException(
            status_code=422, detail="selected vendor has no submitted proposal on this evaluation"
        ) from None
    return _decision_response(decision)


@router.post("/approver", response_model=DecisionResponse)
def set_decision_approver(
    evaluation_id: str,
    body: SetDecisionApproverRequest,
    context: ActorContext = Depends(require_owner),
    service: DecisionService = Depends(get_decision_service),
) -> DecisionResponse:
    try:
        decision = service.set_approver(
            context.tenant_id, evaluation_id, body.approver_membership_id, actor=context
        )
    except DecisionNotFoundError:
        raise HTTPException(status_code=404) from None
    except ApproverMembershipNotFoundError:
        raise HTTPException(status_code=404, detail="approver membership not found") from None
    except ApproverRoleMismatchError:
        raise HTTPException(
            status_code=400, detail="target membership does not hold the approver role"
        ) from None
    except SelfApprovalError:
        raise HTTPException(
            status_code=400, detail="the evaluation owner may not be their own decision approver"
        ) from None
    except InvalidDecisionStateError:
        raise HTTPException(
            status_code=409, detail="decision cannot be edited in its current status"
        ) from None
    return _decision_response(decision)


@router.post("/request-approval", response_model=DecisionResponse)
def request_decision_approval(
    evaluation_id: str,
    context: ActorContext = Depends(require_owner),
    service: DecisionService = Depends(get_decision_service),
) -> DecisionResponse:
    try:
        decision = service.request_approval(context.tenant_id, evaluation_id, actor=context)
    except DecisionNotFoundError:
        raise HTTPException(status_code=404) from None
    except InvalidDecisionStateError:
        raise HTTPException(
            status_code=409, detail="decision cannot be edited in its current status"
        ) from None
    except DecisionPreconditionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return _decision_response(decision)


@router.delete("/request-approval", status_code=204)
def withdraw_decision_approval_request(
    evaluation_id: str,
    context: ActorContext = Depends(require_owner),
    service: DecisionService = Depends(get_decision_service),
) -> None:
    try:
        service.withdraw_approval_request(context.tenant_id, evaluation_id, actor=context)
    except DecisionNotFoundError:
        raise HTTPException(status_code=404) from None
    except InvalidDecisionStateError:
        raise HTTPException(status_code=409, detail="decision approval is not pending") from None


@router.post("/approve", response_model=DecisionResponse)
def approve_decision(
    evaluation_id: str,
    body: DecisionApprovalRequest,
    context: ActorContext = Depends(require_approver),
    service: DecisionService = Depends(get_decision_service),
) -> DecisionResponse:
    try:
        decision = service.approve(context.tenant_id, evaluation_id, body.comment, actor=context)
    except DecisionNotFoundError:
        raise HTTPException(status_code=404) from None
    except NotAssignedApproverError:
        raise HTTPException(
            status_code=403, detail="only the decision's assigned approver may decide it"
        ) from None
    except InvalidDecisionStateError:
        raise HTTPException(status_code=409, detail="decision approval is not pending") from None
    return _decision_response(decision)


@router.post("/reject", response_model=DecisionResponse)
def reject_decision(
    evaluation_id: str,
    body: DecisionRejectionRequest,
    context: ActorContext = Depends(require_approver),
    service: DecisionService = Depends(get_decision_service),
) -> DecisionResponse:
    try:
        decision = service.reject(context.tenant_id, evaluation_id, body.comment, actor=context)
    except DecisionNotFoundError:
        raise HTTPException(status_code=404) from None
    except NotAssignedApproverError:
        raise HTTPException(
            status_code=403, detail="only the decision's assigned approver may decide it"
        ) from None
    except InvalidDecisionStateError:
        raise HTTPException(status_code=409, detail="decision approval is not pending") from None
    return _decision_response(decision)


@router.get("/snapshot", response_model=DecisionSnapshotResponse)
def get_decision_snapshot(
    evaluation_id: str,
    context: ActorContext = Depends(require_buyer_read),
    service: DecisionService = Depends(get_decision_service),
) -> DecisionSnapshotResponse:
    try:
        snapshot = service.get_snapshot(context.tenant_id, evaluation_id)
    except DecisionSnapshotNotFoundError:
        raise HTTPException(status_code=404) from None
    return _snapshot_response(snapshot)
