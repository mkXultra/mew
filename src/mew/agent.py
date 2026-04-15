import json
import os

from .config import (
    DEFAULT_CODEX_MODEL,
    DEFAULT_CODEX_WEB_BASE_URL,
    DEFAULT_MODEL_BACKEND,
    DEFAULT_TASK_TIMEOUT_SECONDS,
    MAX_RECENT_EVENTS,
)
from .errors import ModelBackendError
from .agent_runs import find_agent_run, get_agent_run_result, start_agent_run
from .model_backends import call_model_json, model_backend_label
from .plan_schema import (
    ACTION_TYPES,
    DECISION_TYPES,
    plan_schema_issue,
    validate_plan_items,
)
from .context import (
    build_context,
    build_recall_summary,
    resident_text_for_prompt,
)
from .programmer import (
    create_follow_up_task_from_review,
    create_implementation_run_from_plan,
    create_review_run_for_implementation,
    create_task_plan,
    find_active_implementation_run_for_plan,
    find_review_run_for_implementation,
    find_task_plan,
    latest_task_plan,
)
from .project_snapshot import update_project_snapshot_from_read_result
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
    pending_question_for_task,
)
from .tasks import (
    clip_output,
    execute_task_action,
    is_programmer_task,
    normalize_task_kind,
    normalize_task_id,
    open_tasks,
    task_by_id,
    task_question,
    task_kind,
    task_needs_programmer_plan,
    task_sort_key,
)
from .timeutil import elapsed_hours, now_iso
from .toolbox import format_command_record, run_command_record
from .thoughts import (
    normalize_thread_list,
    record_thought_journal_entry,
)
from .write_tools import (
    edit_file,
    restore_write_snapshot,
    snapshot_write_path,
    summarize_write_result,
    write_file,
)

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
    prompt_context=None,
):
    context = prompt_context or build_context(
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
        "Use open_threads for unfinished reasoning that should survive the next wake, and resolved_threads for threads closed now.\n"
        "If thought_thread_warning is present, explicitly carry those dropped threads forward or mark them resolved.\n"
        "Decision types you may emit: remember, send_message, ask_user, wait_for_user, "
        "execute_task, complete_task, run_verification, update_memory, inspect_dir, read_file, search_text, self_review, propose_task, refine_task, "
        "write_file, edit_file, plan_task, dispatch_task, collect_agent_result, review_agent_run, followup_review.\n"
        f"Autonomous mode is {str(bool(autonomous)).lower()} with level={autonomy_level}.\n"
        f"allow_agent_run is {str(bool(allow_agent_run)).lower()}.\n"
        f"allow_verify is {str(bool(allow_verify)).lower()} and verify_command_configured is {str(bool(verify_command)).lower()}.\n"
        f"allow_write is {str(bool(allow_write)).lower()}.\n"
        "When autonomous mode is false, do not do self-directed work unless it directly answers the user.\n"
        "When autonomous mode is true and there is no user input, use Self and Desires to choose useful small work.\n"
        "Use perception as passive read-only workspace observations; do not treat it as permission to read more.\n"
        "Autonomy levels: observe can remember and self_review; propose can also propose_task and plan_task for coding tasks only; "
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
        "Use complete_task only for a task whose objective is satisfied; autonomous completion is limited to self-proposed internal tasks.\n"
        "Use refine_task when autonomous synthesis has made a self-proposed internal task more concrete than its current title or plan.\n"
        "Use read-only inspection only when it directly helps the current task or memory, and only under allowed_read_roots.\n"
        "Use recent step_runs, thought_journal, and memory before inspecting; autonomous cycles should not repeat the same read-only action.\n"
        "If memory says a read was skipped as repeated, choose a different target or synthesize the next step instead of retrying it.\n"
        "Use write actions only for small targeted changes under allowed_write_roots; prefer dry_run before writing.\n"
        "Do not emit plan_task for personal, admin, research, or unknown tasks; use ask_user, send_message, or remember instead.\n"
        "Do not ask the same question if it already appears in unanswered_questions.\n"
        "Schema:\n"
        "{\n"
        '  "summary": "short memory of the current situation",\n'
        '  "open_threads": ["reasoning threads that should survive the next wake"],\n'
        '  "resolved_threads": ["threads resolved by this decision"],\n'
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
        '    {"type": "complete_task", "task_id": 1, "summary": "..."},\n'
        '    {"type": "write_file", "path": "...", "content": "...", "create": false, "dry_run": true},\n'
        '    {"type": "edit_file", "path": "...", "old": "...", "new": "...", "replace_all": false, "dry_run": true},\n'
        '    {"type": "self_review", "summary": "...", "proposed_task_title": "...", "proposed_task_description": "..."},\n'
        '    {"type": "propose_task", "title": "...", "description": "...", "priority": "low|normal|high"},\n'
        '    {"type": "refine_task", "task_id": 1, "title": "...", "description": "...", "kind": "coding", "notes": "...", "reset_plan": true},\n'
        '    {"type": "plan_task", "task_id": 1, "objective": "...", "approach": "..."},\n'
        '    {"type": "dispatch_task", "task_id": 1, "plan_id": 1, "reason": "..."},\n'
        '    {"type": "collect_agent_result", "run_id": 1},\n'
        '    {"type": "review_agent_run", "run_id": 1},\n'
        '    {"type": "followup_review", "run_id": 2},\n'
        '    {"type": "execute_task", "task_id": 1, "reason": "..."}\n'
        "  ]\n"
        "}\n\n"
        f"Human guidance:\n{resident_text_for_prompt(guidance)}\n\n"
        f"Human policy:\n{policy or '(none)'}\n\n"
        f"Self:\n{resident_text_for_prompt(self_text)}\n\n"
        f"Desires:\n{resident_text_for_prompt(desires)}\n\n"
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
    prompt_context=None,
):
    context = prompt_context or build_context(
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
        "Preserve or refine open_threads when follow-up is needed, and mark resolved_threads when actions close a thread.\n"
        "If thought_thread_warning is present, do not silently drop those threads again.\n"
        "Allowed action types: record_memory, send_message, ask_user, wait_for_user, execute_task, complete_task, run_verification, "
        "update_memory, inspect_dir, read_file, search_text, self_review, propose_task, refine_task, "
        "write_file, edit_file, plan_task, dispatch_task, collect_agent_result, review_agent_run, followup_review.\n"
        f"Autonomous mode is {str(bool(autonomous)).lower()} with level={autonomy_level}.\n"
        f"allow_agent_run is {str(bool(allow_agent_run)).lower()}.\n"
        f"allow_verify is {str(bool(allow_verify)).lower()} and verify_command_configured is {str(bool(verify_command)).lower()}.\n"
        f"allow_write is {str(bool(allow_write)).lower()}.\n"
        "Respect the autonomy level: observe may record_memory and self_review only; propose may propose_task/plan_task for coding tasks only; "
        "act may use allowed read-only inspection and programmer-loop actions. "
        "Use perception as passive read-only workspace observations; it does not expand allowed_read_roots. "
        "Starting agent runs requires allow_agent_run in local state. "
        "Local task command execution still requires allow_task_execution. "
        "Verification command execution requires run_verification plus allow_verify and a configured verify command.\n"
        "File writes require write_file/edit_file plus allow_write, allowed_write_roots, and a configured verification command unless dry_run=true. "
        "Omitting dry_run is treated as dry_run=true; set dry_run=false explicitly to write.\n"
        "If the DecisionPlan is waiting on concrete user input, turn it into ask_user or include question on wait_for_user.\n"
        "Use execute_task only when the task is ready, has command, has auto_execute=true, "
        f"and allow_task_execution is {str(bool(allow_task_execution)).lower()}.\n"
        "Use complete_task only when the task objective is satisfied; autonomous completion is limited to self-proposed internal tasks.\n"
        "Use refine_task to update a self-proposed internal task after synthesis, instead of proposing a duplicate task.\n"
        "Use read-only inspection only under allowed_read_roots. If no read root is allowed, do not emit read actions.\n"
        "Do not repeat the same read-only action shown in recent step_runs or thought_journal during autonomous cycles.\n"
        "If the DecisionPlan repeats a read that memory says was skipped, convert it to record_memory, update_memory, self_review, or propose_task instead.\n"
        "Use write actions only under allowed_write_roots. If no write root is allowed, do not emit write actions.\n"
        "Do not invent shell commands. Reference tasks by task_id only. Do not emit plan_task for personal, admin, research, or unknown tasks.\n"
        "Do not repeat unanswered questions already present in state.\n"
        "Schema:\n"
        "{\n"
        '  "summary": "short action summary",\n'
        '  "open_threads": ["action follow-up threads that should survive the next wake"],\n'
        '  "resolved_threads": ["threads resolved by these actions"],\n'
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
        '    {"type": "complete_task", "task_id": 1, "summary": "..."},\n'
        '    {"type": "write_file", "path": "...", "content": "...", "create": false, "dry_run": true},\n'
        '    {"type": "edit_file", "path": "...", "old": "...", "new": "...", "replace_all": false, "dry_run": true},\n'
        '    {"type": "self_review", "summary": "...", "proposed_task_title": "...", "proposed_task_description": "..."},\n'
        '    {"type": "propose_task", "title": "...", "description": "...", "priority": "low|normal|high"},\n'
        '    {"type": "refine_task", "task_id": 1, "title": "...", "description": "...", "kind": "coding", "notes": "...", "reset_plan": true},\n'
        '    {"type": "plan_task", "task_id": 1, "objective": "...", "approach": "..."},\n'
        '    {"type": "dispatch_task", "task_id": 1, "plan_id": 1, "reason": "..."},\n'
        '    {"type": "collect_agent_result", "run_id": 1},\n'
        '    {"type": "review_agent_run", "run_id": 1},\n'
        '    {"type": "followup_review", "run_id": 2},\n'
        '    {"type": "execute_task", "task_id": 1, "reason": "..."}\n'
        "  ]\n"
        "}\n\n"
        f"Human policy:\n{policy or '(none)'}\n\n"
        f"Self:\n{resident_text_for_prompt(self_text)}\n\n"
        f"Desires:\n{resident_text_for_prompt(desires)}\n\n"
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
        if autonomous and latest_open_verification_attention(state):
            return
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

def has_decision_type(decisions, decision_type):
    return any(decision.get("type") == decision_type for decision in decisions)

def decisions_create_task(decisions):
    return any(
        decision.get("type") == "propose_task"
        or (
            decision.get("type") == "self_review"
            and bool(decision.get("proposed_task_title"))
        )
        for decision in decisions
    )

def latest_open_verification_attention(state):
    for item in reversed(open_attention_items(state)):
        if item.get("kind") == "verification":
            return item
    return None

def append_verification_repair_decision(state, decisions, autonomy_level):
    if autonomy_level not in ("propose", "act"):
        return False
    attention = latest_open_verification_attention(state)
    if not attention:
        return False
    title = f"Fix {attention.get('title') or 'failing runtime verification'}"
    if open_task_with_title(state, title):
        return False
    decisions.append(
        {
            "type": "propose_task",
            "title": title,
            "description": (
                "Investigate and fix the failing runtime verification.\n\n"
                f"Attention #{attention.get('id')}: {attention.get('title')}\n"
                f"Reason:\n{attention.get('reason') or '(none)'}"
            ),
            "priority": "high",
        }
    )
    return True

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

    if append_verification_repair_decision(state, decisions, autonomy_level):
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
    if not has_decision_type(decisions, "self_review") and (
        hours_since_self_review is None or hours_since_self_review >= 1
    ):
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
            and not run.get("followup_processed_at")
        ):
            decisions.append({"type": "followup_review", "run_id": run["id"]})
            return

    if append_runtime_verification_decision(
        state,
        decisions,
        autonomy_level,
        allow_verify,
        verify_command,
        verify_interval_seconds,
        current_time,
    ):
        return

    if autonomy_level in ("propose", "act"):
        for task in sorted(open_tasks(state), key=task_sort_key):
            if (
                task_needs_programmer_plan(task)
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
                and is_programmer_task(task)
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
        autonomy_level in ("propose", "act")
        and not decisions_create_task(decisions)
        and not open_task_with_title(state, "Review mew self direction")
    ):
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

