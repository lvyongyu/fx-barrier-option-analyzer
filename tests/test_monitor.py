import sqlite3
from datetime import date

import pandas as pd

from src.barrier_engine import Trade
from src.monitor import (
    STATUS_ACTIVE,
    STATUS_EXPIRED,
    STATUS_TRIGGERED,
    build_alert_message,
    check_positions,
    evaluate_live_path,
    mark_alerted,
    new_position,
    position_to_trade,
)
from src.repository import (
    init_db,
    load_monitored_positions,
    monitored_position_label_exists,
    save_monitored_position,
    table_count,
    update_monitored_position_state,
)


def row(day: str, high: float, low: float, close: float) -> dict[str, object]:
    return {
        "date": day,
        "pair": "AUD/USD",
        "open": close,
        "high": high,
        "low": low,
        "close": close,
    }


def prices(*rows: dict[str, object]) -> pd.DataFrame:
    return pd.DataFrame(list(rows))


# --- evaluate_live_path -----------------------------------------------------


def test_live_up_barrier_detects_touch_before_future_expiry() -> None:
    # Expiry is in the future relative to the data, which the backtest checker
    # would reject; the live checker must still detect the touch.
    trade = Trade("AUD/USD", date(2026, 6, 1), 0.685, 0.685, 0.6935, date(2026, 12, 30), "up")
    frame = prices(
        row("2026-06-01", high=0.6860, low=0.6840, close=0.6850),
        row("2026-06-12", high=0.6940, low=0.6880, close=0.6930),
        row("2026-06-15", high=0.6920, low=0.6890, close=0.6900),
    )

    result = evaluate_live_path(trade, frame, as_of=date(2026, 6, 15))

    assert result.barrier_hit is True
    assert result.hit_date == date(2026, 6, 12)
    assert result.hit_price == 0.6940
    assert result.is_expired is False


def test_live_down_barrier_detects_touch() -> None:
    trade = Trade("AUD/USD", date(2026, 6, 1), 0.685, 0.685, 0.6770, date(2026, 12, 30), "down")
    frame = prices(
        row("2026-06-01", high=0.6860, low=0.6840, close=0.6850),
        row("2026-06-10", high=0.6830, low=0.6765, close=0.6780),
    )

    result = evaluate_live_path(trade, frame, as_of=date(2026, 6, 15))

    assert result.barrier_hit is True
    assert result.hit_date == date(2026, 6, 10)
    assert result.hit_price == 0.6765


def test_live_no_touch_not_expired() -> None:
    trade = Trade("AUD/USD", date(2026, 6, 1), 0.685, 0.685, 0.6935, date(2026, 12, 30), "up")
    frame = prices(
        row("2026-06-01", high=0.6860, low=0.6840, close=0.6850),
        row("2026-06-15", high=0.6900, low=0.6880, close=0.6890),
    )

    result = evaluate_live_path(trade, frame, as_of=date(2026, 6, 15))

    assert result.barrier_hit is False
    assert result.is_expired is False
    assert result.latest_close == 0.6890


def test_live_expired_without_touch() -> None:
    trade = Trade("AUD/USD", date(2026, 6, 1), 0.685, 0.685, 0.6935, date(2026, 6, 10), "up")
    frame = prices(
        row("2026-06-01", high=0.6860, low=0.6840, close=0.6850),
        row("2026-06-10", high=0.6900, low=0.6880, close=0.6890),
    )

    result = evaluate_live_path(trade, frame, as_of=date(2026, 6, 15))

    assert result.barrier_hit is False
    assert result.is_expired is True


# --- check_positions status transitions -------------------------------------


def _loader(frame: pd.DataFrame):
    return lambda pair: frame


def test_check_marks_triggered_and_flags_alert() -> None:
    data = {
        "positions": [
            new_position(
                "audusd",
                pair="AUD/USD",
                trade_date=date(2026, 6, 1),
                spot=0.685,
                strike=0.685,
                barrier=0.6935,
                expiry_date=date(2026, 12, 30),
                barrier_direction="up",
            )
        ]
    }
    frame = prices(
        row("2026-06-01", high=0.6860, low=0.6840, close=0.6850),
        row("2026-06-12", high=0.6940, low=0.6880, close=0.6930),
    )

    updates = check_positions(data, _loader(frame), as_of=date(2026, 6, 15), now_iso="2026-06-15T00:00:00+00:00")

    assert len(updates) == 1
    assert updates[0].new_status == STATUS_TRIGGERED
    assert updates[0].newly_triggered is True
    assert updates[0].should_alert is True
    position = data["positions"][0]
    assert position["status"] == STATUS_TRIGGERED
    assert position["triggered_date"] == "2026-06-12"
    assert position["last_checked"] == "2026-06-15T00:00:00+00:00"


def test_check_does_not_realert_already_triggered() -> None:
    position = new_position(
        "audusd",
        pair="AUD/USD",
        trade_date=date(2026, 6, 1),
        spot=0.685,
        strike=0.685,
        barrier=0.6935,
        expiry_date=date(2026, 12, 30),
    )
    position["status"] = STATUS_TRIGGERED
    position["alert_sent_at"] = "2026-06-12T00:00:00+00:00"
    data = {"positions": [position]}
    frame = prices(row("2026-06-12", high=0.6940, low=0.6880, close=0.6930))

    updates = check_positions(data, _loader(frame), as_of=date(2026, 6, 15), now_iso="2026-06-15T00:00:00+00:00")

    # Terminal positions produce no update and no alert.
    assert updates == []
    assert data["positions"][0]["status"] == STATUS_TRIGGERED


