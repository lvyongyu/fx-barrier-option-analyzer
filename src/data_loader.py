from __future__ import annotations

import pandas as pd
import yfinance as yf

from src.barrier_engine import normalize_prices


YAHOO_TICKERS = {
    "AUD/USD": "AUDUSD=X",
}


def download_audusd_prices(period: str = "2y") -> pd.DataFrame:
    data = yf.download(YAHOO_TICKERS["AUD/USD"], period=period, auto_adjust=False, progress=False)
    if data.empty:
        raise ValueError("yfinance returned no AUD/USD data")

    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)

    frame = data.reset_index().rename(columns=str.lower)
    frame["pair"] = "AUD/USD"
    return normalize_prices(frame[["date", "pair", "open", "high", "low", "close"]], pair="AUD/USD")
