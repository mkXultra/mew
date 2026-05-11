from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from mew.agent_trace import normalize_harbor_agent_trace, write_normalized_trace
from mew.reference_trace_runner import latest_run_dir, trial_dirs


DEFAULT_DATASET = "terminal-bench/terminal-bench-2"
DEFAULT_JOBS_ROOT = Path("proof-artifacts/terminal-bench/harbor-smoke")
DEFAULT_WORK_GUIDANCE = "selected_lane=implement_v2 write_integration_observation_detail=true"
DEFAULT_INSTALL_COMMAND = (
    "apt-get update && apt-get install -y python3 python3-pip python3-venv "
    "&& python3 -m pip install --break-system-packages -e /mew"
)
DEFAULT_AUTH_CONTAINER_PATH = Path("/codex-auth/auth.json")
RUN_MODES = ("step-check-10min", "speed-proof", "proof-5")


@dataclass(frozen=True)
class MewHarborRunModeDefaults:
    k: int
    n: int
    timeout_seconds: int
    timeout_reserve_seconds: int
    work_guidance: str
    require_observer_detail: bool


RUN_MODE_DEFAULTS: dict[str, MewHarborRunModeDefaults] = {
    "step-check-10min": MewHarborRunModeDefaults(
        k=1,
        n=1,
        timeout_seconds=660,
        timeout_reserve_seconds=60,
        work_guidance=DEFAULT_WORK_GUIDANCE,
        require_observer_detail=True,
    ),
    "speed-proof": MewHarborRunModeDefaults(
        k=1,
        n=1,
        timeout_seconds=1800,
        timeout_reserve_seconds=60,
        work_guidance=DEFAULT_WORK_GUIDANCE,
        require_observer_detail=True,
    ),
    "proof-5": MewHarborRunModeDefaults(
        k=5,
        n=1,
        timeout_seconds=1800,
        timeout_reserve_seconds=60,
        work_guidance=DEFAULT_WORK_GUIDANCE,
        require_observer_detail=True,
    ),
}


@dataclass(frozen=True)
class MewHarborRun:
    task_name: str
    dataset: str
    jobs_dir: Path
    repo_root: Path
    codex_auth_json: Path
    k: int
    n: int
    model: str
    model_timeout: int
    max_steps: int
    timeout_seconds: int
    timeout_reserve_seconds: int
    agent_timeout_multiplier: int
    work_guidance: str
    install_command: str
    run_mode: str = "step-check-10min"
    require_observer_detail: bool = True
    workframe_variant: str = ""

    @property
    def item_id(self) -> str:
        if self.task_name.startswith("terminal-bench/"):
            return self.task_name
        return f"terminal-bench/{self.task_name}"


def make_jobs_dir(
    task_name: str,
    jobs_root: Path,
    now: dt.datetime | None = None,
    run_mode: str = "step-check-10min",
    workframe_variant: str = "",
) -> Path:
    timestamp = (now or dt.datetime.now()).strftime("%Y%m%d-%H%M%S")
    task_slug = task_name.removeprefix("terminal-bench/").replace("/", "-")
    mode_slug = run_mode.replace("_", "-")
    variant_slug = workframe_variant.strip().replace("_", "-") if workframe_variant else ""
    variant_part = f"-wf-{variant_slug}" if variant_slug else ""
    return jobs_root / f"mew-{task_slug}-{mode_slug}{variant_part}-{timestamp}"


def work_guidance_with_workframe_variant(work_guidance: str, workframe_variant: str) -> str:
    variant = str(workframe_variant or "").strip()
    guidance = str(work_guidance or "").strip()
    if not variant:
        return guidance
    if "workframe_variant" in guidance or "work_frame_variant" in guidance:
        return guidance
    return " ".join(part for part in (guidance, f"workframe_variant={variant}") if part)


def build_mew_work_command_template(config: MewHarborRun) -> str:
    guidance = shlex.quote(work_guidance_with_workframe_variant(config.work_guidance, config.workframe_variant))
    return (
        "mew work --oneshot "
        "--instruction {instruction_shell} "
        "--cwd /app "
        "--allow-read . "
        "--allow-read /etc/apt "
        "--allow-read /tmp "
        "--allow-write . "
        "--allow-write /usr/local/bin "
        "--allow-write /tmp "
        "--allow-shell "
        "--allow-verify "
        "--approval-mode accept-edits "
        "--defer-verify "
        "--no-prompt-approval "
        f"--auth {DEFAULT_AUTH_CONTAINER_PATH} "
        "--model-backend codex "
        f"--model {shlex.quote(config.model)} "
        f"--model-timeout {int(config.model_timeout)} "
        "{max_wall_seconds_option} "
        f"--max-steps {int(config.max_steps)} "
        f"--work-guidance {guidance} "
        "--report {report_path} "
        "--artifacts {artifact_dir} "
        "--json"
    )


