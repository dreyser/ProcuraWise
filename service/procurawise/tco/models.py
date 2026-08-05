from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import uuid4

from bson.decimal128 import Decimal128

Currency = Literal["MXN", "USD"]
CostCategory = Literal["initial", "recurring", "variable_extraordinary"]
CostType = Literal["one_time", "recurring", "variable"]

# Fase 21 (ADR 0013): by analogy with ProposalAnswer.status - CostItems are
# freely added/removed by the vendor (unlike answers, which always map 1:1
# to a fixed Requirement), so "removed" is meaningful here in a way it isn't
# for ProposalAnswer. "modified" is also the correct status for every
# Ronda-0-authored item (nothing to inherit from yet).
CostItemVersionStatus = Literal["inherited", "modified", "removed"]

TCO_CURRENCIES: frozenset[Currency] = frozenset({"MXN", "USD"})


def new_id() -> str:
    return uuid4().hex


def decimal_to_bson(value: Decimal) -> Decimal128:
    return Decimal128(value)


def decimal_from_bson(value: Decimal128 | Decimal | int | float) -> Decimal:
    if isinstance(value, Decimal128):
        return value.to_decimal()
    return Decimal(str(value))


@dataclass(frozen=True)
class CostItem:
    """Fase 19 (ADR 0008, spec §8.2): a single vendor-authored cost line,
    embedded in `Proposal.cost_items` - same lifecycle/storage shape as
    `ProposalAnswer` (draft-editable, frozen into `ProposalSnapshot` at
    submit). Free-form: the vendor picks `category`/`concept`, there is no
    buyer-defined cost-concept template (plan §6.A9) - `category` is
    restricted to the three fixed groups from spec §8.1, everything else is
    the vendor's own wording. All monetary/rate fields are `Decimal` -
    `tco` is the first module in this codebase to use `Decimal` for money
    (deliberate deviation from `proposals`' `float` currency answers, see
    plan §9 R1: compounding multi-year math is exactly where float error
    accumulates)."""

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
    # Fase 21 (ADR 0013): version-tracking pair, mirroring ProposalAnswer.
    # "modified" is the correct default for a brand-new item (Ronda 0, or a
    # genuinely new item authored during Ronda 1) - `source_proposal_version`
    # stays None until this exact item is copied forward as "inherited" by
    # ProposalService.reopen().
    status: CostItemVersionStatus = "modified"
    source_proposal_version: int | None = None

    @staticmethod
    def create(
        *,
        concept: str,
        category: CostCategory,
        description: str | None,
        billing_unit: str,
        quantity: Decimal,
        unit_price: Decimal,
        currency: Currency,
        frequency_per_year: Decimal,
        tax_pct: Decimal,
        discount_pct: Decimal,
        year_start: int,
        year_end: int,
        annual_increment_pct: Decimal,
        mandatory: bool,
        cost_type: CostType,
        notes: str | None,
    ) -> "CostItem":
        now = datetime.now(UTC)
        return CostItem(
            id=new_id(),
            concept=concept,
            category=category,
            description=description,
            billing_unit=billing_unit,
            quantity=quantity,
            unit_price=unit_price,
            currency=currency,
            frequency_per_year=frequency_per_year,
            tax_pct=tax_pct,
            discount_pct=discount_pct,
            year_start=year_start,
            year_end=year_end,
            annual_increment_pct=annual_increment_pct,
            mandatory=mandatory,
            cost_type=cost_type,
            notes=notes,
            created_at=now,
            updated_at=now,
        )

    def to_document(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "concept": self.concept,
            "category": self.category,
            "description": self.description,
            "billing_unit": self.billing_unit,
            "quantity": decimal_to_bson(self.quantity),
            "unit_price": decimal_to_bson(self.unit_price),
            "currency": self.currency,
            "frequency_per_year": decimal_to_bson(self.frequency_per_year),
            "tax_pct": decimal_to_bson(self.tax_pct),
            "discount_pct": decimal_to_bson(self.discount_pct),
            "year_start": self.year_start,
            "year_end": self.year_end,
            "annual_increment_pct": decimal_to_bson(self.annual_increment_pct),
            "mandatory": self.mandatory,
            "cost_type": self.cost_type,
            "notes": self.notes,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "status": self.status,
            "source_proposal_version": self.source_proposal_version,
        }

    @staticmethod
    def from_document(doc: dict[str, Any]) -> "CostItem":
        return CostItem(
            id=doc["id"],
            concept=doc["concept"],
            category=doc["category"],
            description=doc.get("description"),
            billing_unit=doc["billing_unit"],
            quantity=decimal_from_bson(doc["quantity"]),
            unit_price=decimal_from_bson(doc["unit_price"]),
            currency=doc["currency"],
            frequency_per_year=decimal_from_bson(doc["frequency_per_year"]),
            tax_pct=decimal_from_bson(doc["tax_pct"]),
            discount_pct=decimal_from_bson(doc["discount_pct"]),
            year_start=doc["year_start"],
            year_end=doc["year_end"],
            annual_increment_pct=decimal_from_bson(doc["annual_increment_pct"]),
            mandatory=doc["mandatory"],
            cost_type=doc["cost_type"],
            notes=doc.get("notes"),
            created_at=doc["created_at"],
            updated_at=doc["updated_at"],
            status=doc.get("status", "modified"),
            source_proposal_version=doc.get("source_proposal_version"),
        )


