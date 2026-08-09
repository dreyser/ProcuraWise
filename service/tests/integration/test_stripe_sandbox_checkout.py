"""Fase 25 (billing, ADR 0025, plan Bloqueante #3): opt-in only, real network
call against a Stripe test-mode account - creates one real Checkout Session
(never a charge, no card is entered), then leaves it to expire on its own.
Never selected by `make test`/`make test-integration`; run explicitly:

    cd service
    STRIPE_SECRET_KEY=sk_test_... STRIPE_PRICE_ID_EVALUATION=price_... \\
        uv run pytest -m stripe_sandbox -q --no-cov

See docs/operations/deployment.md for how to provision the test-mode
account, Price, and webhook secret this exercises.
"""

import os
from uuid import uuid4

import pytest

from procurawise.billing.models import CheckoutSessionRequest

STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY")
STRIPE_PRICE_ID_EVALUATION = os.environ.get("STRIPE_PRICE_ID_EVALUATION")

pytestmark = [
    pytest.mark.stripe_sandbox,
    pytest.mark.skipif(
        not (STRIPE_SECRET_KEY and STRIPE_PRICE_ID_EVALUATION),
        reason="opt-in: export STRIPE_SECRET_KEY and STRIPE_PRICE_ID_EVALUATION "
        "(Stripe test mode) to run - see docs/operations/deployment.md",
    ),
]


def test_creates_a_real_stripe_test_mode_checkout_session() -> None:
    assert STRIPE_SECRET_KEY is not None
    if not STRIPE_SECRET_KEY.startswith("sk_test_"):
        pytest.fail(
            "refusing to run: STRIPE_SECRET_KEY must be a test-mode key (sk_test_...) - "
            "this test creates a real Checkout Session against whatever account the key "
            "belongs to"
        )

    # Imported lazily, mirroring resolve_payment_provider()'s own deferred
    # import (billing/provider.py) - this module is the one exception where a
    # test is explicitly allowed to import the Stripe adapter directly, since
    # its entire purpose is exercising the real SDK boundary.
    from procurawise.billing.stripe_payment_provider import StripePaymentProvider

    provider = StripePaymentProvider(
        api_key=STRIPE_SECRET_KEY,
        webhook_secret="whsec_unused_for_session_creation",
        timeout_seconds=20,
    )
    request = CheckoutSessionRequest(
        price_id=STRIPE_PRICE_ID_EVALUATION,  # type: ignore[arg-type]
        quantity=1,
        success_url="https://example.com/billing/checkout/success?purchase_id=stripe-sandbox-test",
        cancel_url="https://example.com/billing/checkout/cancelled",
        idempotency_key=f"stripe-sandbox-pytest-{uuid4().hex}",
        metadata={"purpose": "stripe_sandbox_pytest_marker"},
        customer_id=None,
    )

    handle = provider.create_checkout_session(request)

    assert handle.session_id.startswith("cs_")
    assert handle.checkout_url.startswith("https://checkout.stripe.com/")
