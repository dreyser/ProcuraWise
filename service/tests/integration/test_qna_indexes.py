import pytest

from procurawise.shared.migrations import MIGRATIONS_DIR, _load_migration_module

pytestmark = pytest.mark.docker

_MIGRATION_0014 = _load_migration_module(MIGRATIONS_DIR / "0014_qna_indexes.py")


@pytest.fixture(autouse=True)
def _clean_qna_questions(mongo_test_db):
    yield
    mongo_test_db["qna_questions"].drop()


def test_migration_creates_expected_indexes(mongo_test_db) -> None:
    _MIGRATION_0014.apply(mongo_test_db)
    indexes = {idx["name"] for idx in mongo_test_db["qna_questions"].list_indexes()}

    assert "idx_qna_questions_tenant_evaluation_status" in indexes
    assert "idx_qna_questions_tenant_proposal" in indexes


def test_migration_apply_is_idempotent(mongo_test_db) -> None:
    _MIGRATION_0014.apply(mongo_test_db)
    _MIGRATION_0014.apply(mongo_test_db)
    indexes = {idx["name"] for idx in mongo_test_db["qna_questions"].list_indexes()}
    assert {
        "idx_qna_questions_tenant_evaluation_status",
        "idx_qna_questions_tenant_proposal",
    }.issubset(indexes)
