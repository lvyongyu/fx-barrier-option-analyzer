"""CLI for tracking real barrier positions and alerting on barrier touches.

Positions are stored in the SQLite database (``monitored_positions`` table),
default ``data/positions.sqlite3``. This is a small, dedicated DB that can be
committed to git so a scheduled GitHub Actions run persists status back.

Workflow:
  1. Run a forecast and (optionally) save research data:
         python -m src.analyze --pair AUD/USD --expiry-date ... --save-db data/research.sqlite3
  2. Register the real trade for monitoring:
         python -m src.monitor_cli add --id audusd-06935-down-dec2026 --pair AUD/USD \\
             --trade-date 2026-06-01 --spot 0.7050 --strike 0.7050 \\
             --barrier 0.6935 --barrier-direction down --expiry-date 2026-12-30
  3. Check positions (locally or from GitHub Actions); an email fires on a fresh touch:
         python -m src.monitor_cli check --notify
  4. Verify the email channel end-to-end any time:
         python -m src.monitor_cli test-alert
"""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

from src.data_loader import (
    DEFAULT_INTRADAY_DAYS,
    DEFAULT_INTRADAY_INTERVAL,
    download_fx_prices,
    download_fx_prices_with_intraday,
    normalize_pair_label,
)
from src.monitor import (
    build_alert_message,
    check_positions,
    mark_alerted,
    new_position,
    position_summary_row,
    update_to_dict,
)
from src.notifications import NotificationError, any_channel_configured, send_alert
from src.repository import (
    connect,
    init_db,
    load_monitored_positions,
    monitored_position_label_exists,
    save_monitored_position,
    update_monitored_position_state,
)


DEFAULT_DB_PATH = Path("data/positions.sqlite3")


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _make_price_loader(
    period: str,
    *,
    intraday: bool = True,
    intraday_days: int = DEFAULT_INTRADAY_DAYS,
    intraday_interval: str = DEFAULT_INTRADAY_INTERVAL,
):
    def loader(pair: str) -> pd.DataFrame:
        normalized = normalize_pair_label(pair)
        if intraday:
            return download_fx_prices_with_intraday(
                pair=normalized,
                period=period,
                intraday_days=intraday_days,
                intraday_interval=intraday_interval,
            )
        return download_fx_prices(pair=normalized, period=period)

    return loader


