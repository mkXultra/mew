#!/usr/bin/env python3
"""Run a counterfactual next-action diagnostic for a saved mew decision."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mew.implement_lane.decision_replay import (  # noqa: E402
    DEFAULT_COUNTERFACTUAL_NEXT_ACTION_MODEL,
    DEFAULT_DECISION_REPLAY_BACKEND,
    ask_counterfactual_next_action_model,
    write_counterfactual_next_action_artifacts,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mew-artifact-root",
        required=True,
        help="mew artifact root, response_transcript.json, or native-provider-requests.json",
    )
    parser.add_argument(
        "--decision-sequence",
        type=int,
        default=None,
        help="transcript sequence to diagnose; defaults to the first mutation tool call",
    )
    parser.add_argument(
        "--context-items",
        type=int,
        default=16,
        help="number of transcript items before the decision to include",
    )
    parser.add_argument(
        "--counterfactual-instruction",
        action="append",
        default=[],
        help="prompt/tool-contract instruction to test; may be specified multiple times",
    )
    parser.add_argument(
        "--analysis-question",
        default="",
        help="optional focused question for the analysis model",
    )
    parser.add_argument(
        "--expected-good",
        action="append",
        default=[],
        help="category hint that should be treated as a good predicted next action",
    )
    parser.add_argument(
        "--expected-bad",
        action="append",
        default=[],
        help="category hint that should be treated as a bad predicted next action",
    )
    parser.add_argument(
        "--auth-json",
        required=True,
        help="Codex/LLM auth JSON path; required because this CLI calls the model",
    )
    parser.add_argument("--out-json", required=True, help="output model prediction JSON path")
    parser.add_argument("--out-prompt", required=True, help="output LLM prompt path")
    parser.add_argument(
        "--model",
        default=DEFAULT_COUNTERFACTUAL_NEXT_ACTION_MODEL,
        help=f"analysis model name; default: {DEFAULT_COUNTERFACTUAL_NEXT_ACTION_MODEL}",
    )
    parser.add_argument(
        "--model-backend",
        default=DEFAULT_DECISION_REPLAY_BACKEND,
        help=f"analysis model backend; default: {DEFAULT_DECISION_REPLAY_BACKEND}",
    )
    parser.add_argument("--base-url", default="", help="override model backend base URL")
    parser.add_argument("--timeout", type=float, default=180.0, help="model call timeout in seconds")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        packet = write_counterfactual_next_action_artifacts(
            args.mew_artifact_root,
            out_prompt=args.out_prompt,
            decision_sequence=args.decision_sequence,
            context_items=max(1, args.context_items),
            counterfactual_instructions=tuple(args.counterfactual_instruction),
            analysis_question=args.analysis_question or None,
            expected_good=tuple(args.expected_good),
            expected_bad=tuple(args.expected_bad),
        )
        prediction = ask_counterfactual_next_action_model(
            packet,
            auth_json=args.auth_json,
            model=args.model,
            model_backend=args.model_backend,
            base_url=args.base_url,
            timeout=args.timeout,
        )
    except Exception as exc:  # noqa: BLE001 - CLI boundary reports artifact/model problems.
        print(f"counterfactual next action: {exc}", file=sys.stderr)
        return 1

    out_json = Path(args.out_json)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(prediction, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"decision sequence: {packet['selected_sequence']}")
    print(f"original decision tool: {packet['original_decision'].get('tool_name')}")
    print(f"counterfactual prompt: {Path(args.out_prompt).expanduser().resolve(strict=False)}")
    print(f"counterfactual prediction: {out_json.expanduser().resolve(strict=False)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
