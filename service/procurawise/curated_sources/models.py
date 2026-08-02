from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4


def new_id() -> str:
    return uuid4().hex


@dataclass(frozen=True)
class CuratedSource:
    """Fase 14 (ADR 0011): a platform-level, admin-curated reference - NOT
    tenant data (`CuratedSourceProvider` reads the same rows for every
    tenant, see `ai.curated_source_provider`). `summary` is manually
    authored/pasted by a platform_admin, never crawled or fetched from
    `url` - Fase 14 does not fetch arbitrary URLs (founder decision, Fase 14
    planning). Soft-deletable only: `active=False` hides a source from
    future `discover()` calls without deleting the row, so a past
    `AIExecution.source_catalog` snapshot that already cited this source's
    id remains attributable to a real, inspectable admin record."""

    id: str
    title: str
    url: str
    summary: str
    tags: list[str]
    active: bool
    created_by_admin_id: str
    created_at: datetime
    updated_at: datetime

    @staticmethod
    def create(
        *, title: str, url: str, summary: str, tags: list[str], created_by_admin_id: str
    ) -> "CuratedSource":
        now = datetime.now(UTC)
        return CuratedSource(
            id=new_id(),
            title=title,
            url=url,
            summary=summary,
            tags=tags,
            active=True,
            created_by_admin_id=created_by_admin_id,
            created_at=now,
            updated_at=now,
        )

    def to_document(self) -> dict[str, Any]:
        return {
            "_id": self.id,
            "title": self.title,
            "url": self.url,
            "summary": self.summary,
            "tags": self.tags,
            "active": self.active,
            "created_by_admin_id": self.created_by_admin_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @staticmethod
    def from_document(doc: dict[str, Any]) -> "CuratedSource":
        return CuratedSource(
            id=doc["_id"],
            title=doc["title"],
            url=doc["url"],
            summary=doc["summary"],
            tags=doc.get("tags", []),
            active=doc["active"],
            created_by_admin_id=doc["created_by_admin_id"],
            created_at=doc["created_at"],
            updated_at=doc["updated_at"],
        )
