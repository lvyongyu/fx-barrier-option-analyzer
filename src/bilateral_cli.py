from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import date, timedelta
import json

from src.bilateral import calculate_bilateral_touch_probability, format_bilateral_report
from src.data_loader import DEFAULT_PAIR, download_fx_prices, normalize_pair_label, resolve_market_date_and_spot
from src.pdf_report import write_pdf_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze bilateral FX barrier touch probability.")
    parser.add_argument("--pair", default=DEFAULT_PAIR, help="FX pair, e.g. AUD/USD, AUD/CNH")
    parser.add_argument("--period", default="5y", help="Yahoo Finance history window")
    parser.add_argument("--trade-date", type=date.fromisoformat)
    parser.add_argument("--expiry-date", type=date.fromisoformat)
    parser.add_argument("--horizon-days", type=int, default=92)
    parser.add_argument("--spot", type=float)
    parser.add_argument("--move-pct", type=float, help="symmetric up/down move percentage, e.g. 3")
    parser.add_argument("--upper-barrier", type=float)
    parser.add_argument("--lower-barrier", type=float)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--pdf", help="optional path for writing PDF report")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    pair = normalize_pair_label(args.pair)
    prices = download_fx_prices(pair, period=args.period)
    trade_date, spot = resolve_market_date_and_spot(
        prices,
        trade_date=args.trade_date,
        spot=args.spot,
        pair=pair,
    )
    expiry_date = args.expiry_date or trade_date + timedelta(days=args.horizon_days)
    upper_barrier, lower_barrier = _resolve_barriers(args, spot)

    result = calculate_bilateral_touch_probability(
        pair=pair,
        trade_date=trade_date,
        spot=spot,
        upper_barrier=upper_barrier,
        lower_barrier=lower_barrier,
        expiry_date=expiry_date,
        prices=prices,
    )

    if args.json:
        if args.pdf:
            raise ValueError("--pdf cannot be combined with --json")
        print(json.dumps(asdict(result), default=str, indent=2))
        return

    report = format_bilateral_report(result)
    if args.pdf:
        write_pdf_report(report, args.pdf)
    print(report)


def _resolve_barriers(args: argparse.Namespace, spot: float) -> tuple[float, float]:
    if args.move_pct is not None:
        distance = abs(args.move_pct) / 100
        return spot * (1 + distance), spot * (1 - distance)

    if args.upper_barrier is None or args.lower_barrier is None:
        raise ValueError("provide either --move-pct or both --upper-barrier and --lower-barrier")
    return args.upper_barrier, args.lower_barrier


if __name__ == "__main__":
    main()
