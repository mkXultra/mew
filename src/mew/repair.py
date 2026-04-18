from .state import incomplete_runtime_effects, update_runtime_effect
from .timeutil import now_iso


def runtime_effect_recovery_hint(effect, old_status):
    event_id = effect.get("event_id")
    event_ref = "the selected event" if event_id is None else f"event #{event_id}"
    if old_status in ("planning", "planned", "precomputing", "precomputed"):
        return f"Re-run {event_ref}; no action was recorded as committed."
    if old_status == "committing":
        actions = ", ".join(effect.get("action_types") or []) or "unknown actions"
        return f"Inspect effect #{effect.get('id')} before retrying; it stopped while committing {actions}."
    return f"Inspect effect #{effect.get('id')} before retrying {event_ref}."


def repair_incomplete_runtime_effects(state, current_time=None):
    current_time = current_time or now_iso()
    repairs = []
    for effect in incomplete_runtime_effects(state):
        old_status = effect.get("status")
        recovery_hint = runtime_effect_recovery_hint(effect, old_status)
        update_runtime_effect(
            state,
            effect.get("id"),
            current_time=current_time,
            status="interrupted",
            error="Runtime stopped before this effect reached a terminal state.",
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
                "recovery_hint": recovery_hint,
            }
        )
    return repairs
