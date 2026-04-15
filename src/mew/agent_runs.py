import json
import re
import subprocess
from pathlib import Path

from .config import AGENT_RUN_DIR
from .state import add_attention_item, add_outbox_message, next_id
from .timeutil import now_iso


DEFAULT_AGENT_BACKEND = "ai-cli"
DEFAULT_AGENT_MODEL = "codex-ultra"


def build_agent_prompt(task):
    prompt = task.get("agent_prompt") or task.get("description") or task.get("title") or ""
    return (
        "You are working for mew, a passive AI work companion.\n"
        "Complete the assigned task in the given repository. "
        "Make focused changes, verify them, and report changed files and results.\n\n"
        f"Task #{task['id']}: {task.get('title')}\n"
        f"Description: {task.get('description') or ''}\n"
        f"Notes: {task.get('notes') or ''}\n\n"
        f"User objective:\n{prompt}"
    )


def resolve_run_cwd(task, cwd_override=None):
    cwd = cwd_override or task.get("cwd") or "."
    path = Path(cwd).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    return path


def create_agent_run(
    state,
    task,
    backend=None,
    model=None,
    cwd=None,
    prompt=None,
    purpose="implementation",
    plan_id=None,
    parent_run_id=None,
    review_of_run_id=None,
    resume_session_id=None,
):
    current_time = now_iso()
    run = {
        "id": next_id(state, "agent_run"),
        "task_id": task["id"],
        "purpose": purpose,
        "plan_id": plan_id,
        "parent_run_id": parent_run_id,
        "review_of_run_id": review_of_run_id,
        "review_status": "",
        "followup_task_id": None,
        "followup_processed_at": None,
        "backend": backend or task.get("agent_backend") or DEFAULT_AGENT_BACKEND,
        "model": model or task.get("agent_model") or DEFAULT_AGENT_MODEL,
        "cwd": str(resolve_run_cwd(task, cwd)),
        "prompt": prompt or build_agent_prompt(task),
        "prompt_file": "",
        "status": "created",
        "external_pid": None,
        "resume_session_id": resume_session_id or "",
        "session_id": None,
        "command": [],
        "started_at": None,
        "finished_at": None,
        "stdout": "",
        "stderr": "",
        "result": "",
        "supervisor_verification": None,
        "created_at": current_time,
        "updated_at": current_time,
    }
    state["agent_runs"].append(run)
    if purpose == "implementation":
        task["agent_run_id"] = run["id"]
    task["updated_at"] = current_time
    return run


def build_ai_cli_run_command(run):
    command = [
        "ai-cli",
        "run",
        "--cwd",
        run["cwd"],
        "--model",
        run["model"],
    ]
    if run.get("prompt_file"):
        command.extend(["--prompt-file", run["prompt_file"]])
    else:
        command.extend(["--prompt", run["prompt"]])
    if run.get("resume_session_id"):
        command.extend(["--session-id", run["resume_session_id"]])
    return command


def ensure_agent_run_prompt_file(run):
    prompt_file = run.get("prompt_file")
    if prompt_file:
        return Path(prompt_file)

    AGENT_RUN_DIR.mkdir(parents=True, exist_ok=True)
    path = (AGENT_RUN_DIR / f"run-{run['id']}-prompt.md").resolve()
    path.write_text(run.get("prompt") or "", encoding="utf-8")
    run["prompt_file"] = str(path)
    run["updated_at"] = now_iso()
    return path


