from pathlib import Path

from .cli_command import mew_command
from .context_checkpoint import current_git_reentry_state, latest_context_checkpoint
from .metrics import build_observation_metrics
from .programmer import find_review_run_for_implementation, latest_task_plan
from .question_view import format_question_context, format_waiting_hours, question_view_metadata
from .state import is_routine_outbox_message
from .tasks import find_task, open_tasks, task_kind, task_needs_programmer_plan, task_sort_key
from .thoughts import recent_thoughts_for_context
from .timeutil import elapsed_hours, now_iso
from .work_session import (
    build_work_session_resume,
    format_work_continuity_inline,
    format_work_continuity_recommendation,
    format_work_failure_risk,
    latest_unresolved_failure,
    work_session_task,
)


def _first_nonempty(*values):
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def current_project_looks_like_mew():
    root = Path.cwd()
    return (
        (root / "pyproject.toml").is_file()
        and (root / "src" / "mew").is_dir()
        and (root / "mew").is_file()
    )


def scoped_agent_status(state, kind=None):
    agent = dict(state.get("agent_status", {}))
    if not kind:
        return agent
    active_task_id = agent.get("active_task_id")
    if active_task_id is None:
        return agent
    task = find_task(state, active_task_id)
    if task and task_kind(task) == kind:
        return agent
    agent["mode"] = "idle"
    agent["current_focus"] = ""
    agent["active_task_id"] = None
    agent["pending_question"] = None
    agent["scope_filtered"] = True
    agent["scope_filter_kind"] = kind
    return agent


def _project_snapshot_item(snapshot):
    if not isinstance(snapshot, dict) or not snapshot.get("updated_at"):
        return {}
    roots = snapshot.get("roots") or []
    files = snapshot.get("files") or []
    package = snapshot.get("package") or {}
    return {
        "updated_at": snapshot.get("updated_at"),
        "project_types": list(snapshot.get("project_types") or []),
        "package_name": package.get("name") or "",
        "root_count": len(roots),
        "file_count": len(files),
    }


def open_unread_messages(state):
    return [message for message in state.get("outbox", []) if not message.get("read_at")]


def _clip_focus_text(value, limit=180):
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def recent_unread_messages(state, limit=5):
    unread = open_unread_messages(state)
    return list(reversed(unread[-limit:]))


def running_agent_runs(state):
    return [
        run for run in state.get("agent_runs", []) if run.get("status") in ("created", "running")
    ]


def implementation_runs_needing_review(state):
    runs = []
    for run in state.get("agent_runs", []):
        if run.get("purpose", "implementation") != "implementation":
            continue
        if run.get("status") not in ("completed", "failed"):
            continue
        if find_review_run_for_implementation(state, run.get("id")):
            continue
        runs.append(run)
    return runs


def review_runs_needing_followup(state):
    return [
        run
        for run in state.get("agent_runs", [])
        if run.get("purpose") == "review"
        and run.get("status") in ("completed", "failed")
        and not run.get("followup_task_id")
        and not run.get("followup_processed_at")
    ]

def dry_run_implementation_runs(state, tasks):
    task_ids = {str(task.get("id")) for task in tasks if task_kind(task) == "coding"}
    runs = []
    for run in reversed(state.get("agent_runs", [])):
        if run.get("purpose", "implementation") != "implementation":
            continue
        if run.get("status") != "dry_run":
            continue
        if str(run.get("task_id")) not in task_ids:
            continue
        runs.append(run)
    return runs


def tasks_needing_plan(tasks):
    return [task for task in tasks if task_needs_programmer_plan(task)]


def practical_next_step(task):
    kind = task_kind(task)
    task_id = task.get("id")
    title = task.get("title") or "untitled task"
    if kind == "coding":
        return f"advance coding task #{task_id}: {title}"
    if kind == "research":
        return f"spend 10 minutes researching task #{task_id}: {title}"
    if kind == "admin":
        return f"take one concrete admin step on task #{task_id}: {title}"
    if kind == "personal":
        return f"take one 5-minute personal step on task #{task_id}: {title}"
    return f"clarify or take one small step on task #{task_id}: {title}"


def dispatchable_planned_tasks(tasks):
    result = []
    for task in tasks:
        if task_kind(task) != "coding":
            continue
        plan = latest_task_plan(task)
        if (
            plan
            and plan.get("status") in ("planned", "dry_run")
            and task.get("status") == "ready"
            and task.get("auto_execute")
        ):
            result.append((task, plan))
    return result


def verification_outcome(run):
    if run.get("exit_code") == 0:
        return "passed"
    return "failed"


def recent_verification_runs(state, limit=5):
    runs = list(state.get("verification_runs", []))
    return list(reversed(runs[-limit:]))


def recent_verification_runs_for_tasks(state, task_ids, limit=1):
    matching = [
        run
        for run in reversed(state.get("verification_runs", []))
        if str(run.get("task_id")) in task_ids
    ]
    return matching[:limit]


def recent_write_runs(state, limit=5):
    runs = list(state.get("write_runs", []))
    return list(reversed(runs[-limit:]))


def recent_runtime_effects(state, limit=5):
    runs = list(state.get("runtime_effects", []))
    return list(reversed(runs[-limit:]))


def recent_step_runs(state, limit=3):
    runs = list(state.get("step_runs", []))
    return list(reversed(runs[-limit:]))


def filter_records_for_tasks(records, tasks, kind=None):
    if not kind:
        return list(records)
    task_ids = {str(task.get("id")) for task in tasks}
    return [record for record in records if str(record.get("task_id")) in task_ids]


def recent_records(records, limit=5):
    return list(reversed(list(records)[-limit:]))


def _message_item(message):
    return {
        "id": message.get("id"),
        "type": message.get("type"),
        "text": message.get("text") or "",
        "event_id": message.get("event_id"),
        "related_task_id": message.get("related_task_id"),
        "created_at": message.get("created_at"),
        "read_at": message.get("read_at"),
    }


def _attention_item(item):
    return {
        "id": item.get("id"),
        "kind": item.get("kind"),
        "title": item.get("title"),
        "reason": item.get("reason"),
        "priority": item.get("priority"),
        "related_task_id": item.get("related_task_id"),
        "status": item.get("status"),
        "created_at": item.get("created_at"),
        "updated_at": item.get("updated_at"),
    }


def _question_item(question, current_time=None):
    metadata = question_view_metadata(question, current_time=current_time)
    return {
        "id": question.get("id"),
        "text": question.get("text"),
        "related_task_id": question.get("related_task_id"),
        "status": question.get("status"),
        "created_at": question.get("created_at"),
        "updated_at": question.get("updated_at"),
        "acknowledged_at": question.get("acknowledged_at"),
        "deferred_at": question.get("deferred_at"),
        "defer_reason": question.get("defer_reason"),
        "activity_at": metadata.get("activity_at"),
        "waiting_hours": metadata.get("waiting_hours"),
        "waiting_for": metadata.get("waiting_for"),
    }


