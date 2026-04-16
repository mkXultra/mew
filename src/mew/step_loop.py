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
    "refine_task",
    "inspect_dir",
    "read_file",
    "search_text",
}

MAX_STEP_RUNS = 100
MAX_STEP_EFFECTS = 12
MAX_STEP_TEXT_CHARS = 240


def _synthetic_step_event(state, step_index, source="manual_step_planning"):
    return {
        "id": state.get("next_ids", {}).get("event", 1),
        "type": "passive_tick",
        "source": source,
        "payload": {"step_index": step_index},
        "created_at": now_iso(),
        "processed_at": None,
    }


def _planned_event_label(event, dry_run=False):
    prefix = "dry-run" if dry_run else "next"
    return f"{prefix}#{event.get('id')}"


def load_state_readonly():
    if not STATE_FILE.exists():
        return default_state()
    with STATE_FILE.open("r", encoding="utf-8") as handle:
        state = json.load(handle)
    return merge_defaults(migrate_state(state), default_state())


def filter_step_action_plan(action_plan, allow_verify=False, allow_write=False):
    allowed = set(STEP_ACTION_TYPES)
    if allow_verify:
        allowed.add("run_verification")
    if allow_write:
        allowed.update({"write_file", "edit_file"})

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


def _wait_action_text(action):
    return action.get("question") or action.get("text") or action.get("reason") or ""


def _has_matching_open_question(state, text, task_id):
    if not text:
        return False
    for question in state.get("questions", []):
        if question.get("status") != "open":
            continue
        if question.get("text") != text:
            continue
        if question.get("related_task_id") != task_id:
            continue
        return True
    return False


def suppress_redundant_wait_actions(action_plan, state):
    actions = []
    redundant = []
    for action in action_plan.get("actions", []):
        if action.get("type") not in ("ask_user", "wait_for_user"):
            actions.append(action)
            continue
        text = _wait_action_text(action)
        if _has_matching_open_question(state, text, action.get("task_id")):
            redundant.append(action)
        else:
            actions.append(action)

    if not redundant:
        return action_plan

    skipped = list(action_plan.get("skipped_actions") or [])
    skipped.extend({**action, "skip_reason": "existing_open_question"} for action in redundant)
    if not actions:
        actions.append(
            {
                "type": "self_review",
                "summary": (
                    "Skipped a repeated wait_for_user because an existing open question "
                    "already covers it; continue with non-duplicate work."
                ),
            }
        )
    return {
        **action_plan,
        "summary": (
            (action_plan.get("summary") or "")
            + " Skipped repeated wait_for_user already covered by an open question."
        ).strip(),
        "actions": actions,
        "skipped_actions": skipped,
    }


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
        "write_file",
        "edit_file",
        "refine_task",
    }
    if not any(action_type in feedback_types for action_type in action_types):
        return "no_feedback_action"
    return ""


def clip_step_text(value, limit=MAX_STEP_TEXT_CHARS):
    text = str(value or "")
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def compact_step_action(action):
    compact = {"type": action.get("type") or "unknown"}
    for key in ("task_id", "path", "query", "title", "kind", "question", "reason", "summary", "text"):
        value = action.get(key)
        if value is None:
            continue
        compact[key] = clip_step_text(value)
    if action.get("reset_plan") is not None:
        compact["reset_plan"] = bool(action.get("reset_plan"))
    return compact


def compact_step_reflex_observation(observation):
    action = observation.get("action") if isinstance(observation.get("action"), dict) else {}
    compact = {
        "round": observation.get("round"),
        "status": observation.get("status") or "unknown",
        "action": {
            key: clip_step_text(value) if isinstance(value, str) else value
            for key, value in action.items()
            if value is not None
        },
    }
    if observation.get("result"):
        compact["result"] = clip_step_text(observation.get("result"))
    if observation.get("error"):
        compact["error"] = clip_step_text(observation.get("error"))
    return {key: value for key, value in compact.items() if value is not None}


def compact_step_effect(effect_type, item):
    effect = {"type": effect_type, "id": item.get("id")}
    timestamp = item.get("created_at") or item.get("updated_at")
    if timestamp:
        effect["at"] = timestamp
    if effect_type == "message":
        effect.update(
            {
                "message_type": item.get("type"),
                "text": clip_step_text(item.get("text")),
                "related_task_id": item.get("related_task_id"),
                "question_id": item.get("question_id"),
                "agent_run_id": item.get("agent_run_id"),
            }
        )
    elif effect_type == "question":
        effect.update(
            {
                "text": clip_step_text(item.get("text")),
                "related_task_id": item.get("related_task_id"),
                "status": item.get("status"),
            }
        )
    elif effect_type == "verification_run":
        effect.update(
            {
                "task_id": item.get("task_id"),
                "exit_code": item.get("exit_code"),
                "reason": clip_step_text(item.get("reason")),
            }
        )
    elif effect_type == "write_run":
        effect.update(
            {
                "task_id": item.get("task_id"),
                "action_type": item.get("action_type"),
                "path": clip_step_text(item.get("path")),
                "dry_run": bool(item.get("dry_run")),
                "changed": item.get("changed"),
                "written": item.get("written"),
                "rolled_back": item.get("rolled_back"),
                "verification_run_id": item.get("verification_run_id"),
                "verification_exit_code": item.get("verification_exit_code"),
            }
        )
    return {key: value for key, value in effect.items() if value is not None}


