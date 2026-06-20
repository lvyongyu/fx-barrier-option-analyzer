from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd

from src.pricing.barrier_engine import calculate_days_to_expiry, normalize_prices


@dataclass(frozen=True)
class BilateralTouchResult:
    pair: str
    trade_date: date
    spot: float
    upper_barrier: float
    lower_barrier: float
    expiry_date: date
    days_to_expiry: int
    upper_distance_pct: float
    lower_distance_pct: float
    sample_count: int
    upper_touch_count: int
    lower_touch_count: int
    either_touch_count: int
    both_touch_count: int
    upper_touch_probability: float
    lower_touch_probability: float
    either_touch_probability: float
    both_touch_probability: float


def calculate_bilateral_touch_probability(
    pair: str,
    trade_date: date,
    spot: float,
    upper_barrier: float,
    lower_barrier: float,
    expiry_date: date,
    prices: pd.DataFrame,
) -> BilateralTouchResult:
    if spot <= 0:
        raise ValueError("spot must be greater than zero")
    if lower_barrier <= 0 or upper_barrier <= 0:
        raise ValueError("barriers must be greater than zero")
    if lower_barrier >= spot:
        raise ValueError("lower_barrier must be below spot")
    if upper_barrier <= spot:
        raise ValueError("upper_barrier must be above spot")

    frame = normalize_prices(prices, pair)
    days_to_expiry = calculate_days_to_expiry(trade_date, expiry_date)
    upper_distance = (upper_barrier - spot) / spot
    lower_distance = (lower_barrier - spot) / spot

    sample_count = 0
    upper_count = 0
    lower_count = 0
    either_count = 0
    both_count = 0
    last_available_date = frame["date"].max()

    for _, row in frame.iterrows():
        start_date = row["date"]
        end_date = start_date + timedelta(days=days_to_expiry)
        if last_available_date < end_date:
            continue

        forward_window = frame[(frame["date"] > start_date) & (frame["date"] <= end_date)]
        if forward_window.empty:
            continue

        synthetic_spot = float(row["close"])
        synthetic_upper = synthetic_spot * (1 + upper_distance)
        synthetic_lower = synthetic_spot * (1 + lower_distance)

        upper_hit = bool((forward_window["high"] >= synthetic_upper).any())
        lower_hit = bool((forward_window["low"] <= synthetic_lower).any())
        either_hit = upper_hit or lower_hit
        both_hit = upper_hit and lower_hit

        sample_count += 1
        upper_count += int(upper_hit)
        lower_count += int(lower_hit)
        either_count += int(either_hit)
        both_count += int(both_hit)

    return BilateralTouchResult(
        pair=pair,
        trade_date=trade_date,
        spot=spot,
        upper_barrier=upper_barrier,
        lower_barrier=lower_barrier,
        expiry_date=expiry_date,
        days_to_expiry=days_to_expiry,
        upper_distance_pct=upper_distance * 100,
        lower_distance_pct=lower_distance * 100,
        sample_count=sample_count,
        upper_touch_count=upper_count,
        lower_touch_count=lower_count,
        either_touch_count=either_count,
        both_touch_count=both_count,
        upper_touch_probability=_probability(upper_count, sample_count),
        lower_touch_probability=_probability(lower_count, sample_count),
        either_touch_probability=_probability(either_count, sample_count),
        both_touch_probability=_probability(both_count, sample_count),
    )


def format_bilateral_report(result: BilateralTouchResult) -> str:
    return "\n".join(
        [
            "FX BILATERAL TOUCH REPORT",
            "",
            "QUESTION",
            (
                f"Will {result.pair} touch either {result.upper_barrier:.4f} "
                f"or {result.lower_barrier:.4f} within {result.days_to_expiry} calendar days?"
            ),
            f"Forecast date: {result.trade_date}",
            "",
            "BARRIER SETUP",
            f"Spot: {result.spot:.4f}",
            f"Upper barrier: {result.upper_barrier:.4f} ({result.upper_distance_pct:.2f}%)",
            f"Lower barrier: {result.lower_barrier:.4f} ({result.lower_distance_pct:.2f}%)",
            f"Expiry date: {result.expiry_date}",
            "",
            "PROBABILITY DISTRIBUTION",
            f"Touch upper barrier: {result.upper_touch_probability:.2f}%",
            f"Touch lower barrier: {result.lower_touch_probability:.2f}%",
            f"Touch either barrier: {result.either_touch_probability:.2f}%",
            f"Touch both barriers: {result.both_touch_probability:.2f}%",
            "",
            "HISTORICAL COUNTS",
            f"Samples: {result.sample_count}",
            f"Upper touch count: {result.upper_touch_count}",
            f"Lower touch count: {result.lower_touch_count}",
            f"Either touch count: {result.either_touch_count}",
            f"Both touch count: {result.both_touch_count}",
            "",
            "INTERPRETATION NOTES",
            "- Upper and lower touch events are not complements.",
            "- Both barriers can touch inside the same forecast window.",
            "- Daily OHLC data can identify that both barriers touched, but not the intraday sequence if both occur on the same day.",
            "- This is path-touch probability, not expiry close probability or payoff probability.",
        ]
    )


def _probability(count: int, sample_count: int) -> float:
    return count / sample_count * 100 if sample_count else 0.0
