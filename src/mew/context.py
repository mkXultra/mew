import json

from .config import LOG_FILE
from .perception import perceive_workspace
from .project_snapshot import snapshot_for_context
from .state import open_attention_items, open_questions
from .tasks import open_tasks, summarize_tasks, task_kind, task_sort_key
from .thoughts import dropped_thread_warning_for_context, recent_thoughts_for_context
from .timeutil import elapsed_hours

MAX_CONTEXT_TEXT_CHARS = 1200
MAX_CONTEXT_LONG_TEXT_CHARS = 2000
MAX_CONTEXT_TASKS = 25
MAX_CONTEXT_QUESTIONS = 20
MAX_CONTEXT_QUESTION_BLOCKS = 5
MAX_CONTEXT_ATTENTION_ITEMS = 25
MAX_CONTEXT_AGENT_RUNS = 8
MAX_CONTEXT_STEP_RUNS = 5
MAX_CONTEXT_STEP_EFFECTS = 8
MAX_CONTEXT_RUN_OUTPUT_CHARS = 600
MAX_CONTEXT_MEMORY_CHARS = 800
MAX_CONTEXT_QUESTION_BLOCK_CHARS = 200
MAX_CONTEXT_CONVERSATION_ITEMS = 12
MAX_CONTEXT_CONVERSATION_TEXT_CHARS = 1000


def clip_context_text(value, limit=MAX_CONTEXT_TEXT_CHARS):
    if value is None:
        return ""
    text = str(value)
    if len(text) <= limit:
        return text
    return text[:limit] + "\n... truncated ..."


def json_char_count(value):
    try:
        return len(json.dumps(value, ensure_ascii=False, sort_keys=True))
    except (TypeError, ValueError):
        return len(str(value))


def latest_item(items):
    return items[-1] if items else None


def compact_recent_items(items, limit):
    values = list(items or [])
    return values[-limit:]


def task_plan_for_context(plan):
    if not plan:
        return None
    return {
        "id": plan.get("id"),
        "status": plan.get("status"),
        "backend": plan.get("backend"),
        "model": plan.get("model"),
        "review_model": plan.get("review_model"),
        "cwd": clip_context_text(plan.get("cwd"), 400),
        "objective": clip_context_text(plan.get("objective"), MAX_CONTEXT_TEXT_CHARS),
        "approach": clip_context_text(plan.get("approach"), MAX_CONTEXT_TEXT_CHARS),
        "done_criteria": clip_context_text(plan.get("done_criteria"), MAX_CONTEXT_TEXT_CHARS),
        "implementation_prompt_chars": len(plan.get("implementation_prompt") or ""),
        "review_prompt_chars": len(plan.get("review_prompt") or ""),
        "created_at": plan.get("created_at"),
        "updated_at": plan.get("updated_at"),
    }


def task_run_for_context(run):
    if not run:
        return None
    return {
        "command": clip_context_text(run.get("command"), 400),
        "cwd": clip_context_text(run.get("cwd"), 400),
        "started_at": run.get("started_at"),
        "finished_at": run.get("finished_at"),
        "exit_code": run.get("exit_code"),
        "stdout_tail": clip_context_text(run.get("stdout"), MAX_CONTEXT_RUN_OUTPUT_CHARS),
        "stderr_tail": clip_context_text(run.get("stderr"), MAX_CONTEXT_RUN_OUTPUT_CHARS),
    }


def task_for_context(task):
    plans = list(task.get("plans") or [])
    runs = list(task.get("runs") or [])
    return {
        "id": task.get("id"),
        "title": clip_context_text(task.get("title"), 400),
        "kind": task_kind(task),
        "description": clip_context_text(task.get("description"), MAX_CONTEXT_TEXT_CHARS),
        "status": task.get("status"),
        "priority": task.get("priority"),
        "notes": clip_context_text(task.get("notes"), MAX_CONTEXT_TEXT_CHARS),
        "command": clip_context_text(task.get("command"), 400),
        "cwd": clip_context_text(task.get("cwd"), 400),
        "auto_execute": bool(task.get("auto_execute")),
        "agent_backend": task.get("agent_backend") or "",
        "agent_model": task.get("agent_model") or "",
        "has_agent_prompt": bool(task.get("agent_prompt")),
        "agent_prompt_chars": len(task.get("agent_prompt") or ""),
        "agent_run_id": task.get("agent_run_id"),
        "latest_plan_id": task.get("latest_plan_id"),
        "plan_count": len(plans),
        "latest_plan": task_plan_for_context(latest_item(plans)),
        "run_count": len(runs),
        "latest_run": task_run_for_context(latest_item(runs)),
        "created_at": task.get("created_at"),
        "updated_at": task.get("updated_at"),
    }


