from pymongo.database import Database


def apply(db: Database) -> None:
    # Fase 20 (ADR 0009): one EconomicAssessment per (tenant_id,
    # evaluation_id, proposal_id) - unique index enforces that grain and
    # backs ScoringService.upsert_economic_assessment's lookup.
    db["economic_assessments"].create_index(
        [("tenant_id", 1), ("evaluation_id", 1), ("proposal_id", 1)],
        name="idx_economic_assessments_tenant_evaluation_proposal",
        unique=True,
    )
