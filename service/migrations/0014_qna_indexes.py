from pymongo.database import Database


def apply(db: Database) -> None:
    # Fase 17: backs QuestionRepository.list_for_evaluation_as_buyer/
    # list_published_for_evaluation (both scoped by evaluation_id, the
    # latter additionally filters by status/visibility in-memory-cheap
    # given the expected low volume per evaluation, see planning §D Q59).
    db["qna_questions"].create_index(
        [("tenant_id", 1), ("evaluation_id", 1), ("status", 1)],
        name="idx_qna_questions_tenant_evaluation_status",
    )
    # Backs QuestionRepository.list_for_proposal (the vendor's own Q&A view,
    # always scoped by its own proposal_id).
    db["qna_questions"].create_index(
        [("tenant_id", 1), ("proposal_id", 1)],
        name="idx_qna_questions_tenant_proposal",
    )
