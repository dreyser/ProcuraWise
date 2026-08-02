from datetime import UTC, datetime

import pytest

from procurawise.ai.composite_research_provider import CompositeResearchProvider
from procurawise.ai.research_provider import DiscoveryQuery, DiscoveryResult, ResearchSnippet


def _query() -> DiscoveryQuery:
    return DiscoveryQuery(dimension="functional", description="reporting")


def _snippet(source_type: str, source_id: str) -> ResearchSnippet:
    return ResearchSnippet(
        source_type=source_type,
        source_id=source_id,
        title="t",
        content="c",
        retrieved_at=datetime.now(UTC),
    )


class _FakeProvider:
    def __init__(
        self, result: DiscoveryResult | None = None, error: Exception | None = None
    ) -> None:
        self._result = result
        self._error = error

    def discover(self, tenant_id: str, query: DiscoveryQuery) -> DiscoveryResult:
        if self._error is not None:
            raise self._error
        assert self._result is not None
        return self._result


def test_concatenates_internal_and_secondary_snippets() -> None:
    internal = _FakeProvider(DiscoveryResult(snippets=[_snippet("internal_template", "a")]))
    curated = _FakeProvider(DiscoveryResult(snippets=[_snippet("curated_source", "b")]))
    composite = CompositeResearchProvider(internal, [("curated_source", curated)])

    result = composite.discover("tenant-1", _query())

    assert {s.source_id for s in result.snippets} == {"a", "b"}
    assert result.warnings == []


def test_internal_provider_failure_propagates_as_hard_failure() -> None:
    internal = _FakeProvider(error=RuntimeError("mongo down"))
    composite = CompositeResearchProvider(internal, [])

    with pytest.raises(RuntimeError, match="mongo down"):
        composite.discover("tenant-1", _query())


def test_secondary_provider_failure_degrades_to_warning_not_raised() -> None:
    internal = _FakeProvider(DiscoveryResult(snippets=[_snippet("internal_template", "a")]))
    broken_curated = _FakeProvider(error=RuntimeError("mongo timeout"))
    composite = CompositeResearchProvider(internal, [("curated_source", broken_curated)])

    result = composite.discover("tenant-1", _query())

    assert [s.source_id for s in result.snippets] == ["a"]
    assert len(result.warnings) == 1
    warning = result.warnings[0]
    assert warning.source_type == "curated_source"
    assert warning.code == "research_provider_unavailable"
    # Founder decision, Fase 14 planning: never raw exception text.
    assert "mongo timeout" not in warning.message


def test_secondary_provider_own_warnings_are_propagated() -> None:
    internal = _FakeProvider(DiscoveryResult(snippets=[]))
    from procurawise.ai.research_provider import ResearchWarning

    degraded_foundry = _FakeProvider(
        DiscoveryResult(
            snippets=[],
            warnings=[
                ResearchWarning(
                    code="research_provider_unavailable", source_type="web_search", message="x"
                )
            ],
        )
    )
    composite = CompositeResearchProvider(internal, [("web_search", degraded_foundry)])

    result = composite.discover("tenant-1", _query())

    assert len(result.warnings) == 1
    assert result.warnings[0].source_type == "web_search"


def test_multiple_secondary_providers_all_run_even_if_one_fails() -> None:
    internal = _FakeProvider(DiscoveryResult(snippets=[]))
    broken = _FakeProvider(error=RuntimeError("boom"))
    healthy = _FakeProvider(DiscoveryResult(snippets=[_snippet("web_search", "w1")]))
    composite = CompositeResearchProvider(
        internal, [("curated_source", broken), ("web_search", healthy)]
    )

    result = composite.discover("tenant-1", _query())

    assert [s.source_id for s in result.snippets] == ["w1"]
    assert len(result.warnings) == 1
