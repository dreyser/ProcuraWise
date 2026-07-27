import logging

from pymongo import MongoClient
from pymongo.database import Database
from pymongo.errors import PyMongoError

from procurawise.shared.config import Settings

logger = logging.getLogger("procurawise.mongo")

# Keyed by URI (not by Settings, which isn't hashable) so distinct URIs used across
# tests (e.g. an intentionally unreachable one for readiness failure cases) each get
# their own cached client rather than colliding on a single global instance.
_clients: dict[str, MongoClient] = {}


def get_mongo_client(settings: Settings) -> MongoClient:
    client = _clients.get(settings.mongodb_uri)
    if client is None:
        logger.info("connecting to mongo")
        client = MongoClient(
            settings.mongodb_uri,
            serverSelectionTimeoutMS=settings.mongodb_server_selection_timeout_ms,
        )
        _clients[settings.mongodb_uri] = client
    return client


def ping_mongo(client: MongoClient) -> bool:
    try:
        client.admin.command("ping")
        return True
    except PyMongoError:
        return False


def get_database(settings: Settings) -> Database:
    client = get_mongo_client(settings)
    return client[settings.mongodb_db_name]
