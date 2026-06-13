from datetime import date, timedelta

import pandas as pd
import pytest

from src.barrier_engine import Trade
from src.barrier_theory import (
    calculate_gbm_touch_probability,
    distance_in_vol_units,
    evaluate_barrier_theory_model,
    expected_move_pct,
)
from src.feature_engine import build_feature_snapshot
from src.training_dataset import build_price_only_training_dataset


def test_gbm_touch_probability_increases_with_volatility() -> None:
    low_vol = calculate_gbm_touch_probability(
        spot=0.7000,
        barrier=0.6900,
        days_to_expiry=65,
        annualized_vol_pct=6.0,
    )
    high_vol = calculate_gbm_touch_probability(
        spot=0.7000,
        barrier=0.6900,
        days_to_expiry=65,
        annualized_vol_pct=12.0,
    )

    assert low_vol.probability is not None
    assert high_vol.probability is not None
    assert high_vol.probability > low_vol.probability
    assert low_vol.method == "driftless_log_brownian_reflection"


def test_gbm_touch_probability_increases_with_longer_expiry() -> None:
    short_expiry = calculate_gbm_touch_probability(
        spot=0.7000,
        barrier=0.6900,
        days_to_expiry=30,
        annualized_vol_pct=8.0,
    )
    long_expiry = calculate_gbm_touch_probability(
        spot=0.7000,
        barrier=0.6900,
        days_to_expiry=180,
        annualized_vol_pct=8.0,
    )

    assert short_expiry.probability is not None
    assert long_expiry.probability is not None
    assert long_expiry.probability > short_expiry.probability


def test_gbm_touch_probability_is_symmetric_for_same_log_distance() -> None:
    up = calculate_gbm_touch_probability(
        spot=1.0,
        barrier=1.05,
        days_to_expiry=90,
        annualized_vol_pct=10.0,
    )
    down = calculate_gbm_touch_probability(
        spot=1.0,
        barrier=1 / 1.05,
        days_to_expiry=90,
        annualized_vol_pct=10.0,
    )

    assert up.probability == pytest.approx(down.probability)


def test_gbm_touch_probability_returns_hundred_when_spot_is_on_barrier() -> None:
    snapshot = calculate_gbm_touch_probability(
        spot=0.7000,
        barrier=0.7000,
        days_to_expiry=90,
        annualized_vol_pct=8.0,
    )

    assert snapshot.probability == 100.0
    assert snapshot.distance_in_vol_units == 0.0
    assert snapshot.barrier_z_score == 0.0


def test_gbm_touch_probability_falls_back_for_missing_volatility() -> None:
    snapshot = calculate_gbm_touch_probability(
        spot=0.7000,
        barrier=0.6900,
        days_to_expiry=90,
        annualized_vol_pct=None,
    )

    assert snapshot.probability is None
    assert snapshot.fallback_reason == "annualized volatility is missing"


def test_expected_move_and_distance_in_vol_units() -> None:
    assert expected_move_pct(annualized_vol_pct=10.0, days_to_expiry=63) == pytest.approx(5.0)
    assert distance_in_vol_units(
        spot=1.0,
        barrier=1.05,
        annualized_vol_pct=10.0,
        days_to_expiry=63,
    ) == pytest.approx(1.0)


def test_evaluate_barrier_theory_model_returns_probability_and_metrics() -> None:
    prices = make_prices()
    trade = Trade(
        pair="AUD/USD",
        trade_date=date(2026, 6, 1),
        spot=1.08,
        strike=1.08,
        barrier=1.04,
        expiry_date=date(2026, 8, 30),
        barrier_direction="down",
    )
    dataset = build_price_only_training_dataset(trade, prices, min_lookback_days=60)
    features = build_feature_snapshot(trade, prices, as_of_date=trade.trade_date).__dict__

    evaluation = evaluate_barrier_theory_model(dataset, features, train_fraction=0.7)

    assert evaluation.used_fallback is False
    assert evaluation.current_snapshot.probability is not None
    assert 0 <= evaluation.current_snapshot.probability <= 100
    assert evaluation.gbm_brier_score is not None
    assert evaluation.baseline_brier_score is not None
    assert evaluation.train_rows > 0
    assert evaluation.test_rows > 0
    assert sum(bucket.sample_count for bucket in evaluation.calibration_buckets) == evaluation.test_rows


def make_prices(days: int = 260) -> pd.DataFrame:
    start = date(2026, 1, 1)
    rows = []
    close = 1.0
    for offset in range(days):
        current = start + timedelta(days=offset)
        regime = (offset // 40) % 2
        change = 0.003 if (offset + regime) % 3 == 0 else -0.0015
        close = max(0.5, close + change)
        rows.append(
            {
                "date": current.isoformat(),
                "pair": "AUD/USD",
                "open": close - change,
                "high": close + 0.015,
                "low": close - 0.015,
                "close": close,
            }
        )
    return pd.DataFrame(rows)
