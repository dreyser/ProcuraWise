from pymongo.database import Database


def apply(db: Database) -> None:
    # Fase 15: (tenant_id, user_id, type, accepted_at desc) backs
    # AgreementRepository.find_latest's exact query+sort shape - not unique,
    # a user may hold several historical acceptances of different versions
    # of the same type over time (no grandfathering, ADR 0014 D4: only the
    # most recent one, compared against the current code-constant version,
    # ever counts as "accepted").
    db["agreements"].create_index(
        [("tenant_id", 1), ("user_id", 1), ("type", 1), ("accepted_at", -1)],
        name="idx_agreements_tenant_user_type_accepted_at",
    )
