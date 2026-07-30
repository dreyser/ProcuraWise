import threading

import pytest

from procurawise.audit.repository import AuditEventRepository
from procurawise.audit.service import AuditEventService
from procurawise.evaluations.models import Evaluation, Requirement
from procurawise.evaluations.repository import EvaluationRepository
from procurawise.identity.models import Tenant, VendorOrganization
from procurawise.identity.repository import TenantRepository, VendorOrganizationRepository
from procurawise.proposals.exceptions import StaleVersionError
from procurawise.proposals.models import Proposal
from procurawise.proposals.repository import ProposalRepository
from procurawise.proposals.service import ProposalService
from procurawise.shared.context import ActorContext

pytestmark = pytest.mark.docker


def _setup(mongo_test_db, mongo_test_settings):
    tenants = TenantRepository(mongo_test_db)
    vendor_orgs = VendorOrganizationRepository(mongo_test_db)
    evaluations = EvaluationRepository(mongo_test_db)
    proposals = ProposalRepository(mongo_test_db)
    audit = AuditEventService(AuditEventRepository(mongo_test_db), mongo_test_settings)
    service = ProposalService(
        proposals=proposals, evaluations=evaluations, vendor_orgs=vendor_orgs, audit=audit
    )

    tenant = Tenant.create(slug="vs2b-proposal-concurrency", name="Proposal Concurrency Tenant")
    tenants.insert(tenant.to_document())
    vendor_org = VendorOrganization.create(tenant_id=tenant.id, name="Concurrency Vendor")
    vendor_orgs.insert(tenant.id, vendor_org.to_document())

    requirement = Requirement.create(
        dimension="functional",
        category="c",
        title="t",
        description="d",
        priority="important",
        response_type="text",
        weight=40.0,
        required=False,
        display_order=1,
    )
    evaluation = Evaluation.create(
        tenant_id=tenant.id, name="Concurrency RFP", description="", created_by_membership_id="m"
    )
    from dataclasses import replace

    evaluation = replace(
        evaluation, requirements=[requirement], status="collecting_responses", linked_vendor_count=1
    )
    evaluations.insert(tenant.id, evaluation.to_document())

    proposal = Proposal.create(
        tenant_id=tenant.id, evaluation_id=evaluation.id, vendor_org_id=vendor_org.id
    )
    proposals.insert(tenant.id, proposal.to_document())

    return tenant, evaluation, proposal, requirement, service, evaluations, proposals, vendor_orgs


def test_concurrent_answer_edits_with_same_expected_version_only_one_wins(
    mongo_test_db, mongo_test_settings
) -> None:
    """Two threads read Proposal.version=1 and both try to write with
    expected_version=1 - exactly one must succeed; the other must fail with
    StaleVersionError, never silently overwrite the winner (plan §12)."""
    tenant, evaluation, proposal, requirement, service, evaluations, proposals, vendor_orgs = (
        _setup(mongo_test_db, mongo_test_settings)
    )
    try:
        results: dict[str, str] = {}

        def edit(value: str) -> None:
            try:
                service.update_answer(
                    tenant.id, proposal.vendor_org_id, proposal.id, requirement.id, value, None, 1
                )
                results[value] = "ok"
            except Exception as exc:  # noqa: BLE001
                results[value] = type(exc).__name__

        threads = [threading.Thread(target=edit, args=(f"answer-{i}",)) for i in range(5)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        successes = [v for v in results.values() if v == "ok"]
        failures = [v for v in results.values() if v != "ok"]
        assert len(successes) == 1
        assert all(outcome == StaleVersionError.__name__ for outcome in failures)

        final = proposals.find_by_id(tenant.id, proposal.id)
        assert final is not None
        assert final["version"] == 2
    finally:
        mongo_test_db["tenants"].delete_one({"_id": tenant.id})
        mongo_test_db["vendor_organizations"].delete_many({"tenant_id": tenant.id})
        mongo_test_db["evaluations"].delete_many({"tenant_id": tenant.id})
        mongo_test_db["proposals"].delete_many({"tenant_id": tenant.id})
        mongo_test_db["audit_events"].delete_many({"tenant_id": tenant.id})


def test_submit_with_stale_expected_version_does_not_persist_snapshot(
    mongo_test_db, mongo_test_settings
) -> None:
    tenant, evaluation, proposal, requirement, service, evaluations, proposals, vendor_orgs = (
        _setup(mongo_test_db, mongo_test_settings)
    )
    actor = ActorContext(
        membership_id="membership-x",
        user_id="user-x",
        tenant_id=tenant.id,
        tenant_name=tenant.name,
        role="vendor_contact",
        vendor_org_id=proposal.vendor_org_id,
        display_name="Vendor",
    )
    try:
        # A real edit bumps version to 2 - a submit still believing it's at
        # version 1 must be rejected and must not freeze a snapshot.
        service.update_answer(
            tenant.id, proposal.vendor_org_id, proposal.id, requirement.id, "real answer", None, 1
        )

        with pytest.raises(StaleVersionError):
            service.submit(
                tenant.id, proposal.vendor_org_id, proposal.id, 1, "membership-x", actor=actor
            )

        final = proposals.find_by_id(tenant.id, proposal.id)
        assert final is not None
        assert final["status"] == "draft"
        assert final["snapshot"] is None
    finally:
        mongo_test_db["tenants"].delete_one({"_id": tenant.id})
        mongo_test_db["vendor_organizations"].delete_many({"tenant_id": tenant.id})
        mongo_test_db["evaluations"].delete_many({"tenant_id": tenant.id})
        mongo_test_db["proposals"].delete_many({"tenant_id": tenant.id})
        mongo_test_db["audit_events"].delete_many({"tenant_id": tenant.id})
