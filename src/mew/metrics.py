from .tasks import find_task, task_kind
from .timeutil import parse_time


WORK_WRITE_TOOLS = {"write_file", "edit_file"}
DEFAULT_SAMPLE_LIMIT = 3
SAMPLE_TEXT_MAX_CHARS = 240
SLOW_MODEL_RESUME_SECONDS = 30.0
HIGH_IDLE_RATIO = 0.8


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


def _clip_text(value, max_chars=SAMPLE_TEXT_MAX_CHARS):
    text = " ".join(str(value or "").split())
    if len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 3)].rstrip() + "..."


def _summary(values):
    values = sorted(float(value) for value in values if value is not None)
    if not values:
        return {"count": 0, "avg": None, "median": None, "p95": None, "max": None}
    return {
        "count": len(values),
        "avg": _round(sum(values) / len(values)),
        "median": _round(_percentile(values, 0.5)),
        "p95": _round(_percentile(values, 0.95)),
        "max": _round(max(values)),
    }


def _percentile(sorted_values, percentile):
    if not sorted_values:
        return None
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = (len(sorted_values) - 1) * percentile
    low = int(rank)
    high = min(low + 1, len(sorted_values) - 1)
    weight = rank - low
    return sorted_values[low] * (1.0 - weight) + sorted_values[high] * weight


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
        exit_code = _verification_exit_code(call)
        if exit_code is None:
            continue
        result = call.get("result") or {}
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
    return [record["wait_seconds"] for record in _tool_to_next_model_wait_records({}, model_turns, tool_calls)]


def _approval_decision_time(call):
    times = []
    for key in ("approved_at", "rejected_at"):
        value = parse_time(call.get(key))
        if value:
            times.append(value)
    if not times:
        return None
    return min(times)


def _approval_bound_wait_seconds(call, finished, next_start):
    result = call.get("result") or {}
    if call.get("tool") not in WORK_WRITE_TOOLS or not result.get("dry_run"):
        return 0.0
    decision_time = _approval_decision_time(call)
    boundary = next_start
    if decision_time:
        try:
            boundary = min(next_start, decision_time)
        except TypeError:
            boundary = next_start
    try:
        if boundary <= finished:
            return 0.0
        return max(0.0, (boundary - finished).total_seconds())
    except TypeError:
        return 0.0


def _tool_to_next_model_wait_records(session, model_turns, tool_calls):
    turn_starts = sorted(
        (parse_time(turn.get("started_at")), turn)
        for turn in model_turns or []
        if isinstance(turn, dict) and parse_time(turn.get("started_at"))
    )
    records = []
    for call in tool_calls or []:
        if not isinstance(call, dict):
            continue
        finished = parse_time(call.get("finished_at"))
        if not finished:
            continue
        next_turn = None
        next_start = None
        for turn_start, turn in turn_starts:
            try:
                if turn_start >= finished:
                    next_start = turn_start
                    next_turn = turn
                    break
            except TypeError:
                continue
        if next_start is None:
            continue
        wait_seconds = max(0.0, (next_start - finished).total_seconds())
        approval_bound_seconds = min(wait_seconds, _approval_bound_wait_seconds(call, finished, next_start))
        model_resume_seconds = max(0.0, wait_seconds - approval_bound_seconds)
        if approval_bound_seconds > 0 and model_resume_seconds <= 0:
            model_resume_seconds = None
        wait_context = "model_resume"
        if approval_bound_seconds > 0:
            wait_context = "approval_bound" if model_resume_seconds is None else "mixed_approval_bound"
        records.append(
            {
                "session_id": session.get("id"),
                "tool_call_id": call.get("id"),
                "tool": call.get("tool") or "",
                "approval_status": call.get("approval_status") or "",
                "path": _call_path(call),
                "wait_seconds": _round(wait_seconds),
                "model_resume_wait_seconds": _round(model_resume_seconds),
                "approval_bound_wait_seconds": _round(approval_bound_seconds) if approval_bound_seconds > 0 else None,
                "wait_context": wait_context,
                "finished_at": call.get("finished_at") or "",
                "next_model_turn_id": next_turn.get("id") if next_turn else None,
                "next_model_started_at": next_turn.get("started_at") if next_turn else "",
            }
        )
    return records