def append_runtime_verification_decision(
    state,
    decisions,
    autonomy_level,
    allow_verify,
    verify_command,
    verify_interval_seconds,
    current_time,
):
    if any(decision.get("type") == "run_verification" for decision in decisions):
        return False
    if not (
        autonomy_level == "act"
        and allow_verify
        and verify_command
        and runtime_verification_due(state, current_time, verify_interval_seconds)
    ):
        return False
    decisions.append(
        {
            "type": "run_verification",
            "reason": "Configured runtime verification is due.",
        }
    )
    return True

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
        append_passive_decisions(
            state,
            decisions,
            allow_task_execution,
            autonomous=autonomous,
            autonomy_level=autonomy_level,
        )
        if autonomous:
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
        append_passive_decisions(
            state,
            decisions,
            allow_task_execution,
            autonomous=autonomous,
            autonomy_level=autonomy_level,
        )
        if autonomous:
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
        "open_threads": [],
        "resolved_threads": [],
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
    schema_issues = []
    if not isinstance(plan, dict):
        schema_issues.append(plan_schema_issue("warning", "$", "decision plan must be an object"))
        plan = {}
    summary = plan.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        summary = fallback_summary

    decisions = plan.get("decisions")
    if not isinstance(decisions, list):
        if "decisions" in plan:
            schema_issues.append(plan_schema_issue("warning", "decisions", "must be a list"))
        decisions = []

    normalized = []
    for index, decision in enumerate(decisions):
        if not isinstance(decision, dict):
            schema_issues.append(plan_schema_issue("warning", f"decisions[{index}]", "must be an object"))
            continue
        decision_type = decision.get("type")
        if not isinstance(decision_type, str):
            schema_issues.append(plan_schema_issue("warning", f"decisions[{index}].type", "must be a string"))
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
            "kind",
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
        for key in ("create", "dry_run", "replace_all", "reset_plan"):
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
    schema_issues.extend(validate_plan_items(normalized, DECISION_TYPES, "decisions"))
    return {
        "summary": summary,
        "open_threads": normalize_thread_list(plan.get("open_threads")),
        "resolved_threads": normalize_thread_list(plan.get("resolved_threads")),
        "agent_status": agent_status,
        "decisions": normalized,
        "schema_issues": schema_issues,
    }

