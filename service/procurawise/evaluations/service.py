from datetime import UTC, datetime

from pymongo.errors import DuplicateKeyError

from procurawise.evaluations.exceptions import (
    EvaluationNotFoundError,
    InvalidTransitionError,
    RequirementNotFoundError,
    StartCollectionPreconditionError,
    VendorAlreadyLinkedError,
    VendorLimitExceededError,
    VendorNotLinkedError,
    VendorOrganizationNotFoundError,
)
from procurawise.evaluations.models import DIMENSION_MAX_POINTS, Evaluation, Requirement
from procurawise.evaluations.repository import EvaluationRepository
from procurawise.identity.repository import VendorOrganizationRepository
from procurawise.proposals.models import Proposal
from procurawise.proposals.repository import ProposalRepository

_WEIGHT_TOLERANCE = 1e-6


class EvaluationService:
    def __init__(
        self,
        evaluations: EvaluationRepository,
        proposals: ProposalRepository,
        vendor_orgs: VendorOrganizationRepository,
    ) -> None:
        self._evaluations = evaluations
        self._proposals = proposals
        self._vendor_orgs = vendor_orgs

    def create_evaluation(
        self, tenant_id: str, membership_id: str, name: str, description: str
    ) -> Evaluation:
        evaluation = Evaluation.create(
            tenant_id=tenant_id,
            name=name,
            description=description,
            created_by_membership_id=membership_id,
        )
        self._evaluations.insert(tenant_id, evaluation.to_document())
        return evaluation

    def get_evaluation(self, tenant_id: str, evaluation_id: str) -> Evaluation:
        doc = self._evaluations.find_by_id(tenant_id, evaluation_id)
        if doc is None:
            raise EvaluationNotFoundError(evaluation_id)
        return Evaluation.from_document(doc)

    def list_evaluations(self, tenant_id: str) -> list[Evaluation]:
        return [Evaluation.from_document(doc) for doc in self._evaluations.find_many(tenant_id)]

    def update_evaluation(
        self, tenant_id: str, evaluation_id: str, name: str | None, description: str | None
    ) -> Evaluation:
        updates: dict[str, str] = {}
        if name is not None:
            updates["name"] = name
        if description is not None:
            updates["description"] = description
        matched = self._evaluations.update_metadata(tenant_id, evaluation_id, updates)
        self._require_matched(matched, tenant_id, evaluation_id)
        return self.get_evaluation(tenant_id, evaluation_id)

    def add_requirement(
        self,
        tenant_id: str,
        evaluation_id: str,
        *,
        dimension: str,
        category: str,
        title: str,
        description: str,
        priority: str,
        response_type: str,
        weight: float,
        required: bool,
        display_order: int,
        buyer_guidance: str | None,
        options: list[str] | None,
    ) -> Requirement:
        requirement = Requirement.create(
            dimension=dimension,  # type: ignore[arg-type]
            category=category,
            title=title,
            description=description,
            priority=priority,  # type: ignore[arg-type]
            response_type=response_type,  # type: ignore[arg-type]
            weight=weight,
            required=required,
            display_order=display_order,
            buyer_guidance=buyer_guidance,
            options=options,
        )
        matched = self._evaluations.add_requirement(
            tenant_id, evaluation_id, requirement.to_document()
        )
        self._require_draft_matched(matched, tenant_id, evaluation_id)
        return requirement

    def update_requirement(
        self, tenant_id: str, evaluation_id: str, requirement_id: str, field_updates: dict
    ) -> Requirement:
        matched = self._evaluations.update_requirement(
            tenant_id, evaluation_id, requirement_id, field_updates
        )
        if not matched:
            evaluation = self.get_evaluation(tenant_id, evaluation_id)
            if evaluation.status != "draft":
                raise InvalidTransitionError(evaluation_id)
            raise RequirementNotFoundError(requirement_id)
        evaluation = self.get_evaluation(tenant_id, evaluation_id)
        for requirement in evaluation.requirements:
            if requirement.id == requirement_id:
                return requirement
        raise RequirementNotFoundError(requirement_id)

    def delete_requirement(self, tenant_id: str, evaluation_id: str, requirement_id: str) -> None:
        evaluation = self.get_evaluation(tenant_id, evaluation_id)
        if evaluation.status != "draft":
            raise InvalidTransitionError(evaluation_id)
        if not any(r.id == requirement_id for r in evaluation.requirements):
            raise RequirementNotFoundError(requirement_id)
        self._evaluations.delete_requirement(tenant_id, evaluation_id, requirement_id)

    def link_vendor(self, tenant_id: str, evaluation_id: str, vendor_org_id: str) -> Proposal:
        outcome = self._evaluations.reserve_vendor_slot(tenant_id, evaluation_id)
        if outcome == "not_found":
            raise EvaluationNotFoundError(evaluation_id)
        if outcome == "not_draft":
            raise InvalidTransitionError(evaluation_id)
        if outcome == "limit_reached":
            raise VendorLimitExceededError(evaluation_id)

        vendor_org_doc = self._vendor_orgs.find_by_id(tenant_id, vendor_org_id)
        if vendor_org_doc is None:
            self._evaluations.release_vendor_slot(tenant_id, evaluation_id)
            raise VendorOrganizationNotFoundError(vendor_org_id)

        proposal = Proposal.create(
            tenant_id=tenant_id, evaluation_id=evaluation_id, vendor_org_id=vendor_org_id
        )
        try:
            self._proposals.insert(tenant_id, proposal.to_document())
        except DuplicateKeyError:
            self._evaluations.release_vendor_slot(tenant_id, evaluation_id)
            raise VendorAlreadyLinkedError(vendor_org_id) from None
        except Exception:
            self._evaluations.release_vendor_slot(tenant_id, evaluation_id)
            raise
        return proposal

    def unlink_vendor(self, tenant_id: str, evaluation_id: str, vendor_org_id: str) -> None:
        proposal_doc = self._proposals.find_one_by_evaluation_and_vendor(
            tenant_id, evaluation_id, vendor_org_id
        )
        if proposal_doc is None:
            raise VendorNotLinkedError(vendor_org_id)
        deleted = self._proposals.delete(tenant_id, proposal_doc["_id"])
        if not deleted:
            raise InvalidTransitionError(evaluation_id)
        self._evaluations.release_vendor_slot(tenant_id, evaluation_id)

    def start_collection(self, tenant_id: str, evaluation_id: str) -> Evaluation:
        evaluation = self.get_evaluation(tenant_id, evaluation_id)
        if evaluation.status != "draft":
            raise InvalidTransitionError(evaluation_id)

        by_dimension: dict[str, float] = {"functional": 0.0, "technical": 0.0}
        for requirement in evaluation.requirements:
            by_dimension[requirement.dimension] = (
                by_dimension.get(requirement.dimension, 0.0) + requirement.weight
            )

        if by_dimension["functional"] == 0.0 or by_dimension["technical"] == 0.0:
            raise StartCollectionPreconditionError(
                "at least one functional and one technical requirement are required"
            )
        for dimension, max_points in DIMENSION_MAX_POINTS.items():
            if abs(by_dimension[dimension] - max_points) > _WEIGHT_TOLERANCE:
                raise StartCollectionPreconditionError(
                    f"{dimension} requirement weights must sum to {max_points}, got "
                    f"{by_dimension[dimension]}"
                )

        if evaluation.linked_vendor_count == 0:
            raise StartCollectionPreconditionError("at least one vendor must be linked")

        matched = self._evaluations.transition_status(
            tenant_id,
            evaluation_id,
            "draft",
            "collecting_responses",
            {"collecting_responses_started_at": datetime.now(UTC)},
        )
        self._require_matched(matched, tenant_id, evaluation_id)
        return self.get_evaluation(tenant_id, evaluation_id)

    def start_evaluation(self, tenant_id: str, evaluation_id: str) -> Evaluation:
        matched = self._evaluations.transition_status(
            tenant_id,
            evaluation_id,
            "collecting_responses",
            "evaluating",
            {"evaluating_started_at": datetime.now(UTC)},
        )
        self._require_matched(matched, tenant_id, evaluation_id)
        return self.get_evaluation(tenant_id, evaluation_id)

    def _require_matched(self, matched: bool, tenant_id: str, evaluation_id: str) -> None:
        if matched:
            return
        evaluation_doc = self._evaluations.find_by_id(tenant_id, evaluation_id)
        if evaluation_doc is None:
            raise EvaluationNotFoundError(evaluation_id)
        raise InvalidTransitionError(evaluation_id)

    def _require_draft_matched(self, matched: bool, tenant_id: str, evaluation_id: str) -> None:
        self._require_matched(matched, tenant_id, evaluation_id)
