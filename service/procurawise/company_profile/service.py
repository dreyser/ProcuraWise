from pymongo.errors import DuplicateKeyError

from procurawise.audit.service import AuditEventService
from procurawise.company_profile.models import CompanyProfile
from procurawise.company_profile.repository import CompanyProfileRepository
from procurawise.shared.context import ActorContext


class CompanyProfileService:
    """UAT-03 (R4): one CompanyProfile per tenant, same lazy-create-on-first-
    read idiom as billing.service.BillingService._get_or_create_billing_
    account - there is no explicit "create" endpoint, only get (which
    materializes an empty row the first time) and update (a full replace)."""

    def __init__(self, repository: CompanyProfileRepository, audit: AuditEventService) -> None:
        self._repository = repository
        self._audit = audit

    def get_profile(self, tenant_id: str) -> CompanyProfile:
        doc = self._repository.find_by_id(tenant_id)
        if doc is not None:
            return CompanyProfile.from_document(doc)
        profile = CompanyProfile.create(tenant_id)
        try:
            self._repository.insert(tenant_id, profile.to_document())
        except DuplicateKeyError:
            # Concurrent first-read race - the other request already created
            # it, same idempotent-insert idiom as billing.BillingAccount.
            doc = self._repository.find_by_id(tenant_id)
            assert doc is not None
            return CompanyProfile.from_document(doc)
        return profile

    def update_profile(
        self,
        tenant_id: str,
        *,
        actor: ActorContext,
        legal_name: str,
        tax_id: str,
        address: str,
        industry: str,
        website_url: str,
    ) -> CompanyProfile:
        current = self.get_profile(tenant_id)
        updated = current.updated(
            legal_name=legal_name,
            tax_id=tax_id,
            address=address,
            industry=industry,
            website_url=website_url,
        )
        self._repository.replace(tenant_id, updated.to_document())
        self._audit.record(
            tenant_id=tenant_id,
            actor=actor,
            action="company_profile_updated",
            resource_type="company_profile",
            resource_id=tenant_id,
        )
        # Re-read rather than return `updated` directly: BSON dates only
        # keep millisecond precision, so the in-memory `updated_at` (full
        # Python microsecond precision) would otherwise differ from what a
        # subsequent GET actually returns - same reason billing.service.
        # BillingService.apply_payment_completed() re-reads after its own
        # transition_status() instead of trusting the pre-persist object.
        persisted = self._repository.find_by_id(tenant_id)
        assert persisted is not None
        return CompanyProfile.from_document(persisted)
