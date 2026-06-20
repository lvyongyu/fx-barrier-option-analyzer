from __future__ import annotations

from dataclasses import dataclass
from math import erf, log, sqrt

import pandas as pd
from sklearn.metrics import brier_score_loss

from src.pricing.price_model import CalibrationBucket, calculate_calibration_buckets
from src.pricing.training_dataset import TARGET_COLUMN


TRADING_DAYS_PER_YEAR = 252


@dataclass(frozen=True)
class BarrierTheorySnapshot:
    probability: float | None
    expected_move_pct: float | None
    distance_in_vol_units: float | None
    barrier_z_score: float | None
    method: str
    fallback_reason: str | None


@dataclass(frozen=True)
class BarrierTheoryEvaluation:
    current_snapshot: BarrierTheorySnapshot
    blended_probability: float | None
    blend_weight: float | None
    train_rows: int
    test_rows: int
    positive_rate_train: float | None
    positive_rate_test: float | None
    baseline_probability: float | None
    gbm_brier_score: float | None
    blended_brier_score: float | None
    baseline_brier_score: float | None
    used_fallback: bool
    fallback_reason: str | None
    calibration_buckets: list[CalibrationBucket]
    blended_calibration_buckets: list[CalibrationBucket]


def calculate_gbm_touch_probability(
    spot: float,
    barrier: float,
    days_to_expiry: int,
    annualized_vol_pct: float | None,
) -> BarrierTheorySnapshot:
    if spot <= 0:
        raise ValueError("spot must be greater than zero")
    if barrier <= 0:
        raise ValueError("barrier must be greater than zero")
    if days_to_expiry <= 0:
        raise ValueError("days_to_expiry must be greater than zero")
    if annualized_vol_pct is None:
        return _fallback("annualized volatility is missing")
    if annualized_vol_pct <= 0:
        return _fallback("annualized volatility must be greater than zero")
    if spot == barrier:
        return BarrierTheorySnapshot(
            probability=100.0,
            expected_move_pct=expected_move_pct(annualized_vol_pct, days_to_expiry),
            distance_in_vol_units=0.0,
            barrier_z_score=0.0,
            method="driftless_log_brownian_reflection",
            fallback_reason=None,
        )

    sigma = annualized_vol_pct / 100
    time_years = days_to_expiry / TRADING_DAYS_PER_YEAR
    log_distance = abs(log(barrier / spot))
    denominator = sigma * sqrt(time_years)
    z_score = log_distance / denominator
    probability = 2 * _normal_cdf(-z_score) * 100

    return BarrierTheorySnapshot(
        probability=max(0.0, min(100.0, probability)),
        expected_move_pct=expected_move_pct(annualized_vol_pct, days_to_expiry),
        distance_in_vol_units=distance_in_vol_units(spot, barrier, annualized_vol_pct, days_to_expiry),
        barrier_z_score=z_score,
        method="driftless_log_brownian_reflection",
        fallback_reason=None,
    )


def calculate_gbm_touch_probability_from_distance(
    distance_pct: float,
    days_to_expiry: int,
    annualized_vol_pct: float | None,
) -> BarrierTheorySnapshot:
    barrier = 1 + distance_pct / 100
    if barrier <= 0:
        return _fallback("distance_pct implies a non-positive barrier")
    return calculate_gbm_touch_probability(
        spot=1.0,
        barrier=barrier,
        days_to_expiry=days_to_expiry,
        annualized_vol_pct=annualized_vol_pct,
    )


def evaluate_barrier_theory_model(
    dataset: pd.DataFrame,
    current_features: dict[str, float | int | None],
    train_fraction: float = 0.7,
    volatility_column: str = "realized_vol_20d",
) -> BarrierTheoryEvaluation:
    current_snapshot = calculate_gbm_touch_probability_from_distance(
        distance_pct=float(current_features["distance_pct"]),
        days_to_expiry=int(current_features["days_to_expiry"]),
        annualized_vol_pct=_optional_float(current_features.get(volatility_column)),
    )
    prepared = _prepare_theory_dataset(dataset, volatility_column=volatility_column)
    if prepared.empty:
        return _evaluation_fallback(current_snapshot, "training dataset has no usable rows")

    split_index = int(len(prepared) * train_fraction)
    if split_index <= 0 or split_index >= len(prepared):
        return _evaluation_fallback(current_snapshot, "training dataset is too small for walk-forward split")

    train = prepared.iloc[:split_index]
    test = prepared.iloc[split_index:].copy()
    baseline_probability = float(train[TARGET_COLUMN].mean())
    train = train.copy()
    train["gbm_probability"] = train.apply(
        lambda row: _row_gbm_probability(row, volatility_column),
        axis=1,
    )
    train = train.dropna(subset=["gbm_probability"])
    test["gbm_probability"] = test.apply(
        lambda row: _row_gbm_probability(row, volatility_column),
        axis=1,
    )
    test = test.dropna(subset=["gbm_probability"])
    if train.empty or test.empty:
        return _evaluation_fallback(current_snapshot, "test dataset has no usable GBM probabilities")

    y_test = test[TARGET_COLUMN].astype(int)
    gbm_probabilities = test["gbm_probability"] / 100
    baseline_probabilities = [baseline_probability] * len(test)
    blend_weight = _fit_blend_weight(
        train[TARGET_COLUMN].astype(int),
        train["gbm_probability"] / 100,
        baseline_probability,
    )
    blended_probabilities = _blend_probabilities(gbm_probabilities, baseline_probability, blend_weight)
    blended_probability = (
        _blend_probability(current_snapshot.probability / 100, baseline_probability, blend_weight) * 100
        if current_snapshot.probability is not None
        else None
    )

    return BarrierTheoryEvaluation(
        current_snapshot=current_snapshot,
        blended_probability=blended_probability,
        blend_weight=blend_weight,
        train_rows=int(len(train)),
        test_rows=int(len(test)),
        positive_rate_train=float(train[TARGET_COLUMN].mean() * 100),
        positive_rate_test=float(test[TARGET_COLUMN].mean() * 100),
        baseline_probability=baseline_probability * 100,
        gbm_brier_score=float(brier_score_loss(y_test, gbm_probabilities)),
        blended_brier_score=float(brier_score_loss(y_test, blended_probabilities)),
        baseline_brier_score=float(brier_score_loss(y_test, baseline_probabilities)),
        used_fallback=current_snapshot.probability is None,
        fallback_reason=current_snapshot.fallback_reason,
        calibration_buckets=calculate_calibration_buckets(gbm_probabilities, y_test),
        blended_calibration_buckets=calculate_calibration_buckets(blended_probabilities, y_test),
    )


