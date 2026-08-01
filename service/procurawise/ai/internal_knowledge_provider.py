import re

from procurawise.ai.research_provider import (
    DiscoveryQuery,
    ResearchSnippet,
    ResearchSourceType,
)
from procurawise.evaluations.models import Requirement
from procurawise.evaluations.repository import EvaluationRepository
from procurawise.knowledge_templates.models import KnowledgeTemplate
from procurawise.knowledge_templates.repository import KnowledgeTemplateRepository

# Small, fixed cap so the rendered prompt stays bounded regardless of how
# large a tenant's library grows - ADR 0021 keeps this phase's grounding
# source internal-only, but "internal" can still be large.
MAX_SNIPPETS = 8

_WORD_RE = re.compile(r"[a-záéíóúñ0-9]+", re.IGNORECASE)


def _keywords(text: str) -> set[str]:
    return {word for word in _WORD_RE.findall(text.lower()) if len(word) > 2}


def _relevance(query_keywords: set[str], candidate_text: str) -> int:
    return len(query_keywords & _keywords(candidate_text))


class InternalKnowledgeProvider:
    """The only active `ResearchProvider` implementation in Fase 13 (ADR
    0011/0021). Queries only the calling tenant's own `KnowledgeTemplate`
    items and prior `Evaluation.requirements` - no external network, no
    cross-tenant read, matching `InternalKnowledgeProvider`'s "sin red
    externa" requirement from the backlog acceptance criterion."""

    def __init__(
        self,
        templates: KnowledgeTemplateRepository,
        evaluations: EvaluationRepository,
    ) -> None:
        self._templates = templates
        self._evaluations = evaluations

    def discover(self, tenant_id: str, query: DiscoveryQuery) -> list[ResearchSnippet]:
        query_keywords = _keywords(query.description)
        scored: list[tuple[int, ResearchSnippet]] = []

        for template_doc in self._templates.find_many(tenant_id):
            template = KnowledgeTemplate.from_document(template_doc)
            for item in template.items:
                if item.dimension != query.dimension:
                    continue
                snippet = _snippet_from_requirement(
                    source_type="internal_template",
                    source_id=template.id,
                    title=f"{template.name}: {item.title}",
                    item=item,
                )
                candidate_text = f"{item.title} {item.category} {item.description}"
                score = _relevance(query_keywords, candidate_text)
                scored.append((score, snippet))

        for evaluation_doc in self._evaluations.find_many(tenant_id):
            if evaluation_doc["_id"] == query.exclude_evaluation_id:
                continue
            for item_doc in evaluation_doc.get("requirements", []):
                item = Requirement.from_document(item_doc)
                if item.dimension != query.dimension:
                    continue
                snippet = _snippet_from_requirement(
                    source_type="internal_evaluation",
                    source_id=evaluation_doc["_id"],
                    title=item.title,
                    item=item,
                )
                candidate_text = f"{item.title} {item.category} {item.description}"
                score = _relevance(query_keywords, candidate_text)
                scored.append((score, snippet))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [snippet for _score, snippet in scored[:MAX_SNIPPETS]]


def _snippet_from_requirement(
    *, source_type: ResearchSourceType, source_id: str, title: str, item: Requirement
) -> ResearchSnippet:
    return ResearchSnippet(
        source_type=source_type,
        source_id=source_id,
        title=title,
        content=f"[{item.category}] {item.description}",
    )
