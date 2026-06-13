from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import date
import json

from src.barrier_engine import Trade, calculate_touch_probability
from src.data_loader import download_audusd_prices


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze AUD/USD barrier touch probability.")
    parser.add_argument("--period", default="2y", help="yfinance period, default: 2y")
    parser.add_argument("--trade-date", required=True, type=date.fromisoformat)
    parser.add_argument("--expiry-date", required=True, type=date.fromisoformat)
    parser.add_argument("--spot", required=True, type=float)
    parser.add_argument("--strike", required=True, type=float)
    parser.add_argument("--barrier", required=True, type=float)
    parser.add_argument("--barrier-direction", default="up", choices=["up", "down"])
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    prices = download_audusd_prices(period=args.period)
    trade = Trade(
        pair="AUD/USD",
        trade_date=args.trade_date,
        spot=args.spot,
        strike=args.strike,
        barrier=args.barrier,
        expiry_date=args.expiry_date,
        barrier_direction=args.barrier_direction,
    )
    result = calculate_touch_probability(trade, prices)
    print(json.dumps(asdict(result), default=str, indent=2))


if __name__ == "__main__":
    main()
