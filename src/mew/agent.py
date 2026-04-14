import json
import os

from .codex_api import call_codex_json
from .config import (
    DEFAULT_CODEX_MODEL,
    DEFAULT_CODEX_WEB_BASE_URL,
    DEFAULT_TASK_TIMEOUT_SECONDS,
    LOG_FILE,
    MAX_RECENT_EVENTS,
)
from .errors import CodexApiError
from .agent_runs import find_agent_run, get_agent_run_result, start_agent_run
from .programmer import (
    create_follow_up_task_from_review,
    create_implementation_run_from_plan,
    create_review_run_for_implementation,
    create_task_plan,
    find_review_run_for_implementation,
    find_task_plan,
    latest_task_plan,
)
from .read_tools import inspect_dir, read_file, search_text, summarize_read_result
from .state import (
    add_event,
    add_attention_item,
    add_outbox_message,
    add_question,
    append_log,
    has_open_question,
    has_unread_outbox_message,
    next_id,
    open_attention_items,
    open_questions,
    pending_question_for_task,
)
from .tasks import (
    execute_task_action,
    normalize_task_id,
    open_tasks,
    summarize_tasks,
    task_by_id,
    task_question,
    task_sort_key,
)
from .timeutil import elapsed_hours, now_iso
from .toolbox import format_command_record, run_command_record
from .write_tools import edit_file, summarize_write_result, write_file


def build_recall_summary(state, event, current_time):
    runtime = state["runtime_status"]
    user = state["user_status"]
    hours_since_wake = elapsed_hours(runtime.get("last_woke_at"), current_time)
    hours_since_eval = elapsed_hours(runtime.get("last_evaluated_at"), current_time)
    hours_since_user = elapsed_hours(user.get("last_interaction_at"), current_time)

    parts = [summarize_tasks(state)]
    if hours_since_wake is not None:
        parts.append(f"Last wake was {hours_since_wake:.2f} hour(s) ago.")
    if hours_since_eval is not None:
        parts.append(f"Last evaluation was {hours_since_eval:.2f} hour(s) ago.")
    if hours_since_user is not None:
        parts.append(f"Last user interaction was {hours_since_user:.2f} hour(s) ago.")

    if event["type"] == "user_message":
        text = event.get("payload", {}).get("text", "")
        parts.append(f"User asked: {text}")

    return " ".join(parts)

def memory_for_context(state, limit=20):
    memory = state.get("memory", {})
    shallow = memory.get("shallow", {})
    deep = memory.get("deep", {})
    return {
        "shallow": shallow,
        "deep": {
            "preferences": list(deep.get("preferences", []))[-limit:],
            "project": list(deep.get("project", []))[-limit:],
            "decisions": list(deep.get("decisions", []))[-limit:],
        },
    }

def read_runtime_log_tail(limit=20):
    if not LOG_FILE.exists():
        return []
    try:
        lines = LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    return lines[-limit:]

def build_context(
    state,
    event,
    current_time,
    allowed_read_roots=None,
    self_text="",
    desires="",
    autonomous=False,
    autonomy_level="off",
    allow_agent_run=False,
    allow_verify=False,
    verify_command="",
    allow_write=False,
    allowed_write_roots=None,
):
    unanswered_questions = [
        {
            "id": question.get("id"),
            "text": question.get("text"),
            "related_task_id": question.get("related_task_id"),
            "blocks": question.get("blocks", []),
            "created_at": question.get("created_at"),
        }
        for question in open_questions(state)
    ]
    return {
        "date": {
            "now": current_time,
            "hours_since_last_wake": elapsed_hours(
                state["runtime_status"].get("last_woke_at"), current_time
            ),
            "hours_since_last_evaluation": elapsed_hours(
                state["runtime_status"].get("last_evaluated_at"), current_time
            ),
            "hours_since_last_user_interaction": elapsed_hours(
                state["user_status"].get("last_interaction_at"), current_time
            ),
        },
        "runtime_status": state["runtime_status"],
        "agent_status": state["agent_status"],
        "user_status": state["user_status"],
        "todo": sorted(open_tasks(state), key=task_sort_key),
        "unanswered_questions": unanswered_questions,
        "attention": open_attention_items(state),
        "memory": memory_for_context(state),
        "knowledge_shallow": state["knowledge"]["shallow"],
        "agent_runs": state.get("agent_runs", [])[-10:],
        "autonomy": {
            **state.get("autonomy", {}),
            "requested_enabled": bool(autonomous),
            "requested_level": autonomy_level,
            "allow_agent_run": bool(allow_agent_run),
            "allow_verify": bool(allow_verify),
            "verify_command_configured": bool(verify_command),
            "allow_write": bool(allow_write),
            "configured_allow_agent_run": bool(state.get("autonomy", {}).get("allow_agent_run")),
        },
        "self": self_text,
        "desires": desires,
        "runtime_log_tail": read_runtime_log_tail(),
        "allowed_read_roots": allowed_read_roots or [],
        "allowed_write_roots": allowed_write_roots or [],
        "verification_runs": state.get("verification_runs", [])[-10:],
        "write_runs": state.get("write_runs", [])[-10:],
        "event": event,
    }

def build_codex_prompt(state, event, current_time):
    context = build_context(state, event, current_time)
    return (
        "Evaluate the current mew state and write the next useful response.\n"
        "For startup or tick events, summarize what should be remembered now.\n"
        "For user_message events, answer the user's message using the task state.\n\n"
        f"State JSON:\n{json.dumps(context, ensure_ascii=False, indent=2)}"
    )

