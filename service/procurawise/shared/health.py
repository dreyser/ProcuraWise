import logging

from azure.core.exceptions import AzureError

from procurawise.shared.config import Settings
from procurawise.shared.mongo import get_mongo_client, ping_mongo
from procurawise.shared.storage import AzureBlobStorage

logger = logging.getLogger("procurawise.health")


def check_mongo_ready(settings: Settings) -> bool:
    client = get_mongo_client(settings)
    return ping_mongo(client)


def check_storage_ready(settings: Settings) -> bool:
    try:
        storage = AzureBlobStorage.from_settings(settings)
        return storage.ping()
    except AzureError:
        return False
