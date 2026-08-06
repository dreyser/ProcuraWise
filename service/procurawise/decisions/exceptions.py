class DecisionNotFoundError(Exception):
    """No Decision exists yet for this evaluation within the caller's tenant."""


class DecisionAlreadyExistsError(Exception):
    """create() was called but a Decision already exists for this evaluation
    - callers must use the update/patch flow instead."""


class EvaluationNotCompletedError(Exception):
    """A Decision may only be created or edited while
    Evaluation.status == "completed" (plan section 10, decision 1) - this
    evaluation has not reached that status yet."""


class InvalidDecisionStateError(Exception):
    """The requested transition is not valid from the Decision's current
    status (e.g. editing while "pending", or approving/rejecting while not
    "pending")."""


class DecisionPreconditionError(Exception):
    """request_approval was called but a precondition (outcome resolved,
    justification long enough, approver assigned) is not met."""


class SelectedProposalNotFoundError(Exception):
    """The given vendor_org_id has no submitted Proposal on this evaluation -
    either it was never linked, or its Proposal was never submitted."""


class ApproverMembershipNotFoundError(Exception):
    """target approver_membership_id does not exist in the caller's tenant."""


class ApproverRoleMismatchError(Exception):
    """The target Membership's role is not "approver"."""


class SelfApprovalError(Exception):
    """The target approver shares a user_id with the actor assigning them -
    the evaluation owner may not appoint themselves as the decision's
    approver (plan Bloqueante #1, Opcion B)."""


class NotAssignedApproverError(Exception):
    """approve/reject was called by someone other than the Decision's own
    assigned approver_membership_id (never Evaluation.approver_membership_id
    - the two are independent, see plan Bloqueante #1)."""


class DecisionSnapshotNotFoundError(Exception):
    """No DecisionSnapshot exists yet for this evaluation - either the
    Decision was never approved, or no Decision exists at all."""
