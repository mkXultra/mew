from copy import deepcopy
import os
import shlex
import signal
import sys
import time

from .agent import (
    apply_event_plans,
    find_event,
    next_unprocessed_event,
    plan_event,
    update_runtime_processing_summary,
)
from .archive import archive_state_records
from .cli_command import mew_command
from .config import (
    DESIRES_FILE,
    GUIDANCE_FILE,
    POLICY_FILE,
    SELF_FILE,
    STATE_FILE,
)
from .errors import MewError
from .model_backends import (
    load_model_auth,
    model_backend_default_base_url,
    model_backend_default_model,
    model_backend_label,
    normalize_model_backend,
)
from .state import (
    acquire_lock,
    add_event,
    add_question,
    add_runtime_effect,
    append_log,
    complete_runtime_effect,
    ensure_desires,
    ensure_guidance,
    ensure_policy,
    ensure_self,
    find_runtime_effect,
    has_pending_user_message,
    load_state,
    read_desires,
    read_guidance,
    read_policy,
    read_self,
    release_lock,
    save_state,
    state_lock,
    update_runtime_effect,
)
from .read_tools import resolve_allowed_path
from .repair import repair_incomplete_runtime_effects
from .sweep import sweep_agent_runs
from .timeutil import now_iso, parse_time
from .toolbox import run_command_record
from .write_tools import resolve_allowed_write_path
from .work_session import (
    active_work_sessions,
    add_work_session_note,
    build_work_session_resume,
    execute_work_tool,
    find_work_session,
    find_work_tool_call,
    finish_work_tool_call,
    GIT_WORK_TOOLS,
    mark_work_session_running_interrupted,
    READ_ONLY_WORK_TOOLS,
    select_work_recovery_plan_item,
    start_work_tool_call,
    work_session_has_pending_write_approval,
    work_session_has_running_activity,
    work_session_runtime_command,
    work_session_started_by_runtime,
    work_session_task,
    work_recovery_read_root,
    work_tool_result_error,
    WRITE_WORK_TOOLS,
)


NATIVE_WORK_STEP_SKIP_HISTORY_LIMIT = 20
WORK_TOOL_RESULT_STALE_ERROR = "work tool result could not be recorded; work session changed during tool execution"


def set_runtime_running(state, started_at):
    runtime = state["runtime_status"]
    runtime["state"] = "running"
    runtime["pid"] = os.getpid()
    runtime["started_at"] = started_at
    runtime["stopped_at"] = None
    runtime["last_action"] = "runtime started"

def set_runtime_stopped(state, stopped_at):
    runtime = state["runtime_status"]
    runtime["state"] = "stopped"
    runtime["pid"] = None
    runtime["stopped_at"] = stopped_at
    runtime["current_reason"] = None
    runtime["current_event_id"] = None
    runtime["current_effect_id"] = None
    runtime["current_phase"] = None
    runtime["cycle_started_at"] = None
    runtime["last_action"] = "runtime stopped"


def repair_runtime_startup_state(state, current_time=None):
    current_time = current_time or now_iso()
    repairs = repair_incomplete_runtime_effects(state, current_time=current_time)
    if repairs:
        runtime = state.setdefault("runtime_status", {})
        runtime["last_startup_repairs"] = repairs[-20:]
        runtime["last_startup_repair_at"] = current_time
        runtime["last_action"] = f"runtime startup repaired {len(repairs)} interrupted item(s)"
    return repairs


def apply_runtime_autonomy_controls(state, args, pending_user, current_time):
    autonomy = state["autonomy"]
    requested_enabled = bool(args.autonomous)
    requested_level = args.autonomy_level if requested_enabled else "off"
    level_override = autonomy.get("level_override") or ""
    if level_override not in ("", "observe", "propose", "act"):
        level_override = ""
        autonomy["level_override"] = ""

    paused = bool(autonomy.get("paused"))
    effective_enabled = requested_enabled and not paused
    effective_level = level_override or requested_level
    if not effective_enabled:
        effective_level = "off"

    autonomy["requested_enabled"] = requested_enabled
    autonomy["requested_level"] = requested_level
    autonomy["enabled"] = effective_enabled
    autonomy["level"] = effective_level
    autonomy["paused"] = paused
    autonomy.setdefault("pause_reason", "")
    autonomy.setdefault("paused_at", None)
    autonomy.setdefault("resumed_at", None)
    autonomy["allow_agent_run"] = bool(args.allow_agent_run)
    autonomy["allow_native_work"] = bool(getattr(args, "allow_native_work", False))
    autonomy["allow_native_advance"] = bool(getattr(args, "allow_native_advance", False))
    autonomy["allow_verify"] = bool(args.allow_verify)
    autonomy["verify_command_configured"] = bool(args.verify_command)
    autonomy["allow_write"] = bool(args.allow_write)
    autonomy["updated_at"] = current_time

    autonomous_for_cycle = effective_enabled and not pending_user
    return {
        "autonomous": autonomous_for_cycle,
        "autonomy_level": effective_level if autonomous_for_cycle else "off",
        "allow_agent_run": bool(args.allow_agent_run) and autonomous_for_cycle,
        "allow_native_work": bool(getattr(args, "allow_native_work", False))
        and autonomous_for_cycle,
        "allow_native_advance": bool(getattr(args, "allow_native_advance", False))
        and autonomous_for_cycle,
    }

def plan_runtime_event(
    state_snapshot,
    event_snapshot,
    current_time,
    model_auth,
    model,
    base_url,
    model_backend,
    args,
    allow_task_execution,
    guidance,
    policy,
    self_text,
    desires,
    autonomy_controls,
):
    return plan_event(
        state_snapshot,
        event_snapshot,
        current_time,
        model_auth=model_auth,
        model=model,
        base_url=base_url,
        model_backend=model_backend,
        timeout=args.timeout,
        ai_ticks=args.ai_ticks,
        allow_task_execution=allow_task_execution,
        guidance=guidance,
        policy=policy,
        self_text=self_text,
        desires=desires,
        autonomous=autonomy_controls["autonomous"],
        autonomy_level=autonomy_controls["autonomy_level"],
        allow_agent_run=autonomy_controls["allow_agent_run"],
        allow_native_work=autonomy_controls["allow_native_work"],
        allow_verify=args.allow_verify,
        verify_command=args.verify_command or "",
        verify_interval_seconds=max(0.0, args.verify_interval_minutes * 60.0),
        allow_write=bool(args.allow_write),
        allowed_read_roots=args.allow_read,
        allowed_write_roots=args.allow_write,
        trace_model=bool(getattr(args, "trace_model", False)),
        max_reflex_rounds=getattr(args, "max_reflex_rounds", 0),
    )

def apply_runtime_event_plans(
    state,
    event_id,
    decision_plan,
    action_plan,
    current_time,
    reason,
    args,
    allow_task_execution,
    autonomy_controls,
    work_auth="",
    work_model_backend="",
    work_model="",
    work_base_url="",
):
    counts = apply_event_plans(
        state,
        event_id,
        decision_plan,
        action_plan,
        current_time,
        reason,
        allow_task_execution=allow_task_execution,
        task_timeout=args.task_timeout,
        allowed_read_roots=args.allow_read,
        autonomous=autonomy_controls["autonomous"],
        autonomy_level=autonomy_controls["autonomy_level"],
        allow_agent_run=autonomy_controls["allow_agent_run"],
        allow_native_work=autonomy_controls["allow_native_work"],
        allow_verify=args.allow_verify,
        verify_command=args.verify_command or "",
        verify_timeout=args.verify_timeout,
        allow_write=bool(args.allow_write),
        allowed_write_roots=args.allow_write,
        agent_result_timeout=getattr(args, "agent_result_timeout", 10.0),
        work_auth=work_auth,
        work_model_backend=work_model_backend,
        work_model=work_model,
        work_base_url=work_base_url,
        work_model_timeout=args.timeout,
        work_verify_timeout=args.verify_timeout,
        work_tool_timeout=args.task_timeout,
    )
    if counts is None:
        counts = {"actions": 0, "messages": 0, "executed": 0, "waits": 0}
        processed_count = 0
    else:
        processed_count = 1
    update_runtime_processing_summary(
        state,
        reason,
        current_time,
        processed_count,
        counts["actions"],
        counts["messages"],
        counts["executed"],
        autonomous=autonomy_controls["autonomous"],
    )
    return processed_count, counts


