import argparse
import sqlite3
from datetime import date

import pandas as pd

import src.monitor_cli as monitor_cli
from src import repository
from src.repository import _LibsqlConnection, _Row, connect_positions, init_db
from src.monitor import new_position
from src.repository import load_monitored_positions, save_monitored_position


# --- libsql row adapter -----------------------------------------------------


def test_row_supports_name_and_index_access() -> None:
    row = _Row(["label", "status"], ("audusd-x", "active"))
    assert row["label"] == "audusd-x"  # by name
    assert row[0] == "audusd-x"  # by index
    assert row["status"] == "active"
    assert row[1] == "active"


# --- connect_positions routing ---------------------------------------------


def test_connect_positions_falls_back_to_local_sqlite(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("TURSO_DATABASE_URL", raising=False)
    monkeypatch.delenv("TURSO_AUTH_TOKEN", raising=False)
    db = tmp_path / "positions.sqlite3"

    connection = connect_positions(db)
    assert isinstance(connection, sqlite3.Connection)
    init_db(connection)
    save_monitored_position(connection, _sample_position())
    connection.commit()

    positions = load_monitored_positions(connection)
    assert [p["id"] for p in positions] == ["audusd-test"]


def test_connect_positions_uses_libsql_when_configured(monkeypatch) -> None:
    monkeypatch.setenv("TURSO_DATABASE_URL", "libsql://example.turso.io")
    monkeypatch.setenv("TURSO_AUTH_TOKEN", "tok")

    captured = {}

    class _FakeLibsql:
        def connect(self, database, auth_token):
            captured["database"] = database
            captured["auth_token"] = auth_token
            return object()

    monkeypatch.setitem(__import__("sys").modules, "libsql_experimental", _FakeLibsql())

    connection = connect_positions()
    assert isinstance(connection, _LibsqlConnection)
    assert captured == {"database": "libsql://example.turso.io", "auth_token": "tok"}


# --- dry-run must not mutate the store --------------------------------------


def test_check_dry_run_does_not_write_but_normal_run_does(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("TURSO_DATABASE_URL", raising=False)
    monkeypatch.delenv("TURSO_AUTH_TOKEN", raising=False)
    db = tmp_path / "positions.sqlite3"
    connection = connect_positions(db)
    init_db(connection)
    save_monitored_position(connection, _sample_position())
    connection.commit()
    connection.close()

    # Price path that breaches the 0.6900 down barrier (low touches 0.68).
    frame = pd.DataFrame(
        [
            {"date": "2026-01-01", "pair": "AUD/USD", "open": 0.70, "high": 0.70, "low": 0.695, "close": 0.70},
            {"date": "2026-01-02", "pair": "AUD/USD", "open": 0.70, "high": 0.70, "low": 0.68, "close": 0.69},
        ]
    )
    monkeypatch.setattr(monitor_cli, "_make_price_loader", lambda *a, **k: (lambda pair: frame))

    # Dry-run: status must stay active.
    monitor_cli.cmd_check(_check_args(db, dry_run=True))
    assert _status(db) == "active"

    # Normal run: status flips to triggered and is persisted.
    monitor_cli.cmd_check(_check_args(db, dry_run=False))
    assert _status(db) == "triggered"


def _sample_position() -> dict:
    return new_position(
        "audusd-test",
        pair="AUD/USD",
        trade_date=date(2026, 1, 1),
        spot=0.70,
        strike=0.69,
        barrier=0.69,
        expiry_date=date(2026, 12, 30),
        barrier_direction="down",
    )


def _check_args(db, *, dry_run: bool) -> argparse.Namespace:
    return argparse.Namespace(
        db=str(db),
        period="2y",
        no_intraday=True,
        intraday_days=5,
        intraday_interval="5m",
        as_of=date(2026, 6, 1),
        notify=False,
        dry_run=dry_run,
        no_write=False,
        mark_dry_run_alerted=False,
        json=False,
    )


def _status(db) -> str:
    connection = sqlite3.connect(db)
    connection.row_factory = sqlite3.Row
    row = connection.execute(
        "SELECT status FROM monitored_positions WHERE label = 'audusd-test'"
    ).fetchone()
    connection.close()
    return row["status"]
