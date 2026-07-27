from fastapi import FastAPI

from procurawise.api.routers.health import router as health_router
from procurawise.identity.router import router as identity_router
from procurawise.shared.config import get_settings
from procurawise.shared.logging import configure_logging

configure_logging(get_settings())

app = FastAPI(title="ProcuraWise API")
app.include_router(health_router)
app.include_router(identity_router, prefix="/api/v1")
