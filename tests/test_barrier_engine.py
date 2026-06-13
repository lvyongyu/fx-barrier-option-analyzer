from datetime import date

import pandas as pd
import pytest

from src.barrier_engine import (
    Trade,
    calculate_days_to_expiry,
    calculate_distance_pct,
    calculate_touch_probability,
    evaluate_actual_path,
)


def test_up_barrier_hit_uses_daily_high() -> None:
    trade = Trade("AUD/USD", date(2026, 4, 15), 0.65, 0.69, 0.705, date(2026, 4, 20))
    prices = pd.DataFrame(
        [
            row("2026-04-15", high=0.66, low=0.64, close=0.65),
            row("2026-04-16", high=0.706, low=0.65, close=0.70),
            row("2026-04-20", high=0.69, low=0.67, close=0.68),
        ]
    )

    result = evaluate_actual_path(trade, prices)

    assert result.is_applicable is True
    assert result.barrier_hit is True
    assert result.hit_date == date(2026, 4, 16)
    assert result.days_to_hit == 1
    assert result.max_high == pytest.approx(0.706)


def test_down_barrier_hit_uses_daily_low() -> None:
    trade = Trade("AUD/USD", date(2026, 4, 15), 0.65, 0.63, 0.61, date(2026, 4, 20), "down")
    prices = pd.DataFrame(
        [
            row("2026-04-15", high=0.66, low=0.64, close=0.65),
            row("2026-04-18", high=0.63, low=0.609, close=0.61),
            row("2026-04-20", high=0.62, low=0.611, close=0.615),
        ]
    )

    result = evaluate_actual_path(trade, prices)

    assert result.is_applicable is True
    assert result.barrier_hit is True
    assert result.hit_date == date(2026, 4, 18)
    assert result.days_to_hit == 3


def test_touch_after_expiry_does_not_count() -> None:
    trade = Trade("AUD/USD", date(2026, 4, 15), 0.65, 0.69, 0.705, date(2026, 4, 16))
    prices = pd.DataFrame(
        [
            row("2026-04-15", high=0.66, low=0.64, close=0.65),
            row("2026-04-17", high=0.710, low=0.65, close=0.70),
        ]
    )

    result = evaluate_actual_path(trade, prices)

    assert result.is_applicable is True
    assert result.reason is None
    assert result.barrier_hit is False


def test_actual_path_not_applicable_when_data_ends_before_expiry() -> None:
    trade = Trade("AUD/USD", date(2026, 4, 15), 0.65, 0.69, 0.705, date(2026, 4, 20))
    prices = pd.DataFrame(
        [
            row("2026-04-15", high=0.66, low=0.64, close=0.65),
            row("2026-04-17", high=0.710, low=0.65, close=0.70),
        ]
    )

    result = evaluate_actual_path(trade, prices)

    assert result.is_applicable is False
    assert result.reason == "expiry_date is after available market data (2026-04-17)"
    assert result.barrier_hit is False


def test_historical_probability_uses_complete_forward_windows() -> None:
    trade = Trade("AUD/USD", date(2026, 4, 15), 1.0, 1.05, 1.10, date(2026, 4, 17))
    prices = pd.DataFrame(
        [
            row("2020-01-01", high=1.00, low=0.99, close=1.00),
            row("2020-01-02", high=1.11, low=0.99, close=1.00),
            row("2020-01-03", high=1.00, low=0.99, close=1.00),
            row("2020-01-04", high=1.00, low=0.99, close=1.00),
        ]
    )

    result = calculate_touch_probability(trade, prices)

    assert result.days_to_expiry == 2
    assert result.distance_pct == pytest.approx(10.0)
    assert result.sample_count == 2
    assert result.touch_count == 1
    assert result.touch_probability == pytest.approx(50.0)


def test_distance_and_expiry_validation() -> None:
    assert calculate_distance_pct(0.65, 0.705) == pytest.approx(0.08461538)

    with pytest.raises(ValueError):
        calculate_days_to_expiry(date(2026, 4, 15), date(2026, 4, 15))


def row(day: str, high: float, low: float, close: float) -> dict[str, object]:
    return {
        "date": day,
        "pair": "AUD/USD",
        "open": close,
        "high": high,
        "low": low,
        "close": close,
    }
