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

    # Fase 27 (ADR 0004/0019): "staging" is its own value, not a reuse of
    # "production" - Stripe must never accept a live key in staging (a
    # secondary pre-production environment used for UAT rehearsal, plan
    # Bloqueante #1 Opcion A), which reusing "production" literally would
    # have broken (see _reject_live_stripe_key_outside_production below,
    # which only exempts environment=="production" and therefore keeps
    # rejecting live keys in staging automatically, unchanged). See
    # `is_production_like` for the validators that *do* treat staging and
    # production identically (OIDC/AI/notifications real config, no
    # in-memory queue, no default JWT secret).
    environment: Literal["local", "test", "staging", "production"] = "local"
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

    # Fase 24 (notifications, ADR 0024): Azure Communication Services is the
    # only NotificationEmailProvider implementation. False by default - no
    # ACS emulator exists (unlike Azurite/Service Bus emulator), so local/
    # test/CI always use LoggingNotificationEmailProvider unless a developer
    # opts in explicitly. The production validator below requires the
    # connection string/sender address together whenever this is true.
    notifications_email_enabled: bool = False
    acs_connection_string: str | None = None
    # A verified ACS sender, e.g. "DoNotReply@<domain>.azurecomm.net" -
    # provisioning the domain/sender is a one-time infra/ops step (documented
    # in deployment.md), not something this adapter does at runtime.
    acs_sender_address: str | None = None
    # No message-bus redelivery exists anywhere in this project today
    # (ServiceBusMessageBus.consume() completes the message before the
    # handler runs) - retries are NotificationService's own mechanism, driven
    # by these three fields, not the queue's.
    notification_email_max_attempts: int = 3
    notification_email_retry_delay_minutes_1: int = 2
    notification_email_retry_delay_minutes_2: int = 10
    # Own field, not audit_event_retention_days/ai_execution_retention_days -
    # a Notification is UX ephemera (the bell dropdown's history), not a
    # compliance record, so a shorter default is appropriate.
    notification_retention_days: int = 90

    # Fase 25 (billing/admin, ADR 0025, plan Bloqueante #1 Opcion A): Stripe
    # Checkout (mode="payment", one-time per-evaluation purchase only - no
    # subscription in this phase). Same flag-gated shape as
    # notifications_email_enabled above, for the same reason: no Stripe
    # sandbox emulator exists (unlike Azurite/Service Bus emulator), so
    # local/test/CI always use LocalPaymentProvider unless a developer opts
    # in explicitly. stripe_price_id_evaluation is a Stripe Price id
    # (`price_...`) created in the Stripe dashboard, never an amount/currency
    # this codebase computes itself.
    billing_enabled: bool = False
    stripe_secret_key: str | None = None
    stripe_webhook_secret: str | None = None
    stripe_price_id_evaluation: str | None = None
    stripe_request_timeout_seconds: int = 20
    # Comfortably longer than Stripe's own webhook-retry window (~3 days) -
    # a late retry must still find its event_id in the idempotency ledger.
    billing_webhook_event_retention_days: int = 30

    # Fase 26 (Hardening, plan Bloque 1): deny-all by default (empty string)
    # - cross-origin browser calls only happen at all once Fase 27 deploys
    # the SPA and API to distinct origins; local dev/CI never need this
    # (Vite's proxy in vite.config.ts makes the browser's own requests
    # same-origin). Comma-separated, not a native `list[str]` field -
    # pydantic-settings' env source tries to JSON-decode any complex-typed
    # field before a validator ever sees it, which rejects a plain
    # comma-separated string outright (confirmed against the pinned
    # pydantic-settings version); see the `cors_allowed_origins_list`
    # property below for the parsed form every call site actually uses.
    cors_allowed_origins: str = ""

    # Fase 26 (Hardening, plan Bloque 2, Decisión recomendada #2): in-process
    # only, no Redis (ADR 0020 retired it from the local/dev architecture and
    # NFR-003's 50-concurrent-user target doesn't justify reopening that
    # decision) - see shared/rate_limit.py. Does not coordinate across
    # multiple API replicas; accepted limitation while Container Apps runs a
    # single replica, documented in threat-model.md, revisit in Fase 27 if
    # the real deployment scales out. Endpoints prioritized by
    # threat-model.md: login (brute force), AI triggers (cost abuse, already
    # named "Fase 26" in the accepted-risks table), billing checkout.
    rate_limit_login_max_attempts: int = 5
    rate_limit_login_window_seconds: int = 60
    rate_limit_ai_max_requests: int = 10
    rate_limit_ai_window_seconds: int = 3600
    rate_limit_billing_checkout_max_requests: int = 5
    rate_limit_billing_checkout_window_seconds: int = 3600

    @property
    def cors_allowed_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]

    @property
    def is_production_like(self) -> bool:
        """Fase 27: "staging" is Azure real, similar to production
        (deployment.md) - it must fail closed on the same missing-real-
        config mistakes production does (no in-memory queue, no default JWT
        secret, no missing OIDC/AI/notifications credentials), so a
        misconfigured staging deploy is caught the same way a misconfigured
        production one would be. Deliberately NOT used by
        _reject_live_stripe_key_outside_production - staging must keep
        rejecting live Stripe keys exactly like local/test do, never be
        treated as an environment where a live key is expected."""
        return self.environment in ("staging", "production")

    @model_validator(mode="after")
    def _reject_memory_queue_in_production(self) -> Self:
        if self.is_production_like and self.queue_backend == "memory":
            raise ValueError(
                "queue_backend=memory no está permitido cuando environment=staging|production"
            )
        return self

    @model_validator(mode="after")
    def _require_real_auth_config_in_production(self) -> Self:
        if not self.is_production_like:
            return self
        if self.jwt_secret == _INSECURE_DEV_JWT_SECRET or len(self.jwt_secret) < 32:
            raise ValueError(
                "jwt_secret debe configurarse explícitamente (>=32 caracteres, "
                "distinto del default de desarrollo) cuando environment=staging|production"
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
                f"faltan credenciales oidc requeridas cuando environment=staging|production: "
                f"{', '.join(missing)}"
            )
        return self

    @model_validator(mode="after")
    def _require_real_ai_config_in_production(self) -> Self:
        if not self.is_production_like:
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
                "faltan credenciales de Azure OpenAI requeridas cuando "
                f"environment=staging|production: {', '.join(missing)}"
            )
        return self

    @model_validator(mode="after")
    def _require_real_notification_config_in_production(self) -> Self:
        """Fase 24 (ADR 0024): prod-like-required (azure_openai-style), not
        fail-closed-in-every-environment (foundry_web_search-style) - unlike
        Foundry/Bing Grounding (ADR 0011), there is no documented legal-
        approval gate on transactional email, and notifications fire
        automatically off routine domain mutations every dev/CI run already
        exercises - forcing real ACS credentials into every local .env for a
        feature no local workflow can test against a real service anyway
        would only add friction, not safety. Fase 27: applies to `staging`
        too, via `is_production_like` - see that property's docstring."""
        if not self.is_production_like:
            return self
        if not self.notifications_email_enabled:
            return self
        missing = [
            name
            for name, value in (
                ("acs_connection_string", self.acs_connection_string),
                ("acs_sender_address", self.acs_sender_address),
            )
            if not value
        ]
        if missing:
            raise ValueError(
                f"faltan credenciales de Azure Communication Services requeridas cuando "
                f"environment=staging|production y notifications_email_enabled=true: "
                f"{', '.join(missing)}"
            )
        return self

    @model_validator(mode="after")
    def _require_real_billing_config_in_production(self) -> Self:
        """Fase 25 (ADR 0025): prod-like-required (azure_openai/notifications-
        style), not fail-closed-in-every-environment (foundry-style) - no
        documented legal-approval gate exists for Stripe (unlike Foundry/Bing
        Grounding, ADR 0011), and no local Stripe sandbox emulator exists for
        any environment to meaningfully test against anyway. Fase 27: applies
        to `staging` too (if billing is enabled there for UAT rehearsal it
        must still be fully configured), but
        `_reject_live_stripe_key_outside_production` below keeps staging
        limited to `sk_test_` keys regardless - staging never gets a path to
        a live key."""
        if not self.is_production_like:
            return self
        if not self.billing_enabled:
            return self
        missing = [
            name
            for name, value in (
                ("stripe_secret_key", self.stripe_secret_key),
                ("stripe_webhook_secret", self.stripe_webhook_secret),
                ("stripe_price_id_evaluation", self.stripe_price_id_evaluation),
            )
            if not value
        ]
        if missing:
            raise ValueError(
                f"faltan credenciales de Stripe requeridas cuando environment=staging|production y "
                f"billing_enabled=true: {', '.join(missing)}"
            )
        return self

    @model_validator(mode="after")
    def _reject_live_stripe_key_outside_production(self) -> Self:
        """Cheap, high-value guard (plan §11 recomendacion #2): a live
        secret key (`sk_live_...`) configured outside production is almost
        certainly a mistake (a real key leaked into a dev .env), not a
        deliberate choice - fail closed on it in every non-production
        environment, unlike the rest of this file's prod-only validators."""
        if self.environment == "production":
            return self
        if self.stripe_secret_key and not self.stripe_secret_key.startswith("sk_test_"):
            raise ValueError(
                "stripe_secret_key debe empezar con 'sk_test_' fuera de environment=production "
                "(una clave live nunca debe configurarse en desarrollo/test/CI)"
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
