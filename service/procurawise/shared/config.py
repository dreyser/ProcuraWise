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


def get_settings() -> Settings:
    return Settings()
