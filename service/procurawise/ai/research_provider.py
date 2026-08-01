from dataclasses import dataclass
from typing import Literal, Protocol

from procurawise.evaluations.models import Dimension

# ADR 0011: only "internal_template"/"internal_evaluation" are reachable in
# Fase 13 - "curated_source"/"web_search" are named here so Fase 14's
# CuratedSourceProvider/FoundryWebSearchProvider slot into the same
# ResearchSnippet shape without a breaking change, but nothing produces them
# yet and no code path is gated on a flag for them (there is nothing to gate).
ResearchSourceType = Literal[
    "internal_template", "internal_evaluation", "curated_source", "web_search"
]


@dataclass(frozen=True)
class DiscoveryQuery:
    dimension: Dimension
    description: str
    exclude_evaluation_id: str | None = None


@dataclass(frozen=True)
class ResearchSnippet:
    source_type: ResearchSourceType
    source_id: str
    title: str
    content: str


class ResearchProvider(Protocol):
    """Approved by ADR 0011, implemented for the first time in Fase 13.
    `InternalKnowledgeProvider` is the only active implementation this
    phase - `CuratedSourceProvider`/`FoundryWebSearchProvider` (Fase 14) are
    legal-gated and out of scope here."""

    def discover(self, tenant_id: str, query: DiscoveryQuery) -> list[ResearchSnippet]: ...
