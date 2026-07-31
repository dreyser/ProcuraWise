from fastapi import APIRouter, Depends, HTTPException

from procurawise.assignments.repository import AssignmentRepository
from procurawise.audit.repository import AuditEventRepository
from procurawise.audit.service import AuditEventService
from procurawise.evaluations.exceptions import CompletionPreconditionError, InvalidTransitionError
from procurawise.evaluations.exceptions import EvaluationNotFoundError as _EvaluationNotFoundError
from procurawise.evaluations.models import Evaluation
from procurawise.evaluations.repository import EvaluationRepository
from procurawise.evaluations.schemas import EvaluationDetailResponse, RequirementResponse
from procurawise.identity.repository import VendorOrganizationRepository
from procurawise.proposals.exceptions import ProposalNotFoundError
from procurawise.proposals.repository import ProposalRepository
from procurawise.scoring.exceptions import (
    RequirementNotInSnapshotError,
    ResultsNotAvailableError,
    ScoreOutOfRangeError,
    ScoringPreconditionError,
    SectionNotAssignedToActorError,
    StaleScoreVersionError,
)
from procurawise.scoring.repository import ScoreRepository
from procurawise.scoring.schemas import ResultsResponse, ScoreResponse, ScoreWriteRequest
from procurawise.scoring.service import ScoringService
from procurawise.shared.config import Settings, get_settings
from procurawise.shared.context import ActorContext, require_role
from procurawise.shared.mongo import get_database
from procurawise.shared.roles import BUYER_READ_ROLES, OWNER_ONLY, SCORE_WRITE_ROLES

router = APIRouter(prefix="/evaluations/{evaluation_id}", tags=["scoring"])

require_buyer_read = require_role(*BUYER_READ_ROLES)
require_owner = require_role(*OWNER_ONLY)
require_score_write = require_role(*SCORE_WRITE_ROLES)


def get_scoring_service(settings: Settings = Depends(get_settings)) -> ScoringService:
    db = get_database(settings)
    return ScoringService(
        scores=ScoreRepository(db),
        proposals=ProposalRepository(db),
        evaluations=EvaluationRepository(db),
        vendor_orgs=VendorOrganizationRepository(db),
        audit=AuditEventService(AuditEventRepository(db), settings),
        assignments=AssignmentRepository(db),
    )


def _evaluation_detail(evaluation: Evaluation) -> EvaluationDetailResponse:
    return EvaluationDetailResponse(
        id=evaluation.id,
        name=evaluation.name,
        description=evaluation.description,
        status=evaluation.status,
        requirements=[
            RequirementResponse(
                id=r.id,
                dimension=r.dimension,
                category=r.category,
                title=r.title,
                description=r.description,
                priority=r.priority,
                response_type=r.response_type,
                weight=r.weight,
                required=r.required,
                buyer_guidance=r.buyer_guidance,
                display_order=r.display_order,
                options=r.options,
                created_at=r.created_at,
                updated_at=r.updated_at,
            )
            for r in evaluation.requirements
        ],
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
    )


@router.put(
    "/proposals/{proposal_id}/scores/{requirement_id}",
    response_model=ScoreResponse,
)
def upsert_score(
    evaluation_id: str,
    proposal_id: str,
    requirement_id: str,
    body: ScoreWriteRequest,
    context: ActorContext = Depends(require_score_write),
    service: ScoringService = Depends(get_scoring_service),
) -> ScoreResponse:
    try:
        score = service.upsert_score(
            context.tenant_id,
            evaluation_id,
            proposal_id,
            requirement_id,
            body.score,
            body.comment,
            body.version,
            context.membership_id,
            actor=context,
        )
    except (_EvaluationNotFoundError, ProposalNotFoundError):
        raise HTTPException(status_code=404) from None
    except ScoreOutOfRangeError:
        raise HTTPException(status_code=400, detail="score must be between 0 and 5") from None
    except RequirementNotInSnapshotError:
        raise HTTPException(
            status_code=400, detail="requirement not in proposal snapshot"
        ) from None
    except SectionNotAssignedToActorError:
        raise HTTPException(
            status_code=403, detail="requirement's section is not assigned to this evaluator"
        ) from None
    except ScoringPreconditionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except StaleScoreVersionError:
        raise HTTPException(status_code=409, detail="stale score version") from None

    return ScoreResponse(
        id=score.id,
        requirement_id=score.requirement_id,
        dimension=score.dimension,
        priority=score.priority,
        requirement_weight=score.requirement_weight,
        score=score.score,
        comment=score.comment,
        weighted_points=score.weighted_points,
        mandatory_alert=score.mandatory_alert,
        version=score.version,
        created_by_membership_id=score.created_by_membership_id,
        updated_by_membership_id=score.updated_by_membership_id,
        created_at=score.created_at,
        updated_at=score.updated_at,
    )


@router.get("/results", response_model=ResultsResponse)
def get_results(
    evaluation_id: str,
    context: ActorContext = Depends(require_buyer_read),
    service: ScoringService = Depends(get_scoring_service),
) -> ResultsResponse:
    try:
        data = service.get_results(context.tenant_id, evaluation_id)
    except _EvaluationNotFoundError:
        raise HTTPException(status_code=404) from None
    except ResultsNotAvailableError:
        raise HTTPException(
            status_code=409, detail="results are not available before evaluating"
        ) from None
    return ResultsResponse.model_validate(data)


@router.post("/complete", response_model=EvaluationDetailResponse)
def complete_evaluation(
    evaluation_id: str,
    context: ActorContext = Depends(require_owner),
    service: ScoringService = Depends(get_scoring_service),
) -> EvaluationDetailResponse:
    try:
        evaluation = service.complete_evaluation(context.tenant_id, evaluation_id, actor=context)
    except _EvaluationNotFoundError:
        raise HTTPException(status_code=404) from None
    except InvalidTransitionError:
        raise HTTPException(status_code=409, detail="evaluation is not evaluating") from None
    except CompletionPreconditionError as exc:
        raise HTTPException(
            status_code=400, detail=f"not all submitted proposals are fully scored: {exc}"
        ) from None

    return _evaluation_detail(evaluation)