def runtime_native_work_step_command(session, task_id):
    command_session = deepcopy(session or {})
    defaults = command_session.setdefault("default_options", {})
    defaults["quiet"] = True
    defaults["compact_live"] = True
    defaults["no_prompt_approval"] = True
    defaults.pop("prompt_approval", None)
    return work_session_runtime_command(command_session, task_id, follow=False, max_steps=1)


def runtime_native_work_step_timeout(args, session=None):
    defaults = (session or {}).get("default_options") or {}
    model_timeout = float(defaults.get("model_timeout") or getattr(args, "timeout", 60.0) or 60.0)
    tool_timeout = float(defaults.get("tool_timeout") or getattr(args, "task_timeout", 300.0) or 300.0)
    verify_timeout = float(defaults.get("verify_timeout") or getattr(args, "verify_timeout", 300.0) or 300.0)
    return max(30.0, model_timeout + tool_timeout + verify_timeout + 30.0)


def record_runtime_native_work_step_skip(
    runtime_status,
    reason,
    *,
    current_time=None,
    event_id=None,
    phase="select",
    session_id=None,
    task_id=None,
    command=None,
    recovery=None,
):
    if not reason:
        runtime_status["last_native_work_step_skip"] = None
        runtime_status["last_native_work_skip_recovery"] = {}
        return None
    entry = {
        "at": current_time or now_iso(),
        "reason": reason,
        "phase": phase,
    }
    if event_id is not None:
        entry["event_id"] = event_id
    if session_id is not None:
        entry["session_id"] = session_id
    if task_id is not None:
        entry["task_id"] = task_id
    if command:
        entry["command"] = command
    if recovery:
        entry["recovery"] = recovery
    skips = list(runtime_status.get("native_work_step_skips") or [])
    skips.append(entry)
    runtime_status["native_work_step_skips"] = skips[-NATIVE_WORK_STEP_SKIP_HISTORY_LIMIT:]
    runtime_status["last_native_work_step_skip"] = reason
    runtime_status["last_native_work_skip_recovery"] = recovery or {}
    return entry


def previous_native_work_step_failure_unresolved(state, session, task=None):
    last_step = (state.get("runtime_status") or {}).get("last_native_work_step") or {}
    if last_step.get("outcome") != "failed":
        return False
    if str(last_step.get("session_id")) != str(session.get("id")):
        return False
    task_id = (task or {}).get("id") or session.get("task_id")
    if last_step.get("task_id") is not None and str(last_step.get("task_id")) != str(task_id):
        return False
    failed_at = parse_time(last_step.get("finished_at"))
    if failed_at and native_work_session_failed_runtime_recovery_after_failure(session, failed_at):
        return True
    if failed_at and native_work_session_activity_after_failure(session, failed_at):
        if work_session_has_unresolved_interruption(session) and not native_work_session_activity_after_failure(
            session,
            failed_at,
            ignore_runtime_recovery=True,
        ):
            return True
        return False
    return True


def work_session_has_unresolved_interruption(session):
    for call in (session or {}).get("tool_calls") or []:
        if call.get("status") == "interrupted" and not call.get("recovery_status"):
            return True
    for turn in (session or {}).get("model_turns") or []:
        if turn.get("status") == "interrupted" and not turn.get("recovery_status"):
            return True
    return False


def native_work_session_activity_after_failure(session, failed_at, *, ignore_runtime_recovery=False):
    for call in session.get("tool_calls") or []:
        for key in ("started_at", "finished_at", "updated_at"):
            timestamp = parse_time(call.get(key))
            if timestamp and timestamp > failed_at:
                parameters = call.get("parameters") or {}
                if (
                    ignore_runtime_recovery
                    and parameters.get("recovery_owner") == "runtime"
                    and call.get("status") == "completed"
                ):
                    continue
                return True
    for turn in session.get("model_turns") or []:
        for key in ("started_at", "finished_at", "updated_at"):
            timestamp = parse_time(turn.get(key))
            if timestamp and timestamp > failed_at:
                return True
    for note in session.get("notes") or []:
        if note.get("source") == "runtime":
            continue
        timestamp = parse_time(note.get("created_at") or note.get("updated_at"))
        if timestamp and timestamp > failed_at:
            return True
    return False


def native_work_session_failed_runtime_recovery_after_failure(session, failed_at):
    return bool(latest_failed_runtime_recovery_after_failure(session, failed_at))


def latest_failed_runtime_recovery_after_failure(session, failed_at):
    latest_call = None
    latest_timestamp = None
    for call in session.get("tool_calls") or []:
        parameters = call.get("parameters") or {}
        if parameters.get("recovery_owner") != "runtime" or call.get("status") == "completed":
            continue
        for key in ("started_at", "finished_at", "updated_at"):
            timestamp = parse_time(call.get(key))
            if timestamp and timestamp > failed_at:
                if latest_timestamp is None or timestamp >= latest_timestamp:
                    latest_call = call
                    latest_timestamp = timestamp
    return latest_call or {}


def recover_previous_native_work_step_failure(state, *, event_id=None, current_time=None):
    runtime_status = state.setdefault("runtime_status", {})
    last_step = runtime_status.get("last_native_work_step") or {}
    if last_step.get("outcome") != "failed":
        return None
    session = find_work_session(state, last_step.get("session_id"))
    if not session:
        return None
    task = work_session_task(state, session)
    if not previous_native_work_step_failure_unresolved(state, session, task):
        return None
    task_id = (task or {}).get("id") or session.get("task_id")
    session_id = session.get("id")
    resume_command = mew_command("work", task_id, "--session", "--resume", "--allow-read", ".")
    retry_command = mew_command("work", task_id, "--live", "--allow-read", ".", "--max-steps", "1")
    recovery_plan = build_work_session_resume(session, task=task, state=state).get("recovery_plan") or {}
    failed_at = parse_time(last_step.get("finished_at"))
    failed_runtime_recovery = (
        latest_failed_runtime_recovery_after_failure(session, failed_at) if failed_at else {}
    )
    recovery_suggestion = (
        {}
        if failed_runtime_recovery
        else native_work_recovery_suggestion_from_plan(recovery_plan, task_id=task_id)
    )
    exit_part = ""
    if last_step.get("timed_out"):
        exit_part = "timed out"
    elif last_step.get("exit_code") not in (None, ""):
        exit_part = f"exit_code={last_step.get('exit_code')}"
    reason = f" after {exit_part}" if exit_part else ""
    text = (
        f"Passive native work session #{session_id} for task #{task_id} failed{reason}. "
        f"Inspect with `{resume_command}`. "
    )
    if failed_runtime_recovery:
        failed_tool = failed_runtime_recovery.get("tool") or "tool"
        failed_id = failed_runtime_recovery.get("id")
        text += (
            f"Previous automatic recovery tool #{failed_id} ({failed_tool}) failed; "
            "inspect that result before retrying more recovery. "
        )
    elif recovery_suggestion:
        effect_part = ""
        if recovery_suggestion.get("effect_classification"):
            effect_part = f" (effect={recovery_suggestion.get('effect_classification')})"
        text += (
            f"Recovery plan suggests {recovery_suggestion.get('label')}{effect_part}: "
            f"`{recovery_suggestion.get('command')}`. "
        )
    text += (
        f"Should I retry with `{retry_command}`, keep it paused, "
        "or close/replan the task?"
    )
    question, created = add_question(
        state,
        text,
        event_id=event_id,
        related_task_id=task_id,
        source="runtime",
    )
    if created:
        add_work_session_note(
            session,
            f"runtime asked for recovery after failed passive native advance: {resume_command}",
            source="runtime",
            current_time=current_time,
        )
    recovery = {
        "at": current_time or now_iso(),
        "action": "ask_user_seeded_question",
        "reason": "previous_native_work_step_failed",
        "session_id": session_id,
        "task_id": task_id,
        "question_id": question.get("id"),
        "question_created": created,
        "resume_command": resume_command,
        "retry_command": retry_command,
        "exit_code": last_step.get("exit_code"),
        "timed_out": bool(last_step.get("timed_out")),
    }
    if recovery_suggestion:
        recovery["recovery_plan_action"] = recovery_suggestion.get("action")
        recovery["recovery_plan_command"] = recovery_suggestion.get("command")
        recovery["recovery_plan_reason"] = recovery_suggestion.get("reason")
        recovery["recovery_effect_classification"] = recovery_suggestion.get("effect_classification")
    if failed_runtime_recovery:
        recovery["failed_runtime_recovery_tool_call_id"] = failed_runtime_recovery.get("id")
        recovery["failed_runtime_recovery_tool"] = failed_runtime_recovery.get("tool")
        recovery["failed_runtime_recovery_status"] = failed_runtime_recovery.get("status")
        recovery["failed_runtime_recovery_error"] = failed_runtime_recovery.get("error") or (
            (failed_runtime_recovery.get("result") or {}).get("stderr") or ""
        )
    runtime_status["last_native_work_recovery"] = recovery
    runtime_status["last_action"] = f"asked for native work recovery session #{session_id}"
    return recovery


