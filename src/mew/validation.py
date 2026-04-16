REQUIRED_LISTS = (
    "tasks",
    "inbox",
    "outbox",
    "questions",
    "replies",
    "agent_runs",
    "verification_runs",
    "write_runs",
    "runtime_effects",
    "work_sessions",
    "step_runs",
    "thought_journal",
)

TASK_STATUSES = {"todo", "ready", "running", "blocked", "done"}
TASK_KINDS = {"", "coding", "research", "personal", "admin", "unknown"}
AGENT_RUN_STATUSES = {"created", "dry_run", "running", "completed", "failed"}
QUESTION_STATUSES = {"open", "answered", "deferred"}
ATTENTION_STATUSES = {"open", "resolved"}
RUNTIME_EFFECT_STATUSES = {
    "planning",
    "planned",
    "precomputing",
    "precomputed",
    "committing",
    "applied",
    "verified",
    "recovered",
    "failed",
    "skipped",
    "deferred",
    "interrupted",
}
WORK_SESSION_STATUSES = {"active", "closed"}
WORK_TOOL_CALL_STATUSES = {"running", "completed", "failed", "interrupted"}
INCOMPLETE_RUNTIME_EFFECT_STATUSES = {
    "planning",
    "planned",
    "precomputing",
    "precomputed",
    "committing",
}


def issue(level, path, message):
    return {"level": level, "path": path, "message": message}


