from datetime import date
from decimal import Decimal

from procurawise.tco.models import CostItem, FrozenFxRate
from procurawise.tco.service import TcoService


def _item(**overrides) -> CostItem:  # noqa: ANN003
    defaults = {
        "concept": "Concepto",
        "category": "recurring",
        "description": None,
        "billing_unit": "usuario",
        "quantity": Decimal("1"),
        "unit_price": Decimal("100"),
        "currency": "MXN",
        "frequency_per_year": Decimal("1"),
        "tax_pct": Decimal("0"),
        "discount_pct": Decimal("0"),
        "year_start": 1,
        "year_end": 1,
        "annual_increment_pct": Decimal("0"),
        "mandatory": True,
        "cost_type": "recurring",
        "notes": None,
    }
    defaults.update(overrides)
    return CostItem.create(**defaults)


def test_one_time_item_single_year() -> None:
    item = _item(category="initial", cost_type="one_time", unit_price=Decimal("1000"))
    result = TcoService().calculate([item], [], "MXN", horizon_years=1)

    assert result.by_year == {1: Decimal("1000.00")}
    assert result.by_year_with_tax == {1: Decimal("1000.00")}
    assert result.by_category == {"initial": Decimal("1000.00")}
    assert result.grand_total == Decimal("1000.00")
    assert result.grand_total_with_tax == Decimal("1000.00")


def test_recurring_item_compounds_annual_increment_across_years() -> None:
    item = _item(
        unit_price=Decimal("100"),
        year_start=1,
        year_end=3,
        annual_increment_pct=Decimal("10"),
    )
    result = TcoService().calculate([item], [], "MXN", horizon_years=3)

    assert result.by_year == {
        1: Decimal("100.00"),
        2: Decimal("110.00"),
        3: Decimal("121.00"),
    }
    assert result.grand_total == Decimal("331.00")


def test_variable_item_uses_the_same_formula_as_other_types() -> None:
    item = _item(
        category="variable_extraordinary",
        cost_type="variable",
        quantity=Decimal("2"),
        unit_price=Decimal("500"),
        year_start=2,
        year_end=2,
    )
    result = TcoService().calculate([item], [], "MXN", horizon_years=3)

    assert result.by_year == {2: Decimal("1000.00")}
    assert result.by_category == {"variable_extraordinary": Decimal("1000.00")}


def test_item_year_end_beyond_horizon_is_truncated() -> None:
    item = _item(unit_price=Decimal("10"), year_start=1, year_end=5)
    result = TcoService().calculate([item], [], "MXN", horizon_years=3)

    assert set(result.by_year) == {1, 2, 3}
    assert result.grand_total == Decimal("30.00")


def test_discount_reduces_net_amount() -> None:
    item = _item(unit_price=Decimal("1000"), discount_pct=Decimal("10"))
    result = TcoService().calculate([item], [], "MXN", horizon_years=1)

    assert result.by_year[1] == Decimal("900.00")


def test_tax_is_kept_separate_from_the_base_total() -> None:
    item = _item(unit_price=Decimal("1000"), tax_pct=Decimal("16"))
    result = TcoService().calculate([item], [], "MXN", horizon_years=1)

    assert result.by_year[1] == Decimal("1000.00")
    assert result.by_year_with_tax[1] == Decimal("1160.00")
    assert result.grand_total == Decimal("1000.00")
    assert result.grand_total_with_tax == Decimal("1160.00")


def test_currency_conversion_uses_the_frozen_rate_passed_in() -> None:
    item = _item(unit_price=Decimal("100"), currency="USD")
    frozen_rate = FrozenFxRate(
        from_currency="USD",
        to_currency="MXN",
        rate=Decimal("18.50"),
        effective_date=date(2026, 8, 1),
        source="manual",
    )
    result = TcoService().calculate([item], [frozen_rate], "MXN", horizon_years=1)

    assert result.by_year[1] == Decimal("1850.00")
    assert result.fx_rates_used == [frozen_rate]


def test_frequency_per_year_multiplies_the_annual_amount() -> None:
    item = _item(unit_price=Decimal("50"), frequency_per_year=Decimal("12"))
    result = TcoService().calculate([item], [], "MXN", horizon_years=1)

    assert result.by_year[1] == Decimal("600.00")


def test_multiple_cost_items_aggregate_by_year_and_category() -> None:
    initial = _item(
        category="initial", cost_type="one_time", unit_price=Decimal("5000"), year_end=1
    )
    recurring = _item(
        category="recurring",
        unit_price=Decimal("100"),
        year_start=1,
        year_end=2,
    )
    result = TcoService().calculate([initial, recurring], [], "MXN", horizon_years=2)

    assert result.by_year == {1: Decimal("5100.00"), 2: Decimal("100.00")}
    assert result.by_category == {
        "initial": Decimal("5000.00"),
        "recurring": Decimal("200.00"),
    }
    assert result.grand_total == Decimal("5200.00")


def test_final_totals_are_rounded_half_up_to_two_decimals() -> None:
    item = _item(unit_price=Decimal("33.335"))
    result = TcoService().calculate([item], [], "MXN", horizon_years=1)

    assert result.by_year[1] == Decimal("33.34")