def parse_ai_cli_pid(text):
    stripped = text.strip()
    if not stripped:
        return None
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        data = None
    if isinstance(data, dict):
        for key in ("pid", "process_id", "id"):
            value = data.get(key)
            if isinstance(value, int):
                return value
            if isinstance(value, str) and value.isdigit():
                return int(value)

    match = re.search(r"\bpid\b\D+(\d+)", text, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None


def _find_first_string_by_key(value, keys):
    if isinstance(value, dict):
        for key in keys:
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
        for child in value.values():
            found = _find_first_string_by_key(child, keys)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_first_string_by_key(child, keys)
            if found:
                return found
    return None


def extract_ai_cli_session_id(text):
    stripped = (text or "").strip()
    if not stripped:
        return None
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    return _find_first_string_by_key(data, ("session_id", "sessionId"))


def _same_id(left, right):
    return left is not None and right is not None and str(left) == str(right)


def sync_task_with_agent_run(state, run, current_time=None):
    if run.get("purpose", "implementation") != "implementation":
        return None

    current_time = current_time or now_iso()
    task = None
    for candidate in state.get("tasks", []):
        if _same_id(candidate.get("id"), run.get("task_id")):
            task = candidate
            break
    if not task:
        return None

    if run.get("status") in ("created", "running"):
        task["status"] = "running"
    elif run.get("status") == "completed":
        task["status"] = "done"
    elif run.get("status") == "failed":
        task["status"] = "blocked"
    task["agent_run_id"] = run["id"]
    task["updated_at"] = current_time
    return task


def start_agent_run(state, run):
    if run["backend"] != "ai-cli":
        raise ValueError(f"unsupported agent backend: {run['backend']}")

    ensure_agent_run_prompt_file(run)
    command = build_ai_cli_run_command(run)
    current_time = now_iso()
    try:
        result = subprocess.run(command, text=True, capture_output=True, shell=False)
    except OSError as exc:
        run["command"] = command
        run["stderr"] = str(exc)
        run["started_at"] = current_time
        run["updated_at"] = now_iso()
        run["finished_at"] = run["updated_at"]
        run["status"] = "failed"
        sync_task_with_agent_run(state, run, run["updated_at"])
        add_outbox_message(
            state,
            "warning",
            f"Agent run #{run['id']} failed to start: {exc}",
            related_task_id=run["task_id"],
            agent_run_id=run["id"],
        )
        return run
    output = result.stdout.strip()
    error = result.stderr.strip()
    run["command"] = command
    run["stdout"] = output
    run["stderr"] = error
    run["session_id"] = extract_ai_cli_session_id(output) or run.get("session_id")
    run["started_at"] = current_time
    run["updated_at"] = now_iso()

    if result.returncode != 0:
        run["status"] = "failed"
        run["finished_at"] = run["updated_at"]
        sync_task_with_agent_run(state, run, run["updated_at"])
        add_outbox_message(
            state,
            "warning",
            f"Agent run #{run['id']} failed to start.\n{error or output}",
            related_task_id=run["task_id"],
            agent_run_id=run["id"],
        )
        return run

    run["external_pid"] = parse_ai_cli_pid(output)
    if not run["external_pid"]:
        run["status"] = "failed"
        run["finished_at"] = run["updated_at"]
        run["result"] = output or error or "could not parse ai-cli pid"
        sync_task_with_agent_run(state, run, run["updated_at"])
        add_outbox_message(
            state,
            "warning",
            f"Agent run #{run['id']} failed to start: could not parse ai-cli pid.\n{run['result']}",
            related_task_id=run["task_id"],
            agent_run_id=run["id"],
        )
        return run
    run["status"] = "running"
    sync_task_with_agent_run(state, run, run["updated_at"])
    add_attention_item(
        state,
        "agent_run",
        f"Agent run #{run['id']} is running",
        f"Task #{run['task_id']} is running on {run['model']}.",
        related_task_id=run["task_id"],
        agent_run_id=run["id"],
        priority="normal",
    )
    add_outbox_message(
        state,
        "info",
        f"Started agent run #{run['id']} for task #{run['task_id']} with {run['model']}.",
        related_task_id=run["task_id"],
        agent_run_id=run["id"],
    )
    return run


def find_agent_run(state, run_id):
    for run in state["agent_runs"]:
        if str(run.get("id")) == str(run_id):
            return run
    return None

def resolve_agent_run_attention(state, run, current_time):
    for item in state["attention"]["items"]:
        if _same_id(item.get("agent_run_id"), run.get("id")) and item.get("status") == "open":
            item["status"] = "resolved"
            item["resolved_at"] = current_time
            item["updated_at"] = current_time


def parse_ai_cli_status(text):
    stripped = text.strip()
    if not stripped:
        return None
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None

    return _find_first_status(data)


def _find_first_status(value):
    if isinstance(value, dict):
        for key in ("status", "state"):
            candidate = value.get(key)
            if candidate in ("created", "running", "completed", "failed"):
                return candidate
        for child in value.values():
            found = _find_first_status(child)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_first_status(child)
            if found:
                return found
    return None


def get_agent_run_result(state, run, verbose=False):
    if run["backend"] != "ai-cli":
        raise ValueError(f"unsupported agent backend: {run['backend']}")
    if not run.get("external_pid"):
        raise ValueError(f"agent run #{run['id']} does not have an external pid")

    command = ["ai-cli", "result", str(run["external_pid"])]
    if verbose:
        command.append("--verbose")
    try:
        result = subprocess.run(command, text=True, capture_output=True, shell=False)
    except OSError as exc:
        current_time = now_iso()
        run["stderr"] = str(exc)
        run["result"] = run["stderr"]
        run["updated_at"] = current_time
        run["status"] = "failed"
        run["finished_at"] = current_time
        sync_task_with_agent_run(state, run, current_time)
        resolve_agent_run_attention(state, run, current_time)
        add_outbox_message(
            state,
            "warning",
            f"Agent run #{run['id']} result failed: {exc}",
            related_task_id=run["task_id"],
            agent_run_id=run["id"],
        )
        return run

    current_time = now_iso()
    run["stdout"] = result.stdout.strip()
    run["stderr"] = result.stderr.strip()
    run["session_id"] = extract_ai_cli_session_id(run["stdout"]) or run.get("session_id")
    run["updated_at"] = current_time
    if result.returncode != 0:
        run["status"] = "failed"
        run["finished_at"] = current_time
        run["result"] = run["stderr"] or run["stdout"]
        sync_task_with_agent_run(state, run, current_time)
        add_outbox_message(
            state,
            "warning",
            f"Agent run #{run['id']} result failed.\n{run['result']}",
            related_task_id=run["task_id"],
            agent_run_id=run["id"],
        )
        resolve_agent_run_attention(state, run, current_time)
        return run

    parsed_status = parse_ai_cli_status(run["stdout"])
    if parsed_status:
        run["status"] = parsed_status
        run["result"] = run["stdout"]
    else:
        run["status"] = "failed"
        run["finished_at"] = current_time
        run["result"] = (run["stdout"] or "ai-cli result returned no parseable status").strip()
        if run["result"]:
            run["result"] += "\n"
        run["result"] += "(mew: could not parse ai-cli result status)"
        sync_task_with_agent_run(state, run, current_time)
        resolve_agent_run_attention(state, run, current_time)
        add_outbox_message(
            state,
            "warning",
            f"Agent run #{run['id']} result had no parseable status.\n{run['result']}",
            related_task_id=run["task_id"],
            agent_run_id=run["id"],
        )
        return run
    if run["status"] in ("completed", "failed"):
        run["finished_at"] = run.get("finished_at") or current_time
        resolve_agent_run_attention(state, run, current_time)
    sync_task_with_agent_run(state, run, current_time)
    return run


def wait_agent_run(state, run, timeout=None):
    if run["backend"] != "ai-cli":
        raise ValueError(f"unsupported agent backend: {run['backend']}")
    if not run.get("external_pid"):
        raise ValueError(f"agent run #{run['id']} does not have an external pid")

    command = ["ai-cli", "wait", str(run["external_pid"])]
    if timeout is not None:
        command.extend(["--timeout", str(timeout)])
    try:
        result = subprocess.run(command, text=True, capture_output=True, shell=False)
    except OSError as exc:
        current_time = now_iso()
        run["stderr"] = str(exc)
        run["result"] = run["stderr"]
        run["updated_at"] = current_time
        run["status"] = "failed"
        run["finished_at"] = current_time
        sync_task_with_agent_run(state, run, current_time)
        resolve_agent_run_attention(state, run, current_time)
        add_outbox_message(
            state,
            "warning",
            f"Agent run #{run['id']} wait failed: {exc}",
            related_task_id=run["task_id"],
            agent_run_id=run["id"],
        )
        return run
    current_time = now_iso()
    run["stdout"] = result.stdout.strip()
    run["stderr"] = result.stderr.strip()
    run["session_id"] = extract_ai_cli_session_id(run["stdout"]) or run.get("session_id")
    run["updated_at"] = current_time
    if result.returncode == 0:
        run["status"] = "completed"
        run["finished_at"] = current_time
        run["result"] = run["stdout"]
        message_type = "info"
        text = f"Agent run #{run['id']} completed for task #{run['task_id']}."
    else:
        run["status"] = "failed"
        run["finished_at"] = current_time
        run["result"] = run["stderr"] or run["stdout"]
        message_type = "warning"
        text = f"Agent run #{run['id']} failed for task #{run['task_id']}."
    if run["result"]:
        text += f"\n{run['result']}"
    add_outbox_message(
        state,
        message_type,
        text,
        related_task_id=run["task_id"],
        agent_run_id=run["id"],
    )
    sync_task_with_agent_run(state, run, current_time)
    resolve_agent_run_attention(state, run, current_time)
    return run