def build_mounts_json(config: MewHarborRun) -> str:
    mounts = [
        {
            "type": "bind",
            "source": str(config.repo_root),
            "target": "/mew",
        },
        {
            "type": "bind",
            "source": str(config.codex_auth_json),
            "target": str(DEFAULT_AUTH_CONTAINER_PATH),
        },
    ]
    return json.dumps(mounts, separators=(",", ":"))


def build_harbor_command(config: MewHarborRun) -> list[str]:
    return [
        "harbor",
        "run",
        "-d",
        config.dataset,
        "-i",
        config.item_id,
        "-k",
        str(config.k),
        "-n",
        str(config.n),
        "-y",
        "--agent-timeout-multiplier",
        str(config.agent_timeout_multiplier),
        "--jobs-dir",
        str(config.jobs_dir),
        "--agent-import-path",
        "mew_terminal_bench_agent:MewTerminalBenchAgent",
        "--ak",
        f"install_command={config.install_command}",
        "--ak",
        "command_cwd=/app",
        "--ak",
        "container_repo_root=/mew",
        "--ak",
        f"timeout_seconds={int(config.timeout_seconds)}",
        "--ak",
        f"timeout_reserve_seconds={int(config.timeout_reserve_seconds)}",
        "--ak",
        f"command_template={build_mew_work_command_template(config)}",
        "--mounts-json",
        build_mounts_json(config),
    ]


def harbor_environment() -> dict[str, str]:
    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = ".harbor" if not existing_pythonpath else f".harbor{os.pathsep}{existing_pythonpath}"
    return env


def summarize_latest_run(config: MewHarborRun) -> list[dict[str, object]]:
    run_dir = latest_run_dir(config.jobs_dir)
    summaries: list[dict[str, object]] = []
    for task_dir in trial_dirs(run_dir):
        normalized_summary: dict[str, object] = {}
        agent_task_dir = task_dir / "agent" / "terminal-bench-harbor-smoke" / "unknown-task"
        normalize_task_dir = agent_task_dir if agent_task_dir.exists() else task_dir
        try:
            events, normalized_summary = normalize_harbor_agent_trace(agent="mew", task_dir=normalize_task_dir)
            write_normalized_trace(events, normalized_summary, task_dir / "normalized-trace")
        except Exception as exc:  # pragma: no cover - defensive around Harbor format drift.
            normalized_summary = {"normalize_error": str(exc)}
        summary = collect_mew_trial_summary(task_dir)
        summary["task_dir"] = str(task_dir)
        summary["trace_dir"] = str(task_dir / "normalized-trace")
        summary["normalized_trace"] = normalized_summary
        summaries.append(summary)
    return summaries


