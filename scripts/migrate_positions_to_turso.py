"""One-time migration: copy monitored_positions from local sqlite -> Turso.

Reads the local positions DB (default ``data/positions.sqlite3``) and copies every
``monitored_positions`` row, faithfully (all columns including id/state/created_at),
into the Turso (libSQL) database configured via TURSO_DATABASE_URL + TURSO_AUTH_TOKEN
(loaded from .env).

Usage:
    python -m scripts.migrate_positions_to_turso            # migrate (refuses if target non-empty)
    python -m scripts.migrate_positions_to_turso --force    # clear target first, then migrate
    python -m scripts.migrate_positions_to_turso --source data/positions.sqlite3
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path

from dotenv import load_dotenv

from src.storage.repository import connect_positions, init_db


def _target_count(connection) -> int:
    return int(connection.execute("SELECT COUNT(*) AS c FROM monitored_positions").fetchone()["c"])


def migrate(source_path: str, force: bool) -> int:
    if not (os.environ.get("TURSO_DATABASE_URL") and os.environ.get("TURSO_AUTH_TOKEN")):
        print("ERROR: TURSO_DATABASE_URL + TURSO_AUTH_TOKEN must be set (check .env).")
        return 2
    if not Path(source_path).exists():
        print(f"ERROR: source sqlite not found: {source_path}")
        return 2

    source = sqlite3.connect(source_path)
    source.row_factory = sqlite3.Row
    columns = [d[0] for d in source.execute("SELECT * FROM monitored_positions LIMIT 0").description]
    rows = source.execute("SELECT * FROM monitored_positions ORDER BY id").fetchall()
    print(f"Source: {len(rows)} position(s) in {source_path}")

    target = connect_positions()  # Turso (env is set)
    init_db(target)
    existing = _target_count(target)
    if existing and not force:
        print(f"ERROR: target already has {existing} position(s). Re-run with --force to overwrite.")
        return 1
    if existing and force:
        target.execute("DELETE FROM monitored_positions")
        target.commit()
        print(f"Cleared {existing} existing target row(s) (--force).")

    collist = ", ".join(columns)
    placeholders = ", ".join("?" for _ in columns)
    insert = f"INSERT INTO monitored_positions ({collist}) VALUES ({placeholders})"
    for row in rows:
        target.execute(insert, tuple(row[c] for c in columns))
    target.commit()

    final = _target_count(target)
    print(f"Target: {final} position(s) after migration.")
    if final != len(rows):
        print("WARNING: target count does not match source count.")
        return 1
    print("Migration complete ✅")
    return 0


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Migrate monitored_positions sqlite -> Turso.")
    parser.add_argument("--source", default="data/positions.sqlite3", help="local sqlite path")
    parser.add_argument("--force", action="store_true", help="clear target before migrating")
    args = parser.parse_args(argv)
    return migrate(args.source, args.force)


if __name__ == "__main__":
    sys.exit(main())