def interrupted_work_verifier_command(call):
    result = (call or {}).get("result") or {}
    parameters = (call or {}).get("parameters") or {}
    return result.get("command") or parameters.get("command") or ""


def interrupted_work_verifier_cwd(call):
    result = (call or {}).get("result") or {}
    parameters = (call or {}).get("parameters") or {}
    return result.get("cwd") or parameters.get("cwd") or "."


def runtime_recovery_commands_match(expected, requested):
    expected = expected or ""
    requested = requested or ""
    if expected == requested:
        return True
    try:
        return shlex.split(expected) == shlex.split(requested)
    except ValueError:
        return False


def recovery_plan_item_index(recovery_plan, item):
    for index, candidate in enumerate((recovery_plan or {}).get("items") or []):
        if candidate is item:
            return index
    return None


def select_runtime_work_recovery_plan_item(recovery_plan):
    selected = select_work_recovery_plan_item(recovery_plan)
    if not selected or selected.get("action") != "retry_tool":
        return selected
    selected_index = recovery_plan_item_index(recovery_plan, selected)
    if selected_index is None:
        return selected
    newer_barriers = [
        item
        for index, item in enumerate((recovery_plan or {}).get("items") or [])
        if index > selected_index and item.get("action") != "retry_tool"
    ]
    if newer_barriers:
        return newer_barriers[-1]
    return selected


def prepare_runtime_native_work_tool_recovery(state, args, *, event_id=None, current_time=None, safe_tool_only=False):
    runtime_status = state.setdefault("runtime_status", {})
    last_step = runtime_status.get("last_native_work_step") or {}
    if last_step.get("outcome") != "failed":
        return None
    session = find_work_session(state, last_step.get("session_id"))
    if not session:
        return None
    task = work_session_task(state, session)
    if not previous_native_work_step_failure_unresolved(state, session, task):
        return None
    failed_at = parse_time(last_step.get("finished_at"))
    if failed_at and native_work_session_failed_runtime_recovery_after_failure(session, failed_at):
        return None
    if work_session_has_pending_write_approval(session):
        return None
    recovery_plan = (build_work_session_resume(session, task=task, state=state) or {}).get("recovery_plan") or {}
    selected_recovery = select_runtime_work_recovery_plan_item(recovery_plan)
    source_call = find_work_tool_call(session, selected_recovery.get("tool_call_id"))
    selected_action = selected_recovery.get("action")
    selected_tool = (source_call or {}).get("tool") or selected_recovery.get("tool") or ""
    if safe_tool_only and not (selected_action == "retry_tool" and selected_tool in (READ_ONLY_WORK_TOOLS | GIT_WORK_TOOLS)):
        return None
    recovery = {
        "at": current_time or now_iso(),
        "action": "auto_retry_tool_blocked",
        "reason": "",
        "session_id": session.get("id"),
        "task_id": (task or {}).get("id") or session.get("task_id"),
        "source_tool_call_id": selected_recovery.get("tool_call_id"),
        "tool": selected_tool,
        "selected_recovery_action": selected_action,
        "selected_tool_call_id": selected_recovery.get("tool_call_id"),
        "selected_effect_classification": selected_recovery.get("effect_classification"),
    }
    if not source_call or source_call.get("status") != "interrupted" or source_call.get("recovery_status"):
        recovery["reason"] = "runtime recovery needs the selected interrupted tool call"
        runtime_status["last_native_work_recovery"] = recovery
        return None
    if selected_action == "retry_verification" and selected_tool == "run_tests":
        command = interrupted_work_verifier_command(source_call)
        cwd = interrupted_work_verifier_cwd(source_call)
        recovery["command"] = command
        recovery["cwd"] = cwd
        if not getattr(args, "allow_read", None):
            recovery["reason"] = "runtime verifier recovery needs explicit --allow-read roots"
            runtime_status["last_native_work_recovery"] = recovery
            return None
        try:
            resolve_allowed_path(cwd, getattr(args, "allow_read", None) or [])
        except ValueError as exc:
            recovery["reason"] = "runtime verifier recovery needs --allow-read to cover the verifier cwd"
            recovery["allow_read"] = list(getattr(args, "allow_read", None) or [])
            recovery["error"] = str(exc)
            runtime_status["last_native_work_recovery"] = recovery
            return None
        if not getattr(args, "allow_verify", False):
            recovery["reason"] = "runtime verifier recovery needs explicit --allow-verify"
            runtime_status["last_native_work_recovery"] = recovery
            return None
        requested_command = getattr(args, "verify_command", None) or ""
        if not requested_command:
            recovery["reason"] = "runtime verifier recovery needs --verify-command"
            runtime_status["last_native_work_recovery"] = recovery
            return None
        if not runtime_recovery_commands_match(command, requested_command):
            recovery["reason"] = "runtime verifier recovery only reruns the exact interrupted command"
            recovery["requested_command"] = requested_command
            runtime_status["last_native_work_recovery"] = recovery
            return None
        parameters = dict(source_call.get("parameters") or {})
        parameters["recovered_from_tool_call_id"] = source_call.get("id")
        parameters["command"] = command
        parameters["cwd"] = cwd
        parameters["allow_verify"] = True
        recovery_kind = "verification"
        recovery_reason = "previous passive native advance left an interrupted verifier"
    elif selected_action == "retry_tool" and selected_tool in (READ_ONLY_WORK_TOOLS | GIT_WORK_TOOLS):
        read_root = work_recovery_read_root(source_call)
        recovery["path"] = read_root
        if not getattr(args, "allow_read", None):
            recovery["reason"] = "runtime safe tool recovery needs explicit --allow-read roots"
            runtime_status["last_native_work_recovery"] = recovery
            return None
        try:
            resolve_allowed_path(read_root, getattr(args, "allow_read", None) or [])
        except ValueError as exc:
            recovery["reason"] = "runtime safe tool recovery needs --allow-read to cover the interrupted tool path"
            recovery["allow_read"] = list(getattr(args, "allow_read", None) or [])
            recovery["error"] = str(exc)
            runtime_status["last_native_work_recovery"] = recovery
            return None
        parameters = dict(source_call.get("parameters") or {})
        parameters["recovered_from_tool_call_id"] = source_call.get("id")
        recovery_kind = "tool"
        recovery_reason = "previous passive native advance left an interrupted safe read/git tool"
    elif selected_action == "retry_dry_run_write" and selected_tool in WRITE_WORK_TOOLS:
        write_root = work_recovery_read_root(source_call)
        recovery["path"] = write_root
        if not getattr(args, "allow_write", None):
            recovery["reason"] = "runtime dry-run write recovery needs explicit --allow-write roots"
            runtime_status["last_native_work_recovery"] = recovery
            return None
        try:
            resolve_allowed_write_path(
                write_root,
                getattr(args, "allow_write", None) or [],
                create=bool((source_call.get("parameters") or {}).get("create")),
            )
        except ValueError as exc:
            recovery["reason"] = "runtime dry-run write recovery needs --allow-write to cover the interrupted tool path"
            recovery["allow_write"] = list(getattr(args, "allow_write", None) or [])
            recovery["error"] = str(exc)
            runtime_status["last_native_work_recovery"] = recovery
            return None
        parameters = dict(source_call.get("parameters") or {})
        parameters["recovered_from_tool_call_id"] = source_call.get("id")
        parameters["apply"] = False
        parameters["allowed_write_roots"] = list(getattr(args, "allow_write", None) or [])
        for key in ("approved_from_tool_call_id", "allow_verify", "verify_command", "verify_cwd", "verify_timeout"):
            parameters.pop(key, None)
        recovery_kind = "dry_run_write"
        recovery_reason = "previous passive native advance left an interrupted dry-run write preview"
    else:
        recovery["reason"] = "runtime recovery only auto-runs the selected safe recovery-plan item"
        runtime_status["last_native_work_recovery"] = recovery
        return None
    parameters["recovery_owner"] = "runtime"
    tool_call = start_work_tool_call(state, session, selected_tool, parameters)
    recovery.update(
        {
            "at": current_time or now_iso(),
            "action": f"auto_retry_{recovery_kind}_started",
            "reason": recovery_reason,
            "recovered_by_tool_call_id": tool_call.get("id"),
            "event_id": event_id,
        }
    )
    runtime_status["last_native_work_recovery"] = recovery
    runtime_status["last_action"] = f"auto retrying native work {recovery_kind} session #{session.get('id')}"
    descriptor = recovery.get("command") or recovery.get("path") or selected_tool
    add_work_session_note(
        session,
        f"runtime auto-retrying interrupted {selected_tool} tool #{source_call.get('id')}: {descriptor}",
        source="runtime",
        current_time=current_time,
    )
    return {
        "session_id": session.get("id"),
        "task_id": recovery.get("task_id"),
        "source_tool_call_id": source_call.get("id"),
        "tool_call_id": tool_call.get("id"),
        "tool": selected_tool,
        "parameters": parameters,
        "recovery_kind": recovery_kind,
        "command": recovery.get("command"),
        "cwd": recovery.get("cwd"),
        "path": recovery.get("path"),
        "event_id": event_id,
    }


