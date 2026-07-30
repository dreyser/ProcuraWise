import pytest

from procurawise.shared.migrations import MIGRATIONS_DIR, _load_migration_module

pytestmark = pytest.mark.docker

_MIGRATION_0005 = _load_migration_module(MIGRATIONS_DIR / "0005_assignments_indexes.py")


@pytest.fixture(autouse=True)
def _clean_assignments(mongo_test_db):
    yield
    mongo_test_db["assignments"].drop()


def test_migration_creates_expected_indexes(mongo_test_db) -> None:
    _MIGRATION_0005.apply(mongo_test_db)
    indexes = {idx["name"]: idx for idx in mongo_test_db["assignments"].list_indexes()}

    assert "uniq_assignment_natural_key" in indexes
    assert indexes["uniq_assignment_natural_key"]["unique"] is True
    assert "idx_assignment_tenant_evaluation" in indexes
    assert "idx_assignment_tenant_evaluation_evaluator" in indexes


def test_migration_apply_is_idempotent(mongo_test_db) -> None:
    _MIGRATION_0005.apply(mongo_test_db)
    _MIGRATION_0005.apply(mongo_test_db)  # must not raise (create_index is idempotent)
    indexes = {idx["name"] for idx in mongo_test_db["assignments"].list_indexes()}
    assert {
        "uniq_assignment_natural_key",
        "idx_assignment_tenant_evaluation",
        "idx_assignment_tenant_evaluation_evaluator",
    }.issubset(indexes)
