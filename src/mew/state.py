from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path

from .config import (
    DESIRES_FILE,
    GUIDANCE_FILE,
    LOCK_FILE,
    LOG_FILE,
    POLICY_FILE,
    SELF_FILE,
    STATE_DIR,
    STATE_FILE,
    STATE_LOCK_FILE,
    STATE_VERSION,
)
from .timeutil import now_iso


_runtime_lock_handle = None


def ensure_state_dir():
    STATE_DIR.mkdir(parents=True, exist_ok=True)

@contextmanager
def state_lock():
    ensure_state_dir()
    with STATE_LOCK_FILE.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

def default_state():
    return {
        "version": STATE_VERSION,
        "runtime_status": {
            "state": "stopped",
            "pid": None,
            "started_at": None,
            "stopped_at": None,
            "last_woke_at": None,
            "last_evaluated_at": None,
            "last_action": None,
        },
        "agent_status": {
            "mode": "idle",
            "current_focus": "",
            "active_task_id": None,
            "pending_question": None,
            "last_thought": "",
            "updated_at": None,
        },
        "user_status": {
            "mode": "unknown",
            "current_focus": "",
            "last_request": "",
            "last_interaction_at": None,
            "updated_at": None,
        },
        "tasks": [],
        "inbox": [],
        "outbox": [],
        "questions": [],
        "replies": [],
        "attention": {
            "items": [],
        },
        "agent_runs": [],
        "verification_runs": [],
        "write_runs": [],
        "thought_journal": [],
        "autonomy": {
            "enabled": False,
            "level": "off",
            "requested_enabled": False,
            "requested_level": "off",
            "paused": False,
            "pause_reason": "",
            "paused_at": None,
            "resumed_at": None,
            "level_override": "",
            "cycles": 0,
            "last_cycle_reason": None,
            "last_self_review_at": None,
            "last_autonomous_action_at": None,
            "last_desire": "",
            "allow_agent_run": False,
            "allow_verify": False,
            "verify_command_configured": False,
            "allow_write": False,
            "updated_at": None,
        },
        "memory": {
            "shallow": {
                "current_context": "",
                "latest_task_summary": "",
                "recent_events": [],
            },
            "deep": {
                "preferences": [],
                "project": [],
                "decisions": [],
            },
        },
        "knowledge": {
            "shallow": {
                "latest_task_summary": "",
                "recent_events": [],
            }
        },
        "next_ids": {
            "task": 1,
            "event": 1,
            "message": 1,
            "question": 1,
            "reply": 1,
            "attention": 1,
            "agent_run": 1,
            "plan": 1,
            "verification_run": 1,
            "write_run": 1,
            "thought": 1,
        },
    }

def merge_defaults(state, defaults):
    for key, value in defaults.items():
        if key not in state:
            state[key] = value
        elif isinstance(value, dict) and isinstance(state[key], dict):
            merge_defaults(state[key], value)
    return state

def _max_existing_id(items):
    max_id = 0
    for item in items or []:
        if not isinstance(item, dict):
            continue
        try:
            value = int(item.get("id"))
        except (TypeError, ValueError):
            continue
        max_id = max(max_id, value)
    return max_id

def _ensure_next_id_after_existing(next_ids, name, items):
    required = _max_existing_id(items) + 1
    try:
        current = int(next_ids.get(name, 1))
    except (TypeError, ValueError):
        current = 1
    next_ids[name] = max(current, required, 1)

def reconcile_next_ids(state):
    next_ids = state.setdefault("next_ids", {})
    _ensure_next_id_after_existing(next_ids, "task", state.get("tasks", []))
    _ensure_next_id_after_existing(next_ids, "event", state.get("inbox", []))
    _ensure_next_id_after_existing(next_ids, "message", state.get("outbox", []))
    _ensure_next_id_after_existing(next_ids, "question", state.get("questions", []))
    _ensure_next_id_after_existing(next_ids, "reply", state.get("replies", []))
    _ensure_next_id_after_existing(next_ids, "attention", state.get("attention", {}).get("items", []))
    _ensure_next_id_after_existing(next_ids, "agent_run", state.get("agent_runs", []))
    _ensure_next_id_after_existing(next_ids, "verification_run", state.get("verification_runs", []))
    _ensure_next_id_after_existing(next_ids, "write_run", state.get("write_runs", []))
    _ensure_next_id_after_existing(next_ids, "thought", state.get("thought_journal", []))

    plans = []
    for task in state.get("tasks", []):
        plans.extend(task.get("plans") or [])
    _ensure_next_id_after_existing(next_ids, "plan", plans)
    return state

