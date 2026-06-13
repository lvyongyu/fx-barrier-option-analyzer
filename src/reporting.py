from __future__ import annotations

from src.barrier_theory import BarrierTheoryEvaluation
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
    barrier_theory: BarrierTheoryEvaluation | None = None,
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
            f"Barrier direction: {_direction_label(result)}",
            f"Touch rule: {_touch_rule(result)}",
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

    if barrier_theory:
        _append_barrier_theory_section(lines, barrier_theory)

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


def format_forecast_report(
    result: TouchProbabilityResult,
    features: FeatureSnapshot | None = None,
    volatility_adjustment: VolatilityAdjustedResult | None = None,
    price_model: PriceModelEvaluation | None = None,
    external_features: ExternalFeatureSnapshot | None = None,
    price_plus_external_model: PriceModelEvaluation | None = None,
    barrier_theory: BarrierTheoryEvaluation | None = None,
) -> str:
    primary_probability = _primary_touch_probability(result, volatility_adjustment, barrier_theory)
    no_touch_probability = 100 - primary_probability if primary_probability is not None else None
    forecast_date = features.as_of_date if features else "n/a"
    question = (
        f"Will {result.pair} touch the {result.barrier:.4f} "
        f"{_direction_label(result)} barrier within {result.days_to_expiry} calendar days?"
    )

    lines = [
        "FX BARRIER TOUCH INTELLIGENCE REPORT",
        "",
        "QUESTION",
        question,
        f"Forecast date: {forecast_date}",
        f"Product: {result.product_type}",
    ]
    if result.client_direction:
        lines.append(f"Client direction: {result.client_direction}")

    lines.extend(
        [
            "",
            "PROBABILITY DISTRIBUTION",
            f"Barrier touched before expiry: {_format_optional_pct(primary_probability)}",
            f"Barrier not touched before expiry: {_format_optional_pct(no_touch_probability)}",
            "",
            "MOST LIKELY OUTCOME",
            _most_likely_outcome(primary_probability),
            "",
            "TRADE SNAPSHOT",
            f"Spot: {result.spot:.4f}",
            f"Strike: {result.strike:.4f}",
            f"Barrier: {result.barrier:.4f}",
            f"Direction: {_direction_label(result)}",
            f"Touch rule: {_touch_rule(result)}",
            f"Market move tested: {_market_move_tested(result)}",
            f"Distance to barrier: {abs(result.distance_pct):.2f}%",
            f"Days to expiry: {result.days_to_expiry}",
            "",
            "REFERENCE ESTIMATES",
            f"Historical baseline: {result.touch_probability:.2f}%",
            f"Volatility-adjusted: {_format_optional_pct(volatility_adjustment.volatility_adjusted_probability if volatility_adjustment else None)}",
            f"GBM barrier-theory: {_format_optional_pct(barrier_theory.current_snapshot.probability if barrier_theory else None)}",
            f"GBM/historical blend: {_format_optional_pct(barrier_theory.blended_probability if barrier_theory else None)}",
            f"Price-only logistic: {_format_optional_pct(price_model.model_probability if price_model else None)}",
            f"Price + external: {_format_optional_pct(price_plus_external_model.model_probability if price_plus_external_model else None)}",
        ]
    )

    if barrier_theory:
        lines.extend(
            [
                "",
                "BARRIER-THEORY DETAILS",
                f"Method: {barrier_theory.current_snapshot.method}",
                f"Expected move to expiry: {_format_optional_pct(barrier_theory.current_snapshot.expected_move_pct)}",
                f"Distance in vol units: {_format_optional_number(barrier_theory.current_snapshot.distance_in_vol_units)}",
                f"Barrier z-score: {_format_optional_number(barrier_theory.current_snapshot.barrier_z_score)}",
                f"Blend GBM weight: {_format_optional_number(barrier_theory.blend_weight)}",
                f"Blend dBrier: {_format_optional_number(_barrier_theory_blend_delta_brier(barrier_theory))}",
            ]
        )

    lines.extend(["", "TOUCH-SUPPORTING FACTORS"])
    lines.extend(_touch_supporting_factors(result, features, volatility_adjustment, barrier_theory))

    lines.extend(["", "TOUCH-OPPOSING FACTORS"])
    lines.extend(_touch_opposing_factors(result, price_model, price_plus_external_model, barrier_theory))

    if external_features:
        lines.extend(
            [
                "",
                "EXTERNAL MARKET CONTEXT",
                f"As of: {external_features.as_of_date}",
                f"DXY return 20d: {_format_optional_pct(external_features.dxy_return_20d)}",
                f"DXY trend 60d: {_format_optional_pct(external_features.dxy_trend_60d)}",
                f"VIX level: {_format_optional_number(external_features.vix_level)}",
                f"VIX change 20d: {_format_optional_number(external_features.vix_change_20d)}",
            ]
        )

    lines.extend(
        [
            "",
            "MODEL RISK NOTES",
            "- This is a probability estimate, not investment advice.",
            "- Daily OHLC data can confirm whether a daily range touched the barrier, but not intraday sequence.",
            "- Positive dBrier means a model beat the historical baseline in walk-forward evaluation.",
            "- Current logistic models remain experimental and should not override baseline or GBM evidence.",
        ]
    )

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


