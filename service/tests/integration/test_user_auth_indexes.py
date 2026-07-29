from datetime import UTC, datetime

import pytest
from pymongo.errors import DuplicateKeyError

from procurawise.shared.migrations import MIGRATIONS_DIR, _load_migration_module

_MIGRATION_0003 = _load_migration_module(MIGRATIONS_DIR / "0003_users_auth_indexes.py")


@pytest.fixture(autouse=True)
def _clean_users(mongo_test_db):
    # Calls apply() directly rather than going through run_migrations()'s
    # already-applied tracking: other docker-marked tests' `seeded_actors`
    # fixture tears down by dropping the whole `users` collection (and with
    # it, any indexes), which run_migrations() would never notice or repair
    # since it only tracks migration ids, not whether their effects still
    # exist. create_index() is itself idempotent, so calling apply() again
    # here is always safe and makes this test file's correctness independent
    # of what other tests do to `users` or of test execution order.
    _MIGRATION_0003.apply(mongo_test_db)
    mongo_test_db["users"].delete_many({})
    yield
    mongo_test_db["users"].delete_many({})


def _user_doc(user_id: str, email: str, oidc_identities: list[dict] | None = None) -> dict:
    return {
        "_id": user_id,
        "display_name": "Test User",
        "email": email,
        "created_at": datetime.now(UTC),
        "password_hash": None,
        "oidc_identities": oidc_identities or [],
    }


@pytest.mark.docker
def test_email_unique_index_rejects_duplicate(mongo_test_db) -> None:
    mongo_test_db["users"].insert_one(_user_doc("u1", "dup@example.com"))
    with pytest.raises(DuplicateKeyError):
        mongo_test_db["users"].insert_one(_user_doc("u2", "dup@example.com"))


@pytest.mark.docker
def test_users_without_oidc_identities_do_not_collide(mongo_test_db) -> None:
    """Confirms the empty-array-produces-no-index-key Mongo behavior the
    migration's `sparse=True` relies on - not assumed, verified against real
    Mongo (a first attempt without `sparse` failed exactly this case)."""
    mongo_test_db["users"].insert_one(_user_doc("u1", "a@example.com"))
    mongo_test_db["users"].insert_one(_user_doc("u2", "b@example.com"))  # must not raise


@pytest.mark.docker
def test_oidc_identity_unique_index_rejects_duplicate(mongo_test_db) -> None:
    identity = [{"provider": "microsoft", "subject": "sub-1", "linked_at": datetime.now(UTC)}]
    mongo_test_db["users"].insert_one(_user_doc("u1", "a@example.com", identity))
    with pytest.raises(DuplicateKeyError):
        mongo_test_db["users"].insert_one(_user_doc("u2", "b@example.com", identity))


@pytest.mark.docker
def test_oidc_identity_allows_same_subject_on_different_providers(mongo_test_db) -> None:
    mongo_test_db["users"].insert_one(
        _user_doc(
            "u1",
            "a@example.com",
            [{"provider": "microsoft", "subject": "same-subject", "linked_at": datetime.now(UTC)}],
        )
    )
    mongo_test_db["users"].insert_one(
        _user_doc(
            "u2",
            "b@example.com",
            [{"provider": "google", "subject": "same-subject", "linked_at": datetime.now(UTC)}],
        )
    )  # must not raise - (provider, subject) pair differs