def collect_mew_trial_summary(task_dir: Path) -> dict[str, object]:
    report_path = task_dir / "agent" / "terminal-bench-harbor-smoke" / "unknown-task" / "mew-report.json"
    report = read_json(report_path)
    unknown_task_dir = task_dir / "agent" / "terminal-bench-harbor-smoke" / "unknown-task"
    manifest_dir = _implement_v2_artifact_dir(unknown_task_dir)
    proof_manifest_path = manifest_dir / "proof-manifest.json"
    history_path = manifest_dir / "history.json"
    transcript_path = _implement_v2_transcript_path(manifest_dir)
    result_path = task_dir / "result.json"
    command_transcript_path = unknown_task_dir / "command-transcript.json"
    verifier_stdout_path = task_dir / "verifier" / "test-stdout.txt"
    verifier_reward_path = task_dir / "verifier" / "reward.txt"
    manifest = read_json(proof_manifest_path)
    result = read_json(result_path)
    report_metrics = _implement_lane_metrics(report)
    manifest_metrics = manifest.get("metrics") if isinstance(manifest.get("metrics"), dict) else {}
    metrics = {**manifest_metrics, **report_metrics}
    workframe_metrics = metrics.get("workframe") if isinstance(metrics.get("workframe"), dict) else {}
    observation = metrics.get("integration_observation") if isinstance(metrics.get("integration_observation"), dict) else {}
    observation_summary = (
        observation.get("summary")
        if isinstance(observation.get("summary"), dict)
        else {}
    )
    artifact_ref = observation.get("artifact_ref") if isinstance(observation.get("artifact_ref"), str) else ""
    detail_path = manifest_dir / artifact_ref if artifact_ref else None
    native_status = _native_artifact_status(manifest_dir)
    return {
        "external_reward": extract_harbor_reward(result),
        "work_exit_code": report.get("work_exit_code"),
        "stop_reason": ((report.get("work_report") or {}).get("stop_reason") if isinstance(report.get("work_report"), dict) else None),
        "model_turns": metrics.get("model_turns") if metrics.get("model_turns") is not None else metrics.get("turn_count"),
        "tool_calls": metrics.get("tool_calls") if metrics.get("tool_calls") is not None else metrics.get("call_count"),
        "tool_results": metrics.get("tool_results") if metrics.get("tool_results") is not None else metrics.get("output_count"),
        "wall_elapsed_seconds": metrics.get("wall_elapsed_seconds"),
        "workframe_variant": workframe_metrics.get("variant"),
        "observer_detail_enabled": bool(observation.get("debug_detail_enabled")),
        "observer_detail_written": bool(observation_summary.get("detail_written")),
        "observer_detail_ref": artifact_ref,
        "observer_detail_exists": bool(detail_path and detail_path.exists()),
        "observer_detail_path": str(detail_path) if detail_path else "",
        "native_observation_present": native_status["valid"],
        "native_observation_reason": native_status["reason"],
        "native_transcript_path": str(native_status["transcript_path"]) if native_status["transcript_path"] else "",
        "native_response_items_path": str(native_status["items_path"]) if native_status["items_path"] else "",
        "native_pairing_valid": native_status["pairing_valid"],
        "native_call_count": native_status["call_count"],
        "native_output_count": native_status["output_count"],
        "proof_manifest_path": str(proof_manifest_path),
        "history_path": str(history_path),
        "transcript_path": str(transcript_path),
        "mew_report_path": str(report_path),
        "result_path": str(result_path),
        "command_transcript_path": str(command_transcript_path),
        "verifier_stdout_path": str(verifier_stdout_path),
        "verifier_reward_path": str(verifier_reward_path),
        "prompt_chars": observation_summary.get("prompt_chars"),
        "model_elapsed_seconds": observation_summary.get("model_elapsed_seconds"),
    }


def _implement_v2_artifact_dir(unknown_task_dir: Path) -> Path:
    """Return the active implement_v2 artifact directory.

    The legacy model-JSON runtime wrote under ``unknown-task/implement_v2``.
    The native transcript runtime writes authoritative artifacts directly into
    the configured artifact root, which is ``unknown-task`` for Harbor.
    """

    native_dir = unknown_task_dir
    legacy_dir = unknown_task_dir / "implement_v2"
    if _native_artifact_status(native_dir)["valid"]:
        return native_dir
    if (legacy_dir / "proof-manifest.json").exists():
        return legacy_dir
    if (native_dir / "proof-manifest.json").exists():
        return native_dir
    return legacy_dir


def _implement_v2_transcript_path(manifest_dir: Path) -> Path:
    native = manifest_dir / "response_transcript.json"
    if native.exists():
        return native
    return manifest_dir / "transcript.json"


def _implement_lane_metrics(report: dict[str, object]) -> dict[str, object]:
    work_report = report.get("work_report") if isinstance(report.get("work_report"), dict) else {}
    result = work_report.get("implement_lane_result") if isinstance(work_report.get("implement_lane_result"), dict) else {}
    metrics = result.get("metrics") if isinstance(result.get("metrics"), dict) else {}
    return dict(metrics)


