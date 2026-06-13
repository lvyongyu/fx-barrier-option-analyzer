from __future__ import annotations

from src.barrier_engine import TouchProbabilityResult
from src.external_features import ExternalFeatureSnapshot
from src.feature_engine import FeatureSnapshot
from src.price_model import PriceModelEvaluation
from src.volatility_adjustment import VolatilityAdjustedResult


def format_summary(
    result: TouchProbabilityResult,
    features: FeatureSnapshot | None = None,
    volatility_adjustment: VolatilityAdjustedResult | None = None,
    price_model: PriceModelEvaluation | None = None,
    external_features: ExternalFeatureSnapshot | None = None,
    price_plus_external_model: PriceModelEvaluation | None = None,
) -> str:
    lines = [
        f"{result.pair} barrier analysis",
        f"Product: {result.product_type}",
    ]
    if result.client_direction:
        lines.append(f"Client direction: {result.client_direction}")

    lines.extend(
        [
            "",
            f"Spot: {result.spot:.4f}",
            f"Strike: {result.strike:.4f}",
            f"Barrier: {result.barrier:.4f}",
            f"Barrier period: {result.barrier_level_period}",
            f"Distance to barrier: {result.distance_pct:.2f}%",
            f"Days to expiry: {result.days_to_expiry}",
        ]
    )

    if result.protected_amount is not None:
        suffix = f" {result.amount_currency}" if result.amount_currency else ""
        lines.append(f"Protected amount: {result.protected_amount:,.0f}{suffix}")
    if result.ratio_amount is not None:
        suffix = f" {result.amount_currency}" if result.amount_currency else ""
        lines.append(f"Ratio amount: {result.ratio_amount:,.0f}{suffix}")

    lines.extend(
        [
            f"Expiry time zone: {result.expiry_time_zone}",
            "",
                f"Historical samples: {result.sample_count}",
                f"Touch count: {result.touch_count}",
                f"Historical touch probability: {result.touch_probability:.2f}%",
            ]
        )

    if volatility_adjustment:
        lines.extend(
            [
                "",
                "Volatility-adjusted estimate:",
                f"Method: {volatility_adjustment.method}",
                f"Current 20d vol percentile: {_format_optional_pct(volatility_adjustment.current_vol_percentile)}",
                f"Comparable samples: {volatility_adjustment.comparable_sample_count}",
                f"Comparable touch count: {volatility_adjustment.comparable_touch_count}",
                "Volatility-adjusted probability: "
                f"{_format_optional_pct(volatility_adjustment.volatility_adjusted_probability)}",
            ]
        )
        if volatility_adjustment.used_fallback and volatility_adjustment.fallback_reason:
            lines.append(f"Fallback: {volatility_adjustment.fallback_reason}")

    if price_model:
        _append_model_section(lines, "Price-only model estimate:", price_model)

    if price_plus_external_model:
        _append_model_section(lines, "Price + external model estimate:", price_plus_external_model)

    if external_features:
        lines.extend(
            [
                "",
                "External market features:",
                f"As of: {external_features.as_of_date}",
                f"DXY return 20d: {_format_optional_pct(external_features.dxy_return_20d)}",
                f"DXY trend 60d: {_format_optional_pct(external_features.dxy_trend_60d)}",
                f"VIX level: {_format_optional_number(external_features.vix_level)}",
                f"VIX change 20d: {_format_optional_number(external_features.vix_change_20d)}",
            ]
        )

    if features:
        lines.extend(
            [
                "",
                "Current feature snapshot:",
                f"As of: {features.as_of_date}",
                f"Realized vol 20d: {_format_optional_pct(features.realized_vol_20d)}",
                f"Realized vol 60d: {_format_optional_pct(features.realized_vol_60d)}",
                f"ATR 14d: {_format_optional_pct(features.atr_14d)}",
                f"Trend 20d: {_format_optional_pct(features.trend_20d)}",
                f"Trend 60d: {_format_optional_pct(features.trend_60d)}",
                f"Range position 60d: {_format_optional_pct(features.range_position_60d)}",
                f"Recent high distance: {_format_optional_pct(features.recent_high_distance)}",
                f"Recent low distance: {_format_optional_pct(features.recent_low_distance)}",
            ]
        )

    actual_path = result.actual_path
    lines.extend(["", "Actual path check:"])
    if not actual_path.is_applicable:
        lines.append(f"Not applicable - {actual_path.reason}")
        return "\n".join(lines)

    lines.append(f"Barrier hit: {'Yes' if actual_path.barrier_hit else 'No'}")
    if actual_path.hit_date:
        lines.append(f"Hit date: {actual_path.hit_date}")
        lines.append(f"Days to hit: {actual_path.days_to_hit}")
    if actual_path.max_high is not None:
        lines.append(f"Max high: {actual_path.max_high:.4f}")
    if actual_path.min_low is not None:
        lines.append(f"Min low: {actual_path.min_low:.4f}")

    return "\n".join(lines)


def _format_optional_pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.2f}%"


def _format_optional_number(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.4f}"


def _append_model_section(lines: list[str], title: str, price_model: PriceModelEvaluation) -> None:
    lines.extend(
        [
            "",
            title,
            f"Model probability: {_format_optional_pct(price_model.model_probability)}",
            f"Train rows: {price_model.train_rows}",
            f"Test rows: {price_model.test_rows}",
            f"Train hit rate: {_format_optional_pct(price_model.positive_rate_train)}",
            f"Test hit rate: {_format_optional_pct(price_model.positive_rate_test)}",
            f"Baseline probability: {_format_optional_pct(price_model.baseline_probability)}",
            f"Model Brier score: {_format_optional_number(price_model.model_brier_score)}",
            f"Baseline Brier score: {_format_optional_number(price_model.baseline_brier_score)}",
            f"Model log loss: {_format_optional_number(price_model.model_log_loss)}",
            f"Baseline log loss: {_format_optional_number(price_model.baseline_log_loss)}",
            f"Model comparison: {_model_comparison_note(price_model)}",
        ]
    )
    if price_model.calibration_buckets:
        lines.append("Calibration buckets:")
        for bucket in price_model.calibration_buckets:
            lines.append(
                "  "
                f"{bucket.lower_bound:.0f}-{bucket.upper_bound:.0f}%: "
                f"n={bucket.sample_count}, "
                f"avg_pred={_format_optional_pct(bucket.average_predicted_probability)}, "
                f"actual_hit={_format_optional_pct(bucket.actual_hit_rate)}"
            )
    if price_model.used_fallback and price_model.fallback_reason:
        lines.append(f"Fallback: {price_model.fallback_reason}")


def _model_comparison_note(price_model: PriceModelEvaluation) -> str:
    if price_model.model_brier_score is None or price_model.baseline_brier_score is None:
        return "n/a"
    if price_model.model_brier_score < price_model.baseline_brier_score:
        return "model beat baseline on Brier score"
    if price_model.model_brier_score > price_model.baseline_brier_score:
        return "model underperformed baseline on Brier score"
    return "model tied baseline on Brier score"