def attention_item_for_context(item):
    return {
        "id": item.get("id"),
        "key": item.get("key"),
        "kind": item.get("kind"),
        "title": clip_context_text(item.get("title"), 400),
        "description": clip_context_text(item.get("description"), MAX_CONTEXT_TEXT_CHARS),
        "reason": clip_context_text(item.get("reason"), MAX_CONTEXT_TEXT_CHARS),
        "priority": item.get("priority"),
        "status": item.get("status"),
        "related_task_id": item.get("related_task_id"),
        "question_id": item.get("question_id"),
        "agent_run_id": item.get("agent_run_id"),
        "created_at": item.get("created_at"),
        "updated_at": item.get("updated_at"),
    }


def attention_items_for_context(items, limit=MAX_CONTEXT_ATTENTION_ITEMS):
    values = list(items or [])
    priority_rank = {"high": 0, "normal": 1, "low": 2}
    values.sort(key=lambda item: item.get("updated_at") or item.get("created_at") or "", reverse=True)
    values.sort(key=lambda item: priority_rank.get(item.get("priority"), 9))
    return [
        attention_item_for_context(item)
        for item in values[:limit]
    ]


def question_for_context(question):
    blocks = [
        clip_context_text(block, MAX_CONTEXT_QUESTION_BLOCK_CHARS)
        for block in list(question.get("blocks") or [])[:MAX_CONTEXT_QUESTION_BLOCKS]
    ]
    return {
        "id": question.get("id"),
        "text": clip_context_text(question.get("text"), MAX_CONTEXT_TEXT_CHARS),
        "source": question.get("source"),
        "event_id": question.get("event_id"),
        "related_task_id": question.get("related_task_id"),
        "blocks": blocks,
        "blocks_omitted_count": max(0, len(question.get("blocks") or []) - len(blocks)),
        "status": question.get("status"),
        "outbox_message_id": question.get("outbox_message_id"),
        "created_at": question.get("created_at"),
        "answered_at": question.get("answered_at"),
        "acknowledged_at": question.get("acknowledged_at"),
    }


def questions_for_context(questions, limit=MAX_CONTEXT_QUESTIONS):
    values = list(questions or [])
    return [question_for_context(question) for question in values[-limit:]]


def request_history_for_context(value, limit=5):
    if isinstance(value, list):
        return [
            clip_context_text(item, MAX_CONTEXT_TEXT_CHARS)
            for item in value[-limit:]
        ]
    return clip_context_text(value, MAX_CONTEXT_TEXT_CHARS)


def runtime_status_for_context(status):
    return {
        "state": status.get("state"),
        "pid": status.get("pid"),
        "started_at": status.get("started_at"),
        "stopped_at": status.get("stopped_at"),
        "last_woke_at": status.get("last_woke_at"),
        "last_evaluated_at": status.get("last_evaluated_at"),
        "last_action": clip_context_text(status.get("last_action"), MAX_CONTEXT_TEXT_CHARS),
        "current_reason": status.get("current_reason"),
        "current_event_id": status.get("current_event_id"),
        "current_phase": status.get("current_phase"),
        "last_agent_reflex_at": status.get("last_agent_reflex_at"),
        "last_agent_reflex_report": status.get("last_agent_reflex_report") or {},
    }


def agent_status_for_context(status):
    return {
        "mode": status.get("mode"),
        "current_focus": clip_context_text(status.get("current_focus"), MAX_CONTEXT_TEXT_CHARS),
        "active_task_id": status.get("active_task_id"),
        "pending_question": clip_context_text(status.get("pending_question"), MAX_CONTEXT_TEXT_CHARS),
        "last_thought": clip_context_text(status.get("last_thought"), MAX_CONTEXT_TEXT_CHARS),
        "updated_at": status.get("updated_at"),
    }


