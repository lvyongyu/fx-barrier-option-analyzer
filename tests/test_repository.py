from datetime import date, timedelta

import pandas as pd

from src.pricing.barrier_engine import Trade, calculate_touch_probability
from src.pricing.feature_engine import build_feature_snapshot
from src.storage.repository import (
    init_db,
    load_market_prices,
    save_analysis_result,
    save_feature_snapshot,
    save_trade,
    save_volatility_adjustment,
    table_count,
    upsert_market_prices,
)
from src.pricing.volatility_adjustment import calculate_volatility_adjusted_probability


def test_repository_persists_research_objects() -> None:
    prices = make_prices()
    trade = Trade(
        pair="AUD/USD",
        trade_date=date(2026, 3, 31),
        spot=1.30,
        strike=1.32,
        barrier=1.34,
        expiry_date=date(2026, 5, 20),
        client_direction="Importer",
        protected_amount=500_000,
        ratio_amount=1_000_000,
        amount_currency="USD",
    )

    import sqlite3

    with sqlite3.connect(":memory:") as connection:
        connection.row_factory = sqlite3.Row
        init_db(connection)

        assert upsert_market_prices(connection, prices) == len(prices)
        assert upsert_market_prices(connection, prices) == len(prices)
        assert table_count(connection, "market_prices") == len(prices)
        assert len(load_market_prices(connection)) == len(prices)

        result = calculate_touch_probability(trade, prices)
        features = build_feature_snapshot(trade, prices)
        adjustment = calculate_volatility_adjusted_probability(
            trade,
            prices,
            baseline_probability=result.touch_probability,
            current_features=features,
            min_comparable_samples=1,
        )

        trade_id = save_trade(connection, trade)
        feature_id = save_feature_snapshot(connection, features, trade_id=trade_id)
        analysis_id = save_analysis_result(connection, result, trade_id=trade_id)
        adjustment_id = save_volatility_adjustment(connection, adjustment, analysis_result_id=analysis_id)

        assert trade_id == 1
        assert feature_id == 1
        assert analysis_id == 1
        assert adjustment_id == 1
        assert table_count(connection, "trades") == 1
        assert table_count(connection, "feature_snapshots") == 1
        assert table_count(connection, "analysis_results") == 1
        assert table_count(connection, "volatility_adjustments") == 1


def make_prices(days: int = 120) -> pd.DataFrame:
    start = date(2026, 1, 1)
    rows = []
    close = 1.0
    for offset in range(days):
        current = start + timedelta(days=offset)
        change = 0.004 if offset % 2 == 0 else -0.002
        close += change
        rows.append(
            {
                "date": current.isoformat(),
                "pair": "AUD/USD",
                "open": close - change,
                "high": close + 0.01,
                "low": close - 0.01,
                "close": close,
            }
        )
    return pd.DataFrame(rows)
