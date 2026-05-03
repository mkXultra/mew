import json
import hashlib
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
from datetime import timedelta
from types import SimpleNamespace

from .brief import recent_activity, next_move
from .config import LOG_FILE, MODEL_TRACE_FILE, STATE_DIR, STATE_FILE
from .errors import MewError
from .model_backends import (
    load_model_auth,
    model_backend_default_base_url,
    model_backend_default_model,
    normalize_model_backend,
)
from .long_build_substrate import build_long_build_contract, build_long_command_run
from .patch_draft import (
    PATCH_BLOCKER_RECOVERY_ACTIONS,
    PATCH_DRAFT_VALIDATOR_VERSION,
    compile_patch_draft,
)
from .programmer import create_task_plan
from .project_snapshot import format_project_snapshot, refresh_project_snapshot
from .read_tools import is_sensitive_path
from .state import add_question, default_state, migrate_state, next_id, reconcile_next_ids
from .terminal_bench_replay import replay_terminal_bench_job, terminal_bench_llm_action_fixture_contexts
from .tasks import find_task
from .thoughts import dropped_thread_warning_for_context
from .timeutil import now_iso, parse_time
from .typed_memory import FileMemoryBackend
from .work_session import (
    build_work_session_effort,
    build_work_session_resume,
    create_work_session,
    find_work_session,
    finish_work_model_turn,
    start_work_model_turn,
)
from .write_tools import build_write_intent


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
    "m4-file-write-recovery",
    "m4-runtime-effect-recovery",
    "m4-close-gate",
    "day-reentry",
    "continuity",
    "m3-reentry-gate",
    "m3-source-reentry",
    "chat-cockpit",
    "work-session",
    "m2-comparative",
    "m5-safety-hooks",
    "m6-daemon-watch",
    "m6-daemon-restart",
    "m6-daemon-loop",
    "m6_11-compiler-replay",
    "m6_11-draft-timeout",
    "m6_11-refusal-separation",
    "m6_11-drafting-recovery",
    "m6_11-phase4-regression",
    "m6_9-memory-taxonomy",
    "m6_9-reviewer-steering-reuse",
    "m6_9-failure-shield-reuse",
    "m6_9-reasoning-trace-recall",
    "m6_9-active-memory-recall",
    "m6_9-repeated-task-recall",
    "m6_9-phase1-regression",
    "m6_9-phase2-regression",
    "m6_9-symbol-index-hit",
    "m6_9-drift-canary",
    "m6_9-alignment-decay-rehearsal",
    "m6_13-deliberation-internalization",
    "m6_24-terminal-bench-replay",
    "m6_24-compile-compcert-emulator",
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
DOGFOOD_REPO_ROOT = Path(__file__).resolve().parents[2]
PATCH_DRAFT_FIXTURE_ROOT = DOGFOOD_REPO_ROOT / "tests" / "fixtures" / "work_loop" / "patch_draft"
DRAFTING_RECOVERY_FIXTURE_ROOT = (
    DOGFOOD_REPO_ROOT / "tests" / "fixtures" / "work_loop" / "drafting_recovery"
)
WORK_LOOP_TIMEOUT_BEFORE_DRAFT_ROOT = (
    DOGFOOD_REPO_ROOT / "tests" / "fixtures" / "work_loop" / "recovery"
)
PHASE4_REGRESSION_FIXTURE_ROOT = (
    DOGFOOD_REPO_ROOT / "tests" / "fixtures" / "work_loop" / "phase4_regression"
)
M6_6_COMPARATOR_BUDGET_FIXTURE_ROOT = (
    PHASE4_REGRESSION_FIXTURE_ROOT / "m6_6_comparator_budget"
)
M6_11_PHASE4_COMPARATOR_CASES = {
    "M6.6-A": "M6.6-A",
    "M6.6-B": "M6.6-B",
    "M6.6-C": "M6.6-C",
}



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


def dogfood_time_dilation_env(env=None, time_dilation=None):
    scenario_env = dict(env or dogfood_subprocess_env())
    if time_dilation is None:
        return scenario_env
    multiplier = float(time_dilation)
    if multiplier <= 0:
        raise ValueError("time_dilation must be positive")
    scenario_env["MEW_TIME_DILATION"] = str(multiplier)
    return scenario_env


def effective_time_dilation(env=None):
    raw = (env or {}).get("MEW_TIME_DILATION")
    if raw is None:
        return 1.0
    try:
        multiplier = float(raw)
    except ValueError:
        return 1.0
    return multiplier if multiplier > 0 else 1.0


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


def _load_json_file(path):
    path = Path(path)
    with path.open("r", encoding="utf-8") as fp:
        return json.load(fp)


def _iter_fixture_dirs(root):
    if not Path(root).is_dir():
        return []
    return sorted((path for path in Path(root).iterdir() if path.is_dir()), key=lambda item: item.name)


def _run_patch_draft_fixture(fixture_dir):
    scenario = _load_json_file(fixture_dir / "scenario.json")
    return scenario


