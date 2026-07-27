from typing import Any

from procurawise.evaluations.models import Requirement
from procurawise.evaluations.repository import EvaluationRepository
from procurawise.proposals.models import Proposal
from procurawise.proposals.service import ProposalService


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
        if proposal.snapshot is not None:
            requirements = proposal.snapshot.requirements
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
    ) -> Proposal:
        return self._proposals.submit(
            tenant_id, vendor_org_id, proposal_id, expected_version, membership_id
        )
