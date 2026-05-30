#!/usr/bin/env python3
"""Evaluate whether codex_hot_path may become the default tool surface."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mew.implement_lane.tool_surface_default_gate import (  # noqa: E402
    evaluate_tool_surface_default_switch_gate,
    load_tool_surface_ab_reports,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", action="append", required=True, help="tool_surface_ab_report.json path")
    parser.add_argument("--fixed-ab-set-id", required=True)
    parser.add_argument("--reviewer-accepted", action="store_true")
    parser.add_argument("--min-pair-count", type=int, default=1)
    parser.add_argument("--visible-bytes-safety-reason", default="")
    parser.add_argument(
        "--external-reward-override-reason",
        default="",
        help="Explicit reviewer-visible reason to allow externally verified traces whose internal finish stayed blocked.",
    )
    parser.add_argument("--output", help="write gate JSON")
    parser.add_argument("--json", action="store_true", help="print JSON instead of text")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        reports = load_tool_surface_ab_reports(args.report)
        result = evaluate_tool_surface_default_switch_gate(
            reports,
            reviewer_accepted=args.reviewer_accepted,
            fixed_ab_set_id=args.fixed_ab_set_id,
            min_pair_count=args.min_pair_count,
            visible_bytes_safety_reason=args.visible_bytes_safety_reason,
            external_reward_override_reason=args.external_reward_override_reason,
        ).as_dict()
    except Exception as exc:  # noqa: BLE001 - script boundary should print actionable failure.
        print(f"check tool-surface default-switch gate: {exc}", file=sys.stderr)
        return 1
    if args.output:
        output = Path(args.output).expanduser()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"default-switch gate: {result.get('status')}")
        print(f"can_switch_default: {result.get('can_switch_default')}")
        reasons = result.get("reasons") or []
        if reasons:
            print(f"reasons: {', '.join(str(reason) for reason in reasons)}")
        if args.output:
            print(f"report: {Path(args.output).expanduser().resolve(strict=False)}")
    return 0 if result.get("can_switch_default") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
