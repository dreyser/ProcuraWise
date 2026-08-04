import pytest

from procurawise.shared.migrations import MIGRATIONS_DIR, _load_migration_module

pytestmark = pytest.mark.docker

_MIGRATION_0015 = _load_migration_module(MIGRATIONS_DIR / "0015_ai_executions_proposal_index.py")


@pytest.fixture(autouse=True)
def _clean_ai_executions(mongo_test_db):
    yield
    mongo_test_db["ai_executions"].drop()


def test_migration_creates_expected_index(mongo_test_db) -> None:
    _MIGRATION_0015.apply(mongo_test_db)
    indexes = {idx["name"]: idx for idx in mongo_test_db["ai_executions"].list_indexes()}

    assert "idx_ai_executions_tenant_proposal_created_at" in indexes
    index = indexes["idx_ai_executions_tenant_proposal_created_at"]
    assert list(index["key"].items()) == [("tenant_id", 1), ("proposal_id", 1), ("created_at", -1)]


def test_migration_apply_is_idempotent(mongo_test_db) -> None:
    _MIGRATION_0015.apply(mongo_test_db)
    _MIGRATION_0015.apply(mongo_test_db)
    indexes = {idx["name"] for idx in mongo_test_db["ai_executions"].list_indexes()}
    assert "idx_ai_executions_tenant_proposal_created_at" in indexes
