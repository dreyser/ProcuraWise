class QuestionNotFoundError(Exception):
    """No Question exists for this id within the caller's tenant/proposal
    scope (or, for vendor-side service methods, vendor_org_id scope)."""


class InvalidQuestionTransitionError(Exception):
    """The action requires a Question.status/Evaluation.status combination
    that does not currently hold (e.g. Evaluation not collecting_responses,
    or answering/withdrawing a Question that isn't "open")."""


class StaleQuestionVersionError(Exception):
    """expected_version did not match Question.version at write time - the
    caller must re-fetch and retry."""


class QuestionValidationError(Exception):
    """The request is structurally inconsistent (e.g. scope="requirement"
    without a requirement_id, or vice versa) - same role as proposals'
    AnswerValidationError, a conditional rule Pydantic's field-level
    validation alone cannot express."""
