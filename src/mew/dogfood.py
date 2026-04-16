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
DOGFOOD_SCENARIOS = (
    "interrupted-focus",
    "trace-smoke",
    "memory-search",
    "runtime-focus",
    "chat-cockpit",
    "work-session",
)


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
    if getattr(args, "max_reflex_rounds", 0):
        command.extend(["--max-reflex-rounds", str(args.max_reflex_rounds)])
    return command


def dogfood_subprocess_env():
    env = os.environ.copy()
    src_root = str(Path(__file__).resolve().parents[1])
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = src_root if not existing else src_root + os.pathsep + existing
    return env


def run_command(command, workspace, timeout=30, env=None, input_text=None):
    try:
        result = subprocess.run(
            command,
            cwd=str(workspace),
            text=True,
            capture_output=True,
            timeout=timeout,
            shell=False,
            env=env,
            input=input_text,
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


def _json_stdout(command_result, default=None):
    fallback = {} if default is None else default
    try:
        return json.loads(command_result.get("stdout") or json.dumps(fallback))
    except json.JSONDecodeError:
        return fallback


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
    state["memory"]["deep"]["project_snapshot"] = {
        "updated_at": "now",
        "files": [
            {
                "path": "README.md",
                "kind": "readme",
                "summary": "Dogfood anchor notes for focused project snapshot recall.",
            }
        ],
    }
    write_json_file(workspace / STATE_FILE, state)

    def run(args, timeout=30):
        result = run_command(_scenario_command(*args), workspace, timeout=timeout, env=env)
        commands.append(result)
        return result

    text_result = run(["memory", "--search", "trace"])
    json_result = run(["memory", "--search", "runtime", "--json"])
    snapshot_result = run(["memory", "--search", "dogfood anchor", "--json"])
    json_data = _json_stdout(json_result)
    matches = json_data.get("matches") or []
    snapshot_data = _json_stdout(snapshot_result)
    snapshot_matches = snapshot_data.get("matches") or []

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
    _scenario_check(
        checks,
        "memory_search_json_finds_project_snapshot_leaf",
        any(
            match.get("scope") == "deep"
            and match.get("key") == "project_snapshot.files[0].summary"
            and "{" not in (match.get("text") or "")
            for match in snapshot_matches
        ),
        observed=snapshot_matches,
        expected="focused project_snapshot.files[0].summary match",
    )
    return _scenario_report("memory-search", workspace, commands, checks)


def run_runtime_focus_scenario(workspace, env=None):
    commands = []
    checks = []

    def run(args, timeout=30):
        result = run_command(_scenario_command(*args), workspace, timeout=timeout, env=env)
        commands.append(result)
        return result

    result = run(
        [
            "run",
            "--once",
            "--focus",
            "Take one focused dogfood runtime step",
            "--poll-interval",
            "0.01",
        ],
        timeout=15,
    )
    brief_result = run(["brief"], timeout=15)
    doctor_result = run(["doctor"], timeout=15)

    _scenario_check(
        checks,
        "runtime_focus_flag_is_accepted",
        result.get("exit_code") == 0
        and "runtime focus: Take one focused dogfood runtime step" in (result.get("stdout") or ""),
        observed=command_result_tail(result),
        expected="run --once accepts and prints runtime focus",
    )
    _scenario_check(
        checks,
        "runtime_focus_cycle_completes",
        "processed 1 event(s) reason=startup" in (result.get("stdout") or ""),
        observed=command_result_tail(result),
        expected="startup event processed",
    )
    _scenario_check(
        checks,
        "brief_still_works_after_runtime_focus",
        brief_result.get("exit_code") == 0 and "Mew brief" in (brief_result.get("stdout") or ""),
        observed=command_result_tail(brief_result),
        expected="brief command succeeds after focused runtime",
    )
    _scenario_check(
        checks,
        "brief_surfaces_runtime_effect",
        "Recent runtime effects" in (brief_result.get("stdout") or ""),
        observed=command_result_tail(brief_result),
        expected="brief shows persisted runtime effect journal",
    )
    _scenario_check(
        checks,
        "doctor_surfaces_runtime_effect",
        doctor_result.get("exit_code") == 0
        and "runtime_effects: total=1 incomplete=0" in (doctor_result.get("stdout") or ""),
        observed=command_result_tail(doctor_result),
        expected="doctor shows runtime effect count",
    )
    return _scenario_report("runtime-focus", workspace, commands, checks)


def run_chat_cockpit_scenario(workspace, env=None):
    commands = []
    checks = []

    def run(args, timeout=30, input_text=None):
        result = run_command(_scenario_command(*args), workspace, timeout=timeout, env=env, input_text=input_text)
        commands.append(result)
        return result

    research_result = run(["task", "add", "Research default task", "--kind", "research"])
    coding_result = run(["task", "add", "Implement scoped chat cockpit", "--kind", "coding"])
    chat_result = run(
        ["chat", "--kind", "coding", "--no-brief", "--no-unread", "--timeout", "5"],
        timeout=15,
        input_text="/scope\n/tasks\n/work\n/exit\n",
    )
    chat_output = chat_result.get("stdout") or ""

    _scenario_check(
        checks,
        "chat_kind_scope_starts_active",
        chat_result.get("exit_code") == 0 and "scope: coding" in chat_output,
        observed=command_result_tail(chat_result),
        expected="chat --kind coding starts with coding scope visible",
    )
    _scenario_check(
        checks,
        "chat_tasks_respect_kind_scope",
        chat_result.get("exit_code") == 0
        and "Implement scoped chat cockpit" in chat_output
        and "Research default task" not in chat_output,
        observed=command_result_tail(chat_result),
        expected="/tasks shows coding tasks and hides research tasks under coding scope",
    )
    _scenario_check(
        checks,
        "chat_work_respects_kind_scope",
        chat_result.get("exit_code") == 0
        and "Work task #2: Implement scoped chat cockpit" in chat_output
        and "No coding tasks." not in chat_output,
        observed=command_result_tail(chat_result),
        expected="/work selects the scoped coding task by default",
    )
    _scenario_check(
        checks,
        "chat_cockpit_seed_commands_succeed",
        research_result.get("exit_code") == 0 and coding_result.get("exit_code") == 0,
        observed=[command_result_tail(research_result), command_result_tail(coding_result)],
        expected="scenario task seeds succeed",
    )
    return _scenario_report("chat-cockpit", workspace, commands, checks)


def run_work_session_scenario(workspace, env=None):
    commands = []
    checks = []

    def run(args, timeout=30, input_text=None):
        result = run_command(_scenario_command(*args), workspace, timeout=timeout, env=env, input_text=input_text)
        commands.append(result)
        return result

    (workspace / "README.md").write_text("# Dogfood\nnative hands\n", encoding="utf-8")
    (workspace / "src").mkdir(exist_ok=True)
    (workspace / "src" / "sample.py").write_text(
        "print('native hands')\nprint('line two')\nprint('line three')\n",
        encoding="utf-8",
    )
    (workspace / "large.py").write_text("x" * 120000 + "\nold_call()\n", encoding="utf-8")

    run(["task", "add", "Native work task", "--kind", "coding"])
    start_result = run(["work", "1", "--start-session", "--json"])
    read_result = run(
        ["work", "1", "--tool", "read_file", "--path", "README.md", "--allow-read", ".", "--json"]
    )
    glob_result = run(
        ["work", "1", "--tool", "glob", "--pattern", "*.py", "--path", ".", "--allow-read", ".", "--json"]
    )
    test_result = run(
        [
            "work",
            "1",
            "--tool",
            "run_tests",
            "--command",
            f"{sys.executable} -c \"print('work test ok')\"",
            "--allow-verify",
            "--json",
        ]
    )
    edit_result = run(
        [
            "work",
            "1",
            "--tool",
            "edit_file",
            "--path",
            "README.md",
            "--old",
            "native hands",
            "--new",
            "native work sessions",
            "--allow-write",
            ".",
            "--json",
        ]
    )
    line_read_result = run(
        [
            "work",
            "1",
            "--tool",
            "read_file",
            "--path",
            "src/sample.py",
            "--allow-read",
            ".",
            "--line-start",
            "2",
            "--line-count",
            "1",
            "--json",
        ]
    )
    large_edit_result = run(
        [
            "work",
            "1",
            "--tool",
            "edit_file",
            "--path",
            "large.py",
            "--old",
            "old_call()",
            "--new",
            "new_call()",
            "--allow-write",
            ".",
            "--json",
        ]
    )
    approve_dry_run_result = run(
        [
            "work",
            "1",
            "--tool",
            "write_file",
            "--path",
            "approved.md",
            "--content",
            "approved dogfood\n",
            "--create",
            "--allow-write",
            ".",
            "--json",
        ]
    )
    approve_dry_run_data = _json_stdout(approve_dry_run_result)
    approve_dry_run_id = str((approve_dry_run_data.get("tool_call") or {}).get("id") or "")
    approve_result = run(
        [
            "work",
            "1",
            "--approve-tool",
            approve_dry_run_id,
            "--allow-write",
            "approved.md",
            "--allow-verify",
            "--verify-command",
            f"{sys.executable} -c \"from pathlib import Path; assert Path('approved.md').read_text() == 'approved dogfood\\n'\"",
            "--json",
        ]
    )
    write_result = run(
        [
            "work",
            "1",
            "--tool",
            "write_file",
            "--path",
            "generated.md",
            "--content",
            "generated dogfood\n",
            "--create",
            "--allow-write",
            ".",
            "--apply",
            "--allow-verify",
            "--verify-command",
            f"{sys.executable} -c \"from pathlib import Path; assert Path('generated.md').exists()\"",
            "--json",
        ]
    )
    stop_result = run(["work", "1", "--stop-session", "--stop-reason", "dogfood pause", "--json"])
    note_result = run(["work", "1", "--session-note", "dogfood note", "--json"])
    resume_result = run(["work", "1", "--session", "--resume", "--json"])
    work_result = run(["work", "1", "--json"])
    verification_ledger_result = run(["verification", "--json"])
    writes_ledger_result = run(["writes", "--json"])
    timeline_result = run(["work", "1", "--session", "--timeline", "--json"])
    chat_result = run(
        ["chat", "--no-brief", "--no-unread", "--timeout", "5"],
        timeout=15,
        input_text="/work-session details\n",
    )
    chat_world_result = run(
        ["chat", "--no-brief", "--no-unread", "--timeout", "5"],
        timeout=15,
        input_text="/work-session resume --allow-read .\n",
    )
    run(["task", "add", "Interrupted side-effect task", "--kind", "coding"])
    run(["work", "2", "--start-session", "--json"])

    state_path = workspace / STATE_FILE
    state = migrate_state(read_json_file(state_path, default_state()))
    reconcile_next_ids(state)
    interrupted_session = None
    for candidate in state.get("work_sessions", []):
        if str(candidate.get("task_id")) == "2":
            interrupted_session = candidate
            break
    if interrupted_session:
        tool_call_id = next_id(state, "work_tool_call")
        interrupted_call = {
            "id": tool_call_id,
            "session_id": interrupted_session.get("id"),
            "task_id": 2,
            "tool": "run_tests",
            "status": "interrupted",
            "parameters": {"command": f"{sys.executable} mutate.py", "cwd": "."},
            "result": None,
            "summary": "interrupted dogfood side-effecting command",
            "error": "Interrupted before the command completed.",
            "started_at": now_iso(),
            "finished_at": now_iso(),
        }
        interrupted_session.setdefault("tool_calls", []).append(interrupted_call)
        interrupted_session["last_tool_call_id"] = tool_call_id
        interrupted_session["updated_at"] = now_iso()
        write_json_file(state_path, state)

    interrupted_resume_result = run(["work", "2", "--session", "--resume", "--json"])
    interrupted_recover_result = run(["work", "2", "--recover-session", "--json"])
    run(["task", "add", "Interrupted read task", "--kind", "coding"])
    run(["work", "3", "--start-session", "--json"])

    state = migrate_state(read_json_file(state_path, default_state()))
    reconcile_next_ids(state)
    interrupted_read_session = None
    for candidate in state.get("work_sessions", []):
        if str(candidate.get("task_id")) == "3":
            interrupted_read_session = candidate
            break
    if interrupted_read_session:
        tool_call_id = next_id(state, "work_tool_call")
        interrupted_read = {
            "id": tool_call_id,
            "session_id": interrupted_read_session.get("id"),
            "task_id": 3,
            "tool": "read_file",
            "status": "interrupted",
            "parameters": {"path": "README.md"},
            "result": None,
            "summary": "interrupted dogfood read",
            "error": "Interrupted before the file read completed.",
            "started_at": now_iso(),
            "finished_at": now_iso(),
        }
        interrupted_read_session.setdefault("tool_calls", []).append(interrupted_read)
        interrupted_read_session["last_tool_call_id"] = tool_call_id
        interrupted_read_session["updated_at"] = now_iso()
        write_json_file(state_path, state)

    auto_recover_result = run(["work", "3", "--session", "--resume", "--allow-read", ".", "--auto-recover-safe", "--json"])

    start_data = _json_stdout(start_result)
    read_data = _json_stdout(read_result)
    glob_data = _json_stdout(glob_result)
    test_data = _json_stdout(test_result)
    edit_data = _json_stdout(edit_result)
    line_read_data = _json_stdout(line_read_result)
    large_edit_data = _json_stdout(large_edit_result)
    approve_data = _json_stdout(approve_result)
    write_data = _json_stdout(write_result)
    stop_data = _json_stdout(stop_result)
    note_data = _json_stdout(note_result)
    resume_data = _json_stdout(resume_result)
    verification_ledger_data = _json_stdout(verification_ledger_result, [])
    writes_ledger_data = _json_stdout(writes_ledger_result, [])
    timeline_data = _json_stdout(timeline_result)
    interrupted_resume_data = _json_stdout(interrupted_resume_result)
    interrupted_recover_data = _json_stdout(interrupted_recover_result)
    auto_recover_data = _json_stdout(auto_recover_result)
    work_data = _json_stdout(work_result)
    session = work_data.get("work_session") or {}
    tool_calls = session.get("tool_calls") or []
    workbench_session_verifications = work_data.get("work_session_verifications") or []
    workbench_session_writes = work_data.get("work_session_writes") or []
    timeline = timeline_data.get("timeline") or []
    interrupted_items = ((interrupted_resume_data.get("resume") or {}).get("recovery_plan") or {}).get("items") or []
    interrupted_recovery = interrupted_recover_data.get("recovery") or {}
    interrupted_review = interrupted_recovery.get("review_item") or {}
    auto_recovery = auto_recover_data.get("auto_recovery") or {}
    auto_tool_call = auto_recovery.get("tool_call") or {}

    _scenario_check(
        checks,
        "work_session_starts",
        start_result.get("exit_code") == 0 and (start_data.get("work_session") or {}).get("task_id") == 1,
        observed=start_data.get("work_session"),
        expected="work session for task #1",
    )
    _scenario_check(
        checks,
        "work_read_file_completes",
        read_result.get("exit_code") == 0
        and ((read_data.get("tool_call") or {}).get("result") or {}).get("text", "").find("native hands") >= 0,
        observed=read_data.get("tool_call"),
        expected="read_file captures README content",
    )
    _scenario_check(
        checks,
        "work_glob_completes",
        glob_result.get("exit_code") == 0
        and any(
            str(match.get("path") or "").endswith("src/sample.py")
            for match in ((glob_data.get("tool_call") or {}).get("result") or {}).get("matches", [])
        ),
        observed=glob_data.get("tool_call"),
        expected="glob finds src/sample.py",
    )
    _scenario_check(
        checks,
        "work_run_tests_completes",
        test_result.get("exit_code") == 0
        and ((test_data.get("tool_call") or {}).get("result") or {}).get("exit_code") == 0,
        observed=test_data.get("tool_call"),
        expected="run_tests records exit_code=0",
    )
    _scenario_check(
        checks,
        "work_edit_file_dry_run_completes",
        edit_result.get("exit_code") == 0
        and ((edit_data.get("tool_call") or {}).get("result") or {}).get("dry_run") is True
        and (workspace / "README.md").read_text(encoding="utf-8").find("native hands") >= 0,
        observed=edit_data.get("tool_call"),
        expected="edit_file previews a change without mutating README",
    )
    _scenario_check(
        checks,
        "work_read_file_line_start_completes",
        line_read_result.get("exit_code") == 0
        and ((line_read_data.get("tool_call") or {}).get("result") or {}).get("line_start") == 2
        and ((line_read_data.get("tool_call") or {}).get("result") or {}).get("text") == "print('line two')\n",
        observed=line_read_data.get("tool_call"),
        expected="read_file can read by 1-based line_start/line_count",
    )
    _scenario_check(
        checks,
        "work_edit_file_large_dry_run_completes",
        large_edit_result.get("exit_code") == 0
        and ((large_edit_data.get("tool_call") or {}).get("result") or {}).get("dry_run") is True
        and "old_call()" in (workspace / "large.py").read_text(encoding="utf-8"),
        observed=large_edit_data.get("tool_call"),
        expected="edit_file previews small replacements in large files",
    )
    _scenario_check(
        checks,
        "work_approve_exact_new_file_write_root",
        approve_dry_run_result.get("exit_code") == 0
        and approve_result.get("exit_code") == 0
        and ((approve_dry_run_data.get("tool_call") or {}).get("result") or {}).get("dry_run") is True
        and ((approve_data.get("tool_call") or {}).get("result") or {}).get("verification_exit_code") == 0
        and (workspace / "approved.md").read_text(encoding="utf-8") == "approved dogfood\n",
        observed={"dry_run": approve_dry_run_data.get("tool_call"), "approval": approve_data.get("tool_call")},
        expected="approve-tool applies a new file when --allow-write names that exact missing file",
    )
    _scenario_check(
        checks,
        "work_write_file_applies_with_verification",
        write_result.get("exit_code") == 0
        and ((write_data.get("tool_call") or {}).get("result") or {}).get("verification_exit_code") == 0
        and (workspace / "generated.md").read_text(encoding="utf-8") == "generated dogfood\n",
        observed=write_data.get("tool_call"),
        expected="write_file writes generated.md after verification",
    )
    _scenario_check(
        checks,
        "work_stop_request_records",
        stop_result.get("exit_code") == 0
        and (stop_data.get("work_session") or {}).get("stop_reason") == "dogfood pause",
        observed=stop_data.get("work_session"),
        expected="stop request recorded on active work session",
    )
    _scenario_check(
        checks,
        "work_resume_surfaces_stop_phase",
        resume_result.get("exit_code") == 0
        and (resume_data.get("resume") or {}).get("phase") == "stop_requested",
        observed=resume_data.get("resume"),
        expected="resume reports phase=stop_requested",
    )
    _scenario_check(
        checks,
        "work_session_note_surfaces_in_resume",
        note_result.get("exit_code") == 0
        and (note_data.get("work_note") or {}).get("text") == "dogfood note"
        and any((note or {}).get("text") == "dogfood note" for note in (resume_data.get("resume") or {}).get("notes") or []),
        observed={"note": note_data.get("work_note"), "resume_notes": (resume_data.get("resume") or {}).get("notes")},
        expected="session note is recorded and surfaced in resume",
    )
    _scenario_check(
        checks,
        "workbench_surfaces_tool_journal",
        len(tool_calls) == 9
        and [call.get("tool") for call in tool_calls]
        == [
            "read_file",
            "glob",
            "run_tests",
            "edit_file",
            "read_file",
            "edit_file",
            "write_file",
            "write_file",
            "write_file",
        ],
        observed={"tool_count": len(tool_calls), "tools": [call.get("tool") for call in tool_calls]},
        expected=[
            "read_file",
            "glob",
            "run_tests",
            "edit_file",
            "read_file",
            "edit_file",
            "write_file",
            "write_file",
            "write_file",
        ],
    )
    _scenario_check(
        checks,
        "workbench_surfaces_work_session_ledgers",
        any(item.get("exit_code") == 0 for item in workbench_session_verifications)
        and any(str(item.get("path") or "").endswith("approved.md") for item in workbench_session_writes)
        and any(str(item.get("path") or "").endswith("generated.md") for item in workbench_session_writes),
        observed={
            "verifications": workbench_session_verifications,
            "writes": workbench_session_writes,
        },
        expected="workbench includes work-session verification and write summaries",
    )
    _scenario_check(
        checks,
        "global_ledgers_surface_work_session_tools",
        verification_ledger_result.get("exit_code") == 0
        and writes_ledger_result.get("exit_code") == 0
        and any((item or {}).get("source") == "work_session" for item in verification_ledger_data)
        and any((item or {}).get("source") == "work_session" for item in writes_ledger_data),
        observed={"verification": verification_ledger_data[:3], "writes": writes_ledger_data[:3]},
        expected="mew verification/writes include native work-session tool calls",
    )
    _scenario_check(
        checks,
        "work_timeline_surfaces_tool_events",
        timeline_result.get("exit_code") == 0
        and len(timeline) >= 5
        and any(event.get("kind") == "tool_call" and event.get("label") == "read_file" for event in timeline),
        observed=timeline[:5],
        expected="timeline includes compact work-session tool events",
    )
    _scenario_check(
        checks,
        "chat_surfaces_work_session_details",
        chat_result.get("exit_code") == 0
        and "Work session #1 [active] task=#1" in (chat_result.get("stdout") or "")
        and "Recent diffs" in (chat_result.get("stdout") or ""),
        observed=command_result_tail(chat_result),
        expected="chat /work-session details shows active session and recent diffs",
    )
    _scenario_check(
        checks,
        "chat_resume_surfaces_world_state",
        chat_world_result.get("exit_code") == 0
        and "World state" in (chat_world_result.get("stdout") or "")
        and "README.md" in (chat_world_result.get("stdout") or ""),
        observed=command_result_tail(chat_world_result),
        expected="chat /work-session resume --allow-read . shows live file state",
    )
    _scenario_check(
        checks,
        "work_recovery_resume_surfaces_side_effect_review",
        interrupted_resume_result.get("exit_code") == 0
        and bool(interrupted_items)
        and interrupted_items[0].get("action") == "needs_user_review"
        and interrupted_items[0].get("command")
        and interrupted_items[0].get("review_hint")
        and interrupted_items[0].get("review_steps"),
        observed=interrupted_items[:1],
        expected="resume recovery plan includes side-effect review context",
    )
    _scenario_check(
        checks,
        "work_recover_reports_side_effect_review_context",
        interrupted_recover_result.get("exit_code") == 0
        and interrupted_recovery.get("action") == "needs_user"
        and interrupted_review.get("command")
        and interrupted_review.get("review_hint")
        and interrupted_review.get("review_steps"),
        observed=interrupted_recovery,
        expected="recover-session reports review context for side-effecting interruption",
    )
    _scenario_check(
        checks,
        "work_resume_auto_recovers_safe_read",
        auto_recover_result.get("exit_code") == 0
        and (auto_recovery.get("recovery") or {}).get("action") == "retry_tool"
        and bool((auto_recovery.get("recovery") or {}).get("world_state_before"))
        and auto_tool_call.get("status") == "completed"
        and ((auto_tool_call.get("result") or {}).get("text") or "").find("native hands") >= 0
        and (auto_recover_data.get("resume") or {}).get("phase") == "idle",
        observed=auto_recovery,
        expected="resume --auto-recover-safe retries interrupted read_file after read gate",
    )
    return _scenario_report("work-session", workspace, commands, checks)


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
        elif name == "runtime-focus":
            reports.append(run_runtime_focus_scenario(scenario_workspace, env=env))
        elif name == "chat-cockpit":
            reports.append(run_chat_cockpit_scenario(scenario_workspace, env=env))
        elif name == "work-session":
            reports.append(run_work_session_scenario(scenario_workspace, env=env))
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


def dogfood_stop_timeout(args):
    timeout = max(0.0, float(getattr(args, "stop_timeout", 10.0) or 0.0))
    if getattr(args, "ai", False):
        timeout = max(timeout, float(getattr(args, "model_timeout", 60.0) or 60.0) + 15.0)
    return timeout


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


def runtime_effect_summary(state, limit=5):
    effects = list(state.get("runtime_effects", []))
    latest = []
    for effect in effects[-limit:]:
        latest.append(
            {
                "id": effect.get("id"),
                "event_id": effect.get("event_id"),
                "reason": effect.get("reason"),
                "status": effect.get("status"),
                "action_types": effect.get("action_types") or [],
                "verification_run_ids": effect.get("verification_run_ids") or [],
                "write_run_ids": effect.get("write_run_ids") or [],
            }
        )
    return {
        "total": len(effects),
        "by_status": count_by(effects, "status"),
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
        "trace_model_enabled": any(part == "--trace-model" for part in command or []),
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
        "runtime_effects": runtime_effect_summary(state),
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


def format_model_trace_summary(summary, enabled=False):
    summary = summary or {}
    latest = summary.get("latest") or []
    return (
        f"enabled={bool(enabled)} "
        f"total={summary.get('total', 0)} "
        f"by_status={summary.get('by_status', {})} "
        f"by_phase={summary.get('by_phase', {})} "
        f"latest={len(latest)}"
    )


def format_runtime_effect_summary(summary):
    if isinstance(summary, int):
        return f"total={summary}"
    summary = summary or {}
    latest = summary.get("latest") or []
    return (
        f"total={summary.get('total', 0)} "
        f"by_status={summary.get('by_status', {})} "
        f"latest={len(latest)}"
    )


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
        "model_traces: "
        + format_model_trace_summary(
            report.get("model_traces"),
            enabled=bool(report.get("trace_model_enabled")),
        ),
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
        "runtime_effects: " + format_runtime_effect_summary(report.get("runtime_effects")),
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
        exit_code = stop_process(process, timeout=dogfood_stop_timeout(args))

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
