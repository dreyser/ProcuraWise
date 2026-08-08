from fastapi import APIRouter, Depends, HTTPException

from procurawise.audit.repository import AuditEventRepository
from procurawise.audit.service import AuditEventService
from procurawise.evaluations.exceptions import EvaluationNotFoundError, RequirementNotFoundError
from procurawise.evaluations.repository import EvaluationRepository
from procurawise.identity.repository import MembershipRepository
from procurawise.notifications.dependencies import build_notification_service
from procurawise.proposals.exceptions import ProposalNotFoundError
from procurawise.proposals.repository import ProposalRepository
from procurawise.qna.exceptions import (
    InvalidQuestionTransitionError,
    QuestionNotFoundError,
    QuestionValidationError,
    StaleQuestionVersionError,
)
from procurawise.qna.models import AnswerVersion, Question
from procurawise.qna.repository import QuestionRepository
from procurawise.qna.schemas import (
    AnswerVersionResponse,
    BuyerQuestionListResponse,
    BuyerQuestionResponse,
    PublicQuestionListResponse,
    PublicQuestionResponse,
    PublishAnswerRequest,
    QuestionCreateRequest,
    VendorQuestionListResponse,
    VendorQuestionResponse,
)
from procurawise.qna.service import QuestionService
from procurawise.shared.config import Settings, get_settings
from procurawise.shared.context import ActorContext, require_role
from procurawise.shared.mongo import get_database
from procurawise.shared.roles import BUYER_READ_ROLES, OWNER_ONLY
from procurawise.vendor_portal.dependencies import require_agreements_accepted

vendor_qna_router = APIRouter(
    prefix="/vendor-portal/proposals/{proposal_id}/questions", tags=["vendor-portal-qna"]
)
buyer_qna_router = APIRouter(
    prefix="/evaluations/{evaluation_id}/questions", tags=["evaluation-qna"]
)

require_buyer_read = require_role(*BUYER_READ_ROLES)
require_owner = require_role(*OWNER_ONLY)


def get_question_service(settings: Settings = Depends(get_settings)) -> QuestionService:
    db = get_database(settings)
    return QuestionService(
        questions=QuestionRepository(db),
        proposals=ProposalRepository(db),
        evaluations=EvaluationRepository(db),
        memberships=MembershipRepository(db),
        audit=AuditEventService(AuditEventRepository(db), settings),
        notifications=build_notification_service(settings),
    )


def _answer_response(answer: AnswerVersion) -> AnswerVersionResponse:
    return AnswerVersionResponse(
        version=answer.version,
        body=answer.body,
        visibility=answer.visibility,
        answered_by_membership_id=answer.answered_by_membership_id,
        answered_at=answer.answered_at,
    )


def _vendor_response(question: Question) -> VendorQuestionResponse:
    return VendorQuestionResponse(
        id=question.id,
        proposal_id=question.proposal_id,
        requirement_id=question.requirement_id,
        scope=question.scope,
        body=question.body,
        status=question.status,
        version=question.version,
        created_at=question.created_at,
        current_answer=_answer_response(question.current_answer)
        if question.current_answer
        else None,
        answer_history=[_answer_response(a) for a in question.answer_history],
    )


def _public_response(question: Question) -> PublicQuestionResponse:
    return PublicQuestionResponse(
        id=question.id,
        requirement_id=question.requirement_id,
        scope=question.scope,
        body=question.body,
        current_answer=_answer_response(question.current_answer)
        if question.current_answer
        else None,
    )


def _buyer_response(question: Question) -> BuyerQuestionResponse:
    return BuyerQuestionResponse(
        id=question.id,
        proposal_id=question.proposal_id,
        vendor_org_id=question.vendor_org_id,
        requirement_id=question.requirement_id,
        scope=question.scope,
        body=question.body,
        status=question.status,
        version=question.version,
        created_by_membership_id=question.created_by_membership_id,
        created_at=question.created_at,
        current_answer=_answer_response(question.current_answer)
        if question.current_answer
        else None,
        answer_history=[_answer_response(a) for a in question.answer_history],
    )


