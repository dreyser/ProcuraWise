import pytest

from procurawise.shared.migrations import MIGRATIONS_DIR, _load_migration_module

pytestmark = pytest.mark.docker

_MIGRATION_0004 = _load_migration_module(MIGRATIONS_DIR / "0004_audit_events_indexes.py")


@pytest.fixture(autouse=True)
def _clean_audit_events(mongo_test_db):
    yield
    mongo_test_db["audit_events"].drop()


def test_migration_creates_expected_indexes(mongo_test_db) -> None:
    _MIGRATION_0004.apply(mongo_test_db)
    indexes = {idx["name"]: idx for idx in mongo_test_db["audit_events"].list_indexes()}

    assert "idx_audit_tenant_occurred_at" in indexes
    assert "idx_audit_tenant_evaluation_occurred_at" in indexes
    assert "idx_audit_tenant_resource_occurred_at" in indexes
    assert "ttl_audit_expires_at" in indexes


def test_ttl_index_expires_on_expires_at_field(mongo_test_db) -> None:
    _MIGRATION_0004.apply(mongo_test_db)
    indexes = {idx["name"]: idx for idx in mongo_test_db["audit_events"].list_indexes()}
    ttl_index = indexes["ttl_audit_expires_at"]
    assert ttl_index["expireAfterSeconds"] == 0
    assert dict(ttl_index["key"]) == {"expires_at": 1}


def test_migration_apply_is_idempotent(mongo_test_db) -> None:
    _MIGRATION_0004.apply(mongo_test_db)
    _MIGRATION_0004.apply(mongo_test_db)  # must not raise (create_index is idempotent)
    indexes = {idx["name"] for idx in mongo_test_db["audit_events"].list_indexes()}
    assert {
        "idx_audit_tenant_occurred_at",
        "idx_audit_tenant_evaluation_occurred_at",
        "idx_audit_tenant_resource_occurred_at",
        "ttl_audit_expires_at",
    }.issubset(indexes)