def build_think_prompt(
    state,
    event,
    current_time,
    allow_task_execution,
    guidance,
    policy,
    self_text="",
    desires="",
    autonomous=False,
    autonomy_level="off",
    allow_agent_run=False,
    allow_verify=False,
    verify_command="",
    allow_write=False,
    allowed_read_roots=None,
    allowed_write_roots=None,
):
    context = build_context(
        state,
        event,
        current_time,
        allowed_read_roots=allowed_read_roots,
        self_text=self_text,
        desires=desires,
        autonomous=autonomous,
        autonomy_level=autonomy_level,
        allow_agent_run=allow_agent_run,
        allow_verify=allow_verify,
        verify_command=verify_command,
        allow_write=allow_write,
        allowed_write_roots=allowed_write_roots,
    )
    return (
        "You are the THINK phase of mew, a passive personal task agent.\n"
        "Return only JSON. Do not use markdown.\n"
        "Your job is to decide what should happen next, not to execute anything.\n"
        "Follow the human-written guidance when prioritizing decisions. "
        "If guidance conflicts with safety rules, safety rules win.\n"
        "Decision types you may emit: remember, send_message, ask_user, wait_for_user, "
        "execute_task, run_verification, update_memory, inspect_dir, read_file, search_text, self_review, propose_task, "
        "write_file, edit_file, plan_task, dispatch_task, collect_agent_result, review_agent_run, followup_review.\n"
        f"Autonomous mode is {str(bool(autonomous)).lower()} with level={autonomy_level}.\n"
        f"allow_agent_run is {str(bool(allow_agent_run)).lower()}.\n"
        f"allow_verify is {str(bool(allow_verify)).lower()} and verify_command_configured is {str(bool(verify_command)).lower()}.\n"
        f"allow_write is {str(bool(allow_write)).lower()}.\n"
        "When autonomous mode is false, do not do self-directed work unless it directly answers the user.\n"
        "When autonomous mode is true and there is no user input, use Self and Desires to choose useful small work.\n"
        "Autonomy levels: observe can remember and self_review; propose can also propose_task and plan_task; "
        "act can also use allowed read-only inspection and programmer-loop actions. "
        "Starting agent runs requires allow_agent_run in local state, even at act level. "
        "Local task command execution still requires allow_task_execution. "
        "Verification command execution requires run_verification plus allow_verify and a configured verify command. "
        "File writes require write_file/edit_file plus allow_write, allowed_write_roots, and a configured verification command unless dry_run=true. "
        "Omitting dry_run is treated as dry_run=true; set dry_run=false explicitly to write. "
        "Agent runs require dispatch_task and allow_agent_run.\n"
        "If you are waiting for the user because specific input is needed, prefer ask_user. "
        "If you emit wait_for_user, include a question when the missing input should be visible to the user.\n"
        "Use execute_task only when a task is ready, has command, has auto_execute=true, "
        f"and allow_task_execution is {str(bool(allow_task_execution)).lower()}.\n"
        "Use read-only inspection only when it directly helps the current task or memory, and only under allowed_read_roots.\n"
        "Use write actions only for small targeted changes under allowed_write_roots; prefer dry_run before writing.\n"
        "Do not ask the same question if it already appears in unanswered_questions.\n"
        "Schema:\n"
        "{\n"
        '  "summary": "short memory of the current situation",\n'
        '  "agent_status": {\n'
        '    "mode": "idle|reviewing_tasks|answering_user|waiting_for_user|acting",\n'
        '    "current_focus": "short phrase",\n'
        '    "active_task_id": null,\n'
        '    "pending_question": null,\n'
        '    "last_thought": "short thought"\n'
        "  },\n"
        '  "decisions": [\n'
        '    {"type": "remember", "summary": "..."},\n'
        '    {"type": "send_message", "message_type": "assistant|info|warning", "text": "..."},\n'
        '    {"type": "ask_user", "task_id": 1, "question": "..."},\n'
        '    {"type": "wait_for_user", "task_id": 1, "reason": "...", "question": "..."},\n'
        '    {"type": "update_memory", "category": "project|preferences|decisions", "text": "..."},\n'
        '    {"type": "inspect_dir", "path": "..."},\n'
        '    {"type": "read_file", "path": "...", "max_chars": 4000},\n'
        '    {"type": "search_text", "path": "...", "query": "...", "max_matches": 20},\n'
        '    {"type": "run_verification", "reason": "..."},\n'
        '    {"type": "write_file", "path": "...", "content": "...", "create": false, "dry_run": true},\n'
        '    {"type": "edit_file", "path": "...", "old": "...", "new": "...", "replace_all": false, "dry_run": true},\n'
        '    {"type": "self_review", "summary": "...", "proposed_task_title": "...", "proposed_task_description": "..."},\n'
        '    {"type": "propose_task", "title": "...", "description": "...", "priority": "low|normal|high"},\n'
        '    {"type": "plan_task", "task_id": 1, "objective": "...", "approach": "..."},\n'
        '    {"type": "dispatch_task", "task_id": 1, "plan_id": 1, "reason": "..."},\n'
        '    {"type": "collect_agent_result", "run_id": 1},\n'
        '    {"type": "review_agent_run", "run_id": 1},\n'
        '    {"type": "followup_review", "run_id": 2},\n'
        '    {"type": "execute_task", "task_id": 1, "reason": "..."}\n'
        "  ]\n"
        "}\n\n"
        f"Human guidance:\n{guidance or '(none)'}\n\n"
        f"Human policy:\n{policy or '(none)'}\n\n"
        f"Self:\n{self_text or '(none)'}\n\n"
        f"Desires:\n{desires or '(none)'}\n\n"
        f"State JSON:\n{json.dumps(context, ensure_ascii=False, indent=2)}"
    )

def build_act_prompt(
    state,
    event,
    decision_plan,
    current_time,
    allow_task_execution,
    policy,
    self_text="",
    desires="",
    autonomous=False,
    autonomy_level="off",
    allow_agent_run=False,
    allow_verify=False,
    verify_command="",
    allow_write=False,
    allowed_read_roots=None,
    allowed_write_roots=None,
):
    context = build_context(
        state,
        event,
        current_time,
        allowed_read_roots=allowed_read_roots,
        self_text=self_text,
        desires=desires,
        autonomous=autonomous,
        autonomy_level=autonomy_level,
        allow_agent_run=allow_agent_run,
        allow_verify=allow_verify,
        verify_command=verify_command,
        allow_write=allow_write,
        allowed_write_roots=allowed_write_roots,
    )
    return (
        "You are the ACT phase of mew, a passive personal task agent.\n"
        "Return only JSON. Do not use markdown.\n"
        "Your job is to normalize the THINK phase DecisionPlan into concrete actions.\n"
        "You still do not execute shell commands yourself. Local code will execute only validated actions.\n"
        "Allowed action types: record_memory, send_message, ask_user, wait_for_user, execute_task, run_verification, "
        "update_memory, inspect_dir, read_file, search_text, self_review, propose_task, "
        "write_file, edit_file, plan_task, dispatch_task, collect_agent_result, review_agent_run, followup_review.\n"
        f"Autonomous mode is {str(bool(autonomous)).lower()} with level={autonomy_level}.\n"
        f"allow_agent_run is {str(bool(allow_agent_run)).lower()}.\n"
        f"allow_verify is {str(bool(allow_verify)).lower()} and verify_command_configured is {str(bool(verify_command)).lower()}.\n"
        f"allow_write is {str(bool(allow_write)).lower()}.\n"
        "Respect the autonomy level: observe may record/self_review only; propose may propose_task/plan_task; "
        "act may use allowed read-only inspection and programmer-loop actions. "
        "Starting agent runs requires allow_agent_run in local state. "
        "Local task command execution still requires allow_task_execution. "
        "Verification command execution requires run_verification plus allow_verify and a configured verify command.\n"
        "File writes require write_file/edit_file plus allow_write, allowed_write_roots, and a configured verification command unless dry_run=true. "
        "Omitting dry_run is treated as dry_run=true; set dry_run=false explicitly to write.\n"
        "If the DecisionPlan is waiting on concrete user input, turn it into ask_user or include question on wait_for_user.\n"
        "Use execute_task only when the task is ready, has command, has auto_execute=true, "
        f"and allow_task_execution is {str(bool(allow_task_execution)).lower()}.\n"
        "Use read-only inspection only under allowed_read_roots. If no read root is allowed, do not emit read actions.\n"
        "Use write actions only under allowed_write_roots. If no write root is allowed, do not emit write actions.\n"
        "Do not invent shell commands. Reference tasks by task_id only.\n"
        "Do not repeat unanswered questions already present in state.\n"
        "Schema:\n"
        "{\n"
        '  "summary": "short action summary",\n'
        '  "actions": [\n'
        '    {"type": "record_memory", "summary": "..."},\n'
        '    {"type": "send_message", "message_type": "assistant|info|warning", "text": "..."},\n'
        '    {"type": "ask_user", "task_id": 1, "question": "..."},\n'
        '    {"type": "wait_for_user", "task_id": 1, "reason": "...", "question": "..."},\n'
        '    {"type": "update_memory", "category": "project|preferences|decisions", "text": "..."},\n'
        '    {"type": "inspect_dir", "path": "..."},\n'
        '    {"type": "read_file", "path": "...", "max_chars": 4000},\n'
        '    {"type": "search_text", "path": "...", "query": "...", "max_matches": 20},\n'
        '    {"type": "run_verification", "reason": "..."},\n'
        '    {"type": "write_file", "path": "...", "content": "...", "create": false, "dry_run": true},\n'
        '    {"type": "edit_file", "path": "...", "old": "...", "new": "...", "replace_all": false, "dry_run": true},\n'
        '    {"type": "self_review", "summary": "...", "proposed_task_title": "...", "proposed_task_description": "..."},\n'
        '    {"type": "propose_task", "title": "...", "description": "...", "priority": "low|normal|high"},\n'
        '    {"type": "plan_task", "task_id": 1, "objective": "...", "approach": "..."},\n'
        '    {"type": "dispatch_task", "task_id": 1, "plan_id": 1, "reason": "..."},\n'
        '    {"type": "collect_agent_result", "run_id": 1},\n'
        '    {"type": "review_agent_run", "run_id": 1},\n'
        '    {"type": "followup_review", "run_id": 2},\n'
        '    {"type": "execute_task", "task_id": 1, "reason": "..."}\n'
        "  ]\n"
        "}\n\n"
        f"Human policy:\n{policy or '(none)'}\n\n"
        f"Self:\n{self_text or '(none)'}\n\n"
        f"Desires:\n{desires or '(none)'}\n\n"
        f"State JSON:\n{json.dumps(context, ensure_ascii=False, indent=2)}\n\n"
        f"DecisionPlan JSON:\n{json.dumps(decision_plan, ensure_ascii=False, indent=2)}"
    )