def user_status_for_context(status):
    return {
        "mode": status.get("mode"),
        "current_focus": clip_context_text(status.get("current_focus"), MAX_CONTEXT_TEXT_CHARS),
        "last_request": request_history_for_context(status.get("last_request")),
        "last_interaction_at": status.get("last_interaction_at"),
        "updated_at": status.get("updated_at"),
    }


def conversation_for_context(state, current_event=None, limit=MAX_CONTEXT_CONVERSATION_ITEMS):
    items = []
    user_event_ids = set()
    cutoff_event_id = None
    if current_event and current_event.get("id"):
        try:
            cutoff_event_id = int(current_event.get("id"))
        except (TypeError, ValueError):
            cutoff_event_id = None
    for inbox_event in state.get("inbox", []):
        if inbox_event.get("type") != "user_message":
            continue
        try:
            event_id = int(inbox_event.get("id") or 0)
        except (TypeError, ValueError):
            event_id = 0
        if cutoff_event_id and event_id > cutoff_event_id:
            continue
        user_event_ids.add(str(inbox_event.get("id")))
        payload = inbox_event.get("payload") or {}
        items.append(
            {
                "_sort_at": inbox_event.get("created_at") or "",
                "_event_id": event_id,
                "_phase": 0,
                "_own_id": event_id,
                "role": "user",
                "kind": "message",
                "event_id": inbox_event.get("id"),
                "reply_to_question_id": payload.get("reply_to_question_id"),
                "text": clip_context_text(
                    payload.get("text"),
                    MAX_CONTEXT_CONVERSATION_TEXT_CHARS,
                ),
                "created_at": inbox_event.get("created_at"),
                "processed_at": inbox_event.get("processed_at"),
            }
        )

    for message in state.get("outbox", []):
        kind = message.get("type") or "message"
        linked_user_message = str(message.get("event_id")) in user_event_ids
        try:
            message_event_id = int(message.get("event_id") or 0)
        except (TypeError, ValueError):
            message_event_id = 0
        if cutoff_event_id and message_event_id and message_event_id > cutoff_event_id:
            continue
        linked_agent_message = kind in ("assistant", "question") and bool(message_event_id)
        if not linked_agent_message and not (
            kind in ("info", "warning") and linked_user_message
        ):
            continue
        items.append(
            {
                "_sort_at": message.get("created_at") or "",
                "_event_id": message_event_id,
                "_phase": 1,
                "_own_id": int(message.get("id") or 0),
                "role": "mew",
                "kind": kind,
                "message_id": message.get("id"),
                "event_id": message.get("event_id"),
                "question_id": message.get("question_id"),
                "requires_reply": bool(message.get("requires_reply")),
                "text": clip_context_text(
                    message.get("text"),
                    MAX_CONTEXT_CONVERSATION_TEXT_CHARS,
                ),
                "created_at": message.get("created_at"),
                "read_at": message.get("read_at"),
                "answered_at": message.get("answered_at"),
            }
        )

    items.sort(key=lambda item: (item["_sort_at"], item["_event_id"], item["_phase"], item["_own_id"]))
    selected = items[-limit:]
    return [
        {
            key: value
            for key, value in item.items()
            if not key.startswith("_")
        }
        for item in selected
    ]


def conversation_item_count(state):
    user_event_ids = {
        str(event.get("id"))
        for event in state.get("inbox", [])
        if event.get("type") == "user_message"
    }
    count = len(user_event_ids)
    for message in state.get("outbox", []):
        kind = message.get("type") or "message"
        linked_user_message = str(message.get("event_id")) in user_event_ids
        linked_agent_message = kind in ("assistant", "question") and bool(message.get("event_id"))
        if linked_agent_message or (
            kind in ("info", "warning") and linked_user_message
        ):
            count += 1
    return count


def autonomy_for_context(state, autonomous, autonomy_level, allow_agent_run, allow_verify, verify_command, allow_write):
    autonomy = dict(state.get("autonomy", {}))
    for key in ("pause_reason", "level_override", "last_cycle_reason", "last_desire"):
        if key in autonomy:
            autonomy[key] = clip_context_text(autonomy.get(key), MAX_CONTEXT_TEXT_CHARS)
    autonomy.update(
        {
            "requested_enabled": bool(autonomous),
            "requested_level": autonomy_level,
            "allow_agent_run": bool(allow_agent_run),
            "allow_verify": bool(allow_verify),
            "verify_command_configured": bool(verify_command),
            "allow_write": bool(allow_write),
            "configured_allow_agent_run": bool(state.get("autonomy", {}).get("allow_agent_run")),
        }
    )
    return autonomy


