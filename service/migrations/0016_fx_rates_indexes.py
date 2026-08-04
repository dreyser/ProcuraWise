from pymongo.database import Database


def apply(db: Database) -> None:
    # Fase 19 (ADR 0008): fx_rates is platform-level content, not
    # tenant-scoped - no tenant_id in the index. The compound index backs
    # FXRateRepository.find_latest_for_pair()'s query (equality on both
    # currencies, sorted by effective_date desc); the admin list endpoint
    # sorts by the same field.
    db["fx_rates"].create_index(
        [("from_currency", 1), ("to_currency", 1), ("effective_date", -1)],
        name="idx_fx_rates_pair_effective_date",
    )
