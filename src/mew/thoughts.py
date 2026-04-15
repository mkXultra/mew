import re


MAX_THOUGHT_JOURNAL_ENTRIES = 100
MAX_THOUGHT_TEXT_CHARS = 700
MAX_THOUGHT_THREADS = 8
MAX_THOUGHT_ITEMS = 12
DROPPED_THREAD_WARNING_THRESHOLD = 0.5

QUESTION_REF_RE = re.compile(r"\bQuestion #(\d+)\b", re.IGNORECASE)
TASK_REF_RE = re.compile(r"\bTask #(\d+)\b", re.IGNORECASE)
AGENT_RUN_REF_RE = re.compile(r"\bAgent run #(\d+)\b", re.IGNORECASE)


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


def compact_thread_key(state, thread):
    text = str(thread or "").strip()
    lowered = text.casefold()
    if not text:
        return ""

    question_match = QUESTION_REF_RE.search(text)
    task_match = TASK_REF_RE.search(text)
    if "waiting for user" in lowered or "pending question" in lowered:
        if question_match:
            task_id = task_id_for_question(state, question_match.group(1))
            if task_id is not None:
                return f"waiting:task:{task_id}"
            return f"waiting:question:{question_match.group(1)}"
        if task_match:
            return f"waiting:task:{task_match.group(1)}"

    run_match = AGENT_RUN_REF_RE.search(text)
    if run_match:
        return f"agent_run:{run_match.group(1)}"
    if "programmer-loop" in lowered and task_match:
        return f"programmer_task:{task_match.group(1)}"

    return "text:" + " ".join(text.split()).casefold()


def task_id_for_question(state, question_id):
    for question in state.get("questions", []):
        if str(question.get("id")) != str(question_id):
            continue
        task_id = question.get("related_task_id")
        return str(task_id) if task_id is not None else None
    return None


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
                task_id = action.get("task_id")
                if task_id is not None:
                    threads.append(f"Waiting for user input on task #{task_id}: {text}")
                else:
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
        active_task_id = state.get("agent_status", {}).get("active_task_id")
        if active_task_id is not None:
            threads.append(f"Pending question for task #{active_task_id}: {pending}")
        else:
            threads.append(f"Pending question: {pending}")

    if event.get("type") == "user_message":
        text = event.get("payload", {}).get("text")
        if text and not threads:
            threads.append(f"User request context: {text}")

    return normalize_thread_list(threads)


def merge_thread_lists(*lists, state=None):
    merged = []
    seen = set()
    for values in lists:
        for value in normalize_thread_list(values):
            key = compact_thread_key(state or {}, value)
            if key in seen:
                continue
            seen.add(key)
            merged.append(value)
            if len(merged) >= MAX_THOUGHT_THREADS:
                return merged
    return merged


def previous_unresolved_threads(state, resolved_threads):
    thoughts = state.get("thought_journal", [])
    if not thoughts:
        return []
    previous_open = merge_thread_lists(
        thoughts[-1].get("open_threads"),
        thoughts[-1].get("dropped_threads"),
        state=state,
    )
    if not previous_open:
        return []
    resolved_keys = {
        compact_thread_key(state, thread)
        for thread in normalize_thread_list(resolved_threads)
    }
    return [
        thread
        for thread in previous_open
        if compact_thread_key(state, thread) not in resolved_keys
    ]


def remove_resolved_threads(state, open_threads, resolved_threads):
    resolved_keys = {
        compact_thread_key(state, thread)
        for thread in normalize_thread_list(resolved_threads)
    }
    if not resolved_keys:
        return open_threads
    return [
        thread
        for thread in normalize_thread_list(open_threads)
        if compact_thread_key(state, thread) not in resolved_keys
    ]


def dropped_threads_from_previous(state, open_threads, resolved_threads):
    thoughts = state.get("thought_journal", [])
    if not thoughts:
        return [], 0.0
    previous_open = merge_thread_lists(
        thoughts[-1].get("open_threads"),
        thoughts[-1].get("dropped_threads"),
        state=state,
    )
    if not previous_open:
        return [], 0.0
    handled = {
        compact_thread_key(state, thread)
        for thread in merge_thread_lists(open_threads, resolved_threads, state=state)
    }
    dropped = [
        thread
        for thread in previous_open
        if compact_thread_key(state, thread) not in handled
    ]
    ratio = len(dropped) / len(previous_open)
    return dropped, ratio


def dropped_thread_warning_for_context(state):
    thoughts = state.get("thought_journal", [])
    if not thoughts:
        return None
    latest = thoughts[-1]
    dropped = normalize_thread_list(latest.get("dropped_threads"))
    try:
        ratio = float(latest.get("dropped_thread_ratio") or 0.0)
    except (TypeError, ValueError):
        ratio = 0.0
    if not dropped or ratio < DROPPED_THREAD_WARNING_THRESHOLD:
        return None
    return {
        "thought_id": latest.get("id"),
        "dropped_thread_ratio": ratio,
        "dropped_threads": dropped,
        "message": "Previous open thought threads were dropped without being carried forward or resolved.",
    }


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
        state=state,
    )
    inferred_open_threads = (
        [] if explicit_open_threads else infer_open_threads(state, event, decision_plan, action_plan)
    )
    open_threads = merge_thread_lists(explicit_open_threads, inferred_open_threads, state=state)
    resolved_threads = merge_thread_lists(
        decision_plan.get("resolved_threads"),
        action_plan.get("resolved_threads"),
        state=state,
    )
    open_threads = remove_resolved_threads(state, open_threads, resolved_threads)
    if event.get("type") == "user_message":
        open_threads = merge_thread_lists(
            open_threads,
            previous_unresolved_threads(state, resolved_threads),
            state=state,
        )
    dropped_threads, dropped_thread_ratio = dropped_threads_from_previous(
        state,
        open_threads,
        resolved_threads,
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
        "dropped_threads": dropped_threads,
        "dropped_thread_ratio": dropped_thread_ratio,
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
            "dropped_threads": thought.get("dropped_threads", []),
            "dropped_thread_ratio": thought.get("dropped_thread_ratio", 0.0),
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
    if thought.get("dropped_threads"):
        ratio = thought.get("dropped_thread_ratio") or 0.0
        lines.append(f"dropped_threads: ratio={ratio:.2f}")
        lines.extend(f"- {item}" for item in thought.get("dropped_threads", []))
    if thought.get("actions"):
        lines.append("actions:")
        for action in thought.get("actions", []):
            label = action.get("type") or "unknown"
            target = action.get("task_id") or action.get("run_id") or action.get("path") or ""
            detail = action.get("reason") or action.get("summary") or action.get("title") or ""
            suffix = f" {target}" if target else ""
            lines.append(f"- {label}{suffix}: {detail}".rstrip())
    return "\n".join(lines)
