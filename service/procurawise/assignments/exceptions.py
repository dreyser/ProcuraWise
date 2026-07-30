class AssignmentNotFoundError(Exception):
    """No Assignment with this id exists for this tenant."""


class DuplicateAssignmentError(Exception):
    """This evaluator Membership is already assigned to this exact
    (evaluation, dimension, section)."""


class EvaluatorMembershipNotFoundError(Exception):
    """target evaluator_membership_id does not exist in the caller's tenant."""


class EvaluatorRoleMismatchError(Exception):
    """The target Membership's role is not the evaluator sub-role matching
    the Assignment's dimension (e.g. evaluator_technical assigned to a
    functional section)."""


class SectionNotFoundError(Exception):
    """No Requirement in this evaluation/dimension uses this section
    (Requirement.category) value - an Assignment can never reference a
    section that doesn't exist yet."""


class AssignmentUpdateNotPermittedError(Exception):
    """Only the assigned evaluator themselves, or the evaluation_owner, may
    update an Assignment's progress status."""
