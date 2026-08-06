from pymongo.database import Database


def apply(db: Database) -> None:
    db["reports"].create_index(
        [("tenant_id", 1), ("evaluation_id", 1), ("requested_at", -1)],
        name="idx_reports_tenant_evaluation_requested_at",
    )
    db["reports"].create_index(
        [("tenant_id", 1), ("status", 1)],
        name="idx_reports_tenant_status",
    )
