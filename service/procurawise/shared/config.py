from typing import Literal, Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    @model_validator(mode="after")
    def _reject_memory_queue_in_production(self) -> Self:
        if self.environment == "production" and self.queue_backend == "memory":
            raise ValueError("queue_backend=memory no está permitido cuando environment=production")
        return self


def get_settings() -> Settings:
    return Settings()

import os  # REMOVE-ME: intentional unused import, only for testing the ci/backend lint gate
