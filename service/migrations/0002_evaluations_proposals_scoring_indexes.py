from pymongo.database import Database


def apply(db: Database) -> None:
    db["evaluations"].create_index(
        [("tenant_id", 1), ("status", 1)], name="idx_evaluation_tenant_status"
    )
    db["proposals"].create_index(
        [("tenant_id", 1), ("evaluation_id", 1), ("vendor_org_id", 1)],
        unique=True,
        name="uniq_proposal_tenant_evaluation_vendor",
    )
    db["proposals"].create_index(
        [("tenant_id", 1), ("evaluation_id", 1)], name="idx_proposal_tenant_evaluation"
    )
    db["proposals"].create_index(
        [("tenant_id", 1), ("vendor_org_id", 1)], name="idx_proposal_tenant_vendor"
    )
    db["scores"].create_index(
        [
            ("tenant_id", 1),
            ("evaluation_id", 1),
            ("proposal_id", 1),
            ("snapshot_id", 1),
            ("requirement_id", 1),
        ],
        unique=True,
        name="uniq_score_natural_key",
    )
    db["scores"].create_index(
        [("tenant_id", 1), ("proposal_id", 1)], name="idx_score_tenant_proposal"
    )
