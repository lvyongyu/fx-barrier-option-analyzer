from __future__ import annotations

from src.barrier_engine import TouchProbabilityResult


def format_summary(result: TouchProbabilityResult) -> str:
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
