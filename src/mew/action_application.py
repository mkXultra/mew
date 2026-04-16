from .tasks import task_by_id


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


def suppress_done_task_wait_actions(state, action_plan):
    actions = action_plan.get("actions", [])
    filtered = [action for action in actions if not action_targets_done_task(state, action)]
    if len(filtered) == len(actions):
        return action_plan
    sanitized = dict(action_plan)
    sanitized["actions"] = filtered
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