@dataclass(frozen=True)
class FXRate:
    """Fase 19 (ADR 0008): platform-level, admin-managed exchange rate -
    NOT tenant data, same reasoning as `curated_sources.models.CuratedSource`
    (deliberately not wrapped in `TenantCollection`, see `tco.repository`).
    Create-only in this phase (plan §9 R4): no update/delete endpoint, so a
    rate already frozen into some `ProposalSnapshot.tco_result.fx_rates_used`
    can never be retroactively altered - a corrected rate is a new row with
    a later `effective_date`, never a mutation of an old one."""

    id: str
    from_currency: Currency
    to_currency: Currency
    rate: Decimal
    effective_date: date
    source: Literal["manual"]
    created_by_admin_id: str
    created_at: datetime

    @staticmethod
    def create(
        *,
        from_currency: Currency,
        to_currency: Currency,
        rate: Decimal,
        effective_date: date,
        created_by_admin_id: str,
    ) -> "FXRate":
        return FXRate(
            id=new_id(),
            from_currency=from_currency,
            to_currency=to_currency,
            rate=rate,
            effective_date=effective_date,
            source="manual",
            created_by_admin_id=created_by_admin_id,
            created_at=datetime.now(UTC),
        )

    def to_document(self) -> dict[str, Any]:
        return {
            "_id": self.id,
            "from_currency": self.from_currency,
            "to_currency": self.to_currency,
            "rate": decimal_to_bson(self.rate),
            "effective_date": self.effective_date.isoformat(),
            "source": self.source,
            "created_by_admin_id": self.created_by_admin_id,
            "created_at": self.created_at,
        }

    @staticmethod
    def from_document(doc: dict[str, Any]) -> "FXRate":
        return FXRate(
            id=doc["_id"],
            from_currency=doc["from_currency"],
            to_currency=doc["to_currency"],
            rate=decimal_from_bson(doc["rate"]),
            effective_date=date.fromisoformat(doc["effective_date"]),
            source=doc["source"],
            created_by_admin_id=doc["created_by_admin_id"],
            created_at=doc["created_at"],
        )


@dataclass(frozen=True)
class FrozenFxRate:
    """The subset of an `FXRate` actually used to convert some `CostItem`,
    copied verbatim into `TcoResult.fx_rates_used` at submit time - never a
    live reference to the `fx_rates` collection (plan §11.2: `TcoService`
    never queries `FXRateRepository` itself, so a post-submit `FXRate`
    update structurally cannot reach an already-frozen `TcoResult`)."""

    from_currency: Currency
    to_currency: Currency
    rate: Decimal
    effective_date: date
    source: Literal["manual"]

    def to_document(self) -> dict[str, Any]:
        return {
            "from_currency": self.from_currency,
            "to_currency": self.to_currency,
            "rate": decimal_to_bson(self.rate),
            "effective_date": self.effective_date.isoformat(),
            "source": self.source,
        }

    @staticmethod
    def from_document(doc: dict[str, Any]) -> "FrozenFxRate":
        return FrozenFxRate(
            from_currency=doc["from_currency"],
            to_currency=doc["to_currency"],
            rate=decimal_from_bson(doc["rate"]),
            effective_date=date.fromisoformat(doc["effective_date"]),
            source=doc["source"],
        )


@dataclass(frozen=True)
class TcoResult:
    """Fase 19: the deterministic output of `TcoService.calculate()`, frozen
    into `ProposalSnapshot.tco_result` at submit - never recomputed after
    (plan §11.1/§14). `by_year`/`by_year_with_tax`/`by_category` keys are
    stringified ints/category names (Mongo requires string keys)."""

    base_currency: Currency
    horizon_years: int
    by_year: dict[int, Decimal]
    by_year_with_tax: dict[int, Decimal]
    by_category: dict[str, Decimal]
    grand_total: Decimal
    grand_total_with_tax: Decimal
    fx_rates_used: list[FrozenFxRate]
    calculated_at: datetime

    def to_document(self) -> dict[str, Any]:
        return {
            "base_currency": self.base_currency,
            "horizon_years": self.horizon_years,
            "by_year": {str(year): decimal_to_bson(v) for year, v in self.by_year.items()},
            "by_year_with_tax": {
                str(year): decimal_to_bson(v) for year, v in self.by_year_with_tax.items()
            },
            "by_category": {cat: decimal_to_bson(v) for cat, v in self.by_category.items()},
            "grand_total": decimal_to_bson(self.grand_total),
            "grand_total_with_tax": decimal_to_bson(self.grand_total_with_tax),
            "fx_rates_used": [r.to_document() for r in self.fx_rates_used],
            "calculated_at": self.calculated_at,
        }

    @staticmethod
    def from_document(doc: dict[str, Any]) -> "TcoResult":
        return TcoResult(
            base_currency=doc["base_currency"],
            horizon_years=doc["horizon_years"],
            by_year={int(year): decimal_from_bson(v) for year, v in doc["by_year"].items()},
            by_year_with_tax={
                int(year): decimal_from_bson(v) for year, v in doc["by_year_with_tax"].items()
            },
            by_category={cat: decimal_from_bson(v) for cat, v in doc["by_category"].items()},
            grand_total=decimal_from_bson(doc["grand_total"]),
            grand_total_with_tax=decimal_from_bson(doc["grand_total_with_tax"]),
            fx_rates_used=[FrozenFxRate.from_document(r) for r in doc.get("fx_rates_used", [])],
            calculated_at=doc["calculated_at"],
        )