def _tool_to_next_model_wait_samples(state, session, model_turns, tool_calls):
    samples = []
    for record in _tool_to_next_model_wait_records(session, model_turns, tool_calls):
        if (record.get("model_resume_wait_seconds") or 0) <= SLOW_MODEL_RESUME_SECONDS:
            continue
        sample = {
            "session_id": session.get("id"),
            **record,
        }
        sample.update(_sample_task(state, session.get("task_id")))
        samples.append(sample)
    return samples


def _approval_bound_wait_samples(state, session, model_turns, tool_calls):
    samples = []
    for record in _tool_to_next_model_wait_records(session, model_turns, tool_calls):
        if (record.get("approval_bound_wait_seconds") or 0) <= SLOW_MODEL_RESUME_SECONDS:
            continue
        sample = {
            "session_id": session.get("id"),
            **record,
        }
        sample.update(_sample_task(state, session.get("task_id")))
        samples.append(sample)
    return samples


def _session_wall_seconds(session):
    return _duration_seconds(session.get("created_at"), session.get("updated_at"))


def _session_activity_seconds(model_turns, tool_calls):
    return _union_seconds(_intervals(model_turns) + _intervals(tool_calls))


def _session_idle_ratio(session, model_turns, tool_calls):
    wall_seconds = _session_wall_seconds(session)
    if not wall_seconds:
        return None
    active_seconds = _session_activity_seconds(model_turns, tool_calls)
    if active_seconds <= 0:
        return None
    return max(0.0, min(1.0, (wall_seconds - active_seconds) / wall_seconds))


def _high_idle_session_sample(state, session, model_turns, tool_calls):
    wall_seconds = _session_wall_seconds(session)
    if not wall_seconds:
        return None
    active_seconds = _session_activity_seconds(model_turns, tool_calls)
    if active_seconds <= 0:
        return None
    idle_ratio = max(0.0, min(1.0, (wall_seconds - active_seconds) / wall_seconds))
    if idle_ratio <= HIGH_IDLE_RATIO:
        return None
    notes = [note for note in session.get("notes") or [] if isinstance(note, dict)]
    latest_note = notes[-1] if notes else {}
    sample = {
        "session_id": session.get("id"),
        "status": session.get("status") or "",
        "idle_ratio": _round(idle_ratio),
        "wall_seconds": _round(wall_seconds),
        "active_seconds": _round(active_seconds),
        "tool_call_count": len(tool_calls or []),
        "model_turn_count": len(model_turns or []),
        "note_count": len(notes),
        "latest_note": _clip_text(latest_note.get("text")),
        "updated_at": session.get("updated_at") or "",
    }
    sample.update(_sample_task(state, session.get("task_id")))
    return sample


def _merge_counts(target, source):
    for key, value in (source or {}).items():
        target[key] = target.get(key, 0) + int(value or 0)


def _rate(part, whole):
    if not whole:
        return None
    return _round(float(part or 0) / float(whole))


def _verification_exit_code(call):
    if not isinstance(call, dict):
        return None
    result = call.get("result") or {}
    verification = result.get("verification") or {}
    exit_code = result.get("verification_exit_code")
    if exit_code is None:
        exit_code = verification.get("exit_code")
    if exit_code is None:
        return None
    try:
        return int(exit_code)
    except (TypeError, ValueError):
        return None


def _call_path(call):
    parameters = call.get("parameters") or {}
    result = call.get("result") or {}
    return parameters.get("path") or result.get("path") or ""