def cmd_add(args: argparse.Namespace) -> int:
    with connect(args.db) as connection:
        init_db(connection)
        if monitored_position_label_exists(connection, args.id):
            raise SystemExit(f"position id already exists: {args.id}")
        position = new_position(
            args.id,
            pair=normalize_pair_label(args.pair),
            trade_date=args.trade_date,
            spot=args.spot,
            strike=args.strike,
            barrier=args.barrier,
            expiry_date=args.expiry_date,
            barrier_direction=args.barrier_direction,
            product_type=args.product_type,
            client_direction=args.client_direction,
            note=args.note,
        )
        save_monitored_position(connection, position)
        connection.commit()
    print(f"Added position '{args.id}' -> {args.db}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    with connect(args.db) as connection:
        init_db(connection)
        positions = load_monitored_positions(connection)
    rows = [position_summary_row(p) for p in positions]
    if args.json:
        print(json.dumps(rows, indent=2, ensure_ascii=False, default=str))
        return 0
    if not rows:
        print(f"No positions in {args.db}. Add one with `monitor_cli add`.")
        return 0
    headers = ["id", "pair", "barrier", "dir", "expiry", "status", "triggered", "alerted"]
    table = [
        [
            str(r["id"]),
            str(r["pair"]),
            f"{float(r['barrier']):.4f}",
            str(r["barrier_direction"]),
            str(r["expiry_date"]),
            str(r["status"]),
            str(r.get("triggered_date") or "-"),
            "yes" if r.get("alert_sent_at") else "-",
        ]
        for r in rows
    ]
    widths = [max(len(row[i]) for row in [headers, *table]) for i in range(len(headers))]
    print(" | ".join(h.ljust(widths[i]) for i, h in enumerate(headers)))
    print("-+-".join("-" * w for w in widths))
    for row in table:
        print(" | ".join(v.ljust(widths[i]) for i, v in enumerate(row)))
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    with connect(args.db) as connection:
        init_db(connection)
        positions = load_monitored_positions(connection)
        if not positions:
            print(f"No positions to check in {args.db}.")
            return 0

        now_iso = _now_iso()
        as_of = args.as_of or date.today()
        loader = _make_price_loader(
            args.period,
            intraday=not args.no_intraday,
            intraday_days=args.intraday_days,
            intraday_interval=args.intraday_interval,
        )
        data = {"positions": positions}
        updates = check_positions(data, loader, as_of=as_of, now_iso=now_iso)

        alerts_sent = 0
        alert_failures = 0
        for update in updates:
            position = next(p for p in data["positions"] if str(p.get("id")) == update.position_id)
            status_line = f"[{update.position_id}] {update.previous_status} -> {update.new_status}"
            if update.path.latest_close is not None:
                status_line += f" (latest {update.path.latest_close:.4f})"
            print(status_line)

            if not update.should_alert:
                continue

            message = build_alert_message(position, update)
            subject = _alert_subject(position)
            print(f"  ALERT: {message}")
            if args.notify and not args.dry_run:
                try:
                    result = send_alert(subject, message)
                    mark_alerted(data, update.position_id, now_iso)
                    alerts_sent += 1
                    print(f"  {result.channel} sent to {result.recipient}")
                except NotificationError as error:
                    alert_failures += 1
                    print(f"  ALERT FAILED: {error}")
            else:
                result = send_alert(subject, message, dry_run=True)
                if args.mark_dry_run_alerted:
                    mark_alerted(data, update.position_id, now_iso)
                print(f"  (dry-run) would {result.channel} to {result.recipient}")

        if not args.no_write:
            for position in data["positions"]:
                update_monitored_position_state(connection, position)
            connection.commit()

    if args.json:
        print(json.dumps([update_to_dict(u) for u in updates], indent=2, ensure_ascii=False))

    triggered = sum(1 for u in updates if u.newly_triggered)
    print(
        f"Checked {len(updates)} active position(s): {triggered} newly triggered, "
        f"{alerts_sent} alert(s) sent, {alert_failures} failed."
    )
    if not any_channel_configured() and any(u.should_alert for u in updates) and args.notify:
        print("WARNING: no alert channel configured (set GMAIL_ADDRESS + GMAIL_APP_PASSWORD).")
    return 1 if alert_failures else 0


def _alert_subject(position: dict) -> str:
    return (
        f"Barrier triggered: {position.get('pair', '?')} "
        f"{position.get('barrier')} {position.get('barrier_direction', '')}".strip()
    )


def cmd_test_alert(args: argparse.Namespace) -> int:
    """Send a one-off test email to confirm the alert channel works."""
    subject = "FX barrier monitor — test alert"
    body = (
        "This is a test alert from the FX barrier monitor. "
        "If you received this email, barrier-touch alerting is configured correctly."
    )
    if args.dry_run:
        result = send_alert(subject, body, dry_run=True)
        print(f"(dry-run) would {result.channel} to {result.recipient}")
        return 0
    if not any_channel_configured():
        print("No alert channel configured. Set GMAIL_ADDRESS + GMAIL_APP_PASSWORD.")
        return 1
    try:
        result = send_alert(subject, body)
    except NotificationError as error:
        print(f"TEST ALERT FAILED: {error}")
        return 1
    print(f"Test alert sent via {result.channel} to {result.recipient}.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Monitor real barrier positions and alert on touches.")
    parser.add_argument(
        "--db",
        default=str(DEFAULT_DB_PATH),
        help=f"path to positions SQLite DB (default: {DEFAULT_DB_PATH})",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    add = sub.add_parser("add", help="register a real position for monitoring")
    add.add_argument("--id", required=True, help="unique label, e.g. audusd-06935-down-dec2026")
    add.add_argument("--pair", required=True)
    add.add_argument("--trade-date", required=True, type=date.fromisoformat)
    add.add_argument("--spot", required=True, type=float)
    add.add_argument("--strike", required=True, type=float)
    add.add_argument("--barrier", required=True, type=float)
    add.add_argument("--expiry-date", required=True, type=date.fromisoformat)
    add.add_argument("--barrier-direction", default="up", choices=["up", "down"])
    add.add_argument("--product-type", default="Ratio Convertible Forward")
    add.add_argument("--client-direction", choices=["Importer", "Exporter"])
    add.add_argument("--note")
    add.set_defaults(func=cmd_add)

    show = sub.add_parser("list", help="show tracked positions and their status")
    show.add_argument("--json", action="store_true")
    show.set_defaults(func=cmd_list)

    check = sub.add_parser("check", help="evaluate positions and alert on fresh barrier touches")
    check.add_argument("--period", default="2y", help="Yahoo history window for the touch scan")
    check.add_argument(
        "--no-intraday",
        action="store_true",
        help="skip the intraday high/low overlay and scan daily bars only",
    )
    check.add_argument(
        "--intraday-days",
        type=int,
        default=DEFAULT_INTRADAY_DAYS,
        help=f"recent days to overlay with intraday high/low (default: {DEFAULT_INTRADAY_DAYS})",
    )
    check.add_argument(
        "--intraday-interval",
        default=DEFAULT_INTRADAY_INTERVAL,
        help=f"intraday bar size for the overlay, e.g. 1m/5m (default: {DEFAULT_INTRADAY_INTERVAL})",
    )
    check.add_argument("--as-of", type=date.fromisoformat, help="override 'today' (testing/backfill)")
    check.add_argument("--notify", action="store_true", help="actually send the email alert on fresh triggers")
    check.add_argument("--dry-run", action="store_true", help="never send email, only print")
    check.add_argument("--no-write", action="store_true", help="do not persist status back to the DB")
    check.add_argument(
        "--mark-dry-run-alerted",
        action="store_true",
        help="in dry-run, still mark positions alerted (suppress future alerts)",
    )
    check.add_argument("--json", action="store_true", help="also print machine-readable updates")
    check.set_defaults(func=cmd_check)

    test = sub.add_parser("test-alert", help="send a one-off test email to verify the alert channel")
    test.add_argument("--dry-run", action="store_true", help="format only, do not send")
    test.set_defaults(func=cmd_test_alert)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
