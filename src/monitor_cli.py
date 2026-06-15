"""CLI for tracking real barrier positions and alerting on barrier touches.

Workflow:
  1. Run a forecast and (optionally) save research data:
         python -m src.analyze --pair AUD/USD --expiry-date ... --save-db data/research.sqlite3
  2. Register the real trade for monitoring:
         python -m src.monitor_cli add --id audusd-0935-dec2026 --pair AUD/USD \\
             --trade-date 2026-06-01 --spot 0.6850 --strike 0.6850 \\
             --barrier 0.6935 --barrier-direction up --expiry-date 2026-12-30
  3. Check positions (locally or from GitHub Actions); SMS fires on a fresh touch:
         python -m src.monitor_cli check --notify
"""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timezone

import pandas as pd

from src.data_loader import download_fx_prices, normalize_pair_label
from src.monitor import (
    DEFAULT_POSITIONS_PATH,
    build_alert_message,
    check_positions,
    load_positions,
    mark_alerted,
    new_position,
    position_summary_row,
    save_positions,
    update_to_dict,
)
from src.notifications import NotificationError, is_configured, send_sms


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _make_price_loader(period: str):
    def loader(pair: str) -> pd.DataFrame:
        return download_fx_prices(pair=normalize_pair_label(pair), period=period)

    return loader


def cmd_add(args: argparse.Namespace) -> int:
    data = load_positions(args.positions)
    if any(str(p.get("id")) == args.id for p in data["positions"]):
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
    data["positions"].append(position)
    save_positions(data, args.positions)
    print(f"Added position '{args.id}' -> {args.positions}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    data = load_positions(args.positions)
    rows = [position_summary_row(p) for p in data["positions"]]
    if args.json:
        print(json.dumps(rows, indent=2, ensure_ascii=False, default=str))
        return 0
    if not rows:
        print(f"No positions in {args.positions}. Add one with `monitor_cli add`.")
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
    data = load_positions(args.positions)
    if not data["positions"]:
        print(f"No positions to check in {args.positions}.")
        return 0

    now_iso = _now_iso()
    as_of = args.as_of or date.today()
    loader = _make_price_loader(args.period)
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
        print(f"  ALERT: {message}")
        if args.notify and not args.dry_run:
            try:
                result = send_sms(message)
                mark_alerted(data, update.position_id, now_iso)
                alerts_sent += 1
                print(f"  SMS sent to {result.to_number} (sid={result.provider_sid})")
            except NotificationError as error:
                alert_failures += 1
                print(f"  SMS FAILED: {error}")
        else:
            # Dry-run / no --notify: still record so we model what would be sent.
            result = send_sms(message, dry_run=True)
            if args.mark_dry_run_alerted:
                mark_alerted(data, update.position_id, now_iso)
            print(f"  (dry-run) would SMS {result.to_number}")

    if not args.no_write:
        save_positions(data, args.positions)

    if args.json:
        print(json.dumps([update_to_dict(u) for u in updates], indent=2, ensure_ascii=False))

    triggered = sum(1 for u in updates if u.newly_triggered)
    print(
        f"Checked {len(updates)} active position(s): {triggered} newly triggered, "
        f"{alerts_sent} SMS sent, {alert_failures} failed."
    )
    if not is_configured() and any(u.should_alert for u in updates) and args.notify:
        print("WARNING: SMS not configured (set TWILIO_* and ALERT_TO_NUMBER).")
    return 1 if alert_failures else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Monitor real barrier positions and alert on touches.")
    parser.add_argument(
        "--positions",
        default=str(DEFAULT_POSITIONS_PATH),
        help=f"path to positions JSON (default: {DEFAULT_POSITIONS_PATH})",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    add = sub.add_parser("add", help="register a real position for monitoring")
    add.add_argument("--id", required=True, help="unique label, e.g. audusd-0935-dec2026")
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
    check.add_argument("--as-of", type=date.fromisoformat, help="override 'today' (testing/backfill)")
    check.add_argument("--notify", action="store_true", help="actually send SMS on fresh triggers")
    check.add_argument("--dry-run", action="store_true", help="never send SMS, only print")
    check.add_argument("--no-write", action="store_true", help="do not persist status back to the file")
    check.add_argument(
        "--mark-dry-run-alerted",
        action="store_true",
        help="in dry-run, still mark positions alerted (suppress future alerts)",
    )
    check.add_argument("--json", action="store_true", help="also print machine-readable updates")
    check.set_defaults(func=cmd_check)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
