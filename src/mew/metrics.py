from .tasks import find_task, task_kind
from .timeutil import parse_time


WORK_WRITE_TOOLS = {"write_file", "edit_file"}


def _duration_seconds(started_at, finished_at):
    start = parse_time(started_at)
    end = parse_time(finished_at)
    if not start or not end:
        return None
    try:
        return max(0.0, (end - start).total_seconds())
    except TypeError:
        return None


def _round(value):
    if value is None:
        return None
    return round(float(value), 3)


def _summary(values):
    values = [float(value) for value in values if value is not None]
    if not values:
        return {"count": 0, "avg": None, "max": None}
    return {
        "count": len(values),
        "avg": _round(sum(values) / len(values)),
        "max": _round(max(values)),
    }


def _status_counts(items):
    counts = {"total": 0, "completed": 0, "failed": 0, "interrupted": 0, "running": 0}
    for item in items or []:
        if not isinstance(item, dict):
            continue
        counts["total"] += 1
        status = item.get("status")
        if status in counts:
            counts[status] += 1
    return counts


def _approval_counts(tool_calls):
    counts = {"total": 0, "pending": 0, "applied": 0, "rejected": 0, "failed": 0, "indeterminate": 0}
    for call in tool_calls or []:
        if not isinstance(call, dict) or call.get("tool") not in WORK_WRITE_TOOLS:
            continue
        result = call.get("result") or {}
        if not result.get("dry_run"):
            continue
        counts["total"] += 1
        status = call.get("approval_status") or "pending"
        if status in counts:
            counts[status] += 1
    return counts


def _verification_counts(tool_calls):
    counts = {"total": 0, "passed": 0, "failed": 0, "rolled_back": 0}
    for call in tool_calls or []:
        if not isinstance(call, dict):
            continue
        result = call.get("result") or {}
        exit_code = result.get("verification_exit_code")
        verification = result.get("verification") or {}
        if exit_code is None:
            exit_code = verification.get("exit_code")
        if exit_code is None:
            continue
        try:
            exit_code = int(exit_code)
        except (TypeError, ValueError):
            continue
        counts["total"] += 1
        if exit_code == 0:
            counts["passed"] += 1
        else:
            counts["failed"] += 1
        if result.get("rolled_back"):
            counts["rolled_back"] += 1
    return counts


def _intervals(items):
    intervals = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        start = parse_time(item.get("started_at"))
        end = parse_time(item.get("finished_at"))
        if not start or not end:
            continue
        try:
            if end < start:
                continue
        except TypeError:
            continue
        intervals.append((start, end))
    return intervals


def _union_seconds(intervals):
    if not intervals:
        return 0.0
    merged = []
    for start, end in sorted(intervals, key=lambda item: item[0]):
        if not merged or start > merged[-1][1]:
            merged.append([start, end])
            continue
        merged[-1][1] = max(merged[-1][1], end)
    return sum(max(0.0, (end - start).total_seconds()) for start, end in merged)


def _first_tool_start_seconds(session, tool_calls):
    created_at = session.get("created_at")
    starts = [call.get("started_at") for call in tool_calls if isinstance(call, dict) and call.get("started_at")]
    if not starts:
        return None
    return _duration_seconds(created_at, min(starts))


def _model_to_tool_waits(model_turns, tool_calls):
    calls_by_id = {str(call.get("id")): call for call in tool_calls if isinstance(call, dict)}
    waits = []
    for turn in model_turns or []:
        if not isinstance(turn, dict) or turn.get("tool_call_id") is None:
            continue
        call = calls_by_id.get(str(turn.get("tool_call_id")))
        if not call:
            continue
        waits.append(_duration_seconds(turn.get("finished_at"), call.get("started_at")))
    return waits


def _tool_to_next_model_waits(model_turns, tool_calls):
    turn_starts = sorted(
        parse_time(turn.get("started_at"))
        for turn in model_turns or []
        if isinstance(turn, dict) and parse_time(turn.get("started_at"))
    )
    waits = []
    for call in tool_calls or []:
        if not isinstance(call, dict):
            continue
        finished = parse_time(call.get("finished_at"))
        if not finished:
            continue
        next_start = None
        for turn_start in turn_starts:
            try:
                if turn_start >= finished:
                    next_start = turn_start
                    break
            except TypeError:
                continue
        if next_start is None:
            continue
        waits.append(max(0.0, (next_start - finished).total_seconds()))
    return waits


def _session_wall_seconds(session):
    return _duration_seconds(session.get("created_at"), session.get("updated_at"))


def _session_idle_ratio(session, model_turns, tool_calls):
    wall_seconds = _session_wall_seconds(session)
    if not wall_seconds:
        return None
    active_seconds = _union_seconds(_intervals(model_turns) + _intervals(tool_calls))
    return max(0.0, min(1.0, (wall_seconds - active_seconds) / wall_seconds))


def _merge_counts(target, source):
    for key, value in (source or {}).items():
        target[key] = target.get(key, 0) + int(value or 0)


def _session_matches_kind(state, session, kind):
    if not kind:
        return True
    task = find_task(state, session.get("task_id"))
    return bool(task) and task_kind(task) == kind


