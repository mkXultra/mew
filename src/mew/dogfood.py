import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace

from .brief import recent_activity, next_move
from .config import LOG_FILE, MODEL_TRACE_FILE, STATE_DIR, STATE_FILE
from .programmer import create_task_plan
from .project_snapshot import format_project_snapshot, refresh_project_snapshot
from .read_tools import is_sensitive_path
from .state import default_state, migrate_state, next_id, reconcile_next_ids
from .tasks import find_task
from .thoughts import dropped_thread_warning_for_context
from .timeutil import now_iso, parse_time
from .typed_memory import FileMemoryBackend
from .work_session import build_work_session_effort, build_work_session_resume, find_work_session


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
    "resident-loop",
    "native-work",
    "self-improve-controls",
    "native-advance",
    "passive-recovery-loop",
    "passive-auto-recovery",
    "passive-auto-recovery-read",
    "passive-auto-recovery-write",
    "day-reentry",
    "continuity",
    "m3-reentry-gate",
    "chat-cockpit",
    "work-session",
    "m2-comparative",
)
M2_COMPARATIVE_TASK_SHAPES = (
    "standard",
    "interruption_resume",
    "test_discovery",
    "approval_pairing",
    "process_stop",
    "write_heavy",
)
M2_FRESH_CLI_CONTEXT_MODES = ("true_restart", "same_session_resume", "unknown")
DOGFOOD_OBSERVED_TEXT_LIMIT = 400
DOGFOOD_OBSERVED_LIST_LIMIT = 5
DOGFOOD_OBSERVED_DICT_LIMIT = 40


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
    if getattr(args, "allow_native_work", False):
        command.append("--allow-native-work")
    if getattr(args, "allow_native_advance", False):
        command.append("--allow-native-advance")
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
    repo_root = Path(__file__).resolve().parents[2]
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = src_root if not existing else src_root + os.pathsep + existing
    source_cli = repo_root / "mew"
    if "MEW_EXECUTABLE" not in env and source_cli.is_file() and os.access(source_cli, os.X_OK):
        env["MEW_EXECUTABLE"] = str(source_cli)
    return env