def _task_item(task):
    return {
        "id": task.get("id"),
        "title": task.get("title"),
        "kind": task_kind(task),
        "status": task.get("status"),
        "priority": task.get("priority"),
        "auto_execute": task.get("auto_execute"),
        "cwd": task.get("cwd"),
        "agent_run_id": task.get("agent_run_id"),
        "latest_plan_id": task.get("latest_plan_id"),
        "updated_at": task.get("updated_at"),
    }


def _agent_run_item(run):
    return {
        "id": run.get("id"),
        "task_id": run.get("task_id"),
        "purpose": run.get("purpose") or "implementation",
        "backend": run.get("backend"),
        "model": run.get("model"),
        "status": run.get("status"),
        "external_pid": run.get("external_pid"),
        "plan_id": run.get("plan_id"),
        "review_of_run_id": run.get("review_of_run_id"),
        "updated_at": run.get("updated_at"),
    }


def _verification_item(run):
    return {
        "id": run.get("id"),
        "outcome": verification_outcome(run),
        "exit_code": run.get("exit_code"),
        "command": run.get("command"),
        "reason": run.get("reason"),
        "finished_at": run.get("finished_at") or run.get("updated_at") or run.get("created_at"),
    }


def _write_item(run):
    return {
        "id": run.get("id"),
        "operation": run.get("operation") or run.get("action_type"),
        "path": run.get("path"),
        "changed": run.get("changed"),
        "dry_run": run.get("dry_run"),
        "written": run.get("written"),
        "rolled_back": run.get("rolled_back"),
        "verification_run_id": run.get("verification_run_id"),
        "verification_exit_code": run.get("verification_exit_code"),
        "updated_at": run.get("updated_at") or run.get("finished_at") or run.get("created_at"),
    }


def _thought_item(thought):
    return {
        "id": thought.get("id"),
        "at": thought.get("at"),
        "event_id": thought.get("event_id"),
        "event_type": thought.get("event_type"),
        "cycle_reason": thought.get("cycle_reason"),
        "summary": thought.get("summary"),
        "open_threads": thought.get("open_threads", []),
        "resolved_threads": thought.get("resolved_threads", []),
        "dropped_threads": thought.get("dropped_threads", []),
        "dropped_thread_ratio": thought.get("dropped_thread_ratio", 0.0),
        "counts": thought.get("counts", {}),
    }


def describe_action(action):
    action_type = action.get("type") or "unknown"
    if action.get("task_id") is not None:
        return f"{action_type} task=#{action.get('task_id')}"
    if action.get("run_id") is not None:
        return f"{action_type} run=#{action.get('run_id')}"
    if action.get("path"):
        return f"{action_type} {action.get('path')}"
    title = action.get("title")
    if title:
        return f"{action_type} {title}"
    text = action.get("summary") or action.get("reason") or action.get("text") or ""
    if text:
        first_line = str(text).strip().splitlines()[0]
        if len(first_line) > 80:
            first_line = first_line[:77] + "..."
        return f"{action_type} {first_line}"
    return action_type


def _activity_item(thought):
    actions = thought.get("actions") or []
    return {
        "id": thought.get("id"),
        "at": thought.get("at"),
        "event_type": thought.get("event_type"),
        "cycle_reason": thought.get("cycle_reason"),
        "summary": thought.get("summary") or "",
        "actions": [describe_action(action) for action in actions[:3]],
        "message_count": (thought.get("counts") or {}).get("messages", 0),
    }


def _work_activity_item(session, kind, record_type, record, summary, actions=None):
    timestamp = (
        record.get("finished_at")
        or record.get("updated_at")
        or record.get("created_at")
        or record.get("started_at")
        or session.get("updated_at")
        or session.get("created_at")
    )
    task_id = session.get("task_id")
    label = f"session #{session.get('id')}"
    if task_id is not None:
        label += f" task #{task_id}"
    if kind:
        label += f" {kind}"
    summary_text = " ".join(str(summary or "").split())
    if len(summary_text) > 160:
        summary_text = summary_text[:157].rstrip() + "..."
    return {
        "id": f"work-{session.get('id')}-{record_type}-{record.get('id') or timestamp or 'note'}",
        "at": timestamp,
        "event_type": "work_session",
        "cycle_reason": record_type,
        "summary": f"{label}: {summary_text}",
        "actions": actions or [],
        "message_count": 0,
        "session_id": session.get("id"),
        "task_id": task_id,
    }


def _work_session_activity_entries(state, limit=5, kind=None):
    task_ids = _task_ids_for_kind(state, kind)
    entries = []
    for session_index, session in enumerate(state.get("work_sessions") or []):
        if kind and str(session.get("task_id")) not in task_ids:
            continue
        session_kind = ""
        task = work_session_task(state, session)
        if task:
            session_kind = task_kind(task)
        for turn_index, turn in enumerate(session.get("model_turns") or []):
            if not isinstance(turn, dict):
                continue
            summary = turn.get("summary") or (turn.get("action") or {}).get("summary") or ""
            if not summary:
                continue
            action = turn.get("action") or {}
            action_type = action.get("type")
            actions = [f"model {action_type}"] if action_type else ["model_turn"]
            item = _work_activity_item(session, session_kind, "model_turn", turn, summary, actions=actions)
            entries.append((item.get("at") or "", session_index, turn_index, item))
        for tool_index, call in enumerate(session.get("tool_calls") or []):
            if not isinstance(call, dict):
                continue
            summary = call.get("summary") or call.get("error") or ""
            tool_name = call.get("tool") or "tool"
            if not summary:
                summary = tool_name
            actions = [f"{tool_name} {call.get('status') or 'unknown'}"]
            item = _work_activity_item(session, session_kind, "tool_call", call, summary, actions=actions)
            entries.append((item.get("at") or "", session_index, tool_index, item))
        for note_index, note in enumerate(session.get("notes") or []):
            if not isinstance(note, dict):
                continue
            text = str(note.get("text") or "").strip()
            if not text:
                continue
            summary = text.splitlines()[0]
            actions = [f"note {note.get('source') or 'user'}"]
            item = _work_activity_item(session, session_kind, "note", note, summary, actions=actions)
            entries.append((item.get("at") or "", session_index, note_index, item))
    entries.sort(key=lambda entry: entry[:3], reverse=True)
    return [entry[3] for entry in entries[:limit]]


def activity_label(item):
    event_type = item.get("event_type") or "unknown"
    cycle_reason = item.get("cycle_reason") or ""
    if cycle_reason and cycle_reason != event_type:
        return f"{event_type}/{cycle_reason}"
    return event_type


def activity_identity(item):
    if item.get("event_type") == "work_session":
        return f"work#{item.get('session_id')}"
    return f"#{item.get('id')}"


def _task_ids_for_kind(state, kind):
    if not kind:
        return set()
    return {str(task.get("id")) for task in state.get("tasks", []) if task_kind(task) == kind}


def _thought_matches_task_ids(thought, task_ids):
    if not task_ids:
        return True
    for action in thought.get("actions") or []:
        action_task_id = action.get("task_id") or action.get("related_task_id")
        if action_task_id is not None and str(action_task_id) in task_ids:
            return True
    return False