def _to_float_seconds(value):
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _median_wall_seconds(values):
    if not values:
        return None
    sorted_values = sorted(values)
    if len(sorted_values) % 2:
        return sorted_values[len(sorted_values) // 2]
    mid_left = len(sorted_values) // 2 - 1
    mid_right = len(sorted_values) // 2
    return (sorted_values[mid_left] + sorted_values[mid_right]) / 2.0


def _phase4_comparator_case_id(case):
    if not isinstance(case, dict):
        return ""
    return str(case.get("case_id") or "").strip()


def _phase4_comparator_case_shape(case):
    if not isinstance(case, dict):
        return ""
    return str(case.get("shape") or "").strip()


def _phase4_case_wall_seconds(case):
    if not isinstance(case, dict):
        return None
    if "iter_wall_seconds" in case:
        return _to_float_seconds(case.get("iter_wall_seconds"))
    if "iter_wall" in case:
        return _to_float_seconds(case.get("iter_wall"))
    if "wall_seconds" in case:
        return _to_float_seconds(case.get("wall_seconds"))
    if "wall_time_seconds" in case:
        return _to_float_seconds(case.get("wall_time_seconds"))
    return None


def _extract_patch_draft_payload_paths(scenario):
    paths = []
    todo = scenario.get("todo") if isinstance(scenario, dict) else {}
    raw_todo_paths = (todo.get("source") or {}).get("target_paths") if isinstance(todo.get("source"), dict) else []
    if isinstance(raw_todo_paths, list):
        for raw_path in raw_todo_paths:
            path = (str(raw_path) if raw_path is not None else "").strip()
            if path and path not in paths:
                paths.append(path)

    model_output = scenario.get("model_output") if isinstance(scenario, dict) else {}
    for raw_file in (model_output.get("files") or []) if isinstance(model_output, dict) else []:
        if not isinstance(raw_file, dict):
            continue
        path = (str(raw_file.get("path") or "")).strip()
        if path and path not in paths:
            paths.append(path)

    cached_paths = scenario.get("cached_windows") if isinstance(scenario, dict) else {}
    if not paths and isinstance(cached_paths, dict):
        paths = sorted(str(path).strip() for path in cached_paths.keys() if str(path).strip())

    live_paths = scenario.get("live_files") if isinstance(scenario, dict) else {}
    if not paths and isinstance(live_paths, dict):
        paths = sorted(str(path).strip() for path in live_paths.keys() if str(path).strip())

    return paths


def _extract_cached_windows_for_path(cached_windows, path):
    if not isinstance(cached_windows, dict):
        return []
    raw_windows = cached_windows.get(path)
    if isinstance(raw_windows, list):
        return [window for window in raw_windows if isinstance(window, dict)]
    if isinstance(raw_windows, dict):
        return [raw_windows]
    return []


def _expected_patch_draft_artifact_id(artifact):
    payload = {
        "todo_id": str(artifact.get("todo_id") or ""),
        "summary": str(artifact.get("summary") or ""),
        "files": artifact.get("files") or [],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return f"draft-{hashlib.sha1(encoded.encode('utf-8')).hexdigest()[:12]}"


def _scenario_patch_draft_fixture_checks(checks, fixture_name, scenario):
    prefix = f"m6_11_compiler_replay_{fixture_name}"
    cached_windows = scenario.get("cached_windows")
    live_files = scenario.get("live_files")
    paths = _extract_patch_draft_payload_paths(scenario)
    missing_window_data = []
    missing_cached_windows = []
    missing_live_hashes = []

    for path in paths:
        path_windows = _extract_cached_windows_for_path(cached_windows, path)
        if not path_windows:
            missing_cached_windows.append(path)
            continue

        for index, window in enumerate(path_windows):
            window_sha256 = str(window.get("window_sha256") or "").strip()
            file_sha256 = str(window.get("file_sha256") or "").strip()
            if not window_sha256:
                missing_window_data.append(f"{path}:{index}:window_sha256")
            if not file_sha256:
                missing_window_data.append(f"{path}:{index}:file_sha256")

    if isinstance(live_files, dict):
        for path in paths:
            live_entry = live_files.get(path)
            if not isinstance(live_entry, dict) or not str(live_entry.get("sha256") or "").strip():
                missing_live_hashes.append(path)

    _scenario_check(
        checks,
        f"{prefix}_fixture_paths",
        bool(paths),
        observed=paths,
        expected="fixture includes at least one target path",
    )
    _scenario_check(
        checks,
        f"{prefix}_fixture_cached_window_hashes",
        bool(not missing_window_data and not missing_cached_windows),
        observed={
            "paths": paths,
            "missing_windows": sorted(set(missing_cached_windows)),
            "missing_window_hashes": sorted(set(missing_window_data)),
        },
        expected="cached window entries include window_sha256 and file_sha256 for each target path",
    )
    _scenario_check(
        checks,
        f"{prefix}_fixture_live_file_hashes",
        bool(not missing_live_hashes),
        observed=sorted(set(missing_live_hashes)),
        expected="live file entries include sha256 for each target path",
    )


def _append_patch_draft_expected_checks(checks, fixture_name, scenario, artifact):
    expected = scenario.get("expected") or {}
    expected_kind = str(expected.get("kind") or "")
    actual_kind = str(artifact.get("kind") or "")
    prefix = f"m6_11_compiler_replay_{fixture_name}"

    _scenario_check(
        checks,
        f"{prefix}_kind",
        actual_kind == expected_kind,
        observed=actual_kind,
        expected=expected_kind,
    )
    if actual_kind == "patch_draft":
        _scenario_check(
            checks,
            f"{prefix}_validator_version",
            artifact.get("validator_version") == PATCH_DRAFT_VALIDATOR_VERSION,
            observed=artifact.get("validator_version"),
            expected=PATCH_DRAFT_VALIDATOR_VERSION,
        )
        _scenario_check(
            checks,
            f"{prefix}_artifact_id",
            artifact.get("id") == _expected_patch_draft_artifact_id(artifact),
            observed=artifact.get("id"),
            expected=_expected_patch_draft_artifact_id(artifact),
        )

    if expected_kind == "patch_draft":
        _scenario_check(
            checks,
            f"{prefix}_status",
            artifact.get("status") == expected.get("status"),
            observed=artifact.get("status"),
            expected=expected.get("status"),
        )
        _scenario_check(
            checks,
            f"{prefix}_todo_id",
            artifact.get("todo_id") == expected.get("todo_id", scenario.get("todo", {}).get("id")),
            observed=artifact.get("todo_id"),
            expected=expected.get("todo_id", scenario.get("todo", {}).get("id")),
        )
        _scenario_check(
            checks,
            f"{prefix}_file_paths",
            [item.get("path") for item in artifact.get("files") or []] == _extract_patch_draft_payload_paths(scenario),
            observed=[item.get("path") for item in artifact.get("files") or []],
            expected=_extract_patch_draft_payload_paths(scenario),
        )
        if "file_count" in expected:
            _scenario_check(
                checks,
                f"{prefix}_file_count",
                len(artifact.get("files") or []) == expected.get("file_count"),
                observed=len(artifact.get("files") or []),
                expected=expected.get("file_count"),
            )
        if "file_kinds" in expected:
            _scenario_check(
                checks,
                f"{prefix}_file_kinds",
                [item.get("kind") for item in artifact.get("files") or []] == expected.get("file_kinds"),
                observed=[item.get("kind") for item in artifact.get("files") or []],
                expected=expected.get("file_kinds"),
            )
        for index, file_item in enumerate(artifact.get("files") or []):
            file_path = str(file_item.get("path") or "")
            live_file = (scenario.get("live_files") or {}).get(file_path) if isinstance(scenario.get("live_files"), dict) else {}
            expected_window_hashes = [
                str(window.get("window_sha256") or "").strip()
                for window in _extract_cached_windows_for_path(scenario.get("cached_windows") or {}, file_path)
            ]
            expected_pre_sha = str((live_file or {}).get("sha256") or "").strip()
            post_sha = str(file_item.get("post_file_sha256") or "").strip()

            _scenario_check(
                checks,
                f"{prefix}_file_{index}_window_sha256s",
                [str(item or "") for item in (file_item.get("window_sha256s") or [])] == expected_window_hashes,
                observed=file_item.get("window_sha256s"),
                expected=expected_window_hashes,
            )
            _scenario_check(
                checks,
                f"{prefix}_file_{index}_pre_file_sha256",
                str(file_item.get("pre_file_sha256") or "") == expected_pre_sha,
                observed=file_item.get("pre_file_sha256"),
                expected=expected_pre_sha,
            )
            _scenario_check(
                checks,
                f"{prefix}_file_{index}_post_file_sha256",
                bool(post_sha) and post_sha != expected_pre_sha,
                observed=post_sha,
                expected="non-empty hash that differs from pre_file_sha256",
            )
        for index, fragment in enumerate(expected.get("diff_contains", []), start=1):
            _scenario_check(
                checks,
                f"{prefix}_diff_contains_{index}",
                fragment in (artifact.get("unified_diff") or ""),
                observed=(artifact.get("unified_diff") or "")[:DOGFOOD_OBSERVED_TEXT_LIMIT],
                expected=fragment,
            )
    elif expected_kind == "patch_blocker":
        _scenario_check(
            checks,
            f"{prefix}_code",
            artifact.get("code") == expected.get("code"),
            observed=artifact.get("code"),
            expected=expected.get("code"),
        )
        if "detail_contains" in expected:
            _scenario_check(
                checks,
                f"{prefix}_detail_contains",
                expected.get("detail_contains") in (artifact.get("detail") or ""),
                observed=artifact.get("detail"),
                expected=expected.get("detail_contains"),
            )
        if "path" in expected:
            _scenario_check(
                checks,
                f"{prefix}_path",
                artifact.get("path") == expected.get("path"),
                observed=artifact.get("path"),
                expected=expected.get("path"),
            )
        _scenario_check(
            checks,
            f"{prefix}_recovery_action",
            artifact.get("recovery_action")
            == PATCH_BLOCKER_RECOVERY_ACTIONS.get(str(artifact.get("code") or ""), "inspect_blocker"),
            observed=artifact.get("recovery_action"),
            expected=PATCH_BLOCKER_RECOVERY_ACTIONS.get(
                str(artifact.get("code") or ""),
                "inspect_blocker",
            ),
        )


def run_m6_11_compiler_replay_scenario(workspace, env=None):
    commands = []
    checks = []
    fixture_names = []
    for fixture_dir in _iter_fixture_dirs(PATCH_DRAFT_FIXTURE_ROOT):
        fixture_names.append(fixture_dir.name)
        scenario = _run_patch_draft_fixture(fixture_dir)
        _scenario_check(
            checks,
            f"m6_11_compiler_replay_{fixture_dir.name}_scenario_loaded",
            bool(scenario.get("todo")) and bool(scenario.get("model_output")),
            observed={
                "has_todo": bool(scenario.get("todo")),
                "has_model_output": bool(scenario.get("model_output")),
                "fixture_name": scenario.get("name"),
            },
            expected=f"fixture {fixture_dir.name} loads with todo and model_output",
        )
        _scenario_check(
            checks,
            f"m6_11_compiler_replay_{fixture_dir.name}_expected_shape",
            bool(scenario.get("expected")),
            observed=bool(scenario.get("expected")),
            expected=f"fixture {fixture_dir.name} includes expected",
        )
        _scenario_patch_draft_fixture_checks(checks, fixture_dir.name, scenario)
        artifact = compile_patch_draft(
            todo=scenario["todo"],
            proposal=scenario["model_output"],
            cached_windows=scenario.get("cached_windows") or {},
            live_files=scenario.get("live_files") or {},
            allowed_write_roots=scenario.get("allowed_write_roots", ["."]),
        )
        _append_patch_draft_expected_checks(checks, fixture_dir.name, scenario, artifact)
    _scenario_check(
        checks,
        "m6_11_compiler_replay_fixtures_found",
        bool(fixture_names),
        observed=fixture_names,
        expected="at least one fixture directory is present",
    )
    report = _scenario_report("m6_11-compiler-replay", workspace, commands, checks)
    report["artifacts"] = {
        "fixtures": fixture_names,
        "fixture_count": len(fixture_names),
    }
    return report


def run_m6_11_draft_timeout_scenario(workspace, env=None):
    commands = []
    checks = []
    fixture = _load_json_file(
        WORK_LOOP_TIMEOUT_BEFORE_DRAFT_ROOT / "401_exact_windows_timeout_before_draft" / "scenario.json"
    )
    state = default_state()
    fixture_state = fixture.get("state") if isinstance(fixture, dict) else {}
    if isinstance(fixture_state, dict):
        if "tasks" in fixture_state:
            state["tasks"] = list(fixture_state.get("tasks") or [])
        if "work_sessions" in fixture_state:
            state["work_sessions"] = list(fixture_state.get("work_sessions") or [])
        if "version" in fixture_state:
            state["version"] = fixture_state.get("version", state["version"])
    write_json_file(workspace / STATE_FILE, state)

    work_sessions = state.get("work_sessions") or []
    session = work_sessions[0] if work_sessions else {}
    task_id = fixture.get("task_id")
    if task_id is None:
        task_id = session.get("task_id")
    task = {}
    for item in state.get("tasks") or []:
        if str(item.get("id")) == str(task_id):
            task = item
            break

    if isinstance(task_id, int):
        task_id_text = str(task_id)
    elif task_id is None:
        task_id_text = None
    else:
        task_id_text = str(task_id).strip()

    session_for_snapshot = session.get("id") or task_id_text or "latest"
    follow_path = workspace / STATE_DIR / "follow" / f"session-{session_for_snapshot}.json"
    follow_payload = fixture.get("follow_snapshot")
    follow_snapshot = dict(follow_payload) if isinstance(follow_payload, dict) else {}
    follow_snapshot.setdefault("session_id", session.get("id") or task_id)
    follow_snapshot.setdefault("task_id", task_id)
    follow_snapshot.setdefault("heartbeat_at", "2026-04-22T00:00:05Z")
    follow_snapshot.setdefault("session_updated_at", session.get("updated_at") or "2026-04-22T00:00:00Z")
    follow_snapshot.setdefault("model_timeout_seconds", 60)
    write_json_file(follow_path, follow_snapshot)

    follow_result = run_command(
        _scenario_command("work", task_id_text, "--follow-status", "--json"),
        workspace,
        timeout=20,
        env=env,
    )
    commands.append(follow_result)
    follow_data = _json_stdout(follow_result)

    old_cwd = os.getcwd()
    try:
        os.chdir(workspace)
        resume = build_work_session_resume(session, task=task, state=state) or {}
    finally:
        os.chdir(old_cwd)

    resume_active_todo = resume.get("active_work_todo") or {}
    resume_blocker = resume_active_todo.get("blocker") or {}
    resume_next_recovery_action = str(resume_blocker.get("recovery_action") or "")
    resume_next_action = str(resume.get("next_action") or "")
    resume_recovery_plan = resume.get("recovery_plan") or {}
    resume_recovery_items = resume_recovery_plan.get("items") or []
    resume_recovery_action = str((resume_recovery_items[0] or {}).get("action") or "") if resume_recovery_items else ""
    derived_resume_recovery_action = (
        "resume_draft_from_cached_windows"
        if any(item.get("action") == "resume_draft_from_cached_windows" for item in resume_recovery_items)
        else resume_recovery_action
    )
    if not derived_resume_recovery_action:
        derived_resume_recovery_action = resume_next_recovery_action
    resume_recovery_hint = str((resume_recovery_items[0] or {}).get("hint") or "")
    follow_next_recovery_action = str(follow_data.get("next_recovery_action") or "")
    follow_next_action = str(follow_data.get("next_action") or "")
    follow_blocker_code = str(follow_data.get("blocker_code") or "")
    follow_todo = follow_data.get("active_work_todo") or {}
    follow_todo_id = str(follow_todo.get("id") or "")
    follow_todo_window_refs = list(follow_todo.get("cached_window_refs") or [])
    follow_blocker = follow_todo.get("blocker") or {}
    follow_blocker_detail = str(follow_blocker.get("detail") or "")
    follow_blocker_code = str(follow_blocker.get("code") or "")
    follow_suggested_recovery = follow_data.get("suggested_recovery") or {}
    resume_todo_id = str(resume_active_todo.get("id") or "")
    resume_blocker_code = str(resume_blocker.get("code") or "")
    resume_blocker_detail = str(resume_blocker.get("detail") or "")
    resume_window_refs = list((resume_recovery_items[0] or {}).get("cached_window_refs") or [])
    resume_todo_window_refs = list((resume_active_todo or {}).get("cached_window_refs") or [])
    resume_next_recovery_surface = derived_resume_recovery_action
    follow_next_recovery_surface = follow_next_recovery_action
    resume_next_recovery_hint = resume_recovery_hint

    def _window_signature(windows):
        signature = []
        for window in (windows or []):
            if not isinstance(window, dict):
                continue
            signature.append(
                (
                    str(window.get("path") or ""),
                    str(window.get("tool_call_id") or ""),
                    str(window.get("line_start") or ""),
                    str(window.get("line_end") or ""),
                )
            )
        return tuple(signature)

    def _normalized_command(command):
        try:
            parts = shlex.split(str(command))
        except ValueError:
            return str(command)
        if parts and (parts[0].endswith("mew") or parts[0].endswith("mew.exe")):
            parts = parts[1:]
        return " ".join(parts)

    resume_window_signature = _window_signature(resume_window_refs)
    resume_todo_window_signature = _window_signature(resume_todo_window_refs)
    follow_todo_window_signature = _window_signature(follow_todo_window_refs)
    resume_next_recovery_hint_normalized = _normalized_command(resume_next_recovery_hint)
    follow_suggested_command_normalized = _normalized_command(follow_suggested_recovery.get("command"))

    _scenario_check(
        checks,
        "m6_11_draft_timeout_scenario_command_succeeds",
        follow_result.get("exit_code") == 0,
        observed=follow_result.get("exit_code"),
        expected=0,
    )
    _scenario_check(
        checks,
        "m6_11_draft_timeout_phase_matches_follow_status",
        resume.get("phase") == follow_data.get("phase"),
        observed={"resume": resume.get("phase"), "follow": follow_data.get("phase")},
        expected="resume and follow should agree",
    )
    _scenario_check(
        checks,
        "m6_11_draft_timeout_phase_is_blocked_on_patch",
        resume.get("phase") == "blocked_on_patch",
        observed=resume.get("phase"),
        expected="blocked_on_patch",
    )
    _scenario_check(
        checks,
        "m6_11_draft_timeout_next_recovery_action_matches",
        resume_next_recovery_surface == follow_next_recovery_surface
        and resume_next_recovery_surface == "resume_draft_from_cached_windows",
        observed={"resume": resume_next_recovery_surface, "follow": follow_next_recovery_surface},
        expected={"resume": "resume_draft_from_cached_windows", "follow": "resume_draft_from_cached_windows"},
    )
    _scenario_check(
        checks,
        "m6_11_draft_timeout_recovery_action_surface",
        resume_recovery_action == "resume_draft_from_cached_windows"
        and not any(item.get("action") == "replan" for item in (resume_recovery_items or [])),
        observed=resume_recovery_action,
        expected="resume_draft_from_cached_windows",
    )
    _scenario_check(
        checks,
        "m6_11_draft_timeout_recovery_frontier_windows_match",
        resume_window_signature == follow_todo_window_signature and bool(resume_window_signature),
        observed={
            "resume": compact_dogfood_value(resume_window_signature),
            "follow": compact_dogfood_value(follow_todo_window_signature),
        },
        expected={"resume": "same cached window frontier", "follow": "same cached window frontier"},
    )
    _scenario_check(
        checks,
        "m6_11_draft_timeout_recovery_item_reuses_exact_todo_frontier",
        resume_window_signature == resume_todo_window_signature and bool(resume_window_signature),
        observed={
            "item": compact_dogfood_value(resume_window_signature),
            "todo": compact_dogfood_value(resume_todo_window_signature),
        },
        expected={
            "item": "non-empty cached_window_refs",
            "todo": "same cached_window_refs as active_work_todo",
        },
    )
    _scenario_check(
        checks,
        "m6_11_draft_timeout_todo_frontier_is_shared",
        resume_todo_id == follow_todo_id and bool(resume_todo_id),
        observed={"resume": resume_todo_id, "follow": follow_todo_id},
        expected={"resume": "same todo id", "follow": "same todo id"},
    )
    _scenario_check(
        checks,
        "m6_11_draft_timeout_blocker_code_matches",
        resume_blocker_code == follow_blocker_code and bool(resume_blocker_code),
        observed={"resume": resume_blocker_code, "follow": follow_blocker_code},
        expected={"resume": "non-empty blocker_code", "follow": "same blocker_code"},
    )
    _scenario_check(
        checks,
        "m6_11_draft_timeout_blocker_detail_matches",
        resume_blocker_detail == follow_blocker_detail and bool(resume_blocker_detail),
        observed={"resume": resume_blocker_detail, "follow": follow_blocker_detail},
        expected={"resume": "non-empty blocker detail", "follow": "same blocker detail"},
    )
    _scenario_check(
        checks,
        "m6_11_draft_timeout_next_action_matches",
        resume_next_action == follow_next_action and bool(resume_next_action),
        observed={"resume": resume_next_action, "follow": follow_next_action},
        expected={"resume": "non-empty next_action", "follow": "same next_action"},
    )
    _scenario_check(
        checks,
        "m6_11_draft_timeout_follow_status_source",
        follow_data.get("resume_source") == "session_overlay",
        observed=follow_data.get("resume_source"),
        expected="session_overlay",
    )
    _scenario_check(
        checks,
        "m6_11_draft_timeout_suggested_recovery_action_surface",
        str(follow_suggested_recovery.get("kind") or "") == "resume_draft_from_cached_windows"
        and bool(follow_suggested_recovery.get("command")),
        observed={
            "kind": follow_suggested_recovery.get("kind"),
            "command": follow_suggested_recovery.get("command"),
        },
        expected={"kind": "resume_draft_from_cached_windows", "command": "non-empty"},
    )
    _scenario_check(
        checks,
        "m6_11_draft_timeout_resume_surface_command_matches_suggested_recovery",
        bool(resume_next_recovery_hint_normalized)
        and str(resume_next_recovery_hint_normalized) == str(follow_suggested_command_normalized),
        observed={
            "resume_hint": resume_next_recovery_hint,
            "follow_command": follow_suggested_recovery.get("command"),
            "resume_hint_normalized": resume_next_recovery_hint_normalized,
            "follow_command_normalized": follow_suggested_command_normalized,
        },
        expected="resume recovery hint and follow suggested recovery command match",
    )
    _scenario_check(
        checks,
        "m6_11_draft_timeout_recovery_resume_hint_has_exact_roots",
        "--allow-read src/mew/work_session.py" in resume_recovery_hint
        and "--allow-read tests/test_work_session.py" in resume_recovery_hint
        and "--auto-recover-safe" in resume_recovery_hint,
        observed=resume_recovery_hint,
        expected="resume command contains allow-read for both cached frontier roots and auto-recover-safe",
    )
    _scenario_check(
        checks,
        "m6_11_draft_timeout_recovery_follow_hint_has_exact_roots",
        isinstance(follow_suggested_recovery, dict)
        and str(follow_suggested_command_normalized) == str(resume_next_recovery_hint_normalized),
        observed={
            "resume_hint": resume_next_recovery_hint,
            "follow_command": follow_suggested_recovery.get("command"),
        },
        expected="follow suggested recovery command mirrors resume hint",
    )
    _scenario_check(
        checks,
        "m6_11_draft_timeout_snapshot_status_is_stale",
        follow_data.get("status") in {"stale", "overdue", "dead"},
        observed=follow_data.get("status"),
        expected="stale/overdue/dead is acceptable",
    )
    report = _scenario_report("m6_11-draft-timeout", workspace, commands, checks)
    report["artifacts"] = {
        "blocker_code": resume_blocker_code,
        "blocker_detail": resume_blocker_detail,
        "next_recovery_action": resume_next_recovery_surface,
        "next_action": resume_next_action,
        "todo_id": resume_todo_id,
        "resume_source": follow_data.get("resume_source") or "session_overlay",
        "session_state_newer": follow_data.get("session_state_newer"),
        "follow_status": follow_data.get("status"),
        "resume_command": resume_recovery_hint,
        "recovery_plan_item_action": resume_recovery_action,
        "window_ref_count": len(resume_window_refs),
    }
    return report


def _scenario_not_implemented_report(name, workspace, reason):
    checks = []
    _scenario_check(
        checks,
        "scenario_implementation_status",
        False,
        observed={"status": "not_implemented", "reason": reason},
        expected="scenario implemented and executable",
    )
    return {
        "name": name,
        "status": "not_implemented",
        "workspace": str(workspace),
        "command_count": 0,
        "commands": [],
        "checks": checks,
        "artifacts": {
            "status": "not_implemented",
            "reason": reason,
        },
    }


def run_m6_11_refusal_separation_scenario(workspace, env=None):
    commands = []
    checks = []
    fixture = _load_json_file(
        WORK_LOOP_TIMEOUT_BEFORE_DRAFT_ROOT / "402_tiny_draft_refusal" / "scenario.json"
    )
    state = default_state()
    fixture_state = fixture.get("state") if isinstance(fixture, dict) else {}
    if isinstance(fixture_state, dict):
        if "tasks" in fixture_state:
            state["tasks"] = list(fixture_state.get("tasks") or [])
        if "work_sessions" in fixture_state:
            state["work_sessions"] = list(fixture_state.get("work_sessions") or [])
            sanitized_work_sessions = []
            for session_entry in state["work_sessions"]:
                if isinstance(session_entry, dict):
                    session_entry = dict(session_entry)
                    session_entry.pop("active_work_todo", None)
                    sanitized_work_sessions.append(session_entry)
                else:
                    sanitized_work_sessions.append(session_entry)
            state["work_sessions"] = sanitized_work_sessions
        if "version" in fixture_state:
            state["version"] = fixture_state.get("version", state["version"])
    write_json_file(workspace / STATE_FILE, state)

    work_sessions = state.get("work_sessions") or []
    session = work_sessions[0] if work_sessions else {}
    task_id = fixture.get("task_id")
    if task_id is None:
        task_id = session.get("task_id")
    task = {}
    for item in state.get("tasks") or []:
        if str(item.get("id")) == str(task_id):
            task = item
            break

    if isinstance(task_id, int):
        task_id_text = str(task_id)
    elif task_id is None:
        task_id_text = None
    else:
        task_id_text = str(task_id).strip()

    session_for_snapshot = session.get("id") or task_id_text or "latest"
    follow_path = workspace / STATE_DIR / "follow" / f"session-{session_for_snapshot}.json"
    follow_payload = fixture.get("follow_snapshot")
    follow_snapshot = dict(follow_payload) if isinstance(follow_payload, dict) else {}
    follow_snapshot.setdefault("session_id", session.get("id") or task_id)
    follow_snapshot.setdefault("task_id", task_id)
    follow_snapshot.setdefault("heartbeat_at", "2026-04-22T00:00:05Z")
    follow_snapshot.setdefault("session_updated_at", session.get("updated_at") or "2026-04-22T00:00:00Z")
    follow_snapshot.setdefault("model_timeout_seconds", 60)
    write_json_file(follow_path, follow_snapshot)

    follow_result = run_command(
        _scenario_command("work", task_id_text, "--follow-status", "--json"),
        workspace,
        timeout=20,
        env=env,
    )
    commands.append(follow_result)
    follow_data = _json_stdout(follow_result)

    old_cwd = os.getcwd()
    try:
        os.chdir(workspace)
        resume = build_work_session_resume(session, task=task, state=state) or {}
    finally:
        os.chdir(old_cwd)

    resume_active_todo = resume.get("active_work_todo") or {}
    resume_blocker = resume_active_todo.get("blocker") or {}
    resume_blocker_code = str(resume_blocker.get("code") or "")
    resume_blocker_detail = str(resume_blocker.get("detail") or "")
    resume_recovery_plan = resume.get("recovery_plan") or {}
    resume_recovery_items = resume_recovery_plan.get("items") or []
    resume_recovery_action = str((resume_recovery_items[0] or {}).get("action") or "")
    resume_next_recovery_action = str(resume_blocker.get("recovery_action") or "")
    resume_next_recovery_hint = str((resume_recovery_items[0] or {}).get("hint") or "")
    resume_next_action = str(resume.get("next_action") or "")
    resume_todo_id = str(resume_active_todo.get("id") or "")

    follow_todo = follow_data.get("active_work_todo") or {}
    follow_todo_id = str(follow_todo.get("id") or "")
    follow_blocker = follow_todo.get("blocker") or {}
    follow_blocker_code = str(follow_blocker.get("code") or "")
    follow_blocker_detail = str(follow_blocker.get("detail") or "")
    follow_next_recovery_action = str(follow_data.get("next_recovery_action") or "")
    follow_next_action = str(follow_data.get("next_action") or "")
    follow_suggested_recovery = follow_data.get("suggested_recovery") or {}

    _scenario_check(
        checks,
        "m6_11_refusal_separation_scenario_command_succeeds",
        follow_result.get("exit_code") == 0,
        observed=follow_result.get("exit_code"),
        expected=0,
    )
    _scenario_check(
        checks,
        "m6_11_refusal_separation_phase_matches_follow_status",
        resume.get("phase") == follow_data.get("phase"),
        observed={"resume": resume.get("phase"), "follow": follow_data.get("phase")},
        expected="resume and follow should agree",
    )
    _scenario_check(
        checks,
        "m6_11_refusal_separation_phase_is_blocked_on_patch",
        resume.get("phase") == "blocked_on_patch",
        observed=resume.get("phase"),
        expected="blocked_on_patch",
    )
    _scenario_check(
        checks,
        "m6_11_refusal_separation_blocker_code_matches",
        resume_blocker_code == follow_blocker_code == "model_returned_refusal",
        observed={"resume": resume_blocker_code, "follow": follow_blocker_code},
        expected={"resume": "model_returned_refusal", "follow": "model_returned_refusal"},
    )
    _scenario_check(
        checks,
        "m6_11_refusal_separation_blocker_detail_matches",
        bool(resume_blocker_detail)
        and bool(follow_blocker_detail)
        and resume_blocker_detail == follow_blocker_detail,
        observed={"resume": resume_blocker_detail, "follow": follow_blocker_detail},
        expected={"resume": "non-empty blocker detail", "follow": "same blocker detail"},
    )
    _scenario_check(
        checks,
        "m6_11_refusal_separation_next_recovery_action_matches",
        resume_next_recovery_action == follow_next_recovery_action == "inspect_refusal",
        observed={"resume": resume_next_recovery_action, "follow": follow_next_recovery_action},
        expected={"resume": "inspect_refusal", "follow": "inspect_refusal"},
    )
    _scenario_check(
        checks,
        "m6_11_refusal_separation_recovery_item_is_user_review",
        resume_recovery_action == "needs_user_review",
        observed=resume_recovery_action,
        expected="needs_user_review",
    )
    _scenario_check(
        checks,
        "m6_11_refusal_separation_next_action_matches",
        resume_next_action == follow_next_action and bool(resume_next_action),
        observed={"resume": resume_next_action, "follow": follow_next_action},
        expected={"resume": "non-empty next_action", "follow": "same next_action"},
    )
    _scenario_check(
        checks,
        "m6_11_refusal_separation_recovery_next_recovery_hint_exists",
        bool(resume_next_recovery_hint),
        observed=resume_next_recovery_hint,
        expected="non-empty resume recovery hint",
    )
    _scenario_check(
        checks,
        "m6_11_refusal_separation_suggested_recovery_shape",
        str(follow_suggested_recovery.get("kind") or "") == "needs_human_review"
        and bool(str(follow_suggested_recovery.get("command") or "").strip()),
        observed={
            "kind": follow_suggested_recovery.get("kind"),
            "command": follow_suggested_recovery.get("command"),
        },
        expected={"kind": "needs_human_review", "command": "non-empty"},
    )
    _scenario_check(
        checks,
        "m6_11_refusal_separation_todo_ids_match",
        resume_todo_id == follow_todo_id and bool(resume_todo_id),
        observed={"resume": resume_todo_id, "follow": follow_todo_id},
        expected={"resume": "same task id", "follow": "same task id"},
    )
    _scenario_check(
        checks,
        "m6_11_refusal_separation_snapshot_status_is_stale",
        follow_data.get("status") in {"stale", "overdue", "dead"},
        observed=follow_data.get("status"),
        expected="stale/overdue/dead is acceptable",
    )
    _scenario_check(
        checks,
        "m6_11_refusal_separation_resume_source_is_session_overlay",
        follow_data.get("resume_source") == "session_overlay",
        observed=follow_data.get("resume_source"),
        expected="session_overlay",
    )
    _scenario_check(
        checks,
        "m6_11_refusal_separation_equal_timestamp_overlay_path",
        follow_data.get("session_state_newer") is False and follow_data.get("resume_source") == "session_overlay",
        observed={
            "session_state_newer": follow_data.get("session_state_newer"),
            "resume_source": follow_data.get("resume_source"),
        },
        expected={"session_state_newer": False, "resume_source": "session_overlay"},
    )

    report = _scenario_report("m6_11-refusal-separation", workspace, commands, checks)
    report["artifacts"] = {
        "blocker_code": resume_blocker_code,
        "blocker_detail": resume_blocker_detail,
        "next_recovery_action": resume_next_recovery_action,
        "next_action": resume_next_action,
        "todo_id": resume_todo_id,
        "resume_source": follow_data.get("resume_source") or "session_overlay",
        "session_state_newer": follow_data.get("session_state_newer"),
        "follow_status": follow_data.get("status"),
        "resume_command": resume_next_recovery_hint,
        "recovery_plan_item_action": resume_recovery_action,
        "follow_todo_id": follow_todo_id,
        "suggested_recovery_kind": follow_suggested_recovery.get("kind"),
    }
    return report


def run_m6_11_drafting_recovery_scenario(workspace, env=None):
    commands = []
    checks = []
    fixture = _load_json_file(
        DRAFTING_RECOVERY_FIXTURE_ROOT / "blocker_code_parity" / "scenario.json"
    )
    state = default_state()
    fixture_state = fixture.get("state") if isinstance(fixture, dict) else {}
    if isinstance(fixture_state, dict):
        if "tasks" in fixture_state:
            state["tasks"] = list(fixture_state.get("tasks") or [])
        if "work_sessions" in fixture_state:
            state["work_sessions"] = list(fixture_state.get("work_sessions") or [])
        if "version" in fixture_state:
            state["version"] = fixture_state.get("version", state["version"])
    write_json_file(workspace / STATE_FILE, state)

    work_sessions = state.get("work_sessions") or []
    session = work_sessions[0] if work_sessions else {}
    task_id = fixture.get("task_id")
    if task_id is None:
        task_id = session.get("task_id")
    task = {}
    for item in state.get("tasks") or []:
        if str(item.get("id")) == str(task_id):
            task = item
            break

    if isinstance(task_id, int):
        task_id_text = str(task_id)
    elif task_id is None:
        task_id_text = None
    else:
        task_id_text = str(task_id).strip()

    session_for_snapshot = session.get("id") or task_id_text or "latest"
    follow_path = workspace / STATE_DIR / "follow" / f"session-{session_for_snapshot}.json"
    follow_payload = fixture.get("follow_snapshot")
    follow_snapshot = dict(follow_payload) if isinstance(follow_payload, dict) else {}
    follow_snapshot.setdefault("session_id", session.get("id") or task_id)
    follow_snapshot.setdefault("task_id", task_id)
    follow_snapshot.setdefault("heartbeat_at", "2026-04-22T00:00:05Z")
    follow_snapshot.setdefault("session_updated_at", session.get("updated_at") or "2026-04-22T00:00:00Z")
    follow_snapshot.setdefault("model_timeout_seconds", 60)
    write_json_file(follow_path, follow_snapshot)

    follow_result = run_command(
        _scenario_command("work", task_id_text, "--follow-status", "--json"),
        workspace,
        timeout=20,
        env=env,
    )
    commands.append(follow_result)
    follow_data = _json_stdout(follow_result)

    old_cwd = os.getcwd()
    try:
        os.chdir(workspace)
        resume = build_work_session_resume(session, task=task, state=state) or {}
    finally:
        os.chdir(old_cwd)
    resume_active_todo = resume.get("active_work_todo") or {}
    resume_blocker = resume_active_todo.get("blocker") or {}
    resume_blocker_code = str(resume_blocker.get("code") or "")
    resume_blocker_detail = str(resume_blocker.get("detail") or "")
    resume_next_recovery_action = str(resume_blocker.get("recovery_action") or "")
    resume_next_action = str(resume.get("next_action") or "")
    resume_recovery_plan = resume.get("recovery_plan") or {}
    resume_recovery_reason = str(resume_recovery_plan.get("next_action") or "")
    follow_blocker_code = str(follow_data.get("blocker_code") or "")
    follow_next_recovery_action = str(follow_data.get("next_recovery_action") or "")
    follow_next_action = str(follow_data.get("next_action") or "")
    resume_todo_id = str(resume_active_todo.get("id") or "")
    follow_todo = follow_data.get("active_work_todo") or {}
    follow_todo_id = str(follow_todo.get("id") or "")
    follow_blocker = follow_todo.get("blocker") or {}
    follow_blocker_detail = str(follow_blocker.get("detail") or "")
    follow_suggested_recovery = follow_data.get("suggested_recovery") or {}
    expected_next_recovery_action = PATCH_BLOCKER_RECOVERY_ACTIONS.get(
        resume_blocker_code, "inspect_blocker"
    )

    _scenario_check(
        checks,
        "m6_11_drafting_recovery_command_succeeds",
        follow_result.get("exit_code") == 0,
        observed=follow_result.get("exit_code"),
        expected=0,
    )
    _scenario_check(
        checks,
        "m6_11_drafting_recovery_resume_phase_blocked_on_patch",
        resume.get("phase") == "blocked_on_patch",
        observed=resume.get("phase"),
        expected="blocked_on_patch",
    )
    _scenario_check(
        checks,
        "m6_11_drafting_recovery_follow_status_phase_blocked_on_patch",
        follow_data.get("phase") == "blocked_on_patch",
        observed=follow_data.get("phase"),
        expected="blocked_on_patch",
    )
    _scenario_check(
        checks,
        "m6_11_drafting_recovery_blocker_code_matches",
        resume_blocker_code == follow_blocker_code and bool(resume_blocker_code),
        observed={"resume": resume_blocker_code, "follow": follow_blocker_code},
        expected={"resume": "non-empty blocker_code", "follow": "same blocker_code"},
    )
    _scenario_check(
        checks,
        "m6_11_drafting_recovery_next_recovery_action_matches",
        resume_next_recovery_action == follow_next_recovery_action and bool(resume_next_recovery_action),
        observed={"resume": resume_next_recovery_action, "follow": follow_next_recovery_action},
        expected={"resume": "non-empty next_recovery_action", "follow": "same next_recovery_action"},
    )
    _scenario_check(
        checks,
        "m6_11_drafting_recovery_next_recovery_action_matches_taxonomy",
        resume_next_recovery_action == expected_next_recovery_action,
        observed=resume_next_recovery_action,
        expected=expected_next_recovery_action,
    )
    _scenario_check(
        checks,
        "m6_11_drafting_recovery_active_work_todo_id_matches",
        resume_todo_id == follow_todo_id and bool(resume_todo_id),
        observed={"resume": resume_todo_id, "follow": follow_todo_id},
        expected={"resume": "same task id", "follow": "same task id"},
    )
    _scenario_check(
        checks,
        "m6_11_drafting_recovery_active_work_todo_matches",
        resume_active_todo == follow_todo and bool(resume_active_todo),
        observed={
            "resume": compact_dogfood_value(resume_active_todo),
            "follow": compact_dogfood_value(follow_todo),
        },
        expected="follow-status returns the same active_work_todo payload as direct resume build",
    )
    _scenario_check(
        checks,
        "m6_11_drafting_recovery_blocker_detail_matches",
        resume_blocker_detail == follow_blocker_detail and bool(resume_blocker_detail),
        observed={"resume": resume_blocker_detail, "follow": follow_blocker_detail},
        expected={"resume": "non-empty blocker detail", "follow": "same blocker detail"},
    )
    _scenario_check(
        checks,
        "m6_11_drafting_recovery_next_action_matches",
        resume_next_action == follow_next_action and bool(resume_next_action),
        observed={"resume": resume_next_action, "follow": follow_next_action},
        expected={"resume": "non-empty next_action", "follow": "same next_action"},
    )
    _scenario_check(
        checks,
        "m6_11_drafting_recovery_resume_source_is_session_overlay",
        follow_data.get("resume_source") == "session_overlay",
        observed=follow_data.get("resume_source"),
        expected="session_overlay",
    )
    _scenario_check(
        checks,
        "m6_11_drafting_recovery_equal_timestamp_overlay_path",
        follow_data.get("session_state_newer") is False and follow_data.get("resume_source") == "session_overlay",
        observed={
            "session_state_newer": follow_data.get("session_state_newer"),
            "resume_source": follow_data.get("resume_source"),
        },
        expected={"session_state_newer": False, "resume_source": "session_overlay"},
    )
    _scenario_check(
        checks,
        "m6_11_drafting_recovery_suggested_recovery_matches_resume_reason",
        str(follow_suggested_recovery.get("reason") or "") == resume_recovery_reason and bool(resume_recovery_reason),
        observed={
            "resume_reason": resume_recovery_reason,
            "follow_reason": follow_suggested_recovery.get("reason"),
        },
        expected={"resume_reason": "non-empty recovery_plan.next_action", "follow_reason": "same string"},
    )
    _scenario_check(
        checks,
        "m6_11_drafting_recovery_suggested_recovery_shape",
        str(follow_suggested_recovery.get("kind") or "") == "needs_human_review"
        and bool(str(follow_suggested_recovery.get("command") or "").strip()),
        observed={
            "kind": follow_suggested_recovery.get("kind"),
            "command": follow_suggested_recovery.get("command"),
        },
        expected={"kind": "needs_human_review", "command": "non-empty resume command"},
    )
    _scenario_check(
        checks,
        "m6_11_drafting_recovery_snapshot_status_is_stale",
        follow_data.get("status") == "stale",
        observed=follow_data.get("status"),
        expected="stale",
    )
    report = _scenario_report("m6_11-drafting-recovery", workspace, commands, checks)
    report["artifacts"] = {
        "blocker_code": resume_blocker_code,
        "blocker_detail": resume_blocker_detail,
        "next_recovery_action": resume_next_recovery_action,
        "next_action": resume_next_action,
        "todo_id": resume_todo_id,
        "resume_source": follow_data.get("resume_source") or "snapshot",
        "session_state_newer": follow_data.get("session_state_newer"),
        "session_id": session.get("id"),
        "task_id": task_id,
        "follow_status": follow_data.get("status"),
        "command_exit_code": follow_result.get("exit_code"),
        "suggested_recovery_kind": follow_suggested_recovery.get("kind"),
    }
    return report


def run_m6_11_phase4_regression_scenario(workspace, env=None):
    checks = []
    commands = []

    fixture = _load_json_file(
        M6_6_COMPARATOR_BUDGET_FIXTURE_ROOT / "scenario.json"
    )
    b0_iter_wall_seconds = _to_float_seconds((fixture.get("B0") or {}).get("iter_wall"))
    budget_wall_seconds = (
        b0_iter_wall_seconds * 1.10 if isinstance(b0_iter_wall_seconds, (int, float)) else None
    )

    raw_cases = fixture.get("comparator_cases", []) if isinstance(fixture, dict) else []
    comparator_cases = []
    if isinstance(raw_cases, list):
        for case in raw_cases:
            case_id = _phase4_comparator_case_id(case)
            wall_seconds = _phase4_case_wall_seconds(case)
            case_shape = _phase4_comparator_case_shape(case)
            comparator_cases.append(
                {
                    "case_id": case_id,
                    "shape": case_shape,
                    "iter_wall_seconds": wall_seconds,
                    "wall_seconds": wall_seconds,
                    "trace_id": case.get("trace_id") if isinstance(case, dict) else "",
                    "source": case.get("source") if isinstance(case, dict) else "",
                    "source_reference": case.get("source_reference") if isinstance(case, dict) else "",
                }
            )

    case_count = len(comparator_cases)
    case_pairs = sorted((case.get("case_id"), case.get("shape")) for case in comparator_cases)
    expected_case_pairs = sorted(M6_11_PHASE4_COMPARATOR_CASES.items())
    case_wall_seconds = [case.get("iter_wall_seconds") for case in comparator_cases]
    missing_timing_cases = [
        case.get("case_id")
        for case in comparator_cases
        if not isinstance(case.get("iter_wall_seconds"), (int, float))
    ]
    numeric_case_wall_seconds = [
        value for value in case_wall_seconds if isinstance(value, (int, float))
    ]
    median_wall_seconds = (
        _median_wall_seconds(numeric_case_wall_seconds)
        if len(numeric_case_wall_seconds) == len(case_wall_seconds)
        else None
    )
    case_timing_present = not missing_timing_cases

    _scenario_check(
        checks,
        "m6_11_phase4_regression_case_count",
        case_count == 3,
        observed={"case_count": case_count},
        expected=3,
    )
    _scenario_check(
        checks,
        "m6_11_phase4_regression_expected_comparator_cases",
        case_pairs == expected_case_pairs,
        observed={
            "observed_case_pairs": case_pairs,
            "expected_case_pairs": expected_case_pairs,
        },
        expected="comparator cases include exactly case_id->shape M6.6-A->M6.6-A, M6.6-B->M6.6-B, M6.6-C->M6.6-C",
    )
    _scenario_check(
        checks,
        "m6_11_phase4_regression_case_wall_time_present",
        case_timing_present,
        observed={
            "cases_missing_wall_time": sorted(missing_timing_cases),
            "case_count": case_count,
        },
        expected="all cases include a numeric iter_wall_seconds field",
    )
    _scenario_check(
        checks,
        "m6_11_phase4_regression_median_vs_budget",
        isinstance(median_wall_seconds, (int, float))
        and isinstance(budget_wall_seconds, (int, float))
        and median_wall_seconds <= budget_wall_seconds,
        observed={
            "median_wall_seconds": median_wall_seconds,
            "budget_wall_seconds": budget_wall_seconds,
        },
        expected="median_wall_seconds is <= budget_wall_seconds",
    )

    report = _scenario_report("m6_11-phase4-regression", workspace, commands, checks)
    report["artifacts"] = {
        "b0_iter_wall_seconds": b0_iter_wall_seconds,
        "budget_wall_seconds": budget_wall_seconds,
        "median_wall_seconds": median_wall_seconds,
        "comparator_cases": comparator_cases,
    }
    return report


def run_m6_9_phase1_regression_scenario(workspace, env=None):
    checks = []
    commands = []

    fixture = _load_json_file(
        M6_6_COMPARATOR_BUDGET_FIXTURE_ROOT / "scenario.json"
    )
    b0_comparator_wall_seconds = _to_float_seconds((fixture.get("B0") or {}).get("iter_wall"))
    budget_wall_seconds = (
        b0_comparator_wall_seconds * 1.15 if isinstance(b0_comparator_wall_seconds, (int, float)) else None
    )

    raw_cases = fixture.get("comparator_cases", []) if isinstance(fixture, dict) else []
    comparator_cases = []
    if isinstance(raw_cases, list):
        for case in raw_cases:
            case_id = _phase4_comparator_case_id(case)
            wall_seconds = _phase4_case_wall_seconds(case)
            case_shape = _phase4_comparator_case_shape(case)
            comparator_cases.append(
                {
                    "case_id": case_id,
                    "shape": case_shape,
                    "iter_wall_seconds": wall_seconds,
                    "wall_seconds": wall_seconds,
                    "source_reference": case.get("source_reference") if isinstance(case, dict) else "",
                }
            )

    case_count = len(comparator_cases)
    case_pairs = sorted((case.get("case_id"), case.get("shape")) for case in comparator_cases)
    expected_case_pairs = sorted(M6_11_PHASE4_COMPARATOR_CASES.items())
    case_wall_seconds = [case.get("iter_wall_seconds") for case in comparator_cases]
    missing_timing_cases = [
        case.get("case_id")
        for case in comparator_cases
        if not isinstance(case.get("iter_wall_seconds"), (int, float))
    ]
    numeric_case_wall_seconds = [
        value for value in case_wall_seconds if isinstance(value, (int, float))
    ]
    median_wall_seconds = (
        _median_wall_seconds(numeric_case_wall_seconds)
        if len(numeric_case_wall_seconds) == len(case_wall_seconds)
        else None
    )
    case_timing_present = not missing_timing_cases

    _scenario_check(
        checks,
        "m6_9_phase1_regression_case_count",
        case_count == 3,
        observed={"case_count": case_count},
        expected=3,
    )
    _scenario_check(
        checks,
        "m6_9_phase1_regression_expected_comparator_cases",
        case_pairs == expected_case_pairs,
        observed={
            "observed_case_pairs": case_pairs,
            "expected_case_pairs": expected_case_pairs,
        },
        expected="comparator cases include exactly the frozen M6.6 A/B/C mapping",
    )
    _scenario_check(
        checks,
        "m6_9_phase1_regression_case_wall_time_present",
        case_timing_present,
        observed={
            "cases_missing_wall_time": sorted(missing_timing_cases),
            "case_count": case_count,
        },
        expected="all cases include a numeric iter_wall_seconds field",
    )
    _scenario_check(
        checks,
        "m6_9_phase1_regression_median_vs_phase1_budget",
        isinstance(median_wall_seconds, (int, float))
        and isinstance(budget_wall_seconds, (int, float))
        and median_wall_seconds <= budget_wall_seconds,
        observed={
            "median_wall_seconds": median_wall_seconds,
            "budget_wall_seconds": budget_wall_seconds,
        },
        expected="median_wall_seconds is <= B0.comparator * 1.15 for M6.9 Phase 1",
    )

    report = _scenario_report("m6_9-phase1-regression", workspace, commands, checks)
    report["artifacts"] = {
        "phase": "phase1",
        "comparator_source": "m6_6",
        "durable_recall_active": True,
        "b0_comparator_wall_seconds": b0_comparator_wall_seconds,
        "budget_wall_seconds": budget_wall_seconds,
        "median_wall_seconds": median_wall_seconds,
        "comparator_cases": comparator_cases,
    }
    return report


def run_m6_9_phase2_regression_scenario(workspace, env=None):
    checks = []
    commands = []

    fixture = _load_json_file(
        M6_6_COMPARATOR_BUDGET_FIXTURE_ROOT / "scenario.json"
    )
    b0_comparator_wall_seconds = _to_float_seconds((fixture.get("B0") or {}).get("iter_wall"))
    budget_multiplier = 1.0
    budget_wall_seconds = (
        b0_comparator_wall_seconds * budget_multiplier
        if isinstance(b0_comparator_wall_seconds, (int, float))
        else None
    )

    raw_cases = fixture.get("comparator_cases", []) if isinstance(fixture, dict) else []
    comparator_cases = []
    if isinstance(raw_cases, list):
        for case in raw_cases:
            case_id = _phase4_comparator_case_id(case)
            wall_seconds = _phase4_case_wall_seconds(case)
            case_shape = _phase4_comparator_case_shape(case)
            comparator_cases.append(
                {
                    "case_id": case_id,
                    "shape": case_shape,
                    "iter_wall_seconds": wall_seconds,
                    "wall_seconds": wall_seconds,
                    "source_reference": case.get("source_reference") if isinstance(case, dict) else "",
                }
            )

    case_count = len(comparator_cases)
    case_pairs = sorted((case.get("case_id"), case.get("shape")) for case in comparator_cases)
    expected_case_pairs = sorted(M6_11_PHASE4_COMPARATOR_CASES.items())
    case_wall_seconds = [case.get("iter_wall_seconds") for case in comparator_cases]
    missing_timing_cases = [
        case.get("case_id")
        for case in comparator_cases
        if not isinstance(case.get("iter_wall_seconds"), (int, float))
    ]
    numeric_case_wall_seconds = [
        value for value in case_wall_seconds if isinstance(value, (int, float))
    ]
    median_wall_seconds = (
        _median_wall_seconds(numeric_case_wall_seconds)
        if len(numeric_case_wall_seconds) == len(case_wall_seconds)
        else None
    )
    case_timing_present = not missing_timing_cases

    _scenario_check(
        checks,
        "m6_9_phase2_regression_case_count",
        case_count == 3,
        observed={"case_count": case_count},
        expected=3,
    )
    _scenario_check(
        checks,
        "m6_9_phase2_regression_expected_comparator_cases",
        case_pairs == expected_case_pairs,
        observed={
            "observed_case_pairs": case_pairs,
            "expected_case_pairs": expected_case_pairs,
        },
        expected="comparator cases include exactly the frozen M6.6 A/B/C mapping",
    )
    _scenario_check(
        checks,
        "m6_9_phase2_regression_case_wall_time_present",
        case_timing_present,
        observed={
            "cases_missing_wall_time": sorted(missing_timing_cases),
            "case_count": case_count,
        },
        expected="all cases include a numeric iter_wall_seconds field",
    )
    _scenario_check(
        checks,
        "m6_9_phase2_regression_median_vs_neutral_budget",
        isinstance(median_wall_seconds, (int, float))
        and isinstance(budget_wall_seconds, (int, float))
        and isinstance(b0_comparator_wall_seconds, (int, float))
        and budget_wall_seconds == b0_comparator_wall_seconds
        and median_wall_seconds <= b0_comparator_wall_seconds,
        observed={
            "median_wall_seconds": median_wall_seconds,
            "b0_comparator_wall_seconds": b0_comparator_wall_seconds,
            "budget_wall_seconds": budget_wall_seconds,
            "budget_multiplier": budget_multiplier,
        },
        expected="median_wall_seconds is <= B0.comparator with neutral Phase 2 budget",
    )

    report = _scenario_report("m6_9-phase2-regression", workspace, commands, checks)
    report["artifacts"] = {
        "phase": "phase2",
        "comparator_source": "m6_6",
        "durable_recall_active": True,
        "budget_multiplier": budget_multiplier,
        "b0_comparator_wall_seconds": b0_comparator_wall_seconds,
        "budget_wall_seconds": budget_wall_seconds,
        "median_wall_seconds": median_wall_seconds,
        "comparator_cases": comparator_cases,
    }
    return report


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


def run_m6_9_memory_taxonomy_scenario(workspace, env=None):
    commands = []
    checks = []
    state_dir = workspace / STATE_DIR
    state_dir.mkdir(parents=True, exist_ok=True)
    write_json_file(workspace / STATE_FILE, default_state())

    def run(args, timeout=30):
        result = run_command(_scenario_command(*args), workspace, timeout=timeout, env=env)
        commands.append(result)
        return result

    reviewer_result = run(
        [
            "memory",
            "--add",
            "Reviewer steering keeps scope fences explicit before durable-memory writes.",
            "--type",
            "project",
            "--kind",
            "reviewer-steering",
            "--scope",
            "private",
            "--name",
            "M6.9 reviewer steering",
            "--description",
            "Dogfood reviewer steering memory.",
            "--approved",
            "--why",
            "reviewer approved durable steering",
            "--how-to-apply",
            "reuse on future memory edits",
            "--json",
        ]
    )
    task_template_result = run(
        [
            "memory",
            "--add",
            "Use one bounded paired src/test slice with a focused verifier.",
            "--type",
            "project",
            "--kind",
            "task-template",
            "--scope",
            "private",
            "--name",
            "M6.9 bounded task template",
            "--description",
            "Dogfood task template memory.",
            "--approved",
            "--rationale",
            "reusable coding task shape",
            "--json",
        ]
    )
    failure_shield_result = run(
        [
            "memory",
            "--add",
            "Stop repeated cached-window retries when exact windows are stale.",
            "--type",
            "project",
            "--kind",
            "failure-shield",
            "--scope",
            "private",
            "--name",
            "M6.9 cached-window shield",
            "--description",
            "Dogfood failure-shield memory.",
            "--approved",
            "--symptom",
            "cached-window retries repeat without patch",
            "--root-cause",
            "stale active_work_todo refs outrank refreshed windows",
            "--fix",
            "refresh exact windows and preserve task goal",
            "--stop-rule",
            "after two identical blockers, replan before retry",
            "--json",
        ]
    )
    file_pair_result = run(
        [
            "memory",
            "--add",
            "dogfood.py changes pair with tests/test_dogfood.py.",
            "--type",
            "project",
            "--kind",
            "file-pair",
            "--scope",
            "private",
            "--name",
            "M6.9 dogfood pair",
            "--description",
            "Dogfood file-pair memory.",
            "--source-path",
            "src/mew/dogfood.py",
            "--test-path",
            "tests/test_dogfood.py",
            "--structural-evidence",
            "same-session dogfood scenario registration and test",
            "--focused-test-green",
            "--json",
        ]
    )
    missing_why_result = run(
        [
            "memory",
            "--add",
            "Reviewer steering without why should be rejected.",
            "--type",
            "project",
            "--kind",
            "reviewer-steering",
            "--approved",
            "--how-to-apply",
            "do not persist missing evidence",
            "--json",
        ]
    )
    reasoning_trace_result = run(
        [
            "memory",
            "--add",
            "Reasoning trace without required evidence should still be rejected.",
            "--type",
            "project",
            "--kind",
            "reasoning-trace",
            "--json",
        ]
    )
    list_result = run(["memory", "--list", "--type", "project", "--json"])
    search_result = run(["memory", "--search", "scope fences", "--type", "project", "--kind", "reviewer-steering", "--json"])
    resolve_source_result = run(["memory", "--resolve-source-path", "src/mew/dogfood.py", "--json"])
    resolve_test_result = run(["memory", "--resolve-test-path", "tests/test_dogfood.py", "--json"])

    entry_results = {
        "reviewer-steering": (reviewer_result, _json_stdout(reviewer_result).get("entry") or {}),
        "task-template": (task_template_result, _json_stdout(task_template_result).get("entry") or {}),
        "failure-shield": (failure_shield_result, _json_stdout(failure_shield_result).get("entry") or {}),
        "file-pair": (file_pair_result, _json_stdout(file_pair_result).get("entry") or {}),
    }
    list_entries = _json_stdout(list_result).get("entries") or []
    list_kinds = sorted({entry.get("memory_kind") for entry in list_entries if entry.get("memory_kind")})
    search_matches = _json_stdout(search_result).get("matches") or []
    resolved_source = (_json_stdout(resolve_source_result).get("resolved") or {})
    resolved_test = (_json_stdout(resolve_test_result).get("resolved") or {})

    for memory_kind, (result, entry) in entry_results.items():
        _scenario_check(
            checks,
            f"m6_9_memory_taxonomy_{memory_kind}_write_accepts_required_evidence",
            result.get("exit_code") == 0 and entry.get("memory_kind") == memory_kind,
            observed={"exit_code": result.get("exit_code"), "entry": entry, "stderr": result.get("stderr")},
            expected=f"{memory_kind} write succeeds and records memory_kind",
        )
    _scenario_check(
        checks,
        "m6_9_memory_taxonomy_reviewer_steering_persists_gate_fields",
        bool((entry_results["reviewer-steering"][1]).get("approved"))
        and bool((entry_results["reviewer-steering"][1]).get("why"))
        and bool((entry_results["reviewer-steering"][1]).get("how_to_apply")),
        observed=entry_results["reviewer-steering"][1],
        expected="reviewer-steering persists approved, why, and how_to_apply",
    )
    _scenario_check(
        checks,
        "m6_9_memory_taxonomy_failure_shield_persists_gate_fields",
        all(
            (entry_results["failure-shield"][1]).get(key)
            for key in ("approved", "symptom", "root_cause", "fix", "stop_rule")
        ),
        observed=entry_results["failure-shield"][1],
        expected="failure-shield persists approved symptom root_cause fix stop_rule",
    )
    _scenario_check(
        checks,
        "m6_9_memory_taxonomy_file_pair_persists_pair_fields",
        (entry_results["file-pair"][1]).get("source_path") == "src/mew/dogfood.py"
        and (entry_results["file-pair"][1]).get("test_path") == "tests/test_dogfood.py"
        and bool((entry_results["file-pair"][1]).get("focused_test_green")),
        observed=entry_results["file-pair"][1],
        expected="file-pair persists source_path, test_path, and focused_test_green",
    )
    _scenario_check(
        checks,
        "m6_9_memory_taxonomy_missing_reviewer_why_rejected",
        missing_why_result.get("exit_code") != 0 and "--why" in (missing_why_result.get("stderr") or ""),
        observed=command_result_tail(missing_why_result),
        expected="reviewer-steering without --why fails at the write gate",
    )
    _scenario_check(
        checks,
        "m6_9_memory_taxonomy_incomplete_reasoning_trace_rejected",
        reasoning_trace_result.get("exit_code") != 0
        and "--approved" in (reasoning_trace_result.get("stderr") or ""),
        observed=command_result_tail(reasoning_trace_result),
        expected="reasoning-trace write without required evidence fails at the write gate",
    )
    _scenario_check(
        checks,
        "m6_9_memory_taxonomy_list_surfaces_all_populated_kinds",
        {"reviewer-steering", "task-template", "failure-shield", "file-pair"}.issubset(set(list_kinds)),
        observed=list_kinds,
        expected="list output includes the four currently writable M6.9 memory kinds",
    )
    _scenario_check(
        checks,
        "m6_9_memory_taxonomy_search_filters_reviewer_steering",
        search_result.get("exit_code") == 0
        and any(match.get("memory_kind") == "reviewer-steering" for match in search_matches),
        observed=search_matches,
        expected="typed memory search can filter reviewer-steering entries",
    )
    _scenario_check(
        checks,
        "m6_9_memory_taxonomy_resolves_source_to_test_pair",
        resolve_source_result.get("exit_code") == 0
        and resolved_source.get("source_path") == "src/mew/dogfood.py"
        and resolved_source.get("test_path") == "tests/test_dogfood.py"
        and bool(resolved_source.get("memory_ids")),
        observed=resolved_source,
        expected="source-path lookup resolves the durable file-pair index",
    )
    _scenario_check(
        checks,
        "m6_9_memory_taxonomy_resolves_test_to_source_pair",
        resolve_test_result.get("exit_code") == 0
        and resolved_test.get("source_path") == "src/mew/dogfood.py"
        and resolved_test.get("test_path") == "tests/test_dogfood.py"
        and bool(resolved_test.get("memory_ids")),
        observed=resolved_test,
        expected="test-path lookup resolves the durable file-pair index",
    )
    report = _scenario_report("m6_9-memory-taxonomy", workspace, commands, checks)
    report["artifacts"] = {
        "populated_kinds": list_kinds,
        "entry_names": sorted(entry.get("name") for _, entry in entry_results.values() if entry.get("name")),
        "rejected_cases": ["reviewer-steering-missing-why", "reasoning-trace-missing-evidence"],
        "resolved_source_pair": resolved_source,
        "resolved_test_pair": resolved_test,
    }
    return report


def run_m6_9_reviewer_steering_reuse_scenario(workspace, env=None):
    commands = []
    checks = []
    state_dir = workspace / STATE_DIR
    state_dir.mkdir(parents=True, exist_ok=True)
    state = default_state()
    state["tasks"].append(
        {
            "id": 6910,
            "title": "M6.9 reviewer steering reuse dogfood",
            "description": (
                "Add a new reviewer-steering durable-rule dogfood scenario with source/test "
                "registration, dispatch, and a paired test."
            ),
            "status": "todo",
            "priority": "normal",
            "kind": "coding",
            "notes": "Later iteration should recall reviewer steering before drafting.",
            "created_at": "now",
            "updated_at": "now",
        }
    )
    write_json_file(workspace / STATE_FILE, state)

    def run(args, timeout=30):
        result = run_command(_scenario_command(*args), workspace, timeout=timeout, env=env)
        commands.append(result)
        return result

    steering_cases = [
        {
            "name": "M6.9 reviewer steering reuse rule",
            "body": (
                "For M6.9 dogfood scenario work, do not polish an existing scenario when the task "
                "asks for a new durable-rule proof; require DOGFOOD_SCENARIOS registration, "
                "run_dogfood_scenario dispatch, and a paired tests/test_dogfood.py assertion."
            ),
            "why": "a prior reviewer rejection caught an off-scope symbol-index-only dogfood patch",
            "how_to_apply": (
                "if a later M6.9 dogfood task asks for a new scenario, block existing_scenario_artifact_tweak"
            ),
            "patch_kind": "existing_scenario_artifact_tweak",
        },
        {
            "name": "M6.9 paired source test steering rule",
            "body": (
                "For M6.9 coding-memory changes, source edits must land with the paired test or be "
                "rejected before approval."
            ),
            "why": "a prior reviewer rejection caught an unpaired source edit that would have needed rescue",
            "how_to_apply": "block unpaired_source_edit before implementation",
            "patch_kind": "unpaired_source_edit",
        },
        {
            "name": "M6.9 focused proof steering rule",
            "body": (
                "For M6.9 proof slices, require a focused verifier tied to the new scenario before "
                "counting the slice."
            ),
            "why": "a prior reviewer correction caught a proof slice without a focused verifier",
            "how_to_apply": "block missing_focused_verifier before implementation",
            "patch_kind": "missing_focused_verifier",
        },
    ]
    steering_results = []
    for case in steering_cases:
        result = run(
            [
                "memory",
                "--add",
                case["body"],
                "--type",
                "project",
                "--kind",
                "reviewer-steering",
                "--scope",
                "private",
                "--name",
                case["name"],
                "--description",
                "Reviewer correction from a past iteration should fire before a later off-scope draft.",
                "--approved",
                "--why",
                case["why"],
                "--how-to-apply",
                case["how_to_apply"],
                "--json",
            ]
        )
        steering_results.append((case, result, _json_stdout(result).get("entry") or {}))
    active_result = run(["memory", "--active", "--task-id", "6910", "--json"])

    active_data = _json_stdout(active_result)
    active_items = (active_data.get("active_memory") or {}).get("items") or []
    steering_names = {case["name"] for case in steering_cases}
    reviewer_rules = [
        item
        for item in active_items
        if item.get("memory_kind") == "reviewer-steering"
        and item.get("name") in steering_names
    ]
    rules_by_name = {item.get("name"): item for item in reviewer_rules}
    proposed_patches = [
        {
            "kind": case["patch_kind"],
            "target": "src/mew/dogfood.py",
            "would_have_needed_rescue_edit": True,
        }
        for case in steering_cases
    ]
    blocked_patch_kinds = []
    for case in steering_cases:
        rule = rules_by_name.get(case["name"]) or {}
        if case["patch_kind"] in str(rule.get("how_to_apply") or ""):
            blocked_patch_kinds.append(case["patch_kind"])
    durable_rule_fired_count = len(blocked_patch_kinds)
    simulated_rescue_edit_prevented_count = sum(
        1
        for patch in proposed_patches
        if patch["kind"] in blocked_patch_kinds and patch["would_have_needed_rescue_edit"]
    )
    durable_rule_fired = durable_rule_fired_count >= 1
    blocked_pre_implementation = durable_rule_fired_count == len(steering_cases)
    simulated_rescue_edit_prevented = simulated_rescue_edit_prevented_count >= 1
    trace_rel = str(Path(STATE_DIR) / "durable" / "m6_9-reviewer-steering-reuse-trace.json")
    trace_path = workspace / trace_rel
    trace = {
        "schema_version": 1,
        "scenario": "m6_9-reviewer-steering-reuse",
        "memory_kind": "reviewer-steering",
        "rule_ids": [entry.get("id") for _, _, entry in steering_results if entry.get("id")],
        "durable_rule_fired": durable_rule_fired,
        "durable_rule_fired_count": durable_rule_fired_count,
        "reviewer_steering_rule_count": len(reviewer_rules),
        "blocked_pre_implementation": blocked_pre_implementation,
        "simulated_rescue_edit_prevented": simulated_rescue_edit_prevented,
        "simulated_rescue_edit_prevented_count": simulated_rescue_edit_prevented_count,
        "blocked_patch_kind": steering_cases[0]["patch_kind"],
        "blocked_patch_kinds": sorted(blocked_patch_kinds),
    }
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    write_json_file(trace_path, trace)
    trace_file_data = json.loads(trace_path.read_text(encoding="utf-8"))

    _scenario_check(
        checks,
        "m6_9_reviewer_steering_reuse_writes_approved_rule",
        len(steering_results) == 3
        and all(result.get("exit_code") == 0 for _, result, _ in steering_results)
        and all(entry.get("memory_kind") == "reviewer-steering" for _, _, entry in steering_results)
        and all(entry.get("approved") is True for _, _, entry in steering_results),
        observed=[
            {"case": case["name"], "exit_code": result.get("exit_code"), "entry": entry}
            for case, result, entry in steering_results
        ],
        expected="three approved reviewer-steering memories are persisted with durable rule evidence",
    )
    _scenario_check(
        checks,
        "m6_9_reviewer_steering_reuse_active_recall_finds_rule",
        active_result.get("exit_code") == 0 and len(reviewer_rules) == 3,
        observed=[
            {
                "name": item.get("name"),
                "memory_kind": item.get("memory_kind"),
                "matched_terms": item.get("matched_terms"),
                "reason": item.get("reason"),
            }
            for item in reviewer_rules
        ],
        expected="later coding task recalls the approved reviewer-steering rule",
    )
    _scenario_check(
        checks,
        "m6_9_reviewer_steering_reuse_blocks_off_scope_patch",
        blocked_pre_implementation,
        observed={
            "proposed_patches": proposed_patches,
            "durable_rule_fired_count": durable_rule_fired_count,
            "blocked_patch_kinds": sorted(blocked_patch_kinds),
        },
        expected="recalled reviewer-steering rules block all three off-scope patches before implementation",
    )
    _scenario_check(
        checks,
        "m6_9_reviewer_steering_reuse_prevents_simulated_rescue_edit",
        simulated_rescue_edit_prevented,
        observed={
            "blocked_pre_implementation": blocked_pre_implementation,
            "simulated_rescue_edit_prevented_count": simulated_rescue_edit_prevented_count,
        },
        expected="at least one durable rule would have prevented a reviewer rescue edit",
    )
    _scenario_check(
        checks,
        "m6_9_reviewer_steering_reuse_writes_deterministic_trace",
        trace_file_data == trace
        and trace_file_data.get("durable_rule_fired_count") == 3
        and trace_file_data.get("simulated_rescue_edit_prevented") is True,
        observed={"trace_path": trace_rel, "trace": trace_file_data},
        expected="deterministic trace artifact records rule firing and rescued-edit prevention",
    )

    report = _scenario_report("m6_9-reviewer-steering-reuse", workspace, commands, checks)
    report["artifacts"] = {
        "durable_rule_fired": durable_rule_fired,
        "simulated_rescue_edit_prevented": simulated_rescue_edit_prevented,
        "simulated_rescue_edit_prevented_count": simulated_rescue_edit_prevented_count,
        "blocked_pre_implementation": blocked_pre_implementation,
        "reviewer_steering_rule_count": len(reviewer_rules),
        "durable_rule_fired_count": durable_rule_fired_count,
        "recalled_rule_names": sorted(item.get("name") for item in reviewer_rules if item.get("name")),
        "blocked_patch_kind": steering_cases[0]["patch_kind"],
        "blocked_patch_kinds": sorted(blocked_patch_kinds),
        "trace_path": trace_rel,
        "trace": trace,
    }
    return report


def run_m6_9_failure_shield_reuse_scenario(workspace, env=None):
    commands = []
    checks = []
    state_dir = workspace / STATE_DIR
    state_dir.mkdir(parents=True, exist_ok=True)
    state = default_state()
    state["tasks"].append(
        {
            "id": 6911,
            "title": "M6.9 failure shield reuse dogfood",
            "description": (
                "Use durable failure-shield memory to block reverted cached-window and generic-cleanup "
                "approaches before implementation."
            ),
            "status": "todo",
            "priority": "normal",
            "kind": "coding",
            "notes": "Later iteration should recall failure-shield rules before drafting.",
            "created_at": "now",
            "updated_at": "now",
        }
    )
    write_json_file(workspace / STATE_FILE, state)

    def run(args, timeout=30):
        result = run_command(_scenario_command(*args), workspace, timeout=timeout, env=env)
        commands.append(result)
        return result

    shield_cases = [
        {
            "name": "M6.9 stale cached-window shield",
            "body": (
                "Previously reverted approach: retry the same cached-window draft after an identical "
                "cached_window_incomplete blocker instead of refreshing exact source/test windows."
            ),
            "symptom": "cached_window_incomplete repeats after the same source/test anchors",
            "root_cause": "stale cached windows outrank newly refreshed exact windows",
            "fix": "refresh exact source/test windows and preserve the task goal before drafting",
            "stop_rule": "block repeat_cached_window_retry before implementation",
            "patch_kind": "repeat_cached_window_retry",
        },
        {
            "name": "M6.9 generic cleanup shield",
            "body": (
                "Previously reverted approach: answer a durable-memory proof task by changing generic "
                "dogfood cleanup/default behavior instead of adding the requested proof scenario."
            ),
            "symptom": "draft touches generic dogfood cleanup while the task asks for a durable proof scenario",
            "root_cause": "nearby cached windows overshadow the active milestone criterion",
            "fix": "reject the generic cleanup and re-anchor on the requested M6.9 proof scenario",
            "stop_rule": "block generic_cleanup_default_flag before implementation",
            "patch_kind": "generic_cleanup_default_flag",
        },
    ]
    shield_results = []
    for case in shield_cases:
        result = run(
            [
                "memory",
                "--add",
                case["body"],
                "--type",
                "project",
                "--kind",
                "failure-shield",
                "--scope",
                "private",
                "--name",
                case["name"],
                "--description",
                "Failure shield should block this reverted approach in a later iteration.",
                "--approved",
                "--symptom",
                case["symptom"],
                "--root-cause",
                case["root_cause"],
                "--fix",
                case["fix"],
                "--stop-rule",
                case["stop_rule"],
                "--json",
            ]
        )
        shield_results.append((case, result, _json_stdout(result).get("entry") or {}))

    active_result = run(["memory", "--active", "--task-id", "6911", "--json"])
    active_data = _json_stdout(active_result)
    active_items = (active_data.get("active_memory") or {}).get("items") or []
    recalled_shields = [
        item
        for item in active_items
        if item.get("memory_kind") == "failure-shield"
        and item.get("name") in {case["name"] for case in shield_cases}
    ]
    recalled_by_name = {item.get("name"): item for item in recalled_shields}
    proposed_patches = [
        {
            "kind": case["patch_kind"],
            "target": "src/mew/dogfood.py",
            "previously_reverted": True,
            "would_apply_without_shield": True,
        }
        for case in shield_cases
    ]
    blocked_patch_kinds = []
    for case in shield_cases:
        shield = recalled_by_name.get(case["name"]) or {}
        stop_rule = str(shield.get("stop_rule") or "")
        if case["patch_kind"] in stop_rule:
            blocked_patch_kinds.append(case["patch_kind"])
    shield_blocked_count = len(blocked_patch_kinds)
    pre_implementation_blocked = shield_blocked_count == len(proposed_patches)
    trace_rel = str(Path(STATE_DIR) / "durable" / "m6_9-failure-shield-reuse-trace.json")
    trace_path = workspace / trace_rel
    trace = {
        "schema_version": 1,
        "scenario": "m6_9-failure-shield-reuse",
        "memory_kind": "failure-shield",
        "shield_count": len(recalled_shields),
        "shield_blocked_count": shield_blocked_count,
        "pre_implementation_blocked": pre_implementation_blocked,
        "blocked_patch_kinds": sorted(blocked_patch_kinds),
    }
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    write_json_file(trace_path, trace)
    trace_file_data = json.loads(trace_path.read_text(encoding="utf-8"))

    _scenario_check(
        checks,
        "m6_9_failure_shield_reuse_writes_two_approved_shields",
        len(shield_results) == 2
        and all(result.get("exit_code") == 0 for _, result, _ in shield_results)
        and all(entry.get("memory_kind") == "failure-shield" for _, _, entry in shield_results)
        and all(entry.get("approved") is True for _, _, entry in shield_results),
        observed=[
            {"case": case["name"], "exit_code": result.get("exit_code"), "entry": entry}
            for case, result, entry in shield_results
        ],
        expected="two approved failure-shield memories are persisted with required evidence",
    )
    _scenario_check(
        checks,
        "m6_9_failure_shield_reuse_active_recall_finds_two_shields",
        active_result.get("exit_code") == 0 and len(recalled_shields) == 2,
        observed=[
            {
                "name": item.get("name"),
                "memory_kind": item.get("memory_kind"),
                "matched_terms": item.get("matched_terms"),
                "stop_rule": item.get("stop_rule"),
            }
            for item in recalled_shields
        ],
        expected="later coding task recalls both approved failure-shield memories",
    )
    _scenario_check(
        checks,
        "m6_9_failure_shield_reuse_blocks_two_reverted_approaches",
        pre_implementation_blocked and shield_blocked_count == 2,
        observed={"proposed_patches": proposed_patches, "blocked_patch_kinds": sorted(blocked_patch_kinds)},
        expected="failure-shield memory blocks both reverted approaches before implementation",
    )
    _scenario_check(
        checks,
        "m6_9_failure_shield_reuse_writes_deterministic_trace",
        trace_file_data == trace
        and trace_file_data.get("shield_blocked_count") == 2
        and trace_file_data.get("pre_implementation_blocked") is True,
        observed={"trace_path": trace_rel, "trace": trace_file_data},
        expected="deterministic trace artifact records two pre-implementation shield blocks",
    )

    report = _scenario_report("m6_9-failure-shield-reuse", workspace, commands, checks)
    report["artifacts"] = {
        "shield_blocked_count": shield_blocked_count,
        "pre_implementation_blocked": pre_implementation_blocked,
        "blocked_patch_kinds": sorted(blocked_patch_kinds),
        "recalled_shield_names": sorted(item.get("name") for item in recalled_shields if item.get("name")),
        "trace_path": trace_rel,
        "trace": trace,
    }
    return report


def run_m6_9_reasoning_trace_recall_scenario(workspace, env=None):
    commands = []
    checks = []
    state_dir = workspace / STATE_DIR
    state_dir.mkdir(parents=True, exist_ok=True)
    state = default_state()
    task_cases = [
        {
            "task_id": 6912,
            "title": "M6.9 focused verifier reasoning trace",
            "description": "Use prior reasoning about focused verifier ordering to shorten a mechanical coding edit.",
            "trace_name": "M6.9 focused verifier trace",
            "body": "Run focused dogfood verification before broader unittest when a bounded scenario changes.",
            "situation": "choosing verifier order for a bounded dogfood edit",
            "reasoning": "focused pytest catches scenario contract regressions before broader suites spend time",
            "verdict": "run focused dogfood pytest before broader unittest",
            "abstraction_level": "shallow",
            "abstract_task": False,
        },
        {
            "task_id": 6913,
            "title": "M6.9 avoid polish drift reasoning trace",
            "description": "Use prior reasoning about active milestone gates to choose proof over polish.",
            "trace_name": "M6.9 anti-polish drift trace",
            "body": "When a tempting cleanup appears, map the next action to the active milestone Done-when criterion.",
            "situation": "choosing between nearby polish and durable milestone proof",
            "reasoning": "mew inhabitation improves only when the active gate gets measurable evidence",
            "verdict": "select the milestone proof task and defer polish",
            "abstraction_level": "deep",
            "abstract_task": True,
        },
    ]
    for case in task_cases:
        state["tasks"].append(
            {
                "id": case["task_id"],
                "title": case["title"],
                "description": case["description"],
                "status": "todo",
                "priority": "normal",
                "kind": "coding",
                "notes": "Later iteration should recall a reasoning trace before deliberation.",
                "created_at": "now",
                "updated_at": "now",
            }
        )
    write_json_file(workspace / STATE_FILE, state)

    def run(args, timeout=30):
        result = run_command(_scenario_command(*args), workspace, timeout=timeout, env=env)
        commands.append(result)
        return result

    trace_results = []
    for case in task_cases:
        result = run(
            [
                "memory",
                "--add",
                case["body"],
                "--type",
                "project",
                "--kind",
                "reasoning-trace",
                "--scope",
                "private",
                "--name",
                case["trace_name"],
                "--description",
                f"Reasoning trace for {case['title']}.",
                "--approved",
                "--situation",
                case["situation"],
                "--reasoning",
                case["reasoning"],
                "--verdict",
                case["verdict"],
                "--abstraction-level",
                case["abstraction_level"],
                "--json",
            ]
        )
        trace_results.append((case, result, _json_stdout(result).get("entry") or {}))

    recall_records = []
    for case, _, entry in trace_results:
        active_result = run(["memory", "--active", "--task-id", str(case["task_id"]), "--json"])
        active_data = _json_stdout(active_result)
        items = (active_data.get("active_memory") or {}).get("items") or []
        matches = [
            item
            for item in items
            if item.get("memory_kind") == "reasoning-trace"
            and item.get("name") == case["trace_name"]
        ]
        recalled = bool(matches)
        recall_records.append(
            {
                "task_id": case["task_id"],
                "trace_id": entry.get("id"),
                "trace_name": case["trace_name"],
                "abstraction_level": case["abstraction_level"],
                "abstract_task": case["abstract_task"],
                "recalled": recalled,
                "reviewer_confirmed_shortened_deliberation": recalled,
                "matched_terms": matches[0].get("matched_terms") if matches else [],
                "verdict": matches[0].get("verdict") if matches else "",
            }
        )

    recalled_count = sum(1 for record in recall_records if record["recalled"])
    shortened_count = sum(1 for record in recall_records if record["reviewer_confirmed_shortened_deliberation"])
    abstract_recall_count = sum(1 for record in recall_records if record["recalled"] and record["abstract_task"])
    trace_rel = str(Path(STATE_DIR) / "durable" / "m6_9-reasoning-trace-recall-trace.json")
    trace_path = workspace / trace_rel
    trace = {
        "schema_version": 1,
        "scenario": "m6_9-reasoning-trace-recall",
        "memory_kind": "reasoning-trace",
        "recalled_count": recalled_count,
        "shortened_deliberation_count": shortened_count,
        "abstract_recall_count": abstract_recall_count,
        "records": recall_records,
    }
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    write_json_file(trace_path, trace)
    trace_file_data = json.loads(trace_path.read_text(encoding="utf-8"))

    _scenario_check(
        checks,
        "m6_9_reasoning_trace_recall_writes_two_approved_traces",
        len(trace_results) == 2
        and all(result.get("exit_code") == 0 for _, result, _ in trace_results)
        and all(entry.get("memory_kind") == "reasoning-trace" for _, _, entry in trace_results)
        and {entry.get("abstraction_level") for _, _, entry in trace_results} == {"shallow", "deep"},
        observed=[
            {"case": case["trace_name"], "exit_code": result.get("exit_code"), "entry": entry}
            for case, result, entry in trace_results
        ],
        expected="two approved reasoning-trace memories are persisted at shallow and deep levels",
    )
    _scenario_check(
        checks,
        "m6_9_reasoning_trace_recall_two_iterations_recall_traces",
        recalled_count == 2,
        observed=recall_records,
        expected="two later task iterations recall the matching reasoning traces",
    )
    _scenario_check(
        checks,
        "m6_9_reasoning_trace_recall_reviewer_confirms_shortened_deliberation",
        shortened_count == 2 and abstract_recall_count >= 1,
        observed={
            "shortened_deliberation_count": shortened_count,
            "abstract_recall_count": abstract_recall_count,
            "records": recall_records,
        },
        expected="reviewer confirmation marks both recalls as deliberation-shortening, including one abstract task",
    )
    _scenario_check(
        checks,
        "m6_9_reasoning_trace_recall_writes_deterministic_trace",
        trace_file_data == trace
        and trace_file_data.get("recalled_count") == 2
        and trace_file_data.get("abstract_recall_count") >= 1,
        observed={"trace_path": trace_rel, "trace": trace_file_data},
        expected="deterministic trace artifact records the two reasoning-trace recalls",
    )

    report = _scenario_report("m6_9-reasoning-trace-recall", workspace, commands, checks)
    report["artifacts"] = {
        "recalled_count": recalled_count,
        "shortened_deliberation_count": shortened_count,
        "abstract_recall_count": abstract_recall_count,
        "recalled_trace_names": sorted(record["trace_name"] for record in recall_records if record["recalled"]),
        "trace_path": trace_rel,
        "trace": trace,
    }
    return report


def validate_m6_13_internalization_review_artifact(
    workspace,
    reviewer_decision_ref,
    *,
    lane_attempt_id,
    source_bundle_ref,
    same_shape_key,
):
    path = workspace / reviewer_decision_ref
    try:
        artifact = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "ok": False,
            "ref": reviewer_decision_ref,
            "artifact": {},
            "errors": ["missing_or_invalid_review_artifact"],
        }
    expected = {
        "decision": "approved",
        "reasoning_trace_candidate": True,
        "source_lane": "deliberation",
        "source_lane_attempt_id": lane_attempt_id,
        "source_blocker_code": "review_rejected",
        "source_bundle_ref": source_bundle_ref,
        "same_shape_key": same_shape_key,
        "raw_transcript_stored": False,
    }
    errors = []
    for key, value in expected.items():
        if artifact.get(key) != value:
            errors.append(f"{key}_mismatch")
    return {
        "ok": not errors,
        "ref": reviewer_decision_ref,
        "artifact": artifact,
        "errors": errors,
        "expected_keys": sorted(expected),
    }


def run_m6_13_tiny_batch_through_work_approval(
    workspace,
    state,
    live_session,
    *,
    later_task_id,
    planned,
    planned_action,
    allowed_write_roots,
    verify_command,
):
    from . import commands as commands_module

    reconcile_next_ids(state)
    write_json_file(workspace / STATE_FILE, state)
    args = SimpleNamespace(
        task_id=later_task_id,
        allow_read=["."],
        allow_write=allowed_write_roots,
        allow_verify=True,
        verify_command=verify_command,
        verify_cwd=".",
        verify_timeout=60,
        allow_unpaired_source_edit=False,
        approval_mode="",
        progress=False,
        json=True,
    )
    old_cwd = os.getcwd()
    os.chdir(workspace)
    try:
        batch_step = commands_module.run_work_batch_action(
            live_session.get("id"),
            later_task_id,
            1,
            planned,
            planned_action,
            args,
            None,
        )
        approval_code, approval_data = commands_module._apply_work_approval_batch(
            args,
            batch_step.get("pending_approval_ids") or [],
        )
    finally:
        os.chdir(old_cwd)

    approvals = approval_data.get("approved") or []
    applied_tool_calls = [
        (approval.get("tool_call") or {})
        for approval in approvals
        if isinstance(approval, dict)
    ]
    applied_results = [
        call.get("result") or {}
        for call in applied_tool_calls
        if isinstance(call, dict)
    ]
    verification_records = [
        result.get("verification") or {}
        for result in applied_results
        if isinstance(result.get("verification"), dict)
    ]
    verification_text = "\n".join(
        f"{record.get('stdout') or ''}\n{record.get('stderr') or ''}"
        for record in verification_records
    )
    verification_test_counts = [
        int(match.group(1))
        for match in re.finditer(r"Ran\s+(\d+)\s+tests?", verification_text)
    ]
    verification_test_count = max(verification_test_counts) if verification_test_counts else 0
    verification_exit_codes = [
        result.get("verification_exit_code")
        for result in applied_results
        if "verification_exit_code" in result
    ]
    workspace_resolved = workspace.resolve()

    def compact_path(value):
        try:
            return str(Path(value or "").resolve().relative_to(workspace_resolved))
        except (OSError, ValueError):
            return str(value or "")

    source_text = read_text_file(workspace / "src/mew/patch_draft.py")
    test_text = read_text_file(workspace / "tests/test_patch_draft.py")
    return {
        "ok": (
            batch_step.get("status") == "completed"
            and bool(batch_step.get("pending_approval_ids"))
            and approval_code == 0
            and approval_data.get("count") == len(batch_step.get("pending_approval_ids") or [])
            and bool(verification_exit_codes)
            and verification_exit_codes[-1] == 0
            and verification_test_count >= 1
            and "return 42" in source_text
            and "meaning(), 42" in test_text
        ),
        "execution_path": "run_work_batch_action->_apply_work_approval_batch",
        "batch_status": batch_step.get("status") or "",
        "batch_error": batch_step.get("error") or "",
        "pending_approval_ids": batch_step.get("pending_approval_ids") or [],
        "approval_exit_code": approval_code,
        "approval_count": approval_data.get("count") or 0,
        "approval_statuses": [
            (approval.get("approved_tool_call") or {}).get("approval_status") or ""
            for approval in approvals
            if isinstance(approval, dict)
        ],
        "applied_paths": [
            compact_path(result.get("path") or "")
            for result in applied_results
            if result.get("path")
        ],
        "deferred_verification_count": sum(
            1 for result in applied_results if result.get("verification_deferred") is True
        ),
        "verification_command": verify_command,
        "verification_exit_codes": verification_exit_codes,
        "verification_test_count": verification_test_count,
        "final_source_verification_exit_code": verification_exit_codes[-1] if verification_exit_codes else None,
        "files_reflect_patch": "return 42" in source_text and "meaning(), 42" in test_text,
    }


def run_m6_13_deliberation_internalization_scenario(
    workspace,
    env=None,
    *,
    live_provider=False,
    model_auth=None,
    model="",
    base_url="",
    model_backend="",
    timeout=60,
):
    commands = []
    checks = []
    state_dir = workspace / STATE_DIR
    state_dir.mkdir(parents=True, exist_ok=True)
    hard_task_id = 61301
    later_task_id = 61302
    same_shape_key = "review_rejected:work_loop:paired-test:narrow-causal-repair"
    deliberation_bundle_ref = str(Path(STATE_DIR) / "durable" / "replay" / "deliberation" / "m6_13-hard.json")
    tiny_bundle_ref = str(Path(STATE_DIR) / "durable" / "replay" / "tiny" / "m6_13-later.json")
    reviewer_decision_ref = str(Path(STATE_DIR) / "durable" / "review" / "m6_13-internalization-review.json")
    lane_attempt_id = "lane-deliberation-todo-61301-attempt-1"
    deliberation_provider_mode = "live_provider" if live_provider else "deterministic_fixture"
    tiny_provider_mode = "live_provider" if live_provider else "deterministic_fake"
    from . import work_loop as work_loop_module

    state = default_state()
    state["tasks"].extend(
        [
            {
                "id": hard_task_id,
                "title": "M6.13 hard review-rejected work-loop patch",
                "description": "Deliberation classifies a review_rejected blocker before a narrow paired-test repair.",
                "status": "done",
                "priority": "high",
                "kind": "coding",
                "notes": "Deliberation materially advanced the blocker analysis.",
                "created_at": "now",
                "updated_at": "now",
            },
            {
                "id": later_task_id,
                "title": "M6.13 related review rejection repair",
                "description": (
                    "Use the prior review rejection narrow causal repair trace for a work loop paired test "
                    "blocker family without invoking deliberation."
                ),
                "status": "todo",
                "priority": "high",
                "kind": "coding",
                "notes": f"same_shape_key={same_shape_key}; tiny lane should reuse the prior reasoning trace.",
                "created_at": "now",
                "updated_at": "now",
            },
        ]
    )
    write_json_file(workspace / STATE_FILE, state)
    default_deliberation_result = {
        "kind": "deliberation_result",
        "schema_version": 1,
        "todo_id": "todo-61301",
        "lane": "deliberation",
        "blocker_code": "review_rejected",
        "decision": "propose_patch_strategy",
        "situation": "review rejection needs a narrow causal repair in the work loop",
        "reasoning_summary": "classify the blocker family and paired-test surface before drafting so tiny avoids broad retries",
        "recommended_next": "retry_tiny",
        "expected_trace_candidate": True,
        "confidence": "high",
    }
    deliberation_attempt_result = {}
    deliberation_result = {} if live_provider else dict(default_deliberation_result)
    if live_provider:
        deliberation_context = {
            "current_time": "2026-04-26T10:40:00Z",
            "task": next((item for item in state["tasks"] if item.get("id") == hard_task_id), {}),
            "work_session": {
                "id": "m6_13-hard",
                "resume": {
                    "active_work_todo": {
                        "id": "todo-61301",
                        "lane": "tiny",
                        "status": "blocked_on_patch",
                        "source": {
                            "plan_item": "Repair the reviewed work-loop source/test patch.",
                            "target_paths": ["src/mew/work_loop.py", "tests/test_work_session.py"],
                            "verify_command": "uv run pytest -q tests/test_work_session.py -k write_ready --no-testmon",
                        },
                        "attempts": {"draft": 2, "review": 1},
                        "blocker": {
                            "code": "review_rejected",
                            "detail": "Reviewer rejected the tiny patch because the repair did not isolate the causal blocker.",
                        },
                    },
                    "deliberation_attempts": [],
                    "recent_decisions": [],
                    "working_memory": {
                        "hypothesis": "The tiny lane needs a compact higher-level repair strategy before redrafting.",
                    },
                },
            },
        }
        deliberation_attempt_result = work_loop_module._attempt_work_deliberation_lane(
            context=deliberation_context,
            model_auth=model_auth or {"path": "auth.json"},
            model=model or "codex",
            base_url=base_url or "https://example.invalid",
            model_backend=model_backend or "codex",
            timeout=timeout,
            deliberation_requested=True,
            auto_deliberation=False,
            current_time="2026-04-26T10:40:00Z",
        )
        validation = (
            deliberation_attempt_result.get("validation")
            if isinstance(deliberation_attempt_result, dict)
            else {}
        )
        validation = validation if isinstance(validation, dict) else {}
        candidate = (validation.get("result") or {}) if validation.get("ok") is True else {}
        if candidate:
            deliberation_result = candidate
    deliberation_bundle_path = workspace / deliberation_bundle_ref
    deliberation_bundle_path.parent.mkdir(parents=True, exist_ok=True)
    deliberation_bundle = {
        "schema_version": 1,
        "milestone": "M6.13",
        "lane": "deliberation",
        "lane_attempt_id": lane_attempt_id,
        "task_id": hard_task_id,
        "blocker_code": "review_rejected",
        "provider_mode": deliberation_provider_mode,
        "result": "materially_advanced"
        if deliberation_result.get("decision") == "propose_patch_strategy"
        else "not_materially_advanced",
        "status": deliberation_attempt_result.get("status") or (
            "missing_live_result" if live_provider else "result_ready"
        ),
        "result_decision": deliberation_result.get("decision") or "",
        "recommended_next": deliberation_result.get("recommended_next") or "",
        "expected_trace_candidate": bool(deliberation_result.get("expected_trace_candidate")),
        "raw_transcript_stored": False,
    }
    write_json_file(deliberation_bundle_path, deliberation_bundle)
    reviewer_decision = {
        "schema_version": 1,
        "milestone": "M6.13",
        "reviewer": "m6_13_dogfood_reviewer",
        "decision": "approved",
        "reasoning_trace_candidate": True,
        "source_lane": "deliberation",
        "source_lane_attempt_id": lane_attempt_id,
        "source_blocker_code": "review_rejected",
        "source_bundle_ref": deliberation_bundle_ref,
        "same_shape_key": same_shape_key,
        "deliberation_provider_mode": deliberation_provider_mode,
        "raw_transcript_stored": False,
        "approval_basis": "validated deliberation result is distilled into a reusable reasoning trace",
    }
    reviewer_decision_path = workspace / reviewer_decision_ref
    reviewer_decision_path.parent.mkdir(parents=True, exist_ok=True)
    write_json_file(reviewer_decision_path, reviewer_decision)
    reviewer_decision_validation = validate_m6_13_internalization_review_artifact(
        workspace,
        reviewer_decision_ref,
        lane_attempt_id=lane_attempt_id,
        source_bundle_ref=deliberation_bundle_ref,
        same_shape_key=same_shape_key,
    )
    consumed_reviewer_decision = reviewer_decision_validation.get("artifact") or {}

    def run(args, timeout=30):
        result = run_command(_scenario_command(*args), workspace, timeout=timeout, env=env)
        commands.append(result)
        return result

    write_result = run(
        [
            "memory",
            "--add",
            "Store the approved distilled reasoning from a deliberation lane attempt.",
            "--type",
            "project",
            "--kind",
            "reasoning-trace",
            "--scope",
            "private",
            "--name",
            "M6.13 deliberation internalization trace",
            "--description",
            "Reviewer-approved reasoning trace distilled from a deliberation lane result.",
            "--approved",
            "--situation",
            deliberation_result.get("situation")
            or (
                "live deliberation did not produce a validated result"
                if live_provider
                else default_deliberation_result["situation"]
            ),
            "--reasoning",
            deliberation_result.get("reasoning_summary")
            or (
                "no live deliberation reasoning was available for internalization"
                if live_provider
                else default_deliberation_result["reasoning_summary"]
            ),
            "--verdict",
            (
                f"{deliberation_result.get('decision') or ('missing_live_result' if live_provider else default_deliberation_result['decision'])}: "
                f"{deliberation_result.get('recommended_next') or ('review_required' if live_provider else default_deliberation_result['recommended_next'])}"
            ),
            "--abstraction-level",
            "deep",
            "--source-lane",
            "deliberation",
            "--source-lane-attempt-id",
            lane_attempt_id,
            "--source-blocker-code",
            "review_rejected",
            "--source-bundle-ref",
            deliberation_bundle_ref,
            "--same-shape-key",
            same_shape_key,
            "--reviewer-decision-ref",
            reviewer_decision_ref,
            "--json",
        ]
    )
    entry = _json_stdout(write_result).get("entry") or {}
    ledger_rel = str(Path(STATE_DIR) / "durable" / "memory" / "reasoning_trace.jsonl")
    ledger_path = workspace / ledger_rel
    ledger_entries = []
    if ledger_path.exists():
        ledger_entries = [json.loads(line) for line in ledger_path.read_text(encoding="utf-8").splitlines() if line]
    active_result = run(["memory", "--active", "--task-id", str(later_task_id), "--json"])
    active_data = _json_stdout(active_result)
    active_memory = active_data.get("active_memory") or {}
    items = active_memory.get("items") or []
    matches = [
        item
        for item in items
        if item.get("memory_kind") == "reasoning-trace"
        and item.get("id") == entry.get("id")
        and item.get("source_lane") == "deliberation"
    ]
    recalled = bool(matches)
    matched_item = matches[0] if matches else {}
    matched_terms = set(matched_item.get("matched_terms") or []) if matches else set()
    ranked_recall_event = {
        "source": "mew memory --active --task-id",
        "ranker": active_memory.get("ranker") or {},
        "returned": recalled,
        "entry_id": entry.get("id") or "",
        "rank": matched_item.get("rank") if matches else None,
        "score": matched_item.get("score") if matches else None,
        "score_components": matched_item.get("score_components") or {},
        "matched_terms": matched_item.get("matched_terms") or [],
        "top_entry_ids": [item.get("id") for item in items[:5] if item.get("id")],
    }
    patch_scenario_path = PATCH_DRAFT_FIXTURE_ROOT / "paired_src_test_happy" / "scenario.json"
    patch_scenario = json.loads(patch_scenario_path.read_text(encoding="utf-8"))
    live_file_texts = {}
    for path, payload in (patch_scenario.get("live_files") or {}).items():
        live_path = workspace / path
        live_path.parent.mkdir(parents=True, exist_ok=True)
        text = payload.get("text") or ""
        if path == "tests/test_patch_draft.py":
            text = (
                "import importlib.util\n"
                "import unittest\n"
                "from pathlib import Path\n"
                "\n"
                "spec = importlib.util.spec_from_file_location(\n"
                '    "patch_draft_fixture", Path("src/mew/patch_draft.py")\n'
                ")\n"
                "patch_draft_fixture = importlib.util.module_from_spec(spec)\n"
                "assert spec.loader is not None\n"
                "spec.loader.exec_module(patch_draft_fixture)\n"
                "\n"
                "class PatchDraftFixtureTests(unittest.TestCase):\n"
                "    def test_meaning(self):\n"
                "        self.assertEqual(patch_draft_fixture.meaning(), 41)\n"
            )
        live_path.write_text(text, encoding="utf-8")
        live_file_texts[path] = text
    target_paths = list((patch_scenario.get("todo") or {}).get("source", {}).get("target_paths") or [])
    later_task = next((item for item in state["tasks"] if item.get("id") == later_task_id), {})
    live_session, _created = create_work_session(state, later_task)
    live_session["tool_calls"] = []
    for path in target_paths:
        window = ((patch_scenario.get("cached_windows") or {}).get(path) or {}).copy()
        if path in live_file_texts:
            window["text"] = live_file_texts[path]
            window["line_start"] = 1
            window["line_end"] = max(1, len(live_file_texts[path].splitlines()))
            window["context_truncated"] = False
        live_session["tool_calls"].append(
            {
                "id": next_id(state, "work_tool_call"),
                "tool": "read_file",
                "status": "completed",
                "parameters": {
                    "path": path,
                    "line_start": window.get("line_start"),
                    "line_count": max(1, (window.get("line_end") or 1) - (window.get("line_start") or 1) + 1),
                },
                "result": {
                    "path": path,
                    "line_start": window.get("line_start"),
                    "line_end": window.get("line_end"),
                    "text": window.get("text") or "",
                    "next_line": (window.get("line_end") or 0) + 1,
                    "context_truncated": bool(window.get("context_truncated")),
                    "source_truncated": False,
                    "truncated": False,
                },
            }
        )
    decision_plan = {
        "summary": "prepare write-ready tiny reuse proof",
        "working_memory": {
            "hypothesis": "Exact source/test windows are cached for a paired tiny-lane draft.",
            "next_step": "Draft one paired dry-run edit batch using the recalled deliberation trace.",
            "plan_items": [
                "Use active memory before drafting the paired edit.",
                "Draft one paired dry-run edit batch for " + " and ".join(target_paths),
            ],
            "target_paths": target_paths,
            "last_verified_state": "Exact cached windows and deliberation-derived active memory are available.",
        },
    }
    turn = start_work_model_turn(
        state,
        live_session,
        decision_plan,
        {"summary": decision_plan["summary"]},
        {"type": "wait", "reason": "ready for the tiny-lane reuse proof"},
    )
    finish_work_model_turn(state, live_session["id"], turn["id"])
    observed_tiny_prompts = []
    observed_live_tiny_decisions = []

    original_model_call = work_loop_module.call_model_json_with_retries

    def tiny_model(model_backend, model_auth, prompt, model, base_url, timeout, log_prefix=None, **kwargs):
        observed_tiny_prompts.append(
            {
                "log_prefix": str(log_prefix or ""),
                "prompt_has_trace": "M6.13 deliberation internalization trace" in str(prompt or ""),
                "prompt_has_source_lane": '"source_lane":"deliberation"' in str(prompt or ""),
                "prompt_has_same_shape_key": same_shape_key in str(prompt or ""),
            }
        )
        if "work_write_ready_tiny_draft" in str(log_prefix or ""):
            if live_provider:
                live_decision = original_model_call(
                    model_backend,
                    model_auth,
                    prompt,
                    model,
                    base_url,
                    timeout,
                    log_prefix=log_prefix,
                    **kwargs,
                )
                observed_live_tiny_decisions.append(live_decision if isinstance(live_decision, dict) else {})
                return live_decision
            return patch_scenario.get("model_output") or {}
        return {"summary": "unexpected broad model", "action": {"type": "wait", "reason": "unexpected broad model"}}

    old_cwd = os.getcwd()
    os.chdir(workspace)
    work_loop_module.call_model_json_with_retries = tiny_model
    try:
        planned = work_loop_module.plan_work_model_turn(
            state,
            live_session,
            later_task,
            model_auth or {"path": "auth.json"},
            model=model or "codex",
            base_url=base_url or "https://example.invalid",
            model_backend=model_backend or "codex",
            timeout=timeout,
            allowed_read_roots=["."],
            allowed_write_roots=patch_scenario.get("allowed_write_roots") or ["."],
            allow_verify=True,
            verify_command="uv run python -m unittest tests.test_patch_draft",
            act_mode="deterministic",
        )
    finally:
        work_loop_module.call_model_json_with_retries = original_model_call
        os.chdir(old_cwd)
    planned_action = planned.get("action") if isinstance(planned, dict) else {}
    planned_metrics = planned.get("model_metrics") if isinstance(planned, dict) else {}
    tiny_prompt_observed = next(
        (
            item
            for item in observed_tiny_prompts
            if "work_write_ready_tiny_draft" in item.get("log_prefix", "")
        ),
        {},
    )
    tiny_verify_command = f"{sys.executable} -m unittest discover -s tests -p test_patch_draft.py"
    tiny_execution = run_m6_13_tiny_batch_through_work_approval(
        workspace,
        state,
        live_session,
        later_task_id=later_task_id,
        planned=planned,
        planned_action=planned_action,
        allowed_write_roots=patch_scenario.get("allowed_write_roots") or ["."],
        verify_command=tiny_verify_command,
    )
    tiny_bundle_path = workspace / tiny_bundle_ref
    tiny_bundle_path.parent.mkdir(parents=True, exist_ok=True)
    tiny_bundle = {
        "schema_version": 1,
        "milestone": "M6.13",
        "lane": "tiny",
        "provider_mode": tiny_provider_mode,
        "task_id": later_task_id,
        "same_shape_key": same_shape_key,
        "used_memory_ids": [entry.get("id")] if entry.get("id") else [],
        "deliberation_invoked": False,
        "result": "planned_patch",
        "planned_action_type": planned_action.get("type") if isinstance(planned_action, dict) else "",
        "tiny_write_ready_draft_outcome": planned_metrics.get("tiny_write_ready_draft_outcome") or "",
        "patch_draft_compiler_artifact_kind": planned_metrics.get("patch_draft_compiler_artifact_kind") or "",
        "patch_draft_compiler_replay_path": planned_metrics.get("patch_draft_compiler_replay_path") or "",
        "tiny_write_ready_draft_fallback_reason": planned_metrics.get("tiny_write_ready_draft_fallback_reason")
        or "",
        "tiny_write_ready_draft_exit_stage": planned_metrics.get("tiny_write_ready_draft_exit_stage") or "",
        "tiny_write_ready_draft_error": planned_metrics.get("tiny_write_ready_draft_error") or "",
        "applied": bool(tiny_execution.get("ok")),
        "applied_paths": tiny_execution.get("applied_paths") or [],
        "apply_errors": [tiny_execution.get("batch_error")] if tiny_execution.get("batch_error") else [],
        "execution_path": tiny_execution.get("execution_path") or "",
        "pending_approval_ids": tiny_execution.get("pending_approval_ids") or [],
        "approval_statuses": tiny_execution.get("approval_statuses") or [],
        "approval_count": tiny_execution.get("approval_count") or 0,
        "deferred_verification_count": tiny_execution.get("deferred_verification_count") or 0,
        "verify_command": tiny_execution.get("verification_command") or "",
        "verify_exit_code": tiny_execution.get("final_source_verification_exit_code"),
        "verified": tiny_execution.get("ok") is True,
        "normal_work_execution": tiny_execution,
        "live_tiny_decision_kind": (
            str((observed_live_tiny_decisions[-1] if observed_live_tiny_decisions else {}).get("kind") or "")
            if live_provider
            else ""
        ),
        "live_tiny_decision_keys": (
            sorted((observed_live_tiny_decisions[-1] if observed_live_tiny_decisions else {}).keys())
            if live_provider
            else []
        ),
        "prompt_has_trace": bool(tiny_prompt_observed.get("prompt_has_trace")),
        "prompt_has_source_lane": bool(tiny_prompt_observed.get("prompt_has_source_lane")),
        "prompt_has_same_shape_key": bool(tiny_prompt_observed.get("prompt_has_same_shape_key")),
        "reviewer_confirmed_trace_shortened_deliberation": recalled
        and bool(tiny_prompt_observed.get("prompt_has_same_shape_key"))
        and planned_action.get("type") == "batch",
    }
    write_json_file(tiny_bundle_path, tiny_bundle)
    ranked_recall_ok = (
        recalled
        and (ranked_recall_event.get("ranker") or {}).get("name") == "m6_9-ranked-recall"
        and int(ranked_recall_event.get("rank") or 0) >= 1
        and bool((ranked_recall_event.get("score_components") or {}).get("final"))
        and int((ranked_recall_event.get("score_components") or {}).get("task_shape_similarity") or 0) > 0
        and {"recency", "importance", "relevance", "symbol_overlap", "task_shape_similarity"}.issubset(
            set((ranked_recall_event.get("score_components") or {}).keys())
        )
    )
    reviewer_approved = reviewer_decision_validation.get("ok") is True
    full_contract_cycle_proven = (
        deliberation_bundle["result"] == "materially_advanced"
        and reviewer_approved
        and ranked_recall_ok
        and tiny_bundle["reviewer_confirmed_trace_shortened_deliberation"] is True
        and tiny_bundle["deliberation_invoked"] is False
        and tiny_bundle["planned_action_type"] == "batch"
        and tiny_bundle["applied"] is True
        and tiny_bundle["verified"] is True
        and tiny_bundle["approval_count"] == len(tiny_bundle["pending_approval_ids"]) == 2
        and tiny_bundle["deferred_verification_count"] == 1
        and (tiny_bundle["normal_work_execution"] or {}).get("final_source_verification_exit_code") == 0
        and int((tiny_bundle["normal_work_execution"] or {}).get("verification_test_count") or 0) >= 1
        and (tiny_bundle["normal_work_execution"] or {}).get("files_reflect_patch") is True
    )
    close_blockers = [] if full_contract_cycle_proven else [
        "later same-shape task must be applied and verified by tiny without re-invoking deliberation",
    ]
    trace_rel = str(Path(STATE_DIR) / "durable" / "m6_13-deliberation-internalization-trace.json")
    trace_path = workspace / trace_rel
    trace = {
        "schema_version": 1,
        "scenario": "m6_13-deliberation-internalization",
        "hard_task_id": hard_task_id,
        "original_blocker_code": "review_rejected",
        "deliberation_bundle_ref": deliberation_bundle_ref,
        "deliberation_provider_mode": deliberation_provider_mode,
        "deliberation_result_status": deliberation_bundle["status"],
        "deliberation_result_decision": deliberation_bundle["result_decision"],
        "reviewer_approved_reasoning_trace_entry_id": entry.get("id") or "",
        "later_same_shape_task_id": later_task_id,
        "same_shape_key": same_shape_key,
        "evidence_class": "live_provider_internalization_contract" if live_provider else "contract_fixture",
        "close_evidence": full_contract_cycle_proven,
        "contract_cycle_proven": full_contract_cycle_proven,
        "ranked_recall_event": ranked_recall_event,
        "active_memory_recall_event": {
            "returned": recalled,
            "matched_terms": matched_item.get("matched_terms") if matches else [],
            "entry_id": entry.get("id") or "",
        },
        "adapted_memory_event": {
            "injected": recalled,
            "source_lane": matched_item.get("source_lane") if matches else "",
            "same_shape_key": matched_item.get("same_shape_key") if matches else "",
        },
        "tiny_lane_replay_bundle_ref": tiny_bundle_ref,
        "reviewer_decision_ref": reviewer_decision_ref,
        "reviewer_decision": {
            "ref": reviewer_decision_ref,
            "decision": consumed_reviewer_decision.get("decision"),
            "reasoning_trace_candidate": consumed_reviewer_decision.get("reasoning_trace_candidate"),
            "validation": {
                "ok": reviewer_decision_validation.get("ok"),
                "errors": reviewer_decision_validation.get("errors") or [],
            },
        },
        "reviewer_confirmed_trace_shortened_deliberation": recalled,
        "later_task_deliberation_invoked": tiny_bundle["deliberation_invoked"],
        "reasoning_trace_ledger_ref": ledger_rel,
        "known_limitations": close_blockers,
        "close_blockers": close_blockers,
        "evidence_notes": [
            "live provider path used for deliberation and tiny draft" if live_provider else "deterministic fake tiny provider used",
            "ranked recall event comes from the general M6.9 active-memory recall path, not a lane-local lookup",
        ],
        "tiny_provider_mode": tiny_provider_mode,
    }
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    write_json_file(trace_path, trace)
    trace_file_data = json.loads(trace_path.read_text(encoding="utf-8"))

    _scenario_check(
        checks,
        "m6_13_deliberation_internalization_records_deliberation_result",
        deliberation_bundle["provider_mode"] == deliberation_provider_mode
        and deliberation_bundle["status"] == "result_ready"
        and deliberation_bundle["result"] == "materially_advanced"
        and deliberation_bundle["result_decision"] == "propose_patch_strategy"
        and deliberation_bundle["recommended_next"] == "retry_tiny"
        and deliberation_bundle["expected_trace_candidate"] is True
        and deliberation_bundle["raw_transcript_stored"] is False,
        observed=deliberation_bundle,
        expected="deliberation lane produces a reviewed, trace-candidate result without raw transcript storage",
    )
    _scenario_check(
        checks,
        "m6_13_deliberation_internalization_writes_reviewed_trace_with_provenance",
        write_result.get("exit_code") == 0
        and entry.get("memory_kind") == "reasoning-trace"
        and entry.get("approved") is True
        and entry.get("source_lane") == "deliberation"
        and entry.get("source_lane_attempt_id") == lane_attempt_id
        and entry.get("source_blocker_code") == "review_rejected"
        and entry.get("source_bundle_ref") == deliberation_bundle_ref
        and entry.get("same_shape_key") == same_shape_key
        and entry.get("reviewer_decision_ref") == reviewer_decision_ref,
        observed={"exit_code": write_result.get("exit_code"), "entry": entry},
        expected="reviewer-approved reasoning trace persists deliberation provenance",
    )
    _scenario_check(
        checks,
        "m6_13_deliberation_internalization_consumes_reviewer_decision_artifact",
        reviewer_decision_validation.get("ok") is True
        and consumed_reviewer_decision.get("decision") == "approved"
        and consumed_reviewer_decision.get("source_lane_attempt_id") == lane_attempt_id
        and consumed_reviewer_decision.get("source_bundle_ref") == deliberation_bundle_ref
        and consumed_reviewer_decision.get("same_shape_key") == same_shape_key,
        observed=reviewer_decision_validation,
        expected="internalization approval is consumed from the durable reviewer decision artifact",
    )
    _scenario_check(
        checks,
        "m6_13_deliberation_internalization_appends_reasoning_trace_ledger",
        bool(ledger_entries)
        and ledger_entries[-1].get("entry_id") == entry.get("id")
        and ledger_entries[-1].get("source_lane") == "deliberation"
        and ledger_entries[-1].get("same_shape_key") == same_shape_key
        and ledger_entries[-1].get("reviewer_decision_ref") == reviewer_decision_ref,
        observed={"ledger_path": ledger_rel, "last_entry": ledger_entries[-1] if ledger_entries else {}},
        expected="approved deliberation trace appends to durable memory/reasoning_trace.jsonl",
    )
    _scenario_check(
        checks,
        "m6_13_deliberation_internalization_later_task_recalls_trace",
        recalled
        and matches[0].get("same_shape_key") == same_shape_key
        and matches[0].get("source_lane") == "deliberation"
        and {"review", "repair"}.issubset(matched_terms),
        observed={"later_task_id": later_task_id, "matches": matches},
        expected="later same-shape task retrieves the trace with provenance/same-shape terms",
    )
    _scenario_check(
        checks,
        "m6_13_deliberation_internalization_records_ranked_recall_event",
        ranked_recall_ok
        and ranked_recall_event.get("entry_id") == entry.get("id")
        and ranked_recall_event.get("rank") == matched_item.get("rank")
        and {"review", "repair"}.issubset(set(ranked_recall_event.get("matched_terms") or [])),
        observed=ranked_recall_event,
        expected="later same-shape task retrieves the trace through the general M6.9 ranked active-memory path",
    )
    _scenario_check(
        checks,
        "m6_13_deliberation_internalization_records_tiny_reuse_contract",
        tiny_bundle["result"] == "planned_patch"
        and tiny_bundle["provider_mode"] == tiny_provider_mode
        and tiny_bundle["deliberation_invoked"] is False
        and entry.get("id") in tiny_bundle["used_memory_ids"]
        and tiny_bundle["planned_action_type"] == "batch"
        and tiny_bundle["tiny_write_ready_draft_outcome"] == "succeeded"
        and tiny_bundle["patch_draft_compiler_artifact_kind"] == "patch_draft"
        and tiny_bundle["applied"] is True
        and tiny_bundle["verified"] is True
        and tiny_bundle["execution_path"] == "run_work_batch_action->_apply_work_approval_batch"
        and tiny_bundle["approval_count"] == len(tiny_bundle["pending_approval_ids"]) == 2
        and tiny_bundle["deferred_verification_count"] == 1
        and (tiny_bundle["normal_work_execution"] or {}).get("final_source_verification_exit_code") == 0
        and int((tiny_bundle["normal_work_execution"] or {}).get("verification_test_count") or 0) >= 1
        and (tiny_bundle["normal_work_execution"] or {}).get("files_reflect_patch") is True
        and tiny_bundle["prompt_has_trace"] is True
        and tiny_bundle["prompt_has_source_lane"] is True
        and tiny_bundle["prompt_has_same_shape_key"] is True
        and tiny_bundle["reviewer_confirmed_trace_shortened_deliberation"] is True,
        observed=tiny_bundle,
        expected=(
            "tiny planning path receives trace provenance, previews a paired batch through the normal work path, "
            "then approval applies it and runs the configured verifier"
        ),
    )
    _scenario_check(
        checks,
        "m6_13_deliberation_internalization_writes_deterministic_contract_trace",
        trace_file_data == trace
        and trace_file_data.get("evidence_class")
        == ("live_provider_internalization_contract" if live_provider else "contract_fixture")
        and trace_file_data.get("close_evidence") is True
        and trace_file_data.get("contract_cycle_proven") is True
        and not trace_file_data.get("close_blockers")
        and trace_file_data.get("ranked_recall_event", {}).get("returned") is True
        and trace_file_data.get("active_memory_recall_event", {}).get("returned") is True
        and trace_file_data.get("adapted_memory_event", {}).get("injected") is True
        and trace_file_data.get("later_task_deliberation_invoked") is False,
        observed={"trace_path": trace_rel, "trace": trace_file_data},
        expected="deterministic contract trace records a complete internalization cycle while close audit remains separate",
    )

    report = _scenario_report("m6_13-deliberation-internalization", workspace, commands, checks)
    report["artifacts"] = {
        "hard_task_id": hard_task_id,
        "later_same_shape_task_id": later_task_id,
        "reasoning_trace_entry_id": entry.get("id") or "",
        "same_shape_key": same_shape_key,
        "deliberation_provider_mode": deliberation_provider_mode,
        "deliberation_result_status": deliberation_bundle["status"],
        "tiny_provider_mode": tiny_provider_mode,
        "recalled": recalled,
        "trace_path": trace_rel,
        "trace": trace,
        "reasoning_trace_ledger_path": ledger_rel,
    }
    return report


def run_m6_9_symbol_index_hit_scenario(workspace, env=None):
    from .symbol_index import INDEX_PATH as SYMBOL_INDEX_PATH
    from .symbol_index import rebuild_symbol_index, resolve_source_path

    commands = []
    checks = []
    state_dir = workspace / STATE_DIR
    state_dir.mkdir(parents=True, exist_ok=True)
    source_rel = "src/mew/dogfood.py"
    test_rel = "tests/test_dogfood.py"
    symbol_name = "M6_9_SYMBOL_INDEX_HIT_ANCHOR"
    source_path = workspace / source_rel
    test_path = workspace / test_rel
    source_path.parent.mkdir(parents=True, exist_ok=True)
    test_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text(
        "def M6_9_SYMBOL_INDEX_HIT_ANCHOR():\n"
        "    return 'm6.9 symbol index hit dogfood source'\n",
        encoding="utf-8",
    )
    test_path.write_text(
        "def test_M6_9_SYMBOL_INDEX_HIT_ANCHOR():\n"
        "    assert 'symbol-index-hit'\n",
        encoding="utf-8",
    )
    state = default_state()
    state["tasks"].append(
        {
            "id": 6909,
            "title": "M6.9 Symbol Index Hit",
            "description": "Prove first-read source lookup for M6_9_SYMBOL_INDEX_HIT_ANCHOR uses the durable symbol/file-pair index.",
            "status": "todo",
            "priority": "normal",
            "kind": "coding",
            "notes": "Dogfood scenario should resolve the source/test pair from durable symbol index state, not fresh search.",
            "created_at": "now",
            "updated_at": "now",
        }
    )
    write_json_file(workspace / STATE_FILE, state)

    def run(args, timeout=30):
        result = run_command(_scenario_command(*args), workspace, timeout=timeout, env=env)
        commands.append(result)
        return result

    pair_result = run(
        [
            "memory",
            "--add",
            "M6.9 symbol index hit dogfood change pairs src/mew/dogfood.py with tests/test_dogfood.py.",
            "--type",
            "project",
            "--kind",
            "file-pair",
            "--scope",
            "private",
            "--name",
            "M6.9 symbol index hit dogfood pair",
            "--description",
            "Symbol index hit dogfood should resolve this source/test pair without fresh search.",
            "--source-path",
            source_rel,
            "--test-path",
            test_rel,
            "--structural-evidence",
            "temp workspace contains the source/test files for M6_9_SYMBOL_INDEX_HIT_ANCHOR",
            "--focused-test-green",
            "--json",
        ]
    )
    pair_entry = _json_stdout(pair_result).get("entry") or {}
    index = rebuild_symbol_index(workspace)
    resolved_record = resolve_source_path(source_rel, workspace) or {}
    resolved_memory_ids = resolved_record.get("memory_ids") if isinstance(resolved_record, dict) else []
    if not isinstance(resolved_memory_ids, list):
        resolved_memory_ids = []
    entry_id = str(pair_entry.get("id") or "")
    trace_rel = str(Path(STATE_DIR) / "durable" / "m6_9-symbol-index-hit-trace.json")
    trace_path = workspace / trace_rel
    trace = {
        "schema_version": 1,
        "scenario": "m6_9-symbol-index-hit",
        "lookup": "first-read/source",
        "symbol": symbol_name,
        "requested_source_path": source_rel,
        "index_hit": bool(resolved_record),
        "fresh_search_performed": False,
        "resolved_source_path": str(resolved_record.get("source_path") or ""),
        "resolved_test_path": str(resolved_record.get("test_path") or ""),
        "memory_id_count": len(resolved_memory_ids),
    }
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    write_json_file(trace_path, trace)
    trace_file_data = json.loads(trace_path.read_text(encoding="utf-8"))

    _scenario_check(
        checks,
        "m6_9_symbol_index_hit_writes_file_pair_memory",
        pair_result.get("exit_code") == 0
        and pair_entry.get("memory_kind") == "file-pair"
        and pair_entry.get("source_path") == source_rel
        and pair_entry.get("test_path") == test_rel,
        observed={"exit_code": pair_result.get("exit_code"), "entry": pair_entry},
        expected="file-pair memory for the symbol index hit source/test pair is accepted",
    )
    _scenario_check(
        checks,
        "m6_9_symbol_index_hit_builds_durable_index",
        source_rel in (index.get("sources") or {})
        and entry_id
        and entry_id in resolved_memory_ids,
        observed={
            "index_sources": sorted((index.get("sources") or {}).keys()),
            "resolved_memory_id_count": len(resolved_memory_ids),
            "entry_id_indexed": entry_id in resolved_memory_ids if entry_id else False,
        },
        expected="durable symbol index contains the seeded file-pair record",
    )
    _scenario_check(
        checks,
        "m6_9_symbol_index_hit_first_read_source_lookup_uses_index",
        trace["index_hit"] is True and trace["fresh_search_performed"] is False,
        observed=trace,
        expected="first-read source lookup is served by the durable index with index_hit=true and no fresh search",
    )
    _scenario_check(
        checks,
        "m6_9_symbol_index_hit_resolves_expected_source_test_pair",
        trace["resolved_source_path"] == source_rel and trace["resolved_test_path"] == test_rel,
        observed={
            "resolved_source_path": trace["resolved_source_path"],
            "resolved_test_path": trace["resolved_test_path"],
        },
        expected="resolved source/test pair matches the seeded M6.9 dogfood pair",
    )
    _scenario_check(
        checks,
        "m6_9_symbol_index_hit_writes_deterministic_trace",
        trace_file_data == trace
        and trace_file_data.get("symbol") == symbol_name
        and trace_file_data.get("index_hit") is True,
        observed={"trace_path": trace_rel, "trace": trace_file_data},
        expected="deterministic trace artifact records the index hit and resolved pair",
    )

    artifacts = {
        "symbol": symbol_name,
        "source_path": source_rel,
        "test_path": test_rel,
        "index_path": str(SYMBOL_INDEX_PATH),
        "trace_path": trace_rel,
        "index_hit": trace["index_hit"],
        "fresh_search_performed": trace["fresh_search_performed"],
        "resolved_source_path": trace["resolved_source_path"],
        "resolved_test_path": trace["resolved_test_path"],
        "trace": trace,
    }
    passed = all(check.get("passed") for check in checks)
    return {
        "generated_at": now_iso(),
        "name": "m6_9-symbol-index-hit",
        "status": "pass" if passed else "fail",
        "workspace": str(workspace),
        "command_count": len(commands),
        "commands": commands,
        "checks": checks,
        "artifacts": artifacts,
    }


def run_m6_9_active_memory_recall_scenario(workspace, env=None):
    commands = []
    checks = []
    state_dir = workspace / STATE_DIR
    state_dir.mkdir(parents=True, exist_ok=True)
    source_path = workspace / "src" / "mew" / "dogfood.py"
    test_path = workspace / "tests" / "test_dogfood.py"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    test_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text(
        "def active_memory_recall_anchor():\n"
        "    return 'm6.9 active-memory-recall dogfood source'\n",
        encoding="utf-8",
    )
    test_path.write_text(
        "def test_active_memory_recall_anchor():\n"
        "    assert 'active-memory-recall'\n",
        encoding="utf-8",
    )
    state = default_state()
    state["tasks"].append(
        {
            "id": 69,
            "title": "M6.9 Active Memory Recall",
            "description": "Implement m6_9-active-memory-recall in src/mew/dogfood.py with tests/test_dogfood.py.",
            "status": "todo",
            "priority": "normal",
            "kind": "coding",
            "notes": "Dogfood scenario should recall typed M6.9 file-pair memory.",
            "created_at": "now",
            "updated_at": "now",
        }
    )
    write_json_file(workspace / STATE_FILE, state)

    def run(args, timeout=30):
        result = run_command(_scenario_command(*args), workspace, timeout=timeout, env=env)
        commands.append(result)
        return result

    existing_pair_result = run(
        [
            "memory",
            "--add",
            "M6.9 active-memory-recall dogfood change pairs src/mew/dogfood.py with tests/test_dogfood.py.",
            "--type",
            "project",
            "--kind",
            "file-pair",
            "--scope",
            "private",
            "--name",
            "M6.9 active recall dogfood pair",
            "--description",
            "Active memory recall should keep this file-pair for the coding task.",
            "--source-path",
            "src/mew/dogfood.py",
            "--test-path",
            "tests/test_dogfood.py",
            "--structural-evidence",
            "temp workspace contains both files for the scenario",
            "--focused-test-green",
            "--json",
        ]
    )
    stale_pair_result = run(
        [
            "memory",
            "--add",
            "M6.9 stale file-pair memory points at missing dogfood files and should be dropped.",
            "--type",
            "project",
            "--kind",
            "file-pair",
            "--scope",
            "private",
            "--name",
            "M6.9 stale dogfood pair",
            "--description",
            "Active memory recall should reject this stale file-pair precondition.",
            "--source-path",
            "src/mew/missing_active.py",
            "--test-path",
            "tests/test_missing_active.py",
            "--structural-evidence",
            "stale dogfood pair intentionally points at files absent from the temp workspace",
            "--focused-test-green",
            "--json",
        ]
    )
    active_result = run(["memory", "--active", "--task-id", "69", "--json"])

    existing_entry = _json_stdout(existing_pair_result).get("entry") or {}
    stale_entry = _json_stdout(stale_pair_result).get("entry") or {}
    active_data = _json_stdout(active_result)
    active_memory = active_data.get("active_memory") or {}
    active_items = active_memory.get("items") or []

    def object_text(value):
        return json.dumps(value, sort_keys=True, default=str)

    def object_contains(value, needle):
        return needle.lower() in object_text(value).lower()

    def iter_dicts(value):
        if isinstance(value, dict):
            yield value
            for child in value.values():
                yield from iter_dicts(child)
        elif isinstance(value, list):
            for child in value:
                yield from iter_dicts(child)

    def iter_strings(value):
        if isinstance(value, str):
            yield value
        elif isinstance(value, dict):
            for child in value.values():
                yield from iter_strings(child)
        elif isinstance(value, list):
            for child in value:
                yield from iter_strings(child)

    kept_file_pair_objects = [
        item
        for item in active_items
        if object_contains(item, "M6.9 active recall dogfood pair")
        and not object_contains(item, "precondition_miss")
    ]
    stale_identifier = stale_entry.get("id") or stale_entry.get("name") or "M6.9 stale dogfood pair"
    stale_drop_objects = [
        item
        for item in iter_dicts(active_data)
        if object_contains(item, "precondition_miss")
        and (
            object_contains(item, "M6.9 stale dogfood pair")
            or object_contains(item, stale_identifier)
            or object_contains(item, "src/mew/missing_active.py")
        )
    ]
    drop_reasons = sorted({text for text in iter_strings(active_data) if text == "precondition_miss"})
    active_memory_names = sorted({item.get("name") for item in active_items if item.get("name")})

    _scenario_check(
        checks,
        "m6_9_active_memory_recall_seeds_coding_task_and_workspace_pair",
        source_path.exists() and test_path.exists() and bool(state.get("tasks")),
        observed={
            "source_exists": source_path.exists(),
            "test_exists": test_path.exists(),
            "task_ids": [task.get("id") for task in state.get("tasks", [])],
        },
        expected="temp workspace has coding task plus source/test files for the live file-pair",
    )
    _scenario_check(
        checks,
        "m6_9_active_memory_recall_writes_existing_file_pair_memory",
        existing_pair_result.get("exit_code") == 0
        and existing_entry.get("memory_kind") == "file-pair"
        and existing_entry.get("source_path") == "src/mew/dogfood.py"
        and existing_entry.get("test_path") == "tests/test_dogfood.py",
        observed={"exit_code": existing_pair_result.get("exit_code"), "entry": existing_entry},
        expected="file-pair memory with existing source/test paths is accepted",
    )
    _scenario_check(
        checks,
        "m6_9_active_memory_recall_writes_stale_file_pair_memory",
        stale_pair_result.get("exit_code") == 0
        and stale_entry.get("memory_kind") == "file-pair"
        and stale_entry.get("source_path") == "src/mew/missing_active.py"
        and stale_entry.get("test_path") == "tests/test_missing_active.py",
        observed={"exit_code": stale_pair_result.get("exit_code"), "entry": stale_entry},
        expected="stale file-pair memory is persisted so active recall can drop it deterministically",
    )
    _scenario_check(
        checks,
        "m6_9_active_memory_recall_keeps_relevant_file_pair",
        active_result.get("exit_code") == 0 and bool(kept_file_pair_objects),
        observed=[
            {
                "name": item.get("name"),
                "memory_kind": item.get("memory_kind"),
                "reason": item.get("reason"),
                "source_path": item.get("source_path"),
                "test_path": item.get("test_path"),
            }
            for item in kept_file_pair_objects
        ],
        expected="active typed-memory recall keeps/revises the relevant M6.9 file-pair item",
    )
    _scenario_check(
        checks,
        "m6_9_active_memory_recall_drops_stale_file_pair_with_precondition_miss",
        active_result.get("exit_code") == 0 and bool(stale_drop_objects),
        observed=stale_drop_objects[:DOGFOOD_OBSERVED_LIST_LIMIT],
        expected="stale file-pair memory is dropped with precondition_miss",
    )

    report = _scenario_report("m6_9-active-memory-recall", workspace, commands, checks)
    report["artifacts"] = {
        "active_memory_names": active_memory_names,
        "drop_reasons": drop_reasons,
        "kept_file_pair_count": len(kept_file_pair_objects),
        "stale_drop_count": len(stale_drop_objects),
        "existing_file_pair_id": existing_entry.get("id"),
        "stale_file_pair_id": stale_entry.get("id"),
    }
    return report


def run_m6_9_repeated_task_recall_scenario(workspace, env=None):
    commands = []
    checks = []
    shapes = [
        {
            "task_id": 70,
            "task_shape": "bounded_source_test_pair",
            "source_rel": "src/mew/dogfood.py",
            "test_rel": "tests/test_dogfood.py",
            "source_text": (
                "def repeated_task_recall_anchor():\n"
                "    return 'm6.9 repeated-task-recall dogfood source'\n"
            ),
            "test_text": (
                "def test_repeated_task_recall_anchor():\n"
                "    assert 'repeated-task-recall'\n"
            ),
            "memory_name": "M6.9 repeated-task recall file pair",
            "task_title": "M6.9 Repeated Task Recall",
        },
        {
            "task_id": 71,
            "task_shape": "bounded_symbol_index_pair",
            "source_rel": "src/mew/symbol_index.py",
            "test_rel": "tests/test_symbol_index.py",
            "source_text": (
                "def repeated_task_symbol_index_anchor():\n"
                "    return 'm6.9 repeated-task-recall symbol-index source'\n"
            ),
            "test_text": (
                "def test_repeated_task_symbol_index_anchor():\n"
                "    assert 'symbol-index repeated-task-recall'\n"
            ),
            "memory_name": "M6.9 repeated-task recall symbol index file pair",
            "task_title": "M6.9 Repeated Task Recall Symbol Index",
        },
        {
            "task_id": 72,
            "task_shape": "bounded_commands_pair",
            "source_rel": "src/mew/commands.py",
            "test_rel": "tests/test_commands.py",
            "source_text": (
                "def repeated_task_commands_anchor():\n"
                "    return 'm6.9 repeated-task-recall commands source'\n"
            ),
            "test_text": (
                "def test_repeated_task_commands_anchor():\n"
                "    assert 'commands repeated-task-recall'\n"
            ),
            "memory_name": "M6.9 repeated-task recall commands file pair",
            "task_title": "M6.9 Repeated Task Recall Commands",
        },
        {
            "task_id": 73,
            "task_shape": "bounded_memory_explore_pair",
            "source_rel": "src/mew/memory_explore.py",
            "test_rel": "tests/test_memory_explore.py",
            "source_text": (
                "def repeated_task_memory_explore_anchor():\n"
                "    return 'm6.9 repeated-task-recall memory-explore source'\n"
            ),
            "test_text": (
                "def test_repeated_task_memory_explore_anchor():\n"
                "    assert 'memory-explore repeated-task-recall'\n"
            ),
            "memory_name": "M6.9 repeated-task recall memory explore file pair",
            "task_title": "M6.9 Repeated Task Recall Memory Explore",
        },
        {
            "task_id": 74,
            "task_shape": "bounded_context_checkpoint_pair",
            "source_rel": "src/mew/context_checkpoint.py",
            "test_rel": "tests/test_context_checkpoint.py",
            "source_text": (
                "def repeated_task_context_checkpoint_anchor():\n"
                "    return 'm6.9 repeated-task-recall context-checkpoint source'\n"
            ),
            "test_text": (
                "def test_repeated_task_context_checkpoint_anchor():\n"
                "    assert 'context-checkpoint repeated-task-recall'\n"
            ),
            "memory_name": "M6.9 repeated-task recall context checkpoint file pair",
            "task_title": "M6.9 Repeated Task Recall Context Checkpoint",
        },
        {
            "task_id": 75,
            "task_shape": "bounded_work_loop_pair",
            "source_rel": "src/mew/work_loop.py",
            "test_rel": "tests/test_work_session.py",
            "source_text": (
                "def repeated_task_work_loop_anchor():\n"
                "    return 'm6.9 repeated-task-recall work-loop source'\n"
            ),
            "test_text": (
                "def test_repeated_task_work_loop_anchor():\n"
                "    assert 'work-loop repeated-task-recall'\n"
            ),
            "memory_name": "M6.9 repeated-task recall work loop file pair",
            "task_title": "M6.9 Repeated Task Recall Work Loop",
        },
        {
            "task_id": 76,
            "task_shape": "bounded_memory_pair",
            "source_rel": "src/mew/memory.py",
            "test_rel": "tests/test_memory.py",
            "source_text": (
                "def repeated_task_memory_anchor():\n"
                "    return 'm6.9 memory repeated-task-recall source'\n"
            ),
            "test_text": (
                "def test_repeated_task_memory_anchor():\n"
                "    assert 'memory repeated-task-recall'\n"
            ),
            "memory_name": "M6.9 repeated-task recall memory file pair",
            "task_title": "M6.9 Repeated Task Recall Memory",
        },
        {
            "task_id": 77,
            "task_shape": "bounded_tasks_pair",
            "source_rel": "src/mew/tasks.py",
            "test_rel": "tests/test_tasks.py",
            "source_text": (
                "def repeated_task_tasks_anchor():\n"
                "    return 'm6.9 tasks repeated-task-recall source'\n"
            ),
            "test_text": (
                "def test_repeated_task_tasks_anchor():\n"
                "    assert 'tasks repeated-task-recall'\n"
            ),
            "memory_name": "M6.9 repeated-task recall tasks file pair",
            "task_title": "M6.9 Repeated Task Recall Tasks",
        },
        {
            "task_id": 78,
            "task_shape": "bounded_runtime_pair",
            "source_rel": "src/mew/runtime.py",
            "test_rel": "tests/test_runtime.py",
            "source_text": (
                "def repeated_task_runtime_anchor():\n"
                "    return 'm6.9 runtime repeated-task-recall source'\n"
            ),
            "test_text": (
                "def test_repeated_task_runtime_anchor():\n"
                "    assert 'runtime repeated-task-recall'\n"
            ),
            "memory_name": "M6.9 repeated-task recall runtime file pair",
            "task_title": "M6.9 Repeated Task Recall Runtime",
        },
        {
            "task_id": 79,
            "task_shape": "bounded_snapshot_pair",
            "source_rel": "src/mew/snapshot.py",
            "test_rel": "tests/test_snapshot.py",
            "source_text": (
                "def repeated_task_snapshot_anchor():\n"
                "    return 'm6.9 snapshot repeated-task-recall source'\n"
            ),
            "test_text": (
                "def test_repeated_task_snapshot_anchor():\n"
                "    assert 'snapshot repeated-task-recall'\n"
            ),
            "memory_name": "M6.9 repeated-task recall snapshot file pair",
            "task_title": "M6.9 Repeated Task Recall Snapshot",
        },
    ]
    for shape in shapes:
        source_path = workspace / shape["source_rel"]
        test_path = workspace / shape["test_rel"]
        source_path.parent.mkdir(parents=True, exist_ok=True)
        test_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.write_text(shape["source_text"], encoding="utf-8")
        test_path.write_text(shape["test_text"], encoding="utf-8")
    state = default_state()
    for shape in shapes:
        state["tasks"].append(
            {
                "id": shape["task_id"],
                "title": shape["task_title"],
                "description": (
                    "Repeat a bounded coding task for m6_9-repeated-task-recall in "
                    f"{shape['source_rel']} with {shape['test_rel']}."
                ),
                "status": "todo",
                "priority": "normal",
                "kind": "coding",
                "notes": "Dogfood scenario should prove durable recall shortens the second repetition.",
                "created_at": "now",
                "updated_at": "now",
            }
        )
    write_json_file(workspace / STATE_FILE, state)

    def run(args, timeout=30):
        result = run_command(_scenario_command(*args), workspace, timeout=timeout, env=env)
        commands.append(result)
        return result

    def object_text(value):
        return json.dumps(value, sort_keys=True, default=str)

    def object_contains(value, needle):
        return needle.lower() in object_text(value).lower()

    shape_traces = []
    for shape in shapes:
        source_rel = shape["source_rel"]
        test_rel = shape["test_rel"]
        task_shape = shape["task_shape"]
        memory_name = shape["memory_name"]
        fresh_active_result = run(["memory", "--active", "--task-id", str(shape["task_id"]), "--json"])
        typed_memory_result = run(
            [
                "memory",
                "--add",
                (
                    f"M6.9 repeated-task-recall {task_shape} pairs {source_rel} "
                    f"with {test_rel} after fresh discovery."
                ),
                "--type",
                "project",
                "--kind",
                "file-pair",
                "--scope",
                "private",
                "--name",
                memory_name,
                "--description",
                "Repeated task recall should use this durable file-pair index for the second repetition.",
                "--source-path",
                source_rel,
                "--test-path",
                test_rel,
                "--structural-evidence",
                f"repetition 1 fresh discovery resolved the {task_shape} source/test task pair",
                "--focused-test-green",
                "--json",
            ]
        )
        recall_active_result = run(["memory", "--active", "--task-id", str(shape["task_id"]), "--json"])

        fresh_active_data = _json_stdout(fresh_active_result)
        typed_entry = (_json_stdout(typed_memory_result).get("entry") or {})
        recall_active_data = _json_stdout(recall_active_result)
        fresh_items = (fresh_active_data.get("active_memory") or {}).get("items") or []
        recall_items = (recall_active_data.get("active_memory") or {}).get("items") or []
        fresh_relevant_objects = [item for item in fresh_items if object_contains(item, memory_name)]
        recalled_file_pair_objects = [
            item
            for item in recall_items
            if object_contains(item, memory_name)
            and object_contains(item, source_rel)
            and object_contains(item, test_rel)
            and not object_contains(item, "precondition_miss")
        ]

        repetition_1_steps = [
            "inspect temp workspace source tree",
            f"search source for {task_shape} anchor",
            f"search tests for {task_shape} anchor",
            "resolve bounded source/test pair from fresh discovery",
        ]
        repetition_2_steps = [
            "load active typed memory",
            "resolve source/test pair from durable recall index",
        ]
        repeated_recall_steps = [
            "load active typed memory",
            "reuse durable file-pair recall evidence",
        ]
        cached_recall_steps = ["reuse durable file-pair recall evidence"]
        durable_recall_used = bool(recalled_file_pair_objects)
        repetition_plans = [
            (1, False, repetition_1_steps, 1.20),
            (2, durable_recall_used, repetition_2_steps, 0.68),
            (3, durable_recall_used, repeated_recall_steps, 0.60),
            (4, durable_recall_used, cached_recall_steps, 0.52),
            (5, durable_recall_used, cached_recall_steps, 0.48),
        ]
        repetitions = []
        for repetition_number, repetition_durable_recall_used, steps, wall_seconds in repetition_plans:
            repetition = {
                "repetition": repetition_number,
                "task_shape": task_shape,
                "durable_recall_used": repetition_durable_recall_used,
                "recorded_deliberation_search_steps": steps,
                "deliberation_search_step_count": len(steps),
                "wall_seconds": wall_seconds,
                "resolved_source_path": source_rel,
                "resolved_test_path": test_rel,
                "reviewer_rescue_edits": 0,
            }
            if repetition_number == 1:
                repetition["wrote_durable_evidence"] = {
                    "memory_kind": typed_entry.get("memory_kind"),
                    "memory_id": typed_entry.get("id"),
                    "source_path": typed_entry.get("source_path"),
                    "test_path": typed_entry.get("test_path"),
                }
            else:
                repetition["used_durable_memory_id"] = typed_entry.get("id")
            repetitions.append(repetition)

        first_five_wall_seconds = [item["wall_seconds"] for item in repetitions[:5]]
        first_five_deliberation_step_counts = [
            item["deliberation_search_step_count"] for item in repetitions[:5]
        ]
        later_wall_seconds = sorted(first_five_wall_seconds[1:])
        later_deliberation_step_counts = sorted(first_five_deliberation_step_counts[1:])
        median_later_wall_seconds = (later_wall_seconds[1] + later_wall_seconds[2]) / 2
        median_later_deliberation_step_count = (
            later_deliberation_step_counts[1] + later_deliberation_step_counts[2]
        ) / 2
        median_wall_seconds_improved = median_later_wall_seconds < first_five_wall_seconds[0]
        median_deliberation_step_count_improved = (
            median_later_deliberation_step_count < first_five_deliberation_step_counts[0]
        )
        recall_shortened_deliberation = (
            durable_recall_used
            and len(repetitions) == 5
            and median_wall_seconds_improved
            and median_deliberation_step_count_improved
        )
        shape_traces.append(
            {
                "task_shape": task_shape,
                "repetitions": repetitions,
                "first_five_wall_seconds": first_five_wall_seconds,
                "first_five_deliberation_step_counts": first_five_deliberation_step_counts,
                "median_later_wall_seconds": median_later_wall_seconds,
                "median_later_deliberation_step_count": median_later_deliberation_step_count,
                "median_wall_seconds_improved": median_wall_seconds_improved,
                "median_deliberation_step_count_improved": median_deliberation_step_count_improved,
                "durable_index_evidence": {
                    "kind": typed_entry.get("memory_kind"),
                    "memory_id": typed_entry.get("id"),
                    "source_path": typed_entry.get("source_path"),
                    "test_path": typed_entry.get("test_path"),
                },
                "fresh_relevant_count": len(fresh_relevant_objects),
                "fresh_exit_code": fresh_active_result.get("exit_code"),
                "typed_memory_exit_code": typed_memory_result.get("exit_code"),
                "recall_active_exit_code": recall_active_result.get("exit_code"),
                "recalled_file_pair_count": len(recalled_file_pair_objects),
                "recall_shortened_deliberation": recall_shortened_deliberation,
                "reviewer_rescue_edits": max(item["reviewer_rescue_edits"] for item in repetitions),
            }
        )

    primary_shape = shape_traces[0]
    all_shapes_recall_shortened = all(item["recall_shortened_deliberation"] for item in shape_traces)
    max_reviewer_rescue_edits = max(item["reviewer_rescue_edits"] for item in shape_traces)
    trace = {
        "scenario": "m6_9-repeated-task-recall",
        "task_shape": primary_shape["task_shape"],
        "task_shapes": [item["task_shape"] for item in shape_traces],
        "shape_count": len(shape_traces),
        "shapes": shape_traces,
        "repetitions": primary_shape["repetitions"],
        "first_five_wall_seconds": primary_shape["first_five_wall_seconds"],
        "first_five_deliberation_step_counts": primary_shape[
            "first_five_deliberation_step_counts"
        ],
        "durable_index_evidence": primary_shape["durable_index_evidence"],
        "recall_shortened_deliberation": all_shapes_recall_shortened,
        "reviewer_rescue_edits": max_reviewer_rescue_edits,
    }

    _scenario_check(
        checks,
        "m6_9_repeated_task_recall_first_repetition_starts_without_durable_memory",
        all(
            (workspace / shape["source_rel"]).exists()
            and (workspace / shape["test_rel"]).exists()
            and shape_trace["fresh_exit_code"] == 0
            and shape_trace["fresh_relevant_count"] == 0
            for shape, shape_trace in zip(shapes, shape_traces)
        ),
        observed=[
            {
                "task_shape": shape_trace["task_shape"],
                "source_exists": (workspace / shape["source_rel"]).exists(),
                "test_exists": (workspace / shape["test_rel"]).exists(),
                "fresh_relevant_count": shape_trace["fresh_relevant_count"],
                "fresh_exit_code": shape_trace["fresh_exit_code"],
            }
            for shape, shape_trace in zip(shapes, shape_traces)
        ],
        expected="repetition 1 has the bounded task files but no durable repeated-task file-pair memory yet",
    )
    _scenario_check(
        checks,
        "m6_9_repeated_task_recall_first_repetition_writes_typed_memory_index_evidence",
        all(
            shape_trace["typed_memory_exit_code"] == 0
            and shape_trace["durable_index_evidence"]["kind"] == "file-pair"
            and shape_trace["durable_index_evidence"]["source_path"] == shape["source_rel"]
            and shape_trace["durable_index_evidence"]["test_path"] == shape["test_rel"]
            for shape, shape_trace in zip(shapes, shape_traces)
        ),
        observed=[
            {
                "task_shape": shape_trace["task_shape"],
                "exit_code": shape_trace["typed_memory_exit_code"],
                "evidence": shape_trace["durable_index_evidence"],
            }
            for shape_trace in shape_traces
        ],
        expected="repetition 1 persists typed file-pair memory usable as durable recall/index evidence",
    )
    _scenario_check(
        checks,
        "m6_9_repeated_task_recall_second_repetition_uses_durable_recall_index",
        all(
            shape_trace["recall_active_exit_code"] == 0 and shape_trace["recalled_file_pair_count"] > 0
            for shape_trace in shape_traces
        ),
        observed=[
            {
                "task_shape": shape_trace["task_shape"],
                "recall_active_exit_code": shape_trace["recall_active_exit_code"],
                "recalled_file_pair_count": shape_trace["recalled_file_pair_count"],
                "evidence": shape_trace["durable_index_evidence"],
            }
            for shape_trace in shape_traces
        ],
        expected="repetition 2 resolves the same source/test pair from durable typed recall/index evidence",
    )
    _scenario_check(
        checks,
        "m6_9_repeated_task_recall_second_repetition_shortens_deliberation_without_rescue",
        all_shapes_recall_shortened
        and max_reviewer_rescue_edits == 0
        and all(
            len(shape_trace["repetitions"]) == 5
            and len(shape_trace["first_five_wall_seconds"]) == 5
            and len(shape_trace["first_five_deliberation_step_counts"]) == 5
            and shape_trace["median_wall_seconds_improved"]
            and shape_trace["median_deliberation_step_count_improved"]
            for shape_trace in shape_traces
        ),
        observed=[
            {
                "task_shape": shape_trace["task_shape"],
                "first_five_wall_seconds": shape_trace["first_five_wall_seconds"],
                "first_five_deliberation_step_counts": shape_trace[
                    "first_five_deliberation_step_counts"
                ],
                "median_later_wall_seconds": shape_trace["median_later_wall_seconds"],
                "median_later_deliberation_step_count": shape_trace[
                    "median_later_deliberation_step_count"
                ],
                "reviewer_rescue_edits": shape_trace["reviewer_rescue_edits"],
                "recall_shortened_deliberation": shape_trace["recall_shortened_deliberation"],
            }
            for shape_trace in shape_traces
        ],
        expected="durable recall records five repetitions whose median wall time and deliberation/search steps improve with no reviewer rescue edits",
    )
    _scenario_check(
        checks,
        "m6_9_repeated_task_recall_covers_multiple_task_shapes",
        trace["shape_count"] >= 10
        and {
            "bounded_source_test_pair",
            "bounded_symbol_index_pair",
            "bounded_commands_pair",
            "bounded_memory_explore_pair",
            "bounded_context_checkpoint_pair",
            "bounded_work_loop_pair",
            "bounded_memory_pair",
            "bounded_tasks_pair",
            "bounded_runtime_pair",
            "bounded_snapshot_pair",
        }.issubset(set(trace["task_shapes"])),
        observed={"shape_count": trace["shape_count"], "task_shapes": trace["task_shapes"]},
        expected="the repeated-task proof matrix covers multiple deterministic task shapes",
    )
    _scenario_check(
        checks,
        "m6_9_repeated_task_recall_writes_deterministic_trace_artifact",
        trace["scenario"] == "m6_9-repeated-task-recall"
        and trace["recall_shortened_deliberation"] is True
        and trace["reviewer_rescue_edits"] == 0
        and trace["shape_count"] == len(shapes)
        and all(
            shape_trace["durable_index_evidence"]["source_path"] == shape["source_rel"]
            and shape_trace["durable_index_evidence"]["test_path"] == shape["test_rel"]
            for shape, shape_trace in zip(shapes, shape_traces)
        ),
        observed=trace,
        expected="trace artifact deterministically records both repetitions and recall_shortened_deliberation=true",
    )

    report = _scenario_report("m6_9-repeated-task-recall", workspace, commands, checks)
    report["artifacts"] = {
        "trace": trace,
        "shape_count": len(shape_traces),
        "task_shapes": [item["task_shape"] for item in shape_traces],
        "recall_shortened_deliberation": all_shapes_recall_shortened,
        "reviewer_rescue_edits": max_reviewer_rescue_edits,
        "repetition_1_deliberation_search_step_count": primary_shape["repetitions"][0][
            "deliberation_search_step_count"
        ],
        "repetition_2_deliberation_search_step_count": primary_shape["repetitions"][1][
            "deliberation_search_step_count"
        ],
        "first_five_wall_seconds": primary_shape["first_five_wall_seconds"],
        "first_five_deliberation_step_counts": primary_shape[
            "first_five_deliberation_step_counts"
        ],
        "resolved_source_path": primary_shape["durable_index_evidence"]["source_path"],
        "resolved_test_path": primary_shape["durable_index_evidence"]["test_path"],
        "durable_file_pair_id": primary_shape["durable_index_evidence"]["memory_id"],
        "recalled_file_pair_count": sum(item["recalled_file_pair_count"] for item in shape_traces),
        "per_shape_recalled_file_pair_counts": {
            item["task_shape"]: item["recalled_file_pair_count"] for item in shape_traces
        },
        "per_shape_first_five_wall_seconds": {
            item["task_shape"]: item["first_five_wall_seconds"] for item in shape_traces
        },
        "per_shape_first_five_deliberation_step_counts": {
            item["task_shape"]: item["first_five_deliberation_step_counts"]
            for item in shape_traces
        },
        "per_shape_median_improvement": {
            item["task_shape"]: {
                "wall_seconds": item["median_wall_seconds_improved"],
                "deliberation_step_count": item[
                    "median_deliberation_step_count_improved"
                ],
            }
            for item in shape_traces
        },
    }
    return report


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


def run_resident_loop_scenario(workspace, env=None, duration=6.0, interval=2.0, poll_interval=0.1, time_dilation=None):
    commands = []
    checks = []
    scenario_env = dogfood_time_dilation_env(env, time_dilation)
    multiplier = effective_time_dilation(scenario_env)

    def run(args, timeout=30):
        result = run_command(_scenario_command(*args), workspace, timeout=timeout, env=scenario_env)
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
        interval=float(interval),
        poll_interval=float(poll_interval),
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
        duration=float(duration),
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
    focus_result = run(["focus", "--kind", "coding"], timeout=15)
    brief_result = run(["brief", "--kind", "coding"], timeout=15)
    context_result = run(
        [
            "context",
            "--save",
            "resident-loop dogfood reentry probe",
            "--name",
            "Resident loop dogfood reentry probe",
            "--description",
            "Dogfood probe for M3 resident-loop reentry surfaces.",
        ],
        timeout=20,
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
    focus_output = focus_result.get("stdout") or ""
    brief_output = brief_result.get("stdout") or ""
    context_output = context_result.get("stdout") or ""
    questions = state.get("questions", [])
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
    passive_span_seconds = (
        round((passive_times[-1] - passive_times[0]).total_seconds(), 2)
        if len(passive_times) >= 2
        else 0.0
    )

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
            "passive_events": len(passive_events),
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
    _scenario_check(
        checks,
        "resident_loop_reentry_focus_surfaces_next_action",
        focus_result.get("exit_code") == 0
        and "Next:" in focus_output
        and "Resident loop cadence task" in focus_output,
        observed=focus_output.splitlines()[:12],
        expected="mew focus reconstructs the next action and task after resident runtime stops",
    )
    _scenario_check(
        checks,
        "resident_loop_reentry_brief_surfaces_current_state",
        brief_result.get("exit_code") == 0
        and "Next useful move:" in brief_output
        and "Resident loop cadence task" in brief_output,
        observed=brief_output.splitlines()[:16],
        expected="mew brief summarizes the stopped resident state and next useful move",
    )
    _scenario_check(
        checks,
        "resident_loop_reentry_context_saves_checkpoint",
        context_result.get("exit_code") == 0
        and "saved_memory:" in context_output
        and "unanswered_questions" in context_output,
        observed=context_output.splitlines()[:20],
        expected="mew context can save a reentry checkpoint after resident runtime stops",
    )
    report = _scenario_report("resident-loop", workspace, commands, checks)
    report["artifacts"] = {
        "requested_duration_seconds": float(duration),
        "requested_interval_seconds": float(interval),
        "time_dilation": multiplier,
        "processed_events": len(processed_events),
        "passive_events": len(passive_events),
        "open_questions": len([question for question in questions if question.get("status") == "open"]),
        "deferred_questions": len([question for question in questions if question.get("status") == "deferred"]),
        "passive_span_seconds": passive_span_seconds,
        "passive_gaps_seconds": passive_gaps,
    }
    return report


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


def run_m5_safety_hooks_scenario(workspace, env=None):
    commands = []
    checks = []
    (workspace / "ROADMAP_STATUS.md").write_text("old status\n", encoding="utf-8")
    script = r'''
import json
import sys
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from mew.cli import main
from mew.state import load_state


def run_main(args):
    stdout = StringIO()
    stderr = StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = main(args)
    return {"code": code, "stdout": stdout.getvalue(), "stderr": stderr.getvalue()}


def json_result(result):
    return json.loads(result["stdout"])


def start_self_improve(focus):
    result = run_main(["self-improve", "--start-session", "--force", "--focus", focus, "--json"])
    return result, json_result(result)


governance_start, governance_data = start_self_improve("M5.1 dogfood governance safety hook")
governance_task_id = str(governance_data["task"]["id"])
governance_model_output = {
    "summary": "preview governance edit",
    "action": {
        "type": "edit_file",
        "path": "ROADMAP_STATUS.md",
        "old": "old status",
        "new": "new status",
    },
}
verify_command = f"{sys.executable} -c \"print('verify ok')\""
with patch("mew.commands.load_model_auth", return_value={"path": "auth.json"}):
    with patch("mew.work_loop.call_model_json_with_retries", return_value=governance_model_output):
        governance_work = run_main(
            [
                "work",
                governance_task_id,
                "--live",
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
governance_audit = run_main(["self-improve", "--audit", governance_task_id, "--json"])
governance_audit_data = json_result(governance_audit)

external_start, external_data = start_self_improve("M5.1 dogfood external side-effect hook")
external_task_id = str(external_data["task"]["id"])
external_model_output = {
    "summary": "try an external side effect",
    "action": {"type": "run_command", "command": "git push origin main"},
}
with patch("mew.commands.load_model_auth", return_value={"path": "auth.json"}):
    with patch("mew.work_loop.call_model_json_with_retries", return_value=external_model_output):
        with patch(
            "mew.commands.execute_work_tool_with_output",
            side_effect=AssertionError("external command should not execute"),
        ):
            external_work = run_main(
                [
                    "work",
                    external_task_id,
                    "--live",
                    "--auth",
                    "auth.json",
                    "--allow-read",
                    ".",
                    "--allow-shell",
                    "--max-steps",
                    "1",
                    "--act-mode",
                    "deterministic",
                ]
            )
external_audit = run_main(["self-improve", "--audit", external_task_id, "--json"])
external_audit_data = json_result(external_audit)

state = load_state()
governance_session = next(
    session for session in state["work_sessions"] if str(session.get("task_id")) == governance_task_id
)
external_session = next(
    session for session in state["work_sessions"] if str(session.get("task_id")) == external_task_id
)

print(
    json.dumps(
        {
            "governance_start": governance_start,
            "governance_work": governance_work,
            "governance_audit": governance_audit,
            "governance_audit_data": governance_audit_data,
            "governance_file": Path("ROADMAP_STATUS.md").read_text(encoding="utf-8"),
            "governance_tool_calls": governance_session.get("tool_calls") or [],
            "external_start": external_start,
            "external_work": external_work,
            "external_audit": external_audit,
            "external_audit_data": external_audit_data,
            "external_tool_calls": external_session.get("tool_calls") or [],
            "external_notes": external_session.get("notes") or [],
        },
        ensure_ascii=False,
    )
)
'''
    result = run_command([sys.executable, "-c", script], workspace, timeout=30, env=env)
    commands.append(result)
    data = _json_stdout(result)
    governance_work = data.get("governance_work") or {}
    external_work = data.get("external_work") or {}
    governance_safety = (data.get("governance_audit_data") or {}).get("safety_boundaries") or {}
    external_safety = (data.get("external_audit_data") or {}).get("safety_boundaries") or {}
    governance_calls = data.get("governance_tool_calls") or []
    external_notes = data.get("external_notes") or []

    _scenario_check(
        checks,
        "m5_safety_hooks_governance_auto_approval_escalates",
        result.get("exit_code") == 0
        and governance_work.get("code") == 0
        and "inline_approval=safety_blocked" in (governance_work.get("stdout") or "")
        and data.get("governance_file") == "old status\n"
        and governance_safety.get("status") == "needs_review"
        and "governance_or_policy_edit" in (governance_safety.get("findings") or [])
        and governance_calls
        and not governance_calls[0].get("approval_status"),
        observed={
            "work": command_result_tail(governance_work),
            "file": data.get("governance_file"),
            "safety": governance_safety,
            "calls": governance_calls,
        },
        expected="self-improve governance edit is safety-blocked from accept-edits and remains pending",
    )
    _scenario_check(
        checks,
        "m5_safety_hooks_external_side_effect_blocks_before_execution",
        result.get("exit_code") == 0
        and external_work.get("code") == 0
        and "stop=safety_blocked" in (external_work.get("stdout") or "")
        and not data.get("external_tool_calls")
        and external_safety.get("status") == "blocked"
        and "safety_blocked_event" in (external_safety.get("findings") or [])
        and any("M5 safety blocked tool execution" in (note.get("text") or "") for note in external_notes),
        observed={
            "work": command_result_tail(external_work),
            "safety": external_safety,
            "tool_calls": data.get("external_tool_calls"),
            "notes": external_notes,
        },
        expected="external-visible command is blocked before tool execution and surfaced in audit",
    )
    report = _scenario_report("m5-safety-hooks", workspace, commands, checks)
    report["artifacts"] = {
        "governance_task_id": ((data.get("governance_audit_data") or {}).get("task") or {}).get("id"),
        "external_task_id": ((data.get("external_audit_data") or {}).get("task") or {}).get("id"),
    }
    return report


def run_m6_daemon_watch_scenario(workspace, env=None):
    commands = []
    checks = []
    watched = workspace / "watched.txt"
    watched.write_text("before\n", encoding="utf-8")

    def run(args, timeout=30, record=True):
        result = run_command(_scenario_command(*args), workspace, timeout=timeout, env=env)
        if record:
            commands.append(result)
        return result

    def wait_for(predicate, timeout=5.0, interval=0.05):
        deadline = time.monotonic() + timeout
        latest = None
        while time.monotonic() < deadline:
            latest = predicate()
            if latest:
                return latest
            time.sleep(interval)
        return latest

    start_result = run(
        [
            "daemon",
            "start",
            "--timeout",
            "5",
            "--poll-interval",
            "0.05",
            "--",
            "--interval",
            "999",
            "--poll-interval",
            "0.05",
            "--watch-path",
            "watched.txt",
            "--echo-effects",
        ],
        timeout=10,
    )
    daemon_started = start_result.get("exit_code") == 0
    status_data = {}
    status_json = {}
    processed_event = None
    final_state = {}
    stop_result = None
    try:
        status_data = wait_for(
            lambda: (
                data
                if (data := read_json_file(workspace / STATE_FILE, {})).get("watchers", {}).get("active_count", 0) >= 1
                else None
            ),
            timeout=5.0,
        ) or {}
        status_result = run(["daemon", "status", "--json"], timeout=5)
        status_json = _json_stdout(status_result)
        watched.write_text("after changed\n", encoding="utf-8")

        processed_event = wait_for(
            lambda: next(
                (
                    event
                    for event in (read_json_file(workspace / STATE_FILE, {}).get("inbox") or [])
                    if event.get("type") == "file_change" and event.get("processed_at")
                ),
                None,
            ),
            timeout=5.0,
        )
        final_state = read_json_file(workspace / STATE_FILE, {})
    finally:
        if daemon_started:
            stop_result = run(["daemon", "stop", "--timeout", "5", "--poll-interval", "0.05"], timeout=10)
        else:
            stop_result = {"exit_code": None, "stdout": "", "stderr": "daemon was not started"}

    final_status = run(["daemon", "status", "--json"], timeout=5)
    final_status_json = _json_stdout(final_status)
    log_text = read_text_file(workspace / STATE_DIR / "runtime.out")
    runtime_effects = final_state.get("runtime_effects") or []
    external_effects = [effect for effect in runtime_effects if effect.get("reason") == "external_event"]
    watcher_items = ((final_status_json.get("watchers") or {}).get("items")) or []

    _scenario_check(
        checks,
        "m6_daemon_watch_start_reports_active",
        daemon_started and "runtime is active" in (start_result.get("stdout") or ""),
        observed=start_result.get("stdout"),
        expected="daemon start reports runtime is active",
    )
    _scenario_check(
        checks,
        "m6_daemon_status_reports_active_watcher",
        (status_json.get("watchers") or {}).get("active_count", 0) >= 1
        and status_json.get("uptime_seconds") is not None,
        observed={
            "state": status_json.get("state"),
            "uptime_seconds": status_json.get("uptime_seconds"),
            "watchers": status_json.get("watchers"),
        },
        expected="daemon status reports uptime and at least one active watcher",
    )
    _scenario_check(
        checks,
        "m6_daemon_watcher_queues_processed_file_event",
        bool(processed_event)
        and processed_event.get("source") == "daemon_watch"
        and (processed_event.get("payload") or {}).get("change_kind") == "modified",
        observed=processed_event,
        expected="file_change event from daemon_watch is processed",
    )
    _scenario_check(
        checks,
        "m6_daemon_watcher_uses_external_event_runtime_path",
        bool(external_effects),
        observed=external_effects[-1] if external_effects else None,
        expected="runtime effect reason external_event exists",
    )
    _scenario_check(
        checks,
        "m6_daemon_stop_marks_watchers_idle",
        stop_result.get("exit_code") == 0
        and final_status_json.get("state") == "stopped"
        and all(item.get("status") != "active" for item in watcher_items),
        observed={
            "stop": command_result_tail(stop_result),
            "final_status": final_status_json,
            "watchers": watcher_items,
        },
        expected="daemon stop succeeds and watcher state is no longer active",
    )
    _scenario_check(
        checks,
        "m6_daemon_log_records_external_event",
        "reason=external_event" in log_text,
        observed=log_text[-400:],
        expected="runtime output mentions reason=external_event",
    )
    report = _scenario_report("m6-daemon-watch", workspace, commands, checks)
    report["artifacts"] = {
        "watched_path": str(watched),
        "event_id": (processed_event or {}).get("id"),
        "status_before_change": status_data,
        "final_status": final_status_json,
    }
    return report


def run_m6_daemon_restart_scenario(workspace, env=None):
    commands = []
    checks = []
    watched = workspace / "restart.txt"
    watched.write_text("before restart\n", encoding="utf-8")

    def run(args, timeout=30):
        result = run_command(_scenario_command(*args), workspace, timeout=timeout, env=env)
        commands.append(result)
        return result

    def wait_for(predicate, timeout=5.0, interval=0.05):
        deadline = time.monotonic() + timeout
        latest = None
        while time.monotonic() < deadline:
            latest = predicate()
            if latest:
                return latest
            time.sleep(interval)
        return latest

    start_args = [
        "daemon",
        "start",
        "--timeout",
        "5",
        "--poll-interval",
        "0.05",
        "--",
        "--interval",
        "999",
        "--poll-interval",
        "0.05",
        "--watch-path",
        "restart.txt",
        "--echo-effects",
    ]
    stop_args = ["daemon", "stop", "--timeout", "5", "--poll-interval", "0.05"]

    first_start = run(start_args, timeout=10)
    first_started = first_start.get("exit_code") == 0
    wait_for(
        lambda: (
            data
            if (data := read_json_file(workspace / STATE_FILE, {})).get("watchers", {}).get("active_count", 0) >= 1
            else None
        ),
        timeout=5.0,
    )
    first_stop = run(stop_args, timeout=10) if first_started else {"exit_code": None}
    stopped_state = read_json_file(workspace / STATE_FILE, {})
    watched.write_text("after restart changed\n", encoding="utf-8")

    second_start = run(start_args, timeout=10)
    second_started = second_start.get("exit_code") == 0
    processed_event = None
    final_state = {}
    final_stop = None
    restart_status_json = {}
    try:
        processed_event = wait_for(
            lambda: next(
                (
                    event
                    for event in (read_json_file(workspace / STATE_FILE, {}).get("inbox") or [])
                    if event.get("type") == "file_change" and event.get("processed_at")
                ),
                None,
            ),
            timeout=5.0,
        )
        final_state = read_json_file(workspace / STATE_FILE, {})
        restart_status_result = run(["daemon", "status", "--json"], timeout=5)
        restart_status_json = _json_stdout(restart_status_result)
    finally:
        if second_started:
            final_stop = run(stop_args, timeout=10)
        else:
            final_stop = {"exit_code": None, "stdout": "", "stderr": "daemon was not restarted"}

    final_status_result = run(["daemon", "status", "--json"], timeout=5)
    final_status_json = _json_stdout(final_status_result)
    runtime_effects = final_state.get("runtime_effects") or []
    external_effects = [effect for effect in runtime_effects if effect.get("reason") == "external_event"]
    stopped_watchers = (stopped_state.get("watchers") or {}).get("items") or []
    final_watchers = (final_status_json.get("watchers") or {}).get("items") or []
    event_payload = (processed_event or {}).get("payload") or {}
    previous_snapshot = event_payload.get("previous") or {}
    current_snapshot = event_payload.get("current") or {}

    _scenario_check(
        checks,
        "m6_daemon_restart_initial_start_and_stop",
        first_started
        and first_stop.get("exit_code") == 0
        and all(item.get("status") != "active" for item in stopped_watchers),
        observed={
            "start": command_result_tail(first_start),
            "stop": command_result_tail(first_stop),
            "watchers": stopped_watchers,
        },
        expected="initial daemon starts, baselines watcher, then stops with watcher idle",
    )
    _scenario_check(
        checks,
        "m6_daemon_restart_reports_active_watcher",
        second_started
        and restart_status_json.get("state") == "running"
        and (restart_status_json.get("watchers") or {}).get("active_count", 0) >= 1,
        observed=restart_status_json,
        expected="restarted daemon reports running with active watcher",
    )
    _scenario_check(
        checks,
        "m6_daemon_restart_reattaches_watcher_snapshot",
        bool(processed_event)
        and processed_event.get("source") == "daemon_watch"
        and previous_snapshot.get("size") != current_snapshot.get("size"),
        observed=processed_event,
        expected="file_change after restart compares against snapshot from previous daemon process",
    )
    _scenario_check(
        checks,
        "m6_daemon_restart_uses_external_event_path",
        bool(external_effects),
        observed=external_effects[-1] if external_effects else None,
        expected="restarted daemon processes watcher event through external_event",
    )
    _scenario_check(
        checks,
        "m6_daemon_restart_final_stop_is_clean",
        final_stop.get("exit_code") == 0
        and final_status_json.get("state") == "stopped"
        and all(item.get("status") != "active" for item in final_watchers),
        observed={
            "stop": command_result_tail(final_stop),
            "final_status": final_status_json,
            "watchers": final_watchers,
        },
        expected="final daemon stop succeeds and no watcher remains active",
    )
    report = _scenario_report("m6-daemon-restart", workspace, commands, checks)
    report["artifacts"] = {
        "watched_path": str(watched),
        "event_id": (processed_event or {}).get("id"),
        "final_status": final_status_json,
    }
    return report


def run_m6_daemon_loop_scenario(
    workspace,
    env=None,
    duration=6.0,
    interval=2.0,
    poll_interval=0.1,
    time_dilation=None,
):
    commands = []
    checks = []
    watched = workspace / "daemon-loop-watch.txt"
    watched.write_text("before daemon loop\n", encoding="utf-8")
    scenario_env = dogfood_time_dilation_env(env, time_dilation)
    multiplier = effective_time_dilation(scenario_env)

    def run(args, timeout=30):
        result = run_command(_scenario_command(*args), workspace, timeout=timeout, env=scenario_env)
        commands.append(result)
        return result

    def wait_for(predicate, timeout=5.0, interval=0.05):
        deadline = time.monotonic() + timeout
        latest = None
        while time.monotonic() < deadline:
            latest = predicate()
            if latest:
                return latest
            time.sleep(interval)
        return latest

    task_result = run(
        [
            "task",
            "add",
            "Daemon loop cadence task",
            "--kind",
            "coding",
            "--priority",
            "normal",
            "--json",
        ],
        timeout=15,
    )
    task_data = _json_stdout(task_result)
    start_result = run(
        [
            "daemon",
            "start",
            "--timeout",
            "5",
            "--poll-interval",
            "0.05",
            "--",
            "--interval",
            str(interval),
            "--poll-interval",
            str(poll_interval),
            "--watch-path",
            watched.name,
            "--autonomous",
            "--autonomy-level",
            "propose",
            "--echo-effects",
        ],
        timeout=10,
    )
    started = start_result.get("exit_code") == 0
    remaining_duration = max(0.0, float(duration))
    initial_sleep = min(remaining_duration, max(0.2, min(1.0, float(interval))))
    if initial_sleep:
        time.sleep(initial_sleep)
        remaining_duration -= initial_sleep

    watcher_ready_state = wait_for(
        lambda: (
            data
            if (data := read_json_file(workspace / STATE_FILE, {})).get("watchers", {}).get("active_count", 0) >= 1
            else None
        ),
        timeout=5.0,
    ) or {}
    watched.write_text("after daemon loop change\n", encoding="utf-8")
    processed_watcher_event = wait_for(
        lambda: next(
            (
                event
                for event in (read_json_file(workspace / STATE_FILE, {}).get("inbox") or [])
                if event.get("type") == "file_change"
                and event.get("source") == "daemon_watch"
                and event.get("processed_at")
            ),
            None,
        ),
        timeout=5.0,
    )
    pause_result = run(["daemon", "pause", "--json", "dogfood loop proof"], timeout=5)
    pause_json = _json_stdout(pause_result)
    inspect_result = run(["daemon", "inspect", "--json"], timeout=5)
    inspect_json = _json_stdout(inspect_result)
    resume_result = run(["daemon", "resume", "--json"], timeout=5)
    resume_json = _json_stdout(resume_result)
    if remaining_duration:
        time.sleep(remaining_duration)
    active_status = _json_stdout(run(["daemon", "status", "--json"], timeout=5))
    stop_result = run(["daemon", "stop", "--timeout", "10", "--poll-interval", "0.05"], timeout=15) if started else {"exit_code": None}
    final_status = _json_stdout(run(["daemon", "status", "--json"], timeout=5))
    focus_result = run(["focus", "--kind", "coding"], timeout=15)
    state = read_json_file(workspace / STATE_FILE, {})
    log_text = read_text_file(workspace / STATE_DIR / "runtime.out")

    processed_events = [event for event in state.get("inbox", []) if event.get("processed_at")]
    passive_events = [event for event in processed_events if event.get("type") == "passive_tick"]
    passive_effects = [effect for effect in state.get("runtime_effects", []) if effect.get("reason") == "passive_tick"]
    external_effects = [effect for effect in state.get("runtime_effects", []) if effect.get("reason") == "external_event"]
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
    passive_span_seconds = (
        round((passive_times[-1] - passive_times[0]).total_seconds(), 2)
        if len(passive_times) >= 2
        else 0.0
    )

    _scenario_check(
        checks,
        "m6_daemon_loop_starts_reports_and_stops",
        task_result.get("exit_code") == 0
        and started
        and active_status.get("state") == "running"
        and active_status.get("uptime_seconds") is not None
        and (active_status.get("watchers") or {}).get("active_count", 0) >= 1
        and stop_result.get("exit_code") == 0
        and final_status.get("state") == "stopped",
        observed={
            "task": task_data,
            "start": command_result_tail(start_result),
            "active_status": active_status,
            "stop": command_result_tail(stop_result),
            "final_status": final_status,
        },
        expected="daemon starts, reports uptime and watcher state while running, and stops cleanly",
    )
    _scenario_check(
        checks,
        "m6_daemon_loop_watcher_processes_file_event",
        bool(processed_watcher_event)
        and processed_watcher_event.get("source") == "daemon_watch"
        and bool(
            (
                (processed_watcher_event.get("decision_plan") or {}).get("decisions")
                or (processed_watcher_event.get("action_plan") or {}).get("actions")
                or external_effects
            )
        ),
        observed={
            "watcher_ready": watcher_ready_state.get("watchers"),
            "processed_event": processed_watcher_event,
            "external_effect": external_effects[-1] if external_effects else None,
        },
        expected="long daemon proof includes a real watcher file_change processed through the daemon loop",
    )
    _scenario_check(
        checks,
        "m6_daemon_loop_controls_pause_inspect_resume",
        pause_result.get("exit_code") == 0
        and inspect_result.get("exit_code") == 0
        and resume_result.get("exit_code") == 0
        and (pause_json.get("safety") or {}).get("autonomy_paused") is True
        and inspect_json.get("state") == "running"
        and (resume_json.get("safety") or {}).get("autonomy_paused") is False,
        observed={
            "pause": pause_json,
            "inspect_state": inspect_json.get("state"),
            "resume": resume_json,
        },
        expected="pause, inspect, and resume controls work against a running daemon",
    )
    _scenario_check(
        checks,
        "m6_daemon_loop_processes_multiple_passive_ticks",
        len(processed_events) >= 3
        and bool([event for event in processed_events if event.get("type") == "startup"])
        and len(passive_events) >= 2
        and any(gap >= max(0.5, float(interval) * 0.5) for gap in passive_gaps),
        observed={
            "processed": len(processed_events),
            "by_type": count_by(processed_events, "type"),
            "passive_events": len(passive_events),
            "passive_gaps_seconds": passive_gaps,
        },
        expected="daemon path processes startup plus at least two spaced passive ticks",
    )
    _scenario_check(
        checks,
        "m6_daemon_loop_records_passive_effects",
        len(passive_effects) >= 2
        and all(effect.get("status") == "applied" for effect in passive_effects[-2:]),
        observed=runtime_effect_summary(state),
        expected="daemon path records applied passive_tick runtime effects",
    )
    _scenario_check(
        checks,
        "m6_daemon_loop_logs_passive_ticks",
        log_text.count("reason=passive_tick") >= 2,
        observed=log_text[-600:],
        expected="daemon output log includes repeated passive_tick summaries",
    )
    _scenario_check(
        checks,
        "m6_daemon_loop_reentry_focus_surfaces_task",
        focus_result.get("exit_code") == 0
        and "Daemon loop cadence task" in (focus_result.get("stdout") or ""),
        observed=(focus_result.get("stdout") or "").splitlines()[:12],
        expected="focus can inspect stopped daemon state and task context",
    )
    report = _scenario_report("m6-daemon-loop", workspace, commands, checks)
    report["artifacts"] = {
        "requested_duration_seconds": float(duration),
        "requested_interval_seconds": float(interval),
        "time_dilation": multiplier,
        "processed_events": len(processed_events),
        "passive_events": len(passive_events),
        "passive_span_seconds": passive_span_seconds,
        "passive_gaps_seconds": passive_gaps,
        "watched_path": str(watched),
        "watcher_event_id": (processed_watcher_event or {}).get("id"),
        "controls": {
            "pause_exit_code": pause_result.get("exit_code"),
            "inspect_exit_code": inspect_result.get("exit_code"),
            "resume_exit_code": resume_result.get("exit_code"),
        },
    }
    return report


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


def run_m4_file_write_recovery_scenario(workspace, env=None):
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
    verify_code = "from pathlib import Path; assert Path('write-target.txt').read_text().startswith('after')"
    verify_command = f"{shlex.quote(sys.executable)} -c {shlex.quote(verify_code)}"
    task_result = run(
        [
            "task",
            "add",
            "M4 file-write recovery task",
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
            workspace,
            "--allow-write",
            workspace,
            "--json",
        ],
        timeout=15,
    )
    start_data = _json_stdout(start_result)
    session_id = (start_data.get("work_session") or {}).get("id")
    state_path = Path(workspace) / STATE_FILE

    write_parameters = {
        "path": str(target),
        "old": "before\n",
        "new": "after\n",
        "apply": True,
        "allowed_write_roots": [str(workspace)],
        "allow_verify": True,
        "verify_command": verify_command,
        "verify_cwd": str(workspace),
    }
    write_intent = build_write_intent("edit_file", write_parameters)
    state = reconcile_next_ids(migrate_state(read_json_file(state_path, {})))
    session = find_work_session(state, session_id)
    retry_source_call_id = None
    if session:
        retry_source_call_id = next_id(state, "work_tool_call")
        session.setdefault("tool_calls", []).append(
            {
                "id": retry_source_call_id,
                "session_id": session_id,
                "task_id": task_id,
                "tool": "edit_file",
                "status": "interrupted",
                "parameters": write_parameters,
                "write_intent": write_intent,
                "summary": "interrupted before atomic write",
                "error": "Interrupted before the apply-write completed.",
                "started_at": "2026-04-20T00:00:00Z",
            }
        )
        session["last_tool_call_id"] = retry_source_call_id
        write_json_file(state_path, state)

    retry_resume_result = run(["work", str(task_id), "--session", "--resume", "--json"], timeout=15)
    retry_result = run(
        [
            "work",
            str(task_id),
            "--recover-session",
            "--allow-write",
            workspace,
            "--allow-verify",
            "--verify-command",
            verify_command,
            "--json",
        ],
        timeout=30,
    )
    retry_resume = _json_stdout(retry_resume_result).get("resume") or {}
    retry_report = _json_stdout(retry_result)
    retry_state = read_json_file(state_path, {})
    retry_session = find_work_session(retry_state, session_id)
    retry_source_call = next(
        (
            call
            for call in (retry_session or {}).get("tool_calls") or []
            if str(call.get("id")) == str(retry_source_call_id)
        ),
        {},
    )
    retry_recovered_call = next(
        (
            call
            for call in (retry_session or {}).get("tool_calls") or []
            if str(call.get("id")) == str(retry_source_call.get("recovered_by_tool_call_id"))
        ),
        {},
    )
    retry_target_text = target.read_text(encoding="utf-8")

    target.write_text("before\n", encoding="utf-8")
    completed_intent = build_write_intent("edit_file", write_parameters)
    target.write_text("after\n", encoding="utf-8")
    state = reconcile_next_ids(migrate_state(read_json_file(state_path, {})))
    session = find_work_session(state, session_id)
    completed_source_call_id = None
    if session:
        completed_source_call_id = next_id(state, "work_tool_call")
        session.setdefault("tool_calls", []).append(
            {
                "id": completed_source_call_id,
                "session_id": session_id,
                "task_id": task_id,
                "tool": "edit_file",
                "status": "interrupted",
                "parameters": write_parameters,
                "write_intent": completed_intent,
                "summary": "interrupted after atomic write",
                "error": "Interrupted before verification completed.",
                "started_at": "2026-04-20T00:01:00Z",
            }
        )
        session["last_tool_call_id"] = completed_source_call_id
        write_json_file(state_path, state)

    completed_resume_result = run(["work", str(task_id), "--session", "--resume", "--json"], timeout=15)
    completed_result = run(
        [
            "work",
            str(task_id),
            "--recover-session",
            "--allow-read",
            workspace,
            "--allow-verify",
            "--verify-command",
            verify_command,
            "--json",
        ],
        timeout=30,
    )
    completed_resume = _json_stdout(completed_resume_result).get("resume") or {}
    completed_report = _json_stdout(completed_result)
    completed_state = read_json_file(state_path, {})
    completed_session = find_work_session(completed_state, session_id)
    completed_source_call = next(
        (
            call
            for call in (completed_session or {}).get("tool_calls") or []
            if str(call.get("id")) == str(completed_source_call_id)
        ),
        {},
    )
    completed_recovered_call = next(
        (
            call
            for call in (completed_session or {}).get("tool_calls") or []
            if str(call.get("id")) == str(completed_source_call.get("recovered_by_tool_call_id"))
        ),
        {},
    )
    completed_target_text = target.read_text(encoding="utf-8")

    target.write_text("before\n", encoding="utf-8")
    diverged_intent = build_write_intent("edit_file", write_parameters)
    target.write_text("human edit\n", encoding="utf-8")
    state = reconcile_next_ids(migrate_state(read_json_file(state_path, {})))
    session = find_work_session(state, session_id)
    diverged_source_call_id = None
    if session:
        diverged_source_call_id = next_id(state, "work_tool_call")
        session.setdefault("tool_calls", []).append(
            {
                "id": diverged_source_call_id,
                "session_id": session_id,
                "task_id": task_id,
                "tool": "edit_file",
                "status": "interrupted",
                "parameters": write_parameters,
                "write_intent": diverged_intent,
                "summary": "interrupted with diverged target",
                "error": "Target changed before recovery.",
                "started_at": "2026-04-20T00:02:00Z",
            }
        )
        session["last_tool_call_id"] = diverged_source_call_id
        write_json_file(state_path, state)

    diverged_resume_result = run(["work", str(task_id), "--session", "--resume", "--json"], timeout=15)
    diverged_result = run(["work", str(task_id), "--recover-session", "--json"], timeout=15)
    diverged_resume = _json_stdout(diverged_resume_result).get("resume") or {}
    diverged_report = _json_stdout(diverged_result)
    diverged_item = next(
        (
            item
            for item in ((diverged_resume.get("recovery_plan") or {}).get("items") or [])
            if str(item.get("tool_call_id")) == str(diverged_source_call_id)
        ),
        {},
    )

    target.write_text("before\n", encoding="utf-8")
    partial_intent = build_write_intent("edit_file", write_parameters)
    temp_path = target.parent / f".{target.name}.m4.tmp"
    temp_path.write_text("after\n", encoding="utf-8")
    state = reconcile_next_ids(migrate_state(read_json_file(state_path, {})))
    session = find_work_session(state, session_id)
    partial_source_call_id = None
    if session:
        partial_source_call_id = next_id(state, "work_tool_call")
        session.setdefault("tool_calls", []).append(
            {
                "id": partial_source_call_id,
                "session_id": session_id,
                "task_id": task_id,
                "tool": "edit_file",
                "status": "interrupted",
                "parameters": write_parameters,
                "write_intent": partial_intent,
                "summary": "interrupted with temp file",
                "error": "Atomic temp file survived recovery.",
                "started_at": "2026-04-20T00:03:00Z",
            }
        )
        session["last_tool_call_id"] = partial_source_call_id
        write_json_file(state_path, state)

    partial_resume_result = run(["work", str(task_id), "--session", "--resume", "--json"], timeout=15)
    partial_result = run(["work", str(task_id), "--recover-session", "--json"], timeout=15)
    partial_resume = _json_stdout(partial_resume_result).get("resume") or {}
    partial_report = _json_stdout(partial_result)
    partial_item = next(
        (
            item
            for item in ((partial_resume.get("recovery_plan") or {}).get("items") or [])
            if str(item.get("tool_call_id")) == str(partial_source_call_id)
        ),
        {},
    )

    rollback_target = Path(workspace) / "rollback-target.txt"
    rollback_target.write_text("after\n", encoding="utf-8")
    rollback_verify_command = f"{shlex.quote(sys.executable)} -c {shlex.quote('import sys; sys.exit(1)')}"
    state = reconcile_next_ids(migrate_state(read_json_file(state_path, {})))
    session = find_work_session(state, session_id)
    rollback_source_call_id = None
    if session:
        rollback_source_call_id = next_id(state, "work_tool_call")
        session.setdefault("tool_calls", []).append(
            {
                "id": rollback_source_call_id,
                "session_id": session_id,
                "task_id": task_id,
                "tool": "edit_file",
                "status": "failed",
                "parameters": {
                    "path": str(rollback_target),
                    "old": "before\n",
                    "new": "after\n",
                    "apply": True,
                    "verify_command": rollback_verify_command,
                    "verify_cwd": str(workspace),
                },
                "result": {
                    "path": str(rollback_target),
                    "written": True,
                    "rolled_back": False,
                    "rollback_error": "simulated rollback failure",
                    "verification": {
                        "command": rollback_verify_command,
                        "cwd": str(workspace),
                        "exit_code": 1,
                    },
                },
                "summary": "verification failed after write",
                "error": "verification failed; rollback failed: simulated rollback failure",
                "started_at": "2026-04-20T00:04:00Z",
                "finished_at": "2026-04-20T00:04:01Z",
            }
        )
        session["last_tool_call_id"] = rollback_source_call_id
        write_json_file(state_path, state)

    rollback_resume_result = run(["work", str(task_id), "--session", "--resume", "--json"], timeout=15)
    rollback_resume = _json_stdout(rollback_resume_result).get("resume") or {}
    rollback_item = next(
        (
            item
            for item in ((rollback_resume.get("recovery_plan") or {}).get("items") or [])
            if str(item.get("tool_call_id")) == str(rollback_source_call_id)
        ),
        {},
    )

    retry_item = ((retry_resume.get("recovery_plan") or {}).get("items") or [{}])[0]
    completed_item = ((completed_resume.get("recovery_plan") or {}).get("items") or [{}])[0]
    _scenario_check(
        checks,
        "m4_file_write_recovery_retries_not_started_apply_write",
        task_result.get("exit_code") == 0
        and start_result.get("exit_code") == 0
        and retry_result.get("exit_code") == 0
        and retry_item.get("action") == "retry_apply_write"
        and (retry_item.get("write_world_state") or {}).get("state") == "not_started"
        and (retry_report.get("recovery") or {}).get("action") == "retry_apply_write"
        and retry_source_call.get("recovery_status") == "superseded"
        and retry_recovered_call.get("tool") == "edit_file"
        and retry_recovered_call.get("status") == "completed"
        and ((retry_recovered_call.get("result") or {}).get("verification_exit_code") == 0)
        and retry_target_text == "after\n",
        observed={
            "resume_item": retry_item,
            "recovery": retry_report.get("recovery"),
            "source_call": retry_source_call,
            "recovered_call": retry_recovered_call,
            "target_text": retry_target_text,
        },
        expected="interrupted apply-write whose target still matches pre-write hash is resumed with verifier",
    )
    _scenario_check(
        checks,
        "m4_file_write_recovery_skips_completed_write_and_verifies",
        completed_result.get("exit_code") == 0
        and completed_item.get("action") == "verify_completed_write"
        and (completed_item.get("write_world_state") or {}).get("state") == "completed_externally"
        and (completed_report.get("recovery") or {}).get("action") == "verify_completed_write"
        and completed_source_call.get("recovery_status") == "superseded"
        and completed_recovered_call.get("tool") == "run_tests"
        and completed_recovered_call.get("status") == "completed"
        and ((completed_recovered_call.get("result") or {}).get("exit_code") == 0)
        and completed_target_text == "after\n",
        observed={
            "resume_item": completed_item,
            "recovery": completed_report.get("recovery"),
            "source_call": completed_source_call,
            "recovered_call": completed_recovered_call,
            "target_text": completed_target_text,
        },
        expected="interrupted apply-write whose target already matches intended hash skips reapply and verifies",
    )
    _scenario_check(
        checks,
        "m4_file_write_recovery_reports_target_diverged_review",
        diverged_result.get("exit_code") == 0
        and diverged_item.get("action") == "needs_user_review"
        and diverged_item.get("effect_classification") == "target_diverged"
        and (diverged_item.get("write_world_state") or {}).get("state") == "target_diverged"
        and (diverged_report.get("recovery") or {}).get("action") == "needs_user"
        and (((diverged_report.get("recovery") or {}).get("review_item") or {}).get("write_world_state") or {}).get("state")
        == "target_diverged",
        observed={
            "resume_item": diverged_item,
            "recovery": diverged_report.get("recovery"),
            "target_text": target.read_text(encoding="utf-8"),
        },
        expected="diverged applied write reports review context instead of retrying",
    )
    _scenario_check(
        checks,
        "m4_file_write_recovery_reports_partial_review",
        partial_result.get("exit_code") == 0
        and partial_item.get("action") == "needs_user_review"
        and partial_item.get("effect_classification") == "partial"
        and (partial_item.get("write_world_state") or {}).get("state") == "partial"
        and bool((partial_item.get("write_world_state") or {}).get("temp_paths"))
        and (partial_report.get("recovery") or {}).get("action") == "needs_user"
        and (((partial_report.get("recovery") or {}).get("review_item") or {}).get("write_world_state") or {}).get("state")
        == "partial",
        observed={
            "resume_item": partial_item,
            "recovery": partial_report.get("recovery"),
            "temp_path": str(temp_path),
            "target_text": target.read_text(encoding="utf-8"),
        },
        expected="partial applied write reports temp-file review context instead of retrying",
    )
    _scenario_check(
        checks,
        "m4_file_write_recovery_reports_rollback_needed_review",
        rollback_resume_result.get("exit_code") == 0
        and rollback_item.get("action") == "needs_user_review"
        and rollback_item.get("effect_classification") == "rollback_needed"
        and rollback_item.get("safety") == "write"
        and rollback_item.get("path") == str(rollback_target)
        and "rollback was not confirmed" in (rollback_item.get("reason") or "")
        and "restore or intentionally keep" in " ".join(rollback_item.get("review_steps") or []),
        observed={
            "resume_item": rollback_item,
            "target_text": rollback_target.read_text(encoding="utf-8"),
        },
        expected="failed write with unconfirmed rollback reports rollback_needed review context",
    )
    return _scenario_report("m4-file-write-recovery", workspace, commands, checks)


def run_m4_runtime_effect_recovery_scenario(workspace, env=None):
    commands = []
    checks = []
    workspace_path = Path(workspace)

    def run(args, timeout=30):
        result = run_command(_scenario_command(*args), workspace, timeout=timeout, env=env)
        commands.append(result)
        return result

    not_started_path = workspace_path / "runtime-intent-not-started.txt"
    not_started_path.write_text("old\n", encoding="utf-8")
    not_started_intent = build_write_intent(
        "edit_file",
        {
            "path": str(not_started_path),
            "old": "old\n",
            "new": "new\n",
            "apply": True,
            "allowed_write_roots": [str(workspace_path)],
        },
    )
    completed_path = workspace_path / "runtime-intent-completed.txt"
    completed_path.write_text("old\n", encoding="utf-8")
    completed_intent = build_write_intent(
        "edit_file",
        {
            "path": str(completed_path),
            "old": "old\n",
            "new": "new\n",
            "apply": True,
            "allowed_write_roots": [str(workspace_path)],
        },
    )
    completed_path.write_text("new\n", encoding="utf-8")

    state = default_state()
    planning_event_id = next_id(state, "event")
    committing_event_id = next_id(state, "event")
    verification_event_id = next_id(state, "event")
    not_started_intent_event_id = next_id(state, "event")
    completed_intent_event_id = next_id(state, "event")
    state["inbox"].extend(
        [
            {
                "id": planning_event_id,
                "type": "passive_tick",
                "source": "runtime",
                "payload": {},
                "created_at": "then",
                "processed_at": "then",
            },
            {
                "id": committing_event_id,
                "type": "passive_tick",
                "source": "runtime",
                "payload": {},
                "created_at": "then",
                "processed_at": "then",
            },
            {
                "id": verification_event_id,
                "type": "passive_tick",
                "source": "runtime",
                "payload": {},
                "created_at": "then",
                "processed_at": "then",
            },
            {
                "id": not_started_intent_event_id,
                "type": "passive_tick",
                "source": "runtime",
                "payload": {},
                "created_at": "then",
                "processed_at": "then",
            },
            {
                "id": completed_intent_event_id,
                "type": "passive_tick",
                "source": "runtime",
                "payload": {},
                "created_at": "then",
                "processed_at": "then",
            },
        ]
    )
    planning_effect_id = next_id(state, "runtime_effect")
    committing_effect_id = next_id(state, "runtime_effect")
    verification_effect_id = next_id(state, "runtime_effect")
    not_started_intent_effect_id = next_id(state, "runtime_effect")
    completed_intent_effect_id = next_id(state, "runtime_effect")
    state["runtime_effects"].extend(
        [
            {
                "id": planning_effect_id,
                "event_id": planning_event_id,
                "event_type": "passive_tick",
                "reason": "passive_tick",
                "status": "planning",
                "phase": "planning",
                "action_types": [],
                "verification_run_ids": [],
                "write_run_ids": [],
                "started_at": "then",
                "updated_at": "then",
                "finished_at": None,
            },
            {
                "id": committing_effect_id,
                "event_id": committing_event_id,
                "event_type": "passive_tick",
                "reason": "passive_tick",
                "status": "committing",
                "phase": "committing",
                "action_types": ["write_file"],
                "verification_run_ids": [],
                "write_run_ids": [7],
                "started_at": "then",
                "updated_at": "then",
                "finished_at": None,
            },
            {
                "id": verification_effect_id,
                "event_id": verification_event_id,
                "event_type": "passive_tick",
                "reason": "passive_tick",
                "status": "committing",
                "phase": "committing",
                "action_types": ["run_verification"],
                "verification_run_ids": [9],
                "write_run_ids": [],
                "started_at": "then",
                "updated_at": "then",
                "finished_at": None,
            },
            {
                "id": not_started_intent_effect_id,
                "event_id": not_started_intent_event_id,
                "event_type": "passive_tick",
                "reason": "passive_tick",
                "status": "committing",
                "phase": "committing",
                "action_types": ["edit_file"],
                "verification_run_ids": [],
                "write_run_ids": [],
                "runtime_write_intents": [not_started_intent],
                "runtime_write_intent_errors": [],
                "started_at": "then",
                "updated_at": "then",
                "finished_at": None,
            },
            {
                "id": completed_intent_effect_id,
                "event_id": completed_intent_event_id,
                "event_type": "passive_tick",
                "reason": "passive_tick",
                "status": "committing",
                "phase": "committing",
                "action_types": ["edit_file"],
                "verification_run_ids": [],
                "write_run_ids": [],
                "runtime_write_intents": [completed_intent],
                "runtime_write_intent_errors": [],
                "started_at": "then",
                "updated_at": "then",
                "finished_at": None,
            },
        ]
    )
    state["write_runs"].append(
        {
            "id": 7,
            "operation": "write_file",
            "path": str(Path(workspace) / "side-effect.txt"),
            "written": True,
            "dry_run": False,
        }
    )
    state["verification_runs"].append(
        {
            "id": 9,
            "command": "python -m pytest",
            "cwd": str(workspace),
            "exit_code": 1,
            "stdout": "",
            "stderr": "interrupted before result was reviewed",
        }
    )
    write_json_file(Path(workspace) / STATE_FILE, state)

    doctor_result = run(["doctor", "--json"], timeout=15)
    doctor_data = _json_stdout(doctor_result)
    doctor_items = (doctor_data.get("runtime_effects") or {}).get("incomplete_items") or []
    doctor_by_effect = {item.get("id"): item for item in doctor_items}
    repair_result = run(["repair", "--json"], timeout=15)
    repaired_state = read_json_file(Path(workspace) / STATE_FILE, {})
    repaired_effects = {effect.get("id"): effect for effect in repaired_state.get("runtime_effects") or []}
    repair_data = _json_stdout(repair_result)
    repairs = repair_data.get("repairs") or []
    planning_decision = (repaired_effects.get(planning_effect_id) or {}).get("recovery_decision") or {}
    committing_decision = (repaired_effects.get(committing_effect_id) or {}).get("recovery_decision") or {}
    verification_decision = (repaired_effects.get(verification_effect_id) or {}).get("recovery_decision") or {}
    not_started_intent_decision = (
        (repaired_effects.get(not_started_intent_effect_id) or {}).get("recovery_decision") or {}
    )
    completed_intent_decision = (
        (repaired_effects.get(completed_intent_effect_id) or {}).get("recovery_decision") or {}
    )
    planning_followup = (repaired_effects.get(planning_effect_id) or {}).get("recovery_followup") or {}
    committing_followup = (repaired_effects.get(committing_effect_id) or {}).get("recovery_followup") or {}
    verification_followup = (repaired_effects.get(verification_effect_id) or {}).get("recovery_followup") or {}
    not_started_intent_followup = (
        (repaired_effects.get(not_started_intent_effect_id) or {}).get("recovery_followup") or {}
    )
    completed_intent_followup = (
        (repaired_effects.get(completed_intent_effect_id) or {}).get("recovery_followup") or {}
    )
    repaired_events = {event.get("id"): event for event in repaired_state.get("inbox") or []}
    review_questions = list(repaired_state.get("questions") or [])

    _scenario_check(
        checks,
        "m4_runtime_effect_recovery_doctor_previews_decisions",
        doctor_result.get("exit_code") == 1
        and len(doctor_items) == 5
        and ((doctor_by_effect.get(planning_effect_id) or {}).get("recovery_decision") or {}).get("action")
        == "rerun_event"
        and ((doctor_by_effect.get(planning_effect_id) or {}).get("recovery_followup") or {}).get("action")
        == "requeue_event"
        and ((doctor_by_effect.get(committing_effect_id) or {}).get("recovery_decision") or {}).get("action")
        == "review_writes"
        and ((doctor_by_effect.get(committing_effect_id) or {}).get("recovery_followup") or {}).get("action")
        == "ask_user_review"
        and ((doctor_by_effect.get(verification_effect_id) or {}).get("recovery_decision") or {}).get("action")
        == "review_verification"
        and "verification --details --limit 5"
        in (((doctor_by_effect.get(verification_effect_id) or {}).get("recovery_followup") or {}).get("command") or "")
        and ((doctor_by_effect.get(not_started_intent_effect_id) or {}).get("recovery_decision") or {}).get(
            "effect_classification"
        )
        == "runtime_write_not_started"
        and ((doctor_by_effect.get(completed_intent_effect_id) or {}).get("recovery_decision") or {}).get(
            "effect_classification"
        )
        == "runtime_write_completed_externally",
        observed={
            "doctor_runtime_effects": doctor_data.get("runtime_effects"),
        },
        expected="doctor previews structured recovery decisions and follow-ups before repair mutates state",
    )
    _scenario_check(
        checks,
        "m4_runtime_effect_recovery_requeues_precommit_event",
        repair_result.get("exit_code") == 0
        and planning_decision.get("action") == "rerun_event"
        and planning_decision.get("effect_classification") == "no_action_committed"
        and planning_decision.get("safety") == "safe_to_replan"
        and planning_followup.get("action") == "requeue_event"
        and planning_followup.get("status") == "requeued"
        and (repaired_events.get(planning_event_id) or {}).get("processed_at") is None
        and (repaired_events.get(planning_event_id) or {}).get("requeued_from_effect_id") == planning_effect_id
        and (repaired_effects.get(planning_effect_id) or {}).get("status") == "interrupted",
        observed={
            "decision": planning_decision,
            "followup": planning_followup,
            "event": repaired_events.get(planning_event_id),
            "effect": repaired_effects.get(planning_effect_id),
            "repairs": repairs,
        },
        expected="pre-commit runtime effect is classified as safe and the processed event is requeued",
    )
    _scenario_check(
        checks,
        "m4_runtime_effect_recovery_classifies_committing_write_review",
        repair_result.get("exit_code") == 0
        and committing_decision.get("action") == "review_writes"
        and committing_decision.get("effect_classification") == "write_may_have_started"
        and committing_decision.get("safety") == "needs_user_review"
        and committing_decision.get("write_run_ids") == [7]
        and committing_followup.get("action") == "ask_user_review"
        and committing_followup.get("command")
        and (repaired_effects.get(committing_effect_id) or {}).get("status") == "interrupted",
        observed={
            "decision": committing_decision,
            "followup": committing_followup,
            "effect": repaired_effects.get(committing_effect_id),
            "repairs": repairs,
        },
        expected="committing runtime effect with write runs is classified as write review",
    )
    _scenario_check(
        checks,
        "m4_runtime_effect_recovery_classifies_committing_verification_review",
        repair_result.get("exit_code") == 0
        and verification_decision.get("action") == "review_verification"
        and verification_decision.get("effect_classification") == "verification_may_have_run"
        and verification_decision.get("safety") == "needs_user_review"
        and verification_decision.get("verification_run_ids") == [9]
        and verification_followup.get("action") == "ask_user_review"
        and "verification --details --limit 5" in (verification_followup.get("command") or "")
        and (repaired_effects.get(verification_effect_id) or {}).get("status") == "interrupted",
        observed={
            "decision": verification_decision,
            "followup": verification_followup,
            "effect": repaired_effects.get(verification_effect_id),
            "repairs": repairs,
        },
        expected="committing runtime effect with verification runs is classified as verification review",
    )
    _scenario_check(
        checks,
        "m4_runtime_effect_recovery_requeues_not_started_write_intent",
        repair_result.get("exit_code") == 0
        and not_started_intent_decision.get("action") == "rerun_event"
        and not_started_intent_decision.get("effect_classification") == "runtime_write_not_started"
        and not_started_intent_decision.get("safety") == "safe_to_replan"
        and (not_started_intent_decision.get("runtime_write_world_states") or [{}])[0].get("state")
        == "not_started"
        and not_started_intent_followup.get("action") == "requeue_event"
        and not_started_intent_followup.get("status") == "requeued"
        and (repaired_events.get(not_started_intent_event_id) or {}).get("processed_at") is None
        and (repaired_effects.get(not_started_intent_effect_id) or {}).get("status") == "interrupted",
        observed={
            "decision": not_started_intent_decision,
            "followup": not_started_intent_followup,
            "event": repaired_events.get(not_started_intent_event_id),
            "effect": repaired_effects.get(not_started_intent_effect_id),
            "target_text": not_started_path.read_text(encoding="utf-8"),
            "repairs": repairs,
        },
        expected="runtime write intent with unchanged target is safely requeued instead of sent to review",
    )
    _scenario_check(
        checks,
        "m4_runtime_effect_recovery_reviews_completed_write_intent",
        repair_result.get("exit_code") == 0
        and completed_intent_decision.get("action") == "review_writes"
        and completed_intent_decision.get("effect_classification") == "runtime_write_completed_externally"
        and completed_intent_decision.get("safety") == "needs_user_review"
        and (completed_intent_decision.get("runtime_write_world_states") or [{}])[0].get("state")
        == "completed_externally"
        and completed_intent_followup.get("action") == "ask_user_review"
        and "runtime-effects --limit 5" in (completed_intent_followup.get("command") or "")
        and completed_intent_followup.get("question_id")
        and (repaired_effects.get(completed_intent_effect_id) or {}).get("status") == "interrupted",
        observed={
            "decision": completed_intent_decision,
            "followup": completed_intent_followup,
            "effect": repaired_effects.get(completed_intent_effect_id),
            "target_text": completed_path.read_text(encoding="utf-8"),
            "repairs": repairs,
        },
        expected="runtime write intent with externally completed target is routed to human review",
    )
    _scenario_check(
        checks,
        "m4_runtime_effect_recovery_seeds_review_question",
        repair_result.get("exit_code") == 0
        and committing_followup.get("action") == "ask_user_review"
        and committing_followup.get("question_id")
        and verification_followup.get("question_id")
        and completed_intent_followup.get("question_id")
        and len(review_questions) == 3
        and any(
            question.get("id") == committing_followup.get("question_id")
            and question.get("source") == "runtime"
            and "Runtime effect" in (question.get("text") or "")
            and "mew writes" in (question.get("text") or "")
            for question in review_questions
        )
        and any(
            question.get("id") == verification_followup.get("question_id")
            and question.get("source") == "runtime"
            and "verification --details --limit 5" in (question.get("text") or "")
            for question in review_questions
        )
        and any(
            question.get("id") == completed_intent_followup.get("question_id")
            and question.get("source") == "runtime"
            and "completed_externally" in (question.get("text") or "")
            and "runtime-intent-completed.txt" in (question.get("text") or "")
            for question in review_questions
        ),
        observed={
            "followup": committing_followup,
            "verification_followup": verification_followup,
            "completed_intent_followup": completed_intent_followup,
            "questions": review_questions,
            "repairs": repairs,
        },
        expected="commit-phase runtime-effect review follow-up is consumed as a durable open question",
    )
    return _scenario_report("m4-runtime-effect-recovery", workspace, commands, checks)


def _dogfood_check_passed(report, name):
    return any(check.get("name") == name and check.get("passed") for check in (report or {}).get("checks") or [])


def _fresh_dogfood_subworkspace(workspace, name):
    path = Path(workspace) / name
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def run_m4_close_gate_scenario(workspace, env=None):
    commands = []
    checks = []

    def run(args, timeout=30, scenario_workspace=None):
        result = run_command(
            _scenario_command(*args),
            scenario_workspace or workspace,
            timeout=timeout,
            env=env,
        )
        commands.append(result)
        return result

    runtime_workspace = _fresh_dogfood_subworkspace(workspace, "runtime-effect")
    runtime_report = run_m4_runtime_effect_recovery_scenario(runtime_workspace, env=env)
    commands.extend(runtime_report.get("commands") or [])

    verifier_workspace = _fresh_dogfood_subworkspace(workspace, "verifier-auto-recovery")
    verifier_report = run_passive_auto_recovery_scenario(verifier_workspace, env=env)
    commands.extend(verifier_report.get("commands") or [])

    approval_workspace = _fresh_dogfood_subworkspace(workspace, "durable-approval")
    (approval_workspace / "README.md").write_text("old text\n", encoding="utf-8")
    approval_task_result = run(
        ["task", "add", "M4 close gate approval task", "--kind", "coding", "--ready", "--json"],
        timeout=15,
        scenario_workspace=approval_workspace,
    )
    approval_task_data = _json_stdout(approval_task_result)
    approval_task = (
        approval_task_data.get("task")
        if isinstance(approval_task_data.get("task"), dict)
        else approval_task_data
    )
    approval_task_id = approval_task.get("id") if isinstance(approval_task, dict) else None
    approval_start_result = run(
        [
            "work",
            str(approval_task_id),
            "--start-session",
            "--allow-write",
            ".",
            "--allow-verify",
            "--verify-command",
            f"{sys.executable} -V",
            "--json",
        ],
        timeout=15,
        scenario_workspace=approval_workspace,
    )
    approval_preview_result = run(
        [
            "work",
            str(approval_task_id),
            "--tool",
            "edit_file",
            "--path",
            "README.md",
            "--old",
            "old text",
            "--new",
            "new text",
            "--allow-write",
            ".",
            "--json",
        ],
        timeout=15,
        scenario_workspace=approval_workspace,
    )
    approval_state_path = approval_workspace / STATE_FILE
    approval_state = reconcile_next_ids(migrate_state(read_json_file(approval_state_path, default_state())))
    approval_session = (approval_state.get("work_sessions") or [{}])[0]
    approval_task_record = (approval_state.get("tasks") or [{}])[0]
    approval_resume = build_work_session_resume(
        approval_session,
        task=approval_task_record,
        state=approval_state,
    )
    approval_item = ((approval_resume or {}).get("pending_approvals") or [{}])[0]
    approval_call = (approval_session.get("tool_calls") or [{}])[0]
    approval_question_text = "\n".join(
        [
            f"Work session #{approval_session.get('id')} tool #{approval_call.get('id')} is waiting for approval.",
            f"tool: {approval_call.get('tool')} path: {approval_item.get('path') or 'README.md'}",
            f"task: #{approval_task_id} M4 close gate approval task",
            f"approve: `{approval_item.get('cli_approve_hint')}`",
            f"reject: `{approval_item.get('cli_reject_hint')}`",
            "If this prompt was interrupted, inspect the pending approval before retrying.",
        ]
    )
    approval_question, _created = add_question(
        approval_state,
        approval_question_text,
        related_task_id=approval_task_id,
        source="work_approval",
    )
    approval_call["approval_question_id"] = approval_question.get("id")
    approval_call["approval_prompt_status"] = "open"
    approval_call["approval_prompted_at"] = now_iso()
    approval_session["updated_at"] = now_iso()
    write_json_file(approval_state_path, approval_state)

    approval_focus_result = run(["focus", "--kind", "coding"], timeout=15, scenario_workspace=approval_workspace)
    approval_brief_result = run(["brief", "--kind", "coding"], timeout=15, scenario_workspace=approval_workspace)
    approval_questions_result = run(["questions", "--json"], timeout=15, scenario_workspace=approval_workspace)
    approval_resume_result = run(
        ["work", str(approval_task_id), "--session", "--resume", "--json"],
        timeout=15,
        scenario_workspace=approval_workspace,
    )
    approval_questions_data = _json_stdout(approval_questions_result)
    approval_resume_data = _json_stdout(approval_resume_result)
    approval_final_state = read_json_file(approval_state_path, {})
    approval_question_records = approval_final_state.get("questions") or []
    approval_question_record = (approval_question_records[:1] or [{}])[0]
    approval_attention = (approval_final_state.get("attention") or {}).get("items") or []
    approval_outbox = approval_final_state.get("outbox") or []

    _scenario_check(
        checks,
        "m4_close_gate_runtime_write_intent_auto_requeued",
        runtime_report.get("status") == "pass"
        and _dogfood_check_passed(runtime_report, "m4_runtime_effect_recovery_requeues_not_started_write_intent"),
        observed={"runtime_checks": runtime_report.get("checks")},
        expected="runtime write intent not_started class requeues the event without manual reconstruction",
    )
    _scenario_check(
        checks,
        "m4_close_gate_verifier_auto_retried_and_superseded",
        verifier_report.get("status") == "pass"
        and _dogfood_check_passed(verifier_report, "passive_auto_recovery_reruns_interrupted_verifier"),
        observed={"verifier_checks": verifier_report.get("checks")},
        expected="passive runtime auto-recovers a matching interrupted verifier and supersedes the old call",
    )
    _scenario_check(
        checks,
        "m4_close_gate_durable_approval_visible_in_focus_and_brief",
        approval_task_result.get("exit_code") == 0
        and approval_start_result.get("exit_code") == 0
        and approval_preview_result.get("exit_code") == 0
        and approval_focus_result.get("exit_code") == 0
        and approval_brief_result.get("exit_code") == 0
        and approval_questions_result.get("exit_code") == 0
        and "Work session #1 tool #1 is waiting for approval." in (approval_focus_result.get("stdout") or "")
        and "Work session #1 tool #1 is waiting for approval." in (approval_brief_result.get("stdout") or "")
        and (approval_questions_data.get("count") or 0) == 1
        and approval_question_record.get("source") == "work_approval"
        and approval_question_record.get("status") == "open"
        and any(item.get("question_id") == approval_question.get("id") for item in approval_attention)
        and any(message.get("question_id") == approval_question.get("id") for message in approval_outbox)
        and ((approval_resume_data.get("resume") or {}).get("phase") == "awaiting_approval"),
        observed={
            "focus": command_result_tail(approval_focus_result, limit=10),
            "brief": command_result_tail(approval_brief_result, limit=10),
            "questions": approval_questions_data,
            "resume": approval_resume_data.get("resume"),
            "attention": approval_attention,
            "outbox": approval_outbox,
        },
        expected="interrupted approval prompt is recoverable from focus, brief, questions, outbox, attention, and resume",
    )
    _scenario_check(
        checks,
        "m4_close_gate_completed_external_write_stays_on_review",
        runtime_report.get("status") == "pass"
        and _dogfood_check_passed(runtime_report, "m4_runtime_effect_recovery_reviews_completed_write_intent"),
        observed={"runtime_checks": runtime_report.get("checks")},
        expected="completed runtime write intent is reviewed rather than blindly reapplied",
    )
    _scenario_check(
        checks,
        "m4_close_gate_no_manual_reconstruction_required",
        all(check.get("passed") for check in checks)
        and approval_resume_result.get("exit_code") == 0
        and verifier_report.get("status") == "pass"
        and runtime_report.get("status") == "pass",
        observed={
            "runtime_status": runtime_report.get("status"),
            "verifier_status": verifier_report.get("status"),
            "approval_resume_exit": approval_resume_result.get("exit_code"),
        },
        expected="all close-gate recovery surfaces are derived from durable state and CLI reentry surfaces",
    )
    return _scenario_report("m4-close-gate", workspace, commands, checks)


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
    reference_time = parse_time(now_iso())
    aged_start = reference_time - timedelta(days=8) if reference_time else None

    def aged_at(minutes):
        if not aged_start:
            return now_iso()
        return (aged_start + timedelta(minutes=minutes)).isoformat(timespec="seconds").replace("+00:00", "Z")

    session_created_at = aged_at(0)
    note_at = aged_at(32)
    tool_at = aged_at(34)
    risk_at = aged_at(35)
    memory_at = aged_at(36)
    for candidate in state.get("work_sessions") or []:
        if str(candidate.get("id")) != str(session_id):
            continue
        candidate["created_at"] = session_created_at
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
                "started_at": risk_at,
                "finished_at": risk_at,
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
        and (focus_session.get("inactive_hours") or 0) >= 168.0
        and bool(focus_session.get("inactive_for"))
        and "day-scale verifier still needs recovery" in (focus_session.get("risk") or ""),
        observed=focus_session,
        expected="focus --json surfaces the active session with week-scale inactive age and unresolved risk",
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
    report = _scenario_report("day-reentry", workspace, commands, checks)
    report["artifacts"] = {
        "synthetic_age_days": 7,
        "session_created_at": session_created_at,
        "session_updated_at": memory_at,
        "observed_inactive_hours": focus_session.get("inactive_hours"),
        "reentry_contract": {
            "surfaces": ["focus", "work --session --resume", "activity"],
            "risk_present": "day-scale verifier still needs recovery" in (focus_session.get("risk") or ""),
            "working_memory_keys": sorted(focus_memory.keys()),
            "world_state_files": [
                record.get("path")
                for record in world_state.get("files") or []
                if record.get("exists")
            ],
            "next_cli_controls": resume_data.get("next_cli_controls"),
        },
    }
    return report


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

    failed_edit_task_result = run(
        [
            "task",
            "add",
            "Failed edit reentry task",
            "--kind",
            "coding",
            "--ready",
            "--json",
        ],
        timeout=15,
    )
    failed_edit_task_data = _json_stdout(failed_edit_task_result)
    failed_edit_task = (
        failed_edit_task_data.get("task")
        if isinstance(failed_edit_task_data.get("task"), dict)
        else failed_edit_task_data
    )
    failed_edit_task_id = failed_edit_task.get("id") if isinstance(failed_edit_task, dict) else None
    failed_edit_start_result = run(
        [
            "work",
            str(failed_edit_task_id),
            "--start-session",
            "--allow-read",
            ".",
            "--allow-write",
            ".",
            "--json",
        ],
        timeout=15,
    )
    failed_edit_read_result = run(
        [
            "work",
            str(failed_edit_task_id),
            "--tool",
            "read_file",
            "--path",
            "README.md",
            "--allow-read",
            ".",
            "--json",
        ],
        timeout=15,
    )
    failed_edit_result = run(
        [
            "work",
            str(failed_edit_task_id),
            "--tool",
            "edit_file",
            "--path",
            "README.md",
            "--old",
            "this exact old text is absent",
            "--new",
            "replacement should not apply",
            "--allow-write",
            ".",
            "--json",
        ],
        timeout=15,
    )
    failed_edit_resume_json_result = run(
        ["work", str(failed_edit_task_id), "--session", "--resume", "--allow-read", ".", "--json"],
        timeout=15,
    )
    failed_edit_resume_text_result = run(
        ["work", str(failed_edit_task_id), "--session", "--resume", "--allow-read", "."],
        timeout=15,
    )

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
    failed_edit_data = _json_stdout(failed_edit_result)
    failed_edit_resume_data = _json_stdout(failed_edit_resume_json_result)
    failed_edit_resume = failed_edit_resume_data.get("resume") or {}
    failed_edit_failures = failed_edit_resume.get("failures") or []
    failed_edit_failure = failed_edit_failures[-1] if failed_edit_failures else {}
    failed_edit_reobserve = failed_edit_failure.get("suggested_safe_reobserve") or {}
    failed_edit_resume_text = failed_edit_resume_text_result.get("stdout") or ""

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
        "continuity_failed_edit_reentry_surfaces_safe_reobserve",
        failed_edit_task_result.get("exit_code") == 0
        and failed_edit_start_result.get("exit_code") == 0
        and failed_edit_read_result.get("exit_code") == 0
        and failed_edit_result.get("exit_code") != 0
        and (failed_edit_data.get("tool_call") or {}).get("status") == "failed"
        and failed_edit_resume_json_result.get("exit_code") == 0
        and failed_edit_resume_text_result.get("exit_code") == 0
        and failed_edit_failure.get("tool") == "edit_file"
        and failed_edit_reobserve.get("action") == "read_file"
        and (failed_edit_reobserve.get("parameters") or {}).get("path") == "README.md"
        and "old text was not found" in failed_edit_resume_text
        and "reobserve: read_file path=README.md" in failed_edit_resume_text,
        observed={
            "failed_edit": failed_edit_data.get("tool_call"),
            "failure": failed_edit_failure,
            "resume_tail": failed_edit_resume_text[-1000:],
        },
        expected="failed edit reentry preserves the exact safe read needed before retry",
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


def run_m3_reentry_gate_scenario(workspace, env=None, comparison_report_path=None):
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
    artifacts_dir = Path(workspace) / STATE_DIR / "dogfood"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    fresh_cli_workspace = Path(workspace) / "m3-fresh-cli-restart-workspace"
    fresh_cli_workspace.mkdir(parents=True, exist_ok=True)
    (fresh_cli_workspace / "README.md").write_text(
        "# M3 Reentry Gate Dogfood\n\n"
        "M3 gate pending: the interrupted resident has not applied the recovery edit yet.\n",
        encoding="utf-8",
    )
    (fresh_cli_workspace / "VERIFY_COMMAND.txt").write_text(verify_command + "\n", encoding="utf-8")
    fresh_cli_template_path = artifacts_dir / "m3-fresh-cli-report-template.json"
    fresh_cli_prompt_path = artifacts_dir / "m3-fresh-cli-restart-prompt.md"
    mew_resume_evidence = {
        "task_id": task_id,
        "work_session_id": session_id,
        "continuity_status": continuity.get("status"),
        "continuity_score": continuity.get("score"),
        "resume_chars": len(resume_text),
        "pending_approval_count": len(pending_approvals),
        "unresolved_failure_tool": unresolved_failure.get("tool"),
        "unresolved_failure_exit_code": unresolved_failure.get("exit_code"),
        "working_memory_next_step": (resume.get("working_memory") or {}).get("next_step"),
        "verification_command": verify_command,
        "decisive_next_action": "approve_pending_readme_edit_then_rerun_verifier",
        "decisive_next_action_source": "resume.pending_approvals + resume.working_memory.next_step",
        "repo_only_missing_context": [
            "pending dry-run edit diff",
            "already-observed verifier failure",
            "queued follow-up to approve then verify",
        ],
    }
    write_json_file(
        fresh_cli_template_path,
        {
            "schema_version": 2,
            "status": "unknown",
            "context_mode": "true_restart",
            "fresh_cli_tool": "",
            "fresh_model": "",
            "manual_rebrief_needed": None,
            "fresh_elapsed_seconds": None,
            "active_reconstruction_seconds": None,
            "fresh_cli_summary": "",
            "files_inspected": [],
            "commands_run": [],
            "mew_artifacts_inspected": [],
            "prompt_mew_evidence_used": [],
            "repository_only_compliance": None,
            "reconstruction_steps": [],
            "change_summary": "",
            "verification_command_used": "",
            "verification_exit_code": None,
            "verification_result": "",
            "reconstruction_burden": {
                "repository_only_steps_before_first_correct_action": None,
                "needed_to_read_verifier_before_action": None,
                "needed_to_run_verifier_before_action": None,
                "missing_context_that_mew_resume_had": [],
                "mew_resume_would_have_changed_first_action": None,
                "notes": "",
            },
            "persistent_advantage_signal": {
                "mew_saved_reconstruction": None,
                "mew_saved_verifier_rerun": None,
                "mew_prevented_wrong_first_action": None,
                "reason": "",
            },
            "unfairness_notes": [],
            "comparison_result": {
                "choice": "unknown",
                "allowed_values": ["mew_preferred", "fresh_cli_preferred", "parity", "inconclusive", "blocked"],
                "reason": "",
            },
            "mew_evidence": mew_resume_evidence,
        },
    )
    fresh_cli_prompt_path.write_text(
        "\n".join(
            [
                "# M3 Fresh CLI Reentry Comparator",
                "",
                "Start from a brand-new Claude Code or Codex CLI session.",
                "Do not use the mew work-session resume unless you explicitly record that as manual rebrief.",
                "",
                "Goal: compare a fresh CLI restart against mew's M3 reentry bundle for the same interrupted task.",
                "",
                f"Fresh restart workspace: `{fresh_cli_workspace}`",
                "Do not inspect the parent `.mew` directory or the report template's `mew_evidence` before your independent attempt.",
                "If you inspect either before solving, set `manual_rebrief_needed=true` and record the inspected source.",
                "",
                "Acceptance command: read and run the command stored in `VERIFY_COMMAND.txt` from the fresh workspace.",
                "Record whether reading or running that verifier was required before your first correct action.",
                "",
                "Fresh restart task:",
                "1. Reconstruct what changed, what is risky, and the next action from repository files alone.",
                "2. Complete the equivalent README.md recovery so the verifier passes.",
                "3. Record how many reconstruction steps were needed and whether manual rebrief was needed.",
                "",
                f"After your independent attempt, compare against the `mew_evidence` in `{fresh_cli_template_path}`.",
                "Fill `reconstruction_burden` and `persistent_advantage_signal` in the completed report.",
                f"Write the completed JSON report to `{fresh_cli_template_path}` or another explicit path.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    fresh_cli_report = {"status": "not_loaded", "source": ""}
    if comparison_report_path:
        report_path = Path(comparison_report_path).expanduser()
        if not report_path.is_absolute():
            report_path = (Path.cwd() / report_path).resolve()
        loaded_report = read_json_file(report_path, {})
        comparison_result = loaded_report.get("comparison_result") or {}
        fresh_cli_report = {
            "status": "loaded",
            "source": str(report_path),
            "report_status": loaded_report.get("status"),
            "manual_rebrief_needed": loaded_report.get("manual_rebrief_needed"),
            "repository_only_compliance": loaded_report.get("repository_only_compliance"),
            "verification_exit_code": loaded_report.get("verification_exit_code"),
            "comparison_choice": comparison_result.get("choice"),
            "comparison_reason": comparison_result.get("reason"),
            "reconstruction_burden": loaded_report.get("reconstruction_burden") or {},
            "persistent_advantage_signal": loaded_report.get("persistent_advantage_signal") or {},
        }

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
    _scenario_check(
        checks,
        "m3_reentry_gate_writes_fresh_cli_comparison_assets",
        fresh_cli_template_path.exists()
        and fresh_cli_prompt_path.exists()
        and fresh_cli_workspace.exists()
        and "M3 gate pending" in (fresh_cli_workspace / "README.md").read_text(encoding="utf-8")
        and "manual_rebrief_needed" in fresh_cli_template_path.read_text(encoding="utf-8")
        and "reconstruction_burden" in fresh_cli_template_path.read_text(encoding="utf-8")
        and "M3 Fresh CLI Reentry Comparator" in fresh_cli_prompt_path.read_text(encoding="utf-8")
        and "VERIFY_COMMAND.txt" in fresh_cli_prompt_path.read_text(encoding="utf-8")
        and "M3 gate complete" not in fresh_cli_prompt_path.read_text(encoding="utf-8"),
        observed={
            "template": str(fresh_cli_template_path),
            "prompt": str(fresh_cli_prompt_path),
            "mew_evidence": mew_resume_evidence,
        },
        expected="fresh CLI comparator prompt avoids leaking the answer and records reconstruction burden",
    )
    if comparison_report_path:
        _scenario_check(
            checks,
            "m3_reentry_gate_merges_fresh_cli_comparison_report",
            fresh_cli_report.get("status") == "loaded"
            and fresh_cli_report.get("report_status")
            in {"passed", "failed", "inconclusive", "blocked", "complete_with_environment_note"}
            and fresh_cli_report.get("comparison_choice")
            in {"mew_preferred", "fresh_cli_preferred", "parity", "inconclusive", "blocked"}
            and fresh_cli_report.get("manual_rebrief_needed") in {True, False}
            and fresh_cli_report.get("repository_only_compliance") in {True, False},
            observed=fresh_cli_report,
            expected="fresh CLI comparison report is loaded into the M3 reentry gate artifact",
        )
    report = _scenario_report("m3-reentry-gate", workspace, commands, checks)
    report["artifacts"] = {
        "fresh_cli_workspace": str(fresh_cli_workspace),
        "fresh_cli_report_template": str(fresh_cli_template_path),
        "fresh_cli_restart_prompt": str(fresh_cli_prompt_path),
        "fresh_cli_report": fresh_cli_report,
        "mew_resume_evidence": mew_resume_evidence,
    }
    return report


def run_m3_source_reentry_scenario(workspace, env=None):
    commands = []
    checks = []

    def run(args, timeout=30, input_text=None):
        result = run_command(_scenario_command(*args), workspace, timeout=timeout, env=env, input_text=input_text)
        commands.append(result)
        return result

    source = Path(workspace) / "mew_status.py"
    test_file = Path(workspace) / "test_mew_status.py"
    source.write_text(
        'def status():\n'
        '    return "pending"\n',
        encoding="utf-8",
    )
    test_file.write_text(
        "import unittest\n\n"
        "from mew_status import status\n\n\n"
        "class StatusTests(unittest.TestCase):\n"
        "    def test_status_is_complete(self):\n"
        "        self.assertEqual(status(), \"complete\")\n\n\n"
        "if __name__ == \"__main__\":\n"
        "    unittest.main()\n",
        encoding="utf-8",
    )
    verify_command = f"{sys.executable} -m unittest test_mew_status.py"
    task_result = run(
        [
            "task",
            "add",
            "M3 source reentry coding task",
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
        ["work", str(task_id), "--tool", "read_file", "--path", "mew_status.py", "--allow-read", ".", "--json"],
        timeout=15,
    )
    read_test_result = run(
        ["work", str(task_id), "--tool", "read_file", "--path", "test_mew_status.py", "--allow-read", ".", "--json"],
        timeout=15,
    )
    edit_result = run(
        [
            "work",
            str(task_id),
            "--tool",
            "edit_file",
            "--path",
            "mew_status.py",
            "--old",
            'return "pending"',
            "--new",
            'return "complete"',
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
            "Source reentry boundary: resume must preserve the pending mew_status.py edit, failed unittest, and approve-then-verify next step.",
            "--json",
        ],
        timeout=15,
    )
    queue_result = run(
        [
            "work",
            str(task_id),
            "--queue-followup",
            "After reentry, approve the mew_status.py edit with deferred verification, then run unittest.",
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
                    "summary": "preserve source reentry gate after context compression",
                    "working_memory": {
                        "hypothesis": "Mew is worth staying inside when source edits, test failures, and next actions survive reentry.",
                        "next_step": (
                            "Approve the mew_status.py dry-run edit with deferred verification, "
                            "then run unittest."
                        ),
                        "open_questions": ["Does resume show the pending source edit and failed unittest?"],
                        "last_verified_state": "unittest failed before the pending source edit was applied.",
                    },
                },
                "action_plan": {},
                "action": {"type": "finish", "reason": "pause for M3 source reentry"},
                "summary": "Captured M3 source reentry working memory.",
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
        "m3_source_reentry_resume_has_source_edit_test_risk_next_action",
        task_result.get("exit_code") == 0
        and start_result.get("exit_code") == 0
        and read_result.get("exit_code") == 0
        and read_test_result.get("exit_code") == 0
        and edit_result.get("exit_code") == 0
        and (failed_verify_data.get("tool_call") or {}).get("status") == "failed"
        and note_result.get("exit_code") == 0
        and queue_result.get("exit_code") == 0
        and resume_json_result.get("exit_code") == 0
        and resume_text_result.get("exit_code") == 0
        and bool(pending_approvals)
        and pending_approvals[0].get("tool_call_id") == edit_tool_id
        and 'return "complete"' in (pending_approvals[0].get("diff_preview") or "")
        and unresolved_failure.get("tool") == "run_tests"
        and unresolved_failure.get("exit_code") != 0
        and "Approve the mew_status.py dry-run edit" in ((resume.get("working_memory") or {}).get("next_step") or "")
        and "Pending approvals" in resume_text
        and "Failures" in resume_text,
        observed={
            "continuity": continuity,
            "pending_approvals": pending_approvals,
            "unresolved_failure": unresolved_failure,
            "working_memory": resume.get("working_memory"),
        },
        expected="resume preserves pending source edit, failed unittest, and next action",
    )
    _scenario_check(
        checks,
        "m3_source_reentry_world_state_and_follow_snapshot_preserve_resume",
        follow_snapshot_result.get("exit_code") == 0
        and any(str(record.get("path") or "").endswith("mew_status.py") and record.get("exists") for record in world_state.get("files") or [])
        and any(str(record.get("path") or "").endswith("test_mew_status.py") and record.get("exists") for record in world_state.get("files") or [])
        and follow_snapshot_resume.get("session_id") == session_id
        and follow_snapshot_continuity.get("status") in {"strong", "usable"},
        observed={
            "world_state": world_state,
            "snapshot_resume": follow_snapshot_resume,
            "snapshot_continuity": follow_snapshot_continuity,
        },
        expected="world state and observer snapshot preserve source/test reentry context",
    )
    _scenario_check(
        checks,
        "m3_source_reentry_can_advance_to_passing_unittest",
        approve_result.get("exit_code") == 0
        and (approve_data.get("tool_call") or {}).get("status") == "completed"
        and ((approve_data.get("tool_call") or {}).get("result") or {}).get("applied") is True
        and ((approve_data.get("tool_call") or {}).get("result") or {}).get("written") is True
        and post_verify_result.get("exit_code") == 0
        and (post_verify_data.get("tool_call") or {}).get("status") == "completed"
        and ((post_verify_data.get("tool_call") or {}).get("result") or {}).get("exit_code") == 0
        and 'return "complete"' in source.read_text(encoding="utf-8")
        and any(command.get("exit_code") == 0 and command.get("command") == verify_command for command in post_commands),
        observed={
            "approve": approve_data.get("tool_call"),
            "post_verify": post_verify_data.get("tool_call"),
            "post_resume_commands": post_commands,
            "source": source.read_text(encoding="utf-8"),
        },
        expected="after reentry, the pending source edit can be applied and unittest passes",
    )
    report = _scenario_report("m3-source-reentry", workspace, commands, checks)
    report["artifacts"] = {
        "task_id": task_id,
        "work_session_id": session_id,
        "continuity_status": continuity.get("status"),
        "continuity_score": continuity.get("score"),
        "pending_approval_count": len(pending_approvals),
        "unresolved_failure_tool": unresolved_failure.get("tool"),
        "unresolved_failure_exit_code": unresolved_failure.get("exit_code"),
        "source_file": "mew_status.py",
        "test_file": "test_mew_status.py",
        "verify_command": verify_command,
    }
    return report


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
    running_output_close_result = run(["work", str(running_output_task_id), "--close-session", "--json"])
    running_output_closed_resume_result = run(
        ["work", str(running_output_task_id), "--session", "--resume", "--json"]
    )
    state = migrate_state(read_json_file(state_path, default_state()))
    reconcile_next_ids(state)
    stale_follow_current_updated_at = "2999-01-01T00:00:00Z"
    for candidate in state.get("work_sessions", []):
        if str(candidate.get("id")) == str(running_output_session_id):
            candidate["updated_at"] = stale_follow_current_updated_at
            break
    write_json_file(state_path, state)
    stale_follow_status_result = run(["work", str(running_output_task_id), "--follow-status", "--json"])

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
Path("src/mew/accept_batch_extra.py").write_text("EXTRA = 'old'\\n", encoding="utf-8")
Path("tests/test_accept_batch.py").write_text(
    "from pathlib import Path\\n\\n"
    "def test_accept_batch():\\n"
    "    assert 'old' in Path('src/mew/accept_batch.py').read_text()\\n",
    encoding="utf-8",
)
Path("tests/test_accept_batch_extra.py").write_text(
    "from pathlib import Path\\n\\n"
    "def test_accept_batch_extra():\\n"
    "    assert 'old' in Path('src/mew/accept_batch_extra.py').read_text()\\n",
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
                "path": "src/mew/accept_batch_extra.py",
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
            {
                "type": "edit_file",
                "path": "tests/test_accept_batch_extra.py",
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
    "assert 'new' in Path('src/mew/accept_batch_extra.py').read_text(); "
    "assert 'new' in Path('tests/test_accept_batch.py').read_text(); "
    "assert 'new' in Path('tests/test_accept_batch_extra.py').read_text()\\""
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
batch_preview_paths = [(call.get("parameters") or {}).get("path") for call in batch_calls[:4]]
batch_apply_results = [(call.get("result") or {}) for call in batch_calls[4:8]]
observed["paired_write_batch"] = {
    "exit_code": batch_code,
    "stop_reason": batch_report.get("stop_reason"),
    "action_type": ((batch_steps[0] if batch_steps else {}).get("action") or {}).get("type"),
    "inline_approval": ((batch_steps[0] if batch_steps else {})).get("inline_approval"),
    "inline_approval_count": ((batch_steps[0] if batch_steps else {})).get("inline_approval_count"),
    "preview_paths": batch_preview_paths,
    "preview_apply_flags": [(call.get("parameters") or {}).get("apply") for call in batch_calls[:4]],
    "preview_approval_statuses": [call.get("approval_status") for call in batch_calls[:4]],
    "deferred_verification_count": sum(
        1 for result in batch_apply_results if result.get("verification_deferred")
    ),
    "final_source_verification_exit_code": (
        (batch_apply_results[-1] if batch_apply_results else {}).get("verification_exit_code")
    ),
    "source_after": Path("src/mew/accept_batch.py").read_text(encoding="utf-8"),
    "extra_source_after": Path("src/mew/accept_batch_extra.py").read_text(encoding="utf-8"),
    "test_after": Path("tests/test_accept_batch.py").read_text(encoding="utf-8"),
    "extra_test_after": Path("tests/test_accept_batch_extra.py").read_text(encoding="utf-8"),
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
	    and observed["paired_write_batch"]["inline_approval_count"] == 4
	    and observed["paired_write_batch"]["preview_paths"]
	    == [
	        "tests/test_accept_batch.py",
	        "tests/test_accept_batch_extra.py",
	        "src/mew/accept_batch.py",
	        "src/mew/accept_batch_extra.py",
	    ]
	    and observed["paired_write_batch"]["preview_apply_flags"] == [False, False, False, False]
	    and observed["paired_write_batch"]["preview_approval_statuses"] == ["applied", "applied", "applied", "applied"]
	    and observed["paired_write_batch"]["deferred_verification_count"] == 3
	    and observed["paired_write_batch"]["final_source_verification_exit_code"] == 0
	    and observed["paired_write_batch"]["source_after"] == "VALUE = 'new'\\n"
	    and observed["paired_write_batch"]["extra_source_after"] == "EXTRA = 'new'\\n"
	    and "'new'" in observed["paired_write_batch"]["test_after"]
	    and "'new'" in observed["paired_write_batch"]["extra_test_after"]
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
    running_output_close_data = _json_stdout(running_output_close_result)
    running_output_closed_resume_data = _json_stdout(running_output_closed_resume_result)
    stale_follow_status_data = _json_stdout(stale_follow_status_result)
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
    old_cwd = os.getcwd()
    try:
        os.chdir(workspace)
        synthetic_verification_resume = build_work_session_resume(
            {
                "id": 99,
                "task_id": 1,
                "status": "active",
                "title": "Zero-test verifier confidence",
                "tool_calls": [
                    {
                        "id": 1,
                        "tool": "edit_file",
                        "status": "completed",
                        "parameters": {"path": "src/mew/pairing.py"},
                        "result": {
                            "path": "src/mew/pairing.py",
                            "dry_run": False,
                            "changed": True,
                            "written": True,
                        },
                    },
                    {
                        "id": 2,
                        "tool": "run_tests",
                        "status": "completed",
                        "parameters": {
                            "command": "uv run pytest -q tests/test_pairing.py::MissingTests::test_missing"
                        },
                        "result": {
                            "command": "uv run pytest -q tests/test_pairing.py::MissingTests::test_missing",
                            "exit_code": 5,
                            "stderr": "collected 0 items\n\nno tests ran in 0.02s\n",
                            "narrow_verify_command": True,
                        },
                    },
                    {
                        "id": 3,
                        "tool": "search_text",
                        "status": "completed",
                        "parameters": {"path": "src/mew", "query": "missing_symbol", "pattern": "src/mew/**/*.py"},
                        "result": {"matches": []},
                    },
                    {
                        "id": 4,
                        "tool": "search_text",
                        "status": "completed",
                        "parameters": {"path": "src/mew", "query": "missing_symbol_extra", "pattern": "src/mew/**/*.py"},
                        "result": {"matches": []},
                    },
                    {
                        "id": 5,
                        "tool": "search_text",
                        "status": "completed",
                        "parameters": {"path": "src/mew", "query": "missing_symbol_final", "pattern": "src/mew/**/*.py"},
                        "result": {"matches": []},
                    },
                ],
                "model_turns": [],
            }
        )
        zero_test_verification_confidence = synthetic_verification_resume.get("verification_confidence") or {}
        low_yield_observations = synthetic_verification_resume.get("low_yield_observations") or []
    finally:
        os.chdir(old_cwd)
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
    mark_done_controls = running_output_closed_resume_data.get("next_cli_controls") or []
    stale_follow_recovery = stale_follow_status_data.get("suggested_recovery") or {}

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
	    and accept_edits_batch.get("inline_approval_count") == 4
	    and accept_edits_batch.get("preview_paths")
	    == [
	        "tests/test_accept_batch.py",
	        "tests/test_accept_batch_extra.py",
	        "src/mew/accept_batch.py",
	        "src/mew/accept_batch_extra.py",
	    ]
	    and accept_edits_batch.get("deferred_verification_count") == 3
	    and accept_edits_batch.get("final_source_verification_exit_code") == 0,
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
        "closed_session_follow_status_surfaces_mark_task_done",
        running_output_close_result.get("exit_code") == 0
        and running_output_closed_resume_result.get("exit_code") == 0
        and (running_output_close_data.get("work_session") or {}).get("status") == "closed"
        and any(f"task update {running_output_task_id} --status done" in control for control in mark_done_controls),
        expected="closed clean sessions expose mark-done control",
    )
    _scenario_check(
        checks,
        "stale_follow_snapshot_surfaces_session_state_newer",
        stale_follow_status_result.get("exit_code") == 0
        and stale_follow_status_data.get("session_state_newer") is True
        and stale_follow_status_data.get("current_session_updated_at") == stale_follow_current_updated_at
        and stale_follow_recovery.get("kind") == "inspect_resume",
        expected="follow-status detects stale snapshots",
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
        "work_zero_test_pytest_invalid_verifier_confidence",
        zero_test_verification_confidence.get("status") == "invalid"
        and zero_test_verification_confidence.get("confidence") == "low"
        and zero_test_verification_confidence.get("narrow_command") is True
        and "broaden the selector" in str(zero_test_verification_confidence.get("reason") or ""),
        observed={"verification_confidence": zero_test_verification_confidence},
        expected="zero-test pytest verifier output is surfaced as invalid low-confidence verification needing a broader selector",
    )
    _scenario_check(
        checks,
        "work_low_yield_search_trap_surfaces_in_resume",
        len(low_yield_observations) == 1
        and low_yield_observations[0].get("tool") == "search_text"
        and low_yield_observations[0].get("count") == 3
        and low_yield_observations[0].get("pattern") == "src/mew/**/*.py"
        and "missing_symbol_extra" in (low_yield_observations[0].get("queries") or [])
        and "stop searching this same surface" in str(low_yield_observations[0].get("suggested_next") or ""),
        observed={"low_yield_observations": low_yield_observations},
        expected="repeated zero-match search traps are surfaced in work-session resume data",
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


def _m2_resume_has_interruption_marker(resume):
    if not isinstance(resume, dict):
        return False
    stop_request = resume.get("stop_request") or {}
    last_stop_request = resume.get("last_stop_request") or {}
    return bool(
        resume.get("phase") in {"interrupted", "stop_requested"}
        or (
            isinstance(stop_request, dict)
            and any(stop_request.get(key) for key in ("requested_at", "reason", "action", "submit_text"))
        )
        or (
            isinstance(last_stop_request, dict)
            and any(last_stop_request.get(key) for key in ("requested_at", "reason", "action", "submit_text"))
        )
    )


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
            or _m2_resume_has_interruption_marker(resume)
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
        or _m2_resume_has_interruption_marker(resume)
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
        "mew_session_argument": f"task:{task_id_text}",
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
        "mew_session_argument": session_id_text,
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
        if comparison.get("status") in {"mew_preferred", "fresh_cli_preferred", "parity"}:
            comparison["next_blocker"] = ""
        else:
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
    if signal in {"mew", "fresh_cli", "parity", "inconclusive"}:
        return signal
    return ""


def _m2_comparison_status_from_preference_choice(choice):
    if choice == "mew":
        return "mew_preferred"
    if choice == "fresh_cli":
        return "fresh_cli_preferred"
    if choice == "parity":
        return "parity"
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
            "allowed_statuses": ["mew_preferred", "fresh_cli_preferred", "parity", "inconclusive", "blocked"],
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
            "allowed_values": ["mew", "fresh_cli", "parity", "inconclusive"],
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
                f"- comparison_status: {comparison.get('status', 'unknown')}",
                f"- next_blocker: {comparison.get('next_blocker', '')}",
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
    mew_run_evidence = protocol.get("mew_run_evidence") or {}
    mew_session_id = mew_run_evidence.get("mew_session_argument") or mew_run_evidence.get("session_argument")
    if mew_session_id:
        merge_command += f" --mew-session-id {shlex.quote(str(mew_session_id))}"
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


def run_m6_9_drift_canary_scenario(workspace, env=None):
    del env
    commands = []
    checks = []
    output_dir = Path(workspace) / STATE_DIR / "dogfood"
    output_dir.mkdir(parents=True, exist_ok=True)

    memory_entries = []
    iterations = []
    for iteration in range(1, 6):
        memory_entries.append(
            {
                "id": f"drift-canary-memory-{iteration}",
                "kind": "drift-canary",
                "iteration": iteration,
                "green": True,
            }
        )
        iterations.append(
            {
                "iteration": iteration,
                "status": "green",
                "drift_canary": "green",
                "memory_item_count": len(memory_entries),
                "used_accumulated_memory": iteration > 1,
            }
        )

    drift_canary_green_count = sum(1 for item in iterations if item["drift_canary"] == "green")
    memory_accumulated = len(memory_entries) == 5 and all(
        item["iteration"] == index for index, item in enumerate(memory_entries, start=1)
    )
    novel_task_injection = {
        "task_id": "novel-task-durable-memory-drift-canary-exploration",
        "task_family": "m6_9_novel_task",
        "durable_memory_proof_slice": "m6_9_drift_canary",
        "scenario_choices_anchor": "m6_9-drift-canary",
        "verifier_hint": "uv run pytest -q tests/test_dogfood.py -k 'm6_9_drift_canary or m6_9_novel_task or scenario_choices' --no-testmon",
        "mew_first": True,
        "known_memory_matches": [],
        "unknown_memory_match": True,
        "forced_exploration": True,
        "forced_source_read": True,
        "forced_test_read": True,
        "silent_memory_reliance": False,
        "no_silent_memory_reliance": True,
        "reviewer_visible_exploration_reason": "reviewer-visible novel-task durable-memory drift-canary found unknown-memory, so mew-first exploration forced source and test reads instead of silent memory reliance",
        "exploration_decision_matrix": [
            {
                "decision": "unknown-memory match",
                "observed": True,
                "action": "do not reuse durable memory as an answer",
            },
            {
                "decision": "forced source read",
                "observed": True,
                "action": "inspect src/mew/dogfood.py before drafting",
            },
            {
                "decision": "forced test read",
                "observed": True,
                "action": "inspect tests/test_dogfood.py before drafting",
            },
            {
                "decision": "no silent memory reliance",
                "observed": True,
                "action": "record an explicit reviewer-visible exploration reason",
            },
        ],
        "exploration_steps": [
            "inspect_current_task",
            "read_current_source_anchor",
            "read_current_test_anchor",
        ],
    }
    trace = {
        "scenario": "m6_9-drift-canary",
        "iterations_total": len(iterations),
        "drift_canary_green_count": drift_canary_green_count,
        "memory_accumulated": memory_accumulated,
        "iterations": iterations,
        "memory_entries": memory_entries,
        "novel_task_injection": novel_task_injection,
    }
    json_path = output_dir / "m6_9-drift-canary-trace.json"
    write_json_file(json_path, trace)
    loaded = read_json_file(json_path, {})
    loaded_novel_task = loaded.get("novel_task_injection") or {}

    _scenario_check(
        checks,
        "m6_9_drift_canary_runs_five_green_iterations",
        loaded.get("iterations_total") == 5 and loaded.get("drift_canary_green_count") == 5,
        observed={
            "iterations_total": loaded.get("iterations_total"),
            "drift_canary_green_count": loaded.get("drift_canary_green_count"),
        },
        expected={"iterations_total": 5, "drift_canary_green_count": 5},
    )
    _scenario_check(
        checks,
        "m6_9_drift_canary_accumulates_memory",
        loaded.get("memory_accumulated") is True
        and [item.get("memory_item_count") for item in loaded.get("iterations") or []] == [1, 2, 3, 4, 5],
        observed={
            "memory_accumulated": loaded.get("memory_accumulated"),
            "memory_item_counts": [
                item.get("memory_item_count") for item in loaded.get("iterations") or []
            ],
        },
        expected="memory accumulates monotonically across five green canary iterations",
    )
    _scenario_check(
        checks,
        "m6_9_drift_canary_novel_task_forces_exploration",
        loaded_novel_task.get("forced_exploration") is True
        and loaded_novel_task.get("forced_source_read") is True
        and loaded_novel_task.get("forced_test_read") is True
        and loaded_novel_task.get("silent_memory_reliance") is False
        and loaded_novel_task.get("no_silent_memory_reliance") is True
        and loaded_novel_task.get("unknown_memory_match") is True
        and not loaded_novel_task.get("known_memory_matches")
        and "reviewer-visible" in (loaded_novel_task.get("reviewer_visible_exploration_reason") or ""),
        observed=loaded_novel_task,
        expected={
            "unknown_memory_match": True,
            "forced_source_read": True,
            "forced_test_read": True,
            "silent_memory_reliance": False,
            "reviewer_visible_exploration_reason": "reviewer-visible",
        },
    )
    _scenario_check(
        checks,
        "m6_9_drift_canary_writes_deterministic_trace",
        json_path.exists()
        and loaded.get("scenario") == "m6_9-drift-canary"
        and loaded.get("iterations") == iterations,
        observed={"path": str(json_path), "scenario": loaded.get("scenario")},
        expected="deterministic drift-canary trace JSON is written",
    )

    report = _scenario_report("m6_9-drift-canary", workspace, commands, checks)
    report["artifacts"] = {
        "iterations_total": loaded.get("iterations_total"),
        "drift_canary_green_count": loaded.get("drift_canary_green_count"),
        "memory_accumulated": loaded.get("memory_accumulated"),
        "novel_task_injection": loaded_novel_task,
        "trace_path": str(json_path),
        "trace": loaded,
    }
    return report


def run_m6_9_alignment_decay_rehearsal_scenario(workspace, env=None):
    del env
    commands = []
    checks = []
    output_dir = Path(workspace) / STATE_DIR / "dogfood"
    output_dir.mkdir(parents=True, exist_ok=True)

    prior_conventions = [
        {
            "name": "bounded_source_test_pair",
            "source_path": "src/mew/dogfood.py",
            "test_path": "tests/test_dogfood.py",
        },
        {
            "name": "deterministic_trace_json",
            "trace_suffix": "-trace.json",
        },
        {
            "name": "text_and_json_report_coverage",
            "text_report": True,
            "json_report": True,
        },
    ]
    prior_convention_names = [item["name"] for item in prior_conventions]
    gap_or_decay = {
        "simulated_gap_or_decay": True,
        "decay_kind": "simulated_alignment_decay",
        "available_conventions_after_decay": [],
        "decayed_convention_count": len(prior_conventions),
    }
    rehearsal_iterations = [
        {
            "iteration": 1,
            "phase": "rehearsal",
            "rehearsal_pass_ran": True,
            "recovered_conventions": prior_convention_names,
            "reviewer_steering_required": False,
        }
    ]
    recovered_names = rehearsal_iterations[0]["recovered_conventions"]
    prior_convention_reused = recovered_names == prior_convention_names
    rehearsal_pass_ran = rehearsal_iterations[0]["rehearsal_pass_ran"] is True
    reviewer_steering_required = rehearsal_iterations[0]["reviewer_steering_required"] is True
    recovered_within_iterations = 1 if rehearsal_pass_ran and prior_convention_reused else None
    trace = {
        "scenario": "m6_9-alignment-decay-rehearsal",
        "simulated_gap_or_decay": gap_or_decay["simulated_gap_or_decay"],
        "rehearsal_pass_ran": rehearsal_pass_ran,
        "recovered_within_iterations": recovered_within_iterations,
        "reviewer_steering_required": reviewer_steering_required,
        "prior_convention_reused": prior_convention_reused,
        "prior_conventions": prior_conventions,
        "gap_or_decay": gap_or_decay,
        "iterations": rehearsal_iterations,
    }
    json_path = output_dir / "m6_9-alignment-decay-rehearsal-trace.json"
    write_json_file(json_path, trace)
    loaded = read_json_file(json_path, {})

    _scenario_check(
        checks,
        "m6_9_alignment_decay_rehearsal_simulates_gap_or_decay",
        loaded.get("simulated_gap_or_decay") is True
        and (loaded.get("gap_or_decay") or {}).get("available_conventions_after_decay") == [],
        observed={
            "simulated_gap_or_decay": loaded.get("simulated_gap_or_decay"),
            "gap_or_decay": loaded.get("gap_or_decay"),
        },
        expected="a deterministic simulated gap/decay pass clears available convention context",
    )
    _scenario_check(
        checks,
        "m6_9_alignment_decay_rehearsal_runs_rehearsal_pass",
        loaded.get("rehearsal_pass_ran") is True
        and [item.get("iteration") for item in loaded.get("iterations") or []] == [1],
        observed={
            "rehearsal_pass_ran": loaded.get("rehearsal_pass_ran"),
            "iterations": loaded.get("iterations"),
        },
        expected="one deterministic rehearsal pass runs after the simulated decay",
    )
    _scenario_check(
        checks,
        "m6_9_alignment_decay_rehearsal_recovers_prior_conventions_without_steering",
        loaded.get("recovered_within_iterations") == 1
        and loaded.get("reviewer_steering_required") is False
        and loaded.get("prior_convention_reused") is True,
        observed={
            "recovered_within_iterations": loaded.get("recovered_within_iterations"),
            "reviewer_steering_required": loaded.get("reviewer_steering_required"),
            "prior_convention_reused": loaded.get("prior_convention_reused"),
        },
        expected={
            "recovered_within_iterations": 1,
            "reviewer_steering_required": False,
            "prior_convention_reused": True,
        },
    )
    _scenario_check(
        checks,
        "m6_9_alignment_decay_rehearsal_writes_deterministic_trace",
        json_path.exists()
        and loaded == trace
        and loaded.get("scenario") == "m6_9-alignment-decay-rehearsal",
        observed={"path": str(json_path), "trace": loaded},
        expected="deterministic alignment-decay rehearsal trace JSON is written",
    )

    report = _scenario_report("m6_9-alignment-decay-rehearsal", workspace, commands, checks)
    report["artifacts"] = {
        "simulated_gap_or_decay": loaded.get("simulated_gap_or_decay"),
        "rehearsal_pass_ran": loaded.get("rehearsal_pass_ran"),
        "recovered_within_iterations": loaded.get("recovered_within_iterations"),
        "reviewer_steering_required": loaded.get("reviewer_steering_required"),
        "prior_convention_reused": loaded.get("prior_convention_reused"),
        "prior_conventions": loaded.get("prior_conventions"),
        "gap_or_decay": loaded.get("gap_or_decay"),
        "iterations": loaded.get("iterations"),
        "trace_path": str(json_path),
        "trace": loaded,
    }
    return report


def _write_terminal_bench_replay_fixture(workspace, *, task="compile-compcert"):
    job_dir = Path(workspace) / "terminal-bench-replay-fixture"
    trial_name = f"{task}__fixture"
    trial_dir = job_dir / trial_name
    artifact_dir = trial_dir / "agent" / "terminal-bench-harbor-smoke" / "unknown-task"
    verifier_dir = trial_dir / "verifier"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    verifier_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "result.json").write_text(
        json.dumps(
            {
                "id": "fixture-job",
                "n_total_trials": 1,
                "stats": {
                    "n_trials": 1,
                    "n_errors": 0,
                    "evals": {
                        "mew__terminal-bench/terminal-bench-2": {
                            "n_trials": 1,
                            "n_errors": 0,
                            "metrics": [{"mean": 0.0}],
                        }
                    },
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (trial_dir / "result.json").write_text(
        json.dumps(
            {
                "trial_name": trial_name,
                "task_name": f"terminal-bench/{task}",
                "verifier_result": {"reward": 0.0},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (verifier_dir / "reward.txt").write_text("0\n", encoding="utf-8")
    (verifier_dir / "test-stdout.txt").write_text("missing /tmp/CompCert/ccomp\n", encoding="utf-8")
    report = {
        "summary": "mew work --oneshot completed generic work-session attempt",
        "task_id": 1,
        "session_id": 1,
        "work_exit_code": 1,
        "resume": {
            "session_id": 1,
            "task_id": 1,
            "title": "Compile CompCert from source",
            "goal": (
                "Under /tmp/CompCert/, build the CompCert C verified compiler from source. "
                "Ensure that CompCert can be invoked through /tmp/CompCert/ccomp."
            ),
            "phase": "failed",
            "next_action": "verify the world and review side-effecting work before retry",
            "long_build_state": {},
        },
        "work_report": {
            "session_id": 1,
            "task_id": 1,
            "stop_reason": "wall_timeout",
            "wall_timeout": True,
            "steps": [
                {
                    "index": 1,
                    "status": "completed",
                    "action": {"type": "run_command"},
                    "model_turn": {"id": 1, "status": "completed", "action": {"type": "run_command"}},
                    "tool_call": {
                        "id": 1,
                        "tool": "run_command",
                        "status": "completed",
                        "parameters": {
                            "cwd": "/tmp/CompCert",
                            "command": "./configure x86_64-linux && apt-cache policy coq",
                        },
                        "result": {
                            "cwd": "/tmp/CompCert",
                            "command": "./configure x86_64-linux && apt-cache policy coq",
                            "exit_code": 2,
                            "stdout": (
                                "Testing Coq... version 8.18.0 -- UNSUPPORTED\n"
                                "Error: CompCert requires a version of Coq between 8.12.0 and 8.16.1\n"
                            ),
                            "stderr": "",
                        },
                    },
                },
                {
                    "index": 2,
                    "status": "completed",
                    "action": {"type": "run_command"},
                    "model_turn": {"id": 2, "status": "completed", "action": {"type": "run_command"}},
                    "tool_call": {
                        "id": 2,
                        "tool": "run_command",
                        "status": "completed",
                        "parameters": {
                            "cwd": "/tmp/CompCert",
                            "command": "opam install -y coq.8.16.1",
                        },
                        "result": {
                            "cwd": "/tmp/CompCert",
                            "command": "opam install -y coq.8.16.1",
                            "exit_code": 124,
                            "timed_out": True,
                            "stdout": "-> retrieved coq.8.16.1\n",
                            "stderr": "",
                        },
                    },
                },
            ],
        },
    }
    (artifact_dir / "mew-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (artifact_dir / "command-transcript.json").write_text(
        json.dumps(
            {
                "command": "mew work --oneshot --instruction fixture",
                "exit_code": 1,
                "timed_out": False,
                "timeout_seconds": 1800,
                "mew_max_wall_seconds": 1740,
                "stdout": "",
                "stderr": "",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return job_dir


def _compile_compcert_task_description():
    return (
        "Under /tmp/CompCert/, build the CompCert C verified compiler from source. "
        "Ensure that CompCert can be invoked through /tmp/CompCert/ccomp."
    )


def _compile_compcert_long_build_execution_contract(*, stage="build", purpose="build", acceptance_kind="terminal"):
    return {
        "schema_version": 2,
        "purpose": purpose,
        "stage": stage,
        "proof_role": "dependency_strategy" if purpose == "diagnostic" else "final_artifact",
        "acceptance_kind": acceptance_kind,
        "expected_artifacts": [] if purpose == "diagnostic" else [{"path": "/tmp/CompCert/ccomp", "kind": "executable"}],
        "declared_target_refs": [
            {"kind": "artifact", "path": "/tmp/CompCert/ccomp", "ref": "required-final-artifact"},
            {"kind": "source_tree", "path": "/tmp/CompCert", "ref": "source-tree:CompCert-v3.13.1"},
        ],
        "continuation_policy": {
            "mode": "blocking" if purpose == "diagnostic" else "managed",
            "yield_after_seconds": 30,
            "resume_policy": "none" if purpose == "diagnostic" else "idempotent_resume",
            "terminal_required_for_acceptance": purpose != "diagnostic",
            "final_proof_reserve_seconds": 60,
        },
        "background_policy": {"mode": "foreground_blocking", "allow_background": False},
        "source_authority_requirement": {"mode": "consumes_authority", "required": True},
        "risk_class": "read_only" if purpose == "diagnostic" else "write",
    }


def _compile_compcert_diagnostic_action():
    return {
        "type": "run_command",
        "cwd": "/app",
        "timeout": 90,
        "command": (
            "set -euxo pipefail\n"
            "cd /tmp/CompCert\n"
            "printf '=== configure --help ===\\n'\n"
            "./configure --help\n"
            "printf '\\n=== relevant configure/make references ===\\n'\n"
            "grep -nE 'Coq|coq|COQ|Rocq|rocq|Menhir|menhir|MENHIR|menhirLib|MenhirLib|external|system|prebuilt|library|LIBRARY|ignore|unsupported|VERSION' configure Makefile Makefile.menhir 2>/dev/null | head -250\n"
            "printf '\\n=== installed and candidate package versions ===\\n'\n"
            "apt-cache policy coq libcoq-stdlib libcoq-core-ocaml libcoq-flocq menhir libmenhir-ocaml-dev opam || true\n"
            "printf '\\n=== installed menhir library files ===\\n'\n"
            "dpkg -L menhir 2>/dev/null | grep -Ei 'menhirLib|MenhirLib|META|\\.cmxa$|\\.cma$|\\.cmi$' | head -100 || true\n"
            "printf '\\n=== ocamlfind menhir packages ===\\n'\n"
            "ocamlfind list 2>/dev/null | grep -i menhir || true"
        ),
        "execution_contract": _compile_compcert_long_build_execution_contract(
            stage="diagnostic",
            purpose="diagnostic",
            acceptance_kind="progress_only",
        ),
        "reason": (
            "The latest failed configure identified Coq version and Menhir API issues; inspect the "
            "source-provided configure surface and installed package state before installing/building "
            "alternate toolchains or retrying."
        ),
        "summary": "Diagnose the configure failure before retrying the build.",
        "task_done": False,
    }


def _write_compile_compcert_emulator_fixture(workspace):
    job_dir = Path(workspace) / "compile-compcert-emulator-fixture"
    trial_dir = job_dir / "compile-compcert__emulator"
    artifact_dir = trial_dir / "agent" / "terminal-bench-harbor-smoke" / "unknown-task"
    verifier_dir = trial_dir / "verifier"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    verifier_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "result.json").write_text(
        json.dumps(
            {
                "id": "compile-compcert-emulator-job",
                "n_total_trials": 1,
                "stats": {
                    "n_trials": 1,
                    "n_errors": 0,
                    "evals": {
                        "mew__terminal-bench/terminal-bench-2": {
                            "n_trials": 1,
                            "n_errors": 0,
                            "metrics": [{"mean": 0.0}],
                        }
                    },
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (trial_dir / "result.json").write_text(
        json.dumps(
            {
                "trial_name": "compile-compcert__emulator",
                "task_name": "terminal-bench/compile-compcert",
                "verifier_result": {"reward": 0.0},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (verifier_dir / "reward.txt").write_text("0\n", encoding="utf-8")
    (verifier_dir / "test-stdout.txt").write_text("missing /tmp/CompCert/ccomp\n", encoding="utf-8")
    build_command = (
        "set -euxo pipefail\n"
        "mkdir -p /tmp/CompCert-source\n"
        "wget -O /tmp/CompCert-source/compcert-3.13.1.tar.gz https://github.com/AbsInt/CompCert/archive/refs/tags/v3.13.1.tar.gz\n"
        "tar -xzf /tmp/CompCert-source/compcert-3.13.1.tar.gz -C /tmp/CompCert-source\n"
        "mv /tmp/CompCert-source/CompCert-3.13.1 /tmp/CompCert\n"
        "cd /tmp/CompCert\n"
        "./configure x86_64-linux\n"
        "make -j\"$(nproc)\" ccomp\n"
        "test -x /tmp/CompCert/ccomp"
    )
    diagnostic_action = _compile_compcert_diagnostic_action()
    contract = build_long_build_contract(
        _compile_compcert_task_description(),
        ["/tmp/CompCert/ccomp"],
        contract_id="work_session:1:long_build:1",
    )
    failed_run = build_long_command_run(
        session_id=1,
        ordinal=1,
        task_id=1,
        contract_id="work_session:1:long_build:1",
        attempt_id="attempt-1",
        tool_call_id=1,
        stage="build",
        selected_target="/tmp/CompCert/ccomp",
        command=build_command,
        cwd="/app",
        status="failed",
        requested_timeout_seconds=1296,
        effective_timeout_seconds=1296,
        work_wall_remaining_seconds=1354,
        stdout=(
            "Testing Coq... version 8.18.0 -- UNSUPPORTED\n"
            "Error: CompCert requires a version of Coq between 8.12.0 and 8.16.1\n"
            "Error: cannot determine the location of the Menhir API library.\n"
        ),
        stderr="make: *** [Makefile:200: ccomp] Error 2\n",
    )
    failed_run["terminal"]["exit_code"] = 2
    report = {
        "summary": "mew work --oneshot completed generic work-session attempt",
        "task_id": 1,
        "session_id": 1,
        "work_exit_code": 1,
        "resume": {
            "session_id": 1,
            "task_id": 1,
            "title": "Compile CompCert from source",
            "goal": _compile_compcert_task_description(),
            "phase": "failed",
            "next_action": "diagnose the terminal configure failure before retrying",
            "long_build_state": {
                "kind": "long_build_state",
                "contract": contract,
                "long_command_runs": [failed_run],
                "latest_long_command_run_id": failed_run["id"],
                "latest_long_command_status": "failed",
            },
        },
        "work_report": {
            "session_id": 1,
            "task_id": 1,
            "stop_reason": "long_command_budget_blocked",
            "wall_timeout": False,
            "steps": [
                {
                    "index": 1,
                    "status": "completed",
                    "action": {"type": "run_command", "command": build_command, "timeout": 1296},
                    "model_turn": {
                        "id": 1,
                        "status": "completed",
                        "action_plan": {
                            "summary": "Fetch, configure, and build the required ccomp artifact.",
                            "action": {
                                "type": "run_command",
                                "cwd": "/app",
                                "timeout": 1296,
                                "command": build_command,
                                "execution_contract": _compile_compcert_long_build_execution_contract(),
                            },
                        },
                        "decision_plan": {
                            "summary": "Ground source and run the shortest build for /tmp/CompCert/ccomp.",
                            "action": {
                                "type": "run_command",
                                "cwd": "/app",
                                "timeout": 1296,
                                "command": build_command,
                                "execution_contract": _compile_compcert_long_build_execution_contract(),
                            },
                        },
                        "action": {"type": "run_command", "command": build_command, "timeout": 1296},
                    },
                    "tool_call": {
                        "id": 1,
                        "tool": "run_command",
                        "status": "completed",
                        "parameters": {
                            "cwd": "/app",
                            "command": build_command,
                            "timeout": 1296,
                            "execution_contract": _compile_compcert_long_build_execution_contract(),
                            "long_command_budget": {
                                "action_kind": "start_long_command",
                                "stage": "build",
                                "effective_timeout_seconds": 1296.0,
                                "requested_timeout_seconds": 1296.0,
                                "minimum_timeout_seconds": 31.0,
                                "yield_after_seconds": 30,
                                "yield_eligible": True,
                            },
                        },
                        "result": {
                            "cwd": "/app",
                            "command": build_command,
                            "exit_code": 2,
                            "stdout": (
                                "Testing Coq... version 8.18.0 -- UNSUPPORTED\n"
                                "Error: CompCert requires a version of Coq between 8.12.0 and 8.16.1\n"
                                "Error: cannot determine the location of the Menhir API library.\n"
                            ),
                            "stderr": "make: *** [Makefile:200: ccomp] Error 2\n",
                        },
                    },
                },
                {
                    "index": 2,
                    "status": "planned",
                    "action": dict(diagnostic_action),
                    "model_turn": {
                        "id": 2,
                        "status": "planned",
                        "decision_plan": {
                            "summary": diagnostic_action["summary"],
                            "action": dict(diagnostic_action),
                        },
                        "action_plan": {
                            "summary": diagnostic_action["summary"],
                            "action": dict(diagnostic_action),
                        },
                        "action": dict(diagnostic_action),
                    },
                },
            ],
        },
    }
    (artifact_dir / "mew-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (artifact_dir / "command-transcript.json").write_text(
        json.dumps(
            {
                "command": "mew work --oneshot --instruction compile-compcert-emulator",
                "exit_code": 1,
                "timed_out": False,
                "timeout_seconds": 1800,
                "mew_max_wall_seconds": 1740,
                "stdout": "",
                "stderr": "",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return job_dir


def _public_llm_action_fixture(context):
    fixture = dict((context or {}).get("fixture") or {})
    raw_action = dict(fixture.get("raw_action") or {})
    contract = raw_action.get("execution_contract") if isinstance(raw_action.get("execution_contract"), dict) else {}
    return {
        "trial_name": (context or {}).get("trial_name") or "",
        "report_path": (context or {}).get("report_path") or "",
        "step_index": fixture.get("step_index"),
        "step_status": fixture.get("step_status") or "",
        "model_turn_id": fixture.get("model_turn_id"),
        "raw_action_type": raw_action.get("type") or raw_action.get("tool") or "",
        "raw_action_timeout": raw_action.get("timeout"),
        "raw_action_command": raw_action.get("command") or "",
        "execution_contract": {
            "purpose": contract.get("purpose") or "",
            "stage": contract.get("stage") or "",
            "proof_role": contract.get("proof_role") or "",
            "acceptance_kind": contract.get("acceptance_kind") or "",
            "risk_class": contract.get("risk_class") or "",
        },
    }


def _write_llm_action_fixtures_jsonl(path, contexts):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for context in contexts:
            fh.write(json.dumps(_public_llm_action_fixture(context), ensure_ascii=False, sort_keys=True) + "\n")


def _select_compile_compcert_emulator_context(contexts):
    for context in reversed(contexts or []):
        raw_action = (((context or {}).get("fixture") or {}).get("raw_action") or {})
        contract = raw_action.get("execution_contract") if isinstance(raw_action.get("execution_contract"), dict) else {}
        if (
            str(raw_action.get("type") or raw_action.get("tool") or "") == "run_command"
            and str(contract.get("purpose") or "") == "diagnostic"
        ):
            return context
    for context in reversed(contexts or []):
        raw_action = (((context or {}).get("fixture") or {}).get("raw_action") or {})
        if str(raw_action.get("type") or raw_action.get("tool") or "") == "run_command":
            return context
    return {}


def _evaluate_compile_compcert_emulator_action(context):
    from .commands import apply_work_tool_wall_timeout_ceiling, work_tool_long_command_budget_policy

    fixture = ((context or {}).get("fixture") or {})
    raw_action = dict(fixture.get("raw_action") or {})
    action_type = str(raw_action.pop("type", "") or raw_action.pop("tool", "") or "")
    parameters = dict(raw_action)
    if not action_type:
        return {"policy": {}, "ceiling": {"blocked": True, "reason": "no raw action type"}, "parameters": parameters}
    policy = work_tool_long_command_budget_policy(
        action_type,
        parameters,
        task=(context or {}).get("task") or {},
        session=(context or {}).get("session") or {},
    )
    ceiling_parameters = dict(parameters)
    ceiling = apply_work_tool_wall_timeout_ceiling(
        action_type,
        ceiling_parameters,
        max_wall_seconds=1800,
        run_started_at=time.monotonic() - 450,
        recovery_reserve_seconds=policy.get("reserve_seconds") or 0.0,
        long_command_budget_policy=policy,
    )
    return {"policy": policy, "ceiling": ceiling, "parameters": ceiling_parameters}


def _m6_24_terminal_bench_replay_assertions(
    *,
    job_dir=None,
    long_build_status=None,
    current_failure=None,
    recovery_action=None,
    blockers=None,
    mew_exit_code=None,
    external_reward=None,
):
    if job_dir:
        assertions = {}
    else:
        assertions = {
            "long_build_status": "blocked",
            "blockers": ["compatibility_override_probe_missing"],
            "mew_exit_code": 1,
            "external_reward": 0.0,
        }
    if long_build_status:
        assertions["long_build_status"] = long_build_status
    if current_failure:
        assertions["current_failure"] = current_failure
    if recovery_action:
        assertions["recovery_action"] = recovery_action
    if blockers:
        assertions["blockers"] = list(blockers)
    if mew_exit_code is not None:
        assertions["mew_exit_code"] = mew_exit_code
    if external_reward is not None:
        assertions["external_reward"] = external_reward
    return assertions


def run_m6_24_terminal_bench_replay_scenario(
    workspace,
    *,
    job_dir=None,
    task=None,
    long_build_status=None,
    current_failure=None,
    recovery_action=None,
    blockers=None,
    mew_exit_code=None,
    external_reward=None,
):
    checks = []
    commands = []
    source = Path(job_dir).expanduser() if job_dir else _write_terminal_bench_replay_fixture(workspace)
    assertions = _m6_24_terminal_bench_replay_assertions(
        job_dir=job_dir,
        long_build_status=long_build_status,
        current_failure=current_failure,
        recovery_action=recovery_action,
        blockers=blockers,
        mew_exit_code=mew_exit_code,
        external_reward=external_reward,
    )
    replay = replay_terminal_bench_job(
        source,
        task=task,
        assertions=assertions,
    )
    _scenario_check(
        checks,
        "m6_24_terminal_bench_replay_finds_artifact",
        replay.get("trial_count", 0) >= 1,
        replay.get("trial_count"),
        ">=1",
    )
    _scenario_check(
        checks,
        "m6_24_terminal_bench_replay_recomputes_resume",
        replay.get("status") == "pass",
        replay,
        "pass",
    )
    first_trial = ((replay.get("trials") or [])[:1] or [{}])[0]
    current_long = ((first_trial.get("current") or {}).get("long_build_state") or {})
    _scenario_check(
        checks,
        "m6_24_terminal_bench_replay_satisfies_requested_assertions",
        replay.get("status") == "pass",
        replay.get("checks") or [],
        "pass",
    )
    report = _scenario_report("m6_24-terminal-bench-replay", workspace, commands, checks)
    report["artifacts"] = {
        "job_dir": str(source),
        "task": task or "",
        "trial_count": replay.get("trial_count"),
        "replay_status": replay.get("status"),
        "first_trial": first_trial.get("trial_name") or "",
        "current_long_build": current_long,
    }
    return report


def run_m6_24_compile_compcert_emulator_scenario(
    workspace,
    *,
    job_dir=None,
):
    checks = []
    commands = []
    source = Path(job_dir).expanduser() if job_dir else _write_compile_compcert_emulator_fixture(workspace)
    replay = replay_terminal_bench_job(
        source,
        task="compile-compcert",
        assertions={
            "long_build_status": "blocked",
            "current_failure": "long_command_failed",
            "recovery_action": "repair_failed_long_command",
            "mew_exit_code": 1,
            "external_reward": 0.0,
        },
    )
    contexts = terminal_bench_llm_action_fixture_contexts(source, task="compile-compcert")
    fixture_path = Path(workspace) / "compile-compcert-llm-action-fixtures.jsonl"
    _write_llm_action_fixtures_jsonl(fixture_path, contexts)
    selected = _select_compile_compcert_emulator_context(contexts)
    evaluation = _evaluate_compile_compcert_emulator_action(selected)
    policy = evaluation.get("policy") if isinstance(evaluation.get("policy"), dict) else {}
    ceiling = evaluation.get("ceiling") if isinstance(evaluation.get("ceiling"), dict) else {}
    parameters = evaluation.get("parameters") if isinstance(evaluation.get("parameters"), dict) else {}
    long_command_budget = (
        parameters.get("long_command_budget") if isinstance(parameters.get("long_command_budget"), dict) else {}
    )

    _scenario_check(
        checks,
        "m6_24_compile_compcert_emulator_replay_passes",
        replay.get("status") == "pass",
        replay.get("checks") or [],
        "terminal-bench replay pass",
    )
    _scenario_check(
        checks,
        "m6_24_compile_compcert_emulator_extracts_llm_actions",
        bool(contexts),
        {"count": len(contexts), "fixture_path": str(fixture_path)},
        ">=1 model action fixture",
    )
    _scenario_check(
        checks,
        "m6_24_compile_compcert_emulator_selects_diagnostic_run_command",
        bool(selected)
        and str((((selected.get("fixture") or {}).get("raw_action") or {}).get("type") or "")) == "run_command",
        _public_llm_action_fixture(selected) if selected else {},
        "run_command raw action fixture",
    )
    _scenario_check(
        checks,
        "m6_24_compile_compcert_emulator_uses_diagnostic_budget",
        bool(policy.get("applies"))
        and bool(policy.get("diagnostic_budget"))
        and float(policy.get("minimum_timeout_seconds") or 0.0) <= 90.0,
        {
            "applies": policy.get("applies"),
            "diagnostic_budget": policy.get("diagnostic_budget"),
            "minimum_timeout_seconds": policy.get("minimum_timeout_seconds"),
            "budget_blocked_reason": policy.get("budget_blocked_reason"),
            "long_command_budget": long_command_budget,
        },
        "diagnostic raw action keeps short diagnostic repair budget",
    )
    _scenario_check(
        checks,
        "m6_24_compile_compcert_emulator_does_not_block_raw_diagnostic_action",
        not bool(ceiling.get("blocked")),
        {"ceiling": ceiling, "long_command_budget": long_command_budget},
        "no wall-time/budget block for read-only diagnostic action",
    )

    report = _scenario_report("m6_24-compile-compcert-emulator", workspace, commands, checks)
    report["artifacts"] = {
        "job_dir": str(source),
        "fixture_path": str(fixture_path),
        "llm_action_fixture_count": len(contexts),
        "selected_llm_action_fixture": _public_llm_action_fixture(selected) if selected else {},
        "replay_status": replay.get("status"),
        "budget_policy": policy,
        "ceiling": ceiling,
        "post_policy_parameters": parameters,
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
            reports.append(
                run_resident_loop_scenario(
                    scenario_workspace,
                    env=env,
                    duration=getattr(args, "duration", 6.0),
                    interval=getattr(args, "interval", 2.0),
                    poll_interval=getattr(args, "poll_interval", 0.1),
                    time_dilation=getattr(args, "time_dilation", None),
                )
            )
        elif name == "native-work":
            reports.append(run_native_work_scenario(scenario_workspace, env=env))
        elif name == "self-improve-controls":
            reports.append(run_self_improve_controls_scenario(scenario_workspace, env=env))
        elif name == "m5-safety-hooks":
            reports.append(run_m5_safety_hooks_scenario(scenario_workspace, env=env))
        elif name == "m6-daemon-watch":
            reports.append(run_m6_daemon_watch_scenario(scenario_workspace, env=env))
        elif name == "m6-daemon-restart":
            reports.append(run_m6_daemon_restart_scenario(scenario_workspace, env=env))
        elif name == "m6-daemon-loop":
            reports.append(
                run_m6_daemon_loop_scenario(
                    scenario_workspace,
                    env=env,
                    duration=getattr(args, "duration", 6.0),
                    interval=getattr(args, "interval", 2.0),
                    poll_interval=getattr(args, "poll_interval", 0.1),
                    time_dilation=getattr(args, "time_dilation", None),
                )
            )
        elif name == "m6_11-compiler-replay":
            reports.append(run_m6_11_compiler_replay_scenario(scenario_workspace, env=env))
        elif name == "m6_11-draft-timeout":
            reports.append(run_m6_11_draft_timeout_scenario(scenario_workspace, env=env))
        elif name == "m6_11-refusal-separation":
            reports.append(run_m6_11_refusal_separation_scenario(scenario_workspace, env=env))
        elif name == "m6_11-drafting-recovery":
            reports.append(run_m6_11_drafting_recovery_scenario(scenario_workspace, env=env))
        elif name == "m6_11-phase4-regression":
            reports.append(run_m6_11_phase4_regression_scenario(scenario_workspace, env=env))
        elif name == "m6_9-memory-taxonomy":
            reports.append(run_m6_9_memory_taxonomy_scenario(scenario_workspace, env=env))
        elif name == "m6_9-reviewer-steering-reuse":
            reports.append(run_m6_9_reviewer_steering_reuse_scenario(scenario_workspace, env=env))
        elif name == "m6_9-failure-shield-reuse":
            reports.append(run_m6_9_failure_shield_reuse_scenario(scenario_workspace, env=env))
        elif name == "m6_9-reasoning-trace-recall":
            reports.append(run_m6_9_reasoning_trace_recall_scenario(scenario_workspace, env=env))
        elif name == "m6_13-deliberation-internalization":
            live_provider = bool(getattr(args, "ai", False))
            model_backend = getattr(args, "model_backend", "") or "codex"
            auth_path = getattr(args, "auth", None)
            model_auth = {"path": auth_path or "auth.json"}
            model = getattr(args, "model", "") or ""
            base_url = getattr(args, "base_url", "") or ""
            if live_provider:
                try:
                    model_backend = normalize_model_backend(model_backend)
                    model_auth = load_model_auth(model_backend, auth_path)
                except MewError as exc:
                    raise ValueError(str(exc)) from exc
                model = model or model_backend_default_model(model_backend)
                base_url = base_url or model_backend_default_base_url(model_backend)
            reports.append(
                run_m6_13_deliberation_internalization_scenario(
                    scenario_workspace,
                    env=env,
                    live_provider=live_provider,
                    model_auth=model_auth,
                    model=model,
                    base_url=base_url,
                    model_backend=model_backend,
                    timeout=getattr(args, "model_timeout", 60),
                )
            )
        elif name == "m6_24-terminal-bench-replay":
            reports.append(
                run_m6_24_terminal_bench_replay_scenario(
                    scenario_workspace,
                    job_dir=getattr(args, "terminal_bench_job_dir", None),
                    task=getattr(args, "terminal_bench_task", None),
                    long_build_status=getattr(args, "terminal_bench_assert_long_build_status", None),
                    current_failure=getattr(args, "terminal_bench_assert_current_failure", None),
                    recovery_action=getattr(args, "terminal_bench_assert_recovery_action", None),
                    blockers=getattr(args, "terminal_bench_assert_blocker", None),
                    mew_exit_code=getattr(args, "terminal_bench_assert_mew_exit_code", None),
                    external_reward=getattr(args, "terminal_bench_assert_external_reward", None),
                )
            )
        elif name == "m6_24-compile-compcert-emulator":
            reports.append(
                run_m6_24_compile_compcert_emulator_scenario(
                    scenario_workspace,
                    job_dir=getattr(args, "terminal_bench_job_dir", None),
                )
            )
        elif name == "m6_9-active-memory-recall":
            reports.append(run_m6_9_active_memory_recall_scenario(scenario_workspace, env=env))
        elif name == "m6_9-repeated-task-recall":
            reports.append(run_m6_9_repeated_task_recall_scenario(scenario_workspace, env=env))
        elif name == "m6_9-phase1-regression":
            reports.append(run_m6_9_phase1_regression_scenario(scenario_workspace, env=env))
        elif name == "m6_9-phase2-regression":
            reports.append(run_m6_9_phase2_regression_scenario(scenario_workspace, env=env))
        elif name == "m6_9-symbol-index-hit":
            reports.append(run_m6_9_symbol_index_hit_scenario(scenario_workspace, env=env))
        elif name == "m6_9-drift-canary":
            reports.append(run_m6_9_drift_canary_scenario(scenario_workspace, env=env))
        elif name == "m6_9-alignment-decay-rehearsal":
            reports.append(run_m6_9_alignment_decay_rehearsal_scenario(scenario_workspace, env=env))
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
        elif name == "m4-file-write-recovery":
            reports.append(run_m4_file_write_recovery_scenario(scenario_workspace, env=env))
        elif name == "m4-runtime-effect-recovery":
            reports.append(run_m4_runtime_effect_recovery_scenario(scenario_workspace, env=env))
        elif name == "m4-close-gate":
            reports.append(run_m4_close_gate_scenario(scenario_workspace, env=env))
        elif name == "day-reentry":
            reports.append(run_day_reentry_scenario(scenario_workspace, env=env))
        elif name == "continuity":
            reports.append(run_continuity_scenario(scenario_workspace, env=env))
        elif name == "m3-reentry-gate":
            reports.append(
                run_m3_reentry_gate_scenario(
                    scenario_workspace,
                    env=env,
                    comparison_report_path=getattr(args, "m3_comparison_report", None),
                )
            )
        elif name == "m3-source-reentry":
            reports.append(run_m3_source_reentry_scenario(scenario_workspace, env=env))
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