def resident_text_for_context(text):
    value = text or ""
    return {
        "chars": len(value),
        "truncated_for_prompt": len(value) > MAX_CONTEXT_LONG_TEXT_CHARS,
    }


def resident_text_for_prompt(text):
    return clip_context_text(text, MAX_CONTEXT_LONG_TEXT_CHARS) or "(none)"


def memory_for_context(state, limit=20):
    memory = state.get("memory", {})
    shallow = memory.get("shallow", {})
    deep = memory.get("deep", {})
    shallow_recent = shallow.get("recent_events", [])
    return {
        "shallow": {
            "current_context": clip_context_text(shallow.get("current_context"), MAX_CONTEXT_LONG_TEXT_CHARS),
            "latest_task_summary": clip_context_text(
                shallow.get("latest_task_summary"),
                MAX_CONTEXT_LONG_TEXT_CHARS,
            ),
            "recent_events": [
                {
                    **event,
                    "summary": clip_context_text(event.get("summary"), MAX_CONTEXT_TEXT_CHARS),
                }
                for event in compact_recent_items(shallow_recent, limit)
            ],
        },
        "deep": {
            "preferences": [
                clip_context_text(item, MAX_CONTEXT_MEMORY_CHARS)
                for item in compact_recent_items(deep.get("preferences", []), limit)
            ],
            "project": [
                clip_context_text(item, MAX_CONTEXT_MEMORY_CHARS)
                for item in compact_recent_items(deep.get("project", []), limit)
            ],
            "project_snapshot": snapshot_for_context(deep.get("project_snapshot")),
            "decisions": [
                clip_context_text(item, MAX_CONTEXT_MEMORY_CHARS)
                for item in compact_recent_items(deep.get("decisions", []), limit)
            ],
        },
    }


def knowledge_shallow_for_context(state, limit=20):
    shallow = state.get("knowledge", {}).get("shallow", {})
    return {
        "latest_task_summary": clip_context_text(
            shallow.get("latest_task_summary"),
            MAX_CONTEXT_LONG_TEXT_CHARS,
        ),
        "recent_events": [
            {
                **event,
                "summary": clip_context_text(event.get("summary"), MAX_CONTEXT_TEXT_CHARS),
            }
            for event in compact_recent_items(shallow.get("recent_events", []), limit)
        ],
    }


def agent_run_for_context(run):
    return {
        "id": run.get("id"),
        "task_id": run.get("task_id"),
        "purpose": run.get("purpose"),
        "status": run.get("status"),
        "backend": run.get("backend"),
        "model": run.get("model"),
        "cwd": clip_context_text(run.get("cwd"), 400),
        "external_pid": run.get("external_pid"),
        "resume_session_id": run.get("resume_session_id"),
        "session_id": run.get("session_id"),
        "review_status": run.get("review_status"),
        "review_report": review_report_for_context(run.get("review_report")),
        "plan_id": run.get("plan_id"),
        "parent_run_id": run.get("parent_run_id"),
        "review_of_run_id": run.get("review_of_run_id"),
        "followup_task_id": run.get("followup_task_id"),
        "prompt_file": run.get("prompt_file"),
        "prompt_chars": len(run.get("prompt") or ""),
        "command": [clip_context_text(part, 400) for part in run.get("command", [])],
        "stdout_tail": clip_context_text(run.get("stdout"), MAX_CONTEXT_RUN_OUTPUT_CHARS),
        "stderr_tail": clip_context_text(run.get("stderr"), MAX_CONTEXT_RUN_OUTPUT_CHARS),
        "result_tail": clip_context_text(run.get("result"), MAX_CONTEXT_RUN_OUTPUT_CHARS),
        "created_at": run.get("created_at"),
        "started_at": run.get("started_at"),
        "finished_at": run.get("finished_at"),
        "updated_at": run.get("updated_at"),
    }