def recent_activity(state, limit=5, kind=None):
    thoughts = list(state.get("thought_journal", []))
    task_ids = _task_ids_for_kind(state, kind)
    entries = []
    for thought_index, thought in enumerate(thoughts):
        if kind and not _thought_matches_task_ids(thought, task_ids):
            continue
        if thought.get("event_type") not in ("startup", "passive_tick", "user_message"):
            continue
        summary = thought.get("summary") or ""
        actions = thought.get("actions") or []
        if not summary and not actions:
            continue
        item = _activity_item(thought)
        entries.append((item.get("at") or "", thought_index, item))
    for work_index, item in enumerate(_work_session_activity_entries(state, limit=limit, kind=kind)):
        entries.append((item.get("at") or "", len(thoughts) + work_index, item))
    entries.sort(key=lambda entry: entry[:2], reverse=True)
    return [entry[2] for entry in entries[:limit]]


def build_activity_data(state, limit=10, kind=None):
    thoughts = list(state.get("thought_journal", []))
    task_ids = _task_ids_for_kind(state, kind)
    filtered_thoughts = [
        thought
        for thought in thoughts
        if not kind or _thought_matches_task_ids(thought, task_ids)
    ]
    dropped = [
        {
            "id": thought.get("id"),
            "event_id": thought.get("event_id"),
            "event_type": thought.get("event_type"),
            "dropped_thread_ratio": thought.get("dropped_thread_ratio", 0.0),
            "dropped_threads": thought.get("dropped_threads", []),
        }
        for thought in reversed(filtered_thoughts)
        if thought.get("dropped_threads")
    ]
    action_counts = {}
    for thought in filtered_thoughts:
        for action in thought.get("actions") or []:
            action_type = action.get("type") or "unknown"
            action_counts[action_type] = action_counts.get(action_type, 0) + 1
    return {
        "generated_at": now_iso(),
        "kind": kind,
        "recent_activity": recent_activity(state, limit=limit, kind=kind),
        "action_counts": dict(sorted(action_counts.items())),
        "dropped_threads": dropped[:limit],
    }


def format_activity(state, limit=10, kind=None):
    data = build_activity_data(state, limit=limit, kind=kind)
    activity = data["recent_activity"]
    title = "Mew activity"
    if kind:
        title += f" ({kind})"
    lines = [f"{title} at {data['generated_at']}"]
    if not activity:
        lines.append("No recent activity.")
    else:
        for item in activity:
            actions = item.get("actions") or []
            suffix = f" actions={', '.join(actions)}" if actions else ""
            lines.append(
                f"- {activity_identity(item)} {activity_label(item)}: "
                f"{item.get('summary')}{suffix}"
            )

    if data["action_counts"]:
        counts = ", ".join(
            f"{key}={value}" for key, value in data["action_counts"].items()
        )
        lines.append(f"action_counts: {counts}")

    if data["dropped_threads"]:
        lines.append("Dropped thread warnings")
        for item in data["dropped_threads"][:limit]:
            lines.append(
                f"- thought #{item.get('id')} ratio={item.get('dropped_thread_ratio')}: "
                f"{len(item.get('dropped_threads') or [])} thread(s)"
            )
    return "\n".join(lines)


def build_brief_data(state, limit=5, kind=None, include_context_checkpoint=False):
    generated_at = now_iso()
    memory = state.get("memory", {})
    shallow = memory.get("shallow", {})
    deep = memory.get("deep", {})
    attention = [
        item for item in state.get("attention", {}).get("items", []) if item.get("status") == "open"
    ]
    questions = [question for question in state.get("questions", []) if question.get("status") == "open"]
    tasks = filter_tasks_by_kind(sorted(open_tasks(state), key=task_sort_key), kind=kind)
    questions = filter_questions_for_tasks(questions, tasks, kind=kind)
    attention = filter_attention_for_tasks(attention, tasks, kind=kind)
    unread = filter_messages_for_tasks(open_unread_messages(state), tasks, kind=kind)
    routine_unread = [message for message in unread if is_routine_outbox_message(state, message)]
    running_runs = running_agent_runs(state)
    if kind:
        task_ids = {str(task.get("id")) for task in tasks}
        running_runs = [run for run in running_runs if str(run.get("task_id")) in task_ids]
    verifications = recent_records(
        filter_records_for_tasks(state.get("verification_runs", []), tasks, kind=kind),
        limit=limit,
    )
    writes = recent_records(
        filter_records_for_tasks(state.get("write_runs", []), tasks, kind=kind),
        limit=limit,
    )
    runtime_effects = recent_records(
        filter_records_for_tasks(state.get("runtime_effects", []), tasks, kind=kind),
        limit=limit,
    )
    review_waiting = implementation_runs_needing_review(state)
    followup_waiting = review_runs_needing_followup(state)
    dry_run_waiting = dry_run_implementation_runs(state, tasks)
    dispatchable = dispatchable_planned_tasks(tasks)
    plan_needed = tasks_needing_plan(tasks)
    activity = [] if kind else recent_activity(state, limit=limit)
    thoughts = [] if kind else recent_thoughts_for_context(state, limit=limit)
    steps = [] if kind else recent_step_runs(state, limit=limit)
    if kind:
        task_ids = {str(task.get("id")) for task in tasks}
        review_waiting = [run for run in review_waiting if str(run.get("task_id")) in task_ids]
        followup_waiting = [run for run in followup_waiting if str(run.get("task_id")) in task_ids]

    return {
        "generated_at": generated_at,
        "kind": kind or "",
        "runtime": state.get("runtime_status", {}),
        "agent": scoped_agent_status(state, kind=kind),
        "autonomy": state.get("autonomy", {}),
        "user": state.get("user_status", {}),
        "unread_outbox": [_message_item(message) for message in list(reversed(unread[-limit:]))],
        "unread_outbox_count": len(unread),
        "routine_unread_info_count": len(routine_unread),
        "memory": {
            "current_context": _first_nonempty(shallow.get("current_context"), ""),
            "latest_task_summary": _first_nonempty(shallow.get("latest_task_summary"), ""),
            "project_snapshot": _project_snapshot_item(deep.get("project_snapshot")),
            "latest_context_checkpoint": latest_context_checkpoint()
            if include_context_checkpoint
            else {},
            "current_git": current_git_reentry_state() if include_context_checkpoint else {},
        },
        "recent_activity": activity,
        "thought_journal": [_thought_item(thought) for thought in thoughts],
        "attention": [_attention_item(item) for item in attention[:limit]],
        "open_questions": [_question_item(question, current_time=generated_at) for question in questions[:limit]],
        "open_tasks": [_task_item(task) for task in tasks[:limit]],
        "open_task_count": len(tasks),
        "running_agents": [_agent_run_item(run) for run in running_runs[:limit]],
        "recent_verification": [
            _verification_item(run) for run in verifications
        ],
        "recent_writes": [
            _write_item(run) for run in writes
        ],
        "recent_runtime_effects": runtime_effects,
        "recent_steps": steps,
        "programmer_queue": {
            "review_needed": [_agent_run_item(run) for run in review_waiting[:limit]],
            "followup_needed": [_agent_run_item(run) for run in followup_waiting[:limit]],
            "dry_run_ready": [_agent_run_item(run) for run in dry_run_waiting[:limit]],
            "dispatchable": [
                {"task": _task_item(task), "plan_id": plan.get("id")}
                for task, plan in dispatchable[:limit]
            ],
            "plan_needed": [_task_item(task) for task in plan_needed[:limit]],
        },
        "next_move": next_move(state, kind=kind),
    }

