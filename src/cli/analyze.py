from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import date
import json

from src.pricing.barrier_theory import evaluate_barrier_theory_model
from src.pricing.barrier_engine import Trade, calculate_touch_probability
from src.data.data_loader import DEFAULT_PAIR, download_fx_prices, normalize_pair_label, resolve_market_date_and_spot
from src.data.external_features import build_external_feature_snapshot, download_external_market_data
from src.pricing.feature_engine import build_feature_snapshot
from src.reporting.pdf_report import write_pdf_report
from src.pricing.price_model import evaluate_price_only_model, evaluate_price_plus_external_model
from src.storage.repository import (
    connect,
    init_db,
    save_analysis_result,
    save_feature_snapshot,
    save_trade,
    save_volatility_adjustment,
    upsert_market_prices,
)
from src.reporting.reporting import format_forecast_report, format_summary
from src.pricing.training_dataset import build_price_only_training_dataset, build_price_plus_external_training_dataset
from src.pricing.volatility_adjustment import calculate_volatility_adjusted_probability


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze FX barrier touch probability.")
    parser.add_argument("--pair", default=DEFAULT_PAIR, help="FX pair, e.g. AUD/USD, EUR/USD, USD/JPY")
    parser.add_argument("--period", default="2y", help="yfinance period, default: 2y")
    parser.add_argument("--trade-date", type=date.fromisoformat)
    parser.add_argument("--expiry-date", required=True, type=date.fromisoformat)
    parser.add_argument("--spot", type=float)
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
    parser.add_argument("--export-training-dataset", help="optional CSV path for exporting price-only training data")
    parser.add_argument("--include-external-features", action="store_true", help="download DXY/VIX and print external features")
    parser.add_argument("--report-style", default="summary", choices=["summary", "forecast"])
    parser.add_argument("--json", action="store_true", help="print raw JSON instead of a readable summary")
    parser.add_argument("--pdf", help="optional path for writing the readable report as a PDF")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    pair = normalize_pair_label(args.pair)
    prices = download_fx_prices(pair=pair, period=args.period)
    resolved_trade_date, resolved_spot = resolve_market_date_and_spot(
        prices,
        trade_date=args.trade_date,
        spot=args.spot,
        pair=pair,
    )
    trade = Trade(
        pair=pair,
        trade_date=resolved_trade_date,
        spot=resolved_spot,
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
    external_features = None
    external_data = None
    if args.include_external_features:
        external_data = download_external_market_data(period=args.period)
        external_features = build_external_feature_snapshot(
            external_data["dxy"],
            external_data["vix"],
            as_of_date=features.as_of_date,
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
    exported_training_dataset = None
    training_dataset = build_price_only_training_dataset(trade, prices)
    if args.export_training_dataset:
        training_dataset.to_csv(args.export_training_dataset, index=False)
        exported_training_dataset = {
            "path": args.export_training_dataset,
            "rows": len(training_dataset),
            "columns": list(training_dataset.columns),
        }
    price_model_evaluation = evaluate_price_only_model(training_dataset, asdict(features))
    barrier_theory_evaluation = evaluate_barrier_theory_model(training_dataset, asdict(features))
    price_plus_external_model_evaluation = None
    if external_data and external_features:
        external_training_dataset = build_price_plus_external_training_dataset(
            trade,
            prices,
            external_data["dxy"],
            external_data["vix"],
        )
        current_external_features = {**asdict(features), **asdict(external_features)}
        price_plus_external_model_evaluation = evaluate_price_plus_external_model(
            external_training_dataset,
            current_external_features,
        )
    if args.json:
        if args.pdf:
            raise ValueError("--pdf cannot be combined with --json")
        print(
            json.dumps(
                {
                    "result": asdict(result),
                    "features": asdict(features),
                    "external_features": asdict(external_features) if external_features else None,
                    "volatility_adjustment": asdict(volatility_adjustment),
                    "barrier_theory": asdict(barrier_theory_evaluation),
                    "price_model": asdict(price_model_evaluation),
                    "price_plus_external_model": (
                        asdict(price_plus_external_model_evaluation)
                        if price_plus_external_model_evaluation
                        else None
                    ),
                    "saved_ids": saved_ids,
                    "exported_training_dataset": exported_training_dataset,
                },
                default=str,
                indent=2,
            )
        )
    else:
        formatter = format_forecast_report if args.report_style == "forecast" else format_summary
        report_text = formatter(
            result=result,
            features=features,
            volatility_adjustment=volatility_adjustment,
            price_model=price_model_evaluation,
            external_features=external_features,
            price_plus_external_model=price_plus_external_model_evaluation,
            barrier_theory=barrier_theory_evaluation,
        )
        if args.pdf:
            write_pdf_report(report_text, args.pdf)
        print(report_text)


if __name__ == "__main__":
    main()
