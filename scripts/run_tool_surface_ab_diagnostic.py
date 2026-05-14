#!/usr/bin/env python3
"""Run a paired live/pre-speed tool-surface A/B diagnostic and build gate artifacts."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mew.implement_lane.tool_registry import CODEX_HOT_PATH_PROFILE_ID, MEW_LEGACY_PROFILE_ID  # noqa: E402
from mew.implement_lane.tool_surface_ab_report import write_tool_surface_ab_report  # noqa: E402
from mew.implement_lane.tool_surface_default_gate import evaluate_tool_surface_default_switch_gate  # noqa: E402
from mew.mew_harbor_runner import RUN_MODES, command_cwd_for_task  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task_name", help="Terminal-Bench task name, e.g. prove-plus-comm.")
    parser.add_argument("--mode", choices=RUN_MODES, default="step-check-10min")
    parser.add_argument("--output-root", type=Path, default=None)
    parser.add_argument("--fixed-ab-set-id", default="m6-24-tool-surface-live-v0")
    parser.add_argument("--ab-pair-id", default="")
    parser.add_argument("--workspace-snapshot-id", default="")
    parser.add_argument("--task-contract-hash", default="")
    parser.add_argument("--model", default="gpt-5.5")
    parser.add_argument("--codex-auth-json", type=Path, default=Path.home() / ".codex" / "auth.json")
    parser.add_argument(
        "--command-cwd",
        default="",
        help=(
            "Override the container working directory for both child Harbor exec and mew work --cwd. "
            "Omit to use the task cwd map."
        ),
    )
    parser.add_argument("-k", type=int)
    parser.add_argument("-n", type=int)
    parser.add_argument("--work-guidance", action="append", default=[])
    parser.add_argument("--reviewer-accepted", action="store_true")
    parser.add_argument("--visible-bytes-safety-reason", default="")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    unsupported_reason = _unsupported_multi_trial_reason(args)
    if unsupported_reason:
        payload = {"status": "unsupported", "reason": unsupported_reason}
        return _print_payload(payload, as_json=args.json, exit_code=2)
    root = args.output_root or _default_output_root(args.task_name, args.mode)
    root = root.expanduser()
    baseline_jobs = root / "baseline-mew-legacy"
    candidate_jobs = root / "candidate-codex-hot-path"
    ab_pair_id = args.ab_pair_id or f"{args.fixed_ab_set_id}:{_task_slug(args.task_name)}:{args.mode}"
    commands = {
        "baseline": _diagnostic_command(args, profile_id=MEW_LEGACY_PROFILE_ID, jobs_dir=baseline_jobs),
        "candidate": _diagnostic_command(args, profile_id=CODEX_HOT_PATH_PROFILE_ID, jobs_dir=candidate_jobs),
    }
    if args.dry_run:
        return _print_payload(
            {
                "status": "dry_run",
                "artifact_root": str(root.resolve(strict=False)),
                "ab_pair_id": ab_pair_id,
                "fixed_ab_set_id": args.fixed_ab_set_id,
                "workspace_snapshot_id": args.workspace_snapshot_id,
                "task_contract_hash": args.task_contract_hash,
                "commands": commands,
            },
            as_json=args.json,
        )

    root.mkdir(parents=True, exist_ok=True)
    baseline_run = _run_diagnostic(commands["baseline"])
    candidate_run = _run_diagnostic(commands["candidate"])
    if not baseline_run.get("artifact_root") or not candidate_run.get("artifact_root"):
        payload = {
            "status": "failed",
            "artifact_root": str(root.resolve(strict=False)),
            "reason": "missing_profile_artifact_root",
            "baseline": baseline_run,
            "candidate": candidate_run,
        }
        _write_json(root / "tool_surface_ab_diagnostic.json", payload)
        return _print_payload(payload, as_json=args.json, exit_code=1)

    report_path = root / "tool_surface_ab_report.json"
    report = write_tool_surface_ab_report(
        report_path,
        baseline_artifact_root=str(baseline_run["artifact_root"]),
        candidate_artifact_root=str(candidate_run["artifact_root"]),
        ab_pair_id=ab_pair_id,
        workspace_snapshot_id=args.workspace_snapshot_id,
        task_contract_hash=args.task_contract_hash,
        model=args.model,
        effort="high",
        budget_profile=args.mode,
        provider_seed_supported=False,
    )
    gate = evaluate_tool_surface_default_switch_gate(
        [report],
        reviewer_accepted=args.reviewer_accepted,
        fixed_ab_set_id=args.fixed_ab_set_id,
        visible_bytes_safety_reason=args.visible_bytes_safety_reason,
    ).as_dict()
    gate = _block_gate_for_child_failures(gate, baseline=baseline_run, candidate=candidate_run)
    gate_path = root / "tool_surface_default_switch_gate.json"
    _write_json(gate_path, gate)
    payload = {
        "status": "completed",
        "artifact_root": str(root.resolve(strict=False)),
        "ab_pair_id": ab_pair_id,
        "fixed_ab_set_id": args.fixed_ab_set_id,
        "baseline": baseline_run,
        "candidate": candidate_run,
        "ab_report": str(report_path.resolve(strict=False)),
        "default_switch_gate": str(gate_path.resolve(strict=False)),
        "ab_comparable": report.get("ab_comparable"),
        "gate_status": gate.get("status"),
        "can_switch_default": gate.get("can_switch_default"),
        "gate_reasons": gate.get("reasons") or [],
    }
    _write_json(root / "tool_surface_ab_diagnostic.json", payload)
    return _print_payload(payload, as_json=args.json)


def _diagnostic_command(args: argparse.Namespace, *, profile_id: str, jobs_dir: Path) -> list[str]:
    command = [
        sys.executable,
        str(ROOT / "scripts" / "run_harbor_mew_diagnostic.py"),
        args.task_name,
        "--mode",
        args.mode,
        "--jobs-dir",
        str(jobs_dir),
        "--model",
        args.model,
        "--codex-auth-json",
        str(args.codex_auth_json),
        "--tool-surface-profile-id",
        profile_id,
    ]
    if args.k is not None:
        command.extend(["-k", str(args.k)])
    if args.n is not None:
        command.extend(["-n", str(args.n)])
    command.extend(["--command-cwd", command_cwd_for_task(args.task_name, args.command_cwd)])
    for guidance in args.work_guidance or []:
        command.extend(["--work-guidance", str(guidance)])
    return command


def _unsupported_multi_trial_reason(args: argparse.Namespace) -> str:
    if args.mode == "proof-5":
        return "proof-5 multi-trial A/B is not supported by this one-pair wrapper"
    if args.k is not None and args.k != 1:
        return "only -k 1 is supported by this one-pair wrapper"
    if args.n is not None and args.n != 1:
        return "only -n 1 is supported by this one-pair wrapper"
    return ""


def _block_gate_for_child_failures(
    gate: dict[str, object],
    *,
    baseline: dict[str, object],
    candidate: dict[str, object],
) -> dict[str, object]:
    updated = dict(gate)
    reasons = [str(reason) for reason in updated.get("reasons") or []]
    for label, run in (("baseline", baseline), ("candidate", candidate)):
        if int(run.get("returncode") or 0) != 0:
            reasons.append(f"{label}_diagnostic_failed")
        reasons.extend(_external_reward_block_reasons(label, run))
    if reasons != list(gate.get("reasons") or []):
        updated["reasons"] = sorted(set(reasons))
        updated["status"] = "blocked"
        updated["can_switch_default"] = False
    return updated


def _external_reward_block_reasons(label: str, run: dict[str, object]) -> list[str]:
    summary = run.get("summary")
    if not isinstance(summary, dict):
        return [f"{label}_external_reward_missing"]
    reward = summary.get("external_reward")
    if reward in (None, ""):
        return [f"{label}_external_reward_missing"]
    try:
        value = float(reward)
    except (TypeError, ValueError):
        return [f"{label}_external_reward_unparseable"]
    if value != 1.0:
        return [f"{label}_external_reward_not_one"]
    return []


def _run_diagnostic(command: list[str]) -> dict[str, object]:
    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    summaries = _json_object_lines(completed.stdout)
    summary = summaries[-1] if summaries else {}
    proof_manifest = Path(str(summary.get("proof_manifest_path") or ""))
    artifact_root = proof_manifest.parent if proof_manifest.name == "proof-manifest.json" else None
    return {
        "returncode": completed.returncode,
        "artifact_root": str(artifact_root.resolve(strict=False)) if artifact_root else "",
        "summary": summary,
        "stdout_tail": _tail(completed.stdout),
        "stderr_tail": _tail(completed.stderr),
    }


def _json_object_lines(text: str) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for line in str(text or "").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            records.append(payload)
    return records


def _tail(text: str, *, limit: int = 4000) -> str:
    value = str(text or "")
    return value[-limit:]


def _default_output_root(task_name: str, mode: str) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return ROOT / "proof-artifacts" / "tool-surface-ab-diagnostic" / f"{_task_slug(task_name)}-{mode}-{stamp}"


def _task_slug(task_name: str) -> str:
    return str(task_name or "task").removeprefix("terminal-bench/").replace("/", "-")


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _print_payload(payload: dict[str, object], *, as_json: bool, exit_code: int = 0) -> int:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"status: {payload.get('status')}")
        print(f"artifact_root: {payload.get('artifact_root')}")
        print(f"ab_pair_id: {payload.get('ab_pair_id')}")
        if payload.get("ab_report"):
            print(f"ab_report: {payload.get('ab_report')}")
        if payload.get("default_switch_gate"):
            print(f"default_switch_gate: {payload.get('default_switch_gate')}")
        reasons = payload.get("gate_reasons") or []
        if reasons:
            print(f"gate_reasons: {', '.join(str(reason) for reason in reasons)}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
