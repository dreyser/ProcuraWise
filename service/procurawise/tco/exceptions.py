class CostItemNotFoundError(Exception):
    """No CostItem with this id exists on the given Proposal."""


class InvalidCostItemError(Exception):
    """A CostItem field failed validation (range, currency, year ordering)."""


class MissingFxRateError(Exception):
    """No FXRate is available for a currency pair required by some CostItem
    at submit time - the submit fails closed, nothing is frozen (plan
    §6.C40-41/§11.2)."""