def review_report_for_context(report):
    if not isinstance(report, dict):
        return None
    return {
        "status": report.get("status") or "unknown",
        "summary": clip_context_text(report.get("summary"), MAX_CONTEXT_RUN_OUTPUT_CHARS),
        "findings": [
            clip_context_text(item, MAX_CONTEXT_RUN_OUTPUT_CHARS)
            for item in (report.get("findings") or [])[:5]
        ],
        "follow_up": [
            clip_context_text(item, MAX_CONTEXT_RUN_OUTPUT_CHARS)
            for item in (report.get("follow_up") or [])[:5]
        ],
    }


def agent_runs_for_context(state, limit=MAX_CONTEXT_AGENT_RUNS):
    runs = list(state.get("agent_runs", []))
    active = [
        run
        for run in runs
        if run.get("status") in ("created", "running")
    ]
    active = active[-limit:]
    active_ids = {run.get("id") for run in active}
    remaining = max(0, limit - len(active))
    recent = []
    if remaining:
        for run in reversed(runs):
            if run.get("id") in active_ids:
                continue
            recent.append(run)
            if len(recent) >= remaining:
                break
    selected = active + list(reversed(recent))
    return [agent_run_for_context(run) for run in selected]


def active_agent_run_count(state):
    return len(
        [
            run
            for run in state.get("agent_runs", [])
            if run.get("status") in ("created", "running")
        ]
    )


def active_agent_runs_omitted_count(state, included_runs):
    included_active = len(
        [
            run
            for run in included_runs
            if run.get("status") in ("created", "running")
        ]
    )
    return max(0, active_agent_run_count(state) - included_active)


def verification_run_for_context(run):
    return {
        "id": run.get("id"),
        "command": clip_context_text(run.get("command"), 400),
        "reason": clip_context_text(run.get("reason"), MAX_CONTEXT_TEXT_CHARS),
        "exit_code": run.get("exit_code"),
        "stdout_tail": clip_context_text(run.get("stdout"), MAX_CONTEXT_RUN_OUTPUT_CHARS),
        "stderr_tail": clip_context_text(run.get("stderr"), MAX_CONTEXT_RUN_OUTPUT_CHARS),
        "started_at": run.get("started_at"),
        "finished_at": run.get("finished_at"),
        "updated_at": run.get("updated_at"),
    }


def write_run_for_context(run):
    return {
        "id": run.get("id"),
        "operation": run.get("operation") or run.get("action_type"),
        "action_type": run.get("action_type") or run.get("operation"),
        "path": clip_context_text(run.get("path"), 500),
        "dry_run": bool(run.get("dry_run")),
        "changed": run.get("changed"),
        "written": run.get("written"),
        "rolled_back": run.get("rolled_back"),
        "rollback_error": clip_context_text(run.get("rollback_error"), MAX_CONTEXT_RUN_OUTPUT_CHARS),
        "diff_tail": clip_context_text(run.get("diff"), MAX_CONTEXT_RUN_OUTPUT_CHARS),
        "summary": clip_context_text(
            run.get("summary") or run.get("message") or run.get("reason"),
            MAX_CONTEXT_TEXT_CHARS,
        ),
        "error": clip_context_text(run.get("error"), MAX_CONTEXT_RUN_OUTPUT_CHARS),
        "created_at": run.get("created_at"),
        "updated_at": run.get("updated_at"),
    }


def _step_action_for_context(action):
    return {
        "type": action.get("type") or "unknown",
        "task_id": action.get("task_id"),
        "path": clip_context_text(action.get("path"), 500),
        "query": clip_context_text(action.get("query"), 500),
        "title": clip_context_text(action.get("title"), 500),
        "reason": clip_context_text(action.get("reason"), MAX_CONTEXT_TEXT_CHARS),
        "summary": clip_context_text(action.get("summary"), MAX_CONTEXT_TEXT_CHARS),
    }


def _step_effect_for_context(effect):
    return {
        "type": effect.get("type") or "unknown",
        "id": effect.get("id"),
        "at": effect.get("at"),
        "message_type": effect.get("message_type"),
        "text": clip_context_text(effect.get("text"), MAX_CONTEXT_TEXT_CHARS),
        "related_task_id": effect.get("related_task_id"),
        "question_id": effect.get("question_id"),
        "agent_run_id": effect.get("agent_run_id"),
        "task_id": effect.get("task_id"),
        "status": effect.get("status"),
        "exit_code": effect.get("exit_code"),
        "action_type": effect.get("action_type"),
        "path": clip_context_text(effect.get("path"), 500),
        "dry_run": effect.get("dry_run"),
        "changed": effect.get("changed"),
        "written": effect.get("written"),
        "rolled_back": effect.get("rolled_back"),
        "reason": clip_context_text(effect.get("reason"), MAX_CONTEXT_TEXT_CHARS),
    }


