"""Fase 25 (billing/admin, ADR 0025) - the single most valuable test in this
phase: exercises the REAL StripePaymentProvider.parse_webhook_event offline,
by hand-computing Stripe's own documented webhook signature scheme
(`t=<timestamp>,v1=<hex hmac-sha256 of "{timestamp}.{payload}">`) - no
network, no Stripe account, no mock of the SDK. This is what proves
signature verification and replay/timestamp tolerance actually work, not
just that some function was called."""

import hashlib
import hmac
import json
import time

import pytest

from procurawise.billing.exceptions import InvalidWebhookSignatureError
from procurawise.billing.stripe_payment_provider import StripePaymentProvider

_SECRET = "whsec_test_unit_secret"


def _event_payload(*, event_id: str = "evt_test_1", session_id: str = "cs_test_1") -> bytes:
    payload_dict = {
        "id": event_id,
        "object": "event",
        "type": "checkout.session.completed",
        "api_version": "2026-01-01",
        "created": int(time.time()),
        "data": {
            "object": {
                "id": session_id,
                "object": "checkout.session",
                "payment_status": "paid",
                "amount_total": 150000,
                "currency": "mxn",
                "payment_intent": "pi_test_1",
                "metadata": {"tenant_id": "tenant-1", "purchase_id": "purchase-1"},
            }
        },
    }
    return json.dumps(payload_dict).encode("utf-8")


def _signature_header(
    payload: bytes, *, secret: str = _SECRET, timestamp: int | None = None
) -> str:
    timestamp = timestamp if timestamp is not None else int(time.time())
    signed_payload = f"{timestamp}.".encode() + payload
    signature = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={signature}"


def _provider() -> StripePaymentProvider:
    return StripePaymentProvider(api_key="sk_test_unit", webhook_secret=_SECRET, timeout_seconds=5)


def test_valid_signature_is_accepted_and_parsed_into_a_provider_independent_event() -> None:
    payload = _event_payload()
    header = _signature_header(payload)

    event = _provider().parse_webhook_event(payload, header)

    assert event.event_id == "evt_test_1"
    assert event.event_type == "checkout.session.completed"
    assert event.session_id == "cs_test_1"
    assert event.payment_status == "paid"
    assert event.amount_total == 150000
    assert event.currency == "mxn"
    assert event.payment_intent_id == "pi_test_1"
    assert event.metadata == {"tenant_id": "tenant-1", "purchase_id": "purchase-1"}


def test_tampered_payload_is_rejected() -> None:
    payload = _event_payload()
    header = _signature_header(payload)
    tampered = payload.replace(b'"paid"', b'"unpaid"')

    with pytest.raises(InvalidWebhookSignatureError):
        _provider().parse_webhook_event(tampered, header)


def test_wrong_secret_is_rejected() -> None:
    payload = _event_payload()
    header = _signature_header(payload, secret="whsec_a_different_secret")

    with pytest.raises(InvalidWebhookSignatureError):
        _provider().parse_webhook_event(payload, header)


def test_timestamp_outside_tolerance_is_rejected() -> None:
    """Stripe's own replay defense (WebhookSignature.verify_header's
    `tolerance` window, DEFAULT_TOLERANCE=300s) - a signature computed for a
    payload from an hour ago is otherwise byte-for-byte valid."""
    payload = _event_payload()
    stale_timestamp = int(time.time()) - 3600
    header = _signature_header(payload, timestamp=stale_timestamp)

    with pytest.raises(InvalidWebhookSignatureError):
        _provider().parse_webhook_event(payload, header)


def test_missing_signature_header_is_rejected() -> None:
    payload = _event_payload()

    with pytest.raises(InvalidWebhookSignatureError):
        _provider().parse_webhook_event(payload, "")
