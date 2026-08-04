from typing import Any

from pymongo.database import Database


class FXRateRepository:
    """Fase 19 (ADR 0008): platform-level, admin-managed exchange rates -
    deliberately NOT wrapped in `TenantCollection`, same reasoning as
    `curated_sources.repository.CuratedSourceRepository` - `FXRate` has no
    `tenant_id` at all, every tenant resolves the same rows. Create-only
    (plan §9 R4): no update/delete method exists here on purpose."""

    def __init__(self, db: Database) -> None:
        self._collection = db["fx_rates"]

    def insert(self, document: dict[str, Any]) -> None:
        self._collection.insert_one(document)

    def find_all(self) -> list[dict[str, Any]]:
        return list(self._collection.find({}).sort([("effective_date", -1)]))

    def find_latest_for_pair(
        self, from_currency: str, to_currency: str, as_of_date: str
    ) -> dict[str, Any] | None:
        """Most recent rate for (from_currency, to_currency) whose
        effective_date is on or before as_of_date (ISO string, same
        lexicographic-sortable format as effective_date is stored in) - the
        resolution rule for "the rate vigente at submit time" (plan
        §6.C38-39)."""
        return self._collection.find_one(
            {
                "from_currency": from_currency,
                "to_currency": to_currency,
                "effective_date": {"$lte": as_of_date},
            },
            sort=[("effective_date", -1)],
        )
