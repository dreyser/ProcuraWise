import pytest
from fastapi.testclient import TestClient

from procurawise.api.main import app
from procurawise.dev_seed import SEEDED_COLLECTIONS, seed
from procurawise.shared.config import Settings, get_settings
from procurawise.shared.mongo import get_mongo_client
from procurawise.shared.storage import AzureBlobStorage

TEST_MONGO_DB_NAME = "procurawise_test"
TEST_STORAGE_CONTAINER_NAME = "procurawise-test"


@pytest.fixture
def mongo_test_settings() -> Settings:
    return Settings(_env_file=None, mongodb_db_name=TEST_MONGO_DB_NAME)


@pytest.fixture
def mongo_test_db(mongo_test_settings: Settings):
    client = get_mongo_client(mongo_test_settings)
    db = client[mongo_test_settings.mongodb_db_name]
    yield db
    db.drop_collection("_infra_probe")


@pytest.fixture
def seeded_actors(mongo_test_settings: Settings, mongo_test_db):
    """Membership id keyed by (tenant_id, role) - shared across every
    docker-marked test that needs a seeded identity fixture plus (as of
    VS-2B) one seeded draft Evaluation+Proposal under tenant_a (see
    dev_seed.py)."""
    memberships = seed(mongo_test_settings)
    by_key = {(m.tenant_id, m.role): m.id for m in memberships}
    yield by_key
    for name in SEEDED_COLLECTIONS:
        mongo_test_db[name].drop()


@pytest.fixture
def client(mongo_test_settings: Settings, seeded_actors):
    app.dependency_overrides[get_settings] = lambda: mongo_test_settings
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def tenant_ids(seeded_actors: dict[tuple[str, str], str]) -> tuple[str, str]:
    """Returns two arbitrary, distinct tenant ids from the seed. The labels
    "tenant_a"/"tenant_b" only mean "some tenant" / "some other tenant" -
    tenant/membership ids are random UUIDs, so this sorted order carries no
    semantic meaning. Only use where a test needs two distinct tenants but
    doesn't care which one is which."""
    tenants = {tenant_id for tenant_id, _role in seeded_actors}
    tenant_a, tenant_b = sorted(tenants)
    return tenant_a, tenant_b


def unique_actor_by_role(seeded_actors: dict[tuple[str, str], str], role: str) -> tuple[str, str]:
    """Resolves (tenant_id, membership_id) for the seeded actor with this
    role, asserting there is exactly one."""
    matches = [
        (tenant_id, membership_id)
        for (tenant_id, actor_role), membership_id in seeded_actors.items()
        if actor_role == role
    ]
    assert len(matches) == 1, (
        f"expected exactly one seeded actor with role={role!r}, found {len(matches)}: {matches}"
    )
    return matches[0]


@pytest.fixture
def blob_test_settings() -> Settings:
    return Settings(_env_file=None, storage_container_name=TEST_STORAGE_CONTAINER_NAME)


@pytest.fixture
def blob_test_storage(blob_test_settings: Settings):
    storage = AzureBlobStorage.from_settings(blob_test_settings)
    storage.ensure_container()
    yield storage
