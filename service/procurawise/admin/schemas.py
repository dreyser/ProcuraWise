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
    name: str
    status: str
    created_at: datetime


class AdminEvaluationListResponse(APIModel):
    items: list[AdminEvaluationSummary]
    next_cursor: str | None
