from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from math import sqrt

import pandas as pd

from src.barrier_engine import Trade, calculate_days_to_expiry, calculate_distance_pct, normalize_prices


TRADING_DAYS_PER_YEAR = 252


@dataclass(frozen=True)
class FeatureSnapshot:
    as_of_date: date
    pair: str
    days_to_expiry: int
    distance_pct: float
    realized_vol_20d: float | None
    realized_vol_60d: float | None
    atr_14d: float | None
    trend_20d: float | None
    trend_60d: float | None
    range_position_60d: float | None
    recent_high_distance: float | None
    recent_low_distance: float | None


def build_feature_snapshot(
    trade: Trade,
    prices: pd.DataFrame,
    as_of_date: date | None = None,
) -> FeatureSnapshot:
    frame = normalize_prices(prices, trade.pair)
    effective_as_of = as_of_date or frame["date"].max()
    history = frame[frame["date"] <= effective_as_of].copy()
    if history.empty:
        raise ValueError("no market data available on or before as_of_date")

    actual_as_of = history.iloc[-1]["date"]
    close = history["close"]
    returns = close.pct_change()

    return FeatureSnapshot(
        as_of_date=actual_as_of,
        pair=trade.pair,
        days_to_expiry=calculate_days_to_expiry(actual_as_of, trade.expiry_date),
        distance_pct=calculate_distance_pct(trade.spot, trade.barrier) * 100,
        realized_vol_20d=_realized_vol(returns, 20),
        realized_vol_60d=_realized_vol(returns, 60),
        atr_14d=_atr_pct(history, 14),
        trend_20d=_trend_pct(close, 20),
        trend_60d=_trend_pct(close, 60),
        range_position_60d=_range_position(trade.spot, history, 60),
        recent_high_distance=_recent_high_distance(trade.spot, history, 60),
        recent_low_distance=_recent_low_distance(trade.spot, history, 60),
    )


def build_historical_feature_snapshots(
    trade: Trade,
    prices: pd.DataFrame,
    min_lookback_days: int = 60,
) -> pd.DataFrame:
    frame = normalize_prices(prices, trade.pair)
    rows: list[dict[str, object]] = []
    for index in range(min_lookback_days, len(frame)):
        as_of = frame.iloc[index]["date"]
        synthetic_trade = Trade(
            pair=trade.pair,
            trade_date=as_of,
            spot=float(frame.iloc[index]["close"]),
            strike=trade.strike,
            barrier=float(frame.iloc[index]["close"]) * (1 + calculate_distance_pct(trade.spot, trade.barrier)),
            expiry_date=as_of + (trade.expiry_date - trade.trade_date),
            barrier_direction=trade.barrier_direction,
            product_type=trade.product_type,
            client_direction=trade.client_direction,
            protected_amount=trade.protected_amount,
            ratio_amount=trade.ratio_amount,
            amount_currency=trade.amount_currency,
            barrier_level_period=trade.barrier_level_period,
            expiry_time_zone=trade.expiry_time_zone,
        )
        snapshot = build_feature_snapshot(synthetic_trade, frame, as_of_date=as_of)
        rows.append(snapshot.__dict__)
    return pd.DataFrame(rows)


def _realized_vol(returns: pd.Series, window: int) -> float | None:
    values = returns.dropna().tail(window)
    if len(values) < window:
        return None
    return float(values.std(ddof=1) * sqrt(TRADING_DAYS_PER_YEAR) * 100)


def _atr_pct(history: pd.DataFrame, window: int) -> float | None:
    if len(history) < window + 1:
        return None

    recent = history.tail(window + 1).copy()
    previous_close = recent["close"].shift(1)
    true_range = pd.concat(
        [
            recent["high"] - recent["low"],
            (recent["high"] - previous_close).abs(),
            (recent["low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    values = true_range.dropna().tail(window)
    if len(values) < window:
        return None
    return float(values.mean() / recent.iloc[-1]["close"] * 100)


def _trend_pct(close: pd.Series, window: int) -> float | None:
    if len(close) <= window:
        return None
    start = float(close.iloc[-window - 1])
    end = float(close.iloc[-1])
    if start <= 0:
        return None
    return (end / start - 1) * 100


def _range_position(spot: float, history: pd.DataFrame, window: int) -> float | None:
    recent = history.tail(window)
    if len(recent) < window:
        return None
    low = float(recent["low"].min())
    high = float(recent["high"].max())
    if high == low:
        return None
    return (spot - low) / (high - low) * 100


def _recent_high_distance(spot: float, history: pd.DataFrame, window: int) -> float | None:
    recent = history.tail(window)
    if len(recent) < window or spot <= 0:
        return None
    high = float(recent["high"].max())
    return (high - spot) / spot * 100


def _recent_low_distance(spot: float, history: pd.DataFrame, window: int) -> float | None:
    recent = history.tail(window)
    if len(recent) < window or spot <= 0:
        return None
    low = float(recent["low"].min())
    return (spot - low) / spot * 100
