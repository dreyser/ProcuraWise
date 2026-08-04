import pytest

from procurawise.shared.migrations import MIGRATIONS_DIR, _load_migration_module

pytestmark = pytest.mark.docker

_MIGRATION_0016 = _load_migration_module(MIGRATIONS_DIR / "0016_fx_rates_indexes.py")


@pytest.fixture(autouse=True)
def _clean_fx_rates(mongo_test_db):
    yield
    mongo_test_db["fx_rates"].drop()


def test_migration_creates_expected_index(mongo_test_db) -> None:
    _MIGRATION_0016.apply(mongo_test_db)
    indexes = {idx["name"] for idx in mongo_test_db["fx_rates"].list_indexes()}
    assert "idx_fx_rates_pair_effective_date" in indexes


def test_migration_apply_is_idempotent(mongo_test_db) -> None:
    _MIGRATION_0016.apply(mongo_test_db)
    _MIGRATION_0016.apply(mongo_test_db)
    indexes = {idx["name"] for idx in mongo_test_db["fx_rates"].list_indexes()}
    assert "idx_fx_rates_pair_effective_date" in indexes
