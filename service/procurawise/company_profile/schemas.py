from datetime import datetime

from pydantic import field_validator

from procurawise.shared.api_models import APIModel


class CompanyProfileResponse(APIModel):
    legal_name: str
    tax_id: str
    address: str
    industry: str
    website_url: str
    updated_at: datetime


class UpdateCompanyProfileRequest(APIModel):
    """Full-replace shape (a settings form always sends its entire current
    state) - no partial-update semantics, so there is no separate meaning
    for "field omitted" vs "field cleared". website_url may be blank (not
    every tenant has filled it in yet); when non-blank it must be an
    http(s) URL, since a future research feature will eventually fetch it
    (UAT-03, backlog.md) and must never be handed an arbitrary scheme."""

    legal_name: str
    tax_id: str
    address: str
    industry: str
    website_url: str

    @field_validator("website_url")
    @classmethod
    def _validate_website_url(cls, value: str) -> str:
        stripped = value.strip()
        if stripped and not (stripped.startswith("http://") or stripped.startswith("https://")):
            raise ValueError("website_url debe comenzar con http:// o https://")
        return stripped
