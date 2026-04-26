from pathlib import Path
import re
import shlex
import subprocess

from .config import MAX_COMMAND_OUTPUT_CHARS
from .errors import MewError
from .state import add_outbox_message, has_unread_outbox_message
from .test_discovery import convention_test_path_for_mew_source, normalize_work_path
from .timeutil import now_iso

TASK_KINDS = ("coding", "research", "personal", "admin", "unknown")

CODING_DECISIVE_KEYWORDS = (
    "bug",
    "cli",
    "code",
    "codex",
    "commit",
    "debug",
    "deploy",
    "feature",
    "implement",
    "integration",
    "json",
    "lint",
    "mew",
    "patch",
    "pr",
    "pytest",
    "refactor",
    "repo",
    "script",
    "sdk",
    "source",
    "typescript",
    "uv",
)

CODING_STRONG_KEYWORDS = (
    "agent",
    "api",
    "json",
    "source",
)

CODING_WEAK_KEYWORDS = (
    "build",
    "docs",
    "error",
    "fail",
    "failure",
    "fix",
    "interface",
    "package",
    "review",
    "test",
)

CODING_CONTEXT_KEYWORDS = (
    "ai-cli",
    "cli",
    "code",
    "codex",
    "git",
    "mew",
    "pytest",
    "python",
    "repo",
    "repository",
    "runtime",
    "script",
    "unittest",
    "uv",
)

CODING_PHRASES = (
    "agent run",
    "build error",
    "build failure",
    "ci failure",
    "code review",
    "command line",
    "failing test",
    "pull request",
    "review run",
    "test failure",
    "type error",
    "unit test",
)

RESEARCH_KEYWORDS = (
    "compare",
    "調査",
    "research",
    "investigate",
    "evaluate",
    "explore",
    "look up",
    "survey",
    "検証",
)

RESEARCH_PHRASES = (
    "look up",
)

ADMIN_KEYWORDS = (
    "bill",
    "document",
    "documents",
    "email",
    "invoice",
    "payment",
    "passport",
    "tax",
)

ADMIN_PHRASES = (
    "pay ",
    "申請",
    "支払い",
    "税",
    "請求",
)

PERSONAL_KEYWORDS = (
    "dentist",
    "doctor",
    "library",
    "appointment",
    "買う",
    "予約",
    "返却",
)

PERSONAL_PHRASES = (
    "book dentist",
    "買う",
    "予約",
    "返却",
)


def open_tasks(state):
    return [task for task in state["tasks"] if task.get("status") != "done"]

def normalize_task_kind(kind):
    if not isinstance(kind, str):
        return ""
    normalized = kind.strip().casefold()
    return normalized if normalized in TASK_KINDS else ""

def infer_task_kind(title="", description="", notes="", command="", cwd="", agent_prompt=""):
    primary_text = " ".join(
        value.strip()
        for value in (title or "", description or "")
        if isinstance(value, str) and value.strip()
    ).casefold()
    execution_text = " ".join(
        value.strip()
        for value in (command or "", cwd or "", agent_prompt or "")
        if isinstance(value, str) and value.strip()
    ).casefold()
    text = " ".join(
        value.strip()
        for value in (primary_text, execution_text)
        if isinstance(value, str) and value.strip()
    )
    primary_tokens = set(re.findall(r"[a-z0-9_.+-]+|[ぁ-んァ-ン一-龯]+", primary_text))
    tokens = set(re.findall(r"[a-z0-9_.+-]+|[ぁ-んァ-ン一-龯]+", text))
    if not text:
        return "unknown"
    if command or agent_prompt:
        return "coding"
    if any(keyword in primary_tokens for keyword in CODING_DECISIVE_KEYWORDS):
        return "coding"
    if any(phrase in primary_text for phrase in CODING_PHRASES):
        return "coding"
    if (
        any(keyword in primary_text for keyword in RESEARCH_PHRASES)
        or any(keyword in primary_text for keyword in ("調査", "検証"))
        or "調べる" in primary_text
        or any(keyword in primary_tokens for keyword in RESEARCH_KEYWORDS)
    ):
        return "research"
    if any(keyword in primary_text for keyword in ADMIN_PHRASES) or any(keyword in primary_tokens for keyword in ADMIN_KEYWORDS):
        return "admin"
    if any(keyword in primary_text for keyword in PERSONAL_PHRASES) or any(keyword in primary_tokens for keyword in PERSONAL_KEYWORDS):
        return "personal"
    if any(keyword in tokens for keyword in CODING_STRONG_KEYWORDS):
        return "coding"
    if any(keyword in tokens for keyword in CODING_WEAK_KEYWORDS) and any(
        keyword in tokens for keyword in CODING_CONTEXT_KEYWORDS
    ):
        return "coding"
    return "unknown"

