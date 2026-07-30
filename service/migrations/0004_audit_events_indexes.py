from pymongo.database import Database


def apply(db: Database) -> None:
    db["audit_events"].create_index(
        [("tenant_id", 1), ("occurred_at", -1)], name="idx_audit_tenant_occurred_at"
    )
    db["audit_events"].create_index(
        [("tenant_id", 1), ("evaluation_id", 1), ("occurred_at", -1)],
        name="idx_audit_tenant_evaluation_occurred_at",
    )
    db["audit_events"].create_index(
        [("tenant_id", 1), ("resource_type", 1), ("resource_id", 1), ("occurred_at", -1)],
        name="idx_audit_tenant_resource_occurred_at",
    )
    # Retention (plan §14, founder decision §18.3): MongoDB's TTL monitor
    # deletes documents once `expires_at` is in the past - expireAfterSeconds=0
    # means "expire exactly at the stored expires_at value", not 0 seconds
    # after insertion. Separate from the query indexes above, since expires_at
    # is never used to order or filter a consultable view.
    db["audit_events"].create_index("expires_at", name="ttl_audit_expires_at", expireAfterSeconds=0)
