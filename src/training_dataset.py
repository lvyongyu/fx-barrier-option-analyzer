from __future__ import annotations

from dataclasses import asdict

import pandas as pd

from src.barrier_engine import Trade, calculate_distance_pct, normalize_direction, normalize_prices
from src.feature_engine import build_feature_snapshot


TARGET_COLUMN = "target_barrier_hit"


def build_price_only_training_dataset(
    trade: Trade,
    prices: pd.DataFrame,
    min_lookback_days: int = 60,
) -> pd.DataFrame:
    direction = normalize_direction(trade.barrier_direction)
    frame = normalize_prices(prices, trade.pair)
    distance_pct = calculate_distance_pct(trade.spot, trade.barrier)
    expiry_delta = trade.expiry_date - trade.trade_date
    last_available_date = frame["date"].max()
    rows: list[dict[str, object]] = []

    for index in range(min_lookback_days, len(frame)):
        start = frame.iloc[index]
        as_of_date = start["date"]
        end_date = as_of_date + expiry_delta
        if last_available_date < end_date:
            continue

        spot = float(start["close"])
        synthetic_trade = Trade(
            pair=trade.pair,
            trade_date=as_of_date,
            spot=spot,
            strike=trade.strike,
            barrier=spot * (1 + distance_pct),
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
        snapshot = build_feature_snapshot(synthetic_trade, frame, as_of_date=as_of_date)
        feature_row = asdict(snapshot)
        if _has_missing_model_features(feature_row):
            continue

        forward_window = frame[(frame["date"] > as_of_date) & (frame["date"] <= end_date)]
        if direction == "up":
            target = bool((forward_window["high"] >= synthetic_trade.barrier).any())
        else:
            target = bool((forward_window["low"] <= synthetic_trade.barrier).any())

        rows.append(
            {
                **feature_row,
                "synthetic_spot": spot,
                "synthetic_barrier": synthetic_trade.barrier,
                "target_start_date": as_of_date,
                "target_end_date": end_date,
                TARGET_COLUMN: target,
            }
        )

    return pd.DataFrame(rows)


def price_only_feature_columns() -> list[str]:
    return [
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


def _has_missing_model_features(row: dict[str, object]) -> bool:
    return any(pd.isna(row[column]) for column in price_only_feature_columns())