def _native_artifact_status(manifest_dir: Path) -> dict[str, object]:
    transcript_path = manifest_dir / "response_transcript.json"
    items_path = manifest_dir / "response_items.jsonl"
    manifest = read_json(manifest_dir / "proof-manifest.json")
    if not manifest:
        return _native_status(False, "missing_manifest", transcript_path, items_path)
    if manifest.get("runtime_id") != "implement_v2_native_transcript_loop":
        return _native_status(False, "non_native_runtime", transcript_path, items_path)
    if manifest.get("transport_kind") != "provider_native":
        return _native_status(False, "non_native_transport", transcript_path, items_path)
    if not transcript_path.exists() or not items_path.exists():
        return _native_status(False, "missing_native_files", transcript_path, items_path)

    transcript = read_json(transcript_path)
    items = transcript.get("items") if isinstance(transcript.get("items"), list) else []
    if not items:
        return _native_status(False, "empty_transcript", transcript_path, items_path)
    jsonl_items = _read_jsonl_records(items_path)
    if not jsonl_items:
        return _native_status(False, "empty_or_invalid_response_items", transcript_path, items_path)
    if jsonl_items != items:
        return _native_status(False, "response_items_mismatch", transcript_path, items_path)

    pairing = manifest.get("pairing") if isinstance(manifest.get("pairing"), dict) else {}
    manifest_call_count = _int_metric(pairing.get("call_count"))
    manifest_output_count = _int_metric(pairing.get("output_count"))
    pairing_valid = bool(pairing.get("valid"))
    pairing_errors = pairing.get("errors") if isinstance(pairing.get("errors"), list) else []
    call_ids, output_ids, item_errors = _native_call_output_ids(items)
    if not pairing_valid:
        return _native_status(False, "invalid_manifest_pairing", transcript_path, items_path)
    if pairing_errors:
        return _native_status(False, "manifest_pairing_errors", transcript_path, items_path)
    if manifest_call_count is None or manifest_output_count is None:
        return _native_status(False, "missing_manifest_pairing_counts", transcript_path, items_path)
    if item_errors:
        return _native_status(False, item_errors[0], transcript_path, items_path)
    if not call_ids or not output_ids:
        return _native_status(False, "empty_call_output_pairing", transcript_path, items_path)
    if len(call_ids) != len(set(call_ids)) or len(output_ids) != len(set(output_ids)):
        return _native_status(False, "duplicate_call_output_ids", transcript_path, items_path)
    if set(call_ids) != set(output_ids):
        return _native_status(False, "call_output_id_mismatch", transcript_path, items_path)
    if manifest_call_count is not None and manifest_call_count != len(call_ids):
        return _native_status(False, "manifest_call_count_mismatch", transcript_path, items_path)
    if manifest_output_count is not None and manifest_output_count != len(output_ids):
        return _native_status(False, "manifest_output_count_mismatch", transcript_path, items_path)
    return {
        **_native_status(True, "ok", transcript_path, items_path),
        "pairing_valid": True,
        "call_count": len(call_ids),
        "output_count": len(output_ids),
    }


def _native_status(valid: bool, reason: str, transcript_path: Path, items_path: Path) -> dict[str, object]:
    return {
        "valid": valid,
        "reason": reason,
        "transcript_path": transcript_path if transcript_path.exists() else "",
        "items_path": items_path if items_path.exists() else "",
        "pairing_valid": False,
        "call_count": 0,
        "output_count": 0,
    }


def _read_jsonl_records(path: Path) -> list[object]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    records: list[object] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            return []
        if not isinstance(payload, dict):
            return []
        records.append(payload)
    return records


def _native_call_output_ids(items: list[object]) -> tuple[list[str], list[str], list[str]]:
    known_non_tool_kinds = {"input_message", "assistant_message", "message", "reasoning"}
    call_ids: list[str] = []
    output_ids: list[str] = []
    errors: list[str] = []
    call_kind_by_id: dict[str, str] = {}
    output_kind_by_id: dict[str, str] = {}
    for item in items:
        if not isinstance(item, dict):
            errors.append("non_object_transcript_item")
            continue
        kind = str(item.get("kind") or "")
        if kind in {"function_call", "custom_tool_call", "finish_call"}:
            call_id = str(item.get("call_id") or "")
            if not call_id:
                errors.append("missing_call_id")
                continue
            call_ids.append(call_id)
            call_kind_by_id[call_id] = kind
        elif kind in {"function_call_output", "custom_tool_call_output", "finish_output"}:
            call_id = str(item.get("call_id") or "")
            if not call_id:
                errors.append("missing_output_call_id")
                continue
            output_ids.append(call_id)
            output_kind_by_id[call_id] = kind
        elif kind not in known_non_tool_kinds:
            errors.append("unknown_native_item_kind")
    expected_output_kind = {
        "function_call": "function_call_output",
        "custom_tool_call": "custom_tool_call_output",
        "finish_call": "finish_output",
    }
    for call_id, call_kind in call_kind_by_id.items():
        output_kind = output_kind_by_id.get(call_id)
        if output_kind and output_kind != expected_output_kind[call_kind]:
            errors.append("call_output_kind_mismatch")
    return call_ids, output_ids, errors


