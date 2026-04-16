import json
import os
import select
import shlex
import signal
import shutil
import socket
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, unquote, urlparse

from .agent_runs import (
    build_ai_cli_run_command,
    create_agent_run,
    ensure_agent_run_prompt_file,
    find_agent_run,
    get_agent_run_result,
    start_agent_run,
    wait_agent_run,
)
from .archive import archive_state_records, format_archive_result
from .brief import (
    build_activity_data,
    build_brief,
    build_brief_data,
    build_focus_data,
    format_activity,
    format_focus,
    next_move,
    verification_outcome,
)
from .codex_api import load_codex_oauth
from .config import DEFAULT_MODEL_BACKEND, EFFECT_LOG_FILE, LOG_FILE, STATE_DIR
from .context import build_context
from .dogfood import (
    format_dogfood_loop_report,
    format_dogfood_report,
    format_dogfood_scenario_report,
    run_dogfood,
    run_dogfood_loop,
    run_dogfood_scenario,
)
from .errors import MewError
from .memory import add_deep_memory, compact_memory, search_memory
from .model_backends import (
    load_model_auth,
    model_backend_default_base_url,
    model_backend_default_model,
    normalize_model_backend,
)
from .model_trace import read_model_traces
from .perception import format_perception, perceive_workspace
from .project_snapshot import format_project_snapshot, format_snapshot_refresh_report, refresh_project_snapshot
from .programmer import (
    acknowledge_review_followup,
    create_follow_up_task_from_review,
    create_implementation_run_from_plan,
    create_retry_run_for_implementation,
    create_review_run_for_implementation,
    create_task_plan,
    find_active_implementation_run_for_plan,
    find_task_plan,
    format_task_plan,
    latest_task_plan,
)
from .self_improve import create_self_improve_task, ensure_self_improve_plan
from .state import (
    add_attention_item,
    add_outbox_message,
    add_question,
    add_event,
    ensure_desires,
    ensure_guidance,
    ensure_policy,
    ensure_self,
    ensure_state_dir,
    find_question,
    incomplete_runtime_effects,
    is_routine_outbox_message,
    load_state,
    mark_message_read,
    mark_question_deferred,
    mark_question_answered,
    next_id,
    open_attention_items,
    open_questions,
    pid_alive,
    read_desires,
    read_guidance,
    read_policy,
    read_self,
    reopen_question,
    read_lock,
    read_last_state_effect,
    reconcile_next_ids,
    record_user_reported_verification,
    resolve_open_questions_for_task,
    save_state,
    state_digest,
    state_lock,
    update_runtime_effect,
)
from .sweep import format_sweep_report, sweep_agent_runs
from .step_loop import format_step_loop_report, run_step_loop
from .read_tools import glob_paths, inspect_dir, read_file, search_text, summarize_read_result
from .tasks import (
    clip_output,
    find_task,
    format_task,
    is_programmer_task,
    normalize_task_kind,
    open_tasks,
    task_kind,
    task_kind_report,
    task_question,
    task_sort_key,
)
from .thoughts import format_thought_entry
from .timeutil import now_iso
from .toolbox import format_command_record, run_command_record, run_git_tool
from .validation import format_validation_issues, validate_state, validation_errors
from .write_tools import edit_file, summarize_write_result, write_file
from .work_session import (
    active_work_session,
    add_work_session_note,
    build_work_session_resume,
    close_work_session,
    consume_work_session_stop,
    create_work_session,
    execute_work_tool,
    find_work_session,
    find_work_tool_call,
    finish_work_model_turn,
    finish_work_tool_call,
    format_work_action,
    format_work_session_resume,
    format_work_session,
    latest_work_verify_command,
    mark_running_work_interrupted,
    request_work_session_stop,
    start_work_model_turn,
    work_tool_result_error,
    start_work_tool_call,
    update_work_model_turn_plan,
    GIT_WORK_TOOLS,
    READ_ONLY_WORK_TOOLS,
    WORK_TOOLS,
    work_session_task,
)
from .work_loop import plan_work_model_turn, work_tool_parameters_from_action
from .work_world import build_work_world_state


RESERVED_EVENT_TYPES = {"startup", "passive_tick", "tick", "user_message"}


def cmd_task_add(args):
    with state_lock():
        state = load_state()
        current_time = now_iso()
        task = {
            "id": next_id(state, "task"),
            "title": args.title,
            "kind": args.kind or "",
            "description": args.description or "",
            "status": "ready" if getattr(args, "ready", False) else "todo",
            "priority": args.priority,
            "notes": args.notes or "",
            "command": args.command or "",
            "cwd": args.cwd or "",
            "auto_execute": args.auto_execute,
            "agent_backend": args.agent_backend or "",
            "agent_model": args.agent_model or "",
            "agent_prompt": args.agent_prompt or "",
            "agent_run_id": None,
            "plans": [],
            "latest_plan_id": None,
            "runs": [],
            "created_at": current_time,
            "updated_at": current_time,
        }
        state["tasks"].append(task)
        save_state(state)
    print(format_task(task))
    return 0

def cmd_task_list(args):
    state = load_state()
    tasks = state["tasks"] if getattr(args, "all", False) else open_tasks(state)
    if getattr(args, "kind", None):
        tasks = [task for task in tasks if task_kind(task) == args.kind]
    tasks = sorted(tasks, key=task_sort_key)
    if not tasks:
        print("No tasks.")
        return 0
    for task in tasks:
        print(format_task(task))
    return 0

def format_task_kind_report(report):
    marker = " mismatch" if report.get("mismatch") else ""
    stored = report.get("stored_kind") or "-"
    return (
        f"#{report.get('id')} [{report.get('status')}] "
        f"effective={report.get('effective_kind')} stored={stored} "
        f"inferred={report.get('inferred_kind')}{marker} {report.get('title')}"
    )

def cmd_task_classify(args):
    if args.apply and args.clear:
        print("mew: choose only one of --apply or --clear", file=sys.stderr)
        return 1
    with state_lock():
        state = load_state()
        if args.task_id:
            task = find_task(state, args.task_id)
            if not task:
                print(f"mew: task not found: {args.task_id}", file=sys.stderr)
                return 1
            tasks = [task]
        else:
            tasks = state["tasks"] if args.all else open_tasks(state)

        tasks = sorted(tasks, key=task_sort_key)
        reports = [task_kind_report(task) for task in tasks]
        if args.mismatches:
            pairs = [(task, report) for task, report in zip(tasks, reports) if report.get("mismatch")]
            tasks = [task for task, _report in pairs]
            reports = [report for _task, report in pairs]

        changed = []
        if args.clear or args.apply:
            for task, report in zip(tasks, reports):
                current = task.get("kind") or ""
                if args.clear:
                    if current:
                        task["kind"] = ""
                        task["updated_at"] = now_iso()
                        changed.append(task)
                    continue
                inferred = report.get("inferred_kind") or "unknown"
                if inferred == "unknown" and not args.include_unknown:
                    continue
                if current != inferred:
                    task["kind"] = inferred
                    task["updated_at"] = now_iso()
                    changed.append(task)
            if changed:
                save_state(state)
            reports = [task_kind_report(task) for task in tasks]

    if args.json:
        print(json.dumps({"tasks": reports, "changed": [task.get("id") for task in changed]}, ensure_ascii=False, indent=2))
        return 0
    if not reports:
        print("No tasks.")
        return 0
    for report in reports:
        print(format_task_kind_report(report))
    if args.clear or args.apply:
        print(f"changed {len(changed)} task(s)")
    return 0

def cmd_task_show(args):
    state = load_state()
    task = find_task(state, args.task_id)
    if not task:
        print(f"mew: task not found: {args.task_id}", file=sys.stderr)
        return 1

    print(format_task(task))
    print(f"description: {task.get('description') or ''}")
    print(f"kind: {task_kind(task)}")
    print(f"kind_override: {task.get('kind') or ''}")
    print(f"notes: {task.get('notes') or ''}")
    print(f"command: {task.get('command') or ''}")
    print(f"cwd: {task.get('cwd') or ''}")
    print(f"auto_execute: {task.get('auto_execute')}")
    print(f"agent_backend: {task.get('agent_backend') or ''}")
    print(f"agent_model: {task.get('agent_model') or ''}")
    print(f"agent_prompt: {task.get('agent_prompt') or ''}")
    print(f"agent_run_id: {task.get('agent_run_id') or ''}")
    print(f"latest_plan_id: {task.get('latest_plan_id') or ''}")
    print(f"plans: {len(task.get('plans') or [])}")
    print(f"runs: {len(task.get('runs') or [])}")
    print(f"created_at: {task.get('created_at')}")
    print(f"updated_at: {task.get('updated_at')}")
    return 0

def _latest_agent_run_for_task(state, task_id, purpose=None):
    wanted = str(task_id)
    for run in reversed(state.get("agent_runs", [])):
        if str(run.get("task_id")) != wanted:
            continue
        if purpose and run.get("purpose", "implementation") != purpose:
            continue
        return run
    return None


def _review_for_run(state, run_id):
    wanted = str(run_id)
    for run in reversed(state.get("agent_runs", [])):
        if run.get("purpose") == "review" and str(run.get("review_of_run_id")) == wanted:
            return run
    return None


def build_workbench_data(state, task):
    task_id = task.get("id")
    effective_kind = task_kind(task)
    task_data = dict(task)
    task_data["kind"] = effective_kind
    plan = latest_task_plan(task)
    agent_runs = [
        run for run in state.get("agent_runs", [])
        if str(run.get("task_id")) == str(task_id)
    ][-8:]
    verification_runs = [
        run for run in state.get("verification_runs", [])
        if str(run.get("task_id")) == str(task_id)
    ][-5:]
    write_runs = [
        run for run in state.get("write_runs", [])
        if str(run.get("task_id")) == str(task_id)
    ][-5:]
    questions = [
        question for question in state.get("questions", [])
        if str(question.get("related_task_id")) == str(task_id)
        and question.get("status") == "open"
    ]
    latest_implementation = _latest_agent_run_for_task(state, task_id, purpose="implementation")
    latest_review = (
        _review_for_run(state, latest_implementation.get("id"))
        if latest_implementation
        else None
    )
    work_session = None
    for session in reversed(state.get("work_sessions", [])):
        if str(session.get("task_id")) == str(task_id) and session.get("status") == "active":
            work_session = session
            break

    next_action = "mew task show {task_id}".format(task_id=task_id)
    if task.get("status") == "done":
        next_action = "wait for the next user request"
    elif questions:
        next_action = f"mew reply {questions[0]['id']} \"...\""
    elif not is_programmer_task(task):
        next_action = f"mew task update {task_id} --kind coding"
    elif work_session:
        next_action = f"mew work {task_id} --live --allow-read . --max-steps 1"
    elif not plan:
        next_action = f"mew work {task_id} --start-session"
    elif not latest_implementation:
        next_action = f"mew work {task_id} --start-session"
    elif latest_implementation.get("status") in ("created", "running"):
        next_action = f"mew agent wait {latest_implementation['id']}"
    elif latest_implementation.get("status") == "dry_run":
        next_action = f"mew buddy --task {task_id} --dispatch"
    elif latest_implementation.get("status") == "failed":
        next_action = f"mew agent retry {latest_implementation['id']} --dry-run"
    elif latest_implementation.get("status") == "completed" and not latest_review:
        next_action = f"mew agent review {latest_implementation['id']}"
    elif latest_review and latest_review.get("status") in ("created", "running"):
        next_action = f"mew agent wait {latest_review['id']}"
    elif latest_review and latest_review.get("status") == "completed" and not latest_review.get("followup_processed_at"):
        next_action = f"mew agent followup {latest_review['id']}"

    return {
        "task": task_data,
        "kind": effective_kind,
        "plan": plan,
        "agent_runs": agent_runs,
        "verification_runs": verification_runs,
        "write_runs": write_runs,
        "open_questions": questions,
        "work_session": work_session,
        "next_action": next_action,
    }


def format_workbench(data):
    task = data["task"]
    lines = [
        f"Work task #{task.get('id')}: {task.get('title')}",
        format_task(task),
        f"kind: {data.get('kind')}",
        f"description: {task.get('description') or ''}",
        f"cwd: {task.get('cwd') or ''}",
        "",
        "Plan",
    ]
    plan = data.get("plan")
    if plan:
        lines.append(format_task_plan(plan))
        lines.append(f"objective: {plan.get('objective') or ''}")
        lines.append(f"approach: {plan.get('approach') or ''}")
    else:
        lines.append("(none)")

    lines.append("")
    lines.append("Agent runs")
    if data.get("agent_runs"):
        for run in data["agent_runs"]:
            purpose = run.get("purpose", "implementation")
            lines.append(
                f"#{run.get('id')} [{run.get('status')}/{purpose}] "
                f"plan={run.get('plan_id') or ''} model={run.get('model') or ''}"
            )
    else:
        lines.append("(none)")

    lines.append("")
    lines.append("Verification")
    if data.get("verification_runs"):
        for run in data["verification_runs"]:
            outcome = verification_outcome(run)
            lines.append(f"#{run.get('id')} [{outcome}] {run.get('command') or ''}")
    else:
        lines.append("(none)")

    lines.append("")
    lines.append("Writes")
    if data.get("write_runs"):
        for run in data["write_runs"]:
            lines.append(
                f"#{run.get('id')} [{run.get('operation') or 'write'}] "
                f"{run.get('path') or ''} changed={bool(run.get('changed'))} "
                f"rolled_back={bool(run.get('rolled_back'))}"
            )
    else:
        lines.append("(none)")

    lines.append("")
    lines.append("Work session")
    if data.get("work_session"):
        session = data["work_session"]
        tool_calls = session.get("tool_calls") or []
        model_turns = session.get("model_turns") or []
        resume = build_work_session_resume(session, task=task)
        lines.append(
            f"#{session.get('id')} [{session.get('status')}] "
            f"phase={(resume or {}).get('phase') or 'unknown'} "
            f"model_turns={len(model_turns)} tool_calls={len(tool_calls)} "
            f"last_tool=#{session.get('last_tool_call_id') or ''}"
        )
    else:
        lines.append("(none)")

    lines.append("")
    lines.append("Open questions")
    if data.get("open_questions"):
        for question in data["open_questions"]:
            lines.append(f"#{question.get('id')} {question.get('text') or ''}")
    else:
        lines.append("(none)")

    lines.append("")
    lines.append("Next action")
    lines.append(data.get("next_action") or "")
    return "\n".join(lines)


def select_workbench_task(state, task_id=None):
    task = find_task(state, task_id) if task_id else None
    if task or task_id:
        return task
    candidates = sorted(open_tasks(state), key=task_sort_key)
    running_tasks = [task for task in candidates if task.get("status") == "running"]
    if running_tasks:
        return running_tasks[0]
    active_task_id = state.get("agent_status", {}).get("active_task_id")
    task = find_task(state, active_task_id) if active_task_id else None
    if task:
        return task
    return candidates[0] if candidates else None


def select_work_ai_task(state, task_id=None):
    if task_id:
        return select_workbench_task(state, task_id)
    session = active_work_session(state)
    task = work_session_task(state, session)
    if task:
        return task
    return select_workbench_task(state)


def format_work_ai_report(report):
    lines = [
        f"mew work ai: {len(report.get('steps') or [])}/{report.get('max_steps')} step(s) "
        f"stop={report.get('stop_reason')}",
        f"session=#{report.get('session_id')} task=#{report.get('task_id')}",
    ]
    for step in report.get("steps") or []:
        action = step.get("action") or {}
        tool_call = step.get("tool_call") or {}
        tool_calls = step.get("tool_calls") or []
        status = step.get("status") or tool_call.get("status") or "unknown"
        action_type = action.get("type") or "unknown"
        line = f"#{step.get('index')} [{status}] {action_type}"
        if tool_call:
            line += f" tool_call=#{tool_call.get('id')}"
        if tool_calls:
            line += " tool_calls=" + ",".join(f"#{call.get('id')}" for call in tool_calls)
        if step.get("outbox_message"):
            line += f" message=#{step['outbox_message'].get('id')}"
        if step.get("question"):
            line += f" question=#{step['question'].get('id')}"
        if step.get("error"):
            line += f" error={step.get('error')}"
        lines.append(line)
        summary = step.get("summary") or tool_call.get("summary") or ""
        if summary:
            lines.append(clip_output(summary, 1000))
    stop_request = report.get("stop_request") or {}
    if stop_request:
        lines.append(f"stop_request: {stop_request.get('reason') or 'stop requested'}")
    return "\n".join(lines)


def _work_control_options(args, session=None):
    defaults = (session or {}).get("default_options") or {}

    def option(name, fallback=None):
        value = defaults.get(name)
        if value not in (None, "", [], False):
            return value
        return getattr(args, name, fallback)

    return {
        "auth": option("auth"),
        "model_backend": option("model_backend"),
        "model": option("model"),
        "base_url": option("base_url"),
        "allow_read": list(option("allow_read", []) or []),
        "allow_write": list(option("allow_write", []) or []),
        "allow_shell": bool(option("allow_shell", False)),
        "allow_verify": bool(option("allow_verify", False)),
        "verify_command": option("verify_command", ""),
        "act_mode": option("act_mode"),
    }


def remember_work_session_default_options(session, args):
    if not session:
        return
    options = _work_control_options(args, session=None)
    session["default_options"] = {
        "auth": options.get("auth") or "",
        "model_backend": options.get("model_backend") or "",
        "model": options.get("model") or "",
        "base_url": options.get("base_url") or "",
        "allow_read": options.get("allow_read") or [],
        "allow_write": options.get("allow_write") or [],
        "allow_shell": bool(options.get("allow_shell")),
        "allow_verify": bool(options.get("allow_verify")),
        "verify_command": options.get("verify_command") or "",
        "act_mode": options.get("act_mode") or "",
    }


def work_chat_continue_options(session):
    options = (session or {}).get("default_options") or {}
    parts = []
    for key, flag in (
        ("auth", "--auth"),
        ("model_backend", "--model-backend"),
        ("model", "--model"),
        ("base_url", "--base-url"),
    ):
        if options.get(key):
            parts.extend([flag, options[key]])
    for root in options.get("allow_read") or []:
        parts.extend(["--allow-read", root])
    for root in options.get("allow_write") or []:
        parts.extend(["--allow-write", root])
    if options.get("allow_shell"):
        parts.append("--allow-shell")
    if options.get("allow_verify"):
        parts.append("--allow-verify")
    if options.get("verify_command"):
        parts.extend(["--verify-command", options["verify_command"]])
    if options.get("act_mode"):
        parts.extend(["--act-mode", options["act_mode"]])
    return shlex.join(parts)


def _work_live_continue_command(args, task_id, session=None):
    parts = ["mew", "work"]
    if task_id is not None:
        parts.append(str(task_id))
    parts.append("--live")
    options = _work_control_options(args, session=session)
    if options.get("auth"):
        parts.extend(["--auth", options["auth"]])
    if options.get("model_backend"):
        parts.extend(["--model-backend", options["model_backend"]])
    if options.get("model"):
        parts.extend(["--model", options["model"]])
    if options.get("base_url"):
        parts.extend(["--base-url", options["base_url"]])
    for root in options.get("allow_read") or ["."]:
        parts.extend(["--allow-read", root])
    for root in options.get("allow_write") or []:
        parts.extend(["--allow-write", root])
    if options.get("allow_shell"):
        parts.append("--allow-shell")
    if options.get("allow_verify"):
        parts.append("--allow-verify")
    if options.get("verify_command"):
        parts.extend(["--verify-command", options["verify_command"]])
    if options.get("act_mode"):
        parts.extend(["--act-mode", options["act_mode"]])
    parts.extend(["--max-steps", "1"])
    return shlex.join(parts)


def _work_resume_command(args, task_id, session=None):
    parts = ["mew", "work"]
    if task_id is not None:
        parts.append(str(task_id))
    parts.extend(["--session", "--resume"])
    options = _work_control_options(args, session=session)
    for root in options.get("allow_read") or ["."]:
        parts.extend(["--allow-read", root])
    return shlex.join(parts)


def work_cli_control_commands(session, args):
    if not session:
        return ["mew work <task-id> --start-session"]
    task_id = session.get("task_id")
    if session.get("status") != "active":
        return [_work_resume_command(args, task_id, session=session), f"mew work {task_id} --start-session"]
    return [
        _work_live_continue_command(args, task_id, session=session),
        f"mew work {task_id} --stop-session --stop-reason pause",
        _work_resume_command(args, task_id, session=session),
        "mew chat",
    ]


def format_work_cli_controls(session, args):
    lines = ["", "Next CLI controls"]
    lines.extend(work_cli_control_commands(session, args))
    return "\n".join(lines)


def _work_control_text(action, fallback):
    for key in ("text", "note", "question", "reason", "summary"):
        value = (action or {}).get(key)
        if value:
            return str(value)
    return fallback


def apply_work_control_action(state, session, task, action):
    action = action or {}
    action_type = action.get("type") or ""
    task_id = task.get("id") if task else None
    if action_type == "finish":
        note = _work_control_text(action, "Work session finished.")
        if session:
            close_work_session(session)
        if task is not None:
            append_task_note(task, f"Work session finished: {note}")
            task["updated_at"] = now_iso()
        return {"finished_note": note}
    if action_type == "send_message":
        message_type = action.get("message_type") or "assistant"
        if message_type not in ("assistant", "info", "warning"):
            message_type = "assistant"
        message = add_outbox_message(
            state,
            message_type,
            _work_control_text(action, "Work session has an update."),
            related_task_id=task_id,
        )
        return {"outbox_message": message}
    if action_type == "ask_user":
        question, _created = add_question(
            state,
            _work_control_text(action, "Need user input before continuing this work session."),
            related_task_id=task_id,
            blocks=[f"task:{task_id}"] if task_id else [],
        )
        return {"question": question}
    if action_type == "remember":
        if session is not None:
            note = add_work_session_note(
                session,
                _work_control_text(action, "Remembered work note."),
                source="model",
            )
        else:
            note = {"created_at": now_iso(), "source": "model", "text": _work_control_text(action, "Remembered work note.")}
        return {"work_note": note}
    return {}


def work_ai_progress(args):
    if not (getattr(args, "progress", False) or getattr(args, "live", False) or not getattr(args, "json", False)):
        return None

    def emit(line):
        print(f"mew work ai: {line}", file=sys.stderr, flush=True)

    return emit


def work_tool_progress(args):
    if not getattr(args, "progress", False):
        return None

    def emit(line):
        print(f"mew work: {line}", file=sys.stderr, flush=True)

    return emit


def work_tool_output_progress(progress, tool_call_id):
    if not progress:
        return None

    def emit(stream_name, text):
        for line in (text or "").splitlines():
            progress(f"tool #{tool_call_id} {stream_name}: {clip_output(line, 500)}")

    return emit


def execute_work_tool_with_output(tool, parameters, allowed_read_roots, output_progress=None):
    if output_progress:
        return execute_work_tool(tool, parameters, allowed_read_roots, on_output=output_progress)
    return execute_work_tool(tool, parameters, allowed_read_roots)


BATCH_READ_WORK_TOOLS = READ_ONLY_WORK_TOOLS | GIT_WORK_TOOLS


def run_work_batch_action(session_id, task_id, index, planned, action, args, progress, turn_id=None):
    sub_actions = [
        sub_action
        for sub_action in (action.get("tools") or [])[:5]
        if (sub_action.get("type") or sub_action.get("tool")) in BATCH_READ_WORK_TOOLS
    ]
    if not sub_actions:
        sub_actions = [{"type": "wait", "reason": "batch has no read-only tools"}]
    with state_lock():
        state = load_state()
        session = find_work_session(state, session_id)
        if turn_id is None:
            turn = start_work_model_turn(
                state,
                session,
                planned.get("decision_plan") or {},
                planned.get("action_plan") or {},
                action,
            )
        else:
            turn = update_work_model_turn_plan(
                state,
                session_id,
                turn_id,
                planned.get("decision_plan") or {},
                planned.get("action_plan") or {},
                action,
            )
        turn_id = turn.get("id")
        save_state(state)

    tool_calls = []
    error = ""
    for sub_action in sub_actions:
        with state_lock():
            state = load_state()
            session = find_work_session(state, session_id)
            stop_request = consume_work_session_stop(session)
            if stop_request:
                tool_call_ids = [call.get("id") for call in tool_calls if call]
                turn = finish_work_model_turn(
                    state,
                    session_id,
                    turn_id,
                    tool_call_id=tool_call_ids[0] if tool_call_ids else None,
                )
                if turn is not None:
                    turn["tool_call_ids"] = tool_call_ids
                    turn["stop_request"] = stop_request
                    turn["summary"] = clip_output(
                        f"stopped before next batch tool: {stop_request.get('reason') or ''}".strip(),
                        4000,
                    )
                save_state(state)
            else:
                turn = None
        if stop_request:
            return {
                "index": index,
                "status": "stopped",
                "action": action,
                "model_turn": turn,
                "tool_calls": tool_calls,
                "stop_request": stop_request,
                "summary": turn.get("summary") if turn else "stopped before next batch tool",
            }
        action_type = sub_action.get("type") or sub_action.get("tool")
        if action_type not in BATCH_READ_WORK_TOOLS:
            error = f"batch tool is not read-only: {action_type or 'missing'}"
            break
        parameters = work_tool_parameters_from_action(
            sub_action,
            allowed_write_roots=[],
            allow_shell=False,
            allow_verify=False,
            verify_command="",
            verify_timeout=args.verify_timeout,
        )
        with state_lock():
            state = load_state()
            session = find_work_session(state, session_id)
            tool_call = start_work_tool_call(state, session, action_type, parameters)
            tool_call_id = tool_call.get("id")
            save_state(state)
        if progress:
            progress(f"step #{index}: batch tool #{tool_call_id} {action_type} start")
        try:
            result = execute_work_tool_with_output(
                action_type,
                parameters,
                args.allow_read or [],
                work_tool_output_progress(progress, tool_call_id),
            )
            error = work_tool_result_error(action_type, result)
        except (OSError, ValueError) as exc:
            result = None
            error = str(exc)
        with state_lock():
            state = load_state()
            tool_call = finish_work_tool_call(state, session_id, tool_call_id, result=result, error=error)
            save_state(state)
        tool_calls.append(tool_call)
        if progress:
            progress(f"step #{index}: batch tool #{tool_call_id} {tool_call.get('status')}")
        if error:
            break

    tool_call_ids = [call.get("id") for call in tool_calls if call]
    with state_lock():
        state = load_state()
        turn = finish_work_model_turn(
            state,
            session_id,
            turn_id,
            tool_call_id=tool_call_ids[0] if tool_call_ids else None,
            error=error,
        )
        if turn is not None:
            turn["tool_call_ids"] = tool_call_ids
        save_state(state)
    return {
        "index": index,
        "status": "failed" if error else "completed",
        "action": action,
        "model_turn": turn,
        "tool_calls": tool_calls,
        "error": error,
        "summary": f"ran {len(tool_calls)} batch tool(s)",
    }