def filter_tasks_by_kind(tasks, kind=None):
    if not kind:
        return list(tasks)
    return [task for task in tasks if task_kind(task) == kind]


def filter_questions_for_tasks(questions, tasks, kind=None):
    if not kind:
        return list(questions)
    task_ids = {str(task.get("id")) for task in tasks}
    return [
        question
        for question in questions
        if str(question.get("related_task_id")) in task_ids
    ]


def filter_attention_for_tasks(attention, tasks, kind=None):
    if not kind:
        return list(attention)
    task_ids = {str(task.get("id")) for task in tasks}
    return [
        item
        for item in attention
        if str(item.get("task_id") or item.get("related_task_id")) in task_ids
    ]


def filter_messages_for_tasks(messages, tasks, kind=None):
    if not kind:
        return list(messages)
    task_ids = {str(task.get("id")) for task in tasks}
    return [
        message
        for message in messages
        if str(message.get("related_task_id")) in task_ids
    ]


def build_focus_data(state, limit=3, kind=None, include_context_checkpoint=False):
    generated_at = now_iso()
    tasks = filter_tasks_by_kind(sorted(open_tasks(state), key=task_sort_key), kind=kind)
    coding_next_move = next_move(state, kind="coding") if not kind else ""
    questions = filter_questions_for_tasks(
        [question for question in state.get("questions", []) if question.get("status") == "open"],
        tasks,
        kind=kind,
    )
    attention = [
        item for item in state.get("attention", {}).get("items", []) if item.get("status") == "open"
    ]
    attention = filter_attention_for_tasks(attention, tasks, kind=kind)
    unread = filter_messages_for_tasks(open_unread_messages(state), tasks, kind=kind)
    routine_unread = [message for message in unread if is_routine_outbox_message(state, message)]
    return {
        "generated_at": generated_at,
        "next_move": next_move(state, kind=kind),
        "coding_next_move": coding_next_move,
        "kind": kind or "",
        "unread_outbox_count": len(unread),
        "routine_unread_info_count": len(routine_unread),
        "latest_context_checkpoint": latest_context_checkpoint()
        if include_context_checkpoint
        else {},
        "current_git": current_git_reentry_state() if include_context_checkpoint else {},
        "open_questions": [_question_item(question, current_time=generated_at) for question in questions[:limit]],
        "attention": [_attention_item(item) for item in attention[:limit]],
        "active_work_sessions": active_work_session_items(
            state,
            limit=limit,
            kind=kind,
            current_time=generated_at,
        ),
        "recent_friction": recent_focus_friction(state, kind=kind),
        "tasks": [
            {
                **_task_item(task),
                "next_step": practical_next_step(task),
            }
            for task in tasks[:limit]
        ],
        "open_task_count": len(tasks),
    }


FOCUS_FRICTION_SIGNAL_IDS = {
    "approval_friction",
    "verification_friction",
    "slow_model_resume",
    "high_idle_ratio",
}


def recent_focus_friction(state, kind=None, *, session_limit=10, sample_limit=2):
    metrics = build_observation_metrics(state, kind=kind, limit=session_limit, sample_limit=sample_limit)
    signals = [
        signal
        for signal in metrics.get("signals") or []
        if signal.get("id") in FOCUS_FRICTION_SIGNAL_IDS
    ]
    diagnostics = metrics.get("diagnostics") or {}
    samples = {
        "verification_failures": diagnostics.get("verification_failures") or [],
        "approval_friction": diagnostics.get("approval_friction") or [],
        "slow_model_resumes": diagnostics.get("slow_model_resumes") or [],
        "approval_bound_waits": diagnostics.get("approval_bound_waits") or [],
    }
    if not signals and not any(samples.values()):
        return {}
    rates = ((metrics.get("reliability") or {}).get("rates") or {})
    latency = metrics.get("latency") or {}
    sessions = metrics.get("sessions") or {}
    active_blocker_count = int(sessions.get("awaiting_approval") or 0) + int(sessions.get("stale_active") or 0)
    return {
        "active_blocker_count": active_blocker_count,
        "rates": {
            "approval_rejection": rates.get("approval_rejection"),
            "verification_failure": rates.get("verification_failure"),
            "verification_rollback": rates.get("verification_rollback"),
        },
        "latency": {
            "model_resume_p95": (latency.get("model_resume_wait_seconds") or {}).get("p95"),
            "approval_bound_p95": (latency.get("approval_bound_wait_seconds") or {}).get("p95"),
        },
        "signals": signals[:sample_limit],
        **samples,
    }


def active_work_session_items(state, limit=3, kind=None, current_time=None):
    current_time = current_time or now_iso()
    items = []
    for session in reversed(state.get("work_sessions") or []):
        if session.get("status") != "active":
            continue
        task = work_session_task(state, session)
        if session.get("task_id") is not None and not task:
            continue
        if task and task.get("status") == "done":
            continue
        if kind and task_kind(task or {}) != kind:
            continue
        resume = build_work_session_resume(session, task=task, limit=3, state=state) or {}
        task_id = session.get("task_id")
        task_parts = [task_id] if task_id is not None else []
        resume_command = _work_session_resume_command(session, task_parts)
        continue_command = _work_session_reentry_command(session, task_parts, max_steps=1)
        follow_command = _work_session_reentry_command(session, task_parts, max_steps=10, follow=True)
        updated_at = session.get("updated_at") or session.get("created_at") or ""
        inactive_hours = elapsed_hours(updated_at, current_time)
        risk = format_work_failure_risk(
            resume.get("unresolved_failure") or latest_unresolved_failure(resume.get("failures") or [])
        )
        items.append(
            {
                "id": session.get("id"),
                "task_id": task_id,
                "title": session.get("title") or (task or {}).get("title") or "",
                "phase": resume.get("phase") or "unknown",
                "updated_at": updated_at,
                "inactive_hours": round(inactive_hours, 2) if inactive_hours is not None else None,
                "inactive_for": format_waiting_hours(inactive_hours, minimum_hours=0.0),
                "next_action": resume.get("next_action") or "",
                "risk": risk,
                "continuity": resume.get("continuity") or {},
                "compressed_prior_think": resume.get("compressed_prior_think") or {},
                "working_memory": resume.get("working_memory") or {},
                "pending_steer": resume.get("pending_steer") or {},
                "queued_followups": resume.get("queued_followups") or [],
                "queued_followups_total": resume.get("queued_followups_total") or 0,
                "resume_command": resume_command,
                "continue_command": continue_command,
                "follow_command": follow_command,
            }
        )
        if len(items) >= limit:
            break
    return items


