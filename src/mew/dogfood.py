import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time

from .brief import recent_activity, next_move
from .config import LOG_FILE, MODEL_TRACE_FILE, STATE_DIR, STATE_FILE
from .programmer import create_task_plan
from .project_snapshot import format_project_snapshot, refresh_project_snapshot
from .read_tools import is_sensitive_path
from .state import default_state, migrate_state, next_id, reconcile_next_ids
from .thoughts import dropped_thread_warning_for_context
from .timeutil import now_iso


DOGFOOD_SKIP_DIR_NAMES = {
    ".git",
    ".mew",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".uv-cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
}
DOGFOOD_MAX_COPY_FILE_BYTES = 1_000_000
DOGFOOD_READY_CODING_TASK_TITLE = "Dogfood programmer loop smoke task"
DOGFOOD_SCENARIOS = ("interrupted-focus", "trace-smoke", "memory-search")


DOGFOOD_README = """# Mew Dogfood Workspace

This temporary workspace is used to test mew's passive runtime.

Expected behavior:
- inspect a small amount of allowed local context,
- record useful memory,
- keep recent passive activity visible,
- avoid noisy or unsafe effects.
"""


def prepare_dogfood_workspace(path=None):
    if path:
        workspace = Path(path).expanduser()
        if is_sensitive_path(workspace):
            raise ValueError(
                "dogfood workspace is inside a sensitive path; use a temporary directory outside .mew"
            )
        workspace.mkdir(parents=True, exist_ok=True)
        created_temp = False
    else:
        workspace = Path(tempfile.mkdtemp(prefix="mew-dogfood-"))
        created_temp = True

    readme = workspace / "README.md"
    if not readme.exists():
        readme.write_text(DOGFOOD_README, encoding="utf-8")
    return workspace.resolve(), created_temp


def _is_relative_to(path, root):
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def copy_source_workspace(source, workspace, max_file_bytes=DOGFOOD_MAX_COPY_FILE_BYTES):
    source = Path(source).expanduser()
    if not source.is_absolute():
        source = (Path.cwd() / source).resolve()
    else:
        source = source.resolve()
    workspace = Path(workspace).expanduser().resolve()
    if source == workspace:
        return {"source": str(source), "copied_files": 0, "skipped_files": 0, "skipped_dirs": 0}
    if not source.exists() or not source.is_dir():
        raise ValueError(f"source workspace does not exist or is not a directory: {source}")

    copied_files = 0
    skipped_files = 0
    skipped_dirs = 0
    for current, dirnames, filenames in os.walk(source):
        current_path = Path(current)
        kept_dirs = []
        for dirname in dirnames:
            candidate = current_path / dirname
            if (
                dirname in DOGFOOD_SKIP_DIR_NAMES
                or is_sensitive_path(candidate)
                or candidate == workspace
                or _is_relative_to(workspace, candidate)
            ):
                skipped_dirs += 1
                continue
            kept_dirs.append(dirname)
        dirnames[:] = kept_dirs

        for filename in filenames:
            path = current_path / filename
            if is_sensitive_path(path):
                skipped_files += 1
                continue
            try:
                stat = path.stat()
            except OSError:
                skipped_files += 1
                continue
            if not path.is_file() or path.is_symlink() or stat.st_size > max_file_bytes:
                skipped_files += 1
                continue
            relative = path.relative_to(source)
            destination = workspace / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
            copied_files += 1

    return {
        "source": str(source),
        "copied_files": copied_files,
        "skipped_files": skipped_files,
        "skipped_dirs": skipped_dirs,
    }


def build_runtime_command(args, workspace):
    command = [
        sys.executable,
        "-m",
        "mew",
        "run",
        "--interval",
        str(args.interval),
        "--poll-interval",
        str(args.poll_interval),
        "--autonomous",
        "--autonomy-level",
        args.autonomy_level,
        "--allow-read",
        str(workspace),
        "--echo-outbox",
        "--timeout",
        str(args.model_timeout),
    ]
    if args.ai:
        command.append("--ai")
        if args.auth:
            auth_path = Path(args.auth).expanduser()
            if not auth_path.is_absolute():
                auth_path = (Path.cwd() / auth_path).resolve()
            command.extend(["--auth", str(auth_path)])
        if args.model_backend:
            command.extend(["--model-backend", args.model_backend])
        if args.model:
            command.extend(["--model", args.model])
        if args.base_url:
            command.extend(["--base-url", args.base_url])
    if args.allow_write:
        command.extend(["--allow-write", str(workspace)])
    if args.allow_verify:
        command.append("--allow-verify")
        command.extend(["--verify-command", args.verify_command])
        command.extend(["--verify-interval-minutes", str(args.verify_interval_minutes)])
    if getattr(args, "execute_tasks", False):
        command.append("--execute-tasks")
    if getattr(args, "allow_agent_run", False):
        command.append("--allow-agent-run")
    if getattr(args, "agent_stale_minutes", None) is not None:
        command.extend(["--agent-stale-minutes", str(args.agent_stale_minutes)])
    if getattr(args, "agent_result_timeout", None) is not None:
        command.extend(["--agent-result-timeout", str(args.agent_result_timeout)])
    if getattr(args, "agent_start_timeout", None) is not None:
        command.extend(["--agent-start-timeout", str(args.agent_start_timeout)])
    if getattr(args, "review_model", None):
        command.extend(["--review-model", args.review_model])
    if getattr(args, "trace_model", False):
        command.append("--trace-model")
    return command


def dogfood_subprocess_env():
    env = os.environ.copy()
    src_root = str(Path(__file__).resolve().parents[1])
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = src_root if not existing else src_root + os.pathsep + existing
    return env


