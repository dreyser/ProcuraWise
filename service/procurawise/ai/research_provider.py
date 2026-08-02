from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Protocol

from procurawise.evaluations.models import Dimension

# ADR 0011: "internal_template"/"internal_evaluation" (InternalKnowledgeProvider)
# and "curated_source" (CuratedSourceProvider) are reachable from Fase 14.
# "web_search" (FoundryWebSearchProvider) is reachable in code but never
# actually produced unless Settings.foundry_web_search_enabled passes the
# fail-closed gate - which it does not in any Fase 14 environment.
ResearchSourceType = Literal[
    "internal_template", "internal_evaluation", "curated_source", "web_search"
]

# Fase 14: provider-neutral codes for a non-fatal `discover()` degradation.
# Never the raw provider exception text - `message` is a canned, reviewed
# string chosen by the caller, not `str(exc)` (founder decision, Fase 14
# planning: structured warnings must never leak raw provider error text).
ResearchWarningCode = Literal["research_provider_unavailable", "research_provider_timeout"]


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
    # Fase 14: only CuratedSourceProvider/FoundryWebSearchProvider populate
    # `url` - InternalKnowledgeProvider's sources are internal records with
    # no public URL. `retrieved_at` is set at query time by every provider,
    # regardless of source, since it records when *this* discover() call
    # observed the snippet, not when the underlying content was authored.
    url: str | None = None
    retrieved_at: datetime | None = None

    def to_document(self) -> dict[str, Any]:
        return {
            "source_type": self.source_type,
            "source_id": self.source_id,
            "title": self.title,
            "content": self.content,
            "url": self.url,
            "retrieved_at": self.retrieved_at,
        }

    @staticmethod
    def from_document(doc: dict[str, Any]) -> "ResearchSnippet":
        return ResearchSnippet(
            source_type=doc["source_type"],
            source_id=doc["source_id"],
            title=doc["title"],
            content=doc["content"],
            url=doc.get("url"),
            retrieved_at=doc.get("retrieved_at"),
        )


@dataclass(frozen=True)
class ResearchWarning:
    """A non-fatal degradation of one *secondary* research source (Curated or
    Foundry - never InternalKnowledgeProvider, which is the mandatory
    default and whose failure is still a hard job failure). Distinct from
    AIExecution.error, which stays reserved for jobs that fail outright."""

    code: ResearchWarningCode
    source_type: ResearchSourceType
    message: str

    def to_document(self) -> dict[str, Any]:
        return {"code": self.code, "source_type": self.source_type, "message": self.message}

    @staticmethod
    def from_document(doc: dict[str, Any]) -> "ResearchWarning":
        return ResearchWarning(
            code=doc["code"], source_type=doc["source_type"], message=doc["message"]
        )


@dataclass(frozen=True)
class DiscoveryResult:
    snippets: list[ResearchSnippet] = field(default_factory=list)
    warnings: list[ResearchWarning] = field(default_factory=list)


class ResearchProvider(Protocol):
    """Approved by ADR 0011. `InternalKnowledgeProvider` (Fase 13) is the
    mandatory default; `CuratedSourceProvider` and `FoundryWebSearchProvider`
    (Fase 14) are additional implementations composed by
    `ai.composite_research_provider.build_research_provider` - none of them
    is ever called directly by `AIService`, which only depends on this
    Protocol."""

    def discover(self, tenant_id: str, query: DiscoveryQuery) -> DiscoveryResult: ...
