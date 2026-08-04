from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, cast
from uuid import uuid4

from procurawise.audit.service import AuditEventService
from procurawise.documents.repository import DocumentRepository
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
from procurawise.tco.exceptions import (
    CostItemNotFoundError,
    InvalidCostItemError,
    MissingFxRateError,
)
from procurawise.tco.models import (
    CostCategory,
    CostItem,
    CostType,
    Currency,
    FrozenFxRate,
    TcoResult,
    decimal_from_bson,
)
from procurawise.tco.repository import FXRateRepository
from procurawise.tco.service import TcoService

_CURRENCY_CODES = {"MXN", "USD"}
_COMPLIANCE_VALUES = {"compliant", "partially_compliant", "non_compliant"}
_TCO_CATEGORIES = {"initial", "recurring", "variable_extraordinary"}
_TCO_COST_TYPES = {"one_time", "recurring", "variable"}


def validate_cost_item_fields(
    *,
    category: str,
    currency: str,
    cost_type: str,
    quantity: Decimal,
    unit_price: Decimal,
    frequency_per_year: Decimal,
    tax_pct: Decimal,
    discount_pct: Decimal,
    year_start: int,
    year_end: int,
    annual_increment_pct: Decimal,
) -> None:
    """Fase 19 - the business-rule checks that don't already fit a Pydantic
    Field/Literal constraint at the schema layer (plan §6.J165-169)."""
    if category not in _TCO_CATEGORIES:
        raise InvalidCostItemError(f"category must be one of {_TCO_CATEGORIES}")
    if currency not in _CURRENCY_CODES:
        raise InvalidCostItemError(f"currency must be one of {_CURRENCY_CODES}")
    if cost_type not in _TCO_COST_TYPES:
        raise InvalidCostItemError(f"cost_type must be one of {_TCO_COST_TYPES}")
    if quantity <= 0:
        raise InvalidCostItemError("quantity must be greater than zero")
    if unit_price < 0:
        raise InvalidCostItemError("unit_price must not be negative")
    if frequency_per_year <= 0:
        raise InvalidCostItemError("frequency_per_year must be greater than zero")
    if not (0 <= tax_pct <= 100):
        raise InvalidCostItemError("tax_pct must be between 0 and 100")
    if not (0 <= discount_pct <= 100):
        raise InvalidCostItemError("discount_pct must be between 0 and 100")
    if not (1 <= year_start <= 5):
        raise InvalidCostItemError("year_start must be between 1 and 5")
    if not (1 <= year_end <= 5):
        raise InvalidCostItemError("year_end must be between 1 and 5")
    if year_start > year_end:
        raise InvalidCostItemError("year_start must not be after year_end")
    if annual_increment_pct < -100:
        raise InvalidCostItemError("annual_increment_pct must not be less than -100")


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
        documents: DocumentRepository,
        fx_rates: FXRateRepository,
    ) -> None:
        self._proposals = proposals
        self._evaluations = evaluations
        self._vendor_orgs = vendor_orgs
        self._audit = audit
        self._documents = documents
        self._fx_rates = fx_rates
        self._tco = TcoService()

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

    def _require_evaluation(self, tenant_id: str, evaluation_id: str) -> Evaluation:
        doc = self._evaluations.find_by_id(tenant_id, evaluation_id)
        if doc is None:
            raise ProposalNotFoundError(evaluation_id)
        return Evaluation.from_document(doc)

    def _require_draft_cost_item_write(
        self, tenant_id: str, vendor_org_id: str, proposal_id: str, expected_version: int
    ) -> tuple[Proposal, Evaluation]:
        proposal = self.get_proposal_for_vendor(tenant_id, vendor_org_id, proposal_id)
        evaluation = self._require_evaluation(tenant_id, proposal.evaluation_id)
        if evaluation.status != "collecting_responses":
            raise InvalidProposalTransitionError("evaluation is not collecting_responses")
        if proposal.status != "draft":
            raise InvalidProposalTransitionError("proposal is not draft")
        if proposal.version != expected_version:
            raise StaleVersionError(proposal_id)
        return proposal, evaluation

    def add_cost_item(
        self,
        tenant_id: str,
        vendor_org_id: str,
        proposal_id: str,
        expected_version: int,
        *,
        concept: str,
        category: CostCategory,
        description: str | None,
        billing_unit: str,
        quantity: Decimal,
        unit_price: Decimal,
        currency: Currency,
        frequency_per_year: Decimal,
        tax_pct: Decimal,
        discount_pct: Decimal,
        year_start: int,
        year_end: int,
        annual_increment_pct: Decimal,
        mandatory: bool,
        cost_type: CostType,
        notes: str | None,
    ) -> Proposal:
        proposal, _evaluation = self._require_draft_cost_item_write(
            tenant_id, vendor_org_id, proposal_id, expected_version
        )
        validate_cost_item_fields(
            category=category,
            currency=currency,
            cost_type=cost_type,
            quantity=quantity,
            unit_price=unit_price,
            frequency_per_year=frequency_per_year,
            tax_pct=tax_pct,
            discount_pct=discount_pct,
            year_start=year_start,
            year_end=year_end,
            annual_increment_pct=annual_increment_pct,
        )
        new_item = CostItem.create(
            concept=concept,
            category=category,
            description=description,
            billing_unit=billing_unit,
            quantity=quantity,
            unit_price=unit_price,
            currency=currency,
            frequency_per_year=frequency_per_year,
            tax_pct=tax_pct,
            discount_pct=discount_pct,
            year_start=year_start,
            year_end=year_end,
            annual_increment_pct=annual_increment_pct,
            mandatory=mandatory,
            cost_type=cost_type,
            notes=notes,
        )
        new_items = [*proposal.cost_items, new_item]
        matched = self._proposals.replace_cost_items(
            tenant_id, proposal_id, expected_version, [c.to_document() for c in new_items]
        )
        if not matched:
            raise StaleVersionError(proposal_id)
        return self.get_proposal(tenant_id, proposal_id)

    def update_cost_item(
        self,
        tenant_id: str,
        vendor_org_id: str,
        proposal_id: str,
        cost_item_id: str,
        expected_version: int,
        *,
        concept: str | None = None,
        category: CostCategory | None = None,
        description: str | None = None,
        billing_unit: str | None = None,
        quantity: Decimal | None = None,
        unit_price: Decimal | None = None,
        currency: Currency | None = None,
        frequency_per_year: Decimal | None = None,
        tax_pct: Decimal | None = None,
        discount_pct: Decimal | None = None,
        year_start: int | None = None,
        year_end: int | None = None,
        annual_increment_pct: Decimal | None = None,
        mandatory: bool | None = None,
        cost_type: CostType | None = None,
        notes: str | None = None,
    ) -> Proposal:
        proposal, _evaluation = self._require_draft_cost_item_write(
            tenant_id, vendor_org_id, proposal_id, expected_version
        )
        current = next((c for c in proposal.cost_items if c.id == cost_item_id), None)
        if current is None:
            raise CostItemNotFoundError(cost_item_id)

        updated = CostItem(
            id=current.id,
            concept=concept if concept is not None else current.concept,
            category=category if category is not None else current.category,
            description=description if description is not None else current.description,
            billing_unit=billing_unit if billing_unit is not None else current.billing_unit,
            quantity=quantity if quantity is not None else current.quantity,
            unit_price=unit_price if unit_price is not None else current.unit_price,
            currency=currency if currency is not None else current.currency,
            frequency_per_year=(
                frequency_per_year if frequency_per_year is not None else current.frequency_per_year
            ),
            tax_pct=tax_pct if tax_pct is not None else current.tax_pct,
            discount_pct=discount_pct if discount_pct is not None else current.discount_pct,
            year_start=year_start if year_start is not None else current.year_start,
            year_end=year_end if year_end is not None else current.year_end,
            annual_increment_pct=(
                annual_increment_pct
                if annual_increment_pct is not None
                else current.annual_increment_pct
            ),
            mandatory=mandatory if mandatory is not None else current.mandatory,
            cost_type=cost_type if cost_type is not None else current.cost_type,
            notes=notes if notes is not None else current.notes,
            created_at=current.created_at,
            updated_at=datetime.now(UTC),
        )
        validate_cost_item_fields(
            category=updated.category,
            currency=updated.currency,
            cost_type=updated.cost_type,
            quantity=updated.quantity,
            unit_price=updated.unit_price,
            frequency_per_year=updated.frequency_per_year,
            tax_pct=updated.tax_pct,
            discount_pct=updated.discount_pct,
            year_start=updated.year_start,
            year_end=updated.year_end,
            annual_increment_pct=updated.annual_increment_pct,
        )
        new_items = [updated if c.id == cost_item_id else c for c in proposal.cost_items]
        matched = self._proposals.replace_cost_items(
            tenant_id, proposal_id, expected_version, [c.to_document() for c in new_items]
        )
        if not matched:
            raise StaleVersionError(proposal_id)
        return self.get_proposal(tenant_id, proposal_id)

    def remove_cost_item(
        self,
        tenant_id: str,
        vendor_org_id: str,
        proposal_id: str,
        cost_item_id: str,
        expected_version: int,
    ) -> Proposal:
        proposal, _evaluation = self._require_draft_cost_item_write(
            tenant_id, vendor_org_id, proposal_id, expected_version
        )
        if not any(c.id == cost_item_id for c in proposal.cost_items):
            raise CostItemNotFoundError(cost_item_id)
        new_items = [c for c in proposal.cost_items if c.id != cost_item_id]
        matched = self._proposals.replace_cost_items(
            tenant_id, proposal_id, expected_version, [c.to_document() for c in new_items]
        )
        if not matched:
            raise StaleVersionError(proposal_id)
        return self.get_proposal(tenant_id, proposal_id)

    def _resolve_frozen_fx_rates(
        self, cost_items: list[CostItem], base_currency: str, as_of: date
    ) -> list[FrozenFxRate]:
        """Fase 19 (plan §11.2) - resolves the FXRate vigente for every
        currency actually used by `cost_items` that differs from
        `base_currency`, as of `as_of`. Raises MissingFxRateError (fails
        closed) rather than silently skipping a conversion."""
        needed_currencies = {c.currency for c in cost_items if c.currency != base_currency}
        frozen: list[FrozenFxRate] = []
        for currency in needed_currencies:
            doc = self._fx_rates.find_latest_for_pair(currency, base_currency, as_of.isoformat())
            if doc is None:
                raise MissingFxRateError(f"{currency}->{base_currency}")
            frozen.append(
                FrozenFxRate(
                    from_currency=doc["from_currency"],
                    to_currency=doc["to_currency"],
                    rate=decimal_from_bson(doc["rate"]),
                    effective_date=date.fromisoformat(doc["effective_date"]),
                    source=doc["source"],
                )
            )
        return frozen

    def preview_tco(self, tenant_id: str, vendor_org_id: str, proposal_id: str) -> TcoResult:
        """Fase 19 - bought-demand calculation using the FX rate(s) vigente
        right now, for the vendor's own eyes while still editing (plan
        §6.E78-79). Never persisted - only `submit()` freezes a TcoResult."""
        proposal = self.get_proposal_for_vendor(tenant_id, vendor_org_id, proposal_id)
        evaluation = self._require_evaluation(tenant_id, proposal.evaluation_id)
        today = datetime.now(UTC).date()
        frozen_rates = self._resolve_frozen_fx_rates(
            proposal.cost_items, evaluation.base_currency, today
        )
        return self._tco.calculate(
            proposal.cost_items,
            frozen_rates,
            cast(Currency, evaluation.base_currency),
            evaluation.tco_horizon_years,
        )

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
        document_ids = [
            doc["_id"] for doc in self._documents.list_current_for_proposal(tenant_id, proposal_id)
        ]

        now = datetime.now(UTC)
        # Fase 19 (plan §11.2/§14): resolve+freeze FX and compute the TCO
        # result in this same atomic step - MissingFxRateError aborts the
        # submit before anything is written (fails closed, nothing frozen).
        frozen_rates = self._resolve_frozen_fx_rates(
            proposal.cost_items, evaluation.base_currency, now.date()
        )
        tco_result = self._tco.calculate(
            proposal.cost_items,
            frozen_rates,
            cast(Currency, evaluation.base_currency),
            evaluation.tco_horizon_years,
        )
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
            document_ids=document_ids,
            cost_items=list(proposal.cost_items),
            tco_result=tco_result,
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
