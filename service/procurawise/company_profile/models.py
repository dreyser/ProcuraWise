from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True)
class CompanyProfile:
    """Grain: one per tenant (`id == tenant_id`, same deterministic-id
    precedent as `billing.models.BillingAccount`). UAT-03 (R4): minimal
    identity only - legal_name/tax_id/address/industry plus website_url,
    the last one deliberately added to let a future, still-unbuilt research
    feature fetch/analyze the tenant's public site for requirement drafting
    (see backlog.md UAT-03). That research feature is out of scope here and,
    per CLAUDE.md S5.1/ADR 0011, must go through ai.research_provider's
    ResearchProvider Protocol and respect FoundryWebSearchProvider's legal
    gate whenever it is eventually built - never a direct fetch of
    website_url from a business module. Created lazily on first read
    (company_profile/service.py), not sembrado in bulk."""

    tenant_id: str
    legal_name: str
    tax_id: str
    address: str
    industry: str
    website_url: str
    created_at: datetime
    updated_at: datetime

    @staticmethod
    def create(tenant_id: str) -> "CompanyProfile":
        now = datetime.now(UTC)
        return CompanyProfile(
            tenant_id=tenant_id,
            legal_name="",
            tax_id="",
            address="",
            industry="",
            website_url="",
            created_at=now,
            updated_at=now,
        )

    def updated(
        self, *, legal_name: str, tax_id: str, address: str, industry: str, website_url: str
    ) -> "CompanyProfile":
        return replace(
            self,
            legal_name=legal_name,
            tax_id=tax_id,
            address=address,
            industry=industry,
            website_url=website_url,
            updated_at=datetime.now(UTC),
        )

    def to_document(self) -> dict[str, Any]:
        return {
            "_id": self.tenant_id,
            "tenant_id": self.tenant_id,
            "legal_name": self.legal_name,
            "tax_id": self.tax_id,
            "address": self.address,
            "industry": self.industry,
            "website_url": self.website_url,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @staticmethod
    def from_document(doc: dict[str, Any]) -> "CompanyProfile":
        return CompanyProfile(
            tenant_id=doc["tenant_id"],
            legal_name=doc.get("legal_name", ""),
            tax_id=doc.get("tax_id", ""),
            address=doc.get("address", ""),
            industry=doc.get("industry", ""),
            website_url=doc.get("website_url", ""),
            created_at=doc["created_at"],
            updated_at=doc["updated_at"],
        )