def run_runtime_native_work_recovery_step(step, args):
    tool = step.get("tool") or "run_tests"
    parameters = dict(step.get("parameters") or {})
    try:
        result = execute_work_tool(
            tool,
            parameters,
            getattr(args, "allow_read", None) or [],
        )
        error = work_tool_result_error(tool, result)
    except (OSError, ValueError) as exc:
        result = None
        error = str(exc)

    completed_at = now_iso()
    with state_lock():
        state = load_state()
        tool_call = finish_work_tool_call(
            state,
            step.get("session_id"),
            step.get("tool_call_id"),
            result=result,
            error=error,
        )
        if not tool_call:
            error = error or WORK_TOOL_RESULT_STALE_ERROR
            tool_call = {
                "id": step.get("tool_call_id"),
                "tool": tool,
                "status": "failed",
                "result": result,
                "error": error,
            }
        session = find_work_session(state, step.get("session_id"))
        source_call = find_work_tool_call(session, step.get("source_tool_call_id"))
        if source_call:
            source_call["recovery_status"] = "superseded" if not error else "retry_failed"
            source_call["recovered_by_tool_call_id"] = step.get("tool_call_id")
            source_call["recovered_at"] = completed_at
            for turn in (session or {}).get("model_turns") or []:
                if turn.get("tool_call_id") != source_call.get("id"):
                    continue
                turn["recovery_status"] = source_call["recovery_status"]
                turn["recovered_by_tool_call_id"] = step.get("tool_call_id")
                turn["recovered_at"] = completed_at
        runtime_status = state.setdefault("runtime_status", {})
        recovery_kind = step.get("recovery_kind") or ("verification" if tool == "run_tests" else "tool")
        runtime_status["last_native_work_recovery"] = {
            "at": completed_at,
            "action": f"auto_retry_{recovery_kind}_completed" if not error else f"auto_retry_{recovery_kind}_failed",
            "session_id": step.get("session_id"),
            "task_id": step.get("task_id"),
            "source_tool_call_id": step.get("source_tool_call_id"),
            "recovered_by_tool_call_id": step.get("tool_call_id"),
            "tool": tool,
            "command": step.get("command"),
            "cwd": step.get("cwd"),
            "path": step.get("path"),
            "status": (tool_call or {}).get("status"),
            "error": error,
        }
        runtime_status["last_action"] = (
            f"auto {recovery_kind} recovery {'completed' if not error else 'failed'} "
            f"session #{step.get('session_id')}"
        )
        save_state(state)

    return {
        "tool_call": tool_call,
        "result": result,
        "error": error,
        "exit_code": (result or {}).get("exit_code"),
    }


def run_runtime_native_work_recovery_steps(first_step, args, *, max_recoveries=5):
    steps = []
    results = []
    step = first_step
    limit = max(1, int(max_recoveries or 1))
    for _ in range(limit):
        steps.append(step)
        result = run_runtime_native_work_recovery_step(step, args)
        results.append(result)
        if result.get("error") or step.get("recovery_kind") != "tool":
            break
        with state_lock():
            state = load_state()
            next_step = prepare_runtime_native_work_tool_recovery(
                state,
                args,
                event_id=step.get("event_id"),
                current_time=now_iso(),
                safe_tool_only=True,
            )
            if next_step:
                save_state(state)
        if not next_step:
            break
        step = next_step

    if len(steps) > 1:
        completed = [item for item, result in zip(steps, results) if not result.get("error")]
        with state_lock():
            state = load_state()
            runtime_status = state.setdefault("runtime_status", {})
            recovery = dict(runtime_status.get("last_native_work_recovery") or {})
            recovery.update(
                {
                    "batch": True,
                    "batch_action": "auto_retry_tool_batch",
                    "batch_status": "completed" if len(completed) == len(steps) else "failed",
                    "count": len(completed),
                    "source_tool_call_ids": [item.get("source_tool_call_id") for item in completed],
                    "tool_call_ids": [item.get("tool_call_id") for item in completed],
                }
            )
            runtime_status["last_native_work_recovery"] = recovery
            save_state(state)

    return {"steps": steps, "results": results}


def native_work_recovery_suggestion_from_plan(recovery_plan, *, task_id=None):
    items = (recovery_plan or {}).get("items") or []
    if not items:
        return {}
    item = select_runtime_work_recovery_plan_item(recovery_plan)
    action = item.get("action") or ""
    command = item.get("hint") or item.get("auto_hint") or item.get("review_hint") or ""
    label = action.replace("_", " ") if action else "review"
    if action == "retry_tool":
        command = item.get("auto_hint") or item.get("hint") or command
        label = "safe read/git recovery"
    elif action == "retry_verification":
        label = "verification recovery"
    elif action == "needs_user_review":
        command = item.get("review_hint") or command
        label = "side-effect review"
    elif action == "retry_apply_write":
        label = "apply-write recovery"
    elif action == "verify_completed_write":
        label = "completed-write verification"
    elif action == "replan":
        label = "replan"
    if not command:
        command = mew_command("work", task_id, "--session", "--resume", "--allow-read", ".")
    return {
        "action": action,
        "label": label,
        "command": command,
        "reason": (recovery_plan or {}).get("next_action") or item.get("reason") or "",
        "effect_classification": item.get("effect_classification") or "",
        "tool_call_id": item.get("tool_call_id"),
        "model_turn_id": item.get("model_turn_id"),
    }


