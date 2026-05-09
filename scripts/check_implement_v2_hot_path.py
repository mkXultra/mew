#!/usr/bin/env python3
"""Run the M6.24 implement_v2 hot-path fastcheck.

This script is intentionally lightweight compared with Harbor step-shape runs.
It reuses a saved micro next-action fixture when hashes match; otherwise it
refreshes that fixture with one bounded live model call.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mew.implement_lane.hot_path_fastcheck import (  # noqa: E402
    DEFAULT_HOT_PATH_BASELINE_PATH,
    format_hot_path_fastcheck_text,
    run_hot_path_fastcheck,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", required=True, help="implement_v2 proof-manifest.json or artifact directory")
    parser.add_argument(
        "--micro-next-action",
        help="saved micro fixture to reuse when hashes match; defaults to artifact-local fixture",
    )
    parser.add_argument(
        "--micro-next-action-output",
        help="where to write refreshed micro fixture; defaults to --micro-next-action or artifact-local fixture",
    )
    parser.add_argument(
        "--refresh-micro-next-action",
        action="store_true",
        help="force one live LLM micro refresh even when the saved fixture hash matches",
    )
    parser.add_argument("--auth", default="auth.json", help="auth JSON for live micro refresh")
    parser.add_argument("--model-backend", default="codex", help="model backend for live micro refresh")
    parser.add_argument("--model", default="", help="model name; backend default when omitted")
    parser.add_argument("--base-url", default="", help="model backend base URL override")
    parser.add_argument("--model-timeout", type=float, default=60.0, help="micro model call timeout in seconds")
    parser.add_argument(
        "--expected-category",
        action="append",
        default=[],
        choices=("patch/edit", "run_verifier", "inspect_latest_failure", "cheap_probe"),
        help="allowed passing micro next-action category; may be repeated",
    )
    parser.add_argument("--max-active-todo-bytes", type=int, default=2048)
    parser.add_argument("--max-sidecar-total-bytes", type=int, default=262144)
    parser.add_argument("--max-sidecar-per-turn-growth-bytes", type=int, default=32768)
    parser.add_argument(
        "--baseline",
        default=str(DEFAULT_HOT_PATH_BASELINE_PATH),
        help="Phase 0 baseline JSON for relative sidecar caps; pass an empty string to use absolute caps",
    )
    parser.add_argument(
        "--no-baseline",
        action="store_true",
        help="explicitly use absolute sidecar caps instead of the Phase 0 baseline",
    )
    parser.add_argument("--report", help="write the full fastcheck JSON report")
    parser.add_argument("--json", action="store_true", help="print JSON instead of text")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = run_hot_path_fastcheck(
            args.artifact,
            micro_next_action=args.micro_next_action,
            refresh_micro_next_action=args.refresh_micro_next_action,
            auth_path=args.auth,
            model_backend=args.model_backend,
            model=args.model,
            base_url=args.base_url,
            model_timeout=args.model_timeout,
            micro_next_action_output=args.micro_next_action_output,
            expected_categories=args.expected_category,
            max_active_todo_bytes=args.max_active_todo_bytes,
            max_sidecar_total_bytes=args.max_sidecar_total_bytes,
            max_sidecar_per_turn_growth_bytes=args.max_sidecar_per_turn_growth_bytes,
            baseline="" if args.no_baseline else args.baseline,
        )
    except Exception as exc:  # noqa: BLE001 - command boundary should print the actionable failure.
        print(f"mew hot-path fastcheck: {exc}", file=sys.stderr)
        return 1
    if args.report:
        report_path = Path(args.report).expanduser()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(format_hot_path_fastcheck_text(result))
        if args.report:
            print(f"report: {Path(args.report).expanduser().resolve(strict=False)}")
    return 0 if result.get("status") == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
