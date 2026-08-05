from decimal import Decimal
from typing import Any

from procurawise.evaluations.models import Requirement
from procurawise.evaluations.repository import EvaluationRepository
from procurawise.proposals.models import Proposal
from procurawise.proposals.service import ProposalService
from procurawise.shared.context import ActorContext
from procurawise.tco.models import CostCategory, CostType, Currency, TcoResult


class VendorPortalService:
    """Vendor-scoped authorization plus response assembly, delegating all
    write/state-machine logic to `proposals.service.ProposalService` (which
    already takes vendor_org_id and enforces "only this vendor's own
    proposal"). The one piece of logic that belongs here rather than in
    ProposalService: deciding whether to show the live (mutable, draft)
    requirement set or the frozen snapshot - a vendor-portal-specific view
    concern, not a proposal state-machine concern."""

    def __init__(self, proposals: ProposalService, evaluations: EvaluationRepository) -> None:
        self._proposals = proposals
        self._evaluations = evaluations

    def _evaluation_name(self, tenant_id: str, evaluation_id: str) -> str:
        doc = self._evaluations.find_by_id(tenant_id, evaluation_id)
        return doc["name"] if doc else evaluation_id

    def list_proposals(self, tenant_id: str, vendor_org_id: str) -> list[tuple[Proposal, str]]:
        return [
            (proposal, self._evaluation_name(tenant_id, proposal.evaluation_id))
            for proposal in self._proposals.list_for_vendor(tenant_id, vendor_org_id)
        ]

    def get_proposal_with_requirements(
        self, tenant_id: str, vendor_org_id: str, proposal_id: str
    ) -> tuple[Proposal, str, list[Requirement]]:
        proposal = self._proposals.get_proposal_for_vendor(tenant_id, vendor_org_id, proposal_id)
        evaluation_name = self._evaluation_name(tenant_id, proposal.evaluation_id)
        # Fase 21: while editing (status=="draft"), Requirements always come
        # from the live Evaluation - true for the original Ronda 0 draft
        # (before any snapshot exists) and equally true for a reopened
        # Ronda 1 draft (a snapshot already exists from Ronda 0, but
        # Requirements are draft-only and never change during negotiation,
        # so the live Evaluation is still the right source while editing).
        # Only a submitted proposal reads its own frozen snapshot.
        if proposal.status == "submitted" and proposal.current_snapshot is not None:
            requirements = proposal.current_snapshot.requirements
        else:
            evaluation_doc = self._evaluations.find_by_id(tenant_id, proposal.evaluation_id)
            requirements = (
                [Requirement.from_document(r) for r in evaluation_doc.get("requirements", [])]
                if evaluation_doc
                else []
            )
        return proposal, evaluation_name, requirements

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
        return self._proposals.update_answer(
            tenant_id,
            vendor_org_id,
            proposal_id,
            requirement_id,
            value,
            vendor_comment,
            expected_version,
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
        return self._proposals.submit(
            tenant_id, vendor_org_id, proposal_id, expected_version, membership_id, actor=actor
        )

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
        return self._proposals.add_cost_item(
            tenant_id,
            vendor_org_id,
            proposal_id,
            expected_version,
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

    def update_cost_item(
        self,
        tenant_id: str,
        vendor_org_id: str,
        proposal_id: str,
        cost_item_id: str,
        expected_version: int,
        **fields: Any,
    ) -> Proposal:
        return self._proposals.update_cost_item(
            tenant_id, vendor_org_id, proposal_id, cost_item_id, expected_version, **fields
        )

    def remove_cost_item(
        self,
        tenant_id: str,
        vendor_org_id: str,
        proposal_id: str,
        cost_item_id: str,
        expected_version: int,
    ) -> Proposal:
        return self._proposals.remove_cost_item(
            tenant_id, vendor_org_id, proposal_id, cost_item_id, expected_version
        )

    def preview_tco(self, tenant_id: str, vendor_org_id: str, proposal_id: str) -> TcoResult:
        return self._proposals.preview_tco(tenant_id, vendor_org_id, proposal_id)
