from datetime import date, timedelta

import pandas as pd
import pytest

from src.barrier_engine import Trade
from src.feature_engine import build_feature_snapshot, build_historical_feature_snapshots


def test_build_feature_snapshot_calculates_price_features() -> None:
    prices = make_prices()
    trade = Trade(
        pair="AUD/USD",
        trade_date=date(2026, 1, 1),
        spot=1.61,
        strike=1.65,
        barrier=1.70,
        expiry_date=date(2026, 6, 1),
    )

    snapshot = build_feature_snapshot(trade, prices, as_of_date=date(2026, 3, 20))

    assert snapshot.as_of_date == date(2026, 3, 20)
    assert snapshot.days_to_expiry == 73
    assert snapshot.distance_pct == pytest.approx(5.590062)
    assert snapshot.realized_vol_20d is not None
    assert snapshot.realized_vol_60d is not None
    assert snapshot.atr_14d is not None
    assert snapshot.trend_20d is not None
    assert snapshot.trend_60d is not None
    assert snapshot.range_position_60d is not None
    assert snapshot.recent_high_distance is not None
    assert snapshot.recent_low_distance is not None


def test_feature_snapshot_does_not_use_future_prices() -> None:
    prices = make_prices()
    trade = Trade(
        pair="AUD/USD",
        trade_date=date(2026, 1, 1),
        spot=1.61,
        strike=1.65,
        barrier=1.70,
        expiry_date=date(2026, 6, 1),
    )

    clean_snapshot = build_feature_snapshot(trade, prices, as_of_date=date(2026, 3, 1))

    shocked = prices.copy()
    shocked.loc[pd.to_datetime(shocked["date"]).dt.date > date(2026, 3, 1), "close"] = 99.0
    shocked.loc[pd.to_datetime(shocked["date"]).dt.date > date(2026, 3, 1), "high"] = 100.0
    shocked.loc[pd.to_datetime(shocked["date"]).dt.date > date(2026, 3, 1), "low"] = 98.0

    shocked_snapshot = build_feature_snapshot(trade, shocked, as_of_date=date(2026, 3, 1))

    assert shocked_snapshot == clean_snapshot


def test_build_historical_feature_snapshots_uses_synthetic_dates() -> None:
    prices = make_prices()
    trade = Trade(
        pair="AUD/USD",
        trade_date=date(2026, 1, 1),
        spot=1.61,
        strike=1.65,
        barrier=1.70,
        expiry_date=date(2026, 1, 31),
    )

    snapshots = build_historical_feature_snapshots(trade, prices, min_lookback_days=60)

    assert not snapshots.empty
    assert snapshots.iloc[0]["as_of_date"] == date(2026, 3, 2)
    assert set(
        [
            "as_of_date",
            "pair",
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
    ).issubset(snapshots.columns)


def make_prices(days: int = 90) -> pd.DataFrame:
    start = date(2026, 1, 1)
    rows = []
    for offset in range(days):
        current = start + timedelta(days=offset)
        close = 1.0 + offset * 0.01
        rows.append(
            {
                "date": current.isoformat(),
                "pair": "AUD/USD",
                "open": close - 0.002,
                "high": close + 0.01,
                "low": close - 0.01,
                "close": close,
            }
        )
    return pd.DataFrame(rows)
