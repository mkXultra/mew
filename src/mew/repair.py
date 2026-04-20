from .cli_command import mew_command
from .state import add_question, incomplete_runtime_effects, update_runtime_effect
from .timeutil import now_iso


PRECOMMIT_RUNTIME_STATUSES = {"planning", "planned", "precomputing", "precomputed"}
TERMINAL_RUNTIME_EFFECT_STATUSES = {
    "applied",
    "verified",
    "failed",
    "recovered",
    "skipped",
    "deferred",
}


def _find_event(state, event_id):
    if event_id is None:
        return None
    for event in (state or {}).get("inbox", []) or []:
        if str(event.get("id")) == str(event_id):
            return event
    return None


def _has_later_terminal_effect(state, effect):
    event_id = (effect or {}).get("event_id")
    effect_id = (effect or {}).get("id")
    if event_id is None or effect_id is None:
        return False
    for candidate in (state or {}).get("runtime_effects", []) or []:
        if str(candidate.get("event_id")) != str(event_id):
            continue
        try:
            later = int(candidate.get("id")) > int(effect_id)
        except (TypeError, ValueError):
            later = str(candidate.get("id")) != str(effect_id)
        if later and candidate.get("status") in TERMINAL_RUNTIME_EFFECT_STATUSES and candidate.get("finished_at"):
            return True
    return False


def runtime_effect_recovery_decision(effect, old_status):
    event_id = effect.get("event_id")
    event_ref = "the selected event" if event_id is None else f"event #{event_id}"
    if old_status in PRECOMMIT_RUNTIME_STATUSES:
        return {
            "action": "rerun_event",
            "effect_classification": "no_action_committed",
            "safety": "safe_to_replan",
            "reason": f"{event_ref} stopped before an action reached the commit phase",
        }
    if old_status == "committing":
        write_run_ids = list(effect.get("write_run_ids") or [])
        verification_run_ids = list(effect.get("verification_run_ids") or [])
        action_types = list(effect.get("action_types") or [])
        if write_run_ids:
            return {
                "action": "review_writes",
                "effect_classification": "write_may_have_started",
                "safety": "needs_user_review",
                "reason": "runtime stopped while committing one or more write actions",
                "write_run_ids": write_run_ids,
            }
        if verification_run_ids:
            return {
                "action": "review_verification",
                "effect_classification": "verification_may_have_run",
                "safety": "needs_user_review",
                "reason": "runtime stopped while committing one or more verification actions",
                "verification_run_ids": verification_run_ids,
            }
        if action_types:
            return {
                "action": "review_actions",
                "effect_classification": "action_may_have_committed",
                "safety": "needs_user_review",
                "reason": "runtime stopped during commit after selecting side-effecting actions",
                "action_types": action_types,
            }
        return {
            "action": "review_unknown_commit",
            "effect_classification": "unknown_commit_state",
            "safety": "needs_user_review",
            "reason": "runtime stopped during commit without enough recorded action detail",
        }
    return {
        "action": "inspect_effect",
        "effect_classification": "unknown",
        "safety": "needs_user_review",
        "reason": f"runtime stopped in unexpected effect status {old_status!r}",
    }


def runtime_effect_recovery_hint(effect, old_status):
    decision = runtime_effect_recovery_decision(effect, old_status)
    event_id = effect.get("event_id")
    event_ref = "the selected event" if event_id is None else f"event #{event_id}"
    if decision.get("action") == "rerun_event":
        return f"Re-run {event_ref}; no action was recorded as committed."
    if old_status == "committing":
        actions = ", ".join(effect.get("action_types") or []) or "unknown actions"
        classification = decision.get("effect_classification") or "unknown"
        return (
            f"Inspect effect #{effect.get('id')} before retrying; it stopped while committing "
            f"{actions} ({classification})."
        )
    return f"Inspect effect #{effect.get('id')} before retrying {event_ref}."


