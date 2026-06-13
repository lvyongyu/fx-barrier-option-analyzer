from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.barrier_engine import Trade, calculate_distance_pct, normalize_direction, normalize_prices
from src.feature_engine import FeatureSnapshot, build_feature_snapshot


@dataclass(frozen=True)
class VolatilityAdjustedResult:
    method: str
    current_vol_20d: float | None
    current_vol_percentile: float | None
    bucket_low_percentile: float | None
    bucket_high_percentile: float | None
    comparable_sample_count: int
    comparable_touch_count: int
    volatility_adjusted_probability: float | None
    used_fallback: bool
    fallback_reason: str | None


def calculate_volatility_adjusted_probability(
    trade: Trade,
    prices: pd.DataFrame,
    baseline_probability: float,
    current_features: FeatureSnapshot | None = None,
    bucket_half_width_percentile: float = 10.0,
    min_comparable_samples: int = 30,
) -> VolatilityAdjustedResult:
    frame = normalize_prices(prices, trade.pair)
    features = current_features or build_feature_snapshot(trade, frame)
    if features.realized_vol_20d is None:
        return _fallback(
            baseline_probability,
            "current 20d realized volatility is unavailable",
            current_vol_20d=None,
        )

    samples = build_labeled_volatility_samples(trade, frame)
    if samples.empty:
        return _fallback(
            baseline_probability,
            "no historical volatility-labeled samples available",
            current_vol_20d=features.realized_vol_20d,
        )

    current_percentile = percentile_rank(samples["realized_vol_20d"], features.realized_vol_20d)
    bucket_low = max(0.0, current_percentile - bucket_half_width_percentile)
    bucket_high = min(100.0, current_percentile + bucket_half_width_percentile)
    comparable = samples[
        (samples["vol_percentile"] >= bucket_low) & (samples["vol_percentile"] <= bucket_high)
    ]

    if len(comparable) < min_comparable_samples:
        return VolatilityAdjustedResult(
            method="historical_baseline_fallback",
            current_vol_20d=features.realized_vol_20d,
            current_vol_percentile=current_percentile,
            bucket_low_percentile=bucket_low,
            bucket_high_percentile=bucket_high,
            comparable_sample_count=int(len(comparable)),
            comparable_touch_count=int(comparable["barrier_hit"].sum()) if not comparable.empty else 0,
            volatility_adjusted_probability=baseline_probability,
            used_fallback=True,
            fallback_reason=f"only {len(comparable)} comparable volatility samples; need at least {min_comparable_samples}",
        )

    touch_count = int(comparable["barrier_hit"].sum())
    probability = touch_count / len(comparable) * 100
    return VolatilityAdjustedResult(
        method="volatility_bucket",
        current_vol_20d=features.realized_vol_20d,
        current_vol_percentile=current_percentile,
        bucket_low_percentile=bucket_low,
        bucket_high_percentile=bucket_high,
        comparable_sample_count=int(len(comparable)),
        comparable_touch_count=touch_count,
        volatility_adjusted_probability=probability,
        used_fallback=False,
        fallback_reason=None,
    )


def build_labeled_volatility_samples(
    trade: Trade,
    prices: pd.DataFrame,
    min_lookback_days: int = 20,
) -> pd.DataFrame:
    direction = normalize_direction(trade.barrier_direction)
    frame = normalize_prices(prices, trade.pair)
    distance_pct = calculate_distance_pct(trade.spot, trade.barrier)
    expiry_delta = trade.expiry_date - trade.trade_date
    last_available_date = frame["date"].max()
    rows: list[dict[str, object]] = []

    for index in range(min_lookback_days, len(frame)):
        start = frame.iloc[index]
        start_date = start["date"]
        end_date = start_date + expiry_delta
        if last_available_date < end_date:
            continue

        synthetic_trade = Trade(
            pair=trade.pair,
            trade_date=start_date,
            spot=float(start["close"]),
            strike=trade.strike,
            barrier=float(start["close"]) * (1 + distance_pct),
            expiry_date=end_date,
            barrier_direction=trade.barrier_direction,
            product_type=trade.product_type,
            client_direction=trade.client_direction,
            protected_amount=trade.protected_amount,
            ratio_amount=trade.ratio_amount,
            amount_currency=trade.amount_currency,
            barrier_level_period=trade.barrier_level_period,
            expiry_time_zone=trade.expiry_time_zone,
        )
        features = build_feature_snapshot(synthetic_trade, frame, as_of_date=start_date)
        if features.realized_vol_20d is None:
            continue

        forward_window = frame[(frame["date"] > start_date) & (frame["date"] <= end_date)]
        synthetic_barrier = synthetic_trade.barrier
        if direction == "up":
            barrier_hit = bool((forward_window["high"] >= synthetic_barrier).any())
        else:
            barrier_hit = bool((forward_window["low"] <= synthetic_barrier).any())

        rows.append(
            {
                "as_of_date": start_date,
                "realized_vol_20d": features.realized_vol_20d,
                "barrier_hit": barrier_hit,
            }
        )

    samples = pd.DataFrame(rows)
    if samples.empty:
        return samples
    samples["vol_percentile"] = samples["realized_vol_20d"].rank(pct=True, method="average") * 100
    return samples


def percentile_rank(values: pd.Series, value: float) -> float:
    clean = pd.to_numeric(values, errors="coerce").dropna()
    if clean.empty:
        raise ValueError("cannot calculate percentile rank from empty values")
    return float((clean <= value).mean() * 100)


def _fallback(
    baseline_probability: float,
    reason: str,
    current_vol_20d: float | None,
) -> VolatilityAdjustedResult:
    return VolatilityAdjustedResult(
        method="historical_baseline_fallback",
        current_vol_20d=current_vol_20d,
        current_vol_percentile=None,
        bucket_low_percentile=None,
        bucket_high_percentile=None,
        comparable_sample_count=0,
        comparable_touch_count=0,
        volatility_adjusted_probability=baseline_probability,
        used_fallback=True,
        fallback_reason=reason,
    )
