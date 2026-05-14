#!/usr/bin/env python3
"""Analyze Codex-vs-mew hot-path step shape from saved artifacts."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mew.implement_lane.hot_path_step_diff import write_hot_path_step_diff_report  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex-reference-root", required=True, help="root containing normalized Codex trace artifacts")
    parser.add_argument("--mew-artifact-root", required=True, help="mew proof/artifact root to analyze")
    parser.add_argument("--out-json", required=True, help="output JSON report path")
    parser.add_argument("--out-md", required=True, help="output Markdown report path")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = write_hot_path_step_diff_report(
            codex_reference_root=args.codex_reference_root,
            mew_artifact_root=args.mew_artifact_root,
            out_json=args.out_json,
            out_md=args.out_md,
        )
    except Exception as exc:  # noqa: BLE001 - CLI boundary should report the artifact issue.
        print(f"analyze hot-path step diff: {exc}", file=sys.stderr)
        return 1
    print(f"hot-path step diff JSON: {Path(args.out_json).expanduser().resolve(strict=False)}")
    print(f"hot-path step diff Markdown: {Path(args.out_md).expanduser().resolve(strict=False)}")
    for line in report.get("divergence_summary") or []:
        print(f"- {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
