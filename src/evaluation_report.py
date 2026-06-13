from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import date
import json

from src.barrier_engine import Trade, calculate_touch_probability
from src.data_loader import download_audusd_prices
from src.external_features import build_external_feature_snapshot, download_external_market_data
from src.feature_engine import build_feature_snapshot
from src.price_model import PriceModelEvaluation, evaluate_price_only_model, evaluate_price_plus_external_model
from src.training_dataset import build_price_only_training_dataset, build_price_plus_external_training_dataset
from src.volatility_adjustment import calculate_volatility_adjusted_probability


@dataclass(frozen=True)
class PeriodEvaluation:
    period: str
    market_rows: int
    baseline_probability: float
    baseline_sample_count: int
    baseline_touch_count: int
    volatility_adjusted_probability: float | None
    volatility_comparable_sample_count: int
    price_only_model: PriceModelEvaluation
    price_plus_external_model: PriceModelEvaluation | None


def evaluate_periods(
    trade: Trade,
    periods: list[str],
    include_external_features: bool = True,
) -> list[PeriodEvaluation]:
    return [
        evaluate_single_period(trade, period, include_external_features=include_external_features)
        for period in periods
    ]


def evaluate_single_period(
    trade: Trade,
    period: str,
    include_external_features: bool = True,
) -> PeriodEvaluation:
    prices = download_audusd_prices(period=period)
    result = calculate_touch_probability(trade, prices)
    features = build_feature_snapshot(trade, prices)
    volatility_adjustment = calculate_volatility_adjusted_probability(
        trade,
        prices,
        baseline_probability=result.touch_probability,
        current_features=features,
    )
    price_only_dataset = build_price_only_training_dataset(trade, prices)
    price_only_model = evaluate_price_only_model(price_only_dataset, asdict(features))

    price_plus_external_model = None
    if include_external_features:
        external_data = download_external_market_data(period=period)
        external_features = build_external_feature_snapshot(
            external_data["dxy"],
            external_data["vix"],
            as_of_date=features.as_of_date,
        )
        price_plus_external_dataset = build_price_plus_external_training_dataset(
            trade,
            prices,
            external_data["dxy"],
            external_data["vix"],
        )
        current_features = {**asdict(features), **asdict(external_features)}
        price_plus_external_model = evaluate_price_plus_external_model(
            price_plus_external_dataset,
            current_features,
        )

    return PeriodEvaluation(
        period=period,
        market_rows=len(prices),
        baseline_probability=result.touch_probability,
        baseline_sample_count=result.sample_count,
        baseline_touch_count=result.touch_count,
        volatility_adjusted_probability=volatility_adjustment.volatility_adjusted_probability,
        volatility_comparable_sample_count=volatility_adjustment.comparable_sample_count,
        price_only_model=price_only_model,
        price_plus_external_model=price_plus_external_model,
    )


def format_evaluation_report(evaluations: list[PeriodEvaluation]) -> str:
    lines = [
        "Model evaluation report",
        "",
        _format_table(
            [
                "Period",
                "Rows",
                "Samples",
                "Hits",
                "Baseline",
                "Vol adj",
                "Price prob",
                "Price Brier",
                "Price dBrier",
                "Ext prob",
                "Ext Brier",
                "Ext dBrier",
            ],
            [_summary_row(evaluation) for evaluation in evaluations],
        ),
    ]
    for evaluation in evaluations:
        lines.extend(["", *_format_period_detail(evaluation)])
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run model evaluation across historical data periods.")
    parser.add_argument("--periods", nargs="+", default=["2y", "5y", "10y"], help="yfinance periods to compare")
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
    parser.add_argument("--no-external-features", action="store_true", help="skip DXY/VIX model comparison")
    parser.add_argument("--json", action="store_true", help="print raw JSON instead of a readable report")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
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
    evaluations = evaluate_periods(
        trade,
        args.periods,
        include_external_features=not args.no_external_features,
    )
    if args.json:
        print(json.dumps([asdict(evaluation) for evaluation in evaluations], default=str, indent=2))
    else:
        print(format_evaluation_report(evaluations))


def _summary_row(evaluation: PeriodEvaluation) -> list[str]:
    price_model = evaluation.price_only_model
    external_model = evaluation.price_plus_external_model
    return [
        evaluation.period,
        str(evaluation.market_rows),
        str(evaluation.baseline_sample_count),
        str(evaluation.baseline_touch_count),
        _format_pct(evaluation.baseline_probability),
        _format_pct(evaluation.volatility_adjusted_probability),
        _format_pct(price_model.model_probability),
        _format_number(price_model.model_brier_score),
        _format_number(_brier_improvement(price_model)),
        _format_pct(external_model.model_probability) if external_model else "n/a",
        _format_number(external_model.model_brier_score) if external_model else "n/a",
        _format_number(_brier_improvement(external_model)) if external_model else "n/a",
    ]


def _format_period_detail(evaluation: PeriodEvaluation) -> list[str]:
    lines = [f"{evaluation.period} calibration"]
    lines.extend(_format_model_buckets("Price-only", evaluation.price_only_model))
    if evaluation.price_plus_external_model:
        lines.extend(_format_model_buckets("Price + external", evaluation.price_plus_external_model))
    return lines


def _format_model_buckets(label: str, evaluation: PriceModelEvaluation) -> list[str]:
    lines = [f"{label}:"]
    if evaluation.used_fallback:
        lines.append(f"  fallback: {evaluation.fallback_reason}")
        return lines
    for bucket in evaluation.calibration_buckets:
        lines.append(
            "  "
            f"{bucket.lower_bound:.0f}-{bucket.upper_bound:.0f}%: "
            f"n={bucket.sample_count}, "
            f"avg_pred={_format_pct(bucket.average_predicted_probability)}, "
            f"actual_hit={_format_pct(bucket.actual_hit_rate)}"
        )
    return lines


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


def _format_pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.2f}%"


def _format_number(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.4f}"


def _brier_improvement(evaluation: PriceModelEvaluation) -> float | None:
    if evaluation.baseline_brier_score is None or evaluation.model_brier_score is None:
        return None
    return evaluation.baseline_brier_score - evaluation.model_brier_score


if __name__ == "__main__":
    main()