def should_use_ai_for_event(event, reason, ai_ticks):
    if event["type"] == "user_message":
        return True
    if event["type"] == "startup":
        return True
    if event["type"] == "passive_tick":
        return True
    if ai_ticks and event["type"] == "tick":
        return True
    return False

def update_shallow_knowledge(state, event, summary, current_time):
    memory = state.setdefault("memory", {})
    memory_shallow = memory.setdefault("shallow", {})
    memory_shallow["current_context"] = summary
    memory_shallow["latest_task_summary"] = summary
    memory_recent = memory_shallow.setdefault("recent_events", [])
    memory_recent.append(
        {
            "at": current_time,
            "event_id": event["id"],
            "event_type": event["type"],
            "summary": summary,
        }
    )
    del memory_recent[:-MAX_RECENT_EVENTS]

    shallow = state["knowledge"]["shallow"]
    shallow["latest_task_summary"] = summary
    recent = shallow.setdefault("recent_events", [])
    if recent is not memory_recent:
        recent.append(
            {
                "at": current_time,
                "event_id": event["id"],
                "event_type": event["type"],
                "summary": summary,
            }
        )
    del recent[:-MAX_RECENT_EVENTS]

def record_deep_memory(state, category, text, current_time):
    if category not in ("preferences", "project", "decisions"):
        category = "project"
    if not isinstance(text, str) or not text.strip():
        return

    memory = state.setdefault("memory", {})
    deep = memory.setdefault("deep", {})
    items = deep.setdefault(category, [])
    clipped = text.strip()
    if len(clipped) > 4000:
        clipped = clipped[:4000] + "\n... memory truncated ..."
    items.append(f"{current_time}: {clipped}")
    del items[:-100]

def update_agent_work_context(state, event, summary, current_time):
    agent = state["agent_status"]
    tasks = sorted(open_tasks(state), key=task_sort_key)
    active_task_id = tasks[0]["id"] if tasks else None

    if event["type"] == "user_message":
        agent["mode"] = "answering_user"
        agent["current_focus"] = event.get("payload", {}).get("text", "")
    else:
        agent["mode"] = "reviewing_tasks"
        agent["current_focus"] = "recalling current tasks and recent context"

    agent["active_task_id"] = active_task_id
    agent["pending_question"] = None
    agent["last_thought"] = summary
    agent["updated_at"] = current_time

def open_task_with_title(state, title):
    normalized = (title or "").strip().casefold()
    if not normalized:
        return None
    for task in open_tasks(state):
        if (task.get("title") or "").strip().casefold() == normalized:
            return task
    return None

def append_passive_decisions(
    state,
    decisions,
    allow_task_execution,
    autonomous=False,
    autonomy_level="off",
):
    tasks = sorted(open_tasks(state), key=task_sort_key)
    if not tasks:
        question = "What task should I track next?"
        if autonomous:
            decision = {
                "type": "self_review",
                "summary": "No open tasks exist. Review state and choose one small useful next move.",
            }
            if autonomy_level in ("propose", "act"):
                decision["proposed_task_title"] = "Define the next useful mew task"
                decision["proposed_task_description"] = (
                    "Use self/desires and current state to choose one small next task."
                )
            decisions.append(decision)
        elif not has_unread_outbox_message(state, "question", question):
            decisions.append({"type": "ask_user", "question": question})
        return

    execution_added = False
    question_added = False
    for task in tasks:
        task_id = task["id"]
        pending_question = pending_question_for_task(state, task_id)
        if pending_question:
            decisions.append(
                {
                    "type": "wait_for_user",
                    "task_id": task_id,
                    "reason": f"Question #{pending_question['id']} is still unanswered.",
                }
            )
            continue

        can_execute = (
            allow_task_execution
            and task.get("status") == "ready"
            and bool(task.get("auto_execute"))
            and bool(task.get("command"))
        )
        if can_execute and not execution_added:
            decisions.append(
                {
                    "type": "execute_task",
                    "task_id": task_id,
                    "reason": "Task is ready and explicitly marked auto_execute.",
                }
            )
            execution_added = True
            continue

        question = task_question(task)
        if question and not question_added and not has_unread_outbox_message(state, "question", question):
            decisions.append(
                {
                    "type": "ask_user",
                    "task_id": task_id,
                    "question": question,
                }
            )
            question_added = True

def append_autonomous_decisions(
    state,
    decisions,
    event,
    autonomy_level,
    desires,
    allow_agent_run=False,
    allow_verify=False,
    verify_command="",
    verify_interval_seconds=3600,
    current_time=None,
):
    if event["type"] not in ("startup", "passive_tick"):
        return

    desires_summary = (desires or "").strip().splitlines()
    first_desire = ""
    for line in desires_summary:
        if line.strip().startswith("-"):
            first_desire = line.strip("- ").strip()
            break
    first_desire = first_desire or "review current state and choose a small useful improvement"
    hours_since_self_review = elapsed_hours(
        state.get("autonomy", {}).get("last_self_review_at"),
        current_time,
    )
    if hours_since_self_review is None or hours_since_self_review >= 1:
        decisions.append(
            {
                "type": "self_review",
                "summary": f"Autonomous self review: {first_desire}",
            }
        )

    for run in state.get("agent_runs", []):
        purpose = run.get("purpose", "implementation")
        status = run.get("status")
        if status == "running":
            decisions.append({"type": "collect_agent_result", "run_id": run["id"]})
            return
        if (
            purpose == "implementation"
            and status in ("completed", "failed")
            and autonomy_level == "act"
            and allow_agent_run
        ):
            if not find_review_run_for_implementation(state, run["id"]):
                decisions.append({"type": "review_agent_run", "run_id": run["id"]})
                return
        if (
            purpose == "review"
            and status in ("completed", "failed")
            and autonomy_level in ("propose", "act")
            and not run.get("followup_task_id")
        ):
            decisions.append({"type": "followup_review", "run_id": run["id"]})
            return

    if autonomy_level in ("propose", "act"):
        for task in sorted(open_tasks(state), key=task_sort_key):
            if (
                task.get("status") in ("todo", "ready")
                and not latest_task_plan(task)
                and not pending_question_for_task(state, task.get("id"))
            ):
                decisions.append(
                    {
                        "type": "plan_task",
                        "task_id": task["id"],
                        "reason": "Task has no programmer plan yet.",
                    }
                )
                return

    if autonomy_level == "act" and allow_agent_run:
        for task in sorted(open_tasks(state), key=task_sort_key):
            plan = latest_task_plan(task)
            if (
                plan
                and plan.get("status") in ("planned", "dry_run")
                and task.get("status") == "ready"
                and task.get("auto_execute")
                and not pending_question_for_task(state, task.get("id"))
            ):
                decisions.append(
                    {
                        "type": "dispatch_task",
                        "task_id": task["id"],
                        "plan_id": plan["id"],
                        "reason": "Ready auto-execute task has a programmer plan.",
                    }
                )
                return

    if (
        autonomy_level == "act"
        and allow_verify
        and verify_command
        and runtime_verification_due(state, current_time, verify_interval_seconds)
    ):
        decisions.append(
            {
                "type": "run_verification",
                "reason": "Configured runtime verification is due.",
            }
        )
        return

    if autonomy_level in ("propose", "act") and not open_task_with_title(state, "Review mew self direction"):
        decisions.append(
            {
                "type": "propose_task",
                "title": "Review mew self direction",
                "description": "Review runtime state, memory, and desires, then propose one small improvement to mew.",
                "priority": "normal",
            }
        )

