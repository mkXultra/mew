import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time

from .brief import recent_activity, next_move
from .config import LOG_FILE, STATE_DIR, STATE_FILE
from .timeutil import now_iso


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
        workspace.mkdir(parents=True, exist_ok=True)
        created_temp = False
    else:
        workspace = Path(tempfile.mkdtemp(prefix="mew-dogfood-"))
        created_temp = True

    readme = workspace / "README.md"
    if not readme.exists():
        readme.write_text(DOGFOOD_README, encoding="utf-8")
    return workspace.resolve(), created_temp


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
            command.extend(["--auth", args.auth])
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


def build_dogfood_report(workspace, command, exit_code, duration_seconds, kept=True):
    workspace = Path(workspace)
    state = read_json_file(workspace / STATE_FILE, {})
    log_text = read_text_file(workspace / LOG_FILE)
    runtime_output = read_text_file(workspace / STATE_DIR / "dogfood-runtime.out")
    inbox = state.get("inbox", [])
    outbox = state.get("outbox", [])
    thoughts = state.get("thought_journal", [])
    dropped = [thought for thought in thoughts if thought.get("dropped_threads")]
    processed = [event for event in inbox if event.get("processed_at")]

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
        "model_phases": parse_phase_counts(log_text),
        "outbox": {
            "total": len(outbox),
            "unread": len([message for message in outbox if not message.get("read_at")]),
            "by_type": count_by(outbox, "type"),
        },
        "actions": action_counts(thoughts),
        "tasks": count_by(state.get("tasks", []), "status"),
        "verification_runs": len(state.get("verification_runs", [])),
        "write_runs": len(state.get("write_runs", [])),
        "dropped_threads": {
            "thought_count": len(dropped),
            "latest": dropped[-1].get("dropped_threads", []) if dropped else [],
        },
        "recent_activity": recent_activity(state, limit=8) if state else [],
        "next_move": next_move(state) if state else "state was not created",
        "log_tail": log_text.splitlines()[-20:],
        "runtime_output_tail": runtime_output.splitlines()[-20:],
    }


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
        "outbox: "
        f"total={report['outbox']['total']} unread={report['outbox']['unread']} "
        f"by_type={report['outbox']['by_type']}",
        f"actions: {report.get('actions')}",
        f"tasks: {report.get('tasks')}",
        f"verification_runs: {report.get('verification_runs')} write_runs: {report.get('write_runs')}",
    ]
    dropped = report.get("dropped_threads", {})
    if dropped.get("thought_count"):
        lines.append(
            "dropped_threads: "
            f"thought_count={dropped.get('thought_count')} latest={dropped.get('latest')}"
        )

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


def run_dogfood(args):
    workspace, created_temp = prepare_dogfood_workspace(args.workspace)
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
    for message in args.send_message or []:
        run_command(
            [sys.executable, "-m", "mew", "message", message],
            workspace,
            timeout=args.message_timeout,
            env=env,
        )

    try:
        time.sleep(max(0.0, args.duration))
    finally:
        exit_code = stop_process(process, timeout=args.stop_timeout)

    duration = time.monotonic() - started_at
    report = build_dogfood_report(
        workspace,
        command,
        exit_code,
        duration,
        kept=not (args.cleanup and created_temp),
    )
    report["runtime_output_path"] = str(output_path)
    if args.cleanup and created_temp:
        shutil.rmtree(workspace, ignore_errors=True)
    return report
