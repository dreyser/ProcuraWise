from pymongo.database import Database


def apply(db: Database) -> None:
    db["decisions"].create_index(
        [("tenant_id", 1), ("status", 1)],
        name="idx_decisions_tenant_status",
    )
    db["decisions"].create_index(
        [("tenant_id", 1), ("approver_membership_id", 1), ("status", 1)],
        name="idx_decisions_tenant_approver_status",
    )
    db["decision_snapshots"].create_index(
        [("tenant_id", 1), ("evaluation_id", 1)],
        unique=True,
        name="uniq_decision_snapshot_per_evaluation",
    )
