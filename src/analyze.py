from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import date
import json

from src.barrier_engine import Trade, calculate_touch_probability
from src.data_loader import download_audusd_prices
from src.feature_engine import build_feature_snapshot
from src.repository import (
    connect,
    init_db,
    save_analysis_result,
    save_feature_snapshot,
    save_trade,
    save_volatility_adjustment,
    upsert_market_prices,
)
from src.reporting import format_summary
from src.volatility_adjustment import calculate_volatility_adjusted_probability


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze FX barrier touch probability.")
    parser.add_argument("--period", default="2y", help="yfinance period, default: 2y")
    parser.add_argument("--trade-date", required=True, type=date.fromisoformat)
    parser.add_argument("--expiry-date", required=True, type=date.fromisoformat)
    parser.add_argument("--spot", required=True, type=float)
    parser.add_argument("--strike", required=True, type=float)
    parser.add_argument("--barrier", required=True, type=float)
    parser.add_argument("--barrier-direction", default="up", choices=["up", "down"])
    parser.add_argument("--product-type", default="Ratio Convertible Forward")
    parser.add_argument("--client-direction", choices=["Importer", "Exporter"])
    parser.add_argument("--protected-amount", type=float)
    parser.add_argument("--ratio-amount", type=float)
    parser.add_argument("--amount-currency")
    parser.add_argument("--barrier-level-period", default="continuous")
    parser.add_argument("--expiry-time-zone", default="Tokyo")
    parser.add_argument("--save-db", help="optional SQLite path for saving research data")
    parser.add_argument("--json", action="store_true", help="print raw JSON instead of a readable summary")
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
        product_type=args.product_type,
        client_direction=args.client_direction,
        protected_amount=args.protected_amount,
        ratio_amount=args.ratio_amount,
        amount_currency=args.amount_currency,
        barrier_level_period=args.barrier_level_period,
        expiry_time_zone=args.expiry_time_zone,
    )
    result = calculate_touch_probability(trade, prices)
    features = build_feature_snapshot(trade, prices)
    volatility_adjustment = calculate_volatility_adjusted_probability(
        trade,
        prices,
        baseline_probability=result.touch_probability,
        current_features=features,
    )
    saved_ids = None
    if args.save_db:
        with connect(args.save_db) as connection:
            init_db(connection)
            upsert_market_prices(connection, prices)
            trade_id = save_trade(connection, trade)
            feature_snapshot_id = save_feature_snapshot(connection, features, trade_id=trade_id)
            analysis_result_id = save_analysis_result(connection, result, trade_id=trade_id)
            volatility_adjustment_id = save_volatility_adjustment(
                connection,
                volatility_adjustment,
                analysis_result_id=analysis_result_id,
            )
            saved_ids = {
                "trade_id": trade_id,
                "feature_snapshot_id": feature_snapshot_id,
                "analysis_result_id": analysis_result_id,
                "volatility_adjustment_id": volatility_adjustment_id,
            }
    if args.json:
        print(
            json.dumps(
                {
                    "result": asdict(result),
                    "features": asdict(features),
                    "volatility_adjustment": asdict(volatility_adjustment),
                    "saved_ids": saved_ids,
                },
                default=str,
                indent=2,
            )
        )
    else:
        print(format_summary(result, features, volatility_adjustment))


if __name__ == "__main__":
    main()
