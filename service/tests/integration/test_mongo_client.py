import pytest

from procurawise.shared.config import Settings
from procurawise.shared.mongo import get_mongo_client, ping_mongo

pytestmark = pytest.mark.docker


def test_ping_mongo_succeeds_against_live_mongo(mongo_test_settings: Settings) -> None:
    client = get_mongo_client(mongo_test_settings)
    assert ping_mongo(client) is True


def test_write_then_read_a_technical_document(mongo_test_db) -> None:
    collection = mongo_test_db["_infra_probe"]

    collection.insert_one({"_id": "probe-1", "checked": True})
    document = collection.find_one({"_id": "probe-1"})

    assert document is not None
    assert document["checked"] is True

    # explicit cleanup on top of the conftest fixture's collection drop
    collection.delete_one({"_id": "probe-1"})
    assert collection.find_one({"_id": "probe-1"}) is None
