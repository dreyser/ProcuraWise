class InvalidWebhookSignatureError(Exception):
    """The `Stripe-Signature` header did not verify against
    `stripe_webhook_secret` for the given raw payload - covers a genuinely
    forged request, a stale/rotated secret, or a timestamp outside Stripe's
    replay-tolerance window. Verification and parsing are one atomic
    operation (PaymentProvider.parse_webhook_event) so no caller can ever
    parse a webhook body without also verifying it."""


class PurchaseNotFoundError(Exception):
    """No Purchase exists for this id, within the caller's tenant - same
    "never confirm which case applies" 404 discipline as every other
    tenant-scoped NotFoundError in this codebase."""


class EvaluationNotOwnedByTenantError(Exception):
    """The evaluation_id in a checkout request does not belong to the
    caller's own tenant - a 404, never a 403 (never confirm the evaluation
    exists elsewhere)."""


class PurchaseAlreadyPaidError(Exception):
    """A checkout was requested for an (tenant, evaluation) pair that
    already has a paid Purchase - a second charge would be a real billing
    bug, not a benign retry."""
