from copy import deepcopy
import json

from .agent import apply_event_plans, plan_event, update_runtime_processing_summary
from .config import DEFAULT_CODEX_MODEL, DEFAULT_CODEX_WEB_BASE_URL, STATE_FILE
from .state import (
    add_event,
    default_state,
    load_state,
    merge_defaults,
    migrate_state,
    next_id,
    save_state,
    state_lock,
)
from .timeutil import now_iso


STEP_ACTION_TYPES = {
    "record_memory",
    "update_memory",
    "send_message",
    "ask_user",
    "wait_for_user",
    "self_review",
    "propose_task",
    "inspect_dir",
    "read_file",
    "search_text",
}

MAX_STEP_RUNS = 100


def _synthetic_step_event(state, step_index):
    return {
        "id": state.get("next_ids", {}).get("event", 1),
        "type": "passive_tick",
        "source": "manual_step_dry_run",
        "payload": {"step_index": step_index},
        "created_at": now_iso(),
        "processed_at": None,
    }


def load_state_readonly():
    if not STATE_FILE.exists():
        return default_state()
    with STATE_FILE.open("r", encoding="utf-8") as handle:
        state = json.load(handle)
    return merge_defaults(migrate_state(state), default_state())


def filter_step_action_plan(action_plan, allow_verify=False):
    allowed = set(STEP_ACTION_TYPES)
    if allow_verify:
        allowed.add("run_verification")

    actions = []
    skipped = []
    for action in action_plan.get("actions", []):
        action_type = action.get("type")
        if action_type in allowed:
            actions.append(dict(action))
        else:
            skipped.append(dict(action))

    if not actions:
        summary = action_plan.get("summary") or "No safe step action was available."
        if skipped:
            skipped_types = ", ".join(sorted({item.get("type") or "unknown" for item in skipped}))
            summary = f"{summary} Skipped unsupported step action(s): {skipped_types}."
        actions.append({"type": "record_memory", "summary": summary})

    filtered = {
        "summary": action_plan.get("summary") or "",
        "open_threads": list(action_plan.get("open_threads") or []),
        "resolved_threads": list(action_plan.get("resolved_threads") or []),
        "actions": actions,
    }
    if skipped:
        filtered["skipped_actions"] = skipped
    return filtered


def step_stop_reason(action_plan, dry_run=False):
    if dry_run:
        return "dry_run"
    action_types = [action.get("type") for action in action_plan.get("actions", [])]
    if any(action_type in ("ask_user", "wait_for_user") for action_type in action_types):
        return "waiting_for_user"
    feedback_types = {
        "update_memory",
        "self_review",
        "propose_task",
        "inspect_dir",
        "read_file",
        "search_text",
        "run_verification",
    }
    if not any(action_type in feedback_types for action_type in action_types):
        return "no_feedback_action"
    return ""


def compact_step_action(action):
    compact = {"type": action.get("type") or "unknown"}
    for key in ("task_id", "path", "query", "title", "question", "reason", "summary", "text"):
        value = action.get(key)
        if value is None:
            continue
        text = str(value)
        if len(text) > 240:
            text = text[:237] + "..."
        compact[key] = text
    return compact


def record_step_run(state, step, stop_reason, at):
    run = {
        "id": next_id(state, "step_run"),
        "at": at,
        "event_id": step.get("event_id"),
        "index": step.get("index"),
        "summary": step.get("summary") or "",
        "stop_reason": stop_reason or "continue",
        "actions": [compact_step_action(action) for action in step.get("actions") or []],
        "skipped_actions": [
            compact_step_action(action) for action in step.get("skipped_actions") or []
        ],
        "counts": dict(step.get("counts") or {}),
    }
    state.setdefault("step_runs", []).append(run)
    del state["step_runs"][:-MAX_STEP_RUNS]
    return run


