from datetime import date, timedelta

import pandas as pd
import pytest

from src.pricing.barrier_engine import Trade, calculate_touch_probability
from src.pricing.feature_engine import build_feature_snapshot
from src.pricing.volatility_adjustment import (
    build_labeled_volatility_samples,
    calculate_volatility_adjusted_probability,
    percentile_rank,
)


def test_percentile_rank_counts_values_at_or_below_current_value() -> None:
    values = pd.Series([1.0, 2.0, 3.0, 4.0])

    assert percentile_rank(values, 3.0) == pytest.approx(75.0)


def test_volatility_adjustment_uses_bucket_when_samples_are_sufficient() -> None:
    prices = make_regime_prices()
    trade = Trade(
        pair="AUD/USD",
        trade_date=date(2026, 6, 29),
        spot=1.30,
        strike=1.32,
        barrier=1.34,
        expiry_date=date(2026, 7, 19),
    )
    baseline = calculate_touch_probability(trade, prices)
    features = build_feature_snapshot(trade, prices)

    result = calculate_volatility_adjusted_probability(
        trade,
        prices,
        baseline_probability=baseline.touch_probability,
        current_features=features,
        bucket_half_width_percentile=20,
        min_comparable_samples=5,
    )

    assert result.used_fallback is False
    assert result.method == "volatility_bucket"
    assert result.current_vol_percentile is not None
    assert result.comparable_sample_count >= 5
    assert result.volatility_adjusted_probability is not None
    assert 0 <= result.volatility_adjusted_probability <= 100


def test_volatility_adjustment_falls_back_when_comparable_samples_are_too_low() -> None:
    prices = make_regime_prices()
    trade = Trade(
        pair="AUD/USD",
        trade_date=date(2026, 6, 29),
        spot=1.30,
        strike=1.32,
        barrier=1.34,
        expiry_date=date(2026, 7, 19),
    )
    baseline = calculate_touch_probability(trade, prices)

    result = calculate_volatility_adjusted_probability(
        trade,
        prices,
        baseline_probability=baseline.touch_probability,
        bucket_half_width_percentile=1,
        min_comparable_samples=10_000,
    )

    assert result.used_fallback is True
    assert result.method == "historical_baseline_fallback"
    assert result.volatility_adjusted_probability == pytest.approx(baseline.touch_probability)
    assert "need at least" in result.fallback_reason


def test_labeled_volatility_samples_include_labels_and_no_empty_vols() -> None:
    prices = make_regime_prices()
    trade = Trade(
        pair="AUD/USD",
        trade_date=date(2026, 6, 29),
        spot=1.30,
        strike=1.32,
        barrier=1.34,
        expiry_date=date(2026, 7, 19),
    )

    samples = build_labeled_volatility_samples(trade, prices)

    assert not samples.empty
    assert {"as_of_date", "realized_vol_20d", "vol_percentile", "barrier_hit"}.issubset(samples.columns)
    assert samples["realized_vol_20d"].notna().all()
    assert samples["barrier_hit"].isin([True, False]).all()


def make_regime_prices(days: int = 180) -> pd.DataFrame:
    start = date(2026, 1, 1)
    rows = []
    close = 1.0
    for offset in range(days):
        current = start + timedelta(days=offset)
        if offset < 90:
            change = 0.001 if offset % 2 == 0 else -0.0005
            spread = 0.003
        else:
            change = 0.006 if offset % 2 == 0 else -0.004
            spread = 0.012
        close = max(0.5, close + change)
        rows.append(
            {
                "date": current.isoformat(),
                "pair": "AUD/USD",
                "open": close - change,
                "high": close + spread,
                "low": close - spread,
                "close": close,
            }
        )
    return pd.DataFrame(rows)
