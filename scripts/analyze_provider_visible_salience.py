#!/usr/bin/env python3
"""Analyze mew provider-visible prompt/transcript salience from saved artifacts."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mew.implement_lane.provider_visible_salience import write_provider_visible_salience_report  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mew-artifact-root", required=True, help="mew artifact root or native-provider-requests.json")
    parser.add_argument("--out-json", required=True, help="output JSON report path")
    parser.add_argument("--out-md", required=True, help="output Markdown report path")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = write_provider_visible_salience_report(
            mew_artifact_root=args.mew_artifact_root,
            out_json=args.out_json,
            out_md=args.out_md,
        )
    except Exception as exc:  # noqa: BLE001 - CLI boundary should report artifact problems.
        print(f"analyze provider-visible salience: {exc}", file=sys.stderr)
        return 1
    print(f"provider-visible salience JSON: {Path(args.out_json).expanduser().resolve(strict=False)}")
    print(f"provider-visible salience Markdown: {Path(args.out_md).expanduser().resolve(strict=False)}")
    for line in report.get("interpretation") or []:
        print(f"- {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
