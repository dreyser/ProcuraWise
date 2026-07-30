from datetime import UTC, date, datetime
from typing import Any
from uuid import uuid4

from procurawise.audit.service import AuditEventService
from procurawise.evaluations.exceptions import RequirementNotFoundError
from procurawise.evaluations.models import Evaluation, Requirement
from procurawise.evaluations.repository import EvaluationRepository
from procurawise.identity.repository import VendorOrganizationRepository
from procurawise.proposals.exceptions import (
    AnswerValidationError,
    IncompleteRequiredAnswersError,
    InvalidProposalTransitionError,
    ProposalNotFoundError,
    StaleVersionError,
)
from procurawise.proposals.models import Proposal, ProposalAnswer, ProposalSnapshot
from procurawise.proposals.repository import ProposalRepository
from procurawise.shared.context import ActorContext

_CURRENCY_CODES = {"MXN", "USD"}
_COMPLIANCE_VALUES = {"compliant", "partially_compliant", "non_compliant"}


def validate_answer_value(requirement: Requirement, value: Any) -> None:
    """One branch per response_type (plan §15) - no plugin/validator
    framework, just a direct dispatch. `value is None` represents "not
    answered yet" and is always accepted here; completeness for `required`
    requirements is enforced separately at submit time."""
    if value is None:
        return

    response_type = requirement.response_type
    if response_type == "compliant_status":
        if value not in _COMPLIANCE_VALUES:
            raise AnswerValidationError(f"value must be one of {_COMPLIANCE_VALUES}")
    elif response_type == "text" or response_type == "comment":
        if not isinstance(value, str):
            raise AnswerValidationError("value must be a string")
    elif response_type == "single_choice":
        if not isinstance(value, str) or value not in (requirement.options or []):
            raise AnswerValidationError("value must be one of the requirement's options")
    elif response_type == "multi_choice":
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise AnswerValidationError("value must be a list of strings")
        if not set(value).issubset(set(requirement.options or [])):
            raise AnswerValidationError("value must be a subset of the requirement's options")
    elif response_type == "number":
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise AnswerValidationError("value must be a number")
    elif response_type == "percentage":
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise AnswerValidationError("value must be a number")
        if not (0 <= value <= 100):
            raise AnswerValidationError("value must be between 0 and 100")
    elif response_type == "date":
        if not isinstance(value, str):
            raise AnswerValidationError("value must be an ISO date string")
        try:
            date.fromisoformat(value)
        except ValueError:
            raise AnswerValidationError("value must be a valid ISO date") from None
    elif response_type == "url":
        if not isinstance(value, str) or not (
            value.startswith("http://") or value.startswith("https://")
        ):
            raise AnswerValidationError("value must be an http(s) URL")
    elif response_type == "currency":
        if not isinstance(value, dict):
            raise AnswerValidationError("value must be an object with amount and currency_code")
        amount = value.get("amount")
        currency_code = value.get("currency_code")
        if isinstance(amount, bool) or not isinstance(amount, int | float) or amount < 0:
            raise AnswerValidationError("amount must be a non-negative number")
        if currency_code not in _CURRENCY_CODES:
            raise AnswerValidationError(f"currency_code must be one of {_CURRENCY_CODES}")
    else:  # pragma: no cover - exhaustive over ResponseType
        raise AnswerValidationError(f"unsupported response_type {response_type!r}")


