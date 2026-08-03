from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response

from procurawise.admin.router import router as admin_router
from procurawise.ai.router import router as ai_router
from procurawise.api.routers.health import router as health_router
from procurawise.assignments.router import router as assignments_router
from procurawise.audit.router import router as audit_router
from procurawise.documents.router import buyer_documents_router, vendor_documents_router
from procurawise.evaluations.router import router as evaluations_router
from procurawise.identity.auth_router import router as auth_router
from procurawise.identity.router import router as identity_router
from procurawise.identity.vendor_auth_router import vendor_auth_router, vendor_organizations_router
from procurawise.knowledge_templates.router import apply_router as knowledge_template_apply_router
from procurawise.knowledge_templates.router import router as knowledge_templates_router
from procurawise.proposals.router import router as proposals_router
from procurawise.qna.router import buyer_qna_router, vendor_qna_router
from procurawise.scoring.router import router as scoring_router
from procurawise.shared.config import get_settings
from procurawise.shared.logging import configure_logging
from procurawise.shared.request_context import new_correlation_id, set_correlation_id
from procurawise.vendor_portal.agreements_router import router as vendor_portal_agreements_router
from procurawise.vendor_portal.router import router as vendor_portal_router

configure_logging(get_settings())

app = FastAPI(title="ProcuraWise API")


@app.middleware("http")
async def correlation_id_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Minimal request-id support (Fase 8/audit, plan §7 - no middleware
    existed before this). Only used today to correlate AuditEvents emitted
    within the same request; also echoed as a response header for manual
    debugging."""
    correlation_id = new_correlation_id()
    set_correlation_id(correlation_id)
    response = await call_next(request)
    response.headers["X-Correlation-Id"] = correlation_id
    return response


app.include_router(health_router)
app.include_router(auth_router, prefix="/api/v1")
app.include_router(identity_router, prefix="/api/v1")
app.include_router(vendor_organizations_router, prefix="/api/v1")
app.include_router(vendor_auth_router, prefix="/api/v1")
app.include_router(evaluations_router, prefix="/api/v1")
app.include_router(ai_router, prefix="/api/v1")
app.include_router(audit_router, prefix="/api/v1")
app.include_router(proposals_router, prefix="/api/v1")
app.include_router(buyer_documents_router, prefix="/api/v1")
app.include_router(buyer_qna_router, prefix="/api/v1")
app.include_router(scoring_router, prefix="/api/v1")
app.include_router(assignments_router, prefix="/api/v1")
app.include_router(knowledge_templates_router, prefix="/api/v1")
app.include_router(knowledge_template_apply_router, prefix="/api/v1")
app.include_router(vendor_portal_agreements_router, prefix="/api/v1")
app.include_router(vendor_portal_router, prefix="/api/v1")
app.include_router(vendor_documents_router, prefix="/api/v1")
app.include_router(vendor_qna_router, prefix="/api/v1")
app.include_router(admin_router, prefix="/api/v1")
