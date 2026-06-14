from __future__ import annotations

from datetime import date

import pandas as pd
import yfinance as yf

from src.barrier_engine import normalize_prices


AUDUSD_YAHOO_TICKER = "AUDUSD=X"
DEFAULT_PAIR = "AUD/USD"


def normalize_pair_label(pair: str) -> str:
    compact = pair.strip().upper().replace(" ", "").replace("-", "/")
    if "/" not in compact and len(compact) == 6:
        compact = f"{compact[:3]}/{compact[3:]}"
    parts = compact.split("/")
    if len(parts) != 2 or any(len(part) != 3 or not part.isalpha() for part in parts):
        raise ValueError("pair must look like AUD/USD or AUDUSD")
    return f"{parts[0]}/{parts[1]}"


def pair_to_yahoo_ticker(pair: str) -> str:
    normalized = normalize_pair_label(pair)
    return normalized.replace("/", "") + "=X"


def download_fx_prices(pair: str = DEFAULT_PAIR, period: str = "2y") -> pd.DataFrame:
    normalized_pair = normalize_pair_label(pair)
    ticker = pair_to_yahoo_ticker(normalized_pair)
    data = yf.download(ticker, period=period, auto_adjust=False, progress=False)
    if data.empty:
        raise ValueError(f"yfinance returned no data for {normalized_pair} ({ticker})")

    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)

    frame = data.reset_index().rename(columns=str.lower)
    frame["pair"] = normalized_pair
    return normalize_prices(frame[["date", "pair", "open", "high", "low", "close"]], pair=normalized_pair)


def download_audusd_prices(period: str = "2y") -> pd.DataFrame:
    return download_fx_prices(DEFAULT_PAIR, period=period)


def resolve_market_date_and_spot(
    prices: pd.DataFrame,
    trade_date: date | None = None,
    spot: float | None = None,
    pair: str = DEFAULT_PAIR,
) -> tuple[date, float]:
    normalized_pair = normalize_pair_label(pair)
    frame = normalize_prices(prices, pair=normalized_pair)
    if trade_date is None:
        resolved_date = frame.iloc[-1]["date"]
    else:
        history = frame[frame["date"] <= trade_date]
        if history.empty:
            raise ValueError(f"no {normalized_pair} market data available on or before trade_date ({trade_date})")
        resolved_date = history.iloc[-1]["date"]

    if spot is not None:
        return resolved_date, spot

    row = frame[frame["date"] <= resolved_date].iloc[-1]
    return resolved_date, float(row["close"])
