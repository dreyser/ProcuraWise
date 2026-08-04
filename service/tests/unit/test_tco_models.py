from datetime import date, datetime
from decimal import Decimal

from procurawise.tco.models import CostItem, FrozenFxRate, FXRate, TcoResult


def test_cost_item_round_trips_through_document_preserving_decimal_precision() -> None:
    item = CostItem.create(
        concept="Licencias anuales",
        category="recurring",
        description="Suscripcion SaaS",
        billing_unit="usuario",
        quantity=Decimal("25"),
        unit_price=Decimal("199.99"),
        currency="USD",
        frequency_per_year=Decimal("1"),
        tax_pct=Decimal("16"),
        discount_pct=Decimal("5.5"),
        year_start=1,
        year_end=3,
        annual_increment_pct=Decimal("3.25"),
        mandatory=True,
        cost_type="recurring",
        notes="Incluye soporte",
    )
    restored = CostItem.from_document(item.to_document())
    assert restored == item
    assert restored.unit_price == Decimal("199.99")
    assert isinstance(restored.unit_price, Decimal)


def test_cost_item_create_defaults_created_and_updated_at_equal() -> None:
    item = CostItem.create(
        concept="Implementacion",
        category="initial",
        description=None,
        billing_unit="proyecto",
        quantity=Decimal("1"),
        unit_price=Decimal("50000"),
        currency="MXN",
        frequency_per_year=Decimal("1"),
        tax_pct=Decimal("0"),
        discount_pct=Decimal("0"),
        year_start=1,
        year_end=1,
        annual_increment_pct=Decimal("0"),
        mandatory=True,
        cost_type="one_time",
        notes=None,
    )
    assert item.created_at == item.updated_at


def test_fx_rate_round_trips_through_document() -> None:
    rate = FXRate.create(
        from_currency="USD",
        to_currency="MXN",
        rate=Decimal("18.4321"),
        effective_date=date(2026, 8, 1),
        created_by_admin_id="admin-1",
    )
    restored = FXRate.from_document(rate.to_document())
    assert restored == rate
    assert restored.rate == Decimal("18.4321")
    assert restored.source == "manual"


def test_frozen_fx_rate_round_trips_through_document() -> None:
    frozen = FrozenFxRate(
        from_currency="USD",
        to_currency="MXN",
        rate=Decimal("18.5"),
        effective_date=date(2026, 8, 1),
        source="manual",
    )
    restored = FrozenFxRate.from_document(frozen.to_document())
    assert restored == frozen


def test_tco_result_round_trips_through_document_with_year_and_category_keys() -> None:
    result = TcoResult(
        base_currency="MXN",
        horizon_years=2,
        by_year={1: Decimal("100000.50"), 2: Decimal("103000.75")},
        by_year_with_tax={1: Decimal("116000.58"), 2: Decimal("119480.87")},
        by_category={"initial": Decimal("50000"), "recurring": Decimal("153001.25")},
        grand_total=Decimal("203001.25"),
        grand_total_with_tax=Decimal("235481.45"),
        fx_rates_used=[
            FrozenFxRate(
                from_currency="USD",
                to_currency="MXN",
                rate=Decimal("18.5"),
                effective_date=date(2026, 8, 1),
                source="manual",
            )
        ],
        calculated_at=datetime(2026, 8, 4, 12, 0, 0),
    )
    restored = TcoResult.from_document(result.to_document())
    assert restored == result
    assert restored.by_year[1] == Decimal("100000.50")
    assert restored.by_category["recurring"] == Decimal("153001.25")
