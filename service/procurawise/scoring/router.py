from fastapi import APIRouter, Depends, HTTPException

from procurawise.ai.repository import AIExecutionRepository
from procurawise.assignments.repository import AssignmentRepository
from procurawise.audit.repository import AuditEventRepository
from procurawise.audit.service import AuditEventService
from procurawise.evaluations.exceptions import CompletionPreconditionError, InvalidTransitionError
from procurawise.evaluations.exceptions import EvaluationNotFoundError as _EvaluationNotFoundError
from procurawise.evaluations.models import Evaluation
from procurawise.evaluations.repository import EvaluationRepository
from procurawise.evaluations.schemas import (
    EconomicCriteriaWeightsResponse,
    EvaluationDetailResponse,
    RequirementResponse,
)
from procurawise.identity.repository import VendorOrganizationRepository
from procurawise.proposals.exceptions import ProposalNotFoundError
from procurawise.proposals.repository import ProposalRepository
from procurawise.scoring.exceptions import (
    EconomicAssessmentNotFoundError,
    InvalidCriterionScoreError,
    RequirementNotInSnapshotError,
    ResultsNotAvailableError,
    ScoreOutOfRangeError,
    ScoringPreconditionError,
    SectionNotAssignedToActorError,
    StaleEconomicAssessmentVersionError,
    StaleScoreVersionError,
)
from procurawise.scoring.models import CriterionScore, EconomicAssessment
from procurawise.scoring.repository import EconomicAssessmentRepository, ScoreRepository
from procurawise.scoring.schemas import (
    CriterionScoreResponse,
    EconomicAssessmentResponse,
    EconomicAssessmentWriteRequest,
    ResultsResponse,
    ScoreResponse,
    ScoreWriteRequest,
)
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
        ai_executions=AIExecutionRepository(db),
        economic_assessments=EconomicAssessmentRepository(db),
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
        base_currency=evaluation.base_currency,
        tco_horizon_years=evaluation.tco_horizon_years,
        economic_criteria_weights=EconomicCriteriaWeightsResponse(
            commercial=evaluation.economic_criteria_weights.commercial,
            risk=evaluation.economic_criteria_weights.risk,
        ),
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
            source_ai_execution_id=body.source_ai_execution_id,
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
        source_ai_execution_id=score.source_ai_execution_id,
    )


def _economic_assessment_response(assessment: EconomicAssessment) -> EconomicAssessmentResponse:
    return EconomicAssessmentResponse(
        id=assessment.id,
        evaluation_id=assessment.evaluation_id,
        proposal_id=assessment.proposal_id,
        commercial_scores=[
            CriterionScoreResponse(criterion_key=s.criterion_key, score=s.score, comment=s.comment)
            for s in assessment.commercial_scores
        ],
        risk_scores=[
            CriterionScoreResponse(criterion_key=s.criterion_key, score=s.score, comment=s.comment)
            for s in assessment.risk_scores
        ],
        version=assessment.version,
        created_by_membership_id=assessment.created_by_membership_id,
        updated_by_membership_id=assessment.updated_by_membership_id,
        created_at=assessment.created_at,
        updated_at=assessment.updated_at,
    )


@router.put(
    "/proposals/{proposal_id}/economic-assessment",
    response_model=EconomicAssessmentResponse,
)
def upsert_economic_assessment(
    evaluation_id: str,
    proposal_id: str,
    body: EconomicAssessmentWriteRequest,
    context: ActorContext = Depends(require_score_write),
    service: ScoringService = Depends(get_scoring_service),
) -> EconomicAssessmentResponse:
    """Fase 20 (ADR 0009) - same role gate as upsert_score (SCORE_WRITE_ROLES),
    plus enforce_section_assignment reused with the fixed "economic" sentinel
    (see assignments.service.ECONOMIC_SECTION)."""
    try:
        assessment = service.upsert_economic_assessment(
            context.tenant_id,
            evaluation_id,
            proposal_id,
            [
                CriterionScore(criterion_key=s.criterion_key, score=s.score, comment=s.comment)
                for s in body.commercial_scores
            ],
            [
                CriterionScore(criterion_key=s.criterion_key, score=s.score, comment=s.comment)
                for s in body.risk_scores
            ],
            body.version,
            context.membership_id,
            actor=context,
        )
    except (_EvaluationNotFoundError, ProposalNotFoundError):
        raise HTTPException(status_code=404) from None
    except InvalidCriterionScoreError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except SectionNotAssignedToActorError:
        raise HTTPException(
            status_code=403, detail="economic dimension is not assigned to this evaluator"
        ) from None
    except ScoringPreconditionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except StaleEconomicAssessmentVersionError:
        raise HTTPException(status_code=409, detail="stale economic assessment version") from None
    return _economic_assessment_response(assessment)


@router.get(
    "/proposals/{proposal_id}/economic-assessment",
    response_model=EconomicAssessmentResponse,
)
def get_economic_assessment(
    evaluation_id: str,
    proposal_id: str,
    context: ActorContext = Depends(require_buyer_read),
    service: ScoringService = Depends(get_scoring_service),
) -> EconomicAssessmentResponse:
    """Fase 20 - the read surface a client needs before it can build a valid
    upsert_economic_assessment call (current scores + version), same role as
    /results is for Score. 404 both when the proposal doesn't exist and when
    it exists but has no EconomicAssessment yet - the client can't tell (and
    doesn't need to) which case it is; either way the form starts empty."""
    try:
        assessment = service.get_economic_assessment(context.tenant_id, evaluation_id, proposal_id)
    except (ProposalNotFoundError, EconomicAssessmentNotFoundError):
        raise HTTPException(status_code=404) from None
    return _economic_assessment_response(assessment)


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
