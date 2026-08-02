import logging

from pymongo.database import Database

from procurawise.ai.curated_source_provider import CuratedSourceProvider
from procurawise.ai.foundry_web_search_provider import FoundryWebSearchProvider
from procurawise.ai.internal_knowledge_provider import InternalKnowledgeProvider
from procurawise.ai.research_provider import (
    DiscoveryQuery,
    DiscoveryResult,
    ResearchProvider,
    ResearchSourceType,
    ResearchWarning,
)
from procurawise.curated_sources.repository import CuratedSourceRepository
from procurawise.evaluations.repository import EvaluationRepository
from procurawise.knowledge_templates.repository import KnowledgeTemplateRepository
from procurawise.shared.config import Settings

logger = logging.getLogger("procurawise.ai.composite_research_provider")


class CompositeResearchProvider:
    """Fase 14 (ADR 0011): the single `ResearchProvider` `AIService` is ever
    given. `internal` is the mandatory P0 default (InternalKnowledgeProvider)
    - its failure is still a hard job failure, exactly like Fase 13, so it
    is called outside the try/except below. Each entry in `secondary` is a
    (source_type, provider) pair; every secondary provider's own
    `discover()` already never raises (see CuratedSourceProvider/
    FoundryWebSearchProvider docstrings), but this class still wraps the
    call defensively so one misbehaving/future provider can never turn into
    a whole-job failure - degradation always produces a structured,
    provider-neutral `ResearchWarning` naming which `source_type` degraded,
    never raw exception text (founder decision, Fase 14 planning)."""

    def __init__(
        self,
        internal: ResearchProvider,
        secondary: list[tuple[ResearchSourceType, ResearchProvider]],
    ) -> None:
        self._internal = internal
        self._secondary = secondary

    def discover(self, tenant_id: str, query: DiscoveryQuery) -> DiscoveryResult:
        internal_result = self._internal.discover(tenant_id, query)
        snippets = list(internal_result.snippets)
        warnings = list(internal_result.warnings)

        for source_type, provider in self._secondary:
            try:
                result = provider.discover(tenant_id, query)
            except Exception:  # noqa: BLE001 - a secondary source degrades, it never fails the job
                logger.warning(
                    "research_provider_degraded",
                    extra={"source_type": source_type, "provider": type(provider).__name__},
                    exc_info=True,
                )
                warnings.append(
                    ResearchWarning(
                        code="research_provider_unavailable",
                        source_type=source_type,
                        message="Una fuente de investigación secundaria no estuvo disponible "
                        "para esta consulta.",
                    )
                )
                continue
            snippets.extend(result.snippets)
            warnings.extend(result.warnings)

        return DiscoveryResult(snippets=snippets, warnings=warnings)


def build_research_provider(settings: Settings, db: Database) -> ResearchProvider:
    """Single wiring point (mirrors `ai.service.build_ai_service`'s "single
    wiring point" discipline) - `InternalKnowledgeProvider` is always
    present; `CuratedSourceProvider` is always additive;
    `FoundryWebSearchProvider` is constructed only when
    `settings.foundry_web_search_enabled` is true, which - by the time this
    function runs - Settings' own `_require_foundry_preconditions_when_enabled`
    validator has already guaranteed cannot be true without a documented
    legal-approval reference, endpoint, and agent name. This is the only
    place in the codebase that can cause a live Foundry call to happen."""
    internal = InternalKnowledgeProvider(KnowledgeTemplateRepository(db), EvaluationRepository(db))
    secondary: list[tuple[ResearchSourceType, ResearchProvider]] = [
        ("curated_source", CuratedSourceProvider(CuratedSourceRepository(db)))
    ]
    if settings.foundry_web_search_enabled:
        secondary.append(("web_search", FoundryWebSearchProvider.from_settings(settings)))
    return CompositeResearchProvider(internal, secondary)
