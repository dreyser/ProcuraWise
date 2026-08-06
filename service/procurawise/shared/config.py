from typing import Literal, Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Obviously-insecure placeholder, never a real secret - safe as a default so
# every existing `Settings(_env_file=None, ...)` call across the test suite
# keeps working without passing a jwt_secret explicitly. The production
# validator below rejects this exact value (and anything under 32 chars).
_INSECURE_DEV_JWT_SECRET = "dev-insecure-jwt-secret-do-not-use-in-production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", populate_by_name=True
    )

    environment: Literal["local", "test", "production"] = "local"
    log_level: str = "info"

    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_db_name: str = "procurawise_local"
    mongodb_server_selection_timeout_ms: int = 2000

    # "UseDevelopmentStorage=true" is Azurite's documented public shortcut connection
    # string, not a credential - safe to ship as a default / commit in .env.example.
    storage_connection_string: str = "UseDevelopmentStorage=true"
    storage_container_name: str = "procurawise-local"
    storage_timeout_seconds: int = 2

    # Pinned, not left on the SDK's default: azure-storage-blob 12.30.0 defaults to
    # REST version 2026-06-06, which Azurite 3.33.0 rejects with InvalidHeaderValue.
    # 2025-01-05 is confirmed supported by both Azurite 3.33.0 and real Azure Storage.
    # Do not remove this pin just because the SDK ships a newer default - bumping it
    # requires re-verifying compatibility against both Azurite and real Azure Storage
    # first. `--skipApiVersionCheck` on Azurite is not an accepted alternative.
    storage_api_version: str = Field(
        default="2025-01-05", validation_alias="AZURE_STORAGE_API_VERSION"
    )

    queue_backend: Literal["memory", "service_bus"] = "memory"
    service_bus_connection_string: str | None = None

    # AUTH-PROD: JWT propio (ADR 0003). Ver _INSECURE_DEV_JWT_SECRET arriba -
    # el default solo es válido fuera de production, el validador de abajo lo
    # exige.
    jwt_secret: str = _INSECURE_DEV_JWT_SECRET
    jwt_algorithm: Literal["HS256"] = "HS256"
    access_token_ttl_minutes: int = 30
    pre_session_token_ttl_minutes: int = 5

    # OIDC Microsoft/Google (authlib, ADR 0003). None por defecto: solo
    # comprador usa este flujo, y no bloquea development/test sin credenciales
    # reales configuradas - el validador de abajo sí las exige en production.
    oidc_microsoft_client_id: str | None = None
    oidc_microsoft_client_secret: str | None = None
    oidc_microsoft_tenant: str = "common"
    oidc_google_client_id: str | None = None
    oidc_google_client_secret: str | None = None
    # Dónde vive este mismo backend (para construir redirect_uri hacia el IdP)
    # y dónde vive el SPA (para el redirect final tras el callback OIDC).
    oidc_redirect_base_url: str = "http://localhost:8000"
    frontend_base_url: str = "http://localhost:5173"

    # Fase 8 (audit): retention window for AuditEvent, backing the `expires_at`
    # TTL index (audit.repository) - one centralized value, consistent with
    # ADR 0016's 1-year default, not configurable per tenant in this phase
    # (founder decision §18.3 of the approved plan).
    audit_event_retention_days: int = 365

    # Fase 13 (ai, ADR 0021): Azure OpenAI is the first AIProvider
    # implementation. None by default so local/test never accidentally calls
    # a real endpoint without explicit config - the production validator
    # below requires all four when environment=production.
    azure_openai_endpoint: str | None = None
    azure_openai_api_key: str | None = None
    azure_openai_deployment: str | None = None
    # Pinned, not left on the SDK default - same rationale as
    # storage_api_version above: an unpinned default can change under us
    # between SDK releases without a deliberate compatibility check.
    azure_openai_api_version: str = "2026-01-01-preview"
    ai_request_timeout_seconds: int = 30
    # Same 1-year default as audit_event_retention_days (ADR 0016) but a
    # separate field - AIExecution is its own collection with its own
    # lifecycle, not an AuditEvent, even though the retention policy happens
    # to match today.
    ai_execution_retention_days: int = 365
    # Deliberately None by default rather than a hardcoded price table -
    # Azure OpenAI pricing varies by region/negotiated agreement and changes
    # over time; AIExecution.cost_estimate stays null (never a guessed
    # number) until the founder configures the tenant's actual per-1k-token
    # price here. Observability only (ADR 0021 founder decision) - never
    # used to enforce a limit.
    ai_prompt_price_per_1k_tokens_usd: float | None = None
    ai_completion_price_per_1k_tokens_usd: float | None = None
    # Fase 18 (evaluacion asistida por IA, ADR 0022): a plain boolean, not a
    # fail-closed gate like foundry_web_search_enabled below - the founder
    # confirmed (Fase 18 planning) that Azure OpenAI chat completions stay
    # within the same Data Protection Addendum already covering the rest of
    # the platform since Fase 13, so this doesn't need a legal-approval-
    # reference precondition the way Bing Grounding does.
    ai_score_suggestion_enabled: bool = True

    # Fase 14 (ResearchProvider completo, ADR 0011): FoundryWebSearchProvider
    # is built but stays off in every environment, including production -
    # unlike azure_openai_* above (required only in production),
    # foundry_web_search_enabled defaults False everywhere and the validator
    # below runs regardless of `environment`. Auth to the Foundry Responses
    # API is Entra ID Bearer tokens (azure-identity's DefaultAzureCredential),
    # not a static API key - there is deliberately no
    # foundry_web_search_api_key field; the credential is resolved from the
    # process's standard Azure identity (managed identity in Azure, service
    # principal env vars locally), the same way any other Azure SDK client
    # would, and FoundryWebSearchProvider accepts it as an injectable
    # dependency for deterministic tests.
    foundry_web_search_enabled: bool = False
    # Foundry project endpoint, e.g. "https://<account>.services.ai.azure.com/api/projects/<project>".
    foundry_web_search_endpoint: str | None = None
    # Name of the pre-provisioned Foundry agent (with the web_search tool
    # already attached) that FoundryWebSearchProvider calls via
    # `extra_body.agent_reference`. Provisioning the agent/Bing connection is
    # a one-time infra/ops step (documented in deployment.md), not something
    # this adapter does at runtime.
    foundry_web_search_agent_name: str | None = None
    # Pinned to the path segment Microsoft's docs use for the Responses API
    # (`/openai/v1/responses`) as of the Block 1 research spike (2026-08) -
    # re-verify against the official OpenAPI reference before bumping.
    foundry_web_search_api_version: str = "v1"
    foundry_web_search_timeout_seconds: int = 20
    # Founder-directed (Phase 14 planning): activation must never depend on
    # the boolean flag alone (backlog.md: "no solo config") - a human-entered
    # identifier for the documented legal-approval record (ADR 0011). This
    # field existing and being non-empty is not itself legal approval; it is
    # the required, auditable pointer to where that approval lives.
    foundry_legal_approval_reference: str | None = None

    # Fase 15 (NDA/COI reales + auth productiva de proveedor): how long a
    # vendor invitation link stays redeemable. Single-use regardless (the
    # atomic pending->accepted transition in
    # identity.repository.VendorInvitationRepository.try_accept makes a
    # second redemption of the same token impossible even before it
    # expires) - this only bounds how long an *unredeemed* link works.
    vendor_invitation_ttl_days: int = 7

    # Fase 15 (Agreement.ip capture, R3 of the planning session): Azure
    # Container Apps sits in front of the API as a single reverse-proxy hop
    # once real infra exists (Fase 27, not provisioned yet) - `X-Forwarded-
    # For` is only trusted up to this many hops from the end of the header's
    # comma-separated chain, and only when > 0. Default 0 means "trust
    # nothing, always use the direct connection's IP" - correct for
    # local/test/CI, where there is no real reverse proxy in front of
    # uvicorn. Re-verify this value against Azure Container Apps' actual
    # proxy behavior when infra is provisioned in Fase 27, before relying on
    # it in production.
    trusted_proxy_hops: int = 0

    # Fase 16 (documents): a dedicated container, separate from
    # storage_container_name (generic, health-check-only today) - least-
    # privilege SAS scoping (a documents-scoped SAS token can never reach
    # unrelated blobs some future feature might store in the generic
    # container) and a clean namespace as the app's first real Blob
    # consumer beyond the health probe.
    documents_container_name: str = "procurawise-documents"
    # No size limit is specified anywhere in the approved spec - 25 MB
    # comfortably covers typical RFP evidence (PDF/Office/images) while
    # staying well under any practical Azure Container Apps ingress limit.
    # Deliberately a plain Settings field, not a business constant, so it
    # can be tuned without a code change.
    documents_max_file_size_mb: int = 25
    # How long a download URL (Service SAS, shared/storage.py::
    # AzureBlobStorage.generate_download_url) stays valid. Short by design -
    # the caller re-authorizes and gets a fresh URL on every request, this
    # only bounds how long a given URL keeps working if intercepted/shared.
    documents_download_url_ttl_minutes: int = 15

    # Fase 23 (reports, ADR 0023): a dedicated container, same
    # least-privilege-SAS-scoping rationale as documents_container_name -
    # never mixed with vendor-uploaded evidence's own retention/lifecycle.
    reports_container_name: str = "procurawise-reports"
    reports_download_url_ttl_minutes: int = 15
    # Same 1-year default as audit_event_retention_days/ai_execution_
    # retention_days (ADR 0016) - Report is its own collection with its own
    # lifecycle, not an AuditEvent/AIExecution, even though the policy
    # happens to match today.
    reports_retention_days: int = 365
    # Fase 23 (requirements import): same rationale/order-of-magnitude as
    # documents_max_file_size_mb - a spreadsheet of requirements is
    # intrinsically small (bounded by what a human can review in a preview
    # step before confirming).
    import_max_file_size_mb: int = 10

    @model_validator(mode="after")
    def _reject_memory_queue_in_production(self) -> Self:
        if self.environment == "production" and self.queue_backend == "memory":
            raise ValueError("queue_backend=memory no está permitido cuando environment=production")
        return self

    @model_validator(mode="after")
    def _require_real_auth_config_in_production(self) -> Self:
        if self.environment != "production":
            return self
        if self.jwt_secret == _INSECURE_DEV_JWT_SECRET or len(self.jwt_secret) < 32:
            raise ValueError(
                "jwt_secret debe configurarse explícitamente (>=32 caracteres, "
                "distinto del default de desarrollo) cuando environment=production"
            )
        missing = [
            name
            for name, value in (
                ("oidc_microsoft_client_id", self.oidc_microsoft_client_id),
                ("oidc_microsoft_client_secret", self.oidc_microsoft_client_secret),
                ("oidc_google_client_id", self.oidc_google_client_id),
                ("oidc_google_client_secret", self.oidc_google_client_secret),
            )
            if not value
        ]
        if missing:
            raise ValueError(
                f"faltan credenciales oidc requeridas cuando environment=production: "
                f"{', '.join(missing)}"
            )
        return self

    @model_validator(mode="after")
    def _require_real_ai_config_in_production(self) -> Self:
        if self.environment != "production":
            return self
        missing = [
            name
            for name, value in (
                ("azure_openai_endpoint", self.azure_openai_endpoint),
                ("azure_openai_api_key", self.azure_openai_api_key),
                ("azure_openai_deployment", self.azure_openai_deployment),
            )
            if not value
        ]
        if missing:
            raise ValueError(
                f"faltan credenciales de Azure OpenAI requeridas cuando environment=production: "
                f"{', '.join(missing)}"
            )
        return self

    @model_validator(mode="after")
    def _require_foundry_preconditions_when_enabled(self) -> Self:
        """Fase 14 (ADR 0011): fail closed in *every* environment, not only
        production - `foundry_web_search_enabled=true` alone must never be
        sufficient to activate live web search. Runs unconditionally
        (contrast `_require_real_ai_config_in_production`, which only checks
        when environment=="production") because there is no environment
        where an incomplete Foundry config should silently no-op instead of
        refusing to start."""
        if not self.foundry_web_search_enabled:
            return self
        missing = [
            name
            for name, value in (
                ("foundry_legal_approval_reference", self.foundry_legal_approval_reference),
                ("foundry_web_search_endpoint", self.foundry_web_search_endpoint),
                ("foundry_web_search_agent_name", self.foundry_web_search_agent_name),
            )
            if not value
        ]
        if missing:
            raise ValueError(
                "foundry_web_search_enabled=true requiere también: "
                f"{', '.join(missing)} (ADR 0011: la activación nunca depende solo del flag "
                "booleano; ver también CLAUDE.md §5)"
            )
        return self


def get_settings() -> Settings:
    return Settings()
