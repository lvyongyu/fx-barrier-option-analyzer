from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd
import yfinance as yf


DXY_TICKER = "DX-Y.NYB"
VIX_TICKER = "^VIX"


@dataclass(frozen=True)
class ExternalFeatureSnapshot:
    as_of_date: date
    dxy_return_20d: float | None
    dxy_trend_60d: float | None
    vix_level: float | None
    vix_change_20d: float | None


def download_external_market_data(period: str = "2y") -> dict[str, pd.DataFrame]:
    return {
        "dxy": download_market_series(DXY_TICKER, period=period),
        "vix": download_market_series(VIX_TICKER, period=period),
    }


def download_market_series(ticker: str, period: str = "2y") -> pd.DataFrame:
    data = yf.download(ticker, period=period, auto_adjust=False, progress=False)
    if data.empty:
        raise ValueError(f"yfinance returned no data for {ticker}")
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)
    frame = data.reset_index().rename(columns=str.lower)
    return normalize_market_series(frame[["date", "close"]])


def normalize_market_series(data: pd.DataFrame) -> pd.DataFrame:
    frame = data.rename(columns={column: column.strip().lower() for column in data.columns}).copy()
    missing = {"date", "close"} - set(frame.columns)
    if missing:
        raise ValueError(f"market series missing columns: {', '.join(sorted(missing))}")
    frame["date"] = pd.to_datetime(frame["date"]).dt.date
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    frame = frame.dropna(subset=["date", "close"])
    frame = frame.sort_values("date").drop_duplicates(subset=["date"], keep="last").reset_index(drop=True)
    if frame.empty:
        raise ValueError("market series is empty after normalization")
    return frame


def build_external_feature_snapshot(
    dxy: pd.DataFrame,
    vix: pd.DataFrame,
    as_of_date: date | None = None,
) -> ExternalFeatureSnapshot:
    dxy_history = _history(dxy, as_of_date)
    vix_history = _history(vix, as_of_date)
    if dxy_history.empty and vix_history.empty:
        raise ValueError("no external market data available on or before as_of_date")

    actual_as_of = max(
        [frame["date"].max() for frame in [dxy_history, vix_history] if not frame.empty]
    )

    return ExternalFeatureSnapshot(
        as_of_date=actual_as_of,
        dxy_return_20d=_trend_pct(dxy_history["close"], 20) if not dxy_history.empty else None,
        dxy_trend_60d=_trend_pct(dxy_history["close"], 60) if not dxy_history.empty else None,
        vix_level=float(vix_history.iloc[-1]["close"]) if not vix_history.empty else None,
        vix_change_20d=_point_change(vix_history["close"], 20) if not vix_history.empty else None,
    )


def _history(data: pd.DataFrame, as_of_date: date | None) -> pd.DataFrame:
    frame = normalize_market_series(data)
    if as_of_date is None:
        return frame
    return frame[frame["date"] <= as_of_date].copy()


def _trend_pct(close: pd.Series, window: int) -> float | None:
    if len(close) <= window:
        return None
    start = float(close.iloc[-window - 1])
    end = float(close.iloc[-1])
    if start <= 0:
        return None
    return (end / start - 1) * 100


def _point_change(close: pd.Series, window: int) -> float | None:
    if len(close) <= window:
        return None
    return float(close.iloc[-1] - close.iloc[-window - 1])
