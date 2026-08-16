"""Regression test for the real staging defect where `timeout` leaked into
the Stripe Checkout Session API payload ("Received unknown parameter:
timeout"). Mocks the SDK call site directly (`StripeClient.v1.checkout.
sessions.create`) to assert on the exact params/options sent - the sandbox
integration test (`tests/integration/test_stripe_sandbox_checkout.py`,
opt-in, never in CI) only asserts the response shape, not the request."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import stripe

from procurawise.billing.models import CheckoutSessionRequest
from procurawise.billing.stripe_payment_provider import StripePaymentProvider


def _provider() -> StripePaymentProvider:
    return StripePaymentProvider(
        api_key="sk_test_unit", webhook_secret="whsec_test_unit", timeout_seconds=7
    )


def _request(*, customer_id: str | None = None) -> CheckoutSessionRequest:
    return CheckoutSessionRequest(
        price_id="price_test_1",
        quantity=1,
        success_url="https://app.example.com/success",
        cancel_url="https://app.example.com/cancel",
        idempotency_key="idem-key-1",
        metadata={"tenant_id": "tenant-1", "purchase_id": "purchase-1"},
        customer_id=customer_id,
    )


def _fake_session(*, session_id: str = "cs_test_1") -> SimpleNamespace:
    return SimpleNamespace(id=session_id, url=f"https://checkout.stripe.com/c/pay/{session_id}")


def test_create_checkout_session_never_sends_timeout_as_an_api_param() -> None:
    provider = _provider()
    provider._client.v1.checkout.sessions.create = MagicMock(  # type: ignore[method-assign]
        return_value=_fake_session()
    )

    provider.create_checkout_session(_request())

    call = provider._client.v1.checkout.sessions.create.call_args
    assert "timeout" not in call.kwargs["params"]
    assert "timeout" not in call.kwargs["options"]


def test_create_checkout_session_sends_expected_params_and_idempotency_key() -> None:
    provider = _provider()
    provider._client.v1.checkout.sessions.create = MagicMock(  # type: ignore[method-assign]
        return_value=_fake_session()
    )

    provider.create_checkout_session(_request())

    call = provider._client.v1.checkout.sessions.create.call_args
    assert call.kwargs["params"] == {
        "mode": "payment",
        "line_items": [{"price": "price_test_1", "quantity": 1}],
        "payment_method_types": ["card"],
        "success_url": "https://app.example.com/success",
        "cancel_url": "https://app.example.com/cancel",
        "metadata": {"tenant_id": "tenant-1", "purchase_id": "purchase-1"},
    }
    assert call.kwargs["options"] == {"idempotency_key": "idem-key-1"}


def test_create_checkout_session_includes_customer_only_when_provided() -> None:
    provider = _provider()
    provider._client.v1.checkout.sessions.create = MagicMock(  # type: ignore[method-assign]
        return_value=_fake_session()
    )

    provider.create_checkout_session(_request(customer_id="cus_test_1"))

    call = provider._client.v1.checkout.sessions.create.call_args
    assert call.kwargs["params"]["customer"] == "cus_test_1"


def test_stripe_client_is_bound_to_a_requests_client_with_the_configured_timeout() -> None:
    provider = _provider()

    http_client = provider._client._requestor._client
    assert isinstance(http_client, stripe.RequestsClient)
    assert http_client._timeout == 7