def latest_verification_time(state):
    for run in reversed(state.get("verification_runs", [])):
        timestamp = run.get("finished_at") or run.get("updated_at") or run.get("created_at")
        if timestamp:
            return timestamp
    return None

def runtime_verification_due(state, current_time, interval_seconds):
    latest = latest_verification_time(state)
    if not latest:
        return True
    hours = elapsed_hours(latest, current_time)
    if hours is None:
        return True
    return hours * 3600 >= max(0.0, interval_seconds)

def deterministic_decision_plan(
    state,
    event,
    current_time,
    allow_task_execution,
    autonomous=False,
    autonomy_level="off",
    desires="",
    allow_agent_run=False,
    allow_verify=False,
    verify_command="",
    verify_interval_seconds=3600,
):
    summary = build_recall_summary(state, event, current_time)
    decisions = [{"type": "remember", "summary": summary}]

    if event["type"] == "user_message":
        decisions.append(
            {
                "type": "send_message",
                "message_type": "info",
                "text": summary,
            }
        )
    elif event["type"] == "startup":
        decisions.append(
            {
                "type": "send_message",
                "message_type": "info",
                "text": summary,
            }
        )
        had_tasks = bool(open_tasks(state))
        append_passive_decisions(
            state,
            decisions,
            allow_task_execution,
            autonomous=autonomous,
            autonomy_level=autonomy_level,
        )
        if autonomous and had_tasks:
            append_autonomous_decisions(
                state,
                decisions,
                event,
                autonomy_level,
                desires,
                allow_agent_run=allow_agent_run,
                allow_verify=allow_verify,
                verify_command=verify_command,
                verify_interval_seconds=verify_interval_seconds,
                current_time=current_time,
            )
    elif event["type"] == "passive_tick":
        had_tasks = bool(open_tasks(state))
        append_passive_decisions(
            state,
            decisions,
            allow_task_execution,
            autonomous=autonomous,
            autonomy_level=autonomy_level,
        )
        if autonomous and had_tasks:
            append_autonomous_decisions(
                state,
                decisions,
                event,
                autonomy_level,
                desires,
                allow_agent_run=allow_agent_run,
                allow_verify=allow_verify,
                verify_command=verify_command,
                verify_interval_seconds=verify_interval_seconds,
                current_time=current_time,
            )

    if len(decisions) == 1:
        decisions.append({"type": "wait_for_user", "reason": "No actionable task."})

    return {
        "summary": summary,
        "agent_status": {
            "mode": "answering_user" if event["type"] == "user_message" else "reviewing_tasks",
            "current_focus": event.get("payload", {}).get("text", "")
            if event["type"] == "user_message"
            else "recalling current tasks and recent context",
            "active_task_id": sorted(open_tasks(state), key=task_sort_key)[0]["id"]
            if open_tasks(state)
            else None,
            "pending_question": None,
            "last_thought": summary,
        },
        "decisions": decisions,
    }

def normalize_decision_plan(plan, fallback_summary):
    if not isinstance(plan, dict):
        plan = {}
    summary = plan.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        summary = fallback_summary

    decisions = plan.get("decisions")
    if not isinstance(decisions, list):
        decisions = []

    normalized = []
    for decision in decisions:
        if not isinstance(decision, dict):
            continue
        decision_type = decision.get("type")
        if not isinstance(decision_type, str):
            continue
        clean = {"type": decision_type}
        for key in (
            "message_type",
            "text",
            "question",
            "reason",
            "summary",
            "path",
            "query",
            "category",
            "title",
            "description",
            "priority",
            "status",
            "notes",
            "proposed_task_title",
            "proposed_task_description",
            "objective",
            "approach",
            "cwd",
            "agent_model",
            "review_model",
            "content",
            "old",
            "new",
        ):
            if isinstance(decision.get(key), str):
                clean[key] = decision[key]
        for key in ("create", "dry_run", "replace_all"):
            if isinstance(decision.get(key), bool):
                clean[key] = decision[key]
        for key in ("run_id", "plan_id"):
            value = normalize_task_id(decision.get(key))
            if value is not None:
                clean[key] = value
        for key in ("max_chars", "max_matches", "limit"):
            if isinstance(decision.get(key), int):
                clean[key] = decision[key]
        task_id = normalize_task_id(decision.get("task_id"))
        if task_id is not None:
            clean["task_id"] = task_id
        normalized.append(clean)

    if not normalized:
        normalized.append({"type": "remember", "summary": summary})

    agent_status = plan.get("agent_status") if isinstance(plan.get("agent_status"), dict) else {}
    return {
        "summary": summary,
        "agent_status": agent_status,
        "decisions": normalized,
    }

def think_phase(
    state,
    event,
    current_time,
    codex_auth,
    model,
    base_url,
    timeout,
    ai_ticks,
    allow_task_execution,
    guidance,
    policy,
    self_text="",
    desires="",
    autonomous=False,
    autonomy_level="off",
    allow_agent_run=False,
    allow_verify=False,
    verify_command="",
    verify_interval_seconds=3600,
    allow_write=False,
    allowed_read_roots=None,
    allowed_write_roots=None,
):
    fallback = deterministic_decision_plan(
        state,
        event,
        current_time,
        allow_task_execution,
        autonomous=autonomous,
        autonomy_level=autonomy_level,
        desires=desires,
        allow_agent_run=allow_agent_run,
        allow_verify=allow_verify,
        verify_command=verify_command,
        verify_interval_seconds=verify_interval_seconds,
    )
    if not codex_auth or not should_use_ai_for_event(event, event["type"], ai_ticks):
        return fallback

    prompt = build_think_prompt(
        state,
        event,
        current_time,
        allow_task_execution,
        guidance,
        policy,
        self_text=self_text,
        desires=desires,
        autonomous=autonomous,
        autonomy_level=autonomy_level,
        allow_agent_run=allow_agent_run,
        allow_verify=allow_verify,
        verify_command=verify_command,
        allow_write=allow_write,
        allowed_read_roots=allowed_read_roots,
        allowed_write_roots=allowed_write_roots,
    )
    try:
        plan = call_codex_json(codex_auth, prompt, model, base_url, timeout)
        append_log(f"- {current_time}: think_phase codex_api ok event={event['id']}")
    except CodexApiError as exc:
        append_log(f"- {current_time}: think_phase codex_api error event={event['id']} error={exc}")
        fallback["decisions"].append(
            {
                "type": "send_message",
                "message_type": "warning",
                "text": f"Codex THINK error: {exc}",
            }
        )
        return fallback
    return normalize_decision_plan(plan, fallback["summary"])

