from datetime import date

import pandas as pd
import pytest

from src.data_loader import resolve_market_date_and_spot


def test_resolve_market_date_and_spot_uses_latest_when_missing() -> None:
    resolved_date, spot = resolve_market_date_and_spot(make_prices())

    assert resolved_date == date(2026, 6, 13)
    assert spot == 0.7048


def test_resolve_market_date_and_spot_uses_previous_available_date() -> None:
    resolved_date, spot = resolve_market_date_and_spot(
        make_prices(),
        trade_date=date(2026, 6, 12),
    )

    assert resolved_date == date(2026, 6, 11)
    assert spot == 0.7001


def test_resolve_market_date_and_spot_keeps_manual_spot() -> None:
    resolved_date, spot = resolve_market_date_and_spot(
        make_prices(),
        trade_date=date(2026, 6, 12),
        spot=0.6800,
    )

    assert resolved_date == date(2026, 6, 11)
    assert spot == 0.6800


def test_resolve_market_date_and_spot_errors_when_trade_date_is_too_early() -> None:
    with pytest.raises(ValueError, match="no AUD/USD market data"):
        resolve_market_date_and_spot(make_prices(), trade_date=date(2026, 1, 1))


def make_prices() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"date": "2026-06-10", "pair": "AUD/USD", "open": 0.701, "high": 0.703, "low": 0.699, "close": 0.702},
            {"date": "2026-06-11", "pair": "AUD/USD", "open": 0.700, "high": 0.702, "low": 0.698, "close": 0.7001},
            {"date": "2026-06-13", "pair": "AUD/USD", "open": 0.7048, "high": 0.7048, "low": 0.7048, "close": 0.7048},
        ]
    )
