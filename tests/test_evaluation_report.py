from src.barrier_theory import BarrierTheoryEvaluation, BarrierTheorySnapshot
from src.evaluation_report import (
    PeriodEvaluation,
    SampleTradeEvaluation,
    format_evaluation_report,
    format_sample_trade_evaluation_report,
)
from src.price_model import CalibrationBucket, PriceModelEvaluation


def test_format_evaluation_report_includes_summary_and_calibration() -> None:
    evaluation = PeriodEvaluation(
        period="2y",
        market_rows=520,
        baseline_probability=87.76,
        baseline_sample_count=335,
        baseline_touch_count=294,
        volatility_adjusted_probability=90.48,
        volatility_comparable_sample_count=63,
        barrier_theory_model=theory_evaluation(72.0, 0.19),
        price_only_model=model_evaluation(41.04, 0.3597),
        price_plus_external_model=model_evaluation(54.82, 0.6104),
    )

    report = format_evaluation_report([evaluation])

    assert "Model evaluation report" in report
    assert "Period | Rows" in report
    assert "Price dBrier" in report
    assert "GBM dBrier" in report
    assert "Blend dBrier" in report
    assert "Ext dBrier" in report
    assert "2y" in report
    assert "87.76%" in report
    assert "GBM:" in report
    assert "GBM blend:" in report
    assert "Price-only:" in report
    assert "Price + external:" in report
    assert "0-20%: n=1, avg_pred=10.00%, actual_hit=0.00%" in report


def test_format_sample_trade_evaluation_report_includes_each_trade_summary() -> None:
    evaluation = SampleTradeEvaluation(
        sample_name="near_up_30d",
        sample_description="30-day near up barrier",
        barrier_direction="up",
        tenor_days=30,
        barrier_distance_pct=1.5,
        period_evaluation=PeriodEvaluation(
            period="5y",
            market_rows=1300,
            baseline_probability=63.1,
            baseline_sample_count=1279,
            baseline_touch_count=807,
            volatility_adjusted_probability=61.2,
            volatility_comparable_sample_count=250,
            barrier_theory_model=theory_evaluation(60.0, 0.18),
            price_only_model=model_evaluation(58.0, 0.19),
            price_plus_external_model=model_evaluation(62.0, 0.18),
        ),
    )

    report = format_sample_trade_evaluation_report([evaluation])

    assert "Sample trade model evaluation report" in report
    assert "Trade" in report
    assert "Dir" in report
    assert "near_up_30d" in report
    assert "30d" in report
    assert "1.50%" in report
    assert "63.10%" in report
    assert "GBM prob" in report
    assert "GBM dBrier" in report
    assert "Blend prob" in report
    assert "Blend dBrier" in report
    assert "Blend w" in report
    assert "Price dBrier" in report
    assert "Ext dBrier" in report


def model_evaluation(probability: float, brier_score: float) -> PriceModelEvaluation:
    return PriceModelEvaluation(
        model_probability=probability,
        train_rows=100,
        test_rows=5,
        positive_rate_train=75.0,
        positive_rate_test=80.0,
        baseline_probability=75.0,
        model_brier_score=brier_score,
        baseline_brier_score=0.2,
        model_log_loss=1.0,
        baseline_log_loss=0.5,
        used_fallback=False,
        fallback_reason=None,
        calibration_buckets=[
            CalibrationBucket(0, 20, 1, 10.0, 0.0),
            CalibrationBucket(20, 40, 1, 30.0, 100.0),
            CalibrationBucket(40, 60, 1, 50.0, 100.0),
            CalibrationBucket(60, 80, 1, 70.0, 100.0),
            CalibrationBucket(80, 100, 1, 90.0, 100.0),
        ],
    )


def theory_evaluation(probability: float, brier_score: float) -> BarrierTheoryEvaluation:
    return BarrierTheoryEvaluation(
        current_snapshot=BarrierTheorySnapshot(
            probability=probability,
            expected_move_pct=5.0,
            distance_in_vol_units=0.8,
            barrier_z_score=0.75,
            method="driftless_log_brownian_reflection",
            fallback_reason=None,
        ),
        blended_probability=probability + 1,
        blend_weight=0.5,
        train_rows=100,
        test_rows=5,
        positive_rate_train=75.0,
        positive_rate_test=80.0,
        baseline_probability=75.0,
        gbm_brier_score=brier_score,
        blended_brier_score=brier_score - 0.01,
        baseline_brier_score=0.2,
        used_fallback=False,
        fallback_reason=None,
        calibration_buckets=[
            CalibrationBucket(0, 20, 1, 10.0, 0.0),
            CalibrationBucket(20, 40, 1, 30.0, 100.0),
            CalibrationBucket(40, 60, 1, 50.0, 100.0),
            CalibrationBucket(60, 80, 1, 70.0, 100.0),
            CalibrationBucket(80, 100, 1, 90.0, 100.0),
        ],
        blended_calibration_buckets=[
            CalibrationBucket(0, 20, 1, 12.0, 0.0),
            CalibrationBucket(20, 40, 1, 32.0, 100.0),
            CalibrationBucket(40, 60, 1, 52.0, 100.0),
            CalibrationBucket(60, 80, 1, 72.0, 100.0),
            CalibrationBucket(80, 100, 1, 92.0, 100.0),
        ],
    )
