DECISION_TYPES = {
    "remember",
    "send_message",
    "ask_user",
    "wait_for_user",
    "execute_task",
    "complete_task",
    "run_verification",
    "update_memory",
    "inspect_dir",
    "read_file",
    "read_image",
    "search_text",
    "write_file",
    "edit_file",
    "self_review",
    "propose_task",
    "refine_task",
    "plan_task",
    "start_work_session",
    "dispatch_task",
    "collect_agent_result",
    "review_agent_run",
    "followup_review",
}

ACTION_TYPES = (DECISION_TYPES - {"remember"}) | {"record_memory"}

PLAN_REQUIRED_FIELDS = {
    "send_message": ("text",),
    "ask_user": ("question",),
    "execute_task": ("task_id",),
    "complete_task": ("task_id",),
    "inspect_dir": ("path",),
    "read_file": ("path",),
    "read_image": ("path",),
    "search_text": ("query",),
    "write_file": ("path", "content"),
    "edit_file": ("path",),
    "propose_task": ("title",),
    "refine_task": ("task_id",),
    "plan_task": ("task_id",),
    "start_work_session": ("task_id",),
    "dispatch_task": ("task_id",),
    "collect_agent_result": ("run_id",),
    "review_agent_run": ("run_id",),
    "followup_review": ("run_id",),
}


def plan_schema_issue(level, path, message):
    return {"level": level, "path": path, "message": message}


def _item_has_value(item, field):
    value = item.get(field)
    if isinstance(value, str):
        return bool(value.strip())
    return value is not None


def validate_plan_items(items, allowed_types, item_name):
    issues = []
    if items is None:
        return issues
    if not isinstance(items, list):
        return [plan_schema_issue("warning", item_name, "must be a list")]
    for index, item in enumerate(items):
        path = f"{item_name}[{index}]"
        if not isinstance(item, dict):
            issues.append(plan_schema_issue("warning", path, "must be an object"))
            continue
        item_type = item.get("type")
        if item_type not in allowed_types:
            issues.append(plan_schema_issue("warning", f"{path}.type", f"unsupported type {item_type!r}"))
            continue
        for field in PLAN_REQUIRED_FIELDS.get(item_type, ()):
            if not _item_has_value(item, field):
                issues.append(plan_schema_issue("error", f"{path}.{field}", "required for this type"))
    return issues