def _is_protected_step_effect(effect):
    return effect.get("type") in ("question", "verification_run", "write_run") or (
        effect.get("type") == "message"
        and effect.get("message_type") == "question"
        and effect.get("question_id") is not None
    )


def _cap_step_effects_for_context(effects):
    values = list(effects or [])
    if len(values) <= MAX_CONTEXT_STEP_EFFECTS:
        return values
    capped = values[:MAX_CONTEXT_STEP_EFFECTS]
    missing_protected = [
        effect
        for effect in values
        if _is_protected_step_effect(effect)
        and effect not in capped
    ]
    if not missing_protected:
        return capped
    protected_slots = min(len(missing_protected), MAX_CONTEXT_STEP_EFFECTS)
    return capped[: MAX_CONTEXT_STEP_EFFECTS - protected_slots] + missing_protected[-protected_slots:]


def step_run_for_context(run):
    effects = _cap_step_effects_for_context(run.get("effects"))
    return {
        "id": run.get("id"),
        "at": run.get("at"),
        "event_id": run.get("event_id"),
        "summary": clip_context_text(run.get("summary"), MAX_CONTEXT_TEXT_CHARS),
        "stop_reason": run.get("stop_reason") or "",
        "actions": [
            _step_action_for_context(action)
            for action in list(run.get("actions") or [])[:8]
        ],
        "skipped_actions": [
            _step_action_for_context(action)
            for action in list(run.get("skipped_actions") or [])[:8]
        ],
        "effects": [
            _step_effect_for_context(effect)
            for effect in effects
        ],
        "counts": dict(run.get("counts") or {}),
    }


def event_for_context(event):
    payload = event.get("payload") or {}
    return {
        "id": event.get("id"),
        "type": event.get("type"),
        "source": event.get("source"),
        "payload": {
            key: clip_context_text(value, MAX_CONTEXT_LONG_TEXT_CHARS)
            for key, value in payload.items()
        },
        "created_at": event.get("created_at"),
        "processed_at": event.get("processed_at"),
    }


def context_size_report(context):
    section_chars = {
        key: json_char_count(value)
        for key, value in context.items()
    }
    return {
        "total_chars": sum(section_chars.values()),
        "section_chars": section_chars,
    }


