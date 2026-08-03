from pymongo.database import Database


def apply(db: Database) -> None:
    # Fase 16: backs DocumentRepository.list_for_proposal/
    # list_current_for_proposal (every query is scoped by proposal_id, most
    # also filter by status).
    db["documents"].create_index(
        [("tenant_id", 1), ("proposal_id", 1), ("status", 1)],
        name="idx_documents_tenant_proposal_status",
    )
    # Backs find_current_for_slot's exact query shape (evidence upload/
    # replace, resolving "the" current document for a given requirement).
    db["documents"].create_index(
        [("tenant_id", 1), ("proposal_id", 1), ("requirement_id", 1)],
        name="idx_documents_tenant_proposal_requirement",
    )
