import threading

import pytest

from procurawise.audit.repository import AuditEventRepository
from procurawise.audit.service import AuditEventService
from procurawise.evaluations.models import MAX_LINKED_VENDORS
from procurawise.evaluations.repository import EvaluationRepository
from procurawise.evaluations.service import EvaluationService
from procurawise.evaluations.snapshot_repository import EvaluationSnapshotRepository
from procurawise.identity.models import Tenant, VendorOrganization
from procurawise.identity.repository import (
    MembershipRepository,
    TenantRepository,
    VendorOrganizationRepository,
)
from procurawise.notifications.dependencies import build_notification_service
from procurawise.proposals.repository import ProposalRepository
from procurawise.shared.context import ActorContext

pytestmark = pytest.mark.docker


def test_vendor_link_reservation_never_exceeds_limit_under_concurrency(
    mongo_test_db, mongo_test_settings
) -> None:
    """count_documents-then-insert would let two concurrent requests both
    read count=5 and both succeed, overshooting the 6-vendor cap (plan §12).
    The atomic $inc-guarded reservation must not allow that: exactly
    MAX_LINKED_VENDORS of 10 concurrent link attempts succeed, the rest fail
    with VendorLimitExceededError, and the stored counter never exceeds the
    cap even though 10 threads raced for it."""
    tenants = TenantRepository(mongo_test_db)
    vendor_orgs = VendorOrganizationRepository(mongo_test_db)
    evaluations = EvaluationRepository(mongo_test_db)
    proposals = ProposalRepository(mongo_test_db)
    memberships = MembershipRepository(mongo_test_db)
    snapshots = EvaluationSnapshotRepository(mongo_test_db)
    audit = AuditEventService(AuditEventRepository(mongo_test_db), mongo_test_settings)
    service = EvaluationService(
        evaluations=evaluations,
        proposals=proposals,
        vendor_orgs=vendor_orgs,
        memberships=memberships,
        snapshots=snapshots,
        audit=audit,
        notifications=build_notification_service(mongo_test_settings),
    )

    tenant = Tenant.create(slug="vs2b-concurrency-tenant", name="Concurrency Tenant")
    tenants.insert(tenant.to_document())
    actor = ActorContext(
        membership_id="membership-x",
        user_id="user-x",
        tenant_id=tenant.id,
        tenant_name=tenant.name,
        role="evaluation_owner",
        vendor_org_id=None,
        display_name="Owner",
    )
    try:
        evaluation = service.create_evaluation(
            tenant.id, "membership-x", "Concurrency RFP", "", actor=actor
        )

        vendor_org_ids = []
        for i in range(10):
            vendor_org = VendorOrganization.create(tenant_id=tenant.id, name=f"Vendor {i}")
            vendor_orgs.insert(tenant.id, vendor_org.to_document())
            vendor_org_ids.append(vendor_org.id)

        results: dict[str, str] = {}

        def link(vendor_org_id: str) -> None:
            try:
                service.link_vendor(tenant.id, evaluation.id, vendor_org_id, actor=actor)
                results[vendor_org_id] = "ok"
            except Exception as exc:  # noqa: BLE001 - recording the outcome, not handling it
                results[vendor_org_id] = type(exc).__name__

        threads = [threading.Thread(target=link, args=(vid,)) for vid in vendor_org_ids]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        successes = [outcome for outcome in results.values() if outcome == "ok"]
        failures = [outcome for outcome in results.values() if outcome != "ok"]
        assert len(successes) == MAX_LINKED_VENDORS
        assert len(failures) == 10 - MAX_LINKED_VENDORS
        assert all(outcome == "VendorLimitExceededError" for outcome in failures)

        final = evaluations.find_by_id(tenant.id, evaluation.id)
        assert final is not None
        assert final["linked_vendor_count"] == MAX_LINKED_VENDORS
        assert len(proposals.find_by_evaluation(tenant.id, evaluation.id)) == MAX_LINKED_VENDORS
    finally:
        mongo_test_db["tenants"].delete_one({"_id": tenant.id})
        mongo_test_db["vendor_organizations"].delete_many({"tenant_id": tenant.id})
        mongo_test_db["evaluations"].delete_many({"tenant_id": tenant.id})
        mongo_test_db["proposals"].delete_many({"tenant_id": tenant.id})
        mongo_test_db["audit_events"].delete_many({"tenant_id": tenant.id})
