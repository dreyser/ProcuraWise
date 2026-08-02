from datetime import UTC, datetime

from procurawise.ai.research_provider import DiscoveryQuery, DiscoveryResult, ResearchSnippet
from procurawise.ai.text_relevance import keywords, relevance
from procurawise.curated_sources.models import CuratedSource
from procurawise.curated_sources.repository import CuratedSourceRepository

# Kept smaller than InternalKnowledgeProvider.MAX_SNIPPETS - curated content
# is meant to supplement, not dominate, the rendered context.
MAX_SNIPPETS = 5


class CuratedSourceProvider:
    """Fase 14 (ADR 0011): reads the platform-level, admin-curated
    `curated_sources` collection - not tenant data. `tenant_id` is accepted
    only for `ResearchProvider` signature consistency and is otherwise
    unused (every tenant sees the same active curated sources). Never
    fetches `url` live - `summary` (manually authored/pasted by a
    platform_admin) is the only content ever fed into a prompt (founder
    decision, Fase 14 planning: no crawling of arbitrary URLs in Fase 14)."""

    def __init__(self, repository: CuratedSourceRepository) -> None:
        self._repository = repository

    def discover(self, tenant_id: str, query: DiscoveryQuery) -> DiscoveryResult:
        query_keywords = keywords(query.description)
        scored: list[tuple[int, ResearchSnippet]] = []
        now = datetime.now(UTC)

        for doc in self._repository.find_active():
            source = CuratedSource.from_document(doc)
            candidate_text = f"{source.title} {source.summary} {' '.join(source.tags)}"
            score = relevance(query_keywords, candidate_text)
            snippet = ResearchSnippet(
                source_type="curated_source",
                source_id=source.id,
                title=source.title,
                content=source.summary,
                url=source.url,
                retrieved_at=now,
            )
            scored.append((score, snippet))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        snippets = [snippet for _score, snippet in scored[:MAX_SNIPPETS]]
        return DiscoveryResult(snippets=snippets, warnings=[])
