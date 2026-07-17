import pytest

from procurawise.shared.config import Settings
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
def blob_test_settings() -> Settings:
    return Settings(_env_file=None, storage_container_name=TEST_STORAGE_CONTAINER_NAME)


@pytest.fixture
def blob_test_storage(blob_test_settings: Settings):
    storage = AzureBlobStorage.from_settings(blob_test_settings)
    storage.ensure_container()
    yield storage
