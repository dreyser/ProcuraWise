import pytest

from procurawise.shared.migrations import MIGRATIONS_DIR, _load_migration_module

pytestmark = pytest.mark.docker

_MIGRATION_0006 = _load_migration_module(MIGRATIONS_DIR / "0006_platform_admins_indexes.py")


@pytest.fixture(autouse=True)
def _clean_platform_admins(mongo_test_db):
    yield
    mongo_test_db["platform_admins"].drop()


def test_migration_creates_expected_index(mongo_test_db) -> None:
    _MIGRATION_0006.apply(mongo_test_db)
    indexes = {idx["name"]: idx for idx in mongo_test_db["platform_admins"].list_indexes()}

    assert "uniq_platform_admin_email" in indexes
    assert indexes["uniq_platform_admin_email"]["unique"] is True


def test_migration_apply_is_idempotent(mongo_test_db) -> None:
    _MIGRATION_0006.apply(mongo_test_db)
    _MIGRATION_0006.apply(mongo_test_db)
    indexes = {idx["name"] for idx in mongo_test_db["platform_admins"].list_indexes()}
    assert "uniq_platform_admin_email" in indexes
