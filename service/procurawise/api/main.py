from fastapi import FastAPI

from procurawise.api.routers.health import router as health_router
from procurawise.evaluations.router import router as evaluations_router
from procurawise.identity.router import router as identity_router
from procurawise.proposals.router import router as proposals_router
from procurawise.scoring.router import router as scoring_router
from procurawise.shared.config import get_settings
from procurawise.shared.logging import configure_logging
from procurawise.vendor_portal.router import router as vendor_portal_router

configure_logging(get_settings())

app = FastAPI(title="ProcuraWise API")
app.include_router(health_router)
app.include_router(identity_router, prefix="/api/v1")
app.include_router(evaluations_router, prefix="/api/v1")
app.include_router(proposals_router, prefix="/api/v1")
app.include_router(scoring_router, prefix="/api/v1")
app.include_router(vendor_portal_router, prefix="/api/v1")