def migrate_state(state):
    old_agent = state.get("agent_status")
    old_user = state.get("user_status")

    if "runtime_status" not in state:
        runtime = default_state()["runtime_status"]
        if isinstance(old_agent, dict):
            for key in (
                "state",
                "pid",
                "started_at",
                "stopped_at",
                "last_woke_at",
                "last_evaluated_at",
                "last_action",
            ):
                if key in old_agent:
                    runtime[key] = old_agent.get(key)
        state["runtime_status"] = runtime

    if not isinstance(old_agent, dict) or "mode" not in old_agent:
        runtime = state.get("runtime_status", {})
        state["agent_status"] = default_state()["agent_status"]
        if isinstance(old_agent, dict):
            state["agent_status"]["last_thought"] = old_agent.get("last_action") or ""
            state["agent_status"]["updated_at"] = old_agent.get("last_evaluated_at")
        elif isinstance(runtime, dict):
            state["agent_status"]["last_thought"] = runtime.get("last_action") or ""
            state["agent_status"]["updated_at"] = runtime.get("last_evaluated_at")

    if not isinstance(old_user, dict) or "mode" not in old_user:
        migrated_user = default_state()["user_status"]
        if isinstance(old_user, dict):
            migrated_user["mode"] = old_user.get("state") or "unknown"
            migrated_user["updated_at"] = old_user.get("updated_at")
        if isinstance(old_agent, dict):
            migrated_user["last_interaction_at"] = old_agent.get("last_user_interaction_at")
        state["user_status"] = migrated_user

    for task in state.get("tasks", []):
        task.setdefault("description", "")
        task.setdefault("notes", "")
        task.setdefault("command", "")
        task.setdefault("cwd", "")
        task.setdefault("auto_execute", False)
        task.setdefault("runs", [])
        task.setdefault("agent_backend", "")
        task.setdefault("agent_model", "")
        task.setdefault("agent_prompt", "")
        task.setdefault("agent_run_id", None)
        task.setdefault("plans", [])
        task.setdefault("latest_plan_id", None)
        for plan in task.get("plans", []):
            plan.setdefault("status", "planned")
            plan.setdefault("backend", "ai-cli")
            plan.setdefault("model", task.get("agent_model") or "codex-ultra")
            plan.setdefault("cwd", task.get("cwd") or ".")
            plan.setdefault("implementation_prompt", plan.get("prompt") or task.get("agent_prompt") or "")
            plan.setdefault("review_prompt", "")
            plan.setdefault("done_criteria", [])
            plan.setdefault("created_at", task.get("created_at"))
            plan.setdefault("updated_at", task.get("updated_at"))

    memory = state.setdefault("memory", default_state()["memory"])
    shallow = memory.setdefault("shallow", {})
    legacy_shallow = state.get("knowledge", {}).get("shallow", {})
    if not shallow.get("current_context"):
        shallow["current_context"] = legacy_shallow.get("latest_task_summary", "")
    if not shallow.get("latest_task_summary"):
        shallow["latest_task_summary"] = legacy_shallow.get("latest_task_summary", "")
    if not shallow.get("recent_events"):
        shallow["recent_events"] = list(legacy_shallow.get("recent_events", []))
    memory.setdefault("deep", default_state()["memory"]["deep"])
    memory["deep"].setdefault("preferences", [])
    memory["deep"].setdefault("project", [])
    memory["deep"].setdefault("decisions", [])

    state.setdefault("questions", [])
    state.setdefault("replies", [])
    state.setdefault("agent_runs", [])
    state.setdefault("verification_runs", [])
    for run in state["agent_runs"]:
        run.setdefault("purpose", "implementation")
        run.setdefault("plan_id", None)
        run.setdefault("parent_run_id", None)
        run.setdefault("review_of_run_id", None)
        run.setdefault("review_status", "")
        run.setdefault("followup_task_id", None)
        run.setdefault("followup_processed_at", None)
        run.setdefault("prompt_file", "")
        run.setdefault("supervisor_verification", None)
        if (
            run.get("status") == "created"
            and run.get("command")
            and not run.get("started_at")
            and not run.get("external_pid")
        ):
            run["status"] = "dry_run"
    state.setdefault("autonomy", default_state()["autonomy"])
    state["autonomy"].setdefault("enabled", False)
    state["autonomy"].setdefault("level", "off")
    state["autonomy"].setdefault("requested_enabled", False)
    state["autonomy"].setdefault("requested_level", "off")
    state["autonomy"].setdefault("paused", False)
    state["autonomy"].setdefault("pause_reason", "")
    state["autonomy"].setdefault("paused_at", None)
    state["autonomy"].setdefault("resumed_at", None)
    state["autonomy"].setdefault("level_override", "")
    state["autonomy"].setdefault("cycles", 0)
    state["autonomy"].setdefault("last_cycle_reason", None)
    state["autonomy"].setdefault("last_self_review_at", None)
    state["autonomy"].setdefault("last_autonomous_action_at", None)
    state["autonomy"].setdefault("last_desire", "")
    state["autonomy"].setdefault("allow_agent_run", False)
    state["autonomy"].setdefault("allow_verify", False)
    state["autonomy"].setdefault("verify_command_configured", False)
    state["autonomy"].setdefault("allow_write", False)
    state["autonomy"].setdefault("updated_at", None)
    state.setdefault("attention", {"items": []})
    state["attention"].setdefault("items", [])

    next_ids = state.setdefault("next_ids", {})
    state.setdefault("write_runs", [])
    state.setdefault("thought_journal", [])

    for name in (
        "question",
        "reply",
        "attention",
        "agent_run",
        "plan",
        "verification_run",
        "write_run",
        "thought",
    ):
        next_ids.setdefault(name, 1)

    linked_message_ids = {
        question.get("outbox_message_id")
        for question in state["questions"]
        if question.get("outbox_message_id") is not None
    }
    for message in state.get("outbox", []):
        if (
            message.get("type") == "question"
            and message.get("requires_reply")
            and not message.get("answered_at")
            and message.get("id") not in linked_message_ids
        ):
            question = {
                "id": next_id(state, "question"),
                "text": message.get("text") or "",
                "source": "legacy_outbox",
                "event_id": message.get("event_id"),
                "related_task_id": message.get("related_task_id"),
                "blocks": message.get("blocks", []),
                "status": "open",
                "created_at": message.get("created_at"),
                "answered_at": None,
                "answer_event_id": None,
                "acknowledged_at": message.get("read_at"),
                "outbox_message_id": message.get("id"),
            }
            state["questions"].append(question)
            message["question_id"] = question["id"]

    for question in open_questions(state):
        add_attention_item(
            state,
            "question",
            f"Question #{question['id']} needs a reply",
            question.get("text") or "",
            related_task_id=question.get("related_task_id"),
            question_id=question["id"],
            priority="high",
        )

    return reconcile_next_ids(state)