def _append_barrier_theory_section(lines: list[str], evaluation: BarrierTheoryEvaluation) -> None:
    snapshot = evaluation.current_snapshot
    lines.extend(
        [
            "",
            "Barrier-theory estimate:",
            f"Method: {snapshot.method}",
            f"GBM probability: {_format_optional_pct(snapshot.probability)}",
            f"Blended probability: {_format_optional_pct(evaluation.blended_probability)}",
            f"Blend GBM weight: {_format_optional_number(evaluation.blend_weight)}",
            f"Expected move to expiry: {_format_optional_pct(snapshot.expected_move_pct)}",
            f"Distance in vol units: {_format_optional_number(snapshot.distance_in_vol_units)}",
            f"Barrier z-score: {_format_optional_number(snapshot.barrier_z_score)}",
            f"Train rows: {evaluation.train_rows}",
            f"Test rows: {evaluation.test_rows}",
            f"GBM Brier score: {_format_optional_number(evaluation.gbm_brier_score)}",
            f"Blended Brier score: {_format_optional_number(evaluation.blended_brier_score)}",
            f"Baseline Brier score: {_format_optional_number(evaluation.baseline_brier_score)}",
            f"GBM comparison: {_barrier_theory_comparison_note(evaluation)}",
            f"Blend comparison: {_barrier_theory_blend_comparison_note(evaluation)}",
        ]
    )
    if evaluation.used_fallback and evaluation.fallback_reason:
        lines.append(f"Fallback: {evaluation.fallback_reason}")


def _model_comparison_note(price_model: PriceModelEvaluation) -> str:
    if price_model.model_brier_score is None or price_model.baseline_brier_score is None:
        return "n/a"
    if price_model.model_brier_score < price_model.baseline_brier_score:
        return "model beat baseline on Brier score"
    if price_model.model_brier_score > price_model.baseline_brier_score:
        return "model underperformed baseline on Brier score"
    return "model tied baseline on Brier score"


def _barrier_theory_comparison_note(evaluation: BarrierTheoryEvaluation) -> str:
    if evaluation.gbm_brier_score is None or evaluation.baseline_brier_score is None:
        return "n/a"
    if evaluation.gbm_brier_score < evaluation.baseline_brier_score:
        return "GBM beat baseline on Brier score"
    if evaluation.gbm_brier_score > evaluation.baseline_brier_score:
        return "GBM underperformed baseline on Brier score"
    return "GBM tied baseline on Brier score"


def _barrier_theory_blend_comparison_note(evaluation: BarrierTheoryEvaluation) -> str:
    if evaluation.blended_brier_score is None or evaluation.baseline_brier_score is None:
        return "n/a"
    if evaluation.blended_brier_score < evaluation.baseline_brier_score:
        return "blend beat baseline on Brier score"
    if evaluation.blended_brier_score > evaluation.baseline_brier_score:
        return "blend underperformed baseline on Brier score"
    return "blend tied baseline on Brier score"