def test_check_retries_alert_when_triggered_but_not_alerted() -> None:
    # Simulates a prior run where the barrier was detected (status set to
    # triggered) but the SMS failed, so alert_sent_at is still empty.
    position = new_position(
        "audusd",
        pair="AUD/USD",
        trade_date=date(2026, 6, 1),
        spot=0.685,
        strike=0.685,
        barrier=0.6935,
        expiry_date=date(2026, 12, 30),
    )
    position["status"] = STATUS_TRIGGERED
    position["triggered_date"] = "2026-06-12"
    position["alert_sent_at"] = None
    data = {"positions": [position]}
    frame = prices(
        row("2026-06-01", high=0.6860, low=0.6840, close=0.6850),
        row("2026-06-12", high=0.6940, low=0.6880, close=0.6930),
    )

    updates = check_positions(data, _loader(frame), as_of=date(2026, 6, 15))

    assert len(updates) == 1
    assert updates[0].new_status == STATUS_TRIGGERED
    assert updates[0].newly_triggered is False  # not a fresh trigger
    assert updates[0].should_alert is True  # but still needs alerting (retry)


def test_alert_suppressed_when_already_alerted_same_run_state() -> None:
    position = new_position(
        "audusd",
        pair="AUD/USD",
        trade_date=date(2026, 6, 1),
        spot=0.685,
        strike=0.685,
        barrier=0.6935,
        expiry_date=date(2026, 12, 30),
    )
    # Status still active but alert already recorded -> should not re-alert.
    position["alert_sent_at"] = "2026-06-12T00:00:00+00:00"
    data = {"positions": [position]}
    frame = prices(
        row("2026-06-01", high=0.6860, low=0.6840, close=0.6850),
        row("2026-06-12", high=0.6940, low=0.6880, close=0.6930),
    )

    updates = check_positions(data, _loader(frame), as_of=date(2026, 6, 15))

    assert updates[0].newly_triggered is True
    assert updates[0].should_alert is False


def test_check_marks_expired() -> None:
    data = {
        "positions": [
            new_position(
                "audusd",
                pair="AUD/USD",
                trade_date=date(2026, 6, 1),
                spot=0.685,
                strike=0.685,
                barrier=0.6935,
                expiry_date=date(2026, 6, 10),
            )
        ]
    }
    frame = prices(
        row("2026-06-01", high=0.6860, low=0.6840, close=0.6850),
        row("2026-06-10", high=0.6900, low=0.6880, close=0.6890),
    )

    updates = check_positions(data, _loader(frame), as_of=date(2026, 6, 15))

    assert updates[0].new_status == STATUS_EXPIRED
    assert updates[0].should_alert is False


# --- message + round-trip ----------------------------------------------------


def test_build_alert_message_mentions_pair_barrier_and_date() -> None:
    position = new_position(
        "audusd-0935",
        pair="AUD/USD",
        trade_date=date(2026, 6, 1),
        spot=0.685,
        strike=0.685,
        barrier=0.6935,
        expiry_date=date(2026, 12, 30),
    )
    data = {"positions": [position]}
    frame = prices(
        row("2026-06-01", high=0.6860, low=0.6840, close=0.6850),
        row("2026-06-12", high=0.6940, low=0.6880, close=0.6930),
    )
    updates = check_positions(data, _loader(frame), as_of=date(2026, 6, 15))

    message = build_alert_message(position, updates[0])

    assert "AUD/USD" in message
    assert "0.6935" in message
    assert "2026-06-12" in message


def test_positions_db_round_trip_and_status_update() -> None:
    position = new_position(
        "audusd",
        pair="AUD/USD",
        trade_date=date(2026, 6, 1),
        spot=0.685,
        strike=0.685,
        barrier=0.6935,
        expiry_date=date(2026, 12, 30),
    )

    with sqlite3.connect(":memory:") as connection:
        connection.row_factory = sqlite3.Row
        init_db(connection)

        assert monitored_position_label_exists(connection, "audusd") is False
        save_monitored_position(connection, position)
        assert table_count(connection, "monitored_positions") == 1
        assert monitored_position_label_exists(connection, "audusd") is True

        loaded = load_monitored_positions(connection)
        assert loaded[0]["id"] == "audusd"
        trade = position_to_trade(loaded[0])
        assert trade.barrier == 0.6935
        assert trade.trade_date == date(2026, 6, 1)

        # Mutate and persist back, then reload.
        loaded[0]["status"] = STATUS_TRIGGERED
        loaded[0]["triggered_date"] = "2026-06-12"
        loaded[0]["alert_sent_at"] = "2026-06-12T00:00:00+00:00"
        update_monitored_position_state(connection, loaded[0])

        reloaded = load_monitored_positions(connection)
        assert reloaded[0]["status"] == STATUS_TRIGGERED
        assert reloaded[0]["triggered_date"] == "2026-06-12"
        assert reloaded[0]["alert_sent_at"] == "2026-06-12T00:00:00+00:00"


def test_mark_alerted_sets_timestamp() -> None:
    position = new_position(
        "audusd",
        pair="AUD/USD",
        trade_date=date(2026, 6, 1),
        spot=0.685,
        strike=0.685,
        barrier=0.6935,
        expiry_date=date(2026, 12, 30),
    )
    data = {"positions": [position]}
    mark_alerted(data, "audusd", "2026-06-15T00:00:00+00:00")
    assert data["positions"][0]["alert_sent_at"] == "2026-06-15T00:00:00+00:00"
    assert position["status"] == STATUS_ACTIVE
