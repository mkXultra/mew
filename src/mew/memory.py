from .timeutil import now_iso


def compact_memory(state, keep_recent=5, dry_run=False):
    keep_recent = max(0, int(keep_recent))
    memory = state.setdefault("memory", {})
    shallow = memory.setdefault("shallow", {})
    deep = memory.setdefault("deep", {})
    project = deep.setdefault("project", [])
    recent = list(shallow.get("recent_events", []))
    current_context = shallow.get("current_context") or shallow.get("latest_task_summary") or ""
    compacted = recent[:-keep_recent] if keep_recent else recent
    retained = recent[-keep_recent:] if keep_recent else []
    current_time = now_iso()

    if compacted:
        event_lines = []
        for event in compacted[-20:]:
            event_lines.append(
                f"- {event.get('at')} {event.get('event_type')}#{event.get('event_id')}: {event.get('summary')}"
            )
        event_text = "\n".join(event_lines)
    else:
        event_text = "- none"

    note = (
        f"{current_time}: Memory compact\n"
        f"Current context: {current_context or '(empty)'}\n"
        f"Compacted recent events: {len(compacted)}\n"
        f"Retained recent events: {len(retained)}\n"
        f"Recent event tail:\n{event_text}"
    )

    if not dry_run:
        project.append(note)
        del project[:-100]
        shallow["recent_events"] = retained
        shallow["current_context"] = current_context or "Memory compacted."
        shallow["latest_task_summary"] = shallow.get("latest_task_summary") or shallow["current_context"]

    return note
