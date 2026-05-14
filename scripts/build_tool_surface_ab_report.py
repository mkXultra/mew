#!/usr/bin/env python3
"""Build a paired implement_v2 tool-surface A/B report from artifact roots."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mew.implement_lane.tool_surface_ab_report import build_tool_surface_ab_report  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-artifact-root", required=True, help="mew_legacy artifact root")
    parser.add_argument("--candidate-artifact-root", required=True, help="codex_hot_path artifact root")
    parser.add_argument("--ab-pair-id", required=True)
    parser.add_argument("--workspace-snapshot-id", default="")
    parser.add_argument("--task-contract-hash", default="")
    parser.add_argument("--model", default="")
    parser.add_argument("--effort", default="")
    parser.add_argument("--budget-profile", default="")
    parser.add_argument("--provider-seed", default="")
    parser.add_argument("--provider-seed-supported", action="store_true")
    parser.add_argument("--output", required=True, help="report JSON path")
    parser.add_argument("--json", action="store_true", help="print full JSON report")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        report = build_tool_surface_ab_report(
            baseline_artifact_root=args.baseline_artifact_root,
            candidate_artifact_root=args.candidate_artifact_root,
            ab_pair_id=args.ab_pair_id,
            workspace_snapshot_id=args.workspace_snapshot_id,
            task_contract_hash=args.task_contract_hash,
            model=args.model,
            effort=args.effort,
            budget_profile=args.budget_profile,
            provider_seed=args.provider_seed,
            provider_seed_supported=args.provider_seed_supported,
        )
    except Exception as exc:  # noqa: BLE001 - script boundary should print actionable failure.
        print(f"build tool-surface A/B report: {exc}", file=sys.stderr)
        return 1
    output = Path(args.output).expanduser()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"tool-surface A/B report: {output.resolve(strict=False)}")
        print(f"ab_comparable: {report.get('ab_comparable')}")
        reasons = report.get("exclusion_reasons") or []
        if reasons:
            print(f"exclusion_reasons: {', '.join(str(reason) for reason in reasons)}")
    return 0 if report.get("ab_comparable") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
