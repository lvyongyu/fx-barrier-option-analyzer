from datetime import date

import pytest

from src.confirmation import (
    barrier_legs_to_trades,
    build_corpay_screenshot_input_example,
    build_uniwell_confirmation_example,
    corpay_trade_input_to_trade,
)


def test_uniwell_confirmation_example_matches_pdf_structure() -> None:
    confirmation = build_uniwell_confirmation_example()

    assert confirmation.customer == "Australia Uniwell Group Pty Ltd"
    assert confirmation.trade_date == date(2026, 4, 15)
    assert confirmation.pair == "AUD/USD"
    assert confirmation.references == ("4096154", "4096155", "4096156", "4096157", "4096158", "4096159")
    assert len(confirmation.expiries) == 3
    assert [expiry.expiration_date for expiry in confirmation.expiries] == [
        date(2026, 8, 28),
        date(2026, 9, 29),
        date(2026, 10, 29),
    ]
    assert sum(len(expiry.legs) for expiry in confirmation.expiries) == 6


def test_barrier_legs_to_trades_creates_one_trade_per_knockout_expiry() -> None:
    confirmation = build_uniwell_confirmation_example()

    trades = barrier_legs_to_trades(
        confirmation,
        spot=0.6500,
        protected_amount=500_000,
        ratio_amount=1_000_000,
        amount_currency="USD",
    )

    assert len(trades) == 3
    assert [trade.expiry_date for trade in trades] == [
        date(2026, 8, 28),
        date(2026, 9, 29),
        date(2026, 10, 29),
    ]
    assert {trade.strike for trade in trades} == {0.6900}
    assert {trade.barrier for trade in trades} == {0.7050}
    assert {trade.barrier_direction for trade in trades} == {"up"}
    assert {trade.barrier_level_period for trade in trades} == {"continuous"}
    assert {trade.protected_amount for trade in trades} == {500_000}
    assert {trade.ratio_amount for trade in trades} == {1_000_000}


def test_barrier_legs_to_trades_requires_barrier_direction() -> None:
    confirmation = build_uniwell_confirmation_example()
    bad_leg = confirmation.expiries[0].legs[1]
    bad_leg = bad_leg.__class__(**{**bad_leg.__dict__, "barrier_direction": None})
    bad_expiry = confirmation.expiries[0].__class__(
        expiration_date=confirmation.expiries[0].expiration_date,
        settlement_date=confirmation.expiries[0].settlement_date,
        legs=(confirmation.expiries[0].legs[0], bad_leg),
    )
    bad_confirmation = confirmation.__class__(
        customer=confirmation.customer,
        trade_date=confirmation.trade_date,
        pair=confirmation.pair,
        base_currency=confirmation.base_currency,
        quote_terms=confirmation.quote_terms,
        references=confirmation.references,
        expiries=(bad_expiry, *confirmation.expiries[1:]),
    )

    with pytest.raises(ValueError, match="missing barrier_direction"):
        barrier_legs_to_trades(bad_confirmation, spot=0.6500)


def test_corpay_screenshot_input_example_maps_to_trade() -> None:
    trade_input = build_corpay_screenshot_input_example()

    assert trade_input.product_type == "Ratio Convertible Forward"
    assert trade_input.client_direction == "Importer"
    assert trade_input.protected_amount == 500_000
    assert trade_input.ratio_amount == 1_000_000
    assert trade_input.amount_currency == "USD"
    assert trade_input.strike == 0.6850
    assert trade_input.barrier == 0.6935
    assert trade_input.barrier_level_period == "continuous"
    assert trade_input.expiry_date == date(2026, 12, 30)

    trade = corpay_trade_input_to_trade(
        trade_input,
        trade_date=date(2026, 4, 15),
        spot=0.6800,
    )

    assert trade.pair == "AUD/USD"
    assert trade.trade_date == date(2026, 4, 15)
    assert trade.spot == 0.6800
    assert trade.strike == 0.6850
    assert trade.barrier == 0.6935
    assert trade.expiry_date == date(2026, 12, 30)
    assert trade.barrier_direction == "up"
    assert trade.expiry_time_zone == "Tokyo"