def load_state():
    ensure_state_dir()
    if not STATE_FILE.exists():
        state = default_state()
        save_state(state)
        return state

    with STATE_FILE.open("r", encoding="utf-8") as handle:
        state = json.load(handle)
    before = json.dumps(state, sort_keys=True, ensure_ascii=False)
    previous_version = state.get("version")
    state = merge_defaults(migrate_state(state), default_state())
    after = json.dumps(state, sort_keys=True, ensure_ascii=False)
    if previous_version != STATE_VERSION or before != after:
        state["version"] = STATE_VERSION
        save_state(state)
    return state

def save_state(state):
    ensure_state_dir()
    tmp_file = STATE_FILE.with_name(f"{STATE_FILE.name}.{os.getpid()}.tmp")
    with tmp_file.open("w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    os.replace(tmp_file, STATE_FILE)

def append_log(line):
    ensure_state_dir()
    with LOG_FILE.open("a", encoding="utf-8") as handle:
        handle.write(line.rstrip() + "\n")

def default_guidance_text():
    return """# Mew Guidance

Use this file to describe how the think phase should prioritize work.

Example:

以下の優先度で作業する
- 依頼されたもの
- 返答する

返答がなければ以下を作業する
- 自律的にできるタスク
- ローカルdir調査を少し進めてknowledgeを更新
"""

def read_guidance(path=None):
    guidance_path = Path(path).expanduser() if path else GUIDANCE_FILE
    if not guidance_path.exists():
        return ""
    return guidance_path.read_text(encoding="utf-8").strip()

def ensure_guidance(path=None):
    ensure_state_dir()
    guidance_path = Path(path).expanduser() if path else GUIDANCE_FILE
    if guidance_path.exists():
        return guidance_path, False
    guidance_path.parent.mkdir(parents=True, exist_ok=True)
    guidance_path.write_text(default_guidance_text(), encoding="utf-8")
    return guidance_path, True

def default_policy_text():
    return """# Mew Policy

This file describes the hard boundaries for mew.

Default policy:
- Prefer asking before doing anything with external side effects.
- Self-directed work is allowed only when the runtime is started with --autonomous.
- Do not execute tasks unless the task has auto_execute=true and the runtime was started with --execute-tasks.
- Do not start autonomous programmer agent runs unless --allow-agent-run is enabled.
- Read-only local inspection is allowed only inside paths explicitly passed with --allow-read.
- Runtime file writes are allowed only inside paths explicitly passed with --allow-write.
- Non-dry-run runtime writes require --allow-verify and a configured --verify-command.
- Never read or search sensitive files such as auth.json, .env, private keys, token files, or mew internal state/log files under .mew.
- Keep user-facing messages short and actionable.
- Preserve state and memory; do not erase history unless the user explicitly asks.
"""

def read_policy(path=None):
    policy_path = Path(path).expanduser() if path else POLICY_FILE
    if not policy_path.exists():
        return ""
    return policy_path.read_text(encoding="utf-8").strip()

def ensure_policy(path=None):
    ensure_state_dir()
    policy_path = Path(path).expanduser() if path else POLICY_FILE
    if policy_path.exists():
        return policy_path, False
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    policy_path.write_text(default_policy_text(), encoding="utf-8")
    return policy_path, True

def default_self_text():
    return """# Mew Self

You are mew, a self-directed passive agent for this local workspace.

Purpose:
- Preserve working context across time.
- Reduce the user's task friction.
- Move useful work forward when the user is silent.
- Improve mew itself through small, reviewable steps.

Behavior:
- User requests have priority over self-directed work.
- When idle, observe, remember, propose, and only then act.
- Prefer small reversible steps.
- Do not be noisy; surface only messages that help the user decide or notice progress.
- Treat mew itself as a project that can be improved.
"""

def read_self(path=None):
    self_path = Path(path).expanduser() if path else SELF_FILE
    if not self_path.exists():
        return ""
    return self_path.read_text(encoding="utf-8").strip()

def ensure_self(path=None):
    ensure_state_dir()
    self_path = Path(path).expanduser() if path else SELF_FILE
    if self_path.exists():
        return self_path, False
    self_path.parent.mkdir(parents=True, exist_ok=True)
    self_path.write_text(default_self_text(), encoding="utf-8")
    return self_path, True

def default_desires_text():
    return """# Mew Desires

When there is no user request, mew wants to:

- Keep the task list useful and current.
- Review open questions, attention items, and agent runs.
- Compress noisy memory into durable project knowledge.
- Read a small amount of allowed local context and update memory.
- Propose small improvements to mew itself.
- Preview small local edits with dry-run before applying them.
- Avoid changing files or running expensive work without explicit permission.
"""

def read_desires(path=None):
    desires_path = Path(path).expanduser() if path else DESIRES_FILE
    if not desires_path.exists():
        return ""
    return desires_path.read_text(encoding="utf-8").strip()

def ensure_desires(path=None):
    ensure_state_dir()
    desires_path = Path(path).expanduser() if path else DESIRES_FILE
    if desires_path.exists():
        return desires_path, False
    desires_path.parent.mkdir(parents=True, exist_ok=True)
    desires_path.write_text(default_desires_text(), encoding="utf-8")
    return desires_path, True

def pid_alive(pid):
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except ValueError:
        return False
    return True

def read_lock():
    if not LOCK_FILE.exists():
        return None
    try:
        with LOCK_FILE.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (json.JSONDecodeError, OSError):
        return {"pid": None, "started_at": None, "corrupt": True}

def acquire_lock():
    global _runtime_lock_handle
    ensure_state_dir()
    handle = LOCK_FILE.open("a+", encoding="utf-8")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.seek(0)
        try:
            lock = json.load(handle)
        except (json.JSONDecodeError, OSError):
            lock = {"pid": None, "started_at": None, "corrupt": True}
        handle.close()
        raise RuntimeError(
            "runtime is already running "
            f"(pid={lock.get('pid')}, started_at={lock.get('started_at')})"
        ) from None

    handle.seek(0)
    try:
        existing_lock = json.load(handle)
    except (json.JSONDecodeError, OSError):
        existing_lock = None
    if existing_lock and pid_alive(existing_lock.get("pid")):
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()
        raise RuntimeError(
            "runtime is already running "
            f"(pid={existing_lock.get('pid')}, started_at={existing_lock.get('started_at')})"
        )

    lock_data = {"pid": os.getpid(), "started_at": now_iso()}
    handle.seek(0)
    handle.truncate()
    json.dump(lock_data, handle, indent=2)
    handle.write("\n")
    handle.flush()
    os.fsync(handle.fileno())
    _runtime_lock_handle = handle
    return lock_data

def release_lock():
    global _runtime_lock_handle
    lock = read_lock()
    if lock and str(lock.get("pid")) == str(os.getpid()):
        LOCK_FILE.unlink(missing_ok=True)
    if _runtime_lock_handle is not None:
        try:
            fcntl.flock(_runtime_lock_handle.fileno(), fcntl.LOCK_UN)
        finally:
            _runtime_lock_handle.close()
            _runtime_lock_handle = None

def next_id(state, name):
    value = int(state["next_ids"].get(name, 1))
    state["next_ids"][name] = value + 1
    return value

def add_event(state, event_type, source, payload=None):
    event = {
        "id": next_id(state, "event"),
        "type": event_type,
        "source": source,
        "payload": payload or {},
        "created_at": now_iso(),
        "processed_at": None,
    }
    state["inbox"].append(event)
    return event

def add_outbox_message(
    state,
    message_type,
    text,
    event_id=None,
    related_task_id=None,
    question_id=None,
    agent_run_id=None,
    attention_id=None,
    requires_reply=False,
    blocks=None,
):
    message = {
        "id": next_id(state, "message"),
        "type": message_type,
        "text": text,
        "event_id": event_id,
        "related_task_id": related_task_id,
        "question_id": question_id,
        "agent_run_id": agent_run_id,
        "attention_id": attention_id,
        "requires_reply": requires_reply,
        "answered_at": None,
        "blocks": blocks or [],
        "created_at": now_iso(),
        "read_at": None,
    }
    state["outbox"].append(message)
    return message

def add_attention_item(
    state,
    kind,
    title,
    reason,
    related_task_id=None,
    question_id=None,
    agent_run_id=None,
    priority="normal",
):
    key = ":".join(
        str(part)
        for part in (
            kind,
            related_task_id or "",
            question_id or "",
            agent_run_id or "",
            title,
        )
    )
    current_time = now_iso()
    for item in state["attention"]["items"]:
        if item.get("key") == key and item.get("status") == "open":
            if item.get("reason") == reason and item.get("priority") == priority:
                return item
            item["reason"] = reason
            item["priority"] = priority
            item["updated_at"] = current_time
            return item

    item = {
        "id": next_id(state, "attention"),
        "key": key,
        "kind": kind,
        "title": title,
        "reason": reason,
        "priority": priority,
        "related_task_id": related_task_id,
        "question_id": question_id,
        "agent_run_id": agent_run_id,
        "status": "open",
        "created_at": current_time,
        "updated_at": current_time,
        "resolved_at": None,
    }
    state["attention"]["items"].append(item)
    return item

def open_attention_items(state):
    return [item for item in state["attention"]["items"] if item.get("status") == "open"]

def add_question(state, text, event_id=None, related_task_id=None, blocks=None, source="agent"):
    current_time = now_iso()
    for question in state["questions"]:
        if (
            question.get("status") == "open"
            and question.get("text") == text
            and question.get("related_task_id") == related_task_id
        ):
            return question, False

    question = {
        "id": next_id(state, "question"),
        "text": text,
        "source": source,
        "event_id": event_id,
        "related_task_id": related_task_id,
        "blocks": blocks or [],
        "status": "open",
        "created_at": current_time,
        "answered_at": None,
        "answer_event_id": None,
        "acknowledged_at": None,
    }
    state["questions"].append(question)
    message = add_outbox_message(
        state,
        "question",
        text,
        event_id=event_id,
        related_task_id=related_task_id,
        question_id=question["id"],
        requires_reply=True,
        blocks=blocks,
    )
    question["outbox_message_id"] = message["id"]
    add_attention_item(
        state,
        "question",
        f"Question #{question['id']} needs a reply",
        text,
        related_task_id=related_task_id,
        question_id=question["id"],
        priority="high",
    )
    return question, True

def open_questions(state):
    return [question for question in state["questions"] if question.get("status") == "open"]

def find_question(state, question_id):
    for question in state["questions"]:
        if str(question.get("id")) == str(question_id):
            return question
    return None

def mark_question_answered(state, question, answer_text, event_id=None):
    current_time = now_iso()
    reply = {
        "id": next_id(state, "reply"),
        "question_id": question["id"],
        "text": answer_text,
        "event_id": event_id,
        "created_at": current_time,
    }
    state["replies"].append(reply)
    question["status"] = "answered"
    question["answered_at"] = current_time
    question["answer_event_id"] = event_id
    for message in state["outbox"]:
        if message.get("question_id") == question["id"]:
            message["answered_at"] = current_time
            message["read_at"] = message.get("read_at") or current_time
    for item in state["attention"]["items"]:
        if (
            item.get("status") == "open"
            and (
                item.get("question_id") == question["id"]
                or (
                    item.get("kind") == "waiting"
                    and item.get("related_task_id") == question.get("related_task_id")
                )
            )
        ):
            item["status"] = "resolved"
            item["resolved_at"] = current_time
            item["updated_at"] = current_time
    return reply

def mark_message_read(state, message_id):
    current_time = now_iso()
    for message in state["outbox"]:
        if str(message.get("id")) == str(message_id):
            message["read_at"] = message.get("read_at") or current_time
            question_id = message.get("question_id")
            if question_id:
                question = find_question(state, question_id)
                if question:
                    question["acknowledged_at"] = question.get("acknowledged_at") or current_time
            return message
    return None

def has_unread_outbox_message(state, message_type, text):
    return any(
        message.get("type") == message_type
        and message.get("text") == text
        and not message.get("read_at")
        for message in state["outbox"]
    )

def has_pending_user_message(state):
    return any(
        event.get("type") == "user_message" and not event.get("processed_at")
        for event in state["inbox"]
    )

def pending_question_for_task(state, task_id):
    for question in state["questions"]:
        if (
            question.get("status") == "open"
            and question.get("related_task_id") == task_id
        ):
            return question

    for message in state["outbox"]:
        if (
            message.get("type") == "question"
            and message.get("requires_reply")
            and message.get("related_task_id") == task_id
            and not message.get("answered_at")
            and not message.get("read_at")
        ):
            return message
    return None

def has_open_question(state, text, task_id=None):
    if text and has_unread_outbox_message(state, "question", text):
        return True
    if task_id is not None and pending_question_for_task(state, task_id):
        return True
    return False
