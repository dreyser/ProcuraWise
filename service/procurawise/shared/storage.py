import logging
from datetime import UTC, datetime, timedelta
from typing import Protocol

from azure.core.exceptions import ResourceExistsError, ResourceNotFoundError
from azure.storage.blob import (
    BlobSasPermissions,
    BlobServiceClient,
    ContentSettings,
    generate_blob_sas,
)

from procurawise.shared.config import Settings

logger = logging.getLogger("procurawise.storage")


class BlobStorage(Protocol):
    def ensure_container(self) -> None: ...

    def upload(self, blob_name: str, data: bytes, content_type: str | None = None) -> None: ...

    def download(self, blob_name: str) -> bytes: ...

    def delete(self, blob_name: str) -> None: ...

    def exists(self, blob_name: str) -> bool: ...

    def generate_download_url(
        self,
        blob_name: str,
        *,
        expires_in_minutes: int,
        filename: str,
        content_type: str,
    ) -> str: ...


class AzureBlobStorage:
    """Sync adapter over azure-storage-blob. Works against Azurite locally and
    against real Azure Blob Storage in staging/production without code changes."""

    def __init__(
        self,
        connection_string: str,
        container_name: str,
        timeout_seconds: int = 2,
        api_version: str = "2025-01-05",
    ) -> None:
        self._container_name = container_name
        self._timeout_seconds = timeout_seconds
        logger.info("connecting to blob storage")
        # api_version is explicit (not left on the SDK default) - see the comment on
        # Settings.storage_api_version. get_container_client/get_blob_client below
        # both inherit this same api_version from the service client automatically.
        self._service_client = BlobServiceClient.from_connection_string(
            connection_string, api_version=api_version
        )
        self._container_client = self._service_client.get_container_client(container_name)

    @classmethod
    def from_settings(
        cls, settings: Settings, *, container_name: str | None = None
    ) -> "AzureBlobStorage":
        """`container_name` defaults to `settings.storage_container_name` (the
        generic container health checks use) - pass an override (e.g.
        `settings.documents_container_name`, Fase 16) to point this same
        adapter at a different, dedicated container without a second class."""
        return cls(
            connection_string=settings.storage_connection_string,
            container_name=container_name or settings.storage_container_name,
            timeout_seconds=settings.storage_timeout_seconds,
            api_version=settings.storage_api_version,
        )

    def ensure_container(self) -> None:
        try:
            self._container_client.create_container(timeout=self._timeout_seconds)
        except ResourceExistsError:
            pass

    def upload(self, blob_name: str, data: bytes, content_type: str | None = None) -> None:
        content_settings = ContentSettings(content_type=content_type) if content_type else None
        self._container_client.upload_blob(
            name=blob_name,
            data=data,
            overwrite=True,
            content_settings=content_settings,
            timeout=self._timeout_seconds,
        )

    def download(self, blob_name: str) -> bytes:
        stream = self._container_client.download_blob(blob_name, timeout=self._timeout_seconds)
        return stream.readall()

    def delete(self, blob_name: str) -> None:
        try:
            self._container_client.delete_blob(blob_name, timeout=self._timeout_seconds)
        except ResourceNotFoundError:
            pass

    def exists(self, blob_name: str) -> bool:
        blob_client = self._container_client.get_blob_client(blob_name)
        return blob_client.exists(timeout=self._timeout_seconds)

    def generate_download_url(
        self,
        blob_name: str,
        *,
        expires_in_minutes: int,
        filename: str,
        content_type: str,
    ) -> str:
        """Fase 16: read-only Service SAS, signed with the storage account key
        extracted from the connection string - never a User Delegation SAS
        (that requires Azure AD/managed identity and does not work against
        Azurite, breaking dev/prod parity). `content_disposition`/
        `content_type` are response-header overrides baked into the SAS
        itself, so the blob never needs to carry a permanent Content-
        Disposition - the caller always re-authorizes before calling this
        (see documents/service.py), so a freshly generated URL is the only
        one that ever exists for a given request."""
        credential = self._service_client.credential
        account_key = getattr(credential, "account_key", None)
        account_name = self._service_client.account_name
        if not account_key or not account_name:
            raise RuntimeError(
                "generate_download_url requires a shared-key connection string "
                "(account_name/account_key not found on the service client)"
            )
        sas_token = generate_blob_sas(
            account_name=account_name,
            container_name=self._container_name,
            blob_name=blob_name,
            account_key=account_key,
            permission=BlobSasPermissions(read=True),
            expiry=datetime.now(UTC) + timedelta(minutes=expires_in_minutes),
            content_disposition=f'attachment; filename="{filename}"',
            content_type=content_type,
        )
        blob_client = self._container_client.get_blob_client(blob_name)
        return f"{blob_client.url}?{sas_token}"

    def ping(self) -> bool:
        """Cheap connectivity check for readiness probes - no side effects,
        unlike `ensure_container`. `retry_total=0` overrides azure-core's default
        retry policy (3 retries with exponential backoff), which would otherwise
        turn a "storage is down" check into a multi-minute wait before failing."""
        self._service_client.get_service_properties(timeout=self._timeout_seconds, retry_total=0)
        return True
