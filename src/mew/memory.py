from .timeutil import now_iso
from .typed_memory import FileMemoryBackend, entry_to_dict, normalize_memory_type, normalize_scope


def add_deep_memory(state, category, text, current_time=None, limit=100):
    category = category if category in ("preferences", "project", "decisions") else "project"
    text = str(text or "").strip()
    if not text:
        return ""
    current_time = current_time or now_iso()
    entry = f"{current_time}: {text}"
    deep = state.setdefault("memory", {}).setdefault("deep", {})
    items = deep.setdefault(category, [])
    items.append(entry)
    del items[:-max(1, int(limit or 100))]
    return entry


def _matches_query(text, query):
    haystack = str(text or "").casefold()
    needle = str(query or "").strip().casefold()
    if not needle:
        return False
    if needle in haystack:
        return True
    terms = [term for term in needle.split() if term]
    return bool(terms) and all(term in haystack for term in terms)


def _snapshot_search_items(value, key="project_snapshot", source_path=None):
    if isinstance(value, dict):
        current_source_path = value.get("path") if isinstance(value.get("path"), str) else source_path
        for child_key, child in value.items():
            yield from _snapshot_search_items(child, f"{key}.{child_key}", current_source_path)
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            yield from _snapshot_search_items(child, f"{key}[{index}]", source_path)
        return
    if value is None:
        return
    text = str(value)
    if text:
        yield key, text, source_path


def search_memory(state, query, limit=20):
    limit = max(0, int(limit or 0))
    if limit <= 0:
        return []
    memory = state.get("memory", {})
    shallow = memory.get("shallow", {})
    deep = memory.get("deep", {})
    results = []

    def add_match(scope, key, text, match_text=None, **extra):
        if not _matches_query(text if match_text is None else match_text, query):
            return
        item = {
            "scope": scope,
            "key": key,
            "text": str(text or ""),
        }
        item.update(extra)
        results.append(item)

    add_match("shallow", "current_context", shallow.get("current_context") or "")
    add_match("shallow", "latest_task_summary", shallow.get("latest_task_summary") or "")
    for event in shallow.get("recent_events", []):
        add_match(
            "shallow",
            "recent_events",
            event.get("summary") or "",
            at=event.get("at"),
            event_id=event.get("event_id"),
            event_type=event.get("event_type"),
        )

    for key in ("preferences", "project", "decisions"):
        for index, text in enumerate(deep.get(key, [])):
            add_match("deep", key, text, index=index)

    snapshot = deep.get("project_snapshot")
    if snapshot:
        for key, text, source_path in _snapshot_search_items(snapshot):
            extra = {}
            if source_path:
                extra["source_path"] = source_path
            add_match("deep", key, text, match_text=f"{key} {text}", **extra)

    return results[-limit:]


def recall_memory(
    state,
    query,
    *,
    limit=20,
    scope=None,
    memory_type=None,
    base_dir=".",
):
    limit = max(0, int(limit or 0))
    if limit <= 0:
        return []
    scope = normalize_scope(scope) if scope else None
    memory_type = normalize_memory_type(memory_type) if memory_type else None
    results = []
    if (scope in (None, "private")) and (memory_type in (None, "unknown")):
        for item in search_memory(state, query, limit=limit):
            legacy = dict(item)
            legacy.setdefault("storage", "state")
            legacy.setdefault("memory_scope", "private")
            legacy.setdefault("memory_type", "unknown")
            legacy.setdefault("type", "unknown")
            results.append(legacy)
    remaining = max(0, limit - len(results))
    if remaining:
        backend = FileMemoryBackend(base_dir)
        for entry in backend.recall(query, scope=scope, memory_type=memory_type, limit=remaining):
            results.append(entry_to_dict(entry))
    return results[:limit]


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
