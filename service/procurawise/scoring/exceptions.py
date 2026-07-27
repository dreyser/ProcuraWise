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
