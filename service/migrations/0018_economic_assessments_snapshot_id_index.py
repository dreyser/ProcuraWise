from pymongo.database import Database
from pymongo.errors import OperationFailure


def apply(db: Database) -> None:
    # Fase 21 (ADR 0013): EconomicAssessment's grain widens from (tenant_id,
    # evaluation_id, proposal_id) to include snapshot_id - a negotiation
    # round always starts with a fresh, unscored assessment (no
    # herencia/fallback across rounds, see
    # scoring.repository.EconomicAssessmentRepository's docstring). The
    # Fase 20 index would otherwise still reject a second round's first
    # write as a duplicate of Ronda 0's assessment for the same proposal.
    try:
        db["economic_assessments"].drop_index("idx_economic_assessments_tenant_evaluation_proposal")
    except OperationFailure:
        # Index never existed (fresh database) - nothing to drop.
        pass
    db["economic_assessments"].create_index(
        [("tenant_id", 1), ("evaluation_id", 1), ("proposal_id", 1), ("snapshot_id", 1)],
        name="idx_economic_assessments_tenant_evaluation_proposal_snapshot",
        unique=True,
    )