def _sample_task(state, task_id):
    task = find_task(state, task_id)
    if not task:
        return {"task_id": task_id, "task_title": "", "task_status": ""}
    return {"task_id": task_id, "task_title": task.get("title") or "", "task_status": task.get("status") or ""}


def _verification_sample(state, session, call):
    result = call.get("result") or {}
    verification = result.get("verification") or {}
    notes = [note for note in session.get("notes") or [] if isinstance(note, dict)]
    latest_note = notes[-1] if notes else {}
    sample = {
        "session_id": session.get("id"),
        "session_status": session.get("status") or "",
        "tool_call_id": call.get("id"),
        "tool": call.get("tool") or "",
        "path": _call_path(call),
        "exit_code": _verification_exit_code(call),
        "rolled_back": bool(result.get("rolled_back")),
        "command": verification.get("command") or result.get("verification_command") or "",
        "finished_at": verification.get("finished_at") or call.get("finished_at") or "",
        "note_count": len(notes),
        "latest_note": _clip_text(latest_note.get("text")),
    }
    sample.update(_sample_task(state, session.get("task_id")))
    stderr = _clip_text(verification.get("stderr"))
    stdout = _clip_text(verification.get("stdout"))
    if stderr:
        sample["stderr"] = stderr
    if stdout:
        sample["stdout"] = stdout
    return sample


def _approval_sample(state, session, call):
    parameters = call.get("parameters") or {}
    result = call.get("result") or {}
    sample = {
        "session_id": session.get("id"),
        "tool_call_id": call.get("id"),
        "tool": call.get("tool") or "",
        "approval_status": call.get("approval_status") or "pending",
        "path": _call_path(call),
        "summary": _clip_text(parameters.get("summary") or call.get("summary")),
        "reason": _clip_text(parameters.get("reason")),
        "diff_stats": result.get("diff_stats") or {},
        "finished_at": call.get("finished_at") or "",
    }
    sample.update(_sample_task(state, session.get("task_id")))
    return sample


def _diagnostic_samples(state, sessions, *, limit=DEFAULT_SAMPLE_LIMIT):
    limit = max(0, int(limit or 0))
    samples = {
        "verification_failures": [],
        "approval_friction": [],
        "slow_model_resumes": [],
        "approval_bound_waits": [],
        "high_idle_sessions": [],
    }
    if limit <= 0:
        return samples

    slow_model_resumes = []
    approval_bound_waits = []
    high_idle_sessions = []
    for session in sessions:
        tool_calls = [call for call in session.get("tool_calls") or [] if isinstance(call, dict)]
        model_turns = [turn for turn in session.get("model_turns") or [] if isinstance(turn, dict)]
        slow_model_resumes.extend(_tool_to_next_model_wait_samples(state, session, model_turns, tool_calls))
        approval_bound_waits.extend(_approval_bound_wait_samples(state, session, model_turns, tool_calls))
        idle_sample = _high_idle_session_sample(state, session, model_turns, tool_calls)
        if idle_sample:
            high_idle_sessions.append(idle_sample)
        for call in sorted(
            tool_calls,
            key=lambda item: item.get("finished_at") or item.get("started_at") or "",
            reverse=True,
        ):
            if len(samples["verification_failures"]) < limit and _verification_exit_code(call) not in (None, 0):
                samples["verification_failures"].append(_verification_sample(state, session, call))
            result = call.get("result") or {}
            approval_status = call.get("approval_status") or "pending"
            if (
                len(samples["approval_friction"]) < limit
                and call.get("tool") in WORK_WRITE_TOOLS
                and result.get("dry_run")
                and approval_status in ("rejected", "failed")
            ):
                samples["approval_friction"].append(_approval_sample(state, session, call))
    samples["slow_model_resumes"] = sorted(
        slow_model_resumes,
        key=lambda item: item.get("model_resume_wait_seconds") or 0,
        reverse=True,
    )[:limit]
    samples["approval_bound_waits"] = sorted(
        approval_bound_waits,
        key=lambda item: item.get("approval_bound_wait_seconds") or 0,
        reverse=True,
    )[:limit]
    samples["high_idle_sessions"] = sorted(
        high_idle_sessions,
        key=lambda item: item.get("idle_ratio") or 0,
        reverse=True,
    )[:limit]
    return samples


