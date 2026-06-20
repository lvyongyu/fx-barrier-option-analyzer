from datetime import date

from src.pricing.barrier_theory import BarrierTheoryEvaluation, BarrierTheorySnapshot
from src.pricing.barrier_engine import BarrierPathResult, TouchProbabilityResult
from src.data.external_features import ExternalFeatureSnapshot
from src.pricing.price_model import PriceModelEvaluation
from src.reporting.reporting import format_forecast_report, format_summary


def test_format_summary_marks_actual_path_not_applicable() -> None:
    result = result_with_path(
        BarrierPathResult(
            is_applicable=False,
            reason="expiry_date is after available market data (2026-06-12)",
            barrier_hit=False,
            hit_date=None,
            max_high=None,
            min_low=None,
            days_to_hit=None,
        ),
    )

    summary = format_summary(result)

    assert "Historical touch probability: 17.06%" in summary
    assert "Actual path check:" in summary
    assert "Not applicable - expiry_date is after available market data" in summary


def test_format_summary_includes_hit_details() -> None:
    result = result_with_path(
        BarrierPathResult(
            is_applicable=True,
            reason=None,
            barrier_hit=True,
            hit_date=date(2026, 4, 18),
            max_high=0.71,
            min_low=0.64,
            days_to_hit=3,
        ),
    )

    summary = format_summary(result)

    assert "Barrier hit: Yes" in summary
    assert "Hit date: 2026-04-18" in summary
    assert "Max high: 0.7100" in summary


def test_format_summary_includes_ratio_convertible_forward_fields() -> None:
    result = result_with_path(
        BarrierPathResult(
            is_applicable=False,
            reason="expiry_date is after available market data (2026-06-12)",
            barrier_hit=False,
            hit_date=None,
            max_high=None,
            min_low=None,
            days_to_hit=None,
        )
    )

    summary = format_summary(result)

    assert "Product: Ratio Convertible Forward" in summary
    assert "Client direction: Importer" in summary
    assert "Strike: 0.6850" in summary
    assert "Barrier direction: up" in summary
    assert "Touch rule: daily high >= 0.7050" in summary
    assert "Barrier period: continuous" in summary
    assert "Protected amount: 500,000 USD" in summary
    assert "Ratio amount: 1,000,000 USD" in summary
    assert "Expiry time zone: Tokyo" in summary


def test_format_summary_includes_price_model_comparison() -> None:
    result = result_with_path(
        BarrierPathResult(
            is_applicable=False,
            reason="expiry_date is after available market data (2026-06-12)",
            barrier_hit=False,
            hit_date=None,
            max_high=None,
            min_low=None,
            days_to_hit=None,
        )
    )
    price_model = PriceModelEvaluation(
        model_probability=41.0,
        train_rows=100,
        test_rows=50,
        positive_rate_train=75.0,
        positive_rate_test=80.0,
        baseline_probability=75.0,
        model_brier_score=0.35,
        baseline_brier_score=0.20,
        model_log_loss=1.0,
        baseline_log_loss=0.5,
        used_fallback=False,
        fallback_reason=None,
    )

    summary = format_summary(result, price_model=price_model)

    assert "Price-only model estimate:" in summary
    assert "Model probability: 41.00%" in summary
    assert "Model comparison: model underperformed baseline on Brier score" in summary


def test_format_summary_includes_external_features() -> None:
    result = result_with_path(
        BarrierPathResult(
            is_applicable=False,
            reason="expiry_date is after available market data (2026-06-12)",
            barrier_hit=False,
            hit_date=None,
            max_high=None,
            min_low=None,
            days_to_hit=None,
        )
    )
    external = ExternalFeatureSnapshot(
        as_of_date=date(2026, 6, 13),
        dxy_return_20d=1.2,
        dxy_trend_60d=-0.5,
        vix_level=15.4,
        vix_change_20d=2.1,
    )

    summary = format_summary(result, external_features=external)

    assert "External market features:" in summary
    assert "DXY return 20d: 1.20%" in summary
    assert "VIX level: 15.4000" in summary


def test_format_summary_includes_price_plus_external_model() -> None:
    result = result_with_path(
        BarrierPathResult(
            is_applicable=False,
            reason="expiry_date is after available market data (2026-06-12)",
            barrier_hit=False,
            hit_date=None,
            max_high=None,
            min_low=None,
            days_to_hit=None,
        )
    )
    price_plus_external_model = PriceModelEvaluation(
        model_probability=52.0,
        train_rows=90,
        test_rows=40,
        positive_rate_train=70.0,
        positive_rate_test=72.0,
        baseline_probability=70.0,
        model_brier_score=0.18,
        baseline_brier_score=0.22,
        model_log_loss=0.4,
        baseline_log_loss=0.6,
        used_fallback=False,
        fallback_reason=None,
    )

    summary = format_summary(result, price_plus_external_model=price_plus_external_model)

    assert "Price + external model estimate:" in summary
    assert "Model probability: 52.00%" in summary
    assert "Model comparison: model beat baseline on Brier score" in summary


