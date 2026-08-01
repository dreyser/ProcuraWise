from pymongo.database import Database


def apply(db: Database) -> None:
    db["ai_executions"].create_index(
        [("tenant_id", 1), ("evaluation_id", 1), ("created_at", -1)],
        name="idx_ai_executions_tenant_evaluation_created_at",
    )
    # Retention (ADR 0021, same policy as audit_events - 1 year default,
    # ADR 0016): expireAfterSeconds=0 means "expire exactly at the stored
    # expires_at value", not 0 seconds after insertion.
    db["ai_executions"].create_index(
        "expires_at", name="ttl_ai_executions_expires_at", expireAfterSeconds=0
    )
