from datetime import UTC, datetime

from procurawise.audit.service import AuditEventService
from procurawise.evaluations.exceptions import EvaluationNotFoundError, RequirementNotFoundError
from procurawise.evaluations.models import Evaluation
from procurawise.evaluations.repository import EvaluationRepository
from procurawise.proposals.exceptions import ProposalNotFoundError
from procurawise.proposals.models import Proposal
from procurawise.proposals.repository import ProposalRepository
from procurawise.qna.exceptions import (
    InvalidQuestionTransitionError,
    QuestionNotFoundError,
    QuestionValidationError,
    StaleQuestionVersionError,
)
from procurawise.qna.models import AnswerVersion, AnswerVisibility, Question, QuestionScope
from procurawise.qna.repository import QuestionRepository
from procurawise.shared.context import ActorContext


class QuestionService:
    """Fase 17: orchestrates the vendor-question -> buyer-answer(+visibility)
    loop. Mirrors documents.service's composition shape (repository + parent
    repositories + audit) and its authorization anchor (a Question always
    resolves through its own Proposal for the vendor side, through its own
    Evaluation for the buyer side) - see qna plan §11.3."""

    def __init__(
        self,
        questions: QuestionRepository,
        proposals: ProposalRepository,
        evaluations: EvaluationRepository,
        audit: AuditEventService,
    ) -> None:
        self._questions = questions
        self._proposals = proposals
        self._evaluations = evaluations
        self._audit = audit

    def _get_proposal(self, tenant_id: str, proposal_id: str) -> Proposal:
        doc = self._proposals.find_by_id(tenant_id, proposal_id)
        if doc is None:
            raise ProposalNotFoundError(proposal_id)
        return Proposal.from_document(doc)

    def _get_vendor_proposal(
        self, tenant_id: str, vendor_org_id: str, proposal_id: str
    ) -> Proposal:
        proposal = self._get_proposal(tenant_id, proposal_id)
        if proposal.vendor_org_id != vendor_org_id:
            # Collapses to the same ProposalNotFoundError/404 as "does not
            # exist at all" - never confirming existence of another
            # vendor's proposal, same principle as documents.service.
            raise ProposalNotFoundError(proposal_id)
        return proposal

    def _get_evaluation(self, tenant_id: str, evaluation_id: str) -> Evaluation:
        doc = self._evaluations.find_by_id(tenant_id, evaluation_id)
        if doc is None:
            raise EvaluationNotFoundError(evaluation_id)
        return Evaluation.from_document(doc)

    def _require_collecting_responses(self, evaluation: Evaluation) -> None:
        if evaluation.status != "collecting_responses":
            raise InvalidQuestionTransitionError("evaluation is not collecting_responses")

    def _resolve_question(self, tenant_id: str, proposal_id: str, question_id: str) -> Question:
        doc = self._questions.find_by_id(tenant_id, question_id)
        if doc is None or doc["proposal_id"] != proposal_id:
            raise QuestionNotFoundError(question_id)
        return Question.from_document(doc)

    def create_question(
        self,
        tenant_id: str,
        vendor_org_id: str,
        proposal_id: str,
        scope: QuestionScope,
        requirement_id: str | None,
        body: str,
        *,
        actor: ActorContext,
    ) -> Question:
        proposal = self._get_vendor_proposal(tenant_id, vendor_org_id, proposal_id)
        evaluation = self._get_evaluation(tenant_id, proposal.evaluation_id)
        self._require_collecting_responses(evaluation)

        if scope == "requirement":
            if requirement_id is None:
                raise QuestionValidationError(
                    "requirement_id is required when scope is requirement"
                )
            if not any(r.id == requirement_id for r in evaluation.requirements):
                raise RequirementNotFoundError(requirement_id)
        elif requirement_id is not None:
            raise QuestionValidationError("requirement_id must be empty when scope is general")

        question = Question.create(
            tenant_id=tenant_id,
            evaluation_id=evaluation.id,
            proposal_id=proposal_id,
            vendor_org_id=vendor_org_id,
            requirement_id=requirement_id,
            scope=scope,
            body=body,
            created_by_membership_id=actor.membership_id,
        )
        self._questions.insert(tenant_id, question.to_document())
        self._audit.record(
            tenant_id=tenant_id,
            actor=actor,
            action="qna_question_created",
            resource_type="qna_question",
            resource_id=question.id,
            evaluation_id=evaluation.id,
            proposal_id=proposal_id,
            metadata={"scope": scope, "requirement_id": requirement_id},
        )
        return question

    def withdraw_question(
        self,
        tenant_id: str,
        vendor_org_id: str,
        proposal_id: str,
        question_id: str,
        *,
        actor: ActorContext,
    ) -> None:
        proposal = self._get_vendor_proposal(tenant_id, vendor_org_id, proposal_id)
        evaluation = self._get_evaluation(tenant_id, proposal.evaluation_id)
        self._require_collecting_responses(evaluation)

        question = self._resolve_question(tenant_id, proposal_id, question_id)
        if question.status != "open":
            raise InvalidQuestionTransitionError("question is not open")

        withdrawn = self._questions.withdraw(tenant_id, question_id)
        if not withdrawn:
            raise QuestionNotFoundError(question_id)

        self._audit.record(
            tenant_id=tenant_id,
            actor=actor,
            action="qna_question_withdrawn",
            resource_type="qna_question",
            resource_id=question_id,
            evaluation_id=evaluation.id,
            proposal_id=proposal_id,
        )

    def list_for_proposal(
        self, tenant_id: str, vendor_org_id: str, proposal_id: str
    ) -> list[Question]:
        self._get_vendor_proposal(tenant_id, vendor_org_id, proposal_id)
        return [
            Question.from_document(d)
            for d in self._questions.list_for_proposal(tenant_id, proposal_id)
        ]

    def list_published_for_evaluation(
        self, tenant_id: str, vendor_org_id: str, proposal_id: str
    ) -> list[Question]:
        proposal = self._get_vendor_proposal(tenant_id, vendor_org_id, proposal_id)
        return [
            Question.from_document(d)
            for d in self._questions.list_published_for_evaluation(
                tenant_id, proposal.evaluation_id, vendor_org_id
            )
        ]

    def list_for_evaluation_as_buyer(self, tenant_id: str, evaluation_id: str) -> list[Question]:
        self._get_evaluation(tenant_id, evaluation_id)
        return [
            Question.from_document(d)
            for d in self._questions.list_for_evaluation_as_buyer(tenant_id, evaluation_id)
        ]

    def publish_answer(
        self,
        tenant_id: str,
        evaluation_id: str,
        question_id: str,
        body: str,
        visibility: AnswerVisibility,
        expected_version: int,
        *,
        actor: ActorContext,
    ) -> Question:
        evaluation = self._get_evaluation(tenant_id, evaluation_id)
        self._require_collecting_responses(evaluation)

        doc = self._questions.find_by_id(tenant_id, question_id)
        if doc is None or doc["evaluation_id"] != evaluation_id:
            raise QuestionNotFoundError(question_id)
        question = Question.from_document(doc)
        if question.version != expected_version:
            raise StaleQuestionVersionError(question_id)

        next_version = question.current_answer.version + 1 if question.current_answer else 1
        new_answer = AnswerVersion(
            version=next_version,
            body=body,
            visibility=visibility,
            answered_by_membership_id=actor.membership_id,
            answered_at=datetime.now(UTC),
        )
        new_history = list(question.answer_history)
        if question.current_answer is not None:
            new_history.append(question.current_answer)

        applied = self._questions.publish_answer(
            tenant_id,
            question_id,
            expected_version,
            current_answer=new_answer.to_document(),
            answer_history=[a.to_document() for a in new_history],
        )
        if not applied:
            raise StaleQuestionVersionError(question_id)

        self._audit.record(
            tenant_id=tenant_id,
            actor=actor,
            action="qna_answer_published",
            resource_type="qna_question",
            resource_id=question_id,
            evaluation_id=evaluation_id,
            proposal_id=question.proposal_id,
            metadata={"version": next_version, "visibility": visibility},
        )

        refreshed = self._questions.find_by_id(tenant_id, question_id)
        assert refreshed is not None  # just written above, in the same tenant scope
        return Question.from_document(refreshed)
