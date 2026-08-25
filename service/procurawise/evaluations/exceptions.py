class EvaluationNotFoundError(Exception):
    """No Evaluation exists for this id within the caller's tenant."""


class RequirementNotFoundError(Exception):
    """No Requirement exists for this id within the given Evaluation."""


class InvalidTransitionError(Exception):
    """The Evaluation is not in the status this action requires."""


class StartCollectionPreconditionError(Exception):
    """draft -> collecting_responses was requested but a precondition (at
    least one functional and one technical requirement, weights summing to
    the dimension allocation, at least one linked vendor) is not met."""


class VendorLimitExceededError(Exception):
    """The evaluation already has MAX_LINKED_VENDORS proposals linked."""


class VendorAlreadyLinkedError(Exception):
    """This vendor_org_id already has a Proposal on this evaluation."""


class VendorOrganizationNotFoundError(Exception):
    """No VendorOrganization exists for this id within the caller's tenant."""


class VendorNotLinkedError(Exception):
    """No Proposal (i.e. no vendor link) exists for this evaluation+vendor_org
    pair within the caller's tenant."""


class CompletionPreconditionError(Exception):
    """evaluating -> completed was requested but not every submitted
    Proposal has a canonical Score for every scoreable requirement in its
    snapshot."""


class ApproverMembershipNotFoundError(Exception):
    """target approver_membership_id does not exist in the caller's tenant."""


class ApproverRoleMismatchError(Exception):
    """The target Membership's role is not "approver"."""


class SelfApprovalError(Exception):
    """The target approver shares a user_id with the evaluation's creator -
    an owner may not appoint themselves as their own approver (plan §18)."""


class ApprovalPreconditionError(Exception):
    """request_approval was called but a precondition (weights complete,
    at least one vendor linked, approver assigned, response_deadline set)
    is not met."""


class NotAssignedApproverError(Exception):
    """approve/reject was called by someone other than the evaluation's
    assigned approver_membership_id."""


class ReviewerMembershipNotFoundError(Exception):
    """target reviewer_membership_id does not exist in the caller's tenant."""


class ReviewerRoleMismatchError(Exception):
    """The target Membership's role is not "internal_collaborator" (ADR
    0026: Reviewer is a capability over that existing role, not a new
    global Role value)."""


class SelfReviewError(Exception):
    """The target reviewer shares a user_id with the evaluation's creator -
    mirrors SelfApprovalError for the review stage (ADR 0026)."""


class ReviewPreconditionError(Exception):
    """request_review was called but a precondition (weights complete, at
    least one vendor linked, reviewer assigned) is not met."""


class NotAssignedReviewerError(Exception):
    """review/approve or review/reject was called by someone other than the
    evaluation's assigned reviewer_membership_id."""


class SnapshotNotFoundError(Exception):
    """No EvaluationSnapshot exists yet for this evaluation - either it has
    never been published, or (plan §29) it was published before Fase 12
    existed and has no retroactive snapshot."""


class InvalidEconomicWeightsError(Exception):
    """Fase 20 (ADR 0009): a commercial/risk weights group does not contain
    exactly the fixed set of criterion keys, or does not sum to 100."""