def cmd_work(args):
    if getattr(args, "live", False):
        args.ai = True
    if getattr(args, "ai", False):
        if getattr(args, "tool", None):
            print("mew: --ai and --tool cannot be combined", file=sys.stderr)
            return 1
        return cmd_work_ai(args)
    if getattr(args, "approve_tool", None):
        return cmd_work_approve_tool(args)
    if getattr(args, "reject_tool", None):
        return cmd_work_reject_tool(args)
    if getattr(args, "tool", None):
        return cmd_work_tool(args)
    if getattr(args, "start_session", False):
        return cmd_work_start_session(args)
    if getattr(args, "session", False):
        return cmd_work_show_session(args)
    if getattr(args, "close_session", False):
        return cmd_work_close_session(args)
    if getattr(args, "stop_session", False):
        return cmd_work_stop_session(args)
    if getattr(args, "session_note", None):
        return cmd_work_session_note(args)
    if getattr(args, "recover_session", False):
        return cmd_work_recover_session(args)

    state = load_state()
    task_id = getattr(args, "task_id", None)
    task = select_workbench_task(state, task_id)
    if not task:
        if task_id:
            print(f"mew: task not found: {task_id}", file=sys.stderr)
            return 1
        else:
            print("No tasks.")
            return 0
    data = build_workbench_data(state, task)
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0
    print(format_workbench(data))
    return 0


def cmd_work_ai(args):
    if getattr(args, "live", False) and getattr(args, "json", False):
        print("mew: --live cannot be combined with --json", file=sys.stderr)
        return 1
    try:
        model_backend = normalize_model_backend(args.model_backend)
    except MewError as exc:
        print(f"mew: {exc}", file=sys.stderr)
        return 1

    model = args.model or model_backend_default_model(model_backend)
    base_url = args.base_url or model_backend_default_base_url(model_backend)
    try:
        model_auth = load_model_auth(model_backend, args.auth)
    except MewError as exc:
        print(f"mew: {exc}", file=sys.stderr)
        return 1

    max_steps = max(1, int(getattr(args, "max_steps", 1) or 1))
    progress = work_ai_progress(args)
    with state_lock():
        state = load_state()
        task = select_work_ai_task(state, getattr(args, "task_id", None))
        if not task:
            if getattr(args, "task_id", None):
                print(f"mew: task not found: {args.task_id}", file=sys.stderr)
                return 1
            print("No tasks.", file=sys.stderr)
            return 1
        session, created = create_work_session(state, task)
        remember_work_session_default_options(session, args)
        session_id = session.get("id")
        task_id = task.get("id")
        save_state(state)
    if progress:
        progress(f"{'created' if created else 'reused'} session #{session_id} task=#{task_id}")

    report = {
        "session_id": session_id,
        "task_id": task_id,
        "created": created,
        "max_steps": max_steps,
        "stop_reason": "max_steps",
        "steps": [],
    }

    for index in range(1, max_steps + 1):
        if progress:
            progress(f"step #{index}: planning")
        with state_lock():
            state = load_state()
            session = find_work_session(state, session_id)
            task = work_session_task(state, session)
        if not session or session.get("status") != "active":
            report["stop_reason"] = "no_active_session"
            break
        with state_lock():
            state = load_state()
            session = find_work_session(state, session_id)
            stop_request = consume_work_session_stop(session)
            if stop_request:
                save_state(state)
        if stop_request:
            report["stop_reason"] = "stop_requested"
            report["stop_request"] = stop_request
            if progress:
                progress(f"step #{index}: stop requested")
            break

        prompt_state = state
        prompt_session = session
        prompt_task = task
        with state_lock():
            state = load_state()
            session = find_work_session(state, session_id)
            planning_turn = start_work_model_turn(
                state,
                session,
                {"summary": "planning work step"},
                {"summary": "planning work step"},
                {"type": "planning", "reason": "THINK/ACT in progress"},
            )
            planning_turn_id = planning_turn.get("id")
            save_state(state)

        try:
            planned = plan_work_model_turn(
                prompt_state,
                prompt_session,
                prompt_task,
                model_auth,
                model=model,
                base_url=base_url,
                model_backend=model_backend,
                timeout=args.model_timeout,
                allowed_read_roots=args.allow_read or [],
                allowed_write_roots=args.allow_write or [],
                allow_shell=args.allow_shell,
                allow_verify=args.allow_verify,
                verify_command=args.verify_command or "",
                guidance=args.work_guidance or "",
                progress=progress,
                act_mode=getattr(args, "act_mode", "model") or "model",
                stream_model=bool(getattr(args, "stream_model", False) or getattr(args, "live", False)),
            )
        except MewError as exc:
            error = str(exc)
            with state_lock():
                state = load_state()
                session = find_work_session(state, session_id)
                task = work_session_task(state, session) or find_task(state, task_id)
                turn = update_work_model_turn_plan(
                    state,
                    session_id,
                    planning_turn_id,
                    {"summary": "model planning failed"},
                    {"summary": "model planning failed"},
                    {"type": "wait", "reason": error},
                )
                turn = finish_work_model_turn(state, session_id, planning_turn_id, error=error)
                save_state(state)
            report["steps"].append(
                {
                    "index": index,
                    "status": "failed",
                    "action": {"type": "wait", "reason": error},
                    "model_turn": turn,
                    "error": error,
                }
            )
            report["stop_reason"] = "model_error"
            if progress:
                progress(f"step #{index}: model failed")
            break

        action = planned.get("action") or {"type": "wait", "reason": "missing action"}
        action_type = action.get("type")
        with state_lock():
            state = load_state()
            session = find_work_session(state, session_id)
            stop_request = consume_work_session_stop(session)
            if stop_request:
                turn = update_work_model_turn_plan(
                    state,
                    session_id,
                    planning_turn_id,
                    planned.get("decision_plan") or {},
                    planned.get("action_plan") or {},
                    action,
                )
                turn = finish_work_model_turn(state, session_id, planning_turn_id)
                if turn is not None:
                    turn["stop_request"] = stop_request
                    turn["summary"] = clip_output(
                        f"stopped before tool execution: {stop_request.get('reason') or ''}".strip(),
                        4000,
                    )
                save_state(state)
        if stop_request:
            report["steps"].append(
                {
                    "index": index,
                    "status": "stopped",
                    "action": action,
                    "model_turn": turn,
                    "stop_request": stop_request,
                    "summary": turn.get("summary") if turn else "stopped before tool execution",
                }
            )
            report["stop_reason"] = "stop_requested"
            report["stop_request"] = stop_request
            if progress:
                progress(f"step #{index}: stop requested after planning")
            break
        if action_type == "batch":
            if getattr(args, "live", False):
                print("")
                print(f"Work live step #{index} action")
                print(format_work_action(action))
            batch_step = run_work_batch_action(
                session_id,
                task_id,
                index,
                planned,
                action,
                args,
                progress,
                turn_id=planning_turn_id,
            )
            report["steps"].append(batch_step)
            if getattr(args, "live", False):
                with state_lock():
                    state = load_state()
                    session = find_work_session(state, session_id)
                    task = work_session_task(state, session)
                print("")
                print(f"Work live step #{index} resume")
                print(format_work_session_resume(build_work_session_resume(session, task=task)))
            if batch_step.get("error"):
                report["stop_reason"] = "tool_failed"
                break
            if batch_step.get("stop_request"):
                report["stop_reason"] = "stop_requested"
                report["stop_request"] = batch_step.get("stop_request")
                break
            continue
        if action_type not in WORK_TOOLS:
            if getattr(args, "live", False):
                print("")
                print(f"Work live step #{index} action")
                print(format_work_action(action))
            with state_lock():
                state = load_state()
                session = find_work_session(state, session_id)
                task = work_session_task(state, session) or find_task(state, task_id)
                turn = update_work_model_turn_plan(
                    state,
                    session_id,
                    planning_turn_id,
                    planned.get("decision_plan") or {},
                    planned.get("action_plan") or {},
                    action,
                )
                turn = finish_work_model_turn(state, session_id, planning_turn_id)
                control_effect = apply_work_control_action(state, session, task, action)
                if control_effect.get("outbox_message"):
                    turn["outbox_message_id"] = control_effect["outbox_message"].get("id")
                if control_effect.get("question"):
                    turn["question_id"] = control_effect["question"].get("id")
                if control_effect.get("finished_note"):
                    turn["finished_note"] = control_effect["finished_note"]
                if control_effect.get("work_note"):
                    turn["work_note"] = control_effect["work_note"]
                save_state(state)
            if getattr(args, "live", False):
                with state_lock():
                    state = load_state()
                    session = find_work_session(state, session_id)
                    task = work_session_task(state, session) or find_task(state, task_id)
                print("")
                print(f"Work live step #{index} resume")
                print(format_work_session_resume(build_work_session_resume(session, task=task)))
            report["steps"].append(
                {
                    "index": index,
                    "status": "completed",
                    "action": action,
                    "model_turn": turn,
                    **control_effect,
                    "summary": (
                        (action.get("text") if action_type == "send_message" else "")
                        or (action.get("question") if action_type == "ask_user" else "")
                        or (action.get("note") if action_type == "remember" else "")
                        or action.get("summary")
                        or action.get("reason")
                        or action.get("text")
                        or action.get("question")
                        or ""
                    ),
                }
            )
            report["stop_reason"] = action_type or "control"
            if progress:
                progress(f"step #{index}: stop={report['stop_reason']}")
            break

        parameters = work_tool_parameters_from_action(
            action,
            allowed_write_roots=args.allow_write or [],
            allow_shell=args.allow_shell,
            allow_verify=args.allow_verify,
            verify_command=args.verify_command or "",
            verify_timeout=args.verify_timeout,
        )
        with state_lock():
            state = load_state()
            session = find_work_session(state, session_id)
            stop_request = consume_work_session_stop(session)
            if stop_request:
                turn = update_work_model_turn_plan(
                    state,
                    session_id,
                    planning_turn_id,
                    planned.get("decision_plan") or {},
                    planned.get("action_plan") or {},
                    action,
                )
                turn = finish_work_model_turn(state, session_id, planning_turn_id)
                if turn is not None:
                    turn["stop_request"] = stop_request
                    turn["summary"] = clip_output(
                        f"stopped before tool execution: {stop_request.get('reason') or ''}".strip(),
                        4000,
                    )
                save_state(state)
        if stop_request:
            report["steps"].append(
                {
                    "index": index,
                    "status": "stopped",
                    "action": action,
                    "model_turn": turn,
                    "stop_request": stop_request,
                    "summary": turn.get("summary") if turn else "stopped before tool execution",
                }
            )
            report["stop_reason"] = "stop_requested"
            report["stop_request"] = stop_request
            if progress:
                progress(f"step #{index}: stop requested before tool start")
            break
        with state_lock():
            state = load_state()
            session = find_work_session(state, session_id)
            turn = update_work_model_turn_plan(
                state,
                session_id,
                planning_turn_id,
                planned.get("decision_plan") or {},
                planned.get("action_plan") or {},
                action,
            )
            tool_call = start_work_tool_call(state, session, action_type, parameters)
            turn["tool_call_id"] = tool_call.get("id")
            turn_id = turn.get("id")
            tool_call_id = tool_call.get("id")
            save_state(state)
        if getattr(args, "live", False):
            print("")
            print(f"Work live step #{index} action")
            print(format_work_action(action, parameters=parameters, tool_call_id=tool_call_id))
        if progress:
            progress(f"step #{index}: tool #{tool_call_id} {action_type} start")

        try:
            result = execute_work_tool_with_output(
                action_type,
                parameters,
                args.allow_read or [],
                work_tool_output_progress(progress, tool_call_id),
            )
            error = work_tool_result_error(action_type, result)
        except (OSError, ValueError) as exc:
            result = None
            error = str(exc)

        with state_lock():
            state = load_state()
            tool_call = finish_work_tool_call(state, session_id, tool_call_id, result=result, error=error)
            turn = finish_work_model_turn(state, session_id, turn_id, tool_call_id=tool_call_id, error=error)
            save_state(state)
        if progress:
            progress(f"step #{index}: tool #{tool_call_id} {tool_call.get('status')}")

        report["steps"].append(
            {
                "index": index,
                "status": tool_call.get("status"),
                "action": action,
                "model_turn": turn,
                "tool_call": tool_call,
                "error": error,
                "summary": tool_call.get("summary") or "",
            }
        )
        if getattr(args, "live", False):
            with state_lock():
                state = load_state()
                session = find_work_session(state, session_id)
                task = work_session_task(state, session)
            print("")
            print(f"Work live step #{index} resume")
            print(format_work_session_resume(build_work_session_resume(session, task=task)))
        if error:
            report["stop_reason"] = "tool_failed"
            break

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(format_work_ai_report(report))
        if getattr(args, "live", False) and not getattr(args, "suppress_cli_controls", False):
            state = load_state()
            session = find_work_session(state, session_id)
            print(format_work_cli_controls(session, args))
    return 0 if report.get("stop_reason") not in ("model_error", "tool_failed", "no_active_session") else 1


def _select_active_work_session_for_args(state, args):
    session = active_work_session(state)
    if getattr(args, "task_id", None):
        session = None
        for candidate in reversed(state.get("work_sessions", [])):
            if str(candidate.get("task_id")) == str(args.task_id) and candidate.get("status") == "active":
                session = candidate
                break
    return session


def _latest_work_session_for_task(state, task_id):
    latest = None
    for candidate in reversed(state.get("work_sessions", [])):
        if str(candidate.get("task_id")) != str(task_id):
            continue
        if candidate.get("status") == "active":
            return candidate
        if latest is None:
            latest = candidate
    return latest


def _approval_parameters_from_call(call, args):
    parameters = dict(call.get("parameters") or {})
    for key in ("allowed_write_roots", "allow_shell", "allow_verify", "verify_command", "verify_cwd", "verify_timeout"):
        parameters.pop(key, None)
    parameters["apply"] = True
    parameters["approved_from_tool_call_id"] = call.get("id")
    parameters["allowed_write_roots"] = getattr(args, "allow_write", None) or []
    parameters["allow_verify"] = bool(getattr(args, "allow_verify", False))
    parameters["verify_command"] = getattr(args, "verify_command", None)
    parameters["verify_cwd"] = getattr(args, "verify_cwd", None) or "."
    parameters["verify_timeout"] = getattr(args, "verify_timeout", None)
    return {key: value for key, value in parameters.items() if value is not None}


def cmd_work_approve_tool(args):
    progress = work_tool_progress(args)
    with state_lock():
        state = load_state()
        session = _select_active_work_session_for_args(state, args)
        if not session:
            print("mew: no active work session; run `mew work <task-id> --start-session`", file=sys.stderr)
            return 1
        task = work_session_task(state, session)
        if not getattr(args, "verify_command", None):
            inferred_verify_command = latest_work_verify_command(session.get("tool_calls") or [], task=task)
            if inferred_verify_command:
                args.verify_command = inferred_verify_command
                args.allow_verify = True
        source_call = find_work_tool_call(session, args.approve_tool)
        if not source_call:
            print(f"mew: work tool call not found: {args.approve_tool}", file=sys.stderr)
            return 1
        if source_call.get("tool") not in ("write_file", "edit_file"):
            print("mew: only write_file/edit_file tool calls can be approved", file=sys.stderr)
            return 1
        result = source_call.get("result") or {}
        if not result.get("dry_run"):
            print("mew: only dry-run write/edit tool calls can be approved", file=sys.stderr)
            return 1
        if source_call.get("approval_status") in ("applying", "applied", "rejected"):
            print(f"mew: tool call is already {source_call.get('approval_status')}", file=sys.stderr)
            return 1
        if not result.get("changed"):
            print("mew: dry-run tool call has no changes to approve", file=sys.stderr)
            return 1
        parameters = _approval_parameters_from_call(source_call, args)
        tool_call = start_work_tool_call(state, session, source_call.get("tool"), parameters)
        source_call["approval_status"] = "applying"
        source_call["approved_by_tool_call_id"] = tool_call.get("id")
        source_call["approved_at"] = now_iso()
        session_id = session.get("id")
        tool_call_id = tool_call.get("id")
        save_state(state)
    if progress:
        progress(f"approval #{args.approve_tool} -> tool #{tool_call_id} start")

    try:
        result = execute_work_tool_with_output(
            source_call.get("tool"),
            parameters,
            getattr(args, "allow_read", None) or [],
            work_tool_output_progress(progress, tool_call_id),
        )
        error = work_tool_result_error(source_call.get("tool"), result)
    except (OSError, ValueError) as exc:
        result = None
        error = str(exc)

    with state_lock():
        state = load_state()
        session = find_work_session(state, session_id)
        source_call = find_work_tool_call(session, args.approve_tool)
        tool_call = finish_work_tool_call(state, session_id, tool_call_id, result=result, error=error)
        if source_call:
            source_call["approval_status"] = "applied" if tool_call.get("status") == "completed" else "failed"
            source_call["approval_error"] = tool_call.get("error") or ""
        save_state(state)
    if args.json:
        print(json.dumps({"approved_tool_call": source_call, "tool_call": tool_call}, ensure_ascii=False, indent=2))
    else:
        print(f"approved work tool #{args.approve_tool} -> #{tool_call['id']} [{tool_call['status']}]")
        print(tool_call.get("summary") or tool_call.get("error") or "")
    if progress:
        progress(f"approval #{args.approve_tool} -> tool #{tool_call_id} {tool_call.get('status')}")
    return 0 if tool_call.get("status") == "completed" else 1


def cmd_work_reject_tool(args):
    with state_lock():
        state = load_state()
        session = _select_active_work_session_for_args(state, args)
        if not session:
            print("mew: no active work session; run `mew work <task-id> --start-session`", file=sys.stderr)
            return 1
        source_call = find_work_tool_call(session, args.reject_tool)
        if not source_call:
            print(f"mew: work tool call not found: {args.reject_tool}", file=sys.stderr)
            return 1
        if source_call.get("tool") not in ("write_file", "edit_file"):
            print("mew: only write_file/edit_file tool calls can be rejected", file=sys.stderr)
            return 1
        if source_call.get("approval_status") in ("applying", "applied"):
            print(f"mew: tool call is already {source_call.get('approval_status')}", file=sys.stderr)
            return 1
        source_call["approval_status"] = "rejected"
        source_call["rejected_at"] = now_iso()
        source_call["rejection_reason"] = getattr(args, "reject_reason", None) or ""
        save_state(state)
    if args.json:
        print(json.dumps({"rejected_tool_call": source_call}, ensure_ascii=False, indent=2))
    else:
        print(f"rejected work tool #{source_call['id']}")
    return 0


def cmd_work_start_session(args):
    task_id = getattr(args, "task_id", None)
    with state_lock():
        state = load_state()
        task = select_workbench_task(state, task_id)
        if not task:
            if task_id:
                print(f"mew: task not found: {task_id}", file=sys.stderr)
                return 1
            print("No tasks.")
            return 0
        session, created = create_work_session(state, task)
        save_state(state)
    if args.json:
        print(json.dumps({"created": created, "work_session": session}, ensure_ascii=False, indent=2))
    else:
        print(("created " if created else "reused ") + f"work session #{session['id']} for task #{task['id']}")
        print(format_work_session(session, task=task))
    return 0


def recent_work_session_summaries(state, limit=5):
    sessions = list(state.get("work_sessions") or [])
    recent = list(reversed(sessions[-limit:]))
    summaries = []
    for session in recent:
        task = work_session_task(state, session)
        resume = build_work_session_resume(session, task=task, limit=3)
        task_id = session.get("task_id")
        resume_command = f"mew work {task_id} --session --resume" if task_id is not None else "mew work --session --resume"
        chat_resume_command = f"/work-session resume {task_id}" if task_id is not None else "/work-session resume"
        summaries.append(
            {
                "id": session.get("id"),
                "status": session.get("status"),
                "task_id": task_id,
                "phase": (resume or {}).get("phase") or "unknown",
                "title": session.get("title") or "",
                "resume_command": resume_command,
                "chat_resume_command": chat_resume_command,
            }
        )
    return summaries


def format_no_active_work_session(state, limit=5):
    lines = ["No active work session."]
    recent = recent_work_session_summaries(state, limit=limit)
    if recent:
        lines.extend(["", "Recent work sessions"])
        for session in recent:
            lines.append(
                f"- #{session.get('id')} [{session.get('status')}] task=#{session.get('task_id')} "
                f"phase={session.get('phase')} {session.get('title') or ''}"
            )
            lines.append(f"  resume: {session.get('resume_command')}")
            lines.append(f"  chat: {session.get('chat_resume_command')}")
    lines.extend(["", "Start or resume", "- mew work <task-id> --start-session", "- /work-session start <task-id>"])
    return "\n".join(lines)


