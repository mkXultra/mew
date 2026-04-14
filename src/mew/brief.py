from .programmer import find_review_run_for_implementation, latest_task_plan
from .tasks import open_tasks, task_sort_key
from .timeutil import now_iso


def _first_nonempty(*values):
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def open_unread_messages(state):
    return [message for message in state.get("outbox", []) if not message.get("read_at")]


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


def tasks_needing_plan(tasks):
    return [
        task
        for task in tasks
        if task.get("status") in ("todo", "ready") and not latest_task_plan(task)
    ]


def dispatchable_planned_tasks(tasks):
    result = []
    for task in tasks:
        plan = latest_task_plan(task)
        if (
            plan
            and plan.get("status") in ("planned", "dry_run")
            and task.get("status") == "ready"
            and task.get("auto_execute")
        ):
            result.append((task, plan))
    return result


def next_move(state):
    questions = [question for question in state.get("questions", []) if question.get("status") == "open"]
    tasks = sorted(open_tasks(state), key=task_sort_key)
    attention = [
        item for item in state.get("attention", {}).get("items", []) if item.get("status") == "open"
    ]
    running_runs = running_agent_runs(state)
    review_waiting = implementation_runs_needing_review(state)
    followup_waiting = review_runs_needing_followup(state)
    dispatchable = dispatchable_planned_tasks(tasks)
    plan_needed = tasks_needing_plan(tasks)

    if questions:
        return f"answer question #{questions[0].get('id')} with `mew reply {questions[0].get('id')} \"...\"`"
    if running_runs:
        return f"check agent run #{running_runs[0].get('id')} with `mew agent result {running_runs[0].get('id')}`"
    if followup_waiting:
        return f"process review run #{followup_waiting[0].get('id')} with `mew agent followup {followup_waiting[0].get('id')}`"
    if review_waiting:
        return f"review implementation run #{review_waiting[0].get('id')} with `mew agent review {review_waiting[0].get('id')}`"
    if dispatchable:
        task, plan = dispatchable[0]
        return f"dispatch task #{task.get('id')} plan #{plan.get('id')} with `mew task dispatch {task.get('id')}`"
    if plan_needed:
        return f"plan task #{plan_needed[0].get('id')} with `mew task plan {plan_needed[0].get('id')}`"
    if attention:
        return f"resolve attention #{attention[0].get('id')}: {attention[0].get('title')}"
    if tasks:
        return f"advance task #{tasks[0].get('id')}: {tasks[0].get('title')}"
    return "ask the user what to track next"


def build_brief(state, limit=5):
    runtime = state.get("runtime_status", {})
    agent = state.get("agent_status", {})
    user = state.get("user_status", {})
    autonomy = state.get("autonomy", {})
    memory = state.get("memory", {})
    shallow = memory.get("shallow", {})
    attention = [
        item for item in state.get("attention", {}).get("items", []) if item.get("status") == "open"
    ]
    questions = [question for question in state.get("questions", []) if question.get("status") == "open"]
    tasks = sorted(open_tasks(state), key=task_sort_key)
    unread = open_unread_messages(state)
    running_runs = running_agent_runs(state)
    review_waiting = implementation_runs_needing_review(state)
    followup_waiting = review_runs_needing_followup(state)
    dispatchable = dispatchable_planned_tasks(tasks)
    plan_needed = tasks_needing_plan(tasks)

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

    if unread:
        lines.append("Unread messages")
        for message in unread[:limit]:
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
                f"- #{task.get('id')} [{task.get('status')}/{task.get('priority')}] "
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

    if review_waiting or followup_waiting or dispatchable or plan_needed:
        lines.append("Programmer queue")
        for run in review_waiting[:limit]:
            lines.append(f"- review needed: run #{run.get('id')} task=#{run.get('task_id')}")
        for run in followup_waiting[:limit]:
            lines.append(f"- follow-up needed: review run #{run.get('id')} task=#{run.get('task_id')}")
        for task, plan in dispatchable[:limit]:
            lines.append(f"- dispatchable: task #{task.get('id')} plan=#{plan.get('id')}")
        for task in plan_needed[:limit]:
            lines.append(f"- plan needed: task #{task.get('id')} {task.get('title')}")
        lines.append("")

    lines.append(f"Next useful move: {next_move(state)}.")

    return "\n".join(lines).rstrip()