def _primary_touch_probability(
    result: TouchProbabilityResult,
    volatility_adjustment: VolatilityAdjustedResult | None,
    barrier_theory: BarrierTheoryEvaluation | None,
) -> float | None:
    if barrier_theory and barrier_theory.blended_probability is not None:
        return barrier_theory.blended_probability
    if barrier_theory and barrier_theory.current_snapshot.probability is not None:
        return barrier_theory.current_snapshot.probability
    if volatility_adjustment and volatility_adjustment.volatility_adjusted_probability is not None:
        return volatility_adjustment.volatility_adjusted_probability
    return result.touch_probability


def _direction_label(result: TouchProbabilityResult) -> str:
    return result.barrier_direction


def _touch_rule(result: TouchProbabilityResult) -> str:
    if result.barrier_direction == "down":
        return f"daily low <= {result.barrier:.4f}"
    return f"daily high >= {result.barrier:.4f}"


def _market_move_tested(result: TouchProbabilityResult) -> str:
    if result.barrier_direction == "down":
        return "AUD/USD falls to or below the barrier"
    return "AUD/USD rises to or above the barrier"


def _most_likely_outcome(probability: float | None) -> str:
    if probability is None:
        return "Insufficient data to identify a most likely outcome."
    if probability >= 50:
        return f"Barrier touch is the more likely outcome at {_format_optional_pct(probability)}."
    return f"No barrier touch is the more likely outcome at {_format_optional_pct(100 - probability)}."


def _touch_supporting_factors(
    result: TouchProbabilityResult,
    features: FeatureSnapshot | None,
    volatility_adjustment: VolatilityAdjustedResult | None,
    barrier_theory: BarrierTheoryEvaluation | None,
) -> list[str]:
    factors = [
        f"- Historical windows touched the barrier {result.touch_count} times out of {result.sample_count}.",
        f"- The barrier is only {abs(result.distance_pct):.2f}% from spot over {result.days_to_expiry} calendar days.",
    ]
    if volatility_adjustment and volatility_adjustment.volatility_adjusted_probability is not None:
        factors.append(
            "- Comparable-volatility windows imply "
            f"{volatility_adjustment.volatility_adjusted_probability:.2f}% touch probability."
        )
    if barrier_theory and barrier_theory.current_snapshot.expected_move_pct is not None:
        factors.append(
            "- Expected move to expiry is "
            f"{barrier_theory.current_snapshot.expected_move_pct:.2f}%, versus "
            f"{abs(result.distance_pct):.2f}% barrier distance."
        )
    if features and features.realized_vol_20d is not None:
        factors.append(f"- Current 20d realized volatility is {features.realized_vol_20d:.2f}%.")
    return factors


def _touch_opposing_factors(
    result: TouchProbabilityResult,
    price_model: PriceModelEvaluation | None,
    price_plus_external_model: PriceModelEvaluation | None,
    barrier_theory: BarrierTheoryEvaluation | None,
) -> list[str]:
    factors: list[str] = []
    if barrier_theory and _barrier_theory_blend_delta_brier(barrier_theory) is not None:
        delta = _barrier_theory_blend_delta_brier(barrier_theory)
        if delta is not None and delta < 0:
            factors.append(
                "- The GBM/historical blend underperformed the historical baseline in walk-forward Brier score."
            )
    if price_model and price_model.model_brier_score and price_model.baseline_brier_score:
        if price_model.model_brier_score > price_model.baseline_brier_score:
            factors.append("- The price-only logistic model underperformed the historical baseline.")
    if price_plus_external_model and price_plus_external_model.model_brier_score and price_plus_external_model.baseline_brier_score:
        if price_plus_external_model.model_brier_score > price_plus_external_model.baseline_brier_score:
            factors.append("- The price + external model underperformed the historical baseline.")
    if result.sample_count < 100:
        factors.append("- Historical sample count is low, reducing confidence.")
    if not factors:
        factors.append("- No major opposing model-quality flags were detected, but all estimates remain data-dependent.")
    return factors


def _barrier_theory_blend_delta_brier(evaluation: BarrierTheoryEvaluation) -> float | None:
    if evaluation.baseline_brier_score is None or evaluation.blended_brier_score is None:
        return None
    return evaluation.baseline_brier_score - evaluation.blended_brier_score