REQUIRED_MODEL_GUARDRAIL_DECISIONS = {
    "collect_agent_result",
    "review_agent_run",
    "followup_review",
    "run_verification",
    "propose_task",
    "refine_task",
    "plan_task",
    "dispatch_task",
}


def required_model_guardrail_decision(decision):
    decision_type = decision.get("type")
    if decision_type in REQUIRED_MODEL_GUARDRAIL_DECISIONS:
        return True
    return decision_type == "self_review" and bool(decision.get("proposed_task_title"))


def decision_matches(candidate, existing):
    if candidate.get("type") != existing.get("type"):
        return False
    target_keys = ("task_id", "run_id", "plan_id")
    compared = False
    for key in target_keys:
        if candidate.get(key) is None and existing.get(key) is None:
            continue
        compared = True
        if candidate.get(key) != existing.get(key):
            return False
    return compared or candidate.get("type") == existing.get("type")


def append_missing_guardrail_decisions(plan, fallback):
    decisions = plan.setdefault("decisions", [])
    for candidate in fallback.get("decisions", []):
        if not required_model_guardrail_decision(candidate):
            continue
        if any(decision_matches(candidate, existing) for existing in decisions):
            continue
        decisions.append(dict(candidate))
    return plan


def think_phase(
    state,
    event,
    current_time,
    model_auth,
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
    model_backend=DEFAULT_MODEL_BACKEND,
    prompt_context=None,
    log_phases=True,
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
    if not model_auth or not should_use_ai_for_event(event, event["type"], ai_ticks):
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
        prompt_context=prompt_context,
    )
    try:
        if log_phases:
            append_log(f"- {current_time}: think_phase {model_backend} start event={event['id']}")
        plan = call_model_json(model_backend, model_auth, prompt, model, base_url, timeout)
        if log_phases:
            append_log(f"- {current_time}: think_phase {model_backend} ok event={event['id']}")
    except ModelBackendError as exc:
        if log_phases:
            append_log(f"- {current_time}: think_phase {model_backend} error event={event['id']} error={exc}")
        fallback["decisions"].append(
            {
                "type": "send_message",
                "message_type": "warning",
                "text": f"{model_backend_label(model_backend)} THINK error: {exc}",
            }
        )
        return fallback
    normalized = append_missing_guardrail_decisions(normalize_decision_plan(plan, fallback["summary"]), fallback)
    if log_phases and normalized.get("schema_issues"):
        append_log(
            "- "
            f"{current_time}: think_phase schema_issues event={event['id']} "
            f"count={len(normalized['schema_issues'])}"
        )
    return normalized

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
            "complete_task",
            "run_verification",
            "update_memory",
            "inspect_dir",
            "read_file",
            "search_text",
            "write_file",
            "edit_file",
            "self_review",
            "propose_task",
            "refine_task",
            "plan_task",
            "dispatch_task",
            "collect_agent_result",
            "review_agent_run",
            "followup_review",
        ):
            actions.append(dict(decision))
    if not actions:
        actions.append({"type": "record_memory", "summary": decision_plan["summary"]})
    return {
        "summary": decision_plan["summary"],
        "open_threads": list(decision_plan.get("open_threads") or []),
        "resolved_threads": list(decision_plan.get("resolved_threads") or []),
        "actions": actions,
    }

