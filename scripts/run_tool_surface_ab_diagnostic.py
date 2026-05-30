#!/usr/bin/env python3
"""Run a paired live/pre-speed tool-surface A/B diagnostic and build gate artifacts."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mew.implement_lane.tool_registry import CODEX_HOT_PATH_PROFILE_ID, MEW_LEGACY_PROFILE_ID  # noqa: E402
from mew.implement_lane.tool_surface_ab_report import write_tool_surface_ab_report  # noqa: E402
from mew.implement_lane.tool_surface_default_gate import evaluate_tool_surface_default_switch_gate  # noqa: E402
from mew.implement_lane.native_tool_schema import stable_json_hash  # noqa: E402
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
    parser.add_argument(
        "--external-reward-override-reason",
        default="",
        help="Explicit reviewer-visible reason to allow externally verified traces whose internal finish stayed blocked.",
    )
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
    workspace_snapshot_id = args.workspace_snapshot_id or _default_workspace_snapshot_id()
    task_contract_hash = args.task_contract_hash or _default_task_contract_hash(args)
    ab_pair_id = args.ab_pair_id or f"{args.fixed_ab_set_id}:{_task_slug(args.task_name)}:{args.mode}"
    commands = _profile_commands(
        args,
        root=root,
        auth_json_paths={"baseline": args.codex_auth_json, "candidate": args.codex_auth_json},
    )
    if args.dry_run:
        return _print_payload(
            {
                "status": "dry_run",
                "artifact_root": str(root.resolve(strict=False)),
                "ab_pair_id": ab_pair_id,
                "fixed_ab_set_id": args.fixed_ab_set_id,
                "workspace_snapshot_id": workspace_snapshot_id,
                "task_contract_hash": task_contract_hash,
                "commands": commands,
            },
            as_json=args.json,
        )

    root.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(prefix="mew-tool-surface-ab-auth-") as auth_tmp:
            commands = _profile_commands(
                args,
                root=root,
                auth_json_paths=_copy_parallel_auth_files(Path(auth_tmp), args.codex_auth_json),
            )
            baseline_run, candidate_run = _run_profile_diagnostics(commands)
    except Exception as exc:
        payload = {
            "status": "failed",
            "artifact_root": str(root.resolve(strict=False)),
            "reason": "parallel_auth_preparation_failed",
            "detail": _safe_error_detail(exc),
        }
        _write_json(root / "tool_surface_ab_diagnostic.json", payload)
        return _print_payload(payload, as_json=args.json, exit_code=1)
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
        workspace_snapshot_id=workspace_snapshot_id,
        task_contract_hash=task_contract_hash,
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
        external_reward_override_reason=args.external_reward_override_reason,
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


def _profile_commands(
    args: argparse.Namespace,
    *,
    root: Path,
    auth_json_paths: dict[str, Path],
) -> dict[str, list[str]]:
    return {
        "baseline": _diagnostic_command(
            args,
            profile_id=MEW_LEGACY_PROFILE_ID,
            jobs_dir=root / "baseline-mew-legacy",
            codex_auth_json=auth_json_paths["baseline"],
        ),
        "candidate": _diagnostic_command(
            args,
            profile_id=CODEX_HOT_PATH_PROFILE_ID,
            jobs_dir=root / "candidate-codex-hot-path",
            codex_auth_json=auth_json_paths["candidate"],
        ),
    }


def _copy_parallel_auth_files(temp_root: Path, source_auth_json: Path) -> dict[str, Path]:
    """Give each child process an isolated auth-file copy.

    Codex OAuth refresh writes back to auth.json. Running the two A/B profiles
    with the same mutable auth file can race on refresh-token rotation and make
    the comparison nondeterministic. The wrapper does not refresh or mutate the
    source auth file; it only copies the current file into per-profile temp
    files that live for the child process lifetime.
    """

    source_auth_json = source_auth_json.expanduser()
    auth_dir = temp_root / "auth"
    auth_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "baseline": auth_dir / "baseline-mew-legacy.auth.json",
        "candidate": auth_dir / "candidate-codex-hot-path.auth.json",
    }
    for path in paths.values():
        shutil.copyfile(source_auth_json, path)
        path.chmod(0o600)
    return paths


def _run_profile_diagnostics(commands: dict[str, list[str]]) -> tuple[dict[str, object], dict[str, object]]:
    """Run baseline and candidate diagnostics concurrently.

    The paired A/B wrapper is intentionally single-pair, but the two child
    profiles are independent once the shared output root is allocated.
    """

    with ThreadPoolExecutor(max_workers=2) as executor:
        baseline = executor.submit(_run_diagnostic_safely, commands["baseline"])
        candidate = executor.submit(_run_diagnostic_safely, commands["candidate"])
        return baseline.result(), candidate.result()


def _diagnostic_command(
    args: argparse.Namespace,
    *,
    profile_id: str,
    jobs_dir: Path,
    codex_auth_json: Path,
) -> list[str]:
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
        str(codex_auth_json),
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


def _run_diagnostic_safely(command: list[str]) -> dict[str, object]:
    try:
        return _run_diagnostic(command)
    except Exception as exc:
        return {
            "returncode": 1,
            "artifact_root": "",
            "summary": {},
            "stdout_tail": "",
            "stderr_tail": _safe_error_detail(exc),
            "error": {
                "type": exc.__class__.__name__,
                "detail": _safe_error_detail(exc),
                "command": _redacted_command(command),
            },
        }


def _safe_error_detail(exc: Exception) -> str:
    return f"{exc.__class__.__name__}: {exc}"[:1000]


def _redacted_command(command: list[str]) -> list[str]:
    redacted = [str(part) for part in command]
    for index, part in enumerate(redacted):
        if part == "--codex-auth-json" and index + 1 < len(redacted):
            redacted[index + 1] = "<isolated-auth-json>"
    return redacted


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


def _default_workspace_snapshot_id() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    head = completed.stdout.strip()
    if completed.returncode == 0 and head:
        return f"git:{head}"
    return stable_json_hash({"repo_root": str(ROOT.resolve(strict=False))})


def _default_task_contract_hash(args: argparse.Namespace) -> str:
    return stable_json_hash(
        {
            "task_name": str(args.task_name),
            "command_cwd": command_cwd_for_task(args.task_name, args.command_cwd),
            "work_guidance": [str(item) for item in args.work_guidance or []],
        }
    )


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
