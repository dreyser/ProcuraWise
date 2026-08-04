import logging
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal

from procurawise.tco.models import CostItem, Currency, FrozenFxRate, FXRate, TcoResult
from procurawise.tco.repository import FXRateRepository

logger = logging.getLogger("procurawise.tco")

_CENTS = Decimal("0.01")


def _round_money(value: Decimal) -> Decimal:
    return value.quantize(_CENTS, rounding=ROUND_HALF_UP)


class FXRateService:
    """Fase 19 (ADR 0008): minimal create/list/resolve for the platform-level
    FXRate table, called only from the platform_admin-only router (CLAUDE.md
    §4). Deliberately does NOT use `AuditEventService` - same reasoning as
    `curated_sources.service.CuratedSourceService`: `AuditEvent` is a
    tenant-scoped trail, and a platform-global admin action has no tenant to
    attach it to. Structured-logged instead."""

    def __init__(self, repository: FXRateRepository) -> None:
        self._repository = repository

    def create(
        self,
        *,
        from_currency: Currency,
        to_currency: Currency,
        rate: Decimal,
        effective_date: date,
        admin_id: str,
    ) -> FXRate:
        fx_rate = FXRate.create(
            from_currency=from_currency,
            to_currency=to_currency,
            rate=rate,
            effective_date=effective_date,
            created_by_admin_id=admin_id,
        )
        self._repository.insert(fx_rate.to_document())
        logger.info(
            "fx_rate_created",
            extra={
                "fx_rate_id": fx_rate.id,
                "from_currency": from_currency,
                "to_currency": to_currency,
                "effective_date": effective_date.isoformat(),
                "admin_id": admin_id,
            },
        )
        return fx_rate

    def list_all(self) -> list[FXRate]:
        return [FXRate.from_document(doc) for doc in self._repository.find_all()]

    def find_latest_for_pair(
        self, from_currency: Currency, to_currency: Currency, as_of_date: date
    ) -> FXRate | None:
        doc = self._repository.find_latest_for_pair(
            from_currency, to_currency, as_of_date.isoformat()
        )
        return FXRate.from_document(doc) if doc is not None else None


class TcoService:
    """Fase 19 (plan §8/§14, formula confirmed by the founder): a pure,
    deterministic calculator - no Mongo/repository access at all. It never
    resolves `FXRate`s itself; the caller (draft preview or `Proposal.
    submit()`) is responsible for resolving `fx_rates_used` first. This
    makes it structurally impossible for a post-submit recalculation to
    reach a currently-live rate instead of the one already frozen into some
    `ProposalSnapshot.tco_result` (the acceptance criterion of this phase).

    Per-item formula (single formula for all three cost_type values - plan
    §8 Pregunta Bloqueante #1, founder-confirmed):

        monto_bruto(Y) = quantity * unit_price * frequency_per_year
                         * (1 + annual_increment_pct/100) ** (Y - year_start)
        monto_neto(Y)  = monto_bruto(Y) * (1 - discount_pct/100)
        impuesto(Y)    = monto_neto(Y) * tax_pct/100

    for each integer year Y in [year_start, min(year_end, horizon_years)].
    "one_time" is simply the year_start == year_end, frequency_per_year == 1
    case - no separate code path."""

    def calculate(
        self,
        cost_items: list[CostItem],
        fx_rates_used: list[FrozenFxRate],
        base_currency: Currency,
        horizon_years: int,
    ) -> TcoResult:
        rate_by_pair = {(r.from_currency, r.to_currency): r.rate for r in fx_rates_used}

        by_year: dict[int, Decimal] = {}
        by_year_with_tax: dict[int, Decimal] = {}
        by_category: dict[str, Decimal] = {}

        for item in cost_items:
            last_year = min(item.year_end, horizon_years)
            for year in range(item.year_start, last_year + 1):
                gross = (
                    item.quantity
                    * item.unit_price
                    * item.frequency_per_year
                    * (1 + item.annual_increment_pct / 100) ** (year - item.year_start)
                )
                net = gross * (1 - item.discount_pct / 100)
                tax = net * (item.tax_pct / 100)

                net_converted = self._convert(net, item.currency, base_currency, rate_by_pair)
                tax_converted = self._convert(tax, item.currency, base_currency, rate_by_pair)

                by_year[year] = by_year.get(year, Decimal(0)) + net_converted
                by_year_with_tax[year] = (
                    by_year_with_tax.get(year, Decimal(0)) + net_converted + tax_converted
                )
                by_category[item.category] = (
                    by_category.get(item.category, Decimal(0)) + net_converted
                )

        grand_total = sum(by_year.values(), Decimal(0))
        grand_total_with_tax = sum(by_year_with_tax.values(), Decimal(0))

        return TcoResult(
            base_currency=base_currency,
            horizon_years=horizon_years,
            by_year={year: _round_money(v) for year, v in by_year.items()},
            by_year_with_tax={year: _round_money(v) for year, v in by_year_with_tax.items()},
            by_category={cat: _round_money(v) for cat, v in by_category.items()},
            grand_total=_round_money(grand_total),
            grand_total_with_tax=_round_money(grand_total_with_tax),
            fx_rates_used=list(fx_rates_used),
            calculated_at=datetime.now(UTC),
        )

    @staticmethod
    def _convert(
        amount: Decimal,
        currency: Currency,
        base_currency: Currency,
        rate_by_pair: dict[tuple[Currency, Currency], Decimal],
    ) -> Decimal:
        if currency == base_currency:
            return amount
        rate = rate_by_pair[(currency, base_currency)]
        return amount * rate