def _work_session_default_option_parts(session):
    options = (session or {}).get("default_options") or {}
    parts = []
    for key, flag in (
        ("auth", "--auth"),
        ("model_backend", "--model-backend"),
        ("model", "--model"),
        ("base_url", "--base-url"),
    ):
        if options.get(key):
            parts.extend([flag, options[key]])
    for root in options.get("allow_read") or []:
        parts.extend(["--allow-read", root])
    for root in options.get("allow_write") or []:
        parts.extend(["--allow-write", root])
    if options.get("allow_shell"):
        parts.append("--allow-shell")
    if options.get("allow_verify"):
        parts.append("--allow-verify")
    if options.get("verify_command"):
        parts.extend(["--verify-command", options["verify_command"]])
    if options.get("act_mode"):
        parts.extend(["--act-mode", options["act_mode"]])
    if options.get("compact_live") and "--compact-live" not in parts:
        parts.append("--compact-live")
    if options.get("no_prompt_approval"):
        parts.append("--no-prompt-approval")
    elif options.get("prompt_approval"):
        parts.append("--prompt-approval")
    return parts


def _work_session_reentry_command(session, task_parts, max_steps=1, follow=False):
    parts = ["work", *task_parts, "--follow" if follow else "--live"]
    option_parts = _work_session_default_option_parts(session)
    parts.extend(option_parts)
    parts.extend(["--max-steps", str(max_steps)])
    return mew_command(*parts)


def _work_session_resume_command(session, task_parts):
    parts = ["work", *task_parts, "--session", "--resume"]
    for root in ((session or {}).get("default_options") or {}).get("allow_read") or []:
        parts.extend(["--allow-read", root])
    return mew_command(*parts)


def _format_focus_memory_stale(memory):
    if not memory:
        return ""
    if memory.get("stale_after_tool_call_id"):
        tool = memory.get("stale_after_tool") or "tool"
        return (
            f"tool #{memory.get('stale_after_tool_call_id')} {tool} ran after this memory; "
            "refresh before relying on next step"
        )
    if memory.get("stale_after_model_turn_id"):
        stale_turns = memory.get("stale_turns")
        if stale_turns is None:
            stale_turns = "some"
        return (
            f"{stale_turns} later model turn(s) after memory; "
            "refresh before relying on next step"
        )
    return ""


def _format_focus_friction_summary(friction):
    rates = friction.get("rates") or {}
    latency = friction.get("latency") or {}
    parts = []
    for label, key in (
        ("approval_rejection", "approval_rejection"),
        ("verification_failure", "verification_failure"),
        ("verification_rollback", "verification_rollback"),
    ):
        value = rates.get(key)
        if value is not None and value > 0:
            parts.append(f"{label}={value}")
    if latency.get("model_resume_p95") is not None and friction.get("slow_model_resumes"):
        parts.append(f"model_resume_p95={latency.get('model_resume_p95')}s")
    if latency.get("approval_bound_p95") is not None and friction.get("approval_bound_waits"):
        parts.append(f"approval_bound_p95={latency.get('approval_bound_p95')}s")
    return " ".join(parts)


def _append_focus_recent_friction(lines, friction):
    if not friction:
        return
    lines.append("")
    heading = "Recent friction"
    if friction.get("active_blocker_count") == 0:
        heading += " (historical; no active blockers)"
    lines.append(heading)
    summary = _format_focus_friction_summary(friction)
    if summary:
        lines.append(f"- {summary}")
    for sample in friction.get("approval_friction") or []:
        task = f" task=#{sample.get('task_id')}" if sample.get("task_id") is not None else ""
        path = f" path={sample.get('path')}" if sample.get("path") else ""
        reason = _clip_focus_text(sample.get("reason") or sample.get("summary"), 220)
        suffix = f": {reason}" if reason else ""
        lines.append(
            f"- rejected {sample.get('tool')}#{sample.get('tool_call_id')}{task}{path}{suffix}"
        )
    for sample in friction.get("verification_failures") or []:
        task = f" task=#{sample.get('task_id')}" if sample.get("task_id") is not None else ""
        path = f" path={sample.get('path')}" if sample.get("path") else ""
        latest_note = sample.get("latest_note")
        detail = _clip_focus_text(latest_note or sample.get("stderr") or sample.get("stdout"), 220)
        if latest_note and detail:
            detail = f"note: {detail}"
        suffix = f": {detail}" if detail else ""
        lines.append(
            f"- failed {sample.get('tool')}#{sample.get('tool_call_id')}{task}{path} exit={sample.get('exit_code')}{suffix}"
        )
    for sample in friction.get("approval_bound_waits") or []:
        task = f" task=#{sample.get('task_id')}" if sample.get("task_id") is not None else ""
        path = f" path={sample.get('path')}" if sample.get("path") else ""
        approval = f" approval={sample.get('approval_status')}" if sample.get("approval_status") else ""
        lines.append(
            f"- approval wait {sample.get('tool')}#{sample.get('tool_call_id')}{task}{approval} "
            f"{sample.get('approval_bound_wait_seconds')}s{path}"
        )
    for sample in friction.get("slow_model_resumes") or []:
        task = f" task=#{sample.get('task_id')}" if sample.get("task_id") is not None else ""
        path = f" path={sample.get('path')}" if sample.get("path") else ""
        lines.append(
            f"- model resume {sample.get('tool')}#{sample.get('tool_call_id')}{task} "
            f"{sample.get('model_resume_wait_seconds')}s{path}"
        )