class ProposalService:
    def __init__(
        self,
        proposals: ProposalRepository,
        evaluations: EvaluationRepository,
        vendor_orgs: VendorOrganizationRepository,
        audit: AuditEventService,
    ) -> None:
        self._proposals = proposals
        self._evaluations = evaluations
        self._vendor_orgs = vendor_orgs
        self._audit = audit

    def get_proposal(self, tenant_id: str, proposal_id: str) -> Proposal:
        doc = self._proposals.find_by_id(tenant_id, proposal_id)
        if doc is None:
            raise ProposalNotFoundError(proposal_id)
        return Proposal.from_document(doc)

    def list_for_evaluation(self, tenant_id: str, evaluation_id: str) -> list[Proposal]:
        return [
            Proposal.from_document(doc)
            for doc in self._proposals.find_by_evaluation(tenant_id, evaluation_id)
        ]

    def get_proposal_for_vendor(
        self, tenant_id: str, vendor_org_id: str, proposal_id: str
    ) -> Proposal:
        proposal = self.get_proposal(tenant_id, proposal_id)
        if proposal.vendor_org_id != vendor_org_id:
            raise ProposalNotFoundError(proposal_id)
        return proposal

    def list_for_vendor(self, tenant_id: str, vendor_org_id: str) -> list[Proposal]:
        return [
            Proposal.from_document(doc)
            for doc in self._proposals.find_by_vendor_org(tenant_id, vendor_org_id)
        ]

    def _require_evaluation_and_requirement(
        self, tenant_id: str, evaluation_id: str, requirement_id: str
    ) -> tuple[Evaluation, Requirement]:
        evaluation_doc = self._evaluations.find_by_id(tenant_id, evaluation_id)
        if evaluation_doc is None:
            raise ProposalNotFoundError(evaluation_id)
        evaluation = Evaluation.from_document(evaluation_doc)
        for requirement in evaluation.requirements:
            if requirement.id == requirement_id:
                return evaluation, requirement
        raise RequirementNotFoundError(requirement_id)

    def update_answer(
        self,
        tenant_id: str,
        vendor_org_id: str,
        proposal_id: str,
        requirement_id: str,
        value: Any,
        vendor_comment: str | None,
        expected_version: int,
    ) -> Proposal:
        proposal = self.get_proposal_for_vendor(tenant_id, vendor_org_id, proposal_id)
        evaluation, requirement = self._require_evaluation_and_requirement(
            tenant_id, proposal.evaluation_id, requirement_id
        )
        if evaluation.status != "collecting_responses":
            raise InvalidProposalTransitionError("evaluation is not collecting_responses")
        if proposal.status != "draft":
            raise InvalidProposalTransitionError("proposal is not draft")
        if proposal.version != expected_version:
            raise StaleVersionError(proposal_id)

        validate_answer_value(requirement, value)

        now = datetime.now(UTC)
        new_answers = [a for a in proposal.answers if a.requirement_id != requirement_id]
        new_answers.append(
            ProposalAnswer(
                requirement_id=requirement_id,
                value=value,
                vendor_comment=vendor_comment,
                updated_at=now,
            )
        )
        matched = self._proposals.replace_answers(
            tenant_id, proposal_id, expected_version, [a.to_document() for a in new_answers]
        )
        if not matched:
            raise StaleVersionError(proposal_id)
        return self.get_proposal(tenant_id, proposal_id)

    def submit(
        self,
        tenant_id: str,
        vendor_org_id: str,
        proposal_id: str,
        expected_version: int,
        membership_id: str,
        *,
        actor: ActorContext,
    ) -> Proposal:
        proposal = self.get_proposal_for_vendor(tenant_id, vendor_org_id, proposal_id)
        evaluation_doc = self._evaluations.find_by_id(tenant_id, proposal.evaluation_id)
        if evaluation_doc is None:
            raise ProposalNotFoundError(proposal.evaluation_id)
        evaluation = Evaluation.from_document(evaluation_doc)

        if evaluation.status != "collecting_responses":
            raise InvalidProposalTransitionError("evaluation is not collecting_responses")
        if proposal.status != "draft":
            raise InvalidProposalTransitionError("proposal is not draft")
        if proposal.version != expected_version:
            raise StaleVersionError(proposal_id)

        answers_by_requirement = {a.requirement_id: a for a in proposal.answers}

        def _is_unanswered(requirement_id: str) -> bool:
            answer = answers_by_requirement.get(requirement_id)
            return answer is None or answer.value is None

        missing = [r.id for r in evaluation.requirements if r.required and _is_unanswered(r.id)]
        if missing:
            raise IncompleteRequiredAnswersError(", ".join(missing))

        vendor_org_doc = self._vendor_orgs.find_by_id(tenant_id, vendor_org_id)
        vendor_org_name = vendor_org_doc["name"] if vendor_org_doc else vendor_org_id

        now = datetime.now(UTC)
        snapshot = ProposalSnapshot(
            snapshot_id=uuid4().hex,
            taken_at=now,
            evaluation_id=evaluation.id,
            evaluation_name=evaluation.name,
            vendor_org_id=vendor_org_id,
            vendor_org_name=vendor_org_name,
            requirements=list(evaluation.requirements),
            answers=list(proposal.answers),
            submitted_by_membership_id=membership_id,
            submitted_at=now,
        )
        matched = self._proposals.submit(
            tenant_id, proposal_id, expected_version, snapshot.to_document(), now
        )
        if not matched:
            raise StaleVersionError(proposal_id)

        submitted = self.get_proposal(tenant_id, proposal_id)
        answered_count = sum(1 for a in submitted.answers if a.value is not None)
        self._audit.record(
            tenant_id=tenant_id,
            actor=actor,
            action="proposal_submitted",
            resource_type="proposal",
            resource_id=proposal_id,
            evaluation_id=evaluation.id,
            proposal_id=proposal_id,
            snapshot_id=snapshot.snapshot_id,
            version=submitted.version,
            metadata={"requirements_answered_count": answered_count},
        )
        return submitted