def normalize_action_plan(plan, fallback_plan):
    schema_issues = []
    if not isinstance(plan, dict):
        schema_issues.append(plan_schema_issue("warning", "$", "action plan must be an object"))
        plan = {}
    summary = plan.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        summary = fallback_plan.get("summary", "")

    actions = plan.get("actions")
    if not isinstance(actions, list):
        if "actions" in plan:
            schema_issues.append(plan_schema_issue("warning", "actions", "must be a list"))
        actions = fallback_plan.get("actions", [])

    normalized = []
    for index, action in enumerate(actions):
        if not isinstance(action, dict):
            schema_issues.append(plan_schema_issue("warning", f"actions[{index}]", "must be an object"))
            continue
        action_type = action.get("type")
        if action_type not in ACTION_TYPES:
            schema_issues.append(plan_schema_issue("warning", f"actions[{index}].type", f"unsupported type {action_type!r}"))
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
            "kind",
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
        for key in ("create", "dry_run", "replace_all", "reset_plan"):
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
    schema_issues.extend(validate_plan_items(normalized, ACTION_TYPES, "actions"))

    return {
        "summary": summary,
        "open_threads": normalize_thread_list(plan.get("open_threads"))
        or normalize_thread_list(fallback_plan.get("open_threads")),
        "resolved_threads": normalize_thread_list(plan.get("resolved_threads"))
        or normalize_thread_list(fallback_plan.get("resolved_threads")),
        "actions": normalized,
        "schema_issues": schema_issues,
    }

