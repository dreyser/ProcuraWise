from pymongo.database import Database


def apply(db: Database) -> None:
    db["assignments"].create_index(
        [
            ("tenant_id", 1),
            ("evaluation_id", 1),
            ("dimension", 1),
            ("section", 1),
            ("evaluator_membership_id", 1),
        ],
        unique=True,
        name="uniq_assignment_natural_key",
    )
    db["assignments"].create_index(
        [("tenant_id", 1), ("evaluation_id", 1)], name="idx_assignment_tenant_evaluation"
    )
    db["assignments"].create_index(
        [("tenant_id", 1), ("evaluation_id", 1), ("evaluator_membership_id", 1)],
        name="idx_assignment_tenant_evaluation_evaluator",
    )
