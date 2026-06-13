from __future__ import annotations

import pandas as pd
import yfinance as yf

from src.barrier_engine import normalize_prices


YAHOO_TICKERS = {
    "AUD/USD": "AUDUSD=X",
}


def download_prices(pair: str = "AUD/USD", period: str = "2y") -> pd.DataFrame:
    if pair not in YAHOO_TICKERS:
        supported = ", ".join(sorted(YAHOO_TICKERS))
        raise ValueError(f"automatic yfinance download is only configured for: {supported}")

    data = yf.download(YAHOO_TICKERS[pair], period=period, auto_adjust=False, progress=False)
    if data.empty:
        raise ValueError(f"yfinance returned no data for {pair}")

    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)

    frame = data.reset_index().rename(columns=str.lower)
    frame["pair"] = pair
    return normalize_prices(frame[["date", "pair", "open", "high", "low", "close"]], pair=pair)


def download_audusd_prices(period: str = "2y") -> pd.DataFrame:
    return download_prices("AUD/USD", period=period)
