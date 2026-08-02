import logging

from procurawise.curated_sources.models import CuratedSource
from procurawise.curated_sources.repository import CuratedSourceRepository

logger = logging.getLogger("procurawise.curated_sources")


class CuratedSourceNotFoundError(Exception):
    """No CuratedSource exists for this id."""


class CuratedSourceService:
    """Fase 14 (ADR 0011): minimal CRUD for the platform-level curated-source
    library, called only from the platform_admin-only router (CLAUDE.md §4).

    Deliberately does NOT use `AuditEventService`: `AuditEvent` is a
    tenant-scoped, per-evaluation trail (`audit.repository.
    AuditEventRepository` always writes through `TenantCollection`, and the
    only read path is per-evaluation) - a platform-global admin action with
    no tenant or evaluation to attach to does not fit that model, and
    inventing a sentinel tenant_id would misrepresent what the trail means.
    Content changes are structured-logged instead, per the plan's
    distinction between the tenant-scoped business audit trail and
    operational logs/metrics.
    """

    def __init__(self, repository: CuratedSourceRepository) -> None:
        self._repository = repository

    def create(
        self, *, title: str, url: str, summary: str, tags: list[str], admin_id: str
    ) -> CuratedSource:
        source = CuratedSource.create(
            title=title, url=url, summary=summary, tags=tags, created_by_admin_id=admin_id
        )
        self._repository.insert(source.to_document())
        logger.info("curated_source_created", extra={"source_id": source.id, "admin_id": admin_id})
        return source

    def list_all(self) -> list[CuratedSource]:
        return [CuratedSource.from_document(doc) for doc in self._repository.find_all()]

    def get(self, source_id: str) -> CuratedSource:
        doc = self._repository.find_by_id(source_id)
        if doc is None:
            raise CuratedSourceNotFoundError(source_id)
        return CuratedSource.from_document(doc)

    def update(
        self,
        source_id: str,
        *,
        title: str | None,
        url: str | None,
        summary: str | None,
        tags: list[str] | None,
        admin_id: str,
    ) -> CuratedSource:
        # `self.get` below raises CuratedSourceNotFoundError if the id
        # doesn't exist, so a no-op update (all fields None) still validates
        # existence rather than silently returning a stale/absent record.
        field_updates = {
            key: value
            for key, value in {"title": title, "url": url, "summary": summary, "tags": tags}.items()
            if value is not None
        }
        if field_updates:
            if not self._repository.update_metadata(source_id, field_updates):
                raise CuratedSourceNotFoundError(source_id)
            logger.info(
                "curated_source_updated", extra={"source_id": source_id, "admin_id": admin_id}
            )
        return self.get(source_id)

    def activate(self, source_id: str, *, admin_id: str) -> CuratedSource:
        if not self._repository.set_active(source_id, True):
            raise CuratedSourceNotFoundError(source_id)
        logger.info(
            "curated_source_activated", extra={"source_id": source_id, "admin_id": admin_id}
        )
        return self.get(source_id)

    def deactivate(self, source_id: str, *, admin_id: str) -> CuratedSource:
        if not self._repository.set_active(source_id, False):
            raise CuratedSourceNotFoundError(source_id)
        logger.info(
            "curated_source_deactivated", extra={"source_id": source_id, "admin_id": admin_id}
        )
        return self.get(source_id)