def act_phase(
    state,
    event,
    decision_plan,
    current_time,
    model_auth,
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
    model_backend=DEFAULT_MODEL_BACKEND,
    prompt_context=None,
    log_phases=True,
):
    fallback = deterministic_action_plan(decision_plan)
    if not model_auth or not should_use_ai_for_event(event, event["type"], ai_ticks):
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
        prompt_context=prompt_context,
    )
    try:
        if log_phases:
            append_log(f"- {current_time}: act_phase {model_backend} start event={event['id']}")
        action_plan = call_model_json(model_backend, model_auth, prompt, model, base_url, timeout)
        if log_phases:
            append_log(f"- {current_time}: act_phase {model_backend} ok event={event['id']}")
    except ModelBackendError as exc:
        if log_phases:
            append_log(f"- {current_time}: act_phase {model_backend} error event={event['id']} error={exc}")
        fallback["actions"].append(
            {
                "type": "send_message",
                "message_type": "warning",
                "text": f"{model_backend_label(model_backend)} ACT error: {exc}",
            }
        )
        return fallback
    normalized = normalize_action_plan(action_plan, fallback)
    if log_phases and normalized.get("schema_issues"):
        append_log(
            "- "
            f"{current_time}: act_phase schema_issues event={event['id']} "
            f"count={len(normalized['schema_issues'])}"
        )
    return normalized

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
                "complete_task",
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

def update_user_status_after_plan(state, event, action_plan, counts, current_time):
    if event.get("type") != "user_message":
        return
    user = state.setdefault("user_status", {})
    actions = action_plan.get("actions", [])
    if any(action.get("type") in ("ask_user", "wait_for_user") for action in actions):
        user["mode"] = "needs_user"
    elif counts.get("messages", 0) > 0 or event.get("processed_at"):
        user["mode"] = "idle"
    user["updated_at"] = current_time


def read_action_key(action):
    action_type = action.get("type")
    if action_type == "inspect_dir":
        return ("inspect_dir", str(action.get("path") or "."))
    if action_type == "read_file":
        return ("read_file", str(action.get("path") or ""))
    if action_type == "search_text":
        return (
            "search_text",
            str(action.get("path") or "."),
            str(action.get("query") or ""),
        )
    return None


