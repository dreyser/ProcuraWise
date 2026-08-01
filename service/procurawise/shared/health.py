import logging

from azure.core.exceptions import AzureError

from procurawise.ai.azure_openai_provider import AzureOpenAIProvider
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


def check_ai_provider_ready(settings: Settings) -> bool | None:
    """`None` means "not configured in this environment" (local/test without
    Azure OpenAI credentials) - deliberately excluded from `/health/ready`'s
    all() rather than counted as unready, since AI is optional outside
    production (Settings._require_real_ai_config_in_production)."""
    if not (
        settings.azure_openai_endpoint
        and settings.azure_openai_api_key
        and settings.azure_openai_deployment
    ):
        return None
    try:
        return AzureOpenAIProvider.from_settings(settings).ping()
    except Exception:  # noqa: BLE001 - health probe must never itself crash the endpoint
        return False