def build_observation_metrics(state, *, kind=None, limit=None):
    sessions = [
        session
        for session in state.get("work_sessions", []) or []
        if isinstance(session, dict) and _session_matches_kind(state, session, kind)
    ]
    sessions.sort(key=lambda item: item.get("updated_at") or item.get("created_at") or "", reverse=True)
    if limit is not None:
        sessions = sessions[: max(0, int(limit))]

    session_counts = {"total": len(sessions), "active": 0, "closed": 0, "stale_active": 0, "awaiting_approval": 0}
    tool_counts = {"total": 0, "completed": 0, "failed": 0, "interrupted": 0, "running": 0}
    turn_counts = {"total": 0, "completed": 0, "failed": 0, "interrupted": 0, "running": 0}
    approval_counts = {"total": 0, "pending": 0, "applied": 0, "rejected": 0, "failed": 0, "indeterminate": 0}
    verification_counts = {"total": 0, "passed": 0, "failed": 0, "rolled_back": 0}
    first_tool_starts = []
    model_to_tool_waits = []
    tool_to_next_model_waits = []
    idle_ratios = []

    for session in sessions:
        status = session.get("status")
        task = find_task(state, session.get("task_id"))
        stale_active = status == "active" and task and task.get("status") == "done"
        if stale_active:
            session_counts["stale_active"] += 1
        elif status in session_counts:
            session_counts[status] += 1
        if status == "active" and not stale_active and any(
            (call.get("approval_status") or "pending") == "pending"
            for call in session.get("tool_calls") or []
            if isinstance(call, dict) and call.get("tool") in WORK_WRITE_TOOLS and (call.get("result") or {}).get("dry_run")
        ):
            session_counts["awaiting_approval"] += 1
        tool_calls = [call for call in session.get("tool_calls") or [] if isinstance(call, dict)]
        model_turns = [turn for turn in session.get("model_turns") or [] if isinstance(turn, dict)]
        _merge_counts(tool_counts, _status_counts(tool_calls))
        _merge_counts(turn_counts, _status_counts(model_turns))
        _merge_counts(approval_counts, _approval_counts(tool_calls))
        _merge_counts(verification_counts, _verification_counts(tool_calls))
        first_tool_starts.append(_first_tool_start_seconds(session, tool_calls))
        model_to_tool_waits.extend(_model_to_tool_waits(model_turns, tool_calls))
        tool_to_next_model_waits.extend(_tool_to_next_model_waits(model_turns, tool_calls))
        idle_ratios.append(_session_idle_ratio(session, model_turns, tool_calls))

    intervention_count = (
        tool_counts["failed"]
        + tool_counts["interrupted"]
        + turn_counts["failed"]
        + turn_counts["interrupted"]
        + approval_counts["rejected"]
        + approval_counts["failed"]
        + verification_counts["failed"]
        + verification_counts["rolled_back"]
    )
    completed_sessions = session_counts["closed"] or 0
    completion_ratio = (completed_sessions / session_counts["total"]) if session_counts["total"] else None

    return {
        "kind": kind or "all",
        "session_limit": limit,
        "sessions": session_counts,
        "reliability": {
            "completion_ratio": _round(completion_ratio),
            "interventions": intervention_count,
            "tool_calls": tool_counts,
            "model_turns": turn_counts,
            "approvals": approval_counts,
            "verification": verification_counts,
        },
        "latency": {
            "first_tool_start_seconds": _summary(first_tool_starts),
            "model_to_tool_wait_seconds": _summary(model_to_tool_waits),
            "tool_to_next_model_wait_seconds": _summary(tool_to_next_model_waits),
            "perceived_idle_ratio": _summary(idle_ratios),
        },
    }


def format_observation_metrics(data):
    sessions = data.get("sessions") or {}
    reliability = data.get("reliability") or {}
    latency = data.get("latency") or {}
    lines = [
        "Mew observation metrics",
        f"scope: kind={data.get('kind') or 'all'} session_limit={data.get('session_limit')}",
        (
            "sessions: "
            f"total={sessions.get('total', 0)} active={sessions.get('active', 0)} "
            f"closed={sessions.get('closed', 0)} stale_active={sessions.get('stale_active', 0)} "
            f"awaiting_approval={sessions.get('awaiting_approval', 0)}"
        ),
        (
            "reliability: "
            f"completion_ratio={reliability.get('completion_ratio')} "
            f"interventions={reliability.get('interventions', 0)}"
        ),
    ]
    for label, key in (
        ("tool_calls", "tool_calls"),
        ("model_turns", "model_turns"),
        ("approvals", "approvals"),
        ("verification", "verification"),
    ):
        counts = reliability.get(key) or {}
        lines.append(
            f"{label}: "
            + " ".join(f"{name}={value}" for name, value in counts.items())
        )
    for label, key in (
        ("first_tool_start_seconds", "first_tool_start_seconds"),
        ("model_to_tool_wait_seconds", "model_to_tool_wait_seconds"),
        ("tool_to_next_model_wait_seconds", "tool_to_next_model_wait_seconds"),
        ("perceived_idle_ratio", "perceived_idle_ratio"),
    ):
        summary = latency.get(key) or {}
        lines.append(
            f"{label}: count={summary.get('count', 0)} avg={summary.get('avg')} max={summary.get('max')}"
        )
    return "\n".join(lines)
