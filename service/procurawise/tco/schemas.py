from datetime import date, datetime
from decimal import Decimal

from procurawise.shared.api_models import APIModel
from procurawise.tco.models import Currency


class CreateFxRateRequest(APIModel):
    from_currency: Currency
    to_currency: Currency
    rate: Decimal
    effective_date: date


class FxRateResponse(APIModel):
    id: str
    from_currency: Currency
    to_currency: Currency
    rate: Decimal
    effective_date: date
    source: str
    created_by_admin_id: str
    created_at: datetime


class FxRateListResponse(APIModel):
    items: list[FxRateResponse]


class FrozenFxRateResponse(APIModel):
    from_currency: Currency
    to_currency: Currency
    rate: Decimal
    effective_date: date
    source: str


class TcoResultResponse(APIModel):
    """Fase 19 - the frozen result read back from `ProposalSnapshot.
    tco_result` (buyer-only, post-submit). Never recalculated from a live
    FXRate - see plan §11.2/§14."""

    base_currency: Currency
    horizon_years: int
    by_year: dict[str, Decimal]
    by_year_with_tax: dict[str, Decimal]
    by_category: dict[str, Decimal]
    grand_total: Decimal
    grand_total_with_tax: Decimal
    fx_rates_used: list[FrozenFxRateResponse]
    calculated_at: datetime
