"""Fase 25 (billing/admin, ADR 0025) - model-level coverage for Purchase/
BillingAccount: safe defaults on create() (status="pending", no amount known
yet), a lossless to_document/from_document round trip, and BillingAccount's
deterministic id (== tenant_id)."""

from datetime import UTC, datetime

from procurawise.billing.models import BillingAccount, Purchase


def test_purchase_create_defaults_to_pending_with_no_amount_known_yet() -> None:
    purchase = Purchase.create(
        id="purchase-1",
        tenant_id="tenant-1",
        evaluation_id="eval-1",
        initiated_by_membership_id="m-owner",
        stripe_checkout_session_id="cs_test_1",
        stripe_price_id="price_test_1",
        checkout_url="https://checkout.stripe.com/test",
    )
    assert purchase.status == "pending"
    assert purchase.stripe_payment_intent_id is None
    assert purchase.amount_total is None
    assert purchase.currency is None
    assert purchase.paid_at is None


def test_purchase_document_round_trip_is_lossless() -> None:
    now = datetime.now(UTC)
    purchase = Purchase(
        id="purchase-1",
        tenant_id="tenant-1",
        evaluation_id="eval-1",
        initiated_by_membership_id="m-owner",
        status="paid",
        stripe_checkout_session_id="cs_test_1",
        stripe_price_id="price_test_1",
        checkout_url="https://checkout.stripe.com/test",
        stripe_payment_intent_id="pi_test_1",
        amount_total=150000,
        currency="mxn",
        created_at=now,
        updated_at=now,
        paid_at=now,
    )
    restored = Purchase.from_document(purchase.to_document())
    assert restored == purchase


def test_purchase_document_round_trip_tolerates_missing_optional_keys() -> None:
    now = datetime.now(UTC)
    minimal_doc = {
        "_id": "purchase-1",
        "tenant_id": "tenant-1",
        "evaluation_id": "eval-1",
        "initiated_by_membership_id": "m-owner",
        "status": "pending",
        "stripe_checkout_session_id": "cs_test_1",
        "stripe_price_id": "price_test_1",
        "checkout_url": "https://checkout.stripe.com/test",
        "created_at": now,
        "updated_at": now,
    }
    purchase = Purchase.from_document(minimal_doc)
    assert purchase.stripe_payment_intent_id is None
    assert purchase.amount_total is None
    assert purchase.currency is None
    assert purchase.paid_at is None


def test_billing_account_id_is_the_tenant_id() -> None:
    account = BillingAccount.create(tenant_id="tenant-1")
    assert account.tenant_id == "tenant-1"
    doc = account.to_document()
    assert doc["_id"] == "tenant-1"
    assert doc["stripe_customer_id"] is None


def test_billing_account_document_round_trip_is_lossless() -> None:
    now = datetime.now(UTC)
    account = BillingAccount(
        tenant_id="tenant-1",
        stripe_customer_id="cus_test_1",
        created_at=now,
        updated_at=now,
    )
    restored = BillingAccount.from_document(account.to_document())
    assert restored == account