def native_work_skip_recovery_suggestion(state, reason, *, session_id=None, task_id=None):
    normalized_reason = str(reason or "").removeprefix("prelaunch_")
    if not normalized_reason:
        return {}

    session = find_work_session(state, session_id) if session_id is not None else None
    active_sessions = active_work_sessions(state)
    if session is None:
        if normalized_reason == "human_work_session_active":
            session = next((candidate for candidate in active_sessions if not work_session_started_by_runtime(candidate)), None)
        else:
            runtime_sessions = [
                candidate for candidate in active_sessions if work_session_started_by_runtime(candidate)
            ]
            if len(runtime_sessions) == 1:
                session = runtime_sessions[0]

    task = work_session_task(state, session) if session else None
    resolved_task_id = task_id or (task or {}).get("id") or (session or {}).get("task_id")
    resume_command = (
        mew_command("work", resolved_task_id, "--session", "--resume", "--allow-read", ".")
        if resolved_task_id
        else mew_command("focus", "--kind", "coding")
    )

    if normalized_reason == "no_active_work_session":
        return {
            "action": "inspect_coding_focus",
            "label": "inspect coding focus",
            "command": mew_command("focus", "--kind", "coding"),
            "reason": "no runtime-owned work session is active",
        }
    if normalized_reason == "multiple_runtime_work_sessions_active":
        return {
            "action": "inspect_coding_focus",
            "label": "inspect active runtime sessions",
            "command": mew_command("focus", "--kind", "coding"),
            "reason": "more than one runtime-owned work session is active",
        }
    if normalized_reason == "session_started_this_cycle":
        return {
            "action": "wait_next_tick",
            "label": "wait for the next passive tick",
            "command": resume_command,
            "reason": "runtime started this work session during the same cycle",
            "session_id": (session or {}).get("id"),
            "task_id": resolved_task_id,
        }
    if normalized_reason == "task_done" and resolved_task_id:
        return {
            "action": "reopen_task",
            "label": "reopen completed task",
            "command": mew_command("task", "update", resolved_task_id, "--status", "ready"),
            "reason": "the runtime-owned work session belongs to a done task",
            "session_id": (session or {}).get("id"),
            "task_id": resolved_task_id,
        }
    if normalized_reason == "pending_write_approval" and session:
        resume = build_work_session_resume(session, task=task, state=state)
        approval = ((resume.get("pending_approvals") or [])[:1] or [{}])[0]
        pairing = approval.get("pairing_status") or {}
        approve_command = approval.get("cli_approve_hint") or ""
        blocked_approve_command = approval.get("cli_blocked_approve_hint") or approve_command
        override_approve_command = approval.get("cli_override_approve_hint") or (
            f"{blocked_approve_command} --allow-unpaired-source-edit" if blocked_approve_command else ""
        )
        if pairing.get("status") == "missing_test_edit":
            command = resume_command
            reason = "a source edit is waiting for a paired tests/** edit or an explicit override"
        else:
            command = approve_command or resume_command
            reason = "a dry-run write/edit is waiting for approval or rejection"
        suggestion = {
            "action": "resolve_pending_write_approval",
            "label": "resolve pending write approval",
            "command": command,
            "reason": reason,
            "session_id": session.get("id"),
            "task_id": resolved_task_id,
            "tool_call_id": approval.get("tool_call_id"),
            "resume_command": resume_command,
        }
        if pairing.get("status") == "missing_test_edit":
            suggestion["pairing_status"] = pairing
            if blocked_approve_command:
                suggestion["blocked_command"] = blocked_approve_command
            if override_approve_command:
                suggestion["override_command"] = override_approve_command
        if approval.get("cli_reject_hint"):
            suggestion["alternate_command"] = approval.get("cli_reject_hint")
        return suggestion
    if normalized_reason == "previous_native_work_step_failed" and session:
        resume = build_work_session_resume(session, task=task, state=state)
        suggestion = native_work_recovery_suggestion_from_plan(
            resume.get("recovery_plan") or {},
            task_id=resolved_task_id,
        )
        if suggestion:
            suggestion.setdefault("session_id", session.get("id"))
            suggestion.setdefault("task_id", resolved_task_id)
            return suggestion
    if normalized_reason in ("human_work_session_active", "stop_requested", "work_session_running") and session:
        labels = {
            "human_work_session_active": "inspect human work session",
            "stop_requested": "inspect stop request",
            "work_session_running": "inspect running work session",
        }
        return {
            "action": "inspect_work_session",
            "label": labels.get(normalized_reason, "inspect work session"),
            "command": resume_command,
            "reason": f"native work advance skipped because {normalized_reason}",
            "session_id": session.get("id"),
            "task_id": resolved_task_id,
        }
    return {}


def select_runtime_native_work_step(state, *, current_event_id=None):
    active_sessions = active_work_sessions(state)
    if not active_sessions:
        return None, "no_active_work_session"

    human_sessions = [
        session
        for session in active_sessions
        if not work_session_started_by_runtime(session)
    ]
    if human_sessions:
        return None, "human_work_session_active"

    runtime_sessions = [
        session
        for session in active_sessions
        if work_session_started_by_runtime(session)
    ]
    if len(runtime_sessions) > 1:
        return None, "multiple_runtime_work_sessions_active"

    session = runtime_sessions[0]
    task = work_session_task(state, session)
    if task and task.get("status") == "done":
        return None, "task_done"
    if current_event_id is not None and str(session.get("runtime_started_event_id")) == str(current_event_id):
        return None, "session_started_this_cycle"
    if session.get("stop_requested_at"):
        return None, "stop_requested"
    if work_session_has_running_activity(session):
        return None, "work_session_running"
    if work_session_has_pending_write_approval(session):
        return None, "pending_write_approval"
    if previous_native_work_step_failure_unresolved(state, session, task):
        return None, "previous_native_work_step_failed"

    task_id = (task or {}).get("id") or session.get("task_id")
    return (
        {
            "session_id": session.get("id"),
            "task_id": task_id,
            "command": runtime_native_work_step_command(session, task_id),
        },
        None,
    )


def run_runtime_native_work_step(step, args):
    with state_lock():
        state = load_state()
        selected, skip = select_runtime_native_work_step(state)
        if not selected or str(selected.get("session_id")) != str(step.get("session_id")):
            skipped_at = now_iso()
            runtime_status = state.setdefault("runtime_status", {})
            skip_reason = f"prelaunch_{skip or 'changed'}"
            skip_recovery = native_work_skip_recovery_suggestion(
                state,
                skip_reason,
                session_id=step.get("session_id"),
                task_id=step.get("task_id"),
            )
            record_runtime_native_work_step_skip(
                runtime_status,
                skip_reason,
                current_time=skipped_at,
                phase="prelaunch",
                session_id=step.get("session_id"),
                task_id=step.get("task_id"),
                command=step.get("command"),
                recovery=skip_recovery,
            )
            runtime_status["last_native_work_step"] = {
                "finished_at": skipped_at,
                "session_id": step.get("session_id"),
                "task_id": step.get("task_id"),
                "command": step.get("command"),
                "outcome": "skipped",
                "skip_reason": skip or "changed",
            }
            save_state(state)
            return {
                "command": step.get("command"),
                "exit_code": 0,
                "skipped": True,
                "skip_reason": skip or "changed",
            }
        session = find_work_session(state, step.get("session_id"))
        timeout = runtime_native_work_step_timeout(args, session)
    result = run_command_record(
        step["command"],
        cwd=".",
        timeout=timeout,
        kill_process_group=True,
    )
    finished_at = now_iso()
    success = result.get("exit_code") == 0 and not result.get("timed_out")
    outcome = "completed" if success else "failed"
    with state_lock():
        state = load_state()
        session = find_work_session(state, step.get("session_id"))
        repairs = []
        if session:
            if result.get("timed_out"):
                repairs = mark_work_session_running_interrupted(session, current_time=finished_at)
            add_work_session_note(
                session,
                f"runtime passive advance step {outcome}: {step['command']}",
                source="runtime",
                current_time=finished_at,
            )
        state.setdefault("runtime_status", {})["last_native_work_step"] = {
            "finished_at": finished_at,
            "session_id": step.get("session_id"),
            "task_id": step.get("task_id"),
            "command": step.get("command"),
            "exit_code": result.get("exit_code"),
            "timed_out": bool(result.get("timed_out")),
            "outcome": outcome,
            "repairs": repairs,
        }
        state["runtime_status"]["last_action"] = f"native work step {outcome}"
        save_state(state)
    return result


def action_types_for_plan(action_plan):
    if not isinstance(action_plan, dict):
        return []
    return [
        action.get("type") or "unknown"
        for action in action_plan.get("actions", [])
        if isinstance(action, dict)
    ]

