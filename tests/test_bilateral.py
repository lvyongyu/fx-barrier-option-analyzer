from datetime import date

import pandas as pd
import pytest

from src.trades.bilateral import calculate_bilateral_touch_probability, format_bilateral_report


def test_bilateral_touch_probability_counts_upper_lower_either_and_both() -> None:
    prices = pd.DataFrame(
        [
            row("2026-01-01", high=1.00, low=1.00, close=1.00),
            row("2026-01-02", high=1.11, low=0.89, close=1.00),
            row("2026-01-03", high=1.02, low=0.95, close=1.00),
            row("2026-01-04", high=1.00, low=0.95, close=1.00),
        ]
    )

    result = calculate_bilateral_touch_probability(
        pair="AUD/USD",
        trade_date=date(2026, 1, 1),
        spot=1.0,
        upper_barrier=1.10,
        lower_barrier=0.90,
        expiry_date=date(2026, 1, 3),
        prices=prices,
    )

    assert result.sample_count == 2
    assert result.upper_touch_count == 1
    assert result.lower_touch_count == 1
    assert result.either_touch_count == 1
    assert result.both_touch_count == 1
    assert result.upper_touch_probability == pytest.approx(50.0)
    assert result.lower_touch_probability == pytest.approx(50.0)
    assert result.either_touch_probability == pytest.approx(50.0)
    assert result.both_touch_probability == pytest.approx(50.0)


def test_format_bilateral_report_explains_non_complementary_events() -> None:
    prices = pd.DataFrame(
        [
            row("2026-01-01", high=1.00, low=1.00, close=1.00),
            row("2026-01-02", high=1.11, low=0.89, close=1.00),
            row("2026-01-03", high=1.00, low=1.00, close=1.00),
        ]
    )
    result = calculate_bilateral_touch_probability(
        pair="AUD/USD",
        trade_date=date(2026, 1, 1),
        spot=1.0,
        upper_barrier=1.10,
        lower_barrier=0.90,
        expiry_date=date(2026, 1, 2),
        prices=prices,
    )

    report = format_bilateral_report(result)

    assert "FX BILATERAL TOUCH REPORT" in report
    assert "Touch upper barrier:" in report
    assert "Touch lower barrier:" in report
    assert "Touch either barrier:" in report
    assert "Touch both barriers:" in report
    assert "Upper and lower touch events are not complements." in report


def test_bilateral_requires_lower_below_spot_and_upper_above_spot() -> None:
    with pytest.raises(ValueError, match="lower_barrier must be below spot"):
        calculate_bilateral_touch_probability(
            pair="AUD/USD",
            trade_date=date(2026, 1, 1),
            spot=1.0,
            upper_barrier=1.10,
            lower_barrier=1.01,
            expiry_date=date(2026, 1, 2),
            prices=pd.DataFrame([row("2026-01-01", high=1.0, low=1.0, close=1.0)]),
        )


def row(day: str, high: float, low: float, close: float) -> dict[str, object]:
    return {
        "date": day,
        "pair": "AUD/USD",
        "open": close,
        "high": high,
        "low": low,
        "close": close,
    }
