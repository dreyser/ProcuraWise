import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import httpx

from procurawise.ai.research_provider import (
    DiscoveryQuery,
    DiscoveryResult,
    ResearchSnippet,
    ResearchWarning,
)
from procurawise.shared.config import Settings

logger = logging.getLogger("procurawise.ai.foundry_web_search")

# Same bounded-retry discipline as AzureOpenAIProvider - two attempts total,
# never the SDK/library's own open-ended default backoff.
_MAX_ATTEMPTS = 2
_RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})

TokenProvider = Callable[[], str]


def _default_token_provider() -> TokenProvider:
    """Entra ID Bearer token acquisition for the Foundry Responses API - per
    the Fase 14 research spike, this endpoint authenticates with Entra ID
    Bearer tokens, not a static API key (unlike Azure OpenAI's
    azure_openai_api_key). Imported lazily so `azure-identity` is only
    touched when Foundry is actually being constructed - this module must
    stay importable (and its `discover()` gracefully degradable) even when
    Foundry is disabled, which is every Fase 14 environment."""
    from azure.identity import DefaultAzureCredential

    credential = DefaultAzureCredential()

    def provide() -> str:
        return credential.get_token("https://ai.azure.com/.default").token

    return provide


def _parse_citations(
    response_json: dict[str, Any], *, retrieved_at: datetime
) -> list[ResearchSnippet]:
    """Foundry Responses API shape, per the Fase 14 research spike (Microsoft
    Learn, 2026-08): `output_items[].content[].annotations[]` entries of
    type "url_citation" carry `url`/`start_index`/`end_index` (and,
    depending on the calling pattern, `title`). Re-verify this shape against
    the live official OpenAPI reference before activation - Microsoft's own
    guidance is to treat this output as untrusted input, which is exactly
    why every field is defensively extracted with fallbacks rather than
    assumed present."""
    snippets: list[ResearchSnippet] = []
    for item in response_json.get("output_items", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            text = content.get("text", "") or ""
            for annotation in content.get("annotations", []):
                if annotation.get("type") != "url_citation":
                    continue
                url = annotation.get("url")
                if not url:
                    continue
                start, end = annotation.get("start_index"), annotation.get("end_index")
                excerpt = (
                    text[start:end]
                    if isinstance(start, int)
                    and isinstance(end, int)
                    and 0 <= start < end <= len(text)
                    else text
                )
                snippets.append(
                    ResearchSnippet(
                        source_type="web_search",
                        source_id=url,
                        title=annotation.get("title") or url,
                        content=excerpt or text,
                        url=url,
                        retrieved_at=retrieved_at,
                    )
                )
    return snippets


class FoundryWebSearchProviderUnavailableError(Exception):
    """A `discover()` call failed outright (auth, network, or a
    non-retryable/exhausted-retry HTTP error). Never propagated past
    `discover()` itself - caught there and turned into a ResearchWarning."""


class FoundryWebSearchProvider:
    """Fase 14 (ADR 0011): calls the Foundry Agent Service's Responses API
    `web_search` tool via direct authenticated REST - no
    `azure-ai-projects`/`azure-ai-agents` SDK (founder decision, Fase 14
    planning: prefer direct REST unless an official SDK proves technically
    necessary; it did not here). Provisioning the underlying Foundry
    agent/Bing connection is a one-time infra/ops step (see
    docs/operations/deployment.md), not something this adapter does at
    runtime - it only POSTs to an already-provisioned agent, by name.

    This class is constructed and fully testable regardless of the feature
    flag, but is only ever instantiated by
    `composite_research_provider.build_research_provider`, which does so
    exclusively after `Settings`' fail-closed Foundry validator has already
    required `foundry_web_search_enabled=true` AND a documented
    legal-approval reference AND endpoint/agent_name - this class itself has
    no opinion on the flag, so there is exactly one place in the codebase
    that can ever cause a live call to happen."""

    def __init__(
        self,
        *,
        endpoint: str,
        agent_name: str,
        api_version: str,
        timeout_seconds: int,
        token_provider: TokenProvider,
    ) -> None:
        self._endpoint = endpoint.rstrip("/")
        self._agent_name = agent_name
        self._api_version = api_version
        self._timeout_seconds = timeout_seconds
        self._token_provider = token_provider
        self._client = httpx.Client(timeout=timeout_seconds)

    @classmethod
    def from_settings(cls, settings: Settings) -> "FoundryWebSearchProvider":
        if not (
            settings.foundry_web_search_enabled
            and settings.foundry_web_search_endpoint
            and settings.foundry_web_search_agent_name
            and settings.foundry_legal_approval_reference
        ):
            raise ValueError(
                "foundry_web_search_enabled, foundry_web_search_endpoint, "
                "foundry_web_search_agent_name and foundry_legal_approval_reference must all be "
                "set to construct FoundryWebSearchProvider"
            )
        return cls(
            endpoint=settings.foundry_web_search_endpoint,
            agent_name=settings.foundry_web_search_agent_name,
            api_version=settings.foundry_web_search_api_version,
            timeout_seconds=settings.foundry_web_search_timeout_seconds,
            token_provider=_default_token_provider(),
        )

    def discover(self, tenant_id: str, query: DiscoveryQuery) -> DiscoveryResult:
        """Never raises: Microsoft's own guidance is to treat web search
        results as untrusted input, and ADR 0011's fallback rule requires
        degrading to Internal+Curated rather than failing the whole job when
        this secondary source is unavailable - any failure here becomes an
        empty result plus a structured, provider-neutral ResearchWarning
        (never raw exception text), handled by
        composite_research_provider."""
        try:
            snippets = self._call(query)
        except Exception:  # noqa: BLE001 - degrade, never propagate raw
            logger.warning("foundry_web_search_unavailable", exc_info=True)
            return DiscoveryResult(
                snippets=[],
                warnings=[
                    ResearchWarning(
                        code="research_provider_unavailable",
                        source_type="web_search",
                        message=(
                            "La búsqueda web no estuvo disponible para esta consulta; se "
                            "usaron únicamente fuentes internas y curadas."
                        ),
                    )
                ],
            )
        return DiscoveryResult(snippets=snippets, warnings=[])

    def _call(self, query: DiscoveryQuery) -> list[ResearchSnippet]:
        # Sanitization discipline mirrors ADR 0011/0021: only the abstract,
        # already-sanitized DiscoveryQuery.description crosses this boundary
        # as the model input - never PII, tenant name, or vendor identity
        # (DiscoveryQuery never carries any of that to begin with).
        token = self._token_provider()
        response = self._post_with_retry(
            url=f"{self._endpoint}/openai/v1/responses",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json_body={
                "input": query.description,
                "tool_choice": "required",
                "extra_body": {
                    "agent_reference": {"name": self._agent_name, "type": "agent_reference"}
                },
            },
        )
        return _parse_citations(response.json(), retrieved_at=datetime.now(UTC))

    def _post_with_retry(
        self, *, url: str, headers: dict[str, str], json_body: dict[str, Any]
    ) -> httpx.Response:
        last_error: Exception | None = None
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                response = self._client.post(url, headers=headers, json=json_body)
            except httpx.HTTPError as exc:
                last_error = exc
            else:
                if response.status_code not in _RETRYABLE_STATUS_CODES:
                    response.raise_for_status()
                    return response
                last_error = FoundryWebSearchProviderUnavailableError(
                    f"retryable status {response.status_code}"
                )
            if attempt < _MAX_ATTEMPTS:
                logger.warning("foundry_web_search_retrying", extra={"attempt": attempt})
                time.sleep(2**attempt)
        assert last_error is not None
        raise last_error