def build_context_stats(state, context):
    open_task_count = len(open_tasks(state))
    attention_count = len(open_attention_items(state))
    agent_run_count = len(state.get("agent_runs", []))
    size_report = context_size_report(context)
    return {
        "approx_chars": size_report["total_chars"],
        "section_chars": size_report["section_chars"],
        "limits": {
            "tasks": MAX_CONTEXT_TASKS,
            "attention": MAX_CONTEXT_ATTENTION_ITEMS,
            "agent_runs": MAX_CONTEXT_AGENT_RUNS,
            "step_runs": MAX_CONTEXT_STEP_RUNS,
            "questions": MAX_CONTEXT_QUESTIONS,
            "question_blocks": MAX_CONTEXT_QUESTION_BLOCKS,
            "question_block_chars": MAX_CONTEXT_QUESTION_BLOCK_CHARS,
            "text_chars": MAX_CONTEXT_TEXT_CHARS,
            "long_text_chars": MAX_CONTEXT_LONG_TEXT_CHARS,
            "run_output_chars": MAX_CONTEXT_RUN_OUTPUT_CHARS,
            "memory_chars": MAX_CONTEXT_MEMORY_CHARS,
            "conversation_items": MAX_CONTEXT_CONVERSATION_ITEMS,
            "conversation_text_chars": MAX_CONTEXT_CONVERSATION_TEXT_CHARS,
        },
        "source_counts": {
            "open_tasks": open_task_count,
            "attention_items": attention_count,
            "unanswered_questions": len(open_questions(state)),
            "agent_runs": agent_run_count,
            "active_agent_runs": active_agent_run_count(state),
            "verification_runs": len(state.get("verification_runs", [])),
            "write_runs": len(state.get("write_runs", [])),
            "step_runs": len(state.get("step_runs", [])),
            "conversation_items": conversation_item_count(state),
        },
        "included_counts": {
            "open_tasks": len(context.get("todo", [])),
            "attention_items": len(context.get("attention", [])),
            "unanswered_questions": len(context.get("unanswered_questions", [])),
            "agent_runs": len(context.get("agent_runs", [])),
            "active_agent_runs": len(
                [
                    run
                    for run in context.get("agent_runs", [])
                    if run.get("status") in ("created", "running")
                ]
            ),
            "verification_runs": len(context.get("verification_runs", [])),
            "write_runs": len(context.get("write_runs", [])),
            "step_runs": len(context.get("step_runs", [])),
            "conversation_items": len(context.get("conversation", [])),
        },
        "omitted_counts": {
            "open_tasks": max(0, open_task_count - len(context.get("todo", []))),
            "attention_items": max(0, attention_count - len(context.get("attention", []))),
            "unanswered_questions": max(
                0,
                len(open_questions(state)) - len(context.get("unanswered_questions", [])),
            ),
            "agent_runs": max(0, agent_run_count - len(context.get("agent_runs", []))),
            "step_runs": max(
                0,
                len(state.get("step_runs", [])) - len(context.get("step_runs", [])),
            ),
            "active_agent_runs": context.get("agent_runs_active_omitted_count", 0),
            "conversation_items": max(
                0,
                conversation_item_count(state) - len(context.get("conversation", [])),
            ),
        },
    }


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
    elif event["type"] not in ("startup", "passive_tick", "tick"):
        payload = json.dumps(event.get("payload") or {}, ensure_ascii=False, sort_keys=True)
        parts.append(f"External event {event['type']} from {event.get('source')}: {payload}")

    return " ".join(parts)

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
    unanswered_questions = open_questions(state)
    tasks = sorted(open_tasks(state), key=task_sort_key)
    attention = open_attention_items(state)
    agent_runs_context = agent_runs_for_context(state)
    context = {
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
        "runtime_status": runtime_status_for_context(state["runtime_status"]),
        "agent_status": agent_status_for_context(state["agent_status"]),
        "user_status": user_status_for_context(state["user_status"]),
        "conversation": conversation_for_context(state, event),
        "todo_summary": summarize_tasks(state),
        "todo": [task_for_context(task) for task in tasks[:MAX_CONTEXT_TASKS]],
        "todo_omitted_count": max(0, len(tasks) - MAX_CONTEXT_TASKS),
        "unanswered_questions": questions_for_context(unanswered_questions),
        "unanswered_questions_omitted_count": max(
            0,
            len(unanswered_questions) - MAX_CONTEXT_QUESTIONS,
        ),
        "attention": attention_items_for_context(attention),
        "attention_omitted_count": max(0, len(attention) - MAX_CONTEXT_ATTENTION_ITEMS),
        "memory": memory_for_context(state),
        "knowledge_shallow": knowledge_shallow_for_context(state),
        "agent_runs": agent_runs_context,
        "agent_runs_active_omitted_count": active_agent_runs_omitted_count(
            state,
            agent_runs_context,
        ),
        "autonomy": autonomy_for_context(
            state,
            autonomous,
            autonomy_level,
            allow_agent_run,
            allow_verify,
            verify_command,
            allow_write,
        ),
        "self": resident_text_for_context(self_text),
        "desires": resident_text_for_context(desires),
        "runtime_log_tail": read_runtime_log_tail(),
        "thought_journal": recent_thoughts_for_context(state),
        "thought_thread_warning": dropped_thread_warning_for_context(state),
        "perception": perceive_workspace(allowed_read_roots=allowed_read_roots),
        "allowed_read_roots": allowed_read_roots or [],
        "allowed_write_roots": allowed_write_roots or [],
        "verification_runs": [
            verification_run_for_context(run)
            for run in compact_recent_items(state.get("verification_runs", []), 10)
        ],
        "write_runs": [
            write_run_for_context(run)
            for run in compact_recent_items(state.get("write_runs", []), 10)
        ],
        "step_runs": [
            step_run_for_context(run)
            for run in compact_recent_items(state.get("step_runs", []), MAX_CONTEXT_STEP_RUNS)
        ],
        "event": event_for_context(event),
    }
    context["context_stats"] = build_context_stats(state, context)
    return context