def _add_signal(signals, signal_id, severity, message, *, value=None, threshold=None):
    signal = {
        "id": signal_id,
        "severity": severity,
        "message": message,
    }
    if value is not None:
        signal["value"] = value
    if threshold is not None:
        signal["threshold"] = threshold
    signals.append(signal)


def _build_signals(sessions, reliability, latency):
    signals = []
    if sessions.get("awaiting_approval", 0) > 0:
        _add_signal(
            signals,
            "awaiting_approval",
            "warn",
            "active work is waiting for human approval",
            value=sessions.get("awaiting_approval"),
            threshold=0,
        )
    if sessions.get("stale_active", 0) > 0:
        _add_signal(
            signals,
            "stale_active_sessions",
            "info",
            "some active sessions belong to done tasks",
            value=sessions.get("stale_active"),
            threshold=0,
        )

    completion_ratio = reliability.get("completion_ratio")
    if completion_ratio is not None and completion_ratio < 0.95:
        _add_signal(
            signals,
            "low_completion_ratio",
            "warn",
            "selected sessions have unfinished or stale work",
            value=completion_ratio,
            threshold=">=0.95",
        )

    approvals = reliability.get("approvals") or {}
    approval_total = approvals.get("total", 0)
    approval_rejection_rate = _rate(approvals.get("rejected", 0) + approvals.get("failed", 0), approval_total)
    if approval_rejection_rate is not None and approval_rejection_rate >= 0.25:
        _add_signal(
            signals,
            "approval_friction",
            "info",
            "write proposals are often rejected or fail approval",
            value=approval_rejection_rate,
            threshold="<0.25",
        )

    verification = reliability.get("verification") or {}
    verification_total = verification.get("total", 0)
    verification_failure_rate = _rate(verification.get("failed", 0), verification_total)
    if verification_failure_rate is not None and verification_failure_rate >= 0.25:
        _add_signal(
            signals,
            "verification_friction",
            "warn",
            "verification failures are frequent in selected sessions",
            value=verification_failure_rate,
            threshold="<0.25",
        )

    first_tool_p95 = (latency.get("first_tool_start_seconds") or {}).get("p95")
    if first_tool_p95 is not None and first_tool_p95 > 60:
        _add_signal(
            signals,
            "slow_first_tool",
            "warn",
            "first tool output is slow at p95",
            value=first_tool_p95,
            threshold="<=60s",
        )

    model_resume_p95 = (latency.get("model_resume_wait_seconds") or {}).get("p95")
    if model_resume_p95 is not None and model_resume_p95 > 30:
        _add_signal(
            signals,
            "slow_model_resume",
            "warn",
            "model resume after tool completion is slow at p95",
            value=model_resume_p95,
            threshold="<=30s",
        )

    idle_ratio_p95 = (latency.get("perceived_idle_ratio") or {}).get("p95")
    if idle_ratio_p95 is not None and idle_ratio_p95 > 0.8:
        _add_signal(
            signals,
            "high_idle_ratio",
            "info",
            "selected sessions spend most wall time outside recorded model/tool activity at p95",
            value=idle_ratio_p95,
            threshold="<=0.8",
        )

    if not signals:
        _add_signal(signals, "no_obvious_bottleneck", "ok", "no obvious bottleneck in selected sessions")
    return signals


def _session_matches_kind(state, session, kind):
    if not kind:
        return True
    task = find_task(state, session.get("task_id"))
    return bool(task) and task_kind(task) == kind


