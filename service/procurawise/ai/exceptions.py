class AIExecutionNotFoundError(Exception):
    """No AIExecution exists for this id within the caller's tenant, or it
    does not belong to the given evaluation_id."""


class InvalidAIExecutionStateError(Exception):
    """The requested action does not apply to this AIExecution's current status."""


class InvalidCandidateSelectionError(Exception):
    """candidate_indices referenced an index outside the AIExecution's
    candidates list."""
