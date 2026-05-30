#!/usr/bin/env python3
"""Generate a small fake-native mew_legacy vs codex_hot_path A/B artifact set."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mew.implement_lane.native_fake_provider import NativeFakeProvider, fake_call, fake_finish  # noqa: E402
from mew.implement_lane.native_tool_harness import run_native_implement_v2  # noqa: E402
from mew.implement_lane.tool_registry import CODEX_HOT_PATH_PROFILE_ID, MEW_LEGACY_PROFILE_ID  # noqa: E402
from mew.implement_lane.tool_surface_ab_report import write_tool_surface_ab_report  # noqa: E402
from mew.implement_lane.tool_surface_default_gate import evaluate_tool_surface_default_switch_gate  # noqa: E402
from mew.implement_lane.types import ImplementLaneInput  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-root",
        default="",
        help="artifact root; defaults to proof-artifacts/tool-surface-ab-smoke/<timestamp>",
    )
    parser.add_argument("--ab-pair-id", default="m6-24-tool-surface-smoke-v0")
    parser.add_argument("--fixed-ab-set-id", default="m6-24-tool-surface-smoke-v0")
    parser.add_argument("--reviewer-accepted", action="store_true")
    parser.add_argument("--expect-ready", action="store_true", help="return nonzero unless the gate is ready")
    parser.add_argument("--visible-bytes-safety-reason", default="")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = _output_root(args.output_root)
    root.mkdir(parents=True, exist_ok=True)
    baseline_root = root / "baseline-mew-legacy"
    candidate_root = root / "candidate-codex-hot-path"
    _run_mew_legacy(root / "baseline-workspace", baseline_root)
    _run_codex_hot_path(root / "candidate-workspace", candidate_root)
    report_path = root / "tool_surface_ab_report.json"
    report = write_tool_surface_ab_report(
        report_path,
        baseline_artifact_root=baseline_root,
        candidate_artifact_root=candidate_root,
        ab_pair_id=args.ab_pair_id,
        workspace_snapshot_id="sha256:fake-native-smoke-workspace",
        task_contract_hash="sha256:fake-native-smoke-task",
        model="fake-native-model",
        effort="high",
        budget_profile="fake-native-smoke",
    )
    gate = evaluate_tool_surface_default_switch_gate(
        [report],
        reviewer_accepted=args.reviewer_accepted,
        fixed_ab_set_id=args.fixed_ab_set_id,
        visible_bytes_safety_reason=args.visible_bytes_safety_reason,
    ).as_dict()
    gate_path = root / "tool_surface_default_switch_gate.json"
    gate_path.write_text(json.dumps(gate, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    payload = {
        "artifact_root": str(root.resolve(strict=False)),
        "baseline_artifact_root": str(baseline_root.resolve(strict=False)),
        "candidate_artifact_root": str(candidate_root.resolve(strict=False)),
        "ab_report": str(report_path.resolve(strict=False)),
        "default_switch_gate": str(gate_path.resolve(strict=False)),
        "ab_comparable": report.get("ab_comparable"),
        "gate_status": gate.get("status"),
        "can_switch_default": gate.get("can_switch_default"),
        "gate_reasons": gate.get("reasons") or [],
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"artifact_root: {payload['artifact_root']}")
        print(f"ab_report: {payload['ab_report']}")
        print(f"default_switch_gate: {payload['default_switch_gate']}")
        print(f"ab_comparable: {payload['ab_comparable']}")
        print(f"gate_status: {payload['gate_status']}")
        if payload["gate_reasons"]:
            print(f"gate_reasons: {', '.join(str(reason) for reason in payload['gate_reasons'])}")
    if args.expect_ready and gate.get("can_switch_default") is not True:
        return 1
    return 0


def _output_root(raw: str) -> Path:
    if raw:
        return Path(raw).expanduser()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return ROOT / "proof-artifacts" / "tool-surface-ab-smoke" / stamp


def _lane_input(workspace: Path, *, artifact_root: Path, profile_id: str) -> ImplementLaneInput:
    return ImplementLaneInput(
        work_session_id="ws-tool-surface-smoke",
        task_id="task-tool-surface-smoke",
        workspace=str(workspace),
        lane="implement_v2",
        model_backend="fake-native",
        model="fake-native-model",
        effort="high",
        task_contract={"goal": "change sample.txt and verify it"},
        lane_config={
            "allowed_read_roots": [str(workspace)],
            "allowed_write_roots": [str(workspace)],
            "allow_shell": True,
            "allow_verify": True,
            "auto_approve_writes": True,
            "artifact_dir": str(artifact_root),
            "tool_surface_profile_id": profile_id,
        },
    )


def _patch_text() -> str:
    return "\n".join(
        [
            "*** Begin Patch",
            "*** Update File: sample.txt",
            "@@",
            "-before",
            "+after",
            "*** End Patch",
        ]
    )


def _verify_command() -> str:
    return (
        f"{sys.executable} -c "
        "\"from pathlib import Path; assert Path('sample.txt').read_text().strip() == 'after'; print('ok')\""
    )


def _run_mew_legacy(workspace: Path, artifact_root: Path) -> None:
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "sample.txt").write_text("before\n", encoding="utf-8")
    provider = NativeFakeProvider.from_item_batches(
        [
            [
                fake_call("read-1", "read_file", {"path": "sample.txt"}, output_index=0),
                fake_call("patch-1", "apply_patch", {"patch": _patch_text(), "apply": True}, output_index=1),
                fake_call(
                    "verify-1",
                    "run_command",
                    {"command": _verify_command(), "command_intent": "verify", "cwd": "."},
                    output_index=2,
                ),
                fake_finish("finish-1", {"outcome": "completed", "summary": "done"}, output_index=3),
            ]
        ]
    )
    run_native_implement_v2(
        _lane_input(workspace, artifact_root=artifact_root, profile_id=MEW_LEGACY_PROFILE_ID),
        provider=provider,
        artifact_root=artifact_root,
        max_turns=1,
    )


def _run_codex_hot_path(workspace: Path, artifact_root: Path) -> None:
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "sample.txt").write_text("before\n", encoding="utf-8")
    provider = NativeFakeProvider.from_item_batches(
        [
            [
                fake_call(
                    "probe-1",
                    "exec_command",
                    {"cmd": f"{sys.executable} -c \"print(open('sample.txt').read().strip())\""},
                    output_index=0,
                ),
                fake_call("patch-1", "apply_patch", {"patch": _patch_text(), "apply": True}, output_index=1),
                fake_call(
                    "verify-1",
                    "exec_command",
                    {"cmd": _verify_command(), "command_intent": "verify"},
                    output_index=2,
                ),
                fake_finish("finish-1", {"outcome": "completed", "summary": "done"}, output_index=3),
            ]
        ]
    )
    run_native_implement_v2(
        _lane_input(workspace, artifact_root=artifact_root, profile_id=CODEX_HOT_PATH_PROFILE_ID),
        provider=provider,
        artifact_root=artifact_root,
        max_turns=1,
    )


if __name__ == "__main__":
    raise SystemExit(main())
