from procurawise.agreements.models import AgreementType
from procurawise.shared.api_models import APIModel


class AgreementAcceptRequest(APIModel):
    type: AgreementType


class AgreementStatusResponse(APIModel):
    """Includes the legal text itself so the frontend can render the
    acceptance screen from a single call, without a second endpoint for
    static content (Fase 15 planning D4: single platform-wide static text,
    versioned as code constants, no admin-editable content this phase)."""

    nda_accepted: bool
    conflict_of_interest_accepted: bool
    current_nda_version: str
    current_conflict_of_interest_version: str
    nda_text: str
    conflict_of_interest_text: str
