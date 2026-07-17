from fastapi import FastAPI

from procurawise.shared.config import get_settings

app = FastAPI(title="ProcuraWise API")


@app.get("/health")
def health() -> dict[str, str]:
    settings = get_settings()
    return {"status": "ok", "environment": settings.environment}
