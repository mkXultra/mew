from .timeutil import elapsed_hours, now_iso


QUESTION_ACTIVITY_FIELDS = ("updated_at", "reopened_at", "acknowledged_at", "created_at")


def question_activity_at(question):
    if not isinstance(question, dict):
        return None
    for field in QUESTION_ACTIVITY_FIELDS:
        value = question.get(field)
        if value:
            return value
    return None


def question_waiting_hours(question, current_time=None):
    current_time = current_time or now_iso()
    return elapsed_hours(question_activity_at(question), current_time)


def format_waiting_hours(hours, minimum_hours=1.0):
    if hours is None or hours < minimum_hours:
        return ""
    if hours < 24:
        return f"{hours:.1f}h"
    return f"{hours / 24.0:.1f}d"


def question_view_metadata(question, current_time=None):
    hours = question_waiting_hours(question, current_time=current_time)
    waiting_for = format_waiting_hours(hours)
    return {
        "activity_at": question_activity_at(question),
        "waiting_hours": round(hours, 2) if hours is not None else None,
        "waiting_for": waiting_for,
    }


def _clip_reason(reason, limit=100):
    text = " ".join(str(reason or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "..."


def format_question_context(question, current_time=None, include_defer_reason=True):
    metadata = question_view_metadata(question, current_time=current_time)
    parts = []
    if question.get("status") == "open" and metadata.get("waiting_for"):
        parts.append(f"waiting={metadata['waiting_for']}")
    if include_defer_reason and question.get("status") == "deferred" and question.get("defer_reason"):
        parts.append(f"defer_reason={_clip_reason(question.get('defer_reason'))}")
    if not parts:
        return ""
    return f" ({'; '.join(parts)})"
