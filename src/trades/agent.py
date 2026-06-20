from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
import re
from typing import Any

from src.data.data_loader import DEFAULT_PAIR, normalize_pair_label


@dataclass(frozen=True)
class ParsedForecastRequest:
    intent: str
    pair: str
    barrier_direction: str
    horizon_days: int | None = None
    expiry_date: date | None = None
    forward_start_date: date | None = None
    barrier: float | None = None
    move_pct: float | None = None
    spot_source: str = "latest_market_close"
    strike_source: str = "spot_placeholder"
    needs_model_call: bool = True
    needs_forward_start_model: bool = False
    assumptions: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class ForecastReview:
    summary: str
    is_result_self_consistent: bool
    input_warnings: tuple[str, ...]
    model_warnings: tuple[str, ...]
    plain_english_explanation: tuple[str, ...]
    suggested_follow_up_questions: tuple[str, ...]


def parse_forecast_request(text: str, analysis_date: date | None = None) -> ParsedForecastRequest:
    clean = text.strip()
    pair = _extract_pair(clean)
    barrier_direction = _extract_direction(clean)
    move_pct = _extract_move_pct(clean, barrier_direction)
    dates = _extract_dates(clean)
    horizon_days = _extract_horizon_days(clean)
    barrier = _extract_absolute_barrier(clean) if move_pct is None else None
    assumptions: list[str] = []
    warnings: list[str] = []

    forward_start_date = None
    expiry_date = None
    intent = "absolute_touch_forecast" if barrier is not None else "relative_touch_forecast"

    if len(dates) >= 2 and _has_forward_start_language(clean):
        forward_start_date, expiry_date = dates[0], dates[1]
        intent = "forward_start_touch_forecast"
    elif dates:
        expiry_date = dates[-1]

    needs_forward_start_model = False
    spot_source = "latest_market_close"
    if forward_start_date and analysis_date and forward_start_date > analysis_date:
        needs_forward_start_model = True
        spot_source = "project_forward_start_distribution"
        warnings.append("forward start date is after analysis date; future spot must be modelled as a distribution")

    if move_pct is None and barrier is None:
        warnings.append("no relative move or absolute barrier was detected")
    if horizon_days is None and expiry_date is None:
        if move_pct is not None:
            horizon_days = 92
            assumptions.append("defaulted horizon to 92 calendar days for a 3-month forecast")
        else:
            warnings.append("no expiry date or forecast horizon was detected")

    return ParsedForecastRequest(
        intent=intent,
        pair=pair,
        barrier_direction=barrier_direction,
        horizon_days=horizon_days,
        expiry_date=expiry_date,
        forward_start_date=forward_start_date,
        barrier=barrier,
        move_pct=move_pct,
        spot_source=spot_source,
        needs_model_call=not needs_forward_start_model,
        needs_forward_start_model=needs_forward_start_model,
        assumptions=tuple(assumptions),
        warnings=tuple(warnings),
    )


def review_forecast_payload(payload: dict[str, Any]) -> ForecastReview:
    result = payload.get("result") or {}
    features = payload.get("features") or {}
    volatility = payload.get("volatility_adjustment") or {}
    theory = payload.get("barrier_theory") or {}
    price_model = payload.get("price_model") or {}

    pair = result.get("pair", "the selected pair")
    spot = _optional_float(result.get("spot"))
    barrier = _optional_float(result.get("barrier"))
    direction = str(result.get("barrier_direction", "up"))
    days = result.get("days_to_expiry")
    probability = _primary_probability(result, volatility, theory)

    input_warnings: list[str] = []
    model_warnings: list[str] = [
        "This is a path-touch probability, not an expiry close or payoff probability."
    ]
    explanations: list[str] = []

    if spot is not None and barrier is not None:
        if _is_already_breached(spot, barrier, direction):
            input_warnings.append("ALREADY_BREACHED: spot is already beyond the barrier in the selected direction.")
        distance_pct = abs((barrier - spot) / spot * 100) if spot > 0 else None
        if distance_pct is not None:
            explanations.append(f"The barrier is {distance_pct:.2f}% from spot.")

    if days is not None:
        explanations.append(f"The forecast window is {days} calendar days.")

    sample_count = result.get("sample_count")
    touch_count = result.get("touch_count")
    if sample_count is not None and touch_count is not None:
        explanations.append(f"Historical windows touched the barrier {touch_count} times out of {sample_count}.")
        if int(sample_count) < 100:
            model_warnings.append("Historical sample count is low.")

    expected_move = ((theory.get("current_snapshot") or {}).get("expected_move_pct"))
    if expected_move is not None:
        explanations.append(f"Estimated move to expiry is {float(expected_move):.2f}%.")

    blend_weight = theory.get("blend_weight")
    if blend_weight is not None and float(blend_weight) == 0:
        model_warnings.append("The final calibrated estimate assigns 0% weight to GBM.")

    gbm_probability = ((theory.get("current_snapshot") or {}).get("probability"))
    if probability is not None and gbm_probability is not None and abs(float(probability) - float(gbm_probability)) >= 20:
        model_warnings.append("GBM and final calibrated estimates disagree materially.")

    model_brier = price_model.get("model_brier_score")
    baseline_brier = price_model.get("baseline_brier_score")
    if model_brier is not None and baseline_brier is not None and float(model_brier) > float(baseline_brier):
        model_warnings.append("The price-only logistic model underperformed the historical baseline.")

    probability_text = f"{probability:.2f}%" if probability is not None else "n/a"
    summary = (
        f"The model estimates {probability_text} probability that {pair} touches the "
        f"{barrier:.4f} {direction} barrier within {days} calendar days."
        if barrier is not None and days is not None
        else f"The model estimates {probability_text} barrier-touch probability for {pair}."
    )

    return ForecastReview(
        summary=summary,
        is_result_self_consistent=not input_warnings,
        input_warnings=tuple(input_warnings),
        model_warnings=tuple(model_warnings),
        plain_english_explanation=tuple(explanations),
        suggested_follow_up_questions=(
            "What is the probability of touching both an upper and lower barrier?",
            "What is the probability of finishing beyond the barrier at expiry?",
            "How sensitive is the result to using a longer history window?",
        ),
    )


