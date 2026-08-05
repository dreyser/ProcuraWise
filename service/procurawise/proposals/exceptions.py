class ProposalNotFoundError(Exception):
    """No Proposal exists for this id (or evaluation+vendor pair) within the
    caller's tenant/vendor scope."""


class StaleVersionError(Exception):
    """expected_version did not match Proposal.version at write time - the
    caller must re-fetch and retry. Also raised when the proposal is no
    longer draft (submit already happened)."""


class InvalidProposalTransitionError(Exception):
    """The action requires Evaluation.status/Proposal.status combination that
    does not currently hold (e.g. Evaluation not collecting_responses)."""


class AnswerValidationError(Exception):
    """ProposalAnswer.value does not match what the frozen requirement's
    response_type requires."""


class IncompleteRequiredAnswersError(Exception):
    """submit was requested but at least one requirement with required=true
    has no answer value yet."""


class ProposalNotSubmittedError(Exception):
    """Fase 21 (FR-047) - reopen() was called on a Proposal that is not
    currently `status="submitted"` (still draft, or already reopened for
    the round already in progress)."""


class ProposalAlreadyMaxRoundsError(Exception):
    """Fase 21 (ADR 0013/mvp-scope.md): the MVP allows at most one
    negotiation round (Ronda 0 + Ronda 1) - reopen() was called on a
    Proposal that already has 2 snapshots."""


class InvalidReopenReasonError(Exception):
    """Fase 21 (FR-047: "motivo") - reopen()'s `reason` was empty or
    whitespace-only."""