def _int_metric(value: object) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    return None


def read_json(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def extract_harbor_reward(result: dict[str, object]) -> object:
    if "reward" in result:
        return result.get("reward")
    verifier_result = result.get("verifier_result")
    if isinstance(verifier_result, dict):
        rewards = verifier_result.get("rewards")
        if isinstance(rewards, dict) and "reward" in rewards:
            return rewards.get("reward")
    return None


def observer_detail_missing(summaries: Sequence[dict[str, object]]) -> bool:
    if not summaries:
        return True
    return any(
        not (
            summary.get("native_observation_present")
            or (
                summary.get("observer_detail_enabled")
                and summary.get("observer_detail_written")
                and summary.get("observer_detail_exists")
            )
        )
        for summary in summaries
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run mew through Harbor for a Terminal-Bench task with fixed diagnostic "
            "instrumentation and summarize the resulting artifacts."
        )
    )
    parser.add_argument("task_name", help="Terminal-Bench task name, e.g. make-mips-interpreter.")
    parser.add_argument(
        "--mode",
        choices=RUN_MODES,
        default="step-check-10min",
        help="Run shape preset: 10 minute diagnostic, one-trial speed proof, or five-trial proof.",
    )
    parser.add_argument("--dataset", default=DEFAULT_DATASET)
    parser.add_argument("--jobs-root", type=Path, default=DEFAULT_JOBS_ROOT)
    parser.add_argument("--jobs-dir", type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--codex-auth-json", type=Path, default=Path.home() / ".codex" / "auth.json")
    parser.add_argument("-k", type=int)
    parser.add_argument("-n", type=int)
    parser.add_argument("-m", "--model", default="gpt-5.5")
    parser.add_argument("--model-timeout", type=int, default=600)
    parser.add_argument("--max-steps", type=int, default=30)
    parser.add_argument("--timeout-seconds", type=int)
    parser.add_argument("--timeout-reserve-seconds", type=int)
    parser.add_argument("--agent-timeout-multiplier", type=int, default=2)
    parser.add_argument("--work-guidance")
    parser.add_argument(
        "--workframe-variant",
        default="",
        help="WorkFrame reducer variant to pass into mew work, e.g. transition_contract, current, or transcript_first.",
    )
    parser.add_argument("--install-command", default=DEFAULT_INSTALL_COMMAND)
    parser.add_argument(
        "--allow-missing-observer-detail",
        action="store_true",
        help="Do not fail the diagnostic if integration observation detail was not written.",
    )
    parser.add_argument("--print-command", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    mode_defaults = RUN_MODE_DEFAULTS[args.mode]
    require_observer_detail = mode_defaults.require_observer_detail and not args.allow_missing_observer_detail
    jobs_dir = args.jobs_dir or make_jobs_dir(
        args.task_name,
        args.jobs_root,
        run_mode=args.mode,
        workframe_variant=args.workframe_variant,
    )
    config = MewHarborRun(
        task_name=args.task_name,
        dataset=args.dataset,
        jobs_dir=jobs_dir,
        repo_root=args.repo_root,
        codex_auth_json=args.codex_auth_json,
        k=args.k if args.k is not None else mode_defaults.k,
        n=args.n if args.n is not None else mode_defaults.n,
        model=args.model,
        model_timeout=args.model_timeout,
        max_steps=args.max_steps,
        timeout_seconds=args.timeout_seconds if args.timeout_seconds is not None else mode_defaults.timeout_seconds,
        timeout_reserve_seconds=(
            args.timeout_reserve_seconds
            if args.timeout_reserve_seconds is not None
            else mode_defaults.timeout_reserve_seconds
        ),
        agent_timeout_multiplier=args.agent_timeout_multiplier,
        work_guidance=args.work_guidance or mode_defaults.work_guidance,
        install_command=args.install_command,
        run_mode=args.mode,
        require_observer_detail=require_observer_detail,
        workframe_variant=args.workframe_variant,
    )
    command = build_harbor_command(config)
    if args.print_command or args.dry_run:
        print(" ".join(shlex.quote(part) for part in command))
    if args.dry_run:
        return 0

    completed = subprocess.run(command, cwd=Path.cwd(), env=harbor_environment(), check=False)
    summaries = summarize_latest_run(config)
    for summary in summaries:
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    if config.require_observer_detail and observer_detail_missing(summaries):
        return completed.returncode or 2
    return completed.returncode


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