def runtime_effect_outcome_for_plan(action_plan):
    if not isinstance(action_plan, dict):
        return ""
    for action in action_plan.get("actions", []):
        if not isinstance(action, dict):
            continue
        action_type = action.get("type")
        if action_type == "send_message":
            return action.get("text") or action.get("summary") or action_plan.get("summary") or ""
        if action_type in ("ask_user", "wait_for_user"):
            return action.get("question") or action.get("text") or action.get("reason") or ""
        if action_type == "run_verification":
            return f"verify: {action.get('command') or 'configured command'}"
        if action_type in ("write_file", "edit_file"):
            return f"{action_type}: {action.get('path') or '(unknown path)'}"
        if action_type in ("dispatch_task", "plan_task", "complete_task"):
            return f"{action_type}: task #{action.get('task_id')}"
    return action_plan.get("summary") or ""

def runtime_effect_final_status(state, verification_run_ids, write_run_ids, processed_count):
    if processed_count == 0:
        return "skipped"
    writes = [
        run
        for run in state.get("write_runs", [])
        if run.get("id") in set(write_run_ids or [])
    ]
    if any(run.get("rolled_back") for run in writes):
        return "recovered"
    if any(run.get("verification_exit_code") not in (None, 0) for run in writes):
        return "failed"
    verifications = [
        run
        for run in state.get("verification_runs", [])
        if run.get("id") in set(verification_run_ids or [])
    ]
    if any(run.get("exit_code") not in (None, 0) for run in verifications):
        return "failed"
    if verification_run_ids:
        return "verified"
    return "applied"

def precompute_runtime_action_effects(
    event_snapshot,
    action_plan,
    args,
    autonomy_controls,
):
    if not action_plan:
        return action_plan
    for action in action_plan.get("actions", []):
        if not runtime_action_effect_needs_precompute(
            event_snapshot,
            action,
            args,
            autonomy_controls,
        ):
            continue
        try:
            action["_precomputed_verification"] = run_command_record(
                args.verify_command,
                cwd=".",
                timeout=args.verify_timeout,
            )
        except ValueError as exc:
            action["_precomputed_verification_error"] = str(exc)
    return action_plan

def runtime_action_effect_needs_precompute(event_snapshot, action, args, autonomy_controls):
    if action.get("type") != "run_verification":
        return False
    allowed_by_mode = event_snapshot.get("type") == "user_message" or (
        autonomy_controls["autonomous"]
        and autonomy_controls["autonomy_level"] == "act"
    )
    return bool(allowed_by_mode and args.allow_verify and args.verify_command)

def action_plan_needs_runtime_precompute(event_snapshot, action_plan, args, autonomy_controls):
    if not action_plan:
        return False
    return any(
        runtime_action_effect_needs_precompute(event_snapshot, action, args, autonomy_controls)
        for action in action_plan.get("actions", [])
    )

def should_defer_commit_for_user_message(state, reason, precomputed_effects=False):
    if reason == "user_input":
        return False
    if precomputed_effects:
        return False
    return has_pending_user_message(state)

def run_runtime_post_run_pipeline(state, args, autonomy_controls):
    return sweep_agent_runs(
        state,
        collect=True,
        start_reviews=bool(
            autonomy_controls.get("allow_agent_run")
            and autonomy_controls.get("autonomy_level") == "act"
        ),
        followup=bool(
            autonomy_controls.get("autonomous")
            and autonomy_controls.get("autonomy_level") in ("propose", "act")
        ),
        stale_minutes=getattr(args, "agent_stale_minutes", 60.0),
        dry_run=False,
        review_model=getattr(args, "review_model", None),
        result_timeout=getattr(args, "agent_result_timeout", 10.0),
        start_timeout=getattr(args, "agent_start_timeout", 30.0),
    )

def guidance_with_runtime_focus(guidance, focus):
    focus_text = str(focus or "").strip()
    if not focus_text:
        return guidance
    return "\n\n".join(
        part
        for part in (
            str(guidance or "").strip(),
            (
                "Immediate runtime focus:\n"
                f"{focus_text}\n"
                "Prefer this focus over unrelated existing tasks or questions during this runtime. "
                "Do not stop solely because an unrelated older question is waiting."
            ),
        )
        if part
    )

def compact_agent_reflex_value(value, limit=5, depth=0):
    if isinstance(value, list):
        items = value[-limit:]
        return [compact_agent_reflex_value(item, limit=limit, depth=depth + 1) for item in items]
    if isinstance(value, dict):
        if depth >= 2:
            return {"omitted": "nested reflex detail"}
        return {
            key: compact_agent_reflex_value(child, limit=limit, depth=depth + 1)
            for key, child in value.items()
            if key != "last_agent_reflex_report"
        }
    if isinstance(value, str) and len(value) > 500:
        return value[:500] + "...<truncated>"
    return value

def compact_agent_reflex_report(report, limit=5):
    compact = {}
    for key, value in (report or {}).items():
        compact[key] = compact_agent_reflex_value(value, limit=limit)
        if isinstance(value, list):
            omitted = max(0, len(value) - limit)
            if omitted:
                compact[f"{key}_omitted"] = omitted
    return compact

def pending_external_event(state):
    return any(
        not event.get("processed_at")
        and event.get("type") not in ("startup", "passive_tick", "user_message")
        for event in state.get("inbox", [])
    )

def next_external_event(state):
    for event in state.get("inbox", []):
        if event.get("processed_at"):
            continue
        if event.get("type") in ("startup", "passive_tick", "user_message"):
            continue
        return event
    return None

def outbox_notification_env(message):
    return {
        "MEW_OUTBOX_ID": str(message.get("id") or ""),
        "MEW_OUTBOX_TYPE": str(message.get("type") or ""),
        "MEW_OUTBOX_TEXT": str(message.get("text") or ""),
        "MEW_OUTBOX_REQUIRES_REPLY": "1" if message.get("requires_reply") else "0",
        "MEW_OUTBOX_EVENT_ID": str(message.get("event_id") or ""),
        "MEW_OUTBOX_RELATED_TASK_ID": str(message.get("related_task_id") or ""),
        "MEW_OUTBOX_QUESTION_ID": str(message.get("question_id") or ""),
        "MEW_OUTBOX_AGENT_RUN_ID": str(message.get("agent_run_id") or ""),
        "MEW_OUTBOX_ATTENTION_ID": str(message.get("attention_id") or ""),
    }

def notify_outbox_messages(messages, args):
    if not messages:
        return []
    if getattr(args, "notify_bell", False):
        print("\a", end="", flush=True)
    command = getattr(args, "notify_command", "") or ""
    if not command:
        return []
    records = []
    for message in messages:
        record = run_command_record(
            command,
            cwd=".",
            timeout=getattr(args, "notify_timeout", 5.0),
            extra_env=outbox_notification_env(message),
        )
        records.append(record)
    return records

