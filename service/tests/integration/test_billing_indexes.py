from datetime import UTC, datetime

import pytest
from pymongo.errors import DuplicateKeyError

from procurawise.shared.migrations import MIGRATIONS_DIR, _load_migration_module

pytestmark = pytest.mark.docker

_MIGRATION_0022 = _load_migration_module(MIGRATIONS_DIR / "0022_billing_indexes.py")


@pytest.fixture(autouse=True)
def _clean_billing_collections(mongo_test_db):
    yield
    mongo_test_db["purchases"].drop()
    mongo_test_db["billing_webhook_events"].drop()


def test_migration_creates_expected_indexes(mongo_test_db) -> None:
    _MIGRATION_0022.apply(mongo_test_db)
    purchase_indexes = {idx["name"]: idx for idx in mongo_test_db["purchases"].list_indexes()}
    webhook_event_indexes = {
        idx["name"]: idx for idx in mongo_test_db["billing_webhook_events"].list_indexes()
    }

    assert "idx_purchases_tenant_created_at" in purchase_indexes
    assert "uniq_purchases_stripe_session" in purchase_indexes
    assert purchase_indexes["uniq_purchases_stripe_session"]["unique"] is True
    assert "idx_purchases_tenant_evaluation" in purchase_indexes
    assert "idx_purchases_cross_tenant_cursor" in purchase_indexes
    assert "ttl_billing_webhook_events_expires_at" in webhook_event_indexes
    assert webhook_event_indexes["ttl_billing_webhook_events_expires_at"]["expireAfterSeconds"] == 0


def test_migration_apply_is_idempotent(mongo_test_db) -> None:
    _MIGRATION_0022.apply(mongo_test_db)
    _MIGRATION_0022.apply(mongo_test_db)
    purchase_indexes = {idx["name"] for idx in mongo_test_db["purchases"].list_indexes()}
    assert "uniq_purchases_stripe_session" in purchase_indexes


def test_unique_index_rejects_duplicate_stripe_session_id(mongo_test_db) -> None:
    _MIGRATION_0022.apply(mongo_test_db)
    base = {
        "tenant_id": "tenant-1",
        "evaluation_id": "eval-1",
        "initiated_by_membership_id": "m-owner",
        "status": "pending",
        "stripe_price_id": "price_1",
        "stripe_payment_intent_id": None,
        "amount_total": None,
        "currency": None,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
        "paid_at": None,
    }
    mongo_test_db["purchases"].insert_one(
        {**base, "_id": "purchase-1", "stripe_checkout_session_id": "cs_dup"}
    )
    with pytest.raises(DuplicateKeyError):
        mongo_test_db["purchases"].insert_one(
            {**base, "_id": "purchase-2", "stripe_checkout_session_id": "cs_dup"}
        )
