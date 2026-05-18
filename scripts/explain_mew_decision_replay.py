#!/usr/bin/env python3
"""Create an LLM-ready replay prompt for a saved mew native-loop decision."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import json

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mew.implement_lane.decision_replay import (  # noqa: E402
    DEFAULT_DECISION_REPLAY_BACKEND,
    DEFAULT_DECISION_REPLAY_MODEL,
    ask_decision_replay_model,
    write_decision_replay_artifacts,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mew-artifact-root",
        required=True,
        help="mew artifact root, response_transcript.json, or native-provider-requests.json",
    )
    parser.add_argument("--out-json", required=True, help="output replay packet JSON path")
    parser.add_argument("--out-prompt", required=True, help="output LLM prompt path")
    parser.add_argument(
        "--out-analysis",
        default="",
        help="output model analysis JSON path; defaults to <out-json>.analysis.json",
    )
    parser.add_argument(
        "--auth-json",
        required=True,
        help="Codex/LLM auth JSON path; required because decision replay always calls the model",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_DECISION_REPLAY_MODEL,
        help=f"analysis model name; default: {DEFAULT_DECISION_REPLAY_MODEL}",
    )
    parser.add_argument(
        "--model-backend",
        default=DEFAULT_DECISION_REPLAY_BACKEND,
        help=f"analysis model backend; default: {DEFAULT_DECISION_REPLAY_BACKEND}",
    )
    parser.add_argument("--base-url", default="", help="override model backend base URL")
    parser.add_argument("--timeout", type=float, default=180.0, help="model call timeout in seconds")
    parser.add_argument(
        "--analysis-question",
        action="append",
        default=[],
        help="extra question to ask the analysis model; may be specified multiple times",
    )
    parser.add_argument(
        "--decision-sequence",
        type=int,
        default=None,
        help="transcript sequence to explain; defaults to the first mutation tool call",
    )
    parser.add_argument(
        "--context-items",
        type=int,
        default=16,
        help="number of transcript items before the decision to include",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        packet = write_decision_replay_artifacts(
            args.mew_artifact_root,
            out_json=args.out_json,
            out_prompt=args.out_prompt,
            decision_sequence=args.decision_sequence,
            context_items=max(1, args.context_items),
            analysis_questions=tuple(args.analysis_question),
        )
        analysis = ask_decision_replay_model(
            packet,
            auth_json=args.auth_json,
            model=args.model,
            model_backend=args.model_backend,
            base_url=args.base_url,
            timeout=args.timeout,
        )
    except Exception as exc:  # noqa: BLE001 - CLI boundary reports artifact problems.
        print(f"explain mew decision replay: {exc}", file=sys.stderr)
        return 1
    out_analysis = (
        Path(args.out_analysis)
        if args.out_analysis
        else Path(args.out_json).with_suffix(".analysis.json")
    )
    out_analysis.parent.mkdir(parents=True, exist_ok=True)
    out_analysis.write_text(json.dumps(analysis, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"decision sequence: {packet['decision'].get('sequence')}")
    print(f"decision tool: {packet['decision'].get('tool_name')}")
    print(f"decision replay JSON: {Path(args.out_json).expanduser().resolve(strict=False)}")
    print(f"decision replay prompt: {Path(args.out_prompt).expanduser().resolve(strict=False)}")
    print(f"decision replay analysis: {out_analysis.expanduser().resolve(strict=False)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