def run_step_loop(
    max_steps=1,
    dry_run=False,
    model_auth=None,
    model=DEFAULT_CODEX_MODEL,
    base_url=DEFAULT_CODEX_WEB_BASE_URL,
    model_backend="codex",
    timeout=60,
    guidance="",
    policy="",
    self_text="",
    desires="",
    autonomy_level="act",
    allowed_read_roots=None,
    allow_verify=False,
    verify_command="",
    verify_timeout=300,
):
    steps = []
    stop_reason = "max_steps"
    max_steps = max(1, int(max_steps or 1))
    allowed_read_roots = allowed_read_roots or []

    for index in range(max_steps):
        current_time = now_iso()
        if dry_run:
            state = load_state_readonly()
            event = _synthetic_step_event(state, index + 1)
            state_snapshot = deepcopy(state)
            event_snapshot = deepcopy(event)
        else:
            with state_lock():
                state = load_state()
                event = _synthetic_step_event(state, index + 1)
                state_snapshot = deepcopy(state)
                event_snapshot = deepcopy(event)

        snapshot_autonomy = state_snapshot.setdefault("autonomy", {})
        snapshot_autonomy["enabled"] = True
        snapshot_autonomy["level"] = autonomy_level
        snapshot_autonomy["manual_step"] = True

        decision_plan, action_plan = plan_event(
            state_snapshot,
            event_snapshot,
            current_time,
            model_auth=model_auth,
            model=model,
            base_url=base_url,
            model_backend=model_backend,
            timeout=timeout,
            ai_ticks=False,
            allow_task_execution=False,
            guidance=guidance,
            policy=policy,
            self_text=self_text,
            desires=desires,
            autonomous=True,
            autonomy_level=autonomy_level,
            allow_agent_run=False,
            allow_verify=allow_verify,
            verify_command=verify_command or "",
            allow_write=False,
            allowed_read_roots=allowed_read_roots,
            allowed_write_roots=[],
            log_phases=not dry_run,
        )
        filtered_action_plan = filter_step_action_plan(action_plan, allow_verify=allow_verify)
        reason = step_stop_reason(filtered_action_plan, dry_run=dry_run)
        step_stop = reason or ("max_steps" if index == max_steps - 1 else "")

        counts = {"actions": 0, "messages": 0, "executed": 0, "waits": 0}
        event_id = event.get("id")
        apply_time = current_time
        step = None
        if not dry_run:
            with state_lock():
                state = load_state()
                event = add_event(
                    state,
                    "passive_tick",
                    "manual_step",
                    {"step_index": index + 1},
                )
                event_id = event.get("id")
                apply_time = now_iso()
                counts = apply_event_plans(
                    state,
                    event_id,
                    decision_plan,
                    filtered_action_plan,
                    apply_time,
                    "manual_step",
                    allow_task_execution=False,
                    allowed_read_roots=allowed_read_roots,
                    autonomous=True,
                    autonomy_level=autonomy_level,
                    allow_agent_run=False,
                    allow_verify=allow_verify,
                    verify_command=verify_command or "",
                    verify_timeout=verify_timeout,
                    allow_write=False,
                    allowed_write_roots=[],
                ) or counts
                update_runtime_processing_summary(
                    state,
                    "manual_step",
                    apply_time,
                    1 if counts else 0,
                    counts.get("actions", 0),
                    counts.get("messages", 0),
                    counts.get("executed", 0),
                    autonomous=True,
                )
                step = {
                    "index": index + 1,
                    "event_id": event_id,
                    "summary": filtered_action_plan.get("summary") or decision_plan.get("summary") or "",
                    "actions": filtered_action_plan.get("actions", []),
                    "skipped_actions": filtered_action_plan.get("skipped_actions", []),
                    "counts": counts,
                }
                record_step_run(state, step, step_stop, apply_time)
                save_state(state)

        if step is None:
            step = {
                "index": index + 1,
                "event_id": event_id,
                "summary": filtered_action_plan.get("summary") or decision_plan.get("summary") or "",
                "actions": filtered_action_plan.get("actions", []),
                "skipped_actions": filtered_action_plan.get("skipped_actions", []),
                "counts": counts,
            }
        steps.append(step)

        if reason:
            stop_reason = reason
            break

    return {
        "steps": steps,
        "stop_reason": stop_reason,
        "dry_run": dry_run,
        "max_steps": max_steps,
    }


def format_step_loop_report(report):
    lines = [
        f"mew step: {len(report.get('steps') or [])}/{report.get('max_steps')} step(s) "
        f"stop={report.get('stop_reason')}"
    ]
    if report.get("dry_run"):
        lines.append("dry_run: true")
    for step in report.get("steps") or []:
        lines.append(f"- step #{step.get('index')} event=#{step.get('event_id')}: {step.get('summary')}")
        for action in step.get("actions") or []:
            label = action.get("type") or "unknown"
            target = action.get("path") or action.get("title") or action.get("task_id") or ""
            suffix = f" {target}" if target else ""
            lines.append(f"  - {label}{suffix}")
        skipped = step.get("skipped_actions") or []
        if skipped:
            labels = ", ".join(action.get("type") or "unknown" for action in skipped)
            lines.append(f"  skipped: {labels}")
        counts = step.get("counts") or {}
        if counts:
            lines.append(
                "  counts: "
                f"actions={counts.get('actions', 0)} "
                f"messages={counts.get('messages', 0)} "
                f"waits={counts.get('waits', 0)}"
            )
    return "\n".join(lines)
