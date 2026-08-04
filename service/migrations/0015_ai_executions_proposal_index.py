from pymongo.database import Database


def apply(db: Database) -> None:
    # Fase 18 (ADR 0022): score-suggestion jobs are scoped to a proposal, not
    # just an evaluation - serves AIExecutionRepository.list_for_proposal
    # (history of suggestions for a given proposal). Additive: the Fase 13
    # (tenant_id, evaluation_id, created_at) index from migration 0009 is
    # unchanged and still serves requirement_generation lookups.
    db["ai_executions"].create_index(
        [("tenant_id", 1), ("proposal_id", 1), ("created_at", -1)],
        name="idx_ai_executions_tenant_proposal_created_at",
    )