def task_kind(task):
    explicit = normalize_task_kind(task.get("kind"))
    if explicit:
        return explicit
    return inferred_task_kind(task)

def inferred_task_kind(task):
    return infer_task_kind(
        task.get("title") or "",
        task.get("description") or "",
        task.get("notes") or "",
        task.get("command") or "",
        task.get("cwd") or "",
        task.get("agent_prompt") or "",
    )

def is_programmer_task(task):
    return task_kind(task) == "coding"

def task_kind_report(task):
    stored_kind = task.get("kind") or ""
    explicit = normalize_task_kind(stored_kind)
    inferred = inferred_task_kind(task)
    effective = explicit or inferred
    return {
        "id": task.get("id"),
        "title": task.get("title") or "",
        "status": task.get("status") or "",
        "stored_kind": stored_kind,
        "explicit_kind": explicit,
        "inferred_kind": inferred,
        "effective_kind": effective,
        "mismatch": bool(explicit and inferred not in ("", "unknown") and explicit != inferred),
    }

_SELECTOR_GOVERNANCE_TARGETS = (
    ("ROADMAP_STATUS.md", ("roadmap_status.md", "roadmap-status")),
    ("milestone close", ("milestone close", "milestone-close", "close milestone")),
    ("governance", ("governance",)),
    ("policy", ("policy",)),
    ("auth", ("auth",)),
    ("permissions", ("permission", "permissions")),
    ("skills", ("skill", "skills")),
)

def _selector_target_surface_text(task):
    task = task if isinstance(task, dict) else {}
    values = [
        task.get("title") or "",
    ]
    scope = task.get("scope") or {}
    if isinstance(scope, dict):
        raw_target_paths = scope.get("target_paths") or []
        if isinstance(raw_target_paths, str):
            raw_target_paths = [raw_target_paths]
        values.extend(str(path) for path in raw_target_paths if path)
    return "\n".join(str(value) for value in values if value).casefold()

def _selector_governance_blocked_reason(task):
    text = _selector_target_surface_text(task)
    for label, needles in _SELECTOR_GOVERNANCE_TARGETS:
        if any(needle in text for needle in needles):
            return f"selector-owned proposal cannot target {label}"
    return ""

def _selector_signal_refs(refs):
    if refs is None:
        return []
    if isinstance(refs, (list, tuple)):
        return list(refs)
    return [refs]


def _selector_reason_text(selector_reason):
    if not isinstance(selector_reason, dict):
        return selector_reason or ""
    lines = []
    for key in ("lane-dispatch", "reviewer-gated", "meta-loop", "expected-value"):
        value = selector_reason.get(key)
        if value:
            lines.append(f"{key}: {value}")
    return "\n".join(lines)


def _selector_lane_dispatch(candidate_task):
    scope = normalize_task_scope(candidate_task.get("scope") or {})
    target_paths = scope.get("target_paths") or []
    test_paths = [path for path in target_paths if path.startswith("tests/") and path.endswith(".py")]
    verifier = "focused verifier required before execution"
    if test_paths:
        verifier = f"uv run python -m unittest {test_paths[0][:-3].replace('/', '.')}"
    return {
        "authoritative_lane": "tiny",
        "helper_lanes": ["deliberation", "mirror"],
        "fallback_lane": "tiny",
        "verifier": verifier,
        "budget": "bounded read-only lane-dispatch proposal; no task dispatch before reviewer approval",
        "expected_value_rationale": (
            "tiny is the implementation default for the meta-loop; deliberation and mirror lanes "
            "supply helper evidence only when reviewer-gated escalation has positive expected-value"
        ),
        "repair_route": "M6.14 repair episode for structural implementation-lane failures",
        "reviewer_gate": "approval_required",
    }


def build_task_selector_proposal(
    previous_task,
    candidate_task,
    selector_reason,
    memory_signal_refs=None,
    failure_cluster_reason="",
    preference_signal_refs=None,
):
    previous_task = previous_task if isinstance(previous_task, dict) else {}
    candidate_task = candidate_task if isinstance(candidate_task, dict) else {}
    blocked_reason = _selector_governance_blocked_reason(candidate_task)
    return {
        "previous_task_id": previous_task.get("id"),
        "proposed_task_id": candidate_task.get("id"),
        "proposed_task_title": candidate_task.get("title") or "",
        "selector_reason": _selector_reason_text(selector_reason),
        "lane_dispatch": _selector_lane_dispatch(candidate_task),
        "approval_required": True,
        "memory_signal_refs": _selector_signal_refs(memory_signal_refs),
        "failure_cluster_reason": failure_cluster_reason or "",
        "preference_signal_refs": _selector_signal_refs(preference_signal_refs),
        "blocked": bool(blocked_reason),
        "blocked_reason": blocked_reason,
        "governance_violation": bool(blocked_reason),
    }

