from __future__ import annotations

import sqlite3
from dataclasses import asdict
from pathlib import Path

import pandas as pd

from src.barrier_engine import Trade, TouchProbabilityResult, normalize_prices
from src.feature_engine import FeatureSnapshot
from src.volatility_adjustment import VolatilityAdjustedResult


DEFAULT_DB_PATH = Path("data/research.sqlite3")


def connect(db_path: str | Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def init_db(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS market_prices (
            date TEXT NOT NULL,
            pair TEXT NOT NULL,
            open REAL NOT NULL,
            high REAL NOT NULL,
            low REAL NOT NULL,
            close REAL NOT NULL,
            PRIMARY KEY (date, pair)
        );

        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_type TEXT NOT NULL,
            client_direction TEXT,
            pair TEXT NOT NULL,
            trade_date TEXT NOT NULL,
            spot REAL NOT NULL,
            strike REAL NOT NULL,
            barrier REAL NOT NULL,
            expiry_date TEXT NOT NULL,
            barrier_direction TEXT NOT NULL,
            protected_amount REAL,
            ratio_amount REAL,
            amount_currency TEXT,
            barrier_level_period TEXT NOT NULL,
            expiry_time_zone TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS feature_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_id INTEGER,
            as_of_date TEXT NOT NULL,
            pair TEXT NOT NULL,
            days_to_expiry INTEGER NOT NULL,
            distance_pct REAL NOT NULL,
            realized_vol_20d REAL,
            realized_vol_60d REAL,
            atr_14d REAL,
            trend_20d REAL,
            trend_60d REAL,
            range_position_60d REAL,
            recent_high_distance REAL,
            recent_low_distance REAL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (trade_id) REFERENCES trades(id)
        );

        CREATE TABLE IF NOT EXISTS analysis_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_id INTEGER NOT NULL,
            days_to_expiry INTEGER NOT NULL,
            distance_pct REAL NOT NULL,
            sample_count INTEGER NOT NULL,
            touch_count INTEGER NOT NULL,
            touch_probability REAL NOT NULL,
            actual_path_applicable INTEGER NOT NULL,
            actual_path_reason TEXT,
            barrier_hit INTEGER NOT NULL,
            hit_date TEXT,
            max_high REAL,
            min_low REAL,
            days_to_hit INTEGER,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (trade_id) REFERENCES trades(id)
        );

        CREATE TABLE IF NOT EXISTS monitored_positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            label TEXT NOT NULL UNIQUE,
            trade_id INTEGER,
            pair TEXT NOT NULL,
            trade_date TEXT NOT NULL,
            spot REAL NOT NULL,
            strike REAL NOT NULL,
            barrier REAL NOT NULL,
            expiry_date TEXT NOT NULL,
            barrier_direction TEXT NOT NULL,
            product_type TEXT,
            client_direction TEXT,
            note TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            triggered_date TEXT,
            triggered_price REAL,
            alert_sent_at TEXT,
            last_checked TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (trade_id) REFERENCES trades(id)
        );

        CREATE TABLE IF NOT EXISTS volatility_adjustments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            analysis_result_id INTEGER NOT NULL,
            method TEXT NOT NULL,
            current_vol_20d REAL,
            current_vol_percentile REAL,
            bucket_low_percentile REAL,
            bucket_high_percentile REAL,
            comparable_sample_count INTEGER NOT NULL,
            comparable_touch_count INTEGER NOT NULL,
            volatility_adjusted_probability REAL,
            used_fallback INTEGER NOT NULL,
            fallback_reason TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (analysis_result_id) REFERENCES analysis_results(id)
        );
        """
    )


def upsert_market_prices(connection: sqlite3.Connection, prices: pd.DataFrame, pair: str = "AUD/USD") -> int:
    frame = normalize_prices(prices, pair)
    rows = [
        (
            row.date.isoformat(),
            pair,
            float(row.open),
            float(row.high),
            float(row.low),
            float(row.close),
        )
        for row in frame.itertuples(index=False)
    ]
    connection.executemany(
        """
        INSERT INTO market_prices (date, pair, open, high, low, close)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(date, pair) DO UPDATE SET
            open = excluded.open,
            high = excluded.high,
            low = excluded.low,
            close = excluded.close
        """,
        rows,
    )
    return len(rows)


def load_market_prices(connection: sqlite3.Connection, pair: str = "AUD/USD") -> pd.DataFrame:
    return pd.read_sql_query(
        """
        SELECT date, pair, open, high, low, close
        FROM market_prices
        WHERE pair = ?
        ORDER BY date
        """,
        connection,
        params=(pair,),
    )


def save_trade(connection: sqlite3.Connection, trade: Trade) -> int:
    cursor = connection.execute(
        """
        INSERT INTO trades (
            product_type, client_direction, pair, trade_date, spot, strike, barrier,
            expiry_date, barrier_direction, protected_amount, ratio_amount,
            amount_currency, barrier_level_period, expiry_time_zone
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            trade.product_type,
            trade.client_direction,
            trade.pair,
            trade.trade_date.isoformat(),
            trade.spot,
            trade.strike,
            trade.barrier,
            trade.expiry_date.isoformat(),
            trade.barrier_direction,
            trade.protected_amount,
            trade.ratio_amount,
            trade.amount_currency,
            trade.barrier_level_period,
            trade.expiry_time_zone,
        ),
    )
    return int(cursor.lastrowid)


