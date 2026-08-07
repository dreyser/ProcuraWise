from pymongo.database import Database


def apply(db: Database) -> None:
    db["notifications"].create_index(
        [("tenant_id", 1), ("recipient_membership_id", 1), ("created_at", -1)],
        name="idx_notifications_tenant_recipient_created_at",
    )
    db["notifications"].create_index(
        [("tenant_id", 1), ("recipient_membership_id", 1), ("read_at", 1)],
        name="idx_notifications_tenant_recipient_read_at",
    )
    db["notifications"].create_index(
        [("email_status", 1), ("email_next_attempt_at", 1)],
        name="idx_notifications_email_retry_due",
    )
    db["notifications"].create_index(
        "expires_at", name="ttl_notifications_expires_at", expireAfterSeconds=0
    )