def normalize_task_scope(scope):
    if not isinstance(scope, dict):
        return {}
    raw_target_paths = scope.get("target_paths") or []
    if isinstance(raw_target_paths, str):
        raw_target_paths = [raw_target_paths]
    target_paths = []
    for item in raw_target_paths:
        path = normalize_work_path(item)
        if path and path not in target_paths:
            target_paths.append(path)
    if len(target_paths) != 2:
        return {}
    source_paths = [path for path in target_paths if convention_test_path_for_mew_source(path)]
    test_paths = [path for path in target_paths if path.startswith("tests/") and path.endswith(".py")]
    if len(source_paths) != 1 or len(test_paths) != 1:
        return {}
    source_path = source_paths[0]
    test_path = test_paths[0]
    if convention_test_path_for_mew_source(source_path) != test_path:
        return {}
    return {"target_paths": [source_path, test_path]}

def task_scope(task):
    task = task if isinstance(task, dict) else {}
    return normalize_task_scope(task.get("scope") or {})

def task_scope_target_paths(task):
    return list((task_scope(task).get("target_paths") or []))

def latest_task_plan_record(task):
    plans = task.get("plans") or []
    latest_id = task.get("latest_plan_id")
    if latest_id is not None:
        for plan in plans:
            if str(plan.get("id")) == str(latest_id):
                return plan
    return plans[-1] if plans else None

def task_needs_programmer_plan(task):
    return (
        is_programmer_task(task)
        and task.get("status") in ("todo", "ready")
        and not latest_task_plan_record(task)
    )

def task_sort_key(task):
    status_order = {"running": 0, "ready": 1, "todo": 2, "blocked": 3, "done": 4}
    priority_order = {"high": 0, "normal": 1, "low": 2}
    return (
        status_order.get(task.get("status"), 9),
        priority_order.get(task.get("priority"), 9),
        task.get("created_at") or "",
    )

def summarize_tasks(state):
    tasks = sorted(open_tasks(state), key=task_sort_key)
    if not tasks:
        return "No open tasks."

    counts = {}
    for task in tasks:
        counts[task["status"]] = counts.get(task["status"], 0) + 1

    count_text = ", ".join(f"{status}: {count}" for status, count in sorted(counts.items()))
    next_task = tasks[0]
    return (
        f"{len(tasks)} open task(s) ({count_text}). "
        f"Next candidate: #{next_task['id']} {next_task['title']}."
    )

def executable_tasks(state):
    return [
        task
        for task in sorted(open_tasks(state), key=task_sort_key)
        if task.get("status") == "ready"
        and task.get("auto_execute")
        and task.get("command")
    ]

def task_question(task):
    if task.get("status") == "todo":
        return f"Task #{task['id']} is todo. Should I make it ready, block it, or add execution details?"
    if task.get("status") == "ready" and not task.get("command") and not task.get("agent_backend"):
        kind = task_kind(task)
        if kind == "coding":
            return (
                f"Task #{task['id']} is ready coding work. "
                f"Open the coding cockpit with ./mew code {task['id']}, add constraints, or block it?"
            )
        if kind == "research":
            return f"Task #{task['id']} is ready research work. Should I assign it to an agent, add research criteria, or block it?"
        if kind in ("personal", "admin"):
            return f"Task #{task['id']} is ready. What concrete next step should I track, or should it stay as a reminder?"
        return f"Task #{task['id']} is ready but has no clear next action. Should I add execution details, assign an agent, or block it?"
    if task.get("status") == "blocked":
        return f"Task #{task['id']} is blocked. What information is needed to unblock it?"
    return ""

def passive_question(state):
    tasks = sorted(open_tasks(state), key=task_sort_key)
    if not tasks:
        return "What task should I track next?"

    return task_question(tasks[0])

def clip_output(text, limit=MAX_COMMAND_OUTPUT_CHARS):
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[:limit] + "\n... output truncated ..."

def resolve_task_cwd(task):
    cwd = task.get("cwd") or "."
    path = Path(cwd).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    return path

