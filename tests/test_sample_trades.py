from datetime import date, timedelta

import pandas as pd

from src.sample_trades import build_sample_trade_examples, format_sample_trade_report


def test_build_sample_trade_examples_creates_up_and_down_scenarios() -> None:
    prices = make_prices()

    examples = build_sample_trade_examples(prices, trade_date=date(2026, 3, 31))

    assert [example.name for example in examples] == [
        "near_up_30d",
        "medium_up_90d",
        "far_up_180d",
        "near_down_30d",
        "medium_down_90d",
        "far_down_180d",
    ]
    assert all(example.trade.spot > 0 for example in examples)
    assert all(example.trade.expiry_date > example.trade.trade_date for example in examples)
    assert all(
        example.trade.barrier > example.trade.spot
        for example in examples
        if example.trade.barrier_direction == "up"
    )
    assert all(
        example.trade.barrier < example.trade.spot
        for example in examples
        if example.trade.barrier_direction == "down"
    )


def test_format_sample_trade_report_includes_historical_probabilities() -> None:
    prices = make_prices(days=260)
    examples = build_sample_trade_examples(prices, trade_date=date(2026, 3, 31))

    report = format_sample_trade_report(examples, prices)

    assert "Sample AUD/USD barrier trades" in report
    assert "near_up_30d" in report
    assert "near_down_30d" in report
    assert "Hist prob" in report


def make_prices(days: int = 220) -> pd.DataFrame:
    start = date(2026, 1, 1)
    rows = []
    close = 0.66
    for offset in range(days):
        current = start + timedelta(days=offset)
        change = 0.001 if offset % 5 in {0, 1, 2} else -0.0007
        close += change
        rows.append(
            {
                "date": current.isoformat(),
                "pair": "AUD/USD",
                "open": close - change,
                "high": close + 0.004,
                "low": close - 0.004,
                "close": close,
            }
        )
    return pd.DataFrame(rows)