def _int_id(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _check_list(state, key, issues):
    value = state.get(key)
    if not isinstance(value, list):
        issues.append(issue("error", key, "must be a list"))
        return []
    return value


def _check_unique_ids(items, path, issues):
    seen = set()
    max_id = 0
    for index, item in enumerate(items):
        item_path = f"{path}[{index}]"
        if not isinstance(item, dict):
            issues.append(issue("error", item_path, "must be an object"))
            continue
        item_id = _int_id(item.get("id"))
        if item_id is None or item_id < 1:
            issues.append(issue("error", f"{item_path}.id", "must be a positive integer"))
            continue
        if item_id in seen:
            issues.append(issue("error", f"{item_path}.id", f"duplicate id {item_id}"))
        seen.add(item_id)
        max_id = max(max_id, item_id)
    return max_id


def _check_next_id(state, name, max_existing_id, issues):
    next_ids = state.get("next_ids")
    if not isinstance(next_ids, dict):
        return
    value = _int_id(next_ids.get(name))
    if value is None or value < 1:
        issues.append(issue("error", f"next_ids.{name}", "must be a positive integer"))
        return
    if value <= max_existing_id:
        issues.append(
            issue(
                "error",
                f"next_ids.{name}",
                f"must be greater than existing max id {max_existing_id}",
            )
        )


def _check_status(item, allowed, path, issues, level="error"):
    status = item.get("status")
    if status not in allowed:
        issues.append(issue(level, path, f"unknown status {status!r}"))

def _check_field_value(item, field, allowed, path, issues, level="error"):
    value = item.get(field)
    if value not in allowed:
        issues.append(issue(level, path, f"unknown value {value!r}"))


def _task_ids(state):
    ids = set()
    for task in state.get("tasks", []):
        if isinstance(task, dict):
            item_id = _int_id(task.get("id"))
            if item_id is not None:
                ids.add(item_id)
    return ids


def _agent_run_ids(state):
    ids = set()
    for run in state.get("agent_runs", []):
        if isinstance(run, dict):
            item_id = _int_id(run.get("id"))
            if item_id is not None:
                ids.add(item_id)
    return ids


def _verification_runs_by_id(state):
    runs = {}
    for run in state.get("verification_runs", []):
        if isinstance(run, dict):
            item_id = _int_id(run.get("id"))
            if item_id is not None:
                runs[item_id] = run
    return runs


def _write_runs_by_id(state):
    runs = {}
    for run in state.get("write_runs", []):
        if isinstance(run, dict):
            item_id = _int_id(run.get("id"))
            if item_id is not None:
                runs[item_id] = run
    return runs


def validate_state(state):
    issues = []
    if not isinstance(state, dict):
        return [issue("error", "$", "state must be an object")]

    for key in ("runtime_status", "agent_status", "user_status", "memory", "next_ids"):
        if not isinstance(state.get(key), dict):
            issues.append(issue("error", key, "must be an object"))

    attention = state.get("attention")
    if not isinstance(attention, dict):
        issues.append(issue("error", "attention", "must be an object"))
        attention_items = []
    else:
        attention_items = attention.get("items")
        if not isinstance(attention_items, list):
            issues.append(issue("error", "attention.items", "must be a list"))
            attention_items = []

    max_ids = {}
    for key in REQUIRED_LISTS:
        items = _check_list(state, key, issues)
        max_ids[key] = _check_unique_ids(items, key, issues)
    max_ids["attention"] = _check_unique_ids(attention_items, "attention.items", issues)

    next_name_by_container = {
        "tasks": "task",
        "inbox": "event",
        "outbox": "message",
        "questions": "question",
        "replies": "reply",
        "agent_runs": "agent_run",
        "verification_runs": "verification_run",
        "write_runs": "write_run",
        "runtime_effects": "runtime_effect",
        "work_sessions": "work_session",
        "step_runs": "step_run",
        "thought_journal": "thought",
        "attention": "attention",
    }
    for container, name in next_name_by_container.items():
        _check_next_id(state, name, max_ids.get(container, 0), issues)

    max_work_tool_call_id = 0
    max_work_model_turn_id = 0
    for session_index, session in enumerate(state.get("work_sessions", [])):
        if not isinstance(session, dict):
            continue
        session_path = f"work_sessions[{session_index}]"
        _check_status(session, WORK_SESSION_STATUSES, f"{session_path}.status", issues, level="warning")
        calls = session.get("tool_calls", [])
        if not isinstance(calls, list):
            issues.append(issue("error", f"{session_path}.tool_calls", "must be a list"))
            continue
        max_work_tool_call_id = max(
            max_work_tool_call_id,
            _check_unique_ids(calls, f"{session_path}.tool_calls", issues),
        )
        for call_index, call in enumerate(calls):
            if not isinstance(call, dict):
                continue
            call_path = f"{session_path}.tool_calls[{call_index}]"
            _check_status(call, WORK_TOOL_CALL_STATUSES, f"{call_path}.status", issues, level="warning")
        turns = session.get("model_turns", [])
        if not isinstance(turns, list):
            issues.append(issue("error", f"{session_path}.model_turns", "must be a list"))
            continue
        max_work_model_turn_id = max(
            max_work_model_turn_id,
            _check_unique_ids(turns, f"{session_path}.model_turns", issues),
        )
        for turn_index, turn in enumerate(turns):
            if not isinstance(turn, dict):
                continue
            turn_path = f"{session_path}.model_turns[{turn_index}]"
            _check_status(turn, WORK_TOOL_CALL_STATUSES, f"{turn_path}.status", issues, level="warning")
    _check_next_id(state, "work_tool_call", max_work_tool_call_id, issues)
    _check_next_id(state, "work_model_turn", max_work_model_turn_id, issues)

    plan_max_id = 0
    seen_plan_ids = set()
    for index, task in enumerate(state.get("tasks", [])):
        if not isinstance(task, dict):
            continue
        task_path = f"tasks[{index}]"
        _check_status(task, TASK_STATUSES, f"{task_path}.status", issues, level="warning")
        _check_field_value(task, "kind", TASK_KINDS, f"{task_path}.kind", issues, level="warning")
        title = task.get("title")
        if not isinstance(title, str) or not title.strip():
            issues.append(issue("error", f"{task_path}.title", "must be a non-empty string"))
        plans = task.get("plans", [])
        if not isinstance(plans, list):
            issues.append(issue("error", f"{task_path}.plans", "must be a list"))
            continue
        for plan_index, plan in enumerate(plans):
            plan_path = f"{task_path}.plans[{plan_index}]"
            if not isinstance(plan, dict):
                issues.append(issue("error", plan_path, "must be an object"))
                continue
            plan_id = _int_id(plan.get("id"))
            if plan_id is None or plan_id < 1:
                issues.append(issue("error", f"{plan_path}.id", "must be a positive integer"))
            elif plan_id in seen_plan_ids:
                issues.append(issue("error", f"{plan_path}.id", f"duplicate id {plan_id}"))
            else:
                seen_plan_ids.add(plan_id)
                plan_max_id = max(plan_max_id, plan_id)

    _check_next_id(state, "plan", plan_max_id, issues)

    valid_task_ids = _task_ids(state)
    valid_run_ids = _agent_run_ids(state)
    verification_runs_by_id = _verification_runs_by_id(state)
    write_runs_by_id = _write_runs_by_id(state)
    for index, run in enumerate(state.get("agent_runs", [])):
        if not isinstance(run, dict):
            continue
        run_path = f"agent_runs[{index}]"
        _check_status(run, AGENT_RUN_STATUSES, f"{run_path}.status", issues)
        task_id = _int_id(run.get("task_id"))
        if task_id is not None and valid_task_ids and task_id not in valid_task_ids:
            issues.append(issue("warning", f"{run_path}.task_id", f"references missing task {task_id}"))
        parent_run_id = _int_id(run.get("parent_run_id"))
        if parent_run_id is not None and parent_run_id not in valid_run_ids:
            issues.append(issue("warning", f"{run_path}.parent_run_id", f"references missing run {parent_run_id}"))
        review_of_run_id = _int_id(run.get("review_of_run_id"))
        if review_of_run_id is not None and review_of_run_id not in valid_run_ids:
            issues.append(issue("warning", f"{run_path}.review_of_run_id", f"references missing run {review_of_run_id}"))

    for index, run in enumerate(state.get("write_runs", [])):
        if not isinstance(run, dict):
            continue
        run_path = f"write_runs[{index}]"
        raw_verification_run_id = run.get("verification_run_id")
        verification_run_id = _int_id(raw_verification_run_id)
        if raw_verification_run_id is None:
            if run.get("written") is True and run.get("dry_run") is False:
                issues.append(
                    issue(
                        "warning",
                        f"{run_path}.verification_run_id",
                        "written non-dry-run should link a verification run",
                    )
                )
            continue
        if verification_run_id is None or verification_run_id < 1:
            issues.append(
                issue(
                    "warning",
                    f"{run_path}.verification_run_id",
                    "must be a positive integer when present",
                )
            )
            continue
        linked_verification = verification_runs_by_id.get(verification_run_id)
        if not linked_verification:
            issues.append(
                issue(
                    "warning",
                    f"{run_path}.verification_run_id",
                    f"references missing verification run {verification_run_id}",
                )
            )
            continue
        if "verification_exit_code" in run:
            write_exit_code = _int_id(run.get("verification_exit_code"))
            verification_exit_code = _int_id(linked_verification.get("exit_code"))
            if write_exit_code is None:
                issues.append(
                    issue(
                        "warning",
                        f"{run_path}.verification_exit_code",
                        "must be an integer when present",
                    )
                )
            elif verification_exit_code is not None and write_exit_code != verification_exit_code:
                issues.append(
                    issue(
                        "warning",
                        f"{run_path}.verification_exit_code",
                        f"does not match verification run {verification_run_id} exit_code {verification_exit_code}",
                    )
                )

    for index, effect in enumerate(state.get("runtime_effects", [])):
        if not isinstance(effect, dict):
            continue
        effect_path = f"runtime_effects[{index}]"
        status = effect.get("status")
        if status not in RUNTIME_EFFECT_STATUSES:
            issues.append(issue("warning", f"{effect_path}.status", f"unknown status {status!r}"))
        if status in INCOMPLETE_RUNTIME_EFFECT_STATUSES and effect.get("finished_at"):
            issues.append(
                issue(
                    "warning",
                    f"{effect_path}.finished_at",
                    f"incomplete status {status!r} should not be finished",
                )
            )
        if (
            status in RUNTIME_EFFECT_STATUSES - INCOMPLETE_RUNTIME_EFFECT_STATUSES
            and not effect.get("finished_at")
        ):
            issues.append(
                issue(
                    "warning",
                    f"{effect_path}.finished_at",
                    f"terminal status {status!r} should have finished_at",
                )
            )
        for link_index, verification_run_id in enumerate(effect.get("verification_run_ids") or []):
            item_id = _int_id(verification_run_id)
            if item_id is None or item_id not in verification_runs_by_id:
                issues.append(
                    issue(
                        "warning",
                        f"{effect_path}.verification_run_ids[{link_index}]",
                        f"references missing verification run {verification_run_id}",
                    )
                )
        for link_index, write_run_id in enumerate(effect.get("write_run_ids") or []):
            item_id = _int_id(write_run_id)
            if item_id is None or item_id not in write_runs_by_id:
                issues.append(
                    issue(
                        "warning",
                        f"{effect_path}.write_run_ids[{link_index}]",
                        f"references missing write run {write_run_id}",
                    )
                )

    for index, question in enumerate(state.get("questions", [])):
        if isinstance(question, dict):
            _check_status(question, QUESTION_STATUSES, f"questions[{index}].status", issues)

    for index, item in enumerate(attention_items):
        if isinstance(item, dict):
            _check_status(item, ATTENTION_STATUSES, f"attention.items[{index}].status", issues)

    return issues


def validation_errors(issues):
    return [item for item in issues if item.get("level") == "error"]


def format_validation_issues(issues):
    if not issues:
        return "state_validation: ok"
    lines = ["state_validation:"]
    for item in issues:
        lines.append(f"- {item.get('level')} {item.get('path')}: {item.get('message')}")
    return "\n".join(lines)
