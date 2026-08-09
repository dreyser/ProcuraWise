from pymongo.database import Database


def apply(db: Database) -> None:
    db["purchases"].create_index(
        [("tenant_id", 1), ("created_at", -1)],
        name="idx_purchases_tenant_created_at",
    )
    db["purchases"].create_index(
        "stripe_checkout_session_id",
        name="uniq_purchases_stripe_session",
        unique=True,
    )
    db["purchases"].create_index(
        [("tenant_id", 1), ("evaluation_id", 1)],
        name="idx_purchases_tenant_evaluation",
    )
    db["purchases"].create_index(
        [("created_at", -1), ("_id", -1)],
        name="idx_purchases_cross_tenant_cursor",
    )
    db["billing_webhook_events"].create_index(
        "expires_at", name="ttl_billing_webhook_events_expires_at", expireAfterSeconds=0
    )
