from datetime import date

from src.barrier_engine import BarrierPathResult, TouchProbabilityResult
from src.price_model import PriceModelEvaluation
from src.reporting import format_summary


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


def result_with_path(actual_path: BarrierPathResult) -> TouchProbabilityResult:
    return TouchProbabilityResult(
        product_type="Ratio Convertible Forward",
        client_direction="Importer",
        pair="AUD/USD",
        spot=0.65,
        strike=0.685,
        barrier=0.705,
        protected_amount=500_000,
        ratio_amount=1_000_000,
        amount_currency="USD",
        barrier_level_period="continuous",
        expiry_time_zone="Tokyo",
        days_to_expiry=135,
        distance_pct=8.4615,
        sample_count=422,
        touch_count=72,
        touch_probability=17.0616,
        actual_path=actual_path,
    )
