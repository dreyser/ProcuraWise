import pytest

from procurawise.shared.migrations import MIGRATIONS_DIR, _load_migration_module

pytestmark = pytest.mark.docker

_MIGRATION_0010 = _load_migration_module(MIGRATIONS_DIR / "0010_curated_sources_indexes.py")


@pytest.fixture(autouse=True)
def _clean_curated_sources(mongo_test_db):
    yield
    mongo_test_db["curated_sources"].drop()


def test_migration_creates_expected_indexes(mongo_test_db) -> None:
    _MIGRATION_0010.apply(mongo_test_db)
    indexes = {idx["name"] for idx in mongo_test_db["curated_sources"].list_indexes()}

    assert "idx_curated_sources_active" in indexes
    assert "idx_curated_sources_created_at" in indexes


def test_migration_apply_is_idempotent(mongo_test_db) -> None:
    _MIGRATION_0010.apply(mongo_test_db)
    _MIGRATION_0010.apply(mongo_test_db)
    indexes = {idx["name"] for idx in mongo_test_db["curated_sources"].list_indexes()}
    assert {"idx_curated_sources_active", "idx_curated_sources_created_at"}.issubset(indexes)