def format_focus(data):
    title = "Mew focus"
    if data.get("kind"):
        title += f" ({data.get('kind')})"
    lines = [title, f"Next: {data.get('next_move')}"]
    if data.get("coding_next_move"):
        lines.append(f"Coding: {data.get('coding_next_move')}")
    unread = data.get("unread_outbox_count") or 0
    if unread:
        lines.append(f"Unread: {unread}")
    routine_unread = data.get("routine_unread_info_count") or 0
    if routine_unread:
        lines.append(f"Routine info: {routine_unread} clear with `{mew_command('ack', '--routine')}`")
    checkpoint = data.get("latest_context_checkpoint") or {}
    if checkpoint:
        current_git = data.get("current_git") or {}
        note = " ".join(str(checkpoint.get("reentry_note") or "").split())
        if len(note) > 280:
            note = note[:277].rstrip() + "..."
        lines.append(f"Checkpoint: {checkpoint.get('name') or checkpoint.get('key')} ({checkpoint.get('created_at')})")
        if current_git.get("status") != "unknown":
            dirty_paths = current_git.get("dirty_paths") or []
            path_suffix = f" paths={', '.join(dirty_paths[:5])}" if dirty_paths else ""
            lines.append(
                f"Checkpoint git: {current_git.get('status')} head={current_git.get('head') or '(unknown)'}"
                f"{path_suffix}"
            )
        if note:
            lines.append(f"Checkpoint note: {note}")
        lines.append(f"Checkpoint load: {mew_command('context', '--load', '--limit', '1')}")

    _append_focus_recent_friction(lines, data.get("recent_friction") or {})

    questions = data.get("open_questions") or []
    if questions:
        lines.append("")
        lines.append("Questions")
        for question in questions:
            task = f" task=#{question.get('related_task_id')}" if question.get("related_task_id") else ""
            context = format_question_context(
                question,
                current_time=data.get("generated_at"),
                include_defer_reason=False,
            )
            lines.append(f"- #{question.get('id')}{task}{context}: {question.get('text')}")

    attention = data.get("attention") or []
    if attention:
        lines.append("")
        lines.append("Attention")
        for item in attention:
            lines.append(f"- #{item.get('id')} [{item.get('priority')}] {item.get('title')}")

    work_sessions = data.get("active_work_sessions") or []
    if work_sessions:
        lines.append("")
        lines.append("Active work sessions")
        for session in work_sessions:
            lines.append(
                f"- #{session.get('id')} task=#{session.get('task_id')} "
                f"phase={session.get('phase')} {session.get('title') or ''}"
            )
            continuity_text = format_work_continuity_inline(session.get("continuity") or {})
            if continuity_text:
                lines.append(f"  {continuity_text}")
            continuity_next = format_work_continuity_recommendation(session.get("continuity") or {})
            if continuity_next:
                lines.append(f"  {continuity_next}")
            if session.get("next_action"):
                lines.append(f"  next: {session.get('next_action')}")
            if session.get("risk"):
                lines.append(f"  risk: {session.get('risk')}")
            if session.get("updated_at"):
                inactive = session.get("inactive_for")
                if inactive:
                    lines.append(f"  last_active: {session.get('updated_at')} ({inactive} ago)")
                else:
                    lines.append(f"  last_active: {session.get('updated_at')}")
            memory = session.get("working_memory") or {}
            stale_memory = _format_focus_memory_stale(memory)
            if memory.get("hypothesis"):
                suffix = " (stale)" if stale_memory else ""
                lines.append(f"  memory: {memory.get('hypothesis')}{suffix}")
            if stale_memory:
                lines.append(f"  memory_stale: {stale_memory}")
            elif memory.get("next_step"):
                lines.append(f"  memory_next: {memory.get('next_step')}")
            pending_steer = session.get("pending_steer") or {}
            if pending_steer.get("text"):
                lines.append(f"  pending_steer: {pending_steer.get('text')}")
            queued_followups = session.get("queued_followups") or []
            if queued_followups:
                first = queued_followups[0]
                total = session.get("queued_followups_total") or len(queued_followups)
                suffix = f" ({len(queued_followups)}/{total})" if total != len(queued_followups) else ""
                lines.append(f"  queued_followup{suffix}: {first.get('text')}")
            compressed_prior = session.get("compressed_prior_think") or {}
            if compressed_prior.get("items"):
                item = (compressed_prior.get("items") or [])[-1]
                summary = item.get("summary") or item.get("hypothesis") or ""
                lines.append(
                    f"  prior_think: {compressed_prior.get('shown')}/{compressed_prior.get('total_older_model_turns')} "
                    f"older turn(s); latest=#{item.get('model_turn_id')} {summary}".rstrip()
                )
            lines.append(f"  resume: {session.get('resume_command')}")
            lines.append(f"  continue: {session.get('continue_command')}")
            lines.append(f"  follow: {session.get('follow_command')}")

    tasks = data.get("tasks") or []
    if tasks:
        lines.append("")
        lines.append("Tasks")
        for task in tasks:
            lines.append(
                f"- #{task.get('id')} [{task.get('kind')}/{task.get('status')}/{task.get('priority')}] "
                f"{task.get('title')}"
            )
            lines.append(f"  next: {task.get('next_step')}")

    omitted = (data.get("open_task_count") or 0) - len(tasks)
    if omitted > 0:
        lines.append(f"... {omitted} more open task(s)")
    return "\n".join(lines)


def continuity_repair_summary(continuity):
    if not continuity or not (continuity.get("missing") or []):
        return ""
    if continuity.get("status") not in {"weak", "broken"}:
        return ""
    recommendation = continuity.get("recommendation") or {}
    return str(recommendation.get("summary") or "").strip()


def next_move(state, kind=None):
    tasks = filter_tasks_by_kind(sorted(open_tasks(state), key=task_sort_key), kind=kind)
    questions = filter_questions_for_tasks(
        [question for question in state.get("questions", []) if question.get("status") == "open"],
        tasks,
        kind=kind,
    )
    running_tasks = [task for task in tasks if task.get("status") == "running"]
    running_task_ids = {str(task.get("id")) for task in running_tasks}
    attention = [
        item for item in state.get("attention", {}).get("items", []) if item.get("status") == "open"
    ]
    attention = filter_attention_for_tasks(attention, tasks, kind=kind)
    task_ids = {str(task.get("id")) for task in tasks}
    running_runs = [
        run for run in running_agent_runs(state)
        if not kind or str(run.get("task_id")) in task_ids
    ]
    running_task_runs = [
        run for run in running_runs if str(run.get("task_id")) in running_task_ids
    ]
    review_waiting = [
        run for run in implementation_runs_needing_review(state)
        if not kind or str(run.get("task_id")) in task_ids
    ]
    followup_waiting = [
        run for run in review_runs_needing_followup(state)
        if not kind or str(run.get("task_id")) in task_ids
    ]
    dry_run_waiting = dry_run_implementation_runs(state, tasks)
    dispatchable = dispatchable_planned_tasks(tasks)
    plan_needed = tasks_needing_plan(tasks)
    recent_verifications = (
        recent_verification_runs_for_tasks(state, task_ids, limit=1)
        if kind
        else recent_verification_runs(state, limit=1)
    )
    active_work = active_work_session_items(state, limit=1, kind=kind)

    if running_tasks:
        for question in questions:
            if str(question.get("related_task_id")) in running_task_ids:
                return f"answer question #{question.get('id')} with `{mew_command('reply', question.get('id'))} \"...\"`"
        if running_task_runs:
            return f"check agent run #{running_task_runs[0].get('id')} with `{mew_command('agent', 'result', running_task_runs[0].get('id'))}`"
        return practical_next_step(running_tasks[0])
    if questions:
        return f"answer question #{questions[0].get('id')} with `{mew_command('reply', questions[0].get('id'))} \"...\"`"
    if running_runs:
        return f"check agent run #{running_runs[0].get('id')} with `{mew_command('agent', 'result', running_runs[0].get('id'))}`"
    if recent_verifications and verification_outcome(recent_verifications[0]) == "failed":
        return f"inspect verification run #{recent_verifications[0].get('id')} with `{mew_command('verification')}`"
    if active_work:
        session = active_work[0]
        continuity_summary = continuity_repair_summary(session.get("continuity") or {})
        if continuity_summary:
            command = session.get("continue_command") or session.get("resume_command")
            return (
                f"repair continuity for active work session #{session.get('id')}: "
                f"{continuity_summary} via `{command}`"
            )
        task = next((task for task in tasks if str(task.get("id")) == str(session.get("task_id"))), {})
        if task_kind(task) == "coding" and session.get("task_id") is not None:
            return (
                f"enter coding cockpit for active work session #{session.get('id')} "
                f"task #{session.get('task_id')} with `{mew_command('code', session.get('task_id'))}`"
            )
        return (
            f"continue active work session #{session.get('id')} for task #{session.get('task_id')} "
            f"with `{session.get('continue_command')}`"
        )
    if followup_waiting:
        return f"process review run #{followup_waiting[0].get('id')} with `{mew_command('agent', 'followup', followup_waiting[0].get('id'))}`"
    if review_waiting:
        return f"review implementation run #{review_waiting[0].get('id')} with `{mew_command('agent', 'review', review_waiting[0].get('id'))}`"
    if dry_run_waiting:
        task_id = dry_run_waiting[0].get("task_id")
        return f"dispatch dry-run task #{task_id} for real with `{mew_command('buddy', '--task', task_id, '--dispatch')}`"
    if dispatchable:
        task, plan = dispatchable[0]
        return f"dispatch task #{task.get('id')} plan #{plan.get('id')} with `{mew_command('task', 'dispatch', task.get('id'))}`"
    if plan_needed:
        task_id = plan_needed[0].get("id")
        return f"enter coding cockpit for task #{task_id} with `{mew_command('code', task_id)}`"
    if attention:
        return f"resolve attention #{attention[0].get('id')}: {attention[0].get('title')}"
    if tasks:
        return practical_next_step(tasks[0])
    if kind == "coding":
        if not current_project_looks_like_mew():
            return (
                "add a coding task with "
                f"`{mew_command('task', 'add', '...', '--kind', 'coding', '--ready')}`"
            )
        return (
            "start a native self-improvement session with "
            f"`{mew_command('self-improve', '--start-session', '--focus', 'Pick the next small mew improvement')}`"
        )
    return "wait for the next user request"