def deterministic_action_plan(decision_plan):
    actions = []
    for decision in decision_plan.get("decisions", []):
        decision_type = decision.get("type")
        if decision_type == "remember":
            actions.append({"type": "record_memory", "summary": decision.get("summary") or decision_plan["summary"]})
        elif decision_type in (
            "send_message",
            "ask_user",
            "wait_for_user",
            "execute_task",
            "run_verification",
            "update_memory",
            "inspect_dir",
            "read_file",
            "search_text",
            "write_file",
            "edit_file",
            "self_review",
            "propose_task",
            "plan_task",
            "dispatch_task",
            "collect_agent_result",
            "review_agent_run",
            "followup_review",
        ):
            actions.append(dict(decision))
    if not actions:
        actions.append({"type": "record_memory", "summary": decision_plan["summary"]})
    return {"summary": decision_plan["summary"], "actions": actions}

def normalize_action_plan(plan, fallback_plan):
    if not isinstance(plan, dict):
        plan = {}
    summary = plan.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        summary = fallback_plan.get("summary", "")

    actions = plan.get("actions")
    if not isinstance(actions, list):
        actions = fallback_plan.get("actions", [])

    normalized = []
    for action in actions:
        if not isinstance(action, dict):
            continue
        action_type = action.get("type")
        if action_type not in (
            "record_memory",
            "send_message",
            "ask_user",
            "wait_for_user",
            "execute_task",
            "run_verification",
            "update_memory",
            "inspect_dir",
            "read_file",
            "search_text",
            "write_file",
            "edit_file",
            "self_review",
            "propose_task",
            "plan_task",
            "dispatch_task",
            "collect_agent_result",
            "review_agent_run",
            "followup_review",
        ):
            continue
        clean = {"type": action_type}
        for key in (
            "message_type",
            "text",
            "question",
            "reason",
            "summary",
            "path",
            "query",
            "category",
            "title",
            "description",
            "priority",
            "status",
            "notes",
            "proposed_task_title",
            "proposed_task_description",
            "objective",
            "approach",
            "cwd",
            "agent_model",
            "review_model",
            "content",
            "old",
            "new",
        ):
            if isinstance(action.get(key), str):
                clean[key] = action[key]
        for key in ("create", "dry_run", "replace_all"):
            if isinstance(action.get(key), bool):
                clean[key] = action[key]
        for key in ("run_id", "plan_id"):
            value = normalize_task_id(action.get(key))
            if value is not None:
                clean[key] = value
        for key in ("max_chars", "max_matches", "limit"):
            if isinstance(action.get(key), int):
                clean[key] = action[key]
        task_id = normalize_task_id(action.get("task_id"))
        if task_id is not None:
            clean["task_id"] = task_id
        normalized.append(clean)

    if not normalized:
        normalized = fallback_plan.get("actions", [])

    return {"summary": summary, "actions": normalized}

def act_phase(
    state,
    event,
    decision_plan,
    current_time,
    codex_auth,
    model,
    base_url,
    timeout,
    ai_ticks,
    allow_task_execution,
    policy,
    self_text="",
    desires="",
    autonomous=False,
    autonomy_level="off",
    allow_agent_run=False,
    allow_verify=False,
    verify_command="",
    allow_write=False,
    allowed_read_roots=None,
    allowed_write_roots=None,
):
    fallback = deterministic_action_plan(decision_plan)
    if not codex_auth or not should_use_ai_for_event(event, event["type"], ai_ticks):
        return fallback

    prompt = build_act_prompt(
        state,
        event,
        decision_plan,
        current_time,
        allow_task_execution,
        policy,
        self_text=self_text,
        desires=desires,
        autonomous=autonomous,
        autonomy_level=autonomy_level,
        allow_agent_run=allow_agent_run,
        allow_verify=allow_verify,
        verify_command=verify_command,
        allow_write=allow_write,
        allowed_read_roots=allowed_read_roots,
        allowed_write_roots=allowed_write_roots,
    )
    try:
        action_plan = call_codex_json(codex_auth, prompt, model, base_url, timeout)
        append_log(f"- {current_time}: act_phase codex_api ok event={event['id']}")
    except CodexApiError as exc:
        append_log(f"- {current_time}: act_phase codex_api error event={event['id']} error={exc}")
        fallback["actions"].append(
            {
                "type": "send_message",
                "message_type": "warning",
                "text": f"Codex ACT error: {exc}",
            }
        )
        return fallback
    return normalize_action_plan(action_plan, fallback)

def update_agent_work_context_from_plan(state, event, decision_plan, action_plan, current_time):
    agent = state["agent_status"]
    planned_status = decision_plan.get("agent_status", {})
    first_task_id = None
    pending_question = None

    for action in action_plan.get("actions", []):
        if first_task_id is None and action.get("task_id") is not None:
            first_task_id = action.get("task_id")
        if action["type"] in ("ask_user", "wait_for_user"):
            pending_question = action.get("question") or action.get("reason")

    mode = planned_status.get("mode")
    if mode not in ("idle", "reviewing_tasks", "answering_user", "waiting_for_user", "acting"):
        if pending_question:
            mode = "waiting_for_user"
        elif event["type"] == "user_message":
            mode = "answering_user"
        elif any(
            action["type"]
            in (
                "execute_task",
                "run_verification",
                "write_file",
                "edit_file",
                "dispatch_task",
                "collect_agent_result",
                "review_agent_run",
                "followup_review",
            )
            for action in action_plan.get("actions", [])
        ):
            mode = "acting"
        else:
            mode = "reviewing_tasks"

    agent["mode"] = mode
    agent["current_focus"] = planned_status.get("current_focus") or action_plan.get("summary") or ""
    agent["active_task_id"] = normalize_task_id(planned_status.get("active_task_id")) or first_task_id
    agent["pending_question"] = planned_status.get("pending_question") or pending_question
    agent["last_thought"] = planned_status.get("last_thought") or decision_plan.get("summary") or action_plan.get("summary") or ""
    agent["updated_at"] = current_time

def apply_read_action(state, event, action, current_time, allowed_read_roots):
    action_type = action.get("type")
    try:
        if action_type == "inspect_dir":
            result = inspect_dir(action.get("path") or ".", allowed_read_roots, limit=action.get("limit", 50))
        elif action_type == "read_file":
            result = read_file(
                action.get("path") or "",
                allowed_read_roots,
                max_chars=action.get("max_chars", 6000),
            )
        elif action_type == "search_text":
            result = search_text(
                action.get("query") or "",
                action.get("path") or ".",
                allowed_read_roots,
                max_matches=action.get("max_matches", 50),
            )
        else:
            return 0
    except ValueError as exc:
        add_outbox_message(
            state,
            "warning",
            f"{action_type} refused: {exc}",
            event_id=event["id"],
            related_task_id=action.get("task_id"),
        )
        return 1

    summary = summarize_read_result(action_type, result)
    record_deep_memory(state, "project", summary, current_time)
    if action_type == "read_file":
        text = f"Read file {result.get('path')} and saved the observation to memory."
    elif action_type == "search_text":
        match_count = len(result.get("matches", []))
        text = (
            f"Searched {result.get('path')} for {result.get('query')!r}; "
            f"{match_count} {'match' if match_count == 1 else 'matches'} saved to memory."
        )
    else:
        entry_count = len(result.get("entries", []))
        text = (
            f"Inspected directory {result.get('path')}; "
            f"{entry_count} {'entry' if entry_count == 1 else 'entries'} saved to memory."
        )
    add_outbox_message(
        state,
        "info",
        text,
        event_id=event["id"],
        related_task_id=action.get("task_id"),
    )
    return 1