def run_runtime(args):
    model_auth = None
    try:
        model_backend = normalize_model_backend(args.model_backend)
    except MewError as exc:
        print(f"mew: {exc}", file=sys.stderr)
        return 1
    model = args.model or model_backend_default_model(model_backend)
    base_url = args.base_url or model_backend_default_base_url(model_backend)
    ensure_guidance(args.guidance)
    ensure_policy(args.policy)
    if args.autonomous:
        ensure_self(args.self_file)
        ensure_desires(args.desires)
    initial_guidance = guidance_with_runtime_focus(read_guidance(args.guidance), args.focus)
    initial_policy = read_policy(args.policy)
    initial_self = read_self(args.self_file)
    initial_desires = read_desires(args.desires)
    if args.ai:
        try:
            model_auth = load_model_auth(model_backend, args.auth)
        except MewError as exc:
            print(f"mew: {exc}", file=sys.stderr)
            return 1

    try:
        lock = acquire_lock()
    except RuntimeError as exc:
        print(f"mew: {exc}", file=sys.stderr)
        return 1

    stop_requested = {"value": False}

    def request_stop(signum, frame):
        stop_requested["value"] = True

    previous_sigint = signal.signal(signal.SIGINT, request_stop)
    previous_sigterm = signal.signal(signal.SIGTERM, request_stop)

    try:
        startup_repairs = []
        with state_lock():
            state = load_state()
            set_runtime_running(state, lock["started_at"])
            startup_repairs = repair_runtime_startup_state(state, current_time=lock["started_at"])
            save_state(state)
        append_log(f"## {lock['started_at']}: runtime started pid={os.getpid()}")
        print(f"mew runtime started pid={os.getpid()} state={STATE_FILE}")
        if startup_repairs:
            print(f"startup repaired {len(startup_repairs)} interrupted item(s)")
        if model_auth:
            print(
                f"{model_backend_label(model_backend)} enabled "
                f"auth={model_auth['path']} model={model} base_url={base_url}"
            )
        if initial_guidance:
            guidance_path = args.guidance or str(GUIDANCE_FILE)
            print(f"guidance loaded path={guidance_path}")
        if args.focus:
            print(f"runtime focus: {args.focus}")
        if initial_policy:
            policy_path = args.policy or str(POLICY_FILE)
            print(f"policy loaded path={policy_path}")
        if initial_self:
            self_path = args.self_file or str(SELF_FILE)
            print(f"self loaded path={self_path}")
        if initial_desires:
            desires_path = args.desires or str(DESIRES_FILE)
            print(f"desires loaded path={desires_path}")
        if args.autonomous:
            print(f"autonomous mode enabled level={args.autonomy_level}")
        if args.allow_agent_run:
            print("autonomous agent runs allowed")
        if getattr(args, "allow_native_work", False):
            print("autonomous native work sessions allowed")
        if getattr(args, "allow_native_advance", False):
            print("autonomous native work advance allowed")
        if args.allow_verify:
            print("runtime verification allowed")
            if args.verify_command:
                print(f"verify command: {args.verify_command}")
        if args.allow_read:
            print("read-only inspection allowed under:")
            for path in args.allow_read:
                print(f"- {path}")
        if args.allow_write:
            print("gated writes allowed under:")
            for path in args.allow_write:
                print(f"- {path}")

        first = True
        next_passive_at = time.time() + args.interval
        while not stop_requested["value"]:
            sleep_for = None
            processed_count = None
            processing_counts = {"actions": 0, "messages": 0, "executed": 0, "waits": 0}
            new_outbox_messages = []
            archive_result = None
            reason = None
            event_id = None
            effect_id = None
            effect_summary = ""
            event_snapshot = None
            state_snapshot = None
            decision_plan = None
            action_plan = None
            native_work_step = None
            native_recovery_step = None
            precomputed_effects = False
            current_time = None
            cycle_started_monotonic = None
            allow_task_execution = False
            guidance = ""
            policy = ""
            self_text = ""
            desires = ""
            autonomy_controls = {
                "autonomous": False,
                "autonomy_level": "off",
                "allow_agent_run": False,
                "allow_native_work": False,
                "allow_native_advance": False,
            }
            outbox_ids_before = set()
            with state_lock():
                state = load_state()
                if state["runtime_status"].get("state") != "running":
                    set_runtime_running(state, lock["started_at"])
                pending_user = has_pending_user_message(state)
                pending_external = pending_external_event(state)
                current_monotonic = time.time()
                if pending_user:
                    reason = "user_input"
                    create_internal_event = False
                elif pending_external:
                    reason = "external_event"
                    create_internal_event = False
                elif first and not getattr(args, "passive_now", False):
                    reason = "startup"
                    create_internal_event = True
                elif (first and getattr(args, "passive_now", False)) or current_monotonic >= next_passive_at:
                    reason = "passive_tick"
                    create_internal_event = True
                else:
                    sleep_for = min(args.poll_interval, max(0.0, next_passive_at - current_monotonic))

                if sleep_for is None:
                    allow_task_execution = args.execute_tasks and not pending_user
                    current_time = now_iso()
                    cycle_started_monotonic = time.monotonic()
                    runtime_status = state["runtime_status"]
                    runtime_status["current_reason"] = reason
                    runtime_status["cycle_started_at"] = current_time
                    runtime_status["last_action"] = f"processing {reason}"
                    autonomy_controls = apply_runtime_autonomy_controls(
                        state,
                        args,
                        pending_user,
                        current_time,
                    )
                    outbox_ids_before = {str(message.get("id")) for message in state.get("outbox", [])}
                    reflex_report = run_runtime_post_run_pipeline(state, args, autonomy_controls)
                    runtime_status["last_agent_reflex_at"] = current_time
                    runtime_status["last_agent_reflex_report"] = compact_agent_reflex_report(reflex_report)
                    if create_internal_event:
                        add_event(state, reason, "runtime", {"pid": os.getpid()})
                    if reason == "user_input":
                        event = next_unprocessed_event(state, "user_message")
                    elif reason == "external_event":
                        event = next_external_event(state)
                    else:
                        event = next_unprocessed_event(state)
                    if event:
                        event_id = event["id"]
                        effect = add_runtime_effect(state, event, reason, "planning", current_time)
                        effect_id = effect["id"]
                        event_snapshot = deepcopy(event)
                        state_snapshot = deepcopy(state)
                        runtime_status["current_event_id"] = event_id
                        runtime_status["current_effect_id"] = effect_id
                        runtime_status["current_phase"] = "planning"
                    save_state(state)

            if sleep_for is not None:
                time.sleep(sleep_for)
                continue

            guidance = guidance_with_runtime_focus(read_guidance(args.guidance), args.focus)
            policy = read_policy(args.policy)
            self_text = read_self(args.self_file)
            desires = read_desires(args.desires)

            if event_snapshot and state_snapshot:
                decision_plan, action_plan = plan_runtime_event(
                    state_snapshot,
                    event_snapshot,
                    current_time,
                    model_auth,
                    model,
                    base_url,
                    model_backend,
                    args,
                    allow_task_execution,
                    guidance,
                    policy,
                    self_text,
                    desires,
                    autonomy_controls,
                )
                with state_lock():
                    state = load_state()
                    event = find_event(state, event_id)
                    effect = find_runtime_effect(state, effect_id)
                    if effect and event and not event.get("processed_at"):
                        update_runtime_effect(
                            state,
                            effect_id,
                            current_time=now_iso(),
                            status="planned",
                            summary=(decision_plan or {}).get("summary")
                            or (action_plan or {}).get("summary")
                            or "",
                            outcome=runtime_effect_outcome_for_plan(action_plan),
                            action_types=action_types_for_plan(action_plan),
                        )
                        save_state(state)
                if action_plan_needs_runtime_precompute(
                    event_snapshot,
                    action_plan,
                    args,
                    autonomy_controls,
                ):
                    with state_lock():
                        state = load_state()
                        event = find_event(state, event_id)
                        if not event or event.get("processed_at"):
                            action_plan = None
                            complete_runtime_effect(
                                state,
                                effect_id,
                                now_iso(),
                                "skipped",
                                processed_count=0,
                                counts={},
                            )
                            save_state(state)
                        else:
                            state["runtime_status"]["current_phase"] = "precomputing"
                            update_runtime_effect(
                                state,
                                effect_id,
                                current_time=now_iso(),
                                status="precomputing",
                            )
                            save_state(state)
                    if action_plan is not None:
                        action_plan = precompute_runtime_action_effects(
                            event_snapshot,
                            action_plan,
                            args,
                            autonomy_controls,
                        )
                        precomputed_effects = True
                        with state_lock():
                            state = load_state()
                            event = find_event(state, event_id)
                            if event and not event.get("processed_at"):
                                update_runtime_effect(
                                    state,
                                    effect_id,
                                    current_time=now_iso(),
                                    status="precomputed",
                                )
                                save_state(state)

            with state_lock():
                state = load_state()
                if event_id is not None and decision_plan is not None and action_plan is not None:
                    commit_time = now_iso()
                    state["runtime_status"]["current_phase"] = "committing"
                    update_runtime_effect(
                        state,
                        effect_id,
                        current_time=commit_time,
                        status="committing",
                    )
                    save_state(state)
                    if should_defer_commit_for_user_message(
                        state,
                        reason,
                        precomputed_effects=precomputed_effects,
                    ):
                        processed_count = 0
                        complete_runtime_effect(
                            state,
                            effect_id,
                            commit_time,
                            "deferred",
                            processed_count=0,
                            counts={},
                            deferred=True,
                        )
                        append_log(
                            "- "
                            f"{commit_time}: deferred {reason} commit because a user message arrived"
                        )
                    else:
                        verification_ids_before = {
                            run.get("id") for run in state.get("verification_runs", [])
                        }
                        write_ids_before = {run.get("id") for run in state.get("write_runs", [])}
                        processed_count, processing_counts = apply_runtime_event_plans(
                            state,
                            event_id,
                            decision_plan,
                            action_plan,
                            commit_time,
                            reason,
                            args,
                            allow_task_execution,
                            autonomy_controls,
                            work_auth=(model_auth or {}).get("path") or "",
                            work_model_backend=model_backend,
                            work_model=model,
                            work_base_url=base_url,
                        )
                        verification_run_ids = [
                            run.get("id")
                            for run in state.get("verification_runs", [])
                            if run.get("id") not in verification_ids_before
                        ]
                        write_run_ids = [
                            run.get("id")
                            for run in state.get("write_runs", [])
                            if run.get("id") not in write_ids_before
                        ]
                        complete_runtime_effect(
                            state,
                            effect_id,
                            commit_time,
                            runtime_effect_final_status(
                                state,
                                verification_run_ids,
                                write_run_ids,
                                processed_count,
                            ),
                            processed_count=processed_count,
                            counts=processing_counts,
                            verification_run_ids=verification_run_ids,
                            write_run_ids=write_run_ids,
                        )
                else:
                    processed_count = 0
                    update_runtime_processing_summary(
                        state,
                        reason,
                        current_time,
                        0,
                        0,
                        0,
                        0,
                        autonomous=autonomy_controls["autonomous"],
                    )
                    if effect_id is not None:
                        complete_runtime_effect(
                            state,
                            effect_id,
                            now_iso(),
                            "skipped",
                            processed_count=0,
                            counts={},
                        )
                runtime_status = state["runtime_status"]
                runtime_status["current_reason"] = None
                runtime_status["current_event_id"] = None
                runtime_status["current_effect_id"] = None
                runtime_status["current_phase"] = None
                runtime_status["cycle_started_at"] = None
                runtime_status["last_cycle_reason"] = reason
                runtime_status["last_cycle_duration_seconds"] = round(
                    time.monotonic() - cycle_started_monotonic,
                    3,
                )
                runtime_status["last_processed_count"] = processed_count
                if args.auto_archive:
                    archive_result = archive_state_records(
                        state,
                        keep_recent=args.archive_keep_recent,
                        dry_run=False,
                    )
                    if archive_result.get("total_archived"):
                        append_log(
                            "- "
                            f"{now_iso()}: archived {archive_result['total_archived']} record(s) "
                            f"path={archive_result.get('archive_path')}"
                        )
                if getattr(args, "echo_effects", False) and effect_id is not None:
                    effect = find_runtime_effect(state, effect_id)
                    if effect:
                        action_types = ",".join(effect.get("action_types") or []) or "-"
                        summary = effect.get("summary") or ""
                        outcome = effect.get("outcome") or ""
                        effect_summary = (
                            f"effect #{effect.get('id')} [{effect.get('status')}] "
                            f"event=#{effect.get('event_id')} reason={effect.get('reason')} "
                            f"actions={action_types}"
                        )
                        if summary:
                            effect_summary = f"{effect_summary} summary={summary}"
                        if outcome and outcome != summary:
                            effect_summary = f"{effect_summary} outcome={outcome}"
                if args.echo_outbox or getattr(args, "notify_bell", False) or getattr(args, "notify_command", ""):
                    new_outbox_messages = [
                        message
                        for message in state.get("outbox", [])
                        if str(message.get("id")) not in outbox_ids_before
                        and not message.get("read_at")
                    ]
                if (
                    reason == "passive_tick"
                    and processed_count
                    and autonomy_controls.get("allow_native_advance")
                ):
                    native_work_step, native_work_skip = select_runtime_native_work_step(
                        state,
                        current_event_id=event_id,
                    )
                    native_skip_time = now_iso()
                    native_skip_recovery = native_work_skip_recovery_suggestion(
                        state,
                        native_work_skip,
                    )
                    record_runtime_native_work_step_skip(
                        runtime_status,
                        native_work_skip,
                        current_time=native_skip_time,
                        event_id=event_id,
                        phase="select",
                        recovery=native_skip_recovery,
                    )
                    if native_work_skip == "previous_native_work_step_failed":
                        native_recovery_step = prepare_runtime_native_work_tool_recovery(
                            state,
                            args,
                            event_id=event_id,
                            current_time=native_skip_time,
                        )
                        if native_recovery_step is None:
                            recover_previous_native_work_step_failure(
                                state,
                                event_id=event_id,
                                current_time=native_skip_time,
                            )
                    if native_work_step:
                        runtime_status["last_action"] = (
                            f"selected native work step for session #{native_work_step.get('session_id')}"
                        )
                save_state(state)
                first = False
                if reason in ("startup", "passive_tick"):
                    next_passive_at = time.time() + args.interval

            print(f"processed {processed_count} event(s) reason={reason}")
            if native_recovery_step:
                print(
                    "recovering native work tool "
                    f"session=#{native_recovery_step.get('session_id')} "
                    f"task=#{native_recovery_step.get('task_id')}"
                )
                recovery_batch = run_runtime_native_work_recovery_steps(native_recovery_step, args)
                for recovery_step, recovery_result in zip(
                    recovery_batch.get("steps") or [],
                    recovery_batch.get("results") or [],
                ):
                    if recovery_result.get("error"):
                        append_log(
                            "- "
                            f"{now_iso()}: native work tool recovery failed "
                            f"session={recovery_step.get('session_id')} "
                            f"error={recovery_result.get('error')!r}"
                        )
                    else:
                        append_log(
                            "- "
                            f"{now_iso()}: native work tool recovery completed "
                            f"session={recovery_step.get('session_id')} "
                            f"task={recovery_step.get('task_id')}"
                        )
            if native_work_step:
                print(
                    "advancing native work "
                    f"session=#{native_work_step.get('session_id')} task=#{native_work_step.get('task_id')}"
                )
                native_result = run_runtime_native_work_step(native_work_step, args)
                if native_result.get("skipped"):
                    append_log(
                        "- "
                        f"{now_iso()}: native work advance skipped "
                        f"session={native_work_step.get('session_id')} "
                        f"reason={native_result.get('skip_reason')}"
                    )
                elif native_result.get("exit_code") in (0,):
                    append_log(
                        "- "
                        f"{now_iso()}: native work advance completed "
                        f"session={native_work_step.get('session_id')} "
                        f"task={native_work_step.get('task_id')}"
                    )
                else:
                    append_log(
                        "- "
                        f"{now_iso()}: native work advance failed "
                        f"session={native_work_step.get('session_id')} "
                        f"exit_code={native_result.get('exit_code')} "
                        f"stderr={native_result.get('stderr')!r}"
                    )
            if effect_summary:
                print(effect_summary)
            if args.echo_outbox:
                for message in new_outbox_messages:
                    text = str(message.get("text") or "").replace("\n", "\n  ")
                    print(f"outbox #{message.get('id')} [{message.get('type')}]: {text}")
            notification_records = notify_outbox_messages(new_outbox_messages, args)
            for record in notification_records:
                if record.get("exit_code") not in (0,):
                    append_log(
                        "- "
                        f"{now_iso()}: notify command failed "
                        f"exit_code={record.get('exit_code')} stderr={record.get('stderr')!r}"
                    )
            if archive_result and archive_result.get("total_archived"):
                print(
                    "archived "
                    f"{archive_result['total_archived']} record(s) "
                    f"path={archive_result.get('archive_path')}"
                )

            if args.once:
                break
            if processing_counts.get("actions") or processing_counts.get("messages"):
                continue
    finally:
        stopped_at = now_iso()
        with state_lock():
            state = load_state()
            set_runtime_stopped(state, stopped_at)
            save_state(state)
        release_lock()
        append_log(f"## {stopped_at}: runtime stopped pid={os.getpid()}")
        signal.signal(signal.SIGINT, previous_sigint)
        signal.signal(signal.SIGTERM, previous_sigterm)
        print("mew runtime stopped")

    return 0
