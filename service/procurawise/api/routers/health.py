from fastapi import APIRouter, Response

from procurawise.shared.config import get_settings
from procurawise.shared.health import check_mongo_ready, check_storage_ready

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/version")
def version() -> dict[str, str]:
    """REMOVE-ME: intentional new route to test the ci/contracts drift gate, added without regenerating apps/web/src/api/client.ts."""
    return {"version": "test"}


@router.get("/ready")
def ready(response: Response) -> dict[str, object]:
    settings = get_settings()
    checks = {
        "mongodb": check_mongo_ready(settings),
        "storage": check_storage_ready(settings),
    }
    all_ready = all(checks.values())
    response.status_code = 200 if all_ready else 503
    return {"status": "ok" if all_ready else "unavailable", "checks": checks}