def expected_move_pct(annualized_vol_pct: float, days_to_expiry: int) -> float:
    return annualized_vol_pct * sqrt(days_to_expiry / TRADING_DAYS_PER_YEAR)


def distance_in_vol_units(
    spot: float,
    barrier: float,
    annualized_vol_pct: float,
    days_to_expiry: int,
) -> float | None:
    move = expected_move_pct(annualized_vol_pct, days_to_expiry)
    if move <= 0:
        return None
    distance_pct = abs((barrier - spot) / spot * 100)
    return distance_pct / move


def _normal_cdf(value: float) -> float:
    return 0.5 * (1 + erf(value / sqrt(2)))


def _prepare_theory_dataset(dataset: pd.DataFrame, volatility_column: str) -> pd.DataFrame:
    required = ["as_of_date", "days_to_expiry", "distance_pct", volatility_column, TARGET_COLUMN]
    missing = [column for column in required if column not in dataset.columns]
    if missing:
        return pd.DataFrame(columns=required)

    prepared = dataset.copy()
    prepared["as_of_date"] = pd.to_datetime(prepared["as_of_date"])
    prepared = prepared.sort_values("as_of_date").reset_index(drop=True)
    prepared = prepared.dropna(subset=["days_to_expiry", "distance_pct", volatility_column, TARGET_COLUMN])
    return prepared


def _row_gbm_probability(row: pd.Series, volatility_column: str) -> float | None:
    snapshot = calculate_gbm_touch_probability_from_distance(
        distance_pct=float(row["distance_pct"]),
        days_to_expiry=int(row["days_to_expiry"]),
        annualized_vol_pct=float(row[volatility_column]),
    )
    return snapshot.probability


def _fit_blend_weight(
    actual_targets: pd.Series,
    gbm_probabilities: pd.Series,
    baseline_probability: float,
) -> float:
    best_weight = 0.0
    best_score: float | None = None
    for step in range(0, 21):
        weight = step / 20
        blended = _blend_probabilities(gbm_probabilities, baseline_probability, weight)
        score = float(brier_score_loss(actual_targets, blended))
        if best_score is None or score < best_score:
            best_score = score
            best_weight = weight
    return best_weight


def _blend_probabilities(
    gbm_probabilities: pd.Series,
    baseline_probability: float,
    blend_weight: float,
) -> pd.Series:
    return gbm_probabilities.apply(lambda probability: _blend_probability(probability, baseline_probability, blend_weight))


def _blend_probability(gbm_probability: float, baseline_probability: float, blend_weight: float) -> float:
    return blend_weight * gbm_probability + (1 - blend_weight) * baseline_probability


def _optional_float(value: object) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def _fallback(reason: str) -> BarrierTheorySnapshot:
    return BarrierTheorySnapshot(
        probability=None,
        expected_move_pct=None,
        distance_in_vol_units=None,
        barrier_z_score=None,
        method="driftless_log_brownian_reflection",
        fallback_reason=reason,
    )


def _evaluation_fallback(snapshot: BarrierTheorySnapshot, reason: str) -> BarrierTheoryEvaluation:
    return BarrierTheoryEvaluation(
        current_snapshot=snapshot,
        blended_probability=None,
        blend_weight=None,
        train_rows=0,
        test_rows=0,
        positive_rate_train=None,
        positive_rate_test=None,
        baseline_probability=None,
        gbm_brier_score=None,
        blended_brier_score=None,
        baseline_brier_score=None,
        used_fallback=True,
        fallback_reason=reason,
        calibration_buckets=[],
        blended_calibration_buckets=[],
    )