def cmd_work_show_session(args):
    state = load_state()
    session = active_work_session(state)
    if getattr(args, "task_id", None):
        task = find_task(state, args.task_id)
        session = _latest_work_session_for_task(state, args.task_id)
    else:
        task = work_session_task(state, session)
    if getattr(args, "resume", False):
        resume = build_work_session_resume(session, task=task)
        if resume and getattr(args, "allow_read", None):
            resume["world_state"] = build_work_world_state(resume, args.allow_read)
        if not resume and not getattr(args, "task_id", None):
            if args.json:
                print(
                    json.dumps(
                        {
                            "resume": None,
                            "recent_work_sessions": recent_work_session_summaries(state),
                            "start_commands": ["mew work <task-id> --start-session", "/work-session start <task-id>"],
                        },
                        ensure_ascii=False,
                        indent=2,
                    )
                )
            else:
                print(format_no_active_work_session(state))
            return 0
        if args.json:
            print(
                json.dumps(
                    {
                        "resume": resume,
                        "next_cli_controls": work_cli_control_commands(session, args) if resume else [],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            print(format_work_session_resume(resume))
            if resume:
                print(format_work_cli_controls(session, args))
        return 0
    if args.json:
        payload = {"work_session": session}
        if not session and not getattr(args, "task_id", None):
            payload["recent_work_sessions"] = recent_work_session_summaries(state)
            payload["start_commands"] = ["mew work <task-id> --start-session", "/work-session start <task-id>"]
        elif session:
            payload["next_cli_controls"] = work_cli_control_commands(session, args)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        if not session and not getattr(args, "task_id", None):
            print(format_no_active_work_session(state))
        else:
            print(format_work_session(session, task=task, details=getattr(args, "details", False)))
            print(format_work_cli_controls(session, args))
    return 0


def cmd_work_close_session(args):
    with state_lock():
        state = load_state()
        session = active_work_session(state)
        if getattr(args, "task_id", None):
            session = None
            for candidate in reversed(state.get("work_sessions", [])):
                if str(candidate.get("task_id")) == str(args.task_id) and candidate.get("status") == "active":
                    session = candidate
                    break
        if not session:
            print("No active work session.")
            return 0
        close_work_session(session)
        save_state(state)
    if args.json:
        print(json.dumps({"work_session": session}, ensure_ascii=False, indent=2))
    else:
        print(f"closed work session #{session['id']}")
    return 0


def cmd_work_stop_session(args):
    with state_lock():
        state = load_state()
        session = _select_active_work_session_for_args(state, args)
        if not session:
            print("No active work session.")
            return 0
        request_work_session_stop(session, reason=getattr(args, "stop_reason", None) or "")
        save_state(state)
    if args.json:
        print(json.dumps({"work_session": session}, ensure_ascii=False, indent=2))
    else:
        reason = session.get("stop_reason") or "stop requested"
        print(f"requested stop for work session #{session['id']}: {reason}")
    return 0


def cmd_work_session_note(args):
    text = (getattr(args, "session_note", None) or "").strip()
    if not text:
        print("mew: --session-note requires text", file=sys.stderr)
        return 1
    with state_lock():
        state = load_state()
        session = _select_active_work_session_for_args(state, args)
        if not session:
            print("No active work session.")
            return 0
        note = add_work_session_note(session, text, source="user")
        save_state(state)
    if args.json:
        print(json.dumps({"work_note": note, "work_session": session}, ensure_ascii=False, indent=2))
    else:
        print(f"recorded work session note #{session['id']}: {note['text']}")
    return 0


def latest_recoverable_interrupted_call(session):
    for call in reversed(session.get("tool_calls") or []):
        if call.get("status") == "interrupted" and not call.get("recovery_status"):
            return call
    return None


def cmd_work_recover_session(args):
    progress = work_tool_progress(args)
    with state_lock():
        state = load_state()
        session = _select_active_work_session_for_args(state, args)
        if not session:
            print("No active work session.")
            return 0
        source_call = latest_recoverable_interrupted_call(session)
        if not source_call:
            report = {"recovery": {"action": "none", "reason": "no interrupted work tool to recover"}}
            if args.json:
                print(json.dumps(report, ensure_ascii=False, indent=2))
            else:
                print("No interrupted work tool to recover.")
            return 0
        tool = source_call.get("tool")
        if tool not in (READ_ONLY_WORK_TOOLS | GIT_WORK_TOOLS):
            report = {
                "recovery": {
                    "action": "needs_user",
                    "reason": f"interrupted {tool} is not safe to retry automatically",
                    "source_tool_call_id": source_call.get("id"),
                    "tool": tool,
                }
            }
            if args.json:
                print(json.dumps(report, ensure_ascii=False, indent=2))
            else:
                print(f"Interrupted {tool} needs user review before retry.")
            return 0
        parameters = dict(source_call.get("parameters") or {})
        parameters["recovered_from_tool_call_id"] = source_call.get("id")
        tool_call = start_work_tool_call(state, session, tool, parameters)
        session_id = session.get("id")
        tool_call_id = tool_call.get("id")
        save_state(state)

    if progress:
        progress(f"recover tool #{source_call.get('id')} -> #{tool_call_id} {tool} start")
    try:
        result = execute_work_tool_with_output(
            tool,
            parameters,
            getattr(args, "allow_read", None) or [],
            work_tool_output_progress(progress, tool_call_id),
        )
        error = work_tool_result_error(tool, result)
    except (OSError, ValueError) as exc:
        result = None
        error = str(exc)

    with state_lock():
        state = load_state()
        tool_call = finish_work_tool_call(state, session_id, tool_call_id, result=result, error=error)
        session = find_work_session(state, session_id)
        source_call = find_work_tool_call(session, parameters.get("recovered_from_tool_call_id"))
        if source_call:
            source_call["recovery_status"] = "superseded" if not error else "retry_failed"
            source_call["recovered_by_tool_call_id"] = tool_call_id
            source_call["recovered_at"] = now_iso()
            for turn in session.get("model_turns") or []:
                if turn.get("tool_call_id") != source_call.get("id"):
                    continue
                turn["recovery_status"] = source_call["recovery_status"]
                turn["recovered_by_tool_call_id"] = tool_call_id
                turn["recovered_at"] = source_call["recovered_at"]
        save_state(state)
    report = {
        "recovery": {
            "action": "retry_tool",
            "source_tool_call_id": parameters.get("recovered_from_tool_call_id"),
            "tool": tool,
            "status": tool_call.get("status"),
        },
        "tool_call": tool_call,
    }
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(
            f"recovered work tool #{parameters.get('recovered_from_tool_call_id')} "
            f"-> #{tool_call_id} [{tool_call.get('status')}] {tool}"
        )
        print(tool_call.get("summary") or tool_call.get("error") or "")
    if progress:
        progress(f"recover tool #{tool_call_id} {tool_call.get('status')}")
    return 0 if tool_call.get("status") == "completed" else 1


def _work_tool_parameters(args):
    parameters = {
        "path": args.path,
        "query": getattr(args, "query", None),
        "pattern": getattr(args, "pattern", None),
        "command": getattr(args, "command", None),
        "base": getattr(args, "base", None),
        "staged": getattr(args, "staged", False),
        "stat": getattr(args, "stat", False),
        "content": getattr(args, "content", None),
        "old": getattr(args, "old", None),
        "new": getattr(args, "new", None),
        "create": getattr(args, "create", False),
        "replace_all": getattr(args, "replace_all", False),
        "apply": getattr(args, "apply", False),
        "cwd": getattr(args, "cwd", None),
        "timeout": getattr(args, "timeout", None),
        "allowed_write_roots": getattr(args, "allow_write", None) or [],
        "allow_shell": getattr(args, "allow_shell", False),
        "allow_verify": getattr(args, "allow_verify", False),
        "verify_command": getattr(args, "verify_command", None),
        "verify_cwd": getattr(args, "verify_cwd", None),
        "verify_timeout": getattr(args, "verify_timeout", None),
        "limit": getattr(args, "limit", None),
        "max_chars": getattr(args, "max_chars", None),
        "offset": getattr(args, "offset", None),
        "max_matches": getattr(args, "max_matches", None),
    }
    return {key: value for key, value in parameters.items() if value is not None}


def cmd_work_tool(args):
    progress = work_tool_progress(args)
    with state_lock():
        state = load_state()
        session = active_work_session(state)
        if getattr(args, "task_id", None):
            session = None
            for candidate in reversed(state.get("work_sessions", [])):
                if str(candidate.get("task_id")) == str(args.task_id) and candidate.get("status") == "active":
                    session = candidate
                    break
        if not session:
            print("mew: no active work session; run `mew work <task-id> --start-session`", file=sys.stderr)
            return 1
        parameters = _work_tool_parameters(args)
        tool_call = start_work_tool_call(state, session, args.tool, parameters)
        session_id = session.get("id")
        tool_call_id = tool_call.get("id")
        save_state(state)
    if progress:
        progress(f"tool #{tool_call_id} {args.tool} start")

    try:
        result = execute_work_tool_with_output(
            args.tool,
            parameters,
            getattr(args, "allow_read", None) or [],
            work_tool_output_progress(progress, tool_call_id),
        )
        error = work_tool_result_error(args.tool, result)
    except (OSError, ValueError) as exc:
        result = None
        error = str(exc)

    with state_lock():
        state = load_state()
        tool_call = finish_work_tool_call(state, session_id, tool_call_id, result=result, error=error)
        save_state(state)
    if args.json:
        print(json.dumps({"tool_call": tool_call}, ensure_ascii=False, indent=2))
    else:
        print(f"work tool #{tool_call['id']} [{tool_call['status']}] {tool_call['tool']}")
        print(tool_call.get("summary") or tool_call.get("error") or "")
    if progress:
        progress(f"tool #{tool_call_id} {tool_call.get('status')}")
    return 0 if tool_call.get("status") == "completed" else 1

def cmd_task_done(args):
    with state_lock():
        state = load_state()
        task = find_task(state, args.task_id)
        if not task:
            print(f"mew: task not found: {args.task_id}", file=sys.stderr)
            return 1
        current_time = now_iso()
        summary = getattr(args, "summary", "") or ""
        task["status"] = "done"
        if summary:
            append_task_note(task, f"{current_time} done: {summary}")
        task["updated_at"] = current_time
        resolve_open_questions_for_task(
            state,
            task["id"],
            reason="task marked done",
        )
        record_user_reported_verification(state, None, task, summary, current_time)
        sync_task_done_state(state, task, summary, current_time)
        save_state(state)
    print(format_task(task))
    return 0

def sync_task_done_state(state, task, summary, current_time):
    task_id = task["id"]
    text = f"Task #{task_id} completed: {task['title']}."
    if summary:
        text = f"{text} {summary}"
    shallow = state.setdefault("memory", {}).setdefault("shallow", {})
    shallow["current_context"] = text
    shallow["latest_task_summary"] = text
    state.setdefault("knowledge", {}).setdefault("shallow", {})["latest_task_summary"] = text

    agent = state.get("agent_status", {})
    if str(agent.get("active_task_id")) == str(task_id) or not open_tasks(state):
        agent["mode"] = "idle"
        agent["current_focus"] = ""
        agent["active_task_id"] = None
        agent["pending_question"] = None
    agent["last_thought"] = text
    agent["updated_at"] = current_time
    user = state.get("user_status", {})
    if not open_questions(state):
        user["mode"] = "idle"
        user["current_focus"] = ""
        user["updated_at"] = current_time

    task_markers = (f"task #{task_id}", f"task {task_id}")
    for message in state.get("outbox", []):
        if message.get("read_at") or message.get("requires_reply"):
            continue
        message_text = (message.get("text") or "").casefold()
        if any(marker in message_text for marker in task_markers):
            message["read_at"] = current_time

def cmd_task_update(args):
    with state_lock():
        state = load_state()
        task = find_task(state, args.task_id)
        if not task:
            print(f"mew: task not found: {args.task_id}", file=sys.stderr)
            return 1

        changed = False
        for field in (
            "title",
            "kind",
            "description",
            "status",
            "priority",
            "notes",
            "command",
            "cwd",
            "agent_backend",
            "agent_model",
            "agent_prompt",
        ):
            value = getattr(args, field)
            if value is not None:
                task[field] = value
                changed = True
        if args.auto_execute is not None:
            task["auto_execute"] = args.auto_execute
            changed = True

        if changed:
            task["updated_at"] = now_iso()
            save_state(state)
    print(format_task(task))
    return 0

def append_task_note(task, note):
    existing = task.get("notes") or ""
    task["notes"] = f"{existing.rstrip()}\n{note}".strip()

def apply_reply_to_related_task(state, question, answer_text, event_id):
    task_id = question.get("related_task_id") if question else None
    if task_id is None:
        return None

    task = find_task(state, task_id)
    if not task:
        return None

    current_time = now_iso()
    text = answer_text.strip()
    append_task_note(task, f"{current_time} reply to question #{question['id']}: {text}")

    lowered = text.lower()
    status_aliases = {
        "ready": "ready",
        "make ready": "ready",
        "todo": "todo",
        "blocked": "blocked",
        "block": "blocked",
        "done": "done",
        "complete": "done",
    }
    if lowered in status_aliases:
        task["status"] = status_aliases[lowered]

    prefix_map = (
        ("command:", "command"),
        ("cmd:", "command"),
        ("cwd:", "cwd"),
        ("prompt:", "agent_prompt"),
        ("agent-prompt:", "agent_prompt"),
        ("agent_prompt:", "agent_prompt"),
        ("model:", "agent_model"),
        ("agent-model:", "agent_model"),
        ("agent_model:", "agent_model"),
    )
    for prefix, field in prefix_map:
        if lowered.startswith(prefix):
            value = text[len(prefix) :].strip()
            if value:
                task[field] = value
                if field in ("command", "agent_prompt") and task.get("status") == "todo":
                    task["status"] = "ready"

    if lowered.startswith("agent:"):
        value = text[len("agent:") :].strip()
        task["agent_backend"] = "ai-cli"
        if value:
            task["agent_model"] = value
        if task.get("status") == "todo":
            task["status"] = "ready"
    elif lowered.startswith("ai-cli:"):
        value = text[len("ai-cli:") :].strip()
        task["agent_backend"] = "ai-cli"
        if value:
            task["agent_model"] = value
        if task.get("status") == "todo":
            task["status"] = "ready"

    task["updated_at"] = current_time
    return task

def queue_user_message(text, reply_to_question_id=None, require_open_question=False):
    current_time = now_iso()
    with state_lock():
        state = load_state()
        payload = {"text": text}
        if reply_to_question_id is not None:
            payload["reply_to_question_id"] = reply_to_question_id
            question = find_question(state, reply_to_question_id)
            if require_open_question and not question:
                raise MewError(f"question not found: {reply_to_question_id}")
            if require_open_question and question.get("status") not in ("open", "deferred"):
                raise MewError(f"question already answered: {reply_to_question_id}")
        else:
            question = None
        event = add_event(state, "user_message", "user", payload)
        if reply_to_question_id is not None:
            if question:
                mark_question_answered(state, question, text, event_id=event["id"])
                apply_reply_to_related_task(state, question, text, event["id"])
        user = state["user_status"]
        user["mode"] = "waiting_for_agent"
        user["last_request"] = text
        user["last_interaction_at"] = current_time
        user["updated_at"] = current_time
        save_state(state)
    return event

def queue_external_event(event_type, source="cli", payload=None):
    event_type = (event_type or "").strip()
    if not event_type:
        raise MewError("event type is required")
    if event_type in RESERVED_EVENT_TYPES:
        raise MewError(f"event type is reserved: {event_type}")
    with state_lock():
        state = load_state()
        event = add_event(state, event_type, source or "cli", payload or {})
        save_state(state)
    return event

def parse_event_payload(raw):
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise MewError(f"invalid JSON payload: {exc}") from exc
    if not isinstance(payload, dict):
        raise MewError("event payload must be a JSON object")
    return payload

def cmd_event(args):
    try:
        payload = parse_event_payload(args.payload)
    except MewError as exc:
        print(f"mew: {exc}", file=sys.stderr)
        return 1
    if args.text:
        payload["text"] = args.text
    try:
        event = queue_external_event(args.event_type, source=args.source, payload=payload)
    except MewError as exc:
        print(f"mew: {exc}", file=sys.stderr)
        return 1
    print(f"queued {event['type']} event #{event['id']} source={event['source']}")
    if not getattr(args, "wait", False):
        return 0
    warn_if_runtime_inactive()
    return wait_for_event_response(
        event["id"],
        timeout=getattr(args, "timeout", 60.0),
        poll_interval=getattr(args, "poll_interval", 1.0),
        mark_read=getattr(args, "mark_read", False),
        event_label=f"{event['type']} event",
    )

def webhook_authorized(headers, token):
    if not token:
        return True
    bearer = headers.get("Authorization", "")
    if bearer == f"Bearer {token}":
        return True
    return headers.get("X-Mew-Token", "") == token

def make_webhook_handler(token="", max_body_bytes=1024 * 1024, read_timeout=5.0):
    class MewWebhookHandler(BaseHTTPRequestHandler):
        server_version = "mew-webhook"
        timeout = read_timeout

        def log_message(self, format, *args):
            return

        def send_json(self, status, payload):
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if urlparse(self.path).path == "/health":
                self.send_json(200, {"ok": True})
                return
            self.send_json(404, {"ok": False, "error": "not found"})

        def do_POST(self):
            self.connection.settimeout(read_timeout)
            if not webhook_authorized(self.headers, token):
                self.send_json(401, {"ok": False, "error": "unauthorized"})
                return

            parsed = urlparse(self.path)
            prefix = "/event/"
            if not parsed.path.startswith(prefix):
                self.send_json(404, {"ok": False, "error": "not found"})
                return
            event_type = unquote(parsed.path[len(prefix) :]).strip()
            try:
                length = int(self.headers.get("Content-Length", "0") or "0")
            except ValueError:
                self.send_json(400, {"ok": False, "error": "invalid content length"})
                return
            if length < 0:
                self.send_json(400, {"ok": False, "error": "invalid content length"})
                return
            if length > max_body_bytes:
                self.send_json(413, {"ok": False, "error": "payload too large"})
                return
            try:
                raw = self.rfile.read(length).decode("utf-8") if length else "{}"
            except (UnicodeDecodeError, socket.timeout):
                self.send_json(400, {"ok": False, "error": "invalid request body"})
                return
            try:
                payload = parse_event_payload(raw)
                query = parse_qs(parsed.query)
                source = query.get("source", [self.headers.get("X-Mew-Source", "webhook")])[0]
                event = queue_external_event(event_type, source=source, payload=payload)
            except MewError as exc:
                self.send_json(400, {"ok": False, "error": str(exc)})
                return
            self.send_json(202, {"ok": True, "event_id": event["id"], "event_type": event["type"]})

    return MewWebhookHandler

def webhook_host_is_loopback(host):
    return host in ("127.0.0.1", "localhost", "::1")

def cmd_webhook(args):
    if not args.token and not args.allow_unauthenticated and not webhook_host_is_loopback(args.host):
        print(
            "mew: webhook token is required for non-loopback hosts; "
            "pass --token or --allow-unauthenticated",
            file=sys.stderr,
        )
        return 1
    handler = make_webhook_handler(
        token=args.token or "",
        max_body_bytes=args.max_body_bytes,
        read_timeout=args.read_timeout,
    )
    server = ThreadingHTTPServer((args.host, args.port), handler)
    server.daemon_threads = True
    host, port = server.server_address
    print(f"mew webhook listening on http://{host}:{port}")
    try:
        if args.once:
            server.handle_request()
        else:
            server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0

def cmd_message(args):
    event = queue_user_message(args.message)
    print(f"queued message event #{event['id']}", flush=True)
    if not getattr(args, "wait", False):
        return 0
    warn_if_runtime_inactive()
    return wait_for_event_response(
        event["id"],
        timeout=getattr(args, "timeout", 60.0),
        poll_interval=getattr(args, "poll_interval", 1.0),
        mark_read=getattr(args, "mark_read", False),
    )

def session_message(kind, request_id=None, **payload):
    data = {"type": kind}
    if request_id is not None:
        data["id"] = request_id
    data.update(payload)
    return data

def unread_outbox_messages(state, include_all=False):
    if include_all:
        return list(state.get("outbox", []))
    return [message for message in state.get("outbox", []) if not message.get("read_at")]

def wait_for_event_messages(event_id, timeout=60.0, poll_interval=1.0, mark_read=False):
    deadline = time.monotonic() + max(0.0, timeout)
    while True:
        state = load_state()
        messages = [
            message
            for message in outbox_for_event(state, event_id)
            if not message.get("read_at")
        ]
        if messages:
            if mark_read:
                mark_outbox_read(message.get("id") for message in messages)
            return {"status": "messages", "messages": messages}

        event = find_event_by_id(state, event_id)
        if event and event.get("processed_at"):
            return {"status": "processed_without_response", "messages": []}

        if time.monotonic() >= deadline:
            return {"status": "timeout", "messages": []}

        time.sleep(max(0.01, poll_interval))

def load_state_locked():
    with state_lock():
        return load_state()

def session_status_payload(state):
    lock = read_lock()
    lock_state = "none"
    if lock:
        lock_state = "active" if pid_alive(lock.get("pid")) else "stale"
    questions = open_questions(state)
    attention = open_attention_items(state)
    running_agents = [run for run in state["agent_runs"] if run.get("status") in ("created", "running")]
    unread = unread_outbox_messages(state)
    return {
        "runtime_status": state["runtime_status"],
        "agent_status": state["agent_status"],
        "user_status": state["user_status"],
        "autonomy": state.get("autonomy", {}),
        "lock": {
            "state": lock_state,
            "pid": (lock or {}).get("pid") if lock else None,
            "started_at": (lock or {}).get("started_at") if lock else None,
        },
        "counts": {
            "open_tasks": len(open_tasks(state)),
            "open_questions": len(questions),
            "open_attention": len(attention),
            "running_agent_runs": len(running_agents),
            "unread_outbox": len(unread),
        },
        "next_move": next_move(state),
    }

def handle_session_request(request):
    if not isinstance(request, dict):
        return session_message("error", error="request must be a JSON object")
    request_id = request.get("id")
    request_type = request.get("type") or request.get("command")

    try:
        if request_type == "message":
            text = request.get("text")
            if not isinstance(text, str) or not text.strip():
                return session_message("error", request_id, error="message.text is required")
            event = queue_user_message(text)
            if request.get("wait"):
                result = wait_for_event_messages(
                    event["id"],
                    timeout=float(request.get("timeout", 60.0)),
                    poll_interval=float(request.get("poll_interval", 1.0)),
                    mark_read=bool(request.get("mark_read")),
                )
                return session_message("event_result", request_id, event=event, **result)
            return session_message("event_queued", request_id, event=event)

        if request_type == "reply":
            question_id = request.get("question_id")
            text = request.get("text")
            if question_id is None:
                return session_message("error", request_id, error="reply.question_id is required")
            if not isinstance(text, str) or not text.strip():
                return session_message("error", request_id, error="reply.text is required")
            event = queue_user_message(text, reply_to_question_id=question_id, require_open_question=True)
            return session_message("event_queued", request_id, event=event)

        if request_type in ("defer_question", "reopen_question"):
            question_id = request.get("question_id")
            if question_id is None:
                return session_message("error", request_id, error=f"{request_type}.question_id is required")
            with state_lock():
                state = load_state()
                question = find_question(state, question_id)
                if not question:
                    return session_message("error", request_id, error=f"question not found: {question_id}")
                if question.get("status") == "answered":
                    return session_message("error", request_id, error=f"question already answered: {question_id}")
                if request_type == "defer_question":
                    mark_question_deferred(state, question, reason=request.get("reason") or "")
                    response_type = "question_deferred"
                else:
                    reopen_question(state, question)
                    response_type = "question_reopened"
                save_state(state)
            return session_message(response_type, request_id, question=question)

        if request_type == "status":
            return session_message("status", request_id, **session_status_payload(load_state_locked()))

        if request_type == "brief":
            limit = request.get("limit", 5)
            if not isinstance(limit, int):
                limit = 5
            return session_message("brief", request_id, brief=build_brief_data(load_state_locked(), limit=limit))

        if request_type in ("focus", "daily"):
            limit = request.get("limit", 3)
            if not isinstance(limit, int):
                limit = 3
            data = build_focus_data(load_state_locked(), limit=limit)
            payload_key = "daily" if request_type == "daily" else "focus"
            return session_message(request_type, request_id, **{payload_key: data})

        if request_type == "activity":
            limit = request.get("limit", 10)
            if not isinstance(limit, int):
                limit = 10
            return session_message("activity", request_id, activity=build_activity_data(load_state_locked(), limit=limit))

        if request_type == "questions":
            state = load_state_locked()
            questions = state["questions"] if request.get("all") else open_questions(state)
            return session_message("questions", request_id, questions=questions)

        if request_type == "attention":
            state = load_state_locked()
            items = state["attention"]["items"] if request.get("all") else open_attention_items(state)
            return session_message("attention", request_id, attention=items)

        if request_type == "outbox":
            state = load_state_locked()
            return session_message(
                "outbox",
                request_id,
                messages=unread_outbox_messages(state, include_all=bool(request.get("all"))),
            )

        if request_type == "wait_outbox":
            event_id = request.get("event_id")
            if event_id is None:
                return session_message("error", request_id, error="wait_outbox.event_id is required")
            result = wait_for_event_messages(
                event_id,
                timeout=float(request.get("timeout", 60.0)),
                poll_interval=float(request.get("poll_interval", 1.0)),
                mark_read=bool(request.get("mark_read")),
            )
            return session_message("event_result", request_id, event_id=event_id, **result)

        if request_type == "ack":
            ids = request.get("message_ids") or []
            if request.get("all"):
                with state_lock():
                    state = load_state()
                    messages = unread_outbox_messages(state)
                    for message in messages:
                        mark_message_read(state, message["id"])
                    save_state(state)
                return session_message("acknowledged", request_id, count=len(messages))
            if not isinstance(ids, list) or not ids:
                return session_message("error", request_id, error="ack.message_ids or ack.all is required")
            with state_lock():
                state = load_state()
                acknowledged = []
                for message_id in ids:
                    message = mark_message_read(state, message_id)
                    if not message:
                        return session_message("error", request_id, error=f"message not found: {message_id}")
                    acknowledged.append(message)
                save_state(state)
            return session_message("acknowledged", request_id, count=len(acknowledged))

        if request_type == "next":
            move = next_move(load_state_locked())
            return session_message("next", request_id, next_move=move, command=command_from_next_move(move))

        if request_type in ("stop", "exit"):
            return session_message("bye", request_id)

        return session_message("error", request_id, error=f"unsupported request type: {request_type}")
    except Exception as exc:
        return session_message("error", request_id, error=str(exc))

def cmd_session(args):
    print(json.dumps(session_message("ready", protocol="mew.session.v1"), ensure_ascii=False), flush=True)
    for line in sys.stdin:
        text = line.strip()
        if not text:
            continue
        try:
            request = json.loads(text)
        except json.JSONDecodeError as exc:
            response = session_message("error", error=f"invalid json: {exc}")
        else:
            response = handle_session_request(request)
        print(json.dumps(response, ensure_ascii=False), flush=True)
        if response.get("type") == "bye":
            return 0
    return 0

def cmd_reply(args):
    with state_lock():
        state = load_state()
        question = find_question(state, args.question_id)
        if not question:
            print(f"mew: question not found: {args.question_id}", file=sys.stderr)
            return 1
    try:
        event = queue_user_message(args.text, reply_to_question_id=question["id"], require_open_question=True)
    except MewError as exc:
        print(f"mew: {exc}", file=sys.stderr)
        return 1
    print(f"answered question #{question['id']} with event #{event['id']}")
    return 0

def print_ack_messages(messages):
    for message in messages:
        print(f"#{message.get('id')} [{message.get('type')}] {message.get('text') or ''}")

def find_ack_messages(state, message_ids):
    wanted = {str(message_id) for message_id in message_ids}
    return [message for message in state.get("outbox", []) if str(message.get("id")) in wanted]

def cmd_ack(args):
    with state_lock():
        state = load_state()
        if args.all and getattr(args, "routine", False):
            print("mew: choose either --all or --routine", file=sys.stderr)
            return 1
        if getattr(args, "routine", False):
            messages = [
                message
                for message in state["outbox"]
                if is_routine_outbox_message(state, message)
            ]
            if getattr(args, "dry_run", False):
                print(f"would acknowledge {len(messages)} routine message(s)")
                if getattr(args, "verbose", False):
                    print_ack_messages(messages)
                return 0
            for message in messages:
                mark_message_read(state, message["id"])
            save_state(state)
            print(f"acknowledged {len(messages)} routine message(s)")
            if getattr(args, "verbose", False):
                print_ack_messages(messages)
            return 0
        if args.all:
            messages = [message for message in state["outbox"] if not message.get("read_at")]
            if getattr(args, "dry_run", False):
                print(f"would acknowledge {len(messages)} message(s)")
                if getattr(args, "verbose", False):
                    print_ack_messages(messages)
                return 0
            for message in messages:
                mark_message_read(state, message["id"])
            save_state(state)
            print(f"acknowledged {len(messages)} message(s)")
            if getattr(args, "verbose", False):
                print_ack_messages(messages)
            return 0

        if not args.message_ids:
            print("mew: ack requires a message id, --all, or --routine", file=sys.stderr)
            return 1

        if getattr(args, "dry_run", False):
            messages = find_ack_messages(state, args.message_ids)
            found_ids = {str(message.get("id")) for message in messages}
            missing = [message_id for message_id in args.message_ids if str(message_id) not in found_ids]
            if missing:
                print(f"mew: message not found: {missing[0]}", file=sys.stderr)
                return 1
            messages = [message for message in messages if not message.get("read_at")]
            print(f"would acknowledge {len(messages)} message(s)")
            if getattr(args, "verbose", False):
                print_ack_messages(messages)
            return 0

        acknowledged = []
        for message_id in args.message_ids:
            message = mark_message_read(state, message_id)
            if not message:
                print(f"mew: message not found: {message_id}", file=sys.stderr)
                return 1
            acknowledged.append(message)
        save_state(state)
    if len(acknowledged) == 1:
        print(f"acknowledged message #{acknowledged[0]['id']}")
    else:
        ids = ", ".join(f"#{message['id']}" for message in acknowledged)
        print(f"acknowledged messages {ids}")
    if getattr(args, "verbose", False):
        print_ack_messages(acknowledged)
    return 0

def cmd_status(args):
    state = load_state()
    lock = read_lock()
    lock_state = "none"
    if lock:
        lock_state = "active" if pid_alive(lock.get("pid")) else "stale"

    runtime = state["runtime_status"]
    agent = state["agent_status"]
    user = state["user_status"]
    autonomy = state.get("autonomy", {})
    unread = [message for message in state["outbox"] if not message.get("read_at")]
    routine_unread = [message for message in unread if is_routine_outbox_message(state, message)]
    questions = open_questions(state)
    attention = open_attention_items(state)
    running_agents = [run for run in state["agent_runs"] if run.get("status") in ("created", "running")]
    if args.json:
        print(
            json.dumps(
                {
                    "runtime_status": runtime,
                    "agent_status": agent,
                    "user_status": user,
                    "autonomy": autonomy,
                    "lock": {
                        "state": lock_state,
                        "pid": (lock or {}).get("pid") if lock else None,
                        "started_at": (lock or {}).get("started_at") if lock else None,
                    },
                    "counts": {
                        "open_tasks": len(open_tasks(state)),
                        "open_questions": len(questions),
                        "open_attention": len(attention),
                        "running_agent_runs": len(running_agents),
                        "unread_outbox": len(unread),
                        "routine_unread_info": len(routine_unread),
                    },
                    "top_attention": attention[0] if attention else None,
                    "latest_summary": (
                        state.get("memory", {}).get("shallow", {}).get("current_context")
                        or state["knowledge"]["shallow"].get("latest_task_summary")
                    ),
                    "next_move": next_move(state),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    print(f"runtime_status: {runtime.get('state')}")
    print(f"pid: {runtime.get('pid')}")
    print(f"lock: {lock_state}")
    print(f"last_woke_at: {runtime.get('last_woke_at')}")
    print(f"last_evaluated_at: {runtime.get('last_evaluated_at')}")
    print(f"last_action: {runtime.get('last_action')}")
    print(f"current_reason: {runtime.get('current_reason') or ''}")
    print(f"current_event_id: {runtime.get('current_event_id') or ''}")
    print(f"current_phase: {runtime.get('current_phase') or ''}")
    print(f"cycle_started_at: {runtime.get('cycle_started_at') or ''}")
    print(f"last_cycle_reason: {runtime.get('last_cycle_reason') or ''}")
    print(f"last_cycle_duration_seconds: {runtime.get('last_cycle_duration_seconds')}")
    print(f"last_processed_count: {runtime.get('last_processed_count')}")
    print(f"last_agent_reflex_at: {runtime.get('last_agent_reflex_at') or ''}")
    print(
        "last_agent_reflex_report: "
        f"{json.dumps(runtime.get('last_agent_reflex_report') or {}, ensure_ascii=False)}"
    )
    print(f"agent_mode: {agent.get('mode')}")
    print(f"agent_focus: {agent.get('current_focus')}")
    print(f"agent_last_thought: {agent.get('last_thought')}")
    print(f"autonomy_enabled: {autonomy.get('enabled')}")
    print(f"autonomy_level: {autonomy.get('level')}")
    print(f"autonomy_paused: {autonomy.get('paused')}")
    print(f"autonomy_level_override: {autonomy.get('level_override') or ''}")
    print(f"autonomy_cycles: {autonomy.get('cycles')}")
    print(f"last_self_review_at: {autonomy.get('last_self_review_at')}")
    print(f"user_mode: {user.get('mode')}")
    print(f"user_focus: {user.get('current_focus')}")
    print(f"user_last_request: {user.get('last_request')}")
    print(f"open_tasks: {len(open_tasks(state))}")
    print(f"open_questions: {len(questions)}")
    print(f"open_attention: {len(attention)}")
    print(f"running_agent_runs: {len(running_agents)}")
    if attention:
        top = attention[0]
        print(f"top_attention: #{top['id']} {top.get('title')}: {top.get('reason')}")
    print(f"unread_outbox: {len(unread)}")
    print(f"routine_unread_info: {len(routine_unread)}")
    if routine_unread:
        print("routine_cleanup: mew ack --routine")
    memory = state.get("memory", {}).get("shallow", {})
    latest_summary = memory.get("current_context") or state["knowledge"]["shallow"].get("latest_task_summary")
    print(f"latest_summary: {latest_summary}")
    print(f"next_move: {next_move(state)}")
    return 0

def cmd_start(args):
    if runtime_is_active():
        lock = read_lock()
        print(f"mew: runtime is already running pid={lock.get('pid')}", file=sys.stderr)
        return 1

    ensure_state_dir()
    run_args = list(args.run_args or [])
    if run_args and run_args[0] == "--":
        run_args = run_args[1:]
    command = [sys.executable, "-m", "mew", "run", *run_args]
    output_path = STATE_DIR / "runtime.out"
    env = os.environ.copy()
    source_root = Path(__file__).resolve().parents[1]
    if (source_root / "mew" / "__main__.py").exists():
        existing_pythonpath = env.get("PYTHONPATH")
        env["PYTHONPATH"] = str(source_root) if not existing_pythonpath else str(source_root) + os.pathsep + existing_pythonpath
    with output_path.open("ab") as output:
        process = subprocess.Popen(
            command,
            stdout=output,
            stderr=subprocess.STDOUT,
            env=env,
            start_new_session=True,
        )

    print(f"started runtime pid={process.pid} output={output_path}")
    print("command: " + " ".join(command))
    if not args.wait:
        return 0

    deadline = time.monotonic() + max(0.0, args.timeout)
    while time.monotonic() < deadline:
        if runtime_is_active():
            print("runtime is active")
            return 0
        if process.poll() is not None:
            print(
                f"mew: runtime exited before becoming active exit_code={process.returncode}",
                file=sys.stderr,
            )
            return 1
        time.sleep(max(0.01, args.poll_interval))

    print("mew: timed out waiting for runtime to become active", file=sys.stderr)
    return 1

def cmd_stop(args):
    lock = read_lock()
    if not lock:
        print("No active runtime.")
        return 0

    pid = lock.get("pid")
    if not pid_alive(pid):
        print(f"mew: runtime lock is stale pid={pid}", file=sys.stderr)
        return 1

    try:
        os.kill(int(pid), signal.SIGTERM)
    except (OSError, ValueError) as exc:
        print(f"mew: failed to stop runtime pid={pid}: {exc}", file=sys.stderr)
        return 1

    print(f"sent stop signal to runtime pid={pid}")
    if not args.wait:
        return 0

    deadline = time.monotonic() + max(0.0, args.timeout)
    while time.monotonic() < deadline:
        if not runtime_is_active():
            print("runtime stopped")
            return 0
        time.sleep(max(0.01, args.poll_interval))

    print(f"mew: timed out waiting for runtime pid={pid} to stop", file=sys.stderr)
    return 1

def build_doctor_data(args):
    data = {"ok": True}
    state = None
    try:
        state = load_state()
        validation_issues = validate_state(state)
        current_sha256 = state_digest(state)
        last_effect = read_last_state_effect()
        data["state"] = {
            "ok": not validation_errors(validation_issues),
            "version": state.get("version"),
            "tasks": len(state.get("tasks", [])),
            "agent_runs": len(state.get("agent_runs", [])),
            "validation_issues": validation_issues,
            "current_sha256": current_sha256,
            "last_effect": last_effect,
            "last_effect_matches_current": bool(
                last_effect and last_effect.get("state_sha256") == current_sha256
            ),
        }
        if validation_errors(validation_issues):
            data["ok"] = False
    except Exception as exc:
        data["state"] = {"ok": False, "error": str(exc)}
        data["ok"] = False

    lock = read_lock()
    if lock:
        lock_state = "active" if pid_alive(lock.get("pid")) else "stale"
        data["runtime_lock"] = {"state": lock_state, "pid": lock.get("pid")}
    else:
        data["runtime_lock"] = {"state": "none", "pid": None}
    runtime_status = (state or {}).get("runtime_status", {})
    incomplete_cycle = bool(
        runtime_status.get("current_phase")
        or runtime_status.get("current_event_id")
        or runtime_status.get("current_reason")
    )
    runtime_effects = list((state or {}).get("runtime_effects", []))
    incomplete_effects = incomplete_runtime_effects(state or {})
    latest_runtime_effect = runtime_effects[-1] if runtime_effects else None
    data["runtime"] = {
        "state": runtime_status.get("state"),
        "pid": runtime_status.get("pid"),
        "current_phase": runtime_status.get("current_phase"),
        "current_event_id": runtime_status.get("current_event_id"),
        "current_effect_id": runtime_status.get("current_effect_id"),
        "current_reason": runtime_status.get("current_reason"),
        "cycle_started_at": runtime_status.get("cycle_started_at"),
        "incomplete_cycle": incomplete_cycle,
    }
    data["runtime_effects"] = {
        "total": len(runtime_effects),
        "incomplete": len(incomplete_effects),
        "latest": latest_runtime_effect,
    }
    if data["runtime_lock"]["state"] == "stale" or (
        incomplete_cycle and data["runtime_lock"]["state"] != "active"
    ) or (
        incomplete_effects and data["runtime_lock"]["state"] != "active"
    ):
        data["ok"] = False

    data["tools"] = {}
    for executable in ("ai-cli", "rg"):
        path = shutil.which(executable)
        if path:
            data["tools"][executable] = {"ok": True, "path": path}
        else:
            data["tools"][executable] = {"ok": False, "path": None}
            data["ok"] = False

    try:
        auth = load_codex_oauth(args.auth)
        account = "present" if auth.get("account_id") else "none"
        expires = auth.get("expires") or "(unknown)"
        data["codex_auth"] = {
            "ok": True,
            "level": "ok",
            "path": auth.get("path"),
            "account_id": account,
            "expires": expires,
        }
    except MewError as exc:
        level = "error" if args.require_auth else "missing"
        data["codex_auth"] = {"ok": not args.require_auth, "level": level, "error": str(exc)}
        if args.require_auth:
            data["ok"] = False
    return data

def format_doctor_data(data):
    lines = []
    state = data.get("state") or {}
    if state.get("ok"):
        lines.append("state: ok")
        lines.append(f"state_version: {state.get('version')}")
        lines.append(f"tasks: {state.get('tasks')}")
        lines.append(f"agent_runs: {state.get('agent_runs')}")
        lines.append(format_validation_issues(state.get("validation_issues") or []))
        last_effect = state.get("last_effect")
        if last_effect:
            lines.append(
                "last_state_effect: "
                f"{last_effect.get('saved_at')} sha256={str(last_effect.get('state_sha256') or '')[:12]} "
                f"matches_current={state.get('last_effect_matches_current')} "
                f"counts={last_effect.get('counts')}"
            )
        else:
            lines.append("last_state_effect: none")
    else:
        lines.append(f"state: error {state.get('error') or 'validation failed'}")
        if state.get("validation_issues"):
            lines.append(format_validation_issues(state.get("validation_issues") or []))

    runtime_lock = data.get("runtime_lock") or {}
    if runtime_lock.get("state") == "none":
        lines.append("runtime_lock: none")
    else:
        lines.append(f"runtime_lock: {runtime_lock.get('state')} pid={runtime_lock.get('pid')}")
    runtime = data.get("runtime") or {}
    lines.append(
        "runtime: "
        f"{runtime.get('state') or 'unknown'} pid={runtime.get('pid')} "
        f"phase={runtime.get('current_phase') or ''} "
        f"effect={runtime.get('current_effect_id') or ''} "
        f"incomplete_cycle={bool(runtime.get('incomplete_cycle'))}"
    )
    runtime_effects = data.get("runtime_effects") or {}
    latest_effect = runtime_effects.get("latest") or {}
    latest_text = "none"
    if latest_effect:
        latest_text = (
            f"#{latest_effect.get('id')} status={latest_effect.get('status')} "
            f"event=#{latest_effect.get('event_id')} reason={latest_effect.get('reason')} "
            f"actions={','.join(latest_effect.get('action_types') or []) or '-'}"
        )
    lines.append(
        "runtime_effects: "
        f"total={runtime_effects.get('total', 0)} "
        f"incomplete={runtime_effects.get('incomplete', 0)} "
        f"latest={latest_text}"
    )

    for executable in ("ai-cli", "rg"):
        tool = (data.get("tools") or {}).get(executable) or {}
        if tool.get("ok"):
            lines.append(f"{executable}: ok {tool.get('path')}")
        else:
            lines.append(f"{executable}: missing")

    auth = data.get("codex_auth") or {}
    if auth.get("level") == "ok":
        lines.append(
            "codex_auth: ok "
            f"path={auth.get('path')} account_id={auth.get('account_id')} expires={auth.get('expires')}"
        )
    else:
        lines.append(f"codex_auth: {auth.get('level')} {auth.get('error')}")
    return "\n".join(lines)

def cmd_doctor(args):
    data = build_doctor_data(args)
    if getattr(args, "json", False):
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(format_doctor_data(data))

    return 0 if data.get("ok") else 1

def legacy_task_command_question(task_id):
    return f"Task #{task_id} is ready but has no command. What should I execute for it?"

def repair_stale_task_questions(state):
    task_by_id = {task.get("id"): task for task in state.get("tasks", [])}
    outbox_by_id = {message.get("id"): message for message in state.get("outbox", [])}
    repairs = []
    for question in state.get("questions", []):
        if question.get("status") != "open":
            continue
        task_id = question.get("related_task_id")
        task = task_by_id.get(task_id)
        if not task:
            continue
        legacy_text = legacy_task_command_question(task_id)
        if question.get("text") != legacy_text:
            continue
        replacement = task_question(task)
        if not replacement or replacement == legacy_text:
            continue
        question["text"] = replacement
        message = outbox_by_id.get(question.get("outbox_message_id"))
        if message and message.get("type") == "question":
            message["text"] = replacement
        for item in state.get("attention", {}).get("items", []):
            if item.get("question_id") == question.get("id") and item.get("status") == "open":
                item["reason"] = replacement
        repairs.append(
            {
                "type": "stale_task_question",
                "question_id": question.get("id"),
                "task_id": task_id,
                "old_text": legacy_text,
                "new_text": replacement,
            }
        )
    return repairs

def runtime_effect_recovery_hint(effect, old_status):
    event_id = effect.get("event_id")
    event_ref = "the selected event" if event_id is None else f"event #{event_id}"
    if old_status in ("planning", "planned", "precomputing", "precomputed"):
        return f"Re-run {event_ref}; no action was recorded as committed."
    if old_status == "committing":
        actions = ", ".join(effect.get("action_types") or []) or "unknown actions"
        return f"Inspect effect #{effect.get('id')} before retrying; it stopped while committing {actions}."
    return f"Inspect effect #{effect.get('id')} before retrying {event_ref}."

def repair_incomplete_runtime_effects(state):
    current_time = now_iso()
    repairs = []
    for effect in incomplete_runtime_effects(state):
        old_status = effect.get("status")
        recovery_hint = runtime_effect_recovery_hint(effect, old_status)
        update_runtime_effect(
            state,
            effect.get("id"),
            current_time=current_time,
            status="interrupted",
            error="Runtime stopped before this effect reached a terminal state.",
            recovery_hint=recovery_hint,
            finished_at=current_time,
        )
        repairs.append(
            {
                "type": "interrupted_runtime_effect",
                "effect_id": effect.get("id"),
                "event_id": effect.get("event_id"),
                "old_status": old_status,
                "new_status": "interrupted",
                "recovery_hint": recovery_hint,
            }
        )
    return repairs


def repair_incomplete_work_sessions(state):
    return mark_running_work_interrupted(state)


def build_repair_data():
    try:
        with state_lock():
            state = load_state()
            before_sha = state_digest(state)
            reconcile_next_ids(state)
            repairs = []
            repairs.extend(repair_stale_task_questions(state))
            repairs.extend(repair_incomplete_runtime_effects(state))
            repairs.extend(repair_incomplete_work_sessions(state))
            issues = validate_state(state)
            errors = validation_errors(issues)
            if errors:
                return {
                    "ok": False,
                    "repaired": False,
                    "before_sha256": before_sha,
                    "after_sha256": before_sha,
                    "repairs": repairs,
                    "validation_issues": issues,
                }
            save_state(state)
            after_sha = state_digest(state)
            last_effect = read_last_state_effect()
            if last_effect and last_effect.get("state_sha256"):
                after_sha = last_effect["state_sha256"]
            return {
                "ok": True,
                "repaired": before_sha != after_sha,
                "before_sha256": before_sha,
                "after_sha256": after_sha,
                "repairs": repairs,
                "validation_issues": validate_state(state),
                "last_effect": last_effect,
            }
    except Exception as exc:
        return {
            "ok": False,
            "repaired": False,
            "before_sha256": "",
            "after_sha256": "",
            "repairs": [],
            "validation_issues": [
                {"level": "error", "path": "$", "message": f"unable to load or repair state: {exc}"}
            ],
        }

def cmd_repair(args):
    if runtime_is_active() and not args.force:
        data = {
            "ok": False,
            "repaired": False,
            "validation_issues": [
                {
                    "level": "error",
                    "path": "runtime_lock",
                    "message": "runtime is active; stop it before repair or pass --force",
                }
            ],
        }
        if getattr(args, "json", False):
            print(json.dumps(data, ensure_ascii=False, indent=2))
        else:
            print("mew: runtime is active; stop it before repair or pass --force", file=sys.stderr)
        return 1
    data = build_repair_data()
    if getattr(args, "json", False):
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        if data.get("ok"):
            status = "repaired" if data.get("repaired") else "already valid"
            print(f"state_repair: {status}")
            print(f"before_sha256: {str(data.get('before_sha256') or '')[:12]}")
            print(f"after_sha256: {str(data.get('after_sha256') or '')[:12]}")
            repairs = data.get("repairs") or []
            if repairs:
                print(f"repairs: {len(repairs)}")
                for repair in repairs:
                    if repair.get("type") == "interrupted_runtime_effect":
                        print(
                            f"- {repair.get('type')} effect=#{repair.get('effect_id')} "
                            f"event=#{repair.get('event_id')} {repair.get('old_status')}->{repair.get('new_status')}"
                        )
                        print(f"  next: {repair.get('recovery_hint')}")
                    elif repair.get("type") == "interrupted_work_tool_call":
                        print(
                            f"- {repair.get('type')} session=#{repair.get('session_id')} "
                            f"tool_call=#{repair.get('tool_call_id')} "
                            f"{repair.get('old_status')}->{repair.get('new_status')}"
                        )
                        print(f"  next: {repair.get('recovery_hint')}")
                    elif repair.get("type") == "interrupted_work_model_turn":
                        print(
                            f"- {repair.get('type')} session=#{repair.get('session_id')} "
                            f"model_turn=#{repair.get('model_turn_id')} "
                            f"{repair.get('old_status')}->{repair.get('new_status')}"
                        )
                        print(f"  next: {repair.get('recovery_hint')}")
                    else:
                        print(
                            f"- {repair.get('type')} question=#{repair.get('question_id')} "
                            f"task=#{repair.get('task_id')}"
                        )
            print(format_validation_issues(data.get("validation_issues") or []))
        else:
            print("state_repair: failed")
            print(format_validation_issues(data.get("validation_issues") or []))
    return 0 if data.get("ok") else 1

def cmd_brief(args):
    state = load_state()
    if args.json:
        print(json.dumps(build_brief_data(state, limit=args.limit), ensure_ascii=False, indent=2))
        return 0
    print(build_brief(state, limit=args.limit))
    return 0

def cmd_focus(args):
    state = load_state()
    data = build_focus_data(state, limit=args.limit)
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0
    print(format_focus(data))
    return 0

def cmd_activity(args):
    state = load_state()
    if args.json:
        print(json.dumps(build_activity_data(state, limit=args.limit), ensure_ascii=False, indent=2))
        return 0
    print(format_activity(state, limit=args.limit))
    return 0


def format_context_report(context, current_time):
    stats = context.get("context_stats", {})
    lines = [
        f"Mew context at {current_time}",
        f"approx_chars: {stats.get('approx_chars', 0)}",
    ]
    limits = stats.get("limits", {})
    if limits:
        limit_text = ", ".join(f"{key}={value}" for key, value in sorted(limits.items()))
        lines.append(f"limits: {limit_text}")

    for label, values in (
        ("source", stats.get("source_counts", {})),
        ("included", stats.get("included_counts", {})),
        ("omitted", stats.get("omitted_counts", {})),
    ):
        if values:
            value_text = ", ".join(f"{key}={value}" for key, value in sorted(values.items()))
            lines.append(f"{label}: {value_text}")

    section_chars = stats.get("section_chars", {})
    if section_chars:
        lines.append("")
        lines.append("Largest sections")
        largest = sorted(section_chars.items(), key=lambda item: item[1], reverse=True)[:8]
        for key, chars in largest:
            lines.append(f"- {key}: {chars}")
    return "\n".join(lines)


def cmd_context(args):
    state = load_state()
    current_time = now_iso()
    message = getattr(args, "context_message", None)
    event = {
        "id": 0,
        "type": "user_message" if message else args.event_type,
        "source": "context_command",
        "payload": {"text": message} if message else {},
        "created_at": current_time,
        "processed_at": None,
    }
    autonomy = state.get("autonomy", {})
    context = build_context(
        state,
        event,
        current_time,
        allowed_read_roots=args.allowed_read_root or [],
        self_text=read_self(),
        desires=read_desires(),
        autonomous=bool(autonomy.get("enabled")),
        autonomy_level=autonomy.get("level") or "off",
        allow_agent_run=bool(autonomy.get("allow_agent_run")),
        allow_verify=bool(autonomy.get("allow_verify")),
        verify_command="configured" if autonomy.get("verify_command_configured") else "",
        allow_write=bool(autonomy.get("allow_write")),
    )
    if args.json:
        print(json.dumps(context, ensure_ascii=False, indent=2))
        return 0
    print(format_context_report(context, current_time))
    return 0


def cmd_step(args):
    try:
        model_backend = normalize_model_backend(args.model_backend)
    except MewError as exc:
        print(f"mew: {exc}", file=sys.stderr)
        return 1

    model = args.model or model_backend_default_model(model_backend)
    base_url = args.base_url or model_backend_default_base_url(model_backend)
    model_auth = None
    if args.ai:
        try:
            model_auth = load_model_auth(model_backend, args.auth)
        except MewError as exc:
            print(f"mew: {exc}", file=sys.stderr)
            return 1

    if not args.dry_run:
        ensure_guidance(args.guidance)
        ensure_policy(args.policy)
        ensure_self(args.self_file)
        ensure_desires(args.desires)
    guidance = read_guidance(args.guidance)
    if args.focus:
        focus_text = args.focus.strip()
        if focus_text:
            guidance = "\n\n".join(
                part
                for part in (
                    guidance.strip(),
                    (
                        "Immediate step focus:\n"
                        f"{focus_text}\n"
                        "Prefer this focus over unrelated existing tasks or questions during this step loop. "
                        "Do not stop solely because an unrelated older question is waiting."
                    ),
                )
                if part
            )
    if args.allow_read:
        guidance = "\n\n".join(
            part
            for part in (
                guidance.strip(),
                (
                    "Manual step read permission:\n"
                    "Read-only local inspection is available for this step. "
                    "When the focus asks for implementation planning, repository reasoning, "
                    "or current-code evaluation, prefer one small targeted inspect_dir, read_file, "
                    "or search_text action before proposing a plan. Keep the read narrow."
                ),
            )
            if part
        )
    if args.allow_write:
        guidance = "\n\n".join(
            part
            for part in (
                guidance.strip(),
                (
                    "Manual step write permission:\n"
                    "Gated write_file/edit_file actions are available under --allow-write roots. "
                    "Omitting dry_run is treated as dry_run=true. "
                    "Set dry_run=false only for a small targeted write, and only when "
                    "--allow-verify plus a verification command are configured."
                ),
            )
            if part
        )

    progress = None
    if args.ai and not args.json:
        progress = lambda line: print(f"mew step: {line}", file=sys.stderr, flush=True)

    report = run_step_loop(
        max_steps=args.max_steps,
        dry_run=args.dry_run,
        model_auth=model_auth,
        model=model,
        base_url=base_url,
        model_backend=model_backend,
        timeout=args.timeout,
        guidance=guidance,
        policy=read_policy(args.policy),
        self_text=read_self(args.self_file),
        desires=read_desires(args.desires),
        autonomy_level=args.autonomy_level,
        allowed_read_roots=args.allow_read or [],
        allowed_write_roots=args.allow_write or [],
        allow_verify=args.allow_verify,
        verify_command=args.verify_command or "",
        verify_timeout=args.verify_timeout,
        allow_write=bool(args.allow_write),
        trace_model=getattr(args, "trace_model", False),
        max_reflex_rounds=getattr(args, "max_reflex_rounds", 0),
        progress=progress,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(format_step_loop_report(report))
    return 0


def cmd_perceive(args):
    roots = args.allow_read or []
    perception = perceive_workspace(allowed_read_roots=roots, cwd=args.cwd)
    if args.json:
        print(json.dumps(perception, ensure_ascii=False, indent=2))
        return 0
    print(format_perception(perception))
    return 0

def cmd_next(args):
    state = load_state()
    move = next_move(state)
    if args.json:
        print(
            json.dumps(
                {"next_move": move, "command": command_from_next_move(move)},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    print(move)
    return 0

def cmd_dogfood(args):
    if args.allow_verify and not args.verify_command:
        print("mew: --allow-verify requires --verify-command", file=sys.stderr)
        return 1
    try:
        if getattr(args, "scenario", ""):
            report = run_dogfood_scenario(args)
        elif getattr(args, "cycles", 1) and args.cycles > 1:
            report = run_dogfood_loop(args)
        else:
            report = run_dogfood(args)
    except ValueError as exc:
        print(f"mew: {exc}", file=sys.stderr)
        return 1

    if getattr(args, "scenario", ""):
        report_path = write_report_if_requested(args, report)
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            print(format_dogfood_scenario_report(report))
            if report_path:
                print(f"report_path: {report_path}")
        return 0 if report.get("status") == "pass" else 1
    if getattr(args, "cycles", 1) and args.cycles > 1:
        report_path = write_report_if_requested(args, report)
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0
        print(format_dogfood_loop_report(report))
        if report_path:
            print(f"report_path: {report_path}")
        return 0
    report_path = write_report_if_requested(args, report)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    print(format_dogfood_report(report))
    if report_path:
        print(f"report_path: {report_path}")
    return 0

def write_report_if_requested(args, report):
    path_arg = getattr(args, "report", None)
    if not path_arg:
        return ""
    path = os.path.abspath(os.path.expanduser(path_arg))
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    report["report_path"] = path
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return path

def command_from_next_move(move):
    parts = (move or "").split("`")
    for index in range(1, len(parts), 2):
        candidate = parts[index].strip()
        if candidate.startswith("mew ") or candidate.startswith("uv run mew "):
            return candidate
    practical_prefixes = (
        "advance coding task #",
        "spend 10 minutes researching task #",
        "take one concrete admin step on task #",
        "take one 5-minute personal step on task #",
        "clarify or take one small step on task #",
    )
    for prefix in practical_prefixes:
        if not (move or "").startswith(prefix):
            continue
        task_id = (move or "")[len(prefix):].split(":", 1)[0].strip()
        if task_id.isdigit():
            return f"mew work {task_id}"
    return ""

def format_verification_run(run):
    return (
        f"#{run.get('id')} [{verification_outcome(run)}] "
        f"exit_code={run.get('exit_code')} command={run.get('command')} "
        f"finished_at={run.get('finished_at') or run.get('updated_at') or run.get('created_at')}"
    )

def cmd_verification(args):
    state = load_state()
    runs = list(state.get("verification_runs", []))
    if not runs:
        print("No verification runs.")
        return 0
    if not args.all:
        runs = runs[-args.limit :]
    runs = list(reversed(runs))
    if args.json:
        print(json.dumps(runs, ensure_ascii=False, indent=2))
        return 0
    for run in runs:
        print(format_verification_run(run))
        if args.details:
            if run.get("stdout"):
                print("stdout:")
                print(run["stdout"])
            if run.get("stderr"):
                print("stderr:")
                print(run["stderr"])
    return 0

def format_write_run(run):
    rollback = f" rolled_back={run.get('rolled_back')}" if run.get("rolled_back") is not None else ""
    verification = (
        f" verification=#{run.get('verification_run_id')} exit={run.get('verification_exit_code')}"
        if run.get("verification_run_id") is not None
        else ""
    )
    return (
        f"#{run.get('id')} [{run.get('operation') or run.get('action_type')}] "
        f"changed={run.get('changed')} dry_run={run.get('dry_run')} "
        f"written={run.get('written')}{rollback}{verification} path={run.get('path')}"
    )

def cmd_writes(args):
    state = load_state()
    runs = list(state.get("write_runs", []))
    if not runs:
        print("No write runs.")
        return 0
    if not args.all:
        runs = runs[-args.limit :]
    runs = list(reversed(runs))
    if args.json:
        print(json.dumps(runs, ensure_ascii=False, indent=2))
        return 0
    for run in runs:
        print(format_write_run(run))
        if args.details and run.get("diff"):
            print("diff:")
            print(run["diff"])
        if args.details and run.get("rollback"):
            print("rollback:")
            print(json.dumps(run["rollback"], ensure_ascii=False, indent=2))
    return 0


def cmd_thoughts(args):
    state = load_state()
    thoughts = list(state.get("thought_journal", []))
    if not thoughts:
        print("No thought journal entries.")
        return 0
    if not args.all:
        thoughts = thoughts[-args.limit :]
    thoughts = list(reversed(thoughts))
    if args.json:
        print(json.dumps(thoughts, ensure_ascii=False, indent=2))
        return 0
    for thought in thoughts:
        print(format_thought_entry(thought, details=args.details))
    return 0


def _tool_allowed_roots(args):
    roots = getattr(args, "root", None) or ["."]
    return roots

def _print_json_or_text(result, as_json, text):
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(text)

def cmd_tool_list(args):
    try:
        result = inspect_dir(args.path, _tool_allowed_roots(args), limit=args.limit)
    except ValueError as exc:
        print(f"mew: {exc}", file=sys.stderr)
        return 1
    _print_json_or_text(result, args.json, summarize_read_result("inspect_dir", result))
    return 0

def cmd_tool_read(args):
    try:
        result = read_file(args.path, _tool_allowed_roots(args), max_chars=args.max_chars, offset=args.offset)
    except ValueError as exc:
        print(f"mew: {exc}", file=sys.stderr)
        return 1
    _print_json_or_text(result, args.json, summarize_read_result("read_file", result))
    return 0

def cmd_tool_search(args):
    try:
        result = search_text(
            args.query,
            args.path,
            _tool_allowed_roots(args),
            max_matches=args.max_matches,
        )
    except ValueError as exc:
        print(f"mew: {exc}", file=sys.stderr)
        return 1
    _print_json_or_text(result, args.json, summarize_read_result("search_text", result))
    return 0

def cmd_tool_glob(args):
    try:
        result = glob_paths(
            args.pattern,
            args.path,
            _tool_allowed_roots(args),
            max_matches=args.max_matches,
        )
    except ValueError as exc:
        print(f"mew: {exc}", file=sys.stderr)
        return 1
    _print_json_or_text(result, args.json, summarize_read_result("glob", result))
    return 0

def cmd_tool_write(args):
    try:
        result = write_file(
            args.path,
            args.content,
            _tool_allowed_roots(args),
            create=args.create,
            dry_run=args.dry_run,
        )
    except ValueError as exc:
        print(f"mew: {exc}", file=sys.stderr)
        return 1
    _print_json_or_text(result, args.json, summarize_write_result(result))
    return 0

def cmd_tool_edit(args):
    try:
        result = edit_file(
            args.path,
            args.old,
            args.new,
            _tool_allowed_roots(args),
            replace_all=args.replace_all,
            dry_run=args.dry_run,
        )
    except ValueError as exc:
        print(f"mew: {exc}", file=sys.stderr)
        return 1
    _print_json_or_text(result, args.json, summarize_write_result(result))
    return 0

def cmd_tool_status(args):
    try:
        result = run_git_tool("status", cwd=args.cwd)
    except ValueError as exc:
        print(f"mew: {exc}", file=sys.stderr)
        return 1
    if result.get("exit_code") == 128 and "not a git repository" in (result.get("stderr") or ""):
        result = {
            **result,
            "git": {
                "available": False,
                "exit_code": result.get("exit_code"),
                "reason": "not a git repository",
            },
        }
        text = "\n".join(
            [
                "workspace status",
                f"cwd: {result.get('cwd')}",
                "git: unavailable (not a git repository)",
            ]
        )
        _print_json_or_text(result, args.json, text)
        return 0
    _print_json_or_text(result, args.json, format_command_record(result))
    return 0 if result.get("exit_code") == 0 else 1

def cmd_tool_test(args):
    try:
        result = run_command_record(args.command, cwd=args.cwd, timeout=args.timeout)
    except ValueError as exc:
        print(f"mew: {exc}", file=sys.stderr)
        return 1
    _print_json_or_text(result, args.json, format_command_record(result))
    return 0 if result.get("exit_code") == 0 else 1

def cmd_tool_git(args):
    try:
        result = run_git_tool(
            args.git_action,
            cwd=args.cwd,
            limit=getattr(args, "limit", 20),
            staged=getattr(args, "staged", False),
            stat=getattr(args, "stat", False),
            base=getattr(args, "base", ""),
        )
    except ValueError as exc:
        print(f"mew: {exc}", file=sys.stderr)
        return 1
    _print_json_or_text(result, args.json, format_command_record(result))
    return 0 if result.get("exit_code") == 0 else 1

def cmd_self_improve(args):
    if args.cycle:
        return cmd_self_improve_cycle(args)
    if args.cycles != 1:
        print("mew: --cycles requires --cycle", file=sys.stderr)
        return 1

    with state_lock():
        state = load_state()
        task, created = create_self_improve_task(
            state,
            title=args.title,
            description=args.description,
            focus=args.focus or "",
            cwd=args.cwd or ".",
            priority=args.priority,
            ready=args.ready or args.dispatch,
            auto_execute=args.auto_execute,
            agent_model=args.agent_model,
            force=args.force,
        )
        plan = None
        plan_created = False
        run = None
        if not args.no_plan or args.dispatch:
            plan, plan_created = ensure_self_improve_plan(
                state,
                task,
                agent_model=args.agent_model,
                review_model=args.review_model,
                force=args.force_plan,
            )
        if args.dispatch:
            run = create_implementation_run_from_plan(state, task, plan, dry_run=args.dry_run)
            if args.dry_run:
                ensure_agent_run_prompt_file(run)
                run["command"] = build_ai_cli_run_command(run)
            else:
                start_agent_run(state, run)
        save_state(state)

    print(("created" if created else "reused") + f" {format_task(task)}")
    if plan:
        print(("created" if plan_created else "reused") + f" {format_task_plan(plan)}")
    if run:
        if args.dry_run:
            print(f"created dry-run self-improve run #{run['id']}")
            print(" ".join(run["command"]))
        else:
            print(f"started self-improve run #{run['id']} status={run.get('status')} pid={run.get('external_pid')}")
            if run.get("status") != "running":
                return 1
    return 0

def _create_self_improve_implementation_run(args):
    state = load_state()
    task, created = create_self_improve_task(
        state,
        title=args.title,
        description=args.description,
        focus=args.focus or "",
        cwd=args.cwd or ".",
        priority=args.priority,
        ready=True,
        auto_execute=args.auto_execute,
        agent_model=args.agent_model,
        force=args.force,
    )
    plan, plan_created = ensure_self_improve_plan(
        state,
        task,
        agent_model=args.agent_model,
        review_model=args.review_model,
        force=args.force_plan,
    )
    run = create_implementation_run_from_plan(state, task, plan, dry_run=args.dry_run)
    if args.dry_run:
        ensure_agent_run_prompt_file(run)
        run["command"] = build_ai_cli_run_command(run)
    else:
        start_agent_run(state, run)
    save_state(state)
    return state, task, created, plan, plan_created, run

def _wait_cycle_run(args, run_id):
    with state_lock():
        state = load_state()
        run = find_agent_run(state, run_id)
        if not run:
            raise MewError(f"agent run not found: {run_id}")
        try:
            wait_agent_run(state, run, timeout=args.timeout)
        except ValueError as exc:
            raise MewError(str(exc)) from exc
        save_state(state)
    return run

def _run_verification_command(command, cwd, timeout):
    try:
        return run_command_record(command, cwd=cwd, timeout=timeout)
    except ValueError as exc:
        raise MewError(str(exc)) from exc

def _verify_cycle_implementation(args, run_id):
    if not args.verify_command:
        return None

    with state_lock():
        state = load_state()
        run = find_agent_run(state, run_id)
        if not run:
            raise MewError(f"agent run not found: {run_id}")
        cwd = run.get("cwd") or args.cwd or "."

    verification = _run_verification_command(args.verify_command, cwd, args.verify_timeout)

    with state_lock():
        state = load_state()
        run = find_agent_run(state, run_id)
        if not run:
            raise MewError(f"agent run not found: {run_id}")
        task = find_task(state, run.get("task_id"))
        run["supervisor_verification"] = verification
        run["updated_at"] = now_iso()
        if verification.get("exit_code") != 0:
            if task:
                task["status"] = "blocked"
                task["updated_at"] = run["updated_at"]
            add_outbox_message(
                state,
                "warning",
                f"Verification failed for agent run #{run['id']}: {args.verify_command}",
                related_task_id=run.get("task_id"),
                agent_run_id=run["id"],
            )
        save_state(state)

    if verification.get("exit_code") != 0:
        raise MewError(f"verification failed for run #{run_id}: exit_code={verification.get('exit_code')}")
    return verification

def _start_cycle_review(args, implementation_run_id):
    with state_lock():
        state = load_state()
        implementation_run = find_agent_run(state, implementation_run_id)
        if not implementation_run:
            raise MewError(f"agent run not found: {implementation_run_id}")
        task = find_task(state, implementation_run.get("task_id"))
        if not task:
            raise MewError(f"task not found for run #{implementation_run_id}")
        plan = find_task_plan(task, implementation_run.get("plan_id")) if implementation_run.get("plan_id") else None
        review_run = create_review_run_for_implementation(
            state,
            task,
            implementation_run,
            plan=plan,
            model=args.review_model,
        )
        start_agent_run(state, review_run)
        save_state(state)
    return review_run

def _process_cycle_review(run_id):
    with state_lock():
        state = load_state()
        review_run = find_agent_run(state, run_id)
        if not review_run:
            raise MewError(f"agent run not found: {run_id}")
        task = find_task(state, review_run.get("task_id"))
        if not task:
            raise MewError(f"task not found for review run #{run_id}")
        followup, status = create_follow_up_task_from_review(state, task, review_run)
        save_state(state)
    return review_run, followup, status

def cmd_self_improve_cycle(args):
    if args.no_plan:
        print("mew: --cycle requires planning; remove --no-plan", file=sys.stderr)
        return 1
    if args.cycles < 1:
        print("mew: --cycles must be at least 1", file=sys.stderr)
        return 1

    for cycle_index in range(args.cycles):
        try:
            with state_lock():
                state, task, created, plan, plan_created, run = _create_self_improve_implementation_run(
                    args
                )
        except MewError as exc:
            print(f"mew: {exc}", file=sys.stderr)
            return 1

        cycle_label = f"cycle {cycle_index + 1}/{args.cycles}"
        print(f"{cycle_label}: {('created' if created else 'reused')} {format_task(task)}")
        print(f"{cycle_label}: {('created' if plan_created else 'reused')} {format_task_plan(plan)}")

        if args.dry_run:
            print(f"{cycle_label}: created dry-run self-improve run #{run['id']}")
            print(" ".join(run["command"]))
            continue

        print(f"{cycle_label}: started implementation run #{run['id']} pid={run.get('external_pid')}")
        if run.get("status") != "running":
            print(f"mew: implementation run #{run['id']} status={run.get('status')}", file=sys.stderr)
            return 1

        try:
            implementation_run = _wait_cycle_run(args, run["id"])
        except MewError as exc:
            print(f"mew: {exc}", file=sys.stderr)
            return 1
        print(f"{cycle_label}: implementation run #{implementation_run['id']} status={implementation_run.get('status')}")
        if implementation_run.get("status") != "completed":
            return 1

        try:
            verification = _verify_cycle_implementation(args, implementation_run["id"])
        except MewError as exc:
            print(f"mew: {exc}", file=sys.stderr)
            return 1
        if verification:
            print(
                f"{cycle_label}: verification exit_code={verification.get('exit_code')} "
                f"command={verification.get('command')}"
            )

        try:
            review_run = _start_cycle_review(args, implementation_run["id"])
        except MewError as exc:
            print(f"mew: {exc}", file=sys.stderr)
            return 1
        print(f"{cycle_label}: started review run #{review_run['id']} pid={review_run.get('external_pid')}")
        if review_run.get("status") != "running":
            print(f"mew: review run #{review_run['id']} status={review_run.get('status')}", file=sys.stderr)
            return 1

        try:
            review_run = _wait_cycle_run(args, review_run["id"])
        except MewError as exc:
            print(f"mew: {exc}", file=sys.stderr)
            return 1
        print(f"{cycle_label}: review run #{review_run['id']} status={review_run.get('status')}")
        if review_run.get("status") != "completed":
            return 1

        try:
            review_run, followup, review_status = _process_cycle_review(review_run["id"])
        except MewError as exc:
            print(f"mew: {exc}", file=sys.stderr)
            return 1
        print(f"{cycle_label}: review status={review_status}")
        if followup:
            print(f"{cycle_label}: created follow-up {format_task(followup)}")
            return 1
        if review_status != "pass" and not args.allow_unknown_review:
            print(
                f"mew: stopping because review run #{review_run['id']} status={review_status}",
                file=sys.stderr,
            )
            return 1

    return 0

def cmd_outbox(args):
    state = load_state()
    messages = state["outbox"] if args.all else [m for m in state["outbox"] if not m.get("read_at")]
    total = len(messages)
    limit = getattr(args, "limit", None)
    if limit is not None:
        if limit < 1:
            print("mew: --limit must be positive", file=sys.stderr)
            return 1
        messages = messages[-limit:]
    if args.json:
        print(
            json.dumps(
                {
                    "messages": messages,
                    "count": len(messages),
                    "total": total,
                    "all": bool(args.all),
                    "limit": limit,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if not messages:
        print("No messages.")
        return 0
    if limit is not None and total > len(messages):
        print(f"showing last {len(messages)} of {total} message(s)")
    for message in messages:
        read = "read" if message.get("read_at") else "unread"
        print(f"#{message['id']} [{message['type']}/{read}] {message['text']}")
    return 0

def cmd_questions(args):
    if args.defer or args.reopen:
        with state_lock():
            state = load_state()
            changed = []
            for question_id in args.defer:
                question = find_question(state, question_id)
                if not question:
                    print(f"mew: question not found: {question_id}", file=sys.stderr)
                    return 1
                if question.get("status") == "answered":
                    print(f"mew: question already answered: {question_id}", file=sys.stderr)
                    return 1
                mark_question_deferred(state, question, reason=args.reason or "")
                changed.append(question)
            for question_id in args.reopen:
                question = find_question(state, question_id)
                if not question:
                    print(f"mew: question not found: {question_id}", file=sys.stderr)
                    return 1
                if question.get("status") == "answered":
                    print(f"mew: question already answered: {question_id}", file=sys.stderr)
                    return 1
                reopen_question(state, question)
                changed.append(question)
            save_state(state)
        action = "updated"
        if args.defer and not args.reopen:
            action = "deferred"
        elif args.reopen and not args.defer:
            action = "reopened"
        if args.json:
            print(
                json.dumps(
                    {"action": action, "count": len(changed), "questions": changed},
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0
        print(f"{action} {len(changed)} question(s)")
        return 0

    state = load_state()
    questions = state["questions"] if args.all else open_questions(state)
    if args.json:
        print(
            json.dumps(
                {"questions": questions, "count": len(questions), "all": bool(args.all)},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if not questions:
        print("No questions.")
        return 0
    for question in questions:
        status = question.get("status")
        task = question.get("related_task_id")
        task_text = f" task=#{task}" if task else ""
        print(f"#{question['id']} [{status}]{task_text} {question['text']}")
    return 0

def cmd_attention(args):
    if args.resolve or args.resolve_all:
        with state_lock():
            state = load_state()
            current_time = now_iso()
            if args.resolve_all:
                items = [item for item in state["attention"]["items"] if item.get("status") == "open"]
            else:
                ids = {str(item_id) for item_id in args.resolve}
                items = [
                    item
                    for item in state["attention"]["items"]
                    if str(item.get("id")) in ids and item.get("status") == "open"
                ]
                found_ids = {str(item.get("id")) for item in items}
                missing = ids - found_ids
                if missing:
                    print(f"mew: attention not found or already resolved: {', '.join(sorted(missing))}", file=sys.stderr)
                    return 1
            for item in items:
                item["status"] = "resolved"
                item["resolved_at"] = current_time
                item["updated_at"] = current_time
            save_state(state)
        if args.json:
            print(
                json.dumps(
                    {"action": "resolved", "count": len(items), "attention": items},
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0
        print(f"resolved {len(items)} attention item(s)")
        return 0

    state = load_state()
    items = state["attention"]["items"] if args.all else open_attention_items(state)
    if args.json:
        print(
            json.dumps(
                {"attention": items, "count": len(items), "all": bool(args.all)},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if not items:
        print("No attention items.")
        return 0
    for item in items:
        status = item.get("status")
        priority = item.get("priority")
        print(f"#{item['id']} [{status}/{priority}] {item.get('title')}: {item.get('reason')}")
    return 0

def cmd_archive(args):
    with state_lock():
        state = load_state()
        result = archive_state_records(
            state,
            keep_recent=args.keep_recent,
            dry_run=not args.apply,
        )
        if args.apply:
            save_state(state)
    print(format_archive_result(result))
    if not args.apply and result.get("total_archived"):
        print("Run `mew archive --apply` to write the archive and compact active state.")
    return 0

def cmd_memory(args):
    if args.add:
        with state_lock():
            state = load_state()
            entry = add_deep_memory(state, args.category, args.add)
            save_state(state)
        if args.json:
            print(json.dumps({"category": args.category, "entry": entry}, ensure_ascii=False, indent=2))
        else:
            print(f"remembered {args.category}: {entry}")
        return 0

    if args.compact:
        with state_lock():
            state = load_state()
            note = compact_memory(state, keep_recent=args.keep_recent, dry_run=args.dry_run)
            if not args.dry_run:
                save_state(state)
        print(note)
        return 0

    state = load_state()
    if args.search:
        results = search_memory(state, args.search, limit=args.limit)
        if args.json:
            print(json.dumps({"query": args.search, "matches": results}, ensure_ascii=False, indent=2))
            return 0
        if not results:
            print("No memory matches.")
            return 0
        for result in results:
            location = f"{result.get('scope')}.{result.get('key')}"
            details = []
            if result.get("event_id") is not None:
                details.append(f"event=#{result.get('event_id')}")
            if result.get("event_type"):
                details.append(str(result.get("event_type")))
            if result.get("at"):
                details.append(str(result.get("at")))
            suffix = f" ({', '.join(details)})" if details else ""
            print(f"- {location}{suffix}: {result.get('text')}")
        return 0

    memory = state.get("memory", {})
    shallow = memory.get("shallow", {})
    deep = memory.get("deep", {})
    print(f"current_context: {shallow.get('current_context') or ''}")
    print(f"latest_task_summary: {shallow.get('latest_task_summary') or ''}")
    if args.recent:
        print("recent_events:")
        for event in shallow.get("recent_events", [])[-args.recent :]:
            print(f"- {event.get('at')} {event.get('event_type')}#{event.get('event_id')}: {event.get('summary')}")
    if args.deep:
        print("preferences:")
        for item in deep.get("preferences", []):
            print(f"- {item}")
        print("project:")
        for item in deep.get("project", []):
            print(f"- {item}")
        print(format_project_snapshot(deep.get("project_snapshot")))
        print("decisions:")
        for item in deep.get("decisions", []):
            print(f"- {item}")
    return 0

def cmd_snapshot(args):
    allowed = args.allow_read or []
    if not allowed:
        print("mew: snapshot requires --allow-read PATH", file=sys.stderr)
        return 1
    with state_lock():
        state = load_state()
        try:
            report = refresh_project_snapshot(
                state,
                args.path,
                allowed,
                now_iso(),
                read_files=not args.no_read_files,
                inspect_key_dirs=not args.no_inspect_key_dirs,
            )
        except ValueError as exc:
            print(f"mew: {exc}", file=sys.stderr)
            return 1
        save_state(state)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    print(format_snapshot_refresh_report(report))
    return 0

def latest_implementation_run_for_task(state, task_id):
    for run in reversed(state.get("agent_runs", [])):
        if run.get("purpose", "implementation") != "implementation":
            continue
        if str(run.get("task_id")) == str(task_id):
            return run
    return None

def latest_implementation_run_for_plan(state, task_id, plan_id, statuses=None):
    wanted_statuses = set(statuses or [])
    for run in reversed(state.get("agent_runs", [])):
        if run.get("purpose", "implementation") != "implementation":
            continue
        if str(run.get("task_id")) != str(task_id):
            continue
        if str(run.get("plan_id")) != str(plan_id):
            continue
        if wanted_statuses and run.get("status") not in wanted_statuses:
            continue
        return run
    return None

def select_buddy_task(state, task_id=None):
    if task_id:
        return find_task(state, task_id)
    for task in sorted(open_tasks(state), key=task_sort_key):
        if is_programmer_task(task):
            return task
    return None

def summarize_buddy_step(action, detail, **extra):
    step = {"action": action, "detail": detail}
    step.update(extra)
    return step

def format_buddy_report(report):
    lines = [f"buddy task #{report['task']['id']}: {report['task']['title']}"]
    for step in report["steps"]:
        lines.append(f"- {step['detail']}")
        if step.get("command"):
            lines.append(f"  command: {shlex.join(step['command'])}")
    if report.get("next"):
        lines.append(f"next: {report['next']}")
    return "\n".join(lines)

def cmd_buddy(args):
    with state_lock():
        state = load_state()
        task = select_buddy_task(state, getattr(args, "task_id", None))
        if not task:
            print("mew: no coding task available for buddy", file=sys.stderr)
            return 1
        if not is_programmer_task(task):
            print(
                f"mew: task #{task['id']} kind={task_kind(task)} is not a coding task; update --kind coding first",
                file=sys.stderr,
            )
            return 1

        steps = []
        dirty = False
        plan = latest_task_plan(task)
        if plan and not args.force_plan:
            steps.append(summarize_buddy_step("plan", f"reused {format_task_plan(plan)}", plan_id=plan["id"]))
        else:
            plan = create_task_plan(
                state,
                task,
                cwd=args.cwd,
                model=args.agent_model,
                review_model=args.review_model,
                objective=args.objective,
                approach=args.approach,
            )
            dirty = True
            steps.append(summarize_buddy_step("plan", f"created {format_task_plan(plan)}", plan_id=plan["id"]))

        run = None
        if args.dispatch:
            active = (
                latest_implementation_run_for_plan(state, task["id"], plan["id"], statuses=("dry_run",))
                if args.dry_run
                else find_active_implementation_run_for_plan(state, task["id"], plan["id"])
            )
            if active and not args.force_dispatch:
                run = active
                extra = {"run_id": run["id"]}
                if run.get("command"):
                    extra["command"] = run["command"]
                steps.append(
                    summarize_buddy_step(
                        "dispatch",
                        f"reused implementation run #{run['id']} status={run.get('status')}",
                        **extra,
                    )
                )
            else:
                if args.cwd:
                    plan["cwd"] = args.cwd
                if args.agent_model:
                    plan["model"] = args.agent_model
                run = create_implementation_run_from_plan(state, task, plan, dry_run=args.dry_run)
                dirty = True
                if args.dry_run:
                    ensure_agent_run_prompt_file(run)
                    run["command"] = build_ai_cli_run_command(run)
                    steps.append(
                        summarize_buddy_step(
                            "dispatch",
                            f"created dry-run implementation run #{run['id']} from plan #{plan['id']}",
                            run_id=run["id"],
                            command=run["command"],
                        )
                    )
                else:
                    try:
                        start_agent_run(state, run)
                    except ValueError as exc:
                        save_state(state)
                        print(f"mew: {exc}", file=sys.stderr)
                        return 1
                    if run.get("status") != "running":
                        save_state(state)
                        detail = run.get("stderr") or run.get("stdout") or run.get("result") or "unknown error"
                        print(f"mew: implementation run #{run['id']} failed to start: {detail}", file=sys.stderr)
                        return 1
                    steps.append(
                        summarize_buddy_step(
                            "dispatch",
                            f"started implementation run #{run['id']} status={run.get('status')} pid={run.get('external_pid')}",
                            run_id=run["id"],
                        )
                    )

        review_run = None
        review_requires_force = False
        if args.review:
            implementation_run = run or latest_implementation_run_for_task(state, task["id"])
            if not implementation_run:
                if dirty:
                    save_state(state)
                print(f"mew: no implementation run found for task #{task['id']}", file=sys.stderr)
                return 1
            if implementation_run.get("status") not in ("completed", "failed") and not args.force_review:
                if dirty:
                    save_state(state)
                print(
                    f"mew: implementation run #{implementation_run['id']} status={implementation_run.get('status')}; use --force-review",
                    file=sys.stderr,
                )
                return 1
            review_requires_force = implementation_run.get("status") not in ("completed", "failed")
            review_plan = (
                find_task_plan(task, implementation_run.get("plan_id"))
                if implementation_run.get("plan_id")
                else plan
            )
            review_run = create_review_run_for_implementation(
                state,
                task,
                implementation_run,
                plan=review_plan,
                model=args.review_model,
            )
            dirty = True
            if args.dry_run:
                review_run["status"] = "dry_run"
                ensure_agent_run_prompt_file(review_run)
                review_run["command"] = build_ai_cli_run_command(review_run)
                steps.append(
                    summarize_buddy_step(
                        "review",
                        f"created dry-run review run #{review_run['id']} for implementation run #{implementation_run['id']}",
                        run_id=review_run["id"],
                        command=review_run["command"],
                    )
                )
            else:
                try:
                    start_agent_run(state, review_run)
                except ValueError as exc:
                    save_state(state)
                    print(f"mew: {exc}", file=sys.stderr)
                    return 1
                if review_run.get("status") != "running":
                    save_state(state)
                    detail = review_run.get("stderr") or review_run.get("stdout") or review_run.get("result") or "unknown error"
                    print(f"mew: review run #{review_run['id']} failed to start: {detail}", file=sys.stderr)
                    return 1
                steps.append(
                    summarize_buddy_step(
                        "review",
                        f"started review run #{review_run['id']} status={review_run.get('status')} pid={review_run.get('external_pid')}",
                        run_id=review_run["id"],
                    )
                )

        save_state(state)

    next_text = f"inspect with `mew task show {task['id']}`"
    if review_run and review_run.get("status") == "dry_run":
        force = " --force-review" if review_requires_force else ""
        next_text = f"start review for real with `mew buddy --task {task['id']} --review{force}`"
    elif review_run and review_run.get("status") == "running":
        next_text = f"wait for review with `mew agent wait {review_run['id']}`"
    elif plan and not args.dispatch and not args.review:
        next_text = f"dispatch with `mew buddy --task {task['id']} --dispatch --dry-run`"
    elif run and run.get("status") == "dry_run":
        next_text = f"start for real with `mew buddy --task {task['id']} --dispatch`"
    elif run and run.get("status") == "running":
        next_text = f"wait with `mew agent wait {run['id']}`"
    elif run and run.get("status") in ("completed", "failed") and not review_run:
        next_text = f"review with `mew buddy --task {task['id']} --review --dry-run`"

    report = {
        "task": {"id": task["id"], "title": task.get("title"), "kind": task_kind(task), "status": task.get("status")},
        "plan_id": plan.get("id") if plan else None,
        "run_id": run.get("id") if run else None,
        "review_run_id": review_run.get("id") if review_run else None,
        "steps": steps,
        "next": next_text,
    }
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(format_buddy_report(report))
    return 0

def cmd_task_run(args):
    with state_lock():
        state = load_state()
        task = find_task(state, args.task_id)
        if not task:
            print(f"mew: task not found: {args.task_id}", file=sys.stderr)
            return 1
        if not is_programmer_task(task):
            print(
                f"mew: task #{task['id']} kind={task_kind(task)} is not a coding task; update --kind coding first",
                file=sys.stderr,
            )
            return 1
        backend = args.agent_backend or task.get("agent_backend") or "ai-cli"
        model = args.agent_model or task.get("agent_model") or "codex-ultra"
        prompt = args.agent_prompt or task.get("agent_prompt") or None
        run = create_agent_run(state, task, backend=backend, model=model, cwd=args.cwd, prompt=prompt)
        if args.dry_run:
            run["status"] = "dry_run"
            ensure_agent_run_prompt_file(run)
            run["command"] = build_ai_cli_run_command(run)
            save_state(state)
            print(f"created dry-run agent run #{run['id']}")
            print(" ".join(run["command"]))
            return 0
        try:
            start_agent_run(state, run)
        except ValueError as exc:
            print(f"mew: {exc}", file=sys.stderr)
            return 1
        save_state(state)
        if run.get("status") != "running":
            detail = run.get("stderr") or run.get("stdout") or run.get("result") or "unknown error"
            print(f"mew: agent run #{run['id']} failed to start: {detail}", file=sys.stderr)
            return 1
    print(f"started agent run #{run['id']} task=#{run['task_id']} backend={run['backend']} model={run['model']} pid={run.get('external_pid')}")
    return 0

def cmd_task_plan(args):
    with state_lock():
        state = load_state()
        task = find_task(state, args.task_id)
        if not task:
            print(f"mew: task not found: {args.task_id}", file=sys.stderr)
            return 1
        if not is_programmer_task(task):
            print(
                f"mew: task #{task['id']} kind={task_kind(task)} is not a coding task; update --kind coding first",
                file=sys.stderr,
            )
            return 1
        if latest_task_plan(task) and not args.force:
            plan = latest_task_plan(task)
        else:
            plan = create_task_plan(
                state,
                task,
                cwd=args.cwd,
                model=args.agent_model,
                review_model=args.review_model,
                objective=args.objective,
                approach=args.approach,
            )
            save_state(state)
    print(format_task_plan(plan))
    if args.prompt:
        print("implementation_prompt:")
        print(plan.get("implementation_prompt") or "")
        print("review_prompt:")
        print(plan.get("review_prompt") or "")
    return 0

def cmd_task_dispatch(args):
    with state_lock():
        state = load_state()
        task = find_task(state, args.task_id)
        if not task:
            print(f"mew: task not found: {args.task_id}", file=sys.stderr)
            return 1
        if not is_programmer_task(task):
            print(
                f"mew: task #{task['id']} kind={task_kind(task)} is not a coding task; update --kind coding first",
                file=sys.stderr,
            )
            return 1
        plan = find_task_plan(task, args.plan_id) if args.plan_id else latest_task_plan(task)
        if not plan:
            plan = create_task_plan(state, task, cwd=args.cwd, model=args.agent_model)
        if args.cwd:
            plan["cwd"] = args.cwd
        if args.agent_model:
            plan["model"] = args.agent_model
        run = create_implementation_run_from_plan(state, task, plan, dry_run=args.dry_run)
        if args.dry_run:
            ensure_agent_run_prompt_file(run)
            run["command"] = build_ai_cli_run_command(run)
            save_state(state)
            print(f"created dry-run implementation run #{run['id']} from plan #{plan['id']}")
            print(" ".join(run["command"]))
            return 0
        start_agent_run(state, run)
        save_state(state)
        if run.get("status") != "running":
            detail = run.get("stderr") or run.get("stdout") or run.get("result") or "unknown error"
            print(f"mew: implementation run #{run['id']} failed to start: {detail}", file=sys.stderr)
            return 1
    print(f"started implementation run #{run['id']} task=#{task['id']} plan=#{plan['id']} pid={run.get('external_pid')}")
    return 0

def cmd_agent_list(args):
    state = load_state()
    runs = state["agent_runs"]
    if not getattr(args, "all", False):
        runs = [run for run in runs if run.get("status") in ("created", "running")]
    if not runs:
        print("No agent runs.")
        return 0
    for run in runs:
        pid = run.get("external_pid") or ""
        purpose = run.get("purpose") or "implementation"
        print(f"#{run['id']} [{run['status']}/{purpose}] task=#{run.get('task_id')} {run.get('backend')}:{run.get('model')} pid={pid}")
    return 0

def cmd_agent_show(args):
    state = load_state()
    run = find_agent_run(state, args.run_id)
    if not run:
        print(f"mew: agent run not found: {args.run_id}", file=sys.stderr)
        return 1
    for key in (
        "id",
        "task_id",
        "purpose",
        "plan_id",
        "parent_run_id",
        "review_of_run_id",
        "review_status",
        "followup_task_id",
        "followup_processed_at",
        "backend",
        "model",
        "cwd",
        "prompt_file",
        "status",
        "external_pid",
        "resume_session_id",
        "session_id",
        "review_report",
        "supervisor_verification",
        "created_at",
        "started_at",
        "finished_at",
        "updated_at",
    ):
        print(f"{key}: {run.get(key)}")
    if args.prompt:
        print("prompt:")
        print(run.get("prompt") or "")
    if run.get("result"):
        print("result:")
        print(run["result"])
    elif run.get("stdout"):
        print("stdout:")
        print(run["stdout"])
    if run.get("stderr"):
        print("stderr:")
        print(run["stderr"])
    return 0

def cmd_agent_wait(args):
    with state_lock():
        state = load_state()
        run = find_agent_run(state, args.run_id)
        if not run:
            print(f"mew: agent run not found: {args.run_id}", file=sys.stderr)
            return 1
        try:
            wait_agent_run(state, run, timeout=args.timeout)
        except ValueError as exc:
            print(f"mew: {exc}", file=sys.stderr)
            return 1
        save_state(state)
    print(f"agent run #{run['id']} status={run['status']}")
    if run.get("result"):
        print(run["result"])
    return 0

def cmd_agent_result(args):
    with state_lock():
        state = load_state()
        run = find_agent_run(state, args.run_id)
        if not run:
            print(f"mew: agent run not found: {args.run_id}", file=sys.stderr)
            return 1
        try:
            get_agent_run_result(state, run, verbose=args.verbose)
        except ValueError as exc:
            print(f"mew: {exc}", file=sys.stderr)
            return 1
        save_state(state)
    print(f"agent run #{run['id']} status={run['status']}")
    if run.get("result"):
        print(run["result"])
    elif run.get("stdout"):
        print(run["stdout"])
    return 0

def cmd_agent_review(args):
    with state_lock():
        state = load_state()
        implementation_run = find_agent_run(state, args.run_id)
        if not implementation_run:
            print(f"mew: agent run not found: {args.run_id}", file=sys.stderr)
            return 1
        if implementation_run.get("purpose") == "review":
            print(f"mew: run #{args.run_id} is already a review run", file=sys.stderr)
            return 1
        if implementation_run.get("status") not in ("completed", "failed") and not args.force:
            print(
                f"mew: run #{args.run_id} status={implementation_run.get('status')}; use --force to review anyway",
                file=sys.stderr,
            )
            return 1
        task = find_task(state, implementation_run.get("task_id"))
        if not task:
            print(f"mew: task not found for run #{args.run_id}", file=sys.stderr)
            return 1
        plan = find_task_plan(task, implementation_run.get("plan_id")) if implementation_run.get("plan_id") else None
        review_run = create_review_run_for_implementation(
            state,
            task,
            implementation_run,
            plan=plan,
            model=args.agent_model,
        )
        if args.dry_run:
            review_run["status"] = "dry_run"
            ensure_agent_run_prompt_file(review_run)
            review_run["command"] = build_ai_cli_run_command(review_run)
            save_state(state)
            print(f"created dry-run review run #{review_run['id']} for run #{implementation_run['id']}")
            print(" ".join(review_run["command"]))
            return 0
        start_agent_run(state, review_run)
        save_state(state)
        if review_run.get("status") != "running":
            detail = review_run.get("stderr") or review_run.get("stdout") or review_run.get("result") or "unknown error"
            print(f"mew: review run #{review_run['id']} failed to start: {detail}", file=sys.stderr)
            return 1
    print(f"started review run #{review_run['id']} for run #{implementation_run['id']} pid={review_run.get('external_pid')}")
    return 0

def cmd_agent_followup(args):
    with state_lock():
        state = load_state()
        review_run = find_agent_run(state, args.run_id)
        if not review_run:
            print(f"mew: agent run not found: {args.run_id}", file=sys.stderr)
            return 1
        if review_run.get("purpose") != "review":
            print(f"mew: run #{args.run_id} is not a review run", file=sys.stderr)
            return 1
        if not review_run.get("result") and not review_run.get("stdout"):
            try:
                get_agent_run_result(state, review_run, verbose=False)
            except ValueError as exc:
                print(f"mew: {exc}", file=sys.stderr)
                return 1
        task = find_task(state, review_run.get("task_id"))
        if not task:
            print(f"mew: task not found for review run #{args.run_id}", file=sys.stderr)
            return 1
        if args.ack:
            status = acknowledge_review_followup(state, task, review_run, note=args.note or "")
            followup = None
        else:
            followup, status = create_follow_up_task_from_review(state, task, review_run)
        save_state(state)
    print(f"review run #{review_run['id']} status={status}")
    if args.ack:
        print("follow-up acknowledged without creating a task")
        return 0
    if followup:
        print(format_task(followup))
    else:
        print("no follow-up task created")
    return 0

def cmd_agent_retry(args):
    with state_lock():
        state = load_state()
        failed_run = find_agent_run(state, args.run_id)
        if not failed_run:
            print(f"mew: agent run not found: {args.run_id}", file=sys.stderr)
            return 1
        if failed_run.get("purpose", "implementation") != "implementation":
            print(f"mew: run #{args.run_id} is not an implementation run", file=sys.stderr)
            return 1
        if failed_run.get("status") not in ("failed", "completed") and not args.force:
            print(
                f"mew: run #{args.run_id} status={failed_run.get('status')}; use --force to retry anyway",
                file=sys.stderr,
            )
            return 1
        task = find_task(state, failed_run.get("task_id"))
        if not task:
            print(f"mew: task not found for run #{args.run_id}", file=sys.stderr)
            return 1
        plan = find_task_plan(task, failed_run.get("plan_id")) if failed_run.get("plan_id") else latest_task_plan(task)
        retry_run = create_retry_run_for_implementation(
            state,
            task,
            failed_run,
            plan=plan,
            model=args.agent_model,
            dry_run=args.dry_run,
        )
        if args.dry_run:
            ensure_agent_run_prompt_file(retry_run)
            retry_run["command"] = build_ai_cli_run_command(retry_run)
            save_state(state)
            print(f"created dry-run retry run #{retry_run['id']} for run #{failed_run['id']}")
            print(" ".join(retry_run["command"]))
            return 0
        start_agent_run(state, retry_run)
        save_state(state)
        if retry_run.get("status") != "running":
            detail = retry_run.get("stderr") or retry_run.get("stdout") or retry_run.get("result") or "unknown error"
            print(f"mew: retry run #{retry_run['id']} failed to start: {detail}", file=sys.stderr)
            return 1
    print(f"started retry run #{retry_run['id']} for run #{failed_run['id']} pid={retry_run.get('external_pid')}")
    return 0

def cmd_agent_sweep(args):
    with state_lock():
        state = load_state()
        report = sweep_agent_runs(
            state,
            collect=not args.no_collect,
            start_reviews=args.start_reviews,
            followup=not args.no_followup,
            stale_minutes=args.stale_minutes,
            dry_run=args.dry_run,
            review_model=args.agent_model,
            result_timeout=args.agent_result_timeout,
            start_timeout=args.agent_start_timeout,
        )
        if not args.dry_run:
            save_state(state)
    print(format_sweep_report(report))
    return 1 if report.get("errors") else 0

def runtime_is_active():
    lock = read_lock()
    return bool(lock and pid_alive(lock.get("pid")))

def format_outbox_line(message):
    created_at = message.get("created_at") or "unknown-time"
    message_id = message.get("id")
    message_type = message.get("type") or "message"
    text = str(message.get("text") or "")
    prefix = f"[{created_at}] #{message_id} {message_type}: "
    return prefix + text.replace("\n", "\n" + " " * len(prefix))

def print_outbox_messages(messages):
    for message in messages:
        print(format_outbox_line(message), flush=True)

def current_log_offset():
    if not LOG_FILE.exists():
        return 0
    return LOG_FILE.stat().st_size

def emit_new_activity(offset):
    if not LOG_FILE.exists():
        return 0

    size = LOG_FILE.stat().st_size
    if size < offset:
        offset = 0

    with LOG_FILE.open("rb") as handle:
        handle.seek(offset)
        data = handle.read()
        new_offset = handle.tell()

    text = data.decode("utf-8", errors="replace")
    for line in text.splitlines():
        if line.strip():
            print(f"runtime: {line}", flush=True)
    return new_offset

def mark_outbox_read(message_ids):
    if not message_ids:
        return
    ids = {str(message_id) for message_id in message_ids}
    current_time = now_iso()
    with state_lock():
        state = load_state()
        changed = False
        for message_id in ids:
            if mark_message_read(state, message_id):
                changed = True
        if changed:
            save_state(state)

def find_event_by_id(state, event_id):
    wanted = str(event_id)
    for event in state.get("inbox", []):
        if str(event.get("id")) == wanted:
            return event
    return None

def outbox_for_event(state, event_id):
    wanted = str(event_id)
    return [
        message
        for message in state.get("outbox", [])
        if str(message.get("event_id")) == wanted
    ]

def wait_for_event_response(event_id, timeout=60.0, poll_interval=1.0, mark_read=False, event_label="message event"):
    deadline = time.monotonic() + max(0.0, timeout)
    seen_ids = set()

    while True:
        state = load_state()
        messages = outbox_for_event(state, event_id)
        new_messages = [
            message
            for message in messages
            if str(message.get("id")) not in seen_ids
            and not message.get("read_at")
        ]
        seen_ids.update(str(message.get("id")) for message in messages)
        if new_messages:
            print_outbox_messages(new_messages)
            if mark_read:
                mark_outbox_read(message.get("id") for message in new_messages)
            return 0

        event = find_event_by_id(state, event_id)
        if event and event.get("processed_at"):
            print(f"{event_label} #{event_id} was processed without an outbox response.")
            return 0

        if time.monotonic() >= deadline:
            print(f"mew: timed out waiting for {event_label} #{event_id}", file=sys.stderr)
            return 1

        time.sleep(max(0.01, poll_interval))

def emit_initial_outbox(history, unread, mark_read):
    state = load_state()
    seen_ids = {str(message.get("id")) for message in state["outbox"]}
    if history:
        messages = list(state["outbox"])
    elif unread:
        messages = [message for message in state["outbox"] if not message.get("read_at")]
    else:
        messages = []
    print_outbox_messages(messages)
    if mark_read:
        mark_outbox_read(message.get("id") for message in messages)
    return seen_ids

def emit_new_outbox(seen_ids, mark_read):
    state = load_state()
    messages = []
    for message in state["outbox"]:
        message_id = str(message.get("id"))
        if message_id in seen_ids:
            continue
        seen_ids.add(message_id)
        if message.get("read_at"):
            continue
        messages.append(message)
    print_outbox_messages(messages)
    if mark_read:
        mark_outbox_read(message.get("id") for message in messages)
    return len(messages)

def stream_outbox_and_input(args, allow_input):
    seen_ids = emit_initial_outbox(args.history, args.unread, args.mark_read)
    activity_offset = current_log_offset() if args.activity else None
    deadline = None
    if args.timeout is not None:
        deadline = time.monotonic() + max(0.0, args.timeout)

    while True:
        emit_new_outbox(seen_ids, args.mark_read)
        if args.activity:
            activity_offset = emit_new_activity(activity_offset)
        if deadline is not None and time.monotonic() >= deadline:
            return 0

        wait_for = args.poll_interval
        if deadline is not None:
            wait_for = min(wait_for, max(0.0, deadline - time.monotonic()))

        if allow_input:
            readable, _, _ = select.select([sys.stdin], [], [], wait_for)
            if readable:
                line = sys.stdin.readline()
                if line == "":
                    allow_input = False
                    continue
                text = line.rstrip("\n")
                if text in ("/quit", "/exit"):
                    return 0
                if text.strip():
                    event = queue_user_message(text)
                    print(f"queued message event #{event['id']}", flush=True)
        else:
            time.sleep(wait_for)

def warn_if_runtime_inactive():
    if not runtime_is_active():
        print(
            "mew: no active runtime found; messages can be queued, but nothing will process them until `mew run` is running.",
            file=sys.stderr,
        )
        print(
            "mew: next: run `mew run --once` for one deterministic local pass, "
            "`mew step --ai --auth auth.json --max-steps 1` for one AI pass, "
            "or `mew run --ai --auth auth.json` for passive AI processing.",
            file=sys.stderr,
        )

def cmd_attach(args):
    warn_if_runtime_inactive()
    for text in args.attach_messages or []:
        event = queue_user_message(text)
        print(f"queued message event #{event['id']}", flush=True)

    allow_input = not args.no_input and sys.stdin.isatty()
    if allow_input:
        print("attached. Type a message and press Enter. Use /exit or Ctrl-C to detach.", flush=True)
    else:
        detail = "outbox messages and runtime activity" if args.activity else "outbox messages"
        print(f"attached. Listening for {detail}.", flush=True)

    try:
        return stream_outbox_and_input(args, allow_input)
    except KeyboardInterrupt:
        print("\ndetached")
        return 0

def cmd_listen(args):
    warn_if_runtime_inactive()
    try:
        return stream_outbox_and_input(args, allow_input=False)
    except KeyboardInterrupt:
        print("\nstopped listening")
        return 0

CHAT_HELP = """Commands:
/help [work]          show this help, or focused work-session help
/focus                show the quiet next-action view
/daily                alias for /focus
/brief                show the current operational brief
/next                 show the next useful move
/doctor              show state/runtime health
/repair [--force]    reconcile state if the runtime is stopped
/status               show compact runtime status
/perception           show passive workspace observations
/add <title> [| desc] create a task from chat
/tasks [all]          list open tasks, or all tasks
/show <task-id>       show task details
/work [task-id]       show task plan/runs/checks and next action
/work-session [cmd]   show/start/close/stop/note/recover/ai/live/resume/approve/reject native work session; add details
/continue [opts|text] run one live step; plain text becomes work guidance
/note <task-id> <txt> append a task note
/kind <task-id> <kind> set task kind: coding|research|personal|admin|unknown
/classify [id]        inspect task kind inference; add apply|clear|mismatches
/questions [all]      list open questions, or all questions
/defer <id> [reason]  defer a question so /next can move on
/reopen <id>          reopen a deferred question
/attention [all]      list open attention items, or all attention items
/resolve all|<ids>    resolve attention items
/outbox [all]         list unread outbox messages, or all messages
/agents [all]         list running agent runs, or all agent runs
/result <run-id>      collect an agent run result
/wait <run-id> [sec]  wait for an agent run result
/review <run-id>      start a review run; add dry-run to preview
/followup <run-id>    process a completed review run
/retry <run-id>       retry an implementation run; add dry-run to preview
/sweep [dry-run]      collect stale programmer-loop work
/verification         show recent verification runs
/verify <command>     run and record a verification command
/writes               show recent runtime write/edit runs
/runtime-effects [n]  show recent runtime effect journal entries
/why                  explain the latest processed think/act decision
/thoughts            show recent thought journal entries
/digest               summarize activity since the last user message
/approve <task-id>    mark a task ready and auto_execute=true
/ready <task-id>      mark a task ready without changing auto_execute
/done <task-id>       mark a task done
/block <task-id>      mark a task blocked
/plan <task-id>       create or show a programmer plan; add prompt to print prompts
/dispatch <task-id>   start an implementation run; add dry-run to preview
/buddy [task-id]      plan one coding task; add dispatch, dry-run, review
/self [focus]         create/plan self-improvement; add dispatch or dry-run
/pause [reason]       pause autonomous non-user work
/resume               resume autonomous non-user work
/mode <level>         override autonomy level: observe|propose|act|default
/ack all|routine|<ids...> mark outbox messages as read
/reply <id> <text>    answer an open question
/activity on|off      toggle runtime activity lines
/history              print all outbox messages
/exit                 leave chat
Any non-slash line is sent to mew as a user message."""

CHAT_WORK_HELP = """Work session quick help:
/work-session                         show active session, or recent sessions if none is active
/work-session details                 show active session with decisions, diffs, failures, and tool calls
/work-session resume [task-id]        show a compact reentry bundle
/work-session <task-id> resume        same as resume; task-first order is accepted
/work-session resume --allow-read .   add live git/file world state to the reentry bundle
/work-session start <task-id>         start or reuse a native work session
/continue --allow-read .              run one live resident-model step
/continue <guidance>                  reuse prior live options with new guidance
/work-session stop <reason>           pause the live loop at the next boundary
/work-session note <text>             save a durable note for future work context
/work-session approve <id> ...        apply a dry-run write after explicit gates
/work-session reject <id> <reason>    reject a pending write"""

CHAT_EOF = object()


def print_chat_status():
    state = load_state()
    lock = read_lock()
    lock_state = "none"
    if lock:
        lock_state = "active" if pid_alive(lock.get("pid")) else "stale"
    unread = [message for message in state["outbox"] if not message.get("read_at")]
    running_agents = [run for run in state["agent_runs"] if run.get("status") in ("created", "running")]
    print(f"runtime: {state['runtime_status'].get('state')} lock={lock_state} pid={state['runtime_status'].get('pid')}")
    print(f"agent: {state['agent_status'].get('mode')} focus={state['agent_status'].get('current_focus') or '(none)'}")
    autonomy = state.get("autonomy", {})
    print(
        f"autonomy: enabled={autonomy.get('enabled')} level={autonomy.get('level')} "
        f"paused={autonomy.get('paused')} override={autonomy.get('level_override') or '(none)'}"
    )
    print(
        f"counts: tasks={len(open_tasks(state))} questions={len(open_questions(state))} "
        f"attention={len(open_attention_items(state))} unread={len(unread)} running_agents={len(running_agents)}"
    )
    print(f"next: {next_move(state)}")


def print_chat_perception():
    print(format_perception(perceive_workspace(allowed_read_roots=["."], cwd=".")))


def print_chat_tasks(show_all=False):
    state = load_state()
    tasks = state["tasks"] if show_all else open_tasks(state)
    tasks = sorted(tasks, key=task_sort_key)
    if not tasks:
        print("No tasks.")
        return
    for task in tasks:
        print(format_task(task))


def print_chat_task(task_id):
    state = load_state()
    task = find_task(state, task_id)
    if not task:
        print(f"mew: task not found: {task_id}")
        return
    print(format_task(task))
    print(f"description: {task.get('description') or ''}")
    print(f"kind: {task_kind(task)}")
    print(f"kind_override: {task.get('kind') or ''}")
    print(f"notes: {task.get('notes') or ''}")
    print(f"command: {task.get('command') or ''}")
    print(f"cwd: {task.get('cwd') or ''}")
    print(f"auto_execute: {task.get('auto_execute')}")
    print(f"agent_model: {task.get('agent_model') or ''}")
    print(f"agent_run_id: {task.get('agent_run_id') or ''}")
    print(f"latest_plan_id: {task.get('latest_plan_id') or ''}")


def print_chat_workbench(task_id):
    state = load_state()
    task = select_workbench_task(state, task_id)
    if not task:
        if task_id:
            print(f"mew: task not found: {task_id}")
        else:
            print("No tasks.")
        return
    print(format_workbench(build_workbench_data(state, task)))


def _chat_option_value(token, parts, index):
    if "=" in token:
        return token.partition("=")[2], index + 1
    if index + 1 >= len(parts):
        return None, index + 1
    return parts[index + 1], index + 2


def _parse_chat_work_ai_args(parts):
    value_options = {
        "--auth",
        "--model-backend",
        "--model",
        "--base-url",
        "--model-timeout",
        "--max-steps",
        "--act-mode",
        "--work-guidance",
        "--allow-read",
        "--allow-write",
        "--verify-command",
        "--verify-timeout",
    }
    value_option_prefixes = tuple(f"{option}=" for option in value_options)
    args = {
        "task_id": None,
        "auth": "auth.json",
        "model_backend": DEFAULT_MODEL_BACKEND,
        "model": None,
        "base_url": None,
        "model_timeout": 60.0,
        "max_steps": 1,
        "act_mode": "model",
        "work_guidance": "",
        "progress": False,
        "live": False,
        "stream_model": False,
        "allow_read": [],
        "allow_write": [],
        "allow_shell": False,
        "allow_verify": False,
        "verify_command": "",
        "verify_timeout": 300.0,
        "json": False,
    }
    index = 1
    if index < len(parts) and not parts[index].startswith("--"):
        args["task_id"] = parts[index]
        index += 1
    while index < len(parts):
        token = parts[index]
        if token in value_options or token.startswith(value_option_prefixes):
            value, next_index = _chat_option_value(token, parts, index)
            if value is None:
                return None, f"mew: missing value for {token}"
            name = token.split("=", 1)[0]
            if name == "--auth":
                args["auth"] = value
            elif name == "--model-backend":
                args["model_backend"] = value
            elif name == "--model":
                args["model"] = value
            elif name == "--base-url":
                args["base_url"] = value
            elif name == "--model-timeout":
                try:
                    args["model_timeout"] = float(value)
                except ValueError:
                    return None, f"mew: invalid --model-timeout: {value}"
            elif name == "--max-steps":
                try:
                    args["max_steps"] = int(value)
                except ValueError:
                    return None, f"mew: invalid --max-steps: {value}"
            elif name == "--act-mode":
                if value not in ("model", "deterministic"):
                    return None, f"mew: invalid --act-mode: {value}"
                args["act_mode"] = value
            elif name == "--work-guidance":
                args["work_guidance"] = value
            elif name == "--allow-read":
                args["allow_read"].append(value)
            elif name == "--allow-write":
                args["allow_write"].append(value)
            elif name == "--verify-command":
                args["verify_command"] = value
            elif name == "--verify-timeout":
                try:
                    args["verify_timeout"] = float(value)
                except ValueError:
                    return None, f"mew: invalid --verify-timeout: {value}"
            index = next_index
            continue
        if token == "--allow-shell":
            args["allow_shell"] = True
            index += 1
            continue
        if token == "--allow-verify":
            args["allow_verify"] = True
            index += 1
            continue
        if token == "--progress":
            args["progress"] = True
            index += 1
            continue
        if token == "--live":
            args["live"] = True
            index += 1
            continue
        if token == "--stream-model":
            args["stream_model"] = True
            index += 1
            continue
        return None, f"mew: unsupported ai option: {token}"
    return SimpleNamespace(**args), ""


def _strip_work_guidance_options(rest):
    try:
        parts = shlex.split(rest or "")
    except ValueError:
        return (rest or "").strip()
    kept = []
    index = 0
    while index < len(parts):
        token = parts[index]
        if token == "--work-guidance":
            index += 2
            continue
        if token.startswith("--work-guidance="):
            index += 1
            continue
        kept.append(token)
        index += 1
    return shlex.join(kept)


def _looks_like_work_continue_options(rest):
    try:
        parts = shlex.split(rest or "")
    except ValueError:
        return False
    if not parts:
        return False
    first = parts[0]
    if first.startswith("-"):
        return True
    return first.lstrip("#").isdigit()


def _chat_continue_rest(rest, chat_state):
    rest = (rest or "").strip()
    cached = (chat_state or {}).get("work_continue_options", "").strip()
    if not rest:
        return cached
    if _looks_like_work_continue_options(rest):
        if chat_state is not None:
            chat_state["work_continue_options"] = _strip_work_guidance_options(rest)
        return rest
    guidance = "--work-guidance " + shlex.quote(rest)
    return " ".join(part for part in (cached, guidance) if part)


def _remember_work_continue_options(parts, chat_state):
    if chat_state is None:
        return
    options = _strip_work_guidance_options(shlex.join(parts[1:]))
    if options:
        chat_state["work_continue_options"] = options


def _parse_chat_work_resume_args(parts):
    task_id = None
    allow_read = []
    index = 1
    while index < len(parts):
        token = parts[index]
        if token in ("--task", "--task-id") and index + 1 < len(parts):
            task_id = parts[index + 1]
            index += 2
            continue
        if token == "--allow-read" and index + 1 < len(parts):
            allow_read.append(parts[index + 1])
            index += 2
            continue
        if token.startswith("--allow-read="):
            allow_read.append(token.partition("=")[2])
            index += 1
            continue
        if token.lstrip("#").isdigit() and task_id is None:
            task_id = token.lstrip("#")
            index += 1
            continue
        return None, None, f"mew: unsupported resume option: {token}"
    return task_id, allow_read, ""


def format_work_cockpit_controls(state=None, session=None, continue_options=""):
    state = state or load_state()
    if session is None:
        session = active_work_session(state)
    lines = ["", "Next controls"]
    if not session:
        lines.append("- /work-session start <task-id>")
        return "\n".join(lines)
    task_id = session.get("task_id")
    task_suffix = f" {task_id}" if task_id else ""
    if session.get("status") != "active":
        lines.append(f"- /work-session resume{task_suffix}")
        lines.append(f"- /work-session start{task_suffix or ' <task-id>'}")
        return "\n".join(lines)

    resume = build_work_session_resume(session, task=work_session_task(state, session))
    for approval in (resume or {}).get("pending_approvals") or []:
        if approval.get("approve_hint"):
            lines.append(f"- {approval.get('approve_hint')}")
        if approval.get("reject_hint"):
            lines.append(f"- {approval.get('reject_hint')}")

    cached = (continue_options or "").strip() or work_chat_continue_options(session)
    if cached:
        lines.append("- /continue")
        lines.append("- /continue <guidance>")
        lines.append(f"- /work-session live {cached}")
    else:
        lines.append("- /continue --allow-read .")
        lines.append('- /continue --allow-read . --work-guidance "focus ..."')
    lines.append("- /work-session resume")
    lines.append("- /work-session resume --allow-read .")
    lines.append("- /work-session details")
    lines.append("- /work-session note <remember this>")
    lines.append("- /work-session recover --allow-read .")
    lines.append("- /work-session stop <reason>")
    lines.append("- /work-session close")
    return "\n".join(lines)


def chat_work_session(rest, chat_state=None):
    try:
        parts = shlex.split(rest)
    except ValueError as exc:
        print(f"mew: {exc}")
        return
    details = "details" in {part.casefold() for part in parts}
    parts = [part for part in parts if part.casefold() != "details"]
    task_first_actions = {"show", "start", "close", "stop", "note", "recover", "ai", "step", "live", "resume"}
    if len(parts) >= 2 and parts[0].lstrip("#").isdigit() and parts[1].casefold() in task_first_actions:
        parts = [parts[1], parts[0], *parts[2:]]
    action = parts[0].casefold() if parts else "show"
    task_id = parts[1] if len(parts) > 1 else None
    if action not in (
        "show",
        "start",
        "close",
        "stop",
        "note",
        "recover",
        "ai",
        "step",
        "live",
        "resume",
        "approve",
        "reject",
    ):
        task_id = parts[0] if parts else None
        action = "show"

    if action == "start":
        with state_lock():
            state = load_state()
            task = select_workbench_task(state, task_id)
            if not task:
                print(f"mew: task not found: {task_id}" if task_id else "No tasks.")
                return
            session, created = create_work_session(state, task)
            save_state(state)
        print(("created " if created else "reused ") + f"work session #{session['id']} for task #{task['id']}")
        print(format_work_session(session, task=task))
        return

    if action == "close":
        with state_lock():
            state = load_state()
            session = active_work_session(state)
            if task_id:
                session = None
                for candidate in reversed(state.get("work_sessions", [])):
                    if str(candidate.get("task_id")) == str(task_id) and candidate.get("status") == "active":
                        session = candidate
                        break
            if not session:
                print("No active work session.")
                return
            close_work_session(session)
            save_state(state)
        print(f"closed work session #{session['id']}")
        return

    if action == "stop":
        args = SimpleNamespace(task_id=None, stop_reason=" ".join(parts[1:]), json=False)
        cmd_work_stop_session(args)
        print(format_work_cockpit_controls(continue_options=(chat_state or {}).get("work_continue_options", "")))
        return

    if action == "note":
        args = SimpleNamespace(task_id=None, session_note=" ".join(parts[1:]), json=False)
        cmd_work_session_note(args)
        print(format_work_cockpit_controls(continue_options=(chat_state or {}).get("work_continue_options", "")))
        return

    if action == "recover":
        recover_parts = ["recover", *parts[1:]]
        args, error = _parse_chat_work_ai_args(recover_parts)
        if error:
            print(error)
            return
        args.recover_session = True
        args.json = False
        cmd_work_recover_session(args)
        print(format_work_cockpit_controls(continue_options=(chat_state or {}).get("work_continue_options", "")))
        return

    if action in ("ai", "step", "live"):
        args, error = _parse_chat_work_ai_args(parts)
        if error:
            print(error)
            return
        live_session_id = None
        if action == "live":
            args.live = True
            args.suppress_cli_controls = True
            _remember_work_continue_options(parts, chat_state)
            state = load_state()
            session = _select_active_work_session_for_args(state, args)
            live_session_id = session.get("id") if session else None
        cmd_work_ai(args)
        if action == "live":
            state = load_state()
            session = find_work_session(state, live_session_id) if live_session_id else None
            if session is None and args.task_id:
                session = _latest_work_session_for_task(state, args.task_id)
            print(
                format_work_cockpit_controls(
                    state=state,
                    session=session,
                    continue_options=(chat_state or {}).get("work_continue_options", ""),
                )
            )
        return

    if action == "resume":
        task_id, allow_read, error = _parse_chat_work_resume_args(parts)
        if error:
            print(error)
            return
        state = load_state()
        session = active_work_session(state)
        if task_id:
            session = _latest_work_session_for_task(state, task_id)
        resume = build_work_session_resume(session, task=work_session_task(state, session))
        if resume and allow_read:
            resume["world_state"] = build_work_world_state(resume, allow_read)
        if not resume and not task_id:
            print(format_no_active_work_session(state))
            return
        print(format_work_session_resume(resume))
        if resume:
            print(format_work_cockpit_controls(state=state, session=session, continue_options=(chat_state or {}).get("work_continue_options", "")))
        return

    if action == "approve":
        if len(parts) < 2:
            print(
                'usage: /work-session approve <tool-call-id> [--task <task-id>] '
                '--allow-write <path> --verify-command "<command>"'
            )
            return
        try:
            tool_call_id = int(parts[1])
        except ValueError:
            print(f"mew: invalid tool call id: {parts[1]}")
            return
        approve_task_id = None
        allow_write = []
        verify_command = ""
        verify_cwd = "."
        verify_timeout = 300.0
        index = 2
        while index < len(parts):
            token = parts[index]
            if token in ("--task", "--task-id") and index + 1 < len(parts):
                approve_task_id = parts[index + 1]
                index += 2
                continue
            if token == "--allow-write" and index + 1 < len(parts):
                allow_write.append(parts[index + 1])
                index += 2
                continue
            if token.startswith("--allow-write="):
                allow_write.append(token.partition("=")[2])
                index += 1
                continue
            if token == "--allow-verify":
                index += 1
                continue
            if token == "--verify-command" and index + 1 < len(parts):
                verify_command = parts[index + 1]
                index += 2
                continue
            if token.startswith("--verify-command="):
                verify_command = token.partition("=")[2]
                index += 1
                continue
            if token == "--verify-cwd" and index + 1 < len(parts):
                verify_cwd = parts[index + 1]
                index += 2
                continue
            if token.startswith("--verify-cwd="):
                verify_cwd = token.partition("=")[2]
                index += 1
                continue
            if token == "--verify-timeout" and index + 1 < len(parts):
                try:
                    verify_timeout = float(parts[index + 1])
                except ValueError:
                    print(f"mew: invalid --verify-timeout: {parts[index + 1]}")
                    return
                index += 2
                continue
            if token.startswith("--verify-timeout="):
                value = token.partition("=")[2]
                try:
                    verify_timeout = float(value)
                except ValueError:
                    print(f"mew: invalid --verify-timeout: {value}")
                    return
                index += 1
                continue
            print(f"mew: unsupported approve option: {token}")
            return
        if not allow_write:
            print("mew: approve requires --allow-write")
            return
        args = SimpleNamespace(
            task_id=approve_task_id,
            approve_tool=tool_call_id,
            allow_write=allow_write,
            allow_verify=bool(verify_command),
            verify_command=verify_command,
            verify_cwd=verify_cwd,
            verify_timeout=verify_timeout,
            allow_read=[],
            json=False,
        )
        cmd_work_approve_tool(args)
        print(format_work_cockpit_controls(continue_options=(chat_state or {}).get("work_continue_options", "")))
        return

    if action == "reject":
        if len(parts) < 2:
            print("usage: /work-session reject <tool-call-id> [reason]")
            return
        try:
            tool_call_id = int(parts[1])
        except ValueError:
            print(f"mew: invalid tool call id: {parts[1]}")
            return
        reject_task_id = None
        reason_parts = []
        index = 2
        while index < len(parts):
            token = parts[index]
            if token in ("--task", "--task-id") and index + 1 < len(parts):
                reject_task_id = parts[index + 1]
                index += 2
                continue
            reason_parts.append(token)
            index += 1
        args = SimpleNamespace(
            task_id=reject_task_id,
            reject_tool=tool_call_id,
            reject_reason=" ".join(reason_parts),
            json=False,
        )
        cmd_work_reject_tool(args)
        print(format_work_cockpit_controls(continue_options=(chat_state or {}).get("work_continue_options", "")))
        return

    state = load_state()
    session = active_work_session(state)
    if task_id:
        session = _latest_work_session_for_task(state, task_id)
    elif not session:
        print(format_no_active_work_session(state))
        return
    print(format_work_session(session, task=work_session_task(state, session), details=details))
    print(format_work_cockpit_controls(state=state, session=session, continue_options=(chat_state or {}).get("work_continue_options", "")))


def chat_add_task(rest):
    title, separator, description = rest.partition("|")
    title = title.strip()
    description = description.strip() if separator else ""
    if not title:
        print("usage: /add <title> [| description]")
        return
    current_time = now_iso()
    with state_lock():
        state = load_state()
        task = {
            "id": next_id(state, "task"),
            "title": title,
            "description": description,
            "status": "todo",
            "priority": "normal",
            "notes": f"Created from chat at {current_time}.",
            "command": "",
            "cwd": "",
            "auto_execute": False,
            "agent_backend": "",
            "agent_model": "",
            "agent_prompt": "",
            "agent_run_id": None,
            "plans": [],
            "latest_plan_id": None,
            "runs": [],
            "created_at": current_time,
            "updated_at": current_time,
        }
        state["tasks"].append(task)
        save_state(state)
    print(f"created {format_task(task)}")


def chat_append_task_note(rest):
    task_id, _, note = rest.partition(" ")
    note = note.strip()
    if not task_id or not note:
        print("usage: /note <task-id> <text>")
        return
    current_time = now_iso()
    with state_lock():
        state = load_state()
        task = find_task(state, task_id)
        if not task:
            print(f"mew: task not found: {task_id}")
            return
        append_task_note(task, f"{current_time} chat: {note}")
        task["updated_at"] = current_time
        save_state(state)
    print(f"noted task #{task_id}")


def chat_set_task_kind(rest):
    task_id, _, kind = rest.partition(" ")
    normalized = normalize_task_kind(kind)
    if not task_id or not normalized:
        print("usage: /kind <task-id> coding|research|personal|admin|unknown")
        return
    with state_lock():
        state = load_state()
        task = find_task(state, task_id)
        if not task:
            print(f"mew: task not found: {task_id}")
            return
        task["kind"] = normalized
        task["updated_at"] = now_iso()
        save_state(state)
    print(f"task #{task['id']} kind={normalized}")

def chat_classify_tasks(rest):
    try:
        tokens = shlex.split(rest) if rest else []
    except ValueError as exc:
        print(f"mew: {exc}")
        return
    args = SimpleNamespace(
        task_id=None,
        all=False,
        mismatches=False,
        apply=False,
        clear=False,
        include_unknown=False,
        json=False,
    )
    for token in tokens:
        normalized = token.strip().casefold().lstrip("-")
        if normalized == "all":
            args.all = True
        elif normalized in ("mismatch", "mismatches"):
            args.mismatches = True
        elif normalized == "apply":
            args.apply = True
        elif normalized == "clear":
            args.clear = True
        elif normalized in ("include-unknown", "unknown"):
            args.include_unknown = True
        elif args.task_id is None:
            args.task_id = token
        else:
            print("usage: /classify [task-id|all] [mismatches] [apply|clear]")
            return
    cmd_task_classify(args)


def print_chat_questions(show_all=False):
    state = load_state()
    questions = state["questions"] if show_all else open_questions(state)
    if not questions:
        print("No questions.")
        return
    for question in questions:
        status = question.get("status")
        task = question.get("related_task_id")
        task_text = f" task=#{task}" if task else ""
        print(f"#{question['id']} [{status}]{task_text} {question['text']}")


def chat_defer_question(rest):
    question_id, _, reason = rest.partition(" ")
    if not question_id:
        print("usage: /defer <question-id> [reason]")
        return
    with state_lock():
        state = load_state()
        question = find_question(state, question_id)
        if not question:
            print(f"mew: question not found: {question_id}")
            return
        if question.get("status") == "answered":
            print(f"mew: question already answered: {question_id}")
            return
        mark_question_deferred(state, question, reason=reason.strip())
        save_state(state)
    print(f"deferred question #{question_id}")


def chat_reopen_question(rest):
    question_id = rest.strip()
    if not question_id:
        print("usage: /reopen <question-id>")
        return
    with state_lock():
        state = load_state()
        question = find_question(state, question_id)
        if not question:
            print(f"mew: question not found: {question_id}")
            return
        if question.get("status") == "answered":
            print(f"mew: question already answered: {question_id}")
            return
        reopen_question(state, question)
        save_state(state)
    print(f"reopened question #{question_id}")


def print_chat_attention(show_all=False):
    state = load_state()
    items = state["attention"]["items"] if show_all else open_attention_items(state)
    if not items:
        print("No attention items.")
        return
    for item in items:
        print(f"#{item['id']} [{item.get('status')}/{item.get('priority')}] {item.get('title')}: {item.get('reason')}")


def chat_resolve_attention(rest):
    if not rest:
        print("usage: /resolve all|<attention-id...>")
        return
    try:
        parts = shlex.split(rest)
    except ValueError as exc:
        print(f"mew: {exc}")
        return

    current_time = now_iso()
    with state_lock():
        state = load_state()
        if len(parts) == 1 and parts[0].casefold() == "all":
            items = [item for item in state["attention"]["items"] if item.get("status") == "open"]
        else:
            ids = {str(part) for part in parts}
            items = [
                item
                for item in state["attention"]["items"]
                if str(item.get("id")) in ids and item.get("status") == "open"
            ]
            found_ids = {str(item.get("id")) for item in items}
            missing = ids - found_ids
            if missing:
                print(f"mew: attention not found or already resolved: {', '.join(sorted(missing))}")
                return

        for item in items:
            item["status"] = "resolved"
            item["resolved_at"] = current_time
            item["updated_at"] = current_time
        save_state(state)

    print(f"resolved {len(items)} attention item(s)")


def print_chat_outbox(show_all=False):
    state = load_state()
    messages = state["outbox"] if show_all else [message for message in state["outbox"] if not message.get("read_at")]
    if not messages:
        print("No messages.")
        return
    print_outbox_messages(messages)


def print_chat_agents(show_all=False):
    state = load_state()
    runs = state["agent_runs"]
    if not show_all:
        runs = [run for run in runs if run.get("status") in ("created", "running")]
    if not runs:
        print("No agent runs.")
        return
    for run in runs:
        pid = run.get("external_pid") or ""
        purpose = run.get("purpose") or "implementation"
        print(
            f"#{run['id']} [{run['status']}/{purpose}] task={run.get('task_id')} "
            f"{run.get('backend')}:{run.get('model')} pid={pid}"
        )


def _first_agent_output(run):
    return run.get("result") or run.get("stdout") or run.get("stderr") or ""


def chat_collect_agent_result(rest):
    run_id = rest.strip()
    if not run_id:
        print("usage: /result <run-id>")
        return
    with state_lock():
        state = load_state()
        run = find_agent_run(state, run_id)
        if not run:
            print(f"mew: agent run not found: {run_id}")
            return
        try:
            get_agent_run_result(state, run)
        except ValueError as exc:
            print(f"mew: {exc}")
            return
        save_state(state)
    print(f"agent run #{run['id']} status={run['status']}")
    output = _first_agent_output(run)
    if output:
        print(output)


def chat_wait_agent(rest):
    parts = rest.split()
    if not parts:
        print("usage: /wait <run-id> [seconds]")
        return
    run_id = parts[0]
    timeout = None
    if len(parts) > 1:
        try:
            timeout = float(parts[1])
        except ValueError:
            print("usage: /wait <run-id> [seconds]")
            return
    with state_lock():
        state = load_state()
        run = find_agent_run(state, run_id)
        if not run:
            print(f"mew: agent run not found: {run_id}")
            return
        try:
            wait_agent_run(state, run, timeout=timeout)
        except ValueError as exc:
            print(f"mew: {exc}")
            return
        save_state(state)
    print(f"agent run #{run['id']} status={run['status']}")
    output = _first_agent_output(run)
    if output:
        print(output)


def chat_review_agent(rest):
    try:
        parts = shlex.split(rest)
    except ValueError as exc:
        print(f"mew: {exc}")
        return
    if not parts:
        print("usage: /review <run-id> [dry-run]")
        return
    run_id = parts[0]
    dry_run = any(part in ("dry-run", "--dry-run") for part in parts[1:])

    with state_lock():
        state = load_state()
        implementation_run = find_agent_run(state, run_id)
        if not implementation_run:
            print(f"mew: agent run not found: {run_id}")
            return
        if implementation_run.get("purpose") == "review":
            print(f"mew: run #{run_id} is already a review run")
            return
        if implementation_run.get("status") not in ("completed", "failed"):
            print(f"mew: run #{run_id} status={implementation_run.get('status')}; cannot review yet")
            return
        task = find_task(state, implementation_run.get("task_id"))
        if not task:
            print(f"mew: task not found for run #{run_id}")
            return
        plan = find_task_plan(task, implementation_run.get("plan_id")) if implementation_run.get("plan_id") else None
        review_run = create_review_run_for_implementation(state, task, implementation_run, plan=plan)
        if dry_run:
            review_run["status"] = "dry_run"
            ensure_agent_run_prompt_file(review_run)
            review_run["command"] = build_ai_cli_run_command(review_run)
        else:
            start_agent_run(state, review_run)
        save_state(state)

    if dry_run:
        print(f"created dry-run review run #{review_run['id']} for run #{implementation_run['id']}")
        print(" ".join(review_run["command"]))
    else:
        print(f"started review run #{review_run['id']} for run #{implementation_run['id']} status={review_run.get('status')} pid={review_run.get('external_pid')}")


def chat_followup_review(rest):
    run_id = rest.strip()
    if not run_id:
        print("usage: /followup <review-run-id>")
        return
    with state_lock():
        state = load_state()
        review_run = find_agent_run(state, run_id)
        if not review_run:
            print(f"mew: agent run not found: {run_id}")
            return
        if review_run.get("purpose") != "review":
            print(f"mew: run #{run_id} is not a review run")
            return
        if not review_run.get("result") and not review_run.get("stdout"):
            try:
                get_agent_run_result(state, review_run, verbose=False)
            except ValueError as exc:
                print(f"mew: {exc}")
                return
        task = find_task(state, review_run.get("task_id"))
        if not task:
            print(f"mew: task not found for review run #{run_id}")
            return
        followup, status = create_follow_up_task_from_review(state, task, review_run)
        save_state(state)
    print(f"review run #{review_run['id']} status={status}")
    if followup:
        print(format_task(followup))
    else:
        print("no follow-up task created")


def chat_retry_agent(rest):
    try:
        parts = shlex.split(rest)
    except ValueError as exc:
        print(f"mew: {exc}")
        return
    if not parts:
        print("usage: /retry <run-id> [dry-run]")
        return
    run_id = parts[0]
    dry_run = any(part in ("dry-run", "--dry-run") for part in parts[1:])

    with state_lock():
        state = load_state()
        failed_run = find_agent_run(state, run_id)
        if not failed_run:
            print(f"mew: agent run not found: {run_id}")
            return
        if failed_run.get("purpose", "implementation") != "implementation":
            print(f"mew: run #{run_id} is not an implementation run")
            return
        if failed_run.get("status") not in ("failed", "completed"):
            print(f"mew: run #{run_id} status={failed_run.get('status')}; cannot retry yet")
            return
        task = find_task(state, failed_run.get("task_id"))
        if not task:
            print(f"mew: task not found for run #{run_id}")
            return
        plan = find_task_plan(task, failed_run.get("plan_id")) if failed_run.get("plan_id") else latest_task_plan(task)
        retry_run = create_retry_run_for_implementation(
            state,
            task,
            failed_run,
            plan=plan,
            dry_run=dry_run,
        )
        if dry_run:
            ensure_agent_run_prompt_file(retry_run)
            retry_run["command"] = build_ai_cli_run_command(retry_run)
        else:
            start_agent_run(state, retry_run)
        save_state(state)

    if dry_run:
        print(f"created dry-run retry run #{retry_run['id']} for run #{failed_run['id']}")
        print(" ".join(retry_run["command"]))
    else:
        print(f"started retry run #{retry_run['id']} for run #{failed_run['id']} status={retry_run.get('status')} pid={retry_run.get('external_pid')}")


def chat_sweep_agents(rest):
    parts = rest.split()
    dry_run = "dry-run" in parts or "--dry-run" in parts
    start_reviews = "reviews" in parts or "--reviews" in parts
    with state_lock():
        state = load_state()
        report = sweep_agent_runs(
            state,
            collect=True,
            start_reviews=start_reviews,
            followup=True,
            dry_run=dry_run,
        )
        if not dry_run:
            save_state(state)
    print(format_sweep_report(report))


def print_chat_verification():
    state = load_state()
    runs = list(reversed(state.get("verification_runs", [])[-10:]))
    if not runs:
        print("No verification runs.")
        return
    for run in runs:
        print(format_verification_run(run))


def chat_verification_failure_reason(command, result):
    parts = [command, f"exit_code={result.get('exit_code')}"]
    stdout = result.get("stdout") or ""
    stderr = result.get("stderr") or ""
    if stdout:
        parts.append("stdout:\n" + clip_output(stdout, 2000))
    if stderr:
        parts.append("stderr:\n" + clip_output(stderr, 2000))
    return "\n".join(parts)


def chat_run_verification(command, timeout=300):
    command = command.strip()
    if not command:
        print("usage: /verify <command>")
        return

    try:
        result = run_command_record(command, cwd=".", timeout=timeout)
    except ValueError as exc:
        print(f"mew: {exc}")
        return

    current_time = now_iso()
    with state_lock():
        state = load_state()
        run = {
            "id": next_id(state, "verification_run"),
            "event_id": None,
            "task_id": None,
            "reason": "manual chat verification",
            **result,
            "created_at": current_time,
            "updated_at": now_iso(),
        }
        state.setdefault("verification_runs", []).append(run)
        del state["verification_runs"][:-100]
        if result.get("exit_code") != 0:
            add_attention_item(
                state,
                "verification",
                f"Verification run #{run['id']} failed",
                chat_verification_failure_reason(command, result),
                priority="high",
            )
        save_state(state)

    print(format_verification_run(run))
    print(format_command_record(result))


def print_chat_writes():
    state = load_state()
    runs = list(reversed(state.get("write_runs", [])[-10:]))
    if not runs:
        print("No write runs.")
        return
    for run in runs:
        print(format_write_run(run))


def print_chat_runtime_effects(rest=""):
    limit = 10
    if rest.strip():
        try:
            limit = int(rest.strip())
        except ValueError:
            print("usage: /runtime-effects [n]")
            return
    if limit < 1:
        print("usage: /runtime-effects [n]")
        return

    state = load_state()
    effects = list(reversed(state.get("runtime_effects", [])[-limit:]))
    if not effects:
        print("No runtime effects.")
        return
    for effect in effects:
        print(format_runtime_effect(effect))


def print_chat_thoughts(details=False):
    state = load_state()
    thoughts = list(reversed(state.get("thought_journal", [])[-10:]))
    if not thoughts:
        print("No thought journal entries.")
        return
    for thought in thoughts:
        print(format_thought_entry(thought, details=details))


def latest_processed_event(state):
    for event in reversed(state.get("inbox", [])):
        if event.get("processed_at"):
            return event
    return None


def describe_plan_item(item):
    item_type = item.get("type") or "unknown"
    parts = [item_type]
    for key in ("task_id", "run_id", "plan_id"):
        if item.get(key) is not None:
            parts.append(f"{key}={item.get(key)}")
    for key in ("reason", "question", "title", "summary", "text"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            first_line = value.strip().splitlines()[0]
            if len(first_line) > 120:
                first_line = first_line[:117] + "..."
            parts.append(f"{key}={first_line}")
            break
    return " ".join(str(part) for part in parts)


def print_chat_why():
    state = load_state()
    event = latest_processed_event(state)
    if not event:
        print("No processed events yet.")
        return

    decision_plan = event.get("decision_plan") or {}
    action_plan = event.get("action_plan") or {}
    print(f"Latest processed event: #{event.get('id')} {event.get('type')} at {event.get('processed_at')}")
    if decision_plan.get("summary"):
        print(f"think: {decision_plan.get('summary')}")
    if action_plan.get("summary"):
        print(f"act: {action_plan.get('summary')}")
    decisions = decision_plan.get("decisions") or []
    actions = action_plan.get("actions") or []
    if decisions:
        print("decisions:")
        for decision in decisions[:10]:
            print(f"- {describe_plan_item(decision)}")
    if actions:
        print("actions:")
        for action in actions[:10]:
            print(f"- {describe_plan_item(action)}")


def _after_since(value, since):
    if not since:
        return True
    if not value:
        return False
    return str(value) > str(since)


def print_chat_digest():
    state = load_state()
    since = state.get("user_status", {}).get("last_interaction_at")
    events = [
        event
        for event in state.get("inbox", [])
        if _after_since(event.get("created_at"), since) or _after_since(event.get("processed_at"), since)
    ]
    outbox = [message for message in state.get("outbox", []) if _after_since(message.get("created_at"), since)]
    tasks = [task for task in state.get("tasks", []) if _after_since(task.get("created_at"), since)]
    agent_runs = [
        run
        for run in state.get("agent_runs", [])
        if _after_since(run.get("created_at"), since) or _after_since(run.get("updated_at"), since)
    ]
    verifications = [
        run
        for run in state.get("verification_runs", [])
        if _after_since(run.get("created_at"), since) or _after_since(run.get("updated_at"), since)
    ]
    writes = [
        run
        for run in state.get("write_runs", [])
        if _after_since(run.get("created_at"), since) or _after_since(run.get("updated_at"), since)
    ]
    passive_ticks = len([event for event in events if event.get("type") == "passive_tick"])
    failed_verifications = len([run for run in verifications if run.get("exit_code") != 0])
    rolled_back = len([run for run in writes if run.get("rolled_back")])

    print(f"Digest since: {since or 'beginning'}")
    print(f"events: {len(events)} passive_ticks={passive_ticks}")
    print(f"outbox_messages: {len(outbox)} unread={len([message for message in state['outbox'] if not message.get('read_at')])}")
    print(f"new_tasks: {len(tasks)}")
    print(f"agent_runs_touched: {len(agent_runs)}")
    print(f"verification_runs: {len(verifications)} failed={failed_verifications}")
    print(f"write_runs: {len(writes)} rolled_back={rolled_back}")
    print(f"open_attention: {len(open_attention_items(state))}")
    print(f"next: {next_move(state)}")


def chat_set_paused(paused, reason=""):
    current_time = now_iso()
    with state_lock():
        state = load_state()
        autonomy = state.setdefault("autonomy", {})
        autonomy["paused"] = paused
        autonomy["updated_at"] = current_time
        if paused:
            autonomy["pause_reason"] = reason
            autonomy["paused_at"] = current_time
        else:
            autonomy["pause_reason"] = ""
            autonomy["resumed_at"] = current_time
        save_state(state)


def chat_set_mode_override(value):
    if value not in ("observe", "propose", "act", "default", ""):
        print("usage: /mode observe|propose|act|default")
        return
    current_time = now_iso()
    with state_lock():
        state = load_state()
        autonomy = state.setdefault("autonomy", {})
        autonomy["level_override"] = "" if value in ("default", "") else value
        autonomy["updated_at"] = current_time
        save_state(state)
    if value in ("default", ""):
        print("mode override cleared")
    else:
        print(f"mode override: {value}")


def chat_approve_task(task_id):
    with state_lock():
        state = load_state()
        task = find_task(state, task_id)
        if not task:
            print(f"mew: task not found: {task_id}")
            return
        task["status"] = "ready"
        task["auto_execute"] = True
        task["updated_at"] = now_iso()
        save_state(state)
    print(f"approved task #{task_id}: ready auto_execute=true")


def chat_set_task_status(task_id, status):
    with state_lock():
        state = load_state()
        task = find_task(state, task_id)
        if not task:
            print(f"mew: task not found: {task_id}")
            return
        task["status"] = status
        task["updated_at"] = now_iso()
        save_state(state)
    print(f"task #{task_id} status={status}")


def chat_plan_task(rest):
    try:
        parts = shlex.split(rest)
    except ValueError as exc:
        print(f"mew: {exc}")
        return
    if not parts:
        print("usage: /plan <task-id> [force] [prompt]")
        return
    task_id = parts[0]
    force = any(part in ("force", "--force") for part in parts[1:])
    show_prompt = any(part in ("prompt", "--prompt") for part in parts[1:])

    with state_lock():
        state = load_state()
        task = find_task(state, task_id)
        if not task:
            print(f"mew: task not found: {task_id}")
            return
        if not is_programmer_task(task):
            print(f"mew: task #{task['id']} kind={task_kind(task)} is not a coding task; use /kind {task['id']} coding first")
            return
        plan = latest_task_plan(task)
        created = False
        if force or not plan:
            plan = create_task_plan(state, task)
            created = True
            save_state(state)

    print(("created " if created else "") + format_task_plan(plan))
    if show_prompt:
        print("implementation_prompt:")
        print(plan.get("implementation_prompt") or "")
        print("review_prompt:")
        print(plan.get("review_prompt") or "")


def chat_dispatch_task(rest):
    try:
        parts = shlex.split(rest)
    except ValueError as exc:
        print(f"mew: {exc}")
        return
    if not parts:
        print("usage: /dispatch <task-id> [dry-run]")
        return
    task_id = parts[0]
    dry_run = any(part in ("dry-run", "--dry-run") for part in parts[1:])

    with state_lock():
        state = load_state()
        task = find_task(state, task_id)
        if not task:
            print(f"mew: task not found: {task_id}")
            return
        if not is_programmer_task(task):
            print(f"mew: task #{task['id']} kind={task_kind(task)} is not a coding task; use /kind {task['id']} coding first")
            return
        plan = latest_task_plan(task)
        plan_created = False
        if not plan:
            plan = create_task_plan(state, task)
            plan_created = True
        run = create_implementation_run_from_plan(state, task, plan, dry_run=dry_run)
        if dry_run:
            ensure_agent_run_prompt_file(run)
            run["command"] = build_ai_cli_run_command(run)
        else:
            start_agent_run(state, run)
        save_state(state)

    if plan_created:
        print(f"created {format_task_plan(plan)}")
    if dry_run:
        print(f"created dry-run implementation run #{run['id']} from plan #{plan['id']}")
        print(" ".join(run["command"]))
    else:
        print(f"started implementation run #{run['id']} task={task['id']} plan={plan['id']} status={run.get('status')} pid={run.get('external_pid')}")


def chat_buddy(rest):
    try:
        tokens = shlex.split(rest) if rest else []
    except ValueError as exc:
        print(f"mew: {exc}")
        return
    args = SimpleNamespace(
        task_id=None,
        cwd=None,
        agent_model=None,
        review_model=None,
        objective=None,
        approach=None,
        force_plan=False,
        dispatch=False,
        force_dispatch=False,
        dry_run=False,
        review=False,
        force_review=False,
        json=False,
    )
    for token in tokens:
        normalized = token.strip().casefold().lstrip("-")
        if normalized == "dispatch":
            args.dispatch = True
        elif normalized in ("dry-run", "dry"):
            args.dry_run = True
        elif normalized == "review":
            args.review = True
        elif normalized == "force-plan":
            args.force_plan = True
        elif normalized == "force-dispatch":
            args.force_dispatch = True
        elif normalized == "force-review":
            args.force_review = True
        elif normalized.startswith("model="):
            args.agent_model = token.split("=", 1)[1]
        elif normalized.startswith("review-model="):
            args.review_model = token.split("=", 1)[1]
        elif normalized.startswith("cwd="):
            args.cwd = token.split("=", 1)[1]
        elif args.task_id is None:
            args.task_id = token
        else:
            print("usage: /buddy [task-id] [dispatch] [dry-run] [review]")
            return
    cmd_buddy(args)


def chat_self_improve(rest):
    try:
        parts = shlex.split(rest)
    except ValueError as exc:
        print(f"mew: {exc}")
        return

    option_tokens = {
        "dispatch",
        "--dispatch",
        "dry-run",
        "--dry-run",
        "force",
        "--force",
        "force-plan",
        "--force-plan",
        "prompt",
        "--prompt",
        "ready",
        "--ready",
        "auto-execute",
        "--auto-execute",
    }
    flags = {part.casefold() for part in parts if part.casefold() in option_tokens}
    dry_run = "dry-run" in flags or "--dry-run" in flags
    dispatch = "dispatch" in flags or "--dispatch" in flags or dry_run
    force = "force" in flags or "--force" in flags
    force_plan = "force-plan" in flags or "--force-plan" in flags
    show_prompt = "prompt" in flags or "--prompt" in flags
    ready = dispatch or "ready" in flags or "--ready" in flags
    auto_execute = "auto-execute" in flags or "--auto-execute" in flags
    focus = " ".join(part for part in parts if part.casefold() not in option_tokens).strip()

    with state_lock():
        state = load_state()
        task, created = create_self_improve_task(
            state,
            focus=focus,
            cwd=".",
            ready=ready,
            auto_execute=auto_execute,
            force=force,
        )
        plan, plan_created = ensure_self_improve_plan(state, task, force=force_plan)
        run = None
        if dispatch:
            run = create_implementation_run_from_plan(state, task, plan, dry_run=dry_run)
            if dry_run:
                ensure_agent_run_prompt_file(run)
                run["command"] = build_ai_cli_run_command(run)
            else:
                start_agent_run(state, run)
        save_state(state)

    print(("created " if created else "reused ") + format_task(task))
    print(("created " if plan_created else "reused ") + format_task_plan(plan))
    if show_prompt:
        print("implementation_prompt:")
        print(plan.get("implementation_prompt") or "")
        print("review_prompt:")
        print(plan.get("review_prompt") or "")
    if run:
        if dry_run:
            print(f"created dry-run self-improve run #{run['id']} from plan #{plan['id']}")
            print(" ".join(run["command"]))
        else:
            print(f"started self-improve run #{run['id']} status={run.get('status')} pid={run.get('external_pid')}")


def run_chat_slash_command(line, chat_state):
    body = line[1:].strip()
    command, _, rest = body.partition(" ")
    command = command.casefold()
    rest = rest.strip()

    if command in ("exit", "quit", "q"):
        return "exit"
    if command in ("help", "?"):
        topic = rest.casefold()
        if topic in ("work", "work-session", "session", "sessions"):
            print(CHAT_WORK_HELP)
        else:
            print(CHAT_HELP)
        return "continue"
    if command in ("focus", "daily"):
        print(format_focus(build_focus_data(load_state(), limit=3)))
        return "continue"
    if command == "brief":
        print(build_brief(load_state()))
        return "continue"
    if command == "next":
        print(next_move(load_state()))
        return "continue"
    if command == "doctor":
        if rest:
            print("usage: /doctor")
        else:
            args = SimpleNamespace(auth=None, require_auth=False)
            print(format_doctor_data(build_doctor_data(args)))
        return "continue"
    if command == "repair":
        if rest and rest.casefold() not in ("--force", "force"):
            print("usage: /repair [--force]")
        else:
            args = SimpleNamespace(force=rest.casefold() in ("--force", "force"), json=False)
            cmd_repair(args)
        return "continue"
    if command == "status":
        print_chat_status()
        return "continue"
    if command in ("perception", "perceive"):
        print_chat_perception()
        return "continue"
    if command == "add":
        chat_add_task(rest)
        return "continue"
    if command in ("tasks", "task"):
        print_chat_tasks(show_all=rest.casefold() == "all")
        return "continue"
    if command == "show":
        if not rest:
            print("usage: /show <task-id>")
        else:
            print_chat_task(rest)
        return "continue"
    if command == "work":
        print_chat_workbench(rest or None)
        return "continue"
    if command in ("work-session", "work_session"):
        chat_work_session(rest, chat_state)
        return "continue"
    if command in ("continue", "cont"):
        chat_work_session(("live " + _chat_continue_rest(rest, chat_state)).strip(), chat_state)
        return "continue"
    if command == "note":
        chat_append_task_note(rest)
        return "continue"
    if command == "kind":
        chat_set_task_kind(rest)
        return "continue"
    if command in ("classify", "classification"):
        chat_classify_tasks(rest)
        return "continue"
    if command in ("questions", "question"):
        print_chat_questions(show_all=rest.casefold() == "all")
        return "continue"
    if command == "defer":
        chat_defer_question(rest)
        return "continue"
    if command == "reopen":
        chat_reopen_question(rest)
        return "continue"
    if command == "attention":
        print_chat_attention(show_all=rest.casefold() == "all")
        return "continue"
    if command == "resolve":
        chat_resolve_attention(rest)
        return "continue"
    if command == "outbox":
        print_chat_outbox(show_all=rest.casefold() == "all")
        return "continue"
    if command in ("agents", "agent", "runs"):
        print_chat_agents(show_all=rest.casefold() == "all")
        return "continue"
    if command == "result":
        chat_collect_agent_result(rest)
        return "continue"
    if command == "wait":
        chat_wait_agent(rest)
        return "continue"
    if command == "review":
        chat_review_agent(rest)
        return "continue"
    if command == "followup":
        chat_followup_review(rest)
        return "continue"
    if command == "retry":
        chat_retry_agent(rest)
        return "continue"
    if command == "sweep":
        chat_sweep_agents(rest)
        return "continue"
    if command == "verification":
        print_chat_verification()
        return "continue"
    if command == "verify":
        if not rest:
            print_chat_verification()
        else:
            chat_run_verification(rest)
        return "continue"
    if command in ("writes", "write"):
        print_chat_writes()
        return "continue"
    if command in ("runtime-effects", "runtime_effects", "effects"):
        print_chat_runtime_effects(rest)
        return "continue"
    if command in ("thoughts", "thought"):
        print_chat_thoughts(details=rest.casefold() in ("details", "--details"))
        return "continue"
    if command == "why":
        print_chat_why()
        return "continue"
    if command == "digest":
        print_chat_digest()
        return "continue"
    if command == "approve":
        if not rest:
            print("usage: /approve <task-id>")
        else:
            chat_approve_task(rest)
        return "continue"
    if command == "ready":
        if not rest:
            print("usage: /ready <task-id>")
        else:
            chat_set_task_status(rest, "ready")
        return "continue"
    if command == "done":
        if not rest:
            print("usage: /done <task-id>")
        else:
            chat_set_task_status(rest, "done")
        return "continue"
    if command in ("block", "blocked"):
        if not rest:
            print("usage: /block <task-id>")
        else:
            chat_set_task_status(rest, "blocked")
        return "continue"
    if command == "plan":
        chat_plan_task(rest)
        return "continue"
    if command == "dispatch":
        chat_dispatch_task(rest)
        return "continue"
    if command == "buddy":
        chat_buddy(rest)
        return "continue"
    if command in ("self", "self-improve"):
        chat_self_improve(rest)
        return "continue"
    if command == "pause":
        chat_set_paused(True, rest)
        print("autonomy paused")
        return "continue"
    if command == "resume":
        chat_set_paused(False)
        print("autonomy resumed")
        return "continue"
    if command == "mode":
        chat_set_mode_override(rest.casefold())
        return "continue"
    if command == "history":
        print_chat_outbox(show_all=True)
        return "continue"
    if command == "activity":
        value = rest.casefold()
        if value in ("on", "true", "1"):
            chat_state["activity"] = True
            chat_state["activity_offset"] = current_log_offset()
            print("activity: on")
        elif value in ("off", "false", "0"):
            chat_state["activity"] = False
            print("activity: off")
        else:
            print("usage: /activity on|off")
        return "continue"
    if command == "ack":
        if not rest:
            print("usage: /ack all|routine|<ids...>")
            return "continue"
        if rest.casefold() == "all":
            with state_lock():
                state = load_state()
                ids = [message.get("id") for message in state["outbox"] if not message.get("read_at")]
            mark_outbox_read(ids)
            print(f"acknowledged {len(ids)} message(s)")
            return "continue"
        if rest.casefold() == "routine":
            with state_lock():
                state = load_state()
                ids = [
                    message.get("id")
                    for message in state["outbox"]
                    if is_routine_outbox_message(state, message)
                ]
            mark_outbox_read(ids)
            print(f"acknowledged {len(ids)} routine message(s)")
            return "continue"
        try:
            ids = shlex.split(rest)
        except ValueError as exc:
            print(f"mew: {exc}")
            return "continue"
        mark_outbox_read(ids)
        print(f"acknowledged {len(ids)} message(s)")
        return "continue"
    if command == "reply":
        question_id, _, text = rest.partition(" ")
        if not question_id or not text.strip():
            print("usage: /reply <question-id> <text>")
            return "continue"
        with state_lock():
            state = load_state()
            question = find_question(state, question_id)
            if not question:
                print(f"mew: question not found: {question_id}")
                return "continue"
        event = queue_user_message(text.strip(), reply_to_question_id=question_id)
        print(f"answered question #{question_id} with event #{event['id']}")
        return "continue"

    print(f"unknown command: /{command}. Type /help.")
    return "continue"


def read_chat_line(poll_interval, prompt_state):
    if not sys.stdin.isatty():
        line = sys.stdin.readline()
        if line == "":
            return CHAT_EOF
        return line.rstrip("\n")

    if prompt_state.get("needed", True):
        print("mew> ", end="", flush=True)
        prompt_state["needed"] = False

    readable, _, _ = select.select([sys.stdin], [], [], poll_interval)
    if not readable:
        return None
    line = sys.stdin.readline()
    prompt_state["needed"] = True
    if line == "":
        return CHAT_EOF
    return line.rstrip("\n")


def cmd_chat(args):
    print("mew chat. Type /help for commands, /exit to leave.", flush=True)
    state = load_state()
    if not args.no_brief:
        print(build_brief(state, limit=args.limit), flush=True)
    session = active_work_session(state)
    if session:
        print(format_work_cockpit_controls(state=state, session=session), flush=True)

    seen_ids = emit_initial_outbox(
        history=False,
        unread=not args.no_unread,
        mark_read=args.mark_read,
    )
    chat_state = {
        "activity": bool(args.activity),
        "activity_offset": current_log_offset() if args.activity else None,
    }
    prompt_state = {"needed": True}
    deadline = time.monotonic() + max(0.0, args.timeout) if args.timeout is not None else None

    try:
        while True:
            emit_new_outbox(seen_ids, args.mark_read)
            if chat_state["activity"]:
                chat_state["activity_offset"] = emit_new_activity(chat_state["activity_offset"])
            if deadline is not None and time.monotonic() >= deadline:
                return 0

            poll_interval = args.poll_interval
            if deadline is not None:
                poll_interval = min(poll_interval, max(0.0, deadline - time.monotonic()))

            line = read_chat_line(poll_interval, prompt_state)
            if line is None:
                continue
            if line is CHAT_EOF:
                return 0
            text = line.strip()
            if not text:
                continue
            if text.startswith("/"):
                result = run_chat_slash_command(text, chat_state)
                if result == "exit":
                    return 0
                continue

            warn_if_runtime_inactive()
            event = queue_user_message(text)
            print(f"queued message event #{event['id']}", flush=True)
    except KeyboardInterrupt:
        print("\nleft chat")
        return 0

def cmd_log(args):
    if not LOG_FILE.exists():
        print("No runtime log.")
        return 0
    print(LOG_FILE.read_text(encoding="utf-8").rstrip())
    return 0

def cmd_trace(args):
    records = read_model_traces(limit=args.limit, include_prompt=args.prompt, phase=args.phase or "")
    if args.json:
        print(json.dumps({"traces": records, "phase": args.phase or ""}, ensure_ascii=False, indent=2))
        return 0
    if not records:
        print("No model traces.")
        return 0
    for record in records:
        plan = record.get("plan") if isinstance(record.get("plan"), dict) else {}
        decisions = len(plan.get("decisions") or [])
        actions = len(plan.get("actions") or [])
        suffix = ""
        if decisions:
            suffix = f" decisions={decisions}"
        elif actions:
            suffix = f" actions={actions}"
        print(
            f"{record.get('at') or '(unknown)'} "
            f"{record.get('phase') or '?'} "
            f"{record.get('status') or '?'} "
            f"event=#{record.get('event_id') or ''}/{record.get('event_type') or ''} "
            f"backend={record.get('backend') or ''} model={record.get('model') or ''} "
            f"prompt_chars={record.get('prompt_chars') or 0} "
            f"sha={str(record.get('prompt_sha256') or '')[:12]}"
            f"{suffix}"
        )
        reason = record.get("reason")
        if not reason and record.get("status") == "skipped":
            reason = record.get("error")
        if reason:
            print(f"  reason: {reason}")
        elif record.get("error"):
            print(f"  error: {record.get('error')}")
        if args.prompt and record.get("prompt"):
            print("  prompt:")
            print(record.get("prompt"))
    return 0

def read_effect_records(limit=20):
    ensure_state_dir()
    if limit <= 0:
        return []
    if not EFFECT_LOG_FILE.exists():
        return []
    try:
        lines = EFFECT_LOG_FILE.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    records = []
    for line in lines:
        if not line.strip():
            continue
        try:
            record = json.loads(line)
            if not isinstance(record, dict):
                record = {"type": "corrupt_effect_record", "raw": line}
            records.append(record)
        except json.JSONDecodeError:
            records.append({"type": "corrupt_effect_record", "raw": line})
    return records[-limit:]

def cmd_effects(args):
    records = read_effect_records(limit=args.limit)
    if args.json:
        print(json.dumps({"effects": records}, ensure_ascii=False, indent=2))
        return 0
    if not records:
        print("No effects yet.")
        return 0
    for record in records:
        counts = record.get("counts") or {}
        sha = str(record.get("state_sha256") or "")[:12]
        print(
            f"{record.get('saved_at') or '(unknown)'} "
            f"{record.get('type') or 'unknown'} "
            f"sha={sha} "
            f"tasks={counts.get('tasks')} inbox={counts.get('inbox')} outbox={counts.get('outbox')}"
        )
    return 0

def format_runtime_effect(effect):
    actions = ",".join(effect.get("action_types") or []) or "-"
    verification = ",".join(str(item) for item in effect.get("verification_run_ids") or []) or "-"
    writes = ",".join(str(item) for item in effect.get("write_run_ids") or []) or "-"
    finished = effect.get("finished_at") or ""
    text = (
        f"#{effect.get('id')} [{effect.get('status')}] "
        f"event=#{effect.get('event_id')} reason={effect.get('reason')} "
        f"actions={actions} verification={verification} writes={writes} "
        f"finished={finished}"
    )
    outcome = effect.get("outcome")
    if outcome:
        text += f" outcome={clip_output(outcome, 160)}"
    recovery_hint = effect.get("recovery_hint")
    if recovery_hint:
        text += f" next={recovery_hint}"
    return text

def cmd_runtime_effects(args):
    state = load_state()
    effects = list(reversed(state.get("runtime_effects", [])[-args.limit:]))
    if args.json:
        print(json.dumps({"runtime_effects": effects}, ensure_ascii=False, indent=2))
        return 0
    if not effects:
        print("No runtime effects.")
        return 0
    for effect in effects:
        print(format_runtime_effect(effect))
    return 0

def cmd_guidance_init(args):
    path, created = ensure_guidance(args.path)
    if created:
        print(f"created guidance: {path}")
    else:
        print(f"guidance already exists: {path}")
    return 0

def cmd_guidance_show(args):
    text = read_guidance(args.path)
    if not text:
        print("No guidance found.")
        return 0
    print(text)
    return 0

def cmd_policy_init(args):
    path, created = ensure_policy(args.path)
    if created:
        print(f"created policy: {path}")
    else:
        print(f"policy already exists: {path}")
    return 0

def cmd_policy_show(args):
    text = read_policy(args.path)
    if not text:
        print("No policy found.")
        return 0
    print(text)
    return 0

def cmd_self_init(args):
    path, created = ensure_self(args.path)
    if created:
        print(f"created self: {path}")
    else:
        print(f"self already exists: {path}")
    return 0

def cmd_self_show(args):
    text = read_self(args.path)
    if not text:
        print("No self found.")
        return 0
    print(text)
    return 0

def cmd_desires_init(args):
    path, created = ensure_desires(args.path)
    if created:
        print(f"created desires: {path}")
    else:
        print(f"desires already exists: {path}")
    return 0

def cmd_desires_show(args):
    text = read_desires(args.path)
    if not text:
        print("No desires found.")
        return 0
    print(text)
    return 0
