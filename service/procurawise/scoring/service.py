from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from pymongo.errors import DuplicateKeyError

from procurawise.ai.repository import AIExecutionRepository
from procurawise.assignments.repository import AssignmentRepository
from procurawise.assignments.service import ECONOMIC_SECTION
from procurawise.audit.service import AuditEventService
from procurawise.evaluations.exceptions import (
    CompletionPreconditionError,
    EvaluationNotFoundError,
    InvalidTransitionError,
)
from procurawise.evaluations.models import (
    DEFAULT_COMMERCIAL_WEIGHTS,
    DEFAULT_RISK_WEIGHTS,
    DIMENSION_MAX_POINTS,
    ECONOMIC_MAX_POINTS,
    Evaluation,
)
from procurawise.evaluations.repository import EvaluationRepository
from procurawise.identity.repository import VendorOrganizationRepository
from procurawise.proposals.exceptions import ProposalNotFoundError
from procurawise.proposals.models import Proposal
from procurawise.proposals.repository import ProposalRepository
from procurawise.scoring.economic_formulas import (
    EconomicSubtotalResult,
    calculate_economic_points,
    calculate_rubric_pct,
    calculate_tco_normalized_pct,
)
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
from procurawise.scoring.models import CriterionScore, EconomicAssessment, Score
from procurawise.scoring.repository import EconomicAssessmentRepository, ScoreRepository
from procurawise.shared.context import ActorContext
from procurawise.shared.roles import EVALUATOR_ROLES

_EXTREME_SCORES = {0, 1, 2, 5}

# functional(40) + technical(20) = 60 of the eventual 100-point model;
# partial_result always reports against this 60, regardless of whether the
# economic(40) component is available yet - see final_result (Fase 20) for
# the 100-point total once all three dimensions are complete.
_PARTIAL_RESULT_MAX_POINTS = sum(DIMENSION_MAX_POINTS.values())


def enforce_section_assignment(
    assignments: AssignmentRepository,
    tenant_id: str,
    evaluation_id: str,
    dimension: str,
    section: str,
    actor: ActorContext,
) -> None:
    """An evaluator sub-role may act on any (dimension, section) that has no
    Assignment recorded yet (today's VS-2B behavior, unchanged) - but once at
    least one evaluator has been assigned to a section, acting on it is
    restricted to the assigned evaluator(s) only, even for other holders of
    the same sub-role (Fase 9 Block 3, spec §4/§6.7). The evaluation_owner is
    never restricted by this check.

    Module-level (not a ScoringService method) since Fase 18 needs the exact
    same gate for requesting/reviewing an AI score suggestion - ai.service
    imports this function directly rather than duplicating the check or
    importing a private method."""
    if actor.role not in EVALUATOR_ROLES:
        return
    assignments_docs = assignments.list_for_section(tenant_id, evaluation_id, dimension, section)
    if not assignments_docs:
        return
    assigned_membership_ids = {doc["evaluator_membership_id"] for doc in assignments_docs}
    if actor.membership_id not in assigned_membership_ids:
        raise SectionNotAssignedToActorError(section)