def recently_repeated_read_action(state, action, limit=5):
    key = read_action_key(action)
    if not key:
        return False
    for thought in reversed(state.get("thought_journal", [])[-limit:]):
        for previous in thought.get("actions") or []:
            if read_action_key(previous) == key:
                return True
    for run in reversed(state.get("step_runs", [])[-limit:]):
        for previous in run.get("actions") or []:
            if read_action_key(previous) == key:
                return True
    return False


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
    update_project_snapshot_from_read_result(state, action_type, result, current_time)
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
    message = add_outbox_message(
        state,
        "info",
        text,
        event_id=event["id"],
        related_task_id=action.get("task_id"),
    )
    if event.get("type") != "user_message":
        message["read_at"] = current_time
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
        "kind": "",
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
    if (
        event["type"] != "user_message"
        and autonomous
        and open_tasks(state)
        and action.get("priority") != "high"
    ):
        record_deep_memory(
            state,
            "decisions",
            f"Deferred propose_task because open tasks already exist: {title}",
            current_time,
        )
        return 0
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
        if event["type"] != "user_message" and autonomous and open_tasks(state):
            record_deep_memory(
                state,
                "decisions",
                (
                    "Deferred self-review task proposal because open tasks already exist: "
                    f"{title}"
                ),
                current_time,
            )
            return message_count
        can_propose = event["type"] == "user_message" or (
            autonomous and autonomy_level in ("propose", "act")
        )
        if not can_propose:
            record_deep_memory(
                state,
                "decisions",
                (
                    "Deferred self-review task proposal because the current autonomy "
                    f"level does not allow task creation: {title}"
                ),
                current_time,
            )
            return message_count
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
    if not is_programmer_task(task):
        add_outbox_message(
            state,
            "warning",
            (
                f"Refused plan_task for task #{task['id']}: "
                f"task kind {task_kind(task)!r} is not a coding task."
            ),
            event_id=event["id"],
            related_task_id=task["id"],
        )
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
    if not is_programmer_task(task):
        add_outbox_message(
            state,
            "warning",
            (
                f"Refused dispatch_task for task #{task['id']}: "
                f"task kind {task_kind(task)!r} is not a coding task."
            ),
            event_id=event["id"],
            related_task_id=task["id"],
        )
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
    existing_run = find_active_implementation_run_for_plan(state, task["id"], plan.get("id"))
    if existing_run:
        add_outbox_message(
            state,
            "info",
            f"Skipped dispatch_task for task #{task['id']}: implementation run #{existing_run['id']} is already {existing_run.get('status')}.",
            event_id=event["id"],
            related_task_id=task["id"],
            agent_run_id=existing_run["id"],
        )
        return 1
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


def is_self_proposed_task(task):
    notes = str(task.get("notes") or "")
    return "Proposed by mew" in notes or "Proposed by self_review" in notes


def is_mew_internal_task(task):
    notes = str(task.get("notes") or "")
    return (
        "Proposed by mew" in notes
        or "Proposed by self_review" in notes
        or "Created by mew" in notes
    )


def append_agent_task_note(task, note):
    existing = task.get("notes") or ""
    task["notes"] = f"{existing.rstrip()}\n{note}".strip()


def _refine_text(value):
    if not isinstance(value, str):
        return ""
    return value.strip()


def apply_refine_task_action(state, event, action, current_time, autonomous, autonomy_level):
    task = task_by_id(state, action.get("task_id"))
    if not task:
        add_outbox_message(state, "warning", f"Cannot refine missing task #{action.get('task_id')}", event_id=event["id"])
        return 1
    allowed = event["type"] == "user_message"
    if autonomous:
        allowed = allowed or (autonomy_level == "act" and is_mew_internal_task(task))
    if not allowed:
        add_outbox_message(
            state,
            "warning",
            f"Refused refine_task for task #{task['id']}: only user-requested or mew-internal tasks can be refined this way.",
            event_id=event["id"],
            related_task_id=task["id"],
        )
        return 1

    changed = []
    title = _refine_text(action.get("title"))
    if title and title != task.get("title"):
        task["title"] = title
        changed.append("title")
    description = _refine_text(action.get("description"))
    if description and description != task.get("description"):
        task["description"] = description
        changed.append("description")
    kind = normalize_task_kind(action.get("kind"))
    if kind and kind != task.get("kind"):
        task["kind"] = kind
        changed.append("kind")
    priority = action.get("priority")
    if priority in ("low", "normal", "high") and priority != task.get("priority"):
        task["priority"] = priority
        changed.append("priority")
    notes = _refine_text(action.get("notes") or action.get("summary") or action.get("reason"))
    if notes:
        append_agent_task_note(task, f"{current_time} refine_task: {notes}")
        changed.append("notes")

    if not changed and not action.get("reset_plan"):
        return 0

    task["updated_at"] = current_time
    reset_plan = bool(action.get("reset_plan"))
    if reset_plan:
        for plan in task.get("plans") or []:
            if plan.get("status") in ("planned", "dry_run"):
                plan["status"] = "superseded"
                plan["updated_at"] = current_time
        task["latest_plan_id"] = None
        changed.append("plan")
        if task_kind(task) == "coding":
            create_task_plan(
                state,
                task,
                cwd=action.get("cwd"),
                model=action.get("agent_model"),
                review_model=action.get("review_model"),
                objective=action.get("objective") or task.get("description") or task.get("title"),
                approach=action.get("approach"),
            )

    add_outbox_message(
        state,
        "info",
        f"Refined task #{task['id']}: {', '.join(dict.fromkeys(changed))}",
        event_id=event["id"],
        related_task_id=task["id"],
    )
    return 1


