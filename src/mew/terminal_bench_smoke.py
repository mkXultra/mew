from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mew-smoke",
        description="Minimal instruction-consuming Terminal-Bench smoke entrypoint.",
    )
    parser.add_argument("--instruction", required=True, help="Terminal-Bench task instruction text.")
    parser.add_argument("--report", required=True, help="Path to write the smoke report JSON.")
    parser.add_argument("--artifacts", required=True, help="Directory for smoke artifacts.")
    return parser


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    artifact_dir = Path(args.artifacts)
    report_path = Path(args.report)
    artifact_dir.mkdir(parents=True, exist_ok=True)

    instruction_payload: dict[str, object] = {
        "instruction": args.instruction,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    instruction_path = artifact_dir / "instruction.json"
    _write_json(instruction_path, instruction_payload)

    report_payload: dict[str, object] = {
        "status": "smoke-complete",
        "instruction": args.instruction,
        "artifacts": str(artifact_dir),
        "instruction_path": str(instruction_path),
        "summary": "mew-smoke completed instruction capture",
        "verification": {
            "passed": None,
            "command": "mew-smoke",
            "reason": "Terminal-Bench verifier runs outside mew-smoke",
        },
    }
    _write_json(report_path, report_payload)
    print(json.dumps(report_payload, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
