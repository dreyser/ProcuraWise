from datetime import datetime

from procurawise.shared.api_models import APIModel


class AdminLoginRequest(APIModel):
    email: str
    password: str


class AdminTokenResponse(APIModel):
    access_token: str
    expires_in: int
    admin_id: str
    display_name: str


class AdminEvaluationSummary(APIModel):
    id: str
    tenant_id: str
    # Fase 25 (billing/admin, ADR 0025): server-resolved display join, not a
    # new cross-tenant capability - the console would otherwise be a wall of
    # raw tenant UUIDs. Never a new AuditEvent of its own; the tenant_id was
    # already returned (and already audited) before this field existed.
    tenant_name: str
    name: str
    status: str
    created_at: datetime


class AdminEvaluationListResponse(APIModel):
    items: list[AdminEvaluationSummary]
    next_cursor: str | None


class AdminPurchaseSummary(APIModel):
    id: str
    tenant_id: str
    tenant_name: str
    evaluation_id: str
    status: str
    amount_total: int | None
    currency: str | None
    created_at: datetime
    paid_at: datetime | None


class AdminPurchaseListResponse(APIModel):
    items: list[AdminPurchaseSummary]
    next_cursor: str | None
