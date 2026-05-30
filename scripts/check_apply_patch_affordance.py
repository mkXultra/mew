#!/usr/bin/env python3
"""Run the M6.24 H6 apply_patch affordance check.

This script sends one provider-native Responses turn with the codex_hot_path
tool surface and records which tool the model selects first.  It does not
execute the returned tool call.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mew.implement_lane.apply_patch_affordance import (  # noqa: E402
    DEFAULT_APPLY_PATCH_AFFORDANCE_BASE_URL,
    DEFAULT_APPLY_PATCH_AFFORDANCE_LANE_ATTEMPT_ID,
    DEFAULT_APPLY_PATCH_AFFORDANCE_MODEL,
    build_apply_patch_affordance_descriptor,
    run_apply_patch_affordance_check,
    write_apply_patch_affordance_result,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--auth", default=str(Path.home() / ".codex" / "auth.json"))
    parser.add_argument("--model", default=DEFAULT_APPLY_PATCH_AFFORDANCE_MODEL)
    parser.add_argument("--base-url", default=DEFAULT_APPLY_PATCH_AFFORDANCE_BASE_URL)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--lane-attempt-id", default=DEFAULT_APPLY_PATCH_AFFORDANCE_LANE_ATTEMPT_ID)
    parser.add_argument("--http", action="store_true", help="use HTTP Responses transport instead of websocket")
    parser.add_argument(
        "--descriptor-only",
        action="store_true",
        help="write the request descriptor without calling the model",
    )
    parser.add_argument(
        "--out",
        default="",
        help="output JSON path; defaults under proof-artifacts/m6_24_apply_patch_affordance/",
    )
    parser.add_argument("--json", action="store_true", help="print the full JSON artifact")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output_path = _output_path(args.out)
    try:
        if args.descriptor_only:
            descriptor = build_apply_patch_affordance_descriptor(model=args.model)
            payload = {
                "schema_version": 1,
                "status": "descriptor_only",
                "descriptor": descriptor,
            }
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            status = "descriptor_only"
            first_tool = ""
            artifact_payload = payload
        else:
            result = run_apply_patch_affordance_check(
                auth_path=args.auth,
                model=args.model,
                base_url=args.base_url,
                timeout=args.timeout,
                lane_attempt_id=args.lane_attempt_id,
                use_websocket=not args.http,
            )
            write_apply_patch_affordance_result(result, output_path)
            artifact_payload = result.as_dict()
            status = result.status
            first_tool = result.first_tool_name
    except Exception as exc:  # noqa: BLE001 - command boundary should print actionable detail.
        print(f"apply_patch affordance check failed: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(artifact_payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print("apply_patch affordance check")
        print(f"status: {status}")
        if first_tool:
            print(f"first_tool: {first_tool}")
        print(f"artifact: {output_path.resolve(strict=False)}")
    return 0 if status in {"pass", "descriptor_only"} else 1


def _output_path(raw: str) -> Path:
    if raw:
        return Path(raw).expanduser()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return ROOT / "proof-artifacts" / "m6_24_apply_patch_affordance" / f"{stamp}.json"


if __name__ == "__main__":
    raise SystemExit(main())
