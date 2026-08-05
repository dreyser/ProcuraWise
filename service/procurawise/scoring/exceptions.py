class ScoreOutOfRangeError(Exception):
    """score must be an integer 0-5 inclusive."""


class RequirementNotInSnapshotError(Exception):
    """requirement_id does not exist in the target Proposal's frozen
    snapshot - a score can never reference a mutable, unfrozen requirement."""


class ScoringPreconditionError(Exception):
    """Evaluation is not `evaluating` or the target Proposal is not
    `submitted` - scores may only be written under those conditions."""


class StaleScoreVersionError(Exception):
    """expected_version did not match the current Score.version."""


class ResultsNotAvailableError(Exception):
    """GET /results was called while Evaluation is still draft or
    collecting_responses - nothing scoreable exists yet."""


class SectionNotAssignedToActorError(Exception):
    """The requirement's (dimension, section) has at least one Assignment
    recorded, and the acting evaluator is not one of the assigned
    evaluator_membership_ids for it (Fase 9 Block 3)."""


class InvalidCriterionScoreError(Exception):
    """Fase 20 (ADR 0009): a commercial/risk CriterionScore's key set doesn't
    match the fixed rubric exactly, a score is outside 0-5, or a required
    comment (score in {0,1,2,5} or score is None/"N/A") is missing."""


class StaleEconomicAssessmentVersionError(Exception):
    """expected_version did not match the current EconomicAssessment.version."""


class EconomicAssessmentNotFoundError(Exception):
    """No EconomicAssessment has been written yet for this (evaluation_id,
    proposal_id) - distinct from the proposal/evaluation itself not
    existing, which raises EvaluationNotFoundError/ProposalNotFoundError."""