def apply_complete_task_action(state, event, action, current_time, autonomous, autonomy_level):
    task_id = action.get("task_id")
    task = task_by_id(state, task_id)
    if not task:
        add_outbox_message(state, "warning", f"Cannot complete missing task #{task_id}", event_id=event["id"])
        return 1
    if task.get("status") == "done":
        return 0

    allowed = event["type"] == "user_message"
    if autonomous:
        allowed = allowed or (autonomy_level == "act" and is_self_proposed_task(task))
    if not allowed:
        add_outbox_message(
            state,
            "warning",
            f"Refused complete_task for task #{task['id']}: only user-requested or self-proposed autonomous tasks can be completed this way.",
            event_id=event["id"],
            related_task_id=task["id"],
        )
        return 1

    summary = action.get("summary") or action.get("reason") or "Completed by mew."
    append_agent_task_note(task, f"{current_time} complete_task: {summary}")
    task["status"] = "done"
    task["updated_at"] = current_time
    add_outbox_message(
        state,
        "info",
        f"Completed task #{task['id']}: {task['title']}",
        event_id=event["id"],
        related_task_id=task["id"],
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
            verification_failure_reason(verify_command, result),
            related_task_id=action.get("task_id"),
            priority="high",
        )
    return run

def verification_failure_reason(verify_command, result):
    parts = [verify_command, f"exit_code={result.get('exit_code')}"]
    stdout = result.get("stdout") or ""
    stderr = result.get("stderr") or ""
    if stdout:
        parts.append("stdout:\n" + clip_output(stdout, 2000))
    if stderr:
        parts.append("stderr:\n" + clip_output(stderr, 2000))
    return "\n".join(parts)

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

    if action.get("_precomputed_verification_error"):
        add_outbox_message(
            state,
            "warning",
            f"Refused run_verification: {action.get('_precomputed_verification_error')}",
            event_id=event["id"],
            related_task_id=action.get("task_id"),
        )
        return 1
    result = action.get("_precomputed_verification")
    if not isinstance(result, dict):
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

    snapshot = None
    try:
        if not dry_run:
            snapshot = snapshot_write_path(
                action.get("path") or "",
                allowed_write_roots,
                create=bool(action.get("create")) if action_type == "write_file" else False,
            )
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
        if verification.get("exit_code") != 0 and snapshot:
            try:
                rollback = restore_write_snapshot(snapshot)
                run["rolled_back"] = True
                run["rollback"] = {
                    key: value
                    for key, value in rollback.items()
                    if key != "content"
                }
                run["updated_at"] = now_iso()
                add_outbox_message(
                    state,
                    "warning",
                    f"Rolled back write run #{run['id']} because verification failed.",
                    event_id=event["id"],
                    related_task_id=action.get("task_id"),
                )
                message_count += 1
            except (OSError, ValueError) as exc:
                run["rolled_back"] = False
                run["rollback_error"] = str(exc)
                run["updated_at"] = now_iso()
                add_attention_item(
                    state,
                    "rollback",
                    f"Rollback failed for write run #{run['id']}",
                    str(exc),
                    related_task_id=action.get("task_id"),
                    priority="high",
                )
                add_outbox_message(
                    state,
                    "warning",
                    f"Rollback failed for write run #{run['id']}: {exc}",
                    event_id=event["id"],
                    related_task_id=action.get("task_id"),
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
    cycle_reason="",
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
            if event["type"] != "user_message" and recently_repeated_read_action(state, action):
                skip_text = (
                    f"Skipped repeated {action_type} for {action.get('path') or '.'}; "
                    "recent context already contains that inspection. Choose a different target "
                    "or synthesize the next step instead of retrying the same read."
                )
                message = add_outbox_message(
                    state,
                    "info",
                    skip_text,
                    event_id=event["id"],
                    related_task_id=action.get("task_id"),
                )
                message["read_at"] = current_time
                record_deep_memory(state, "decisions", skip_text, current_time)
                memory_summary = skip_text
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
        elif action_type == "refine_task":
            counts["messages"] += apply_refine_task_action(
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
        elif action_type == "complete_task":
            counts["messages"] += apply_complete_task_action(
                state,
                event,
                action,
                current_time,
                autonomous,
                autonomy_level,
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
    update_user_status_after_plan(state, event, action_plan, counts, current_time)
    record_thought_journal_entry(
        state,
        event,
        current_time,
        decision_plan,
        action_plan,
        counts,
        cycle_reason=cycle_reason,
    )
    return counts

def next_unprocessed_event(state, event_type=None):
    for event in state["inbox"]:
        if event_type is not None and event.get("type") != event_type:
            continue
        if not event.get("processed_at"):
            return event
    return None

def plan_event(
    state,
    event,
    current_time,
    model_auth=None,
    model=DEFAULT_CODEX_MODEL,
    base_url=DEFAULT_CODEX_WEB_BASE_URL,
    model_backend=DEFAULT_MODEL_BACKEND,
    timeout=60,
    ai_ticks=False,
    allow_task_execution=False,
    guidance="",
    policy="",
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
    log_phases=True,
):
    prompt_context = build_context(
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
    decision_plan = think_phase(
        state,
        event,
        current_time,
        model_auth,
        model,
        base_url=base_url,
        timeout=timeout,
        ai_ticks=ai_ticks,
        allow_task_execution=allow_task_execution,
        guidance=guidance,
        policy=policy,
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
        model_backend=model_backend,
        prompt_context=prompt_context,
        log_phases=log_phases,
    )
    action_plan = act_phase(
        state,
        event,
        decision_plan,
        current_time,
        model_auth,
        model,
        base_url=base_url,
        timeout=timeout,
        ai_ticks=ai_ticks,
        allow_task_execution=allow_task_execution,
        policy=policy,
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
        model_backend=model_backend,
        prompt_context=prompt_context,
        log_phases=log_phases,
    )
    return decision_plan, action_plan

def find_event(state, event_id):
    wanted = str(event_id)
    for event in state["inbox"]:
        if str(event.get("id")) == wanted:
            return event
    return None

def public_action_plan(action_plan):
    if not isinstance(action_plan, dict):
        return action_plan
    clean = dict(action_plan)
    clean["actions"] = [
        {
            key: value
            for key, value in action.items()
            if not str(key).startswith("_")
        }
        for action in action_plan.get("actions", [])
    ]
    return clean

def apply_event_plans(
    state,
    event_id,
    decision_plan,
    action_plan,
    current_time,
    reason,
    allow_task_execution=False,
    task_timeout=DEFAULT_TASK_TIMEOUT_SECONDS,
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
    event = find_event(state, event_id)
    if not event or event.get("processed_at"):
        return None

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
        cycle_reason=reason,
    )
    event["decision_plan"] = decision_plan
    event["action_plan"] = public_action_plan(action_plan)
    event["processed_at"] = current_time
    update_user_status_after_plan(state, event, action_plan, counts, current_time)
    return counts

def update_runtime_processing_summary(
    state,
    reason,
    current_time,
    processed_count,
    action_count,
    message_count,
    executed_count,
    autonomous=False,
):
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

def process_events(
    state,
    reason,
    model_auth=None,
    model=DEFAULT_CODEX_MODEL,
    base_url=DEFAULT_CODEX_WEB_BASE_URL,
    model_backend=DEFAULT_MODEL_BACKEND,
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

        decision_plan, action_plan = plan_event(
            state,
            event,
            current_time,
            model_auth,
            model,
            base_url=base_url,
            timeout=timeout,
            ai_ticks=ai_ticks,
            allow_task_execution=allow_task_execution,
            guidance=guidance,
            policy=policy,
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
            model_backend=model_backend,
        )
        counts = apply_event_plans(
            state,
            event["id"],
            decision_plan,
            action_plan,
            current_time,
            reason,
            allow_task_execution=allow_task_execution,
            task_timeout=task_timeout,
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
        if counts is None:
            continue
        processed_count += 1
        action_count += counts["actions"]
        message_count += counts["messages"]
        executed_count += counts["executed"]

    update_runtime_processing_summary(
        state,
        reason,
        current_time,
        processed_count,
        action_count,
        message_count,
        executed_count,
        autonomous=autonomous,
    )
    return processed_count
