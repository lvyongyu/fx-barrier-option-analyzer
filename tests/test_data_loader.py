from datetime import date

import pandas as pd
import pytest

from src.data_loader import (
    aggregate_intraday_to_daily,
    build_cross_rate_prices,
    normalize_pair_label,
    pair_to_yahoo_ticker,
    resolve_market_date_and_spot,
    splice_intraday_over_daily,
)


def test_normalize_pair_label_accepts_slash_dash_and_compact_forms() -> None:
    assert normalize_pair_label("aud/usd") == "AUD/USD"
    assert normalize_pair_label("aud-usd") == "AUD/USD"
    assert normalize_pair_label("AUDUSD") == "AUD/USD"


def test_pair_to_yahoo_ticker_uses_fx_suffix() -> None:
    assert pair_to_yahoo_ticker("EUR/USD") == "EURUSD=X"
    assert pair_to_yahoo_ticker("USDJPY") == "USDJPY=X"


def test_resolve_market_date_and_spot_uses_latest_when_missing() -> None:
    resolved_date, spot = resolve_market_date_and_spot(make_prices())

    assert resolved_date == date(2026, 6, 13)
    assert spot == 0.7048


def test_resolve_market_date_and_spot_uses_previous_available_date() -> None:
    resolved_date, spot = resolve_market_date_and_spot(
        make_prices(),
        trade_date=date(2026, 6, 12),
    )

    assert resolved_date == date(2026, 6, 11)
    assert spot == 0.7001


def test_resolve_market_date_and_spot_keeps_manual_spot() -> None:
    resolved_date, spot = resolve_market_date_and_spot(
        make_prices(),
        trade_date=date(2026, 6, 12),
        spot=0.6800,
    )

    assert resolved_date == date(2026, 6, 11)
    assert spot == 0.6800


def test_resolve_market_date_and_spot_errors_when_trade_date_is_too_early() -> None:
    with pytest.raises(ValueError, match="no AUD/USD market data"):
        resolve_market_date_and_spot(make_prices(), trade_date=date(2026, 1, 1))


def test_resolve_market_date_and_spot_filters_requested_pair() -> None:
    prices = pd.DataFrame(
        [
            {"date": "2026-06-10", "pair": "AUD/USD", "open": 0.70, "high": 0.71, "low": 0.69, "close": 0.705},
            {"date": "2026-06-10", "pair": "EUR/USD", "open": 1.10, "high": 1.11, "low": 1.09, "close": 1.105},
        ]
    )

    resolved_date, spot = resolve_market_date_and_spot(prices, pair="EUR/USD")

    assert resolved_date == date(2026, 6, 10)
    assert spot == 1.105


def test_build_cross_rate_prices_multiplies_base_usd_by_usd_quote() -> None:
    base_usd = pd.DataFrame(
        [
            {"date": "2026-06-10", "pair": "AUD/USD", "open": 0.70, "high": 0.71, "low": 0.69, "close": 0.705},
        ]
    )
    usd_quote = pd.DataFrame(
        [
            {"date": "2026-06-10", "pair": "USD/CNH", "open": 7.10, "high": 7.20, "low": 7.00, "close": 7.15},
        ]
    )

    cross = build_cross_rate_prices("AUD/CNH", base_usd, usd_quote)

    assert cross.iloc[0]["pair"] == "AUD/CNH"
    assert cross.iloc[0]["open"] == 0.70 * 7.10
    assert cross.iloc[0]["close"] == 0.705 * 7.15


def test_aggregate_intraday_to_daily_takes_true_high_low_per_day() -> None:
    intraday = pd.DataFrame(
        [
            {"datetime": "2026-06-18 22:00", "open": 0.6500, "high": 0.6510, "low": 0.6495, "close": 0.6505},
            {"datetime": "2026-06-18 23:00", "open": 0.6505, "high": 0.6560, "low": 0.6500, "close": 0.6540},
            {"datetime": "2026-06-19 00:00", "open": 0.6540, "high": 0.6545, "low": 0.6470, "close": 0.6480},
            {"datetime": "2026-06-19 01:00", "open": 0.6480, "high": 0.6490, "low": 0.6460, "close": 0.6475},
        ]
    )

    daily = aggregate_intraday_to_daily(intraday, "AUD/USD")

    first, second = daily.iloc[0], daily.iloc[1]
    assert first["date"] == date(2026, 6, 18)
    assert first["open"] == 0.6500  # first bar of the day
    assert first["high"] == 0.6560  # intraday peak, not the close
    assert first["low"] == 0.6495
    assert first["close"] == 0.6540  # last bar of the day
    assert second["date"] == date(2026, 6, 19)
    assert second["low"] == 0.6460  # would-be barrier touch the daily close (0.6475) hides
    assert second["close"] == 0.6475


def test_splice_intraday_over_daily_overrides_overlapping_days() -> None:
    daily = pd.DataFrame(
        [
            {"date": "2026-06-17", "pair": "AUD/USD", "open": 0.66, "high": 0.665, "low": 0.658, "close": 0.66},
            # Stale/unfinished daily bar: its low (0.659) never reaches the barrier.
            {"date": "2026-06-19", "pair": "AUD/USD", "open": 0.66, "high": 0.661, "low": 0.659, "close": 0.66},
        ]
    )
    intraday = pd.DataFrame(
        [
            {"date": "2026-06-19", "pair": "AUD/USD", "open": 0.66, "high": 0.661, "low": 0.6460, "close": 0.6475},
        ]
    )

    spliced = splice_intraday_over_daily(daily, intraday, "AUD/USD")

    assert list(spliced["date"]) == [date(2026, 6, 17), date(2026, 6, 19)]
    untouched = spliced[spliced["date"] == date(2026, 6, 17)].iloc[0]
    assert untouched["low"] == 0.658  # non-overlapping day preserved
    overridden = spliced[spliced["date"] == date(2026, 6, 19)].iloc[0]
    assert overridden["low"] == 0.6460  # intraday low wins over the stale daily bar


def test_splice_intraday_over_daily_falls_back_to_daily_when_intraday_empty() -> None:
    daily = make_prices()
    empty = pd.DataFrame(columns=["date", "pair", "open", "high", "low", "close"])

    spliced = splice_intraday_over_daily(daily, empty, "AUD/USD")

    assert list(spliced["date"]) == [date(2026, 6, 10), date(2026, 6, 11), date(2026, 6, 13)]


def make_prices() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"date": "2026-06-10", "pair": "AUD/USD", "open": 0.701, "high": 0.703, "low": 0.699, "close": 0.702},
            {"date": "2026-06-11", "pair": "AUD/USD", "open": 0.700, "high": 0.702, "low": 0.698, "close": 0.7001},
            {"date": "2026-06-13", "pair": "AUD/USD", "open": 0.7048, "high": 0.7048, "low": 0.7048, "close": 0.7048},
        ]
    )
