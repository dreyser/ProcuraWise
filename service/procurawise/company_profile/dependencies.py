"""UAT-03 (R4) - single composition point for `CompanyProfileService`,
same pattern as `billing.dependencies.build_billing_service`."""

from procurawise.audit.repository import AuditEventRepository
from procurawise.audit.service import AuditEventService
from procurawise.company_profile.repository import CompanyProfileRepository
from procurawise.company_profile.service import CompanyProfileService
from procurawise.shared.config import Settings
from procurawise.shared.mongo import get_database


def build_company_profile_service(settings: Settings) -> CompanyProfileService:
    db = get_database(settings)
    audit = AuditEventService(AuditEventRepository(db), settings)
    return CompanyProfileService(CompanyProfileRepository(db), audit)
