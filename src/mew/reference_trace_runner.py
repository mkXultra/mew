from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from mew.agent_trace import normalize_harbor_agent_trace, write_normalized_trace


DEFAULT_DATASET = "terminal-bench/terminal-bench-2"
DEFAULT_JOBS_ROOT = Path("proof-artifacts/terminal-bench/reference-trace")
REFERENCE_AGENTS = ("codex", "claude-code")


@dataclass(frozen=True)
class ReferenceAgentSpec:
    harbor_agent: str
    normalize_agent: str
    default_model: str


AGENT_SPECS: dict[str, ReferenceAgentSpec] = {
    "codex": ReferenceAgentSpec(harbor_agent="codex", normalize_agent="codex", default_model="gpt-5.5"),
    "claude-code": ReferenceAgentSpec(harbor_agent="claude-code", normalize_agent="claude", default_model="sonnet"),
}


@dataclass(frozen=True)
class ReferenceTraceRun:
    task_name: str
    agent: str
    dataset: str
    jobs_dir: Path
    k: int
    n: int
    model: str
    reasoning_effort: str
    env_file: Path | None
    codex_auth_json: Path | None

    @property
    def item_id(self) -> str:
        if self.task_name.startswith("terminal-bench/"):
            return self.task_name
        return f"terminal-bench/{self.task_name}"


def build_harbor_command(config: ReferenceTraceRun) -> list[str]:
    spec = AGENT_SPECS[config.agent]
    command = [
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
        "--jobs-dir",
        str(config.jobs_dir),
        "--agent",
        spec.harbor_agent,
        "-m",
        config.model,
    ]
    if config.reasoning_effort:
        command.extend(["--ak", f"reasoning_effort={config.reasoning_effort}"])
    if config.env_file is not None and config.env_file.exists():
        command.extend(["--env-file", str(config.env_file)])
    if config.agent == "codex" and config.codex_auth_json is not None and config.codex_auth_json.exists():
        command.extend(["--ae", f"CODEX_AUTH_JSON_PATH={config.codex_auth_json}"])
    return command


def harbor_environment() -> dict[str, str]:
    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = ".harbor" if not existing_pythonpath else f".harbor{os.pathsep}{existing_pythonpath}"
    return env


def normalize_latest_run(config: ReferenceTraceRun) -> list[dict[str, object]]:
    run_dir = latest_run_dir(config.jobs_dir)
    summaries: list[dict[str, object]] = []
    spec = AGENT_SPECS[config.agent]
    for task_dir in trial_dirs(run_dir):
        events, summary = normalize_harbor_agent_trace(agent=spec.normalize_agent, task_dir=task_dir)
        write_normalized_trace(events, summary, task_dir / "normalized-trace")
        summary_with_path = dict(summary)
        summary_with_path["task_dir"] = str(task_dir)
        summary_with_path["trace_dir"] = str(task_dir / "normalized-trace")
        summaries.append(summary_with_path)
    return summaries


def summarize_frontier_reference_metrics(summaries: Sequence[dict[str, object]]) -> dict[str, object]:
    summary_list = list(summaries)
    anchor_to_patch = [
        float(summary["time_from_first_anchor_to_first_patch_seconds"])
        for summary in summary_list
        if summary.get("time_from_first_anchor_to_first_patch_seconds") is not None
    ]
    broad_cycles = [
        int(summary.get("same_frontier_broad_cycle_count") or 0)
        for summary in summary_list
    ]
    return {
        "trace_count": len(summary_list),
        "anchor_to_patch_observed_count": len(anchor_to_patch),
        "min_time_from_first_anchor_to_first_patch_seconds": min(anchor_to_patch) if anchor_to_patch else None,
        "max_time_from_first_anchor_to_first_patch_seconds": max(anchor_to_patch) if anchor_to_patch else None,
        "same_frontier_broad_cycle_count": sum(broad_cycles),
    }


def latest_run_dir(jobs_dir: Path) -> Path:
    candidates = [path for path in jobs_dir.iterdir() if path.is_dir()]
    if not candidates:
        raise FileNotFoundError(f"no Harbor run directories found under {jobs_dir}")
    return max(candidates, key=lambda path: path.stat().st_mtime)


def trial_dirs(run_dir: Path) -> list[Path]:
    return sorted(
        path
        for path in run_dir.iterdir()
        if path.is_dir() and (path / "result.json").exists() and (path / "agent").is_dir()
    )


def make_jobs_dir(agent: str, task_name: str, jobs_root: Path, now: dt.datetime | None = None) -> Path:
    timestamp = (now or dt.datetime.now()).strftime("%Y%m%d-%H%M%S")
    task_slug = task_name.removeprefix("terminal-bench/").replace("/", "-")
    return jobs_root / f"{agent}-{task_slug}-{timestamp}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a Harbor reference agent for a Terminal-Bench task and normalize post-task logs."
    )
    parser.add_argument("task_name", help="Terminal-Bench task name, e.g. prove-plus-comm or terminal-bench/prove-plus-comm.")
    parser.add_argument("agent", choices=REFERENCE_AGENTS, help="Reference CLI agent to run.")
    parser.add_argument("--dataset", default=DEFAULT_DATASET)
    parser.add_argument("--jobs-root", type=Path, default=DEFAULT_JOBS_ROOT)
    parser.add_argument("--jobs-dir", type=Path, default=None)
    parser.add_argument("-k", type=int, default=1)
    parser.add_argument("-n", type=int, default=1)
    parser.add_argument("-m", "--model", default=None)
    parser.add_argument("--reasoning-effort", default="high")
    parser.add_argument("--env-file", type=Path, default=Path(".env.local"))
    parser.add_argument("--no-env-file", action="store_true", help="Do not pass --env-file to Harbor.")
    parser.add_argument("--codex-auth-json", type=Path, default=Path.home() / ".codex" / "auth.json")
    parser.add_argument("--no-codex-auth-json", action="store_true", help="Do not pass CODEX_AUTH_JSON_PATH for Codex.")
    parser.add_argument("--print-command", action="store_true", help="Print the Harbor command before running.")
    parser.add_argument("--dry-run", action="store_true", help="Print the Harbor command and exit without running.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    spec = AGENT_SPECS[args.agent]
    jobs_dir = args.jobs_dir or make_jobs_dir(args.agent, args.task_name, args.jobs_root)
    config = ReferenceTraceRun(
        task_name=args.task_name,
        agent=args.agent,
        dataset=args.dataset,
        jobs_dir=jobs_dir,
        k=args.k,
        n=args.n,
        model=args.model or spec.default_model,
        reasoning_effort=args.reasoning_effort,
        env_file=None if args.no_env_file else args.env_file,
        codex_auth_json=None if args.no_codex_auth_json else args.codex_auth_json,
    )
    command = build_harbor_command(config)
    if args.print_command or args.dry_run:
        print(" ".join(command))
    if args.dry_run:
        return 0
    completed = subprocess.run(command, cwd=Path.cwd(), env=harbor_environment(), check=False)
    summaries = normalize_latest_run(config)
    for summary in summaries:
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return completed.returncode


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
