from __future__ import annotations

from datetime import date

import pandas as pd
import yfinance as yf

from src.barrier_engine import normalize_prices


AUDUSD_YAHOO_TICKER = "AUDUSD=X"
DEFAULT_PAIR = "AUD/USD"
MIN_DIRECT_ROWS = 30


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
    direct = _download_yahoo_ohlc(ticker, normalized_pair, period)
    if len(direct) >= MIN_DIRECT_ROWS or not _can_cross_via_usd(normalized_pair):
        if direct.empty:
            raise ValueError(f"yfinance returned no data for {normalized_pair} ({ticker})")
        return direct

    cross = _download_cross_via_usd(normalized_pair, period)
    if cross.empty:
        if direct.empty:
            raise ValueError(f"yfinance returned no data for {normalized_pair} ({ticker})")
        return direct
    return cross


def _download_yahoo_ohlc(ticker: str, pair: str, period: str) -> pd.DataFrame:
    data = yf.download(ticker, period=period, auto_adjust=False, progress=False)
    if data.empty:
        return pd.DataFrame(columns=["date", "pair", "open", "high", "low", "close"])

    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)

    frame = data.reset_index().rename(columns=str.lower)
    frame["pair"] = pair
    return normalize_prices(frame[["date", "pair", "open", "high", "low", "close"]], pair=pair)


def _can_cross_via_usd(pair: str) -> bool:
    base, quote = pair.split("/")
    return base != "USD" and quote != "USD"


def _download_cross_via_usd(pair: str, period: str) -> pd.DataFrame:
    base, quote = pair.split("/")
    base_usd = _download_yahoo_ohlc(f"{base}USD=X", f"{base}/USD", period)
    quote_ticker = "USDCNY=X" if quote == "CNH" else f"USD{quote}=X"
    quote_pair = "USD/CNY" if quote == "CNH" else f"USD/{quote}"
    usd_quote = _download_yahoo_ohlc(quote_ticker, quote_pair, period)
    return build_cross_rate_prices(pair, base_usd, usd_quote)


def build_cross_rate_prices(pair: str, base_usd: pd.DataFrame, usd_quote: pd.DataFrame) -> pd.DataFrame:
    normalized_pair = normalize_pair_label(pair)
    left = normalize_prices(base_usd).rename(
        columns={
            "open": "base_open",
            "high": "base_high",
            "low": "base_low",
            "close": "base_close",
        }
    )
    right = normalize_prices(usd_quote).rename(
        columns={
            "open": "quote_open",
            "high": "quote_high",
            "low": "quote_low",
            "close": "quote_close",
        }
    )
    merged = left.merge(right, on="date", how="inner")
    if merged.empty:
        return pd.DataFrame(columns=["date", "pair", "open", "high", "low", "close"])

    frame = pd.DataFrame(
        {
            "date": merged["date"],
            "pair": normalized_pair,
            "open": merged["base_open"] * merged["quote_open"],
            "high": merged["base_high"] * merged["quote_high"],
            "low": merged["base_low"] * merged["quote_low"],
            "close": merged["base_close"] * merged["quote_close"],
        }
    )
    return normalize_prices(frame, pair=normalized_pair)


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