@vendor_qna_router.post("", response_model=VendorQuestionResponse, status_code=201)
def create_question(
    proposal_id: str,
    body: QuestionCreateRequest,
    context: ActorContext = Depends(require_agreements_accepted),
    service: QuestionService = Depends(get_question_service),
) -> VendorQuestionResponse:
    assert context.vendor_org_id is not None
    try:
        question = service.create_question(
            context.tenant_id,
            context.vendor_org_id,
            proposal_id,
            body.scope,
            body.requirement_id,
            body.body,
            actor=context,
        )
    except ProposalNotFoundError:
        raise HTTPException(status_code=404) from None
    except EvaluationNotFoundError:
        raise HTTPException(status_code=404) from None
    except RequirementNotFoundError:
        raise HTTPException(status_code=404) from None
    except InvalidQuestionTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except QuestionValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return _vendor_response(question)


@vendor_qna_router.get("", response_model=VendorQuestionListResponse)
def list_questions(
    proposal_id: str,
    context: ActorContext = Depends(require_agreements_accepted),
    service: QuestionService = Depends(get_question_service),
) -> VendorQuestionListResponse:
    assert context.vendor_org_id is not None
    try:
        questions = service.list_for_proposal(context.tenant_id, context.vendor_org_id, proposal_id)
    except ProposalNotFoundError:
        raise HTTPException(status_code=404) from None
    return VendorQuestionListResponse(items=[_vendor_response(q) for q in questions])


@vendor_qna_router.get("/published", response_model=PublicQuestionListResponse)
def list_published_questions(
    proposal_id: str,
    context: ActorContext = Depends(require_agreements_accepted),
    service: QuestionService = Depends(get_question_service),
) -> PublicQuestionListResponse:
    assert context.vendor_org_id is not None
    try:
        questions = service.list_published_for_evaluation(
            context.tenant_id, context.vendor_org_id, proposal_id
        )
    except ProposalNotFoundError:
        raise HTTPException(status_code=404) from None
    return PublicQuestionListResponse(items=[_public_response(q) for q in questions])


@vendor_qna_router.delete("/{question_id}", status_code=204)
def withdraw_question(
    proposal_id: str,
    question_id: str,
    context: ActorContext = Depends(require_agreements_accepted),
    service: QuestionService = Depends(get_question_service),
) -> None:
    assert context.vendor_org_id is not None
    try:
        service.withdraw_question(
            context.tenant_id, context.vendor_org_id, proposal_id, question_id, actor=context
        )
    except ProposalNotFoundError:
        raise HTTPException(status_code=404) from None
    except EvaluationNotFoundError:
        raise HTTPException(status_code=404) from None
    except InvalidQuestionTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except QuestionNotFoundError:
        raise HTTPException(status_code=404) from None


@buyer_qna_router.get("", response_model=BuyerQuestionListResponse)
def list_questions_as_buyer(
    evaluation_id: str,
    context: ActorContext = Depends(require_buyer_read),
    service: QuestionService = Depends(get_question_service),
) -> BuyerQuestionListResponse:
    try:
        questions = service.list_for_evaluation_as_buyer(context.tenant_id, evaluation_id)
    except EvaluationNotFoundError:
        raise HTTPException(status_code=404) from None
    return BuyerQuestionListResponse(items=[_buyer_response(q) for q in questions])


@buyer_qna_router.put("/{question_id}/answer", response_model=BuyerQuestionResponse)
def publish_answer(
    evaluation_id: str,
    question_id: str,
    body: PublishAnswerRequest,
    context: ActorContext = Depends(require_owner),
    service: QuestionService = Depends(get_question_service),
) -> BuyerQuestionResponse:
    try:
        question = service.publish_answer(
            context.tenant_id,
            evaluation_id,
            question_id,
            body.body,
            body.visibility,
            body.expected_version,
            actor=context,
        )
    except EvaluationNotFoundError:
        raise HTTPException(status_code=404) from None
    except QuestionNotFoundError:
        raise HTTPException(status_code=404) from None
    except InvalidQuestionTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except StaleQuestionVersionError:
        raise HTTPException(status_code=409, detail="stale version") from None
    return _buyer_response(question)
