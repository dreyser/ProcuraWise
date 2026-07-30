from datetime import UTC, datetime
from typing import Any

from pymongo.errors import DuplicateKeyError

from procurawise.assignments.repository import AssignmentRepository
from procurawise.audit.service import AuditEventService
from procurawise.evaluations.exceptions import (
    CompletionPreconditionError,
    EvaluationNotFoundError,
    InvalidTransitionError,
)
from procurawise.evaluations.models import DIMENSION_MAX_POINTS, ECONOMIC_MAX_POINTS, Evaluation
from procurawise.evaluations.repository import EvaluationRepository
from procurawise.identity.repository import VendorOrganizationRepository
from procurawise.proposals.exceptions import ProposalNotFoundError
from procurawise.proposals.models import Proposal
from procurawise.proposals.repository import ProposalRepository
from procurawise.scoring.exceptions import (
    RequirementNotInSnapshotError,
    ResultsNotAvailableError,
    ScoreOutOfRangeError,
    ScoringPreconditionError,
    SectionNotAssignedToActorError,
    StaleScoreVersionError,
)
from procurawise.scoring.models import Score
from procurawise.scoring.repository import ScoreRepository
from procurawise.shared.context import ActorContext
from procurawise.shared.roles import EVALUATOR_ROLES

# functional(40) + technical(20) = 60 of the eventual 100-point model; this
# also happens to equal the coverage percentage (60/100), since the model's
# grand total is 100 points - not a coincidence to "fix", just how the numbers
# align while economic(40) is not_available.
_PARTIAL_RESULT_MAX_POINTS = sum(DIMENSION_MAX_POINTS.values())