def build_observation_metrics(state, *, kind=None, limit=None, sample_limit=DEFAULT_SAMPLE_LIMIT):
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
    model_resume_waits = []
    approval_bound_waits = []
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
        wait_records = _tool_to_next_model_wait_records(session, model_turns, tool_calls)
        tool_to_next_model_waits.extend(record.get("wait_seconds") for record in wait_records)
        model_resume_waits.extend(
            record.get("model_resume_wait_seconds")
            for record in wait_records
            if record.get("model_resume_wait_seconds") is not None
        )
        approval_bound_waits.extend(
            record.get("approval_bound_wait_seconds")
            for record in wait_records
            if record.get("approval_bound_wait_seconds") is not None
        )
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
    approval_problem_count = approval_counts["rejected"] + approval_counts["failed"]
    verification_failure_count = verification_counts["failed"]
    reliability_rates = {
        "completion": _round(completion_ratio),
        "interventions_per_session": _rate(intervention_count, session_counts["total"]),
        "tool_failure": _rate(tool_counts["failed"] + tool_counts["interrupted"], tool_counts["total"]),
        "model_turn_failure": _rate(turn_counts["failed"] + turn_counts["interrupted"], turn_counts["total"]),
        "approval_rejection": _rate(approval_problem_count, approval_counts["total"]),
        "verification_failure": _rate(verification_failure_count, verification_counts["total"]),
        "verification_rollback": _rate(verification_counts["rolled_back"], verification_counts["total"]),
    }

    reliability = {
        "completion_ratio": _round(completion_ratio),
        "interventions": intervention_count,
        "rates": reliability_rates,
        "tool_calls": tool_counts,
        "model_turns": turn_counts,
        "approvals": approval_counts,
        "verification": verification_counts,
    }
    latency = {
        "first_tool_start_seconds": _summary(first_tool_starts),
        "model_to_tool_wait_seconds": _summary(model_to_tool_waits),
        "tool_to_next_model_wait_seconds": _summary(tool_to_next_model_waits),
        "model_resume_wait_seconds": _summary(model_resume_waits),
        "approval_bound_wait_seconds": _summary(approval_bound_waits),
        "perceived_idle_ratio": _summary(idle_ratios),
    }
    return {
        "kind": kind or "all",
        "session_limit": limit,
        "sample_limit": sample_limit,
        "sessions": session_counts,
        "reliability": reliability,
        "latency": latency,
        "signals": _build_signals(session_counts, reliability, latency),
        "diagnostics": _diagnostic_samples(state, sessions, limit=sample_limit),
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
        ("rates", "rates"),
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
        ("model_resume_wait_seconds", "model_resume_wait_seconds"),
        ("approval_bound_wait_seconds", "approval_bound_wait_seconds"),
        ("perceived_idle_ratio", "perceived_idle_ratio"),
    ):
        summary = latency.get(key) or {}
        lines.append(
            f"{label}: count={summary.get('count', 0)} avg={summary.get('avg')} "
            f"median={summary.get('median')} p95={summary.get('p95')} max={summary.get('max')}"
        )
    signals = data.get("signals") or []
    if signals:
        lines.append("signals:")
        for signal in signals:
            value = signal.get("value")
            threshold = signal.get("threshold")
            details = []
            if value is not None:
                details.append(f"value={value}")
            if threshold is not None:
                details.append(f"threshold={threshold}")
            suffix = f" ({', '.join(details)})" if details else ""
            lines.append(f"- {signal.get('severity')}: {signal.get('message')}{suffix}")
    diagnostics = data.get("diagnostics") or {}
    verification_failures = diagnostics.get("verification_failures") or []
    approval_friction = diagnostics.get("approval_friction") or []
    slow_model_resumes = diagnostics.get("slow_model_resumes") or []
    approval_bound_waits = diagnostics.get("approval_bound_waits") or []
    high_idle_sessions = diagnostics.get("high_idle_sessions") or []
    if verification_failures or approval_friction or slow_model_resumes or approval_bound_waits or high_idle_sessions:
        lines.append("diagnostics:")
    if verification_failures:
        lines.append("verification_failures:")
        for sample in verification_failures:
            rollback = " rolled_back=true" if sample.get("rolled_back") else ""
            task = f" task=#{sample.get('task_id')}" if sample.get("task_id") is not None else ""
            path = f" path={sample.get('path')}" if sample.get("path") else ""
            command = f" command={sample.get('command')}" if sample.get("command") else ""
            lines.append(
                f"- session=#{sample.get('session_id')} call=#{sample.get('tool_call_id')}"
                f"{task} tool={sample.get('tool')} exit={sample.get('exit_code')}"
                f"{rollback}{path}{command}"
            )
            if sample.get("stderr"):
                lines.append(f"  stderr: {sample.get('stderr')}")
            elif sample.get("stdout"):
                lines.append(f"  stdout: {sample.get('stdout')}")
            if sample.get("latest_note"):
                lines.append(f"  latest_note: {sample.get('latest_note')}")
    if approval_friction:
        lines.append("approval_friction:")
        for sample in approval_friction:
            task = f" task=#{sample.get('task_id')}" if sample.get("task_id") is not None else ""
            path = f" path={sample.get('path')}" if sample.get("path") else ""
            lines.append(
                f"- session=#{sample.get('session_id')} call=#{sample.get('tool_call_id')}"
                f"{task} tool={sample.get('tool')} status={sample.get('approval_status')}{path}"
            )
            if sample.get("summary"):
                lines.append(f"  summary: {sample.get('summary')}")
            if sample.get("reason"):
                lines.append(f"  reason: {sample.get('reason')}")
    if slow_model_resumes:
        lines.append("slow_model_resumes:")
        for sample in slow_model_resumes:
            task = f" task=#{sample.get('task_id')}" if sample.get("task_id") is not None else ""
            path = f" path={sample.get('path')}" if sample.get("path") else ""
            lines.append(
                f"- session=#{sample.get('session_id')} call=#{sample.get('tool_call_id')}"
                f"{task} tool={sample.get('tool')} model_wait={sample.get('model_resume_wait_seconds')}s"
                f" raw_wait={sample.get('wait_seconds')}s next_turn=#{sample.get('next_model_turn_id')}{path}"
            )
    if approval_bound_waits:
        lines.append("approval_bound_waits:")
        for sample in approval_bound_waits:
            task = f" task=#{sample.get('task_id')}" if sample.get("task_id") is not None else ""
            path = f" path={sample.get('path')}" if sample.get("path") else ""
            approval = f" approval={sample.get('approval_status')}" if sample.get("approval_status") else ""
            lines.append(
                f"- session=#{sample.get('session_id')} call=#{sample.get('tool_call_id')}"
                f"{task} tool={sample.get('tool')}{approval} approval_wait={sample.get('approval_bound_wait_seconds')}s"
                f" raw_wait={sample.get('wait_seconds')}s next_turn=#{sample.get('next_model_turn_id')}{path}"
            )
    if high_idle_sessions:
        lines.append("high_idle_sessions:")
        for sample in high_idle_sessions:
            task = f" task=#{sample.get('task_id')}" if sample.get("task_id") is not None else ""
            lines.append(
                f"- session=#{sample.get('session_id')}{task} status={sample.get('status')} "
                f"idle_ratio={sample.get('idle_ratio')} wall={sample.get('wall_seconds')}s "
                f"active={sample.get('active_seconds')}s tools={sample.get('tool_call_count', 0)} "
                f"turns={sample.get('model_turn_count', 0)} notes={sample.get('note_count', 0)}"
            )
            if sample.get("latest_note"):
                lines.append(f"  latest_note: {sample.get('latest_note')}")
    return "\n".join(lines)
