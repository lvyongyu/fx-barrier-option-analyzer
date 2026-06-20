from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import date, timedelta
import json

import pandas as pd

from src.pricing.barrier_engine import Trade, calculate_touch_probability, normalize_prices
from src.data.data_loader import download_audusd_prices


@dataclass(frozen=True)
class SampleTradeExample:
    name: str
    description: str
    tenor_days: int
    barrier_distance_pct: float
    trade: Trade


def build_sample_trade_examples(
    prices: pd.DataFrame,
    trade_date: date | None = None,
) -> list[SampleTradeExample]:
    frame = normalize_prices(prices, pair="AUD/USD")
    if trade_date is None:
        trade_date = frame["date"].max()
    history = frame[frame["date"] <= trade_date].copy()
    if history.empty:
        raise ValueError("no AUD/USD history available on or before trade_date")

    spot = float(history.iloc[-1]["close"])
    atr_pct = _recent_atr_pct(history)
    scenarios = [
        ("near_up_30d", "30-day near up barrier", 30, "up", max(0.015, atr_pct * 2.0)),
        ("medium_up_90d", "90-day medium up barrier", 90, "up", max(0.035, atr_pct * 4.0)),
        ("far_up_180d", "180-day far up barrier", 180, "up", max(0.060, atr_pct * 7.0)),
        ("near_down_30d", "30-day near down barrier", 30, "down", max(0.015, atr_pct * 2.0)),
        ("medium_down_90d", "90-day medium down barrier", 90, "down", max(0.035, atr_pct * 4.0)),
        ("far_down_180d", "180-day far down barrier", 180, "down", max(0.060, atr_pct * 7.0)),
    ]

    examples: list[SampleTradeExample] = []
    for name, description, tenor_days, direction, distance in scenarios:
        barrier = spot * (1 + distance) if direction == "up" else spot * (1 - distance)
        trade = Trade(
            pair="AUD/USD",
            trade_date=trade_date,
            spot=spot,
            strike=spot,
            barrier=barrier,
            expiry_date=trade_date + timedelta(days=tenor_days),
            barrier_direction=direction,
            product_type="Sample Barrier Trade",
            client_direction="Importer" if direction == "up" else "Exporter",
            barrier_level_period="continuous",
            expiry_time_zone="Tokyo",
        )
        examples.append(
            SampleTradeExample(
                name=name,
                description=description,
                tenor_days=tenor_days,
                barrier_distance_pct=distance * 100,
                trade=trade,
            )
        )
    return examples


def format_sample_trade_report(examples: list[SampleTradeExample], prices: pd.DataFrame) -> str:
    rows = []
    for example in examples:
        result = calculate_touch_probability(example.trade, prices)
        rows.append(
            [
                example.name,
                example.trade.barrier_direction,
                str(example.tenor_days),
                f"{example.trade.spot:.4f}",
                f"{example.trade.barrier:.4f}",
                f"{example.barrier_distance_pct:.2f}%",
                str(result.sample_count),
                f"{result.touch_probability:.2f}%",
            ]
        )
    return "\n".join(
        [
            "Sample AUD/USD barrier trades",
            "",
            _format_table(
                [
                    "Name",
                    "Dir",
                    "Tenor",
                    "Spot",
                    "Barrier",
                    "Distance",
                    "Samples",
                    "Hist prob",
                ],
                rows,
            ),
        ]
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate sample AUD/USD barrier trades from recent history.")
    parser.add_argument("--period", default="5y", help="yfinance period used for historical probability")
    parser.add_argument("--trade-date", type=date.fromisoformat, help="optional sample trade date")
    parser.add_argument("--json", action="store_true", help="print raw JSON instead of a readable table")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    prices = download_audusd_prices(period=args.period)
    examples = build_sample_trade_examples(prices, trade_date=args.trade_date)
    if args.json:
        print(json.dumps([asdict(example) for example in examples], default=str, indent=2))
    else:
        print(format_sample_trade_report(examples, prices))


def _recent_atr_pct(prices: pd.DataFrame, window: int = 14) -> float:
    if len(prices) < window:
        raise ValueError(f"need at least {window} AUD/USD rows to build sample trades")
    tail = prices.tail(window)
    return float(((tail["high"] - tail["low"]) / tail["close"]).mean())


def _format_table(headers: list[str], rows: list[list[str]]) -> str:
    widths = [
        max(len(row[index]) for row in [headers, *rows])
        for index in range(len(headers))
    ]
    header_line = " | ".join(header.ljust(widths[index]) for index, header in enumerate(headers))
    separator = "-+-".join("-" * width for width in widths)
    row_lines = [
        " | ".join(value.ljust(widths[index]) for index, value in enumerate(row))
        for row in rows
    ]
    return "\n".join([header_line, separator, *row_lines])


if __name__ == "__main__":
    main()
