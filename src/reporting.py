from __future__ import annotations

from src.barrier_engine import TouchProbabilityResult


def format_summary(result: TouchProbabilityResult) -> str:
    lines = [
        "AUD/USD barrier analysis",
        "",
        f"Spot: {result.spot:.4f}",
        f"Barrier: {result.barrier:.4f}",
        f"Distance to barrier: {result.distance_pct:.2f}%",
        f"Days to expiry: {result.days_to_expiry}",
        "",
        f"Historical samples: {result.sample_count}",
        f"Touch count: {result.touch_count}",
        f"Historical touch probability: {result.touch_probability:.2f}%",
    ]

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
