"""Live monitoring logic for real barrier-option positions.

Persistence lives in the SQLite store (``src.storage.repository.monitored_positions``);
this module holds only the pure logic so it stays testable without a database.
A *position* is a plain dict (the shape returned by
``repository.load_monitored_positions``) keyed by ``id`` (the unique label).

The backtest helper ``barrier_engine.evaluate_actual_path`` requires the whole
trade window to be in the past. A live position usually expires in the FUTURE, so
here we evaluate touches over ``[trade_date, min(expiry, last_available)]`` instead.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from typing import Callable

import pandas as pd

from src.pricing.barrier_engine import Trade, normalize_direction, normalize_prices


# Position lifecycle.
STATUS_ACTIVE = "active"
STATUS_TRIGGERED = "triggered"
STATUS_EXPIRED = "expired"

# Fields that define the trade (the rest of a position dict is monitoring state).
_TRADE_FIELDS = (
    "pair",
    "trade_date",
    "spot",
    "strike",
    "barrier",
    "expiry_date",
    "barrier_direction",
    "product_type",
    "client_direction",
    "protected_amount",
    "ratio_amount",
    "amount_currency",
    "barrier_level_period",
    "expiry_time_zone",
)


@dataclass(frozen=True)
class LivePathResult:
    """Outcome of checking a live position against available market data."""

    barrier_hit: bool
    hit_date: date | None
    hit_price: float | None
    latest_date: date | None
    latest_close: float | None
    is_expired: bool
    reason: str | None


@dataclass(frozen=True)
class PositionUpdate:
    """What changed for one position after a check run."""

    position_id: str
    previous_status: str
    new_status: str
    path: LivePathResult
    newly_triggered: bool
    should_alert: bool


def position_to_trade(position: dict) -> Trade:
    """Build a Trade from a position dict, parsing ISO date strings."""

    def _as_date(value: object) -> date:
        return value if isinstance(value, date) else date.fromisoformat(str(value))

    return Trade(
        pair=position["pair"],
        trade_date=_as_date(position["trade_date"]),
        spot=float(position["spot"]),
        strike=float(position["strike"]),
        barrier=float(position["barrier"]),
        expiry_date=_as_date(position["expiry_date"]),
        barrier_direction=position.get("barrier_direction", "up"),
        product_type=position.get("product_type", "Ratio Convertible Forward"),
        client_direction=position.get("client_direction"),
        protected_amount=position.get("protected_amount"),
        ratio_amount=position.get("ratio_amount"),
        amount_currency=position.get("amount_currency"),
        barrier_level_period=position.get("barrier_level_period", "continuous"),
        expiry_time_zone=position.get("expiry_time_zone", "Tokyo"),
    )


def evaluate_live_path(trade: Trade, prices: pd.DataFrame, as_of: date | None = None) -> LivePathResult:
    """Has the barrier been touched between trade_date and the latest data?

    Unlike the backtest path checker this does not require the expiry to be in the
    past — it scans up to ``min(expiry_date, last_available_date)``.
    """

    direction = normalize_direction(trade.barrier_direction)
    frame = normalize_prices(prices, trade.pair)
    first_available = frame["date"].min()
    last_available = frame["date"].max()
    as_of = as_of or last_available

    if trade.trade_date < first_available:
        return LivePathResult(
            barrier_hit=False,
            hit_date=None,
            hit_price=None,
            latest_date=last_available,
            latest_close=float(frame.iloc[-1]["close"]),
            is_expired=as_of >= trade.expiry_date,
            reason=f"trade_date is before available market data ({first_available})",
        )

    cutoff = min(trade.expiry_date, last_available)
    window = frame[(frame["date"] >= trade.trade_date) & (frame["date"] <= cutoff)]
    latest_close = float(frame[frame["date"] <= cutoff].iloc[-1]["close"]) if not window.empty else None

    is_expired = as_of >= trade.expiry_date

    if window.empty:
        return LivePathResult(
            barrier_hit=False,
            hit_date=None,
            hit_price=None,
            latest_date=last_available,
            latest_close=latest_close,
            is_expired=is_expired,
            reason="no market data inside trade window yet",
        )

    if direction == "up":
        hits = window[window["high"] >= trade.barrier]
    else:
        hits = window[window["low"] <= trade.barrier]

    if hits.empty:
        return LivePathResult(
            barrier_hit=False,
            hit_date=None,
            hit_price=None,
            latest_date=cutoff,
            latest_close=latest_close,
            is_expired=is_expired,
            reason=None,
        )

    hit_row = hits.iloc[0]
    hit_price = float(hit_row["high"]) if direction == "up" else float(hit_row["low"])
    return LivePathResult(
        barrier_hit=True,
        hit_date=hit_row["date"],
        hit_price=hit_price,
        latest_date=cutoff,
        latest_close=latest_close,
        is_expired=is_expired,
        reason=None,
    )


def _next_status(previous_status: str, path: LivePathResult) -> str:
    if previous_status in {STATUS_TRIGGERED, STATUS_EXPIRED}:
        return previous_status  # terminal states never revert
    if path.barrier_hit:
        return STATUS_TRIGGERED
    if path.is_expired:
        return STATUS_EXPIRED
    return STATUS_ACTIVE


def check_positions(
    data: dict,
    price_loader: Callable[[str], pd.DataFrame],
    as_of: date | None = None,
    now_iso: str | None = None,
) -> list[PositionUpdate]:
    """Evaluate every position in-place and return the updates.

    ``price_loader`` maps a pair label to an OHLC frame (injected so tests and the
    CLI can supply data without hitting the network here). ``now_iso`` stamps
    ``last_checked``/``alert_sent_at`` so the caller controls the clock.
    """

    updates: list[PositionUpdate] = []
    price_cache: dict[str, pd.DataFrame] = {}

    for position in data.get("positions", []):
        position_id = str(position.get("id", "<unnamed>"))
        previous_status = position.get("status", STATUS_ACTIVE)
        already_alerted = bool(position.get("alert_sent_at"))

        # A position is "done" only when it is expired, or triggered AND the alert
        # was actually delivered. A position that triggered but whose email failed
        # (alert_sent_at still empty) is NOT skipped, so the next run retries it.
        if previous_status == STATUS_EXPIRED or (previous_status == STATUS_TRIGGERED and already_alerted):
            if now_iso:
                position["last_checked"] = now_iso
            continue

        pair = position["pair"]
        if pair not in price_cache:
            price_cache[pair] = price_loader(pair)
        trade = position_to_trade(position)
        path = evaluate_live_path(trade, price_cache[pair], as_of=as_of)
        new_status = _next_status(previous_status, path)

        if now_iso:
            position["last_checked"] = now_iso
        position["status"] = new_status

        newly_triggered = new_status == STATUS_TRIGGERED and previous_status != STATUS_TRIGGERED
        if new_status == STATUS_TRIGGERED and not position.get("triggered_date"):
            # Record trigger metadata once (also covers a retry where status was
            # already 'triggered' but the fields were somehow not persisted).
            position["triggered_date"] = path.hit_date.isoformat() if path.hit_date else None
            position["triggered_price"] = path.hit_price
        if new_status == STATUS_EXPIRED and previous_status != STATUS_EXPIRED:
            position.setdefault("triggered_date", None)

        # Alert whenever the position is triggered and not yet successfully
        # alerted. This fires on the first touch AND retries a prior failed send
        # (where status is already 'triggered' but alert_sent_at is still empty).
        should_alert = new_status == STATUS_TRIGGERED and not already_alerted

        updates.append(
            PositionUpdate(
                position_id=position_id,
                previous_status=previous_status,
                new_status=new_status,
                path=path,
                newly_triggered=newly_triggered,
                should_alert=should_alert,
            )
        )

    return updates


def mark_alerted(data: dict, position_id: str, now_iso: str) -> None:
    for position in data.get("positions", []):
        if str(position.get("id")) == position_id:
            position["alert_sent_at"] = now_iso
            return


def build_alert_message(position: dict, update: PositionUpdate) -> str:
    """Short email body for a newly triggered position."""

    path = update.path
    direction = position.get("barrier_direction", "up")
    arrow = "high>=" if normalize_direction(direction) == "up" else "low<="
    pair = position.get("pair", "?")
    barrier = position.get("barrier")
    hit_date = path.hit_date.isoformat() if path.hit_date else "?"
    label = position.get("id", "position")
    product = position.get("product_type", "barrier trade")
    body = (
        f"BARRIER HIT [{label}]: {pair} {arrow}{barrier} touched on {hit_date}. "
        f"Your {product} barrier triggered - time to act."
    )
    if path.latest_close is not None:
        body += f" Latest close {path.latest_close:.4f}."
    return body


def position_summary_row(position: dict) -> dict:
    """Flat dict used by the CLI ``list`` table and JSON output."""

    row = {field: position.get(field) for field in ("id", *_TRADE_FIELDS)}
    row.update(
        status=position.get("status", STATUS_ACTIVE),
        triggered_date=position.get("triggered_date"),
        triggered_price=position.get("triggered_price"),
        alert_sent_at=position.get("alert_sent_at"),
        last_checked=position.get("last_checked"),
    )
    return row


def new_position(
    position_id: str,
    *,
    pair: str,
    trade_date: date,
    spot: float,
    strike: float,
    barrier: float,
    expiry_date: date,
    barrier_direction: str = "up",
    product_type: str = "Ratio Convertible Forward",
    client_direction: str | None = None,
    note: str | None = None,
) -> dict:
    """Create a position dict with monitoring state initialised to active."""

    # Validate the direction eagerly so bad input fails at add-time, not check-time.
    normalize_direction(barrier_direction)
    return {
        "id": position_id,
        "pair": pair,
        "trade_date": trade_date.isoformat(),
        "spot": float(spot),
        "strike": float(strike),
        "barrier": float(barrier),
        "expiry_date": expiry_date.isoformat(),
        "barrier_direction": barrier_direction,
        "product_type": product_type,
        "client_direction": client_direction,
        "note": note,
        "status": STATUS_ACTIVE,
        "triggered_date": None,
        "triggered_price": None,
        "alert_sent_at": None,
        "last_checked": None,
    }


def update_to_dict(update: PositionUpdate) -> dict:
    payload = {
        "position_id": update.position_id,
        "previous_status": update.previous_status,
        "new_status": update.new_status,
        "newly_triggered": update.newly_triggered,
        "should_alert": update.should_alert,
        "path": asdict(update.path),
    }
    # Make dates JSON-serialisable.
    path = payload["path"]
    for key in ("hit_date", "latest_date"):
        if isinstance(path.get(key), date):
            path[key] = path[key].isoformat()
    return payload