def add_proposed_task(state, title, description, priority, notes, current_time):
    title = (title or "").strip()
    if not title:
        return None, False
    existing = open_task_with_title(state, title)
    if existing:
        return existing, False

    if priority not in ("low", "normal", "high"):
        priority = "normal"
    task = {
        "id": next_id(state, "task"),
        "title": title,
        "description": description or "",
        "status": "todo",
        "priority": priority,
        "notes": notes or "",
        "command": "",
        "cwd": "",
        "auto_execute": False,
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
    return task, True

def apply_propose_task_action(state, event, action, current_time, autonomous, autonomy_level):
    allowed = event["type"] == "user_message" or (autonomous and autonomy_level in ("propose", "act"))
    title = action.get("title") or action.get("proposed_task_title") or ""
    if not allowed:
        add_outbox_message(
            state,
            "warning",
            f"Refused propose_task {title!r}: autonomy level does not allow task proposals.",
            event_id=event["id"],
        )
        return 1

    task, created = add_proposed_task(
        state,
        title,
        action.get("description") or action.get("proposed_task_description") or "",
        action.get("priority") or "normal",
        action.get("notes") or f"Proposed by mew from event #{event['id']}.",
        current_time,
    )
    if not task:
        return 0

    if created:
        add_outbox_message(
            state,
            "info",
            f"Proposed task #{task['id']}: {task['title']}",
            event_id=event["id"],
            related_task_id=task["id"],
        )
        return 1
    return 0

def apply_self_review_action(state, event, action, current_time, autonomous, autonomy_level):
    summary = action.get("summary") or action.get("text") or "Self review completed without details."
    record_deep_memory(state, "decisions", f"Self review: {summary}", current_time)
    autonomy = state.setdefault("autonomy", {})
    autonomy["last_self_review_at"] = current_time
    autonomy["last_autonomous_action_at"] = current_time if autonomous else autonomy.get("last_autonomous_action_at")
    autonomy["last_cycle_reason"] = event["type"]
    autonomy["last_desire"] = summary[:500]
    autonomy["updated_at"] = current_time
    message_count = 0
    if event["type"] == "user_message":
        add_outbox_message(
            state,
            "info",
            f"Self review recorded: {summary}",
            event_id=event["id"],
        )
        message_count = 1

    title = action.get("proposed_task_title")
    if title:
        message_count += apply_propose_task_action(
            state,
            event,
            {
                "title": title,
                "description": action.get("proposed_task_description") or "",
                "priority": action.get("priority") or "normal",
                "notes": f"Proposed by self_review from event #{event['id']}.",
            },
            current_time,
            autonomous,
            autonomy_level,
        )
    return message_count

def programmer_action_allowed(event, autonomous, autonomy_level, required_level):
    if event["type"] == "user_message":
        return True
    if not autonomous:
        return False
    if required_level == "propose":
        return autonomy_level in ("propose", "act")
    if required_level == "act":
        return autonomy_level == "act"
    return False

def apply_plan_task_action(state, event, action, current_time, autonomous, autonomy_level):
    if not programmer_action_allowed(event, autonomous, autonomy_level, "propose"):
        add_outbox_message(
            state,
            "warning",
            f"Refused plan_task for task #{action.get('task_id')}: autonomy level does not allow planning.",
            event_id=event["id"],
            related_task_id=action.get("task_id"),
        )
        return 1
    task = task_by_id(state, action.get("task_id"))
    if not task:
        add_outbox_message(state, "warning", f"Cannot plan missing task #{action.get('task_id')}", event_id=event["id"])
        return 1
    plan = latest_task_plan(task)
    if plan:
        return 0
    plan = create_task_plan(
        state,
        task,
        cwd=action.get("cwd"),
        model=action.get("agent_model"),
        review_model=action.get("review_model"),
        objective=action.get("objective"),
        approach=action.get("approach"),
    )
    add_outbox_message(
        state,
        "info",
        f"Created programmer plan #{plan['id']} for task #{task['id']}.",
        event_id=event["id"],
        related_task_id=task["id"],
    )
    return 1

def apply_dispatch_task_action(state, event, action, current_time, autonomous, autonomy_level, allow_agent_run):
    if not programmer_action_allowed(event, autonomous, autonomy_level, "act"):
        add_outbox_message(
            state,
            "warning",
            f"Refused dispatch_task for task #{action.get('task_id')}: autonomy level does not allow dispatch.",
            event_id=event["id"],
            related_task_id=action.get("task_id"),
        )
        return 1
    if not allow_agent_run:
        add_outbox_message(
            state,
            "warning",
            f"Refused dispatch_task for task #{action.get('task_id')}: --allow-agent-run is required.",
            event_id=event["id"],
            related_task_id=action.get("task_id"),
        )
        return 1
    task = task_by_id(state, action.get("task_id"))
    if not task:
        add_outbox_message(state, "warning", f"Cannot dispatch missing task #{action.get('task_id')}", event_id=event["id"])
        return 1
    if autonomous and not (task.get("status") == "ready" and task.get("auto_execute")):
        add_outbox_message(
            state,
            "warning",
            f"Refused autonomous dispatch for task #{task['id']}: task must be ready and auto_execute=true.",
            event_id=event["id"],
            related_task_id=task["id"],
        )
        return 1
    plan = find_task_plan(task, action.get("plan_id")) if action.get("plan_id") else latest_task_plan(task)
    if not plan:
        plan = create_task_plan(state, task)
    run = create_implementation_run_from_plan(state, task, plan)
    start_agent_run(state, run)
    if run.get("status") == "running":
        return 1
    return 1

def apply_collect_agent_result_action(state, event, action):
    run = find_agent_run(state, action.get("run_id"))
    if not run:
        add_outbox_message(state, "warning", f"Cannot collect missing agent run #{action.get('run_id')}", event_id=event["id"])
        return 1
    before = run.get("status")
    try:
        get_agent_run_result(state, run)
    except ValueError as exc:
        add_outbox_message(state, "warning", f"Cannot collect agent run #{run['id']}: {exc}", event_id=event["id"], agent_run_id=run["id"])
        return 1
    after = run.get("status")
    if after != before:
        add_outbox_message(
            state,
            "info",
            f"Agent run #{run['id']} status changed {before} -> {after}.",
            event_id=event["id"],
            related_task_id=run.get("task_id"),
            agent_run_id=run["id"],
        )
        return 1
    return 0

def apply_review_agent_run_action(state, event, action, autonomous, autonomy_level, allow_agent_run):
    if not programmer_action_allowed(event, autonomous, autonomy_level, "act"):
        add_outbox_message(
            state,
            "warning",
            f"Refused review_agent_run #{action.get('run_id')}: autonomy level does not allow review dispatch.",
            event_id=event["id"],
        )
        return 1
    if not allow_agent_run:
        add_outbox_message(
            state,
            "warning",
            f"Refused review_agent_run #{action.get('run_id')}: --allow-agent-run is required.",
            event_id=event["id"],
        )
        return 1
    implementation_run = find_agent_run(state, action.get("run_id"))
    if not implementation_run:
        add_outbox_message(state, "warning", f"Cannot review missing agent run #{action.get('run_id')}", event_id=event["id"])
        return 1
    if implementation_run.get("purpose", "implementation") != "implementation":
        add_outbox_message(state, "warning", f"Cannot review non-implementation run #{implementation_run['id']}", event_id=event["id"], agent_run_id=implementation_run["id"])
        return 1
    if implementation_run.get("status") not in ("completed", "failed"):
        return 0
    existing = find_review_run_for_implementation(state, implementation_run["id"])
    if existing:
        return 0
    task = task_by_id(state, implementation_run.get("task_id"))
    if not task:
        add_outbox_message(state, "warning", f"Cannot review run #{implementation_run['id']}: task missing", event_id=event["id"], agent_run_id=implementation_run["id"])
        return 1
    plan = find_task_plan(task, implementation_run.get("plan_id")) if implementation_run.get("plan_id") else None
    review_run = create_review_run_for_implementation(state, task, implementation_run, plan=plan)
    start_agent_run(state, review_run)
    return 1

def apply_followup_review_action(state, event, action, autonomous, autonomy_level):
    if not programmer_action_allowed(event, autonomous, autonomy_level, "propose"):
        add_outbox_message(
            state,
            "warning",
            f"Refused followup_review #{action.get('run_id')}: autonomy level does not allow follow-up tasks.",
            event_id=event["id"],
        )
        return 1
    review_run = find_agent_run(state, action.get("run_id"))
    if not review_run:
        add_outbox_message(state, "warning", f"Cannot follow up missing review run #{action.get('run_id')}", event_id=event["id"])
        return 1
    if review_run.get("purpose") != "review":
        add_outbox_message(state, "warning", f"Cannot follow up non-review run #{review_run['id']}", event_id=event["id"], agent_run_id=review_run["id"])
        return 1
    if review_run.get("status") not in ("completed", "failed"):
        return 0
    task = task_by_id(state, review_run.get("task_id"))
    if not task:
        add_outbox_message(state, "warning", f"Cannot follow up review run #{review_run['id']}: task missing", event_id=event["id"], agent_run_id=review_run["id"])
        return 1
    followup, status = create_follow_up_task_from_review(state, task, review_run)
    if followup:
        add_outbox_message(
            state,
            "info",
            f"Created follow-up task #{followup['id']} from review run #{review_run['id']} status={status}.",
            event_id=event["id"],
            related_task_id=followup["id"],
            agent_run_id=review_run["id"],
        )
        return 1
    add_outbox_message(
        state,
        "info",
        f"Review run #{review_run['id']} status={status}; no follow-up task needed.",
        event_id=event["id"],
        related_task_id=task["id"],
        agent_run_id=review_run["id"],
    )
    return 1

def record_verification_result(state, event, action, current_time, verify_command, result):
    run = {
        "id": next_id(state, "verification_run"),
        "event_id": event["id"],
        "task_id": action.get("task_id"),
        "reason": action.get("reason") or "",
        **result,
        "created_at": current_time,
        "updated_at": now_iso(),
    }
    state.setdefault("verification_runs", []).append(run)
    del state["verification_runs"][:-100]

    passed = result.get("exit_code") == 0
    message_type = "info" if passed else "warning"
    status = "passed" if passed else "failed"
    add_outbox_message(
        state,
        message_type,
        f"Verification {status}: {verify_command}\n{format_command_record(result)}",
        event_id=event["id"],
        related_task_id=action.get("task_id"),
    )
    if not passed:
        add_attention_item(
            state,
            "verification",
            f"Verification run #{run['id']} failed",
            f"{verify_command}\nexit_code={result.get('exit_code')}",
            related_task_id=action.get("task_id"),
            priority="high",
        )
    return run

def apply_run_verification_action(
    state,
    event,
    action,
    current_time,
    autonomous,
    autonomy_level,
    allow_verify,
    verify_command,
    verify_timeout,
):
    if event["type"] != "user_message" and not (autonomous and autonomy_level == "act"):
        add_outbox_message(
            state,
            "warning",
            "Refused run_verification: current mode does not allow verification.",
            event_id=event["id"],
            related_task_id=action.get("task_id"),
        )
        return 1
    if not allow_verify:
        add_outbox_message(
            state,
            "warning",
            "Refused run_verification: --allow-verify is required.",
            event_id=event["id"],
            related_task_id=action.get("task_id"),
        )
        return 1
    if not verify_command:
        add_outbox_message(
            state,
            "warning",
            "Refused run_verification: --verify-command is required.",
            event_id=event["id"],
            related_task_id=action.get("task_id"),
        )
        return 1

    result = run_command_record(verify_command, cwd=".", timeout=verify_timeout)
    record_verification_result(state, event, action, current_time, verify_command, result)
    return 1

def apply_write_action(
    state,
    event,
    action,
    current_time,
    autonomous,
    autonomy_level,
    allow_write,
    allowed_write_roots,
    allow_verify,
    verify_command,
    verify_timeout,
):
    action_type = action.get("type")
    dry_run = action.get("dry_run") is not False
    if event["type"] != "user_message" and not (autonomous and autonomy_level == "act"):
        add_outbox_message(
            state,
            "warning",
            f"Refused {action_type}: current mode does not allow writes.",
            event_id=event["id"],
            related_task_id=action.get("task_id"),
        )
        return 1
    if not allow_write:
        add_outbox_message(
            state,
            "warning",
            f"Refused {action_type}: --allow-write is required.",
            event_id=event["id"],
            related_task_id=action.get("task_id"),
        )
        return 1
    if not dry_run and (not allow_verify or not verify_command):
        add_outbox_message(
            state,
            "warning",
            f"Refused {action_type}: non-dry-run writes require --allow-verify and --verify-command.",
            event_id=event["id"],
            related_task_id=action.get("task_id"),
        )
        return 1

    try:
        if action_type == "write_file":
            result = write_file(
                action.get("path") or "",
                action.get("content") or "",
                allowed_write_roots,
                create=bool(action.get("create")),
                dry_run=dry_run,
            )
        elif action_type == "edit_file":
            result = edit_file(
                action.get("path") or "",
                action.get("old") or "",
                action.get("new") or "",
                allowed_write_roots,
                replace_all=bool(action.get("replace_all")),
                dry_run=dry_run,
            )
        else:
            return 0
    except ValueError as exc:
        add_outbox_message(
            state,
            "warning",
            f"{action_type} refused: {exc}",
            event_id=event["id"],
            related_task_id=action.get("task_id"),
        )
        return 1

    run = {
        "id": next_id(state, "write_run"),
        "event_id": event["id"],
        "task_id": action.get("task_id"),
        "action_type": action_type,
        "reason": action.get("reason") or "",
        **result,
        "created_at": current_time,
        "updated_at": now_iso(),
    }
    state.setdefault("write_runs", []).append(run)
    del state["write_runs"][:-100]

    add_outbox_message(
        state,
        "info",
        summarize_write_result(result),
        event_id=event["id"],
        related_task_id=action.get("task_id"),
    )

    message_count = 1
    if result.get("written"):
        verification_action = {
            "task_id": action.get("task_id"),
            "reason": f"Verification after {action_type} run #{run['id']}",
        }
        verification = run_command_record(verify_command, cwd=".", timeout=verify_timeout)
        record_verification_result(
            state,
            event,
            verification_action,
            current_time,
            verify_command,
            verification,
        )
        message_count += 1
    return message_count

def apply_action_plan(
    state,
    event,
    decision_plan,
    action_plan,
    current_time,
    allow_task_execution,
    task_timeout,
    allowed_read_roots=None,
    autonomous=False,
    autonomy_level="off",
    allow_agent_run=False,
    allow_verify=False,
    verify_command="",
    verify_timeout=300,
    allow_write=False,
    allowed_write_roots=None,
):
    counts = {"actions": 0, "messages": 0, "executed": 0, "waits": 0}
    memory_summary = action_plan.get("summary") or decision_plan.get("summary") or build_recall_summary(state, event, current_time)

    for action in action_plan.get("actions", []):
        action_type = action.get("type")
        counts["actions"] += 1

        if action_type == "record_memory":
            memory_summary = action.get("summary") or memory_summary
        elif action_type == "update_memory":
            text = action.get("text") or action.get("summary") or ""
            record_deep_memory(state, action.get("category") or "project", text, current_time)
        elif action_type in ("inspect_dir", "read_file", "search_text"):
            read_allowed = event["type"] == "user_message" or (autonomous and autonomy_level == "act")
            if not read_allowed:
                add_outbox_message(
                    state,
                    "warning",
                    f"Refused {action_type}: current mode does not allow inspection.",
                    event_id=event["id"],
                    related_task_id=action.get("task_id"),
                )
                counts["messages"] += 1
                continue
            counts["messages"] += apply_read_action(
                state,
                event,
                action,
                current_time,
                allowed_read_roots or [],
            )
        elif action_type == "self_review":
            counts["messages"] += apply_self_review_action(
                state,
                event,
                action,
                current_time,
                autonomous,
                autonomy_level,
            )
        elif action_type == "propose_task":
            counts["messages"] += apply_propose_task_action(
                state,
                event,
                action,
                current_time,
                autonomous,
                autonomy_level,
            )
        elif action_type == "plan_task":
            counts["messages"] += apply_plan_task_action(
                state,
                event,
                action,
                current_time,
                autonomous,
                autonomy_level,
            )
        elif action_type == "dispatch_task":
            counts["messages"] += apply_dispatch_task_action(
                state,
                event,
                action,
                current_time,
                autonomous,
                autonomy_level,
                allow_agent_run,
            )
        elif action_type == "collect_agent_result":
            counts["messages"] += apply_collect_agent_result_action(state, event, action)
        elif action_type == "review_agent_run":
            counts["messages"] += apply_review_agent_run_action(
                state,
                event,
                action,
                autonomous,
                autonomy_level,
                allow_agent_run,
            )
        elif action_type == "followup_review":
            counts["messages"] += apply_followup_review_action(
                state,
                event,
                action,
                autonomous,
                autonomy_level,
            )
        elif action_type == "run_verification":
            counts["messages"] += apply_run_verification_action(
                state,
                event,
                action,
                current_time,
                autonomous,
                autonomy_level,
                allow_verify,
                verify_command,
                verify_timeout,
            )
        elif action_type in ("write_file", "edit_file"):
            counts["messages"] += apply_write_action(
                state,
                event,
                action,
                current_time,
                autonomous,
                autonomy_level,
                allow_write,
                allowed_write_roots or [],
                allow_verify,
                verify_command,
                verify_timeout,
            )
        elif action_type == "send_message":
            text = action.get("text") or memory_summary
            message_type = action.get("message_type") or "info"
            if message_type not in ("assistant", "info", "warning"):
                message_type = "info"
            add_outbox_message(state, message_type, text, event_id=event["id"], related_task_id=action.get("task_id"))
            counts["messages"] += 1
        elif action_type == "ask_user":
            text = action.get("question") or action.get("text") or ""
            task_id = action.get("task_id")
            if text and not has_open_question(state, text, task_id):
                add_question(
                    state,
                    text,
                    event_id=event["id"],
                    related_task_id=task_id,
                    blocks=[f"task:{task_id}"] if task_id else [],
                )
                counts["messages"] += 1
        elif action_type == "wait_for_user":
            counts["waits"] += 1
            task_id = action.get("task_id")
            planned_status = decision_plan.get("agent_status", {})
            planned_question = planned_status.get("pending_question")
            text = action.get("question") or action.get("text")
            if not text and isinstance(planned_question, str):
                text = planned_question
            if text and not has_open_question(state, text, task_id):
                add_question(
                    state,
                    text,
                    event_id=event["id"],
                    related_task_id=task_id,
                    blocks=[f"task:{task_id}"] if task_id else [],
                )
                counts["messages"] += 1
            elif text:
                add_attention_item(
                    state,
                    "waiting",
                    "Waiting for user",
                    text,
                    related_task_id=task_id,
                    priority="normal",
                )
        elif action_type == "execute_task":
            if allow_task_execution:
                counts["executed"] += execute_task_action(state, action, task_timeout)
            else:
                add_outbox_message(
                    state,
                    "warning",
                    f"Refused execute_task decision for task #{action.get('task_id')}: task execution disabled.",
                    event_id=event["id"],
                    related_task_id=action.get("task_id"),
                )
                counts["messages"] += 1

    update_shallow_knowledge(state, event, memory_summary, current_time)
    update_agent_work_context_from_plan(state, event, decision_plan, action_plan, current_time)
    return counts

def process_events(
    state,
    reason,
    codex_auth=None,
    model=DEFAULT_CODEX_MODEL,
    base_url=DEFAULT_CODEX_WEB_BASE_URL,
    timeout=60,
    ai_ticks=False,
    create_internal_event=True,
    allow_task_execution=False,
    task_timeout=DEFAULT_TASK_TIMEOUT_SECONDS,
    guidance="",
    policy="",
    self_text="",
    desires="",
    autonomous=False,
    autonomy_level="off",
    allow_agent_run=False,
    allow_verify=False,
    verify_command="",
    verify_timeout=300,
    verify_interval_seconds=3600,
    allow_write=False,
    allowed_read_roots=None,
    allowed_write_roots=None,
):
    current_time = now_iso()
    if create_internal_event:
        add_event(state, reason, "runtime", {"pid": os.getpid()})
    processed_count = 0
    action_count = 0
    message_count = 0
    executed_count = 0

    for event in state["inbox"]:
        if event.get("processed_at"):
            continue

        decision_plan = think_phase(
            state,
            event,
            current_time,
            codex_auth,
            model,
            base_url,
            timeout,
            ai_ticks,
            allow_task_execution,
            guidance,
            policy,
            self_text=self_text,
            desires=desires,
            autonomous=autonomous,
            autonomy_level=autonomy_level,
            allow_agent_run=allow_agent_run,
            allow_verify=allow_verify,
            verify_command=verify_command,
            verify_interval_seconds=verify_interval_seconds,
            allow_write=allow_write,
            allowed_read_roots=allowed_read_roots,
            allowed_write_roots=allowed_write_roots,
        )
        action_plan = act_phase(
            state,
            event,
            decision_plan,
            current_time,
            codex_auth,
            model,
            base_url,
            timeout,
            ai_ticks,
            allow_task_execution,
            policy,
            self_text=self_text,
            desires=desires,
            autonomous=autonomous,
            autonomy_level=autonomy_level,
            allow_agent_run=allow_agent_run,
            allow_verify=allow_verify,
            verify_command=verify_command,
            allow_write=allow_write,
            allowed_read_roots=allowed_read_roots,
            allowed_write_roots=allowed_write_roots,
        )
        counts = apply_action_plan(
            state,
            event,
            decision_plan,
            action_plan,
            current_time,
            allow_task_execution,
            task_timeout,
            allowed_read_roots=allowed_read_roots,
            autonomous=autonomous,
            autonomy_level=autonomy_level,
            allow_agent_run=allow_agent_run,
            allow_verify=allow_verify,
            verify_command=verify_command,
            verify_timeout=verify_timeout,
            allow_write=allow_write,
            allowed_write_roots=allowed_write_roots,
        )
        event["decision_plan"] = decision_plan
        event["action_plan"] = action_plan
        event["processed_at"] = current_time
        processed_count += 1
        action_count += counts["actions"]
        message_count += counts["messages"]
        executed_count += counts["executed"]

    runtime = state["runtime_status"]
    autonomy = state.setdefault("autonomy", {})
    if autonomous and reason in ("startup", "passive_tick"):
        autonomy["cycles"] = int(autonomy.get("cycles") or 0) + 1
        autonomy["last_cycle_reason"] = reason
        autonomy["last_autonomous_action_at"] = current_time
        autonomy["updated_at"] = current_time
    runtime["last_woke_at"] = current_time
    runtime["last_evaluated_at"] = current_time
    runtime["last_action"] = (
        f"processed {processed_count} event(s), planned {action_count} action(s), "
        f"sent {message_count} message(s), executed {executed_count} task(s)"
    )
    append_log(f"- {current_time}: {runtime['last_action']} reason={reason}")
    return processed_count
