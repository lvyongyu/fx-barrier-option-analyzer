from datetime import date, timedelta

import pandas as pd
import pytest

from src.data.external_features import build_external_feature_snapshot, normalize_market_series


def test_build_external_feature_snapshot_calculates_dxy_and_vix_features() -> None:
    dxy = make_series(start_value=100)
    vix = make_series(start_value=20, daily_change=0.2)

    snapshot = build_external_feature_snapshot(dxy, vix, as_of_date=date(2026, 3, 15))

    assert snapshot.as_of_date == date(2026, 3, 15)
    assert snapshot.dxy_return_20d is not None
    assert snapshot.dxy_trend_60d is not None
    assert snapshot.vix_level is not None
    assert snapshot.vix_change_20d is not None
    assert snapshot.vix_change_20d == pytest.approx(4.0)


def test_external_feature_snapshot_does_not_use_future_values() -> None:
    dxy = make_series(start_value=100)
    vix = make_series(start_value=20, daily_change=0.2)
    clean = build_external_feature_snapshot(dxy, vix, as_of_date=date(2026, 3, 1))

    shocked_dxy = dxy.copy()
    shocked_vix = vix.copy()
    shocked_dxy.loc[pd.to_datetime(shocked_dxy["date"]).dt.date > date(2026, 3, 1), "close"] = 999
    shocked_vix.loc[pd.to_datetime(shocked_vix["date"]).dt.date > date(2026, 3, 1), "close"] = 999
    shocked = build_external_feature_snapshot(shocked_dxy, shocked_vix, as_of_date=date(2026, 3, 1))

    assert shocked == clean


def test_normalize_market_series_requires_date_and_close() -> None:
    with pytest.raises(ValueError, match="missing columns"):
        normalize_market_series(pd.DataFrame({"date": ["2026-01-01"]}))


def make_series(days: int = 90, start_value: float = 100, daily_change: float = 0.1) -> pd.DataFrame:
    start = date(2026, 1, 1)
    rows = []
    for offset in range(days):
        rows.append(
            {
                "date": (start + timedelta(days=offset)).isoformat(),
                "close": start_value + offset * daily_change,
            }
        )
    return pd.DataFrame(rows)
