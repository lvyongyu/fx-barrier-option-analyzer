from datetime import date

from src.barrier_engine import BarrierPathResult, TouchProbabilityResult
from src.reporting import format_summary


def test_format_summary_marks_actual_path_not_applicable() -> None:
    result = TouchProbabilityResult(
        pair="AUD/USD",
        spot=0.65,
        barrier=0.705,
        days_to_expiry=135,
        distance_pct=8.4615,
        sample_count=422,
        touch_count=72,
        touch_probability=17.0616,
        actual_path=BarrierPathResult(
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
    result = TouchProbabilityResult(
        pair="AUD/USD",
        spot=0.65,
        barrier=0.705,
        days_to_expiry=135,
        distance_pct=8.4615,
        sample_count=422,
        touch_count=72,
        touch_probability=17.0616,
        actual_path=BarrierPathResult(
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