def dataclass_to_json_dict(value: Any) -> dict[str, Any]:
    return asdict(value)


def _extract_pair(text: str) -> str:
    upper = text.upper()
    match = re.search(r"\b([A-Z]{3})\s*[/\-]?\s*([A-Z]{3})\b", upper)
    if match:
        return normalize_pair_label(f"{match.group(1)}/{match.group(2)}")
    compact = upper.replace(" ", "")
    for candidate in ["AUDUSD", "EURUSD", "GBPUSD", "USDJPY", "USDCNH", "AUDCNH", "EURJPY", "AUDJPY"]:
        if candidate in compact:
            return normalize_pair_label(candidate)
    return DEFAULT_PAIR


def _extract_direction(text: str) -> str:
    lower = text.lower()
    down_words = ["跌", "下跌", "跌破", "below", "lower", "down", "fall", "falls", "drop", "drops"]
    up_words = ["涨", "上涨", "涨到", "above", "higher", "up", "rise", "rises", "touch"]
    if any(word in lower for word in down_words):
        return "down"
    if any(word in lower for word in up_words):
        return "up"
    return "up"


def _extract_move_pct(text: str, direction: str) -> float | None:
    match = re.search(r"([+-]?\d+(?:\.\d+)?)\s*%", text)
    if not match:
        return None
    value = float(match.group(1))
    if value < 0:
        return value
    if direction == "down":
        return -abs(value)
    return abs(value)


def _extract_absolute_barrier(text: str) -> float | None:
    numbers = [float(match.group(1)) for match in re.finditer(r"(\d+\.\d+)", text)]
    plausible = [number for number in numbers if 0.01 <= number <= 300]
    return plausible[-1] if plausible else None


def _extract_dates(text: str) -> list[date]:
    dates: list[date] = []
    for match in re.finditer(r"(20\d{2}-\d{2}-\d{2})", text):
        dates.append(date.fromisoformat(match.group(1)))
    return dates


def _extract_horizon_days(text: str) -> int | None:
    lower = text.lower()
    month_match = re.search(r"(\d+)\s*(?:个月|月|months?|m)\b", lower)
    if month_match:
        return int(month_match.group(1)) * 31
    day_match = re.search(r"(\d+)\s*(?:天|days?|d)\b", lower)
    if day_match:
        return int(day_match.group(1))
    if "3个月" in lower or "三个月" in lower or "three months" in lower:
        return 92
    return None


def _has_forward_start_language(text: str) -> bool:
    lower = text.lower()
    return "从" in lower or "between" in lower or "from" in lower


def _primary_probability(
    result: dict[str, Any],
    volatility: dict[str, Any],
    theory: dict[str, Any],
) -> float | None:
    if theory.get("blended_probability") is not None:
        return float(theory["blended_probability"])
    current_snapshot = theory.get("current_snapshot") or {}
    if current_snapshot.get("probability") is not None:
        return float(current_snapshot["probability"])
    if volatility.get("volatility_adjusted_probability") is not None:
        return float(volatility["volatility_adjusted_probability"])
    if result.get("touch_probability") is not None:
        return float(result["touch_probability"])
    return None


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _is_already_breached(spot: float, barrier: float, direction: str) -> bool:
    if direction == "down":
        return spot <= barrier
    return spot >= barrier
