from pymongo.database import Database


def apply(db: Database) -> None:
    db["knowledge_templates"].create_index(
        [("tenant_id", 1), ("created_at", -1)],
        name="idx_knowledge_template_tenant_created_at",
    )
