#!/usr/bin/env python3
"""Run the M6.24 implement_v2 native-loop validation gate."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _repo_src() -> Path:
    return Path(__file__).resolve().parents[1] / "src"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", default=".", help="repository root to scan")
    parser.add_argument("--artifact", help="optional implement_v2 native proof manifest or artifact directory")
    parser.add_argument("--json", action="store_true", help="print structured JSON")
    args = parser.parse_args(argv)

    sys.path.insert(0, str(_repo_src()))
    from mew.implement_lane.native_validation import validate_native_loop_gate

    result = validate_native_loop_gate(source_root=args.source_root, artifact=args.artifact)
    payload = result.as_dict()
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        status = "PASS" if result.ok else "FAIL"
        print(f"implement_v2 native gate: {status}")
        for key, passed in sorted(result.checks.items()):
            marker = "ok" if passed else "fail"
            print(f"- {marker}: {key}")
        for warning in result.warnings:
            print(f"warning: {warning}")
        for error in result.errors:
            print(f"error: {error}")
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
