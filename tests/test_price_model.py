from datetime import date, timedelta

import pandas as pd
from src.pricing.barrier_engine import Trade
from src.pricing.feature_engine import build_feature_snapshot
from src.pricing.price_model import (
    calculate_calibration_buckets,
    evaluate_price_only_model,
    evaluate_price_plus_external_model,
    prepare_model_dataset,
)
from src.pricing.training_dataset import (
    build_price_only_training_dataset,
    external_feature_columns,
    price_only_feature_columns,
    price_plus_external_feature_columns,
)


def test_evaluate_price_only_model_returns_probability_and_metrics() -> None:
    prices = make_model_prices()
    trade = Trade(
        pair="AUD/USD",
        trade_date=date(2026, 9, 17),
        spot=1.05,
        strike=1.06,
        barrier=1.065,
        expiry_date=date(2026, 10, 2),
    )
    dataset = build_price_only_training_dataset(trade, prices, min_lookback_days=60)
    features = build_feature_snapshot(trade, prices)

    evaluation = evaluate_price_only_model(dataset, features.__dict__, train_fraction=0.7)

    assert evaluation.used_fallback is False
    assert evaluation.model_probability is not None
    assert 0 <= evaluation.model_probability <= 100
    assert evaluation.train_rows > 0
    assert evaluation.test_rows > 0
    assert evaluation.model_brier_score is not None
    assert evaluation.baseline_brier_score is not None
    assert evaluation.model_log_loss is not None
    assert evaluation.baseline_log_loss is not None
    assert len(evaluation.calibration_buckets) == 5
    assert sum(bucket.sample_count for bucket in evaluation.calibration_buckets) == evaluation.test_rows


def test_evaluate_price_only_model_falls_back_for_single_class_target() -> None:
    prices = make_model_prices(always_hit=True)
    trade = Trade(
        pair="AUD/USD",
        trade_date=date(2026, 8, 1),
        spot=1.05,
        strike=1.06,
        barrier=1.051,
        expiry_date=date(2026, 8, 16),
    )
    dataset = build_price_only_training_dataset(trade, prices, min_lookback_days=60)

    evaluation = evaluate_price_only_model(dataset, {}, train_fraction=0.7)

    assert evaluation.used_fallback is True
    assert evaluation.model_probability is None
    assert "only one class" in evaluation.fallback_reason


def test_evaluate_price_plus_external_model_uses_external_columns() -> None:
    prices = make_model_prices()
    trade = Trade(
        pair="AUD/USD",
        trade_date=date(2026, 9, 17),
        spot=1.05,
        strike=1.06,
        barrier=1.065,
        expiry_date=date(2026, 10, 2),
    )
    dataset = build_price_only_training_dataset(trade, prices, min_lookback_days=60)
    for index, column in enumerate(external_feature_columns(), start=1):
        dataset[column] = index + (dataset.index % 7) * 0.1
    current_features = build_feature_snapshot(trade, prices).__dict__
    current_features.update({column: 1.0 for column in external_feature_columns()})

    evaluation = evaluate_price_plus_external_model(dataset, current_features, train_fraction=0.7)

    assert evaluation.used_fallback is False
    assert evaluation.model_probability is not None
    assert prepare_model_dataset(dataset, price_plus_external_feature_columns()).shape[0] == len(dataset)


def test_prepare_model_dataset_returns_empty_frame_when_columns_are_missing() -> None:
    dataset = pd.DataFrame({"as_of_date": ["2026-01-01"], "target_barrier_hit": [True]})

    prepared = prepare_model_dataset(dataset)

    assert prepared.empty


def test_evaluate_price_only_model_falls_back_for_empty_dataset() -> None:
    evaluation = evaluate_price_only_model(pd.DataFrame(), {})

    assert evaluation.used_fallback is True
    assert evaluation.fallback_reason == "training dataset has no usable rows"


def test_price_only_feature_columns_are_stable() -> None:
    assert price_only_feature_columns() == [
        "days_to_expiry",
        "distance_pct",
        "realized_vol_20d",
        "realized_vol_60d",
        "atr_14d",
        "trend_20d",
        "trend_60d",
        "range_position_60d",
        "recent_high_distance",
        "recent_low_distance",
    ]


def test_calibration_buckets_report_actual_hit_rate_by_probability_band() -> None:
    buckets = calculate_calibration_buckets(
        predicted_probabilities=[0.05, 0.25, 0.45, 0.85, 0.95],
        actual_targets=[0, 0, 1, 1, 0],
    )

    assert len(buckets) == 5
    assert buckets[0].sample_count == 1
    assert buckets[0].actual_hit_rate == 0.0
    assert buckets[2].sample_count == 1
    assert buckets[2].actual_hit_rate == 100.0
    assert buckets[4].sample_count == 2
    assert buckets[4].actual_hit_rate == 50.0


def make_model_prices(days: int = 260, always_hit: bool = False) -> pd.DataFrame:
    start = date(2026, 1, 1)
    rows = []
    close = 1.0
    for offset in range(days):
        current = start + timedelta(days=offset)
        if always_hit:
            change = 0.001
            high_spread = 0.08
        else:
            regime = (offset // 30) % 2
            change = 0.004 if (offset + regime) % 3 == 0 else -0.002
            high_spread = 0.012 if regime == 0 else 0.035
        close = max(0.5, close + change)
        rows.append(
            {
                "date": current.isoformat(),
                "pair": "AUD/USD",
                "open": close - change,
                "high": close + high_spread,
                "low": close - high_spread,
                "close": close,
            }
        )
    return pd.DataFrame(rows)