def execute_task_command(task, timeout):
    command = task.get("command") or ""
    if not command.strip():
        raise MewError("task has no command")

    args = shlex.split(command)
    if not args:
        raise MewError("task command is empty")

    cwd = resolve_task_cwd(task)
    if not cwd.exists() or not cwd.is_dir():
        raise MewError(f"task cwd does not exist: {cwd}")

    started_at = now_iso()
    result = subprocess.run(
        args,
        cwd=str(cwd),
        text=True,
        capture_output=True,
        timeout=timeout,
        shell=False,
    )
    finished_at = now_iso()

    return {
        "command": command,
        "cwd": str(cwd),
        "started_at": started_at,
        "finished_at": finished_at,
        "exit_code": result.returncode,
        "stdout": clip_output(result.stdout),
        "stderr": clip_output(result.stderr),
    }

def execute_one_autonomous_task(state, timeout):
    tasks = executable_tasks(state)
    if not tasks:
        question = passive_question(state)
        if question:
            if not has_unread_outbox_message(state, "question", question):
                add_outbox_message(state, "question", question)
        return 0

    task = tasks[0]
    current_time = now_iso()
    task["status"] = "running"
    task["updated_at"] = current_time
    add_outbox_message(
        state,
        "info",
        f"Executing task #{task['id']}: {task['title']} command={task['command']}",
    )

    try:
        run = execute_task_command(task, timeout)
        task.setdefault("runs", []).append(run)
        if run["exit_code"] == 0:
            task["status"] = "done"
            text = f"Task #{task['id']} completed successfully."
        else:
            task["status"] = "blocked"
            text = f"Task #{task['id']} failed with exit code {run['exit_code']}."
        if run.get("stdout"):
            text += f"\nstdout:\n{run['stdout']}"
        if run.get("stderr"):
            text += f"\nstderr:\n{run['stderr']}"
        add_outbox_message(state, "info" if run["exit_code"] == 0 else "warning", text)
    except (MewError, subprocess.TimeoutExpired) as exc:
        task.setdefault("runs", []).append(
            {
                "command": task.get("command"),
                "cwd": str(resolve_task_cwd(task)),
                "started_at": current_time,
                "finished_at": now_iso(),
                "exit_code": None,
                "stdout": "",
                "stderr": str(exc),
            }
        )
        task["status"] = "blocked"
        add_outbox_message(state, "warning", f"Task #{task['id']} execution failed: {exc}")

    task["updated_at"] = now_iso()
    return 1

def normalize_task_id(value):
    if value is None:
        return None
    try:
        return int(str(value).strip().lstrip("#"))
    except (TypeError, ValueError):
        return None

def task_by_id(state, task_id):
    normalized = normalize_task_id(task_id)
    if normalized is None:
        return None
    for task in state["tasks"]:
        if task.get("id") == normalized:
            return task
    return None

def execute_task_action(state, action, task_timeout):
    task = task_by_id(state, action.get("task_id"))
    if not task:
        add_outbox_message(state, "warning", f"Cannot execute missing task #{action.get('task_id')}")
        return 0
    if not (task.get("status") == "ready" and task.get("auto_execute") and task.get("command")):
        add_outbox_message(
            state,
            "warning",
            f"Refused to execute task #{task['id']}: task is not ready with command and auto_execute.",
            related_task_id=task["id"],
        )
        return 0

    current_time = now_iso()
    task["status"] = "running"
    task["updated_at"] = current_time
    add_outbox_message(
        state,
        "info",
        f"Executing task #{task['id']}: {task['title']} command={task['command']}",
        related_task_id=task["id"],
    )

    try:
        run = execute_task_command(task, task_timeout)
        task.setdefault("runs", []).append(run)
        if run["exit_code"] == 0:
            task["status"] = "done"
            text = f"Task #{task['id']} completed successfully."
        else:
            task["status"] = "blocked"
            text = f"Task #{task['id']} failed with exit code {run['exit_code']}."
        if run.get("stdout"):
            text += f"\nstdout:\n{run['stdout']}"
        if run.get("stderr"):
            text += f"\nstderr:\n{run['stderr']}"
        add_outbox_message(
            state,
            "info" if run["exit_code"] == 0 else "warning",
            text,
            related_task_id=task["id"],
        )
    except (MewError, subprocess.TimeoutExpired) as exc:
        task.setdefault("runs", []).append(
            {
                "command": task.get("command"),
                "cwd": str(resolve_task_cwd(task)),
                "started_at": current_time,
                "finished_at": now_iso(),
                "exit_code": None,
                "stdout": "",
                "stderr": str(exc),
            }
        )
        task["status"] = "blocked"
        add_outbox_message(
            state,
            "warning",
            f"Task #{task['id']} execution failed: {exc}",
            related_task_id=task["id"],
        )

    task["updated_at"] = now_iso()
    return 1

def format_task(task):
    return f"#{task['id']} [{task['status']}/{task['priority']}/{task_kind(task)}] {task['title']}"

def find_task(state, task_id):
    return task_by_id(state, task_id)
