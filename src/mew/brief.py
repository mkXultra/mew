from .programmer import find_review_run_for_implementation, latest_task_plan
from .state import is_routine_outbox_message
from .tasks import open_tasks, task_kind, task_needs_programmer_plan, task_sort_key
from .thoughts import recent_thoughts_for_context
from .timeutil import now_iso


def _first_nonempty(*values):
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


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


def recent_write_runs(state, limit=5):
    runs = list(state.get("write_runs", []))
    return list(reversed(runs[-limit:]))


def recent_runtime_effects(state, limit=5):
    runs = list(state.get("runtime_effects", []))
    return list(reversed(runs[-limit:]))


def recent_step_runs(state, limit=3):
    runs = list(state.get("step_runs", []))
    return list(reversed(runs[-limit:]))


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


def _question_item(question):
    return {
        "id": question.get("id"),
        "text": question.get("text"),
        "related_task_id": question.get("related_task_id"),
        "status": question.get("status"),
        "created_at": question.get("created_at"),
        "acknowledged_at": question.get("acknowledged_at"),
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


def activity_label(item):
    event_type = item.get("event_type") or "unknown"
    cycle_reason = item.get("cycle_reason") or ""
    if cycle_reason and cycle_reason != event_type:
        return f"{event_type}/{cycle_reason}"
    return event_type


def recent_activity(state, limit=5):
    thoughts = list(state.get("thought_journal", []))
    items = []
    for thought in reversed(thoughts):
        if thought.get("event_type") not in ("startup", "passive_tick", "user_message"):
            continue
        summary = thought.get("summary") or ""
        actions = thought.get("actions") or []
        if not summary and not actions:
            continue
        items.append(_activity_item(thought))
        if len(items) >= limit:
            break
    return items


def build_activity_data(state, limit=10):
    thoughts = list(state.get("thought_journal", []))
    dropped = [
        {
            "id": thought.get("id"),
            "event_id": thought.get("event_id"),
            "event_type": thought.get("event_type"),
            "dropped_thread_ratio": thought.get("dropped_thread_ratio", 0.0),
            "dropped_threads": thought.get("dropped_threads", []),
        }
        for thought in reversed(thoughts)
        if thought.get("dropped_threads")
    ]
    action_counts = {}
    for thought in thoughts:
        for action in thought.get("actions") or []:
            action_type = action.get("type") or "unknown"
            action_counts[action_type] = action_counts.get(action_type, 0) + 1
    return {
        "generated_at": now_iso(),
        "recent_activity": recent_activity(state, limit=limit),
        "action_counts": dict(sorted(action_counts.items())),
        "dropped_threads": dropped[:limit],
    }


def format_activity(state, limit=10):
    data = build_activity_data(state, limit=limit)
    activity = data["recent_activity"]
    lines = [f"Mew activity at {data['generated_at']}"]
    if not activity:
        lines.append("No recent activity.")
    else:
        for item in activity:
            actions = item.get("actions") or []
            suffix = f" actions={', '.join(actions)}" if actions else ""
            lines.append(
                f"- #{item.get('id')} {activity_label(item)}: "
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


def build_brief_data(state, limit=5):
    memory = state.get("memory", {})
    shallow = memory.get("shallow", {})
    deep = memory.get("deep", {})
    attention = [
        item for item in state.get("attention", {}).get("items", []) if item.get("status") == "open"
    ]
    questions = [question for question in state.get("questions", []) if question.get("status") == "open"]
    tasks = sorted(open_tasks(state), key=task_sort_key)
    unread = open_unread_messages(state)
    routine_unread = [message for message in unread if is_routine_outbox_message(state, message)]
    running_runs = running_agent_runs(state)
    review_waiting = implementation_runs_needing_review(state)
    followup_waiting = review_runs_needing_followup(state)
    dry_run_waiting = dry_run_implementation_runs(state, tasks)
    dispatchable = dispatchable_planned_tasks(tasks)
    plan_needed = tasks_needing_plan(tasks)

    return {
        "generated_at": now_iso(),
        "runtime": state.get("runtime_status", {}),
        "agent": state.get("agent_status", {}),
        "autonomy": state.get("autonomy", {}),
        "user": state.get("user_status", {}),
        "unread_outbox": [_message_item(message) for message in recent_unread_messages(state, limit=limit)],
        "unread_outbox_count": len(unread),
        "routine_unread_info_count": len(routine_unread),
        "memory": {
            "current_context": _first_nonempty(shallow.get("current_context"), ""),
            "latest_task_summary": _first_nonempty(shallow.get("latest_task_summary"), ""),
            "project_snapshot": _project_snapshot_item(deep.get("project_snapshot")),
        },
        "recent_activity": recent_activity(state, limit=limit),
        "thought_journal": [_thought_item(thought) for thought in recent_thoughts_for_context(state, limit=limit)],
        "attention": [_attention_item(item) for item in attention[:limit]],
        "open_questions": [_question_item(question) for question in questions[:limit]],
        "open_tasks": [_task_item(task) for task in tasks[:limit]],
        "open_task_count": len(tasks),
        "running_agents": [_agent_run_item(run) for run in running_runs[:limit]],
        "recent_verification": [
            _verification_item(run) for run in recent_verification_runs(state, limit=limit)
        ],
        "recent_writes": [
            _write_item(run) for run in recent_write_runs(state, limit=limit)
        ],
        "recent_runtime_effects": recent_runtime_effects(state, limit=limit),
        "recent_steps": recent_step_runs(state, limit=limit),
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
        "next_move": next_move(state),
    }

def build_focus_data(state, limit=3):
    tasks = sorted(open_tasks(state), key=task_sort_key)
    questions = [question for question in state.get("questions", []) if question.get("status") == "open"]
    attention = [
        item for item in state.get("attention", {}).get("items", []) if item.get("status") == "open"
    ]
    unread = open_unread_messages(state)
    routine_unread = [message for message in unread if is_routine_outbox_message(state, message)]
    return {
        "next_move": next_move(state),
        "unread_outbox_count": len(unread),
        "routine_unread_info_count": len(routine_unread),
        "open_questions": [_question_item(question) for question in questions[:limit]],
        "attention": [_attention_item(item) for item in attention[:limit]],
        "tasks": [
            {
                **_task_item(task),
                "next_step": practical_next_step(task),
            }
            for task in tasks[:limit]
        ],
        "open_task_count": len(tasks),
    }


def format_focus(data):
    lines = ["Mew focus", f"Next: {data.get('next_move')}"]
    unread = data.get("unread_outbox_count") or 0
    if unread:
        lines.append(f"Unread: {unread}")
    routine_unread = data.get("routine_unread_info_count") or 0
    if routine_unread:
        lines.append(f"Routine info: {routine_unread} clear with `mew ack --routine`")

    questions = data.get("open_questions") or []
    if questions:
        lines.append("")
        lines.append("Questions")
        for question in questions:
            task = f" task=#{question.get('related_task_id')}" if question.get("related_task_id") else ""
            lines.append(f"- #{question.get('id')}{task}: {question.get('text')}")

    attention = data.get("attention") or []
    if attention:
        lines.append("")
        lines.append("Attention")
        for item in attention:
            lines.append(f"- #{item.get('id')} [{item.get('priority')}] {item.get('title')}")

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


def next_move(state):
    questions = [question for question in state.get("questions", []) if question.get("status") == "open"]
    tasks = sorted(open_tasks(state), key=task_sort_key)
    running_tasks = [task for task in tasks if task.get("status") == "running"]
    running_task_ids = {str(task.get("id")) for task in running_tasks}
    attention = [
        item for item in state.get("attention", {}).get("items", []) if item.get("status") == "open"
    ]
    running_runs = running_agent_runs(state)
    running_task_runs = [
        run for run in running_runs if str(run.get("task_id")) in running_task_ids
    ]
    review_waiting = implementation_runs_needing_review(state)
    followup_waiting = review_runs_needing_followup(state)
    dry_run_waiting = dry_run_implementation_runs(state, tasks)
    dispatchable = dispatchable_planned_tasks(tasks)
    plan_needed = tasks_needing_plan(tasks)
    recent_verifications = recent_verification_runs(state, limit=1)

    if running_tasks:
        for question in questions:
            if str(question.get("related_task_id")) in running_task_ids:
                return f"answer question #{question.get('id')} with `mew reply {question.get('id')} \"...\"`"
        if running_task_runs:
            return f"check agent run #{running_task_runs[0].get('id')} with `mew agent result {running_task_runs[0].get('id')}`"
        return practical_next_step(running_tasks[0])
    if questions:
        return f"answer question #{questions[0].get('id')} with `mew reply {questions[0].get('id')} \"...\"`"
    if running_runs:
        return f"check agent run #{running_runs[0].get('id')} with `mew agent result {running_runs[0].get('id')}`"
    if recent_verifications and verification_outcome(recent_verifications[0]) == "failed":
        return f"inspect verification run #{recent_verifications[0].get('id')} with `mew verification`"
    if followup_waiting:
        return f"process review run #{followup_waiting[0].get('id')} with `mew agent followup {followup_waiting[0].get('id')}`"
    if review_waiting:
        return f"review implementation run #{review_waiting[0].get('id')} with `mew agent review {review_waiting[0].get('id')}`"
    if dry_run_waiting:
        task_id = dry_run_waiting[0].get("task_id")
        return f"dispatch dry-run task #{task_id} for real with `mew buddy --task {task_id} --dispatch`"
    if dispatchable:
        task, plan = dispatchable[0]
        return f"dispatch task #{task.get('id')} plan #{plan.get('id')} with `mew task dispatch {task.get('id')}`"
    if plan_needed:
        return f"plan task #{plan_needed[0].get('id')} with `mew task plan {plan_needed[0].get('id')}`"
    if attention:
        return f"resolve attention #{attention[0].get('id')}: {attention[0].get('title')}"
    if tasks:
        return practical_next_step(tasks[0])
    return "wait for the next user request"


def build_brief(state, limit=5):
    runtime = state.get("runtime_status", {})
    agent = state.get("agent_status", {})
    user = state.get("user_status", {})
    autonomy = state.get("autonomy", {})
    memory = state.get("memory", {})
    shallow = memory.get("shallow", {})
    deep = memory.get("deep", {})
    attention = [
        item for item in state.get("attention", {}).get("items", []) if item.get("status") == "open"
    ]
    questions = [question for question in state.get("questions", []) if question.get("status") == "open"]
    tasks = sorted(open_tasks(state), key=task_sort_key)
    unread = open_unread_messages(state)
    routine_unread = [message for message in unread if is_routine_outbox_message(state, message)]
    running_runs = running_agent_runs(state)
    review_waiting = implementation_runs_needing_review(state)
    followup_waiting = review_runs_needing_followup(state)
    dry_run_waiting = dry_run_implementation_runs(state, tasks)
    dispatchable = dispatchable_planned_tasks(tasks)
    plan_needed = tasks_needing_plan(tasks)
    verifications = recent_verification_runs(state, limit=limit)
    writes = recent_write_runs(state, limit=limit)
    runtime_effects = recent_runtime_effects(state, limit=limit)
    step_runs = recent_step_runs(state, limit=limit)
    thoughts = recent_thoughts_for_context(state, limit=limit)
    activity = recent_activity(state, limit=limit)
    recent_unread = recent_unread_messages(state, limit=limit)

    lines = [
        f"Mew brief at {now_iso()}",
        f"runtime: {runtime.get('state')} pid={runtime.get('pid')}",
        f"agent: {agent.get('mode')} focus={agent.get('current_focus') or '(none)'}",
        f"autonomy: {'on' if autonomy.get('enabled') else 'off'} level={autonomy.get('level') or 'off'} cycles={autonomy.get('cycles') or 0}",
        f"user: {user.get('mode')} last_request={user.get('last_request') or '(none)'}",
        f"unread_outbox: {len(unread)}",
        f"memory: {_first_nonempty(shallow.get('current_context'), shallow.get('latest_task_summary'), '(empty)')}",
        "",
    ]
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
            lines.append(f"- routine info: {len(routine_unread)}; clear with `mew ack --routine`")
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
            lines.append(f"- #{question.get('id')}{task}: {question.get('text')}")
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

    lines.append(f"Next useful move: {next_move(state)}.")

    return "\n".join(lines).rstrip()
