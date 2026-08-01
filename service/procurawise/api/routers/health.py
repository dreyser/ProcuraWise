from fastapi import APIRouter, Response

from procurawise.shared.config import get_settings
from procurawise.shared.health import (
    check_ai_provider_ready,
    check_mongo_ready,
    check_storage_ready,
)

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
def ready(response: Response) -> dict[str, object]:
    settings = get_settings()
    checks: dict[str, bool] = {
        "mongodb": check_mongo_ready(settings),
        "storage": check_storage_ready(settings),
    }
    ai_provider_ready = check_ai_provider_ready(settings)
    if ai_provider_ready is not None:
        checks["ai_provider"] = ai_provider_ready
    all_ready = all(checks.values())
    response.status_code = 200 if all_ready else 503
    return {"status": "ok" if all_ready else "unavailable", "checks": checks}