def dogfood_runtime_env(extra_env=None):
    env = dogfood_subprocess_env()
    if extra_env:
        env.update(extra_env)
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
            "observed": compact_dogfood_value(observed),
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
        "commands": [compact_command_result(command) for command in commands],
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
    explicit_b_questions = explicit_b.get("open_questions") or []
    explicit_b_question_text = (explicit_b_questions[0] or {}).get("text") if explicit_b_questions else ""

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
        and bool(explicit_b_questions),
        observed={
            "task_id": (explicit_b.get("task") or {}).get("id"),
            "open_questions": len(explicit_b_questions),
        },
        expected={"task_id": 1, "open_questions": ">=1"},
    )
    _scenario_check(
        checks,
        "ready_coding_question_points_to_code_cockpit",
        "./mew code 1" in explicit_b_question_text,
        observed=explicit_b_question_text,
        expected="ready coding passive question mentions ./mew code 1",
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
    state["tasks"].append(
        {
            "id": 1,
            "title": "Dogfood Active Recall",
            "description": "Check active typed memory injection.",
            "status": "todo",
            "priority": "normal",
            "kind": "coding",
            "notes": "",
            "created_at": "now",
            "updated_at": "now",
        }
    )
    write_json_file(workspace / STATE_FILE, state)
    FileMemoryBackend(workspace).write(
        "User prefers compact typed memory recall in dogfood output.",
        scope="private",
        memory_type="user",
        name="Dogfood recall preference",
        description="Typed memory should stay separable from legacy state memory.",
        created_at="2026-04-19T00:00:00Z",
    )
    FileMemoryBackend(workspace).write(
        "Dogfood Active Recall should surface this project memory in active memory output.",
        scope="private",
        memory_type="project",
        name="Dogfood active recall project note",
        description="Active memory debug output should include relevant project memory.",
        created_at="2026-04-19T00:00:01Z",
    )

    def run(args, timeout=30):
        result = run_command(_scenario_command(*args), workspace, timeout=timeout, env=env)
        commands.append(result)
        return result

    text_result = run(["memory", "--search", "trace"])
    json_result = run(["memory", "--search", "runtime", "--json"])
    snapshot_result = run(["memory", "--search", "dogfood anchor", "--json"])
    typed_result = run(["memory", "--search", "compact typed", "--type", "user", "--json"])
    active_result = run(["memory", "--active", "--task-id", "1", "--json"])
    context_save_result = run(
        [
            "context",
            "--save",
            "Dogfood checkpoint next safe action: continue memory-search scenario.",
            "--name",
            "Dogfood context checkpoint",
            "--description",
            "Dogfood context checkpoint should load after compression.",
        ]
    )
    context_load_result = run(["context", "--load", "--query", "Dogfood context checkpoint", "--limit", "1"])
    context_focus_result = run(["focus", "--kind", "coding"])
    context_brief_result = run(["brief", "--kind", "coding"])
    context_desk_result = run(["desk", "--kind", "coding", "--json"])
    json_data = _json_stdout(json_result)
    matches = json_data.get("matches") or []
    snapshot_data = _json_stdout(snapshot_result)
    snapshot_matches = snapshot_data.get("matches") or []
    typed_data = _json_stdout(typed_result)
    typed_matches = typed_data.get("matches") or []
    active_data = _json_stdout(active_result)
    active_matches = (active_data.get("active_memory") or {}).get("items") or []
    context_desk_data = _json_stdout(context_desk_result)

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
    _scenario_check(
        checks,
        "memory_search_json_filters_typed_user_memory",
        typed_result.get("exit_code") == 0
        and any(
            match.get("memory_type") == "user"
            and match.get("memory_scope") == "private"
            and match.get("storage") == "file"
            for match in typed_matches
        ),
        observed=typed_matches,
        expected="typed private user memory match from file-backed store",
    )
    _scenario_check(
        checks,
        "memory_active_json_surfaces_injected_typed_memory",
        active_result.get("exit_code") == 0
        and any(match.get("memory_type") == "user" for match in active_matches)
        and any(match.get("name") == "Dogfood active recall project note" for match in active_matches),
        observed=[
            {"name": match.get("name"), "memory_type": match.get("memory_type"), "reason": match.get("reason")}
            for match in active_matches
        ],
        expected="active typed memory includes always-on user memory and task-matched project memory",
    )
    _scenario_check(
        checks,
        "context_checkpoint_save_load_round_trips",
        context_save_result.get("exit_code") == 0
        and context_load_result.get("exit_code") == 0
        and "recommended: Dogfood context checkpoint" in (context_load_result.get("stdout") or "")
        and "Dogfood checkpoint next safe action" in (context_load_result.get("stdout") or "")
        and "current_git_status:" in (context_load_result.get("stdout") or ""),
        observed=command_result_tail(context_load_result),
        expected="context --save checkpoint is recoverable through context --load",
    )
    _scenario_check(
        checks,
        "context_checkpoint_surfaces_in_focus",
        context_focus_result.get("exit_code") == 0
        and "Checkpoint: Dogfood context checkpoint" in (context_focus_result.get("stdout") or "")
        and "Dogfood checkpoint next safe action" in (context_focus_result.get("stdout") or ""),
        observed=command_result_tail(context_focus_result),
        expected="focus surfaces the latest context checkpoint and next safe action",
    )
    _scenario_check(
        checks,
        "context_checkpoint_surfaces_in_brief",
        context_brief_result.get("exit_code") == 0
        and "context_checkpoint: Dogfood context checkpoint" in (context_brief_result.get("stdout") or "")
        and "context_checkpoint_note: Dogfood checkpoint next safe action" in (context_brief_result.get("stdout") or ""),
        observed=command_result_tail(context_brief_result),
        expected="brief surfaces the latest context checkpoint and note",
    )
    desk_checkpoint = context_desk_data.get("latest_context_checkpoint") or {}
    _scenario_check(
        checks,
        "context_checkpoint_surfaces_in_desk_json",
        context_desk_result.get("exit_code") == 0
        and desk_checkpoint.get("name") == "Dogfood context checkpoint"
        and "text" not in desk_checkpoint
        and "Dogfood checkpoint next safe action" in (desk_checkpoint.get("reentry_note") or ""),
        observed={
            "checkpoint": desk_checkpoint,
            "current_git": context_desk_data.get("current_git"),
        },
        expected="desk --json surfaces a compact latest context checkpoint",
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
    passive_result = run(
        [
            "run",
            "--once",
            "--passive-now",
            "--echo-effects",
            "--focus",
            "Take one focused dogfood passive tick",
            "--poll-interval",
            "0.01",
        ],
        timeout=15,
    )
    brief_result = run(["brief"], timeout=15)
    doctor_result = run(["doctor"], timeout=15)
    desk_result = run(["desk", "--json"], timeout=15)
    observe_result = run(["observe", "--allow-read", ".", "--json"], timeout=15)
    bundle_day = now_iso()[:10]
    feed_path = workspace / "morning-feed.json"
    feed_path.write_text(
        json.dumps(
            {
                "items": [
                    {
                        "title": "Passive AI shell dogfood",
                        "source": "local",
                        "summary": "A local-first passive AI shell note.",
                        "tags": ["mew", "passive-ai"],
                    },
                    {
                        "title": "Unrelated database note",
                        "source": "local",
                        "summary": "A low-priority exploration item.",
                        "tags": ["database"],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    journal_result = run(["journal", "--date", bundle_day, "--write", "--json"], timeout=15)
    mood_result = run(["mood", "--date", bundle_day, "--write", "--json"], timeout=15)
    self_memory_result = run(["self-memory", "--date", bundle_day, "--write", "--json"], timeout=15)
    dream_result = run(["dream", "--date", bundle_day, "--write", "--json"], timeout=15)
    morning_paper_result = run(
        [
            "morning-paper",
            str(feed_path),
            "--date",
            bundle_day,
            "--interest",
            "passive-ai",
            "--write",
            "--json",
        ],
        timeout=15,
    )
    bundle_result = run(["bundle", "--date", bundle_day, "--json"], timeout=15)
    stale_task_result = run(
        [
            "task",
            "add",
            "Dogfood stale passive question",
            "--kind",
            "research",
            "--ready",
            "--description",
            "Synthetic task for stale passive question refresh dogfood.",
            "--json",
        ],
        timeout=15,
    )
    stale_seed_result = run(
        [
            "run",
            "--once",
            "--passive-now",
            "--autonomous",
            "--autonomy-level",
            "propose",
            "--echo-outbox",
            "--poll-interval",
            "0.01",
            "--focus",
            "Seed one stale passive question for dogfood.",
        ],
        timeout=15,
    )
    stale_task_data = _json_stdout(stale_task_result)
    stale_task_id = stale_task_data.get("id")
    if stale_task_id is not None:
        state_path = workspace / STATE_FILE
        state = json.loads(state_path.read_text(encoding="utf-8"))
        stale_question_ids = []
        for question in state.get("questions", []):
            if question.get("related_task_id") == stale_task_id and question.get("status") == "open":
                question["created_at"] = "2026-01-01T00:00:00Z"
                question["updated_at"] = "2026-01-01T00:00:00Z"
                stale_question_ids.append(question.get("id"))
        for message in state.get("outbox", []):
            if message.get("question_id") in stale_question_ids:
                message["created_at"] = "2026-01-01T00:00:00Z"
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    stale_refresh_result = run(
        [
            "run",
            "--once",
            "--passive-now",
            "--autonomous",
            "--autonomy-level",
            "propose",
            "--echo-outbox",
            "--poll-interval",
            "0.01",
            "--focus",
            "Refresh stale passive question for dogfood.",
        ],
        timeout=15,
    )
    stale_state = json.loads((workspace / STATE_FILE).read_text(encoding="utf-8"))
    desk_data = _json_stdout(desk_result)
    observe_data = _json_stdout(observe_result)
    journal_data = _json_stdout(journal_result)
    mood_data = _json_stdout(mood_result)
    self_memory_data = _json_stdout(self_memory_result)
    dream_data = _json_stdout(dream_result)
    morning_paper_data = _json_stdout(morning_paper_result)
    bundle_data = _json_stdout(bundle_result)

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
        "runtime_passive_now_processes_passive_tick",
        passive_result.get("exit_code") == 0
        and "processed 1 event(s) reason=passive_tick" in (passive_result.get("stdout") or ""),
        observed=command_result_tail(passive_result),
        expected="run --once --passive-now processes a passive_tick without waiting for a loop",
    )
    _scenario_check(
        checks,
        "runtime_passive_now_echoes_effect_summary",
        "effect #2 [applied] event=#2 reason=passive_tick" in (passive_result.get("stdout") or ""),
        observed=command_result_tail(passive_result),
        expected="run --once --passive-now --echo-effects prints the passive runtime effect",
    )
    stale_questions = [
        question
        for question in stale_state.get("questions", [])
        if question.get("related_task_id") == stale_task_id
    ]
    _scenario_check(
        checks,
        "runtime_passive_refreshes_stale_question_once",
        stale_task_result.get("exit_code") == 0
        and stale_seed_result.get("exit_code") == 0
        and stale_refresh_result.get("exit_code") == 0
        and len([question for question in stale_questions if question.get("status") == "deferred"]) == 1
        and len([question for question in stale_questions if question.get("status") == "open"]) == 1
        and f"Task #{stale_task_id} is ready research work." in (stale_refresh_result.get("stdout") or ""),
        observed={
            "task": stale_task_data,
            "seed": command_result_tail(stale_seed_result),
            "refresh": command_result_tail(stale_refresh_result),
            "questions": [
                {
                    "id": question.get("id"),
                    "status": question.get("status"),
                    "defer_reason": question.get("defer_reason"),
                }
                for question in stale_questions
            ],
        },
        expected="one stale task question is deferred and refreshed as one visible outbox question",
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
        and "runtime_effects: total=2 incomplete=0" in (doctor_result.get("stdout") or ""),
        observed=command_result_tail(doctor_result),
        expected="doctor shows runtime effect count",
    )
    _scenario_check(
        checks,
        "desk_json_surfaces_pet_state",
        desk_result.get("exit_code") == 0 and bool(desk_data.get("pet_state")),
        observed=desk_data,
        expected="desk --json returns a pet_state view model",
    )
    _scenario_check(
        checks,
        "observe_alias_json_surfaces_observations",
        observe_result.get("exit_code") == 0 and isinstance(observe_data.get("observations"), list),
        observed={"observation_count": len(observe_data.get("observations") or [])},
        expected="observe --json aliases perceive and returns observations",
    )
    _scenario_check(
        checks,
        "journal_json_writes_report",
        journal_result.get("exit_code") == 0
        and bool(journal_data.get("mew_note"))
        and (workspace / ".mew" / "journal" / f"{bundle_day}.md").exists(),
        observed=journal_data,
        expected="journal --write --json returns summary counts and writes a journal report",
    )
    _scenario_check(
        checks,
        "mood_json_writes_report",
        mood_result.get("exit_code") == 0
        and bool(mood_data.get("label"))
        and (workspace / ".mew" / "mood" / f"{bundle_day}.md").exists(),
        observed=mood_data,
        expected="mood --write --json returns scores and writes a mood report",
    )
    _scenario_check(
        checks,
        "self_memory_json_writes_report",
        self_memory_result.get("exit_code") == 0
        and "learnings" in self_memory_data
        and (workspace / ".mew" / "self" / f"learned-{bundle_day}.md").exists(),
        observed=self_memory_data,
        expected="self-memory --write --json returns learnings and writes a report",
    )
    _scenario_check(
        checks,
        "dream_json_writes_report",
        dream_result.get("exit_code") == 0
        and "learnings" in dream_data
        and (workspace / ".mew" / "dreams" / f"{bundle_day}.md").exists(),
        observed=dream_data,
        expected="dream --write --json returns learnings and writes a report",
    )
    _scenario_check(
        checks,
        "morning_paper_json_writes_report",
        morning_paper_result.get("exit_code") == 0
        and morning_paper_data.get("top_picks") == 1
        and (workspace / ".mew" / "morning-paper" / f"{bundle_day}.md").exists(),
        observed=morning_paper_data,
        expected="morning-paper --write --json ranks a static feed and writes a report",
    )
    _scenario_check(
        checks,
        "bundle_json_surfaces_generated_report",
        bundle_result.get("exit_code") == 0
        and "Journal" in (bundle_data.get("included") or [])
        and "Mood" in (bundle_data.get("included") or [])
        and "Morning Paper" in (bundle_data.get("included") or [])
        and "Dream" in (bundle_data.get("included") or [])
        and "Self Memory" in (bundle_data.get("included") or [])
        and (workspace / ".mew" / "passive-bundle" / f"{bundle_day}.md").exists(),
        observed=bundle_data,
        expected="bundle --json includes generated journal, mood, morning paper, dream, and self-memory reports",
    )
    return _scenario_report("runtime-focus", workspace, commands, checks)


def run_resident_loop_scenario(workspace, env=None):
    commands = []
    checks = []

    def run(args, timeout=30):
        result = run_command(_scenario_command(*args), workspace, timeout=timeout, env=env)
        commands.append(result)
        return result

    task_result = run(
        [
            "task",
            "add",
            "Resident loop cadence task",
            "--kind",
            "coding",
            "--priority",
            "normal",
            "--json",
        ],
        timeout=15,
    )
    task_data = _json_stdout(task_result)
    runtime_args = SimpleNamespace(
        interval=2.0,
        poll_interval=0.1,
        autonomy_level="propose",
        model_timeout=20.0,
        ai=False,
        auth=None,
        model_backend="",
        model="",
        base_url="",
        allow_write=False,
        allow_verify=False,
        verify_command="",
        verify_interval_minutes=0.05,
        execute_tasks=False,
        allow_agent_run=False,
        agent_stale_minutes=None,
        agent_result_timeout=None,
        agent_start_timeout=None,
        review_model=None,
        trace_model=False,
        max_reflex_rounds=0,
        startup_timeout=5.0,
        message_timeout=5.0,
        send_message=[],
        duration=6.0,
        cleanup=False,
        stop_timeout=10.0,
        wait_agent_runs=0.0,
    )
    resident_report = _run_dogfood_in_workspace(
        runtime_args,
        workspace,
        created_temp=False,
    )
    commands.append(
        {
            "command": resident_report.get("command") or [],
            "exit_code": resident_report.get("exit_code"),
            "stdout": "\n".join(resident_report.get("runtime_output_tail") or []),
            "stderr": "",
        }
    )

    state = read_json_file(Path(workspace) / STATE_FILE, {})
    processed_events = [
        event for event in state.get("inbox", [])
        if event.get("processed_at")
    ]
    passive_events = [
        event for event in processed_events
        if event.get("type") == "passive_tick"
    ]
    passive_effects = [
        effect for effect in state.get("runtime_effects", [])
        if effect.get("reason") == "passive_tick"
    ]
    repeated_wait_thoughts = [
        thought for thought in state.get("thought_journal", [])
        if int(thought.get("repeat_count") or 1) >= 2
    ]
    runtime_output = "\n".join(resident_report.get("runtime_output_tail") or [])
    passive_times = [
        parsed
        for parsed in (
            parse_time(event.get("processed_at") or event.get("created_at"))
            for event in passive_events
        )
        if parsed is not None
    ]
    passive_gaps = [
        round((later - earlier).total_seconds(), 2)
        for earlier, later in zip(passive_times, passive_times[1:])
    ]

    _scenario_check(
        checks,
        "resident_loop_starts_and_stops",
        task_result.get("exit_code") == 0
        and resident_report.get("exit_code") == 0
        and (resident_report.get("duration_seconds") or 0) >= 5.0,
        observed={
            "task": task_data,
            "exit_code": resident_report.get("exit_code"),
            "duration_seconds": resident_report.get("duration_seconds"),
        },
        expected="resident runtime starts, runs briefly, and stops cleanly",
    )
    _scenario_check(
        checks,
        "resident_loop_processes_multiple_events",
        len(processed_events) >= 2
        and bool([event for event in processed_events if event.get("type") == "startup"])
        and len(passive_events) >= 2
        and any(gap >= 1.0 for gap in passive_gaps),
        observed={
            "processed": len(processed_events),
            "by_type": count_by(processed_events, "type"),
            "passive_gaps_seconds": passive_gaps,
        },
        expected="startup and at least two spaced passive_tick events are processed",
    )
    _scenario_check(
        checks,
        "resident_loop_records_passive_effect",
        len(passive_effects) >= 2
        and all(effect.get("status") == "applied" for effect in passive_effects[-2:]),
        observed=runtime_effect_summary(state),
        expected="at least two applied passive_tick runtime effects",
    )
    _scenario_check(
        checks,
        "resident_loop_compacts_repeated_wait_thoughts",
        bool(repeated_wait_thoughts),
        observed=[
            {
                "id": thought.get("id"),
                "repeat_count": thought.get("repeat_count"),
                "last_event_id": thought.get("last_event_id"),
            }
            for thought in repeated_wait_thoughts[-3:]
        ],
        expected="repeated passive wait thoughts are compacted instead of appended every tick",
    )
    _scenario_check(
        checks,
        "resident_loop_echoes_passive_output",
        runtime_output.count("reason=passive_tick") >= 2,
        observed=resident_report.get("runtime_output_tail"),
        expected="runtime stdout includes repeated passive_tick summaries",
    )
    return _scenario_report("resident-loop", workspace, commands, checks)


def run_native_work_scenario(workspace, env=None):
    commands = []
    checks = []

    def run(args, timeout=30):
        result = run_command(_scenario_command(*args), workspace, timeout=timeout, env=env)
        commands.append(result)
        return result

    task_result = run(
        [
            "task",
            "add",
            "Native work session smoke task",
            "--kind",
            "coding",
            "--ready",
            "--priority",
            "high",
            "--json",
        ],
        timeout=15,
    )
    task_data = _json_stdout(task_result)
    task = task_data.get("task") if isinstance(task_data.get("task"), dict) else task_data
    task_id = task.get("id") if isinstance(task, dict) else None
    runtime_args = SimpleNamespace(
        interval=2.0,
        poll_interval=0.1,
        autonomy_level="act",
        model_timeout=20.0,
        ai=False,
        auth=None,
        model_backend="",
        model="",
        base_url="",
        allow_write=False,
        allow_verify=True,
        verify_command=f"{sys.executable} -V",
        verify_interval_minutes=0.05,
        execute_tasks=False,
        allow_agent_run=False,
        allow_native_work=True,
        agent_stale_minutes=None,
        agent_result_timeout=None,
        agent_start_timeout=None,
        review_model=None,
        trace_model=False,
        max_reflex_rounds=0,
        startup_timeout=5.0,
        message_timeout=5.0,
        send_message=[],
        duration=3.0,
        cleanup=False,
        stop_timeout=10.0,
        wait_agent_runs=0.0,
    )
    resident_report = _run_dogfood_in_workspace(
        runtime_args,
        workspace,
        created_temp=False,
    )
    commands.append(
        {
            "command": resident_report.get("command") or [],
            "exit_code": resident_report.get("exit_code"),
            "stdout": "\n".join(resident_report.get("runtime_output_tail") or []),
            "stderr": "",
        }
    )

    state = read_json_file(Path(workspace) / STATE_FILE, {})
    sessions = [
        session for session in state.get("work_sessions", [])
        if str(session.get("task_id")) == str(task_id)
    ]
    active_sessions = [session for session in sessions if session.get("status") == "active"]
    latest_active_session = active_sessions[-1] if active_sessions else {}
    latest_defaults = latest_active_session.get("default_options") or {}
    task_questions = [
        question for question in state.get("questions", [])
        if str(question.get("related_task_id")) == str(task_id)
    ]
    native_messages = [
        message for message in state.get("outbox", [])
        if "native work session" in (message.get("text") or "")
    ]
    outbox_text = "\n".join(message.get("text") or "" for message in state.get("outbox", []))
    action_types = [
        action_type
        for effect in state.get("runtime_effects", [])
        for action_type in effect.get("action_types", [])
    ]

    _scenario_check(
        checks,
        "native_work_starts_and_stops",
        task_result.get("exit_code") == 0
        and resident_report.get("exit_code") == 0
        and (resident_report.get("duration_seconds") or 0) >= 2.0,
        observed={
            "task": task_data,
            "exit_code": resident_report.get("exit_code"),
            "duration_seconds": resident_report.get("duration_seconds"),
        },
        expected="resident runtime starts, runs briefly, and stops cleanly",
    )
    _scenario_check(
        checks,
        "native_work_session_created_for_ready_coding_task",
        bool(active_sessions),
        observed=active_sessions[-3:],
        expected="an active work session is attached to the ready coding task",
    )
    _scenario_check(
        checks,
        "native_work_seeds_runtime_defaults",
        str(workspace) in (latest_defaults.get("allow_read") or [])
        and latest_defaults.get("allow_verify") is True
        and latest_defaults.get("verify_command") == runtime_args.verify_command
        and latest_defaults.get("model_backend") == "codex"
        and any(note.get("source") == "runtime" for note in latest_active_session.get("notes") or []),
        observed={
            "default_options": latest_defaults,
            "notes": latest_active_session.get("notes") or [],
        },
        expected="passive-started session inherits runtime read/verify defaults and records provenance",
    )
    _scenario_check(
        checks,
        "native_work_records_start_action",
        "start_work_session" in action_types,
        observed=runtime_effect_summary(state),
        expected="runtime effect action_types include start_work_session",
    )
    _scenario_check(
        checks,
        "native_work_routes_user_to_code_cockpit",
        (f"./mew code {task_id}" in outbox_text or f"mew code {task_id}" in outbox_text)
        and f"mew work {task_id} --live" in outbox_text
        and f"mew work {task_id} --follow" in outbox_text
        and "--model-backend codex" in outbox_text
        and "--allow-verify" in outbox_text
        and "--verify-command" in outbox_text
        and "native work session" in outbox_text,
        observed=outbox_text,
        expected="outbox tells the user how to open, live-step, or follow the native work session",
    )
    _scenario_check(
        checks,
        "native_work_start_message_is_visible",
        any(
            message.get("type") == "assistant" and not message.get("read_at")
            for message in native_messages
        ),
        observed=native_messages,
        expected="native work start message remains visible to attach/outbox listeners",
    )
    _scenario_check(
        checks,
        "native_work_skips_redundant_ready_question",
        not task_questions,
        observed=task_questions,
        expected="starting native work does not also leave a redundant task question open",
    )
    _scenario_check(
        checks,
        "native_work_does_not_start_external_agent_run",
        not state.get("agent_runs"),
        observed=state.get("agent_runs"),
        expected="native work dogfood keeps external agent runs disabled",
    )
    return _scenario_report("native-work", workspace, commands, checks)


def run_self_improve_controls_scenario(workspace, env=None):
    commands = []
    checks = []

    def run(args, timeout=30):
        result = run_command(_scenario_command(*args), workspace, timeout=timeout, env=env)
        commands.append(result)
        return result

    def run_control(control, timeout=30):
        parts = shlex.split(str(control or ""))
        if parts and Path(parts[0]).name == "mew":
            parts = parts[1:]
        if not parts:
            result = {
                "command": [],
                "exit_code": None,
                "stdout": "",
                "stderr": "empty control command",
            }
            commands.append(result)
            return result
        return run(parts, timeout=timeout)

    start_result = run(
        [
            "self-improve",
            "--start-session",
            "--focus",
            "Dogfood native self-improve controls",
            "--json",
        ],
        timeout=15,
    )
    start_data = _json_stdout(start_result)
    controls = start_data.get("controls") or {}
    task = start_data.get("task") or {}
    work_session = start_data.get("work_session") or {}
    start_notes = work_session.get("notes") or []
    task_id = task.get("id")

    status_absent_result = run_control(controls.get("status"), timeout=15)
    status_absent_data = _json_stdout(status_absent_result)
    refresh_command = (status_absent_data.get("suggested_recovery") or {}).get("command") or ""
    refresh_result = run_control(refresh_command, timeout=15)
    status_fresh_result = run_control(controls.get("status"), timeout=15)
    status_fresh_data = _json_stdout(status_fresh_result)
    resume_result = run_control(controls.get("resume"), timeout=15)
    cells_result = run_control(controls.get("cells"), timeout=15)
    active_memory_result = run_control(controls.get("active_memory"), timeout=15)

    state_path = workspace / STATE_FILE
    state = migrate_state(read_json_file(state_path, default_state()))
    reconcile_next_ids(state)
    session = next(
        (
            candidate
            for candidate in state.get("work_sessions", [])
            if str(candidate.get("task_id")) == str(task_id)
        ),
        None,
    )
    if session:
        session["default_options"] = {
            "auth": "auth.json",
            "model_backend": "codex",
            "allow_read": ["README.md"],
            "allow_write": ["src/mew", "tests"],
            "allow_verify": True,
            "verify_command": f"{sys.executable} -V",
            "act_mode": "deterministic",
            "compact_live": False,
            "quiet": True,
        }
        session["updated_at"] = now_iso()
        write_json_file(state_path, state)

    reused_result = run(
        [
            "self-improve",
            "--start-session",
            "--focus",
            "Dogfood native self-improve controls reused",
            "--json",
        ],
        timeout=15,
    )
    reused_data = _json_stdout(reused_result)
    reused_controls = reused_data.get("controls") or {}
    reused_session = reused_data.get("work_session") or {}
    reused_defaults = reused_session.get("default_options") or {}
    reused_notes = reused_session.get("notes") or []

    _scenario_check(
        checks,
        "self_improve_start_session_json_surfaces_controls",
        start_result.get("exit_code") == 0
        and start_data.get("native") is True
        and bool(task_id)
        and work_session.get("task_id") == task_id
        and all(key in controls for key in ("continue", "follow", "status", "resume", "cells", "active_memory", "chat")),
        observed={
            "task_id": task_id,
            "session_id": work_session.get("id"),
            "controls": controls,
        },
        expected="self-improve --start-session --json returns native work controls",
    )
    _scenario_check(
        checks,
        "self_improve_start_session_seeds_reentry_note",
        any(
            str(note.get("text") or "").startswith("Native self-improve reentry prepared.")
            and (controls.get("continue") or "") in str(note.get("text") or "")
            and (controls.get("resume") or "") in str(note.get("text") or "")
            for note in start_notes
        ),
        observed={"notes": start_notes, "controls": controls},
        expected="native self-improve sessions carry a durable reentry note",
    )
    _scenario_check(
        checks,
        "self_improve_status_reports_absent_snapshot_with_refresh",
        status_absent_result.get("exit_code") == 1
        and status_absent_data.get("status") == "absent"
        and (status_absent_data.get("suggested_recovery") or {}).get("kind") == "refresh_snapshot"
        and " --follow " in f" {refresh_command} ",
        observed=status_absent_data,
        expected="status control is usable and points to a follow snapshot refresh",
    )
    _scenario_check(
        checks,
        "self_improve_status_refresh_command_is_executable",
        refresh_result.get("exit_code") == 0
        and status_fresh_result.get("exit_code") == 0
        and status_fresh_data.get("status") == "fresh"
        and status_fresh_data.get("stop_reason") == "snapshot_refresh",
        observed={
            "refresh": command_result_tail(refresh_result),
            "status": status_fresh_data,
        },
        expected="suggested follow refresh command writes a fresh snapshot",
    )
    _scenario_check(
        checks,
        "self_improve_resume_cells_and_active_memory_controls_run",
        resume_result.get("exit_code") == 0
        and cells_result.get("exit_code") == 0
        and active_memory_result.get("exit_code") == 0,
        observed={
            "resume": command_result_tail(resume_result),
            "cells": command_result_tail(cells_result),
            "active_memory": command_result_tail(active_memory_result),
        },
        expected="resume, cells, and active-memory controls are executable",
    )
    _scenario_check(
        checks,
        "self_improve_reused_session_preserves_defaults",
        reused_result.get("exit_code") == 0
        and reused_data.get("session_created") is False
        and reused_defaults.get("allow_read") == ["README.md", "."]
        and reused_defaults.get("compact_live") is True
        and "--allow-read README.md --allow-read ." in (reused_controls.get("continue") or "")
        and "--allow-write src/mew --allow-write tests" in (reused_controls.get("continue") or "")
        and "--allow-verify" in (reused_controls.get("continue") or ""),
        observed={
            "defaults": reused_defaults,
            "controls": reused_controls,
        },
        expected="reused native self-improve session preserves and extends cached work defaults",
    )
    _scenario_check(
        checks,
        "self_improve_reused_session_refreshes_reentry_note",
        sum(
            1
            for note in reused_notes
            if str(note.get("text") or "").startswith("Native self-improve reentry prepared.")
        )
        == 1
        and (reused_controls.get("continue") or "") in str(reused_notes[-1].get("text") if reused_notes else ""),
        observed={
            "notes": reused_notes,
            "controls": reused_controls,
        },
        expected="reused native self-improve session keeps one current reentry note",
    )
    return _scenario_report("self-improve-controls", workspace, commands, checks)


def write_fake_mew_executable(path):
    script = f"""#!{sys.executable}
import json
import os
import pathlib
import sys

log_path = pathlib.Path(os.environ["MEW_FAKE_WORK_LOG"])
records = []
if log_path.exists():
    records = json.loads(log_path.read_text(encoding="utf-8"))
records.append({{"argv": sys.argv[1:]}})
log_path.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
sys.exit(int(os.environ.get("MEW_FAKE_WORK_EXIT_CODE", "0")))
"""
    path.write_text(script, encoding="utf-8")
    path.chmod(0o755)
    return path


def run_native_advance_scenario(workspace, env=None):
    commands = []
    checks = []

    def run(args, timeout=30):
        result = run_command(_scenario_command(*args), workspace, timeout=timeout, env=env)
        commands.append(result)
        return result

    task_result = run(
        [
            "task",
            "add",
            "Native advance smoke task",
            "--kind",
            "coding",
            "--ready",
            "--priority",
            "high",
            "--json",
        ],
        timeout=15,
    )
    task_data = _json_stdout(task_result)
    task = task_data.get("task") if isinstance(task_data.get("task"), dict) else task_data
    task_id = task.get("id") if isinstance(task, dict) else None

    fake_log = Path(workspace) / "fake-mew-calls.json"
    fake_mew = write_fake_mew_executable(Path(workspace) / "fake-mew")
    scenario_env = dict(env or os.environ)
    scenario_env["MEW_EXECUTABLE"] = str(fake_mew)
    scenario_env["MEW_FAKE_WORK_LOG"] = str(fake_log)
    runtime_args = SimpleNamespace(
        interval=1.0,
        poll_interval=0.05,
        autonomy_level="act",
        model_timeout=20.0,
        ai=False,
        auth=None,
        model_backend="",
        model="",
        base_url="",
        allow_write=False,
        allow_verify=False,
        verify_command=f"{sys.executable} -V",
        verify_interval_minutes=0.05,
        execute_tasks=False,
        allow_agent_run=False,
        allow_native_work=True,
        allow_native_advance=True,
        agent_stale_minutes=None,
        agent_result_timeout=None,
        agent_start_timeout=None,
        review_model=None,
        trace_model=False,
        max_reflex_rounds=0,
        startup_timeout=5.0,
        message_timeout=5.0,
        send_message=[],
        duration=3.5,
        cleanup=False,
        stop_timeout=10.0,
        wait_agent_runs=0.0,
    )
    resident_report = _run_dogfood_in_workspace(
        runtime_args,
        workspace,
        created_temp=False,
        env=scenario_env,
    )
    commands.append(
        {
            "command": resident_report.get("command") or [],
            "exit_code": resident_report.get("exit_code"),
            "stdout": "\n".join(resident_report.get("runtime_output_tail") or []),
            "stderr": "",
        }
    )

    state = read_json_file(Path(workspace) / STATE_FILE, {})
    fake_calls = read_json_file(fake_log, [])
    latest_step = state.get("runtime_status", {}).get("last_native_work_step") or {}
    advance_metrics = native_work_advance_metrics(state)
    work_calls = [call for call in fake_calls if (call.get("argv") or [])[:2] == ["work", str(task_id)]]
    latest_work_args = (work_calls[-1].get("argv") if work_calls else [])

    _scenario_check(
        checks,
        "native_advance_starts_and_stops",
        task_result.get("exit_code") == 0
        and resident_report.get("exit_code") == 0
        and (resident_report.get("duration_seconds") or 0) >= 3.0,
        observed={
            "task": task_data,
            "exit_code": resident_report.get("exit_code"),
            "duration_seconds": resident_report.get("duration_seconds"),
        },
        expected="resident runtime starts, processes passive native advance, and stops cleanly",
    )
    _scenario_check(
        checks,
        "native_advance_invokes_mew_work_live_once_per_tick",
        bool(work_calls)
        and "--live" in latest_work_args
        and "--max-steps" in latest_work_args
        and "1" in latest_work_args
        and "--quiet" in latest_work_args
        and "--compact-live" in latest_work_args
        and "--no-prompt-approval" in latest_work_args,
        observed=fake_calls,
        expected="runtime native advance invokes the configured mew executable with one quiet live step",
    )
    _scenario_check(
        checks,
        "native_advance_records_completed_step",
        latest_step.get("outcome") == "completed"
        and latest_step.get("exit_code") == 0
        and advance_metrics.get("by_outcome", {}).get("completed", 0) >= 1,
        observed={
            "last_native_work_step": latest_step,
            "native_work_advance": advance_metrics,
        },
        expected="runtime status and dogfood metrics record a completed native advance",
    )
    _scenario_check(
        checks,
        "native_advance_preserves_runtime_owned_session",
        any(
            session.get("runtime_managed") is True
            and session.get("owner") == "runtime"
            and str(session.get("task_id")) == str(task_id)
            for session in state.get("work_sessions", [])
        ),
        observed=state.get("work_sessions", []),
        expected="advance scenario uses an explicitly runtime-owned work session",
    )

    approval_workspace = Path(workspace) / "pending-approval-skip"
    approval_workspace.mkdir(parents=True, exist_ok=True)
    approval_task_result = run_command(
        _scenario_command(
            "task",
            "add",
            "Native advance pending approval task",
            "--kind",
            "coding",
            "--ready",
            "--priority",
            "high",
            "--json",
        ),
        approval_workspace,
        timeout=15,
        env=env,
    )
    commands.append(approval_task_result)
    approval_task_data = _json_stdout(approval_task_result)
    approval_task = (
        approval_task_data.get("task")
        if isinstance(approval_task_data.get("task"), dict)
        else approval_task_data
    )
    approval_task_id = approval_task.get("id") if isinstance(approval_task, dict) else None
    approval_state_path = approval_workspace / STATE_FILE
    approval_state = migrate_state(read_json_file(approval_state_path, default_state()))
    reconcile_next_ids(approval_state)
    approval_session_id = next_id(approval_state, "work_session")
    approval_tool_call_id = next_id(approval_state, "work_tool_call")
    approval_time = now_iso()
    approval_state.setdefault("work_sessions", []).append(
        {
            "id": approval_session_id,
            "task_id": approval_task_id,
            "status": "active",
            "title": "Native advance pending approval task",
            "goal": "Hold a pending approval during passive advance.",
            "created_at": approval_time,
            "updated_at": approval_time,
            "runtime_managed": True,
            "owner": "runtime",
            "runtime_started_event_id": 99,
            "default_options": {"allow_read": ["."]},
            "last_tool_call_id": approval_tool_call_id,
            "last_model_turn_id": None,
            "tool_calls": [
                {
                    "id": approval_tool_call_id,
                    "session_id": approval_session_id,
                    "task_id": approval_task_id,
                    "tool": "write_file",
                    "status": "completed",
                    "parameters": {"path": "src/mew/pending.py"},
                    "result": {"dry_run": True, "changed": True, "diff": "+pending\n"},
                    "summary": "pending approval dogfood write",
                    "error": "",
                    "started_at": approval_time,
                    "finished_at": approval_time,
                }
            ],
            "model_turns": [],
        }
    )
    write_json_file(approval_state_path, approval_state)
    approval_fake_log = approval_workspace / "fake-mew-approval-calls.json"
    approval_fake_mew = write_fake_mew_executable(approval_workspace / "fake-mew-approval")
    approval_env = dict(env or os.environ)
    approval_env["MEW_EXECUTABLE"] = str(approval_fake_mew)
    approval_env["MEW_FAKE_WORK_LOG"] = str(approval_fake_log)
    approval_runtime_args = SimpleNamespace(**vars(runtime_args))
    approval_runtime_args.duration = 1.5
    approval_report = _run_dogfood_in_workspace(
        approval_runtime_args,
        approval_workspace,
        created_temp=False,
        env=approval_env,
    )
    commands.append(
        {
            "command": approval_report.get("command") or [],
            "exit_code": approval_report.get("exit_code"),
            "stdout": "\n".join(approval_report.get("runtime_output_tail") or []),
            "stderr": "",
        }
    )
    approval_state = read_json_file(approval_state_path, {})
    approval_runtime = approval_state.get("runtime_status") or {}
    approval_skip_recovery = approval_runtime.get("last_native_work_skip_recovery") or {}
    approval_fake_calls = read_json_file(approval_fake_log, [])
    _scenario_check(
        checks,
        "native_advance_pending_approval_records_recovery_hint",
        approval_task_result.get("exit_code") == 0
        and approval_report.get("exit_code") == 0
        and approval_runtime.get("last_native_work_step_skip") == "pending_write_approval"
        and approval_skip_recovery.get("action") == "resolve_pending_write_approval"
        and "--session --resume --allow-read ." in (approval_skip_recovery.get("command") or "")
        and "--approve-tool" in (approval_skip_recovery.get("blocked_command") or "")
        and "--allow-unpaired-source-edit" in (approval_skip_recovery.get("override_command") or "")
        and "--reject-tool" in (approval_skip_recovery.get("alternate_command") or "")
        and not [
            call for call in approval_fake_calls if (call.get("argv") or [])[:2] == ["work", str(approval_task_id)]
        ],
        observed={
            "last_native_work_step_skip": approval_runtime.get("last_native_work_step_skip"),
            "last_native_work_skip_recovery": approval_skip_recovery,
            "fake_calls": approval_fake_calls,
        },
        expected="unpaired source approval skip records resume-first recovery with blocked approve and override commands",
    )

    failure_workspace = Path(workspace) / "failed-advance"
    failure_workspace.mkdir(parents=True, exist_ok=True)
    failure_task_result = run_command(
        _scenario_command(
            "task",
            "add",
            "Native advance failure recovery task",
            "--kind",
            "coding",
            "--ready",
            "--priority",
            "high",
            "--json",
        ),
        failure_workspace,
        timeout=15,
        env=env,
    )
    commands.append(failure_task_result)
    failure_task_data = _json_stdout(failure_task_result)
    failure_task = (
        failure_task_data.get("task")
        if isinstance(failure_task_data.get("task"), dict)
        else failure_task_data
    )
    failure_task_id = failure_task.get("id") if isinstance(failure_task, dict) else None
    failure_log = failure_workspace / "fake-mew-failure-calls.json"
    failure_fake_mew = write_fake_mew_executable(failure_workspace / "fake-mew-failure")
    failure_env = dict(env or os.environ)
    failure_env["MEW_EXECUTABLE"] = str(failure_fake_mew)
    failure_env["MEW_FAKE_WORK_LOG"] = str(failure_log)
    failure_env["MEW_FAKE_WORK_EXIT_CODE"] = "1"
    failure_runtime_args = SimpleNamespace(**vars(runtime_args))
    failure_runtime_args.duration = 5.0
    failure_report = _run_dogfood_in_workspace(
        failure_runtime_args,
        failure_workspace,
        created_temp=False,
        env=failure_env,
    )
    commands.append(
        {
            "command": failure_report.get("command") or [],
            "exit_code": failure_report.get("exit_code"),
            "stdout": "\n".join(failure_report.get("runtime_output_tail") or []),
            "stderr": "",
        }
    )
    failure_state = read_json_file(failure_workspace / STATE_FILE, {})
    failure_calls = read_json_file(failure_log, [])
    failure_runtime = failure_state.get("runtime_status", {})
    failure_recovery = failure_runtime.get("last_native_work_recovery") or {}
    failure_questions = [
        question
        for question in failure_state.get("questions", [])
        if str(question.get("related_task_id")) == str(failure_task_id)
    ]
    _scenario_check(
        checks,
        "native_advance_failure_asks_recovery_question",
        failure_task_result.get("exit_code") == 0
        and failure_report.get("exit_code") == 0
        and failure_runtime.get("last_native_work_step_skip") == "previous_native_work_step_failed"
        and failure_recovery.get("action") == "ask_user_seeded_question"
        and bool(failure_questions)
        and len([call for call in failure_calls if (call.get("argv") or [])[:2] == ["work", str(failure_task_id)]]) == 1,
        observed={
            "last_native_work_step": failure_runtime.get("last_native_work_step"),
            "last_native_work_step_skip": failure_runtime.get("last_native_work_step_skip"),
            "last_native_work_recovery": failure_recovery,
            "questions": failure_questions,
            "fake_calls": failure_calls,
        },
        expected="failed passive native advance asks a seeded recovery question and does not blindly retry",
    )
    return _scenario_report("native-advance", workspace, commands, checks)


def run_passive_recovery_loop_scenario(workspace, env=None):
    commands = []
    checks = []

    def run(args, timeout=30, scenario_env=None):
        result = run_command(
            _scenario_command(*args),
            workspace,
            timeout=timeout,
            env=scenario_env if scenario_env is not None else env,
        )
        commands.append(result)
        return result

    task_result = run(
        [
            "task",
            "add",
            "Passive recovery loop task",
            "--kind",
            "coding",
            "--ready",
            "--priority",
            "high",
            "--json",
        ],
        timeout=15,
    )
    task_data = _json_stdout(task_result)
    task = task_data.get("task") if isinstance(task_data.get("task"), dict) else task_data
    task_id = task.get("id") if isinstance(task, dict) else None
    verify_command = f"{sys.executable} -V"

    start_result = run(
        [
            "work",
            str(task_id),
            "--start-session",
            "--allow-read",
            ".",
            "--allow-verify",
            "--verify-command",
            verify_command,
            "--json",
        ],
        timeout=15,
    )
    start_data = _json_stdout(start_result)
    session = start_data.get("work_session") or {}
    session_id = session.get("id")

    state_path = Path(workspace) / STATE_FILE
    state = read_json_file(state_path, {})
    state = reconcile_next_ids(migrate_state(state))
    runtime_session = None
    for candidate in state.get("work_sessions") or []:
        if str(candidate.get("id")) == str(session_id):
            runtime_session = candidate
            break
    if runtime_session:
        before = "2026-04-18T05:00:00Z"
        failed_at = "2026-04-18T05:00:10Z"
        runtime_session["owner"] = "runtime"
        runtime_session["runtime_managed"] = True
        runtime_session["runtime_started_at"] = before
        runtime_session["runtime_started_event_id"] = 999
        tool_call_id = next_id(state, "work_tool_call")
        runtime_session.setdefault("tool_calls", []).append(
            {
                "id": tool_call_id,
                "session_id": session_id,
                "task_id": task_id,
                "tool": "run_tests",
                "status": "interrupted",
                "parameters": {
                    "command": verify_command,
                    "cwd": ".",
                    "allow_verify": True,
                    "timeout": 300,
                },
                "result": {"command": verify_command, "cwd": ".", "timed_out": True},
                "summary": "interrupted dogfood verifier",
                "error": "Interrupted before the verifier completed.",
                "started_at": before,
                "finished_at": before,
            }
        )
        runtime_session["last_tool_call_id"] = tool_call_id
        runtime_session["updated_at"] = before
        runtime_status = state.setdefault("runtime_status", {})
        runtime_status["last_native_work_step"] = {
            "finished_at": failed_at,
            "session_id": session_id,
            "task_id": task_id,
            "command": f"mew work {task_id} --live --allow-read . --max-steps 1",
            "exit_code": 1,
            "timed_out": False,
            "outcome": "failed",
        }
        runtime_status["last_action"] = "seeded failed native work step for dogfood"
        write_json_file(state_path, state)

    fake_log = Path(workspace) / "fake-mew-recovery-loop-calls.json"
    fake_mew = write_fake_mew_executable(Path(workspace) / "fake-mew-recovery-loop")
    scenario_env = dict(env or os.environ)
    scenario_env["MEW_EXECUTABLE"] = str(fake_mew)
    scenario_env["MEW_FAKE_WORK_LOG"] = str(fake_log)

    recovery_question_result = run(
        [
            "run",
            "--once",
            "--passive-now",
            "--autonomous",
            "--autonomy-level",
            "act",
            "--allow-native-advance",
            "--poll-interval",
            "0.01",
            "--echo-outbox",
        ],
        timeout=30,
        scenario_env=scenario_env,
    )
    recovery_state = read_json_file(state_path, {})
    recovery_runtime = recovery_state.get("runtime_status") or {}
    recovery = recovery_runtime.get("last_native_work_recovery") or {}
    recovery_questions = [
        question
        for question in recovery_state.get("questions") or []
        if str(question.get("related_task_id")) == str(task_id)
    ]

    recover_result = run(
        [
            "work",
            str(task_id),
            "--recover-session",
            "--allow-read",
            ".",
            "--allow-verify",
            "--verify-command",
            verify_command,
            "--json",
        ],
        timeout=30,
    )
    recover_data = _json_stdout(recover_result)
    recovered_state = read_json_file(state_path, {})
    recovered_session = next(
        (
            candidate
            for candidate in recovered_state.get("work_sessions") or []
            if str(candidate.get("id")) == str(session_id)
        ),
        {},
    )
    source_call = ((recovered_session.get("tool_calls") or [])[:1] or [{}])[0]

    resume_result = run(
        [
            "run",
            "--once",
            "--passive-now",
            "--autonomous",
            "--autonomy-level",
            "act",
            "--allow-native-advance",
            "--poll-interval",
            "0.01",
        ],
        timeout=30,
        scenario_env=scenario_env,
    )
    final_state = read_json_file(state_path, {})
    final_runtime = final_state.get("runtime_status") or {}
    latest_step = final_runtime.get("last_native_work_step") or {}
    fake_calls = read_json_file(fake_log, [])
    fake_work_calls = [
        call for call in fake_calls if (call.get("argv") or [])[:2] == ["work", str(task_id)]
    ]
    latest_fake_args = (fake_work_calls[-1].get("argv") if fake_work_calls else [])

    _scenario_check(
        checks,
        "passive_recovery_loop_asks_for_verifier_recovery",
        task_result.get("exit_code") == 0
        and start_result.get("exit_code") == 0
        and recovery_question_result.get("exit_code") == 0
        and recovery_runtime.get("last_native_work_step_skip") == "previous_native_work_step_failed"
        and recovery.get("recovery_plan_action") == "retry_verification"
        and bool(recovery.get("recovery_plan_command"))
        and bool(recovery_questions),
        observed={
            "last_native_work_step_skip": recovery_runtime.get("last_native_work_step_skip"),
            "last_native_work_recovery": recovery,
            "questions": recovery_questions,
        },
        expected="failed passive native work asks a recovery question with a retry_verification command",
    )
    _scenario_check(
        checks,
        "passive_recovery_loop_recovers_interrupted_verifier",
        recover_result.get("exit_code") == 0
        and (recover_data.get("recovery") or {}).get("status") == "completed"
        and source_call.get("recovery_status") == "superseded"
        and source_call.get("recovered_by_tool_call_id"),
        observed={
            "recovery": recover_data.get("recovery"),
            "source_call": source_call,
        },
        expected="recover-session reruns the interrupted verifier and marks the original call superseded",
    )
    _scenario_check(
        checks,
        "passive_recovery_loop_resumes_native_advance",
        resume_result.get("exit_code") == 0
        and latest_step.get("outcome") == "completed"
        and latest_step.get("exit_code") == 0
        and final_runtime.get("last_native_work_step_skip") != "previous_native_work_step_failed"
        and bool(fake_work_calls)
        and "--live" in latest_fake_args
        and "--max-steps" in latest_fake_args,
        observed={
            "last_native_work_step": latest_step,
            "last_native_work_step_skip": final_runtime.get("last_native_work_step_skip"),
            "fake_calls": fake_calls,
        },
        expected="after manual recovery, the next passive tick advances the runtime-owned work session",
    )
    return _scenario_report("passive-recovery-loop", workspace, commands, checks)


def run_passive_auto_recovery_scenario(workspace, env=None):
    commands = []
    checks = []

    def run(args, timeout=30, scenario_env=None):
        result = run_command(
            _scenario_command(*args),
            workspace,
            timeout=timeout,
            env=scenario_env if scenario_env is not None else env,
        )
        commands.append(result)
        return result

    task_result = run(
        [
            "task",
            "add",
            "Passive auto recovery task",
            "--kind",
            "coding",
            "--ready",
            "--priority",
            "high",
            "--json",
        ],
        timeout=15,
    )
    task_data = _json_stdout(task_result)
    task = task_data.get("task") if isinstance(task_data.get("task"), dict) else task_data
    task_id = task.get("id") if isinstance(task, dict) else None
    verify_command = f"{sys.executable} -V"

    start_result = run(
        [
            "work",
            str(task_id),
            "--start-session",
            "--allow-read",
            ".",
            "--allow-verify",
            "--verify-command",
            verify_command,
            "--json",
        ],
        timeout=15,
    )
    start_data = _json_stdout(start_result)
    session = start_data.get("work_session") or {}
    session_id = session.get("id")

    state_path = Path(workspace) / STATE_FILE
    state = read_json_file(state_path, {})
    state = reconcile_next_ids(migrate_state(state))
    runtime_session = next(
        (
            candidate
            for candidate in state.get("work_sessions") or []
            if str(candidate.get("id")) == str(session_id)
        ),
        None,
    )
    seeded_tool_call_id = None
    if runtime_session:
        before = "2026-04-18T05:00:00Z"
        failed_at = "2026-04-18T05:00:10Z"
        runtime_session["owner"] = "runtime"
        runtime_session["runtime_managed"] = True
        runtime_session["runtime_started_at"] = before
        runtime_session["runtime_started_event_id"] = 999
        seeded_tool_call_id = next_id(state, "work_tool_call")
        runtime_session.setdefault("tool_calls", []).append(
            {
                "id": seeded_tool_call_id,
                "session_id": session_id,
                "task_id": task_id,
                "tool": "run_tests",
                "status": "interrupted",
                "parameters": {
                    "command": verify_command,
                    "cwd": ".",
                    "allow_verify": True,
                    "timeout": 300,
                },
                "result": {"command": verify_command, "cwd": ".", "timed_out": True},
                "summary": "interrupted dogfood verifier",
                "error": "Interrupted before the verifier completed.",
                "started_at": before,
                "finished_at": before,
            }
        )
        runtime_session["last_tool_call_id"] = seeded_tool_call_id
        runtime_session["updated_at"] = before
        runtime_status = state.setdefault("runtime_status", {})
        runtime_status["last_native_work_step"] = {
            "finished_at": failed_at,
            "session_id": session_id,
            "task_id": task_id,
            "command": f"mew work {task_id} --live --allow-read . --max-steps 1",
            "exit_code": 1,
            "timed_out": False,
            "outcome": "failed",
        }
        runtime_status["last_action"] = "seeded failed native work step for auto recovery dogfood"
        write_json_file(state_path, state)

    auto_recover_result = run(
        [
            "run",
            "--once",
            "--passive-now",
            "--autonomous",
            "--autonomy-level",
            "act",
            "--allow-native-advance",
            "--allow-read",
            ".",
            "--allow-verify",
            "--verify-command",
            verify_command,
            "--poll-interval",
            "0.01",
        ],
        timeout=30,
    )
    recovered_state = read_json_file(state_path, {})
    recovered_session = next(
        (
            candidate
            for candidate in recovered_state.get("work_sessions") or []
            if str(candidate.get("id")) == str(session_id)
        ),
        {},
    )
    source_call = next(
        (
            call
            for call in recovered_session.get("tool_calls") or []
            if str(call.get("id")) == str(seeded_tool_call_id)
        ),
        {},
    )
    recovered_call = next(
        (
            call
            for call in recovered_session.get("tool_calls") or []
            if str(call.get("id")) == str(source_call.get("recovered_by_tool_call_id"))
        ),
        {},
    )
    auto_recovery = (recovered_state.get("runtime_status") or {}).get("last_native_work_recovery") or {}
    recovery_questions = [
        question
        for question in recovered_state.get("questions") or []
        if str(question.get("related_task_id")) == str(task_id)
    ]

    fake_log = Path(workspace) / "fake-mew-auto-recovery-calls.json"
    fake_mew = write_fake_mew_executable(Path(workspace) / "fake-mew-auto-recovery")
    scenario_env = dict(env or os.environ)
    scenario_env["MEW_EXECUTABLE"] = str(fake_mew)
    scenario_env["MEW_FAKE_WORK_LOG"] = str(fake_log)
    resume_result = run(
        [
            "run",
            "--once",
            "--passive-now",
            "--autonomous",
            "--autonomy-level",
            "act",
            "--allow-native-advance",
            "--allow-read",
            ".",
            "--poll-interval",
            "0.01",
        ],
        timeout=30,
        scenario_env=scenario_env,
    )
    final_state = read_json_file(state_path, {})
    final_runtime = final_state.get("runtime_status") or {}
    latest_step = final_runtime.get("last_native_work_step") or {}
    fake_calls = read_json_file(fake_log, [])
    fake_work_calls = [
        call for call in fake_calls if (call.get("argv") or [])[:2] == ["work", str(task_id)]
    ]

    _scenario_check(
        checks,
        "passive_auto_recovery_reruns_interrupted_verifier",
        task_result.get("exit_code") == 0
        and start_result.get("exit_code") == 0
        and auto_recover_result.get("exit_code") == 0
        and auto_recovery.get("action") == "auto_retry_verification_completed"
        and source_call.get("recovery_status") == "superseded"
        and recovered_call.get("status") == "completed"
        and (recovered_call.get("result") or {}).get("exit_code") == 0
        and not recovery_questions,
        observed={
            "last_native_work_recovery": auto_recovery,
            "source_call": source_call,
            "recovered_call": recovered_call,
            "questions": recovery_questions,
        },
        expected="passive tick auto-recovers a runtime-owned interrupted verifier when gates match",
    )
    _scenario_check(
        checks,
        "passive_auto_recovery_resumes_native_advance",
        resume_result.get("exit_code") == 0
        and latest_step.get("outcome") == "completed"
        and latest_step.get("exit_code") == 0
        and bool(fake_work_calls),
        observed={
            "last_native_work_step": latest_step,
            "fake_calls": fake_calls,
        },
        expected="after auto recovery, the next passive tick can advance the runtime-owned work session",
    )
    return _scenario_report("passive-auto-recovery", workspace, commands, checks)


def run_passive_auto_recovery_read_scenario(workspace, env=None):
    commands = []
    checks = []

    def run(args, timeout=30, scenario_env=None):
        result = run_command(
            _scenario_command(*args),
            workspace,
            timeout=timeout,
            env=scenario_env if scenario_env is not None else env,
        )
        commands.append(result)
        return result

    target_a = Path(workspace) / "read-target-a.txt"
    target_b = Path(workspace) / "read-target-b.txt"
    target_a.write_text("first safe read recovery dogfood\n", encoding="utf-8")
    target_b.write_text("second safe read recovery dogfood\n", encoding="utf-8")
    task_result = run(
        [
            "task",
            "add",
            "Passive auto read recovery task",
            "--kind",
            "coding",
            "--ready",
            "--priority",
            "high",
            "--json",
        ],
        timeout=15,
    )
    task_data = _json_stdout(task_result)
    task = task_data.get("task") if isinstance(task_data.get("task"), dict) else task_data
    task_id = task.get("id") if isinstance(task, dict) else None

    start_result = run(
        [
            "work",
            str(task_id),
            "--start-session",
            "--allow-read",
            ".",
            "--json",
        ],
        timeout=15,
    )
    start_data = _json_stdout(start_result)
    session = start_data.get("work_session") or {}
    session_id = session.get("id")

    state_path = Path(workspace) / STATE_FILE
    state = read_json_file(state_path, {})
    state = reconcile_next_ids(migrate_state(state))
    runtime_session = next(
        (
            candidate
            for candidate in state.get("work_sessions") or []
            if str(candidate.get("id")) == str(session_id)
        ),
        None,
    )
    seeded_tool_call_ids = []
    if runtime_session:
        before = "2026-04-18T05:00:00Z"
        failed_at = "2026-04-18T05:00:10Z"
        runtime_session["owner"] = "runtime"
        runtime_session["runtime_managed"] = True
        runtime_session["runtime_started_at"] = before
        runtime_session["runtime_started_event_id"] = 999
        seeded_tool_call_ids = [next_id(state, "work_tool_call"), next_id(state, "work_tool_call")]
        runtime_session.setdefault("tool_calls", []).extend(
            [
                {
                    "id": seeded_tool_call_ids[0],
                    "session_id": session_id,
                    "task_id": task_id,
                    "tool": "read_file",
                    "status": "interrupted",
                    "parameters": {
                        "path": "read-target-a.txt",
                        "max_chars": 50000,
                    },
                    "result": None,
                    "summary": "interrupted dogfood read",
                    "error": "Interrupted before the read completed.",
                    "started_at": before,
                    "finished_at": before,
                },
                {
                    "id": seeded_tool_call_ids[1],
                    "session_id": session_id,
                    "task_id": task_id,
                    "tool": "read_file",
                    "status": "interrupted",
                    "parameters": {
                        "path": "read-target-b.txt",
                        "max_chars": 50000,
                    },
                    "result": None,
                    "summary": "interrupted dogfood read",
                    "error": "Interrupted before the read completed.",
                    "started_at": before,
                    "finished_at": before,
                },
            ]
        )
        runtime_session["last_tool_call_id"] = seeded_tool_call_ids[-1]
        runtime_session["updated_at"] = before
        runtime_status = state.setdefault("runtime_status", {})
        runtime_status["last_native_work_step"] = {
            "finished_at": failed_at,
            "session_id": session_id,
            "task_id": task_id,
            "command": f"mew work {task_id} --live --allow-read . --max-steps 1",
            "exit_code": 1,
            "timed_out": False,
            "outcome": "failed",
        }
        runtime_status["last_action"] = "seeded failed native work step for auto read recovery dogfood"
        write_json_file(state_path, state)

    auto_recover_result = run(
        [
            "run",
            "--once",
            "--passive-now",
            "--autonomous",
            "--autonomy-level",
            "act",
            "--allow-native-advance",
            "--allow-read",
            ".",
            "--poll-interval",
            "0.01",
        ],
        timeout=30,
    )
    recovered_state = read_json_file(state_path, {})
    recovered_session = next(
        (
            candidate
            for candidate in recovered_state.get("work_sessions") or []
            if str(candidate.get("id")) == str(session_id)
        ),
        {},
    )
    source_calls = [
        call
        for call in recovered_session.get("tool_calls") or []
        if call.get("id") in set(seeded_tool_call_ids)
    ]
    recovered_call_ids = {
        call.get("recovered_by_tool_call_id")
        for call in source_calls
        if call.get("recovered_by_tool_call_id")
    }
    recovered_calls = [
        call
        for call in recovered_session.get("tool_calls") or []
        if call.get("id") in recovered_call_ids
    ]
    auto_recovery = (recovered_state.get("runtime_status") or {}).get("last_native_work_recovery") or {}
    recovery_questions = [
        question
        for question in recovered_state.get("questions") or []
        if str(question.get("related_task_id")) == str(task_id)
    ]

    fake_log = Path(workspace) / "fake-mew-auto-read-recovery-calls.json"
    fake_mew = write_fake_mew_executable(Path(workspace) / "fake-mew-auto-read-recovery")
    scenario_env = dict(env or os.environ)
    scenario_env["MEW_EXECUTABLE"] = str(fake_mew)
    scenario_env["MEW_FAKE_WORK_LOG"] = str(fake_log)
    resume_result = run(
        [
            "run",
            "--once",
            "--passive-now",
            "--autonomous",
            "--autonomy-level",
            "act",
            "--allow-native-advance",
            "--allow-read",
            ".",
            "--poll-interval",
            "0.01",
        ],
        timeout=30,
        scenario_env=scenario_env,
    )
    final_state = read_json_file(state_path, {})
    final_runtime = final_state.get("runtime_status") or {}
    latest_step = final_runtime.get("last_native_work_step") or {}
    fake_calls = read_json_file(fake_log, [])
    fake_work_calls = [
        call for call in fake_calls if (call.get("argv") or [])[:2] == ["work", str(task_id)]
    ]

    _scenario_check(
        checks,
        "passive_auto_recovery_read_reruns_interrupted_read",
        task_result.get("exit_code") == 0
        and start_result.get("exit_code") == 0
        and auto_recover_result.get("exit_code") == 0
        and auto_recovery.get("action") == "auto_retry_tool_completed"
        and auto_recovery.get("batch") is True
        and auto_recovery.get("count") == 2
        and len(source_calls) == 2
        and all(call.get("recovery_status") == "superseded" for call in source_calls)
        and len(recovered_calls) == 2
        and all(call.get("tool") == "read_file" for call in recovered_calls)
        and all(call.get("status") == "completed" for call in recovered_calls)
        and "first safe read recovery dogfood"
        in "\n".join(((call.get("result") or {}).get("text") or "") for call in recovered_calls)
        and "second safe read recovery dogfood"
        in "\n".join(((call.get("result") or {}).get("text") or "") for call in recovered_calls)
        and not recovery_questions,
        observed={
            "last_native_work_recovery": auto_recovery,
            "source_calls": source_calls,
            "recovered_calls": recovered_calls,
            "questions": recovery_questions,
        },
        expected="passive tick auto-recovers runtime-owned interrupted safe reads when gates match",
    )
    _scenario_check(
        checks,
        "passive_auto_recovery_read_resumes_native_advance",
        resume_result.get("exit_code") == 0
        and latest_step.get("outcome") == "completed"
        and latest_step.get("exit_code") == 0
        and bool(fake_work_calls),
        observed={
            "last_native_work_step": latest_step,
            "fake_calls": fake_calls,
        },
        expected="after auto read recovery, the next passive tick can advance the runtime-owned work session",
    )
    return _scenario_report("passive-auto-recovery-read", workspace, commands, checks)


def run_passive_auto_recovery_write_scenario(workspace, env=None):
    commands = []
    checks = []

    def run(args, timeout=30, scenario_env=None):
        result = run_command(
            _scenario_command(*args),
            workspace,
            timeout=timeout,
            env=scenario_env if scenario_env is not None else env,
        )
        commands.append(result)
        return result

    target = Path(workspace) / "write-target.txt"
    target.write_text("before\n", encoding="utf-8")
    task_result = run(
        [
            "task",
            "add",
            "Passive auto dry-run write recovery task",
            "--kind",
            "coding",
            "--ready",
            "--priority",
            "high",
            "--json",
        ],
        timeout=15,
    )
    task_data = _json_stdout(task_result)
    task = task_data.get("task") if isinstance(task_data.get("task"), dict) else task_data
    task_id = task.get("id") if isinstance(task, dict) else None

    start_result = run(
        [
            "work",
            str(task_id),
            "--start-session",
            "--allow-read",
            ".",
            "--allow-write",
            ".",
            "--json",
        ],
        timeout=15,
    )
    start_data = _json_stdout(start_result)
    session = start_data.get("work_session") or {}
    session_id = session.get("id")

    state_path = Path(workspace) / STATE_FILE
    state = read_json_file(state_path, {})
    state = reconcile_next_ids(migrate_state(state))
    runtime_session = next(
        (
            candidate
            for candidate in state.get("work_sessions") or []
            if str(candidate.get("id")) == str(session_id)
        ),
        None,
    )
    seeded_tool_call_id = None
    if runtime_session:
        before = "2026-04-18T05:00:00Z"
        failed_at = "2026-04-18T05:00:10Z"
        runtime_session["owner"] = "runtime"
        runtime_session["runtime_managed"] = True
        runtime_session["runtime_started_at"] = before
        runtime_session["runtime_started_event_id"] = 999
        seeded_tool_call_id = next_id(state, "work_tool_call")
        runtime_session.setdefault("tool_calls", []).append(
            {
                "id": seeded_tool_call_id,
                "session_id": session_id,
                "task_id": task_id,
                "tool": "edit_file",
                "status": "interrupted",
                "parameters": {
                    "path": "write-target.txt",
                    "old": "before\n",
                    "new": "after\n",
                    "apply": False,
                    "allowed_write_roots": ["."],
                },
                "result": None,
                "summary": "interrupted dogfood dry-run edit",
                "error": "Interrupted before the dry-run diff completed.",
                "started_at": before,
                "finished_at": before,
            }
        )
        runtime_session["last_tool_call_id"] = seeded_tool_call_id
        runtime_session["updated_at"] = before
        runtime_status = state.setdefault("runtime_status", {})
        runtime_status["last_native_work_step"] = {
            "finished_at": failed_at,
            "session_id": session_id,
            "task_id": task_id,
            "command": f"mew work {task_id} --live --allow-read . --allow-write . --max-steps 1",
            "exit_code": 1,
            "timed_out": False,
            "outcome": "failed",
        }
        runtime_status["last_action"] = "seeded failed native work step for auto dry-run write recovery dogfood"
        write_json_file(state_path, state)

    auto_recover_result = run(
        [
            "run",
            "--once",
            "--passive-now",
            "--autonomous",
            "--autonomy-level",
            "act",
            "--allow-native-advance",
            "--allow-read",
            ".",
            "--allow-write",
            ".",
            "--poll-interval",
            "0.01",
        ],
        timeout=30,
    )
    recovered_state = read_json_file(state_path, {})
    recovered_session = next(
        (
            candidate
            for candidate in recovered_state.get("work_sessions") or []
            if str(candidate.get("id")) == str(session_id)
        ),
        {},
    )
    source_call = next(
        (
            call
            for call in recovered_session.get("tool_calls") or []
            if str(call.get("id")) == str(seeded_tool_call_id)
        ),
        {},
    )
    recovered_call = next(
        (
            call
            for call in recovered_session.get("tool_calls") or []
            if str(call.get("id")) == str(source_call.get("recovered_by_tool_call_id"))
        ),
        {},
    )
    recovered_result = recovered_call.get("result") or {}
    auto_recovery = (recovered_state.get("runtime_status") or {}).get("last_native_work_recovery") or {}
    recovery_questions = [
        question
        for question in recovered_state.get("questions") or []
        if str(question.get("related_task_id")) == str(task_id)
    ]

    _scenario_check(
        checks,
        "passive_auto_recovery_write_reruns_interrupted_dry_run_preview",
        task_result.get("exit_code") == 0
        and start_result.get("exit_code") == 0
        and auto_recover_result.get("exit_code") == 0
        and auto_recovery.get("action") == "auto_retry_dry_run_write_completed"
        and source_call.get("recovery_status") == "superseded"
        and recovered_call.get("tool") == "edit_file"
        and recovered_call.get("status") == "completed"
        and recovered_result.get("dry_run") is True
        and recovered_result.get("written") is False
        and target.read_text(encoding="utf-8") == "before\n"
        and not recovery_questions,
        observed={
            "last_native_work_recovery": auto_recovery,
            "source_call": source_call,
            "recovered_call": recovered_call,
            "target_text": target.read_text(encoding="utf-8"),
            "questions": recovery_questions,
        },
        expected="passive tick auto-recovers an interrupted dry-run write preview without changing the file",
    )
    return _scenario_report("passive-auto-recovery-write", workspace, commands, checks)


def run_day_reentry_scenario(workspace, env=None):
    commands = []
    checks = []

    def run(args, timeout=30):
        result = run_command(_scenario_command(*args), workspace, timeout=timeout, env=env)
        commands.append(result)
        return result

    readme = Path(workspace) / "README.md"
    readme.write_text(
        "# Day Reentry Dogfood\n\n"
        "The next step is to reopen this file and verify that aged work context stays visible.\n",
        encoding="utf-8",
    )
    verify_command = f"{sys.executable} -V"
    task_result = run(
        [
            "task",
            "add",
            "Day-scale reentry task",
            "--kind",
            "coding",
            "--ready",
            "--priority",
            "high",
            "--json",
        ],
        timeout=15,
    )
    task_data = _json_stdout(task_result)
    task = task_data.get("task") if isinstance(task_data.get("task"), dict) else task_data
    task_id = task.get("id") if isinstance(task, dict) else None
    start_result = run(
        [
            "work",
            str(task_id),
            "--start-session",
            "--allow-read",
            ".",
            "--allow-verify",
            "--verify-command",
            verify_command,
            "--json",
        ],
        timeout=15,
    )
    start_data = _json_stdout(start_result)
    session = start_data.get("work_session") or {}
    session_id = session.get("id")

    state_path = Path(workspace) / STATE_FILE
    state = reconcile_next_ids(migrate_state(read_json_file(state_path, {})))
    note_at = "2026-04-16T08:32:00Z"
    tool_at = "2026-04-16T08:34:00Z"
    memory_at = "2026-04-16T08:36:00Z"
    for candidate in state.get("work_sessions") or []:
        if str(candidate.get("id")) != str(session_id):
            continue
        candidate["created_at"] = "2026-04-16T08:00:00Z"
        candidate["updated_at"] = memory_at
        candidate["goal"] = "Prove a next-day reentry surface for active work."
        candidate.setdefault("notes", []).append(
            {
                "id": next_id(state, "work_note"),
                "source": "dogfood",
                "text": "Day-scale reentry note: keep the hypothesis, next step, and last touched file visible.",
                "created_at": note_at,
            }
        )
        read_tool_call_id = next_id(state, "work_tool_call")
        candidate.setdefault("tool_calls", []).append(
            {
                "id": read_tool_call_id,
                "session_id": session_id,
                "task_id": task_id,
                "tool": "read_file",
                "status": "completed",
                "parameters": {"path": "README.md"},
                "result": {"path": "README.md", "content": readme.read_text(encoding="utf-8")},
                "summary": "Read README.md to seed day-scale reentry context.",
                "started_at": tool_at,
                "finished_at": tool_at,
            }
        )
        risk_tool_call_id = next_id(state, "work_tool_call")
        candidate.setdefault("tool_calls", []).append(
            {
                "id": risk_tool_call_id,
                "session_id": session_id,
                "task_id": task_id,
                "tool": "run_tests",
                "status": "failed",
                "parameters": {"command": verify_command},
                "result": {"command": verify_command, "exit_code": 1, "stderr": "dogfood verifier failed\n"},
                "error": "day-scale verifier still needs recovery",
                "summary": "Verifier failed before day-scale reentry.",
                "started_at": "2026-04-16T08:35:00Z",
                "finished_at": "2026-04-16T08:35:00Z",
            }
        )
        memory_turn_id = next_id(state, "work_model_turn")
        candidate.setdefault("model_turns", []).append(
            {
                "id": memory_turn_id,
                "session_id": session_id,
                "task_id": task_id,
                "status": "completed",
                "decision_plan": {
                    "summary": "preserve day-scale reentry context",
                    "working_memory": {
                        "hypothesis": "Day-scale reentry is viable if focus preserves age, memory, and controls.",
                        "next_step": "Run the day-reentry dogfood and inspect the README context before changing code.",
                        "open_questions": ["Does focus show how old the active work session is?"],
                        "last_verified_state": "No code changes yet; README evidence was inspected.",
                    },
                },
                "action_plan": {},
                "action": {"type": "finish", "reason": "pause until next-day reentry"},
                "summary": "Captured next-day reentry memory.",
                "started_at": memory_at,
                "finished_at": memory_at,
            }
        )
        break
    write_json_file(state_path, state)

    focus_json_result = run(["focus", "--kind", "coding", "--json"], timeout=15)
    focus_text_result = run(["focus", "--kind", "coding"], timeout=15)
    resume_json_result = run(
        [
            "work",
            str(task_id),
            "--session",
            "--resume",
            "--allow-read",
            ".",
            "--json",
        ],
        timeout=15,
    )
    activity_json_result = run(["activity", "--kind", "coding", "--json"], timeout=15)

    focus_data = _json_stdout(focus_json_result)
    focus_sessions = focus_data.get("active_work_sessions") or []
    focus_session = focus_sessions[0] if focus_sessions else {}
    focus_memory = focus_session.get("working_memory") or {}
    resume_data = _json_stdout(resume_json_result)
    resume = resume_data.get("resume") or {}
    resume_memory = resume.get("working_memory") or {}
    world_state = resume.get("world_state") or {}
    activity_data = _json_stdout(activity_json_result)
    activity_text = json.dumps(activity_data.get("recent_activity") or [], ensure_ascii=False)
    focus_text = focus_text_result.get("stdout") or ""

    _scenario_check(
        checks,
        "day_reentry_focus_surfaces_aged_active_session",
        task_result.get("exit_code") == 0
        and start_result.get("exit_code") == 0
        and focus_json_result.get("exit_code") == 0
        and focus_session.get("id") == session_id
        and focus_session.get("task_id") == task_id
        and (focus_session.get("inactive_hours") or 0) >= 24.0
        and bool(focus_session.get("inactive_for"))
        and "day-scale verifier still needs recovery" in (focus_session.get("risk") or ""),
        observed=focus_session,
        expected="focus --json surfaces the active session with day-scale inactive age and unresolved risk",
    )
    _scenario_check(
        checks,
        "day_reentry_focus_text_is_copy_paste_reentry",
        focus_text_result.get("exit_code") == 0
        and "last_active:" in focus_text
        and "Day-scale reentry is viable" in focus_text
        and "risk: run_tests#" in focus_text
        and "day-scale verifier still needs recovery" in focus_text
        and f" work {task_id} --session --resume --allow-read ." in focus_text
        and f" work {task_id} --follow " in focus_text
        and "--allow-read ." in focus_text
        and "--allow-verify" in focus_text,
        observed=command_result_tail(focus_text_result),
        expected="focus text shows age, risk, working memory, and runnable resume/follow controls",
    )
    _scenario_check(
        checks,
        "day_reentry_resume_restores_memory_and_world_state",
        resume_json_result.get("exit_code") == 0
        and resume.get("session_id") == session_id
        and resume_memory.get("hypothesis") == focus_memory.get("hypothesis")
        and any("Day-scale reentry note" in (note.get("text") or "") for note in resume.get("notes") or [])
        and any(record.get("path") == "README.md" and record.get("exists") for record in world_state.get("files") or []),
        observed={
            "resume": resume,
            "next_cli_controls": resume_data.get("next_cli_controls"),
        },
        expected="work --session --resume restores memory, notes, and live file world state",
    )
    _scenario_check(
        checks,
        "day_reentry_activity_preserves_old_work_events",
        activity_json_result.get("exit_code") == 0
        and "Captured next-day reentry memory." in activity_text
        and "Read README.md to seed day-scale reentry context." in activity_text
        and "Day-scale reentry note" in activity_text,
        observed=activity_data,
        expected="activity --kind coding preserves old turn, tool, and note events for reentry audit",
    )
    return _scenario_report("day-reentry", workspace, commands, checks)


def run_continuity_scenario(workspace, env=None):
    commands = []
    checks = []

    def run(args, timeout=30, input_text=None):
        result = run_command(_scenario_command(*args), workspace, timeout=timeout, env=env, input_text=input_text)
        commands.append(result)
        return result

    readme = Path(workspace) / "README.md"
    readme.write_text(
        "# Continuity Dogfood\n\n"
        "mew should restore the work thread after interruption, failed verification, and pending approval.\n",
        encoding="utf-8",
    )
    verifier_command = f"{sys.executable} -c \"import sys; print('continuity verifier failed'); sys.exit(1)\""
    task_result = run(
        [
            "task",
            "add",
            "Continuity reentry task",
            "--kind",
            "coding",
            "--ready",
            "--priority",
            "high",
            "--json",
        ],
        timeout=15,
    )
    task_data = _json_stdout(task_result)
    task = task_data.get("task") if isinstance(task_data.get("task"), dict) else task_data
    task_id = task.get("id") if isinstance(task, dict) else None
    start_result = run(
        [
            "work",
            str(task_id),
            "--start-session",
            "--allow-read",
            ".",
            "--allow-verify",
            "--verify-command",
            verifier_command,
            "--json",
        ],
        timeout=15,
    )
    read_result = run(
        ["work", str(task_id), "--tool", "read_file", "--path", "README.md", "--allow-read", ".", "--json"],
        timeout=15,
    )
    approval_result = run(
        [
            "work",
            str(task_id),
            "--tool",
            "edit_file",
            "--path",
            "README.md",
            "--old",
            "restore the work thread",
            "--new",
            "restore continuity",
            "--allow-write",
            ".",
            "--json",
        ],
        timeout=15,
    )
    failed_verify_result = run(
        [
            "work",
            str(task_id),
            "--tool",
            "run_tests",
            "--command",
            verifier_command,
            "--allow-verify",
            "--json",
        ],
        timeout=15,
    )
    note_result = run(
        [
            "work",
            str(task_id),
            "--session-note",
            "User pivot: preserve pending approval, failed verifier, and next action for reentry.",
            "--json",
        ],
        timeout=15,
    )
    queue_result = run(
        [
            "work",
            str(task_id),
            "--queue-followup",
            "After the pivot, inspect the failed verifier before approving README.md.",
            "--json",
        ],
        timeout=15,
    )

    state_path = Path(workspace) / STATE_FILE
    state = reconcile_next_ids(migrate_state(read_json_file(state_path, {})))
    start_data = _json_stdout(start_result)
    session_id = (start_data.get("work_session") or {}).get("id")
    for candidate in state.get("work_sessions") or []:
        if str(candidate.get("id")) != str(session_id):
            continue
        timestamp = now_iso()
        turn_id = next_id(state, "work_model_turn")
        candidate.setdefault("model_turns", []).append(
            {
                "id": turn_id,
                "session_id": session_id,
                "task_id": task_id,
                "status": "completed",
                "decision_plan": {
                    "summary": "preserve continuity after interruption",
                    "working_memory": {
                        "hypothesis": "Continuity is viable when memory, risks, approvals, and next action survive interruption.",
                        "next_step": "Inspect the failed verifier, then decide whether to approve the README dry-run edit.",
                        "open_questions": ["Is the pending README approval still visible after reentry?"],
                        "last_verified_state": "The explicit continuity verifier failed and must be reviewed.",
                    },
                },
                "action_plan": {},
                "action": {"type": "finish", "reason": "pause for continuity reentry"},
                "summary": "Captured continuity working memory.",
                "started_at": timestamp,
                "finished_at": timestamp,
            }
        )
        candidate["updated_at"] = timestamp
        break
    write_json_file(state_path, state)

    resume_json_result = run(
        ["work", str(task_id), "--session", "--resume", "--allow-read", ".", "--json"],
        timeout=15,
    )
    resume_text_result = run(
        ["work", str(task_id), "--session", "--resume", "--allow-read", "."],
        timeout=15,
    )
    focus_text_result = run(["focus", "--kind", "coding"], timeout=15)
    follow_snapshot_result = run(
        [
            "work",
            str(task_id),
            "--follow",
            "--max-steps",
            "0",
            "--allow-read",
            ".",
            "--quiet",
            "--json",
        ],
        timeout=15,
    )
    follow_status_result = run(["work", str(task_id), "--follow-status", "--json"], timeout=15)

    resume_data = _json_stdout(resume_json_result)
    failed_verify_data = _json_stdout(failed_verify_result)
    resume = resume_data.get("resume") or {}
    continuity = resume.get("continuity") or {}
    axes = {axis.get("key"): axis for axis in continuity.get("axes") or []}
    pending_approvals = resume.get("pending_approvals") or []
    focus_text = focus_text_result.get("stdout") or ""
    resume_text = resume_text_result.get("stdout") or ""
    follow_snapshot_file_data = read_json_file(
        Path(workspace) / STATE_DIR / "follow" / f"session-{session_id}.json",
        {},
    )
    follow_status_data = _json_stdout(follow_status_result)

    state = reconcile_next_ids(migrate_state(read_json_file(state_path, {})))
    weak_task_id = next_id(state, "task")
    weak_session_id = next_id(state, "work_session")
    state.setdefault("tasks", []).append(
        {
            "id": weak_task_id,
            "title": "Weak continuity first-look task",
            "kind": "coding",
            "status": "ready",
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }
    )
    state.setdefault("work_sessions", []).append(
        {
            "id": weak_session_id,
            "task_id": weak_task_id,
            "status": "active",
            "title": "Weak continuity first-look task",
            "goal": "Continue work after a large context window",
            "created_at": now_iso(),
            "updated_at": now_iso(),
            "tool_calls": [
                {
                    "id": next_id(state, "work_tool_call"),
                    "session_id": weak_session_id,
                    "task_id": weak_task_id,
                    "tool": "read_file",
                    "status": "completed",
                    "summary": "x" * 210_000,
                    "result": {"path": "README.md"},
                    "started_at": now_iso(),
                    "finished_at": now_iso(),
                }
            ],
            "model_turns": [],
        }
    )
    write_json_file(state_path, state)
    morning_feed = Path(workspace) / "morning-feed.json"
    morning_feed.write_text(json.dumps({"items": []}), encoding="utf-8")
    morning_risk_result = run(
        ["morning-paper", str(morning_feed), "--date", "2026-04-17", "--write", "--json"],
        timeout=15,
    )
    bundle_risk_result = run(["bundle", "--date", "2026-04-17", "--json"], timeout=15)
    morning_risk_data = _json_stdout(morning_risk_result)
    bundle_text = (Path(workspace) / STATE_DIR / "passive-bundle" / "2026-04-17.md").read_text(
        encoding="utf-8"
    )

    _scenario_check(
        checks,
        "continuity_resume_scores_reentry_artifacts",
        task_result.get("exit_code") == 0
        and start_result.get("exit_code") == 0
        and read_result.get("exit_code") == 0
        and approval_result.get("exit_code") == 0
        and (failed_verify_data.get("tool_call") or {}).get("status") == "failed"
        and note_result.get("exit_code") == 0
        and queue_result.get("exit_code") == 0
        and resume_json_result.get("exit_code") == 0
        and continuity.get("score") == "9/9"
        and continuity.get("status") == "strong"
        and axes.get("working_memory_survived", {}).get("ok") is True
        and axes.get("risks_preserved", {}).get("ok") is True
        and axes.get("approvals_visible", {}).get("ok") is True
        and axes.get("verifier_confidence_kept", {}).get("ok") is True
        and axes.get("user_pivot_preserved", {}).get("ok") is True,
        observed={
            "continuity": continuity,
            "pending_approvals": pending_approvals,
            "unresolved_failure": resume.get("unresolved_failure"),
            "working_memory": resume.get("working_memory"),
        },
        expected="resume continuity score preserves memory, risk, approval, and verifier artifacts",
    )
    _scenario_check(
        checks,
        "continuity_text_surfaces_score_and_controls",
        resume_text_result.get("exit_code") == 0
        and "continuity: 9/9 status=strong" in resume_text
        and "Pending approvals" in resume_text
        and "continuity verifier failed" in resume_text
        and "Working memory" in resume_text
        and "Next action" in resume_text,
        observed=command_result_tail(resume_text_result),
        expected="text resume exposes continuity score with approval, failed verifier, memory, and next action",
    )
    _scenario_check(
        checks,
        "continuity_focus_surfaces_score",
        focus_text_result.get("exit_code") == 0
        and "continuity: 9/9 status=strong" in focus_text
        and "Continuity is viable" in focus_text
        and "queued_followup" in focus_text
        and "After the pivot, inspect the failed verifier" in focus_text
        and "risk: run_tests#" in focus_text,
        observed=command_result_tail(focus_text_result),
        expected="focus preserves continuity score and reentry cues after user pivot",
    )
    _scenario_check(
        checks,
        "continuity_follow_snapshot_and_status_surface_score",
        follow_snapshot_result.get("exit_code") == 0
        and follow_status_result.get("exit_code") == 0
        and (follow_snapshot_file_data.get("resume") or {}).get("continuity", {}).get("score") == "9/9"
        and follow_snapshot_file_data.get("continuity", {}).get("score") == "9/9"
        and follow_status_data.get("continuity", {}).get("score") == "9/9",
        observed={
            "snapshot_continuity": follow_snapshot_file_data.get("continuity"),
            "status_continuity": follow_status_data.get("continuity"),
            "follow_status": follow_status_data.get("status"),
        },
        expected="observer snapshot and follow-status expose the same continuity score",
    )
    _scenario_check(
        checks,
        "continuity_morning_paper_and_bundle_surface_weak_reentry",
        morning_risk_result.get("exit_code") == 0
        and bundle_risk_result.get("exit_code") == 0
        and any(
            str(risk.get("session_id")) == str(weak_session_id) and risk.get("status") == "weak"
            for risk in (morning_risk_data.get("continuity_risks") or [])
        )
        and f"Morning Paper: work session #{weak_session_id} task #{weak_task_id}: weak 6/9" in bundle_text,
        observed={
            "morning_risks": morning_risk_data.get("continuity_risks"),
            "bundle_tail": bundle_text[-1000:],
        },
        expected="morning-paper JSON and passive bundle reentry hints surface weak active-work continuity",
    )
    return _scenario_report("continuity", workspace, commands, checks)


def run_m3_reentry_gate_scenario(workspace, env=None):
    commands = []
    checks = []

    def run(args, timeout=30, input_text=None):
        result = run_command(_scenario_command(*args), workspace, timeout=timeout, env=env, input_text=input_text)
        commands.append(result)
        return result

    readme = Path(workspace) / "README.md"
    readme.write_text(
        "# M3 Reentry Gate Dogfood\n\n"
        "M3 gate pending: the interrupted resident has not applied the recovery edit yet.\n",
        encoding="utf-8",
    )
    verify_command = (
        f"{sys.executable} -c \"from pathlib import Path; "
        "raise SystemExit(0 if 'M3 gate complete' in Path('README.md').read_text() else 7)\""
    )
    task_result = run(
        [
            "task",
            "add",
            "M3 reentry gate coding task",
            "--kind",
            "coding",
            "--ready",
            "--priority",
            "high",
            "--json",
        ],
        timeout=15,
    )
    task_data = _json_stdout(task_result)
    task = task_data.get("task") if isinstance(task_data.get("task"), dict) else task_data
    task_id = task.get("id") if isinstance(task, dict) else None
    start_result = run(
        [
            "work",
            str(task_id),
            "--start-session",
            "--allow-read",
            ".",
            "--allow-write",
            ".",
            "--allow-verify",
            "--verify-command",
            verify_command,
            "--json",
        ],
        timeout=15,
    )
    read_result = run(
        ["work", str(task_id), "--tool", "read_file", "--path", "README.md", "--allow-read", ".", "--json"],
        timeout=15,
    )
    edit_result = run(
        [
            "work",
            str(task_id),
            "--tool",
            "edit_file",
            "--path",
            "README.md",
            "--old",
            "M3 gate pending",
            "--new",
            "M3 gate complete",
            "--allow-write",
            ".",
            "--json",
        ],
        timeout=15,
    )
    edit_data = _json_stdout(edit_result)
    edit_tool_id = (edit_data.get("tool_call") or {}).get("id")
    failed_verify_result = run(
        [
            "work",
            str(task_id),
            "--tool",
            "run_tests",
            "--command",
            verify_command,
            "--allow-verify",
            "--json",
        ],
        timeout=15,
    )
    note_result = run(
        [
            "work",
            str(task_id),
            "--session-note",
            "Context compression boundary: resume must explain the pending README edit, failed verifier, and next verification step.",
            "--json",
        ],
        timeout=15,
    )
    queue_result = run(
        [
            "work",
            str(task_id),
            "--queue-followup",
            "After reentry, approve the README edit with deferred verification, then run the verifier.",
            "--json",
        ],
        timeout=15,
    )

    state_path = Path(workspace) / STATE_FILE
    state = reconcile_next_ids(migrate_state(read_json_file(state_path, {})))
    start_data = _json_stdout(start_result)
    session_id = (start_data.get("work_session") or {}).get("id")
    for candidate in state.get("work_sessions") or []:
        if str(candidate.get("id")) != str(session_id):
            continue
        timestamp = now_iso()
        turn_id = next_id(state, "work_model_turn")
        candidate.setdefault("model_turns", []).append(
            {
                "id": turn_id,
                "session_id": session_id,
                "task_id": task_id,
                "status": "completed",
                "decision_plan": {
                    "summary": "preserve reentry gate after context compression",
                    "working_memory": {
                        "hypothesis": "Mew is worth staying inside when an interrupted coding task resumes with change, risk, and next action intact.",
                        "next_step": (
                            "Approve the README.md dry-run edit with deferred verification, "
                            "then run the verifier command."
                        ),
                        "open_questions": ["Does the resume brief make the failed verifier and pending edit obvious?"],
                        "last_verified_state": "The verifier failed before the pending README.md edit was applied.",
                    },
                },
                "action_plan": {},
                "action": {"type": "finish", "reason": "pause for M3 reentry gate"},
                "summary": "Captured M3 reentry gate working memory.",
                "started_at": timestamp,
                "finished_at": timestamp,
            }
        )
        candidate["updated_at"] = timestamp
        break
    write_json_file(state_path, state)

    resume_json_result = run(
        ["work", str(task_id), "--session", "--resume", "--allow-read", ".", "--json"],
        timeout=15,
    )
    resume_text_result = run(
        ["work", str(task_id), "--session", "--resume", "--allow-read", "."],
        timeout=15,
    )
    follow_snapshot_result = run(
        [
            "work",
            str(task_id),
            "--follow",
            "--max-steps",
            "0",
            "--allow-read",
            ".",
            "--quiet",
            "--json",
        ],
        timeout=15,
    )
    approve_result = run(
        [
            "work",
            str(task_id),
            "--approve-tool",
            str(edit_tool_id),
            "--allow-write",
            ".",
            "--defer-verify",
            "--json",
        ],
        timeout=15,
    )
    post_verify_result = run(
        [
            "work",
            str(task_id),
            "--tool",
            "run_tests",
            "--command",
            verify_command,
            "--allow-verify",
            "--json",
        ],
        timeout=15,
    )
    post_resume_json_result = run(
        ["work", str(task_id), "--session", "--resume", "--allow-read", ".", "--json"],
        timeout=15,
    )

    resume_data = _json_stdout(resume_json_result)
    resume = resume_data.get("resume") or {}
    resume_text = resume_text_result.get("stdout") or ""
    continuity = resume.get("continuity") or {}
    pending_approvals = resume.get("pending_approvals") or []
    unresolved_failure = resume.get("unresolved_failure") or {}
    world_state = resume.get("world_state") or {}
    failed_verify_data = _json_stdout(failed_verify_result)
    follow_snapshot_file_data = read_json_file(
        Path(workspace) / STATE_DIR / "follow" / f"session-{session_id}.json",
        {},
    )
    follow_snapshot_resume = follow_snapshot_file_data.get("resume") or {}
    follow_snapshot_continuity = follow_snapshot_file_data.get("continuity") or (
        follow_snapshot_resume.get("continuity") or {}
    )
    approve_data = _json_stdout(approve_result)
    post_verify_data = _json_stdout(post_verify_result)
    post_resume_data = _json_stdout(post_resume_json_result)
    post_resume = post_resume_data.get("resume") or {}
    post_commands = post_resume.get("commands") or []

    _scenario_check(
        checks,
        "m3_reentry_gate_resume_brief_has_change_risk_next_action",
        task_result.get("exit_code") == 0
        and start_result.get("exit_code") == 0
        and read_result.get("exit_code") == 0
        and edit_result.get("exit_code") == 0
        and (failed_verify_data.get("tool_call") or {}).get("status") == "failed"
        and note_result.get("exit_code") == 0
        and queue_result.get("exit_code") == 0
        and resume_json_result.get("exit_code") == 0
        and resume_text_result.get("exit_code") == 0
        and bool(pending_approvals)
        and pending_approvals[0].get("tool_call_id") == edit_tool_id
        and "M3 gate complete" in (pending_approvals[0].get("diff_preview") or "")
        and unresolved_failure.get("tool") == "run_tests"
        and unresolved_failure.get("exit_code") == 7
        and "Approve the README.md dry-run edit" in ((resume.get("working_memory") or {}).get("next_step") or "")
        and "Next action" in resume_text
        and "Pending approvals" in resume_text
        and "Failures" in resume_text
        and len(resume_text) < 20_000,
        observed={
            "continuity": continuity,
            "pending_approvals": pending_approvals,
            "unresolved_failure": unresolved_failure,
            "resume_chars": len(resume_text),
            "working_memory": resume.get("working_memory"),
        },
        expected="resume gives a concise reentry brief with pending change, failed verifier risk, and next action",
    )
    _scenario_check(
        checks,
        "m3_reentry_gate_world_state_and_follow_snapshot_preserve_resume",
        follow_snapshot_result.get("exit_code") == 0
        and any(str(record.get("path") or "").endswith("README.md") and record.get("exists") for record in world_state.get("files") or [])
        and follow_snapshot_resume.get("session_id") == session_id
        and follow_snapshot_continuity.get("status") in {"strong", "usable"},
        observed={
            "world_state": world_state,
            "snapshot_resume": follow_snapshot_resume,
            "snapshot_continuity": follow_snapshot_continuity,
        },
        expected="live world state and observer snapshot keep the same reentry bundle available",
    )
    _scenario_check(
        checks,
        "m3_reentry_gate_can_advance_to_verification_after_reentry",
        approve_result.get("exit_code") == 0
        and (approve_data.get("tool_call") or {}).get("status") == "completed"
        and ((approve_data.get("tool_call") or {}).get("result") or {}).get("applied") is True
        and ((approve_data.get("tool_call") or {}).get("result") or {}).get("written") is True
        and post_verify_result.get("exit_code") == 0
        and (post_verify_data.get("tool_call") or {}).get("status") == "completed"
        and ((post_verify_data.get("tool_call") or {}).get("result") or {}).get("exit_code") == 0
        and "M3 gate complete" in readme.read_text(encoding="utf-8")
        and any(command.get("exit_code") == 0 and command.get("command") == verify_command for command in post_commands),
        observed={
            "approve": approve_data.get("tool_call"),
            "post_verify": post_verify_data.get("tool_call"),
            "post_resume_commands": post_commands,
            "readme": readme.read_text(encoding="utf-8"),
        },
        expected="after resume, the resident can apply the known change and run verification successfully",
    )
    return _scenario_report("m3-reentry-gate", workspace, commands, checks)


def run_chat_cockpit_scenario(workspace, env=None):
    commands = []
    checks = []

    def run(args, timeout=30, input_text=None):
        result = run_command(_scenario_command(*args), workspace, timeout=timeout, env=env, input_text=input_text)
        commands.append(result)
        return result

    research_result = run(["task", "add", "Research default task", "--kind", "research"])
    coding_result = run(["task", "add", "Implement scoped chat cockpit", "--kind", "coding"])
    coding_session_result = run(["work", "2", "--start-session", "--allow-read", "coding-root"])
    research_session_result = run(["work", "1", "--start-session", "--allow-read", "research-root"])
    chat_result = run(
        ["chat", "--kind", "coding", "--no-brief", "--no-unread", "--timeout", "5"],
        timeout=15,
        input_text="/scope\n/tasks\n/work\n/work-session\n/work-mode on\n/work-mode off\n/exit\n",
    )
    chat_output = chat_result.get("stdout") or ""
    chat_log_result = run(["chat-log", "--limit", "20"])
    chat_log_output = chat_log_result.get("stdout") or ""
    code_task_result = run(["task", "add", "Code entrypoint task", "--kind", "coding"])
    code_seed_result = run(
        [
            "work",
            "3",
            "--start-session",
            "--allow-read",
            ".",
            "--allow-write",
            ".",
            "--allow-shell",
            "--allow-verify",
            "--verify-command",
            "python -m pytest -q",
        ]
    )
    code_close_result = run(["work", "3", "--close-session"])
    code_result = run(
        ["code", "3", "--timeout", "0", "--read-only", "--no-verify"],
        timeout=15,
    )
    code_quiet_result = run(
        ["code", "3", "--quiet", "--timeout", "0", "--read-only", "--no-verify"],
        timeout=15,
    )
    code_output = code_result.get("stdout") or ""
    code_controls = code_output.split("Next controls", 1)[1] if "Next controls" in code_output else code_output
    code_primary_controls = code_controls.split("Inspect", 1)[0]

    _scenario_check(
        checks,
        "chat_kind_scope_starts_active",
        chat_result.get("exit_code") == 0
        and "scope: coding" in chat_output
        and "--allow-read coding-root" in chat_output
        and "--allow-read research-root" not in chat_output,
        observed=command_result_tail(chat_result),
        expected="chat --kind coding starts with coding scope and scoped work controls visible",
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
        research_result.get("exit_code") == 0
        and coding_result.get("exit_code") == 0
        and coding_session_result.get("exit_code") == 0
        and research_session_result.get("exit_code") == 0,
        observed=[
            command_result_tail(research_result),
            command_result_tail(coding_result),
            command_result_tail(coding_session_result),
            command_result_tail(research_session_result),
        ],
        expected="scenario task and active-session seeds succeed",
    )
    _scenario_check(
        checks,
        "chat_work_session_respects_kind_scope",
        chat_result.get("exit_code") == 0
        and "Work session #1 [active] task=#2" in chat_output
        and "Research default task" not in chat_output,
        observed=command_result_tail(chat_result),
        expected="/work-session uses the scoped coding active session even when a research session is newer",
    )
    _scenario_check(
        checks,
        "chat_work_controls_include_follow",
        chat_result.get("exit_code") == 0 and "/follow " in chat_output and "--allow-read coding-root" in chat_output,
        observed=command_result_tail(chat_result),
        expected="chat work controls include a bounded follow loop for the scoped active session",
    )
    _scenario_check(
        checks,
        "chat_work_mode_toggles",
        chat_result.get("exit_code") == 0
        and "work-mode: on; text becomes /continue guidance; blank line repeats after one work step" in chat_output
        and "work-mode: off; text is sent as user messages" in chat_output,
        observed=command_result_tail(chat_result),
        expected="/work-mode toggles the chat cockpit text routing",
    )
    _scenario_check(
        checks,
        "chat_transcript_records_inputs",
        chat_log_result.get("exit_code") == 0
        and "slash kind=coding: /work-session" in chat_log_output
        and "slash kind=coding: /exit" in chat_log_output,
        observed=command_result_tail(chat_log_result),
        expected="chat-log records recent scoped slash inputs outside the runtime activity log",
    )
    _scenario_check(
        checks,
        "code_entrypoint_starts_work_mode_chat",
        code_task_result.get("exit_code") == 0
        and code_seed_result.get("exit_code") == 0
        and code_close_result.get("exit_code") == 0
        and code_result.get("exit_code") == 0
        and "mew chat. Type /help" in code_output
        and "scope: coding" in code_output
        and "work-mode: on" in code_output
        and "Mew code (coding):" in code_output
        and "Current: coding cockpit is open for task #3" in code_output
        and "Next: enter coding cockpit for task #3" not in code_output,
        observed=command_result_tail(code_result),
        expected="mew code <task-id> starts/reuses a coding work session and enters work-mode chat",
    )
    _scenario_check(
        checks,
        "code_read_only_clears_side_effect_defaults",
        code_result.get("exit_code") == 0
        and "--allow-write" not in code_controls
        and "--allow-shell" not in code_controls
        and "--allow-verify" not in code_controls,
        observed=command_result_tail(code_result),
        expected="mew code --read-only --no-verify does not inherit stale write/shell/verify controls",
    )
    _scenario_check(
        checks,
        "code_startup_controls_stay_short",
        code_result.get("exit_code") == 0
        and "- /c" in code_primary_controls
        and "- /follow" in code_primary_controls
        and "- /continue <guidance>" in code_primary_controls
        and "--auth" not in code_primary_controls
        and "--model-backend" not in code_primary_controls
        and "--allow-read" not in code_primary_controls
        and "--act-mode" not in code_primary_controls
        and "/work-session resume --allow-read ." in code_controls
        and "/work-session details" in code_controls,
        observed=command_result_tail(code_result),
        expected="mew code startup keeps primary controls short while resume preserves read gates",
    )
    _scenario_check(
        checks,
        "code_quiet_startup_is_silent",
        code_quiet_result.get("exit_code") == 0
        and not (code_quiet_result.get("stdout") or "")
        and not (code_quiet_result.get("stderr") or ""),
        observed=command_result_tail(code_quiet_result),
        expected="mew code --quiet suppresses startup output while still entering the cockpit",
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
    (workspace / "src" / "mew").mkdir(exist_ok=True)
    (workspace / "tests").mkdir(exist_ok=True)
    (workspace / "src" / "sample.py").write_text(
        "print('native hands')\nprint('line two')\nprint('line three')\n",
        encoding="utf-8",
    )
    (workspace / "src" / "mew" / "pairing.py").write_text("PAIRING = 'old'\n", encoding="utf-8")
    (workspace / "src" / "mew" / "cli.py").write_text(
        "def build_parser():\n"
        "    return 'old parser'\n\n"
        "def main():\n"
        "    return 0\n",
        encoding="utf-8",
    )
    (workspace / "src" / "mew" / "dogfood_override.py").write_text("OVERRIDE = 'old'\n", encoding="utf-8")
    (workspace / "tests" / "test_pairing.py").write_text(
        "import unittest\n\n"
        "class PairingTests(unittest.TestCase):\n"
        "    def test_placeholder(self):\n"
        "        self.assertTrue(True)\n",
        encoding="utf-8",
    )
    (workspace / "tests" / "test_dogfood.py").write_text(
        "from mew.cli import build_parser\n\n"
        "def test_cli_dogfood_parser():\n"
        "    assert build_parser() == 'old parser'\n",
        encoding="utf-8",
    )
    (workspace / "large.py").write_text("x" * 120000 + "\nold_call()\n", encoding="utf-8")
    (workspace / "large_no_newline.py").write_text("x" * 120000 + " old_call()", encoding="utf-8")

    task_add_json_result = run(["task", "add", "Native work task", "--kind", "coding", "--json"])
    task_show_json_result = run(["task", "show", "1", "--json"])
    task_list_json_result = run(["task", "list", "--kind", "coding", "--json"])
    task_update_json_result = run(["task", "update", "1", "--priority", "high", "--json"])
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
    command_result = run(
        [
            "work",
            "1",
            "--tool",
            "run_command",
            "--command",
            f"{sys.executable} -c \"print('work command ok')\"",
            "--allow-shell",
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
    large_no_newline_edit_result = run(
        [
            "work",
            "1",
            "--tool",
            "edit_file",
            "--path",
            "large_no_newline.py",
            "--old",
            "old_call()",
            "--new",
            "new_call()",
            "--allow-write",
            ".",
            "--json",
        ]
    )
    source_edit_result = run(
        [
            "work",
            "1",
            "--tool",
            "edit_file",
            "--path",
            "src/mew/pairing.py",
            "--old",
            "old",
            "--new",
            "new",
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
    steer_result = run(["work", "1", "--steer", "dogfood steer", "--json"])
    queue_followup_result = run(["work", "1", "--queue-followup", "dogfood queued follow-up", "--json"])
    chat_steer_result = run(
        ["chat", "--no-brief", "--no-unread", "--timeout", "5"],
        timeout=15,
        input_text="/work-session steer dogfood chat steer\n",
    )
    chat_queue_result = run(
        ["chat", "--no-brief", "--no-unread", "--timeout", "5"],
        timeout=15,
        input_text="/work-session queue dogfood chat follow-up\n",
    )
    state_path = workspace / STATE_FILE
    state = migrate_state(read_json_file(state_path, default_state()))
    reconcile_next_ids(state)
    memory_session = None
    for candidate in state.get("work_sessions", []):
        if str(candidate.get("task_id")) == "1":
            memory_session = candidate
            break
    if memory_session:
        turn_id = next_id(state, "work_model_turn")
        timestamp = now_iso()
        state.setdefault("memory", {}).setdefault("deep", {}).setdefault("preferences", []).append(
            "Prefer compact dogfood reentry."
        )
        FileMemoryBackend(workspace).write(
            "User prefers typed active dogfood recall during native work.",
            scope="private",
            memory_type="user",
            name="Dogfood active recall preference",
            description="Typed user memory should enter resident startup context.",
            created_at="2026-04-19T00:00:00Z",
        )
        FileMemoryBackend(workspace).write(
            "Native hands work should surface active typed memory recall.",
            scope="private",
            memory_type="project",
            name="Dogfood active recall project note",
            description="Native work resume should include relevant project memory.",
            created_at="2026-04-19T00:00:01Z",
        )
        memory_session.setdefault("model_turns", []).append(
            {
                "id": turn_id,
                "session_id": memory_session.get("id"),
                "task_id": 1,
                "status": "completed",
                "decision_plan": {
                    "summary": "dogfood reentry contract",
                    "working_memory": {
                        "hypothesis": "Dogfood work session has readable reentry state.",
                        "next_step": "Inspect resume before continuing.",
                        "open_questions": ["Does resume show this compact memory?"],
                        "last_verified_state": "dogfood verification passed",
                    },
                },
                "action_plan": {"summary": "dogfood reentry contract"},
                "action": {"type": "finish", "reason": "record memory for resume dogfood"},
                "summary": "dogfood reentry contract",
                "guidance": "",
                "tool_call_id": None,
                "tool_call_ids": [],
                "started_at": timestamp,
                "finished_at": timestamp,
            }
        )
        memory_session["updated_at"] = timestamp
        write_json_file(state_path, state)

    resume_result = run(["work", "1", "--session", "--resume", "--json"])
    work_result = run(["work", "1", "--json"])
    verification_ledger_result = run(["verification", "--json"])
    writes_ledger_result = run(["writes", "--json"])
    timeline_result = run(["work", "1", "--session", "--timeline", "--json"])
    cells_result = run(["work", "1", "--cells", "--json"])
    metrics_result = run_command(_scenario_command("metrics", "--kind", "coding"), workspace, timeout=30, env=env)
    chat_result = run(
        ["chat", "--no-brief", "--no-unread", "--timeout", "5"],
        timeout=15,
        input_text="/work-session details\n",
    )
    chat_diffs_result = run(
        ["chat", "--no-brief", "--no-unread", "--timeout", "5"],
        timeout=15,
        input_text="/work-session diffs\n",
    )
    chat_tests_result = run(
        ["chat", "--no-brief", "--no-unread", "--timeout", "5"],
        timeout=15,
        input_text="/work-session tests\n",
    )
    chat_commands_result = run(
        ["chat", "--no-brief", "--no-unread", "--timeout", "5"],
        timeout=15,
        input_text="/work-session commands\n",
    )
    chat_cells_result = run(
        ["chat", "--no-brief", "--no-unread", "--timeout", "5"],
        timeout=15,
        input_text="/work-session cells\n",
    )
    chat_world_result = run(
        ["chat", "--no-brief", "--no-unread", "--timeout", "5"],
        timeout=15,
        input_text="/work-session resume --allow-read .\n",
    )
    run(["task", "add", "Interrupted side-effect task", "--kind", "coding"])
    run(["work", "2", "--start-session", "--json"])

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
            "tool": "run_command",
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
    run(["task", "add", "Approve all batch task", "--kind", "coding"])
    run(["work", "4", "--start-session", "--json"])
    approve_all_first_result = run(
        [
            "work",
            "4",
            "--tool",
            "write_file",
            "--path",
            "batch-one.md",
            "--content",
            "batch one\n",
            "--create",
            "--allow-write",
            ".",
            "--json",
        ]
    )
    approve_all_second_result = run(
        [
            "work",
            "4",
            "--tool",
            "write_file",
            "--path",
            "batch-two.md",
            "--content",
            "batch two\n",
            "--create",
            "--allow-write",
            ".",
            "--json",
        ]
    )
    approve_all_result = run(
        [
            "work",
            "4",
            "--approve-all",
            "--allow-write",
            ".",
            "--allow-verify",
            "--verify-command",
            (
                f"{sys.executable} -c \"from pathlib import Path; "
                "assert Path('batch-one.md').read_text() == 'batch one\\n'; "
                "assert Path('batch-two.md').read_text() == 'batch two\\n'\""
            ),
            "--json",
        ]
    )
    run(["task", "add", "Reply file task", "--kind", "coding"])
    reply_start_result = run(["work", "5", "--start-session", "--json"])
    reply_start_data = _json_stdout(reply_start_result)
    reply_session = reply_start_data.get("work_session") or {}
    reply_schema_result = run(["work", "5", "--reply-schema", "--json"])
    reply_schema_data = _json_stdout(reply_schema_result)
    reply_path = workspace / "follow-reply.json"
    reply_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "session_id": reply_session.get("id"),
                "task_id": 5,
                "observed_session_updated_at": reply_session.get("updated_at"),
                "actions": [
                    {"type": "steer", "text": "dogfood observer steer"},
                    {"type": "followup", "text": "dogfood observer follow-up"},
                    {"type": "note", "text": "dogfood observer note"},
                ],
            }
        ),
        encoding="utf-8",
    )
    reply_file_result = run(["work", "--reply-file", str(reply_path), "--json"])
    reply_snapshot_data = read_json_file(workspace / STATE_DIR / "follow" / "latest.json", {})

    run(["task", "add", "Interrupt submit task", "--kind", "coding"])
    interrupt_start_result = run(["work", "6", "--start-session", "--json"])
    interrupt_submit_result = run(["work", "6", "--interrupt-submit", "dogfood interrupt submit", "--json"])
    interrupt_resume_result = run(["work", "6", "--session", "--resume", "--json"])
    run(["task", "add", "Reply approve task", "--kind", "coding"])
    reply_approve_start_result = run(
        [
            "work",
            "7",
            "--start-session",
            "--allow-write",
            ".",
            "--allow-verify",
            "--verify-command",
            "true",
            "--json",
        ]
    )
    reply_approve_write_result = run(
        [
            "work",
            "7",
            "--tool",
            "write_file",
            "--path",
            "reply-approved.md",
            "--content",
            "reply approved\n",
            "--create",
            "--allow-write",
            ".",
            "--json",
        ]
    )
    reply_approve_write_data_for_reply = _json_stdout(reply_approve_write_result)
    reply_approve_tool_id = (reply_approve_write_data_for_reply.get("tool_call") or {}).get("id")
    reply_approve_snapshot_result = run(
        [
            "work",
            "7",
            "--follow",
            "--max-steps",
            "0",
            "--quiet",
            "--allow-read",
            ".",
        ]
    )
    reply_approve_snapshot_data = read_json_file(workspace / STATE_DIR / "follow" / "latest.json", {})
    reply_approve_status_result = run(["work", "7", "--follow-status", "--json"])
    reply_approve_session_result = run(["work", "7", "--session", "--json"])
    reply_approve_session = (_json_stdout(reply_approve_session_result).get("work_session") or {})
    reply_approve_path = workspace / "follow-approve-reply.json"
    reply_approve_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "session_id": reply_approve_session.get("id"),
                "task_id": 7,
                "observed_session_updated_at": reply_approve_session.get("updated_at"),
                "actions": [
                    {
                        "type": "approve",
                        "tool_call_id": reply_approve_tool_id,
                        "allow_write": ".",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    reply_approve_result = run(["work", "--reply-file", str(reply_approve_path), "--json"])
    task_done_json_seed_result = run(["task", "add", "Done JSON dogfood task", "--kind", "admin", "--json"])
    task_done_json_result = run(["task", "done", "8", "--summary", "dogfood verified", "--json"])

    state = migrate_state(read_json_file(state_path, default_state()))
    reconcile_next_ids(state)
    done_resume_task = next((task for task in state.get("tasks", []) if str(task.get("id")) == "8"), {})
    current_time = now_iso()
    state.setdefault("work_sessions", []).append(
        {
            "id": next_id(state, "work_session"),
            "task_id": 8,
            "status": "closed",
            "title": done_resume_task.get("title") or "Done JSON dogfood task",
            "goal": done_resume_task.get("description") or done_resume_task.get("title") or "",
            "created_at": current_time,
            "updated_at": current_time,
            "last_tool_call_id": None,
            "last_model_turn_id": None,
            "tool_calls": [],
            "model_turns": [],
        }
    )
    write_json_file(state_path, state)
    done_resume_json_result = run(["work", "8", "--session", "--resume", "--json"])

    defer_verify_task_result = run(["task", "add", "Deferred verification approval task", "--kind", "coding", "--json"])
    defer_verify_task_data = _json_stdout(defer_verify_task_result)
    defer_verify_task_id = (defer_verify_task_data.get("task") or {}).get("id") or 9
    (workspace / "defer-verify.md").write_text("before\n", encoding="utf-8")
    defer_verify_command = f"{sys.executable} -c \"raise SystemExit(23)\""
    defer_verify_start_result = run(
        [
            "work",
            str(defer_verify_task_id),
            "--start-session",
            "--allow-write",
            ".",
            "--allow-verify",
            "--verify-command",
            defer_verify_command,
            "--json",
        ]
    )
    defer_verify_write_result = run(
        [
            "work",
            str(defer_verify_task_id),
            "--tool",
            "edit_file",
            "--path",
            "defer-verify.md",
            "--old",
            "before",
            "--new",
            "after",
            "--allow-write",
            ".",
            "--json",
        ]
    )
    defer_verify_write_data = _json_stdout(defer_verify_write_result)
    defer_verify_tool_id = (defer_verify_write_data.get("tool_call") or {}).get("id")
    defer_verify_resume_result = run(["work", str(defer_verify_task_id), "--session", "--resume", "--json"])
    defer_verify_resume_data = _json_stdout(defer_verify_resume_result)
    defer_verify_approve_result = run(
        [
            "work",
            str(defer_verify_task_id),
            "--approve-tool",
            str(defer_verify_tool_id),
            "--allow-write",
            ".",
            "--defer-verify",
            "--json",
        ]
    )
    defer_verify_approve_data = _json_stdout(defer_verify_approve_result)

    verification_command = f"{sys.executable} -c \"print('dogfood verify recovered')\""
    verification_task_result = run(["task", "add", "Interrupted verification task", "--kind", "coding", "--json"])
    verification_task_data = _json_stdout(verification_task_result)
    verification_task_id = (verification_task_data.get("task") or {}).get("id") or 9
    run(["work", str(verification_task_id), "--start-session", "--json"])
    state = migrate_state(read_json_file(state_path, default_state()))
    reconcile_next_ids(state)
    verification_session = None
    for candidate in state.get("work_sessions", []):
        if str(candidate.get("task_id")) == str(verification_task_id):
            verification_session = candidate
            break
    if verification_session:
        tool_call_id = next_id(state, "work_tool_call")
        verification_call = {
            "id": tool_call_id,
            "session_id": verification_session.get("id"),
            "task_id": verification_task_id,
            "tool": "run_tests",
            "status": "interrupted",
            "parameters": {"command": verification_command, "cwd": "."},
            "result": None,
            "summary": "interrupted dogfood verifier",
            "error": "Interrupted before the verifier completed.",
            "started_at": now_iso(),
            "finished_at": now_iso(),
        }
        verification_session.setdefault("tool_calls", []).append(verification_call)
        verification_session["last_tool_call_id"] = tool_call_id
        verification_session["updated_at"] = now_iso()
        write_json_file(state_path, state)
    verification_resume_result = run(["work", str(verification_task_id), "--session", "--resume", "--json"])
    verification_recover_result = run(
        [
            "work",
            str(verification_task_id),
            "--recover-session",
            "--allow-read",
            ".",
            "--allow-verify",
            "--verify-command",
            verification_command,
            "--json",
        ]
    )
    unpaired_task_result = run(
        ["task", "add", "Unpaired source approval task", "--kind", "coding", "--json"]
    )
    unpaired_task_data_for_id = _json_stdout(unpaired_task_result)
    unpaired_task_id = (unpaired_task_data_for_id.get("task") or {}).get("id") or 10
    unpaired_start_result = run(["work", str(unpaired_task_id), "--start-session", "--json"])
    unpaired_edit_result = run(
        [
            "work",
            str(unpaired_task_id),
            "--tool",
            "edit_file",
            "--path",
            "src/mew/dogfood_override.py",
            "--old",
            "old",
            "--new",
            "new",
            "--allow-write",
            ".",
            "--json",
        ]
    )
    unpaired_edit_data_for_id = _json_stdout(unpaired_edit_result)
    unpaired_tool_id = str((unpaired_edit_data_for_id.get("tool_call") or {}).get("id") or "")
    unpaired_reject_result = run(
        [
            "work",
            str(unpaired_task_id),
            "--approve-tool",
            unpaired_tool_id,
            "--allow-write",
            ".",
            "--allow-verify",
            "--verify-command",
            "true",
            "--json",
        ]
    )
    unpaired_override_result = run(
        [
            "work",
            str(unpaired_task_id),
            "--approve-tool",
            unpaired_tool_id,
            "--allow-write",
            ".",
            "--allow-unpaired-source-edit",
            "--allow-verify",
            "--verify-command",
            "true",
            "--json",
        ]
    )
    running_output_task_result = run(
        ["task", "add", "Running output snapshot task", "--kind", "coding", "--json"]
    )
    running_output_task_data_for_id = _json_stdout(running_output_task_result)
    running_output_task_id = (running_output_task_data_for_id.get("task") or {}).get("id") or 11
    running_output_start_result = run(["work", str(running_output_task_id), "--start-session", "--json"])
    running_output_start_data_for_state = _json_stdout(running_output_start_result)
    running_output_session_id = (running_output_start_data_for_state.get("work_session") or {}).get("id")
    state = migrate_state(read_json_file(state_path, default_state()))
    reconcile_next_ids(state)
    running_output_session = None
    for candidate in state.get("work_sessions", []):
        if str(candidate.get("id")) == str(running_output_session_id):
            running_output_session = candidate
            break
    running_output_observed_session_updated_at = ""
    if running_output_session:
        current_time = now_iso()
        tool_call_id = next_id(state, "work_tool_call")
        running_output_session.setdefault("tool_calls", []).append(
            {
                "id": tool_call_id,
                "session_id": running_output_session.get("id"),
                "task_id": running_output_task_id,
                "tool": "run_tests",
                "status": "running",
                "parameters": {"command": "pytest -q", "cwd": "."},
                "result": None,
                "summary": "",
                "error": "",
                "started_at": current_time,
                "finished_at": None,
                "running_output": {
                    "stdout": "dogfood partial output\nstill running\n",
                    "stdout_truncated": False,
                    "updated_at": now_iso(),
                    "max_chars": 4000,
                },
            }
        )
        running_output_session["last_tool_call_id"] = tool_call_id
        running_output_session["updated_at"] = current_time
        running_output_observed_session_updated_at = current_time
        write_json_file(state_path, state)
    running_output_snapshot_result = run(
        [
            "work",
            str(running_output_task_id),
            "--follow",
            "--max-steps",
            "0",
            "--quiet",
            "--allow-read",
            ".",
        ]
    )
    running_output_snapshot_data = read_json_file(workspace / STATE_DIR / "follow" / "latest.json", {})
    run(["work", str(running_output_task_id), "--close-session", "--json"])

    discovery_task_result = run(
        ["task", "add", "Existing paired-test discovery task", "--kind", "coding", "--json"]
    )
    discovery_task_data = _json_stdout(discovery_task_result)
    discovery_task_id = str((discovery_task_data.get("task") or {}).get("id") or "")
    discovery_start_result = run(["work", discovery_task_id, "--start-session", "--json"])
    discovered_source_edit_result = run(
        [
            "work",
            discovery_task_id,
            "--tool",
            "edit_file",
            "--path",
            "src/mew/cli.py",
            "--old",
            "old parser",
            "--new",
            "new parser",
            "--allow-write",
            ".",
            "--json",
        ]
    )
    discovery_resume_result = run(["work", discovery_task_id, "--session", "--resume", "--json"])
    discovery_cells_result = run(["work", discovery_task_id, "--cells", "--json"])

    paired_steer_ai_script = workspace / "paired_steer_ai_check.py"
    paired_steer_ai_script.write_text(
        """
import json
import sys
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from mew.cli import main
from mew.state import load_state


def run_main(args):
    stdout = StringIO()
    with redirect_stdout(stdout):
        code = main(args)
    return code, stdout.getvalue()


Path("src/mew").mkdir(parents=True, exist_ok=True)
Path("tests").mkdir(exist_ok=True)
Path("src/mew/dogfood_ai_pairing.py").write_text("VALUE = 'old'\\n", encoding="utf-8")

code, output = run_main(["task", "add", "Dogfood AI paired steer task", "--kind", "coding", "--json"])
task_id = str(json.loads(output)["task"]["id"])
run_main(["work", task_id, "--start-session"])

model_outputs = [
    {
        "summary": "preview source edit first",
        "action": {
            "type": "edit_file",
            "path": "src/mew/dogfood_ai_pairing.py",
            "old": "old",
            "new": "new",
        },
    },
    {
        "summary": "read before editing paired test",
        "action": {
            "type": "read_file",
            "path": "src/mew/dogfood_ai_pairing.py",
        },
    },
    {
        "summary": "add paired test first",
        "action": {
            "type": "write_file",
            "path": "tests/test_dogfood_ai_pairing.py",
            "content": "def test_dogfood_ai_pairing():\\n    assert True\\n",
            "create": True,
            "dry_run": False,
        },
    },
]
verify_command = f"{sys.executable} -c \\"raise SystemExit(99)\\""
with patch("mew.commands.load_model_auth", return_value={"path": "auth.json"}):
    with patch("mew.work_loop.call_model_json_with_retries", side_effect=model_outputs):
        code, output = run_main(
            [
                "work",
                task_id,
                "--ai",
                "--auth",
                "auth.json",
                "--allow-read",
                ".",
                "--allow-write",
                ".",
                "--allow-verify",
                "--verify-command",
                verify_command,
                "--max-steps",
                "3",
                "--act-mode",
                "deterministic",
                "--json",
            ]
        )

report = json.loads(output)
session = next(candidate for candidate in load_state()["work_sessions"] if str(candidate.get("task_id")) == task_id)
tool_call = (session.get("tool_calls") or [{}])[-1]
result = tool_call.get("result") or {}
initial_coerced_dry_run_reason = (session.get("model_turns") or [{}])[-1].get("coerced_dry_run_reason")
test_file_exists_before_approval = Path("tests/test_dogfood_ai_pairing.py").exists()
approval_code, approval_output = run_main(
    [
        "work",
        task_id,
        "--approve-tool",
        str(tool_call.get("id")),
        "--allow-write",
        ".",
        "--allow-verify",
        "--verify-command",
        verify_command,
        "--json",
    ]
)
approval = json.loads(approval_output) if approval_output.strip() else {}
approval_tool_call = approval.get("tool_call") or {}
approval_result = approval_tool_call.get("result") or {}
source_retry_model_output = {
    "summary": "retry source edit after paired test approval",
    "action": {
        "type": "edit_file",
        "path": "src/mew/dogfood_ai_pairing.py",
        "old": "old",
        "new": "new",
    },
}
with patch("mew.commands.load_model_auth", return_value={"path": "auth.json"}):
    with patch("mew.work_loop.call_model_json_with_retries", return_value=source_retry_model_output):
        source_retry_code, source_retry_output = run_main(
            [
                "work",
                task_id,
                "--ai",
                "--auth",
                "auth.json",
                "--allow-read",
                ".",
                "--allow-write",
                ".",
                "--allow-verify",
                "--verify-command",
                verify_command,
                "--max-steps",
                "1",
                "--act-mode",
                "deterministic",
                "--json",
            ]
        )
source_retry_report = json.loads(source_retry_output) if source_retry_output.strip() else {}
session = next(candidate for candidate in load_state()["work_sessions"] if str(candidate.get("task_id")) == task_id)
source_call = (session.get("tool_calls") or [{}])[-1]
good_verify_command = (
    f"{sys.executable} -c \\"from pathlib import Path; "
    "assert 'new' in Path('src/mew/dogfood_ai_pairing.py').read_text(); "
    "assert Path('tests/test_dogfood_ai_pairing.py').exists()\\""
)
source_approval_code, source_approval_output = run_main(
    [
        "work",
        task_id,
        "--approve-tool",
        str(source_call.get("id")),
        "--allow-write",
        ".",
        "--allow-verify",
        "--verify-command",
        good_verify_command,
        "--json",
    ]
)
source_approval = json.loads(source_approval_output) if source_approval_output.strip() else {}
source_approval_result = ((source_approval.get("tool_call") or {}).get("result") or {})
observed = {
    "exit_code": code,
    "stop_reason": report.get("stop_reason"),
    "test_file_exists_before_approval": test_file_exists_before_approval,
    "test_file_exists_after_approval": Path("tests/test_dogfood_ai_pairing.py").exists(),
    "tool": tool_call.get("tool"),
    "path": (tool_call.get("parameters") or {}).get("path"),
    "apply": (tool_call.get("parameters") or {}).get("apply"),
    "dry_run": result.get("dry_run"),
    "defer_verify_on_approval": (tool_call.get("parameters") or {}).get("defer_verify_on_approval"),
    "paired_test_source_path": (tool_call.get("parameters") or {}).get("paired_test_source_path"),
    "verification_exit_code": result.get("verification_exit_code"),
    "coerced_dry_run_reason": initial_coerced_dry_run_reason,
    "approval_exit_code": approval_code,
    "approval_verification_deferred": approval_result.get("verification_deferred"),
    "approval_verification_exit_code": approval_result.get("verification_exit_code"),
    "source_retry_exit_code": source_retry_code,
    "source_retry_stop_reason": source_retry_report.get("stop_reason"),
    "source_retry_path": (source_call.get("parameters") or {}).get("path"),
    "source_approval_exit_code": source_approval_code,
    "source_verification_exit_code": source_approval_result.get("verification_exit_code"),
    "source_after": "new" in Path("src/mew/dogfood_ai_pairing.py").read_text(encoding="utf-8"),
}
passed = (
    code == 0
    and observed["stop_reason"] == "pending_approval"
    and observed["test_file_exists_before_approval"] is False
    and observed["test_file_exists_after_approval"] is True
    and observed["tool"] == "write_file"
    and observed["path"] == "tests/test_dogfood_ai_pairing.py"
    and observed["apply"] is False
    and observed["dry_run"] is True
    and observed["defer_verify_on_approval"] is True
    and observed["paired_test_source_path"] == "src/mew/dogfood_ai_pairing.py"
    and observed["verification_exit_code"] is None
    and observed["coerced_dry_run_reason"] == "paired_test_steer"
    and observed["approval_exit_code"] == 0
    and observed["approval_verification_deferred"] is True
    and observed["approval_verification_exit_code"] is None
    and observed["source_retry_exit_code"] == 0
    and observed["source_retry_stop_reason"] == "pending_approval"
    and observed["source_retry_path"] == "src/mew/dogfood_ai_pairing.py"
    and observed["source_approval_exit_code"] == 0
    and observed["source_verification_exit_code"] == 0
    and observed["source_after"] is True
)

Path("src/mew/dogfood_batch.py").write_text("VALUE = 'before'\\n", encoding="utf-8")
Path("tests/test_dogfood_batch.py").write_text(
    "import unittest\\n"
    "from pathlib import Path\\n\\n"
    "class DogfoodBatchTests(unittest.TestCase):\\n"
    "    def test_value(self):\\n"
    "        self.assertIn('before', Path('src/mew/dogfood_batch.py').read_text())\\n",
    encoding="utf-8",
)
code, output = run_main(["task", "add", "Dogfood paired approve-all task", "--kind", "coding", "--json"])
batch_task_id = str(json.loads(output)["task"]["id"])
stale_command = f"{sys.executable} -c \\"print('stale verifier')\\""
run_main(
    [
        "work",
        batch_task_id,
        "--start-session",
        "--allow-write",
        ".",
        "--allow-verify",
        "--verify-command",
        stale_command,
    ]
)
code, output = run_main(
    [
        "work",
        batch_task_id,
        "--tool",
        "edit_file",
        "--path",
        "src/mew/dogfood_batch.py",
        "--old",
        "before",
        "--new",
        "after",
        "--allow-write",
        ".",
        "--json",
    ]
)
source_dry_run = json.loads(output)["tool_call"]
code, output = run_main(
    [
        "work",
        batch_task_id,
        "--tool",
        "edit_file",
        "--path",
        "tests/test_dogfood_batch.py",
        "--old",
        "before",
        "--new",
        "after",
        "--allow-write",
        ".",
        "--json",
    ]
)
test_dry_run = json.loads(output)["tool_call"]
code, output = run_main(["work", batch_task_id, "--approve-all", "--allow-write", ".", "--json"])
approve_all = json.loads(output)
batch_session = next(
    candidate for candidate in load_state()["work_sessions"] if str(candidate.get("task_id")) == batch_task_id
)
applied = [
    call
    for call in batch_session.get("tool_calls", [])
    if (call.get("parameters") or {}).get("approved_from_tool_call_id")
    in {source_dry_run.get("id"), test_dry_run.get("id")}
]
batch_observed = {
    "exit_code": code,
    "approved_count": approve_all.get("count"),
    "source_after": "after" in Path("src/mew/dogfood_batch.py").read_text(encoding="utf-8"),
    "test_after": "after" in Path("tests/test_dogfood_batch.py").read_text(encoding="utf-8"),
    "deferred_count": sum(1 for call in applied if (call.get("result") or {}).get("verification_deferred")),
    "verification_exit_codes": [
        (call.get("result") or {}).get("verification_exit_code")
        for call in applied
        if (call.get("result") or {}).get("verification_exit_code") is not None
    ],
}
batch_passed = (
    code == 0
    and batch_observed["approved_count"] == 2
    and batch_observed["source_after"]
    and batch_observed["test_after"]
    and batch_observed["deferred_count"] == 1
    and batch_observed["verification_exit_codes"] == [0]
)
observed["approve_all_batch"] = batch_observed
passed = passed and batch_passed
print(json.dumps({"passed": passed, "observed": observed}, ensure_ascii=False))
raise SystemExit(0 if passed else 1)
""".lstrip(),
        encoding="utf-8",
    )
    paired_steer_ai_result = run_command([sys.executable, str(paired_steer_ai_script)], workspace, timeout=30, env=env)
    paired_steer_ai_data = _json_stdout(paired_steer_ai_result)
    if paired_steer_ai_result.get("exit_code") != 0 or not paired_steer_ai_data.get("passed"):
        commands.append(paired_steer_ai_result)

    accept_edits_ai_script = workspace / "accept_edits_ai_check.py"
    accept_edits_ai_script.write_text(
        """
import json
import sys
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from mew.cli import main
from mew.state import load_state


def run_main(args):
    stdout = StringIO()
    with redirect_stdout(stdout):
        code = main(args)
    return code, stdout.getvalue()


Path("accept-edits.md").write_text("old text\\n", encoding="utf-8")
code, output = run_main(["task", "add", "Dogfood accept-edits task", "--kind", "coding", "--json"])
task_id = str(json.loads(output)["task"]["id"])
model_output = {
    "summary": "preview and accept one edit",
    "action": {
        "type": "edit_file",
        "path": "accept-edits.md",
        "old": "old text",
        "new": "new text",
    },
}
verify_command = (
    f"{sys.executable} -c \\"from pathlib import Path; "
    "assert Path('accept-edits.md').read_text() == 'new text\\\\n'\\""
)
with patch("mew.commands.load_model_auth", return_value={"path": "auth.json"}):
    with patch("mew.work_loop.call_model_json_with_retries", return_value=model_output):
        code, output = run_main(
            [
                "work",
                task_id,
                "--ai",
                "--json",
                "--auth",
                "auth.json",
                "--allow-read",
                ".",
                "--allow-write",
                ".",
                "--allow-verify",
                "--verify-command",
                verify_command,
                "--approval-mode",
                "accept-edits",
                "--max-steps",
                "1",
                "--act-mode",
                "deterministic",
            ]
        )

report = json.loads(output)
session = next(candidate for candidate in load_state()["work_sessions"] if str(candidate.get("task_id")) == task_id)
tool_calls = session.get("tool_calls") or []
preview_call = tool_calls[0] if tool_calls else {}
apply_call = tool_calls[1] if len(tool_calls) > 1 else {}
apply_result = apply_call.get("result") or {}
observed = {
    "exit_code": code,
    "stdout_parseable_json": isinstance(report, dict),
    "stop_reason": report.get("stop_reason"),
    "inline_approval": ((report.get("steps") or [{}])[0]).get("inline_approval"),
    "inline_approval_status": ((report.get("steps") or [{}])[0]).get("inline_approval_status"),
    "preview_approval_status": preview_call.get("approval_status"),
    "apply_tool_status": apply_call.get("status"),
    "apply_dry_run": apply_result.get("dry_run"),
    "verification_exit_code": apply_result.get("verification_exit_code"),
    "content": Path("accept-edits.md").read_text(encoding="utf-8"),
}

Path("src/mew/accept_pairing.py").write_text("VALUE = 'old'\\n", encoding="utf-8")
pair_outputs = [
    {
        "summary": "preview source edit first",
        "action": {
            "type": "edit_file",
            "path": "src/mew/accept_pairing.py",
            "old": "old",
            "new": "new",
        },
    },
    {
        "summary": "add paired test first",
        "action": {
            "type": "write_file",
            "path": "tests/test_accept_pairing.py",
            "content": "def test_accept_pairing():\\n    assert True\\n",
            "create": True,
        },
    },
]
code, output = run_main(["task", "add", "Dogfood accept-edits paired test-first task", "--kind", "coding", "--json"])
pair_task_id = str(json.loads(output)["task"]["id"])
failing_verify = f"{sys.executable} -c \\"raise SystemExit(99)\\""
with patch("mew.commands.load_model_auth", return_value={"path": "auth.json"}):
    with patch("mew.work_loop.call_model_json_with_retries", side_effect=pair_outputs):
        pair_code, pair_output = run_main(
            [
                "work",
                pair_task_id,
                "--ai",
                "--json",
                "--auth",
                "auth.json",
                "--allow-read",
                ".",
                "--allow-write",
                ".",
                "--allow-verify",
                "--verify-command",
                failing_verify,
                "--approval-mode",
                "accept-edits",
                "--max-steps",
                "2",
                "--act-mode",
                "deterministic",
            ]
        )
pair_report = json.loads(pair_output)
pair_session = next(candidate for candidate in load_state()["work_sessions"] if str(candidate.get("task_id")) == pair_task_id)
pair_calls = pair_session.get("tool_calls") or []
pair_steps = pair_report.get("steps") or []
pair_preview = pair_calls[0] if pair_calls else {}
pair_apply = pair_calls[1] if len(pair_calls) > 1 else {}
pair_apply_result = pair_apply.get("result") or {}
observed["paired_test_first"] = {
    "exit_code": pair_code,
    "stop_reason": pair_report.get("stop_reason"),
    "inline_approval": ((pair_steps[1] if len(pair_steps) > 1 else {})).get("inline_approval"),
    "preview_defer_verify_on_approval": (pair_preview.get("parameters") or {}).get("defer_verify_on_approval"),
    "paired_test_source_path": (pair_preview.get("parameters") or {}).get("paired_test_source_path"),
    "preview_approval_status": pair_preview.get("approval_status"),
    "apply_verification_deferred": pair_apply_result.get("verification_deferred"),
    "verification_exit_code_present": "verification_exit_code" in pair_apply_result,
    "test_file_exists": Path("tests/test_accept_pairing.py").exists(),
    "source_after": Path("src/mew/accept_pairing.py").read_text(encoding="utf-8"),
}

Path("src/mew/accept_batch.py").write_text("VALUE = 'old'\\n", encoding="utf-8")
Path("tests/test_accept_batch.py").write_text(
    "from pathlib import Path\\n\\n"
    "def test_accept_batch():\\n"
    "    assert 'old' in Path('src/mew/accept_batch.py').read_text()\\n",
    encoding="utf-8",
)
code, output = run_main(["task", "add", "Dogfood accept-edits paired batch task", "--kind", "coding", "--json"])
batch_task_id = str(json.loads(output)["task"]["id"])
batch_model_output = {
    "summary": "preview paired batch",
    "action": {
        "type": "batch",
        "tools": [
            {
                "type": "edit_file",
                "path": "src/mew/accept_batch.py",
                "old": "old",
                "new": "new",
                "dry_run": False,
            },
            {
                "type": "edit_file",
                "path": "tests/test_accept_batch.py",
                "old": "'old'",
                "new": "'new'",
                "dry_run": False,
            },
        ],
    },
}
batch_verify_command = (
    f"{sys.executable} -c \\"from pathlib import Path; "
    "assert 'new' in Path('src/mew/accept_batch.py').read_text(); "
    "assert 'new' in Path('tests/test_accept_batch.py').read_text()\\""
)
with patch("mew.commands.load_model_auth", return_value={"path": "auth.json"}):
    with patch("mew.work_loop.call_model_json_with_retries", return_value=batch_model_output):
        batch_code, batch_output = run_main(
            [
                "work",
                batch_task_id,
                "--ai",
                "--json",
                "--auth",
                "auth.json",
                "--allow-read",
                ".",
                "--allow-write",
                ".",
                "--allow-verify",
                "--verify-command",
                batch_verify_command,
                "--approval-mode",
                "accept-edits",
                "--max-steps",
                "1",
                "--act-mode",
                "deterministic",
            ]
        )
batch_report = json.loads(batch_output)
batch_session = next(candidate for candidate in load_state()["work_sessions"] if str(candidate.get("task_id")) == batch_task_id)
batch_calls = batch_session.get("tool_calls") or []
batch_steps = batch_report.get("steps") or []
batch_preview_paths = [(call.get("parameters") or {}).get("path") for call in batch_calls[:2]]
batch_apply_results = [(call.get("result") or {}) for call in batch_calls[2:4]]
observed["paired_write_batch"] = {
    "exit_code": batch_code,
    "stop_reason": batch_report.get("stop_reason"),
    "action_type": ((batch_steps[0] if batch_steps else {}).get("action") or {}).get("type"),
    "inline_approval": ((batch_steps[0] if batch_steps else {})).get("inline_approval"),
    "inline_approval_count": ((batch_steps[0] if batch_steps else {})).get("inline_approval_count"),
    "preview_paths": batch_preview_paths,
    "preview_apply_flags": [(call.get("parameters") or {}).get("apply") for call in batch_calls[:2]],
    "preview_approval_statuses": [call.get("approval_status") for call in batch_calls[:2]],
    "test_verification_deferred": (batch_apply_results[0] if batch_apply_results else {}).get("verification_deferred"),
    "source_verification_exit_code": (
        (batch_apply_results[1] if len(batch_apply_results) > 1 else {}).get("verification_exit_code")
    ),
    "source_after": Path("src/mew/accept_batch.py").read_text(encoding="utf-8"),
    "test_after": Path("tests/test_accept_batch.py").read_text(encoding="utf-8"),
}
passed = (
    code == 0
    and observed["stdout_parseable_json"] is True
    and observed["stop_reason"] == "max_steps"
    and observed["inline_approval"] == "auto_applied"
    and observed["inline_approval_status"] == "completed"
    and observed["preview_approval_status"] == "applied"
    and observed["apply_tool_status"] == "completed"
    and observed["apply_dry_run"] is False
    and observed["verification_exit_code"] == 0
    and observed["content"] == "new text\\n"
    and observed["paired_test_first"]["exit_code"] == 0
    and observed["paired_test_first"]["stop_reason"] == "max_steps"
    and observed["paired_test_first"]["inline_approval"] == "auto_applied"
    and observed["paired_test_first"]["preview_defer_verify_on_approval"] is True
    and observed["paired_test_first"]["paired_test_source_path"] == "src/mew/accept_pairing.py"
    and observed["paired_test_first"]["preview_approval_status"] == "applied"
    and observed["paired_test_first"]["apply_verification_deferred"] is True
    and observed["paired_test_first"]["verification_exit_code_present"] is False
    and observed["paired_test_first"]["test_file_exists"] is True
    and observed["paired_test_first"]["source_after"] == "VALUE = 'old'\\n"
    and observed["paired_write_batch"]["exit_code"] == 0
    and observed["paired_write_batch"]["action_type"] == "batch"
    and observed["paired_write_batch"]["inline_approval"] == "auto_applied"
    and observed["paired_write_batch"]["inline_approval_count"] == 2
    and observed["paired_write_batch"]["preview_paths"]
    == ["tests/test_accept_batch.py", "src/mew/accept_batch.py"]
    and observed["paired_write_batch"]["preview_apply_flags"] == [False, False]
    and observed["paired_write_batch"]["preview_approval_statuses"] == ["applied", "applied"]
    and observed["paired_write_batch"]["test_verification_deferred"] is True
    and observed["paired_write_batch"]["source_verification_exit_code"] == 0
    and observed["paired_write_batch"]["source_after"] == "VALUE = 'new'\\n"
    and "'new'" in observed["paired_write_batch"]["test_after"]
)
print(json.dumps({"passed": passed, "observed": observed}, ensure_ascii=False))
raise SystemExit(0 if passed else 1)
""".lstrip(),
        encoding="utf-8",
    )
    accept_edits_ai_result = run_command([sys.executable, str(accept_edits_ai_script)], workspace, timeout=30, env=env)
    accept_edits_ai_data = _json_stdout(accept_edits_ai_result)
    if accept_edits_ai_result.get("exit_code") != 0 or not accept_edits_ai_data.get("passed"):
        commands.append(accept_edits_ai_result)

    start_data = _json_stdout(start_result)
    task_add_json_data = _json_stdout(task_add_json_result)
    task_show_json_data = _json_stdout(task_show_json_result)
    task_list_json_data = _json_stdout(task_list_json_result)
    task_update_json_data = _json_stdout(task_update_json_result)
    read_data = _json_stdout(read_result)
    glob_data = _json_stdout(glob_result)
    test_data = _json_stdout(test_result)
    command_data = _json_stdout(command_result)
    edit_data = _json_stdout(edit_result)
    line_read_data = _json_stdout(line_read_result)
    large_edit_data = _json_stdout(large_edit_result)
    large_no_newline_edit_data = _json_stdout(large_no_newline_edit_result)
    source_edit_data = _json_stdout(source_edit_result)
    discovered_source_edit_data = _json_stdout(discovered_source_edit_result)
    discovery_resume_data = _json_stdout(discovery_resume_result)
    discovery_cells_data = _json_stdout(discovery_cells_result)
    approve_data = _json_stdout(approve_result)
    approve_all_first_data = _json_stdout(approve_all_first_result)
    approve_all_second_data = _json_stdout(approve_all_second_result)
    approve_all_data = _json_stdout(approve_all_result)
    approve_all_applied = approve_all_data.get("approved") or []
    approve_all_first_apply = ((approve_all_applied[0] if approve_all_applied else {}).get("tool_call") or {})
    approve_all_second_apply = (
        (approve_all_applied[1] if len(approve_all_applied) > 1 else {}).get("tool_call") or {}
    )
    reply_file_data = _json_stdout(reply_file_result)
    interrupt_submit_data = _json_stdout(interrupt_submit_result)
    interrupt_resume_data = _json_stdout(interrupt_resume_result)
    reply_approve_write_data = _json_stdout(reply_approve_write_result)
    reply_approve_status_data = _json_stdout(reply_approve_status_result)
    reply_approve_data = _json_stdout(reply_approve_result)
    task_done_json_seed_data = _json_stdout(task_done_json_seed_result)
    task_done_json_data = _json_stdout(task_done_json_result)
    done_resume_json_data = _json_stdout(done_resume_json_result)
    verification_resume_data = _json_stdout(verification_resume_result)
    verification_recover_data = _json_stdout(verification_recover_result)
    unpaired_task_data = _json_stdout(unpaired_task_result)
    unpaired_edit_data = _json_stdout(unpaired_edit_result)
    unpaired_override_data = _json_stdout(unpaired_override_result)
    running_output_task_data = _json_stdout(running_output_task_result)
    write_data = _json_stdout(write_result)
    stop_data = _json_stdout(stop_result)
    note_data = _json_stdout(note_result)
    steer_data = _json_stdout(steer_result)
    queue_followup_data = _json_stdout(queue_followup_result)
    resume_data = _json_stdout(resume_result)
    verification_ledger_data = _json_stdout(verification_ledger_result, [])
    writes_ledger_data = _json_stdout(writes_ledger_result, [])
    timeline_data = _json_stdout(timeline_result)
    cells_data = _json_stdout(cells_result)
    interrupted_resume_data = _json_stdout(interrupted_resume_result)
    interrupted_recover_data = _json_stdout(interrupted_recover_result)
    auto_recover_data = _json_stdout(auto_recover_result)
    work_data = _json_stdout(work_result)
    session = work_data.get("work_session") or {}
    tool_calls = session.get("tool_calls") or []
    workbench_session_verifications = work_data.get("work_session_verifications") or []
    workbench_session_writes = work_data.get("work_session_writes") or []
    timeline = timeline_data.get("timeline") or []
    cells = cells_data.get("cells") or []
    def is_source_pairing_path(value):
        normalized = str(value or "").replace("\\", "/")
        return normalized == "src/mew/pairing.py" or normalized.endswith("/src/mew/pairing.py")

    def is_cli_discovery_path(value):
        normalized = str(value or "").replace("\\", "/")
        return normalized == "src/mew/cli.py" or normalized.endswith("/src/mew/cli.py")

    source_pairing_approvals = [
        approval
        for approval in (resume_data.get("resume") or {}).get("pending_approvals") or []
        if is_source_pairing_path(approval.get("path"))
    ]
    cli_discovery_approvals = [
        approval
        for approval in (discovery_resume_data.get("resume") or {}).get("pending_approvals") or []
        if is_cli_discovery_path(approval.get("path"))
    ]
    source_pairing_cells = [
        cell
        for cell in cells
        if cell.get("kind") == "approval" and is_source_pairing_path(cell.get("target"))
    ]
    cli_discovery_cells = [
        cell
        for cell in discovery_cells_data.get("cells") or []
        if cell.get("kind") == "approval" and is_cli_discovery_path(cell.get("target"))
    ]
    interrupted_items = ((interrupted_resume_data.get("resume") or {}).get("recovery_plan") or {}).get("items") or []
    interrupted_recovery = interrupted_recover_data.get("recovery") or {}
    interrupted_review = interrupted_recovery.get("review_item") or {}
    auto_recovery = auto_recover_data.get("auto_recovery") or {}
    auto_tool_call = auto_recovery.get("tool_call") or {}
    verification_items = ((verification_resume_data.get("resume") or {}).get("recovery_plan") or {}).get("items") or []
    verification_recovery = verification_recover_data.get("recovery") or {}
    verification_tool_call = verification_recover_data.get("tool_call") or {}
    pending_diff_previews = [
        approval.get("diff_preview") or ""
        for approval in (resume_data.get("resume") or {}).get("pending_approvals") or []
    ]
    working_memory = (resume_data.get("resume") or {}).get("working_memory") or {}
    user_preferences = (resume_data.get("resume") or {}).get("user_preferences") or {}
    active_memory = (resume_data.get("resume") or {}).get("active_memory") or {}
    same_surface_audit = (resume_data.get("resume") or {}).get("same_surface_audit") or {}
    source_verification_confidence = (resume_data.get("resume") or {}).get("verification_confidence") or {}
    running_output_preferences = (running_output_snapshot_data.get("resume") or {}).get("user_preferences") or {}
    resume_commands = (resume_data.get("resume") or {}).get("commands") or []
    done_resume_next_action = ((done_resume_json_data.get("resume") or {}).get("next_action") or "")
    done_resume_controls = done_resume_json_data.get("next_cli_controls") or []
    running_output_commands = (running_output_snapshot_data.get("resume") or {}).get("commands") or []
    running_output_cells = running_output_snapshot_data.get("cells") or []
    running_output_cell = next((cell for cell in running_output_cells if cell.get("kind") == "test"), {})
    running_output_tail = "\n".join(
        line
        for tail in running_output_cell.get("tail") or []
        for line in tail.get("lines") or []
    )

    _scenario_check(
        checks,
        "work_task_add_json_returns_created_task",
        task_add_json_result.get("exit_code") == 0
        and task_add_json_data.get("id") == 1
        and (task_add_json_data.get("task") or {}).get("id") == 1
        and (task_add_json_data.get("task") or {}).get("title") == "Native work task"
        and (task_add_json_data.get("task") or {}).get("kind") == "coding",
        observed={
            "id": task_add_json_data.get("id"),
            "title": task_add_json_data.get("title"),
            "kind": task_add_json_data.get("kind"),
        },
        expected="task add --json returns the created task without text parsing",
    )
    _scenario_check(
        checks,
        "work_task_show_json_returns_task",
        task_show_json_result.get("exit_code") == 0
        and (task_show_json_data.get("task") or {}).get("id") == 1
        and (task_show_json_data.get("task") or {}).get("title") == "Native work task"
        and (task_show_json_data.get("task") or {}).get("effective_kind") == "coding",
        observed={
            "id": task_show_json_data.get("id"),
            "title": task_show_json_data.get("title"),
            "effective_kind": task_show_json_data.get("effective_kind"),
        },
        expected="task show --json returns the selected task without text parsing",
    )
    _scenario_check(
        checks,
        "work_task_list_json_returns_tasks",
        task_list_json_result.get("exit_code") == 0
        and task_list_json_data.get("count") == 1
        and ((task_list_json_data.get("tasks") or [{}])[0]).get("id") == 1
        and ((task_list_json_data.get("tasks") or [{}])[0]).get("effective_kind") == "coding",
        observed={
            "count": task_list_json_data.get("count"),
            "first_id": ((task_list_json_data.get("tasks") or [{}])[0]).get("id"),
            "first_effective_kind": ((task_list_json_data.get("tasks") or [{}])[0]).get("effective_kind"),
        },
        expected="task list --json returns matching tasks without text parsing",
    )
    _scenario_check(
        checks,
        "work_task_update_json_returns_updated_task",
        task_update_json_result.get("exit_code") == 0
        and task_update_json_data.get("changed") is True
        and task_update_json_data.get("id") == 1
        and (task_update_json_data.get("task") or {}).get("id") == 1
        and (task_update_json_data.get("task") or {}).get("priority") == "high",
        observed={
            "id": task_update_json_data.get("id"),
            "changed": task_update_json_data.get("changed"),
            "priority": (task_update_json_data.get("task") or {}).get("priority"),
        },
        expected="task update --json returns the updated task and changed flag",
    )
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
        "work_run_command_completes",
        command_result.get("exit_code") == 0
        and ((command_data.get("tool_call") or {}).get("result") or {}).get("exit_code") == 0,
        observed=command_data.get("tool_call"),
        expected="run_command records exit_code=0",
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
        "work_edit_file_large_no_newline_diff_stats",
        large_no_newline_edit_result.get("exit_code") == 0
        and ((large_no_newline_edit_data.get("tool_call") or {}).get("result") or {}).get("diff_stats")
        == {"added": 1, "removed": 1}
        and "old_call()" in (workspace / "large_no_newline.py").read_text(encoding="utf-8"),
        observed=large_no_newline_edit_data.get("tool_call"),
        expected="large no-newline dry-run edit reports full +1/-1 diff stats",
    )
    _scenario_check(
        checks,
        "work_source_edit_pairing_advisory",
        source_edit_result.get("exit_code") == 0
        and ((source_edit_data.get("tool_call") or {}).get("result") or {}).get("dry_run") is True
        and ((source_pairing_approvals[0].get("pairing_status") or {}).get("status") if source_pairing_approvals else None)
        == "missing_test_edit"
        and (
            (source_pairing_cells[0].get("pairing_status") or {}).get("status") if source_pairing_cells else None
        )
        == "missing_test_edit"
        and (
            (source_pairing_approvals[0].get("pairing_status") or {}).get("suggested_test_path")
            if source_pairing_approvals
            else None
        )
        == "tests/test_pairing.py"
        and same_surface_audit.get("status") == "needed"
        and "src/mew/pairing.py" in (same_surface_audit.get("paths") or [])
        and source_verification_confidence.get("status") == "pending_approval"
        and source_verification_confidence.get("expected_command") == "uv run python -m unittest tests.test_pairing"
        and "paired test missing" in ((source_pairing_cells[0].get("preview") or "") if source_pairing_cells else ""),
        observed={
            "tool_call_id": (source_edit_data.get("tool_call") or {}).get("id"),
            "approval_path": (source_pairing_approvals[0] or {}).get("path") if source_pairing_approvals else None,
            "approval_pairing_status": (
                ((source_pairing_approvals[0] or {}).get("pairing_status") or {}).get("status")
                if source_pairing_approvals
                else None
            ),
            "cell_pairing_status": (
                ((source_pairing_cells[0] or {}).get("pairing_status") or {}).get("status")
                if source_pairing_cells
                else None
            ),
            "suggested_test_path": (
                ((source_pairing_approvals[0] or {}).get("pairing_status") or {}).get("suggested_test_path")
                if source_pairing_approvals
                else None
            ),
            "same_surface_audit": same_surface_audit,
            "verification_confidence": source_verification_confidence,
            "cell_preview": (source_pairing_cells[0] or {}).get("preview") if source_pairing_cells else None,
        },
        expected=(
            "src/mew dry-run edits surface a missing paired test advisory, same-surface audit, and verification confidence"
        ),
    )
    cli_discovery_pairing = (
        ((cli_discovery_approvals[0] or {}).get("pairing_status") or {}) if cli_discovery_approvals else {}
    )
    _scenario_check(
        checks,
        "work_source_edit_pairing_discovers_existing_test",
        discovery_task_result.get("exit_code") == 0
        and discovery_start_result.get("exit_code") == 0
        and discovery_resume_result.get("exit_code") == 0
        and discovery_cells_result.get("exit_code") == 0
        and discovered_source_edit_result.get("exit_code") == 0
        and ((discovered_source_edit_data.get("tool_call") or {}).get("result") or {}).get("dry_run") is True
        and cli_discovery_pairing.get("status") == "missing_test_edit"
        and cli_discovery_pairing.get("suggested_test_path") == "tests/test_dogfood.py"
        and (cli_discovery_pairing.get("discovered_test_paths") or [""])[0] == "tests/test_dogfood.py"
        and cli_discovery_pairing.get("suggested_test_path") != "tests/test_cli.py"
        and "imports mew.cli" in (cli_discovery_pairing.get("suggestion_reason") or "")
        and bool(cli_discovery_cells),
        observed={
            "tool_call_id": (discovered_source_edit_data.get("tool_call") or {}).get("id"),
            "approval_path": (cli_discovery_approvals[0] or {}).get("path") if cli_discovery_approvals else None,
            "pairing_status": cli_discovery_pairing,
            "cell_preview": (cli_discovery_cells[0] or {}).get("preview") if cli_discovery_cells else None,
        },
        expected=(
            "paired-test steering discovers existing parser coverage before falling back to nonexistent tests/test_cli.py"
        ),
    )
    _scenario_check(
        checks,
        "work_ai_paired_test_steer_keeps_test_write_reviewable",
        paired_steer_ai_result.get("exit_code") == 0 and bool(paired_steer_ai_data.get("passed")),
        observed=paired_steer_ai_data.get("observed") or command_result_tail(paired_steer_ai_result, limit=5),
        expected="paired-test steer coerces model-suggested tests/** apply writes into dry-run pending approval",
    )
    paired_approval_observed = paired_steer_ai_data.get("observed") or {}
    _scenario_check(
        checks,
        "work_ai_paired_test_approval_auto_defers_verification",
        paired_steer_ai_result.get("exit_code") == 0
        and paired_approval_observed.get("defer_verify_on_approval") is True
        and paired_approval_observed.get("approval_exit_code") == 0
        and paired_approval_observed.get("approval_verification_deferred") is True
        and paired_approval_observed.get("approval_verification_exit_code") is None
        and paired_approval_observed.get("test_file_exists_after_approval") is True,
        observed=paired_approval_observed or command_result_tail(paired_steer_ai_result, limit=5),
        expected=(
            "approving a paired-test-steer dry-run defaults to deferred verification until the source edit arrives"
        ),
    )
    accept_edits_observed = accept_edits_ai_data.get("observed") or {}
    _scenario_check(
        checks,
        "work_ai_accept_edits_auto_applies_preview",
        accept_edits_ai_result.get("exit_code") == 0
        and accept_edits_ai_data.get("passed") is True
        and accept_edits_observed.get("stdout_parseable_json") is True
        and accept_edits_observed.get("inline_approval") == "auto_applied"
        and accept_edits_observed.get("preview_approval_status") == "applied"
        and accept_edits_observed.get("verification_exit_code") == 0,
        observed=accept_edits_observed or command_result_tail(accept_edits_ai_result, limit=5),
        expected=(
            "approval-mode accept-edits applies one dry-run write/edit preview automatically "
            "and keeps JSON work-loop output parseable"
        ),
    )
    accept_edits_paired = accept_edits_observed.get("paired_test_first") or {}
    _scenario_check(
        checks,
        "work_ai_accept_edits_defers_paired_test_first_verification",
        accept_edits_ai_result.get("exit_code") == 0
        and accept_edits_ai_data.get("passed") is True
        and accept_edits_paired.get("inline_approval") == "auto_applied"
        and accept_edits_paired.get("preview_defer_verify_on_approval") is True
        and accept_edits_paired.get("apply_verification_deferred") is True
        and accept_edits_paired.get("verification_exit_code_present") is False,
        observed=accept_edits_paired or command_result_tail(accept_edits_ai_result, limit=5),
        expected=(
            "approval-mode accept-edits auto-applies paired-test-steer test previews "
            "with verification deferred until the source edit lands"
        ),
    )
    accept_edits_batch = accept_edits_observed.get("paired_write_batch") or {}
    _scenario_check(
        checks,
        "work_ai_accept_edits_auto_approves_paired_write_batch",
        accept_edits_ai_result.get("exit_code") == 0
        and accept_edits_ai_data.get("passed") is True
        and accept_edits_batch.get("action_type") == "batch"
        and accept_edits_batch.get("inline_approval") == "auto_applied"
        and accept_edits_batch.get("inline_approval_count") == 2
        and accept_edits_batch.get("preview_paths")
        == ["tests/test_accept_batch.py", "src/mew/accept_batch.py"]
        and accept_edits_batch.get("test_verification_deferred") is True
        and accept_edits_batch.get("source_verification_exit_code") == 0,
        observed=accept_edits_batch or command_result_tail(accept_edits_ai_result, limit=5),
        expected=(
            "approval-mode accept-edits can preview and approve a paired tests/** + src/mew/** "
            "write batch as one guarded group"
        ),
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
        "work_approve_all_pending_writes",
        approve_all_first_result.get("exit_code") == 0
        and approve_all_second_result.get("exit_code") == 0
        and approve_all_result.get("exit_code") == 0
        and ((approve_all_first_data.get("tool_call") or {}).get("result") or {}).get("dry_run") is True
        and ((approve_all_second_data.get("tool_call") or {}).get("result") or {}).get("dry_run") is True
        and approve_all_data.get("count") == 2
        and (approve_all_first_apply.get("result") or {}).get("verification_deferred") is True
        and "verification_exit_code" not in (approve_all_first_apply.get("result") or {})
        and (approve_all_second_apply.get("result") or {}).get("verification_exit_code") == 0
        and (workspace / "batch-one.md").read_text(encoding="utf-8") == "batch one\n"
        and (workspace / "batch-two.md").read_text(encoding="utf-8") == "batch two\n",
        observed={
            "first": approve_all_first_data.get("tool_call"),
            "second": approve_all_second_data.get("tool_call"),
            "approval": approve_all_data,
        },
        expected="approve-all applies multiple pending dry-run writes with one command",
    )
    defer_verify_approval = (((defer_verify_resume_data.get("resume") or {}).get("pending_approvals") or [{}])[0])
    defer_verify_apply = defer_verify_approve_data.get("tool_call") or {}
    defer_verify_apply_result = defer_verify_apply.get("result") or {}
    _scenario_check(
        checks,
        "work_approve_tool_can_defer_verification",
        defer_verify_task_result.get("exit_code") == 0
        and defer_verify_start_result.get("exit_code") == 0
        and defer_verify_write_result.get("exit_code") == 0
        and defer_verify_resume_result.get("exit_code") == 0
        and defer_verify_approve_result.get("exit_code") == 0
        and ((defer_verify_write_data.get("tool_call") or {}).get("result") or {}).get("dry_run") is True
        and "--defer-verify" in (defer_verify_approval.get("cli_defer_verify_hint") or "")
        and defer_verify_apply_result.get("verification_deferred") is True
        and "verification_exit_code" not in defer_verify_apply_result
        and (workspace / "defer-verify.md").read_text(encoding="utf-8") == "after\n",
        observed={
            "tool_call_id": defer_verify_tool_id,
            "cli_defer_verify_hint": defer_verify_approval.get("cli_defer_verify_hint"),
            "verification_deferred": defer_verify_apply_result.get("verification_deferred"),
            "verification_exit_code_present": "verification_exit_code" in defer_verify_apply_result,
            "content": (workspace / "defer-verify.md").read_text(encoding="utf-8"),
        },
        expected="approve-tool --defer-verify applies one pending write without running the default verifier",
    )
    _scenario_check(
        checks,
        "work_reply_file_updates_follow_snapshot",
        reply_start_result.get("exit_code") == 0
        and reply_schema_result.get("exit_code") == 0
        and (reply_schema_data.get("reply_template") or {}).get("session_id") == reply_session.get("id")
        and reply_file_result.get("exit_code") == 0
        and any(action.get("type") == "steer" for action in reply_file_data.get("applied") or [])
        and any(action.get("type") == "followup" for action in reply_file_data.get("applied") or [])
        and reply_snapshot_data.get("mode") == "reply_file"
        and reply_snapshot_data.get("session_id") == reply_session.get("id")
        and ((reply_snapshot_data.get("resume") or {}).get("pending_steer") or {}).get("source") == "reply_file"
        and ((reply_snapshot_data.get("resume") or {}).get("pending_steer") or {}).get("text")
        == "dogfood observer steer"
        and (((reply_snapshot_data.get("resume") or {}).get("queued_followups") or [{}])[0]).get("text")
        == "dogfood observer follow-up",
        observed={"schema": reply_schema_data, "reply": reply_file_data, "snapshot": reply_snapshot_data},
        expected="reply-schema is session-specific and reply-file rewrites steer/follow-up snapshot state",
    )
    _scenario_check(
        checks,
        "work_reply_file_approves_pending_write",
        reply_approve_start_result.get("exit_code") == 0
        and reply_approve_write_result.get("exit_code") == 0
        and reply_approve_snapshot_result.get("exit_code") == 0
        and not (reply_approve_snapshot_result.get("stdout") or "")
        and not (reply_approve_snapshot_result.get("stderr") or "")
        and "Next CLI controls" not in (reply_approve_snapshot_result.get("stdout") or "")
        and reply_approve_status_result.get("exit_code") == 0
        and reply_approve_result.get("exit_code") == 0
        and ((reply_approve_write_data.get("tool_call") or {}).get("result") or {}).get("dry_run") is True
        and reply_approve_snapshot_data.get("stop_reason") == "snapshot_refresh"
        and reply_approve_status_data.get("status") in ("fresh", "working")
        and (reply_approve_status_data.get("producer_health") or {}).get("state") in ("fresh", "working")
        and isinstance(reply_approve_status_data.get("producer_alive"), bool)
        and isinstance(reply_approve_status_data.get("heartbeat_age_seconds"), (int, float))
        and ((reply_approve_snapshot_data.get("pending_approvals") or [{}])[0]).get("tool_call_id")
        == reply_approve_tool_id
        and ((reply_approve_snapshot_data.get("reply_template") or {}).get("actions") or [{}])[0]
        == {"type": "approve", "tool_call_id": reply_approve_tool_id}
        and any(action.get("type") == "approve_all" for action in reply_approve_snapshot_data.get("supported_actions") or [])
        and any(action.get("type") == "approve" for action in reply_approve_data.get("applied") or [])
        and (workspace / "reply-approved.md").read_text(encoding="utf-8") == "reply approved\n",
        observed={
            "write": reply_approve_write_data.get("tool_call"),
            "status": {
                "status": reply_approve_status_data.get("status"),
                "producer_alive": reply_approve_status_data.get("producer_alive"),
                "heartbeat_age_seconds": reply_approve_status_data.get("heartbeat_age_seconds"),
                "snapshot_path": reply_approve_status_data.get("snapshot_path"),
            },
            "snapshot": {
                "stop_reason": reply_approve_snapshot_data.get("stop_reason"),
                "pending_approvals": reply_approve_snapshot_data.get("pending_approvals"),
                "reply_template": reply_approve_snapshot_data.get("reply_template"),
                "supported_actions": reply_approve_snapshot_data.get("supported_actions"),
            },
            "reply": reply_approve_data,
        },
        expected="reply-file approve applies a pending dry-run write from a zero-step follow snapshot",
    )
    _scenario_check(
        checks,
        "work_follow_snapshot_surfaces_running_output",
        running_output_task_result.get("exit_code") == 0
        and running_output_start_result.get("exit_code") == 0
        and running_output_snapshot_result.get("exit_code") == 0
        and not (running_output_snapshot_result.get("stdout") or "")
        and not (running_output_snapshot_result.get("stderr") or "")
        and (running_output_task_data.get("id") or (running_output_task_data.get("task") or {}).get("id"))
        == running_output_task_id
        and running_output_snapshot_data.get("session_updated_at") == running_output_observed_session_updated_at
        and any(
            command.get("output_running") is True
            and "dogfood partial output" in (command.get("stdout") or "")
            for command in running_output_commands
        )
        and "still running" in running_output_tail,
        observed={
            "task": running_output_task_data,
            "snapshot": {
                "session_updated_at": running_output_snapshot_data.get("session_updated_at"),
                "commands": running_output_commands,
                "cell_tail": running_output_tail,
            },
        },
        expected="zero-step follow snapshots include bounded output for running command/test cells",
    )
    _scenario_check(
        checks,
        "work_task_done_json_returns_completed_task",
        task_done_json_seed_result.get("exit_code") == 0
        and (task_done_json_seed_data.get("task") or {}).get("id") == 8
        and task_done_json_result.get("exit_code") == 0
        and task_done_json_data.get("id") == 8
        and task_done_json_data.get("completion_summary") == "dogfood verified"
        and (task_done_json_data.get("task") or {}).get("id") == 8
        and (task_done_json_data.get("task") or {}).get("status") == "done"
        and "dogfood verified" in ((task_done_json_data.get("task") or {}).get("notes") or ""),
        observed={
            "seed_id": (task_done_json_seed_data.get("task") or {}).get("id"),
            "done_id": task_done_json_data.get("id"),
            "status": task_done_json_data.get("status"),
            "completion_summary": task_done_json_data.get("completion_summary"),
        },
        expected="task done --json returns the completed task without text parsing",
    )
    _scenario_check(
        checks,
        "work_done_task_closed_resume_suggests_reopen",
        task_done_json_result.get("exit_code") == 0
        and (task_done_json_data.get("task") or {}).get("status") == "done"
        and done_resume_json_result.get("exit_code") == 0
        and "task #8 is done" in done_resume_next_action
        and "task update 8 --status ready" in done_resume_next_action
        and "work 8 --start-session" not in done_resume_next_action
        and any("task update 8 --status ready" in control for control in done_resume_controls)
        and not any("work 8 --start-session" in control for control in done_resume_controls),
        observed={
            "done": task_done_json_data,
            "next_action": done_resume_next_action,
            "controls": done_resume_controls,
        },
        expected="closed resumes for done tasks point at task reopen instead of an invalid start-session command",
    )
    _scenario_check(
        checks,
        "work_interrupt_submit_sets_boundary_stop_and_steer",
        interrupt_start_result.get("exit_code") == 0
        and interrupt_submit_result.get("exit_code") == 0
        and (interrupt_submit_data.get("stop_request") or {}).get("action") == "interrupt_submit"
        and (interrupt_submit_data.get("pending_steer") or {}).get("text") == "dogfood interrupt submit"
        and ((interrupt_resume_data.get("resume") or {}).get("stop_request") or {}).get("action")
        == "interrupt_submit"
        and ((interrupt_resume_data.get("resume") or {}).get("pending_steer") or {}).get("source")
        == "interrupt_submit",
        observed={"submit": interrupt_submit_data, "resume": interrupt_resume_data},
        expected="interrupt-submit records a boundary stop request and next-step steer",
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
        observed={
            "phase": (resume_data.get("resume") or {}).get("phase"),
            "pending_approval_count": len((resume_data.get("resume") or {}).get("pending_approvals") or []),
            "has_stop_request": bool((resume_data.get("resume") or {}).get("stop_request")),
        },
        expected="resume reports phase=stop_requested",
    )
    _scenario_check(
        checks,
        "work_resume_surfaces_pending_diff_preview",
        resume_result.get("exit_code") == 0
        and any("Diff preview" in preview and "native work sessions" in preview for preview in pending_diff_previews),
        observed=pending_diff_previews,
        expected="resume pending approvals include readable diff previews",
    )
    _scenario_check(
        checks,
        "work_resume_surfaces_command_output",
        resume_result.get("exit_code") == 0
        and any("work test ok" in (command.get("stdout") or "") for command in resume_commands)
        and any("work command ok" in (command.get("stdout") or "") for command in resume_commands),
        observed=resume_commands,
        expected="resume commands include clipped stdout previews",
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
        "work_session_steer_queues_pending_guidance",
        steer_result.get("exit_code") == 0
        and (steer_data.get("pending_steer") or {}).get("text") == "dogfood steer"
        and chat_steer_result.get("exit_code") == 0
        and "queued steer for work session #1: dogfood chat steer" in (chat_steer_result.get("stdout") or "")
        and (session.get("pending_steer") or {}).get("text") == "dogfood chat steer"
        and ((resume_data.get("resume") or {}).get("pending_steer") or {}).get("text") == "dogfood chat steer",
        observed={
            "cli": steer_data,
            "chat": command_result_tail(chat_steer_result),
            "pending_steer": session.get("pending_steer"),
            "resume_pending_steer": (resume_data.get("resume") or {}).get("pending_steer"),
        },
        expected="CLI and chat can queue one-time steer guidance for the active session",
    )
    queued_followups = session.get("queued_followups") or []
    resume_followups = (resume_data.get("resume") or {}).get("queued_followups") or []
    _scenario_check(
        checks,
        "work_session_queue_followup_queues_fifo_input",
        queue_followup_result.get("exit_code") == 0
        and (queue_followup_data.get("queued_followup") or {}).get("text") == "dogfood queued follow-up"
        and chat_queue_result.get("exit_code") == 0
        and "queued follow-up for work session #1: dogfood chat follow-up" in (chat_queue_result.get("stdout") or "")
        and any(item.get("text") == "dogfood queued follow-up" for item in queued_followups)
        and any(item.get("text") == "dogfood chat follow-up" for item in queued_followups)
        and any(item.get("text") == "dogfood chat follow-up" for item in resume_followups),
        observed={
            "cli": queue_followup_data,
            "chat": command_result_tail(chat_queue_result),
            "queued_followups": queued_followups,
            "resume_queued_followups": resume_followups,
        },
        expected="CLI and chat can queue FIFO follow-up input for the active session",
    )
    _scenario_check(
        checks,
        "work_resume_surfaces_working_memory",
        resume_result.get("exit_code") == 0
        and working_memory.get("hypothesis") == "Dogfood work session has readable reentry state."
        and working_memory.get("next_step") == "Inspect resume before continuing."
        and working_memory.get("open_questions") == ["Does resume show this compact memory?"],
        observed=working_memory,
        expected="resume includes compact working memory from resident THINK output",
    )
    _scenario_check(
        checks,
        "work_resume_surfaces_user_preferences",
        resume_result.get("exit_code") == 0
        and "Prefer compact dogfood reentry." in " ".join(user_preferences.get("items") or [])
        and "Prefer compact dogfood reentry." in " ".join(running_output_preferences.get("items") or []),
        observed={
            "resume": user_preferences,
            "follow_snapshot": running_output_preferences,
        },
        expected="resume and follow snapshots include durable user preferences",
    )
    _scenario_check(
        checks,
        "work_resume_surfaces_active_typed_memory",
        resume_result.get("exit_code") == 0
        and any(
            item.get("memory_type") == "user"
            and item.get("name") == "Dogfood active recall preference"
            for item in active_memory.get("items") or []
        )
        and any(
            item.get("memory_type") == "project"
            and item.get("name") == "Dogfood active recall project note"
            for item in active_memory.get("items") or []
        ),
        observed={
            "total": active_memory.get("total"),
            "items": [
                {
                    "name": item.get("name"),
                    "memory_type": item.get("memory_type"),
                    "reason": item.get("reason"),
                }
                for item in (active_memory.get("items") or [])
            ],
        },
        expected="resume includes typed user memory and task-relevant project memory",
    )
    _scenario_check(
        checks,
        "workbench_surfaces_tool_journal",
        len(tool_calls) == 12
        and [call.get("tool") for call in tool_calls]
        == [
            "read_file",
            "glob",
            "run_tests",
            "run_command",
            "edit_file",
            "read_file",
            "edit_file",
            "edit_file",
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
            "run_command",
            "edit_file",
            "read_file",
            "edit_file",
            "edit_file",
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
        "metrics_surface_work_session_observations",
        metrics_result.get("exit_code") == 0
        and "Mew observation metrics" in (metrics_result.get("stdout") or "")
        and "sessions: total=" in (metrics_result.get("stdout") or "")
        and "tool_calls: total=" in (metrics_result.get("stdout") or "")
        and "first_tool_start_seconds: count=" in (metrics_result.get("stdout") or ""),
        expected="metrics --kind coding reports work-session reliability and latency observations",
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
        "work_cells_surface_stable_cockpit_rows",
        cells_result.get("exit_code") == 0
        and any(cell.get("kind") == "model_turn" for cell in cells)
        and any(cell.get("kind") == "test" for cell in cells)
        and any(cell.get("kind") == "diff" for cell in cells)
        and any(cell.get("kind") == "approval" for cell in cells),
        observed=cells[:6],
        expected="cells include model, test, diff, and approval cockpit rows",
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
        "chat_surfaces_work_session_diffs",
        chat_diffs_result.get("exit_code") == 0
        and "Work diffs #1 [active] task=#1" in (chat_diffs_result.get("stdout") or "")
        and "Diff preview" in (chat_diffs_result.get("stdout") or ""),
        observed=command_result_tail(chat_diffs_result),
        expected="chat /work-session diffs shows focused diff previews",
    )
    _scenario_check(
        checks,
        "chat_surfaces_work_session_tests",
        chat_tests_result.get("exit_code") == 0
        and "Work tests #1 [active] task=#1" in (chat_tests_result.get("stdout") or "")
        and "work test ok" in (chat_tests_result.get("stdout") or ""),
        observed=command_result_tail(chat_tests_result),
        expected="chat /work-session tests shows focused test output",
    )
    _scenario_check(
        checks,
        "chat_surfaces_work_session_commands",
        chat_commands_result.get("exit_code") == 0
        and "Work commands #1 [active] task=#1" in (chat_commands_result.get("stdout") or "")
        and "work command ok" in (chat_commands_result.get("stdout") or ""),
        observed=command_result_tail(chat_commands_result),
        expected="chat /work-session commands shows focused command output",
    )
    _scenario_check(
        checks,
        "chat_surfaces_work_session_cells",
        chat_cells_result.get("exit_code") == 0
        and "Work cells #1 [active] task=#1" in (chat_cells_result.get("stdout") or "")
        and "model_turn [completed]" in (chat_cells_result.get("stdout") or ""),
        observed=command_result_tail(chat_cells_result),
        expected="chat /work-session cells shows stable cockpit rows",
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
    _scenario_check(
        checks,
        "work_recover_retries_interrupted_run_tests",
        verification_resume_result.get("exit_code") == 0
        and verification_recover_result.get("exit_code") == 0
        and bool(verification_items)
        and verification_items[0].get("action") == "retry_verification"
        and verification_items[0].get("command") == verification_command
        and verification_recovery.get("action") == "retry_tool"
        and verification_recovery.get("tool") == "run_tests"
        and verification_tool_call.get("status") == "completed"
        and ((verification_tool_call.get("result") or {}).get("stdout") or "").find("dogfood verify recovered") >= 0,
        observed={
            "items": verification_items[:1],
            "recovery": verification_recovery,
            "tool_call": {
                "id": verification_tool_call.get("id"),
                "status": verification_tool_call.get("status"),
                "tool": verification_tool_call.get("tool"),
                "exit_code": (verification_tool_call.get("result") or {}).get("exit_code"),
            },
        },
        expected="recover-session can rerun an interrupted run_tests verifier with explicit read and verify gates",
    )
    _scenario_check(
        checks,
        "work_unpaired_source_approval_requires_override",
        unpaired_task_result.get("exit_code") == 0
        and unpaired_start_result.get("exit_code") == 0
        and unpaired_edit_result.get("exit_code") == 0
        and unpaired_reject_result.get("exit_code") != 0
        and "requires a paired tests/** write/edit" in (unpaired_reject_result.get("stderr") or "")
        and unpaired_override_result.get("exit_code") == 0
        and ((unpaired_edit_data.get("tool_call") or {}).get("result") or {}).get("dry_run") is True
        and ((unpaired_override_data.get("tool_call") or {}).get("status") == "completed")
        and (workspace / "src" / "mew" / "dogfood_override.py").read_text(encoding="utf-8")
        == "OVERRIDE = 'new'\n",
        observed={
            "task": unpaired_task_data,
            "edit_tool_id": (unpaired_edit_data.get("tool_call") or {}).get("id"),
            "reject": command_result_tail(unpaired_reject_result, limit=5),
            "override": {
                "approved": (unpaired_override_data.get("approved_tool_call") or {}).get("approval_status"),
                "tool_status": (unpaired_override_data.get("tool_call") or {}).get("status"),
            },
        },
        expected="src/mew approval is blocked without a paired test edit and succeeds only with explicit override",
    )
    return _scenario_report("work-session", workspace, commands, checks)


def _m2_session_id_text(value):
    if value is None:
        return ""
    return str(value).strip().removeprefix("#")


def _m2_latest_work_session(state):
    sessions = [session for session in state.get("work_sessions") or [] if isinstance(session, dict)]
    if not sessions:
        return None
    return max(
        sessions,
        key=lambda session: (
            session.get("updated_at") or session.get("closed_at") or session.get("created_at") or "",
            str(session.get("id") or ""),
        ),
    )


def _m2_find_work_session(state, session_id):
    session_id_text = _m2_session_id_text(session_id)
    if not session_id_text:
        return None
    if session_id_text in {"latest", "last"}:
        return _m2_latest_work_session(state)
    return find_work_session(state, session_id_text)


def _m2_work_sessions_for_task(state, task_id):
    task_id_text = _m2_session_id_text(task_id)
    sessions = []
    for session in state.get("work_sessions") or []:
        if not isinstance(session, dict):
            continue
        if str(session.get("task_id") or "") == task_id_text:
            sessions.append(session)
    return sorted(
        sessions,
        key=lambda session: (
            session.get("created_at") or "",
            session.get("updated_at") or "",
            str(session.get("id") or ""),
        ),
    )


def _m2_command_records(calls, limit=8):
    records = []
    for call in calls or []:
        if not isinstance(call, dict):
            continue
        tool = call.get("tool")
        result = call.get("result") or {}
        parameters = call.get("parameters") or {}
        if tool not in {"run_command", "run_tests"} and "verification_exit_code" not in result:
            continue
        verification = result.get("verification") or {}
        command = result.get("command") or parameters.get("command") or verification.get("command")
        if not command:
            continue
        records.append(
            {
                "tool_call_id": call.get("id"),
                "tool": tool,
                "command": command,
                "exit_code": result.get("exit_code"),
                "verification_exit_code": result.get("verification_exit_code"),
                "status": call.get("status") or "",
            }
        )
    return records[-limit:]


def _m2_approval_counts(calls):
    counts = {"total": 0, "pending": 0, "applied": 0, "rejected": 0, "failed": 0, "indeterminate": 0}
    for call in calls or []:
        if not isinstance(call, dict):
            continue
        result = call.get("result") or {}
        status = call.get("approval_status")
        if not status and not result.get("dry_run"):
            continue
        counts["total"] += 1
        normalized = status or "pending"
        if normalized in counts:
            counts[normalized] += 1
        else:
            counts["indeterminate"] += 1
    return counts


def _m2_latest_verification(calls):
    for call in reversed(calls or []):
        if not isinstance(call, dict):
            continue
        result = call.get("result") or {}
        verification = result.get("verification") or {}
        exit_code = None
        command = ""
        source = ""
        if "verification_exit_code" in result:
            exit_code = result.get("verification_exit_code")
            command = verification.get("command") or result.get("command") or (call.get("parameters") or {}).get("command") or ""
            source = "approval_verification"
        elif call.get("tool") in {"run_tests", "run_command"} and result.get("exit_code") is not None:
            exit_code = result.get("exit_code")
            command = result.get("command") or (call.get("parameters") or {}).get("command") or ""
            source = call.get("tool") or "command"
        else:
            continue
        status = "passed" if exit_code == 0 else "failed"
        return {
            "status": status,
            "exit_code": exit_code,
            "command": command,
            "tool_call_id": call.get("id"),
            "source": source,
            "finished_at": call.get("finished_at") or "",
        }
    return {"status": "unknown", "exit_code": None, "command": "", "tool_call_id": None, "source": "", "finished_at": ""}


def _m2_verification_from_task_run(run):
    if not isinstance(run, dict):
        return None
    exit_code = run.get("exit_code")
    status = "passed" if exit_code == 0 else "failed"
    return {
        "status": status,
        "exit_code": exit_code,
        "command": run.get("command") or "",
        "tool_call_id": None,
        "verification_run_id": run.get("id"),
        "source": "task_verification",
        "reason": run.get("reason") or "",
        "finished_at": run.get("finished_at") or run.get("updated_at") or "",
    }


def _m2_latest_task_verification(state, task_id):
    task_id_text = str(task_id or "")
    if not task_id_text:
        return None
    for run in reversed((state or {}).get("verification_runs") or []):
        if str(run.get("task_id") or "") == task_id_text:
            return _m2_verification_from_task_run(run)
    return None


def _m2_verification_finished_at(verification):
    return str((verification or {}).get("finished_at") or "")


def _m2_choose_m2_verification(work_verification, task_verification):
    work_verification = work_verification or {}
    if not task_verification:
        return work_verification
    if (work_verification.get("status") or "unknown") == "unknown":
        return task_verification
    if task_verification.get("status") == "passed" and work_verification.get("status") != "passed":
        return task_verification
    if _m2_verification_finished_at(task_verification) >= _m2_verification_finished_at(work_verification):
        return task_verification
    return work_verification


def _m2_call_has_failure_or_interruption(call):
    if not isinstance(call, dict):
        return False
    if call.get("status") in {"failed", "interrupted"}:
        return True
    result = call.get("result") or {}
    verification = result.get("verification") or {}
    exit_values = [
        result.get("exit_code"),
        result.get("verification_exit_code"),
        verification.get("exit_code"),
    ]
    return any(value not in (None, 0) for value in exit_values)


def _m2_turn_has_failure_or_interruption(turn):
    if not isinstance(turn, dict):
        return False
    return bool(turn.get("status") in {"failed", "interrupted"} or turn.get("error"))


def _m2_resume_gate_status(gate):
    if not gate:
        return "unknown"
    required = (
        gate.get("changed_or_pending_work"),
        gate.get("risk_or_interruption_preserved"),
        gate.get("runnable_next_action"),
        gate.get("continuity_usable"),
        gate.get("verification_after_resume_candidate"),
    )
    if all(required):
        return "proved"
    if any(value is True for value in required):
        return "not_proved"
    return "unknown"


def _m2_resume_gate_evidence(resume, calls, approval_counts, verification, resume_command, turns=None):
    resume = resume or {}
    continuity = resume.get("continuity") or {}
    calls = list(calls or [])
    turns = list(turns or [])
    approval_counts = approval_counts or {}
    verification = verification or {}
    gate = {
        "status": "unknown",
        "resume_command": resume_command or "",
        "continuity_score": continuity.get("score") or "",
        "continuity_status": continuity.get("status") or "",
        "changed_or_pending_work": bool(resume.get("files_touched") or (approval_counts.get("total") or 0) > 0),
        "risk_or_interruption_preserved": bool(
            resume.get("unresolved_failure")
            or resume.get("failures")
            or any(_m2_call_has_failure_or_interruption(call) for call in calls)
            or any(_m2_turn_has_failure_or_interruption(turn) for turn in turns)
        ),
        "runnable_next_action": bool(str(resume.get("next_action") or "").strip()),
        "continuity_usable": continuity.get("status") in {"strong", "usable"},
        "verification_after_resume_candidate": verification.get("status") == "passed",
        "evidence_gap": [],
    }
    gap_labels = {
        "changed_or_pending_work": "resume did not expose changed or pending work",
        "risk_or_interruption_preserved": "resume did not preserve an interruption, failure, or recovery risk",
        "runnable_next_action": "resume did not expose a runnable next action",
        "continuity_usable": "continuity was not strong or usable",
        "verification_after_resume_candidate": "no passing verification candidate was recorded",
    }
    gate["evidence_gap"] = [label for key, label in gap_labels.items() if not gate.get(key)]
    gate["status"] = _m2_resume_gate_status(gate)
    return gate


def _m2_session_risk_preserved(resume, calls, turns):
    resume = resume or {}
    return bool(
        resume.get("unresolved_failure")
        or resume.get("failures")
        or any(_m2_call_has_failure_or_interruption(call) for call in calls or [])
        or any(_m2_turn_has_failure_or_interruption(turn) for turn in turns or [])
    )


def _m2_normalized_work_path(path):
    return str(path or "").replace("\\", "/").lstrip("./")


def _m2_call_path(call):
    parameters = (call or {}).get("parameters") or {}
    result = (call or {}).get("result") or {}
    return parameters.get("path") or result.get("path") or ""


def _m2_path_is_tests(path):
    normalized = _m2_normalized_work_path(path)
    return normalized == "tests" or normalized.startswith("tests/") or "/tests/" in normalized


def _m2_path_is_mew_source(path):
    normalized = _m2_normalized_work_path(path)
    return normalized.startswith("src/mew/") or "/src/mew/" in normalized


def _m2_paired_write_batch_evidence(turns, calls):
    calls_by_id = {call.get("id"): call for call in calls or []}
    for turn in turns or []:
        action = turn.get("action") or ((turn.get("action_plan") or {}).get("action") or {})
        if (action.get("type") or action.get("tool")) != "batch":
            continue
        tool_call_ids = [tool_id for tool_id in turn.get("tool_call_ids") or [] if tool_id in calls_by_id]
        write_calls = [
            calls_by_id[tool_id]
            for tool_id in tool_call_ids
            if (calls_by_id[tool_id].get("tool") or "") in ("write_file", "edit_file")
        ]
        if len(write_calls) < 2:
            continue
        source_paths = []
        test_paths = []
        for call in write_calls:
            path = _m2_call_path(call)
            if _m2_path_is_mew_source(path) and path not in source_paths:
                source_paths.append(path)
            if _m2_path_is_tests(path) and path not in test_paths:
                test_paths.append(path)
        if not source_paths or not test_paths:
            continue
        return {
            "status": "proved",
            "turn_id": turn.get("id"),
            "tool_call_ids": [call.get("id") for call in write_calls],
            "source_paths": source_paths[:DOGFOOD_OBSERVED_LIST_LIMIT],
            "test_paths": test_paths[:DOGFOOD_OBSERVED_LIST_LIMIT],
            "preview_count": len(write_calls),
            "applied_count": sum(1 for call in write_calls if call.get("approval_status") == "applied"),
            "forced_preview": all(((call.get("result") or {}).get("dry_run") is True) for call in write_calls),
        }
    return {"status": "not_observed"}


def _m2_task_chain_resume_gate_evidence(session_infos, resume_command, task_verification=None):
    session_infos = list(session_infos or [])
    if not session_infos:
        return {
            "status": "unknown",
            "resume_command": resume_command or "",
            "evidence_gap": ["no work sessions were found for the task"],
        }
    latest = session_infos[-1]
    latest_resume = latest.get("resume") or {}
    continuity = latest_resume.get("continuity") or {}
    risk_indices = [index for index, info in enumerate(session_infos) if info.get("risk_preserved")]
    passed_indices = [
        index
        for index, info in enumerate(session_infos)
        if (info.get("verification") or {}).get("status") == "passed"
    ]
    task_verification_passed = (task_verification or {}).get("status") == "passed"
    verification_after_resume = any(
        passed_index >= risk_index for risk_index in risk_indices for passed_index in passed_indices
    ) or (bool(risk_indices) and task_verification_passed)
    approval_total = sum((info.get("approval_counts") or {}).get("total", 0) for info in session_infos)
    gate = {
        "status": "unknown",
        "resume_command": resume_command or "",
        "continuity_score": continuity.get("score") or "",
        "continuity_status": continuity.get("status") or "",
        "changed_or_pending_work": bool(
            approval_total
            or any((info.get("resume") or {}).get("files_touched") for info in session_infos)
        ),
        "risk_or_interruption_preserved": bool(risk_indices),
        "runnable_next_action": bool(str(latest_resume.get("next_action") or "").strip() or passed_indices),
        "continuity_usable": continuity.get("status") in {"strong", "usable"},
        "verification_after_resume_candidate": verification_after_resume,
        "evidence_mode": "task_chain",
        "risk_session_ids": [session_infos[index].get("session_id") for index in risk_indices],
        "verification_session_ids": [session_infos[index].get("session_id") for index in passed_indices],
        "verification_run_ids": (
            [task_verification.get("verification_run_id")]
            if task_verification_passed and task_verification.get("verification_run_id") is not None
            else []
        ),
        "evidence_gap": [],
    }
    gap_labels = {
        "changed_or_pending_work": "task chain did not expose changed or pending work",
        "risk_or_interruption_preserved": "task chain did not preserve an interruption, failure, or recovery risk",
        "runnable_next_action": "task chain did not expose a runnable next action",
        "continuity_usable": "latest continuity was not strong or usable",
        "verification_after_resume_candidate": "no passing verification was recorded after a risk session",
    }
    gate["evidence_gap"] = [label for key, label in gap_labels.items() if not gate.get(key)]
    gate["status"] = _m2_resume_gate_status(gate)
    return gate


def build_m2_mew_task_chain_evidence(state, task_id):
    task_id_text = _m2_session_id_text(task_id)
    task = find_task(state, task_id_text)
    sessions = _m2_work_sessions_for_task(state, task_id_text)
    if not sessions:
        return {
            "status": "missing",
            "requested_session_id": f"task:{task_id_text}",
            "source_state": str(STATE_FILE),
        }

    session_infos = []
    combined_calls = []
    combined_turns = []
    for session in sessions:
        calls = list(session.get("tool_calls") or [])
        turns = list(session.get("model_turns") or [])
        resume = build_work_session_resume(session, task=task, limit=3, state=state) or {}
        approval_counts = _m2_approval_counts(calls)
        verification = _m2_latest_verification(calls)
        session_infos.append(
            {
                "session_id": session.get("id"),
                "resume": resume,
                "calls": calls,
                "turns": turns,
                "approval_counts": approval_counts,
                "verification": verification,
                "risk_preserved": _m2_session_risk_preserved(resume, calls, turns),
            }
        )
        combined_calls.extend(calls)
        combined_turns.extend(turns)

    latest_session = sessions[-1]
    latest_resume = session_infos[-1].get("resume") or {}
    latest_effort = build_work_session_effort(latest_session) or {}
    continuity = latest_resume.get("continuity") or {}
    approval_counts = {
        key: sum((info.get("approval_counts") or {}).get(key, 0) for info in session_infos)
        for key in ("total", "pending", "applied", "rejected", "failed", "indeterminate")
    }
    work_verification = _m2_latest_verification(combined_calls)
    paired_write_batch = _m2_paired_write_batch_evidence(combined_turns, combined_calls)
    task_id_value = latest_session.get("task_id") or (task or {}).get("id") or task_id_text
    task_verification = _m2_latest_task_verification(state, task_id_value)
    verification = _m2_choose_m2_verification(work_verification, task_verification)
    resume_command = f"mew work {task_id_value} --session --resume --allow-read ."
    return {
        "status": "found",
        "evidence_mode": "task_chain",
        "source_state": str(STATE_FILE),
        "requested_session_id": f"task:{task_id_text}",
        "session_argument": f"task:{task_id_text}",
        "work_session_id": latest_session.get("id"),
        "work_session_ids": [session.get("id") for session in sessions],
        "task_id": task_id_value,
        "task_title": (task or {}).get("title") or latest_session.get("title") or "",
        "task_description": (task or {}).get("description") or "",
        "session_status": latest_session.get("status") or "",
        "phase": latest_session.get("phase") or "",
        "created_at": sessions[0].get("created_at") or "",
        "updated_at": latest_session.get("updated_at") or "",
        "model_turns": len(combined_turns),
        "tool_calls": len(combined_calls),
        "effort": {
            "wall_elapsed_seconds": latest_effort.get("wall_elapsed_seconds"),
            "observed_active_seconds": latest_effort.get("observed_active_seconds"),
            "tool_seconds": latest_effort.get("tool_seconds"),
            "model_seconds": latest_effort.get("model_seconds"),
            "pressure": latest_effort.get("pressure") or "",
        },
        "commands_or_tests_run": _m2_command_records(combined_calls),
        "approval_counts": approval_counts,
        "paired_write_batch": paired_write_batch,
        "verification": verification,
        "resume_command": resume_command,
        "resume_gate": _m2_task_chain_resume_gate_evidence(
            session_infos,
            resume_command,
            task_verification=task_verification,
        ),
        "continuity": {
            "score": continuity.get("score") or "",
            "status": continuity.get("status") or "",
            "missing": continuity.get("missing") or [],
            "recommendation": (continuity.get("recommendation") or {}).get("summary") or "",
        },
    }


def build_m2_mew_run_evidence(state, session_id):
    session_id_text = _m2_session_id_text(session_id)
    if not session_id_text:
        return None
    if session_id_text.startswith("task:"):
        return build_m2_mew_task_chain_evidence(state, session_id_text.removeprefix("task:"))
    session = _m2_find_work_session(state, session_id_text)
    if not session:
        return {
            "status": "missing",
            "requested_session_id": session_id_text,
            "source_state": str(STATE_FILE),
        }

    task = find_task(state, session.get("task_id"))
    calls = list(session.get("tool_calls") or [])
    turns = list(session.get("model_turns") or [])
    defaults = session.get("default_options") or {}
    resume = build_work_session_resume(session, task=task, limit=3, state=state) or {}
    effort = build_work_session_effort(session) or {}
    approval_counts = _m2_approval_counts(calls)
    work_verification = _m2_latest_verification(calls)
    task_id = session.get("task_id") or (task or {}).get("id")
    task_verification = _m2_latest_task_verification(state, task_id)
    verification = _m2_choose_m2_verification(work_verification, task_verification)
    continuity = resume.get("continuity") or {}
    paired_write_batch = _m2_paired_write_batch_evidence(turns, calls)
    resume_command = (
        f"mew work {task_id} --session --resume --allow-read ."
        if task_id
        else "mew work --session --resume --allow-read ."
    )
    return {
        "status": "found",
        "source_state": str(STATE_FILE),
        "requested_session_id": session_id_text,
        "session_argument": session_id_text,
        "work_session_id": session.get("id"),
        "task_id": task_id,
        "task_title": (task or {}).get("title") or session.get("title") or "",
        "task_description": (task or {}).get("description") or "",
        "session_status": session.get("status") or "",
        "phase": session.get("phase") or "",
        "created_at": session.get("created_at") or "",
        "updated_at": session.get("updated_at") or "",
        "model_turns": len(turns),
        "tool_calls": len(calls),
        "approval_mode": defaults.get("approval_mode") or "default",
        "default_permission_posture": {
            "allow_read": bool(defaults.get("allow_read")),
            "allow_write": bool(defaults.get("allow_write")),
            "allow_shell": bool(defaults.get("allow_shell")),
            "allow_verify": bool(defaults.get("allow_verify")),
        },
        "effort": {
            "wall_elapsed_seconds": effort.get("wall_elapsed_seconds"),
            "observed_active_seconds": effort.get("observed_active_seconds"),
            "tool_seconds": effort.get("tool_seconds"),
            "model_seconds": effort.get("model_seconds"),
            "pressure": effort.get("pressure") or "",
        },
        "commands_or_tests_run": _m2_command_records(calls),
        "approval_counts": approval_counts,
        "paired_write_batch": paired_write_batch,
        "verification": verification,
        "resume_command": resume_command,
        "resume_gate": _m2_resume_gate_evidence(
            resume,
            calls,
            approval_counts,
            verification,
            resume_command,
            turns=turns,
        ),
        "continuity": {
            "score": continuity.get("score") or "",
            "status": continuity.get("status") or "",
            "missing": continuity.get("missing") or [],
            "recommendation": (continuity.get("recommendation") or {}).get("summary") or "",
        },
    }


def _m2_apply_mew_run_evidence(protocol, evidence):
    if not evidence:
        return protocol
    protocol["mew_run_evidence"] = evidence
    comparison = protocol.setdefault("comparison_result", {})
    run_summaries = comparison.setdefault("run_summaries", {})
    mew_summary = run_summaries.setdefault("mew", {})
    if evidence.get("status") != "found":
        mew_summary.update(
            {
                "summary": f"requested mew work session {evidence.get('requested_session_id')} was not found",
                "verification_result": "unknown",
                "friction_summary": "no mew-side evidence loaded",
                "preference_signal": "blocked until a valid mew work session id is provided",
            }
        )
        comparison["next_blocker"] = "Provide a valid mew work session id and rerun the M2 comparative dogfood."
        return protocol

    effort = evidence.get("effort") or {}
    approvals = evidence.get("approval_counts") or {}
    verification = evidence.get("verification") or {}
    continuity = evidence.get("continuity") or {}
    wall = effort.get("wall_elapsed_seconds")
    active = effort.get("observed_active_seconds")
    session_ids = evidence.get("work_session_ids") or []
    session_label = (
        f"task-chain sessions {','.join(f'#{session_id}' for session_id in session_ids)}"
        if session_ids
        else f"session #{evidence.get('work_session_id')}"
    )
    mew_summary.update(
        {
            "summary": (
                f"{session_label} task #{evidence.get('task_id')} "
                f"status={evidence.get('session_status')} phase={evidence.get('phase')} "
                f"turns={evidence.get('model_turns')} tools={evidence.get('tool_calls')} "
                f"wall={wall}s active={active}s"
            ),
            "verification_result": (
                f"{verification.get('status')} exit={verification.get('exit_code')} "
                f"command={verification.get('command') or '-'}"
            ),
            "friction_summary": (
                f"approvals total={approvals.get('total', 0)} applied={approvals.get('applied', 0)} "
                f"rejected={approvals.get('rejected', 0)} failed={approvals.get('failed', 0)}; "
                f"effort_pressure={effort.get('pressure') or 'unknown'}"
            ),
            "preference_signal": (
                f"continuity={continuity.get('score') or '-'} {continuity.get('status') or 'unknown'}; "
                f"resume=`{evidence.get('resume_command')}`"
            ),
        }
    )
    fresh_cli_summary = ((run_summaries.get("fresh_cli") or {}).get("summary") or "").strip()
    if not comparison.get("next_blocker"):
        comparison["next_blocker"] = (
            "Review the paired evidence and choose the resident preference outcome."
            if fresh_cli_summary
            else "Run the matching fresh_cli task and fill its run summary."
        )
    comparison["notes"] = comparison.get("notes") or (
        f"Mew-side evidence was prefilled from {session_label}."
    )
    resume_behavior = protocol.setdefault("resume_behavior", {})
    resume_behavior["mew_resume_command"] = evidence.get("resume_command") or resume_behavior.get("mew_resume_command", "")
    resume_behavior["could_resume_without_user_rebrief"] = (
        continuity.get("status") in {"strong", "usable"} if continuity.get("status") else None
    )
    resume_behavior["risky_or_missing_context"] = continuity.get("missing") or []
    resume_gate = evidence.get("resume_gate") or {}
    if resume_gate:
        gate = protocol.setdefault("interruption_resume_gate", {})
        gate["mew"] = resume_gate
    friction_counts = protocol.setdefault("friction_counts", {})
    friction_counts["approval_confusions"] = approvals.get("rejected", 0) + approvals.get("failed", 0)
    friction_counts["verification_confusions"] = 1 if verification.get("status") == "failed" else 0
    return protocol


def _m2_merge_mapping(base, updates):
    if not isinstance(base, dict) or not isinstance(updates, dict):
        return base
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _m2_merge_mapping(base[key], value)
        else:
            base[key] = value
    return base


def _m2_flat_fresh_cli_summary(report):
    if not isinstance(report, dict):
        return {}
    summary = str(report.get("task_summary") or report.get("summary") or "").strip()
    verification = report.get("verification")
    verification_result = ""
    if isinstance(verification, list):
        verification_parts = []
        for item in verification:
            if not isinstance(item, dict):
                continue
            command = str(item.get("command") or "").strip()
            exit_code = item.get("exit_code")
            item_summary = str(item.get("summary") or "").strip()
            if command or exit_code is not None or item_summary:
                verification_parts.append(
                    f"{command} exit={exit_code} {item_summary}".strip()
                )
        verification_result = "; ".join(verification_parts)
    elif isinstance(verification, dict):
        command = str(verification.get("command") or "").strip()
        exit_code = verification.get("exit_code")
        item_summary = str(verification.get("summary") or "").strip()
        verification_result = f"{command} exit={exit_code} {item_summary}".strip()
    elif verification is not None:
        verification_result = str(verification).strip()

    friction_summary = str(report.get("friction_summary") or "").strip()
    if not friction_summary and "manual_rebrief_needed" in report:
        friction_summary = f"manual_rebrief_needed={bool(report.get('manual_rebrief_needed'))}"

    preference_signal = str(report.get("preference_signal") or "").strip()
    flat = {}
    if summary:
        flat["summary"] = summary
    if verification_result:
        flat["verification_result"] = verification_result
    if friction_summary:
        flat["friction_summary"] = friction_summary
    if preference_signal:
        flat["preference_signal"] = preference_signal
    return flat


def _m2_report_bool(value):
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "y"}:
        return True
    if normalized in {"0", "false", "no", "n"}:
        return False
    return None


def _m2_normalize_fresh_cli_context_mode(value):
    normalized = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "fresh_restart": "true_restart",
        "fresh_session": "true_restart",
        "new_session": "true_restart",
        "restart": "true_restart",
        "true_fresh": "true_restart",
        "resumed_session": "same_session_resume",
        "same_session": "same_session_resume",
        "session_resume": "same_session_resume",
        "resume": "same_session_resume",
        "resumed": "same_session_resume",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized in M2_FRESH_CLI_CONTEXT_MODES:
        return normalized
    return ""


def _m2_fresh_cli_context_from_report(report):
    if not isinstance(report, dict):
        return {}
    fresh_cli = report.get("fresh_cli") or report.get("fresh_cli_summary") or {}
    if not isinstance(fresh_cli, dict):
        fresh_cli = {}
    values = {}
    context_mode = _m2_normalize_fresh_cli_context_mode(
        report.get("fresh_cli_context_mode") or fresh_cli.get("context_mode")
    )
    if context_mode:
        values["context_mode"] = context_mode
    if "fresh_cli_session_resumed" in report or "session_resumed" in fresh_cli:
        values["session_resumed"] = _m2_report_bool(
            report.get("fresh_cli_session_resumed", fresh_cli.get("session_resumed"))
        )
    if "fresh_cli_handoff_note_used" in report or "handoff_note_used" in fresh_cli:
        values["handoff_note_used"] = _m2_report_bool(
            report.get("fresh_cli_handoff_note_used", fresh_cli.get("handoff_note_used"))
        )
    restart_status = str(
        report.get("fresh_cli_restart_comparator_status")
        or fresh_cli.get("restart_comparator_status")
        or ""
    ).strip()
    if restart_status:
        values["restart_comparator_status"] = restart_status
    return values


def _m2_preference_choice_from_signal(signal):
    if signal == "mew_preferred":
        return "mew"
    if signal == "fresh_cli_preferred":
        return "fresh_cli"
    if signal in {"mew", "fresh_cli", "inconclusive"}:
        return signal
    return ""


def _m2_comparison_status_from_preference_choice(choice):
    if choice == "mew":
        return "mew_preferred"
    if choice == "fresh_cli":
        return "fresh_cli_preferred"
    if choice == "inconclusive":
        return "inconclusive"
    return ""


def _m2_interruption_gate_status_from_children(gate):
    gate = gate or {}
    current = gate.get("status") or "unknown"
    if current != "unknown":
        return current
    child_statuses = [
        ((gate.get(run_id) or {}).get("status") or "unknown")
        for run_id in ("mew", "fresh_cli")
    ]
    if any(status == "unknown" for status in child_statuses):
        return current
    if any(status == "blocked" for status in child_statuses):
        return "blocked"
    if all(status == "proved" for status in child_statuses):
        return "proved"
    if any(status == "not_proved" for status in child_statuses):
        return "not_proved"
    return current


def _m2_refresh_interruption_gate_status(protocol):
    gate = (protocol or {}).get("interruption_resume_gate") or {}
    status = _m2_interruption_gate_status_from_children(gate)
    if status in set(gate.get("allowed_statuses") or []) or status == "unknown":
        gate["status"] = status
    return protocol


def _m2_apply_comparison_report(protocol, report, source_path=""):
    if source_path:
        protocol["comparison_report"] = {
            "status": "loaded" if isinstance(report, dict) and report else "missing",
            "source": source_path,
        }
    if not isinstance(report, dict) or not report:
        return protocol

    comparison = protocol.setdefault("comparison_result", {})
    report_comparison = report.get("comparison_result")
    explicit_comparison_status = False
    if isinstance(report_comparison, dict):
        explicit_comparison_status = "status" in report_comparison
        _m2_merge_mapping(comparison, report_comparison or {})
    allowed_comparison_statuses = set(comparison.get("allowed_statuses") or [])
    explicit_top_level_status = False
    if report.get("status") in allowed_comparison_statuses or report.get("status") == "unknown":
        comparison["status"] = report.get("status")
        explicit_top_level_status = True
    for key in ("next_blocker", "notes"):
        if key in report:
            comparison[key] = report.get(key)

    run_summaries = comparison.setdefault("run_summaries", {})
    fresh_cli = report.get("fresh_cli") or report.get("fresh_cli_summary")
    if isinstance(fresh_cli, dict):
        _m2_merge_mapping(run_summaries.setdefault("fresh_cli", {}), fresh_cli)
    flat_fresh_cli = _m2_flat_fresh_cli_summary(report)
    if flat_fresh_cli:
        _m2_merge_mapping(run_summaries.setdefault("fresh_cli", {}), flat_fresh_cli)
    if isinstance(report.get("run_summaries"), dict):
        _m2_merge_mapping(run_summaries, report.get("run_summaries") or {})

    for key in ("friction_counts", "resume_behavior", "resident_preference"):
        if isinstance(report.get(key), dict):
            _m2_merge_mapping(protocol.setdefault(key, {}), report.get(key) or {})
    preference_signal = str(report.get("preference_signal") or "").strip()
    explicit_preference_signal_status = False
    if preference_signal in allowed_comparison_statuses:
        comparison["status"] = preference_signal
        explicit_preference_signal_status = True
    preference_choice = _m2_preference_choice_from_signal(preference_signal)
    if preference_choice:
        protocol.setdefault("resident_preference", {})["choice"] = preference_choice
    preference_choice_status = _m2_comparison_status_from_preference_choice(
        str((protocol.get("resident_preference") or {}).get("choice") or "").strip()
    )
    if (
        preference_choice_status in allowed_comparison_statuses
        and not explicit_comparison_status
        and not explicit_top_level_status
        and not explicit_preference_signal_status
    ):
        comparison["status"] = preference_choice_status
    for key in ("task_shape", "interruption_resume_gate"):
        if isinstance(report.get(key), dict):
            _m2_merge_mapping(protocol.setdefault(key, {}), report.get(key) or {})
    gate_status = report.get("interruption_resume_gate")
    if isinstance(gate_status, str) and gate_status:
        fresh_gate = protocol.setdefault("interruption_resume_gate", {}).setdefault("fresh_cli", {})
        fresh_gate["status"] = gate_status
        if "manual_rebrief_needed" in report:
            fresh_gate["manual_rebrief_needed"] = bool(report.get("manual_rebrief_needed"))
        if report.get("notes"):
            fresh_gate.setdefault("evidence_gap", [])
            if isinstance(fresh_gate["evidence_gap"], list):
                fresh_gate["evidence_gap"].append(str(report.get("notes")))
    fresh_cli_context = _m2_fresh_cli_context_from_report(report)
    if fresh_cli_context:
        fresh_gate = protocol.setdefault("interruption_resume_gate", {}).setdefault("fresh_cli", {})
        _m2_merge_mapping(fresh_gate, fresh_cli_context)
        if (
            fresh_cli_context.get("context_mode") == "same_session_resume"
            and not comparison.get("next_blocker")
        ):
            comparison["next_blocker"] = (
                "Run a true fresh CLI restart leg or mark the restart comparator inconclusive; "
                "current fresh_cli evidence came from the same external agent session."
            )
    return protocol


def _m2_task_shape_selected(value):
    selected = str(value or "").strip()
    if selected in M2_COMPARATIVE_TASK_SHAPES:
        return selected
    return "standard"


def build_m2_comparative_protocol(
    mew_run_evidence=None,
    comparison_report=None,
    comparison_report_source="",
    task_shape_selected=None,
):
    protocol = {
        "name": "m2-comparative",
        "generated_at": now_iso(),
        "roadmap_milestone": "M2 Interactive Parity",
        "purpose": (
            "Compare one focused coding task in mew against a fresh Claude Code "
            "or Codex CLI session with enough structure to decide whether the "
            "resident would prefer to stay inside mew."
        ),
        "observer_tip": (
            "When approving only one half of a paired source/test change, "
            "apply it with deferred verification and run the verifier after "
            "the companion change lands."
        ),
        "task_shape": {
            "selected": _m2_task_shape_selected(task_shape_selected),
            "recommended_next": "interruption_resume",
            "allowed_values": list(M2_COMPARATIVE_TASK_SHAPES),
            "why": (
                "M2 cannot be closed until an interruption-shaped task proves "
                "that the resident can resume without user rebrief and still "
                "prefer mew over a fresh CLI."
            ),
        },
        "required_runs": [
            {
                "id": "mew",
                "entry": "mew code <task-id>",
                "required_evidence": [
                    "task_id",
                    "work_session_id",
                    "commands_or_tests_run",
                    "approvals_or_rejections",
                    "verification_result",
                    "resume_after_interrupt",
                    "friction_counts",
                    "resident_preference",
                ],
            },
            {
                "id": "fresh_cli",
                "entry": "Claude Code or Codex CLI fresh session",
                "required_evidence": [
                    "context_mode: true_restart or same_session_resume",
                    "tool_or_command_count",
                    "manual_rebrief_needed",
                    "session_resumed",
                    "handoff_note_used",
                    "verification_result",
                    "friction_counts",
                    "resident_preference",
                ],
            },
        ],
        "comparison_result": {
            "status": "unknown",
            "allowed_statuses": ["mew_preferred", "fresh_cli_preferred", "inconclusive", "blocked"],
            "next_blocker": "",
            "notes": "",
            "run_summaries": {
                "mew": {
                    "summary": "",
                    "verification_result": "",
                    "friction_summary": "",
                    "preference_signal": "",
                },
                "fresh_cli": {
                    "summary": "",
                    "verification_result": "",
                    "friction_summary": "",
                    "preference_signal": "",
                },
            },
        },
        "friction_counts": {
            "retyped_gate_flags": 0,
            "lost_context_or_rebriefs": 0,
            "manual_status_probes": 0,
            "approval_confusions": 0,
            "verification_confusions": 0,
            "dead_waits_over_30s": 0,
            "restart_or_recovery_steps": 0,
        },
        "resume_behavior": {
            "interrupt_point": "",
            "mew_resume_command": "mew work <task-id> --session --resume --allow-read .",
            "could_resume_without_user_rebrief": None,
            "risky_or_missing_context": [],
        },
        "interruption_resume_gate": {
            "status": "unknown",
            "allowed_statuses": ["proved", "not_proved", "unknown", "blocked"],
            "required_mew_evidence": [
                "resume brief includes changed or pending work",
                "resume brief preserves interruption, failure, or recovery risk",
                "resume brief exposes a runnable next action",
                "continuity is strong or usable",
                "the resident can advance to passing verification after reentry",
            ],
            "required_fresh_cli_evidence": [
                "whether the comparison was a true fresh restart or a same-session resume",
                "whether manual rebrief was needed after interruption",
                "whether a handoff note or prior agent session context was used",
                "whether files/risks/next action had to be reconstructed from scratch",
                "whether the fresh CLI completed verification faster or with less supervision",
            ],
            "mew": {"status": "unknown", "evidence_gap": []},
            "fresh_cli": {
                "status": "unknown",
                "context_mode": "unknown",
                "allowed_context_modes": list(M2_FRESH_CLI_CONTEXT_MODES),
                "session_resumed": None,
                "handoff_note_used": None,
                "restart_comparator_status": "unknown",
                "evidence_gap": [],
            },
        },
        "resident_preference": {
            "choice": "unknown",
            "allowed_values": ["mew", "fresh_cli", "inconclusive"],
            "reason": "",
            "blocking_gap": "",
        },
        "done_when_mapping": [
            "using mew for one focused coding task feels close to Claude Code / Codex CLI",
            "the model does not lose momentum while waiting for tool feedback",
            "an interrupted resident can resume inside mew without user re-briefing",
        ],
    }
    protocol = _m2_apply_comparison_report(
        protocol,
        comparison_report,
        source_path=comparison_report_source,
    )
    protocol = _m2_apply_mew_run_evidence(protocol, mew_run_evidence)
    return _m2_refresh_interruption_gate_status(protocol)


def format_m2_comparative_protocol(protocol):
    comparison = protocol.get("comparison_result") or {}
    run_summaries = comparison.get("run_summaries") or {}
    lines = [
        "# M2 Comparative Dogfood Protocol",
        "",
        f"Generated at: {protocol.get('generated_at')}",
        "",
        f"Milestone: {protocol.get('roadmap_milestone')}",
        "",
        protocol.get("purpose") or "",
        "",
        "## Task Shape",
    ]
    task_shape = protocol.get("task_shape") or {}
    lines.extend(
        [
            f"- selected: {task_shape.get('selected', '')}",
            f"- recommended_next: {task_shape.get('recommended_next', '')}",
            f"- allowed_values: {', '.join(task_shape.get('allowed_values') or [])}",
            f"- why: {task_shape.get('why', '')}",
            "",
        ]
    )
    lines.extend(
        [
            "## Observer Tip",
            protocol.get("observer_tip") or "",
            "",
            "## Comparison Result",
            f"- status: {comparison.get('status', 'unknown')}",
            f"- allowed_statuses: {', '.join(comparison.get('allowed_statuses') or [])}",
            f"- next_blocker: {comparison.get('next_blocker', '')}",
            f"- notes: {comparison.get('notes', '')}",
            "- run_summaries:",
        ]
    )
    for run_id in ("mew", "fresh_cli"):
        summary = run_summaries.get(run_id) or {}
        lines.extend(
            [
                f"  - {run_id}:",
                f"    summary: {summary.get('summary', '')}",
                f"    verification_result: {summary.get('verification_result', '')}",
                f"    friction_summary: {summary.get('friction_summary', '')}",
                f"    preference_signal: {summary.get('preference_signal', '')}",
            ]
        )
    report_meta = protocol.get("comparison_report") or {}
    if report_meta:
        lines.extend(
            [
                "",
                "## Comparison Report",
                f"- status: {report_meta.get('status')}",
                f"- source: `{report_meta.get('source', '')}`",
            ]
        )
    evidence = protocol.get("mew_run_evidence") or {}
    if evidence:
        effort = evidence.get("effort") or {}
        verification = evidence.get("verification") or {}
        approvals = evidence.get("approval_counts") or {}
        continuity = evidence.get("continuity") or {}
        paired_write_batch = evidence.get("paired_write_batch") or {}
        lines.extend(
            [
                "",
                "## Mew Run Evidence",
                f"- status: {evidence.get('status')}",
                f"- evidence_mode: {evidence.get('evidence_mode', 'single_session')}",
                f"- source_state: `{evidence.get('source_state', '')}`",
                f"- work_session_id: {evidence.get('work_session_id', evidence.get('requested_session_id', ''))}",
                f"- work_session_ids: {evidence.get('work_session_ids') or []}",
                f"- task_id: {evidence.get('task_id', '')}",
                f"- task_title: {evidence.get('task_title', '')}",
                f"- task_description: {evidence.get('task_description', '')}",
                f"- session_status: {evidence.get('session_status', '')}",
                f"- phase: {evidence.get('phase', '')}",
                f"- approval_mode: {evidence.get('approval_mode', 'default')}",
                f"- default_permission_posture: {evidence.get('default_permission_posture') or {}}",
                f"- paired_write_batch: {paired_write_batch.get('status', 'unknown')}",
                f"- elapsed: wall={effort.get('wall_elapsed_seconds')}s active={effort.get('observed_active_seconds')}s",
                (
                    f"- verification: {verification.get('status')} exit={verification.get('exit_code')} "
                    f"command=`{verification.get('command') or ''}`"
                ),
                (
                    f"- approvals: total={approvals.get('total', 0)} applied={approvals.get('applied', 0)} "
                    f"rejected={approvals.get('rejected', 0)} failed={approvals.get('failed', 0)}"
                ),
                f"- resume_command: `{evidence.get('resume_command', '')}`",
                f"- continuity: {continuity.get('score') or '-'} {continuity.get('status') or 'unknown'}",
            ]
        )
        commands = evidence.get("commands_or_tests_run") or []
        if commands:
            lines.append("- commands_or_tests_run:")
            for command in commands:
                lines.append(
                    f"  - #{command.get('tool_call_id')} {command.get('tool')}: "
                    f"`{command.get('command')}` exit={command.get('exit_code')}"
                )
    lines.extend(
        [
            "",
            "## Runs",
        ]
    )
    for run in protocol.get("required_runs") or []:
        lines.append(f"- {run.get('id')}: `{run.get('entry')}`")
        evidence = ", ".join(run.get("required_evidence") or [])
        lines.append(f"  evidence: {evidence}")
    lines.extend(
        [
            "",
            "## Friction Counts",
        ]
    )
    for key, value in (protocol.get("friction_counts") or {}).items():
        lines.append(f"- {key}: {value}")
    resume_behavior = protocol.get("resume_behavior") or {}
    resume_known = resume_behavior.get("could_resume_without_user_rebrief")
    resume_text = "unknown" if resume_known is None else str(bool(resume_known)).lower()
    preference = protocol.get("resident_preference") or {}
    lines.extend(
        [
            "",
            "## Resume Behavior",
            f"- interrupt_point: {resume_behavior.get('interrupt_point', '')}",
            f"- mew_resume_command: `{resume_behavior.get('mew_resume_command', '')}`",
            f"- could_resume_without_user_rebrief: {resume_text}",
            f"- risky_or_missing_context: {resume_behavior.get('risky_or_missing_context') or []}",
            "",
            "## Interruption Resume Gate",
        ]
    )
    gate = protocol.get("interruption_resume_gate") or {}
    lines.extend(
        [
            f"- status: {gate.get('status', 'unknown')}",
            f"- allowed_statuses: {', '.join(gate.get('allowed_statuses') or [])}",
            "- mew:",
        ]
    )
    for key, value in (gate.get("mew") or {}).items():
        lines.append(f"  - {key}: {value}")
    lines.append("- fresh_cli:")
    for key, value in (gate.get("fresh_cli") or {}).items():
        lines.append(f"  - {key}: {value}")
    required_mew = gate.get("required_mew_evidence") or []
    if required_mew:
        lines.append("- required_mew_evidence:")
        lines.extend(f"  - {item}" for item in required_mew)
    required_fresh = gate.get("required_fresh_cli_evidence") or []
    if required_fresh:
        lines.append("- required_fresh_cli_evidence:")
        lines.extend(f"  - {item}" for item in required_fresh)
    lines.extend(
        [
            "",
            "## Resident Preference",
            f"- choice: {preference.get('choice', 'unknown')}",
            f"- reason: {preference.get('reason', '')}",
            f"- blocking_gap: {preference.get('blocking_gap', '')}",
            "",
            "## Done-When Mapping",
        ]
    )
    for item in protocol.get("done_when_mapping") or []:
        lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def build_m2_fresh_cli_report_template(protocol):
    evidence = (protocol or {}).get("mew_run_evidence") or {}
    task_summary = evidence.get("task_title") or ""
    task_description = evidence.get("task_description") or ""
    verification = (evidence.get("verification") or {}).get("command") or ""
    return {
        "task_summary": task_summary,
        "task_description": task_description,
        "fresh_cli_context_mode": "true_restart",
        "fresh_cli_session_resumed": False,
        "fresh_cli_handoff_note_used": False,
        "fresh_cli_restart_comparator_status": "unknown",
        "manual_rebrief_needed": None,
        "interruption_resume_gate": "unknown",
        "verification": [
            {
                "command": verification,
                "exit_code": None,
                "summary": "",
            }
        ],
        "friction_summary": "",
        "preference_signal": "",
        "resident_preference": {
            "choice": "inconclusive",
            "reason": "",
            "blocking_gap": "",
        },
        "notes": "",
    }


def format_m2_fresh_cli_restart_prompt(protocol, report_template_path="m2-fresh-cli-report-template.json"):
    evidence = (protocol or {}).get("mew_run_evidence") or {}
    task_shape = (protocol or {}).get("task_shape") or {}
    commands = evidence.get("commands_or_tests_run") or []
    lines = [
        "# M2 Fresh CLI Restart Comparator",
        "",
        "You are running the fresh CLI leg of mew's M2 comparative dogfood.",
        "",
        "Use a new coding-agent session. Do not resume a previous agent session. "
        "Treat the repository checkout and this prompt as the only starting context.",
        "",
        "## Comparator Rules",
        "",
        "- Set `fresh_cli_context_mode` to `true_restart` only if no prior agent-session context was used.",
        "- Set `fresh_cli_context_mode` to `same_session_resume` if you resume an earlier external agent session.",
        "- Set `fresh_cli_session_resumed` and `fresh_cli_handoff_note_used` honestly.",
        "- Record whether a human had to rebrief the task after interruption.",
        "- Run verification or explain the blocker.",
        "- Write a JSON report using the template below.",
        "",
        "## Task Shape",
        "",
        f"- selected: {task_shape.get('selected', '')}",
        f"- recommended_next: {task_shape.get('recommended_next', '')}",
        "",
        "## Mew-Side Evidence Summary",
        "",
        f"- task_id: {evidence.get('task_id', '')}",
        f"- task_title: {evidence.get('task_title', '')}",
        f"- task_description: {evidence.get('task_description', '')}",
        f"- work_session_id: {evidence.get('work_session_id', '')}",
        f"- work_session_ids: {evidence.get('work_session_ids') or []}",
        f"- resume_gate: {(evidence.get('resume_gate') or {}).get('status', '')}",
        f"- continuity: {(evidence.get('continuity') or {}).get('score', '')} "
        f"{(evidence.get('continuity') or {}).get('status', '')}".rstrip(),
        "",
    ]
    if commands:
        lines.append("## Mew-Side Commands Or Tests")
        lines.append("")
        for command in commands:
            lines.append(
                f"- {command.get('tool')}: `{command.get('command')}` exit={command.get('exit_code')}"
            )
        lines.append("")
    merge_command = "./mew dogfood --scenario m2-comparative"
    mew_session_id = (protocol.get("mew_run_evidence") or {}).get("session_argument")
    if mew_session_id:
        merge_command += f" --mew-session-id {mew_session_id}"
    merge_command += " --m2-comparison-report <report.json>"
    lines.extend(
        [
            "## Required Report",
            "",
            f"Write the completed report to `{report_template_path}` or another explicit JSON path.",
            "The report must include these fields:",
            "",
            "```json",
            json.dumps(build_m2_fresh_cli_report_template(protocol), indent=2, ensure_ascii=False),
            "```",
            "",
            "After writing the report, the supervisor should merge it with:",
            "",
            "```bash",
            merge_command,
            "```",
        ]
    )
    return "\n".join(lines) + "\n"


def run_m2_comparative_scenario(
    workspace,
    env=None,
    mew_session_id=None,
    comparison_report_path=None,
    task_shape=None,
):
    del env
    commands = []
    checks = []
    mew_run_evidence = None
    if mew_session_id:
        current_state = reconcile_next_ids(migrate_state(read_json_file(STATE_FILE, default_state())))
        mew_run_evidence = build_m2_mew_run_evidence(current_state, mew_session_id)
    comparison_report = None
    comparison_report_source = ""
    if comparison_report_path:
        report_path = Path(comparison_report_path).expanduser()
        if not report_path.is_absolute():
            report_path = (Path.cwd() / report_path).resolve()
        comparison_report = read_json_file(report_path, {})
        comparison_report_source = str(report_path)
    protocol = build_m2_comparative_protocol(
        mew_run_evidence=mew_run_evidence,
        comparison_report=comparison_report,
        comparison_report_source=comparison_report_source,
        task_shape_selected=task_shape,
    )
    output_dir = Path(workspace) / STATE_DIR / "dogfood"
    json_path = output_dir / "m2-comparative-protocol.json"
    md_path = output_dir / "m2-comparative-protocol.md"
    fresh_cli_template_path = output_dir / "m2-fresh-cli-report-template.json"
    fresh_cli_prompt_path = output_dir / "m2-fresh-cli-restart-prompt.md"
    write_json_file(json_path, protocol)
    md_path.write_text(format_m2_comparative_protocol(protocol), encoding="utf-8")
    write_json_file(fresh_cli_template_path, build_m2_fresh_cli_report_template(protocol))
    fresh_cli_prompt_path.write_text(
        format_m2_fresh_cli_restart_prompt(
            protocol,
            report_template_path=str(fresh_cli_template_path),
        ),
        encoding="utf-8",
    )
    loaded = read_json_file(json_path, {})
    markdown = read_text_file(md_path)
    fresh_cli_template = read_json_file(fresh_cli_template_path, {})
    fresh_cli_prompt = read_text_file(fresh_cli_prompt_path)

    run_ids = {run.get("id") for run in loaded.get("required_runs") or []}
    friction_keys = set((loaded.get("friction_counts") or {}).keys())
    preference_values = set((loaded.get("resident_preference") or {}).get("allowed_values") or [])
    done_when = loaded.get("done_when_mapping") or []
    comparison = loaded.get("comparison_result") or {}
    comparison_run_summaries = comparison.get("run_summaries") or {}
    loaded_evidence = loaded.get("mew_run_evidence") or {}
    loaded_comparison_report = loaded.get("comparison_report") or {}
    allowed_comparison_statuses = set(comparison.get("allowed_statuses") or [])
    comparison_status = comparison.get("status")
    task_shape = loaded.get("task_shape") or {}
    interruption_gate = loaded.get("interruption_resume_gate") or {}
    fresh_cli_gate = interruption_gate.get("fresh_cli") or {}

    _scenario_check(
        checks,
        "m2_comparative_protocol_writes_json_record",
        json_path.exists()
        and loaded.get("roadmap_milestone") == "M2 Interactive Parity"
        and bool(loaded.get("generated_at")),
        observed={
            "path": str(json_path),
            "roadmap_milestone": loaded.get("roadmap_milestone"),
            "generated_at": loaded.get("generated_at"),
        },
        expected="JSON protocol record exists for M2 Interactive Parity with a generated timestamp",
    )
    _scenario_check(
        checks,
        "m2_comparative_protocol_writes_markdown_runbook",
        md_path.exists()
        and "M2 Comparative Dogfood Protocol" in markdown
        and "## Comparison Result" in markdown
        and "Resident Preference" in markdown,
        observed={"path": str(md_path), "chars": len(markdown)},
        expected="Markdown runbook exists with comparison result and resident preference sections",
    )
    _scenario_check(
        checks,
        "m2_comparative_protocol_writes_fresh_cli_restart_assets",
        fresh_cli_template_path.exists()
        and fresh_cli_prompt_path.exists()
        and fresh_cli_template.get("fresh_cli_context_mode") == "true_restart"
        and fresh_cli_template.get("fresh_cli_session_resumed") is False
        and "M2 Fresh CLI Restart Comparator" in fresh_cli_prompt
        and "fresh_cli_context_mode" in fresh_cli_prompt,
        observed={
            "template": str(fresh_cli_template_path),
            "prompt": str(fresh_cli_prompt_path),
            "template_context_mode": fresh_cli_template.get("fresh_cli_context_mode"),
        },
        expected="fresh CLI restart prompt and report template are emitted beside the protocol",
    )
    if mew_session_id:
        _scenario_check(
            checks,
            "m2_comparative_protocol_prefills_mew_run_evidence",
            loaded_evidence.get("status") == "found"
            and bool((comparison_run_summaries.get("mew") or {}).get("summary"))
            and "## Mew Run Evidence" in markdown
            and bool((loaded.get("resume_behavior") or {}).get("mew_resume_command")),
            observed={
                "requested_session_id": _m2_session_id_text(mew_session_id),
                "evidence": loaded_evidence,
                "mew_summary": comparison_run_summaries.get("mew"),
            },
            expected="m2-comparative can prefill mew-side evidence from a real work session",
        )
    if comparison_report_path:
        _scenario_check(
            checks,
            "m2_comparative_protocol_merges_comparison_report",
            loaded_comparison_report.get("status") == "loaded"
            and bool((comparison_run_summaries.get("fresh_cli") or {}).get("summary"))
            and "## Comparison Report" in markdown
            and bool((loaded.get("resident_preference") or {}).get("choice")),
            observed={
                "source": loaded_comparison_report.get("source"),
                "fresh_cli": comparison_run_summaries.get("fresh_cli"),
                "resident_preference": loaded.get("resident_preference"),
            },
            expected="m2-comparative can merge a paired fresh CLI comparison report",
        )
    _scenario_check(
        checks,
        "m2_comparative_protocol_has_fillable_comparison_result",
        (comparison_status == "unknown" or comparison_status in allowed_comparison_statuses)
        and "blocked" in (comparison.get("allowed_statuses") or [])
        and "mew" in comparison_run_summaries
        and "fresh_cli" in comparison_run_summaries
        and all(
            {"summary", "verification_result", "friction_summary", "preference_signal"}.issubset(
                (comparison_run_summaries.get(run_id) or {}).keys()
            )
            for run_id in ("mew", "fresh_cli")
        ),
        observed=comparison,
        expected="comparison_result is directly fillable after paired dogfood runs",
    )
    _scenario_check(
        checks,
        "m2_comparative_protocol_requires_both_runs",
        {"mew", "fresh_cli"}.issubset(run_ids),
        observed=sorted(run_ids),
        expected=["fresh_cli", "mew"],
    )
    _scenario_check(
        checks,
        "m2_comparative_protocol_tracks_momentum_and_resume",
        {"dead_waits_over_30s", "lost_context_or_rebriefs", "restart_or_recovery_steps"}.issubset(friction_keys)
        and "could_resume_without_user_rebrief" in (loaded.get("resume_behavior") or {}),
        observed={
            "friction_counts": sorted(friction_keys),
            "resume_behavior": loaded.get("resume_behavior"),
        },
        expected="friction counts include waits/context/recovery and resume behavior gate",
    )
    _scenario_check(
        checks,
        "m2_comparative_protocol_tracks_interruption_resume_gate",
        task_shape.get("recommended_next") == "interruption_resume"
        and "interruption_resume" in (task_shape.get("allowed_values") or [])
        and "proved" in (interruption_gate.get("allowed_statuses") or [])
        and "not_proved" in (interruption_gate.get("allowed_statuses") or [])
        and {"mew", "fresh_cli"}.issubset(interruption_gate.keys())
        and len(interruption_gate.get("required_mew_evidence") or []) >= 4
        and len(interruption_gate.get("required_fresh_cli_evidence") or []) >= 2,
        observed={
            "task_shape": task_shape,
            "interruption_resume_gate": interruption_gate,
        },
        expected="protocol captures the M2 interruption-resume gate and evidence requirements for both runs",
    )
    _scenario_check(
        checks,
        "m2_comparative_protocol_tracks_fresh_cli_restart_context",
        "context_mode" in fresh_cli_gate
        and "true_restart" in (fresh_cli_gate.get("allowed_context_modes") or [])
        and "same_session_resume" in (fresh_cli_gate.get("allowed_context_modes") or [])
        and "session_resumed" in fresh_cli_gate
        and "handoff_note_used" in fresh_cli_gate
        and "restart_comparator_status" in fresh_cli_gate,
        observed={"fresh_cli": fresh_cli_gate},
        expected="fresh CLI evidence records whether the comparator was a true restart or same-session resume",
    )
    _scenario_check(
        checks,
        "m2_comparative_protocol_records_resident_preference",
        {"mew", "fresh_cli", "inconclusive"}.issubset(preference_values),
        observed=sorted(preference_values),
        expected=["fresh_cli", "inconclusive", "mew"],
    )
    _scenario_check(
        checks,
        "m2_comparative_protocol_maps_to_m2_done_when",
        len(done_when) == 3
        and any("focused coding task" in item for item in done_when)
        and any("momentum" in item for item in done_when)
        and any("interrupted resident" in item for item in done_when),
        observed=done_when,
        expected="all three M2 Done-when criteria are represented",
    )
    report = _scenario_report("m2-comparative", workspace, commands, checks)
    report["artifacts"] = {
        "json": str(json_path),
        "markdown": str(md_path),
        "fresh_cli_report_template": str(fresh_cli_template_path),
        "fresh_cli_restart_prompt": str(fresh_cli_prompt_path),
    }
    return report


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
        elif name == "resident-loop":
            reports.append(run_resident_loop_scenario(scenario_workspace, env=env))
        elif name == "native-work":
            reports.append(run_native_work_scenario(scenario_workspace, env=env))
        elif name == "self-improve-controls":
            reports.append(run_self_improve_controls_scenario(scenario_workspace, env=env))
        elif name == "native-advance":
            reports.append(run_native_advance_scenario(scenario_workspace, env=env))
        elif name == "passive-recovery-loop":
            reports.append(run_passive_recovery_loop_scenario(scenario_workspace, env=env))
        elif name == "passive-auto-recovery":
            reports.append(run_passive_auto_recovery_scenario(scenario_workspace, env=env))
        elif name == "passive-auto-recovery-read":
            reports.append(run_passive_auto_recovery_read_scenario(scenario_workspace, env=env))
        elif name == "passive-auto-recovery-write":
            reports.append(run_passive_auto_recovery_write_scenario(scenario_workspace, env=env))
        elif name == "day-reentry":
            reports.append(run_day_reentry_scenario(scenario_workspace, env=env))
        elif name == "continuity":
            reports.append(run_continuity_scenario(scenario_workspace, env=env))
        elif name == "m3-reentry-gate":
            reports.append(run_m3_reentry_gate_scenario(scenario_workspace, env=env))
        elif name == "chat-cockpit":
            reports.append(run_chat_cockpit_scenario(scenario_workspace, env=env))
        elif name == "work-session":
            reports.append(run_work_session_scenario(scenario_workspace, env=env))
        elif name == "m2-comparative":
            reports.append(
                run_m2_comparative_scenario(
                    scenario_workspace,
                    env=env,
                    mew_session_id=getattr(args, "mew_session_id", None),
                    comparison_report_path=getattr(args, "m2_comparison_report", None),
                    task_shape=getattr(args, "m2_task_shape", None),
                )
            )
        else:
            raise ValueError(f"unknown dogfood scenario: {name}")

    passed = all(report.get("status") == "pass" for report in reports)
    cleanup_skipped_reason = "explicit_workspace" if args.cleanup and not created_temp else ""
    report = {
        "generated_at": now_iso(),
        "workspace": str(workspace),
        "kept": not (args.cleanup and created_temp),
        "scenario": requested,
        "status": "pass" if passed else "fail",
        "scenarios": reports,
    }
    if cleanup_skipped_reason:
        report["cleanup_skipped_reason"] = cleanup_skipped_reason
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


def compact_command_result(result, limit=4):
    summary = {
        "command": result.get("command", []),
        "exit_code": result.get("exit_code"),
        "stdout_tail": tail_lines(result.get("stdout"), limit=limit, max_line_chars=100),
        "stderr_tail": tail_lines(result.get("stderr"), limit=limit, max_line_chars=100),
    }
    summary["stdout_chars"] = len(result.get("stdout") or "")
    summary["stderr_chars"] = len(result.get("stderr") or "")
    return summary


def compact_dogfood_value(value, *, depth=0):
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        if len(value) <= DOGFOOD_OBSERVED_TEXT_LIMIT:
            return value
        omitted = len(value) - DOGFOOD_OBSERVED_TEXT_LIMIT
        return value[:DOGFOOD_OBSERVED_TEXT_LIMIT] + f"\n... truncated {omitted} char(s) ..."
    if depth >= 6:
        return repr(value)[:DOGFOOD_OBSERVED_TEXT_LIMIT]
    if isinstance(value, (list, tuple)):
        items = [compact_dogfood_value(item, depth=depth + 1) for item in list(value)[:DOGFOOD_OBSERVED_LIST_LIMIT]]
        if len(value) > DOGFOOD_OBSERVED_LIST_LIMIT:
            items.append({"omitted_items": len(value) - DOGFOOD_OBSERVED_LIST_LIMIT})
        return items
    if isinstance(value, dict):
        if {"status", "score", "axes"}.issubset(value.keys()):
            return {
                "status": value.get("status"),
                "score": value.get("score"),
                "passed": value.get("passed"),
                "total": value.get("total"),
                "missing": compact_dogfood_value(value.get("missing") or [], depth=depth + 1),
            }
        compacted = {}
        items = list(value.items())
        for key, item in items[:DOGFOOD_OBSERVED_DICT_LIMIT]:
            compacted[key] = compact_dogfood_value(item, depth=depth + 1)
        if len(items) > DOGFOOD_OBSERVED_DICT_LIMIT:
            compacted["omitted_keys"] = len(items) - DOGFOOD_OBSERVED_DICT_LIMIT
        return compacted
    return compact_dogfood_value(str(value), depth=depth + 1)


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


def native_work_advance_metrics(state, limit=5):
    advances = []
    runtime_status = state.get("runtime_status") or {}
    for session in state.get("work_sessions", []) or []:
        for note in session.get("notes") or []:
            text = note.get("text") or ""
            prefix = "runtime passive advance step "
            if note.get("source") != "runtime" or prefix not in text:
                continue
            outcome = text.split(prefix, 1)[1].split(":", 1)[0].strip() or "unknown"
            advances.append(
                {
                    "session_id": session.get("id"),
                    "task_id": session.get("task_id"),
                    "at": note.get("created_at"),
                    "outcome": outcome,
                    "text": text,
                }
            )
    skips = list(runtime_status.get("native_work_step_skips") or [])
    return {
        "attempts": len(advances),
        "by_outcome": count_by(advances, "outcome"),
        "latest": advances[-limit:],
        "skip_count": len(skips),
        "by_skip_reason": count_by(skips, "reason"),
        "recent_skips": skips[-limit:],
        "last_step": runtime_status.get("last_native_work_step") or {},
        "last_skip": runtime_status.get("last_native_work_step_skip"),
        "last_skip_recovery": runtime_status.get("last_native_work_skip_recovery") or {},
        "last_recovery": runtime_status.get("last_native_work_recovery") or {},
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
        "native_work_advance": native_work_advance_metrics(state),
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
        f"native_work_advance: {report.get('native_work_advance')}",
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
    if report.get("cleanup_skipped_reason"):
        lines.append(f"cleanup_skipped: {report.get('cleanup_skipped_reason')}")
    for scenario in report.get("scenarios") or []:
        lines.append("")
        lines.append(
            f"{scenario.get('name')}: {scenario.get('status')} "
            f"commands={scenario.get('command_count')}"
        )
        artifacts = scenario.get("artifacts") or {}
        if artifacts:
            lines.append(f"  artifacts: {artifacts}")
        for check in scenario.get("checks") or []:
            marker = "PASS" if check.get("passed") else "FAIL"
            lines.append(f"- {marker} {check.get('name')}")
            if not check.get("passed"):
                lines.append(f"  observed: {check.get('observed')}")
                lines.append(f"  expected: {check.get('expected')}")
    return "\n".join(lines)


def summarize_dogfood_scenario_json(report):
    scenarios = []
    for scenario in report.get("scenarios") or []:
        checks = []
        for check in scenario.get("checks") or []:
            item = {
                "name": check.get("name"),
                "passed": bool(check.get("passed")),
            }
            if not check.get("passed"):
                item["observed"] = compact_dogfood_value(check.get("observed"))
                item["expected"] = compact_dogfood_value(check.get("expected"))
            checks.append(item)
        scenarios.append(
            {
                "name": scenario.get("name"),
                "status": scenario.get("status"),
                "workspace": scenario.get("workspace"),
                "command_count": scenario.get("command_count"),
                "artifacts": scenario.get("artifacts") or {},
                "checks": checks,
            }
        )
    return {
        "generated_at": report.get("generated_at"),
        "workspace": report.get("workspace"),
        "kept": report.get("kept"),
        "cleanup_skipped_reason": report.get("cleanup_skipped_reason") or "",
        "scenario": report.get("scenario"),
        "status": report.get("status"),
        "scenarios": scenarios,
    }


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
            "notes": "Proposed by mew from dogfood seed. Refined self-proposed coding task.",
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


def _run_dogfood_in_workspace(args, workspace, created_temp, source_copy=None, pre_snapshot=None, env=None):
    command = build_runtime_command(args, workspace)
    state_dir = workspace / STATE_DIR
    state_dir.mkdir(parents=True, exist_ok=True)
    output_path = state_dir / "dogfood-runtime.out"
    started_at = time.monotonic()
    exit_code = None

    runtime_env = dogfood_runtime_env(env)
    with output_path.open("ab") as output:
        process = subprocess.Popen(
            command,
            cwd=str(workspace),
            stdout=output,
            stderr=subprocess.STDOUT,
            text=True,
            env=runtime_env,
            start_new_session=True,
        )

    wait_for_runtime_state(workspace, timeout=args.startup_timeout, poll_interval=0.1)
    injected_event_ids = []
    for message in args.send_message or []:
        result = run_command(
            [sys.executable, "-m", "mew", "message", message],
            workspace,
            timeout=args.message_timeout,
            env=runtime_env,
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
    elif args.cleanup and not created_temp:
        report["kept"] = True
        report["cleanup_skipped_reason"] = "explicit_workspace"
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
    elif args.cleanup and not created_temp:
        cleanup_skipped_reason = "explicit_workspace"
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
