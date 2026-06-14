from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path

from src.agent import dataclass_to_json_dict, parse_forecast_request, review_forecast_payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Local AI-agent workflow helpers.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    parse_request = subparsers.add_parser("parse-request", help="parse a natural-language forecast request")
    parse_request.add_argument("text", help="natural-language forecast request")
    parse_request.add_argument("--analysis-date", type=date.fromisoformat)

    review_json = subparsers.add_parser("review-json", help="review a JSON payload from src.analyze --json")
    review_json.add_argument("path", help="path to forecast JSON payload")

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.command == "parse-request":
        parsed = parse_forecast_request(args.text, analysis_date=args.analysis_date)
        print(json.dumps(dataclass_to_json_dict(parsed), default=str, indent=2, ensure_ascii=False))
        return

    if args.command == "review-json":
        payload = json.loads(Path(args.path).read_text())
        review = review_forecast_payload(payload)
        print(json.dumps(dataclass_to_json_dict(review), indent=2, ensure_ascii=False))
        return

    raise ValueError(f"unsupported command: {args.command}")


if __name__ == "__main__":
    main()
