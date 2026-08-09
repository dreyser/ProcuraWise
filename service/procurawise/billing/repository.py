from datetime import UTC, datetime
from typing import Any

from pymongo.database import Database

from procurawise.shared.tenant_collection import TenantCollection


class PurchaseRepository:
    def __init__(self, db: Database) -> None:
        self._collection = db["purchases"]

    def _scoped(self, tenant_id: str) -> TenantCollection:
        return TenantCollection(self._collection, tenant_id)

    def insert(self, tenant_id: str, document: dict[str, Any]) -> None:
        self._scoped(tenant_id).insert_one(document)

    def find_by_id(self, tenant_id: str, purchase_id: str) -> dict[str, Any] | None:
        return self._scoped(tenant_id).find_one({"_id": purchase_id})

    def find_by_stripe_session_id(self, stripe_checkout_session_id: str) -> dict[str, Any] | None:
        """Deliberately NOT tenant-scoped - the webhook that calls this has
        no tenant claim of its own (it arrives server-to-server, no JWT).
        This is how the webhook handler *learns* the tenant: the returned
        row's own tenant_id becomes the source of truth for the rest of the
        handler, the Stripe payload's metadata.tenant_id is only ever used
        as a cross-check (billing/service.py), never trusted directly."""
        return self._collection.find_one({"stripe_checkout_session_id": stripe_checkout_session_id})

    def find_active_for_evaluation(
        self, tenant_id: str, evaluation_id: str
    ) -> dict[str, Any] | None:
        """Most recent pending/paid Purchase for this (tenant, evaluation) -
        backs the "reuse a pending session, reject a second charge" checkout
        rule (billing/service.py)."""
        return self._scoped(tenant_id).find_one(
            {"evaluation_id": evaluation_id, "status": {"$in": ["pending", "paid"]}},
            sort=[("created_at", -1)],
        )

    def list_for_tenant(
        self, tenant_id: str, *, evaluation_id: str | None = None
    ) -> list[dict[str, Any]]:
        filter_: dict[str, Any] = {}
        if evaluation_id is not None:
            filter_["evaluation_id"] = evaluation_id
        return list(self._scoped(tenant_id).find(filter_).sort("created_at", -1))

    def transition_status(
        self,
        tenant_id: str,
        purchase_id: str,
        from_status: str,
        to_status: str,
        extra_set: dict[str, Any] | None = None,
    ) -> bool:
        """Atomic, status-conditioned transition - same guard pattern as
        ReportRepository/AIExecutionRepository.transition_status: the
        filter's `status` clause is the concurrency control, and doubles as
        a second idempotency layer against a duplicated webhook delivery
        (the billing_webhook_events ledger is the first)."""
        update = dict(extra_set or {})
        update["status"] = to_status
        update.setdefault("updated_at", datetime.now(UTC))
        result = self._scoped(tenant_id).update_one(
            {"_id": purchase_id, "status": from_status},
            {"$set": update},
        )
        return result.matched_count > 0

    def find_across_tenants(
        self, *, limit: int, cursor: tuple[datetime, str] | None
    ) -> list[dict[str, Any]]:
        """The `find_across_tenants()` escape hatch (ADR 0002/architecture.md
        S5, first used by EvaluationRepository, Fase 9) reserved for
        `platform_admin` - deliberately bypasses TenantCollection. Callers
        (procurawise.admin) must always pair this with a mandatory,
        server-recorded reason and an AuditEvent per record touched; nothing
        here enforces that on its own."""
        filter_: dict[str, Any] = {}
        if cursor is not None:
            cursor_created_at, cursor_id = cursor
            filter_["$or"] = [
                {"created_at": {"$lt": cursor_created_at}},
                {"created_at": cursor_created_at, "_id": {"$lt": cursor_id}},
            ]
        return list(
            self._collection.find(filter_).sort([("created_at", -1), ("_id", -1)]).limit(limit + 1)
        )


class BillingAccountRepository:
    def __init__(self, db: Database) -> None:
        self._collection = db["billing_accounts"]

    def _scoped(self, tenant_id: str) -> TenantCollection:
        return TenantCollection(self._collection, tenant_id)

    def insert(self, tenant_id: str, document: dict[str, Any]) -> None:
        self._scoped(tenant_id).insert_one(document)

    def find_by_id(self, tenant_id: str) -> dict[str, Any] | None:
        return self._scoped(tenant_id).find_one({"_id": tenant_id})

    def set_stripe_customer_id(self, tenant_id: str, stripe_customer_id: str) -> bool:
        result = self._scoped(tenant_id).update_one(
            {"_id": tenant_id},
            {"$set": {"stripe_customer_id": stripe_customer_id, "updated_at": datetime.now(UTC)}},
        )
        return result.matched_count > 0


class BillingWebhookEventRepository:
    """Deliberately NOT tenant-scoped, same justification as
    `admin.repository.PlatformAdminAccountRepository` - a Stripe webhook
    arrives server-to-server with no tenant claim at all. `_id` is Stripe's
    own `event_id`, so `insert()` raising `DuplicateKeyError` on a replayed
    event IS the idempotency check (billing/service.py catches it, same
    idiom as Notification's deterministic-id insert)."""

    def __init__(self, db: Database) -> None:
        self._collection = db["billing_webhook_events"]

    def insert(self, document: dict[str, Any]) -> None:
        self._collection.insert_one(document)

    def mark_processed(self, event_id: str, processed_at: datetime) -> None:
        self._collection.update_one({"_id": event_id}, {"$set": {"processed_at": processed_at}})

    def delete(self, event_id: str) -> None:
        """Used only when processing raises unexpectedly after the ledger
        row was already inserted - removes the row so Stripe's retry of the
        same event_id is reprocessed cleanly instead of silently no-oping
        against a row that never actually finished."""
        self._collection.delete_one({"_id": event_id})
