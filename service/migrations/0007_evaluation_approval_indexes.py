from pymongo.database import Database


def apply(db: Database) -> None:
    db["evaluations"].create_index(
        [("tenant_id", 1), ("approval_status", 1)],
        name="idx_evaluations_tenant_approval_status",
    )
    db["evaluations"].create_index(
        [("tenant_id", 1), ("approver_membership_id", 1), ("approval_status", 1)],
        name="idx_evaluations_tenant_approver_status",
    )
    db["evaluation_snapshots"].create_index(
        [("tenant_id", 1), ("evaluation_id", 1)],
        unique=True,
        name="uniq_evaluation_snapshot_per_evaluation",
    )
