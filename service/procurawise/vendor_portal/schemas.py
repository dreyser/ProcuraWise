from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import Field

from procurawise.evaluations.models import Dimension, Priority, ResponseType
from procurawise.proposals.models import ProposalStatus
from procurawise.shared.api_models import APIModel
from procurawise.tco.models import CostCategory, CostType, Currency


class AnswerWriteRequest(APIModel):
    """`expected_version` is the optimistic-concurrency contract (plan §12):
    the version the vendor last read. A mismatch means someone/something
    changed the proposal concurrently - the server responds 409 rather than
    accepting the write."""

    value: Any
    vendor_comment: str | None = None
    expected_version: int


class SubmitRequest(APIModel):
    expected_version: int


class CostItemWriteRequest(APIModel):
    """Fase 19 (spec §8.2) - free-form vendor-authored cost line, no
    buyer-defined template (plan §6.A9). Numeric/enum bounds enforced here
    via Pydantic; cross-field checks (year_start<=year_end) enforced by
    `proposals.service.validate_cost_item_fields`."""

    concept: str
    category: CostCategory
    description: str | None = None
    billing_unit: str
    quantity: Decimal = Field(gt=0)
    unit_price: Decimal = Field(ge=0)
    currency: Currency
    frequency_per_year: Decimal = Field(gt=0)
    tax_pct: Decimal = Field(ge=0, le=100, default=Decimal(0))
    discount_pct: Decimal = Field(ge=0, le=100, default=Decimal(0))
    year_start: int = Field(ge=1, le=5)
    year_end: int = Field(ge=1, le=5)
    annual_increment_pct: Decimal = Field(ge=-100, default=Decimal(0))
    mandatory: bool = True
    cost_type: CostType
    notes: str | None = None
    expected_version: int


class CostItemUpdateRequest(APIModel):
    concept: str | None = None
    category: CostCategory | None = None
    description: str | None = None
    billing_unit: str | None = None
    quantity: Decimal | None = Field(default=None, gt=0)
    unit_price: Decimal | None = Field(default=None, ge=0)
    currency: Currency | None = None
    frequency_per_year: Decimal | None = Field(default=None, gt=0)
    tax_pct: Decimal | None = Field(default=None, ge=0, le=100)
    discount_pct: Decimal | None = Field(default=None, ge=0, le=100)
    year_start: int | None = Field(default=None, ge=1, le=5)
    year_end: int | None = Field(default=None, ge=1, le=5)
    annual_increment_pct: Decimal | None = Field(default=None, ge=-100)
    mandatory: bool | None = None
    cost_type: CostType | None = None
    notes: str | None = None
    expected_version: int


class CostItemResponse(APIModel):
    id: str
    concept: str
    category: CostCategory
    description: str | None
    billing_unit: str
    quantity: Decimal
    unit_price: Decimal
    currency: Currency
    frequency_per_year: Decimal
    tax_pct: Decimal
    discount_pct: Decimal
    year_start: int
    year_end: int
    annual_increment_pct: Decimal
    mandatory: bool
    cost_type: CostType
    notes: str | None
    created_at: datetime
    updated_at: datetime


class TcoPreviewResponse(APIModel):
    """Fase 19 - bajo-demanda, nunca persistido (plan §6.E78-79); uses the
    FX rate(s) vigente right now, distinct from the frozen result a
    submitted proposal carries."""

    base_currency: Currency
    horizon_years: int
    by_year: dict[str, Decimal]
    by_year_with_tax: dict[str, Decimal]
    by_category: dict[str, Decimal]
    grand_total: Decimal
    grand_total_with_tax: Decimal


class VendorRequirementResponse(APIModel):
    """Deliberately narrower than evaluations.schemas.RequirementResponse:
    no `weight` field - scoring weight is buyer-internal configuration, not
    exposed to the vendor portal (CLAUDE.md: comentarios internos/scoring
    nunca visibles al proveedor)."""

    id: str
    dimension: Dimension
    category: str
    title: str
    description: str
    priority: Priority
    response_type: ResponseType
    required: bool
    buyer_guidance: str | None
    display_order: int
    options: list[str] | None


class VendorAnswerResponse(APIModel):
    requirement_id: str
    value: Any
    vendor_comment: str | None
    updated_at: datetime


class VendorProposalSummaryResponse(APIModel):
    id: str
    evaluation_id: str
    evaluation_name: str
    status: ProposalStatus
    version: int
    created_at: datetime
    updated_at: datetime
    submitted_at: datetime | None


class VendorProposalDetailResponse(APIModel):
    id: str
    evaluation_id: str
    evaluation_name: str
    status: ProposalStatus
    version: int
    requirements: list[VendorRequirementResponse]
    answers: list[VendorAnswerResponse]
    cost_items: list[CostItemResponse]
    created_at: datetime
    updated_at: datetime
    submitted_at: datetime | None
