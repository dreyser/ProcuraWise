import pytest

from procurawise.shared.migrations import MIGRATIONS_DIR, _load_migration_module

pytestmark = pytest.mark.docker

_MIGRATION_0008 = _load_migration_module(MIGRATIONS_DIR / "0008_knowledge_template_indexes.py")


@pytest.fixture(autouse=True)
def _clean_knowledge_templates(mongo_test_db):
    yield
    mongo_test_db["knowledge_templates"].drop()


def test_migration_creates_expected_index(mongo_test_db) -> None:
    _MIGRATION_0008.apply(mongo_test_db)
    indexes = {idx["name"] for idx in mongo_test_db["knowledge_templates"].list_indexes()}
    assert "idx_knowledge_template_tenant_created_at" in indexes


def test_migration_apply_is_idempotent(mongo_test_db) -> None:
    _MIGRATION_0008.apply(mongo_test_db)
    _MIGRATION_0008.apply(mongo_test_db)  # must not raise (create_index is idempotent)
    indexes = {idx["name"] for idx in mongo_test_db["knowledge_templates"].list_indexes()}
    assert "idx_knowledge_template_tenant_created_at" in indexes
