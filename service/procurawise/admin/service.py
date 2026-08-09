import base64
import json
from datetime import datetime

from procurawise.admin.models import PlatformAdminAccount
from procurawise.admin.repository import PlatformAdminAccountRepository
from procurawise.audit.service import AuditEventService
from procurawise.billing.models import Purchase
from procurawise.billing.repository import PurchaseRepository
from procurawise.evaluations.models import Evaluation
from procurawise.evaluations.repository import EvaluationRepository
from procurawise.identity.passwords import verify_password
from procurawise.shared.context import ActorContext


class InvalidAdminCredentialsError(Exception):
    """email/password did not resolve to a real, matching PlatformAdminAccount."""


class InvalidAdminCursorError(Exception):
    """The `cursor` query param is not a value this endpoint produced."""


def _encode_cursor(created_at: datetime, evaluation_id: str) -> str:
    payload = json.dumps([created_at.isoformat(), evaluation_id]).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii")


def _decode_cursor(cursor: str) -> tuple[datetime, str]:
    try:
        payload = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
        data = json.loads(payload)
        if (
            not isinstance(data, list)
            or len(data) != 2
            or not all(isinstance(part, str) for part in data)
        ):
            raise ValueError("malformed cursor payload")
        created_at = datetime.fromisoformat(data[0])
    except Exception as exc:
        raise InvalidAdminCursorError(cursor) from exc
    return created_at, data[1]


def _synthetic_actor_for_audit(admin_id: str, display_name: str, tenant_id: str) -> ActorContext:
    """AuditEvent.create() only reads role/membership_id/user_id/
    vendor_org_id off the actor it's given (see audit/models.py) -
    `tenant_name` is unused here, left empty rather than resolved via an
    extra TenantRepository lookup this cross-tenant read doesn't otherwise
    need. `membership_id` is prefixed so it can never collide with (or be
    mistaken for) a real Membership id, which is always a bare new_id() hex
    string."""
    return ActorContext(
        membership_id=f"platform-admin:{admin_id}",
        user_id=admin_id,
        tenant_id=tenant_id,
        tenant_name="",
        role="platform_admin",
        vendor_org_id=None,
        display_name=display_name,
    )


class AdminAuthService:
    def __init__(self, admins: PlatformAdminAccountRepository) -> None:
        self._admins = admins

    def authenticate(self, email: str, password: str) -> PlatformAdminAccount:
        doc = self._admins.find_by_email(email)
        # Never distinguish "no such email" from "wrong password" - same
        # generic rejection either way, same rationale as buyer /auth/login.
        if doc is None:
            raise InvalidAdminCredentialsError()
        account = PlatformAdminAccount.from_document(doc)
        if not verify_password(password, account.password_hash):
            raise InvalidAdminCredentialsError()
        return account


class AdminEvaluationService:
    """The one concrete `find_across_tenants()` capability built for Fase 9
    Block 4 (per the founder's approved scope: role + minimal audited
    cross-tenant primitive, not the full admin console - that's Fase 25).
    Read-only, always requires a `reason`, always audited per tenant
    touched."""

    def __init__(self, evaluations: EvaluationRepository, audit: AuditEventService) -> None:
        self._evaluations = evaluations
        self._audit = audit

    def list_evaluations_across_tenants(
        self,
        *,
        reason: str,
        limit: int,
        cursor: str | None,
        admin_id: str,
        display_name: str,
    ) -> tuple[list[Evaluation], str | None]:
        decoded_cursor = _decode_cursor(cursor) if cursor else None
        docs = self._evaluations.find_across_tenants(limit=limit, cursor=decoded_cursor)
        page_docs = docs[:limit]
        evaluations = [Evaluation.from_document(doc) for doc in page_docs]

        # One AuditEvent per evaluation actually touched (not batched per
        # tenant): `evaluation_id` must be set for the event to surface
        # through GET /evaluations/{evaluation_id}/audit-events, the only
        # audit-reading surface that exists today (no tenant-wide audit feed
        # until an admin console is built, Fase 25) - a tenant's own
        # evaluation_owner must be able to see, on that evaluation's own
        # trail, that platform_admin viewed it and why.
        for evaluation in evaluations:
            self._audit.record(
                tenant_id=evaluation.tenant_id,
                actor=_synthetic_actor_for_audit(admin_id, display_name, evaluation.tenant_id),
                action="platform_admin_cross_tenant_read",
                resource_type="evaluation",
                resource_id=evaluation.id,
                evaluation_id=evaluation.id,
                metadata={"reason": reason},
            )

        next_cursor = (
            _encode_cursor(evaluations[-1].created_at, evaluations[-1].id)
            if len(docs) > limit
            else None
        )
        return evaluations, next_cursor


class AdminPurchaseService:
    """Fase 25 (billing/admin, ADR 0025, plan Bloqueante #2 Opcion b): the
    one new cross-tenant capability this phase adds, following
    AdminEvaluationService's pattern exactly (same cursor helpers, same
    synthetic-actor audit, same "reason required, one AuditEvent per record
    touched" discipline) - deliberately not a new find_across_tenants()
    twin on a different repository shape, so the two admin read endpoints
    stay structurally identical for a future reader."""

    def __init__(self, purchases: PurchaseRepository, audit: AuditEventService) -> None:
        self._purchases = purchases
        self._audit = audit

    def list_purchases_across_tenants(
        self,
        *,
        reason: str,
        limit: int,
        cursor: str | None,
        admin_id: str,
        display_name: str,
    ) -> tuple[list[Purchase], str | None]:
        decoded_cursor = _decode_cursor(cursor) if cursor else None
        docs = self._purchases.find_across_tenants(limit=limit, cursor=decoded_cursor)
        page_docs = docs[:limit]
        purchases = [Purchase.from_document(doc) for doc in page_docs]

        # Same rationale as AdminEvaluationService above: evaluation_id is
        # set so the read surfaces on that evaluation's own audit trail, not
        # just in a tenant-wide feed that doesn't exist yet.
        for purchase in purchases:
            self._audit.record(
                tenant_id=purchase.tenant_id,
                actor=_synthetic_actor_for_audit(admin_id, display_name, purchase.tenant_id),
                action="platform_admin_cross_tenant_read",
                resource_type="purchase",
                resource_id=purchase.id,
                evaluation_id=purchase.evaluation_id,
                metadata={"reason": reason},
            )

        next_cursor = (
            _encode_cursor(purchases[-1].created_at, purchases[-1].id)
            if len(docs) > limit
            else None
        )
        return purchases, next_cursor
