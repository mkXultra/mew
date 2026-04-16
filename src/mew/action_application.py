from .tasks import task_by_id, task_kind, task_question


LOW_INTENT_USER_INPUT_MARKERS = (
    "dogfood",
    "no-op",
    "noop",
    "no op",
    "stopped-runtime hint",
    "runtime focus",
    "smoke test",
    "test message",
)

RESEARCH_ROUTING_QUESTION_MARKERS = (
    "ready research work",
    "research criteria",
    "what should i execute",
    "has no command",
    "no command or agent backend",
    "assign it to an agent",
    "add execution details",
)


def new_action_counts():
    return {"actions": 0, "messages": 0, "executed": 0, "waits": 0}


def should_skip_outbox_send(state, message_type, text, event_id):
    for message in state.get("outbox", []):
        if message.get("type") != message_type or message.get("text") != text:
            continue
        if event_id is not None and message.get("event_id") == event_id:
            return True
        if message_type == "warning" and not message.get("read_at"):
            return True
    return False


def action_targets_done_task(state, action):
    if action.get("type") not in ("ask_user", "wait_for_user"):
        return False
    task_id = action.get("task_id")
    if task_id is None:
        return False
    task = task_by_id(state, task_id)
    return bool(task and task.get("status") == "done")


def normalize_wait_text(text):
    return " ".join(str(text or "").casefold().split())


def action_wait_text(action):
    return action.get("question") or action.get("text") or action.get("reason") or ""


def action_wait_text_candidates(action, fallback_question=""):
    candidates = [
        action.get("question"),
        action.get("text"),
        fallback_question,
        action.get("reason"),
    ]
    return [candidate for candidate in candidates if candidate]


def event_is_low_intent_wait_context(event):
    if not isinstance(event, dict):
        return False
    if event.get("type") == "passive_tick" and event.get("source") in (
        "manual_step",
        "manual_step_planning",
    ):
        return True
    if event.get("type") != "user_message":
        return False
    payload = event.get("payload") or {}
    text = normalize_wait_text(payload.get("text"))
    if not text:
        return True
    return any(marker in text for marker in LOW_INTENT_USER_INPUT_MARKERS)


def action_is_ready_research_routing_question(state, action, text=None):
    if action.get("type") not in ("ask_user", "wait_for_user"):
        return False
    task = task_by_id(state, action.get("task_id"))
    if not task or task.get("status") != "ready":
        return False
    if task.get("command") or task.get("agent_backend"):
        return False
    if task_kind(task) != "research":
        return False

    question_text = action_wait_text(action) if text is None else text
    normalized = normalize_wait_text(question_text)
    if not normalized:
        return False
    if normalized == normalize_wait_text(task_question(task)):
        return True
    return any(marker in normalized for marker in RESEARCH_ROUTING_QUESTION_MARKERS)


def should_skip_low_intent_task_wait_action(state, event, action, text=None):
    return event_is_low_intent_wait_context(event) and action_is_ready_research_routing_question(
        state,
        action,
        text=text,
    )


def suppress_done_task_wait_actions(state, action_plan):
    actions = action_plan.get("actions", [])
    filtered = [action for action in actions if not action_targets_done_task(state, action)]
    if len(filtered) == len(actions):
        return action_plan
    sanitized = dict(action_plan)
    sanitized["actions"] = filtered
    return sanitized


def suppress_low_intent_task_wait_actions(state, event, action_plan, fallback_question=""):
    actions = action_plan.get("actions", [])
    filtered = [
        action
        for action in actions
        if not any(
            should_skip_low_intent_task_wait_action(
                state,
                event,
                action,
                text=candidate,
            )
            for candidate in action_wait_text_candidates(action, fallback_question)
        )
    ]
    if len(filtered) == len(actions):
        return action_plan
    sanitized = dict(action_plan)
    skipped = list(action_plan.get("skipped_actions") or [])
    skipped.extend(
        {**action, "skip_reason": "low_intent_research_task_routing"}
        for action in actions
        if action not in filtered
    )
    sanitized["actions"] = filtered or [
        {
            "type": "record_memory",
            "summary": (
                "Skipped a generic ready-research task routing question because this "
                "event was a low-intent check rather than a user request."
            ),
        }
    ]
    sanitized["skipped_actions"] = skipped
    return sanitized


def public_action_plan(action_plan):
    if not isinstance(action_plan, dict):
        return action_plan
    clean = dict(action_plan)
    clean["actions"] = [
        {key: value for key, value in action.items() if not str(key).startswith("_")}
        for action in action_plan.get("actions", [])
    ]
    return clean