class ScoringService:
    def __init__(
        self,
        scores: ScoreRepository,
        proposals: ProposalRepository,
        evaluations: EvaluationRepository,
        vendor_orgs: VendorOrganizationRepository,
        audit: AuditEventService,
        assignments: AssignmentRepository,
        ai_executions: AIExecutionRepository,
        economic_assessments: EconomicAssessmentRepository,
    ) -> None:
        self._scores = scores
        self._proposals = proposals
        self._evaluations = evaluations
        self._vendor_orgs = vendor_orgs
        self._audit = audit
        self._assignments = assignments
        self._ai_executions = ai_executions
        self._economic_assessments = economic_assessments

    def _enforce_section_assignment(
        self, tenant_id: str, evaluation_id: str, dimension: str, section: str, actor: ActorContext
    ) -> None:
        enforce_section_assignment(
            self._assignments, tenant_id, evaluation_id, dimension, section, actor
        )

    def _ai_decision(
        self,
        tenant_id: str,
        source_ai_execution_id: str | None,
        requirement_id: str,
        score_value: int,
    ) -> str | None:
        """Fase 18 (ADR 0022): never trusts the client's own claim of
        "accepted"/"modified" - derives it server-side by comparing the
        submitted score against the referenced job's own persisted
        candidate. Returns None (no metadata added) if the execution/
        candidate can't be found - a stale or foreign id degrades to "just a
        manual score with an unresolvable reference", never an error, since
        this is provenance for audit only, not a precondition of the write."""
        if source_ai_execution_id is None:
            return None
        doc = self._ai_executions.find_by_id(tenant_id, source_ai_execution_id)
        if doc is None or doc.get("candidates") is None:
            return None
        candidate = next(
            (c for c in doc["candidates"] if c.get("requirement_id") == requirement_id), None
        )
        if candidate is None:
            return None
        return "accepted" if candidate.get("suggested_score") == score_value else "modified"

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
        source_ai_execution_id: str | None = None,
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

        ai_decision = self._ai_decision(
            tenant_id, source_ai_execution_id, requirement_id, score_value
        )
        audit_metadata: dict[str, Any] = {"requirement_id": requirement_id, "score": score_value}
        if ai_decision is not None:
            audit_metadata["ai_decision"] = ai_decision

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
                source_ai_execution_id=source_ai_execution_id,
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
                metadata=audit_metadata,
            )
            return score

        existing = Score.from_document(existing_doc)
        if expected_version != existing.version:
            raise StaleScoreVersionError(requirement_id)
        matched = self._scores.update(
            tenant_id,
            existing.id,
            expected_version,
            score_value,
            comment,
            membership_id,
            source_ai_execution_id,
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
            metadata=audit_metadata,
        )
        return updated

    @staticmethod
    def _validate_criterion_scores(
        scores: list[CriterionScore], expected_keys: dict[str, float]
    ) -> None:
        if {s.criterion_key for s in scores} != set(expected_keys.keys()):
            raise InvalidCriterionScoreError(f"keys must be exactly {sorted(expected_keys)}")
        for criterion in scores:
            if criterion.score is not None and not (0 <= criterion.score <= 5):
                raise InvalidCriterionScoreError(f"{criterion.criterion_key}: score must be 0-5")
            comment_required = criterion.score is None or criterion.score in _EXTREME_SCORES
            if comment_required and not criterion.comment:
                raise InvalidCriterionScoreError(
                    f"{criterion.criterion_key}: comment required for this score"
                )

    def upsert_economic_assessment(
        self,
        tenant_id: str,
        evaluation_id: str,
        proposal_id: str,
        commercial_scores: list[CriterionScore],
        risk_scores: list[CriterionScore],
        expected_version: int | None,
        membership_id: str,
        *,
        actor: ActorContext,
    ) -> EconomicAssessment:
        """Fase 20 (ADR 0009) - same gates as upsert_score (evaluating +
        submitted + snapshot present), same enforce_section_assignment reuse
        (with the fixed "economic" sentinel, see assignments.service.
        ECONOMIC_SECTION), same optimistic-concurrency-by-version contract.
        Writes the whole 10-criterion assessment as one document, never a
        partial patch - the caller always sends the full commercial_scores/
        risk_scores lists (mirrors how a vendor's whole cost_items list is
        replaced, not patched, in tco/proposals.service)."""
        self._validate_criterion_scores(commercial_scores, DEFAULT_COMMERCIAL_WEIGHTS)
        self._validate_criterion_scores(risk_scores, DEFAULT_RISK_WEIGHTS)

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

        self._enforce_section_assignment(
            tenant_id, evaluation_id, "economic", ECONOMIC_SECTION, actor
        )

        existing_doc = self._economic_assessments.find_by_evaluation_and_proposal(
            tenant_id, evaluation_id, proposal_id
        )

        if existing_doc is None:
            if expected_version is not None:
                raise StaleEconomicAssessmentVersionError(proposal_id)
            assessment = EconomicAssessment.create(
                tenant_id=tenant_id,
                evaluation_id=evaluation_id,
                proposal_id=proposal_id,
                commercial_scores=commercial_scores,
                risk_scores=risk_scores,
                membership_id=membership_id,
            )
            try:
                self._economic_assessments.insert(tenant_id, assessment.to_document())
            except DuplicateKeyError:
                raise StaleEconomicAssessmentVersionError(proposal_id) from None
            self._audit.record(
                tenant_id=tenant_id,
                actor=actor,
                action="economic_assessment_created",
                resource_type="economic_assessment",
                resource_id=assessment.id,
                evaluation_id=evaluation_id,
                proposal_id=proposal_id,
                version=assessment.version,
                metadata={
                    "commercial_scored_count": sum(
                        1 for s in commercial_scores if s.score is not None
                    ),
                    "risk_scored_count": sum(1 for s in risk_scores if s.score is not None),
                },
            )
            return assessment

        existing = EconomicAssessment.from_document(existing_doc)
        if expected_version != existing.version:
            raise StaleEconomicAssessmentVersionError(proposal_id)
        matched = self._economic_assessments.update(
            tenant_id,
            existing.id,
            expected_version,
            [s.to_document() for s in commercial_scores],
            [s.to_document() for s in risk_scores],
            membership_id,
        )
        if not matched:
            raise StaleEconomicAssessmentVersionError(proposal_id)
        updated_doc = self._economic_assessments.find_by_evaluation_and_proposal(
            tenant_id, evaluation_id, proposal_id
        )
        assert updated_doc is not None
        updated = EconomicAssessment.from_document(updated_doc)
        self._audit.record(
            tenant_id=tenant_id,
            actor=actor,
            action="economic_assessment_updated",
            resource_type="economic_assessment",
            resource_id=updated.id,
            evaluation_id=evaluation_id,
            proposal_id=proposal_id,
            version=updated.version,
            metadata={
                "commercial_scored_count": sum(1 for s in commercial_scores if s.score is not None),
                "risk_scored_count": sum(1 for s in risk_scores if s.score is not None),
            },
        )
        return updated

    def get_economic_assessment(
        self, tenant_id: str, evaluation_id: str, proposal_id: str
    ) -> EconomicAssessment:
        """Fase 20 - the read surface a client needs to build a valid
        upsert_economic_assessment call (current scores + version), same
        role as RequirementScoreDetail is for Score - but EconomicAssessment
        has no per-requirement aggregate to piggyback on, so it gets its own
        dedicated GET instead of living inside get_results()."""
        proposal_doc = self._proposals.find_by_id(tenant_id, proposal_id)
        if proposal_doc is None or proposal_doc["evaluation_id"] != evaluation_id:
            raise ProposalNotFoundError(proposal_id)
        assessment_doc = self._economic_assessments.find_by_evaluation_and_proposal(
            tenant_id, evaluation_id, proposal_id
        )
        if assessment_doc is None:
            raise EconomicAssessmentNotFoundError(proposal_id)
        return EconomicAssessment.from_document(assessment_doc)

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

    def _economic_subtotals(
        self, tenant_id: str, evaluation: Evaluation, submitted: list[Proposal]
    ) -> dict[str, EconomicSubtotalResult]:
        """Fase 20 (ADR 0009) - TCO normalized % is computed by comparing
        every submitted proposal's frozen tco_result.grand_total (Fase 19)
        in one pass (calculate_tco_normalized_pct needs the full comparable
        set); commercial/risk % are computed per-proposal from that
        proposal's own EconomicAssessment, if any. Everything here is
        derived in vivo, never cached - same principle already applied to
        functional_points/technical_points/partial_result below."""
        tco_totals: dict[str, Decimal | None] = {
            p.id: (
                p.snapshot.tco_result.grand_total if p.snapshot and p.snapshot.tco_result else None
            )
            for p in submitted
        }
        tco_results = calculate_tco_normalized_pct(tco_totals)
        weights = evaluation.economic_criteria_weights
        subtotals: dict[str, EconomicSubtotalResult] = {}
        for proposal in submitted:
            assessment_doc = self._economic_assessments.find_by_evaluation_and_proposal(
                tenant_id, evaluation.id, proposal.id
            )
            commercial_pct = risk_pct = None
            if assessment_doc is not None:
                assessment = EconomicAssessment.from_document(assessment_doc)
                commercial_pct = calculate_rubric_pct(
                    assessment.commercial_scores, weights.commercial
                )
                risk_pct = calculate_rubric_pct(assessment.risk_scores, weights.risk)
            tco_result = tco_results[proposal.id]
            tco_pct = tco_result.pct if tco_result.status == "available" else None
            subtotals[proposal.id] = calculate_economic_points(tco_pct, commercial_pct, risk_pct)
        return subtotals

    @staticmethod
    def _is_economically_assessed(economic_subtotals: dict[str, EconomicSubtotalResult]) -> bool:
        return all(result.status == "available" for result in economic_subtotals.values())

    def get_results(self, tenant_id: str, evaluation_id: str) -> dict[str, Any]:
        evaluation_doc = self._evaluations.find_by_id(tenant_id, evaluation_id)
        if evaluation_doc is None:
            raise EvaluationNotFoundError(evaluation_id)
        evaluation = Evaluation.from_document(evaluation_doc)
        if evaluation.status not in ("evaluating", "completed"):
            raise ResultsNotAvailableError(evaluation_id)

        submitted, drafts = self._submitted_and_draft_proposals(tenant_id, evaluation_id)
        economic_subtotals = self._economic_subtotals(tenant_id, evaluation, submitted)

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

            requirement_ids = set(requirements_by_id.keys())
            scored_ids = {s.requirement_id for s in scores}
            functional_technical_complete = requirement_ids.issubset(scored_ids)
            economic_result = economic_subtotals[proposal.id]

            final_result = None
            if functional_technical_complete and economic_result.status == "available":
                assert economic_result.earned_points is not None
                final_result = {
                    "total_points": round(
                        functional_points + technical_points + economic_result.earned_points, 2
                    ),
                    "maximum_points": _PARTIAL_RESULT_MAX_POINTS + ECONOMIC_MAX_POINTS,
                }

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
                        "status": economic_result.status,
                        "earned_points": economic_result.earned_points,
                        "maximum_points": ECONOMIC_MAX_POINTS,
                    },
                    "partial_result": {
                        "earned_points": partial_earned,
                        "maximum_points": _PARTIAL_RESULT_MAX_POINTS,
                        "model_coverage_percent": _PARTIAL_RESULT_MAX_POINTS,
                    },
                    "final_result": final_result,
                    "scores": score_details,
                    "mandatory_alerts_count": mandatory_alerts,
                }
            )

        is_final = bool(proposal_results) and all(
            p["final_result"] is not None for p in proposal_results
        )
        fully_scored = self._is_fully_scored(tenant_id, evaluation_id) and (
            self._is_economically_assessed(economic_subtotals)
        )
        scoring_status = "complete" if fully_scored else "incomplete"
        if evaluation.status == "completed":
            scoring_status = "complete"

        draft_summaries = [
            {
                "proposal_id": p.id,
                "vendor_org_id": p.vendor_org_id,
                "vendor_org_name": self._vendor_org_name(tenant_id, p.vendor_org_id),
            }
            for p in drafts
        ]

        disclaimer = (
            "Resultado final. No constituye recomendacion de adjudicacion."
            if is_final
            else "Resultado parcial. No constituye recomendacion de adjudicacion."
        )
        return {
            "result_status": "final" if is_final else "partial",
            "is_final": is_final,
            "scoring_status": scoring_status,
            "proposals": proposal_results,
            "draft_proposals": draft_summaries,
            "disclaimer": disclaimer,
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
        submitted, _drafts = self._submitted_and_draft_proposals(tenant_id, evaluation_id)
        economic_subtotals = self._economic_subtotals(tenant_id, evaluation, submitted)
        if not self._is_economically_assessed(economic_subtotals):
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
