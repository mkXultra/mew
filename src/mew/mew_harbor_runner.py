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
) -> Path:
    timestamp = (now or dt.datetime.now()).strftime("%Y%m%d-%H%M%S")
    task_slug = task_name.removeprefix("terminal-bench/").replace("/", "-")
    mode_slug = run_mode.replace("_", "-")
    return jobs_root / f"mew-{task_slug}-{mode_slug}-{timestamp}"


def build_mew_work_command_template(config: MewHarborRun) -> str:
    guidance = shlex.quote(config.work_guidance)
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
    manifest_dir = task_dir / "agent" / "terminal-bench-harbor-smoke" / "unknown-task" / "implement_v2"
    proof_manifest_path = manifest_dir / "proof-manifest.json"
    history_path = manifest_dir / "history.json"
    transcript_path = manifest_dir / "transcript.json"
    result_path = task_dir / "result.json"
    command_transcript_path = task_dir / "agent" / "terminal-bench-harbor-smoke" / "unknown-task" / "command-transcript.json"
    verifier_stdout_path = task_dir / "verifier" / "test-stdout.txt"
    verifier_reward_path = task_dir / "verifier" / "reward.txt"
    manifest = read_json(proof_manifest_path)
    result = read_json(result_path)
    metrics = manifest.get("metrics") if isinstance(manifest.get("metrics"), dict) else {}
    observation = metrics.get("integration_observation") if isinstance(metrics.get("integration_observation"), dict) else {}
    observation_summary = (
        observation.get("summary")
        if isinstance(observation.get("summary"), dict)
        else {}
    )
    artifact_ref = observation.get("artifact_ref") if isinstance(observation.get("artifact_ref"), str) else ""
    detail_path = manifest_dir / artifact_ref if artifact_ref else None
    return {
        "external_reward": result.get("reward"),
        "work_exit_code": report.get("work_exit_code"),
        "stop_reason": ((report.get("work_report") or {}).get("stop_reason") if isinstance(report.get("work_report"), dict) else None),
        "model_turns": metrics.get("model_turns"),
        "tool_calls": metrics.get("tool_calls"),
        "tool_results": metrics.get("tool_results"),
        "wall_elapsed_seconds": metrics.get("wall_elapsed_seconds"),
        "observer_detail_enabled": bool(observation.get("debug_detail_enabled")),
        "observer_detail_written": bool(observation_summary.get("detail_written")),
        "observer_detail_ref": artifact_ref,
        "observer_detail_exists": bool(detail_path and detail_path.exists()),
        "observer_detail_path": str(detail_path) if detail_path else "",
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


def read_json(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def observer_detail_missing(summaries: Sequence[dict[str, object]]) -> bool:
    if not summaries:
        return True
    return any(
        not summary.get("observer_detail_enabled")
        or not summary.get("observer_detail_written")
        or not summary.get("observer_detail_exists")
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
    parser.add_argument("--model-timeout", type=int, default=300)
    parser.add_argument("--max-steps", type=int, default=30)
    parser.add_argument("--timeout-seconds", type=int)
    parser.add_argument("--timeout-reserve-seconds", type=int)
    parser.add_argument("--agent-timeout-multiplier", type=int, default=2)
    parser.add_argument("--work-guidance")
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
    jobs_dir = args.jobs_dir or make_jobs_dir(args.task_name, args.jobs_root, run_mode=args.mode)
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