class ScoringService:
    def __init__(
        self,
        scores: ScoreRepository,
        proposals: ProposalRepository,
        evaluations: EvaluationRepository,
        vendor_orgs: VendorOrganizationRepository,
        audit: AuditEventService,
        assignments: AssignmentRepository,
    ) -> None:
        self._scores = scores
        self._proposals = proposals
        self._evaluations = evaluations
        self._vendor_orgs = vendor_orgs
        self._audit = audit
        self._assignments = assignments

    def _enforce_section_assignment(
        self, tenant_id: str, evaluation_id: str, dimension: str, section: str, actor: ActorContext
    ) -> None:
        """An evaluator sub-role may score any (dimension, section) that has
        no Assignment recorded yet (today's VS-2B behavior, unchanged) - but
        once at least one evaluator has been assigned to a section, scoring
        it is restricted to the assigned evaluator(s) only, even for other
        holders of the same sub-role (Fase 9 Block 3, spec §4/§6.7). The
        evaluation_owner is never restricted by this check."""
        if actor.role not in EVALUATOR_ROLES:
            return
        assignments = self._assignments.list_for_section(
            tenant_id, evaluation_id, dimension, section
        )
        if not assignments:
            return
        assigned_membership_ids = {doc["evaluator_membership_id"] for doc in assignments}
        if actor.membership_id not in assigned_membership_ids:
            raise SectionNotAssignedToActorError(section)

    def upsert_score(
        self,
        tenant_id: str,
        evaluation_id: str,
        proposal_id: str,
        requirement_id: str,
        score_value: int,
        comment: str | None,
        expected_version: int | None,
        membership_id: str,
        *,
        actor: ActorContext,
    ) -> Score:
        if score_value < 0 or score_value > 5:
            raise ScoreOutOfRangeError(score_value)

        evaluation_doc = self._evaluations.find_by_id(tenant_id, evaluation_id)
        if evaluation_doc is None:
            raise EvaluationNotFoundError(evaluation_id)
        evaluation = Evaluation.from_document(evaluation_doc)
        if evaluation.status != "evaluating":
            raise ScoringPreconditionError("evaluation is not evaluating")

        proposal_doc = self._proposals.find_by_id(tenant_id, proposal_id)
        if proposal_doc is None or proposal_doc["evaluation_id"] != evaluation_id:
            raise ProposalNotFoundError(proposal_id)
        proposal = Proposal.from_document(proposal_doc)
        if proposal.status != "submitted" or proposal.snapshot is None:
            raise ScoringPreconditionError("proposal is not submitted")

        requirement = next(
            (r for r in proposal.snapshot.requirements if r.id == requirement_id), None
        )
        if requirement is None:
            raise RequirementNotInSnapshotError(requirement_id)

        self._enforce_section_assignment(
            tenant_id, evaluation_id, requirement.dimension, requirement.category, actor
        )

        existing_doc = self._scores.find_one_by_natural_key(
            tenant_id, evaluation_id, proposal_id, proposal.snapshot.snapshot_id, requirement_id
        )

        if existing_doc is None:
            if expected_version is not None:
                raise StaleScoreVersionError(requirement_id)
            score = Score.create(
                tenant_id=tenant_id,
                evaluation_id=evaluation_id,
                proposal_id=proposal_id,
                snapshot_id=proposal.snapshot.snapshot_id,
                requirement_id=requirement_id,
                dimension=requirement.dimension,
                priority=requirement.priority,
                requirement_weight=requirement.weight,
                score=score_value,
                comment=comment,
                membership_id=membership_id,
            )
            try:
                self._scores.insert(tenant_id, score.to_document())
            except DuplicateKeyError:
                raise StaleScoreVersionError(requirement_id) from None
            self._audit.record(
                tenant_id=tenant_id,
                actor=actor,
                action="score_created",
                resource_type="score",
                resource_id=score.id,
                evaluation_id=evaluation_id,
                proposal_id=proposal_id,
                snapshot_id=proposal.snapshot.snapshot_id,
                version=score.version,
                metadata={"requirement_id": requirement_id, "score": score_value},
            )
            return score

        existing = Score.from_document(existing_doc)
        if expected_version != existing.version:
            raise StaleScoreVersionError(requirement_id)
        matched = self._scores.update(
            tenant_id, existing.id, expected_version, score_value, comment, membership_id
        )
        if not matched:
            raise StaleScoreVersionError(requirement_id)
        updated_doc = self._scores.find_one_by_natural_key(
            tenant_id, evaluation_id, proposal_id, proposal.snapshot.snapshot_id, requirement_id
        )
        assert updated_doc is not None
        updated = Score.from_document(updated_doc)
        self._audit.record(
            tenant_id=tenant_id,
            actor=actor,
            action="score_updated",
            resource_type="score",
            resource_id=updated.id,
            evaluation_id=evaluation_id,
            proposal_id=proposal_id,
            snapshot_id=proposal.snapshot.snapshot_id,
            version=updated.version,
            metadata={"requirement_id": requirement_id, "score": score_value},
        )
        return updated

    def _submitted_and_draft_proposals(
        self, tenant_id: str, evaluation_id: str
    ) -> tuple[list[Proposal], list[Proposal]]:
        proposals = [
            Proposal.from_document(doc)
            for doc in self._proposals.find_by_evaluation(tenant_id, evaluation_id)
        ]
        submitted = [p for p in proposals if p.status == "submitted"]
        drafts = [p for p in proposals if p.status == "draft"]
        return submitted, drafts

    def _is_fully_scored(self, tenant_id: str, evaluation_id: str) -> bool:
        submitted, _drafts = self._submitted_and_draft_proposals(tenant_id, evaluation_id)
        for proposal in submitted:
            assert proposal.snapshot is not None
            score_docs = self._scores.find_by_proposal(tenant_id, proposal.id)
            scored_ids = {doc["requirement_id"] for doc in score_docs}
            requirement_ids = {r.id for r in proposal.snapshot.requirements}
            if not requirement_ids.issubset(scored_ids):
                return False
        return True

    def _vendor_org_name(self, tenant_id: str, vendor_org_id: str) -> str:
        doc = self._vendor_orgs.find_by_id(tenant_id, vendor_org_id)
        return doc["name"] if doc else vendor_org_id

    def get_results(self, tenant_id: str, evaluation_id: str) -> dict[str, Any]:
        evaluation_doc = self._evaluations.find_by_id(tenant_id, evaluation_id)
        if evaluation_doc is None:
            raise EvaluationNotFoundError(evaluation_id)
        evaluation = Evaluation.from_document(evaluation_doc)
        if evaluation.status not in ("evaluating", "completed"):
            raise ResultsNotAvailableError(evaluation_id)

        submitted, drafts = self._submitted_and_draft_proposals(tenant_id, evaluation_id)
        fully_scored = self._is_fully_scored(tenant_id, evaluation_id)
        scoring_status = "complete" if fully_scored else "incomplete"
        if evaluation.status == "completed":
            scoring_status = "complete"

        proposal_results = []
        for proposal in submitted:
            assert proposal.snapshot is not None
            score_docs = self._scores.find_by_proposal(tenant_id, proposal.id)
            scores = [Score.from_document(d) for d in score_docs]
            requirements_by_id = {r.id: r for r in proposal.snapshot.requirements}

            functional_points = 0.0
            technical_points = 0.0
            mandatory_alerts = 0
            score_details = []
            for score in scores:
                requirement = requirements_by_id.get(score.requirement_id)
                title = requirement.title if requirement else score.requirement_id
                if score.dimension == "functional":
                    functional_points += score.weighted_points
                elif score.dimension == "technical":
                    technical_points += score.weighted_points
                if score.mandatory_alert:
                    mandatory_alerts += 1
                score_details.append(
                    {
                        "requirement_id": score.requirement_id,
                        "dimension": score.dimension,
                        "title": title,
                        "priority": score.priority,
                        "raw_score": score.score,
                        "comment": score.comment,
                        "requirement_weight": score.requirement_weight,
                        "weighted_points": score.weighted_points,
                        "version": score.version,
                        "evaluator_membership_id": score.updated_by_membership_id,
                        "mandatory_alert": score.mandatory_alert,
                    }
                )

            partial_earned = round(functional_points + technical_points, 2)
            proposal_results.append(
                {
                    "proposal_id": proposal.id,
                    "vendor_org_id": proposal.vendor_org_id,
                    "vendor_org_name": self._vendor_org_name(tenant_id, proposal.vendor_org_id),
                    "status": "submitted",
                    "functional": {
                        "earned_points": round(functional_points, 2),
                        "maximum_points": DIMENSION_MAX_POINTS["functional"],
                    },
                    "technical": {
                        "earned_points": round(technical_points, 2),
                        "maximum_points": DIMENSION_MAX_POINTS["technical"],
                    },
                    "economic": {
                        "status": "not_available",
                        "earned_points": None,
                        "maximum_points": ECONOMIC_MAX_POINTS,
                    },
                    "partial_result": {
                        "earned_points": partial_earned,
                        "maximum_points": _PARTIAL_RESULT_MAX_POINTS,
                        "model_coverage_percent": _PARTIAL_RESULT_MAX_POINTS,
                    },
                    "scores": score_details,
                    "mandatory_alerts_count": mandatory_alerts,
                }
            )

        draft_summaries = [
            {
                "proposal_id": p.id,
                "vendor_org_id": p.vendor_org_id,
                "vendor_org_name": self._vendor_org_name(tenant_id, p.vendor_org_id),
            }
            for p in drafts
        ]

        return {
            "result_status": "partial",
            "is_final": False,
            "scoring_status": scoring_status,
            "proposals": proposal_results,
            "draft_proposals": draft_summaries,
            "disclaimer": (
                "Resultado parcial - componente economico pendiente. "
                "No constituye recomendacion de adjudicacion."
            ),
        }

    def complete_evaluation(
        self, tenant_id: str, evaluation_id: str, *, actor: ActorContext
    ) -> Evaluation:
        evaluation_doc = self._evaluations.find_by_id(tenant_id, evaluation_id)
        if evaluation_doc is None:
            raise EvaluationNotFoundError(evaluation_id)
        evaluation = Evaluation.from_document(evaluation_doc)
        if evaluation.status != "evaluating":
            raise InvalidTransitionError(evaluation_id)
        if not self._is_fully_scored(tenant_id, evaluation_id):
            raise CompletionPreconditionError(evaluation_id)

        matched = self._evaluations.transition_status(
            tenant_id,
            evaluation_id,
            "evaluating",
            "completed",
            {"completed_at": datetime.now(UTC)},
        )
        if not matched:
            raise InvalidTransitionError(evaluation_id)
        self._audit.record(
            tenant_id=tenant_id,
            actor=actor,
            action="evaluation_completed",
            resource_type="evaluation",
            resource_id=evaluation_id,
            evaluation_id=evaluation_id,
            metadata={"from_status": "evaluating", "to_status": "completed"},
        )
        updated_doc = self._evaluations.find_by_id(tenant_id, evaluation_id)
        assert updated_doc is not None
        return Evaluation.from_document(updated_doc)
