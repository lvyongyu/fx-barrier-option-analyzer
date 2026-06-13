from __future__ import annotations

from datetime import date

import pandas as pd
import yfinance as yf

from src.barrier_engine import normalize_prices


AUDUSD_YAHOO_TICKER = "AUDUSD=X"


def download_audusd_prices(period: str = "2y") -> pd.DataFrame:
    pair = "AUD/USD"
    data = yf.download(AUDUSD_YAHOO_TICKER, period=period, auto_adjust=False, progress=False)
    if data.empty:
        raise ValueError("yfinance returned no data for AUD/USD")

    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)

    frame = data.reset_index().rename(columns=str.lower)
    frame["pair"] = pair
    return normalize_prices(frame[["date", "pair", "open", "high", "low", "close"]], pair=pair)


def resolve_market_date_and_spot(
    prices: pd.DataFrame,
    trade_date: date | None = None,
    spot: float | None = None,
) -> tuple[date, float]:
    frame = normalize_prices(prices, pair="AUD/USD")
    if trade_date is None:
        resolved_date = frame.iloc[-1]["date"]
    else:
        history = frame[frame["date"] <= trade_date]
        if history.empty:
            raise ValueError(f"no AUD/USD market data available on or before trade_date ({trade_date})")
        resolved_date = history.iloc[-1]["date"]

    if spot is not None:
        return resolved_date, spot

    row = frame[frame["date"] <= resolved_date].iloc[-1]
    return resolved_date, float(row["close"])
