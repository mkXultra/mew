from .state import incomplete_runtime_effects, update_runtime_effect
from .timeutil import now_iso


PRECOMMIT_RUNTIME_STATUSES = {"planning", "planned", "precomputing", "precomputed"}


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


def repair_incomplete_runtime_effects(state, current_time=None):
    current_time = current_time or now_iso()
    repairs = []
    for effect in incomplete_runtime_effects(state):
        old_status = effect.get("status")
        recovery_decision = runtime_effect_recovery_decision(effect, old_status)
        recovery_hint = runtime_effect_recovery_hint(effect, old_status)
        update_runtime_effect(
            state,
            effect.get("id"),
            current_time=current_time,
            status="interrupted",
            error="Runtime stopped before this effect reached a terminal state.",
            recovery_decision=recovery_decision,
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
                "recovery_hint": recovery_hint,
            }
        )
    return repairs
