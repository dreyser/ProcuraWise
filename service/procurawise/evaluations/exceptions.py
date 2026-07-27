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
