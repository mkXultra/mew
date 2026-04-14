MAX_THOUGHT_JOURNAL_ENTRIES = 100
MAX_THOUGHT_TEXT_CHARS = 700
MAX_THOUGHT_THREADS = 8
MAX_THOUGHT_ITEMS = 12


def clip_thought_text(value, limit=MAX_THOUGHT_TEXT_CHARS):
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 24].rstrip() + "\n... thought truncated ..."


def normalize_thread_list(value, limit=MAX_THOUGHT_THREADS):
    if not isinstance(value, list):
        return []
    result = []
    seen = set()
    for item in value:
        if not isinstance(item, str):
            continue
        text = clip_thought_text(item, 500)
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
        if len(result) >= limit:
            break
    return result


def _compact_plan_item(item):
    compact = {"type": item.get("type") or "unknown"}
    for key in ("task_id", "run_id", "plan_id"):
        if item.get(key) is not None:
            compact[key] = item.get(key)
    for key in ("title", "path", "query", "question", "reason", "summary", "text"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            compact[key] = clip_thought_text(value, 220)
    return compact


def _compact_items(items, limit=MAX_THOUGHT_ITEMS):
    if not isinstance(items, list):
        return []
    return [_compact_plan_item(item) for item in items[:limit] if isinstance(item, dict)]


def infer_open_threads(state, event, decision_plan, action_plan):
    threads = []
    for action in action_plan.get("actions", []):
        action_type = action.get("type")
        if action_type in ("ask_user", "wait_for_user"):
            text = action.get("question") or action.get("text") or action.get("reason")
            if text:
                threads.append(f"Waiting for user input: {text}")
        elif action_type in ("dispatch_task", "collect_agent_result", "review_agent_run"):
            run_id = action.get("run_id")
            task_id = action.get("task_id")
            if run_id is not None:
                threads.append(f"Agent run #{run_id} needs follow-up.")
            elif task_id is not None:
                threads.append(f"Task #{task_id} has active programmer-loop work.")

    pending = state.get("agent_status", {}).get("pending_question")
    if pending:
        threads.append(f"Pending question: {pending}")

    if event.get("type") == "user_message":
        text = event.get("payload", {}).get("text")
        if text and not threads:
            threads.append(f"User request context: {text}")

    return normalize_thread_list(threads)


def merge_thread_lists(*lists):
    merged = []
    seen = set()
    for values in lists:
        for value in normalize_thread_list(values):
            if value in seen:
                continue
            seen.add(value)
            merged.append(value)
            if len(merged) >= MAX_THOUGHT_THREADS:
                return merged
    return merged


def record_thought_journal_entry(
    state,
    event,
    current_time,
    decision_plan,
    action_plan,
    counts,
    cycle_reason="",
):
    summary = (
        action_plan.get("summary")
        or decision_plan.get("summary")
        or state.get("agent_status", {}).get("last_thought")
        or ""
    )
    explicit_open_threads = merge_thread_lists(
        decision_plan.get("open_threads"),
        action_plan.get("open_threads"),
    )
    inferred_open_threads = (
        [] if explicit_open_threads else infer_open_threads(state, event, decision_plan, action_plan)
    )
    open_threads = merge_thread_lists(explicit_open_threads, inferred_open_threads)
    resolved_threads = merge_thread_lists(
        decision_plan.get("resolved_threads"),
        action_plan.get("resolved_threads"),
    )
    try:
        entry_id = int(state["next_ids"].get("thought", 1))
    except (TypeError, ValueError):
        entry_id = 1
    entry = {
        "id": entry_id,
        "event_id": event.get("id"),
        "event_type": event.get("type"),
        "cycle_reason": cycle_reason or event.get("type") or "",
        "at": current_time,
        "summary": clip_thought_text(summary),
        "decision_summary": clip_thought_text(decision_plan.get("summary")),
        "action_summary": clip_thought_text(action_plan.get("summary")),
        "agent_mode": state.get("agent_status", {}).get("mode"),
        "agent_focus": clip_thought_text(state.get("agent_status", {}).get("current_focus"), 220),
        "open_threads": open_threads,
        "resolved_threads": resolved_threads,
        "decisions": _compact_items(decision_plan.get("decisions")),
        "actions": _compact_items(action_plan.get("actions")),
        "counts": dict(counts or {}),
    }
    state["next_ids"]["thought"] = entry_id + 1
    state.setdefault("thought_journal", []).append(entry)
    del state["thought_journal"][:-MAX_THOUGHT_JOURNAL_ENTRIES]
    return entry


def recent_thoughts_for_context(state, limit=8):
    thoughts = list(state.get("thought_journal", []))[-limit:]
    return [
        {
            "id": thought.get("id"),
            "at": thought.get("at"),
            "event_id": thought.get("event_id"),
            "event_type": thought.get("event_type"),
            "cycle_reason": thought.get("cycle_reason"),
            "summary": thought.get("summary"),
            "open_threads": thought.get("open_threads", []),
            "resolved_threads": thought.get("resolved_threads", []),
            "counts": thought.get("counts", {}),
        }
        for thought in reversed(thoughts)
    ]


def format_thought_entry(thought, details=False):
    line = (
        f"#{thought.get('id')} event={thought.get('event_type')}#{thought.get('event_id')} "
        f"at={thought.get('at')} summary={thought.get('summary') or ''}"
    )
    if not details:
        return line
    lines = [line]
    if thought.get("open_threads"):
        lines.append("open_threads:")
        lines.extend(f"- {item}" for item in thought.get("open_threads", []))
    if thought.get("resolved_threads"):
        lines.append("resolved_threads:")
        lines.extend(f"- {item}" for item in thought.get("resolved_threads", []))
    if thought.get("actions"):
        lines.append("actions:")
        for action in thought.get("actions", []):
            label = action.get("type") or "unknown"
            target = action.get("task_id") or action.get("run_id") or action.get("path") or ""
            detail = action.get("reason") or action.get("summary") or action.get("title") or ""
            suffix = f" {target}" if target else ""
            lines.append(f"- {label}{suffix}: {detail}".rstrip())
    return "\n".join(lines)