def test_format_summary_includes_barrier_theory_estimate() -> None:
    result = result_with_path(
        BarrierPathResult(
            is_applicable=False,
            reason="expiry_date is after available market data (2026-06-12)",
            barrier_hit=False,
            hit_date=None,
            max_high=None,
            min_low=None,
            days_to_hit=None,
        )
    )
    theory = BarrierTheoryEvaluation(
        current_snapshot=BarrierTheorySnapshot(
            probability=72.0,
            expected_move_pct=5.0,
            distance_in_vol_units=0.8,
            barrier_z_score=0.75,
            method="driftless_log_brownian_reflection",
            fallback_reason=None,
        ),
        blended_probability=68.0,
        blend_weight=0.45,
        train_rows=100,
        test_rows=50,
        positive_rate_train=60.0,
        positive_rate_test=62.0,
        baseline_probability=60.0,
        gbm_brier_score=0.18,
        blended_brier_score=0.17,
        baseline_brier_score=0.22,
        used_fallback=False,
        fallback_reason=None,
        calibration_buckets=[],
        blended_calibration_buckets=[],
    )

    summary = format_summary(result, barrier_theory=theory)

    assert "Barrier-theory estimate:" in summary
    assert "GBM probability: 72.00%" in summary
    assert "Blended probability: 68.00%" in summary
    assert "Blend GBM weight: 0.4500" in summary
    assert "Expected move to expiry: 5.00%" in summary
    assert "GBM comparison: GBM beat baseline on Brier score" in summary
    assert "Blend comparison: blend beat baseline on Brier score" in summary


def test_format_forecast_report_uses_institutional_style_sections() -> None:
    result = result_with_path(
        BarrierPathResult(
            is_applicable=False,
            reason="expiry_date is after available market data (2026-06-12)",
            barrier_hit=False,
            hit_date=None,
            max_high=None,
            min_low=None,
            days_to_hit=None,
        )
    )
    theory = BarrierTheoryEvaluation(
        current_snapshot=BarrierTheorySnapshot(
            probability=72.0,
            expected_move_pct=5.0,
            distance_in_vol_units=0.8,
            barrier_z_score=0.75,
            method="driftless_log_brownian_reflection",
            fallback_reason=None,
        ),
        blended_probability=68.0,
        blend_weight=0.45,
        train_rows=100,
        test_rows=50,
        positive_rate_train=60.0,
        positive_rate_test=62.0,
        baseline_probability=60.0,
        gbm_brier_score=0.18,
        blended_brier_score=0.17,
        baseline_brier_score=0.22,
        used_fallback=False,
        fallback_reason=None,
        calibration_buckets=[],
        blended_calibration_buckets=[],
    )

    report = format_forecast_report(result, barrier_theory=theory)

    assert "FX BARRIER TOUCH INTELLIGENCE REPORT" in report
    assert "QUESTION" in report
    assert "PROBABILITY DISTRIBUTION" in report
    assert "Barrier touched before expiry: 68.00%" in report
    assert "Touch rule: daily high >= 0.7050" in report
    assert "Market move tested: AUD/USD rises to or above the barrier" in report
    assert "MOST LIKELY OUTCOME" in report
    assert "REFERENCE ESTIMATES" in report
    assert "TOUCH-SUPPORTING FACTORS" in report
    assert "TOUCH-OPPOSING FACTORS" in report
    assert "MODEL RISK NOTES" in report


def test_format_forecast_report_explains_downside_barrier_rule() -> None:
    result = result_with_path(
        BarrierPathResult(
            is_applicable=False,
            reason="expiry_date is after available market data (2026-06-12)",
            barrier_hit=False,
            hit_date=None,
            max_high=None,
            min_low=None,
            days_to_hit=None,
        ),
        barrier_direction="down",
        spot=0.7050,
        barrier=0.6935,
        distance_pct=-1.6312,
    )

    report = format_forecast_report(result)

    assert "Direction: down" in report
    assert "Touch rule: daily low <= 0.6935" in report
    assert "Market move tested: AUD/USD falls to or below the barrier" in report


def test_format_forecast_report_uses_actual_pair_in_market_move() -> None:
    result = result_with_path(
        BarrierPathResult(
            is_applicable=False,
            reason="expiry_date is after available market data (2026-06-12)",
            barrier_hit=False,
            hit_date=None,
            max_high=None,
            min_low=None,
            days_to_hit=None,
        ),
        pair="EUR/USD",
        spot=1.0800,
        barrier=1.1000,
        distance_pct=1.8519,
    )

    report = format_forecast_report(result)

    assert "Will EUR/USD touch the 1.1000 up barrier" in report
    assert "Market move tested: EUR/USD rises to or above the barrier" in report


def result_with_path(
    actual_path: BarrierPathResult,
    pair: str = "AUD/USD",
    barrier_direction: str = "up",
    spot: float = 0.65,
    barrier: float = 0.705,
    distance_pct: float = 8.4615,
) -> TouchProbabilityResult:
    return TouchProbabilityResult(
        product_type="Ratio Convertible Forward",
        client_direction="Importer",
        pair=pair,
        spot=spot,
        strike=0.685,
        barrier=barrier,
        barrier_direction=barrier_direction,
        protected_amount=500_000,
        ratio_amount=1_000_000,
        amount_currency="USD",
        barrier_level_period="continuous",
        expiry_time_zone="Tokyo",
        days_to_expiry=135,
        distance_pct=distance_pct,
        sample_count=422,
        touch_count=72,
        touch_probability=17.0616,
        actual_path=actual_path,
    )
