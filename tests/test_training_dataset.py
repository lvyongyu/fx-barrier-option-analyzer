from datetime import date, timedelta

import pandas as pd

from src.barrier_engine import Trade
from src.training_dataset import (
    TARGET_COLUMN,
    build_price_only_training_dataset,
    build_price_plus_external_training_dataset,
    external_feature_columns,
    price_only_feature_columns,
    price_plus_external_feature_columns,
)


def test_build_price_only_training_dataset_has_features_and_target() -> None:
    prices = make_prices()
    trade = Trade(
        pair="AUD/USD",
        trade_date=date(2026, 5, 1),
        spot=1.40,
        strike=1.42,
        barrier=1.43,
        expiry_date=date(2026, 5, 21),
    )

    dataset = build_price_only_training_dataset(trade, prices)

    assert not dataset.empty
    assert TARGET_COLUMN in dataset.columns
    assert set(price_only_feature_columns()).issubset(dataset.columns)
    assert dataset[price_only_feature_columns()].notna().all().all()
    assert dataset[TARGET_COLUMN].isin([True, False]).all()
    assert dataset["target_end_date"].max() <= pd.to_datetime(prices["date"]).dt.date.max()


def test_training_dataset_target_marks_forward_barrier_hit() -> None:
    prices = make_prices(days=90, jump_day=70, jump_close=1.20, jump_high=1.30)
    trade = Trade(
        pair="AUD/USD",
        trade_date=date(2026, 3, 2),
        spot=1.00,
        strike=1.01,
        barrier=1.05,
        expiry_date=date(2026, 3, 12),
    )

    dataset = build_price_only_training_dataset(trade, prices, min_lookback_days=60)
    first = dataset.iloc[0]

    assert first["target_start_date"] == date(2026, 3, 2)
    assert first["target_end_date"] == date(2026, 3, 12)
    assert bool(first[TARGET_COLUMN]) is True


def test_training_dataset_features_do_not_use_future_prices() -> None:
    prices = make_prices(days=100)
    trade = Trade(
        pair="AUD/USD",
        trade_date=date(2026, 3, 2),
        spot=1.00,
        strike=1.01,
        barrier=1.05,
        expiry_date=date(2026, 3, 12),
    )

    clean = build_price_only_training_dataset(trade, prices, min_lookback_days=60)

    shocked = prices.copy()
    shocked.loc[pd.to_datetime(shocked["date"]).dt.date > date(2026, 3, 2), "close"] = 99.0
    shocked.loc[pd.to_datetime(shocked["date"]).dt.date > date(2026, 3, 2), "high"] = 100.0
    shocked.loc[pd.to_datetime(shocked["date"]).dt.date > date(2026, 3, 2), "low"] = 98.0
    changed = build_price_only_training_dataset(trade, shocked, min_lookback_days=60)

    feature_columns = price_only_feature_columns()
    clean_first = clean[clean["target_start_date"] == date(2026, 3, 2)].iloc[0]
    changed_first = changed[changed["target_start_date"] == date(2026, 3, 2)].iloc[0]

    for column in feature_columns:
        assert changed_first[column] == clean_first[column]


def test_price_plus_external_training_dataset_has_external_features() -> None:
    prices = make_prices(days=140)
    dxy = make_market_series(days=140, start_close=100.0)
    vix = make_market_series(days=140, start_close=15.0)
    trade = Trade(
        pair="AUD/USD",
        trade_date=date(2026, 3, 2),
        spot=1.00,
        strike=1.01,
        barrier=1.05,
        expiry_date=date(2026, 3, 12),
    )

    dataset = build_price_plus_external_training_dataset(
        trade,
        prices,
        dxy,
        vix,
        min_lookback_days=60,
    )

    assert not dataset.empty
    assert set(price_plus_external_feature_columns()).issubset(dataset.columns)
    assert dataset[external_feature_columns()].notna().all().all()
    assert dataset["external_as_of_date"].le(dataset["target_start_date"]).all()


def test_external_training_features_do_not_use_future_external_data() -> None:
    prices = make_prices(days=140)
    dxy = make_market_series(days=140, start_close=100.0)
    vix = make_market_series(days=140, start_close=15.0)
    trade = Trade(
        pair="AUD/USD",
        trade_date=date(2026, 3, 2),
        spot=1.00,
        strike=1.01,
        barrier=1.05,
        expiry_date=date(2026, 3, 12),
    )

    clean = build_price_plus_external_training_dataset(
        trade,
        prices,
        dxy,
        vix,
        min_lookback_days=60,
    )

    shocked_dxy = dxy.copy()
    shocked_vix = vix.copy()
    shocked_dxy.loc[pd.to_datetime(shocked_dxy["date"]).dt.date > date(2026, 3, 2), "close"] = 500.0
    shocked_vix.loc[pd.to_datetime(shocked_vix["date"]).dt.date > date(2026, 3, 2), "close"] = 80.0
    changed = build_price_plus_external_training_dataset(
        trade,
        prices,
        shocked_dxy,
        shocked_vix,
        min_lookback_days=60,
    )

    clean_first = clean[clean["target_start_date"] == date(2026, 3, 2)].iloc[0]
    changed_first = changed[changed["target_start_date"] == date(2026, 3, 2)].iloc[0]

    for column in external_feature_columns():
        assert changed_first[column] == clean_first[column]


def make_prices(days: int = 120, jump_day: int | None = None, jump_close: float = 1.0, jump_high: float = 1.0) -> pd.DataFrame:
    start = date(2026, 1, 1)
    rows = []
    close = 1.0
    for offset in range(days):
        current = start + timedelta(days=offset)
        close += 0.001 if offset % 2 == 0 else -0.0005
        high = close + 0.003
        low = close - 0.003
        if jump_day is not None and offset == jump_day:
            close = jump_close
            high = jump_high
            low = min(low, close - 0.01)
        rows.append(
            {
                "date": current.isoformat(),
                "pair": "AUD/USD",
                "open": close,
                "high": high,
                "low": low,
                "close": close,
            }
        )
    return pd.DataFrame(rows)


def make_market_series(days: int = 120, start_close: float = 100.0) -> pd.DataFrame:
    start = date(2026, 1, 1)
    rows = []
    close = start_close
    for offset in range(days):
        current = start + timedelta(days=offset)
        close += 0.2 if offset % 3 == 0 else -0.05
        rows.append({"date": current.isoformat(), "close": close})
    return pd.DataFrame(rows)
