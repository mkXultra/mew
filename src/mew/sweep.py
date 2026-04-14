from .agent_runs import get_agent_run_result, start_agent_run
from .programmer import (
    create_follow_up_task_from_review,
    create_review_run_for_implementation,
    find_review_run_for_implementation,
    find_task_plan,
)
from .state import add_attention_item
from .tasks import task_by_id
from .timeutil import elapsed_hours, now_iso


def run_age_minutes(run, current_time):
    since = run.get("started_at") or run.get("updated_at") or run.get("created_at")
    hours = elapsed_hours(since, current_time)
    if hours is None:
        return None
    return hours * 60.0


def stale_running_run(run, current_time, stale_minutes):
    if run.get("status") not in ("created", "running"):
        return False
    age = run_age_minutes(run, current_time)
    return age is not None and age >= stale_minutes


def _append(report, kind, text):
    report.setdefault(kind, []).append(text)


def sweep_agent_runs(
    state,
    collect=True,
    start_reviews=False,
    followup=True,
    stale_minutes=60,
    dry_run=False,
    review_model=None,
):
    current_time = now_iso()
    report = {
        "collected": [],
        "stale": [],
        "review_needed": [],
        "review_started": [],
        "followup_needed": [],
        "followup_created": [],
        "no_followup": [],
        "errors": [],
    }

    for run in list(state.get("agent_runs", [])):
        status = run.get("status")
        if status not in ("created", "running"):
            continue

        age = run_age_minutes(run, current_time)
        if stale_running_run(run, current_time, stale_minutes):
            text = f"run #{run.get('id')} task={run.get('task_id')} status={status} age={age:.1f}m"
            _append(report, "stale", text)
            if not dry_run:
                add_attention_item(
                    state,
                    "agent_run_stale",
                    f"Agent run #{run.get('id')} may be stale",
                    text,
                    related_task_id=run.get("task_id"),
                    agent_run_id=run.get("id"),
                    priority="high",
                )

        if not collect:
            continue
        if not run.get("external_pid"):
            continue

        if dry_run:
            _append(report, "collected", f"would collect run #{run.get('id')}")
            continue

        before = run.get("status")
        try:
            get_agent_run_result(state, run)
        except ValueError as exc:
            _append(report, "errors", f"run #{run.get('id')}: {exc}")
            continue
        after = run.get("status")
        _append(report, "collected", f"run #{run.get('id')} {before} -> {after}")

    for run in list(state.get("agent_runs", [])):
        if run.get("purpose", "implementation") != "implementation":
            continue
        if run.get("status") not in ("completed", "failed"):
            continue
        if find_review_run_for_implementation(state, run.get("id")):
            continue

        task = task_by_id(state, run.get("task_id"))
        if not task:
            _append(report, "errors", f"run #{run.get('id')}: missing task #{run.get('task_id')}")
            continue
        plan = find_task_plan(task, run.get("plan_id")) if run.get("plan_id") else None

        if not start_reviews:
            _append(report, "review_needed", f"run #{run.get('id')} task={task.get('id')}")
            continue
        if dry_run:
            _append(report, "review_started", f"would start review for run #{run.get('id')}")
            continue

        review_run = create_review_run_for_implementation(
            state,
            task,
            run,
            plan=plan,
            model=review_model,
        )
        start_agent_run(state, review_run)
        _append(
            report,
            "review_started",
            f"review run #{review_run.get('id')} for implementation run #{run.get('id')} status={review_run.get('status')}",
        )

    for run in list(state.get("agent_runs", [])):
        if run.get("purpose") != "review":
            continue
        if run.get("status") not in ("completed", "failed"):
            continue
        if run.get("followup_task_id"):
            continue

        task = task_by_id(state, run.get("task_id"))
        if not task:
            _append(report, "errors", f"review run #{run.get('id')}: missing task #{run.get('task_id')}")
            continue

        if not followup:
            _append(report, "followup_needed", f"review run #{run.get('id')} task={task.get('id')}")
            continue
        if dry_run:
            _append(report, "followup_created", f"would process follow-up for review run #{run.get('id')}")
            continue

        followup_task, status = create_follow_up_task_from_review(state, task, run)
        if followup_task:
            _append(
                report,
                "followup_created",
                f"task #{followup_task.get('id')} from review run #{run.get('id')} status={status}",
            )
        else:
            _append(report, "no_followup", f"review run #{run.get('id')} status={status}")

    return report


def format_sweep_report(report):
    lines = []
    for key, title in (
        ("collected", "Collected"),
        ("stale", "Stale"),
        ("review_needed", "Review needed"),
        ("review_started", "Review started"),
        ("followup_needed", "Follow-up needed"),
        ("followup_created", "Follow-up created"),
        ("no_followup", "No follow-up"),
        ("errors", "Errors"),
    ):
        items = report.get(key) or []
        if not items:
            continue
        lines.append(title)
        lines.extend(f"- {item}" for item in items)
    return "\n".join(lines) if lines else "No agent-run work."