def run_command(command, workspace, timeout=30, env=None):
    try:
        result = subprocess.run(
            command,
            cwd=str(workspace),
            text=True,
            capture_output=True,
            timeout=timeout,
            shell=False,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        return {
            "command": command,
            "exit_code": None,
            "stdout": stdout,
            "stderr": stderr or f"command timed out after {timeout} second(s)",
        }
    return {
        "command": command,
        "exit_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def _scenario_command(*args):
    return [sys.executable, "-m", "mew", *args]


def _json_stdout(command_result):
    try:
        return json.loads(command_result.get("stdout") or "{}")
    except json.JSONDecodeError:
        return {}


def _scenario_check(checks, name, passed, observed=None, expected=None):
    checks.append(
        {
            "name": name,
            "passed": bool(passed),
            "observed": observed,
            "expected": expected,
        }
    )


def _scenario_report(name, workspace, commands, checks):
    passed = all(check.get("passed") for check in checks)
    return {
        "name": name,
        "status": "pass" if passed else "fail",
        "workspace": str(workspace),
        "command_count": len(commands),
        "commands": commands,
        "checks": checks,
    }


def run_interrupted_focus_scenario(workspace, env=None):
    commands = []
    checks = []

    def run(args, timeout=30):
        result = run_command(_scenario_command(*args), workspace, timeout=timeout, env=env)
        commands.append(result)
        return result

    run(["task", "add", "Task B ready normal no-agent", "--kind", "coding", "--ready", "--priority", "normal"])
    run(["run", "--once", "--execute-tasks", "--echo-outbox"], timeout=15)
    run(["task", "add", "Task A interrupted high running", "--kind", "coding", "--ready", "--priority", "high"])
    run(["task", "update", "2", "--status", "running", "--priority", "high"])

    next_data = _json_stdout(run(["next", "--json"]))
    focus_data = _json_stdout(run(["focus", "--json"]))
    work_data = _json_stdout(run(["work", "--json"]))
    explicit_b = _json_stdout(run(["work", "1", "--json"]))

    _scenario_check(
        checks,
        "next_stays_on_running_task",
        "#2" in (next_data.get("next_move") or ""),
        observed=next_data.get("next_move"),
        expected="next_move mentions task #2",
    )
    _scenario_check(
        checks,
        "focus_stays_on_running_task",
        "#2" in (focus_data.get("next_move") or ""),
        observed=focus_data.get("next_move"),
        expected="focus.next_move mentions task #2",
    )
    _scenario_check(
        checks,
        "default_workbench_selects_running_task",
        (work_data.get("task") or {}).get("id") == 2,
        observed=(work_data.get("task") or {}).get("id"),
        expected=2,
    )
    _scenario_check(
        checks,
        "explicit_workbench_can_select_background_question_task",
        (explicit_b.get("task") or {}).get("id") == 1
        and bool(explicit_b.get("open_questions")),
        observed={
            "task_id": (explicit_b.get("task") or {}).get("id"),
            "open_questions": len(explicit_b.get("open_questions") or []),
        },
        expected={"task_id": 1, "open_questions": ">=1"},
    )
    return _scenario_report("interrupted-focus", workspace, commands, checks)


def run_trace_smoke_scenario(workspace, env=None):
    commands = []
    checks = []

    def run(args, timeout=30):
        result = run_command(_scenario_command(*args), workspace, timeout=timeout, env=env)
        commands.append(result)
        return result

    run(["run", "--once", "--trace-model"], timeout=15)
    trace_data = _json_stdout(run(["trace", "--json"]))
    trace_prompt_data = _json_stdout(run(["trace", "--json", "--prompt"]))
    traces = trace_data.get("traces") or []
    prompt_traces = trace_prompt_data.get("traces") or []

    _scenario_check(
        checks,
        "trace_records_created",
        len(traces) >= 2,
        observed=len(traces),
        expected=">=2",
    )
    _scenario_check(
        checks,
        "trace_json_hides_prompts_by_default",
        all("prompt" not in record for record in traces),
        observed=[sorted(record.keys()) for record in traces[:2]],
        expected="no prompt key unless --prompt is passed",
    )
    _scenario_check(
        checks,
        "skipped_trace_uses_reason_not_error",
        all(record.get("reason") and not record.get("error") for record in traces),
        observed=[{"status": record.get("status"), "reason": record.get("reason"), "error": record.get("error")} for record in traces[:2]],
        expected="skipped deterministic records carry reason without error",
    )
    _scenario_check(
        checks,
        "trace_prompt_flag_is_accepted",
        isinstance(prompt_traces, list) and len(prompt_traces) == len(traces),
        observed=len(prompt_traces),
        expected=len(traces),
    )
    return _scenario_report("trace-smoke", workspace, commands, checks)


def run_memory_search_scenario(workspace, env=None):
    commands = []
    checks = []
    state_dir = workspace / STATE_DIR
    state_dir.mkdir(parents=True, exist_ok=True)
    state = default_state()
    state["memory"]["shallow"]["current_context"] = "Trace logs help runtime debugging."
    state["memory"]["deep"]["project"].append("The model runtime should support searchable memory recall.")
    write_json_file(workspace / STATE_FILE, state)

    def run(args, timeout=30):
        result = run_command(_scenario_command(*args), workspace, timeout=timeout, env=env)
        commands.append(result)
        return result

    text_result = run(["memory", "--search", "trace"])
    json_result = run(["memory", "--search", "runtime", "--json"])
    json_data = _json_stdout(json_result)
    matches = json_data.get("matches") or []

    _scenario_check(
        checks,
        "memory_search_text_finds_shallow_context",
        text_result.get("exit_code") == 0 and "shallow.current_context" in (text_result.get("stdout") or ""),
        observed=text_result.get("stdout"),
        expected="text output includes shallow.current_context",
    )
    _scenario_check(
        checks,
        "memory_search_json_returns_matches",
        json_result.get("exit_code") == 0 and bool(matches),
        observed=matches,
        expected="at least one JSON match",
    )
    _scenario_check(
        checks,
        "memory_search_json_finds_deep_project",
        any(match.get("scope") == "deep" and match.get("key") == "project" for match in matches),
        observed=matches,
        expected="deep.project match",
    )
    return _scenario_report("memory-search", workspace, commands, checks)


def run_dogfood_scenario(args):
    workspace, created_temp = prepare_dogfood_workspace(args.workspace)
    env = dogfood_subprocess_env()
    requested = getattr(args, "scenario", "all") or "all"
    names = list(DOGFOOD_SCENARIOS) if requested == "all" else [requested]
    reports = []
    for name in names:
        scenario_workspace = workspace / name if len(names) > 1 else workspace
        scenario_workspace.mkdir(parents=True, exist_ok=True)
        if name == "interrupted-focus":
            reports.append(run_interrupted_focus_scenario(scenario_workspace, env=env))
        elif name == "trace-smoke":
            reports.append(run_trace_smoke_scenario(scenario_workspace, env=env))
        elif name == "memory-search":
            reports.append(run_memory_search_scenario(scenario_workspace, env=env))
        else:
            raise ValueError(f"unknown dogfood scenario: {name}")

    passed = all(report.get("status") == "pass" for report in reports)
    report = {
        "generated_at": now_iso(),
        "workspace": str(workspace),
        "kept": not (args.cleanup and created_temp),
        "scenario": requested,
        "status": "pass" if passed else "fail",
        "scenarios": reports,
    }
    if args.cleanup and created_temp:
        shutil.rmtree(workspace, ignore_errors=True)
    return report

def queued_message_event_id(output):
    match = re.search(r"queued message event #(\d+)", output or "")
    if not match:
        return None
    return int(match.group(1))


def tail_lines(text, limit=20, max_line_chars=1000):
    lines = (text or "").splitlines()[-limit:]
    clipped = []
    for line in lines:
        if len(line) > max_line_chars:
            clipped.append(line[:max_line_chars] + "...<truncated>")
        else:
            clipped.append(line)
    return clipped


def command_result_tail(result, limit=20):
    return {
        "command": result.get("command", []),
        "exit_code": result.get("exit_code"),
        "stdout_tail": tail_lines(result.get("stdout"), limit=limit),
        "stderr_tail": tail_lines(result.get("stderr"), limit=limit),
    }


def active_agent_run_ids(workspace):
    return [run["id"] for run in active_agent_runs_for_wait(workspace)]


def active_agent_runs_for_wait(workspace):
    state = read_json_file(Path(workspace) / STATE_FILE, {})
    runs = []
    for run in state.get("agent_runs", []):
        if run.get("id") is None or run.get("status") not in ("created", "running"):
            continue
        runs.append({"id": run.get("id"), "external_pid": run.get("external_pid")})
    return runs


def wait_for_active_agent_runs(workspace, timeout_seconds, env=None):
    timeout_seconds = max(0.0, float(timeout_seconds or 0.0))
    if timeout_seconds <= 0.0:
        return []
    deadline = time.monotonic() + timeout_seconds
    results = []
    for run in active_agent_runs_for_wait(workspace):
        run_id = run["id"]
        external_pid = run.get("external_pid")
        if not external_pid:
            results.append({"run_id": run_id, "skipped": "missing_external_pid"})
            continue
        remaining = max(0.0, deadline - time.monotonic())
        if remaining <= 0.0:
            results.append({"run_id": run_id, "skipped": "timeout_exhausted"})
            continue
        wait_command = ["ai-cli", "wait", str(external_pid), "--timeout", str(remaining)]
        try:
            wait_result = subprocess.run(
                wait_command,
                cwd=str(workspace),
                text=True,
                capture_output=True,
                timeout=remaining + 30.0,
                shell=False,
                env=env,
            )
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout if isinstance(exc.stdout, str) else ""
            stderr = exc.stderr if isinstance(exc.stderr, str) else ""
            results.append(
                {
                    "run_id": run_id,
                    "external_pid": external_pid,
                    "command": wait_command,
                    "exit_code": None,
                    "timed_out": True,
                    "stdout_tail": tail_lines(stdout),
                    "stderr_tail": tail_lines(stderr or f"wait timed out after {remaining:.1f} second(s)"),
                }
            )
            continue

        wait_summary = command_result_tail(
            {
                "command": wait_command,
                "exit_code": wait_result.returncode,
                "stdout": wait_result.stdout,
                "stderr": wait_result.stderr,
            }
        )
        wait_summary["run_id"] = run_id
        wait_summary["external_pid"] = external_pid
        if wait_result.returncode != 0 and "timed out" in (wait_result.stderr or "").casefold():
            wait_summary["timed_out"] = True
        if wait_result.returncode == 0:
            collect_result = run_command(
                [sys.executable, "-m", "mew", "agent", "result", str(run_id)],
                workspace,
                timeout=30.0,
                env=env,
            )
            wait_summary["collect_result"] = command_result_tail(collect_result)
        results.append(wait_summary)
    return results


def agent_reflex_sweep_timeout(args):
    configured = []
    for name in ("agent_result_timeout", "agent_start_timeout"):
        value = getattr(args, name, None)
        if value is None:
            continue
        configured.append(max(0.0, float(value)))
    if not configured:
        return 60.0
    return max(60.0, sum(configured) + 30.0)


def run_agent_reflex_sweep(workspace, args, env=None, phase="sweep"):
    command = [
        sys.executable,
        "-m",
        "mew",
        "agent",
        "sweep",
        "--start-reviews",
    ]
    if getattr(args, "review_model", None):
        command.extend(["--agent-model", args.review_model])
    if getattr(args, "agent_stale_minutes", None) is not None:
        command.extend(["--stale-minutes", str(args.agent_stale_minutes)])
    if getattr(args, "agent_result_timeout", None) is not None:
        command.extend(["--agent-result-timeout", str(args.agent_result_timeout)])
    if getattr(args, "agent_start_timeout", None) is not None:
        command.extend(["--agent-start-timeout", str(args.agent_start_timeout)])
    result = run_command(command, workspace, timeout=agent_reflex_sweep_timeout(args), env=env)
    return {
        "phase": phase,
        "sweep": command_result_tail(result),
    }


def run_post_wait_agent_reflex(workspace, args, env=None):
    if not getattr(args, "allow_agent_run", False):
        return []
    wait_timeout = float(getattr(args, "wait_agent_runs", 0.0) or 0.0)
    if wait_timeout <= 0:
        return []

    results = [run_agent_reflex_sweep(workspace, args, env=env, phase="post_wait_sweep")]
    review_wait_results = wait_for_active_agent_runs(workspace, wait_timeout, env=env)
    if review_wait_results:
        results.append({"phase": "review_wait", "agent_wait_results": review_wait_results})
        results.append(run_agent_reflex_sweep(workspace, args, env=env, phase="post_review_sweep"))
    return results


def wait_for_runtime_state(workspace, timeout=15.0, poll_interval=0.1):
    deadline = time.monotonic() + max(0.0, timeout)
    state_path = workspace / STATE_FILE
    while time.monotonic() < deadline:
        if state_path.exists():
            try:
                state = json.loads(state_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                state = {}
            if state.get("runtime_status", {}).get("state") == "running":
                return True
        time.sleep(max(0.01, poll_interval))
    return False


def stop_process(process, timeout=10.0):
    if process.poll() is not None:
        return process.returncode
    try:
        process.send_signal(signal.SIGTERM)
    except OSError:
        return process.poll()
    deadline = time.monotonic() + max(0.0, timeout)
    while time.monotonic() < deadline:
        code = process.poll()
        if code is not None:
            return code
        time.sleep(0.05)
    try:
        process.kill()
    except OSError:
        pass
    return process.wait(timeout=timeout)


def read_json_file(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def write_json_file(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def read_text_file(path):
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def parse_phase_counts(log_text):
    counts = {
        "think_ok": 0,
        "think_error": 0,
        "act_ok": 0,
        "act_error": 0,
    }
    for line in log_text.splitlines():
        if "think_phase" in line and " ok " in line:
            counts["think_ok"] += 1
        elif "think_phase" in line and " error " in line:
            counts["think_error"] += 1
        elif "act_phase" in line and " ok " in line:
            counts["act_ok"] += 1
        elif "act_phase" in line and " error " in line:
            counts["act_error"] += 1
    return counts


def count_by(items, key):
    counts = {}
    for item in items:
        value = item.get(key) or "unknown"
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def action_counts(thoughts):
    counts = {}
    for thought in thoughts:
        for action in thought.get("actions") or []:
            action_type = action.get("type") or "unknown"
            counts[action_type] = counts.get(action_type, 0) + 1
    return dict(sorted(counts.items()))


def read_inspection_metrics(outbox, actions):
    read_progress = [
        message
        for message in outbox
        if str(message.get("text") or "").startswith("Read file ")
        and "saved the observation to memory" in str(message.get("text") or "")
    ]
    repeated_skips = [
        message
        for message in outbox
        if "Skipped repeated read_file" in str(message.get("text") or "")
    ]
    return {
        "read_file_actions": actions.get("read_file", 0),
        "read_progress_messages": len(read_progress),
        "read_progress_unread": len([message for message in read_progress if not message.get("read_at")]),
        "repeated_read_skips": len(repeated_skips),
        "repeated_read_skips_unread": len([message for message in repeated_skips if not message.get("read_at")]),
    }


def agent_run_summary(agent_runs, limit=5):
    latest = []
    for run in agent_runs[-limit:]:
        latest.append(
            {
                "id": run.get("id"),
                "task_id": run.get("task_id"),
                "plan_id": run.get("plan_id"),
                "purpose": run.get("purpose") or "implementation",
                "status": run.get("status") or "unknown",
                "model": run.get("model") or "",
                "external_pid": run.get("external_pid"),
                "session_id": run.get("session_id"),
            }
        )
    return {
        "total": len(agent_runs),
        "by_status": count_by(agent_runs, "status"),
        "by_purpose": count_by(agent_runs, "purpose"),
        "latest": latest,
    }


def programmer_loop_metrics(state):
    runs = state.get("agent_runs", [])
    implementation_runs = [run for run in runs if (run.get("purpose") or "implementation") == "implementation"]
    review_runs = [run for run in runs if run.get("purpose") == "review"]
    followup_task_ids = [
        run.get("followup_task_id")
        for run in review_runs
        if run.get("followup_task_id") is not None
    ]
    return {
        "implementation_runs": len(implementation_runs),
        "implementation_by_status": count_by(implementation_runs, "status"),
        "review_runs": len(review_runs),
        "review_by_status": count_by(review_runs, "status"),
        "reviews_with_followup_processed": len(
            [run for run in review_runs if run.get("followup_processed_at")]
        ),
        "followup_tasks_created": len(followup_task_ids),
        "followup_task_ids": followup_task_ids[-5:],
    }


def has_active_agent_runs(report):
    statuses = (report.get("agent_runs") or {}).get("by_status") or {}
    return bool(statuses.get("created") or statuses.get("running"))


def workspace_has_active_agent_runs(workspace):
    state = read_json_file(Path(workspace) / STATE_FILE, {})
    return any(run.get("status") in ("created", "running") for run in state.get("agent_runs", []))


def active_implementation_run_for_task(state, task_id):
    wanted = str(task_id)
    for run in reversed(state.get("agent_runs", [])):
        if str(run.get("task_id")) != wanted:
            continue
        if (run.get("purpose") or "implementation") != "implementation":
            continue
        if run.get("status") in ("created", "running"):
            return run
    return None


def plan_schema_issues(events, limit=5):
    issues = []
    for event in events:
        for phase, plan_key in (("think", "decision_plan"), ("act", "action_plan")):
            plan = event.get(plan_key) or {}
            for item in plan.get("schema_issues") or []:
                if not isinstance(item, dict):
                    continue
                issues.append(
                    {
                        "event_id": event.get("id"),
                        "event_type": event.get("type"),
                        "phase": phase,
                        "level": item.get("level") or "unknown",
                        "path": item.get("path") or "",
                        "message": item.get("message") or "",
                    }
                )
    return {
        "count": len(issues),
        "by_level": count_by(issues, "level"),
        "latest": issues[-limit:],
    }


def read_jsonl_records(path):
    records = []
    for line in read_text_file(path).splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            record = {"status": "corrupt", "raw": line}
        if not isinstance(record, dict):
            record = {"status": "corrupt", "raw": line}
        record.pop("prompt", None)
        records.append(record)
    return records


def model_trace_summary(workspace, limit=5):
    records = read_jsonl_records(Path(workspace) / MODEL_TRACE_FILE)
    latest = []
    for record in records[-limit:]:
        latest.append(
            {
                "at": record.get("at"),
                "phase": record.get("phase"),
                "event_id": record.get("event_id"),
                "event_type": record.get("event_type"),
                "status": record.get("status"),
                "backend": record.get("backend"),
                "model": record.get("model"),
                "prompt_chars": record.get("prompt_chars", 0),
                "prompt_sha256": record.get("prompt_sha256", ""),
            }
        )
    return {
        "total": len(records),
        "by_status": count_by(records, "status"),
        "by_phase": count_by(records, "phase"),
        "latest": latest,
    }


def build_dogfood_report(workspace, command, exit_code, duration_seconds, kept=True):
    workspace = Path(workspace)
    state = read_json_file(workspace / STATE_FILE, {})
    log_text = read_text_file(workspace / LOG_FILE)
    runtime_output = read_text_file(workspace / STATE_DIR / "dogfood-runtime.out")
    inbox = state.get("inbox", [])
    outbox = state.get("outbox", [])
    thoughts = state.get("thought_journal", [])
    dropped = [thought for thought in thoughts if thought.get("dropped_threads")]
    active_dropped = dropped_thread_warning_for_context(state) if state else None
    processed = [event for event in inbox if event.get("processed_at")]
    actions = action_counts(thoughts)

    return {
        "generated_at": now_iso(),
        "workspace": str(workspace),
        "kept": kept,
        "command": command,
        "exit_code": exit_code,
        "duration_seconds": duration_seconds,
        "events": {
            "total": len(inbox),
            "processed": len(processed),
            "by_type": count_by(inbox, "type"),
        },
        "runtime_status": state.get("runtime_status", {}) if state else {},
        "model_phases": parse_phase_counts(log_text),
        "model_traces": model_trace_summary(workspace),
        "plan_schema_issues": plan_schema_issues(inbox),
        "outbox": {
            "total": len(outbox),
            "unread": len([message for message in outbox if not message.get("read_at")]),
            "by_type": count_by(outbox, "type"),
        },
        "actions": actions,
        "read_inspection": read_inspection_metrics(outbox, actions),
        "tasks": count_by(state.get("tasks", []), "status"),
        "agent_runs": agent_run_summary(state.get("agent_runs", [])),
        "programmer_loop": programmer_loop_metrics(state),
        "verification_runs": len(state.get("verification_runs", [])),
        "write_runs": len(state.get("write_runs", [])),
        "dropped_threads": {
            "thought_count": len(dropped),
            "latest": dropped[-1].get("dropped_threads", []) if dropped else [],
        },
        "active_dropped_threads": {
            "thought_count": len(active_dropped.get("dropped_threads", [])) if active_dropped else 0,
            "latest": active_dropped.get("dropped_threads", []) if active_dropped else [],
            "thought_id": active_dropped.get("thought_id") if active_dropped else None,
        },
        "project_snapshot": state.get("memory", {}).get("deep", {}).get("project_snapshot", {}) if state else {},
        "pre_snapshot": state.get("dogfood", {}).get("pre_snapshot") if state else None,
        "recent_activity": recent_activity(state, limit=8) if state else [],
        "next_move": next_move(state) if state else "state was not created",
        "log_tail": log_text.splitlines()[-20:],
        "runtime_output_tail": runtime_output.splitlines()[-20:],
    }


def injected_message_status(state, sent_messages, event_ids=None):
    sent_messages = list(sent_messages or [])
    if not sent_messages:
        return {"total": 0, "processed": 0, "unprocessed": 0, "events": []}

    if event_ids:
        events_by_id = {str(event.get("id")): event for event in state.get("inbox", [])}
        events = []
        unmatched = []
        for index, text in enumerate(sent_messages):
            event_id = event_ids[index] if index < len(event_ids) else None
            event = events_by_id.get(str(event_id)) if event_id is not None else None
            if not event:
                unmatched.append(text)
                continue
            events.append(
                {
                    "id": event.get("id"),
                    "text": (event.get("payload") or {}).get("text"),
                    "processed": bool(event.get("processed_at")),
                    "processed_at": event.get("processed_at"),
                }
            )
        processed = len([event for event in events if event.get("processed")])
        return {
            "total": len(sent_messages),
            "matched": len(events),
            "processed": processed,
            "unprocessed": len(events) - processed + len(unmatched),
            "events": events,
            "unmatched": unmatched,
        }

    pending_texts = list(sent_messages)
    events = []
    for event in state.get("inbox", []):
        if event.get("type") != "user_message":
            continue
        text = (event.get("payload") or {}).get("text")
        if text not in pending_texts:
            continue
        pending_texts.remove(text)
        events.append(
            {
                "id": event.get("id"),
                "text": text,
                "processed": bool(event.get("processed_at")),
                "processed_at": event.get("processed_at"),
            }
        )

    processed = len([event for event in events if event.get("processed")])
    return {
        "total": len(sent_messages),
        "matched": len(events),
        "processed": processed,
        "unprocessed": len(events) - processed + len(pending_texts),
        "events": events,
        "unmatched": pending_texts,
    }

def suppress_processed_injected_dropped_threads(report):
    injected = report.get("injected_messages") or {}
    processed_texts = {
        str(event.get("text") or "")
        for event in injected.get("events", [])
        if event.get("processed") and event.get("text")
    }
    if not processed_texts:
        return report
    active = report.get("active_dropped_threads") or {}
    latest = list(active.get("latest") or [])
    remaining = [
        thread
        for thread in latest
        if not any(thread == f"User request context: {text}" for text in processed_texts)
    ]
    if len(remaining) == len(latest):
        return report
    report["active_dropped_threads"] = {
        **active,
        "thought_count": len(remaining),
        "latest": remaining,
        "thought_id": active.get("thought_id") if remaining else None,
    }
    return report


def format_dogfood_report(report):
    lines = [
        f"Mew dogfood report at {report.get('generated_at')}",
        f"workspace: {report.get('workspace')}",
        f"exit_code: {report.get('exit_code')} duration_seconds={report.get('duration_seconds'):.1f}",
        "events: "
        f"processed={report['events']['processed']}/{report['events']['total']} "
        f"by_type={report['events']['by_type']}",
        "model_phases: " + ", ".join(
            f"{key}={value}" for key, value in report.get("model_phases", {}).items()
        ),
        f"model_traces: {report.get('model_traces')}",
        "runtime_cycle: "
        f"last_reason={report.get('runtime_status', {}).get('last_cycle_reason')} "
        f"duration={report.get('runtime_status', {}).get('last_cycle_duration_seconds')} "
        f"processed={report.get('runtime_status', {}).get('last_processed_count')}",
        "outbox: "
        f"total={report['outbox']['total']} unread={report['outbox']['unread']} "
        f"by_type={report['outbox']['by_type']}",
        f"actions: {report.get('actions')}",
        f"read_inspection: {report.get('read_inspection')}",
        f"tasks: {report.get('tasks')}",
        f"agent_runs: {report.get('agent_runs')}",
        f"programmer_loop: {report.get('programmer_loop')}",
        f"verification_runs: {report.get('verification_runs')} write_runs: {report.get('write_runs')}",
        f"model_enabled: {bool(report.get('model_enabled'))}",
    ]
    injected = report.get("injected_messages") or {}
    if injected.get("total"):
        lines.append(
            "injected_messages: "
            f"processed={injected.get('processed')}/{injected.get('total')} "
            f"unprocessed={injected.get('unprocessed')}"
        )
        if injected.get("unprocessed"):
            lines.append("warning: injected user message(s) were left unprocessed")
    seed_task = report.get("seed_task")
    if seed_task:
        lines.append(
            "seed_task: "
            f"task=#{seed_task.get('id')} plan=#{seed_task.get('plan_id')} "
            f"status={seed_task.get('status')} auto_execute={seed_task.get('auto_execute')}"
        )
    if report.get("cleanup_skipped_reason"):
        lines.append(f"cleanup_skipped: {report.get('cleanup_skipped_reason')}")
    wait_results = report.get("agent_wait_results") or []
    if wait_results:
        lines.append(f"agent_wait_results: {len(wait_results)}")
        for result in wait_results:
            lines.append(
                f"- run #{result.get('run_id')} exit={result.get('exit_code')} "
                f"timed_out={bool(result.get('timed_out'))} "
                f"stdout_tail={result.get('stdout_tail')} stderr_tail={result.get('stderr_tail')}"
            )
    reflex_results = report.get("agent_reflex_results") or []
    if reflex_results:
        lines.append(f"agent_reflex_results: {len(reflex_results)}")
        for result in reflex_results:
            if result.get("sweep"):
                sweep = result.get("sweep") or {}
                lines.append(
                    f"- {result.get('phase')} exit={sweep.get('exit_code')} "
                    f"stdout_tail={sweep.get('stdout_tail')} stderr_tail={sweep.get('stderr_tail')}"
                )
            else:
                lines.append(
                    f"- {result.get('phase')} "
                    f"agent_wait_results={len(result.get('agent_wait_results') or [])}"
                )
                for wait_result in result.get("agent_wait_results") or []:
                    lines.append(
                        f"  - run #{wait_result.get('run_id')} exit={wait_result.get('exit_code')} "
                        f"timed_out={bool(wait_result.get('timed_out'))} "
                        f"stdout_tail={wait_result.get('stdout_tail')} "
                        f"stderr_tail={wait_result.get('stderr_tail')}"
                    )
    source_copy = report.get("source_copy")
    if source_copy:
        lines.append(
            "source_copy: "
            f"source={source_copy.get('source')} copied={source_copy.get('copied_files')} "
            f"skipped_files={source_copy.get('skipped_files')} skipped_dirs={source_copy.get('skipped_dirs')}"
        )
    pre_snapshot = report.get("pre_snapshot")
    if pre_snapshot:
        lines.append(
            "pre_snapshot: "
            f"inspected_dirs={len(pre_snapshot.get('inspected_dirs') or [])} "
            f"read_files={len(pre_snapshot.get('read_files') or [])}"
        )
    dropped = report.get("dropped_threads", {})
    if dropped.get("thought_count"):
        lines.append(
            "dropped_threads_history: "
            f"thought_count={dropped.get('thought_count')} latest={dropped.get('latest')}"
        )
    active_dropped = report.get("active_dropped_threads") or {}
    if active_dropped.get("thought_count"):
        lines.append(
            "active_dropped_threads: "
            f"thought_id={active_dropped.get('thought_id')} latest={active_dropped.get('latest')}"
        )
    schema_issues = report.get("plan_schema_issues") or {}
    if schema_issues.get("count"):
        lines.append(
            "plan_schema_issues: "
            f"count={schema_issues.get('count')} by_level={schema_issues.get('by_level')} "
            f"latest={schema_issues.get('latest')}"
        )
    project_snapshot = report.get("project_snapshot") or {}
    if project_snapshot:
        lines.append("")
        lines.append("Project snapshot")
        lines.append(format_project_snapshot(project_snapshot))

    activity = report.get("recent_activity") or []
    if activity:
        lines.append("")
        lines.append("Recent activity")
        for item in activity:
            actions = item.get("actions") or []
            suffix = f" actions={', '.join(actions)}" if actions else ""
            lines.append(f"- #{item.get('id')} {item.get('event_type')}: {item.get('summary')}{suffix}")

    runtime_output_tail = report.get("runtime_output_tail") or []
    if runtime_output_tail:
        lines.append("")
        lines.append("Runtime output (last lines)")
        lines.extend(runtime_output_tail)

    lines.append("")
    lines.append(f"Next useful move: {report.get('next_move')}")
    return "\n".join(lines)


def format_dogfood_scenario_report(report):
    lines = [
        f"Mew dogfood scenario report at {report.get('generated_at')}",
        f"workspace: {report.get('workspace')}",
        f"scenario: {report.get('scenario')} status={report.get('status')}",
    ]
    for scenario in report.get("scenarios") or []:
        lines.append("")
        lines.append(
            f"{scenario.get('name')}: {scenario.get('status')} "
            f"commands={scenario.get('command_count')}"
        )
        for check in scenario.get("checks") or []:
            marker = "PASS" if check.get("passed") else "FAIL"
            lines.append(f"- {marker} {check.get('name')}")
            if not check.get("passed"):
                lines.append(f"  observed: {check.get('observed')}")
                lines.append(f"  expected: {check.get('expected')}")
    return "\n".join(lines)


def seed_ready_coding_task(workspace, title=DOGFOOD_READY_CODING_TASK_TITLE):
    workspace = Path(workspace).resolve()
    state_path = workspace / STATE_FILE
    state = migrate_state(read_json_file(state_path, default_state()))
    reconcile_next_ids(state)
    current_time = now_iso()

    existing = None
    for task in state.get("tasks", []):
        if task.get("title") == title:
            existing = task
            break

    if existing is None:
        task = {
            "id": next_id(state, "task"),
            "title": title,
            "kind": "coding",
            "description": (
                "Exercise mew's programmer dispatch loop from an autonomous ready task. "
                "Inspect the workspace, make no risky changes, and report a minimal safe improvement."
            ),
            "status": "ready",
            "priority": "normal",
            "notes": "Seeded by dogfood as a refined self-proposed coding task.",
            "command": "",
            "cwd": str(workspace),
            "auto_execute": True,
            "agent_backend": "",
            "agent_model": "",
            "agent_prompt": "",
            "agent_run_id": None,
            "plans": [],
            "latest_plan_id": None,
            "runs": [],
            "created_at": current_time,
            "updated_at": current_time,
        }
        state["tasks"].append(task)
    else:
        task = existing
        active_run = active_implementation_run_for_task(state, task.get("id"))
        if active_run:
            task["status"] = "running"
            task["agent_run_id"] = active_run.get("id")
            task["updated_at"] = current_time
            write_json_file(state_path, state)
            return {
                "id": task["id"],
                "title": task.get("title"),
                "status": task.get("status"),
                "auto_execute": task.get("auto_execute"),
                "plan_id": task.get("latest_plan_id"),
                "active_run_id": active_run.get("id"),
            }
        task["kind"] = "coding"
        task["status"] = "ready"
        task["auto_execute"] = True
        task["command"] = ""
        task["cwd"] = task.get("cwd") or str(workspace)
        task["agent_run_id"] = None
        task["updated_at"] = current_time
        task.setdefault("notes", "")
        if "Seeded by dogfood" not in task["notes"]:
            task["notes"] = f"{task['notes'].rstrip()}\nSeeded by dogfood for programmer dispatch.".strip()

    plan = create_task_plan(
        state,
        task,
        cwd=task.get("cwd") or str(workspace),
        objective=task.get("description") or task.get("title"),
        approach=(
            "Dispatch the implementation agent under the normal programmer loop and report what happened. "
            "Keep changes minimal and safe."
        ),
    )
    write_json_file(state_path, state)
    return {
        "id": task["id"],
        "title": task.get("title"),
        "status": task.get("status"),
        "auto_execute": task.get("auto_execute"),
        "plan_id": plan.get("id"),
    }


def prepopulate_project_snapshot(workspace):
    workspace = Path(workspace)
    state_path = workspace / STATE_FILE
    state = read_json_file(state_path, default_state())
    report = refresh_project_snapshot(
        state,
        str(workspace),
        [str(workspace)],
        now_iso(),
    )
    state.setdefault("dogfood", {})["pre_snapshot"] = {
        "updated_at": report.get("updated_at"),
        "path": report.get("path"),
        "inspected_dirs": report.get("inspected_dirs") or [],
        "read_files": report.get("read_files") or [],
        "errors": report.get("errors") or [],
    }
    write_json_file(state_path, state)
    return state["dogfood"]["pre_snapshot"]


def _run_dogfood_in_workspace(args, workspace, created_temp, source_copy=None, pre_snapshot=None):
    command = build_runtime_command(args, workspace)
    state_dir = workspace / STATE_DIR
    state_dir.mkdir(parents=True, exist_ok=True)
    output_path = state_dir / "dogfood-runtime.out"
    started_at = time.monotonic()
    exit_code = None

    env = dogfood_subprocess_env()
    with output_path.open("ab") as output:
        process = subprocess.Popen(
            command,
            cwd=str(workspace),
            stdout=output,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
            start_new_session=True,
        )

    wait_for_runtime_state(workspace, timeout=args.startup_timeout, poll_interval=0.1)
    injected_event_ids = []
    for message in args.send_message or []:
        result = run_command(
            [sys.executable, "-m", "mew", "message", message],
            workspace,
            timeout=args.message_timeout,
            env=env,
        )
        injected_event_ids.append(queued_message_event_id(result.get("stdout")))

    try:
        time.sleep(max(0.0, args.duration))
    finally:
        exit_code = stop_process(process, timeout=args.stop_timeout)

    duration = time.monotonic() - started_at
    agent_wait_results = wait_for_active_agent_runs(
        workspace,
        getattr(args, "wait_agent_runs", 0.0),
        env=env,
    )
    agent_reflex_results = run_post_wait_agent_reflex(workspace, args, env=env)
    report = build_dogfood_report(
        workspace,
        command,
        exit_code,
        duration,
        kept=not (args.cleanup and created_temp),
    )
    report["model_enabled"] = bool(getattr(args, "ai", False))
    report["injected_messages"] = injected_message_status(
        read_json_file(workspace / STATE_FILE, {}),
        getattr(args, "send_message", None),
        event_ids=injected_event_ids,
    )
    suppress_processed_injected_dropped_threads(report)
    report["runtime_output_path"] = str(output_path)
    report["source_copy"] = source_copy
    if pre_snapshot is not None:
        report["pre_snapshot"] = pre_snapshot
    seed_task = getattr(args, "_seed_task", None)
    if seed_task is not None:
        report["seed_task"] = seed_task
    if agent_wait_results:
        report["agent_wait_results"] = agent_wait_results
    if agent_reflex_results:
        report["agent_reflex_results"] = agent_reflex_results
    return report


def run_dogfood(args):
    workspace, created_temp = prepare_dogfood_workspace(args.workspace)
    source_copy = None
    if getattr(args, "source_workspace", None):
        source_copy = copy_source_workspace(args.source_workspace, workspace)
    pre_snapshot = prepopulate_project_snapshot(workspace) if getattr(args, "pre_snapshot", False) else None
    args._seed_task = seed_ready_coding_task(workspace) if getattr(args, "seed_ready_coding_task", False) else None
    report = _run_dogfood_in_workspace(
        args,
        workspace,
        created_temp,
        source_copy=source_copy,
        pre_snapshot=pre_snapshot,
    )
    if args.cleanup and created_temp and has_active_agent_runs(report):
        report["kept"] = True
        report["cleanup_skipped_reason"] = "active_agent_runs"
    elif args.cleanup and created_temp:
        shutil.rmtree(workspace, ignore_errors=True)
    return report


def run_dogfood_loop(args):
    workspace, created_temp = prepare_dogfood_workspace(args.workspace)
    source_copy = None
    if getattr(args, "source_workspace", None):
        source_copy = copy_source_workspace(args.source_workspace, workspace)
    pre_snapshot = prepopulate_project_snapshot(workspace) if getattr(args, "pre_snapshot", False) else None
    args._seed_task = seed_ready_coding_task(workspace) if getattr(args, "seed_ready_coding_task", False) else None

    cycles = max(1, int(getattr(args, "cycles", 1) or 1))
    reports = []
    try:
        for index in range(cycles):
            report = _run_dogfood_in_workspace(
                args,
                workspace,
                created_temp,
                source_copy=source_copy if index == 0 else None,
                pre_snapshot=pre_snapshot if index == 0 else None,
            )
            report["cycle"] = index + 1
            reports.append(report)
            if index < cycles - 1:
                time.sleep(max(0.0, float(getattr(args, "cycle_gap", 0.0) or 0.0)))
    except Exception:
        active_runs = (has_active_agent_runs(reports[-1]) if reports else False) or workspace_has_active_agent_runs(
            workspace
        )
        if args.cleanup and created_temp and not active_runs:
            shutil.rmtree(workspace, ignore_errors=True)
        raise

    final_report = reports[-1] if reports else {}
    cleanup_skipped_reason = ""
    if args.cleanup and created_temp and has_active_agent_runs(final_report):
        cleanup_skipped_reason = "active_agent_runs"
    elif args.cleanup and created_temp:
        shutil.rmtree(workspace, ignore_errors=True)

    return {
        "generated_at": now_iso(),
        "workspace": str(workspace),
        "kept": not (args.cleanup and created_temp) or bool(cleanup_skipped_reason),
        "cleanup_skipped_reason": cleanup_skipped_reason,
        "cycles": reports,
        "cycle_count": cycles,
        "exit_codes": [report.get("exit_code") for report in reports],
        "final_next_move": final_report.get("next_move"),
        "final_events": final_report.get("events", {}),
        "final_model_phases": final_report.get("model_phases", {}),
        "final_runtime_status": final_report.get("runtime_status", {}),
        "final_plan_schema_issues": final_report.get("plan_schema_issues", {}),
        "final_agent_runs": final_report.get("agent_runs", {}),
        "final_dropped_threads": final_report.get("dropped_threads", {}),
        "final_active_dropped_threads": final_report.get("active_dropped_threads", {}),
        "final_project_snapshot": final_report.get("project_snapshot", {}),
    }


def format_dogfood_loop_report(report):
    lines = [
        f"Mew dogfood loop report at {report.get('generated_at')}",
        f"workspace: {report.get('workspace')}",
        f"cycles: {report.get('cycle_count')} exit_codes={report.get('exit_codes')}",
        f"final_events: {report.get('final_events')}",
        f"final_model_phases: {report.get('final_model_phases')}",
        f"final_agent_runs: {report.get('final_agent_runs')}",
    ]
    if report.get("cleanup_skipped_reason"):
        lines.append(f"cleanup_skipped: {report.get('cleanup_skipped_reason')}")
    final_dropped = report.get("final_dropped_threads") or {}
    if final_dropped.get("thought_count"):
        lines.append(
            "final_dropped_threads: "
            f"thought_count={final_dropped.get('thought_count')} latest={final_dropped.get('latest')}"
        )
    final_active_dropped = report.get("final_active_dropped_threads") or {}
    if final_active_dropped.get("thought_count"):
        lines.append(
            "final_active_dropped_threads: "
            f"thought_id={final_active_dropped.get('thought_id')} "
            f"latest={final_active_dropped.get('latest')}"
        )
    final_schema_issues = report.get("final_plan_schema_issues") or {}
    if final_schema_issues.get("count"):
        lines.append(
            "final_plan_schema_issues: "
            f"count={final_schema_issues.get('count')} by_level={final_schema_issues.get('by_level')}"
        )
    final_runtime = report.get("final_runtime_status") or {}
    if final_runtime:
        lines.append(
            "final_runtime_cycle: "
            f"last_reason={final_runtime.get('last_cycle_reason')} "
            f"duration={final_runtime.get('last_cycle_duration_seconds')} "
            f"processed={final_runtime.get('last_processed_count')}"
        )
    final_snapshot = report.get("final_project_snapshot") or {}
    if final_snapshot:
        lines.append("")
        lines.append("Final project snapshot")
        lines.append(format_project_snapshot(final_snapshot))
    lines.append("")
    lines.append("Cycle summaries")
    for cycle in report.get("cycles") or []:
        events = cycle.get("events") or {}
        phases = cycle.get("model_phases") or {}
        dropped = cycle.get("dropped_threads") or {}
        active_dropped = cycle.get("active_dropped_threads") or {}
        schema_issues = cycle.get("plan_schema_issues") or {}
        wait_results = cycle.get("agent_wait_results") or []
        lines.append(
            f"- #{cycle.get('cycle')} exit={cycle.get('exit_code')} "
            f"duration={cycle.get('duration_seconds'):.1f}s "
            f"processed={events.get('processed')}/{events.get('total')} "
            f"think_ok={phases.get('think_ok')} act_ok={phases.get('act_ok')} "
            f"agent_runs={(cycle.get('agent_runs') or {}).get('total', 0)} "
            f"agent_waits={len(wait_results)} "
            f"dropped_threads={dropped.get('thought_count', 0)} "
            f"active_dropped_threads={active_dropped.get('thought_count', 0)} "
            f"schema_issues={schema_issues.get('count', 0)} "
            f"next={cycle.get('next_move')}"
        )
        for result in wait_results:
            lines.append(
                f"  wait run #{result.get('run_id')}: exit={result.get('exit_code')} "
                f"timed_out={bool(result.get('timed_out'))}"
            )
    lines.append("")
    lines.append(f"Final next useful move: {report.get('final_next_move')}")
    return "\n".join(lines)
