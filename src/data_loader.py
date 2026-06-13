from __future__ import annotations

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
