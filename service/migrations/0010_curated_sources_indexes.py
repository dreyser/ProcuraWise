from pymongo.database import Database


def apply(db: Database) -> None:
    # Fase 14 (ADR 0011): curated_sources is platform-level content, not
    # tenant-scoped - no tenant_id in the index. `active` backs
    # CuratedSourceProvider.discover()'s find_active() query; the admin list
    # endpoint sorts by created_at.
    db["curated_sources"].create_index("active", name="idx_curated_sources_active")
    db["curated_sources"].create_index("created_at", name="idx_curated_sources_created_at")
