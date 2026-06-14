from datetime import date

from src.agent import parse_forecast_request, review_forecast_payload


def test_parse_chinese_relative_downside_request() -> None:
    parsed = parse_forecast_request("想预测一下未来3个月audusd是否跌1.5%")

    assert parsed.intent == "relative_touch_forecast"
    assert parsed.pair == "AUD/USD"
    assert parsed.horizon_days == 92
    assert parsed.move_pct == -1.5
    assert parsed.barrier_direction == "down"
    assert parsed.spot_source == "latest_market_close"


def test_parse_english_absolute_upside_request() -> None:
    parsed = parse_forecast_request("Will EUR/USD touch 1.10 before 2026-07-13?")

    assert parsed.intent == "absolute_touch_forecast"
    assert parsed.pair == "EUR/USD"
    assert parsed.expiry_date == date(2026, 7, 13)
    assert parsed.barrier == 1.10
    assert parsed.barrier_direction == "up"


def test_parse_forward_start_request_requires_future_spot_distribution() -> None:
    parsed = parse_forecast_request(
        "从2026-09-30到2026-12-30 AUD/USD 会不会跌破0.6935？",
        analysis_date=date(2026, 6, 14),
    )

    assert parsed.intent == "forward_start_touch_forecast"
    assert parsed.forward_start_date == date(2026, 9, 30)
    assert parsed.expiry_date == date(2026, 12, 30)
    assert parsed.barrier == 0.6935
    assert parsed.barrier_direction == "down"
    assert parsed.spot_source == "project_forward_start_distribution"
    assert parsed.needs_model_call is False
    assert parsed.needs_forward_start_model is True
    assert parsed.warnings


def test_review_forecast_payload_flags_gbm_zero_weight_and_touch_probability_context() -> None:
    review = review_forecast_payload(make_payload())

    assert "90.51%" in review.summary
    assert review.is_result_self_consistent is True
    assert any("path-touch probability" in warning for warning in review.model_warnings)
    assert any("0% weight to GBM" in warning for warning in review.model_warnings)
    assert any("1.50% from spot" in explanation for explanation in review.plain_english_explanation)


def test_review_forecast_payload_flags_already_breached() -> None:
    payload = make_payload()
    payload["result"]["barrier_direction"] = "up"
    payload["result"]["spot"] = 0.7049
    payload["result"]["barrier"] = 0.6935

    review = review_forecast_payload(payload)

    assert review.is_result_self_consistent is False
    assert any("ALREADY_BREACHED" in warning for warning in review.input_warnings)


def make_payload() -> dict[str, object]:
    return {
        "result": {
            "pair": "AUD/USD",
            "spot": 0.704871,
            "strike": 0.704871,
            "barrier": 0.694298,
            "barrier_direction": "down",
            "days_to_expiry": 92,
            "sample_count": 1235,
            "touch_count": 1032,
            "touch_probability": 83.56,
        },
        "features": {
            "as_of_date": "2026-06-13",
        },
        "volatility_adjustment": {
            "volatility_adjusted_probability": 94.24,
        },
        "barrier_theory": {
            "blended_probability": 90.51,
            "blend_weight": 0.0,
            "current_snapshot": {
                "probability": 75.47,
                "expected_move_pct": 4.84,
            },
        },
        "price_model": {
            "model_brier_score": 0.3,
            "baseline_brier_score": 0.2,
        },
    }
