from unittest.mock import MagicMock

import pytest

from procurawise.ai.foundry_web_search_provider import FoundryWebSearchProvider
from procurawise.ai.research_provider import DiscoveryQuery
from procurawise.shared.config import Settings


def _provider(token_provider=lambda: "fake-token") -> FoundryWebSearchProvider:  # noqa: ANN001
    return FoundryWebSearchProvider(
        endpoint="https://example.services.ai.azure.com/api/projects/p",
        agent_name="test-agent",
        api_version="v1",
        timeout_seconds=5,
        token_provider=token_provider,
    )


def _query() -> DiscoveryQuery:
    return DiscoveryQuery(dimension="functional", description="reporting dashboards")


def _fake_http_response(status_code: int, json_body: dict) -> MagicMock:  # noqa: ANN001
    response = MagicMock(status_code=status_code)
    response.json.return_value = json_body
    if status_code >= 400:
        response.raise_for_status.side_effect = Exception(f"HTTP {status_code}")
    else:
        response.raise_for_status.return_value = None
    return response


_VALID_RESPONSE_BODY = {
    "output_items": [
        {
            "type": "message",
            "content": [
                {
                    "text": "Contoso lidera el mercado con nuevas funciones.",
                    "annotations": [
                        {
                            "type": "url_citation",
                            "url": "https://contoso.com/blog",
                            "title": "Contoso Blog",
                            "start_index": 0,
                            "end_index": 8,
                        }
                    ],
                }
            ],
        }
    ]
}


def test_from_settings_requires_full_foundry_config() -> None:
    settings = Settings(_env_file=None)
    with pytest.raises(ValueError, match="foundry_web_search_enabled"):
        FoundryWebSearchProvider.from_settings(settings)


def test_from_settings_builds_provider_when_fully_configured() -> None:
    settings = Settings(
        _env_file=None,
        foundry_web_search_enabled=True,
        foundry_legal_approval_reference="LEGAL-2026-001",
        foundry_web_search_endpoint="https://example.services.ai.azure.com/api/projects/p",
        foundry_web_search_agent_name="agent",
    )
    provider = FoundryWebSearchProvider.from_settings(settings)
    assert provider is not None


def test_discover_parses_url_citations_into_snippets() -> None:
    provider = _provider()
    provider._client.post = MagicMock(  # type: ignore[method-assign]
        return_value=_fake_http_response(200, _VALID_RESPONSE_BODY)
    )

    result = provider.discover("tenant-1", _query())

    assert result.warnings == []
    assert len(result.snippets) == 1
    snippet = result.snippets[0]
    assert snippet.source_type == "web_search"
    assert snippet.url == "https://contoso.com/blog"
    assert snippet.title == "Contoso Blog"
    assert snippet.content == "Contoso "
    assert snippet.retrieved_at is not None


def test_discover_ignores_non_citation_annotations() -> None:
    provider = _provider()
    body = {
        "output_items": [
            {"type": "message", "content": [{"text": "hola", "annotations": [{"type": "other"}]}]}
        ]
    }
    provider._client.post = MagicMock(return_value=_fake_http_response(200, body))  # type: ignore[method-assign]

    result = provider.discover("tenant-1", _query())

    assert result.snippets == []
    assert result.warnings == []


def test_discover_degrades_to_warning_when_token_provider_fails() -> None:
    def _raise() -> str:
        raise RuntimeError("no credential available")

    provider = _provider(token_provider=_raise)

    result = provider.discover("tenant-1", _query())

    assert result.snippets == []
    assert len(result.warnings) == 1
    warning = result.warnings[0]
    assert warning.code == "research_provider_unavailable"
    assert warning.source_type == "web_search"
    # Founder decision, Fase 14 planning: never raw exception text in a
    # structured warning.
    assert "no credential available" not in warning.message


def test_discover_degrades_to_warning_after_exhausting_retries(monkeypatch) -> None:
    monkeypatch.setattr(
        "procurawise.ai.foundry_web_search_provider.time.sleep", lambda _seconds: None
    )
    provider = _provider()
    provider._client.post = MagicMock(  # type: ignore[method-assign]
        return_value=_fake_http_response(503, {})
    )

    result = provider.discover("tenant-1", _query())

    assert result.snippets == []
    assert len(result.warnings) == 1
    assert provider._client.post.call_count == 2


def test_discover_retries_once_on_retryable_status_then_succeeds(monkeypatch) -> None:
    monkeypatch.setattr(
        "procurawise.ai.foundry_web_search_provider.time.sleep", lambda _seconds: None
    )
    provider = _provider()
    provider._client.post = MagicMock(  # type: ignore[method-assign]
        side_effect=[
            _fake_http_response(429, {}),
            _fake_http_response(200, _VALID_RESPONSE_BODY),
        ]
    )

    result = provider.discover("tenant-1", _query())

    assert result.warnings == []
    assert len(result.snippets) == 1
    assert provider._client.post.call_count == 2


def test_discover_sends_bearer_token_and_agent_reference() -> None:
    provider = _provider(token_provider=lambda: "the-token")
    provider._client.post = MagicMock(  # type: ignore[method-assign]
        return_value=_fake_http_response(200, {"output_items": []})
    )

    provider.discover("tenant-1", _query())

    _args, kwargs = provider._client.post.call_args
    assert kwargs["headers"]["Authorization"] == "Bearer the-token"
    assert kwargs["json"]["extra_body"]["agent_reference"]["name"] == "test-agent"
    # Sanitization discipline (ADR 0011/0021): only the abstract query
    # description crosses this boundary, never tenant_id/PII.
    assert kwargs["json"]["input"] == "reporting dashboards"
    assert "tenant-1" not in str(kwargs["json"])