def runtime_effect_recovery_followup(state, effect, decision=None, current_time=None, mutate=False):
    decision = decision or runtime_effect_recovery_decision(effect, (effect or {}).get("status"))
    action = decision.get("action")
    event_id = (effect or {}).get("event_id")
    if action == "rerun_event":
        followup = {
            "action": "requeue_event",
            "event_id": event_id,
            "effect_id": (effect or {}).get("id"),
            "command": mew_command("run", "--once"),
            "reason": decision.get("reason") or "effect stopped before commit",
        }
        event = _find_event(state, event_id)
        if not event:
            followup.update(
                {
                    "status": "blocked_missing_event",
                    "reason": f"event #{event_id} is no longer in the inbox",
                }
            )
            return followup
        if _has_later_terminal_effect(state, effect):
            followup.update(
                {
                    "status": "blocked_later_effect",
                    "reason": f"event #{event_id} already has a later terminal runtime effect",
                }
            )
            return followup
        if event.get("processed_at") is None:
            followup["status"] = "already_pending"
            return followup
        if mutate:
            event["processed_at"] = None
            event["requeued_at"] = current_time or now_iso()
            event["requeued_from_effect_id"] = (effect or {}).get("id")
            followup["status"] = "requeued"
            followup["requeued_at"] = event["requeued_at"]
        else:
            followup["status"] = "would_requeue"
        return followup
    if decision.get("safety") == "needs_user_review":
        command = mew_command("runtime-effects", "--limit", "5")
        if action == "review_writes":
            command = mew_command("writes")
        followup = {
            "action": "ask_user_review",
            "status": "needs_user_review",
            "event_id": event_id,
            "effect_id": (effect or {}).get("id"),
            "command": command,
            "reason": decision.get("reason") or "effect stopped during commit",
        }
        if mutate:
            event_ref = "unknown event" if event_id is None else f"event #{event_id}"
            actions = ", ".join((effect or {}).get("action_types") or []) or "unknown actions"
            text = (
                f"Runtime effect #{(effect or {}).get('id')} for {event_ref} stopped while committing "
                f"{actions}. Recovery needs review before retry. Inspect with `{command}`. "
                "Reply with the observed state and whether mew should retry, abort, or replan."
            )
            question, created = add_question(
                state,
                text,
                event_id=event_id,
                related_task_id=(effect or {}).get("task_id"),
                source="runtime",
            )
            followup["question_id"] = question.get("id")
            followup["question_created"] = created
        return followup
    return {
        "action": "inspect_effect",
        "status": "needs_user_review",
        "event_id": event_id,
        "effect_id": (effect or {}).get("id"),
        "command": mew_command("runtime-effects", "--limit", "5"),
        "reason": decision.get("reason") or "effect recovery needs inspection",
    }


def repair_incomplete_runtime_effects(state, current_time=None):
    current_time = current_time or now_iso()
    repairs = []
    for effect in incomplete_runtime_effects(state):
        old_status = effect.get("status")
        recovery_decision = runtime_effect_recovery_decision(effect, old_status)
        recovery_hint = runtime_effect_recovery_hint(effect, old_status)
        recovery_followup = runtime_effect_recovery_followup(
            state,
            effect,
            recovery_decision,
            current_time=current_time,
            mutate=True,
        )
        update_runtime_effect(
            state,
            effect.get("id"),
            current_time=current_time,
            status="interrupted",
            error="Runtime stopped before this effect reached a terminal state.",
            recovery_decision=recovery_decision,
            recovery_followup=recovery_followup,
            recovery_hint=recovery_hint,
            finished_at=current_time,
        )
        repairs.append(
            {
                "type": "interrupted_runtime_effect",
                "effect_id": effect.get("id"),
                "event_id": effect.get("event_id"),
                "old_status": old_status,
                "new_status": "interrupted",
                "recovery_decision": recovery_decision,
                "recovery_followup": recovery_followup,
                "recovery_hint": recovery_hint,
            }
        )
    return repairs