def build_brief(state, limit=5, kind=None, include_context_checkpoint=False):
    generated_at = now_iso()
    runtime = state.get("runtime_status", {})
    agent = scoped_agent_status(state, kind=kind)
    user = state.get("user_status", {})
    autonomy = state.get("autonomy", {})
    memory = state.get("memory", {})
    shallow = memory.get("shallow", {})
    deep = memory.get("deep", {})
    attention = [
        item for item in state.get("attention", {}).get("items", []) if item.get("status") == "open"
    ]
    questions = [question for question in state.get("questions", []) if question.get("status") == "open"]
    tasks = filter_tasks_by_kind(sorted(open_tasks(state), key=task_sort_key), kind=kind)
    questions = filter_questions_for_tasks(questions, tasks, kind=kind)
    attention = filter_attention_for_tasks(attention, tasks, kind=kind)
    unread = filter_messages_for_tasks(open_unread_messages(state), tasks, kind=kind)
    routine_unread = [message for message in unread if is_routine_outbox_message(state, message)]
    running_runs = running_agent_runs(state)
    review_waiting = implementation_runs_needing_review(state)
    followup_waiting = review_runs_needing_followup(state)
    dry_run_waiting = dry_run_implementation_runs(state, tasks)
    dispatchable = dispatchable_planned_tasks(tasks)
    plan_needed = tasks_needing_plan(tasks)
    verifications = recent_records(
        filter_records_for_tasks(state.get("verification_runs", []), tasks, kind=kind),
        limit=limit,
    )
    writes = recent_records(
        filter_records_for_tasks(state.get("write_runs", []), tasks, kind=kind),
        limit=limit,
    )
    runtime_effects = recent_records(
        filter_records_for_tasks(state.get("runtime_effects", []), tasks, kind=kind),
        limit=limit,
    )
    step_runs = [] if kind else recent_step_runs(state, limit=limit)
    thoughts = [] if kind else recent_thoughts_for_context(state, limit=limit)
    activity = [] if kind else recent_activity(state, limit=limit)
    recent_unread = list(reversed(unread[-limit:]))
    context_checkpoint = latest_context_checkpoint() if include_context_checkpoint else {}
    current_git = current_git_reentry_state() if include_context_checkpoint else {}
    if kind:
        task_ids = {str(task.get("id")) for task in tasks}
        running_runs = [run for run in running_runs if str(run.get("task_id")) in task_ids]
        review_waiting = [run for run in review_waiting if str(run.get("task_id")) in task_ids]
        followup_waiting = [run for run in followup_waiting if str(run.get("task_id")) in task_ids]

    title = "Mew brief"
    if kind:
        title += f" ({kind})"
    lines = [
        f"{title} at {now_iso()}",
        f"runtime: {runtime.get('state')} pid={runtime.get('pid')}",
        f"agent: {agent.get('mode')} focus={agent.get('current_focus') or '(none)'}",
        f"autonomy: {'on' if autonomy.get('enabled') else 'off'} level={autonomy.get('level') or 'off'} cycles={autonomy.get('cycles') or 0}",
        f"user: {user.get('mode')} last_request={user.get('last_request') or '(none)'}",
        f"unread_outbox: {len(unread)}",
        f"memory: {_first_nonempty(shallow.get('current_context'), shallow.get('latest_task_summary'), '(empty)')}",
        "",
    ]
    if context_checkpoint:
        note = " ".join(str(context_checkpoint.get("reentry_note") or "").split())
        if len(note) > 500:
            note = note[:497].rstrip() + "..."
        lines.insert(
            -1,
            "context_checkpoint: "
            f"{context_checkpoint.get('name') or context_checkpoint.get('key')} "
            f"at={context_checkpoint.get('created_at')} "
            f"load={mew_command('context', '--load', '--limit', '1')}",
        )
        if current_git.get("status") != "unknown":
            dirty_paths = current_git.get("dirty_paths") or []
            path_suffix = f" paths={', '.join(dirty_paths[:5])}" if dirty_paths else ""
            lines.insert(
                -1,
                f"context_checkpoint_git: {current_git.get('status')} head={current_git.get('head') or '(unknown)'}"
                f"{path_suffix}",
            )
        if note:
            lines.insert(-1, f"context_checkpoint_note: {note}")
    skip_recovery = runtime.get("last_native_work_skip_recovery") or {}
    if runtime.get("last_native_work_step_skip"):
        recovery = f" next={skip_recovery.get('command')}" if skip_recovery.get("command") else ""
        lines.insert(-1, f"native_work_skip: {runtime.get('last_native_work_step_skip')}{recovery}")
    native_recovery = runtime.get("last_native_work_recovery") or {}
    if native_recovery.get("action"):
        status = f" status={native_recovery.get('status')}" if native_recovery.get("status") else ""
        command = f" command={native_recovery.get('command')}" if native_recovery.get("command") else ""
        lines.insert(-1, f"native_work_recovery: {native_recovery.get('action')}{status}{command}")
    startup_repairs = runtime.get("last_startup_repairs") or []
    if startup_repairs:
        repair_types = ", ".join(repair.get("type") or "unknown" for repair in startup_repairs[:3])
        suffix = f" at={runtime.get('last_startup_repair_at')}" if runtime.get("last_startup_repair_at") else ""
        lines.insert(-1, f"startup_repair: {len(startup_repairs)} item(s){suffix} types={repair_types}")
    snapshot_item = _project_snapshot_item(deep.get("project_snapshot"))
    if snapshot_item:
        project_types = ", ".join(snapshot_item.get("project_types") or []) or "(unknown)"
        package = snapshot_item.get("package_name") or "(unknown)"
        lines.insert(
            -1,
            "project_snapshot: "
            f"types={project_types} package={package} "
            f"roots={snapshot_item.get('root_count')} files={snapshot_item.get('file_count')} "
            f"updated_at={snapshot_item.get('updated_at')}",
        )

    if unread:
        lines.append("Unread messages")
        if routine_unread:
            lines.append(f"- routine info: {len(routine_unread)}; clear with `{mew_command('ack', '--routine')}`")
        if len(unread) > len(recent_unread):
            lines.append(
                f"- showing latest {len(recent_unread)}; {len(unread) - len(recent_unread)} older unread omitted"
            )
        for message in recent_unread:
            lines.append(
                f"- #{message.get('id')} [{message.get('type')}] {str(message.get('text') or '').splitlines()[0]}"
            )
        lines.append("")

    if attention:
        lines.append("Attention")
        for item in attention[:limit]:
            lines.append(
                f"- #{item.get('id')} [{item.get('priority')}] {item.get('title')}: {item.get('reason')}"
            )
        lines.append("")

    if questions:
        lines.append("Open questions")
        for question in questions[:limit]:
            task = f" task=#{question.get('related_task_id')}" if question.get("related_task_id") else ""
            context = format_question_context(
                question,
                current_time=generated_at,
                include_defer_reason=False,
            )
            lines.append(f"- #{question.get('id')}{task}{context}: {question.get('text')}")
        lines.append("")

    if tasks:
        lines.append("Open tasks")
        for task in tasks[:limit]:
            run = f" agent_run=#{task.get('agent_run_id')}" if task.get("agent_run_id") else ""
            lines.append(
                f"- #{task.get('id')} [{task.get('status')}/{task.get('priority')}/{task_kind(task)}] "
                f"{task.get('title')}{run}"
            )
        lines.append("")

    if running_runs:
        lines.append("Running agents")
        for run in running_runs[:limit]:
            pid = f" pid={run.get('external_pid')}" if run.get("external_pid") else ""
            lines.append(
                f"- #{run.get('id')} task=#{run.get('task_id')} "
                f"{run.get('backend')}:{run.get('model')} status={run.get('status')}{pid}"
            )
        lines.append("")

    if verifications:
        lines.append("Recent verification")
        for run in verifications[:limit]:
            lines.append(
                f"- #{run.get('id')} [{verification_outcome(run)}] "
                f"exit_code={run.get('exit_code')} command={run.get('command')}"
            )
        lines.append("")

    if writes:
        lines.append("Recent writes")
        for run in writes[:limit]:
            rollback = " rolled_back=true" if run.get("rolled_back") else ""
            verification = (
                f" verification=#{run.get('verification_run_id')}"
                f" exit={run.get('verification_exit_code')}"
                if run.get("verification_run_id") is not None
                else ""
            )
            lines.append(
                f"- #{run.get('id')} [{run.get('operation') or run.get('action_type')}] "
                f"changed={run.get('changed')} dry_run={run.get('dry_run')} "
                f"written={run.get('written')}{rollback}{verification} path={run.get('path')}"
            )
        lines.append("")

    if runtime_effects:
        lines.append("Recent runtime effects")
        for effect in runtime_effects[:limit]:
            actions = ",".join(effect.get("action_types") or []) or "-"
            verification = ",".join(str(item) for item in effect.get("verification_run_ids") or []) or "-"
            writes_text = ",".join(str(item) for item in effect.get("write_run_ids") or []) or "-"
            lines.append(
                f"- #{effect.get('id')} [{effect.get('status')}] "
                f"event=#{effect.get('event_id')} reason={effect.get('reason')} "
                f"actions={actions} verification={verification} writes={writes_text}"
            )
        lines.append("")

    if activity:
        lines.append("Recent activity")
        for item in activity[:limit]:
            actions = item.get("actions") or []
            suffix = f" actions={', '.join(actions)}" if actions else ""
            lines.append(
                f"- #{item.get('id')} {activity_label(item)}: "
                f"{item.get('summary')}{suffix}"
            )
        lines.append("")

    if step_runs:
        lines.append("Recent steps")
        for run in step_runs[:limit]:
            action_types = ", ".join(
                action.get("type") or "unknown" for action in run.get("actions", [])[:3]
            )
            skipped = run.get("skipped_actions") or []
            skipped_text = f" skipped={len(skipped)}" if skipped else ""
            effects = run.get("effects") or []
            effects_text = f" effects={len(effects)}" if effects else ""
            suffix = f" actions={action_types}" if action_types else ""
            lines.append(
                f"- #{run.get('id')} event=#{run.get('event_id')} "
                f"stop={run.get('stop_reason')}{suffix}{skipped_text}{effects_text}: "
                f"{run.get('summary') or ''}"
            )
        lines.append("")

    if thoughts:
        lines.append("Thought journal")
        show_thread_counts = bool(
            questions
            or attention
            or tasks
            or running_runs
            or review_waiting
            or followup_waiting
            or dry_run_waiting
            or dispatchable
            or plan_needed
        )
        for thought in thoughts[:limit]:
            open_count = len(thought.get("open_threads", []))
            dropped_count = len(thought.get("dropped_threads", []))
            suffix = f" open_threads={open_count}" if show_thread_counts and open_count else ""
            if show_thread_counts and dropped_count:
                suffix += f" dropped_threads={dropped_count}"
            lines.append(
                f"- #{thought.get('id')} {thought.get('event_type')}#{thought.get('event_id')}: "
                f"{thought.get('summary')}{suffix}"
            )
        lines.append("")

    if review_waiting or followup_waiting or dry_run_waiting or dispatchable or plan_needed:
        lines.append("Programmer queue")
        for run in review_waiting[:limit]:
            lines.append(f"- review needed: run #{run.get('id')} task=#{run.get('task_id')}")
        for run in followup_waiting[:limit]:
            lines.append(f"- follow-up needed: review run #{run.get('id')} task=#{run.get('task_id')}")
        for run in dry_run_waiting[:limit]:
            lines.append(f"- dry-run ready: run #{run.get('id')} task=#{run.get('task_id')}")
        for task, plan in dispatchable[:limit]:
            lines.append(f"- dispatchable: task #{task.get('id')} plan=#{plan.get('id')}")
        for task in plan_needed[:limit]:
            lines.append(f"- plan needed: task #{task.get('id')} {task.get('title')}")
        lines.append("")

    lines.append(f"Next useful move: {next_move(state, kind=kind)}.")

    return "\n".join(lines).rstrip()
