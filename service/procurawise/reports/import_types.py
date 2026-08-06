from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RequirementImportPreview:
    """Fase 23 - stateless preview (plan section 10, decision 9): nothing
    here is persisted. The client keeps `rows`/`suggested_mapping`, lets the
    user adjust the mapping locally, and sends the already-resolved
    Requirement values back on confirm - the server never re-derives a
    mapping from a stored session."""

    columns: list[str]
    rows: list[dict[str, Any]]
    suggested_mapping: dict[str, str]