def _is_protected_step_effect(effect):
    return effect.get("type") in ("question", "verification_run", "write_run") or (
        effect.get("type") == "message"
        and effect.get("message_type") == "question"
        and effect.get("question_id") is not None
    )


def _cap_step_effects(effects):
    if len(effects) <= MAX_STEP_EFFECTS:
        return effects
    protected = [
        effect
        for effect in effects
        if _is_protected_step_effect(effect)
    ]
    capped = list(effects[:MAX_STEP_EFFECTS])
    missing_protected = [effect for effect in protected if effect not in capped]
    if not missing_protected:
        return capped
    protected_slots = min(len(missing_protected), MAX_STEP_EFFECTS)
    return capped[: MAX_STEP_EFFECTS - protected_slots] + missing_protected[-protected_slots:]


def collect_step_effects(state, event_id):
    effects = []
    questions_by_id = {
        question.get("id"): question
        for question in state.get("questions", [])
        if question.get("event_id") == event_id
    }
    included_questions = set()
    for message in state.get("outbox", []):
        if message.get("event_id") == event_id:
            effects.append(compact_step_effect("message", message))
            question_id = message.get("question_id")
            question = questions_by_id.get(question_id)
            if question:
                effects.append(compact_step_effect("question", question))
                included_questions.add(question_id)
    for question in state.get("questions", []):
        if question.get("event_id") == event_id and question.get("id") not in included_questions:
            effects.append(compact_step_effect("question", question))
    for run in state.get("verification_runs", []):
        if run.get("event_id") == event_id:
            effects.append(compact_step_effect("verification_run", run))
    for run in state.get("write_runs", []):
        if run.get("event_id") == event_id:
            effects.append(compact_step_effect("write_run", run))
    return _cap_step_effects(effects)


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
        "reflex_observations": [
            compact_step_reflex_observation(observation)
            for observation in step.get("reflex_observations") or []
        ],
        "effects": [
            dict(effect)
            for effect in list(step.get("effects") or [])[:MAX_STEP_EFFECTS]
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
    allowed_write_roots=None,
    allow_verify=False,
    verify_command="",
    verify_timeout=300,
    allow_write=False,
    trace_model=False,
    max_reflex_rounds=0,
    progress=None,
):
    steps = []
    stop_reason = "max_steps"
    max_steps = max(1, int(max_steps or 1))
    allowed_read_roots = allowed_read_roots or []
    allowed_write_roots = allowed_write_roots or []

    for index in range(max_steps):
        current_time = now_iso()
        if dry_run:
            state = load_state_readonly()
            event = _synthetic_step_event(state, index + 1, source="manual_step_dry_run")
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

        if progress:
            progress(
                f"step #{index + 1}: planning start "
                f"planned_event={_planned_event_label(event_snapshot, dry_run=dry_run)}"
            )
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
            allow_write=allow_write,
            allowed_read_roots=allowed_read_roots,
            allowed_write_roots=allowed_write_roots,
            log_phases=not dry_run,
            trace_model=bool(trace_model and not dry_run),
            max_reflex_rounds=max_reflex_rounds,
        )
        if progress:
            progress(
                f"step #{index + 1}: planning ok "
                f"planned_event={_planned_event_label(event_snapshot, dry_run=dry_run)}"
            )
        reflex_observations = [
            compact_step_reflex_observation(observation)
            for observation in decision_plan.get("reflex_observations") or []
        ]
        filtered_action_plan = filter_step_action_plan(
            action_plan,
            allow_verify=allow_verify,
            allow_write=allow_write,
        )
        filtered_action_plan = suppress_redundant_wait_actions(filtered_action_plan, state_snapshot)
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
                if progress:
                    progress(f"step #{index + 1}: apply start event=#{event_id}")
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
                    allow_write=allow_write,
                    allowed_write_roots=allowed_write_roots,
                ) or counts
                if progress:
                    progress(
                        f"step #{index + 1}: apply ok event=#{event_id} "
                        f"actions={counts.get('actions', 0)} messages={counts.get('messages', 0)}"
                    )
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
                    "reflex_observations": reflex_observations,
                    "effects": collect_step_effects(state, event_id),
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
                "reflex_observations": reflex_observations,
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
        planned_reads = [
            action
            for step in report.get("steps") or []
            for action in step.get("actions") or []
            if action.get("type") in ("inspect_dir", "read_file", "search_text")
        ]
        if planned_reads:
            lines.append("dry-run: read actions were planned but not executed")
    for step in report.get("steps") or []:
        lines.append(f"- step #{step.get('index')} event=#{step.get('event_id')}: {step.get('summary')}")
        for action in step.get("actions") or []:
            label = action.get("type") or "unknown"
            target = action.get("path") or action.get("title") or action.get("task_id") or ""
            suffix = f" {target}" if target else ""
            lines.append(f"  - {label}{suffix}")
        for observation in step.get("reflex_observations") or []:
            action = observation.get("action") or {}
            label = action.get("type") or "observation"
            target = action.get("path") or action.get("query") or ""
            target_suffix = f" {target}" if target else ""
            status = observation.get("status") or "unknown"
            lines.append(f"  reflex round {observation.get('round')}: {label}{target_suffix} {status}")
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
