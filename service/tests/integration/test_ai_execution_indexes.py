import pytest

from procurawise.shared.migrations import MIGRATIONS_DIR, _load_migration_module

pytestmark = pytest.mark.docker

_MIGRATION_0009 = _load_migration_module(MIGRATIONS_DIR / "0009_ai_executions_indexes.py")


@pytest.fixture(autouse=True)
def _clean_ai_executions(mongo_test_db):
    yield
    mongo_test_db["ai_executions"].drop()


def test_migration_creates_expected_indexes(mongo_test_db) -> None:
    _MIGRATION_0009.apply(mongo_test_db)
    indexes = {idx["name"]: idx for idx in mongo_test_db["ai_executions"].list_indexes()}

    assert "idx_ai_executions_tenant_evaluation_created_at" in indexes
    assert "ttl_ai_executions_expires_at" in indexes


def test_ttl_index_expires_on_expires_at_field(mongo_test_db) -> None:
    _MIGRATION_0009.apply(mongo_test_db)
    indexes = {idx["name"]: idx for idx in mongo_test_db["ai_executions"].list_indexes()}
    ttl_index = indexes["ttl_ai_executions_expires_at"]
    assert ttl_index["expireAfterSeconds"] == 0
    assert dict(ttl_index["key"]) == {"expires_at": 1}


def test_migration_apply_is_idempotent(mongo_test_db) -> None:
    _MIGRATION_0009.apply(mongo_test_db)
    _MIGRATION_0009.apply(mongo_test_db)
    indexes = {idx["name"] for idx in mongo_test_db["ai_executions"].list_indexes()}
    assert {
        "idx_ai_executions_tenant_evaluation_created_at",
        "ttl_ai_executions_expires_at",
    }.issubset(indexes)