def save_feature_snapshot(
    connection: sqlite3.Connection,
    snapshot: FeatureSnapshot,
    trade_id: int | None = None,
) -> int:
    data = asdict(snapshot)
    cursor = connection.execute(
        """
        INSERT INTO feature_snapshots (
            trade_id, as_of_date, pair, days_to_expiry, distance_pct,
            realized_vol_20d, realized_vol_60d, atr_14d, trend_20d,
            trend_60d, range_position_60d, recent_high_distance, recent_low_distance
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            trade_id,
            data["as_of_date"].isoformat(),
            data["pair"],
            data["days_to_expiry"],
            data["distance_pct"],
            data["realized_vol_20d"],
            data["realized_vol_60d"],
            data["atr_14d"],
            data["trend_20d"],
            data["trend_60d"],
            data["range_position_60d"],
            data["recent_high_distance"],
            data["recent_low_distance"],
        ),
    )
    return int(cursor.lastrowid)


def save_analysis_result(
    connection: sqlite3.Connection,
    result: TouchProbabilityResult,
    trade_id: int,
) -> int:
    actual_path = result.actual_path
    cursor = connection.execute(
        """
        INSERT INTO analysis_results (
            trade_id, days_to_expiry, distance_pct, sample_count, touch_count,
            touch_probability, actual_path_applicable, actual_path_reason,
            barrier_hit, hit_date, max_high, min_low, days_to_hit
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            trade_id,
            result.days_to_expiry,
            result.distance_pct,
            result.sample_count,
            result.touch_count,
            result.touch_probability,
            int(actual_path.is_applicable),
            actual_path.reason,
            int(actual_path.barrier_hit),
            actual_path.hit_date.isoformat() if actual_path.hit_date else None,
            actual_path.max_high,
            actual_path.min_low,
            actual_path.days_to_hit,
        ),
    )
    return int(cursor.lastrowid)


def save_volatility_adjustment(
    connection: sqlite3.Connection,
    adjustment: VolatilityAdjustedResult,
    analysis_result_id: int,
) -> int:
    cursor = connection.execute(
        """
        INSERT INTO volatility_adjustments (
            analysis_result_id, method, current_vol_20d, current_vol_percentile,
            bucket_low_percentile, bucket_high_percentile, comparable_sample_count,
            comparable_touch_count, volatility_adjusted_probability,
            used_fallback, fallback_reason
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            analysis_result_id,
            adjustment.method,
            adjustment.current_vol_20d,
            adjustment.current_vol_percentile,
            adjustment.bucket_low_percentile,
            adjustment.bucket_high_percentile,
            adjustment.comparable_sample_count,
            adjustment.comparable_touch_count,
            adjustment.volatility_adjusted_probability,
            int(adjustment.used_fallback),
            adjustment.fallback_reason,
        ),
    )
    return int(cursor.lastrowid)


# --- Live monitored positions ------------------------------------------------
#
# These rows are the source of truth for real-trade monitoring (see src.monitor).
# A position dict uses "id" for the unique label so it round-trips with the pure
# logic in src.monitor; the DB stores it in the `label` column.

_MONITORED_POSITION_FIELDS = (
    "pair",
    "trade_date",
    "spot",
    "strike",
    "barrier",
    "expiry_date",
    "barrier_direction",
    "product_type",
    "client_direction",
    "note",
    "status",
    "triggered_date",
    "triggered_price",
    "alert_sent_at",
    "last_checked",
)


def save_monitored_position(connection: sqlite3.Connection, position: dict, trade_id: int | None = None) -> int:
    cursor = connection.execute(
        """
        INSERT INTO monitored_positions (
            label, trade_id, pair, trade_date, spot, strike, barrier, expiry_date,
            barrier_direction, product_type, client_direction, note, status,
            triggered_date, triggered_price, alert_sent_at, last_checked
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            position["id"],
            trade_id,
            position["pair"],
            position["trade_date"],
            float(position["spot"]),
            float(position["strike"]),
            float(position["barrier"]),
            position["expiry_date"],
            position["barrier_direction"],
            position.get("product_type"),
            position.get("client_direction"),
            position.get("note"),
            position.get("status", "active"),
            position.get("triggered_date"),
            position.get("triggered_price"),
            position.get("alert_sent_at"),
            position.get("last_checked"),
        ),
    )
    return int(cursor.lastrowid)


def load_monitored_positions(connection: sqlite3.Connection) -> list[dict]:
    rows = connection.execute(
        """
        SELECT label, pair, trade_date, spot, strike, barrier, expiry_date,
               barrier_direction, product_type, client_direction, note, status,
               triggered_date, triggered_price, alert_sent_at, last_checked
        FROM monitored_positions
        ORDER BY id
        """
    ).fetchall()
    positions: list[dict] = []
    for row in rows:
        position = {field: row[field] for field in _MONITORED_POSITION_FIELDS}
        position["id"] = row["label"]
        positions.append(position)
    return positions


def update_monitored_position_state(connection: sqlite3.Connection, position: dict) -> None:
    connection.execute(
        """
        UPDATE monitored_positions
        SET status = ?, triggered_date = ?, triggered_price = ?,
            alert_sent_at = ?, last_checked = ?
        WHERE label = ?
        """,
        (
            position.get("status", "active"),
            position.get("triggered_date"),
            position.get("triggered_price"),
            position.get("alert_sent_at"),
            position.get("last_checked"),
            position["id"],
        ),
    )


def monitored_position_label_exists(connection: sqlite3.Connection, label: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM monitored_positions WHERE label = ? LIMIT 1", (label,)
    ).fetchone()
    return row is not None


def table_count(connection: sqlite3.Connection, table_name: str) -> int:
    allowed = {
        "market_prices",
        "trades",
        "feature_snapshots",
        "analysis_results",
        "volatility_adjustments",
        "monitored_positions",
    }
    if table_name not in allowed:
        raise ValueError(f"unsupported table: {table_name}")
    row = connection.execute(f"SELECT COUNT(*) AS count FROM {table_name}").fetchone()
    return int(row["count"])
