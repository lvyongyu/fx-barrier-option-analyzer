from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd


@dataclass(frozen=True)
class Trade:
    pair: str
    trade_date: date
    spot: float
    strike: float
    barrier: float
    expiry_date: date
    barrier_direction: str = "up"
    product_type: str = "Ratio Convertible Forward"
    client_direction: str | None = None
    protected_amount: float | None = None
    ratio_amount: float | None = None
    amount_currency: str | None = None
    barrier_level_period: str = "continuous"
    expiry_time_zone: str = "Tokyo"


@dataclass(frozen=True)
class BarrierPathResult:
    is_applicable: bool
    reason: str | None
    barrier_hit: bool
    hit_date: date | None
    max_high: float | None
    min_low: float | None
    days_to_hit: int | None


@dataclass(frozen=True)
class TouchProbabilityResult:
    product_type: str
    client_direction: str | None
    pair: str
    spot: float
    strike: float
    barrier: float
    protected_amount: float | None
    ratio_amount: float | None
    amount_currency: str | None
    barrier_level_period: str
    expiry_time_zone: str
    days_to_expiry: int
    distance_pct: float
    sample_count: int
    touch_count: int
    touch_probability: float
    actual_path: BarrierPathResult


def normalize_direction(direction: str) -> str:
    value = direction.strip().lower()
    if value in {"up", "upper", "up-and-out", "knock-out-up"}:
        return "up"
    if value in {"down", "lower", "down-and-out", "knock-out-down"}:
        return "down"
    raise ValueError("barrier_direction must be 'up' or 'down'")


def calculate_days_to_expiry(trade_date: date, expiry_date: date) -> int:
    days = (expiry_date - trade_date).days
    if days <= 0:
        raise ValueError("expiry_date must be after trade_date")
    return days


def calculate_distance_pct(spot: float, barrier: float) -> float:
    if spot <= 0:
        raise ValueError("spot must be greater than zero")
    if barrier <= 0:
        raise ValueError("barrier must be greater than zero")
    return (barrier - spot) / spot


def normalize_prices(prices: pd.DataFrame, pair: str | None = None) -> pd.DataFrame:
    frame = prices.rename(columns={column: column.strip().lower() for column in prices.columns}).copy()
    required = {"date", "open", "high", "low", "close"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"price data missing columns: {', '.join(sorted(missing))}")

    if pair and "pair" in frame.columns:
        frame = frame[frame["pair"].astype(str).str.upper() == pair.upper()]

    frame["date"] = pd.to_datetime(frame["date"]).dt.date
    for column in ["open", "high", "low", "close"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")

    frame = frame.dropna(subset=["date", "open", "high", "low", "close"])
    frame = frame.sort_values("date").drop_duplicates(subset=["date"], keep="last")
    frame = frame.reset_index(drop=True)
    if frame.empty:
        raise ValueError("price data is empty after normalization")
    return frame


def evaluate_actual_path(trade: Trade, prices: pd.DataFrame) -> BarrierPathResult:
    direction = normalize_direction(trade.barrier_direction)
    frame = normalize_prices(prices, trade.pair)
    first_available_date = frame["date"].min()
    last_available_date = frame["date"].max()

    if trade.trade_date < first_available_date:
        return BarrierPathResult(
            is_applicable=False,
            reason=f"trade_date is before available market data ({first_available_date})",
            barrier_hit=False,
            hit_date=None,
            max_high=None,
            min_low=None,
            days_to_hit=None,
        )

    if trade.expiry_date > last_available_date:
        return BarrierPathResult(
            is_applicable=False,
            reason=f"expiry_date is after available market data ({last_available_date})",
            barrier_hit=False,
            hit_date=None,
            max_high=None,
            min_low=None,
            days_to_hit=None,
        )

    window = frame[(frame["date"] >= trade.trade_date) & (frame["date"] <= trade.expiry_date)]

    if window.empty:
        return BarrierPathResult(
            is_applicable=False,
            reason="no market data inside trade window",
            barrier_hit=False,
            hit_date=None,
            max_high=None,
            min_low=None,
            days_to_hit=None,
        )

    max_high = float(window["high"].max())
    min_low = float(window["low"].min())
    hits = window[window["high"] >= trade.barrier] if direction == "up" else window[window["low"] <= trade.barrier]

    if hits.empty:
        return BarrierPathResult(
            is_applicable=True,
            reason=None,
            barrier_hit=False,
            hit_date=None,
            max_high=max_high,
            min_low=min_low,
            days_to_hit=None,
        )

    hit_date = hits.iloc[0]["date"]
    return BarrierPathResult(
        is_applicable=True,
        reason=None,
        barrier_hit=True,
        hit_date=hit_date,
        max_high=max_high,
        min_low=min_low,
        days_to_hit=(hit_date - trade.trade_date).days,
    )


def calculate_touch_probability(trade: Trade, prices: pd.DataFrame) -> TouchProbabilityResult:
    direction = normalize_direction(trade.barrier_direction)
    days_to_expiry = calculate_days_to_expiry(trade.trade_date, trade.expiry_date)
    distance_pct = calculate_distance_pct(trade.spot, trade.barrier)
    frame = normalize_prices(prices, trade.pair)

    sample_count = 0
    touch_count = 0
    last_available_date = frame["date"].max()

    for _, row in frame.iterrows():
        start_date = row["date"]
        end_date = start_date + timedelta(days=days_to_expiry)
        forward_window = frame[(frame["date"] > start_date) & (frame["date"] <= end_date)]

        if forward_window.empty or last_available_date < end_date:
            continue

        synthetic_barrier = float(row["close"]) * (1 + distance_pct)
        if direction == "up":
            touched = bool((forward_window["high"] >= synthetic_barrier).any())
        else:
            touched = bool((forward_window["low"] <= synthetic_barrier).any())

        sample_count += 1
        touch_count += int(touched)

    probability = touch_count / sample_count * 100 if sample_count else 0.0

    return TouchProbabilityResult(
        product_type=trade.product_type,
        client_direction=trade.client_direction,
        pair=trade.pair,
        spot=trade.spot,
        strike=trade.strike,
        barrier=trade.barrier,
        protected_amount=trade.protected_amount,
        ratio_amount=trade.ratio_amount,
        amount_currency=trade.amount_currency,
        barrier_level_period=trade.barrier_level_period,
        expiry_time_zone=trade.expiry_time_zone,
        days_to_expiry=days_to_expiry,
        distance_pct=distance_pct * 100,
        sample_count=sample_count,
        touch_count=touch_count,
        touch_probability=probability,
        actual_path=evaluate_actual_path(trade, frame),
    )
