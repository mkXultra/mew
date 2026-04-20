import json
import os
import select
import shlex
import signal
import shutil
import socket
import subprocess
import sys
import threading
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
from .cli_command import mew_command, mew_executable
from .brief import (
    build_activity_data,
    build_brief,
    build_brief_data,
    build_focus_data,
    filter_attention_for_tasks,
    filter_messages_for_tasks,
    filter_questions_for_tasks,
    filter_tasks_by_kind,
    format_activity,
    format_focus,
    next_move,
    scoped_agent_status,
    verification_outcome,
)
from .codex_api import load_codex_oauth
from .config import CHAT_TRANSCRIPT_FILE, DEFAULT_MODEL_BACKEND, EFFECT_LOG_FILE, LOG_FILE, STATE_DIR
from .context import build_context
from .context_checkpoint import (
    compact_context_checkpoint,
    context_load_current_state,
    current_git_reentry_state,
    latest_context_checkpoint,
    load_context_checkpoints,
)
from .desk import build_desk_view_model, format_desk_view, write_desk_view
from .daemon import build_daemon_status, format_daemon_log, format_daemon_status, tail_daemon_log
from .dogfood import (
    format_dogfood_loop_report,
    format_dogfood_report,
    format_dogfood_scenario_report,
    run_dogfood,
    run_dogfood_loop,
    run_dogfood_scenario,
    summarize_dogfood_scenario_json,
)
from .dream import build_dream_view_model, format_dream_view, render_dream_markdown, write_dream_report
from .errors import MewError
from .journal import (
    build_journal_view_model,
    format_journal_view,
    render_journal_markdown,
    write_journal_report,
)
from .memory import add_deep_memory, compact_memory, recall_memory
from .metrics import build_observation_metrics, format_observation_metrics
from .model_backends import (
    load_model_auth,
    model_backend_default_base_url,
    model_backend_default_model,
    normalize_model_backend,
)
from .model_trace import read_model_traces
from .mood import (
    build_mood_view_model,
    format_mood_view,
    render_mood_markdown,
    write_mood_report,
)
from .proof_summary import format_proof_summary, summarize_proof_artifacts
from .typed_memory import FileMemoryBackend, entry_to_dict
from .morning_paper import (
    build_morning_paper_view_model,
    format_morning_paper_view,
    load_feed,
    render_morning_paper_markdown,
    write_morning_paper_report,
)
from .passive_bundle import generate_bundle
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
from .question_view import format_question_context
from .repair import (
    repair_incomplete_runtime_effects,
    runtime_effect_recovery_decision,
    runtime_effect_recovery_followup,
)
from .self_improve import DEFAULT_SELF_IMPROVE_TITLE, create_self_improve_task, ensure_self_improve_plan
from .self_improve_audit import (
    build_m5_self_improve_audit_bundle,
    build_m5_self_improve_audit_sequence,
    format_m5_self_improve_audit_bundle,
    format_m5_self_improve_audit_sequence,
    m5_self_improve_auto_approval_blocker,
    m5_self_improve_tool_execution_blocker,
    seed_m5_self_improve_audit,
)
from .self_memory import (
    build_self_memory_view_model,
    format_self_memory_view,
    render_self_memory_markdown,
    write_self_memory_report,
)
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
)
from .snapshot import load_snapshot, save_snapshot, snapshot_path, take_snapshot
from .sweep import format_sweep_report, sweep_agent_runs
from .step_loop import format_step_loop_report, run_step_loop
from .read_tools import (
    glob_paths,
    inspect_dir,
    is_sensitive_path,
    read_file,
    resolve_allowed_path,
    search_text,
    summarize_read_result,
)
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
from .timeutil import now_iso, parse_time
from .toolbox import format_command_record, run_command_record, run_git_tool
from .validation import format_validation_issues, validate_state, validation_errors
from .write_tools import edit_file, restore_write_snapshot, snapshot_write_path, summarize_write_result, write_file
from .work_session import (
    active_work_session,
    active_work_sessions,
    add_work_session_note,
    active_memory_item_detail_parts,
    append_work_tool_running_output,
    attach_work_resume_world_state,
    build_work_active_memory,
    build_work_session_resume,
    close_work_session,
    compact_work_tool_summary,
    consume_work_session_stop,
    create_work_session,
    execute_work_tool,
    find_work_session,
    find_work_tool_call,
    finish_work_model_turn,
    finish_work_tool_call,
    build_work_session_command_entries,
    build_work_session_diff_entries,
    build_work_session_test_entries,
    clip_inline_text,
    format_diff_preview,
    format_work_action,
    format_work_continuity_inline,
    format_work_continuity_recommendation,
    format_work_failure_risk,
    format_work_session_commands,
    format_work_session_diffs,
    format_work_session_resume,
    format_work_session,
    format_work_session_tests,
    format_work_session_timeline,
    build_work_session_timeline,
    latest_unresolved_failure,
    latest_work_verify_command,
    mark_running_work_interrupted,
    mark_work_tool_call_interrupted,
    APPROVAL_STATUS_INDETERMINATE,
    clip_tail,
    request_work_session_stop,
    select_work_recovery_plan_item,
    start_work_model_turn,
    work_tool_result_error,
    start_work_tool_call,
    suggested_verify_command_for_call_path,
    update_work_model_turn_plan,
    verification_command_covers_suggestion,
    work_approval_default_defer_reason,
    work_tool_repeat_guard,
    GIT_WORK_TOOLS,
    NON_PENDING_APPROVAL_STATUSES,
    READ_ONLY_WORK_TOOLS,
    WORK_TOOLS,
    WRITE_WORK_TOOLS,
    work_session_has_pending_write_approval,
    work_session_has_running_activity,
    work_session_phase,
    work_recovery_read_root,
    work_call_path,
    work_session_runtime_command,
    work_session_task,
    work_write_pairing_status,
)
from .work_loop import plan_work_model_turn, work_tool_parameters_from_action
from .work_cells import build_work_session_cells, format_work_cells, format_work_session_cells
from .work_world import build_work_world_state
from .write_tools import resolve_allowed_write_path


RESERVED_EVENT_TYPES = {"startup", "passive_tick", "tick", "user_message"}
MAX_OUTBOX_TEXT_CHARS = 2000
RUNNING_OUTPUT_MIRROR_INTERVAL_SECONDS = 0.5
RUNNING_OUTPUT_MIRROR_BUFFER_CHARS = 4_000
APPROVAL_MODE_ACCEPT_EDITS = "accept-edits"
APPROVAL_MODES = ("default", APPROVAL_MODE_ACCEPT_EDITS)


def task_json_data(task):
    data = dict(task)
    data["effective_kind"] = task_kind(task)
    data["plan_count"] = len(task.get("plans") or [])
    data["run_count"] = len(task.get("runs") or [])
    return data


def task_json_response(task, **extra):
    data = task_json_data(task)
    response = {
        "task": data,
        "id": data.get("id"),
        "title": data.get("title"),
        "status": data.get("status"),
        "kind": data.get("kind"),
        "effective_kind": data.get("effective_kind"),
    }
    response.update(extra)
    return response


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
    if getattr(args, "json", False):
        print(json.dumps(task_json_response(task), ensure_ascii=False, indent=2))
        return 0
    print(format_task(task))
    return 0

def cmd_task_list(args):
    state = load_state()
    status = getattr(args, "status", None)
    tasks = state["tasks"] if (status or getattr(args, "all", False)) else open_tasks(state)
    if getattr(args, "kind", None):
        tasks = [task for task in tasks if task_kind(task) == args.kind]
    if status:
        if status in ("pending", "open"):
            tasks = [task for task in tasks if task.get("status") != "done"]
        else:
            tasks = [task for task in tasks if task.get("status") == status]
    tasks = sorted(tasks, key=task_sort_key)
    limit = getattr(args, "limit", None)
    if limit is not None:
        if limit <= 0:
            print("mew: task list --limit must be positive", file=sys.stderr)
            return 1
        tasks = tasks[:limit]
    if getattr(args, "json", False):
        print(
            json.dumps(
                {"tasks": [task_json_data(task) for task in tasks], "count": len(tasks)},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
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

def format_task_notes_display(notes, max_lines=12, max_chars=4000):
    if not notes:
        return ""
    text = str(notes)
    lines = text.splitlines()
    if len(lines) > max_lines:
        text = "[...older task notes omitted...]\n" + "\n".join(lines[-max_lines:])
    return clip_output(text, max_chars)


def cmd_task_show(args):
    state = load_state()
    task = find_task(state, args.task_id)
    if not task:
        print(f"mew: task not found: {args.task_id}", file=sys.stderr)
        return 1

    if getattr(args, "json", False):
        print(json.dumps(task_json_response(task), ensure_ascii=False, indent=2))
        return 0

    print(format_task(task))
    print(f"description: {task.get('description') or ''}")
    print(f"kind: {task_kind(task)}")
    print(f"kind_override: {task.get('kind') or ''}")
    print(f"notes: {format_task_notes_display(task.get('notes') or '')}")
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
    active_task_work_session = None
    for session in reversed(state.get("work_sessions", [])):
        if str(session.get("task_id")) != str(task_id):
            continue
        if session.get("status") == "active":
            active_task_work_session = session
            work_session = session
            break
        if work_session is None:
            work_session = session

    next_action = mew_command("task", "show", task_id)
    if task.get("status") == "done":
        next_action = "wait for the next user request"
    elif questions:
        next_action = f"{mew_command('reply', questions[0]['id'])} \"...\""
    elif not is_programmer_task(task):
        next_action = mew_command("task", "update", task_id, "--kind", "coding")
    elif active_task_work_session:
        next_action = _workbench_active_work_session_command(active_task_work_session, task_id)
    elif not plan:
        next_action = mew_command("work", task_id, "--start-session")
    elif not latest_implementation:
        next_action = mew_command("work", task_id, "--start-session")
    elif latest_implementation.get("status") in ("created", "running"):
        next_action = mew_command("agent", "wait", latest_implementation["id"])
    elif latest_implementation.get("status") == "dry_run":
        next_action = mew_command("buddy", "--task", task_id, "--dispatch")
    elif latest_implementation.get("status") == "failed":
        next_action = mew_command("agent", "retry", latest_implementation["id"], "--dry-run")
    elif latest_implementation.get("status") == "completed" and not latest_review:
        next_action = mew_command("agent", "review", latest_implementation["id"])
    elif latest_review and latest_review.get("status") in ("created", "running"):
        next_action = mew_command("agent", "wait", latest_review["id"])
    elif latest_review and latest_review.get("status") == "completed" and not latest_review.get("followup_processed_at"):
        next_action = mew_command("agent", "followup", latest_review["id"])

    return {
        "task": task_data,
        "kind": effective_kind,
        "plan": plan,
        "agent_runs": agent_runs,
        "verification_runs": verification_runs,
        "write_runs": write_runs,
        "work_session_verifications": work_session_verification_summaries(work_session),
        "work_session_writes": work_session_write_summaries(work_session),
        "open_questions": questions,
        "work_session": work_session,
        "next_action": next_action,
    }


def work_session_verification_summaries(session, limit=5):
    items = []
    for call in (session or {}).get("tool_calls") or []:
        if call.get("status") not in ("completed", "failed"):
            continue
        result = call.get("result") or {}
        parameters = call.get("parameters") or {}
        session_id = (session or {}).get("id")
        tool_call_id = call.get("id")
        if call.get("tool") == "run_tests":
            if result.get("exit_code") is None:
                continue
            items.append(
                {
                    "id": f"work:{session_id}:{tool_call_id}",
                    "ledger_id": f"work:{session_id}:{tool_call_id}",
                    "source": "work_session",
                    "label": f"work{session_id}#{tool_call_id}",
                    "work_session_id": session_id,
                    "task_id": (session or {}).get("task_id"),
                    "tool_call_id": tool_call_id,
                    "tool": call.get("tool"),
                    "command": result.get("command") or parameters.get("command"),
                    "exit_code": result.get("exit_code"),
                    "stdout": result.get("stdout") or "",
                    "stderr": result.get("stderr") or "",
                    "finished_at": call.get("finished_at"),
                }
            )
        verification = result.get("verification") or {}
        if verification.get("command"):
            if verification.get("exit_code") is None:
                continue
            items.append(
                {
                    "id": f"work:{session_id}:{tool_call_id}:verify",
                    "ledger_id": f"work:{session_id}:{tool_call_id}:verify",
                    "source": "work_session",
                    "label": f"work{session_id}#{tool_call_id}.verify",
                    "work_session_id": session_id,
                    "task_id": (session or {}).get("task_id"),
                    "tool_call_id": tool_call_id,
                    "tool": f"{call.get('tool')}_verification",
                    "command": verification.get("command"),
                    "exit_code": verification.get("exit_code"),
                    "stdout": verification.get("stdout") or "",
                    "stderr": verification.get("stderr") or "",
                    "finished_at": verification.get("finished_at") or call.get("finished_at"),
                }
            )
    return items if limit is None else items[-limit:]


def work_session_write_summaries(session, limit=5):
    items = []
    for call in (session or {}).get("tool_calls") or []:
        if call.get("status") not in ("completed", "failed"):
            continue
        if call.get("tool") not in WRITE_WORK_TOOLS:
            continue
        result = call.get("result") or {}
        parameters = call.get("parameters") or {}
        if not result.get("diff") and not result.get("path") and not parameters.get("path"):
            continue
        session_id = (session or {}).get("id")
        tool_call_id = call.get("id")
        items.append(
            {
                "id": f"work:{session_id}:{tool_call_id}",
                "ledger_id": f"work:{session_id}:{tool_call_id}",
                "source": "work_session",
                "label": f"work{session_id}#{tool_call_id}",
                "work_session_id": session_id,
                "task_id": (session or {}).get("task_id"),
                "tool_call_id": tool_call_id,
                "operation": call.get("tool"),
                "path": result.get("path") or parameters.get("path"),
                "changed": result.get("changed"),
                "dry_run": result.get("dry_run"),
                "written": result.get("written"),
                "rolled_back": result.get("rolled_back"),
                "verification_exit_code": result.get("verification_exit_code"),
                "approval_status": call.get("approval_status") or "",
                "diff": result.get("diff") or "",
                "rollback": result.get("rollback") or {},
                "finished_at": call.get("finished_at"),
            }
        )
    return items if limit is None else items[-limit:]


def _workbench_active_work_session_command(session, task_id):
    defaults = (session or {}).get("default_options") or {}
    has_gate = (
        bool(defaults.get("allow_read"))
        or bool(defaults.get("allow_write"))
        or bool(defaults.get("allow_shell"))
        or bool(defaults.get("allow_verify"))
    )
    if not defaults:
        return mew_command("work", task_id, "--live", "--allow-read", ".", "--max-steps", "1")
    if has_gate:
        return work_session_runtime_command(session, task_id)
    defaulted = dict(session or {})
    default_options = dict(defaults)
    default_options["allow_read"] = ["."]
    defaulted["default_options"] = default_options
    return work_session_runtime_command(defaulted, task_id)


def _format_workbench_reentry(resume, task):
    if not resume:
        return []
    lines = []
    continuity_text = format_work_continuity_inline(resume.get("continuity") or {})
    if continuity_text:
        lines.append(continuity_text)
    next_action = clip_inline_text(resume.get("next_action") or "", 360)
    if next_action:
        lines.append(f"resume_next_action: {next_action}")
    memory = resume.get("working_memory") or {}
    if memory:
        stale_memory = bool(memory.get("stale_after_model_turn_id") or memory.get("stale_after_tool_call_id"))
        if stale_memory:
            lines.append("memory: stale; refresh before relying on next_step")
            lines.extend(_format_stale_working_memory_source_lines(memory))
        for key in ("hypothesis", "next_step", "last_verified_state"):
            value = memory.get(key)
            if not value:
                continue
            if stale_memory and key != "next_step":
                continue
            label = "stale_next_step" if key == "next_step" and stale_memory else key
            lines.append(f"{label}: {clip_inline_text(value, 360)}")
        questions = memory.get("open_questions") or []
        if questions:
            lines.append(f"open_questions: {clip_inline_text('; '.join(str(item) for item in questions), 360)}")

    notes = resume.get("notes") or []
    display_notes = [
        note
        for note in notes
        if not (
            note.get("source") == "system"
            and str(note.get("text") or "").startswith(("Follow reached max_steps=", "Live run reached max_steps="))
        )
    ]
    for note in display_notes[-2:]:
        text = clip_inline_text(note.get("text") or "", 360)
        if text:
            source = note.get("source") or "note"
            lines.append(f"note[{source}]: {text}")

    risk = format_work_failure_risk(
        resume.get("unresolved_failure") or latest_unresolved_failure(resume.get("failures") or [])
    )
    if risk:
        lines.append(f"risk: {risk}")

    audit = resume.get("same_surface_audit") or {}
    if audit:
        paths = audit.get("paths") or []
        path_text = f" for {', '.join(str(path) for path in paths[:2])}" if paths else ""
        lines.append(
            f"same_surface_audit: {audit.get('status')}{path_text}; "
            f"{clip_inline_text(audit.get('prompt') or audit.get('reason') or '', 240)}"
        )

    verification_confidence = resume.get("verification_confidence") or {}
    if verification_confidence and verification_confidence.get("status") != "verified":
        lines.append(_format_verification_confidence_inline(verification_confidence))

    recurring = resume.get("recurring_failures") or []
    if recurring:
        item = recurring[-1]
        target = f" {item.get('target')}" if item.get("target") else ""
        lines.append(
            f"repeat: {item.get('tool')}{target} failed {item.get('count')}x "
            f"(same error: {clip_inline_text(item.get('error'), 180)}); "
            f"last_tool=#{item.get('last_tool_call_id')}"
        )

    decisions = resume.get("recent_decisions") or []
    if decisions:
        decision = decisions[-1]
        summary = clip_inline_text(decision.get("summary") or "", 300)
        tool_text = f" tool_call=#{decision.get('tool_call_id')}" if decision.get("tool_call_id") else ""
        lines.append(
            f"latest_decision: #{decision.get('model_turn_id')} "
            f"{decision.get('action') or 'unknown'}{tool_text} {summary}".rstrip()
        )
    compressed_prior = resume.get("compressed_prior_think") or {}
    if compressed_prior.get("items"):
        item = (compressed_prior.get("items") or [])[-1]
        summary = clip_inline_text(item.get("summary") or item.get("hypothesis") or "", 240)
        lines.append(
            f"prior_think: {compressed_prior.get('shown')}/{compressed_prior.get('total_older_model_turns')} "
            f"older turn(s); latest=#{item.get('model_turn_id')} {summary}".rstrip()
        )

    task_notes = _format_workbench_task_notes((task or {}).get("notes") or "")
    if task_notes:
        lines.append("task_notes:")
        lines.extend(f"  {line}" for line in task_notes.splitlines())

    task_id = resume.get("task_id") or (task or {}).get("id")
    if task_id:
        lines.append(
            f"resume: {mew_command('work', task_id, '--session', '--resume')} "
            f"(chat: /work-session resume {task_id})"
        )
    return lines


def _format_stale_working_memory_source_lines(memory):
    lines = []
    if not memory:
        return lines
    if memory.get("stale_after_model_turn_id"):
        latest = ""
        if memory.get("latest_model_turn_id"):
            latest = f"; latest=#{memory.get('latest_model_turn_id')}"
        lines.append(
            f"stale_after_model_turn: #{memory.get('stale_after_model_turn_id')}{latest}"
        )
    if memory.get("stale_after_tool_call_id"):
        stale_tool = memory.get("stale_after_tool") or "tool"
        lines.append(
            f"stale_after_tool_call: #{memory.get('stale_after_tool_call_id')} ({stale_tool} ran)"
        )
    return lines


def _format_workbench_task_notes(notes):
    if not notes:
        return ""
    lines = str(notes).splitlines()
    if not lines:
        return ""
    if len(lines) > 3:
        lines = ["[...older task notes omitted...]", *lines[-3:]]
    finish_indices = [index for index, line in enumerate(lines) if line.startswith("Work session finished:")]
    if len(finish_indices) <= 1:
        return clip_output("\n".join(lines), 800)

    omitted = len(finish_indices) - 1
    omitted_indices = set(finish_indices[:-1])
    compacted = []
    marker_inserted = False
    for index, line in enumerate(lines):
        if index in omitted_indices:
            if not marker_inserted:
                compacted.append(f"[...{omitted} older work-session finish notes omitted...]")
                marker_inserted = True
            continue
        compacted.append(line)
    content_lines = [line for line in compacted if not line.startswith("[...")]
    if content_lines and all(line.startswith("Work session finished:") for line in content_lines):
        return ""
    return clip_output("\n".join(compacted), 800)


def _format_workbench_description(description):
    text = str(description or "")
    if "Current coding focus:" not in text:
        return text
    lines = []
    skipping_coding_focus = False
    for line in text.splitlines():
        if line.strip() == "Current coding focus:":
            skipping_coding_focus = True
            continue
        if skipping_coding_focus and line.strip() == "Constraints:":
            skipping_coding_focus = False
        if skipping_coding_focus:
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def format_workbench(data):
    task = data["task"]
    lines = [
        f"Work task #{task.get('id')}: {task.get('title')}",
        format_task(task),
        f"kind: {data.get('kind')}",
        f"description: {_format_workbench_description(task.get('description') or '')}",
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
    if data.get("work_session_verifications"):
        for run in data["work_session_verifications"]:
            outcome = "passed" if run.get("exit_code") == 0 else "failed"
            if run.get("exit_code") is None:
                outcome = "unknown"
            label = run.get("label") or f"work#{run.get('tool_call_id')}"
            if not run.get("label") and str(run.get("tool") or "").endswith("_verification"):
                label += ".verify"
            lines.append(
                f"{label} [{outcome}] "
                f"{run.get('command') or ''}"
            )
    if not data.get("verification_runs") and not data.get("work_session_verifications"):
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
    if data.get("work_session_writes"):
        for run in data["work_session_writes"]:
            label = run.get("label") or f"work#{run.get('tool_call_id')}"
            verification = (
                f" verification_exit={run.get('verification_exit_code')}"
                if run.get("verification_exit_code") is not None
                else ""
            )
            approval = f" approval={run.get('approval_status')}" if run.get("approval_status") else ""
            lines.append(
                f"{label} [{run.get('operation') or 'write'}] "
                f"{run.get('path') or ''} changed={bool(run.get('changed'))} "
                f"written={bool(run.get('written'))} dry_run={bool(run.get('dry_run'))} "
                f"rolled_back={bool(run.get('rolled_back'))}{verification}{approval}"
            )
    if not data.get("write_runs") and not data.get("work_session_writes"):
        lines.append("(none)")

    lines.append("")
    lines.append("Work session")
    if data.get("work_session"):
        session = data["work_session"]
        tool_calls = session.get("tool_calls") or []
        model_turns = session.get("model_turns") or []
        resume = build_work_session_resume(session, task=task)
        last_tool = f" last_tool=#{session.get('last_tool_call_id')}" if session.get("last_tool_call_id") else ""
        lines.append(
            f"#{session.get('id')} [{session.get('status')}] "
            f"phase={(resume or {}).get('phase') or 'unknown'} "
            f"model_turns={len(model_turns)} tool_calls={len(tool_calls)}"
            f"{last_tool}"
        )
        reentry = _format_workbench_reentry(resume, task)
        if reentry:
            lines.append("Reentry")
            lines.extend(f"- {line}" if not line.startswith("  ") else line for line in reentry)
    else:
        lines.append("(none)")

    lines.append("")
    lines.append("Open questions")
    if data.get("open_questions"):
        for question in data["open_questions"]:
            context = format_question_context(question)
            lines.append(f"#{question.get('id')}{context} {question.get('text') or ''}")
    else:
        lines.append("(none)")

    lines.append("")
    lines.append("Next action")
    lines.append(data.get("next_action") or "")
    return "\n".join(lines)


def select_workbench_task(state, task_id=None, kind=None):
    task = find_task(state, task_id) if task_id else None
    if task or task_id:
        return task
    candidates = sorted(open_tasks(state), key=task_sort_key)
    candidates = filter_tasks_by_kind(candidates, kind=kind)
    running_tasks = [task for task in candidates if task.get("status") == "running"]
    if running_tasks:
        return running_tasks[0]
    active_task_id = state.get("agent_status", {}).get("active_task_id")
    task = find_task(state, active_task_id) if active_task_id else None
    if task and (not kind or task_kind(task) == kind):
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


def done_task_work_session_error(task):
    task_id = task.get("id")
    return (
        f"mew: task #{task_id} is done; reopen it before starting a work session with "
        f"`{mew_command('task', 'update', task_id, '--status', 'ready')}`"
    )


def format_work_ai_report(report, compact=False):
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
        if step.get("inline_approval"):
            line += f" inline_approval={step.get('inline_approval')}"
        if step.get("inline_approval_error"):
            line += f" approval_error={clip_inline_text(step.get('inline_approval_error') or '', 180)}"
        if step.get("inline_approval_tool_call_id"):
            line += f" approval_tool_call=#{step.get('inline_approval_tool_call_id')}"
        if step.get("inline_approval_status"):
            line += f" approval_status={step.get('inline_approval_status')}"
        lines.append(line)
        if tool_call:
            summary = _format_live_tool_summary(tool_call) if compact else compact_work_tool_summary(tool_call)
        else:
            summary = step.get("summary") or ""
        if summary:
            lines.append(clip_output(summary, 1000))
    stop_request = report.get("stop_request") or {}
    if stop_request:
        lines.append(f"stop_request: {stop_request.get('reason') or 'stop requested'}")
    if report.get("interrupted_step"):
        lines.append(f"interrupted_step: {report.get('interrupted_step')}")
    if report.get("interrupt_note"):
        lines.append(f"interrupt_note: {report.get('interrupt_note')}")
    if report.get("max_steps_note"):
        lines.append(f"max_steps_note: {report.get('max_steps_note')}")
    return "\n".join(lines)


def _format_live_output_preview(label, text, max_chars=500):
    text = clip_output(text or "", max_chars)
    if not text:
        return []
    lines = [f"{label}:"]
    lines.extend(f"  {line}" for line in text.splitlines())
    return lines


def _compact_live_path_text(text):
    text = str(text or "")
    cwd = str(Path.cwd())
    variants = [cwd]
    if cwd.startswith("/var/"):
        variants.append("/private" + cwd)
    elif cwd.startswith("/private/var/"):
        variants.append(cwd.removeprefix("/private"))
    for root in variants:
        if text == root:
            text = "."
        text = text.replace(root + os.sep, "")
        text = text.replace(root, ".")
    return text


def _format_live_match_preview(matches, max_items=5, max_chars=700):
    matches = [_compact_live_path_text(match) for match in (matches or []) if str(match).strip()]
    if not matches:
        return []
    text = clip_output("\n".join(matches[:max_items]), max_chars)
    lines = ["matches:"]
    lines.extend(f"  {line}" for line in text.splitlines())
    if len(matches) > max_items:
        lines.append(f"  ... {len(matches) - max_items} more match(es)")
    return lines


def _format_live_search_snippet_preview(snippets, max_items=3, max_chars=900):
    chunks = []
    for snippet in (snippets or [])[:max_items]:
        path = _compact_live_path_text(snippet.get("path") or "")
        header = f"{path}:{snippet.get('start_line')}-{snippet.get('end_line')}"
        lines = [header]
        for line in snippet.get("lines") or []:
            marker = ">" if line.get("match") else " "
            lines.append(f"{marker} {line.get('line')}: {line.get('text')}")
        chunks.append("\n".join(lines))
    if not chunks:
        return []
    text = clip_output("\n\n".join(chunks), max_chars)
    lines = ["snippets:"]
    lines.extend(f"  {line}" for line in text.splitlines())
    if len(snippets or []) > max_items:
        lines.append(f"  ... {len(snippets or []) - max_items} more snippet(s)")
    return lines


def _format_live_search_context_preview(snippets, max_chars=320):
    lines = _format_live_search_snippet_preview(snippets, max_items=1, max_chars=max_chars)
    if lines:
        lines[0] = "context:"
    return lines


def _format_live_tool_summary(call):
    result = call.get("result") or {}
    if result.get("command"):
        return "\n".join(
            [
                f"command: {result.get('command')}",
                f"cwd: {result.get('cwd')}",
                f"exit_code: {result.get('exit_code')}",
            ]
        )
    if call.get("tool") in WRITE_WORK_TOOLS:
        parameters = call.get("parameters") or {}
        path = _compact_live_path_text(result.get("path") or parameters.get("path") or "")
        stats = result.get("diff_stats") or {}
        stat_text = ""
        if isinstance(stats, dict) and ("added" in stats or "removed" in stats):
            stat_text = f" diff=+{stats.get('added', 0) or 0} -{stats.get('removed', 0) or 0}"
        return (
            f"{result.get('operation') or call.get('tool')} {path} "
            f"changed={result.get('changed')} dry_run={result.get('dry_run')} "
            f"written={result.get('written')}{stat_text}"
        ).strip()
    return _compact_live_path_text(compact_work_tool_summary(call))


def _format_live_tool_call_result(call):
    tool = call.get("tool") or "unknown"
    result = call.get("result") or {}
    parameters = call.get("parameters") or {}
    command = result.get("command") or parameters.get("command") or ""
    path = _compact_live_path_text(result.get("path") or parameters.get("path") or "")
    target = command or path
    exit_code = result.get("exit_code", result.get("verification_exit_code"))
    exit_text = "" if exit_code is None else f" exit={exit_code}"
    started_at = parse_time(call.get("started_at"))
    finished_at = parse_time(call.get("finished_at"))
    duration_text = ""
    if started_at and finished_at:
        duration_text = f" duration={max(0.0, (finished_at - started_at).total_seconds()):.1f}s"
    target_text = f" {target}" if target else ""
    lines = [f"tool #{call.get('id')} [{call.get('status')}] {tool}{exit_text}{duration_text}{target_text}"]
    if command:
        if result.get("cwd"):
            lines.append(f"cwd: {result.get('cwd')}")
    else:
        summary = _format_live_tool_summary(call)
        if summary:
            lines.append(f"summary: {clip_output(summary, 500)}")
    if result.get("stdout"):
        lines.extend(_format_live_output_preview("stdout", result.get("stdout")))
    if result.get("stderr"):
        lines.extend(_format_live_output_preview("stderr", result.get("stderr")))
    if call.get("tool") == "search_text":
        match_preview = _format_live_match_preview(result.get("matches") or [])
        if match_preview:
            lines.extend(match_preview)
            lines.extend(_format_live_search_context_preview(result.get("snippets") or []))
        else:
            lines.extend(_format_live_search_snippet_preview(result.get("snippets") or []))
    if result.get("diff"):
        lines.append(
            format_diff_preview(
                result.get("diff") or "",
                max_chars=800,
                diff_stats=result.get("diff_stats"),
            )
        )
    if call.get("tool") in WRITE_WORK_TOOLS and result.get("dry_run") and result.get("changed") and not call.get("approval_status"):
        lines.append("pending_approval: yes")
    return lines


def _append_live_section(lines, title, items):
    items = [item for item in (items or []) if str(item).strip()]
    if not items:
        return
    lines.append(f"{title}:")
    for item in items:
        lines.extend(f"  {line}" for line in str(item).splitlines())


def _format_verification_coverage_warning_inline(warning):
    if not warning:
        return ""
    command = clip_inline_text(warning.get("command") or "latest verifier", 120)
    source = clip_inline_text(warning.get("source_path") or "edited source", 120)
    expected = clip_inline_text(
        warning.get("expected_command") or warning.get("expected_test_path") or "",
        180,
    )
    text = f"verification_warning: {command} did not cover {source}"
    if expected:
        text += f"; expected {expected}"
    return clip_inline_text(text, 360)


def _format_verification_confidence_inline(confidence):
    if not confidence:
        return ""
    status = confidence.get("status") or "unknown"
    level = confidence.get("confidence") or "unknown"
    reason = clip_inline_text(confidence.get("reason") or "", 180)
    expected = clip_inline_text(confidence.get("expected_command") or "", 160)
    text = f"verification_confidence: {level} status={status}"
    if reason:
        text += f"; {reason}"
    if expected and status != "verified":
        text += f"; expected {expected}"
    return clip_inline_text(text, 420)


def format_work_live_step_result(step, resume=None):
    action = step.get("action") or {}
    status = step.get("status") or "unknown"
    tool_calls = list(step.get("tool_calls") or [])
    if step.get("tool_call"):
        tool_calls.append(step.get("tool_call"))
    outcome_lines = [
        f"status: {status}",
        f"action: {action.get('type') or action.get('tool') or 'unknown'}",
    ]
    summary = step.get("summary") or step.get("error") or action.get("reason") or action.get("summary") or ""
    tool_summaries = set()
    for call in tool_calls:
        call = call or {}
        tool_summaries.add(str(call.get("summary") or "").strip())
        tool_summaries.add(str(_format_live_tool_summary(call) or "").strip())
    if summary and str(summary).strip() not in tool_summaries:
        outcome_lines.append(f"summary: {clip_output(summary, 700)}")
    for item in (resume or {}).get("recurring_failures") or []:
        target = f" {item.get('target')}" if item.get("target") else ""
        outcome_lines.append(
            f"repeat: {item.get('tool')}{target} failed {item.get('count')}x "
            f"(same error: {clip_inline_text(item.get('error'), 180)}); "
            f"last_tool=#{item.get('last_tool_call_id')}"
        )
    for item in (resume or {}).get("low_yield_observations") or []:
        target = f" {item.get('path')}" if item.get("path") else ""
        outcome_lines.append(
            f"low_yield: {item.get('tool')}{target} returned zero matches {item.get('count')}x; "
            f"last_tool=#{item.get('last_tool_call_id')}"
        )
        if item.get("suggested_next"):
            outcome_lines.append(f"low_yield_next: {clip_inline_text(item.get('suggested_next'), 220)}")
    lines = []
    _append_live_section(lines, "outcome", outcome_lines)
    tool_lines = []
    for call in tool_calls:
        tool_lines.extend(_format_live_tool_call_result(call or {}))
    _append_live_section(lines, "tools", tool_lines)
    if resume:
        context = resume.get("context") or {}
        session_lines = [f"phase: {resume.get('phase') or 'unknown'}"]
        if context:
            session_lines.append(
                f"context: pressure={context.get('pressure')} "
                f"tool_calls={context.get('tool_calls')} model_turns={context.get('model_turns')}"
            )
        if resume.get("pending_approvals"):
            ids = ", ".join(f"#{item.get('tool_call_id')}" for item in resume.get("pending_approvals") or [])
            session_lines.append(f"pending_approvals: {ids}")
        pending_steer = resume.get("pending_steer") or {}
        if pending_steer.get("text"):
            session_lines.append(f"pending_steer: {clip_inline_text(pending_steer.get('text'), 280)}")
        queued_followups = resume.get("queued_followups") or []
        if queued_followups:
            session_lines.append(
                f"queued_followups: {len(queued_followups)} "
                f"next={clip_inline_text(queued_followups[0].get('text'), 220)}"
            )
        coverage_warning = resume.get("verification_coverage_warning") or {}
        if coverage_warning:
            session_lines.append(_format_verification_coverage_warning_inline(coverage_warning))
        verification_confidence = resume.get("verification_confidence") or {}
        if verification_confidence and verification_confidence.get("status") != "verified":
            session_lines.append(_format_verification_confidence_inline(verification_confidence))
        memory = resume.get("working_memory") or {}
        if memory:
            stale_memory = bool(memory.get("stale_after_model_turn_id") or memory.get("stale_after_tool_call_id"))
            if stale_memory:
                session_lines.append("memory: stale; refresh before relying on next_step")
                session_lines.extend(_format_stale_working_memory_source_lines(memory))
            if memory.get("hypothesis") and not stale_memory:
                session_lines.append(f"memory_hypothesis: {clip_inline_text(memory.get('hypothesis'), 280)}")
            if memory.get("next_step"):
                key = "stale_memory_next" if stale_memory else "memory_next"
                session_lines.append(f"{key}: {clip_inline_text(memory.get('next_step'), 280)}")
            if memory.get("last_verified_state") and not stale_memory:
                session_lines.append(f"memory_verified: {clip_inline_text(memory.get('last_verified_state'), 280)}")
        if resume.get("next_action"):
            session_lines.append(f"next: {resume.get('next_action')}")
        _append_live_section(lines, "session", session_lines)
    return "\n".join(lines)


def _planning_value_text(value):
    if value is None or value == "":
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def format_work_planning(planned, include_stream_preview=True):
    decision_plan = (planned or {}).get("decision_plan") or {}
    action_plan = (planned or {}).get("action_plan") or {}
    action = (planned or {}).get("action") or {}
    lines = []
    summary = decision_plan.get("summary") or action_plan.get("summary") or action.get("summary") or action.get("reason")
    if summary:
        lines.append(f"summary: {clip_output(str(summary), 500)}")
    action_type = action.get("type") or action.get("tool")
    if action_type:
        lines.append(f"planned_action: {action_type}")
    model_stream = (planned or {}).get("model_stream") or {}
    for phase in model_stream.get("phases") or []:
        lines.append(
            f"model_stream: {phase.get('phase')} chunks={phase.get('chunks')} chars={phase.get('chars')}"
        )
        if include_stream_preview and phase.get("preview"):
            lines.append(f"stream_preview: {phase.get('preview')}")
    reason = action.get("reason") or (action_plan.get("action") or {}).get("reason")
    if reason and reason != summary:
        lines.append(f"reason: {clip_output(str(reason), 500)}")
    for key in ("observations", "risks", "plan", "next_steps"):
        text = _planning_value_text(decision_plan.get(key))
        if text:
            lines.append(f"{key}: {clip_output(text, 500)}")
    return "\n".join(lines) or "(no planning summary)"


def format_work_follow_planning(planned):
    action = (planned or {}).get("action") or {}
    decision_plan = (planned or {}).get("decision_plan") or {}
    action_plan = (planned or {}).get("action_plan") or {}
    action_type = action.get("type") or action.get("tool") or "unknown"
    summary = decision_plan.get("summary") or action_plan.get("summary") or action.get("summary") or action.get("reason")
    lines = [f"plan: {action_type}"]
    if summary:
        lines[0] = f"{lines[0]} - {clip_inline_text(summary, 280)}"
    model_stream = (planned or {}).get("model_stream") or {}
    for phase in model_stream.get("phases") or []:
        lines.append(
            f"model_stream: {phase.get('phase')} chunks={phase.get('chunks')} chars={phase.get('chars')}"
        )
    return "\n".join(lines)


def format_work_live_progress(index, max_steps, session_id, task_id, phase="thinking", elapsed_seconds=None):
    text = f"progress: step={index}/{max_steps} session=#{session_id} task=#{task_id}"
    if phase:
        text += f" phase={phase}"
    if elapsed_seconds is not None:
        text += f" elapsed={elapsed_seconds:.1f}s"
    return text


def format_work_live_model_delta(phase, text):
    return f"model_delta: {phase} {clip_output(text, 500)}"


def _extract_json_string_field_prefix(text, field):
    marker = f'"{field}"'
    start = text.find(marker)
    if start < 0:
        return ""
    colon = text.find(":", start + len(marker))
    if colon < 0:
        return ""
    quote = text.find('"', colon + 1)
    if quote < 0:
        return ""

    chars = []
    escaped = False
    for char in text[quote + 1 :]:
        if escaped:
            if char == "n":
                chars.append("\n")
            elif char == "t":
                chars.append("\t")
            elif char in ('"', "\\", "/"):
                chars.append(char)
            else:
                chars.append(char)
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == '"':
            break
        chars.append(char)
    return "".join(chars)


def _compact_live_model_delta_lines(phase, total_text, rendered_lengths):
    lines = []
    for field, label in (("summary", "summary_delta"), ("reason", "reason_delta")):
        value = _extract_json_string_field_prefix(total_text, field)
        previous = rendered_lengths.get((phase, field), 0)
        if len(value) <= previous:
            continue
        delta = " ".join(value[previous:].split())
        rendered_lengths[(phase, field)] = len(value)
        if delta:
            lines.append(f"{label}: {phase} {clip_output(delta, 500)}")

    action_type = _extract_json_string_field_prefix(total_text, "type")
    if action_type and not rendered_lengths.get((phase, "action_type")):
        rendered_lengths[(phase, "action_type")] = len(action_type)
        lines.append(f"action_delta: {phase} {clip_output(action_type, 120)}")
    return lines


def _work_control_options(args, session=None):
    defaults = (session or {}).get("default_options") or {}

    def option(name, fallback=None):
        value = defaults.get(name)
        if value not in (None, "", [], False):
            return value
        return getattr(args, name, fallback)

    options = {
        "auth": option("auth"),
        "model_backend": option("model_backend"),
        "model": option("model"),
        "base_url": option("base_url"),
        "allow_read": list(option("allow_read", []) or []),
        "allow_write": list(option("allow_write", []) or []),
        "allow_shell": bool(option("allow_shell", False)),
        "allow_verify": bool(option("allow_verify", False)),
        "verify_command": option("verify_command", ""),
        "approval_mode": option("approval_mode", ""),
        "act_mode": option("act_mode"),
        "compact_live": bool(option("compact_live", False)),
        "prompt_approval": bool(option("prompt_approval", False)),
        "no_prompt_approval": bool(option("no_prompt_approval", False)),
        "quiet": bool(option("quiet", False)),
    }
    options["allow_write"] = safe_work_write_roots(options.get("allow_write") or [])
    return options


def _work_effective_args(args, options):
    effective = SimpleNamespace(**vars(args))
    for key, value in (options or {}).items():
        setattr(effective, key, value)
    return effective


def safe_work_write_roots(roots):
    safe = []
    for root in roots or []:
        path = Path(root).expanduser()
        if not path.is_absolute():
            path = Path.cwd() / path
        if is_sensitive_path(path):
            continue
        if root not in safe:
            safe.append(root)
    return safe


def _work_args_have_tool_gates(args):
    return bool(
        getattr(args, "allow_read", None)
        or getattr(args, "allow_write", None)
        or getattr(args, "allow_shell", False)
        or getattr(args, "allow_verify", False)
        or getattr(args, "verify_command", "")
    )


def _work_tool_gate_options(args, session=None):
    defaults = (session or {}).get("default_options") or {}
    verify_disabled = bool(defaults.get("verify_disabled"))

    def merged_list(name):
        default_items = list(defaults.get(name) or [])
        if name == "allow_write":
            default_items = safe_work_write_roots(default_items)
        merged = []
        for item in default_items + list(getattr(args, name, None) or []):
            if item and item not in merged:
                merged.append(item)
        return merged

    def explicit_or_default(name, fallback=None):
        value = getattr(args, name, fallback)
        if value not in (None, "", [], False):
            return value
        return defaults.get(name, fallback)

    options = {
        "allow_read": merged_list("allow_read"),
        "allow_write": merged_list("allow_write"),
        "allow_shell": bool(defaults.get("allow_shell") or getattr(args, "allow_shell", False)),
        "allow_verify": bool((not verify_disabled and defaults.get("allow_verify")) or getattr(args, "allow_verify", False)),
        "verify_command": explicit_or_default("verify_command", ""),
    }
    if verify_disabled and not getattr(args, "verify_command", ""):
        options["verify_command"] = ""
    return options


def remember_work_session_default_options(session, args):
    if not session:
        return
    options = _work_control_options(args, session=None)
    clear_write_defaults = bool(getattr(args, "read_only", False))
    clear_verify_defaults = bool(getattr(args, "no_verify", False))
    has_meaningful_defaults = any(
        (
            options.get("allow_read"),
            options.get("allow_write"),
            options.get("allow_shell"),
            options.get("allow_verify"),
            options.get("verify_command"),
            options.get("approval_mode"),
            options.get("model"),
            options.get("base_url"),
            options.get("act_mode") and options.get("act_mode") != "model",
            options.get("compact_live"),
            options.get("quiet"),
            options.get("prompt_approval"),
            options.get("no_prompt_approval"),
            clear_write_defaults,
            clear_verify_defaults,
        )
    )
    if not has_meaningful_defaults:
        return
    current = session.get("default_options") or {}

    def merged_list(name):
        merged = []
        for item in list(current.get(name) or []) + list(options.get(name) or []):
            if item and item not in merged:
                merged.append(item)
        if name == "allow_write":
            return safe_work_write_roots(merged)
        return merged

    def merged_scalar(name):
        value = options.get(name)
        if value not in (None, "", [], False):
            parser_defaults = {"auth": "auth.json", "model_backend": "codex", "act_mode": "model"}
            if current.get(name) and value == parser_defaults.get(name):
                return current.get(name) or ""
            return value
        return current.get(name) or ""

    no_prompt_approval = bool(current.get("no_prompt_approval") or options.get("no_prompt_approval"))
    prompt_approval = bool(current.get("prompt_approval") or options.get("prompt_approval"))
    if no_prompt_approval:
        prompt_approval = False
    verify_disabled = bool(current.get("verify_disabled"))
    if clear_verify_defaults:
        verify_disabled = True
    elif options.get("allow_verify") or options.get("verify_command"):
        verify_disabled = False

    session["default_options"] = {
        "auth": merged_scalar("auth"),
        "model_backend": merged_scalar("model_backend"),
        "model": merged_scalar("model"),
        "base_url": merged_scalar("base_url"),
        "allow_read": merged_list("allow_read"),
        "allow_write": [] if clear_write_defaults else merged_list("allow_write"),
        "allow_shell": False if clear_write_defaults else bool(current.get("allow_shell") or options.get("allow_shell")),
        "allow_verify": False if clear_verify_defaults else bool(current.get("allow_verify") or options.get("allow_verify")),
        "verify_command": "" if clear_verify_defaults else merged_scalar("verify_command"),
        "verify_disabled": verify_disabled,
        "approval_mode": merged_scalar("approval_mode"),
        "act_mode": merged_scalar("act_mode"),
        "compact_live": bool(current.get("compact_live") or options.get("compact_live")),
        "quiet": bool(current.get("quiet") or options.get("quiet")),
        "prompt_approval": prompt_approval,
        "no_prompt_approval": no_prompt_approval,
    }


def _pytest_invocation_args(command):
    try:
        argv = shlex.split(command or "")
    except ValueError:
        return []
    for index, arg in enumerate(argv):
        name = Path(arg).name
        if name in ("pytest", "py.test"):
            return argv[index + 1 :]
        if arg == "-m" and index + 1 < len(argv) and argv[index + 1] == "pytest":
            previous = Path(argv[index - 1]).name if index > 0 else ""
            if previous.startswith("python"):
                return argv[index + 2 :]
    return []


def _pytest_positional_selectors(args):
    selectors = []
    value_flags = {
        "-c",
        "-k",
        "-m",
        "-o",
        "--basetemp",
        "--confcutdir",
        "--ignore",
        "--ignore-glob",
        "--import-mode",
        "--junit-prefix",
        "--junit-xml",
        "--log-cli-format",
        "--log-cli-level",
        "--log-file",
        "--log-file-format",
        "--log-file-level",
        "--maxfail",
        "--rootdir",
        "--tb",
    }
    skip_next = False
    for arg in args or []:
        if skip_next:
            skip_next = False
            continue
        if arg in value_flags:
            skip_next = True
            continue
        if arg.startswith("-"):
            continue
        selectors.append(arg)
    return selectors


def _is_narrow_pytest_verify_command(command, existing_command=""):
    args = _pytest_invocation_args(command)
    if not args:
        return False
    selection_flags = {"-k", "-m", "--deselect", "--lf", "--ff", "--failed-first", "--last-failed"}
    for arg in args:
        if arg in selection_flags or arg.startswith(("-k=", "-m=", "--deselect=", "--keyword=")):
            return True
    selectors = _pytest_positional_selectors(args)
    if any("::" in selector for selector in selectors):
        return True
    existing_selectors = _pytest_positional_selectors(_pytest_invocation_args(existing_command))
    return bool(existing_command and selectors and not existing_selectors)


def remember_successful_work_verification(session, tool, result):
    if not session or not isinstance(result, dict):
        return
    command = ""
    if tool == "run_tests" and result.get("exit_code") == 0:
        command = result.get("command") or ""
    verification = result.get("verification") or {}
    if verification.get("exit_code") == 0:
        command = verification.get("command") or command
    if not command:
        return
    defaults = session.setdefault("default_options", {})
    if _is_narrow_pytest_verify_command(command, defaults.get("verify_command")):
        if tool == "run_tests":
            result["narrow_verify_command"] = True
        elif verification:
            verification["narrow_verify_command"] = True
        defaults["allow_verify"] = True
        defaults["verify_disabled"] = False
        return
    defaults["allow_verify"] = True
    defaults["verify_command"] = command
    defaults["verify_disabled"] = False


def work_session_default_verify_command(session, task=None):
    defaults = (session or {}).get("default_options") or {}
    if defaults.get("verify_disabled"):
        return ""
    return defaults.get("verify_command") or latest_work_verify_command(
        (session or {}).get("tool_calls") or [],
        task=task,
    )


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
    if options.get("approval_mode"):
        parts.extend(["--approval-mode", options["approval_mode"]])
    if options.get("act_mode"):
        parts.extend(["--act-mode", options["act_mode"]])
    if options.get("compact_live"):
        parts.append("--compact-live")
    if options.get("quiet"):
        parts.append("--quiet")
    if options.get("no_prompt_approval"):
        parts.append("--no-prompt-approval")
    elif options.get("prompt_approval"):
        parts.append("--prompt-approval")
    return shlex.join(parts)


def _work_live_continue_command(args, task_id, session=None, max_steps=1, follow=False):
    parts = [mew_executable(), "work"]
    if task_id is not None:
        parts.append(str(task_id))
    parts.append("--follow" if follow else "--live")
    option_session = None if getattr(args, "live", False) and _work_args_have_tool_gates(args) else session
    options = _work_control_options(args, session=option_session)
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
    if options.get("approval_mode"):
        parts.extend(["--approval-mode", options["approval_mode"]])
    if options.get("act_mode"):
        parts.extend(["--act-mode", options["act_mode"]])
    if options.get("compact_live"):
        parts.append("--compact-live")
    if options.get("quiet"):
        parts.append("--quiet")
    if options.get("no_prompt_approval"):
        parts.append("--no-prompt-approval")
    elif options.get("prompt_approval"):
        parts.append("--prompt-approval")
    parts.extend(["--max-steps", str(max_steps)])
    return shlex.join(parts)


def _work_resume_command(args, task_id, session=None):
    parts = [mew_executable(), "work"]
    if task_id is not None:
        parts.append(str(task_id))
    parts.extend(["--session", "--resume"])
    options = _work_control_options(args, session=session)
    for root in options.get("allow_read") or ["."]:
        parts.extend(["--allow-read", root])
    return shlex.join(parts)


def _work_cli_verify_suffix(session):
    verify_command = work_session_default_verify_command(session)
    if verify_command:
        return shlex.join(["--allow-verify", "--verify-command", verify_command])
    return "--allow-verify --verify-command <cmd>"


def _work_cli_approve_command(session, tool_call_id, path):
    task_id = (session or {}).get("task_id")
    parts = [mew_executable(), "work"]
    if task_id is not None:
        parts.append(str(task_id))
    parts.extend(["--approve-tool", str(tool_call_id), "--allow-write", path or "."])
    return f"{shlex.join(parts)} {_work_cli_verify_suffix(session)}"


def _work_cli_defer_verify_approve_command(session, tool_call_id, path):
    task_id = (session or {}).get("task_id")
    parts = [mew_executable(), "work"]
    if task_id is not None:
        parts.append(str(task_id))
    parts.extend(
        [
            "--approve-tool",
            str(tool_call_id),
            "--allow-write",
            path or ".",
            "--defer-verify",
        ]
    )
    return shlex.join(parts)


def _work_cli_override_approve_command(session, tool_call_id, path):
    return f"{_work_cli_approve_command(session, tool_call_id, path)} --allow-unpaired-source-edit"


def _work_cli_reject_command(session, tool_call_id):
    task_id = (session or {}).get("task_id")
    parts = [mew_executable(), "work"]
    if task_id is not None:
        parts.append(str(task_id))
    parts.extend(["--reject-tool", str(tool_call_id), "--reject-reason"])
    return f"{shlex.join(parts)} <feedback>"


def _work_cli_approve_all_command(session, approvals):
    task_id = (session or {}).get("task_id")
    parts = [mew_executable(), "work"]
    if task_id is not None:
        parts.append(str(task_id))
    parts.append("--approve-all")
    paths = []
    for approval in approvals or []:
        path = approval.get("path") or "."
        if path not in paths:
            paths.append(path)
    for path in paths:
        parts.extend(["--allow-write", path])
    return f"{shlex.join(parts)} {_work_cli_verify_suffix(session)}"


def _work_cli_override_approve_all_command(session, approvals):
    return f"{_work_cli_approve_all_command(session, approvals)} --allow-unpaired-source-edit"


def _work_cli_approval_items(session, resume):
    if not session or session.get("status") != "active":
        return []
    approvals = (resume or {}).get("pending_approvals") or []
    items = []
    if (resume or {}).get("approve_all_hint") or (resume or {}).get("approve_all_blocked_reason"):
        if (resume or {}).get("approve_all_blocked_reason"):
            items.append(
                {
                    "label": "add paired tests before approve all",
                    "command": _work_resume_command(args=None, task_id=session.get("task_id"), session=session),
                }
            )
            items.append(
                {
                    "label": "override unpaired approve all",
                    "command": (resume or {}).get("cli_override_approve_all_hint")
                    or _work_cli_override_approve_all_command(session, approvals),
                }
            )
        else:
            items.append(
                {
                    "label": "approve all pending writes",
                    "command": (resume or {}).get("cli_approve_all_hint") or _work_cli_approve_all_command(session, approvals),
                }
            )
    for approval in approvals:
        tool_call_id = approval.get("tool_call_id")
        approval_status = approval.get("approval_status") or ""
        pairing = approval.get("pairing_status") or {}
        if pairing.get("status") == "missing_test_edit":
            items.append(
                {
                    "label": f"add paired test before approving #{tool_call_id}",
                    "command": _work_resume_command(args=None, task_id=session.get("task_id"), session=session),
                }
            )
            items.append(
                {
                    "label": f"override unpaired approval #{tool_call_id}",
                    "command": _work_cli_override_approve_command(session, tool_call_id, approval.get("path") or "."),
                }
            )
            items.append(
                {
                    "label": f"reject tool #{tool_call_id}",
                    "command": _work_cli_reject_command(session, tool_call_id),
                }
            )
            continue
        approve_label = (
            f"retry failed approval #{tool_call_id}"
            if approval_status == "failed"
            else f"approve tool #{tool_call_id}"
        )
        if approval.get("auto_defer_verify_reason"):
            approve_label = f"approve tool #{tool_call_id} and wait for paired source"
        items.append(
            {
                "label": approve_label,
                "command": approval.get("cli_approve_hint")
                or _work_cli_approve_command(session, tool_call_id, approval.get("path") or "."),
            }
        )
        if not approval.get("auto_defer_verify_reason"):
            items.append(
                {
                    "label": f"apply tool #{tool_call_id} and defer verification",
                    "command": _work_cli_defer_verify_approve_command(session, tool_call_id, approval.get("path") or "."),
                }
            )
        items.append(
            {
                "label": f"reject tool #{tool_call_id}",
                "command": _work_cli_reject_command(session, tool_call_id),
            }
        )
    return items


def work_cli_control_items(session, args, task=None):
    if not session:
        return [{"label": "start a work session", "command": f"{mew_executable()} work <task-id> --start-session"}]
    task_id = session.get("task_id")
    if session.get("status") != "active":
        resume = build_work_session_resume(session)
        verification_confidence = resume.get("verification_confidence") or {}
        has_unresolved_state = bool(
            resume.get("pending_approvals")
            or resume.get("unresolved_failure")
            or resume.get("failures")
            or (verification_confidence and not verification_confidence.get("finish_ready"))
        )
        controls = [
            {"label": "review closed session", "command": _work_resume_command(args, task_id, session=session)},
        ]
        if task and task.get("status") == "done":
            controls.append(
                {
                    "label": "reopen task",
                    "command": mew_command("task", "update", task_id, "--status", "ready"),
                }
            )
        else:
            if task_id is not None and not has_unresolved_state:
                controls.append(
                    {
                        "label": "mark task done",
                        "command": mew_command("task", "update", task_id, "--status", "done"),
                    }
                )
            controls.append({"label": "start a new session", "command": mew_command("work", task_id, "--start-session")})
        return controls
    controls = []
    resume = build_work_session_resume(session)
    approval_items = _work_cli_approval_items(session, resume)
    if session.get("stop_requested_at"):
        if session.get("stop_action") == "interrupt_submit" and not work_session_has_running_activity(session):
            return approval_items + [
                {
                    "label": "submit pending interrupt",
                    "command": _work_live_continue_command(args, task_id, session=session),
                },
                {
                    "label": "short live burst after interrupt",
                    "command": _work_live_continue_command(args, task_id, session=session, max_steps=3),
                },
                {"label": "interrupt snapshot", "command": _work_resume_command(args, task_id, session=session)},
                {"label": "open chat", "command": mew_command("chat")},
            ]
        return approval_items + [
            {"label": "stop requested snapshot", "command": _work_resume_command(args, task_id, session=session)},
            {"label": "open chat", "command": mew_command("chat")},
        ]
    controls.extend(approval_items)
    recovery_items = ((resume or {}).get("recovery_plan") or {}).get("items") or []
    if any(item.get("action") == "retry_tool" for item in recovery_items):
        task_part = f" {task_id}" if task_id is not None else ""
        controls.append(
            {
                "label": "auto-recover safe read",
                "command": f"{mew_executable()} work{task_part} --session --resume --allow-read . --auto-recover-safe",
            }
        )
    if any(item.get("action") == "retry_dry_run_write" for item in recovery_items):
        task_part = f" {task_id}" if task_id is not None else ""
        controls.append(
            {
                "label": "auto-recover dry-run preview",
                "command": f"{mew_executable()} work{task_part} --session --resume --allow-write . --auto-recover-safe",
            }
        )
    steer_parts = ["work"]
    if task_id is not None:
        steer_parts.append(task_id)
    steer_parts.append("--steer")
    followup_parts = ["work"]
    if task_id is not None:
        followup_parts.append(task_id)
    followup_parts.append("--queue-followup")
    interrupt_parts = ["work"]
    if task_id is not None:
        interrupt_parts.append(task_id)
    interrupt_parts.append("--interrupt-submit")
    controls.extend(
        [
            {"label": "one live step", "command": _work_live_continue_command(args, task_id, session=session)},
            {
                "label": "short live burst",
                "command": _work_live_continue_command(args, task_id, session=session, max_steps=3),
            },
            {
                "label": "follow loop",
                "command": _work_live_continue_command(args, task_id, session=session, max_steps=10, follow=True),
            },
            {
                "label": "steer next step",
                "command": f"{mew_command(*steer_parts)} <guidance>",
            },
            {
                "label": "queue follow-up",
                "command": f"{mew_command(*followup_parts)} <message>",
            },
            {
                "label": "interrupt and submit",
                "command": f"{mew_command(*interrupt_parts)} <message>",
            },
            {
                "label": "pause at boundary",
                "command": mew_command("work", task_id, "--stop-session", "--stop-reason", "pause"),
            },
            {"label": "resume snapshot", "command": _work_resume_command(args, task_id, session=session)},
            {"label": "open chat", "command": mew_command("chat")},
        ]
    )
    return controls


def work_cli_control_commands(session, args, task=None):
    return [item["command"] for item in work_cli_control_items(session, args, task=task)]


def compact_work_cli_control_items(items):
    keep_labels = {
        "start a work session",
        "review closed session",
        "mark task done",
        "reopen task",
        "start a new session",
        "submit pending interrupt",
        "interrupt snapshot",
        "stop requested snapshot",
        "one live step",
        "follow loop",
        "steer next step",
        "queue follow-up",
        "resume snapshot",
        "open chat",
    }
    keep_prefixes = (
        "add paired test",
        "add paired tests",
        "approve",
        "apply tool",
        "auto-recover",
        "override unpaired",
        "reject",
        "retry failed approval",
    )
    compact = []
    for item in items or []:
        label = item.get("label") or ""
        if label in keep_labels or label.startswith(keep_prefixes):
            compact.append(item)
    return compact or list(items or [])[:6]


def format_work_cli_controls(session, args, task=None, compact=False):
    lines = ["", "Next CLI controls"]
    items = work_cli_control_items(session, args, task=task)
    if compact:
        items = compact_work_cli_control_items(items)
    for item in items:
        label = item.get("label") or "run"
        lines.append(f"{label}: {item.get('command')}")
    return "\n".join(lines)


def _work_task_command(task_id, *parts):
    args = ["work"]
    if task_id is not None:
        args.append(task_id)
    args.extend(parts)
    return mew_command(*args)


def work_recovery_suggestion_from_plan(recovery_plan, task_id=None):
    items = (recovery_plan or {}).get("items") or []
    if not items:
        return {}
    item = select_work_recovery_plan_item(recovery_plan)
    source_index = next((index for index, candidate in enumerate(items) if candidate is item), None)
    action = item.get("action") or "review"
    if action == "retry_tool":
        kind = "retry_read"
        command = item.get("auto_hint") or item.get("hint") or _work_task_command(
            task_id,
            "--session",
            "--resume",
            "--allow-read",
            ".",
            "--auto-recover-safe",
        )
    elif action == "needs_user_review":
        kind = "needs_human_review"
        command = item.get("review_hint") or _work_task_command(task_id, "--session", "--resume", "--allow-read", ".")
    elif action == "retry_verification":
        kind = "retry_verification"
        command = item.get("hint") or _work_task_command(
            task_id,
            "--recover-session",
            "--allow-read",
            ".",
            "--allow-verify",
            "--verify-command",
            item.get("command") or "<command>",
        )
    elif action == "retry_dry_run_write":
        kind = "retry_dry_run_write"
        command = item.get("auto_hint") or item.get("hint") or _work_task_command(
            task_id,
            "--session",
            "--resume",
            "--allow-write",
            ".",
            "--auto-recover-safe",
        )
    elif action == "retry_apply_write":
        kind = "retry_apply_write"
        command = item.get("hint") or _work_task_command(task_id, "--recover-session", "--allow-write", ".")
    elif action == "verify_completed_write":
        kind = "verify_completed_write"
        command = item.get("hint") or _work_task_command(
            task_id,
            "--recover-session",
            "--allow-read",
            ".",
            "--allow-verify",
            "--verify-command",
            item.get("command") or "<command>",
        )
    elif action == "replan":
        kind = "replannable"
        command = item.get("hint") or _work_task_command(task_id, "--live", "--allow-read", ".")
    else:
        kind = action
        command = item.get("hint") or item.get("review_hint") or _work_task_command(task_id, "--session", "--resume")
    return {
        "kind": kind,
        "command": command,
        "reason": (recovery_plan or {}).get("next_action") or item.get("reason") or "",
        "source_action": action,
        "source_index": source_index,
        "source_kind": item.get("kind") or "",
        "effect_classification": item.get("effect_classification") or "",
        "tool_call_id": item.get("tool_call_id"),
        "model_turn_id": item.get("model_turn_id"),
    }


def work_cockpit_recovery_command(resume, task_id=None):
    recovery_plan = (resume or {}).get("recovery_plan") or {}
    suggestion = work_recovery_suggestion_from_plan(recovery_plan, task_id=task_id)
    if not suggestion:
        return ""
    items = list(recovery_plan.get("items") or [])
    source_action = suggestion.get("source_action")
    source_index = suggestion.get("source_index")
    item = {}
    if isinstance(source_index, int) and 0 <= source_index < len(items):
        item = items[source_index]
    if item.get("action") == source_action and item.get("chat_auto_hint"):
        return item.get("chat_auto_hint")
    return suggestion.get("command") or ""


def write_work_follow_snapshot(args, report, session, task, resume, step=None, force=False, mode=None):
    if not force and not getattr(args, "live", False):
        return None
    ensure_state_dir()
    follow_dir = STATE_DIR / "follow"
    follow_dir.mkdir(parents=True, exist_ok=True)
    session_id = (session or {}).get("id")
    task_id = (session or {}).get("task_id")
    generated_at = now_iso()
    reply_path = STATE_DIR / "follow" / "reply.json"
    reply_schema = build_work_reply_schema(session, resume=resume)
    checkpoint = compact_context_checkpoint(latest_context_checkpoint())
    payload = {
        "schema_version": 1,
        "generated_at": generated_at,
        "heartbeat_at": generated_at,
        "producer": {"pid": os.getpid()},
        "session_id": session_id,
        "session_updated_at": (session or {}).get("updated_at"),
        "task_id": task_id,
        "title": (session or {}).get("title") or (task or {}).get("title") or "",
        "mode": mode or ("follow" if getattr(args, "follow", False) else "live"),
        "stop_reason": (report or {}).get("stop_reason"),
        "max_steps": (report or {}).get("max_steps"),
        "step_count": len((report or {}).get("steps") or []),
        "last_step": step or (((report or {}).get("steps") or [None])[-1]),
        "resume": resume or {},
        "continuity": (resume or {}).get("continuity") or {},
        "pending_approvals": (resume or {}).get("pending_approvals") or [],
        "latest_context_checkpoint": checkpoint,
        "current_git": current_git_reentry_state(),
        "suggested_recovery": work_recovery_suggestion_from_plan(
            (resume or {}).get("recovery_plan") or {},
            task_id=task_id,
        ),
        "cells": build_work_session_cells(session, limit=30) if session else [],
        "controls": work_cli_control_items(session, args, task=task) if session else [],
        "reply_command": _work_reply_file_command(task_id, reply_path),
        "supported_actions": reply_schema["supported_actions"],
        "reply_template": reply_schema["reply_template"],
    }
    latest_path = follow_dir / "latest.json"
    targets = [latest_path]
    if session_id is not None:
        targets.append(follow_dir / f"session-{session_id}.json")
    encoded = json.dumps(payload, ensure_ascii=False, indent=2)
    for path in targets:
        tmp = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.{time.monotonic_ns()}.tmp")
        tmp.write_text(encoded + "\n", encoding="utf-8")
        os.replace(tmp, path)
    return latest_path


def refresh_work_follow_snapshot(args, report, session_id, task_id=None):
    if not getattr(args, "live", False):
        return None
    with state_lock():
        state = load_state()
        session = find_work_session(state, session_id)
        task = work_session_task(state, session) or find_task(state, task_id)
        resume = build_work_session_resume(session, task=task, state=state)
    return write_work_follow_snapshot(args, report, session, task, resume, force=True)


def work_ai_has_tool_gates(options):
    return bool(
        options.get("allow_read")
        or options.get("allow_write")
        or options.get("allow_shell")
        or options.get("allow_verify")
    )


def live_approval_prompt_enabled(args):
    if getattr(args, "no_prompt_approval", False):
        return False
    return bool(
        getattr(args, "prompt_approval", False)
        or (getattr(args, "live", False) and not getattr(args, "json", False) and sys.stdin.isatty())
    )


def work_auto_approve_edits_enabled(args):
    return getattr(args, "approval_mode", "") == APPROVAL_MODE_ACCEPT_EDITS


def resolved_work_act_mode(args):
    explicit = getattr(args, "act_mode", None)
    if explicit:
        return explicit
    return "deterministic" if getattr(args, "live", False) else "model"


def prompt_live_write_approval(tool_call, verify_command=""):
    result = (tool_call or {}).get("result") or {}
    parameters = (tool_call or {}).get("parameters") or {}
    path = result.get("path") or parameters.get("path") or ""
    if result.get("diff"):
        print(format_diff_preview(result.get("diff") or "", max_chars=2000, diff_stats=result.get("diff_stats")))
    if verify_command:
        print(f"Verify on approval: {verify_command}")
    else:
        print("Verify on approval: (none configured)")
    prompt = f"Apply dry-run work tool #{(tool_call or {}).get('id')} {(tool_call or {}).get('tool')} {path}? [y/N/q]: "
    print(prompt, end="", flush=True)
    answer = sys.stdin.readline()
    if answer == "":
        return "skip"
    normalized = answer.strip().lower()
    if normalized in ("y", "yes"):
        return "approve"
    if normalized in ("n", "no"):
        return "reject"
    if normalized in ("q", "quit"):
        return "quit"
    return "skip"


def _resume_pending_approval_for_tool(resume, tool_call_id):
    for approval in (resume or {}).get("pending_approvals") or []:
        if str(approval.get("tool_call_id")) == str(tool_call_id):
            return approval
    return {}


def record_work_approval_elicitation(state, session, task, source_call, resume=None):
    if not state or not session or not source_call:
        return None
    if source_call.get("approval_status") in NON_PENDING_APPROVAL_STATUSES:
        return None
    result = source_call.get("result") or {}
    if source_call.get("tool") not in WRITE_WORK_TOOLS or not result.get("dry_run") or not result.get("changed"):
        return None
    existing = find_question(state, source_call.get("approval_question_id"))
    if existing and existing.get("status") == "open":
        return existing
    task_id = session.get("task_id") or (task or {}).get("id")
    approval = _resume_pending_approval_for_tool(resume, source_call.get("id"))
    path = approval.get("path") or work_call_path(source_call) or ""
    title = (task or {}).get("title") or ""
    lines = [
        f"Work session #{session.get('id')} tool #{source_call.get('id')} is waiting for approval.",
        f"tool: {source_call.get('tool')} path: {path or '(unknown)'}",
    ]
    if task_id:
        task_text = f"task: #{task_id}"
        if title:
            task_text += f" {title}"
        lines.append(task_text)
    summary = source_call.get("summary") or ""
    if summary:
        lines.append(f"summary: {summary}")
    if approval.get("approval_blocked_reason"):
        lines.append(f"approval blocked: {approval.get('approval_blocked_reason')}")
    if approval.get("cli_approve_hint"):
        lines.append(f"approve: `{approval.get('cli_approve_hint')}`")
    if approval.get("cli_override_approve_hint"):
        lines.append(f"override approve: `{approval.get('cli_override_approve_hint')}`")
    if approval.get("cli_defer_verify_hint") and approval.get("cli_defer_verify_hint") != approval.get("cli_approve_hint"):
        lines.append(f"defer verify: `{approval.get('cli_defer_verify_hint')}`")
    if approval.get("cli_reject_hint"):
        lines.append(f"reject: `{approval.get('cli_reject_hint')}`")
    lines.append("If this prompt was interrupted, inspect the pending approval before retrying.")
    question, _created = add_question(
        state,
        "\n".join(lines),
        related_task_id=task_id,
        source="work_approval",
    )
    source_call["approval_question_id"] = question.get("id")
    source_call["approval_prompt_status"] = "open"
    source_call["approval_prompted_at"] = source_call.get("approval_prompted_at") or now_iso()
    return question


def resolve_work_approval_elicitation(state, source_call, answer_text):
    if not state or not source_call:
        return None
    question = find_question(state, source_call.get("approval_question_id"))
    if not question or question.get("status") != "open":
        return None
    reply = mark_question_answered(state, question, answer_text)
    source_call["approval_prompt_status"] = "answered"
    source_call["approval_prompt_answered_at"] = question.get("answered_at")
    return reply


def _work_control_text(action, fallback):
    for key in ("text", "note", "question", "reason", "summary"):
        value = (action or {}).get(key)
        if value:
            return str(value)
    return fallback


def _work_finish_text(action, fallback):
    summary = str((action or {}).get("summary") or "").strip()
    if summary and summary.casefold() not in ("done", "finish", "finished"):
        return summary
    for key in ("text", "note", "reason"):
        value = (action or {}).get(key)
        if value:
            return str(value)
    return fallback


def apply_work_control_action(state, session, task, action):
    action = action or {}
    action_type = action.get("type") or ""
    task_id = task.get("id") if task else None
    if action_type == "finish":
        note = _work_finish_text(action, "Work session finished.")
        current_time = now_iso()
        if session:
            close_work_session(session)
        if task is not None:
            append_task_note(task, f"Work session finished: {note}")
            if action.get("task_done"):
                completion_summary = str(action.get("completion_summary") or note)
                task["status"] = "done"
                append_task_note(task, f"{current_time} done: {completion_summary}")
                resolve_open_questions_for_task(
                    state,
                    task["id"],
                    reason="work session marked task done",
                )
                sync_task_done_state(state, task, completion_summary, current_time)
            task["updated_at"] = current_time
        return {"finished_note": note, "task_done": bool(action.get("task_done"))}
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
    if getattr(args, "quiet", False) and not getattr(args, "progress", False):
        return None
    if not (getattr(args, "progress", False) or getattr(args, "live", False) or not getattr(args, "json", False)):
        return None

    def emit(line):
        if getattr(args, "live", False):
            sys.stdout.flush()
        print(f"mew work ai: {line}", file=sys.stderr, flush=True)

    return emit


def work_tool_progress(args):
    if not getattr(args, "progress", False):
        return None

    def emit(line):
        print(f"mew work: {line}", file=sys.stderr, flush=True)

    return emit


def work_tool_output_progress(progress, tool_call_id, session_id=None, on_state_update=None):
    if not progress and session_id is None:
        return None
    mirror_lock = threading.Lock()
    buffered = {"stdout": "", "stderr": ""}
    last_mirror_at = 0.0
    last_snapshot_at = 0.0
    flush_timer = None

    def flush_buffer_locked(current_time):
        nonlocal flush_timer, last_mirror_at, last_snapshot_at
        state_updated = False
        chunks = {name: value for name, value in buffered.items() if value}
        if not chunks:
            flush_timer = None
            return False
        buffered["stdout"] = ""
        buffered["stderr"] = ""
        if flush_timer is not None:
            flush_timer.cancel()
            flush_timer = None
        last_mirror_at = current_time
        try:
            with state_lock():
                state = load_state()
                for name, value in chunks.items():
                    state_updated = bool(
                        append_work_tool_running_output(
                            state,
                            session_id,
                            tool_call_id,
                            name,
                            value,
                        )
                    ) or state_updated
                if state_updated:
                    save_state(state)
        except Exception as exc:  # pragma: no cover - output mirroring must not break the tool
            if progress:
                progress(f"tool #{tool_call_id} output mirror failed: {clip_output(str(exc), 200)}")
            return False
        snapshot_due = (
            last_snapshot_at == 0.0
            or current_time - last_snapshot_at >= RUNNING_OUTPUT_MIRROR_INTERVAL_SECONDS
        )
        if state_updated and on_state_update and snapshot_due:
            try:
                last_snapshot_at = current_time
                on_state_update()
            except Exception as exc:  # pragma: no cover - snapshot writes are advisory
                if progress:
                    progress(f"tool #{tool_call_id} follow snapshot failed: {clip_output(str(exc), 200)}")
        return state_updated

    def flush_buffer_from_timer():
        with mirror_lock:
            flush_buffer_locked(time.monotonic())

    def schedule_flush_locked(current_time):
        nonlocal flush_timer
        if flush_timer is not None:
            return
        delay = max(0.01, RUNNING_OUTPUT_MIRROR_INTERVAL_SECONDS - (current_time - last_mirror_at))
        flush_timer = threading.Timer(delay, flush_buffer_from_timer)
        flush_timer.daemon = True
        flush_timer.start()

    def emit(stream_name, text):
        if session_id is not None:
            with mirror_lock:
                if stream_name in buffered and text:
                    buffered[stream_name] = clip_tail(
                        f"{buffered[stream_name]}{text}",
                        RUNNING_OUTPUT_MIRROR_BUFFER_CHARS,
                    )
                buffered_chars = sum(len(value) for value in buffered.values())
                current_time = time.monotonic()
                due = last_mirror_at == 0.0 or current_time - last_mirror_at >= RUNNING_OUTPUT_MIRROR_INTERVAL_SECONDS
                if due and buffered_chars:
                    flush_buffer_locked(current_time)
                elif buffered_chars:
                    schedule_flush_locked(current_time)
        if progress:
            for line in (text or "").splitlines():
                progress(f"tool #{tool_call_id} {stream_name}: {clip_output(line, 500)}")

    return emit


def execute_work_tool_with_output(tool, parameters, allowed_read_roots, output_progress=None):
    if output_progress:
        return execute_work_tool(tool, parameters, allowed_read_roots, on_output=output_progress)
    return execute_work_tool(tool, parameters, allowed_read_roots)


def compact_repeat_guard_action(action):
    return {
        key: action.get(key)
        for key in (
            "kind",
            "label",
            "command",
            "task_id",
            "question_id",
            "session_id",
            "attention_id",
            "effort_summary",
            "reason",
            "stale_for_seconds",
        )
        if action.get(key) not in (None, "")
    }


def work_session_guard_command(session, *parts):
    command_parts = ["work"]
    task_id = (session or {}).get("task_id")
    if task_id is not None:
        command_parts.append(task_id)
    command_parts.extend(parts)
    return mew_command(*command_parts)


def repeat_guard_session_actions(session):
    return [
        {
            "kind": "review_work_session",
            "label": "Review current work session",
            "command": work_session_guard_command(session, "--session", "--resume", "--allow-read", "."),
            "task_id": (session or {}).get("task_id"),
            "session_id": (session or {}).get("id"),
        },
        {
            "kind": "steer_work_session",
            "label": "Steer next work step",
            "command": work_session_guard_command(session, "--steer", "<guidance>"),
            "task_id": (session or {}).get("task_id"),
            "session_id": (session or {}).get("id"),
        },
    ]


def repeat_guard_desk_actions(state, session, limit=3):
    try:
        actions = build_desk_view_model(state).get("actions") or []
    except (TypeError, ValueError):
        return []
    current_session_id = str((session or {}).get("id") or "")
    current_task_id = str((session or {}).get("task_id") or "")
    suggestions = []
    for action in actions:
        if not isinstance(action, dict):
            continue
        if action.get("kind") == "resume_work" and (
            str(action.get("session_id") or "") == current_session_id
            or str(action.get("task_id") or "") == current_task_id
        ):
            continue
        suggestions.append(compact_repeat_guard_action(action))
        if len(suggestions) >= limit:
            break
    return suggestions


def enrich_repeat_guard_with_actions(state, session, guard):
    guard = dict(guard or {})
    actions = [
        compact_repeat_guard_action(action)
        for action in repeat_guard_session_actions(session)
    ]
    actions.extend(repeat_guard_desk_actions(state, session))
    if actions:
        guard["suggested_actions"] = actions
        guard["suggested_next"] = (
            "review the current work session, steer the next step with new guidance, "
            "or choose one of suggested_actions"
        )
    return guard


def finish_repeated_work_tool_guard(state, session, tool, parameters, guard):
    guard = enrich_repeat_guard_with_actions(state, session, guard)
    tool_call = start_work_tool_call(state, session, tool, parameters)
    tool_call["repeat_guard"] = guard
    tool_call = finish_work_tool_call(
        state,
        session.get("id"),
        tool_call.get("id"),
        error=guard.get("message") or "repeat-action guard blocked tool call",
    )
    if tool_call:
        tool_call["repeat_guard"] = guard
        tool_call["summary"] = guard.get("message") or tool_call.get("summary") or ""
    return tool_call


BATCH_READ_WORK_TOOLS = READ_ONLY_WORK_TOOLS | GIT_WORK_TOOLS
BATCH_WRITE_WORK_TOOLS = WRITE_WORK_TOOLS


def _work_path_is_mew_source_path(path):
    normalized = str(path or "").replace("\\", "/").lstrip("./")
    return normalized.startswith("src/mew/") and normalized.endswith(".py")


def _paired_write_batch_actions(actions):
    write_actions = [
        dict(action)
        for action in actions or []
        if (action.get("type") or action.get("tool")) in BATCH_WRITE_WORK_TOOLS
    ]
    if len(write_actions) < 2 or len(write_actions) != len(actions or []):
        return []
    tests = [action for action in write_actions if _work_path_is_tests_path(action.get("path"))]
    sources = [action for action in write_actions if _work_path_is_mew_source_path(action.get("path"))]
    if not tests or not sources or len(tests) + len(sources) != len(write_actions):
        return []
    source_path = sources[0].get("path")
    ordered = []
    for raw_action in [*tests, *sources]:
        action = dict(raw_action)
        action["apply"] = False
        action["dry_run"] = True
        if raw_action in tests:
            action["defer_verify_on_approval"] = True
            action["paired_test_source_path"] = source_path
        ordered.append(action)
    return ordered


def run_work_batch_action(session_id, task_id, index, planned, action, args, progress, turn_id=None):
    raw_sub_actions = [sub_action for sub_action in (action.get("tools") or [])[:5] if isinstance(sub_action, dict)]
    write_batch = any((sub_action.get("type") or sub_action.get("tool")) in BATCH_WRITE_WORK_TOOLS for sub_action in raw_sub_actions)
    if write_batch:
        sub_actions = _paired_write_batch_actions(raw_sub_actions)
    else:
        sub_actions = [
            sub_action
            for sub_action in raw_sub_actions
            if (sub_action.get("type") or sub_action.get("tool")) in BATCH_READ_WORK_TOOLS
        ]
    if not sub_actions:
        sub_actions = [
            {
                "type": "wait",
                "reason": (
                    "batch requires write/edit tools under tests/** and src/mew/** with at least one of each"
                    if write_batch
                    else "batch has no read-only tools"
                ),
            }
        ]
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
    pending_approval_ids = []
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
        expected_tools = BATCH_WRITE_WORK_TOOLS if write_batch else BATCH_READ_WORK_TOOLS
        if action_type not in expected_tools:
            error = (
                f"batch write tool is not a paired write/edit: {action_type or 'missing'}"
                if write_batch
                else f"batch tool is not read-only: {action_type or 'missing'}"
            )
            break
        parameters = work_tool_parameters_from_action(
            sub_action,
            allowed_write_roots=args.allow_write or [] if write_batch else [],
            allow_shell=False,
            allow_verify=bool(args.allow_verify) if write_batch else False,
            verify_command=args.verify_command or "" if write_batch else "",
            verify_timeout=args.verify_timeout,
        )
        if write_batch:
            parameters["apply"] = False
            if _work_path_is_tests_path(parameters.get("path")):
                source_paths = [
                    candidate.get("path")
                    for candidate in sub_actions
                    if _work_path_is_mew_source_path(candidate.get("path"))
                ]
                parameters["defer_verify_on_approval"] = True
                if source_paths:
                    parameters["paired_test_source_path"] = source_paths[0]
        if write_batch:
            with state_lock():
                state = load_state()
                session = find_work_session(state, session_id)
                pairing_status = planned_unpaired_source_write_pairing_status(
                    session,
                    action_type,
                    parameters,
                    allow_unpaired=bool(getattr(args, "allow_unpaired_source_edit", False)),
                )
            if pairing_status:
                error = paired_test_steer_text(pairing_status)
                break
        with state_lock():
            state = load_state()
            session = find_work_session(state, session_id)
            repeat_guard = work_tool_repeat_guard(session, action_type, parameters)
            if repeat_guard:
                tool_call = finish_repeated_work_tool_guard(state, session, action_type, parameters, repeat_guard)
            else:
                tool_call = start_work_tool_call(state, session, action_type, parameters)
            tool_call_id = tool_call.get("id") if tool_call else None
            save_state(state)
        if repeat_guard:
            error = repeat_guard.get("message") or "repeat-action guard blocked tool call"
            tool_calls.append(tool_call)
            if progress:
                progress(f"step #{index}: batch tool #{tool_call_id} {action_type} repeat-guard")
            break
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
            if not tool_call:
                error = WORK_TOOL_RESULT_STALE_ERROR
                tool_call = _missing_finished_work_tool_call(action_type, tool_call_id, error)
            session = find_work_session(state, session_id)
            remember_successful_work_verification(session, action_type, result)
            save_state(state)
        tool_calls.append(tool_call)
        result = tool_call.get("result") or {}
        if (
            write_batch
            and action_type in WRITE_WORK_TOOLS
            and tool_call.get("status") == "completed"
            and result.get("dry_run")
            and result.get("changed")
            and not tool_call.get("approval_status")
        ):
            pending_approval_ids.append(tool_call.get("id"))
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
        "pending_approval_ids": pending_approval_ids,
        "pending_approval": bool(pending_approval_ids),
        "error": error,
        "summary": f"ran {len(tool_calls)} batch tool(s)",
    }


def cmd_work(args):
    try:
        args.cell_tail_lines = positive_int_option(getattr(args, "cell_tail_lines", None), "--cell-tail-lines")
    except MewError as exc:
        print(f"mew: {exc}", file=sys.stderr)
        return 1
    if getattr(args, "follow_status", False):
        return cmd_work_follow_status(args)
    if getattr(args, "reply_schema", False):
        return cmd_work_reply_schema(args)
    if getattr(args, "reply_file", None):
        return cmd_work_reply_file(args)
    if getattr(args, "live", False) or getattr(args, "follow", False):
        args.ai = True
    if getattr(args, "ai", False):
        if getattr(args, "tool", None):
            print("mew: --ai and --tool cannot be combined", file=sys.stderr)
            return 1
        return cmd_work_ai(args)
    if getattr(args, "approve_all", False):
        return cmd_work_approve_all(args)
    if getattr(args, "approve_tool", None):
        return cmd_work_approve_tool(args)
    if getattr(args, "reject_tool", None):
        return cmd_work_reject_tool(args)
    if getattr(args, "tool", None):
        return cmd_work_tool(args)
    if getattr(args, "start_session", False):
        return cmd_work_start_session(args)
    if getattr(args, "stop_session", False):
        return cmd_work_stop_session(args)
    if getattr(args, "session", False) or any(
        getattr(args, name, False) for name in ("resume", "timeline", "diffs", "tests", "commands", "cells")
    ):
        return cmd_work_show_session(args)
    if getattr(args, "close_session", False):
        return cmd_work_close_session(args)
    if getattr(args, "steer", None):
        return cmd_work_steer(args)
    if getattr(args, "queue_followup", None):
        return cmd_work_queue_followup(args)
    if getattr(args, "interrupt_submit", None):
        return cmd_work_interrupt_submit(args)
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


def detect_default_verify_command():
    if Path("pyproject.toml").exists() and Path("tests").exists():
        return "uv run pytest -q"
    if Path("pytest.ini").exists() or Path("tests").exists():
        return "python -m pytest -q"
    if Path("package.json").exists():
        return "npm test"
    return ""


def positive_max_steps(value, default=1, allow_zero=False):
    if value is None:
        value = default
    try:
        max_steps = int(value)
    except (TypeError, ValueError) as exc:
        raise MewError("--max-steps must be an integer") from exc
    minimum = 0 if allow_zero else 1
    if max_steps < minimum:
        raise MewError(f"--max-steps must be >= {minimum}")
    return max_steps


def positive_int_option(value, flag):
    if value is None:
        return None
    try:
        option = int(value)
    except (TypeError, ValueError) as exc:
        raise MewError(f"{flag} must be an integer") from exc
    if option < 1:
        raise MewError(f"{flag} must be >= 1")
    return option


def cmd_do(args):
    verify_command = getattr(args, "verify_command", None) or detect_default_verify_command()
    allow_verify = bool(verify_command) and not getattr(args, "no_verify", False)
    try:
        max_steps = positive_max_steps(getattr(args, "max_steps", None), default=3)
    except MewError as exc:
        print(f"mew: {exc}", file=sys.stderr)
        return 1
    work_args = SimpleNamespace(
        task_id=getattr(args, "task_id", None),
        ai=True,
        live=True,
        json=False,
        tool=None,
        auth=getattr(args, "auth", None),
        model_backend=getattr(args, "model_backend", None) or DEFAULT_MODEL_BACKEND,
        model=getattr(args, "model", None),
        base_url=getattr(args, "base_url", None),
        model_timeout=getattr(args, "model_timeout", 60.0),
        max_steps=max_steps,
        act_mode=getattr(args, "act_mode", None) or "deterministic",
        work_guidance=getattr(args, "work_guidance", None),
        progress=True,
        stream_model=bool(getattr(args, "stream_model", False)),
        compact_live=bool(getattr(args, "compact_live", False)),
        prompt_approval=bool(getattr(args, "prompt_approval", False)),
        no_prompt_approval=bool(getattr(args, "no_prompt_approval", False)),
        approval_mode=getattr(args, "approval_mode", None) or "",
        allow_read=getattr(args, "allow_read", None) or ["."],
        allow_write=[] if getattr(args, "read_only", False) else (getattr(args, "allow_write", None) or ["."]),
        allow_shell=False,
        allow_verify=allow_verify,
        verify_command=verify_command if allow_verify else "",
        verify_cwd=".",
        verify_timeout=getattr(args, "verify_timeout", 300),
        start_session=False,
        session=False,
        close_session=False,
        stop_session=False,
        stop_reason=None,
        session_note=None,
        recover_session=False,
        approve_tool=None,
        reject_tool=None,
        reject_reason=None,
    )
    return cmd_work_ai(work_args)


def code_args_request_default_update(args):
    return bool(
        getattr(args, "auth", None)
        or getattr(args, "model_backend", None)
        or getattr(args, "model", None)
        or getattr(args, "base_url", None)
        or getattr(args, "allow_read", None)
        or getattr(args, "allow_write", None)
        or getattr(args, "read_only", False)
        or getattr(args, "verify_command", None)
        or getattr(args, "no_verify", False)
        or getattr(args, "compact_live", False)
        or getattr(args, "prompt_approval", False)
        or getattr(args, "no_prompt_approval", False)
        or getattr(args, "approval_mode", None)
    )


def code_default_update_args(args, session):
    current = (session or {}).get("default_options") or {}
    verify_command = getattr(args, "verify_command", None)
    if verify_command is None:
        verify_command = current.get("verify_command") or ""
    allow_verify = bool(verify_command) and not getattr(args, "no_verify", False)
    return SimpleNamespace(
        auth=getattr(args, "auth", None),
        model_backend=getattr(args, "model_backend", None),
        model=getattr(args, "model", None),
        base_url=getattr(args, "base_url", None),
        allow_read=getattr(args, "allow_read", None) or [],
        allow_write=[] if getattr(args, "read_only", False) else (getattr(args, "allow_write", None) or []),
        allow_shell=False,
        allow_verify=allow_verify,
        verify_command=verify_command if allow_verify else "",
        verify_timeout=getattr(args, "verify_timeout", 300),
        act_mode=None,
        compact_live=bool(getattr(args, "compact_live", False)),
        prompt_approval=bool(getattr(args, "prompt_approval", False)),
        no_prompt_approval=bool(getattr(args, "no_prompt_approval", False)),
        approval_mode=getattr(args, "approval_mode", None) or "",
        read_only=bool(getattr(args, "read_only", False)),
        no_verify=bool(getattr(args, "no_verify", False)),
    )


def format_code_task_not_found(task_id):
    text = str(task_id or "")
    if text and not text.lstrip("#").isdigit():
        return (
            "mew: code expects an existing task id; create one with "
            f"`{mew_command('task', 'add', text, '--kind', 'coding')}`"
        )
    return f"mew: task not found: {task_id}"


def cmd_code(args):
    task_id = getattr(args, "task_id", None)
    if task_id:
        verify_command = getattr(args, "verify_command", None) or detect_default_verify_command()
        allow_verify = bool(verify_command) and not getattr(args, "no_verify", False)
        start_args = SimpleNamespace(
            task_id=task_id,
            json=False,
            auth=getattr(args, "auth", None),
            model_backend=getattr(args, "model_backend", None) or DEFAULT_MODEL_BACKEND,
            model=getattr(args, "model", None),
            base_url=getattr(args, "base_url", None),
            allow_read=getattr(args, "allow_read", None) or ["."],
            allow_write=[] if getattr(args, "read_only", False) else (getattr(args, "allow_write", None) or ["."]),
            allow_shell=False,
            allow_verify=allow_verify,
            verify_command=verify_command if allow_verify else "",
            verify_timeout=getattr(args, "verify_timeout", 300),
            act_mode="deterministic",
            compact_live=bool(getattr(args, "compact_live", False)),
            prompt_approval=bool(getattr(args, "prompt_approval", False)),
            no_prompt_approval=bool(getattr(args, "no_prompt_approval", False)),
            approval_mode=getattr(args, "approval_mode", None) or "",
            read_only=bool(getattr(args, "read_only", False)),
            no_verify=bool(getattr(args, "no_verify", False)),
        )
        with state_lock():
            state = load_state()
            task = select_workbench_task(state, task_id)
            if not task:
                print(format_code_task_not_found(task_id), file=sys.stderr)
                return 1
            if task.get("status") == "done":
                print(done_task_work_session_error(task), file=sys.stderr)
                return 1
            session, created = create_work_session(state, task)
            remember_work_session_default_options(session, start_args)
            save_state(state)
        if not getattr(args, "quiet", False):
            print(("created " if created else "reused ") + f"work session #{session['id']} for task #{task['id']}")
    elif code_args_request_default_update(args):
        with state_lock():
            state = load_state()
            session = active_work_session_for_kind(state, kind="coding")
            if not session:
                print("mew: code option defaults require an active coding work session or a task id", file=sys.stderr)
                return 1
            remember_work_session_default_options(session, code_default_update_args(args, session))
            save_state(state)
        if not getattr(args, "quiet", False):
            print(f"updated work session #{session['id']} defaults")

    chat_args = SimpleNamespace(
        poll_interval=getattr(args, "poll_interval", 1.0),
        limit=getattr(args, "limit", 5),
        kind="coding",
        mark_read=bool(getattr(args, "mark_read", False)),
        activity=bool(getattr(args, "activity", True)),
        no_brief=bool(getattr(args, "no_brief", False)),
        no_unread=bool(getattr(args, "no_unread", False)),
        quiet=bool(getattr(args, "quiet", False)),
        work_mode=True,
        compact_controls=True,
        compact_brief=True,
        timeout=getattr(args, "timeout", None),
    )
    return cmd_chat(chat_args)


def work_ai_step_guidance(args, index, max_steps):
    guidance = (getattr(args, "work_guidance", None) or "").strip()
    if getattr(args, "follow", False) and index == max_steps:
        final_guidance = (
            "This is the final allowed --follow step. If you have enough evidence, prefer a "
            "remember, ask_user, or finish action over another observation so reentry has a durable note."
        )
        return "\n\n".join(part for part in (guidance, final_guidance) if part)
    return guidance


def queue_work_session_steer(session, text, source="user", metadata=None):
    text = str(text or "").strip()
    if not session or not text:
        return None
    current_time = now_iso()
    steer = {"text": text, "source": source, "created_at": current_time}
    if isinstance(metadata, dict) and metadata:
        steer["metadata"] = dict(metadata)
    session["pending_steer"] = steer
    session["updated_at"] = current_time
    return steer


def pending_work_session_steer(session):
    steer = (session or {}).get("pending_steer") or {}
    text = str(steer.get("text") or "").strip()
    if not text:
        return None
    pending = dict(steer)
    pending["text"] = text
    return pending


def complete_work_session_steer(session, steer, step_index, action_type=None, action=None, result=None):
    expected = steer or {}
    current = pending_work_session_steer(session)
    if not current:
        return False
    for key in ("text", "source", "created_at"):
        if str(current.get(key) or "") != str(expected.get(key) or ""):
            return False
    if current.get("source") == "paired_test_steer":
        path = (action or {}).get("path")
        if action_type not in WRITE_WORK_TOOLS or not _work_path_is_tests_path(path):
            return False
        if result is None or not result.get("changed"):
            return False
    session.pop("pending_steer", None)
    add_work_session_note(
        session,
        f"steer for step {step_index}: {current.get('text')}",
        source=current.get("source") or "user",
    )
    return True


def _next_work_followup_id(session):
    ids = []
    for item in (session or {}).get("queued_followups") or []:
        try:
            ids.append(int(item.get("id")))
        except (TypeError, ValueError):
            continue
    return (max(ids) if ids else 0) + 1


def queue_work_session_followup(session, text, source="user"):
    text = str(text or "").strip()
    if not session or not text:
        return None
    current_time = now_iso()
    followup = {
        "id": _next_work_followup_id(session),
        "text": text,
        "source": source or "user",
        "status": "queued",
        "created_at": current_time,
    }
    items = session.setdefault("queued_followups", [])
    items.append(followup)
    del items[:-50]
    session["updated_at"] = current_time
    return followup


def pending_work_session_followup(session):
    for item in (session or {}).get("queued_followups") or []:
        text = str(item.get("text") or "").strip()
        if item.get("status") == "queued" and text:
            pending = dict(item)
            pending["text"] = text
            return pending
    return None


def complete_work_session_followup(session, followup, step_index):
    expected = followup or {}
    expected_id = expected.get("id")
    for item in (session or {}).get("queued_followups") or []:
        if expected_id is not None and item.get("id") != expected_id:
            continue
        if item.get("status") != "queued":
            return False
        if str(item.get("text") or "").strip() != str(expected.get("text") or "").strip():
            return False
        current_time = now_iso()
        item["status"] = "consumed"
        item["consumed_at"] = current_time
        item["consumed_step_index"] = step_index
        add_work_session_note(
            session,
            f"queued follow-up for step {step_index}: {item.get('text')}",
            source=item.get("source") or "user",
            current_time=current_time,
        )
        return True
    return False


def planned_unpaired_source_write_pairing_status(session, action_type, parameters, *, allow_unpaired=False):
    if allow_unpaired or action_type not in WRITE_WORK_TOOLS:
        return {}
    if not (parameters or {}).get("path"):
        return {}
    planned_call = {
        "id": "__planned__",
        "tool": action_type,
        "parameters": parameters,
        "result": {"changed": True},
    }
    pairing = work_write_pairing_status(session, planned_call)
    if pairing.get("status") != "missing_test_edit":
        return {}
    return pairing


def _work_path_is_tests_path(path):
    normalized = str(path or "").replace("\\", "/").lstrip("./")
    return normalized == "tests" or normalized.startswith("tests/")


def _force_paired_test_steer_write_to_dry_run(pending_steer, action_type, parameters, action):
    if not pending_steer or pending_steer.get("source") != "paired_test_steer":
        return False
    if action_type not in WRITE_WORK_TOOLS:
        return False
    if not _work_path_is_tests_path((parameters or {}).get("path")):
        return False
    if (parameters or {}).get("apply"):
        parameters["apply"] = False
        if isinstance(action, dict):
            action["apply"] = False
            action["dry_run"] = True
    parameters["defer_verify_on_approval"] = True
    metadata = pending_steer.get("metadata") or {}
    if metadata.get("source_path"):
        parameters["paired_test_source_path"] = metadata.get("source_path")
    if isinstance(action, dict):
        action["coerced_dry_run_reason"] = "paired_test_steer"
        action["defer_verify_on_approval"] = True
        if metadata.get("source_path"):
            action["paired_test_source_path"] = metadata.get("source_path")
    return True


def paired_test_steer_text(pairing):
    source_path = pairing.get("source_path") or "src/mew/**"
    suggested = pairing.get("suggested_test_path") or "the matching tests/** file"
    discovered = [path for path in pairing.get("discovered_test_paths") or [] if path]
    suggestion_label = "Suggested existing test path" if discovered else "Suggested first test path"
    other_discovered = ""
    if len(discovered) > 1:
        other_discovered = f" Other discovered candidates: {', '.join(discovered[1:4])}."
    return (
        f"Before retrying the src/mew source edit for {source_path}, add or update a paired tests/** "
        f"write/edit in this same work session. {suggestion_label}: {suggested}.{other_discovered} "
        "Use a narrow read_file/search_text/edit_file step on the test first; after the test edit exists, retry the source edit. "
        "Only use --allow-unpaired-source-edit if this source-only edit is intentional."
    )


def paired_test_steer_action(pairing):
    action = {
        "type": "paired_test_steer",
        "source_path": pairing.get("source_path") or "",
        "reason": paired_test_steer_text(pairing),
    }
    if pairing.get("suggested_test_path"):
        action["suggested_test_path"] = pairing.get("suggested_test_path")
    return action


def request_work_session_interrupt_submit(session, text, source="user"):
    text = str(text or "").strip()
    if not session or not text:
        return None, None
    reason = f"interrupt and submit: {clip_inline_text(text, 240)}"
    request_work_session_stop(
        session,
        reason=reason,
        action="interrupt_submit",
        submit_text=text,
    )
    stop_request = {
        "requested_at": session.get("stop_requested_at"),
        "reason": session.get("stop_reason") or reason,
        "action": session.get("stop_action") or "interrupt_submit",
        "submit_text": session.get("stop_submit_text") or text,
    }
    steer = queue_work_session_steer(session, text, source=source or "interrupt_submit")
    return stop_request, steer


def pause_work_session_after_user_interrupt(session_id, step_index):
    current_time = now_iso()
    repairs = []
    note_text = (
        f"Follow interrupted by user at step {step_index}. "
        "Resume with /c, /continue, or the printed Next CLI controls after reviewing the latest session state."
    )
    with state_lock():
        state = load_state()
        session = find_work_session(state, session_id)
        if not session:
            return {"repairs": repairs, "note": note_text}
        recovery_hint = (
            f"Review work session #{session.get('id')} resume, verify world state, then retry or choose a new action."
        )
        for call in session.get("tool_calls") or []:
            if not isinstance(call, dict) or call.get("status") != "running":
                continue
            call["status"] = "interrupted"
            call["finished_at"] = current_time
            call["error"] = call.get("error") or "Interrupted by user during follow."
            call["summary"] = call.get("summary") or "interrupted work tool call"
            call["recovery_hint"] = recovery_hint
            repairs.append({"type": "interrupted_work_tool_call", "tool_call_id": call.get("id")})
        for turn in session.get("model_turns") or []:
            if not isinstance(turn, dict) or turn.get("status") != "running":
                continue
            turn["status"] = "interrupted"
            turn["finished_at"] = current_time
            turn["error"] = turn.get("error") or "Interrupted by user during follow."
            turn["summary"] = turn.get("summary") or "interrupted work model turn"
            turn["recovery_hint"] = recovery_hint
            repairs.append({"type": "interrupted_work_model_turn", "model_turn_id": turn.get("id")})
        add_work_session_note(session, note_text, source="system", current_time=current_time)
        session["last_user_interrupt"] = {
            "step": step_index,
            "at": current_time,
            "note": note_text,
        }
        save_state(state)
    return {"repairs": repairs, "note": note_text}


def record_max_steps_reentry_note(session_id, report, mode="follow"):
    steps = list((report or {}).get("steps") or [])
    if not steps:
        return ""
    last_step = steps[-1]
    action = last_step.get("action") or {}
    action_type = action.get("type") or action.get("tool") or "unknown"
    tool_call = last_step.get("tool_call") or {}
    summary = ""
    if tool_call:
        summary = compact_work_tool_summary(tool_call)
    elif last_step.get("tool_calls"):
        summaries = [compact_work_tool_summary(call) for call in last_step.get("tool_calls") or [] if call]
        summary = "; ".join(item for item in summaries if item)
    if not summary:
        summary = last_step.get("summary") or last_step.get("error") or action.get("reason") or ""
    label = "Follow" if mode == "follow" else "Live run"
    note_text = (
        f"{label} reached max_steps={report.get('max_steps')} after {len(steps)} step(s). "
        f"Last action: {action_type}."
    )
    if summary:
        note_text += f" Last result: {clip_inline_text(str(summary), 240)}"
    with state_lock():
        state = load_state()
        session = find_work_session(state, session_id)
        if not session:
            return note_text
        session["notes"] = [
            note
            for note in session.get("notes") or []
            if not (
                note.get("source") == "system"
                and str(note.get("text") or "").startswith(("Follow reached max_steps=", "Live run reached max_steps="))
            )
        ]
        add_work_session_note(session, note_text, source="system")
        save_state(state)
    return note_text


def maybe_print_work_live_cells(args, session, task, index, seen_count=0):
    if not (getattr(args, "follow", False) or getattr(args, "cells", False)):
        return seen_count
    cells = build_work_session_cells(
        session,
        limit=None,
        tail_max_lines=getattr(args, "cell_tail_lines", None),
        include_startup_status=False,
    )
    new_cells = cells[seen_count:] if seen_count < len(cells) else []
    if not new_cells:
        return len(cells)
    print("")
    title = (session or {}).get("title") or (task or {}).get("title") or ""
    compact_follow_cells = getattr(args, "follow", False) and not getattr(args, "cells", False)
    cell_text = format_work_cells(
        new_cells,
        header="",
        include_detail=not compact_follow_cells,
        include_tail=not compact_follow_cells,
        include_timestamps=not compact_follow_cells,
    )
    if title:
        print(f"Work cells after step #{index}")
        print(f"title: {title}")
        if compact_follow_cells:
            print(f"compact: details available with {mew_executable()} work {session.get('task_id')} --cells")
        print(cell_text)
    else:
        header = f"Work cells after step #{index}"
        if compact_follow_cells:
            print(header)
            print(f"compact: details available with {mew_executable()} work {session.get('task_id')} --cells")
            print(cell_text)
        else:
            print(format_work_cells(new_cells, header=header))
    return len(cells)


def maybe_print_work_active_cell(args, session, task, index, source, source_id):
    if not getattr(args, "follow", False):
        return
    for cell in build_work_session_cells(
        session,
        limit=None,
        tail_max_lines=getattr(args, "cell_tail_lines", None),
        include_startup_status=False,
    ):
        if (
            cell.get("source") == source
            and str(cell.get("source_id")) == str(source_id)
            and cell.get("status") == "running"
        ):
            print("")
            print(f"Work active cell step #{index}")
            title = (session or {}).get("title") or (task or {}).get("title") or ""
            if title:
                print(f"title: {title}")
            print(format_work_cells([cell], header=""))
            return


def print_work_live_step_output(args, index, step, resume, session, task, seen_count=0):
    if getattr(args, "follow", False):
        next_seen = maybe_print_work_live_cells(args, session, task, index, seen_count)
        if next_seen != seen_count:
            return next_seen
    print("")
    print(f"Work live step #{index} result")
    print(format_work_live_step_result(step, resume=resume))
    return maybe_print_work_live_cells(args, session, task, index, seen_count)


def _refresh_step_tool_call_after_approval(step, approved_tool_call):
    approved_tool_call = approved_tool_call or {}
    approved_id = approved_tool_call.get("id")
    if approved_id is None:
        return
    if (step.get("tool_call") or {}).get("id") == approved_id:
        step["tool_call"] = approved_tool_call
    refreshed_calls = []
    changed = False
    for call in step.get("tool_calls") or []:
        if (call or {}).get("id") == approved_id:
            refreshed_calls.append(approved_tool_call)
            changed = True
        else:
            refreshed_calls.append(call)
    if changed:
        step["tool_calls"] = refreshed_calls
        pending_ids = [
            call.get("id")
            for call in refreshed_calls
            if call
            and call.get("tool") in WRITE_WORK_TOOLS
            and (call.get("result") or {}).get("dry_run")
            and (call.get("result") or {}).get("changed")
            and not call.get("approval_status")
        ]
        step["pending_approval_ids"] = pending_ids
        step["pending_approval"] = bool(pending_ids)


def cmd_work_ai(args):
    if getattr(args, "follow", False):
        args.live = True
        args.compact_live = True
        args.stream_model = True
        if getattr(args, "max_steps", None) is None:
            args.max_steps = 10
    try:
        max_steps = positive_max_steps(
            getattr(args, "max_steps", None),
            default=1,
            allow_zero=bool(getattr(args, "live", False) or getattr(args, "follow", False)),
        )
    except MewError as exc:
        print(f"mew: {exc}", file=sys.stderr)
        return 1
    if getattr(args, "live", False) and getattr(args, "json", False) and max_steps != 0:
        print("mew: --live cannot be combined with --json except for --max-steps 0 snapshot refresh", file=sys.stderr)
        return 1
    args.act_mode = resolved_work_act_mode(args)
    try:
        model_backend = normalize_model_backend(args.model_backend)
    except MewError as exc:
        print(f"mew: {exc}", file=sys.stderr)
        return 1

    model = args.model or model_backend_default_model(model_backend)
    base_url = args.base_url or model_backend_default_base_url(model_backend)

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
        if task.get("status") == "done":
            print(done_task_work_session_error(task), file=sys.stderr)
            return 1
        task_id = task.get("id")
    with state_lock():
        state = load_state()
        task = find_task(state, task_id)
        if not task:
            print(f"mew: task not found: {task_id}", file=sys.stderr)
            return 1
        if task.get("status") == "done":
            print(done_task_work_session_error(task), file=sys.stderr)
            return 1
        session = None
        created = False
        if max_steps == 0:
            session = next(
                (
                    candidate
                    for candidate in reversed(state.get("work_sessions", []))
                    if str(candidate.get("task_id")) == str(task_id)
                    and candidate.get("status") == "active"
                ),
                None,
            )
        if session is None:
            session, created = create_work_session(state, task)
            remember_work_session_default_options(session, args)
            save_state(state)
        session_id = session.get("id")
    if progress:
        progress(f"{'created' if created else 'reused'} session #{session_id} task=#{task_id}")

    options = _work_control_options(args, session=session)
    effective_args = _work_effective_args(args, options)
    compact_cli_controls = bool(getattr(effective_args, "compact_live", False) or getattr(args, "follow", False))
    report = {
        "session_id": session_id,
        "task_id": task_id,
        "created": created,
        "max_steps": max_steps,
        "stop_reason": "max_steps",
        "steps": [],
    }
    if max_steps == 0:
        report["stop_reason"] = "snapshot_refresh"
        if getattr(args, "live", False) or getattr(args, "follow", False):
            with state_lock():
                state = load_state()
                session = find_work_session(state, session_id)
                task = work_session_task(state, session)
            resume = build_work_session_resume(session, task=task, state=state)
            write_work_follow_snapshot(args, report, session, task, resume, force=True)
        if getattr(args, "json", False):
            print(json.dumps(report, ensure_ascii=False, indent=2))
        elif not getattr(args, "quiet", False):
            print(format_work_ai_report(report, compact=getattr(effective_args, "compact_live", False)))
        if (
            getattr(args, "live", False)
            and not getattr(args, "quiet", False)
            and not getattr(args, "suppress_cli_controls", False)
        ):
            with state_lock():
                state = load_state()
                session = find_work_session(state, session_id)
            print(format_work_cli_controls(session, args, compact=compact_cli_controls))
        return 0

    with state_lock():
        state = load_state()
        running_sessions = [
            candidate
            for candidate in active_work_sessions(state)
            if work_session_has_running_activity(candidate)
        ]
    if running_sessions:
        blocked_by = running_sessions[0]
        report["stop_reason"] = "work_already_running"
        report["blocked_by_session_id"] = blocked_by.get("id")
        report["blocked_by_task_id"] = blocked_by.get("task_id")
        if progress:
            progress(f"work session #{blocked_by.get('id')} is already running")
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            print(format_work_ai_report(report, compact=getattr(effective_args, "compact_live", False)))
            if getattr(args, "live", False) and not getattr(args, "suppress_cli_controls", False):
                with state_lock():
                    state = load_state()
                    session = find_work_session(state, session_id)
                print(format_work_cli_controls(session, args, compact=compact_cli_controls))
        return 1

    try:
        model_backend = normalize_model_backend(effective_args.model_backend)
    except MewError as exc:
        print(f"mew: {exc}", file=sys.stderr)
        return 1
    model = effective_args.model or model_backend_default_model(model_backend)
    base_url = effective_args.base_url or model_backend_default_base_url(model_backend)
    effective_args.model_backend = model_backend
    effective_args.model = model
    effective_args.base_url = base_url
    try:
        model_auth = load_model_auth(model_backend, effective_args.auth)
    except MewError as exc:
        print(f"mew: {exc}", file=sys.stderr)
        return 1

    live_cells_seen = len(build_work_session_cells(session, limit=None, include_startup_status=False))
    if getattr(args, "live", False) and not session.get("stop_requested_at") and not work_ai_has_tool_gates(options):
        report["stop_reason"] = "missing_gates"
        if progress:
            progress("no work tool gates enabled; skipping model call")
        print(format_work_ai_report(report, compact=getattr(effective_args, "compact_live", False)))
        print(
            "No work tool gates are enabled. Rerun with `--allow-read .`, explicit write/verify gates, "
            "or use `mew do <task-id>` for the supervised default loop."
        )
        print(format_work_cli_controls(session, args, compact=compact_cli_controls))
        return 1

    for index in range(1, max_steps + 1):
        step_started = time.monotonic()
        live_thinking_open = False
        live_model_delta_seen = False
        live_delta_buffers = {}
        live_delta_totals = {}
        live_delta_rendered_lengths = {}
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
            pending_steer = None
            pending_followup = None
            if stop_request and stop_request.get("action") == "interrupt_submit":
                pending_steer = pending_work_session_steer(session)
            elif not stop_request:
                pending_steer = pending_work_session_steer(session)
                if not pending_steer:
                    pending_followup = pending_work_session_followup(session)
            task = work_session_task(state, session)
            if stop_request:
                save_state(state)
        if stop_request:
            if stop_request.get("action") == "interrupt_submit" and pending_steer:
                report.setdefault("interrupt_submits", []).append(stop_request)
                if progress:
                    progress(f"step #{index}: interrupt submit requested")
            else:
                report["stop_reason"] = "stop_requested"
                report["stop_request"] = stop_request
                if progress:
                    progress(f"step #{index}: stop requested")
                break
        step_guidance = work_ai_step_guidance(args, index, max_steps)
        if pending_steer:
            pending_steer_text = pending_steer.get("text") or ""
            step_guidance = "\n\n".join(
                part for part in (step_guidance, f"User steer for this step:\n{pending_steer_text}") if part
            )
            if progress:
                progress(f"step #{index}: applying steer")
        elif pending_followup:
            pending_followup_text = pending_followup.get("text") or ""
            step_guidance = "\n\n".join(
                part
                for part in (
                    step_guidance,
                    f"Queued follow-up for this step:\n{pending_followup_text}",
                )
                if part
            )
            if progress:
                progress(f"step #{index}: applying queued follow-up")

        prompt_state = state
        prompt_session = session
        prompt_task = task

        def flush_live_model_delta(phase=None):
            if not getattr(args, "live", False):
                return
            phases = [phase] if phase else list(live_delta_buffers)
            for current_phase in phases:
                buffered = live_delta_buffers.get(current_phase) or ""
                if not buffered:
                    continue
                live_delta_buffers[current_phase] = ""
                total = live_delta_totals.get(current_phase) or buffered
                if getattr(effective_args, "compact_live", False) and total.lstrip().startswith("{"):
                    for line in _compact_live_model_delta_lines(
                        current_phase,
                        total,
                        live_delta_rendered_lengths,
                    ):
                        print(line, flush=True)
                    continue
                rendered = " ".join(buffered.split())
                if rendered:
                    print(format_work_live_model_delta(current_phase, rendered), flush=True)

        def live_model_delta(phase, text):
            nonlocal live_thinking_open, live_model_delta_seen
            if not getattr(args, "live", False):
                return
            live_model_delta_seen = True
            if not live_thinking_open:
                print("")
                print(f"Work live step #{index} thinking")
                print(
                    format_work_live_progress(
                        index,
                        max_steps,
                        session_id,
                        task_id,
                        phase="thinking",
                        elapsed_seconds=time.monotonic() - step_started,
                    )
                )
                live_thinking_open = True
            live_delta_totals[phase] = f"{live_delta_totals.get(phase, '')}{text or ''}"
            live_delta_buffers[phase] = f"{live_delta_buffers.get(phase, '')}{text or ''}"
            rendered = " ".join(live_delta_buffers[phase].split())
            if len(rendered) >= 160 or "\n" in str(text or ""):
                flush_live_model_delta(phase)

        with state_lock():
            state = load_state()
            running_sessions = [
                candidate
                for candidate in active_work_sessions(state)
                if work_session_has_running_activity(candidate)
            ]
            if running_sessions:
                blocked_by = running_sessions[0]
                report["stop_reason"] = "work_already_running"
                report["blocked_by_session_id"] = blocked_by.get("id")
                report["blocked_by_task_id"] = blocked_by.get("task_id")
                if progress:
                    progress(f"step #{index}: work session #{blocked_by.get('id')} is already running")
                break
            session = find_work_session(state, session_id)
            planning_turn = start_work_model_turn(
                state,
                session,
                {"summary": "planning work step"},
                {"summary": "planning work step"},
                {"type": "planning", "reason": "THINK/ACT in progress"},
                guidance=step_guidance,
            )
            planning_turn_id = planning_turn.get("id")
            save_state(state)
        refresh_work_follow_snapshot(args, report, session_id, task_id)
        maybe_print_work_active_cell(args, session, task, index, "model_turn", planning_turn_id)

        try:
            planned = plan_work_model_turn(
                prompt_state,
                prompt_session,
                prompt_task,
                model_auth,
                model=model,
                base_url=base_url,
                model_backend=model_backend,
                timeout=effective_args.model_timeout,
                allowed_read_roots=effective_args.allow_read or [],
                allowed_write_roots=effective_args.allow_write or [],
                allow_shell=effective_args.allow_shell,
                allow_verify=effective_args.allow_verify,
                verify_command=effective_args.verify_command or "",
                guidance=step_guidance,
                progress=progress,
                act_mode=getattr(effective_args, "act_mode", "model") or "model",
                stream_model=bool(getattr(args, "stream_model", False)),
                model_delta_sink=(
                    live_model_delta if bool(getattr(args, "stream_model", False)) else None
                ),
                progress_model_deltas=not bool(getattr(effective_args, "compact_live", False)),
            )
            flush_live_model_delta()
        except KeyboardInterrupt:
            flush_live_model_delta()
            interrupt = pause_work_session_after_user_interrupt(session_id, index)
            report["stop_reason"] = "user_interrupt"
            report["interrupted_step"] = index
            report["interrupt_note"] = interrupt.get("note")
            report["interrupt_repairs"] = interrupt.get("repairs") or []
            if progress:
                progress(f"step #{index}: interrupted by user")
            break
        except MewError as exc:
            flush_live_model_delta()
            error = str(exc)
            with state_lock():
                state = load_state()
                session = find_work_session(state, session_id)
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
            steer_consumed = (
                complete_work_session_steer(session, pending_steer, index, action_type=action_type, action=action)
                if pending_steer
                else False
            )
            followup_consumed = (
                complete_work_session_followup(session, pending_followup, index) if pending_followup else False
            )
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
            elif steer_consumed or followup_consumed:
                save_state(state)
        if pending_steer and steer_consumed and progress:
            progress(f"step #{index}: consumed steer")
        if pending_followup and followup_consumed and progress:
            progress(f"step #{index}: consumed queued follow-up")
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
            if stop_request.get("action") == "interrupt_submit" and index < max_steps:
                report.setdefault("interrupt_submits", []).append(stop_request)
                report["stop_reason"] = "max_steps"
                report.pop("stop_request", None)
                if progress:
                    progress(f"step #{index}: continuing after interrupt submit")
                continue
            break
        if getattr(args, "live", False):
            if not live_thinking_open:
                print("")
                print(f"Work live step #{index} thinking")
                print(
                    format_work_live_progress(
                        index,
                        max_steps,
                        session_id,
                        task_id,
                        phase="thinking",
                        elapsed_seconds=time.monotonic() - step_started,
                    )
                )
                live_thinking_open = True
            print(
                format_work_follow_planning(planned)
                if getattr(args, "follow", False)
                else format_work_planning(
                    planned,
                    include_stream_preview=not (getattr(effective_args, "compact_live", False) and live_model_delta_seen),
                )
            )
        if action_type == "batch":
            if getattr(args, "live", False) and not getattr(args, "follow", False):
                print("")
                print(f"Work live step #{index} action")
                print(format_work_action(action))
            try:
                batch_step = run_work_batch_action(
                    session_id,
                    task_id,
                    index,
                    planned,
                    action,
                    effective_args,
                    progress,
                    turn_id=planning_turn_id,
                )
            except KeyboardInterrupt:
                interrupt = pause_work_session_after_user_interrupt(session_id, index)
                report["stop_reason"] = "user_interrupt"
                report["interrupted_step"] = index
                report["interrupt_note"] = interrupt.get("note")
                report["interrupt_repairs"] = interrupt.get("repairs") or []
                if progress:
                    progress(f"step #{index}: interrupted by user")
                break
            report["steps"].append(batch_step)
            if batch_step.get("error"):
                report["stop_reason"] = "tool_failed"
                if getattr(args, "live", False):
                    with state_lock():
                        state = load_state()
                        session = find_work_session(state, session_id)
                        task = work_session_task(state, session)
                    resume = build_work_session_resume(session, task=task, state=state)
                    live_cells_seen = print_work_live_step_output(
                        args,
                        index,
                        batch_step,
                        resume,
                        session,
                        task,
                        live_cells_seen,
                    )
                break
            if batch_step.get("stop_request"):
                report["stop_reason"] = "stop_requested"
                report["stop_request"] = batch_step.get("stop_request")
                if getattr(args, "live", False):
                    with state_lock():
                        state = load_state()
                        session = find_work_session(state, session_id)
                        task = work_session_task(state, session)
                    resume = build_work_session_resume(session, task=task, state=state)
                    live_cells_seen = print_work_live_step_output(
                        args,
                        index,
                        batch_step,
                        resume,
                        session,
                        task,
                        live_cells_seen,
                    )
                if batch_step.get("stop_request", {}).get("action") == "interrupt_submit" and index < max_steps:
                    report.setdefault("interrupt_submits", []).append(batch_step.get("stop_request"))
                    report["stop_reason"] = "max_steps"
                    report.pop("stop_request", None)
                    continue
                break
            if batch_step.get("pending_approval"):
                pending_ids = batch_step.get("pending_approval_ids") or []
                if pending_ids and work_auto_approve_edits_enabled(effective_args):
                    approve_args = SimpleNamespace(
                        task_id=task_id,
                        approve_all=True,
                        allow_write=effective_args.allow_write or [],
                        allow_verify=effective_args.allow_verify,
                        verify_command=effective_args.verify_command or "",
                        verify_cwd=args.verify_cwd,
                        verify_timeout=effective_args.verify_timeout,
                        progress=bool(getattr(args, "progress", False) or getattr(args, "live", False)),
                        json=False,
                        allow_unpaired_source_edit=False,
                    )
                    approval_code, approval_data = _apply_work_approval_batch(approve_args, pending_ids)
                    batch_step["inline_approval"] = "auto_applied" if approval_code == 0 else "auto_failed"
                    batch_step["inline_approval_count"] = (approval_data or {}).get("count", 0)
                    batch_step["inline_approvals"] = (approval_data or {}).get("approved") or []
                    for approval in batch_step["inline_approvals"]:
                        _refresh_step_tool_call_after_approval(batch_step, (approval or {}).get("approved_tool_call"))
            if getattr(args, "live", False):
                with state_lock():
                    state = load_state()
                    session = find_work_session(state, session_id)
                    task = work_session_task(state, session)
                resume = build_work_session_resume(session, task=task, state=state)
                live_cells_seen = print_work_live_step_output(
                    args,
                    index,
                    batch_step,
                    resume,
                    session,
                    task,
                    live_cells_seen,
                )
                if not getattr(effective_args, "compact_live", False):
                    print("")
                    print(f"Work live step #{index} resume")
                    print(format_work_session_resume(resume))
            if batch_step.get("pending_approval"):
                if batch_step.get("inline_approval") == "auto_applied":
                    continue
                if batch_step.get("inline_approval") == "auto_failed":
                    report["stop_reason"] = "tool_failed"
                    break
                report["stop_reason"] = "pending_approval"
                if progress:
                    progress(f"step #{index}: pending batch write approval")
                break
            continue
        if action_type not in WORK_TOOLS:
            if getattr(args, "live", False) and not getattr(args, "follow", False):
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
                control_step = {
                    "index": index,
                    "status": "completed",
                    "action": action,
                    **control_effect,
                    "summary": (
                        (action.get("text") if action_type == "send_message" else "")
                        or (action.get("question") if action_type == "ask_user" else "")
                        or (action.get("note") if action_type == "remember" else "")
                        or action.get("reason")
                        or action.get("summary")
                        or action.get("text")
                        or action.get("question")
                        or ""
                    ),
                }
                resume = build_work_session_resume(session, task=task, state=state)
                live_cells_seen = print_work_live_step_output(
                    args,
                    index,
                    control_step,
                    resume,
                    session,
                    task,
                    live_cells_seen,
                )
                if not getattr(effective_args, "compact_live", False):
                    print("")
                    print(f"Work live step #{index} resume")
                    print(format_work_session_resume(resume))
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
                        or action.get("reason")
                        or action.get("summary")
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
            allowed_write_roots=effective_args.allow_write or [],
            allow_shell=effective_args.allow_shell,
            allow_verify=effective_args.allow_verify,
            verify_command=effective_args.verify_command or "",
            verify_timeout=effective_args.verify_timeout,
        )
        coerced_test_dry_run = _force_paired_test_steer_write_to_dry_run(
            pending_steer,
            action_type,
            parameters,
            action,
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
            if stop_request.get("action") == "interrupt_submit" and index < max_steps:
                report.setdefault("interrupt_submits", []).append(stop_request)
                report["stop_reason"] = "max_steps"
                report.pop("stop_request", None)
                if progress:
                    progress(f"step #{index}: continuing after interrupt submit")
                continue
            break
        safety_blocker = m5_self_improve_tool_execution_blocker(task, action_type, parameters)
        if safety_blocker:
            safety_action = {"type": "wait", "reason": safety_blocker}
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
                    safety_action,
                )
                turn = finish_work_model_turn(state, session_id, planning_turn_id)
                if turn is not None:
                    turn["safety_blocker"] = safety_blocker
                    turn["summary"] = clip_output(safety_blocker, 4000)
                add_work_session_note(session, f"M5 safety blocked tool execution: {safety_blocker}", source="system")
                save_state(state)
            step = {
                "index": index,
                "status": "blocked",
                "action": safety_action,
                "model_turn": turn,
                "safety_blocker": safety_blocker,
                "summary": safety_blocker,
            }
            report["steps"].append(step)
            report["stop_reason"] = "safety_blocked"
            if getattr(args, "live", False):
                with state_lock():
                    state = load_state()
                    session = find_work_session(state, session_id)
                    task = work_session_task(state, session)
                resume = build_work_session_resume(session, task=task, state=state)
                write_work_follow_snapshot(args, report, session, task, resume, step=step)
                live_cells_seen = print_work_live_step_output(
                    args,
                    index,
                    step,
                    resume,
                    session,
                    task,
                    live_cells_seen,
                )
            if progress:
                progress(f"step #{index}: safety blocked")
            break
        pairing_status = planned_unpaired_source_write_pairing_status(
            session,
            action_type,
            parameters,
            allow_unpaired=bool(getattr(effective_args, "allow_unpaired_source_edit", False)),
        )
        if pairing_status:
            steer_action = paired_test_steer_action(pairing_status)
            steer_text = steer_action["reason"]
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
                    steer_action,
                )
                steer = queue_work_session_steer(
                    session,
                    steer_text,
                    source="paired_test_steer",
                    metadata=pairing_status,
                )
                turn = finish_work_model_turn(state, session_id, planning_turn_id)
                if turn is not None:
                    turn["paired_test_steer"] = pairing_status
                    turn["pending_steer"] = steer
                    turn["summary"] = clip_output(steer_text, 4000)
                save_state(state)
            step = {
                "index": index,
                "status": "completed",
                "action": steer_action,
                "model_turn": turn,
                "pairing_status": pairing_status,
                "pending_steer": steer,
                "summary": steer_text,
            }
            report["steps"].append(step)
            if getattr(args, "live", False):
                with state_lock():
                    state = load_state()
                    session = find_work_session(state, session_id)
                    task = work_session_task(state, session)
                resume = build_work_session_resume(session, task=task, state=state)
                write_work_follow_snapshot(args, report, session, task, resume, step=step)
                live_cells_seen = print_work_live_step_output(
                    args,
                    index,
                    step,
                    resume,
                    session,
                    task,
                    live_cells_seen,
                )
                if not getattr(effective_args, "compact_live", False):
                    print("")
                    print(f"Work live step #{index} resume")
                    print(format_work_session_resume(resume))
            if progress:
                progress(f"step #{index}: paired-test steer")
            if index < max_steps:
                continue
            report["stop_reason"] = "paired_test_steer"
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
            if coerced_test_dry_run:
                turn["coerced_dry_run_reason"] = "paired_test_steer"
            repeat_guard = work_tool_repeat_guard(session, action_type, parameters)
            if repeat_guard:
                tool_call = finish_repeated_work_tool_guard(state, session, action_type, parameters, repeat_guard)
                turn["tool_call_id"] = tool_call.get("id") if tool_call else None
                turn = finish_work_model_turn(
                    state,
                    session_id,
                    planning_turn_id,
                    tool_call_id=turn["tool_call_id"],
                    error=repeat_guard.get("message") or "repeat-action guard blocked tool call",
                )
            else:
                tool_call = start_work_tool_call(state, session, action_type, parameters)
                turn["tool_call_id"] = tool_call.get("id")
            turn_id = turn.get("id")
            tool_call_id = tool_call.get("id") if tool_call else None
            save_state(state)
        if repeat_guard:
            error = repeat_guard.get("message") or "repeat-action guard blocked tool call"
            step = {
                "index": index,
                "status": "failed",
                "action": action,
                "model_turn": turn,
                "tool_call": tool_call,
                "error": error,
                "summary": error,
            }
            report["steps"].append(step)
            report["stop_reason"] = "tool_failed"
            refresh_work_follow_snapshot(args, report, session_id, task_id)
            if getattr(args, "live", False):
                with state_lock():
                    state = load_state()
                    session = find_work_session(state, session_id)
                    task = work_session_task(state, session)
                resume = build_work_session_resume(session, task=task, state=state)
                write_work_follow_snapshot(args, report, session, task, resume, step=step)
                live_cells_seen = print_work_live_step_output(
                    args,
                    index,
                    step,
                    resume,
                    session,
                    task,
                    live_cells_seen,
                )
            if progress:
                progress(f"step #{index}: tool #{tool_call_id} {action_type} repeat-guard")
            break
        refresh_work_follow_snapshot(args, report, session_id, task_id)
        maybe_print_work_active_cell(args, session, task, index, "tool_call", tool_call_id)
        if getattr(args, "live", False) and not getattr(args, "follow", False):
            print("")
            print(f"Work live step #{index} action")
            print(format_work_action(action, parameters=parameters, tool_call_id=tool_call_id))
        if progress:
            progress(f"step #{index}: tool #{tool_call_id} {action_type} start")

        try:
            result = execute_work_tool_with_output(
                action_type,
                parameters,
                effective_args.allow_read or [],
                work_tool_output_progress(
                    progress,
                    tool_call_id,
                    session_id=session_id if getattr(args, "live", False) else None,
                    on_state_update=(
                        (lambda: refresh_work_follow_snapshot(args, report, session_id, task_id))
                        if getattr(args, "live", False)
                        else None
                    ),
                ),
            )
            error = work_tool_result_error(action_type, result)
        except KeyboardInterrupt:
            interrupt = pause_work_session_after_user_interrupt(session_id, index)
            report["steps"].append(
                {
                    "index": index,
                    "status": "interrupted",
                    "action": action,
                    "error": "Interrupted by user during follow.",
                    "summary": interrupt.get("note") or "",
                }
            )
            report["stop_reason"] = "user_interrupt"
            report["interrupted_step"] = index
            report["interrupt_note"] = interrupt.get("note")
            report["interrupt_repairs"] = interrupt.get("repairs") or []
            if progress:
                progress(f"step #{index}: interrupted by user")
            break
        except (OSError, ValueError) as exc:
            result = None
            error = str(exc)

        with state_lock():
            state = load_state()
            tool_call = finish_work_tool_call(state, session_id, tool_call_id, result=result, error=error)
            if not tool_call:
                error = WORK_TOOL_RESULT_STALE_ERROR
                tool_call = _missing_finished_work_tool_call(action_type, tool_call_id, error)
            session = find_work_session(state, session_id)
            remember_successful_work_verification(session, action_type, result)
            if pending_steer and not steer_consumed:
                steer_consumed = complete_work_session_steer(
                    session,
                    pending_steer,
                    index,
                    action_type=action_type,
                    action=action,
                    result=tool_call.get("result") or {},
                )
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
        result = tool_call.get("result") or {}
        pending_approval = (
            action_type in WRITE_WORK_TOOLS
            and tool_call.get("status") == "completed"
            and result.get("dry_run")
            and result.get("changed")
            and not tool_call.get("approval_status")
        )
        if pending_approval and work_auto_approve_edits_enabled(effective_args):
            safety_blocker = m5_self_improve_auto_approval_blocker(task, tool_call)
            if safety_blocker:
                report["steps"][-1]["inline_approval"] = "safety_blocked"
                report["steps"][-1]["inline_approval_error"] = safety_blocker
            else:
                approve_args = SimpleNamespace(
                    task_id=task_id,
                    approve_tool=tool_call.get("id"),
                    allow_write=effective_args.allow_write or [],
                    allow_verify=effective_args.allow_verify,
                    verify_command=effective_args.verify_command or "",
                    verify_cwd=args.verify_cwd,
                    verify_timeout=effective_args.verify_timeout,
                    progress=bool(getattr(args, "progress", False) or getattr(args, "live", False)),
                    json=False,
                    defer_verify=False,
                    allow_unpaired_source_edit=False,
                )
                approval_code, approval_data = _apply_work_approval(approve_args, tool_call.get("id"))
                report["steps"][-1]["inline_approval"] = "auto_applied" if approval_code == 0 else "auto_failed"
                if approval_data:
                    _refresh_step_tool_call_after_approval(report["steps"][-1], approval_data.get("approved_tool_call"))
                    applied_tool = approval_data.get("tool_call") or {}
                    report["steps"][-1]["inline_approval_tool_call_id"] = applied_tool.get("id")
                    report["steps"][-1]["inline_approval_status"] = applied_tool.get("status")
        if getattr(args, "live", False):
            with state_lock():
                state = load_state()
                session = find_work_session(state, session_id)
                task = work_session_task(state, session)
            resume = build_work_session_resume(session, task=task, state=state)
            write_work_follow_snapshot(args, report, session, task, resume, step=report["steps"][-1])
            live_cells_seen = print_work_live_step_output(
                args,
                index,
                report["steps"][-1],
                resume,
                session,
                task,
                live_cells_seen,
            )
            if not getattr(effective_args, "compact_live", False):
                print("")
                print(f"Work live step #{index} resume")
                print(format_work_session_resume(resume))
        if pending_approval:
            if report["steps"][-1].get("inline_approval") == "auto_applied":
                continue
            if report["steps"][-1].get("inline_approval") == "auto_failed":
                report["stop_reason"] = "tool_failed"
                break
            if live_approval_prompt_enabled(effective_args):
                with state_lock():
                    state = load_state()
                    session = find_work_session(state, session_id)
                    task = work_session_task(state, session)
                    resume = build_work_session_resume(session, task=task, state=state)
                    stored_tool_call = find_work_tool_call(session, tool_call.get("id"))
                    approval_question = record_work_approval_elicitation(
                        state,
                        session,
                        task,
                        stored_tool_call,
                        resume=resume,
                    )
                    if approval_question:
                        report["steps"][-1]["approval_question_id"] = approval_question.get("id")
                    save_state(state)
                approval_verify_command = effective_args.verify_command or work_session_default_verify_command(session, task=task)
                approval = prompt_live_write_approval(tool_call, verify_command=approval_verify_command)
                report["steps"][-1]["inline_approval"] = approval
                if approval == "approve":
                    approve_args = SimpleNamespace(
                        task_id=task_id,
                        approve_tool=tool_call.get("id"),
                        allow_write=effective_args.allow_write or [],
                        allow_verify=effective_args.allow_verify,
                        verify_command=effective_args.verify_command or "",
                        verify_cwd=args.verify_cwd,
                        verify_timeout=effective_args.verify_timeout,
                        progress=bool(getattr(args, "progress", False) or getattr(args, "live", False)),
                        json=False,
                    )
                    approval_code = cmd_work_approve_tool(approve_args)
                    report["steps"][-1]["inline_approval"] = "applied" if approval_code == 0 else "failed"
                    if approval_code != 0:
                        report["stop_reason"] = "tool_failed"
                        break
                    continue
                if approval == "reject":
                    reject_args = SimpleNamespace(
                        task_id=task_id,
                        reject_tool=tool_call.get("id"),
                        reject_reason="inline approval rejected",
                        json=False,
                    )
                    cmd_work_reject_tool(reject_args)
                    report["steps"][-1]["inline_approval"] = "rejected"
                    report["stop_reason"] = "approval_rejected"
                    break
                if approval == "quit":
                    report["stop_reason"] = "user_quit"
                    break
            report["stop_reason"] = "pending_approval"
            if progress:
                progress(f"step #{index}: pending write approval")
            break
        if error:
            report["stop_reason"] = "tool_failed"
            break

    should_note_max_steps = (
        report.get("stop_reason") == "max_steps"
        and getattr(args, "live", False)
        and (getattr(args, "follow", False) or max_steps > 1)
    )
    if should_note_max_steps:
        mode = "follow" if getattr(args, "follow", False) else "live"
        report["max_steps_note"] = record_max_steps_reentry_note(session_id, report, mode=mode)

    if getattr(args, "live", False):
        state = load_state()
        session = find_work_session(state, session_id)
        task = work_session_task(state, session)
        resume = build_work_session_resume(session, task=task, state=state)
        write_work_follow_snapshot(args, report, session, task, resume)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(format_work_ai_report(report, compact=getattr(effective_args, "compact_live", False)))
        if getattr(args, "live", False) and not getattr(args, "suppress_cli_controls", False):
            state = load_state()
            session = find_work_session(state, session_id)
            print(format_work_cli_controls(session, args, compact=compact_cli_controls))
    if report.get("stop_reason") == "user_interrupt":
        return 130
    return 0 if report.get("stop_reason") not in (
        "model_error",
        "tool_failed",
        "no_active_session",
        "work_already_running",
    ) else 1


def _select_active_work_session_for_args(state, args):
    session = active_work_session(state)
    if getattr(args, "task_id", None):
        session = None
        for candidate in reversed(state.get("work_sessions", [])):
            task = work_session_task(state, candidate)
            if (
                str(candidate.get("task_id")) == str(args.task_id)
                and candidate.get("status") == "active"
                and (not task or task.get("status") != "done")
            ):
                session = candidate
                break
    return session


def _review_work_tools():
    return READ_ONLY_WORK_TOOLS | GIT_WORK_TOOLS


def _select_work_tool_session_for_args(state, args):
    session = _select_active_work_session_for_args(state, args)
    if session:
        return session, False
    task_id = getattr(args, "task_id", None)
    if not task_id:
        return None, False
    task = find_task(state, task_id)
    latest = _latest_work_session_for_task(state, task_id)
    if not task or not latest:
        return None, False
    if getattr(args, "tool", "") not in _review_work_tools():
        return None, False
    if latest.get("status") != "active" or task.get("status") == "done":
        return latest, True
    return None, False


def format_no_work_tool_session(state, args):
    task_id = getattr(args, "task_id", None)
    if not task_id:
        lines = ["mew: no active work session; run `mew work <task-id> --start-session`"]
        for command in no_active_work_session_one_shot_tool_commands(args):
            lines.append(f"one-shot: {command}")
        return "\n".join(lines)
    task = find_task(state, task_id)
    if not task:
        return f"mew: task not found: {task_id}"
    latest = _latest_work_session_for_task(state, task_id)
    if task.get("status") == "done":
        lines = [done_task_work_session_error(task)]
    else:
        lines = [f"mew: no active work session for task #{task_id}; run `{mew_command('work', task_id, '--start-session')}`"]
    if latest:
        lines.append(f"review: {mew_command('work', task_id, '--session', '--resume', '--allow-read', '.')}")
        lines.append(f"read-only review tools: {', '.join(sorted(_review_work_tools()))}")
    for command in no_active_work_session_one_shot_tool_commands(args):
        lines.append(f"one-shot: {command}")
    return "\n".join(lines)


def _work_session_matches_kind(state, session, kind=None):
    if not session:
        return False
    task = work_session_task(state, session)
    if task and task.get("status") == "done":
        return False
    if not kind:
        return True
    return bool(task and task_kind(task) == kind)


def active_work_session_for_kind(state, kind=None):
    if not kind:
        return active_work_session(state)
    for session in reversed(state.get("work_sessions", [])):
        if session.get("status") == "active" and _work_session_matches_kind(state, session, kind=kind):
            return session
    return None

def active_work_sessions_for_kind(state, kind=None):
    return [
        session
        for session in state.get("work_sessions", [])
        if session.get("status") == "active" and _work_session_matches_kind(state, session, kind=kind)
    ]


def active_work_session_status_items(state, kind=None):
    items = []
    for session in active_work_sessions_for_kind(state, kind=kind):
        task_id = session.get("task_id")
        calls = session.get("tool_calls") or []
        turns = session.get("model_turns") or []
        pending_ids = _pending_approval_tool_ids(session)
        task = find_task(state, task_id) if task_id is not None else None
        resume = build_work_session_resume(session, task=task, limit=3, state=state) or {}
        status_command = (
            mew_command(
                "work",
                task_id,
                "--follow-status",
                "--json",
            )
            if task_id is not None
            else mew_command("work", "--follow-status", "--json")
        )
        snapshot_path = STATE_DIR / "follow" / f"session-{session.get('id')}.json"
        follow_status = _work_follow_status_from_snapshot(snapshot_path, task_id=task_id, session=session)
        items.append(
            {
                "id": session.get("id"),
                "task_id": task_id,
                "status": session.get("status") or "",
                "phase": resume.get("phase") or work_session_phase(session, calls, turns, pending_ids),
                "title": session.get("title") or "",
                "updated_at": session.get("updated_at") or "",
                "pending_approval_count": len(pending_ids),
                "follow_status": follow_status,
                "follow_status_command": status_command,
                "continuity": resume.get("continuity") or {},
                "next_action": resume.get("next_action") or "",
                "resume_command": (
                    mew_command("work", task_id, "--session", "--resume") if task_id is not None else ""
                ),
            }
        )
    return items


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
    if getattr(args, "defer_verify", False):
        parameters["defer_verify"] = True
    return {key: value for key, value in parameters.items() if value is not None}


def _deferred_approval_rollback_snapshot(source_call, parameters):
    if not parameters.get("apply") or not parameters.get("defer_verify"):
        return None
    try:
        return snapshot_write_path(
            parameters.get("path") or "",
            parameters.get("allowed_write_roots") or [],
            create=source_call.get("tool") == "write_file" and bool(parameters.get("create")),
        )
    except (OSError, ValueError):
        return None


WORK_TOOL_RESULT_STALE_ERROR = "work tool result could not be recorded; work session changed during tool execution"


def _missing_finished_work_tool_call(tool, tool_call_id, error=WORK_TOOL_RESULT_STALE_ERROR):
    tool_name = tool or "work_tool"
    return {
        "id": tool_call_id,
        "tool": tool_name,
        "status": "failed",
        "error": error,
        "summary": f"{tool_name} failed: {error}",
    }


def _mark_work_recovery_chain(session, source_call, status, recovered_by_tool_call_id, recovered_at):
    seen = set()
    current = source_call
    while isinstance(current, dict) and current.get("id") not in seen:
        seen.add(current.get("id"))
        if not current.get("recovery_status"):
            current["recovery_status"] = status
            current["recovered_by_tool_call_id"] = recovered_by_tool_call_id
            current["recovered_at"] = recovered_at
            for turn in (session or {}).get("model_turns") or []:
                if turn.get("tool_call_id") != current.get("id"):
                    continue
                turn["recovery_status"] = status
                turn["recovered_by_tool_call_id"] = recovered_by_tool_call_id
                turn["recovered_at"] = recovered_at
        parent_id = (current.get("parameters") or {}).get("recovered_from_tool_call_id")
        current = find_work_tool_call(session, parent_id) if parent_id is not None else None


def _work_unpaired_source_approval_error(session, source_call, args):
    pairing = work_write_pairing_status(session, source_call)
    if pairing.get("status") != "missing_test_edit":
        return "", pairing
    if getattr(args, "allow_unpaired_source_edit", False):
        return "", pairing
    path = pairing.get("source_path") or "src/mew/**"
    suggestion = (
        f"; suggested test path: {pairing.get('suggested_test_path')}"
        if pairing.get("suggested_test_path")
        else ""
    )
    return (
        "src/mew source edit approval requires a paired tests/** write/edit in the same work session "
        f"before approving {path}{suggestion}; pass --allow-unpaired-source-edit to override explicitly",
        pairing,
    )


def _maybe_promote_paired_source_verify_command(session, source_call, args, task=None):
    if not session or not source_call or getattr(args, "verify_command", None):
        return {}
    defaults = session.setdefault("default_options", {})
    if defaults.get("verify_disabled"):
        return {}
    suggestion = suggested_verify_command_for_call_path(work_call_path(source_call))
    if not suggestion:
        return {}
    current = work_session_default_verify_command(session, task=task)
    if verification_command_covers_suggestion(current, suggestion):
        return {}
    command = suggestion.get("command") or ""
    if not command:
        return {}
    args.verify_command = command
    args.allow_verify = True
    defaults["allow_verify"] = True
    defaults["verify_command"] = command
    defaults["verify_disabled"] = False
    promotion = {
        "source": "paired_source_edit",
        "source_path": suggestion.get("source_path") or "",
        "test_path": suggestion.get("test_path") or "",
        "command": command,
        "previous_command": current,
        "promoted_at": now_iso(),
    }
    defaults["verify_command_promotion"] = promotion
    add_work_session_note(
        session,
        (
            "promoted default verifier for paired source edit: "
            f"{promotion['source_path']} -> {promotion['test_path']} with `{command}`"
        ),
        source="system",
    )
    return promotion


def _apply_work_approval(args, approve_tool_id):
    progress = work_tool_progress(args)
    with state_lock():
        state = load_state()
        session = _select_active_work_session_for_args(state, args)
        if not session:
            if getattr(args, "json", False):
                return 1, no_active_work_session_json(state, args=args)
            print("mew: no active work session; run `mew work <task-id> --start-session`", file=sys.stderr)
            return 1, None
        expected_updated_at = getattr(args, "expected_session_updated_at", None)
        if expected_updated_at and session.get("updated_at") != expected_updated_at:
            print("mew: reply file was based on a stale work-session snapshot", file=sys.stderr)
            return 1, None
        task = work_session_task(state, session)
        source_call = find_work_tool_call(session, approve_tool_id)
        if not source_call:
            print(f"mew: work tool call not found: {approve_tool_id}", file=sys.stderr)
            return 1, None
        if source_call.get("tool") not in ("write_file", "edit_file"):
            print("mew: only write_file/edit_file tool calls can be approved", file=sys.stderr)
            return 1, None
        result = source_call.get("result") or {}
        if not result.get("dry_run"):
            print("mew: only dry-run write/edit tool calls can be approved", file=sys.stderr)
            return 1, None
        if source_call.get("approval_status") in NON_PENDING_APPROVAL_STATUSES:
            print(f"mew: tool call is already {source_call.get('approval_status')}", file=sys.stderr)
            return 1, None
        if not result.get("changed"):
            print("mew: dry-run tool call has no changes to approve", file=sys.stderr)
            return 1, None
        pairing_error, pairing_status = _work_unpaired_source_approval_error(session, source_call, args)
        if pairing_error:
            print(f"mew: {pairing_error}", file=sys.stderr)
            return 1, None
        if pairing_status.get("status") == "missing_test_edit":
            add_work_session_note(
                session,
                (
                    "allowed unpaired source edit override for approval attempt on "
                    f"tool #{source_call.get('id')} {pairing_status.get('source_path')}"
                ),
                source="system",
            )
        if not getattr(args, "verify_command", None):
            _maybe_promote_paired_source_verify_command(session, source_call, args, task=task)
        if not getattr(args, "verify_command", None):
            inferred_verify_command = work_session_default_verify_command(session, task=task)
            if inferred_verify_command:
                args.verify_command = inferred_verify_command
                args.allow_verify = True
        auto_defer_reason = work_approval_default_defer_reason(source_call)
        if auto_defer_reason and not getattr(args, "defer_verify", False):
            args.defer_verify = True
            add_work_session_note(
                session,
                (
                    "auto-deferred verification for approval "
                    f"#{source_call.get('id')}: {auto_defer_reason}"
                ),
                source="system",
            )
        parameters = _approval_parameters_from_call(source_call, args)
        rollback_snapshot = _deferred_approval_rollback_snapshot(source_call, parameters)
        tool_call = start_work_tool_call(state, session, source_call.get("tool"), parameters)
        source_call["approval_status"] = "applying"
        source_call["approved_by_tool_call_id"] = tool_call.get("id")
        source_call["approved_at"] = now_iso()
        session_id = session.get("id")
        tool_call_id = tool_call.get("id")
        save_state(state)
    if progress:
        progress(f"approval #{approve_tool_id} -> tool #{tool_call_id} start")

    try:
        result = execute_work_tool_with_output(
            source_call.get("tool"),
            parameters,
            getattr(args, "allow_read", None) or [],
            work_tool_output_progress(progress, tool_call_id),
        )
        error = work_tool_result_error(source_call.get("tool"), result)
    except KeyboardInterrupt:
        with state_lock():
            state = load_state()
            session = find_work_session(state, session_id)
            repairs = mark_work_tool_call_interrupted(session, tool_call_id)
            source_call = find_work_tool_call(session, approve_tool_id)
            tool_call = find_work_tool_call(session, tool_call_id)
            interrupted_error = (
                "Interrupted while applying approved work tool; inspect the work-session resume before retrying."
            )
            if source_call:
                source_call["approval_status"] = APPROVAL_STATUS_INDETERMINATE
                source_call["approval_error"] = interrupted_error
            if not tool_call:
                tool_call = {
                    "id": tool_call_id,
                    "tool": source_call.get("tool") if source_call else "work_tool",
                    "status": "interrupted",
                    "error": interrupted_error,
                    "summary": "interrupted approval apply tool call",
                }
            save_state(state)
        if progress:
            progress(f"approval #{approve_tool_id} -> tool #{tool_call_id} interrupted")
        return 130, {
            "approved_tool_call": source_call,
            "tool_call": tool_call,
            "interrupted": True,
            "repairs": repairs,
        }
    except (OSError, ValueError) as exc:
        result = None
        error = str(exc)

    with state_lock():
        state = load_state()
        session = find_work_session(state, session_id)
        source_call = find_work_tool_call(session, approve_tool_id)
        tool_call = finish_work_tool_call(state, session_id, tool_call_id, result=result, error=error)
        remember_successful_work_verification(session, source_call.get("tool") if source_call else "", result)
        if not tool_call:
            stale_error = "approval result could not be recorded; work session changed during approval"
            if source_call:
                source_call["approval_status"] = APPROVAL_STATUS_INDETERMINATE
                source_call["approval_error"] = stale_error
            save_state(state)
            print(f"mew: {stale_error}", file=sys.stderr)
            return 1, None
        if source_call:
            source_call["approval_status"] = "applied" if tool_call.get("status") == "completed" else "failed"
            source_call["approval_error"] = tool_call.get("error") or ""
            if tool_call.get("status") == "completed":
                resolve_work_approval_elicitation(
                    state,
                    source_call,
                    f"Approved work tool #{approve_tool_id}.",
                )
        save_state(state)
    if progress:
        progress(f"approval #{approve_tool_id} -> tool #{tool_call_id} {tool_call.get('status')}")
    return 0 if tool_call.get("status") == "completed" else 1, {
        "approved_tool_call": source_call,
        "tool_call": tool_call,
        "rollback_snapshot": rollback_snapshot,
    }


def cmd_work_approve_tool(args):
    code, data = _apply_work_approval(args, args.approve_tool)
    if data is None:
        return code
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        tool_call = data["tool_call"]
        print(f"approved work tool #{args.approve_tool} -> #{tool_call['id']} [{tool_call['status']}]")
        print(tool_call.get("summary") or tool_call.get("error") or "")
    return code


def _pending_approval_tool_ids(session):
    ids = []
    for call in (session or {}).get("tool_calls") or []:
        if call.get("tool") not in ("write_file", "edit_file"):
            continue
        result = call.get("result") or {}
        if not result.get("dry_run") or not result.get("changed"):
            continue
        if call.get("approval_status") in NON_PENDING_APPROVAL_STATUSES:
            continue
        ids.append(call.get("id"))
    return ids


def _pending_approval_tool_ids_for_batch(session, task=None, *, promote_paired_source_verifiers=False):
    ids = _pending_approval_tool_ids(session)
    calls_by_id = {call.get("id"): call for call in (session or {}).get("tool_calls") or []}
    id_set = set(ids)
    ordered = []
    seen = set()
    for approve_id in ids:
        if approve_id in seen:
            continue
        call = calls_by_id.get(approve_id)
        pairing = work_write_pairing_status(session, call)
        paired_id = pairing.get("paired_tool_call_id")
        if paired_id in id_set and paired_id not in seen:
            ordered.append(paired_id)
            seen.add(paired_id)
        if promote_paired_source_verifiers:
            suggestion = suggested_verify_command_for_call_path(work_call_path(call))
            current = work_session_default_verify_command(session, task=task)
            if suggestion and not verification_command_covers_suggestion(current, suggestion):
                paired_id = pairing.get("paired_tool_call_id")
                if paired_id in id_set and paired_id not in seen:
                    ordered.append(paired_id)
                    seen.add(paired_id)
        ordered.append(approve_id)
        seen.add(approve_id)
    return ordered


def _deferred_verify_approval_ids_for_batch(_session, approve_ids):
    approve_ids = list(approve_ids or [])
    if len(approve_ids) <= 1:
        return set()
    return set(approve_ids[:-1])


def _rollback_deferred_approval_batch(approved, reason):
    rolled_back = []
    for approval in reversed(approved or []):
        tool_call = (approval or {}).get("tool_call") or {}
        result = tool_call.get("result") or {}
        if not result.get("verification_deferred"):
            continue
        snapshot = (approval or {}).get("rollback_snapshot")
        if not snapshot:
            continue
        rollback = None
        error = ""
        try:
            rollback = restore_write_snapshot(snapshot)
        except (OSError, ValueError) as exc:
            error = str(exc)
        with state_lock():
            state = load_state()
            session = find_work_session(state, tool_call.get("session_id"))
            stored_call = find_work_tool_call(session, tool_call.get("id"))
            if stored_call:
                stored_result = stored_call.setdefault("result", {})
                stored_result["batch_rollback_reason"] = reason
                if rollback:
                    stored_result["rollback"] = rollback
                    stored_result["rolled_back"] = True
                    stored_call["status"] = "failed"
                    stored_call["error"] = reason
                    stored_call["summary"] = f"{stored_call.get('tool')} rolled back after batch verification failed"
                else:
                    stored_result["rollback_error"] = error or "rollback snapshot unavailable"
                    stored_result["rolled_back"] = False
                    stored_call["status"] = "failed"
                    stored_call["error"] = stored_result["rollback_error"]
            for source_call in (session or {}).get("tool_calls") or []:
                if source_call.get("approved_by_tool_call_id") != tool_call.get("id"):
                    continue
                source_call["approval_status"] = "failed"
                source_call["approval_error"] = reason if rollback else error or "rollback snapshot unavailable"
            save_state(state)
        rolled_back.append(
            {
                "tool_call_id": tool_call.get("id"),
                "rolled_back": bool(rollback),
                "rollback": rollback,
                "error": error,
            }
        )
    return rolled_back


def _apply_work_approval_batch(args, approve_ids=None):
    with state_lock():
        state = load_state()
        session = _select_active_work_session_for_args(state, args)
        if not session:
            return 1, no_active_work_session_json(state, args=args) if getattr(args, "json", False) else None
        task = work_session_task(state, session)
        ordered_ids = _pending_approval_tool_ids_for_batch(
            session,
            task=task,
            promote_paired_source_verifiers=not bool(getattr(args, "verify_command", None)),
        )
    if approve_ids is not None:
        requested = set(approve_ids)
        ordered_ids = [approve_id for approve_id in ordered_ids if approve_id in requested]
    if not ordered_ids:
        return 0, {"approved": [], "count": 0}

    approved = []
    exit_code = 0
    deferred_verify_ids = _deferred_verify_approval_ids_for_batch(session, ordered_ids)
    for approve_id in ordered_ids:
        approve_args = SimpleNamespace(**vars(args))
        approve_args.approve_tool = approve_id
        approve_args.defer_verify = approve_id in deferred_verify_ids
        code, data = _apply_work_approval(approve_args, approve_id)
        if data is not None:
            approved.append(data)
        if code != 0:
            rollback_reason = f"batch verification failed after approving tool #{approve_id}"
            _rollback_deferred_approval_batch(approved, rollback_reason)
            exit_code = code
            break
    return exit_code, {"approved": approved, "count": len(approved)}


def cmd_work_approve_all(args):
    with state_lock():
        state = load_state()
        session = _select_active_work_session_for_args(state, args)
        if not session:
            if args.json:
                print(json.dumps(no_active_work_session_json(state, args=args), ensure_ascii=False, indent=2))
                return 1
            print("mew: no active work session; run `mew work <task-id> --start-session`", file=sys.stderr)
            return 1
        task = work_session_task(state, session)
        approve_ids = _pending_approval_tool_ids_for_batch(
            session,
            task=task,
            promote_paired_source_verifiers=not bool(getattr(args, "verify_command", None)),
        )
    if not approve_ids:
        if args.json:
            print(json.dumps({"approved": [], "count": 0}, ensure_ascii=False, indent=2))
        else:
            print("No pending dry-run write/edit tool calls to approve.")
        return 0

    exit_code, data = _apply_work_approval_batch(args, approve_ids)
    approved = data.get("approved") or []
    if not args.json:
        for approve_id, approval in zip(approve_ids, approved):
            tool_call = approval["tool_call"]
            print(f"approved work tool #{approve_id} -> #{tool_call['id']} [{tool_call['status']}]")
            print(tool_call.get("summary") or tool_call.get("error") or "")
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    return exit_code


def _work_reject_error(source_call):
    if not source_call:
        return "work tool call not found"
    if source_call.get("tool") not in ("write_file", "edit_file"):
        return "only write_file/edit_file tool calls can be rejected"
    result = source_call.get("result") or {}
    if not result.get("dry_run") or not result.get("changed"):
        return "only pending dry-run write/edit tool calls can be rejected"
    if source_call.get("approval_status") in NON_PENDING_APPROVAL_STATUSES:
        return f"tool call is already {source_call.get('approval_status')}"
    return ""


def reject_work_tool_call(session, source_call, reason=""):
    current_time = now_iso()
    source_call["approval_status"] = "rejected"
    source_call["rejected_at"] = current_time
    source_call["rejection_reason"] = reason or ""
    session["updated_at"] = current_time
    return source_call


def cmd_work_reject_tool(args):
    with state_lock():
        state = load_state()
        session = _select_active_work_session_for_args(state, args)
        if not session:
            if args.json:
                print(json.dumps(no_active_work_session_json(state, args=args), ensure_ascii=False, indent=2))
                return 1
            print("mew: no active work session; run `mew work <task-id> --start-session`", file=sys.stderr)
            return 1
        source_call = find_work_tool_call(session, args.reject_tool)
        if not source_call:
            print(f"mew: work tool call not found: {args.reject_tool}", file=sys.stderr)
            return 1
        reject_error = _work_reject_error(source_call)
        if reject_error:
            print(f"mew: {reject_error}", file=sys.stderr)
            return 1
        reject_work_tool_call(session, source_call, getattr(args, "reject_reason", None) or "")
        resolve_work_approval_elicitation(
            state,
            source_call,
            f"Rejected work tool #{args.reject_tool}: {getattr(args, 'reject_reason', None) or ''}".strip(),
        )
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
        if task.get("status") == "done":
            print(done_task_work_session_error(task), file=sys.stderr)
            return 1
        session, created = create_work_session(state, task)
        remember_work_session_default_options(session, args)
        if is_self_improve_task(task):
            seed_native_self_improve_session_defaults(session, task)
            seed_m5_self_improve_audit(session, task)
            seed_native_self_improve_reentry_note(session, task)
        save_state(state)
    if args.json:
        print(json.dumps({"created": created, "work_session": session}, ensure_ascii=False, indent=2))
    else:
        print(("created " if created else "reused ") + f"work session #{session['id']} for task #{task['id']}")
        print(format_work_session(session, task=task))
    return 0


def recent_work_session_summaries(state, limit=5, kind=None):
    sessions = list(state.get("work_sessions") or [])
    summaries = []
    recent = []
    for session in reversed(sessions):
        if kind and not _work_session_matches_kind(state, session, kind=kind):
            continue
        recent.append(session)
        if len(recent) >= limit:
            break
    for session in recent:
        task = work_session_task(state, session)
        resume = build_work_session_resume(session, task=task, limit=3, state=state)
        task_id = session.get("task_id")
        resume_command = (
            mew_command("work", task_id, "--session", "--resume")
            if task_id is not None
            else mew_command("work", "--session", "--resume")
        )
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


def format_no_active_work_session(state, limit=5, kind=None):
    lines = [f"No active {kind} work session." if kind else "No active work session."]
    recent = recent_work_session_summaries(state, limit=limit, kind=kind)
    if recent:
        lines.extend(["", "Recent work sessions"])
        for session in recent:
            lines.append(
                f"- #{session.get('id')} [{session.get('status')}] task=#{session.get('task_id')} "
                f"phase={session.get('phase')} {session.get('title') or ''}"
            )
            lines.append(f"  resume: {session.get('resume_command')}")
            lines.append(f"  chat: {session.get('chat_resume_command')}")
    lines.extend(
        ["", "Start or resume", f"- {mew_executable()} work <task-id> --start-session", "- /work-session start <task-id>"]
    )
    return "\n".join(lines)


def no_active_work_session_one_shot_tool_commands(args=None):
    tool = getattr(args, "tool", None) if args is not None else None
    if not tool:
        return []
    read_root = ((getattr(args, "allow_read", None) or ["."])[0]) or "."
    path = getattr(args, "path", None) or "."
    if tool == "inspect_dir":
        return [mew_command("tool", "list", path, "--root", read_root)]
    if tool == "read_file" and getattr(args, "path", None):
        return [mew_command("tool", "read", path, "--root", read_root)]
    if tool == "search_text" and getattr(args, "query", None):
        return [mew_command("tool", "search", getattr(args, "query"), path, "--root", read_root)]
    if tool == "glob" and getattr(args, "pattern", None):
        return [mew_command("tool", "glob", getattr(args, "pattern"), path, "--root", read_root)]
    return []


def no_active_work_session_json(state, args=None, limit=5, kind=None):
    task_id = getattr(args, "task_id", None) if args is not None else None
    payload = {
        "work_session": None,
        "error": "no_active_work_session",
        "message": f"No active {kind} work session." if kind else "No active work session.",
    }
    one_shot_commands = no_active_work_session_one_shot_tool_commands(args)
    if one_shot_commands:
        payload["one_shot_commands"] = one_shot_commands
    if task_id is not None:
        payload["task_id"] = str(task_id)
        payload["start_commands"] = [
            mew_command("work", task_id, "--start-session"),
            f"/work-session start {task_id}",
        ]
        return payload
    payload["recent_work_sessions"] = recent_work_session_summaries(state, limit=limit, kind=kind)
    payload["start_commands"] = [
        f"{mew_executable()} work <task-id> --start-session",
        "/work-session start <task-id>",
    ]
    return payload


def print_no_active_work_session_response(state, args=None, limit=5, kind=None):
    if getattr(args, "json", False):
        print(json.dumps(no_active_work_session_json(state, args=args, limit=limit, kind=kind), ensure_ascii=False, indent=2))
    else:
        print(f"No active {kind} work session." if kind else "No active work session.")
        for command in no_active_work_session_one_shot_tool_commands(args):
            print(f"one-shot: {command}")


def work_session_snapshot_summary(session, state):
    if not session:
        return {}
    session_id = session.get("id")
    try:
        loaded = load_snapshot(session_id, state=state)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {
            "status": "error",
            "path": str(snapshot_path(session_id)),
            "error": str(exc),
        }
    if not loaded:
        return {
            "status": "absent",
            "path": str(snapshot_path(session_id)),
        }
    snapshot = loaded.snapshot
    return {
        "status": "usable" if loaded.usable else "partial",
        "path": loaded.path,
        "session_id": snapshot.session_id,
        "task_id": snapshot.task_id,
        "saved_at": snapshot.saved_at,
        "closed_at": snapshot.closed_at,
        "continuity_score": snapshot.continuity_score,
        "continuity_status": snapshot.continuity_status,
        "drift_notes": loaded.drift_notes,
        "partial_reasons": loaded.partial_reasons,
    }


def format_work_session_snapshot_summary(summary):
    if not summary:
        return ""
    status = summary.get("status") or "unknown"
    if status == "absent":
        return "snapshot: absent"
    if status == "error":
        return f"snapshot: error error={summary.get('error') or ''}"
    drift = "; ".join(summary.get("drift_notes") or summary.get("partial_reasons") or [])
    suffix = f" drift={drift}" if drift else ""
    continuity = summary.get("continuity_score") or "-"
    return f"snapshot: {status} continuity={continuity}{suffix}"


def cmd_work_show_session(args):
    state = load_state()
    session = active_work_session(state)
    if getattr(args, "task_id", None):
        task = find_task(state, args.task_id)
        session = _latest_work_session_for_task(state, args.task_id)
    else:
        task = work_session_task(state, session)
    if getattr(args, "resume", False):
        auto_recovery = None
        auto_recovery_code = 0
        if getattr(args, "auto_recover_safe", False):
            auto_recovery_code, auto_recovery = _work_recover_safe_session(args)
            state = load_state()
            if getattr(args, "task_id", None):
                task = find_task(state, args.task_id)
                session = _latest_work_session_for_task(state, args.task_id)
            else:
                session = active_work_session(state)
                task = work_session_task(state, session)
        resume = build_work_session_resume(session, task=task, state=state)
        if resume and getattr(args, "allow_read", None):
            attach_work_resume_world_state(resume, build_work_world_state(resume, args.allow_read))
        snapshot_summary = work_session_snapshot_summary(session, state) if resume else {}
        if not resume and not getattr(args, "task_id", None):
            if args.json:
                payload = {
                    "resume": None,
                    "recent_work_sessions": recent_work_session_summaries(state),
                    "start_commands": [
                        f"{mew_executable()} work <task-id> --start-session",
                        "/work-session start <task-id>",
                    ],
                }
                if auto_recovery is not None:
                    payload["auto_recovery"] = auto_recovery
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                if auto_recovery is not None:
                    print("Auto recovery")
                    print_work_recovery_report(auto_recovery)
                    print("")
                print(format_no_active_work_session(state))
            return auto_recovery_code
        if args.json:
            payload = {
                "resume": resume,
                "snapshot": snapshot_summary,
                "next_cli_controls": work_cli_control_commands(session, args, task=task) if resume else [],
            }
            if auto_recovery is not None:
                payload["auto_recovery"] = auto_recovery
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            if auto_recovery is not None:
                print("Auto recovery")
                print_work_recovery_report(auto_recovery)
                print("")
            print(format_work_session_resume(resume))
            snapshot_text = format_work_session_snapshot_summary(snapshot_summary)
            if snapshot_text:
                print(snapshot_text)
            if resume:
                print(format_work_cli_controls(session, args, task=task))
        return auto_recovery_code
    if args.json:
        payload = {"work_session": session}
        if not session:
            if getattr(args, "task_id", None):
                payload["task_id"] = args.task_id
                payload["start_commands"] = [
                    mew_command("work", args.task_id, "--start-session"),
                    f"/work-session start {args.task_id}",
                ]
            else:
                payload["recent_work_sessions"] = recent_work_session_summaries(state)
                payload["start_commands"] = [
                    f"{mew_executable()} work <task-id> --start-session",
                    "/work-session start <task-id>",
                ]
        elif session:
            if getattr(args, "timeline", False):
                payload["timeline"] = build_work_session_timeline(session, limit=getattr(args, "limit", 20))
            if getattr(args, "diffs", False):
                payload["diffs"] = build_work_session_diff_entries(session, limit=getattr(args, "limit", 8))
            if getattr(args, "tests", False):
                payload["tests"] = build_work_session_test_entries(session, limit=getattr(args, "limit", 8))
            if getattr(args, "commands", False):
                payload["commands"] = build_work_session_command_entries(session, limit=getattr(args, "limit", 8))
            if getattr(args, "cells", False):
                payload["cells"] = build_work_session_cells(
                    session,
                    limit=getattr(args, "limit", 20),
                    tail_max_lines=getattr(args, "cell_tail_lines", None),
                )
            payload["next_cli_controls"] = work_cli_control_commands(session, args, task=task)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        if not session and not getattr(args, "task_id", None):
            print(format_no_active_work_session(state))
        elif any(getattr(args, name, False) for name in ("timeline", "diffs", "tests", "commands", "cells")):
            if not session:
                print(format_no_active_work_session(state))
                return 0
            panes = []
            if getattr(args, "timeline", False):
                panes.append(format_work_session_timeline(session, task=task, limit=getattr(args, "limit", 20)))
            if getattr(args, "diffs", False):
                panes.append(format_work_session_diffs(session, task=task, limit=getattr(args, "limit", 8)))
            if getattr(args, "tests", False):
                panes.append(format_work_session_tests(session, task=task, limit=getattr(args, "limit", 8)))
            if getattr(args, "commands", False):
                panes.append(
                    format_work_session_commands(
                        session,
                        task=task,
                        limit=getattr(args, "limit", 8),
                        include_tests=not getattr(args, "tests", False),
                    )
                )
            if getattr(args, "cells", False):
                panes.append(
                    format_work_session_cells(
                        session,
                        task=task,
                        limit=getattr(args, "limit", 20),
                        tail_max_lines=getattr(args, "cell_tail_lines", None),
                    )
                )
            print("\n\n".join(panes))
            print(format_work_cli_controls(session, args, task=task))
        else:
            print(format_work_session(session, task=task, details=getattr(args, "details", False)))
            print(format_work_cli_controls(session, args, task=task))
    return 0


def cmd_work_close_session(args):
    snapshot_file = None
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
            print_no_active_work_session_response(state, args)
            return 0
        close_work_session(session)
        save_state(state)
        snapshot_file = save_snapshot(take_snapshot(session["id"], state=state))
    if args.json:
        print(json.dumps({"work_session": session, "snapshot_path": str(snapshot_file)}, ensure_ascii=False, indent=2))
    else:
        print(f"closed work session #{session['id']}")
        print(f"snapshot saved: {snapshot_file}")
    return 0


def cmd_work_stop_session(args):
    with state_lock():
        state = load_state()
        session = _select_active_work_session_for_args(state, args)
        if not session:
            print_no_active_work_session_response(state, args)
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
        if not session and getattr(args, "task_id", None):
            session = _latest_work_session_for_task(state, args.task_id)
        if not session:
            print_no_active_work_session_response(state, args)
            return 0
        note = add_work_session_note(session, text, source="user")
        save_state(state)
    if args.json:
        print(json.dumps({"work_note": note, "work_session": session}, ensure_ascii=False, indent=2))
    else:
        print(f"recorded work session note #{session['id']}: {note['text']}")
    return 0


def _coerce_work_reply_text(value):
    if isinstance(value, dict):
        value = value.get("text") or value.get("guidance") or value.get("reason") or ""
    if value is None:
        return ""
    return str(value).strip()


def _coerce_work_reply_list(value):
    if value is None or value == "":
        return []
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()]


def _coerce_work_reply_bool(value, field):
    if value is None or value == "":
        return False
    if isinstance(value, bool):
        return value
    raise MewError(f"reply {field} must be a boolean true/false value")


def _reject_reply_verify_overrides(raw):
    raw = raw if isinstance(raw, dict) else {}
    blocked = [key for key in ("verify_command", "verify_cwd", "verify_timeout") if raw.get(key) not in (None, "")]
    if blocked:
        raise MewError(
            "reply approve actions cannot set verification commands; "
            "use an existing session default or pass CLI --allow-verify/--verify-command"
        )


def _normalize_work_reply_actions(payload):
    actions = []
    raw_actions = payload.get("actions")
    if raw_actions is not None:
        if not isinstance(raw_actions, list):
            raise MewError("reply actions must be a list")
        for raw in raw_actions:
            if not isinstance(raw, dict):
                raise MewError("reply action entries must be objects")
            action_type = str(raw.get("type") or raw.get("action") or "").strip()
            if action_type in ("steer", "guidance"):
                text = _coerce_work_reply_text(raw.get("text") or raw.get("guidance"))
                actions.append({"type": "steer", "text": text})
            elif action_type in ("followup", "follow_up", "queue", "queue_followup"):
                text = _coerce_work_reply_text(raw.get("text") or raw.get("message") or raw.get("followup"))
                actions.append({"type": "followup", "text": text})
            elif action_type in ("interrupt", "interrupt_submit"):
                text = _coerce_work_reply_text(raw.get("text") or raw.get("message") or raw.get("submit"))
                actions.append({"type": "interrupt_submit", "text": text})
            elif action_type in ("note", "session_note"):
                text = _coerce_work_reply_text(raw.get("text") or raw.get("note"))
                actions.append({"type": "note", "text": text})
            elif action_type == "stop":
                reason = _coerce_work_reply_text(raw.get("reason") or raw.get("text"))
                actions.append({"type": "stop", "reason": reason})
            elif action_type == "reject":
                tool_call_id = raw.get("tool_call_id") or raw.get("tool") or raw.get("id")
                reason = _coerce_work_reply_text(raw.get("reason") or raw.get("text"))
                actions.append({"type": "reject", "tool_call_id": tool_call_id, "reason": reason})
            elif action_type == "approve":
                _reject_reply_verify_overrides(raw)
                tool_call_id = raw.get("tool_call_id") or raw.get("tool") or raw.get("id")
                actions.append(
                    {
                        "type": "approve",
                        "tool_call_id": tool_call_id,
                        "allow_write": _coerce_work_reply_list(raw.get("allow_write") or raw.get("allow_write_roots")),
                        "allow_unpaired_source_edit": _coerce_work_reply_bool(
                            raw.get("allow_unpaired_source_edit"),
                            "allow_unpaired_source_edit",
                        ),
                        "defer_verify": _coerce_work_reply_bool(raw.get("defer_verify"), "defer_verify"),
                    }
                )
            elif action_type in ("approve_all", "approve-all"):
                _reject_reply_verify_overrides(raw)
                actions.append(
                    {
                        "type": "approve_all",
                        "allow_write": _coerce_work_reply_list(raw.get("allow_write") or raw.get("allow_write_roots")),
                        "allow_unpaired_source_edit": _coerce_work_reply_bool(
                            raw.get("allow_unpaired_source_edit"),
                            "allow_unpaired_source_edit",
                        ),
                    }
                )
            else:
                raise MewError(f"unsupported reply action type: {action_type or '(missing)'}")
    steer = _coerce_work_reply_text(payload.get("steer") or payload.get("pending_steer"))
    if steer:
        actions.append({"type": "steer", "text": steer})
    followup = _coerce_work_reply_text(
        payload.get("followup") or payload.get("follow_up") or payload.get("queued_followup")
    )
    if followup:
        actions.append({"type": "followup", "text": followup})
    interrupt_submit = _coerce_work_reply_text(payload.get("interrupt_submit") or payload.get("interrupt"))
    if interrupt_submit:
        actions.append({"type": "interrupt_submit", "text": interrupt_submit})
    note = _coerce_work_reply_text(payload.get("note") or payload.get("session_note"))
    if note:
        actions.append({"type": "note", "text": note})
    if payload.get("stop") or payload.get("stop_reason"):
        stop_value = payload.get("stop_reason") if payload.get("stop_reason") is not None else payload.get("stop")
        reason = "" if stop_value is True else _coerce_work_reply_text(stop_value)
        actions.append({"type": "stop", "reason": reason})
    reject = payload.get("reject")
    if reject or payload.get("reject_tool"):
        if isinstance(reject, dict):
            tool_call_id = reject.get("tool_call_id") or reject.get("tool") or reject.get("id")
            reason = _coerce_work_reply_text(reject.get("reason") or reject.get("text"))
        else:
            tool_call_id = payload.get("reject_tool") or reject
            reason = _coerce_work_reply_text(payload.get("reject_reason"))
        actions.append({"type": "reject", "tool_call_id": tool_call_id, "reason": reason})
    approve = payload.get("approve")
    if approve or payload.get("approve_tool"):
        if isinstance(approve, dict):
            _reject_reply_verify_overrides(approve)
            tool_call_id = approve.get("tool_call_id") or approve.get("tool") or approve.get("id")
            allow_write = _coerce_work_reply_list(approve.get("allow_write") or approve.get("allow_write_roots"))
            allow_unpaired = _coerce_work_reply_bool(
                approve.get("allow_unpaired_source_edit"),
                "allow_unpaired_source_edit",
            )
            defer_verify = _coerce_work_reply_bool(approve.get("defer_verify"), "defer_verify")
        else:
            _reject_reply_verify_overrides(payload)
            tool_call_id = payload.get("approve_tool") or approve
            allow_write = _coerce_work_reply_list(payload.get("allow_write") or payload.get("allow_write_roots"))
            allow_unpaired = _coerce_work_reply_bool(
                payload.get("allow_unpaired_source_edit"),
                "allow_unpaired_source_edit",
            )
            defer_verify = _coerce_work_reply_bool(payload.get("defer_verify"), "defer_verify")
        actions.append(
            {
                "type": "approve",
                "tool_call_id": tool_call_id,
                "allow_write": allow_write,
                "allow_unpaired_source_edit": allow_unpaired,
                "defer_verify": defer_verify,
            }
        )
    if payload.get("approve_all"):
        approve_all = payload.get("approve_all")
        if isinstance(approve_all, dict):
            _reject_reply_verify_overrides(approve_all)
            allow_write = _coerce_work_reply_list(approve_all.get("allow_write") or approve_all.get("allow_write_roots"))
            allow_unpaired = _coerce_work_reply_bool(
                approve_all.get("allow_unpaired_source_edit"),
                "allow_unpaired_source_edit",
            )
        else:
            _reject_reply_verify_overrides(payload)
            allow_write = _coerce_work_reply_list(payload.get("allow_write") or payload.get("allow_write_roots"))
            allow_unpaired = _coerce_work_reply_bool(
                payload.get("allow_unpaired_source_edit"),
                "allow_unpaired_source_edit",
            )
        actions.append(
            {
                "type": "approve_all",
                "allow_write": allow_write,
                "allow_unpaired_source_edit": allow_unpaired,
            }
        )
    for action in actions:
        if action["type"] in ("steer", "followup", "interrupt_submit", "note") and not action.get("text"):
            raise MewError(f"reply {action['type']} action requires text")
        if action["type"] in ("reject", "approve"):
            try:
                action["tool_call_id"] = int(action.get("tool_call_id"))
            except (TypeError, ValueError) as exc:
                raise MewError(f"reply {action['type']} action requires tool_call_id") from exc
    if not actions:
        raise MewError("reply file has no supported actions")
    return actions


def _active_work_sessions_for_reply(state):
    sessions = []
    for candidate in state.get("work_sessions", []):
        task = work_session_task(state, candidate)
        if candidate.get("status") == "active" and (not task or task.get("status") != "done"):
            sessions.append(candidate)
    return sessions


def _work_reply_supported_actions():
    return [
        {
            "type": "steer",
            "description": "queue one-shot guidance for the next live/follow step",
            "required": ["text"],
        },
        {
            "type": "followup",
            "description": "queue FIFO user input for a later live/follow step",
            "required": ["text"],
        },
        {
            "type": "interrupt_submit",
            "description": "stop at the next boundary and submit text as the next step",
            "required": ["text"],
        },
        {"type": "note", "description": "record durable observer context", "required": ["text"]},
        {"type": "stop", "description": "request a stop at the next model/tool boundary", "required": []},
        {
            "type": "reject",
            "description": "reject a pending dry-run write_file/edit_file tool call",
            "required": ["tool_call_id"],
        },
        {
            "type": "approve",
            "description": "approve and apply a pending dry-run write_file/edit_file tool call",
            "required": ["tool_call_id"],
            "optional": ["allow_write", "allow_unpaired_source_edit", "defer_verify"],
        },
        {
            "type": "approve_all",
            "description": "approve and apply all pending dry-run write_file/edit_file tool calls",
            "required": [],
            "optional": ["allow_write", "allow_unpaired_source_edit"],
        },
    ]


def _work_reply_template(session=None, resume=None):
    task_id = (session or {}).get("task_id")
    session_id = (session or {}).get("id")
    observed = (session or {}).get("updated_at")
    pending_approvals = (resume or {}).get("pending_approvals") or []
    blocked_source_approval = next(
        (
            approval
            for approval in pending_approvals
            if ((approval or {}).get("pairing_status") or {}).get("status") == "missing_test_edit"
        ),
        {},
    )
    first_approval = blocked_source_approval or ((pending_approvals[0] or {}) if pending_approvals else {})
    first_approval_id = first_approval.get("tool_call_id")
    if not blocked_source_approval and (resume or {}).get("approve_all_blocked_reason"):
        actions = [
            {
                "type": "steer",
                "text": (
                    "Inspect the work-session resume before approving: at least one hidden src/mew source edit "
                    "needs a paired tests/** write/edit or an explicit unpaired override."
                ),
            }
        ]
    elif first_approval_id not in (None, ""):
        pairing = first_approval.get("pairing_status") or {}
        if pairing.get("status") == "missing_test_edit":
            path = pairing.get("source_path") or first_approval.get("path") or "src/mew/**"
            suggestion = (
                f" Suggested test path: {pairing.get('suggested_test_path')}."
                if pairing.get("suggested_test_path")
                else ""
            )
            actions = [
                {
                    "type": "steer",
                    "text": (
                        f"Add a paired tests/** write/edit before approving tool #{first_approval_id} for {path}; "
                        "only set allow_unpaired_source_edit=true if this source-only edit is intentional."
                        f"{suggestion}"
                    ),
                }
            ]
        else:
            actions = [{"type": "approve", "tool_call_id": first_approval_id}]
    else:
        actions = [{"type": "steer", "text": "<next-step guidance>"}]
    return {
        "schema_version": 1,
        "session_id": session_id,
        "task_id": task_id,
        "observed_session_updated_at": observed,
        "actions": actions,
    }


def _work_reply_file_command(task_id, reply_path):
    parts = ["work"]
    if task_id is not None:
        parts.append(task_id)
    parts.extend(["--reply-file", str(reply_path)])
    return mew_command(*parts)


def build_work_reply_schema(session=None, resume=None):
    task_id = (session or {}).get("task_id")
    session_id = (session or {}).get("id")
    observed = (session or {}).get("updated_at")
    submit_ready = bool(session_id and observed)
    reply_path = STATE_DIR / "follow" / "reply.json"
    docs_path = Path(__file__).resolve().parents[2] / "docs" / "FOLLOW_REPLY_SCHEMA.md"
    return {
        "schema_version": 1,
        "docs": "docs/FOLLOW_REPLY_SCHEMA.md",
        "docs_path": str(docs_path),
        "reply_file": str(reply_path),
        "reply_command": _work_reply_file_command(task_id, reply_path),
        "session_id": session_id,
        "task_id": task_id,
        "observed_session_updated_at": observed,
        "submit_ready": submit_ready,
        "schema_only": not submit_ready,
        "supported_actions": _work_reply_supported_actions(),
        "reply_template": _work_reply_template(session, resume=resume),
    }


def _work_follow_status_session_for_args(args, state):
    task_id = getattr(args, "task_id", None)
    if task_id:
        return _latest_work_session_for_task(state, task_id)
    return active_work_session(state)


def _work_follow_snapshot_path_for_args(args, state, session=None):
    follow_dir = STATE_DIR / "follow"
    if session is None:
        session = _work_follow_status_session_for_args(args, state)
    task_id = getattr(args, "task_id", None)
    if session and session.get("id") is not None:
        return follow_dir / f"session-{session.get('id')}.json"
    if task_id:
        return follow_dir / f"session-for-task-{task_id}.json"
    return follow_dir / "latest.json"


def work_follow_producer_health(status, heartbeat_at=None, age=None, producer_pid=None, producer_alive=False):
    reasons = {
        "absent": "no follow snapshot exists at the selected path",
        "fresh": "snapshot heartbeat is recent",
        "working": "producer process is still alive",
        "completed": "producer exited after writing a stopped snapshot",
        "dead": "producer disappeared without a stop reason",
        "stale": "snapshot heartbeat is old and no active producer is known",
    }
    return {
        "state": status,
        "heartbeat_at": heartbeat_at,
        "heartbeat_age_seconds": age,
        "producer_pid": producer_pid,
        "producer_alive": bool(producer_alive),
        "stale": status in ("absent", "dead", "stale"),
        "terminal": status == "completed",
        "reason": reasons.get(status, ""),
    }


def _work_follow_status_read_roots(session):
    roots = []
    defaults = (session or {}).get("default_options") or {}
    for root in defaults.get("allow_read") or []:
        if root and root not in roots:
            roots.append(root)
    return roots or ["."]


def _work_follow_status_refresh_command(task_id, session=None):
    parts = ["work"]
    if task_id is not None:
        parts.append(task_id)
    parts.extend(["--follow", "--max-steps", "0", "--quiet"])
    for root in _work_follow_status_read_roots(session):
        parts.extend(["--allow-read", root])
    if ((session or {}).get("default_options") or {}).get("compact_live"):
        parts.append("--compact-live")
    return mew_command(*parts)


def _work_follow_status_inspect_command(task_id, session=None):
    parts = ["work"]
    if task_id is not None:
        parts.append(task_id)
    parts.extend(["--session", "--resume"])
    for root in _work_follow_status_read_roots(session):
        parts.extend(["--allow-read", root])
    parts.append("--auto-recover-safe")
    return mew_command(*parts)


def work_follow_status_suggested_recovery(status, snapshot_data=None, task_id=None, session=None):
    snapshot_data = snapshot_data or {}
    task_id = snapshot_data.get("task_id") or task_id or (session or {}).get("task_id")
    planned = work_recovery_suggestion_from_plan(
        ((snapshot_data.get("resume") or {}).get("recovery_plan") or {}),
        task_id=task_id,
    )
    if planned:
        return planned
    if status == "absent":
        if task_id is None:
            return {
                "kind": "select_task",
                "command": mew_command("task", "list", "--json"),
                "reason": "select a task before writing a task-scoped observer snapshot",
            }
        return {
            "kind": "refresh_snapshot",
            "command": _work_follow_status_refresh_command(task_id, session=session),
            "reason": "write a fresh observer snapshot before replying",
        }
    if status in ("dead", "stale"):
        return {
            "kind": "inspect_resume",
            "command": _work_follow_status_inspect_command(task_id, session=session),
            "reason": "producer is not active; inspect the session resume and recover safe interrupted reads if present",
        }
    return {}


def _work_follow_status_session_state_newer(snapshot_updated_at, session_updated_at):
    snapshot_time = parse_time(snapshot_updated_at)
    session_time = parse_time(session_updated_at)
    if snapshot_time and session_time:
        return session_time > snapshot_time
    if snapshot_updated_at and session_updated_at:
        return str(session_updated_at) > str(snapshot_updated_at)
    return False


def _work_follow_status_from_snapshot(path, task_id=None, session=None):
    checkpoint = compact_context_checkpoint(latest_context_checkpoint())
    current_git = current_git_reentry_state()
    if not path.exists():
        status = "absent"
        return {
            "snapshot_path": str(path),
            "status": status,
            "exists": False,
            "heartbeat_at": None,
            "heartbeat_age_seconds": None,
            "producer_pid": None,
            "producer_alive": False,
            "producer_health": work_follow_producer_health(status),
            "latest_context_checkpoint": checkpoint,
            "current_git": current_git,
            "suggested_recovery": work_follow_status_suggested_recovery(status, task_id=task_id, session=session),
        }
    data = json.loads(path.read_text(encoding="utf-8"))
    heartbeat_at = data.get("heartbeat_at") or data.get("generated_at")
    heartbeat = parse_time(heartbeat_at)
    now = parse_time(now_iso())
    age = None
    if heartbeat and now:
        age = max(0.0, (now - heartbeat).total_seconds())
    producer_pid = ((data.get("producer") or {}).get("pid")) or None
    has_producer = producer_pid not in (None, "")
    producer_alive = pid_alive(producer_pid) if has_producer else False
    if age is not None and age <= 10:
        status = "fresh"
    elif producer_alive:
        status = "working"
    elif has_producer and not producer_alive and data.get("stop_reason"):
        status = "completed"
    elif has_producer and not producer_alive:
        status = "dead"
    else:
        status = "stale"
    resume = data.get("resume") or {}
    working_memory = resume.get("working_memory") or {}
    working_memory_stale = bool(
        working_memory.get("stale_after_model_turn_id") or working_memory.get("stale_after_tool_call_id")
    )
    checkpoint = compact_context_checkpoint(data.get("latest_context_checkpoint") or checkpoint)
    current_git = data.get("current_git") or current_git
    snapshot_session_updated_at = data.get("session_updated_at")
    current_session_updated_at = (session or {}).get("updated_at")
    session_state_newer = _work_follow_status_session_state_newer(
        snapshot_session_updated_at,
        current_session_updated_at,
    )
    suggested_recovery = work_follow_status_suggested_recovery(
        status,
        snapshot_data=data,
        task_id=task_id,
        session=session,
    )
    if session_state_newer and not suggested_recovery:
        recovery_task_id = data.get("task_id") or task_id or (session or {}).get("task_id")
        suggested_recovery = {
            "kind": "inspect_resume",
            "command": _work_follow_status_inspect_command(recovery_task_id, session=session),
            "reason": "current session state is newer than the follow snapshot",
        }
    return {
        "snapshot_path": str(path),
        "status": status,
        "exists": True,
        "schema_version": data.get("schema_version"),
        "mode": data.get("mode"),
        "session_id": data.get("session_id"),
        "task_id": data.get("task_id"),
        "heartbeat_at": heartbeat_at,
        "heartbeat_age_seconds": age,
        "producer_pid": producer_pid,
        "producer_alive": producer_alive,
        "producer_health": work_follow_producer_health(status, heartbeat_at, age, producer_pid, producer_alive),
        "phase": resume.get("phase") or data.get("phase") or "",
        "next_action": resume.get("next_action") or "",
        "working_memory_stale": working_memory_stale,
        "latest_context_checkpoint": checkpoint,
        "current_git": current_git,
        "suggested_recovery": suggested_recovery,
        "verification_coverage_warning": resume.get("verification_coverage_warning") or {},
        "verification_confidence": resume.get("verification_confidence") or {},
        "continuity": resume.get("continuity") or data.get("continuity") or {},
        "stop_reason": data.get("stop_reason"),
        "step_count": data.get("step_count"),
        "pending_approval_count": len(data.get("pending_approvals") or []),
        "session_updated_at": snapshot_session_updated_at,
        "current_session_updated_at": current_session_updated_at,
        "session_state_newer": session_state_newer,
    }


def _append_work_follow_status_checkpoint_lines(lines, data):
    checkpoint = data.get("latest_context_checkpoint") or {}
    if not checkpoint:
        return
    lines.append(
        f"checkpoint: {checkpoint.get('name') or checkpoint.get('key')} "
        f"({checkpoint.get('created_at') or '-'})"
    )
    current_git = data.get("current_git") or {}
    if current_git:
        lines.append(
            f"checkpoint_git: {current_git.get('status')} head={current_git.get('head') or '(unknown)'}"
        )


def format_work_follow_status(data):
    lines = [
        f"Follow snapshot status: {data.get('status')}",
        f"path: {data.get('snapshot_path')}",
    ]
    if not data.get("exists"):
        lines.append("snapshot: absent")
        _append_work_follow_status_checkpoint_lines(lines, data)
        recovery = data.get("suggested_recovery") or {}
        if recovery:
            lines.append(f"recovery: {recovery.get('kind') or '-'}")
            if recovery.get("command"):
                lines.append(f"recovery_command: {recovery.get('command')}")
        return "\n".join(lines)
    age = data.get("heartbeat_age_seconds")
    age_text = "-" if age is None else f"{age:.1f}s"
    lines.extend(
        [
            f"mode: {data.get('mode') or '-'}",
            f"session: {data.get('session_id') or '-'} task: {data.get('task_id') or '-'}",
            f"heartbeat: {data.get('heartbeat_at') or '-'} age={age_text}",
            f"producer: pid={data.get('producer_pid') or '-'} alive={bool(data.get('producer_alive'))}",
            f"pending_approvals: {data.get('pending_approval_count', 0)}",
            f"phase: {data.get('phase') or '-'}",
            f"steps: {data.get('step_count') if data.get('step_count') is not None else '-'}",
        ]
    )
    if data.get("stop_reason"):
        lines.append(f"stop_reason: {data.get('stop_reason')}")
    if data.get("session_state_newer"):
        lines.append(
            "session_state: newer_than_snapshot "
            f"current={data.get('current_session_updated_at') or '-'} "
            f"snapshot={data.get('session_updated_at') or '-'}"
        )
    producer_health = data.get("producer_health") or {}
    if producer_health:
        health_line = f"producer_health: {producer_health.get('state') or '-'}"
        if producer_health.get("reason"):
            health_line += f" ({producer_health.get('reason')})"
        lines.append(health_line)
    if data.get("working_memory_stale"):
        lines.append("working_memory: stale")
    if data.get("next_action"):
        lines.append(f"next_action: {data.get('next_action')}")
    _append_work_follow_status_checkpoint_lines(lines, data)
    recovery = data.get("suggested_recovery") or {}
    if recovery:
        lines.append(f"recovery: {recovery.get('kind') or '-'}")
        if recovery.get("command"):
            lines.append(f"recovery_command: {recovery.get('command')}")
    coverage_warning = data.get("verification_coverage_warning") or {}
    if coverage_warning:
        lines.append(_format_verification_coverage_warning_inline(coverage_warning))
    verification_confidence = data.get("verification_confidence") or {}
    if verification_confidence and verification_confidence.get("status") != "verified":
        lines.append(_format_verification_confidence_inline(verification_confidence))
    continuity_text = format_work_continuity_inline(data.get("continuity") or {})
    if continuity_text:
        lines.append(continuity_text)
    continuity_next = format_work_continuity_recommendation(data.get("continuity") or {})
    if continuity_next:
        lines.append(continuity_next)
    return "\n".join(lines)


def cmd_work_follow_status(args):
    try:
        state = load_state()
        session = _work_follow_status_session_for_args(args, state)
        path = _work_follow_snapshot_path_for_args(args, state, session=session)
        data = _work_follow_status_from_snapshot(path, task_id=getattr(args, "task_id", None), session=session)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"mew: invalid follow snapshot: {exc}", file=sys.stderr)
        return 1
    if getattr(args, "json", False):
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(format_work_follow_status(data))
    return 0 if data.get("status") != "absent" else 1


def format_work_reply_schema(data):
    lines = [
        "Follow reply schema v1",
        f"docs: {data.get('docs')}",
        f"reply_file: {data.get('reply_file')}",
        f"reply_command: {data.get('reply_command')}",
        f"session_id: {data.get('session_id') or '-'}",
        f"task_id: {data.get('task_id') or '-'}",
        f"observed_session_updated_at: {data.get('observed_session_updated_at') or '-'}",
        f"submit_ready: {bool(data.get('submit_ready'))}",
        "",
        "Supported actions",
    ]
    for action in data.get("supported_actions") or []:
        required = ", ".join(action.get("required") or []) or "-"
        lines.append(f"- {action.get('type')}: {action.get('description')} (required: {required})")
    lines.extend(
        [
            "",
            "Reply template",
            json.dumps(data.get("reply_template") or {}, ensure_ascii=False, indent=2),
        ]
    )
    return "\n".join(lines)


def cmd_work_reply_schema(args):
    state = load_state()
    session = _select_active_work_session_for_args(state, args)
    data = build_work_reply_schema(session)
    if getattr(args, "json", False):
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(format_work_reply_schema(data))
    return 0


def _work_approve_error(source_call):
    if not source_call:
        return "work tool call not found"
    if source_call.get("tool") not in ("write_file", "edit_file"):
        return "only write_file/edit_file tool calls can be approved"
    result = source_call.get("result") or {}
    if not result.get("dry_run"):
        return "only dry-run write/edit tool calls can be approved"
    if source_call.get("approval_status") in NON_PENDING_APPROVAL_STATUSES:
        return f"tool call is already {source_call.get('approval_status')}"
    if not result.get("changed"):
        return "dry-run tool call has no changes to approve"
    return ""


def _reply_approval_write_roots(session, source_call, action):
    roots = list(action.get("allow_write") or [])
    if roots:
        return roots
    roots = list(((session or {}).get("default_options") or {}).get("allow_write") or [])
    if roots:
        return roots
    result = (source_call or {}).get("result") or {}
    parameters = (source_call or {}).get("parameters") or {}
    path = result.get("path") or parameters.get("path") or ""
    return [path] if path else []


def _reply_approval_args(args, session, source_call, action):
    approval_args = SimpleNamespace(**vars(args))
    approval_args.task_id = str(session.get("task_id")) if session and session.get("task_id") is not None else None
    approval_args.allow_write = _reply_approval_write_roots(session, source_call, action)
    approval_args.allow_read = getattr(args, "allow_read", None) or []
    approval_args.allow_verify = bool(getattr(args, "allow_verify", False))
    approval_args.verify_command = getattr(args, "verify_command", None)
    approval_args.verify_cwd = getattr(args, "verify_cwd", None) or "."
    approval_args.verify_timeout = getattr(args, "verify_timeout", None)
    approval_args.allow_unpaired_source_edit = bool(action.get("allow_unpaired_source_edit"))
    approval_args.defer_verify = bool(action.get("defer_verify"))
    approval_args.progress = False
    approval_args.json = False
    return approval_args


def _apply_work_reply_approval_action(args, session_id, action, expected_updated_at=None):
    approved = []
    approval_records = []
    with state_lock():
        state = load_state()
        session = find_work_session(state, session_id)
        if not session or session.get("status") != "active":
            print("mew: no active work session for reply approval", file=sys.stderr)
            return 1, approved
        if action["type"] == "approve_all":
            task = work_session_task(state, session)
            approve_ids = _pending_approval_tool_ids_for_batch(
                session,
                task=task,
                promote_paired_source_verifiers=not bool(getattr(args, "verify_command", None)),
            )
        else:
            approve_ids = [action["tool_call_id"]]
        deferred_verify_ids = (
            _deferred_verify_approval_ids_for_batch(session, approve_ids)
            if action["type"] == "approve_all"
            else set()
        )

    for approve_id in approve_ids:
        with state_lock():
            state = load_state()
            session = find_work_session(state, session_id)
            source_call = find_work_tool_call(session, approve_id)
            approval_error = _work_approve_error(source_call)
            if approval_error:
                print(f"mew: {approval_error}", file=sys.stderr)
                return 1, approved
            approval_args = _reply_approval_args(args, session, source_call, action)
            approval_args.defer_verify = bool(action.get("defer_verify")) or approve_id in deferred_verify_ids
            approval_args.expected_session_updated_at = expected_updated_at
        code, data = _apply_work_approval(approval_args, approve_id)
        if data is not None:
            approval_records.append(data)
            tool_call = data["tool_call"]
            approved.append(
                {
                    "type": "approve",
                    "tool_call_id": approve_id,
                    "applied_tool_call_id": tool_call.get("id"),
                    "status": tool_call.get("status"),
                    "summary": tool_call.get("summary") or tool_call.get("error") or "",
                }
            )
        if code != 0:
            if action["type"] == "approve_all":
                rollback_reason = f"batch verification failed after approving tool #{approve_id}"
                _rollback_deferred_approval_batch(approval_records, rollback_reason)
            return code, approved
        with state_lock():
            state = load_state()
            session = find_work_session(state, session_id)
            expected_updated_at = (session or {}).get("updated_at")
    if action["type"] == "approve_all":
        return 0, [{"type": "approve_all", "count": len(approved), "approved": approved}]
    return 0, approved


def cmd_work_reply_file(args):
    path = Path(getattr(args, "reply_file", "") or "")
    if not path.exists():
        print(f"mew: reply file not found: {path}", file=sys.stderr)
        return 1
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"mew: invalid reply file: {exc}", file=sys.stderr)
        return 1
    if not isinstance(payload, dict):
        print("mew: reply file must contain a JSON object", file=sys.stderr)
        return 1
    if payload.get("schema_version") != 1:
        print("mew: reply file requires schema_version 1", file=sys.stderr)
        return 1
    if not payload.get("observed_session_updated_at"):
        print("mew: reply file requires observed_session_updated_at", file=sys.stderr)
        return 1
    try:
        actions = _normalize_work_reply_actions(payload)
    except MewError as exc:
        print(f"mew: {exc}", file=sys.stderr)
        return 1

    reply_task_id = payload.get("task_id")
    cli_task_id = getattr(args, "task_id", None)
    if cli_task_id and reply_task_id is not None and str(cli_task_id) != str(reply_task_id):
        print("mew: reply task_id does not match command task_id", file=sys.stderr)
        return 1
    reply_session_id = payload.get("session_id")
    observed_session_updated_at = payload.get("observed_session_updated_at")
    select_args = SimpleNamespace(**vars(args))
    if not getattr(select_args, "task_id", None) and reply_task_id is not None:
        select_args.task_id = str(reply_task_id)

    applied = []
    deferred_approval_actions = []
    session_id = None
    approval_expected_updated_at = None
    with state_lock():
        state = load_state()
        session = None
        if reply_session_id is not None:
            session = find_work_session(state, reply_session_id)
            task = work_session_task(state, session)
            if not session or session.get("status") != "active" or (task and task.get("status") == "done"):
                if getattr(args, "json", False):
                    print(
                        json.dumps(
                            {"applied": False, "reason": "no_active_work_session", "session_id": reply_session_id},
                            ensure_ascii=False,
                            indent=2,
                        )
                    )
                else:
                    print("mew: no active work session for reply file", file=sys.stderr)
                return 1
        elif not getattr(select_args, "task_id", None):
            active_sessions = _active_work_sessions_for_reply(state)
            if len(active_sessions) > 1:
                if getattr(args, "json", False):
                    print(
                        json.dumps(
                            {
                                "error": "multiple_active_work_sessions",
                                "active_work_sessions": [
                                    {"session_id": item.get("id"), "task_id": item.get("task_id")}
                                    for item in active_sessions[-5:]
                                ],
                            },
                            ensure_ascii=False,
                            indent=2,
                        )
                    )
                else:
                    print("Multiple active work sessions; include task_id in the reply file or command:")
                    for item in active_sessions[-5:]:
                        print(f"- {mew_command('work', item.get('task_id'), '--reply-file', str(path))}")
                return 1
        if not session:
            session = _select_active_work_session_for_args(state, select_args)
        if not session:
            if getattr(args, "json", False):
                print(
                    json.dumps(
                        {"applied": False, "reason": "no_active_work_session"},
                        ensure_ascii=False,
                        indent=2,
                    )
                )
            else:
                print("mew: no active work session for reply file", file=sys.stderr)
            return 1
        if cli_task_id and str(session.get("task_id")) != str(cli_task_id):
            print("mew: reply session_id does not match command task_id", file=sys.stderr)
            return 1
        if reply_task_id is not None and str(session.get("task_id")) != str(reply_task_id):
            print("mew: reply session_id does not match reply task_id", file=sys.stderr)
            return 1
        if observed_session_updated_at and session.get("updated_at") != observed_session_updated_at:
            if getattr(args, "json", False):
                print(
                    json.dumps(
                        {
                            "applied": False,
                            "reason": "stale_session_snapshot",
                            "observed_session_updated_at": observed_session_updated_at,
                            "current_session_updated_at": session.get("updated_at"),
                        },
                        ensure_ascii=False,
                        indent=2,
                    )
                )
            else:
                print("mew: reply file was based on a stale work-session snapshot", file=sys.stderr)
            return 1

        for action in actions:
            if action["type"] == "reject":
                source_call = find_work_tool_call(session, action["tool_call_id"])
                if not source_call:
                    print(f"mew: work tool call not found: {action['tool_call_id']}", file=sys.stderr)
                    return 1
                reject_error = _work_reject_error(source_call)
                if reject_error:
                    print(f"mew: {reject_error}", file=sys.stderr)
                    return 1
            elif action["type"] == "approve":
                source_call = find_work_tool_call(session, action["tool_call_id"])
                approval_error = _work_approve_error(source_call)
                if approval_error:
                    print(f"mew: {approval_error}", file=sys.stderr)
                    return 1

        for action in actions:
            if action["type"] == "steer":
                steer = queue_work_session_steer(session, action["text"], source="reply_file")
                applied.append({"type": "steer", "text": steer.get("text")})
            elif action["type"] == "followup":
                followup = queue_work_session_followup(session, action["text"], source="reply_file")
                applied.append({"type": "followup", "id": followup.get("id"), "text": followup.get("text")})
            elif action["type"] == "interrupt_submit":
                stop_request, steer = request_work_session_interrupt_submit(
                    session,
                    action["text"],
                    source="reply_file",
                )
                applied.append(
                    {
                        "type": "interrupt_submit",
                        "text": steer.get("text"),
                        "reason": stop_request.get("reason"),
                    }
                )
            elif action["type"] == "note":
                note = add_work_session_note(session, action["text"], source="reply_file")
                applied.append({"type": "note", "text": note.get("text")})
            elif action["type"] == "stop":
                request_work_session_stop(session, reason=action.get("reason") or "reply file requested stop")
                applied.append({"type": "stop", "reason": session.get("stop_reason") or ""})
            elif action["type"] == "reject":
                source_call = find_work_tool_call(session, action["tool_call_id"])
                reject_work_tool_call(session, source_call, action.get("reason") or "")
                applied.append(
                    {
                        "type": "reject",
                        "tool_call_id": source_call.get("id"),
                        "reason": source_call.get("rejection_reason") or "",
                    }
                )
            elif action["type"] in ("approve", "approve_all"):
                deferred_approval_actions.append(action)
        save_state(state)
        session_id = session.get("id")
        approval_expected_updated_at = session.get("updated_at")

    for action in deferred_approval_actions:
        code, approved = _apply_work_reply_approval_action(
            select_args,
            session_id,
            action,
            expected_updated_at=approval_expected_updated_at,
        )
        applied.extend(approved)
        if code != 0:
            return code
        with state_lock():
            state = load_state()
            session = find_work_session(state, session_id)
            approval_expected_updated_at = (session or {}).get("updated_at")

    with state_lock():
        state = load_state()
        session = find_work_session(state, session_id)
        task = work_session_task(state, session)
        resume = build_work_session_resume(session, task=task, state=state)
    snapshot_step = {
        "status": "completed",
        "action": {"type": "reply_file", "path": str(path)},
        "summary": f"applied {len(applied)} reply action(s)",
        "applied": applied,
    }
    write_work_follow_snapshot(
        select_args,
        {"stop_reason": "reply_file", "steps": [snapshot_step]},
        session,
        task,
        resume,
        step=snapshot_step,
        force=True,
        mode="reply_file",
    )
    if getattr(args, "json", False):
        print(
            json.dumps(
                {"work_session_id": session.get("id"), "applied": applied, "work_session": session},
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(f"applied reply file to work session #{session['id']}:")
        for action in applied:
            if action["type"] == "reject":
                print(f"- rejected tool #{action['tool_call_id']}: {action.get('reason') or '(no reason)'}")
            elif action["type"] == "approve":
                print(
                    f"- approved tool #{action['tool_call_id']} -> "
                    f"#{action.get('applied_tool_call_id')} [{action.get('status')}]"
                )
            elif action["type"] == "approve_all":
                print(f"- approve_all: approved {action.get('count', 0)} tool(s)")
            elif action["type"] == "stop":
                print(f"- stop: {action.get('reason') or '(no reason)'}")
            else:
                print(f"- {action['type']}: {action.get('text') or ''}")
    return 0


def cmd_work_steer(args):
    text = (getattr(args, "steer", None) or "").strip()
    if not text:
        print("mew: --steer requires text", file=sys.stderr)
        return 1
    with state_lock():
        state = load_state()
        if not getattr(args, "task_id", None):
            active_sessions = []
            for candidate in state.get("work_sessions", []):
                task = work_session_task(state, candidate)
                if candidate.get("status") == "active" and (not task or task.get("status") != "done"):
                    active_sessions.append(candidate)
            if len(active_sessions) > 1:
                if getattr(args, "json", False):
                    print(
                        json.dumps(
                            {
                                "error": "multiple_active_work_sessions",
                                "active_work_sessions": [
                                    {"session_id": item.get("id"), "task_id": item.get("task_id")}
                                    for item in active_sessions[-5:]
                                ],
                            },
                            ensure_ascii=False,
                            indent=2,
                        )
                    )
                else:
                    print("Multiple active work sessions; pass a task id:")
                    for item in active_sessions[-5:]:
                        print(f"- {mew_command('work', item.get('task_id'), '--steer')} <guidance>")
                return 1
        session = _select_active_work_session_for_args(state, args)
        if not session:
            print_no_active_work_session_response(state, args)
            return 0
        steer = queue_work_session_steer(session, text)
        save_state(state)
    if getattr(args, "json", False):
        print(json.dumps({"work_session_id": session.get("id"), "pending_steer": steer}, ensure_ascii=False, indent=2))
    else:
        print(f"queued steer for work session #{session['id']}: {steer['text']}")
    return 0


def cmd_work_queue_followup(args):
    text = (getattr(args, "queue_followup", None) or "").strip()
    if not text:
        print("mew: --queue-followup requires text", file=sys.stderr)
        return 1
    with state_lock():
        state = load_state()
        if not getattr(args, "task_id", None):
            active_sessions = _active_work_sessions_for_reply(state)
            if len(active_sessions) > 1:
                if getattr(args, "json", False):
                    print(
                        json.dumps(
                            {
                                "error": "multiple_active_work_sessions",
                                "active_work_sessions": [
                                    {"session_id": item.get("id"), "task_id": item.get("task_id")}
                                    for item in active_sessions[-5:]
                                ],
                            },
                            ensure_ascii=False,
                            indent=2,
                        )
                    )
                else:
                    print("Multiple active work sessions; pass a task id:")
                    for item in active_sessions[-5:]:
                        print(f"- {mew_command('work', item.get('task_id'), '--queue-followup')} <message>")
                return 1
        session = _select_active_work_session_for_args(state, args)
        if not session:
            print_no_active_work_session_response(state, args)
            return 0
        followup = queue_work_session_followup(session, text)
        save_state(state)
    if getattr(args, "json", False):
        print(
            json.dumps(
                {"work_session_id": session.get("id"), "queued_followup": followup},
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(f"queued follow-up for work session #{session['id']}: {followup['text']}")
    return 0


def cmd_work_interrupt_submit(args):
    text = (getattr(args, "interrupt_submit", None) or "").strip()
    if not text:
        print("mew: --interrupt-submit requires text", file=sys.stderr)
        return 1
    with state_lock():
        state = load_state()
        if not getattr(args, "task_id", None):
            active_sessions = _active_work_sessions_for_reply(state)
            if len(active_sessions) > 1:
                if getattr(args, "json", False):
                    print(
                        json.dumps(
                            {
                                "error": "multiple_active_work_sessions",
                                "active_work_sessions": [
                                    {"session_id": item.get("id"), "task_id": item.get("task_id")}
                                    for item in active_sessions[-5:]
                                ],
                            },
                            ensure_ascii=False,
                            indent=2,
                        )
                    )
                else:
                    print("Multiple active work sessions; pass a task id:")
                    for item in active_sessions[-5:]:
                        print(f"- {mew_command('work', item.get('task_id'), '--interrupt-submit')} <message>")
                return 1
        session = _select_active_work_session_for_args(state, args)
        if not session:
            print_no_active_work_session_response(state, args)
            return 0
        stop_request, steer = request_work_session_interrupt_submit(session, text, source="interrupt_submit")
        save_state(state)
    if getattr(args, "json", False):
        print(
            json.dumps(
                {
                    "work_session_id": session.get("id"),
                    "stop_request": stop_request,
                    "pending_steer": steer,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(f"interrupt-submit queued for work session #{session['id']}: {steer['text']}")
    return 0


def latest_recoverable_interrupted_call(session):
    for call in reversed(session.get("tool_calls") or []):
        if call.get("status") == "interrupted" and not call.get("recovery_status"):
            return call
    return None


def interrupted_run_tests_command(call):
    result = (call or {}).get("result") or {}
    parameters = (call or {}).get("parameters") or {}
    return result.get("command") or parameters.get("command") or ""


def recovery_commands_match(expected, requested):
    expected = expected or ""
    requested = requested or ""
    if expected == requested:
        return True
    try:
        return shlex.split(expected) == shlex.split(requested)
    except ValueError:
        return False


def interrupted_run_tests_cwd(call):
    result = (call or {}).get("result") or {}
    parameters = (call or {}).get("parameters") or {}
    return result.get("cwd") or parameters.get("cwd") or "."


def interrupted_write_verify_command(call):
    result = (call or {}).get("result") or {}
    parameters = (call or {}).get("parameters") or {}
    intent = (call or {}).get("write_intent") or {}
    return result.get("verification_command") or parameters.get("verify_command") or intent.get("verify_command") or ""


def interrupted_write_verify_cwd(call):
    result = (call or {}).get("result") or {}
    parameters = (call or {}).get("parameters") or {}
    intent = (call or {}).get("write_intent") or {}
    return result.get("verify_cwd") or parameters.get("verify_cwd") or intent.get("verify_cwd") or "."


def work_recover_verification_blocker(args, session, source_call, *, safe_only=False):
    if safe_only:
        return {
            "action": "needs_user",
            "reason": "automatic safe recovery only retries read/git tools",
            "source_tool_call_id": source_call.get("id"),
            "tool": source_call.get("tool"),
        }
    if work_session_has_pending_write_approval(session):
        return {
            "action": "needs_user",
            "reason": "resolve pending write approvals before retrying verification",
            "source_tool_call_id": source_call.get("id"),
            "tool": source_call.get("tool"),
        }
    if not getattr(args, "allow_read", None):
        return {
            "action": "needs_read_gate",
            "reason": "verification recovery needs explicit --allow-read roots for world-state review",
            "source_tool_call_id": source_call.get("id"),
            "tool": source_call.get("tool"),
            "cwd": interrupted_run_tests_cwd(source_call),
        }
    source_cwd = interrupted_run_tests_cwd(source_call)
    try:
        resolve_allowed_path(source_cwd, getattr(args, "allow_read", None) or [])
    except ValueError as exc:
        return {
            "action": "needs_read_gate",
            "reason": "verification recovery needs --allow-read to cover the interrupted verifier cwd",
            "source_tool_call_id": source_call.get("id"),
            "tool": source_call.get("tool"),
            "cwd": source_cwd,
            "allow_read": list(getattr(args, "allow_read", None) or []),
            "error": str(exc),
        }
    if not getattr(args, "allow_verify", False):
        return {
            "action": "needs_verify_gate",
            "reason": "verification recovery needs explicit --allow-verify",
            "source_tool_call_id": source_call.get("id"),
            "tool": source_call.get("tool"),
            "cwd": source_cwd,
        }
    source_command = interrupted_run_tests_command(source_call)
    requested_command = getattr(args, "verify_command", None) or getattr(args, "command", None) or ""
    if not requested_command:
        return {
            "action": "needs_verify_command",
            "reason": "verification recovery needs the interrupted command passed as --verify-command",
            "source_tool_call_id": source_call.get("id"),
            "tool": source_call.get("tool"),
            "command": source_command,
            "cwd": source_cwd,
        }
    if not recovery_commands_match(source_command, requested_command):
        return {
            "action": "needs_matching_verifier",
            "reason": "verification recovery only reruns the exact interrupted command",
            "source_tool_call_id": source_call.get("id"),
            "tool": source_call.get("tool"),
            "command": source_command,
            "requested_command": requested_command,
            "cwd": source_cwd,
        }
    return None


def work_recover_apply_write_blocker(args, source_call, recovery_item, *, safe_only=False):
    if safe_only:
        return {
            "action": "needs_user",
            "reason": "automatic safe recovery does not apply interrupted writes",
            "source_tool_call_id": source_call.get("id"),
            "tool": source_call.get("tool"),
        }
    write_state = (recovery_item or {}).get("write_world_state") or {}
    if write_state.get("state") != "not_started":
        return {
            "action": "needs_user",
            "reason": "apply-write recovery only retries when the target still matches the pre-write state",
            "source_tool_call_id": source_call.get("id"),
            "tool": source_call.get("tool"),
            "write_world_state": write_state,
        }
    write_root = work_recovery_read_root(source_call)
    if not getattr(args, "allow_write", None):
        return {
            "action": "needs_write_gate",
            "reason": "apply-write recovery needs explicit --allow-write roots",
            "source_tool_call_id": source_call.get("id"),
            "tool": source_call.get("tool"),
            "path": write_root,
            "write_world_state": write_state,
        }
    try:
        resolve_allowed_write_path(
            write_root,
            getattr(args, "allow_write", None) or [],
            create=bool((source_call.get("parameters") or {}).get("create")),
        )
    except ValueError as exc:
        return {
            "action": "needs_write_gate",
            "reason": "apply-write recovery needs --allow-write to cover the interrupted tool path",
            "source_tool_call_id": source_call.get("id"),
            "tool": source_call.get("tool"),
            "path": write_root,
            "allow_write": list(getattr(args, "allow_write", None) or []),
            "write_world_state": write_state,
            "error": str(exc),
        }
    parameters = source_call.get("parameters") or {}
    command = interrupted_write_verify_command(source_call)
    if not parameters.get("defer_verify"):
        if not getattr(args, "allow_verify", False):
            return {
                "action": "needs_verify_gate",
                "reason": "apply-write recovery needs explicit --allow-verify",
                "source_tool_call_id": source_call.get("id"),
                "tool": source_call.get("tool"),
                "path": write_root,
                "write_world_state": write_state,
            }
        requested_command = getattr(args, "verify_command", None) or ""
        if not requested_command:
            return {
                "action": "needs_verify_command",
                "reason": "apply-write recovery needs the interrupted verifier passed as --verify-command",
                "source_tool_call_id": source_call.get("id"),
                "tool": source_call.get("tool"),
                "command": command,
                "path": write_root,
                "write_world_state": write_state,
            }
        if not recovery_commands_match(command, requested_command):
            return {
                "action": "needs_matching_verifier",
                "reason": "apply-write recovery only reruns the original verifier",
                "source_tool_call_id": source_call.get("id"),
                "tool": source_call.get("tool"),
                "command": command,
                "requested_command": requested_command,
                "path": write_root,
                "write_world_state": write_state,
            }
    return None


def work_recover_completed_write_blocker(args, source_call, recovery_item, *, safe_only=False):
    if safe_only:
        return {
            "action": "needs_user",
            "reason": "automatic safe recovery does not verify interrupted writes",
            "source_tool_call_id": source_call.get("id"),
            "tool": source_call.get("tool"),
        }
    write_state = (recovery_item or {}).get("write_world_state") or {}
    if write_state.get("state") != "completed_externally":
        return {
            "action": "needs_user",
            "reason": "completed-write recovery only verifies when the target matches the intended content",
            "source_tool_call_id": source_call.get("id"),
            "tool": source_call.get("tool"),
            "write_world_state": write_state,
        }
    if not getattr(args, "allow_verify", False):
        return {
            "action": "needs_verify_gate",
            "reason": "completed-write recovery needs explicit --allow-verify",
            "source_tool_call_id": source_call.get("id"),
            "tool": source_call.get("tool"),
            "write_world_state": write_state,
        }
    command = interrupted_write_verify_command(source_call)
    requested_command = getattr(args, "verify_command", None) or ""
    if not requested_command:
        return {
            "action": "needs_verify_command",
            "reason": "completed-write recovery needs the interrupted verifier passed as --verify-command",
            "source_tool_call_id": source_call.get("id"),
            "tool": source_call.get("tool"),
            "command": command,
            "write_world_state": write_state,
        }
    if not recovery_commands_match(command, requested_command):
        return {
            "action": "needs_matching_verifier",
            "reason": "completed-write recovery only reruns the original verifier",
            "source_tool_call_id": source_call.get("id"),
            "tool": source_call.get("tool"),
            "command": command,
            "requested_command": requested_command,
            "write_world_state": write_state,
        }
    return None


def work_recovery_plan_item_for_call(state, session, source_call):
    if not source_call:
        return {}
    resume = build_work_session_resume(session, task=work_session_task(state, session), state=state)
    for item in (resume.get("recovery_plan") or {}).get("items") or []:
        if str(item.get("tool_call_id")) == str(source_call.get("id")):
            return item
    return {}


def selected_recoverable_interrupted_call(state, session):
    if not session:
        return None, {}
    resume = build_work_session_resume(session, task=work_session_task(state, session), state=state)
    recovery_item = select_work_recovery_plan_item((resume or {}).get("recovery_plan") or {})
    source_call = find_work_tool_call(session, recovery_item.get("tool_call_id"))
    if source_call and source_call.get("status") == "interrupted" and not source_call.get("recovery_status"):
        return source_call, recovery_item
    source_call = latest_recoverable_interrupted_call(session)
    return source_call, work_recovery_plan_item_for_call(state, session, source_call)


def work_recover_dry_run_write_blocker(args, source_call):
    write_root = work_recovery_read_root(source_call)
    if not getattr(args, "allow_write", None):
        return {
            "action": "needs_write_gate",
            "reason": "dry-run write recovery needs explicit --allow-write roots",
            "source_tool_call_id": source_call.get("id"),
            "tool": source_call.get("tool"),
            "path": write_root,
        }
    try:
        resolve_allowed_write_path(
            write_root,
            getattr(args, "allow_write", None) or [],
            create=bool((source_call.get("parameters") or {}).get("create")),
        )
    except ValueError as exc:
        return {
            "action": "needs_write_gate",
            "reason": "dry-run write recovery needs --allow-write to cover the interrupted tool path",
            "source_tool_call_id": source_call.get("id"),
            "tool": source_call.get("tool"),
            "path": write_root,
            "allow_write": list(getattr(args, "allow_write", None) or []),
            "error": str(exc),
        }
    return None


def _work_recover_session_once(args, progress=None, safe_only=False):
    progress = progress if progress is not None else work_tool_progress(args)
    with state_lock():
        state = load_state()
        session = _select_active_work_session_for_args(state, args)
        if not session:
            return 0, {"recovery": {"action": "none", "reason": "no active work session"}}
        source_call, recovery_item = selected_recoverable_interrupted_call(state, session)
        if not source_call:
            return 0, {"recovery": {"action": "none", "reason": "no interrupted work tool to recover"}}
        tool = source_call.get("tool")
        if tool == "run_tests":
            blocker = work_recover_verification_blocker(args, session, source_call, safe_only=safe_only)
            if blocker:
                return 0, {"recovery": blocker}
        elif tool in WRITE_WORK_TOOLS:
            if recovery_item.get("action") == "retry_dry_run_write":
                blocker = work_recover_dry_run_write_blocker(args, source_call)
                if blocker:
                    return 0, {"recovery": blocker}
            elif recovery_item.get("action") == "retry_apply_write":
                blocker = work_recover_apply_write_blocker(args, source_call, recovery_item, safe_only=safe_only)
                if blocker:
                    return 0, {"recovery": blocker}
            elif recovery_item.get("action") == "verify_completed_write":
                blocker = work_recover_completed_write_blocker(args, source_call, recovery_item, safe_only=safe_only)
                if blocker:
                    return 0, {"recovery": blocker}
            else:
                report = {
                    "recovery": {
                        "action": "needs_user",
                        "reason": f"interrupted {tool} is not safe to retry automatically",
                        "source_tool_call_id": source_call.get("id"),
                        "tool": tool,
                        "review_item": recovery_item,
                    }
                }
                return 0, report
        elif tool not in (READ_ONLY_WORK_TOOLS | GIT_WORK_TOOLS):
            report = {
                "recovery": {
                    "action": "needs_user",
                    "reason": f"interrupted {tool} is not safe to retry automatically",
                    "source_tool_call_id": source_call.get("id"),
                    "tool": tool,
                    "review_item": recovery_item,
                }
            }
            return 0, report
        if safe_only and tool in (READ_ONLY_WORK_TOOLS | GIT_WORK_TOOLS) and not getattr(args, "allow_read", None):
            return 0, {
                "recovery": {
                    "action": "needs_read_gate",
                    "reason": "safe recovery needs explicit --allow-read roots",
                    "source_tool_call_id": source_call.get("id"),
                    "tool": tool,
                }
            }
        source_tool_call_id = source_call.get("id")
        resume_for_world = build_work_session_resume(session, task=work_session_task(state, session), state=state)

    world_state_before = {}
    if getattr(args, "allow_read", None):
        world_state_before = build_work_world_state(resume_for_world, args.allow_read)

    with state_lock():
        state = load_state()
        session = _select_active_work_session_for_args(state, args)
        if not session:
            return 0, {"recovery": {"action": "none", "reason": "no active work session"}}
        source_call = find_work_tool_call(session, source_tool_call_id)
        if not source_call or source_call.get("status") != "interrupted" or source_call.get("recovery_status"):
            return 0, {
                "recovery": {
                    "action": "none",
                    "reason": "interrupted work tool already changed before recovery could start",
                    "source_tool_call_id": source_tool_call_id,
                    "tool": tool,
                }
            }
        if tool == "run_tests":
            blocker = work_recover_verification_blocker(args, session, source_call, safe_only=safe_only)
            if blocker:
                return 0, {"recovery": blocker}
        elif tool in WRITE_WORK_TOOLS:
            recovery_item = work_recovery_plan_item_for_call(state, session, source_call)
            if recovery_item.get("action") == "retry_dry_run_write":
                blocker = work_recover_dry_run_write_blocker(args, source_call)
                if blocker:
                    return 0, {"recovery": blocker}
            elif recovery_item.get("action") == "retry_apply_write":
                blocker = work_recover_apply_write_blocker(args, source_call, recovery_item, safe_only=safe_only)
                if blocker:
                    return 0, {"recovery": blocker}
            elif recovery_item.get("action") == "verify_completed_write":
                blocker = work_recover_completed_write_blocker(args, source_call, recovery_item, safe_only=safe_only)
                if blocker:
                    return 0, {"recovery": blocker}
            else:
                return 0, {
                    "recovery": {
                        "action": "needs_user",
                        "reason": f"interrupted {tool} is not safe to retry automatically",
                        "source_tool_call_id": source_call.get("id"),
                        "tool": tool,
                        "review_item": recovery_item,
                    }
                }
        recovery_tool = tool
        parameters = dict(source_call.get("parameters") or {})
        parameters["recovered_from_tool_call_id"] = source_call.get("id")
        if tool == "run_tests":
            parameters["command"] = interrupted_run_tests_command(source_call)
            parameters["allow_verify"] = True
        elif tool in WRITE_WORK_TOOLS:
            if recovery_item.get("action") == "retry_dry_run_write":
                parameters["apply"] = False
                parameters["allowed_write_roots"] = list(getattr(args, "allow_write", None) or [])
                for key in ("approved_from_tool_call_id", "allow_verify", "verify_command", "verify_cwd", "verify_timeout"):
                    parameters.pop(key, None)
            elif recovery_item.get("action") == "retry_apply_write":
                parameters["apply"] = True
                parameters["allowed_write_roots"] = list(getattr(args, "allow_write", None) or [])
                parameters["allow_verify"] = bool(getattr(args, "allow_verify", False))
                parameters["verify_command"] = getattr(args, "verify_command", None) or interrupted_write_verify_command(source_call)
                parameters["verify_cwd"] = getattr(args, "verify_cwd", None) or interrupted_write_verify_cwd(source_call)
            elif recovery_item.get("action") == "verify_completed_write":
                recovery_tool = "run_tests"
                parameters = {
                    "recovered_from_tool_call_id": source_call.get("id"),
                    "command": getattr(args, "verify_command", None) or interrupted_write_verify_command(source_call),
                    "cwd": getattr(args, "verify_cwd", None) or interrupted_write_verify_cwd(source_call),
                    "allow_verify": True,
                    "timeout": getattr(args, "verify_timeout", None),
                }
        tool_call = start_work_tool_call(state, session, recovery_tool, parameters)
        session_id = session.get("id")
        tool_call_id = tool_call.get("id")
        save_state(state)

    recovery_action = (
        recovery_item.get("action")
        if tool in WRITE_WORK_TOOLS and recovery_item.get("action") in {"retry_dry_run_write", "retry_apply_write", "verify_completed_write"}
        else "retry_tool"
    )
    if progress:
        progress(f"recover tool #{source_call.get('id')} -> #{tool_call_id} {recovery_tool} start")
    try:
        result = execute_work_tool_with_output(
            recovery_tool,
            parameters,
            getattr(args, "allow_read", None) or [],
            work_tool_output_progress(progress, tool_call_id),
        )
        error = work_tool_result_error(recovery_tool, result)
    except KeyboardInterrupt:
        with state_lock():
            state = load_state()
            session = find_work_session(state, session_id)
            repairs = mark_work_tool_call_interrupted(session, tool_call_id)
            tool_call = find_work_tool_call(session, tool_call_id)
            if not tool_call:
                tool_call = {
                    "id": tool_call_id,
                    "tool": tool,
                    "status": "interrupted",
                    "error": "recovery work tool was interrupted before the result could be recorded",
                    "summary": "interrupted recovery work tool call",
                }
            save_state(state)
        report = {
            "recovery": {
                "action": recovery_action,
                "source_tool_call_id": parameters.get("recovered_from_tool_call_id"),
                "tool": recovery_tool,
                "source_tool": tool,
                "status": tool_call.get("status"),
            },
            "tool_call": tool_call,
            "interrupted": True,
            "repairs": repairs,
        }
        if world_state_before:
            report["recovery"]["world_state_before"] = world_state_before
        if progress:
            progress(f"recover tool #{tool_call_id} interrupted")
        return 130, report
    except (OSError, ValueError) as exc:
        result = None
        error = str(exc)

    with state_lock():
        state = load_state()
        tool_call = finish_work_tool_call(state, session_id, tool_call_id, result=result, error=error)
        session = find_work_session(state, session_id)
        source_call = find_work_tool_call(session, parameters.get("recovered_from_tool_call_id"))
        if not tool_call:
            error = WORK_TOOL_RESULT_STALE_ERROR
            tool_call = _missing_finished_work_tool_call(tool, tool_call_id, error)
        if source_call:
            recovered_at = now_iso()
            recovery_status = "superseded" if not error else "retry_failed"
            _mark_work_recovery_chain(session, source_call, recovery_status, tool_call_id, recovered_at)
        save_state(state)
    report = {
        "recovery": {
                "action": recovery_action,
                "source_tool_call_id": parameters.get("recovered_from_tool_call_id"),
                "tool": recovery_tool,
                "source_tool": tool,
                "status": tool_call.get("status"),
            },
        "tool_call": tool_call,
    }
    if world_state_before:
        report["recovery"]["world_state_before"] = world_state_before
    if progress:
        progress(f"recover tool #{tool_call_id} {tool_call.get('status')}")
    return (0 if tool_call.get("status") == "completed" else 1), report


def _work_has_safe_recovery_candidate(args):
    with state_lock():
        state = load_state()
        session = _select_active_work_session_for_args(state, args)
        source_call, recovery_item = selected_recoverable_interrupted_call(state, session)
    if not source_call:
        return False
    return (
        recovery_item.get("action") == "retry_tool"
        and source_call.get("tool") in (READ_ONLY_WORK_TOOLS | GIT_WORK_TOOLS)
    )


def _work_recover_safe_session(args, max_recoveries=5):
    reports = []
    code = 0
    for _ in range(max(1, int(max_recoveries or 1))):
        code, report = _work_recover_session_once(args, safe_only=True)
        reports.append(report)
        recovery = (report or {}).get("recovery") or {}
        tool_call = (report or {}).get("tool_call") or {}
        if (
            code != 0
            or recovery.get("action") != "retry_tool"
            or tool_call.get("status") != "completed"
            or not _work_has_safe_recovery_candidate(args)
        ):
            break
    if len(reports) == 1:
        return code, reports[0]
    recoveries = [
        report
        for report in reports
        if ((report or {}).get("recovery") or {}).get("action") == "retry_tool"
    ]
    base_report = recoveries[-1] if recoveries else reports[-1]
    aggregate = dict(base_report or {})
    aggregate["recovery"] = dict((base_report or {}).get("recovery") or {})
    aggregate["recovery"].update(
        {
            "batch": True,
            "batch_action": "retry_tool_batch",
            "batch_status": "completed" if code == 0 else "failed",
            "count": len(recoveries),
            "source_tool_call_ids": [
                ((report or {}).get("recovery") or {}).get("source_tool_call_id")
                for report in recoveries
            ],
            "tool_call_ids": [
                ((report or {}).get("tool_call") or {}).get("id")
                for report in recoveries
            ],
        }
    )
    aggregate["recoveries"] = reports
    if recoveries:
        aggregate["tool_call"] = recoveries[-1].get("tool_call")
    return code, aggregate


def print_work_recovery_report(report):
    recoveries = (report or {}).get("recoveries") or []
    if recoveries:
        recovery = (report or {}).get("recovery") or {}
        print(f"auto-recovered {recovery.get('count') or len(recoveries)} safe work tools")
        for child in recoveries:
            print_work_recovery_report(child)
        return
    recovery = (report or {}).get("recovery") or {}
    action = recovery.get("action")
    if action == "none":
        reason = recovery.get("reason") or "No interrupted work tool to recover."
        if reason == "no active work session":
            reason = "No active work session."
        print(reason)
        return
    if action == "needs_user":
        tool = recovery.get("tool") or "tool"
        print(f"Interrupted {tool} needs user review before retry.")
        review_item = recovery.get("review_item") or {}
        if review_item.get("effect_classification"):
            print(f"effect: {review_item.get('effect_classification')}")
        if review_item.get("path"):
            print(f"path: {review_item.get('path')}")
        if review_item.get("command"):
            print(f"command: {review_item.get('command')}")
        if review_item.get("review_hint"):
            print(f"review: {review_item.get('review_hint')}")
        for step in review_item.get("review_steps") or []:
            print(f"review_step: {step}")
        return
    if action == "needs_read_gate":
        print(recovery.get("reason") or "Safe recovery needs explicit --allow-read roots.")
        if recovery.get("cwd"):
            print(f"cwd: {recovery.get('cwd')}")
        return
    if action == "needs_write_gate":
        print(recovery.get("reason") or "Safe dry-run write recovery needs explicit --allow-write roots.")
        if recovery.get("path"):
            print(f"path: {recovery.get('path')}")
        return
    if action in {"needs_verify_gate", "needs_verify_command", "needs_matching_verifier"}:
        print(recovery.get("reason") or "Verification recovery needs explicit verifier gates.")
        if recovery.get("cwd"):
            print(f"cwd: {recovery.get('cwd')}")
        if recovery.get("command"):
            print(f"command: {recovery.get('command')}")
        if recovery.get("requested_command"):
            print(f"requested_command: {recovery.get('requested_command')}")
        return
    if action in {"retry_tool", "retry_dry_run_write", "retry_apply_write", "verify_completed_write"}:
        tool_call = (report or {}).get("tool_call") or {}
        if report.get("interrupted") or tool_call.get("status") == "interrupted":
            print(
                f"recovery interrupted for work tool #{recovery.get('source_tool_call_id')} "
                f"-> #{tool_call.get('id')} [{tool_call.get('status')}] {recovery.get('tool')}"
            )
            print(tool_call.get("summary") or tool_call.get("error") or "")
            return
        print(
            f"recovered work tool #{recovery.get('source_tool_call_id')} "
            f"-> #{tool_call.get('id')} [{tool_call.get('status')}] {recovery.get('tool')}"
        )
        print(tool_call.get("summary") or tool_call.get("error") or "")
        return
    print(json.dumps(report or {}, ensure_ascii=False, indent=2))


def cmd_work_recover_session(args):
    code, report = _work_recover_session_once(args)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_work_recovery_report(report)
    return code


def _work_tool_task_cwd(task):
    cwd = (task or {}).get("cwd") or "."
    return cwd if cwd != "." else ""


def _work_tool_effective_cwd(args, task=None):
    cwd = getattr(args, "cwd", None)
    if cwd not in (None, "", "."):
        return cwd
    if getattr(args, "tool", "") in (GIT_WORK_TOOLS | {"run_command", "run_tests"}):
        return _work_tool_task_cwd(task) or cwd
    return cwd


def _work_tool_parameters(args, session=None, gate_options=None, task=None):
    path_tools = {"inspect_dir", "read_file", "search_text", "glob", "write_file", "edit_file"}
    options = gate_options if gate_options is not None else _work_tool_gate_options(args, session)
    parameters = {
        "path": args.path if getattr(args, "tool", "") in path_tools else None,
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
        "cwd": _work_tool_effective_cwd(args, task=task),
        "timeout": getattr(args, "timeout", None),
        "allowed_write_roots": options.get("allow_write") or [],
        "allow_shell": options.get("allow_shell"),
        "allow_verify": options.get("allow_verify"),
        "verify_command": options.get("verify_command"),
        "verify_cwd": getattr(args, "verify_cwd", None),
        "verify_timeout": getattr(args, "verify_timeout", None),
        "limit": getattr(args, "limit", None),
        "max_chars": getattr(args, "max_chars", None),
        "offset": getattr(args, "offset", None),
        "line_start": getattr(args, "line_start", None),
        "line_count": getattr(args, "line_count", None),
        "max_matches": getattr(args, "max_matches", None),
        "context_lines": getattr(args, "context_lines", None),
    }
    return {key: value for key, value in parameters.items() if value is not None}


def cmd_work_tool(args):
    progress = work_tool_progress(args)
    with state_lock():
        state = load_state()
        session, review_probe = _select_work_tool_session_for_args(state, args)
        if not session:
            if getattr(args, "json", False):
                if getattr(args, "task_id", None) and not find_task(state, args.task_id):
                    print(
                        json.dumps(
                            {
                                "error": "task_not_found",
                                "task_id": str(args.task_id),
                                "message": f"mew: task not found: {args.task_id}",
                            },
                            ensure_ascii=False,
                            indent=2,
                        )
                    )
                    return 1
                print(json.dumps(no_active_work_session_json(state, args=args), ensure_ascii=False, indent=2))
                return 1
            print(format_no_work_tool_session(state, args), file=sys.stderr)
            return 1
        gate_options = _work_tool_gate_options(args, session)
        task = work_session_task(state, session)
        parameters = _work_tool_parameters(args, session=session, gate_options=gate_options, task=task)
        tool_call = start_work_tool_call(state, session, args.tool, parameters)
        if review_probe:
            tool_call["review_probe"] = True
        session_id = session.get("id")
        tool_call_id = tool_call.get("id")
        save_state(state)
    if progress:
        progress(f"tool #{tool_call_id} {args.tool} start")

    try:
        result = execute_work_tool_with_output(
            args.tool,
            parameters,
            gate_options.get("allow_read") or [],
            work_tool_output_progress(progress, tool_call_id),
        )
        error = work_tool_result_error(args.tool, result)
    except KeyboardInterrupt:
        with state_lock():
            state = load_state()
            session = find_work_session(state, session_id)
            repairs = mark_work_tool_call_interrupted(session, tool_call_id)
            tool_call = find_work_tool_call(session, tool_call_id)
            if not tool_call:
                tool_call = {
                    "id": tool_call_id,
                    "tool": args.tool,
                    "status": "interrupted",
                    "error": "work tool was interrupted before the result could be recorded",
                    "summary": "interrupted work tool call",
                }
            save_state(state)
        if args.json:
            print(
                json.dumps(
                    {"tool_call": tool_call, "interrupted": True, "repairs": repairs},
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            print(f"work tool #{tool_call['id']} [{tool_call['status']}] {tool_call['tool']}")
            print(tool_call.get("summary") or tool_call.get("error") or "")
            fallback_task_id = tool_call.get("task_id") or (session or {}).get("task_id") or getattr(args, "task_id", None)
            fallback_task_arg = f" {fallback_task_id}" if fallback_task_id is not None else ""
            recovery_hint = (
                tool_call.get("recovery_hint")
                or f"{mew_executable()} work{fallback_task_arg} --session --resume --allow-read ."
            )
            print(f"recovery_hint: {recovery_hint}")
        if progress:
            progress(f"tool #{tool_call_id} interrupted")
        return 130
    except (OSError, ValueError) as exc:
        result = None
        error = str(exc)

    with state_lock():
        state = load_state()
        tool_call = finish_work_tool_call(state, session_id, tool_call_id, result=result, error=error)
        if not tool_call:
            error = WORK_TOOL_RESULT_STALE_ERROR
            tool_call = _missing_finished_work_tool_call(args.tool, tool_call_id, error)
        session = find_work_session(state, session_id)
        remember_successful_work_verification(session, args.tool, result)
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
    if getattr(args, "json", False):
        print(json.dumps(task_json_response(task, completion_summary=summary), ensure_ascii=False, indent=2))
        return 0
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

    for session in state.get("work_sessions", []):
        if session.get("status") != "active":
            continue
        if str(session.get("task_id")) != str(task_id):
            continue
        close_work_session(session, current_time=current_time)

def cmd_task_update(args):
    with state_lock():
        state = load_state()
        task = find_task(state, args.task_id)
        if not task:
            print(f"mew: task not found: {args.task_id}", file=sys.stderr)
            return 1

        changed = False
        previous_status = task.get("status")
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
            current_time = now_iso()
            task["updated_at"] = current_time
            if previous_status != "done" and task.get("status") == "done":
                summary = getattr(args, "notes", None) or ""
                resolve_open_questions_for_task(
                    state,
                    task["id"],
                    reason="task marked done",
                )
                record_user_reported_verification(state, None, task, summary, current_time)
                sync_task_done_state(state, task, summary, current_time)
            save_state(state)
    if getattr(args, "json", False):
        print(json.dumps(task_json_response(task, changed=changed), ensure_ascii=False, indent=2))
        return 0
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

def session_message(message_type, request_id=None, **payload):
    data = {"type": message_type}
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

def session_request_kind(request):
    kind = request.get("kind")
    return kind if isinstance(kind, str) and kind.strip() else None


def session_status_payload(state, kind=None):
    lock = read_lock()
    lock_state = "none"
    if lock:
        lock_state = "active" if pid_alive(lock.get("pid")) else "stale"
    tasks = filter_tasks_by_kind(open_tasks(state), kind=kind)
    task_ids = {str(task.get("id")) for task in tasks}
    questions = filter_questions_for_tasks(open_questions(state), tasks, kind=kind)
    attention = filter_attention_for_tasks(open_attention_items(state), tasks, kind=kind)
    running_agents = [run for run in state["agent_runs"] if run.get("status") in ("created", "running")]
    if kind:
        running_agents = [run for run in running_agents if str(run.get("task_id")) in task_ids]
    unread = filter_messages_for_tasks(unread_outbox_messages(state), tasks, kind=kind)
    return {
        "kind": kind or "",
        "runtime_status": state["runtime_status"],
        "agent_status": scoped_agent_status(state, kind=kind),
        "user_status": state["user_status"],
        "autonomy": state.get("autonomy", {}),
        "lock": {
            "state": lock_state,
            "pid": (lock or {}).get("pid") if lock else None,
            "started_at": (lock or {}).get("started_at") if lock else None,
        },
        "counts": {
            "open_tasks": len(tasks),
            "open_questions": len(questions),
            "open_attention": len(attention),
            "running_agent_runs": len(running_agents),
            "unread_outbox": len(unread),
        },
        "next_move": next_move(state, kind=kind),
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
            kind = session_request_kind(request)
            return session_message("status", request_id, **session_status_payload(load_state_locked(), kind=kind))

        if request_type == "brief":
            limit = request.get("limit", 5)
            if not isinstance(limit, int):
                limit = 5
            kind = session_request_kind(request)
            return session_message("brief", request_id, brief=build_brief_data(load_state_locked(), limit=limit, kind=kind))

        if request_type in ("focus", "daily"):
            limit = request.get("limit", 3)
            if not isinstance(limit, int):
                limit = 3
            kind = request.get("kind") if isinstance(request.get("kind"), str) else ""
            data = build_focus_data(load_state_locked(), limit=limit, kind=kind or None)
            payload_key = "daily" if request_type == "daily" else "focus"
            return session_message(request_type, request_id, **{payload_key: data})

        if request_type == "activity":
            limit = request.get("limit", 10)
            if not isinstance(limit, int):
                limit = 10
            kind = session_request_kind(request)
            return session_message("activity", request_id, activity=build_activity_data(load_state_locked(), limit=limit, kind=kind))

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
    kind = getattr(args, "kind", None) or None
    lock = read_lock()
    lock_state = "none"
    if lock:
        lock_state = "active" if pid_alive(lock.get("pid")) else "stale"

    runtime = state["runtime_status"]
    agent = scoped_agent_status(state, kind=kind)
    user = state["user_status"]
    autonomy = state.get("autonomy", {})
    tasks = filter_tasks_by_kind(open_tasks(state), kind=kind)
    task_ids = {str(task.get("id")) for task in tasks}
    unread = [message for message in state["outbox"] if not message.get("read_at")]
    unread = filter_messages_for_tasks(unread, tasks, kind=kind)
    routine_unread = [message for message in unread if is_routine_outbox_message(state, message)]
    questions = filter_questions_for_tasks(open_questions(state), tasks, kind=kind)
    attention = filter_attention_for_tasks(open_attention_items(state), tasks, kind=kind)
    running_agents = [run for run in state["agent_runs"] if run.get("status") in ("created", "running")]
    if kind:
        running_agents = [run for run in running_agents if str(run.get("task_id")) in task_ids]
    active_native_work = active_work_session_status_items(state, kind=kind)
    if args.json:
        print(
            json.dumps(
                {
                    "kind": kind or "",
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
                        "open_tasks": len(tasks),
                        "open_questions": len(questions),
                        "open_attention": len(attention),
                        "running_agent_runs": len(running_agents),
                        "active_work_sessions": len(active_native_work),
                        "unread_outbox": len(unread),
                        "routine_unread_info": len(routine_unread),
                    },
                    "active_work_sessions": active_native_work,
                    "top_attention": attention[0] if attention else None,
                    "latest_summary": (
                        state.get("memory", {}).get("shallow", {}).get("current_context")
                        or state["knowledge"]["shallow"].get("latest_task_summary")
                    ),
                    "next_move": next_move(state, kind=kind),
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
    print(f"last_startup_repair_at: {runtime.get('last_startup_repair_at') or ''}")
    print(
        "last_startup_repairs: "
        f"{json.dumps(runtime.get('last_startup_repairs') or [], ensure_ascii=False)}"
    )
    print(f"last_native_work_step_skip: {runtime.get('last_native_work_step_skip') or ''}")
    print(
        "last_native_work_skip_recovery: "
        f"{json.dumps(runtime.get('last_native_work_skip_recovery') or {}, ensure_ascii=False)}"
    )
    print(
        "last_native_work_recovery: "
        f"{json.dumps(runtime.get('last_native_work_recovery') or {}, ensure_ascii=False)}"
    )
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
    if kind:
        print(f"kind_filter: {kind}")
    print(f"open_tasks: {len(tasks)}")
    print(f"open_questions: {len(questions)}")
    print(f"open_attention: {len(attention)}")
    print(f"running_agent_runs: {len(running_agents)}")
    print(f"active_work_sessions: {len(active_native_work)}")
    for session in active_native_work:
        follow = session.get("follow_status") or {}
        health = follow.get("producer_health") or {}
        print(
            "active_work_session: "
            f"#{session.get('id')} task=#{session.get('task_id')} "
            f"phase={session.get('phase')} "
            f"pending_approvals={session.get('pending_approval_count')} "
            f"producer={health.get('state') or follow.get('status') or 'unknown'} "
            f"alive={bool(follow.get('producer_alive'))} "
            f"status={session.get('follow_status_command')}"
        )
        continuity_text = format_work_continuity_inline(session.get("continuity") or {})
        if continuity_text:
            print(f"  {continuity_text}")
        continuity_next = format_work_continuity_recommendation(session.get("continuity") or {})
        if continuity_next:
            print(f"  {continuity_next}")
    if attention:
        top = attention[0]
        print(f"top_attention: #{top['id']} {top.get('title')}: {top.get('reason')}")
    print(f"unread_outbox: {len(unread)}")
    print(f"routine_unread_info: {len(routine_unread)}")
    if routine_unread:
        print(f"routine_cleanup: {mew_command('ack', '--routine')}")
    memory = state.get("memory", {}).get("shallow", {})
    latest_summary = memory.get("current_context") or state["knowledge"]["shallow"].get("latest_task_summary")
    print(f"latest_summary: {latest_summary}")
    print(f"next_move: {next_move(state, kind=kind)}")
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


def cmd_daemon(args):
    daemon_command = getattr(args, "daemon_command", None) or "status"
    if daemon_command == "start":
        return cmd_start(args)
    if daemon_command == "stop":
        return cmd_stop(args)
    if daemon_command == "logs":
        data = tail_daemon_log(lines=getattr(args, "lines", 40))
        if getattr(args, "json", False):
            print(json.dumps(data, ensure_ascii=False, indent=2))
        else:
            print(format_daemon_log(data))
        return 0

    state = load_state()
    data = build_daemon_status(state, read_lock(), pid_alive)
    if getattr(args, "json", False):
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(format_daemon_status(data))
    return 0

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
    incomplete_effect_items = []
    for effect in incomplete_effects[-5:]:
        decision = runtime_effect_recovery_decision(effect, effect.get("status"))
        incomplete_effect_items.append(
            {
                "id": effect.get("id"),
                "event_id": effect.get("event_id"),
                "status": effect.get("status"),
                "reason": effect.get("reason") or "",
                "recovery_decision": decision,
                "recovery_followup": runtime_effect_recovery_followup(state, effect, decision, mutate=False),
            }
        )
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
        "incomplete_items": incomplete_effect_items,
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
    for item in runtime_effects.get("incomplete_items") or []:
        decision = item.get("recovery_decision") or {}
        followup = item.get("recovery_followup") or {}
        lines.append(
            "runtime_effect_recovery: "
            f"#{item.get('id')} status={item.get('status')} "
            f"action={decision.get('action')} "
            f"effect={decision.get('effect_classification')} "
            f"safety={decision.get('safety')}"
        )
        if followup:
            lines.append(
                "runtime_effect_followup: "
                f"#{item.get('id')} action={followup.get('action')} "
                f"status={followup.get('status')} "
                f"command={followup.get('command') or ''}"
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

def repair_incomplete_work_sessions(state):
    return mark_running_work_interrupted(state)


def build_repair_data(dry_run=False):
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
                    "dry_run": bool(dry_run),
                    "before_sha256": before_sha,
                    "after_sha256": before_sha,
                    "repairs": repairs,
                    "validation_issues": issues,
                }
            if dry_run:
                after_sha = state_digest(state)
                return {
                    "ok": True,
                    "repaired": before_sha != after_sha,
                    "dry_run": True,
                    "before_sha256": before_sha,
                    "after_sha256": after_sha,
                    "repairs": repairs,
                    "validation_issues": validate_state(state),
                    "last_effect": None,
                }
            save_state(state)
            after_sha = state_digest(state)
            last_effect = read_last_state_effect()
            if last_effect and last_effect.get("state_sha256"):
                after_sha = last_effect["state_sha256"]
            return {
                "ok": True,
                "repaired": before_sha != after_sha,
                "dry_run": False,
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
            "dry_run": bool(dry_run),
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
            "dry_run": bool(getattr(args, "dry_run", False)),
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
    data = build_repair_data(dry_run=getattr(args, "dry_run", False))
    if getattr(args, "json", False):
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        if data.get("ok"):
            if data.get("dry_run"):
                status = "would repair" if data.get("repaired") else "already valid"
            else:
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
                        decision = repair.get("recovery_decision") or {}
                        if decision:
                            print(
                                "  decision: "
                                f"{decision.get('action')} "
                                f"effect={decision.get('effect_classification')} "
                                f"safety={decision.get('safety')}"
                            )
                        followup = repair.get("recovery_followup") or {}
                        if followup:
                            question_text = (
                                f" question=#{followup.get('question_id')}"
                                if followup.get("question_id")
                                else ""
                            )
                            print(
                                "  followup: "
                                f"{followup.get('action')} "
                                f"status={followup.get('status')} "
                                f"command={followup.get('command') or ''}"
                                f"{question_text}"
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
    kind = getattr(args, "kind", None) or None
    if args.json:
        print(
            json.dumps(
                build_brief_data(state, limit=args.limit, kind=kind, include_context_checkpoint=True),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    print(build_brief(state, limit=args.limit, kind=kind, include_context_checkpoint=True))
    return 0

def cmd_focus(args):
    state = load_state()
    data = build_focus_data(
        state,
        limit=args.limit,
        kind=getattr(args, "kind", None) or None,
        include_context_checkpoint=True,
    )
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0
    print(format_focus(data))
    return 0


def cmd_metrics(args):
    state = load_state()
    data = build_observation_metrics(
        state,
        kind=getattr(args, "kind", None) or None,
        limit=getattr(args, "limit", None),
        sample_limit=getattr(args, "sample_limit", None),
    )
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0
    print(format_observation_metrics(data))
    return 0

def cmd_passive_bundle(args):
    if args.json and args.show:
        print("mew: --json and --show cannot be used together", file=sys.stderr)
        return 1
    if args.morning_feed and not args.generate_core:
        print("mew: --morning-feed requires --generate-core", file=sys.stderr)
        return 1
    if args.interest and not args.morning_feed:
        print("mew: --interest requires --morning-feed", file=sys.stderr)
        return 1
    if args.limit != 8 and not args.morning_feed:
        print("mew: --limit requires --morning-feed", file=sys.stderr)
        return 1
    reports_root = Path(args.reports_root).expanduser()
    output_dir = Path(args.output_dir).expanduser()
    generated = []
    try:
        if args.generate_core:
            with state_lock():
                state = load_state()
            journal_view = build_journal_view_model(state, explicit_date=args.date)
            journal_path = write_journal_report(journal_view, reports_root)
            generated.append({"type": "Journal", "path": str(journal_path)})

            mood_view = build_mood_view_model(state, explicit_date=args.date)
            mood_path = write_mood_report(mood_view, reports_root)
            generated.append({"type": "Mood", "path": str(mood_path)})

            self_memory_view = build_self_memory_view_model(state, explicit_date=args.date)
            self_memory_path = write_self_memory_report(self_memory_view, reports_root)
            generated.append({"type": "Self Memory", "path": str(self_memory_path)})

            dream_view = build_dream_view_model(state, explicit_date=args.date)
            dream_path = write_dream_report(dream_view, reports_root)
            generated.append({"type": "Dream", "path": str(dream_path)})

            if args.morning_feed:
                try:
                    items = load_feed(Path(args.morning_feed).expanduser())
                except (OSError, json.JSONDecodeError) as exc:
                    print(f"mew: failed to read feed: {exc}", file=sys.stderr)
                    return 1
                morning_view = build_morning_paper_view_model(
                    items,
                    state,
                    explicit_date=args.date,
                    explicit_interests=args.interest,
                    limit=args.limit,
                )
                morning_path = write_morning_paper_report(morning_view, reports_root)
                generated.append({"type": "Morning Paper", "path": str(morning_path)})

        result = generate_bundle(
            reports_root,
            output_dir,
            explicit_date=args.date,
        )
    except OSError as exc:
        print(f"mew: failed to write report: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"mew: {exc}", file=sys.stderr)
        return 1
    data = {
        "path": str(result.path),
        "included": result.included,
        "missing": result.missing,
        "generated": generated,
    }
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    elif args.show:
        print(result.text, end="")
    else:
        print(result.path)
    return 0

def cmd_desk(args):
    state = load_state()
    try:
        view_model = build_desk_view_model(state, explicit_date=args.date, kind=getattr(args, "kind", None))
    except ValueError as exc:
        print(f"mew: {exc}", file=sys.stderr)
        return 1
    written = None
    if args.write:
        written = write_desk_view(view_model, Path(args.output_dir).expanduser())
    if args.json:
        data = dict(view_model)
        if written:
            data["paths"] = {"json": str(written[0]), "markdown": str(written[1])}
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(format_desk_view(view_model))
        if written:
            print(f"written_json: {written[0]}")
            print(f"written_markdown: {written[1]}")
    return 0

def cmd_mood(args):
    if args.json and args.show:
        print("mew: --json and --show cannot be used together", file=sys.stderr)
        return 1
    state = load_state()
    try:
        view_model = build_mood_view_model(state, explicit_date=args.date)
    except ValueError as exc:
        print(f"mew: {exc}", file=sys.stderr)
        return 1
    written = None
    if args.write:
        try:
            written = write_mood_report(view_model, Path(args.output_dir).expanduser())
        except OSError as exc:
            print(f"mew: failed to write report: {exc}", file=sys.stderr)
            return 1
    if args.json:
        data = dict(view_model)
        if written:
            data["path"] = str(written)
        print(json.dumps(data, ensure_ascii=False, indent=2))
    elif args.show:
        print(render_mood_markdown(view_model), end="")
    else:
        print(format_mood_view(view_model))
        if written:
            print(f"written_markdown: {written}")
    return 0

def cmd_journal(args):
    if args.json and args.show:
        print("mew: --json and --show cannot be used together", file=sys.stderr)
        return 1
    state = load_state()
    try:
        view_model = build_journal_view_model(state, explicit_date=args.date)
    except ValueError as exc:
        print(f"mew: {exc}", file=sys.stderr)
        return 1
    written = None
    if args.write:
        try:
            written = write_journal_report(view_model, Path(args.output_dir).expanduser())
        except OSError as exc:
            print(f"mew: failed to write report: {exc}", file=sys.stderr)
            return 1
    if args.json:
        data = {
            "date": view_model["date"],
            "counts": {
                "completed": len(view_model["completed"]),
                "active": len(view_model["active"]),
                "questions": len(view_model["questions"]),
                "sessions": len(view_model["sessions"]),
                "runtime_effects": len(view_model["runtime_effects"]),
            },
            "mew_note": view_model["mew_note"],
        }
        if written:
            data["path"] = str(written)
        print(json.dumps(data, ensure_ascii=False, indent=2))
    elif args.show:
        print(render_journal_markdown(view_model), end="")
    else:
        print(format_journal_view(view_model))
        if written:
            print(f"written_markdown: {written}")
    return 0

def cmd_morning_paper(args):
    if args.json and args.show:
        print("mew: --json and --show cannot be used together", file=sys.stderr)
        return 1
    state = load_state()
    try:
        items = load_feed(Path(args.feed).expanduser())
        view_model = build_morning_paper_view_model(
            items,
            state,
            explicit_date=args.date,
            explicit_interests=args.interest,
            limit=args.limit,
        )
    except (OSError, json.JSONDecodeError) as exc:
        print(f"mew: failed to read feed: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"mew: {exc}", file=sys.stderr)
        return 1
    written = None
    if args.write:
        try:
            written = write_morning_paper_report(view_model, Path(args.output_dir).expanduser())
        except OSError as exc:
            print(f"mew: failed to write report: {exc}", file=sys.stderr)
            return 1
    if args.json:
        data = {
            "date": view_model["date"],
            "interests": view_model["interests"],
            "continuity_risks": view_model.get("continuity_risks") or [],
            "top_picks": len(view_model["top_picks"]),
            "explore_later": len(view_model["explore_later"]),
            "items": view_model["items"],
        }
        if written:
            data["path"] = str(written)
        print(json.dumps(data, ensure_ascii=False, indent=2))
    elif args.show:
        print(render_morning_paper_markdown(view_model), end="")
    else:
        print(format_morning_paper_view(view_model))
        if written:
            print(f"written_markdown: {written}")
    return 0

def cmd_self_memory(args):
    if args.json and args.show:
        print("mew: --json and --show cannot be used together", file=sys.stderr)
        return 1
    state = load_state()
    try:
        view_model = build_self_memory_view_model(state, explicit_date=args.date)
    except ValueError as exc:
        print(f"mew: {exc}", file=sys.stderr)
        return 1
    written = None
    if args.write:
        try:
            written = write_self_memory_report(view_model, Path(args.output_dir).expanduser())
        except OSError as exc:
            print(f"mew: failed to write report: {exc}", file=sys.stderr)
            return 1
    if args.json:
        data = dict(view_model)
        if written:
            data["path"] = str(written)
        print(json.dumps(data, ensure_ascii=False, indent=2))
    elif args.show:
        print(render_self_memory_markdown(view_model), end="")
    else:
        print(format_self_memory_view(view_model))
        if written:
            print(f"written_markdown: {written}")
    return 0

def cmd_dream(args):
    if args.json and args.show:
        print("mew: --json and --show cannot be used together", file=sys.stderr)
        return 1
    state = load_state()
    try:
        view_model = build_dream_view_model(state, explicit_date=args.date)
    except ValueError as exc:
        print(f"mew: {exc}", file=sys.stderr)
        return 1
    written = None
    if args.write:
        try:
            written = write_dream_report(view_model, Path(args.output_dir).expanduser())
        except OSError as exc:
            print(f"mew: failed to write report: {exc}", file=sys.stderr)
            return 1
    if args.json:
        data = dict(view_model)
        if written:
            data["path"] = str(written)
        print(json.dumps(data, ensure_ascii=False, indent=2))
    elif args.show:
        print(render_dream_markdown(view_model), end="")
    else:
        print(format_dream_view(view_model))
        if written:
            print(f"written_markdown: {written}")
    return 0

def cmd_activity(args):
    state = load_state()
    kind = getattr(args, "kind", None) or None
    if args.json:
        print(json.dumps(build_activity_data(state, limit=args.limit, kind=kind), ensure_ascii=False, indent=2))
        return 0
    print(format_activity(state, limit=args.limit, kind=kind))
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


def build_context_save_text(context, current_time, note):
    report = format_context_report(context, current_time)
    note = str(note or "").strip()
    lines = [
        f"Context save {current_time}",
        f"Note: {note or '(empty)'}",
        "",
        "Diagnostics:",
        report,
        "",
        "Suggested reentry:",
        "- git status --short",
        "- ./mew desk --kind coding --json",
        "- ./mew focus --kind coding",
        "- ./mew brief --kind coding",
        "- ./mew memory --search 'next safe action context compression long session' --type project --json",
    ]
    return "\n".join(lines)


def format_context_load_report(data):
    current = data.get("current") or {}
    lines = [
        "Mew context load",
        f"query: {data.get('query') or ''}",
        f"matches: {len(data.get('matches') or [])}",
        f"current_git_head: {current.get('git_head') or '(unknown)'}",
        f"current_git_status: {current.get('git_status') or 'unknown'}",
    ]
    if data.get("matches"):
        lines.append(f"recommended: {(data.get('matches') or [{}])[0].get('name')}")
    for item in data.get("matches") or []:
        lines.append("")
        label = "recommended, historical" if item.get("recommended") else "historical"
        lines.append(f"- [{label}] {item.get('name') or item.get('key') or item.get('id')}")
        if item.get("created_at"):
            lines.append(f"  created_at: {item.get('created_at')}")
        if item.get("description"):
            lines.append(f"  description: {item.get('description')}")
        if item.get("path"):
            lines.append(f"  path: {item.get('path')}")
        if item.get("reentry_note"):
            lines.append("  note:")
            for line in str(item.get("reentry_note") or "").splitlines() or [""]:
                lines.append(f"    {line}")
        lines.append("  diagnostics_preview:")
        preview = clip_output(item.get("text") or "", 900)
        for line in preview.splitlines() or [""]:
            lines.append(f"    {line}")
    return "\n".join(lines)


def cmd_context(args):
    state = load_state()
    current_time = now_iso()
    if getattr(args, "load", False):
        if getattr(args, "save", None) is not None:
            print("mew: --load cannot be combined with --save", file=sys.stderr)
            return 1
        data = {
            "query": args.query,
            "current": context_load_current_state(),
            "matches": load_context_checkpoints(args.query, args.limit),
        }
        if args.json:
            print(json.dumps(data, ensure_ascii=False, indent=2))
            return 0
        print(format_context_load_report(data))
        return 0

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
        allow_native_work=bool(autonomy.get("allow_native_work")),
        allow_verify=bool(autonomy.get("allow_verify")),
        verify_command="configured" if autonomy.get("verify_command_configured") else "",
        allow_write=bool(autonomy.get("allow_write")),
    )
    save_note = getattr(args, "save", None)
    if save_note is not None:
        entry = FileMemoryBackend(".").write(
            build_context_save_text(context, current_time, save_note),
            scope="private",
            memory_type="project",
            name=args.name or f"Context save {current_time}",
            description=args.description or "Saved by mew context --save for future reentry.",
            created_at=current_time,
        )
        if args.json:
            print(
                json.dumps(
                    {
                        "context": context,
                        "saved_memory": entry_to_dict(entry),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0
        print(format_context_report(context, current_time))
        print(f"saved_memory: {entry.scope}.{entry.memory_type}: {entry.name}")
        if entry.path:
            print(f"path: {entry.path}")
        return 0

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

    if args.max_steps == 0:
        report = run_step_loop(max_steps=0, dry_run=args.dry_run)
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            print(format_step_loop_report(report))
        return 0

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
        def progress(line):
            print(f"mew step: {line}", file=sys.stderr, flush=True)

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
    kind = getattr(args, "kind", None) or None
    coding_move = ""
    if kind:
        move = next_move(state, kind=kind)
    else:
        focus_data = build_focus_data(state, limit=0)
        move = focus_data.get("next_move") or next_move(state)
        coding_move = focus_data.get("coding_next_move") or ""
    if args.json:
        payload = {"next_move": move, "command": command_from_next_move(move), "kind": kind or ""}
        if coding_move and coding_move != move:
            payload["coding_next_move"] = coding_move
            payload["coding_command"] = command_from_next_move(coding_move)
        print(
            json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    print(move)
    if coding_move and coding_move != move:
        print(f"Coding: {coding_move}")
    return 0

def cmd_dogfood(args):
    if getattr(args, "all_scenarios", False):
        if getattr(args, "scenario", "") and args.scenario != "all":
            print("mew: --all cannot be combined with --scenario", file=sys.stderr)
            return 1
        args.scenario = "all"
    if args.allow_verify and not args.verify_command:
        print("mew: --allow-verify requires --verify-command", file=sys.stderr)
        return 1
    try:
        if getattr(args, "scenario", ""):
            report = run_dogfood_scenario(args)
        elif getattr(args, "cycles", 1) and args.cycles > 1:
            if not hasattr(args, "duration"):
                args.duration = 45.0
            if not hasattr(args, "interval"):
                args.interval = 10.0
            if not hasattr(args, "poll_interval"):
                args.poll_interval = 0.5
            report = run_dogfood_loop(args)
        else:
            if not hasattr(args, "duration"):
                args.duration = 45.0
            if not hasattr(args, "interval"):
                args.interval = 10.0
            if not hasattr(args, "poll_interval"):
                args.poll_interval = 0.5
            report = run_dogfood(args)
    except ValueError as exc:
        print(f"mew: {exc}", file=sys.stderr)
        return 1

    if getattr(args, "scenario", ""):
        report_path = write_report_if_requested(args, report)
        if args.json:
            print(json.dumps(summarize_dogfood_scenario_json(report), ensure_ascii=False, indent=2))
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

def cmd_proof_summary(args):
    summary = summarize_proof_artifacts(args.artifact_dir)
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(format_proof_summary(summary))
    if getattr(args, "strict", False) and not summary.get("ok"):
        return 1
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
        if command_candidate_invokes_mew(candidate):
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
            return mew_command("work", task_id)
    return ""


def command_candidate_invokes_mew(candidate):
    try:
        tokens = shlex.split(candidate or "")
    except ValueError:
        return False
    if not tokens:
        return False
    if tokens[:3] == ["uv", "run", "mew"]:
        return True
    executable = tokens[0]
    if executable in ("mew", "./mew"):
        return True
    return os.path.basename(executable) == "mew" and (os.path.isabs(executable) or os.sep in executable)

def format_verification_run(run):
    label = run.get("label") or f"#{run.get('id')}"
    return (
        f"{label} [{verification_outcome(run)}] "
        f"exit_code={run.get('exit_code')} command={run.get('command')} "
        f"finished_at={run.get('finished_at') or run.get('updated_at') or run.get('created_at')}"
    )


def _run_finished_sort_key(run):
    identifier = run.get("ledger_id") or run.get("id") or run.get("label") or ""
    return (
        run.get("finished_at")
        or run.get("updated_at")
        or run.get("created_at")
        or "0000-00-00T00:00:00Z",
        str(identifier),
    )


def runtime_verification_runs(state):
    runs = []
    for run in state.get("verification_runs", []) or []:
        item = dict(run)
        item.setdefault("source", "runtime")
        item.setdefault("label", f"#{item.get('id')}")
        item.setdefault("ledger_id", f"verification:{item.get('id')}")
        runs.append(item)
    return runs


def work_session_verification_runs(state):
    runs = []
    for session in state.get("work_sessions", []) or []:
        runs.extend(work_session_verification_summaries(session, limit=None))
    return runs


def runtime_write_runs(state):
    runs = []
    for run in state.get("write_runs", []) or []:
        item = dict(run)
        item.setdefault("source", "runtime")
        item.setdefault("label", f"#{item.get('id')}")
        item.setdefault("ledger_id", f"write:{item.get('id')}")
        runs.append(item)
    return runs


def work_session_write_runs(state):
    runs = []
    for session in state.get("work_sessions", []) or []:
        runs.extend(work_session_write_summaries(session, limit=None))
    return runs


def cmd_verification(args):
    state = load_state()
    runs = runtime_verification_runs(state) + work_session_verification_runs(state)
    if not runs:
        print("No verification runs.")
        return 0
    runs = sorted(runs, key=_run_finished_sort_key)
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
                print(clip_output(run["stdout"], 4000))
            if run.get("stderr"):
                print("stderr:")
                print(clip_output(run["stderr"], 4000))
    return 0

def format_write_run(run):
    label = run.get("label") or f"#{run.get('id')}"
    rollback = f" rolled_back={run.get('rolled_back')}" if run.get("rolled_back") is not None else ""
    verification = (
        f" verification=#{run.get('verification_run_id')} exit={run.get('verification_exit_code')}"
        if run.get("verification_run_id") is not None
        else ""
    )
    if not verification and run.get("verification_exit_code") is not None:
        verification = f" verification_exit={run.get('verification_exit_code')}"
    return (
        f"{label} [{run.get('operation') or run.get('action_type')}] "
        f"changed={run.get('changed')} dry_run={run.get('dry_run')} "
        f"written={run.get('written')}{rollback}{verification} path={run.get('path')}"
    )

def cmd_writes(args):
    state = load_state()
    runs = runtime_write_runs(state) + work_session_write_runs(state)
    if not runs:
        print("No write runs.")
        return 0
    runs = sorted(runs, key=_run_finished_sort_key)
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
            print(clip_output(run["diff"], 4000))
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
        result = read_file(
            args.path,
            _tool_allowed_roots(args),
            max_chars=args.max_chars,
            offset=args.offset,
            line_start=getattr(args, "line_start", None),
            line_count=getattr(args, "line_count", None),
        )
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
            context_lines=getattr(args, "context_lines", 3),
            pattern=getattr(args, "pattern", None),
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

def resolved_task_cwd_text(task):
    cwd = Path((task or {}).get("cwd") or ".").expanduser()
    if not cwd.is_absolute():
        cwd = Path.cwd() / cwd
    return str(cwd.resolve(strict=False))


def native_self_improve_read_root(task):
    resolved = resolved_task_cwd_text(task)
    current = str(Path.cwd().resolve(strict=False))
    if resolved == current:
        return "."
    return resolved


def native_self_improve_write_roots(task):
    root = Path(resolved_task_cwd_text(task))
    current = Path.cwd().resolve(strict=False)
    roots = []
    for relative in ("src/mew", "tests"):
        candidate = root / relative
        if not candidate.exists():
            continue
        roots.append(relative if root == current else str(candidate.resolve(strict=False)))
    return roots


def native_self_improve_verify_command(task):
    root = Path(resolved_task_cwd_text(task))
    if (root / "pyproject.toml").is_file() and (root / "tests").is_dir():
        return "uv run pytest -q"
    return ""


def seed_native_self_improve_session_defaults(session, task):
    if not session:
        return
    defaults = session.setdefault("default_options", {})
    read_root = native_self_improve_read_root(task)
    allow_read = []
    for root in list(defaults.get("allow_read") or []) + [read_root]:
        if root and root not in allow_read:
            allow_read.append(root)
    defaults["allow_read"] = allow_read
    write_roots = native_self_improve_write_roots(task)
    if write_roots:
        allow_write = []
        for root in list(defaults.get("allow_write") or []) + write_roots:
            if root and root not in allow_write:
                allow_write.append(root)
        defaults["allow_write"] = allow_write
    verify_command = native_self_improve_verify_command(task)
    if verify_command and not defaults.get("verify_command"):
        defaults["allow_verify"] = True
        defaults["verify_command"] = verify_command
    defaults["compact_live"] = True
    session["updated_at"] = now_iso()


def is_self_improve_task(task):
    if not task:
        return False
    if (task.get("title") or "").strip() == DEFAULT_SELF_IMPROVE_TITLE:
        return True
    return "Created by mew self-improve" in (task.get("notes") or "")


NATIVE_SELF_IMPROVE_REENTRY_NOTE_PREFIX = "Native self-improve reentry prepared."


def _native_self_improve_control_args(read_root, *, quiet=False):
    return SimpleNamespace(
        live=False,
        follow=False,
        auth=None,
        model_backend=None,
        model=None,
        base_url=None,
        allow_read=[read_root],
        allow_write=[],
        allow_shell=False,
        allow_verify=False,
        verify_command="",
        act_mode=None,
        compact_live=True,
        quiet=quiet,
        prompt_approval=False,
        no_prompt_approval=False,
    )


def native_self_improve_controls(task, *, include_start_hint=False, session=None):
    read_root = native_self_improve_read_root(task)
    continue_args = _native_self_improve_control_args(read_root)
    follow_args = _native_self_improve_control_args(read_root, quiet=True)
    controls = {
        "work_cwd": resolved_task_cwd_text(task),
        "continue": _work_live_continue_command(continue_args, task["id"], session=session, max_steps=1),
        "follow": _work_live_continue_command(follow_args, task["id"], session=session, max_steps=10, follow=True),
        "status": mew_command("work", task["id"], "--follow-status", "--json"),
        "resume": _work_resume_command(continue_args, task["id"], session=session),
        "inspect": _work_resume_command(continue_args, task["id"], session=session),
        "cells": mew_command("work", task["id"], "--cells"),
        "active_memory": mew_command("memory", "--active", "--task-id", task["id"]),
        "audit": mew_command("self-improve", "--audit", task["id"]),
        "chat": mew_command("chat"),
    }
    if include_start_hint:
        controls["start_session"] = mew_command(
            "work",
            task["id"],
            "--start-session",
            "--allow-read",
            read_root,
            "--compact-live",
        )
    return controls


def seed_native_self_improve_reentry_note(session, task):
    if not session:
        return None
    controls = native_self_improve_controls(task, session=session)
    notes = session.get("notes") or []
    session["notes"] = [
        note
        for note in notes
        if not (
            note.get("source") == "system"
            and str(note.get("text") or "").startswith(NATIVE_SELF_IMPROVE_REENTRY_NOTE_PREFIX)
        )
    ]
    text = (
        f"{NATIVE_SELF_IMPROVE_REENTRY_NOTE_PREFIX} "
        f"Next: run `{controls['continue']}`. "
        f"Inspect: `{controls['resume']}`. "
        f"Status: `{controls['status']}`. "
        f"Audit: `{controls['audit']}`."
    )
    return add_work_session_note(session, text, source="system")


def print_native_self_improve_controls(task, *, include_start_hint=False, session=None):
    controls = native_self_improve_controls(task, include_start_hint=include_start_hint, session=session)
    if include_start_hint:
        print(f"start session: {controls['start_session']}")
    print(f"work cwd: {controls['work_cwd']}")
    print(f"continue: {controls['continue']}")
    print(f"follow: {controls['follow']}")
    print(f"status: {controls['status']}")
    print(f"resume: {controls['resume']}")
    print(f"inspect: {controls['inspect']}")
    print(f"cells: {controls['cells']}")
    print(f"active memory: {controls['active_memory']}")
    print(f"audit: {controls['audit']}")
    print(f"chat: {controls['chat']}")


def self_improve_native_validation_error(
    *, native=False, dispatch=False, cycle=False, show_prompt=False, force_plan=False
):
    if native and (cycle or dispatch):
        return "--native/--start-session cannot be combined with --cycle or --dispatch"
    if native and show_prompt:
        return "--native/--start-session cannot be combined with --prompt"
    if native and force_plan:
        return "--native/--start-session cannot be combined with --force-plan"
    if cycle and show_prompt:
        return "--prompt cannot be combined with --cycle"
    return ""


def cmd_self_improve(args):
    if getattr(args, "audit", None) is not None or getattr(args, "audit_sequence", None):
        return cmd_self_improve_audit(args)
    native = bool(getattr(args, "native", False) or getattr(args, "start_session", False))
    if args.prompt and args.no_plan:
        print("mew: --prompt requires a programmer plan; remove --no-plan", file=sys.stderr)
        return 1
    validation_error = self_improve_native_validation_error(
        native=native,
        dispatch=args.dispatch,
        cycle=args.cycle,
        show_prompt=args.prompt,
        force_plan=args.force_plan,
    )
    if validation_error:
        print(f"mew: {validation_error}", file=sys.stderr)
        return 1
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
            ready=args.ready or args.dispatch or getattr(args, "start_session", False),
            auto_execute=args.auto_execute,
            agent_model=args.agent_model,
            force=args.force,
        )
        plan = None
        plan_created = False
        run = None
        session = None
        session_created = False
        if not native and (not args.no_plan or args.dispatch):
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
        if getattr(args, "start_session", False):
            session, session_created = create_work_session(state, task)
            seed_native_self_improve_session_defaults(session, task)
            seed_m5_self_improve_audit(session, task)
            seed_native_self_improve_reentry_note(session, task)
        save_state(state)

    if getattr(args, "json", False):
        payload = {
            "created": created,
            "task": task,
            "plan_created": plan_created,
            "plan": plan,
            "run": run,
            "session_created": session_created,
            "work_session": session,
            "native": native,
            "controls": native_self_improve_controls(
                task,
                include_start_hint=native and not getattr(args, "start_session", False),
                session=session,
            )
            if native
            else {},
        }
        if args.prompt and plan:
            payload["implementation_prompt"] = plan.get("implementation_prompt") or ""
            payload["review_prompt"] = plan.get("review_prompt") or ""
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        if run and not args.dry_run and run.get("status") != "running":
            return 1
        return 0

    print(("created" if created else "reused") + f" {format_task(task)}")
    if plan:
        print(("created" if plan_created else "reused") + f" {format_task_plan(plan)}")
    if session:
        print(("started" if session_created else "reused") + f" work session #{session['id']}")
    if native:
        print_native_self_improve_controls(
            task,
            include_start_hint=not getattr(args, "start_session", False),
            session=session,
        )
    if args.prompt:
        if not plan:
            print("No programmer plan was created for native self-improvement.")
            return 0
        print("implementation_prompt:")
        print(plan.get("implementation_prompt") or "")
        print("review_prompt:")
        print(plan.get("review_prompt") or "")
    if run:
        return print_self_improve_run_status(run, dry_run=args.dry_run, plan=plan)
    return 0


def cmd_self_improve_audit(args):
    with state_lock():
        state = load_state()
        if getattr(args, "audit_sequence", None):
            sequence = build_m5_self_improve_audit_sequence(state, getattr(args, "audit_sequence", None))
            save_state(state)
            if args.json:
                print(json.dumps(sequence, ensure_ascii=False, indent=2))
            else:
                print(format_m5_self_improve_audit_sequence(sequence))
            return 0 if sequence.get("status") != "needs_review" else 1
        bundle = build_m5_self_improve_audit_bundle(state, getattr(args, "audit", None))
        save_state(state)
    if args.json:
        print(json.dumps(bundle, ensure_ascii=False, indent=2))
    else:
        print(format_m5_self_improve_audit_bundle(bundle))
    return 0 if bundle.get("status") != "missing_task" else 1


def print_self_improve_run_status(run, *, dry_run=False, plan=None):
    if dry_run:
        plan_id = (plan or {}).get("id") or run.get("plan_id")
        print(f"created dry-run self-improve run #{run['id']} from plan #{plan_id}")
        print(" ".join(run["command"]))
        return 0
    print(f"started self-improve run #{run['id']} status={run.get('status')} pid={run.get('external_pid')}")
    if run.get("status") != "running":
        detail = clip_output(run.get("stderr") or run.get("result") or "", 500)
        suffix = f": {detail}" if detail else ""
        print(f"mew: self-improve run #{run['id']} status={run.get('status')}{suffix}")
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
        context = format_question_context(question)
        print(f"#{question['id']} [{status}]{task_text}{context} {question['text']}")
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


def active_memory_target(state, task_id=None):
    task = None
    session = None
    if task_id is not None:
        task = find_task(state, task_id)
        if not task:
            raise ValueError(f"task not found: {task_id}")
        for candidate in reversed(state.get("work_sessions") or []):
            if str(candidate.get("task_id")) == str(task_id) and candidate.get("status") == "active":
                session = candidate
                break
        return task, session
    session = active_work_session(state)
    task = work_session_task(state, session) if session else None
    if task:
        return task, session
    open_items = open_tasks(state)
    if open_items:
        return open_items[0], None
    return None, None


def format_active_memory(active_memory, task=None, session=None):
    lines = []
    if task:
        lines.append(f"Active memory for task #{task.get('id')}: {task.get('title') or ''}".rstrip())
    elif session:
        lines.append(f"Active memory for work session #{session.get('id')}")
    else:
        lines.append("Active memory")
    terms = active_memory.get("terms") or []
    if terms:
        lines.append(f"terms: {', '.join(str(term) for term in terms)}")
    items = active_memory.get("items") or []
    if not items:
        lines.append("No active typed memory.")
        return "\n".join(lines)
    for item in items:
        label = f"{item.get('memory_scope') or item.get('scope')}.{item.get('memory_type') or item.get('type')}"
        name = item.get("name") or item.get("key") or "memory"
        details = active_memory_item_detail_parts(item, include_score=True, include_matches=True)
        lines.append(f"- [{label}] {name}: {item.get('description') or item.get('text') or ''} ({'; '.join(details)})")
    if active_memory.get("truncated"):
        lines.append(f"... {active_memory.get('total')} total active memories; older items omitted")
    return "\n".join(lines)


def cmd_memory(args):
    if args.active:
        if args.add or args.search or args.compact:
            print("mew: --active cannot be combined with --add, --search, or --compact", file=sys.stderr)
            return 1
        state = load_state()
        try:
            task, session = active_memory_target(state, task_id=args.task_id)
        except ValueError as exc:
            print(f"mew: {exc}", file=sys.stderr)
            return 1
        active_memory = build_work_active_memory(session=session, task=task, limit=args.limit)
        if args.json:
            print(
                json.dumps(
                    {
                        "active_memory": active_memory,
                        "task": task or {},
                        "work_session": session or {},
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0
        print(format_active_memory(active_memory, task=task, session=session))
        return 0

    if args.add:
        if not args.memory_type and (args.scope or args.name or args.description):
            print("mew: typed memory metadata requires --type when adding memory", file=sys.stderr)
            return 1
        if args.memory_type:
            try:
                entry = FileMemoryBackend(".").write(
                    args.add,
                    scope=args.scope or "private",
                    memory_type=args.memory_type,
                    name=args.name or "",
                    description=args.description or "",
                )
            except ValueError as exc:
                print(f"mew: {exc}", file=sys.stderr)
                return 1
            data = entry_to_dict(entry)
            if args.json:
                print(json.dumps({"entry": data}, ensure_ascii=False, indent=2))
            else:
                print(f"remembered {entry.scope}.{entry.memory_type}: {entry.name}")
                if entry.path:
                    print(f"path: {entry.path}")
            return 0
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
        try:
            results = recall_memory(
                state,
                args.search,
                limit=args.limit,
                scope=args.scope,
                memory_type=args.memory_type,
            )
        except ValueError as exc:
            print(f"mew: {exc}", file=sys.stderr)
            return 1
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
            if result.get("memory_type"):
                details.append(f"type={result.get('memory_type')}")
            if result.get("path"):
                details.append(str(result.get("path")))
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
        typed_entries = FileMemoryBackend(".").entries()
        print("typed_memory:")
        if typed_entries:
            for entry in typed_entries:
                print(f"- {entry.scope}.{entry.memory_type} {entry.name}: {entry.description}")
        else:
            print("- none")
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

    next_text = f"inspect with `{mew_command('task', 'show', task['id'])}`"
    if review_run and review_run.get("status") == "dry_run":
        force = ["--force-review"] if review_requires_force else []
        next_text = f"start review for real with `{mew_command('buddy', '--task', task['id'], '--review', *force)}`"
    elif review_run and review_run.get("status") == "running":
        next_text = f"wait for review with `{mew_command('agent', 'wait', review_run['id'])}`"
    elif plan and not args.dispatch and not args.review:
        next_text = f"dispatch with `{mew_command('buddy', '--task', task['id'], '--dispatch', '--dry-run')}`"
    elif run and run.get("status") == "dry_run":
        next_text = f"start for real with `{mew_command('buddy', '--task', task['id'], '--dispatch')}`"
    elif run and run.get("status") == "running":
        next_text = f"wait with `{mew_command('agent', 'wait', run['id'])}`"
    elif run and run.get("status") in ("completed", "failed") and not review_run:
        next_text = f"review with `{mew_command('buddy', '--task', task['id'], '--review', '--dry-run')}`"

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

def format_outbox_line(message, max_text_chars=MAX_OUTBOX_TEXT_CHARS):
    created_at = message.get("created_at") or "unknown-time"
    message_id = message.get("id")
    message_type = message.get("type") or "message"
    text = str(message.get("text") or "")
    if max_text_chars and len(text) > max_text_chars:
        omitted = len(text) - max_text_chars
        text = (
            text[:max_text_chars].rstrip()
            + f"\n... truncated {omitted} char(s); use `{mew_command('outbox', '--json')}` for full text"
        )
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


def messages_for_kind_scope(state, messages, kind=None):
    if not kind:
        return list(messages)
    tasks = filter_tasks_by_kind(state.get("tasks", []), kind=kind)
    return filter_messages_for_tasks(messages, tasks, kind=kind)


def emit_initial_outbox(history, unread, mark_read, kind=None):
    state = load_state()
    seen_ids = {str(message.get("id")) for message in state["outbox"]}
    if history:
        messages = list(state["outbox"])
    elif unread:
        messages = [message for message in state["outbox"] if not message.get("read_at")]
    else:
        messages = []
    messages = messages_for_kind_scope(state, messages, kind=kind)
    print_outbox_messages(messages)
    if mark_read:
        mark_outbox_read(message.get("id") for message in messages)
    return seen_ids


def emit_new_outbox(seen_ids, mark_read, kind=None):
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
    messages = messages_for_kind_scope(state, messages, kind=kind)
    print_outbox_messages(messages)
    if mark_read:
        mark_outbox_read(message.get("id") for message in messages)
    return len(messages)


def stream_outbox_and_input(args, allow_input):
    kind = getattr(args, "kind", None) or None
    seen_ids = emit_initial_outbox(args.history, args.unread, args.mark_read, kind=kind)
    activity_offset = current_log_offset() if args.activity else None
    deadline = None
    if args.timeout is not None:
        deadline = time.monotonic() + max(0.0, args.timeout)

    while True:
        emit_new_outbox(seen_ids, args.mark_read, kind=kind)
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
/scope [kind|off]     show or change the chat kind scope
/focus [kind]         show the quiet next-action view
/daily [kind]         alias for /focus
/brief [kind]         show the current operational brief
/next [kind]          show the next useful move
/doctor              show state/runtime health
/repair [--force] [--dry-run]
                    reconcile state if the runtime is stopped
/status [kind]        show compact runtime status
/perception           show passive workspace observations
/add <title> [| desc] create a task from chat
/tasks [all]          list open tasks, or all tasks
/show <task-id>       show task details
/work [task-id]       show task plan/runs/checks and next action
/work-session [cmd]   show/start/close/stop/note/steer/queue/interrupt/recover/ai/live/resume/timeline/approve/reject native work session; add details
/continue [opts|text] run one live step; plain text becomes work guidance; /c is alias
/follow [opts|text]   run compact continuous live steps; defaults to 10 steps
/work-mode [on|off]   toggle chat mode where text guides /continue and blank repeats after one work step
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
/self [focus]         create/plan self-improvement; add native, start, dispatch, or dry-run
/pause [reason]       pause autonomous non-user work
/resume               resume autonomous non-user work
/mode <level>         override autonomy level: observe|propose|act|default
/ack all|routine|<ids...> mark outbox messages as read
/reply <id> <text>    answer an open question
/activity [kind|on|off] show scoped activity; on/off toggles runtime lines
/history              print all outbox messages
/transcript [n]       print recent chat input transcript
/exit                 leave chat
Any non-slash line is sent to mew as a user message unless work-mode is on."""


def chat_kind_filter(rest, default_kind=None, usage="usage: /focus [kind] or /focus --kind <kind>"):
    if not rest:
        return default_kind, ""
    try:
        tokens = shlex.split(rest)
    except ValueError as exc:
        return None, f"invalid kind filter: {exc}"
    if len(tokens) == 1:
        token = tokens[0]
        candidate = token.removeprefix("--kind=") if token.startswith("--kind=") else token
    elif len(tokens) == 2 and tokens[0] == "--kind":
        candidate = tokens[1]
    else:
        return None, usage
    kind = normalize_task_kind(candidate)
    if not kind:
        return None, "kind must be one of: coding, research, personal, admin, unknown"
    return kind, ""

CHAT_WORK_HELP = """Work session quick help:
/work-session                         show active session, or recent sessions if none is active
/work-session details                 show active session with decisions, diffs, failures, and tool calls
/work-session diffs                   show only recent write/edit diff previews
/work-session tests                   show recent test and verification output
/work-session commands                show recent command stdout/stderr
/work-session cells                   show stable cockpit cells for model/tool state
/work-session timeline                show compact model/tool event timeline
/work-session resume [task-id]        show a compact reentry bundle
/work-session <task-id> resume        same as resume; task-first order is accepted
/work-session resume --allow-read .   add live git/file world state to the reentry bundle
/work-session resume --auto-recover-safe --allow-read .|--allow-write .
                                      retry one interrupted safe tool before showing resume
/work-session start <task-id>         start or reuse a native work session
/outside chat: mew code <task-id>     enter coding scoped work-mode chat
/outside chat: mew do <task-id>       run the common supervised coding loop
/continue --allow-read .              run one live resident-model step
/c --allow-read .                     short alias for /continue
/follow --allow-read .                run a compact bounded live loop; default max 10
/work-session live --allow-read . --max-steps 3
                                      run a short bounded resident-model loop
/work-session <task-id> live --allow-read .
                                      same as live; task-first order is accepted
/work-session live --compact-live     show thinking/action/result panes without full per-step resumes
/work-session live                    prompts inline for dry-run writes in an interactive TTY
/work-session live --no-prompt-approval
                                      disable inline dry-run write prompts for this run
/continue <guidance>                  reuse prior live options with new guidance
/work-mode on                         text becomes /continue guidance; blank repeats after one work step
/work-session stop <reason>           pause the live loop at the next boundary
/work-session note <text>             save a durable note for future work context
/outside chat: mew memory --add "Prefer compact diffs" --category preferences
                                      add durable preferences injected into work reentry
/work-session steer <text>            queue one-time guidance for the next live/follow step
/work-session queue <text>            queue FIFO follow-up input for a later live/follow step
/work-session interrupt <text>        stop at boundary and submit this as the next step
/outside chat: mew work <task-id> --reply-schema --json
                                      print the structured observer reply template
/work-session approve <id> ...        apply a dry-run write after explicit gates
/work-session reject <id> <reason>    reject a pending write"""

CHAT_EOF = object()


def print_chat_status(kind=None):
    state = load_state()
    lock = read_lock()
    lock_state = "none"
    if lock:
        lock_state = "active" if pid_alive(lock.get("pid")) else "stale"
    tasks = filter_tasks_by_kind(open_tasks(state), kind=kind)
    task_ids = {str(task.get("id")) for task in tasks}
    questions = filter_questions_for_tasks(open_questions(state), tasks, kind=kind)
    attention = filter_attention_for_tasks(open_attention_items(state), tasks, kind=kind)
    unread = [message for message in state["outbox"] if not message.get("read_at")]
    unread = messages_for_kind_scope(state, unread, kind=kind)
    running_agents = [run for run in state["agent_runs"] if run.get("status") in ("created", "running")]
    if kind:
        running_agents = [run for run in running_agents if str(run.get("task_id")) in task_ids]
    print(f"runtime: {state['runtime_status'].get('state')} lock={lock_state} pid={state['runtime_status'].get('pid')}")
    agent = scoped_agent_status(state, kind=kind)
    print(f"agent: {agent.get('mode')} focus={agent.get('current_focus') or '(none)'}")
    autonomy = state.get("autonomy", {})
    print(
        f"autonomy: enabled={autonomy.get('enabled')} level={autonomy.get('level')} "
        f"paused={autonomy.get('paused')} override={autonomy.get('level_override') or '(none)'}"
    )
    if kind:
        print(f"scope: {kind}")
    print(
        f"counts: tasks={len(tasks)} questions={len(questions)} "
        f"attention={len(attention)} unread={len(unread)} running_agents={len(running_agents)}"
    )
    print(f"next: {next_move(state, kind=kind)}")


def print_chat_perception():
    print(format_perception(perceive_workspace(allowed_read_roots=["."], cwd=".")))


def print_chat_tasks(show_all=False, kind=None):
    state = load_state()
    tasks = state["tasks"] if show_all else open_tasks(state)
    tasks = filter_tasks_by_kind(tasks, kind=kind)
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
    print(f"notes: {format_task_notes_display(task.get('notes') or '')}")
    print(f"command: {task.get('command') or ''}")
    print(f"cwd: {task.get('cwd') or ''}")
    print(f"auto_execute: {task.get('auto_execute')}")
    print(f"agent_model: {task.get('agent_model') or ''}")
    print(f"agent_run_id: {task.get('agent_run_id') or ''}")
    print(f"latest_plan_id: {task.get('latest_plan_id') or ''}")


def print_chat_workbench(task_id, kind=None):
    state = load_state()
    task = select_workbench_task(state, task_id, kind=kind)
    if not task:
        if task_id:
            print(f"mew: task not found: {task_id}")
        elif kind:
            print(f"No {kind} tasks.")
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
        "auth": None,
        "model_backend": DEFAULT_MODEL_BACKEND,
        "model": None,
        "base_url": None,
        "model_timeout": 60.0,
        "max_steps": None,
        "act_mode": None,
        "work_guidance": "",
        "progress": False,
        "live": False,
        "follow": False,
        "stream_model": False,
        "compact_live": False,
        "quiet": False,
        "prompt_approval": False,
        "no_prompt_approval": False,
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
        if token == "--follow":
            args["follow"] = True
            args["live"] = True
            index += 1
            continue
        if token == "--stream-model":
            args["stream_model"] = True
            index += 1
            continue
        if token == "--compact-live":
            args["compact_live"] = True
            index += 1
            continue
        if token == "--quiet":
            args["quiet"] = True
            index += 1
            continue
        if token == "--prompt-approval":
            args["prompt_approval"] = True
            index += 1
            continue
        if token == "--no-prompt-approval":
            args["no_prompt_approval"] = True
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
        if token == "--follow":
            index += 1
            continue
        if token == "--work-guidance":
            index += 2
            continue
        if token.startswith("--work-guidance="):
            index += 1
            continue
        kept.append(token)
        index += 1
    return shlex.join(kept)


def _work_options_with_max_steps(rest, max_steps):
    try:
        parts = shlex.split(rest or "")
    except ValueError:
        return " ".join(part for part in ((rest or "").strip(), "--max-steps", str(max_steps)) if part)
    kept = []
    index = 0
    while index < len(parts):
        token = parts[index]
        if token == "--max-steps":
            index += 2
            continue
        if token.startswith("--max-steps="):
            index += 1
            continue
        kept.append(token)
        index += 1
    kept.extend(["--max-steps", str(max_steps)])
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


def _split_continue_options_and_guidance(rest):
    try:
        parts = shlex.split(rest or "")
    except ValueError:
        return (rest or "").strip(), ""
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
    flag_options = {
        "--allow-shell",
        "--allow-verify",
        "--progress",
        "--live",
        "--follow",
        "--stream-model",
        "--compact-live",
        "--quiet",
        "--prompt-approval",
        "--no-prompt-approval",
    }
    value_option_prefixes = tuple(f"{option}=" for option in value_options)
    kept = []
    index = 0
    if parts and parts[0].lstrip("#").isdigit():
        kept.append(parts[0])
        index = 1
    while index < len(parts):
        token = parts[index]
        if token in value_options:
            if index + 1 >= len(parts):
                return shlex.join(parts), ""
            kept.extend([token, parts[index + 1]])
            index += 2
            continue
        if token.startswith(value_option_prefixes) or token in flag_options:
            kept.append(token)
            index += 1
            continue
        if token.startswith("-"):
            return shlex.join(parts), ""
        return shlex.join(kept), " ".join(parts[index:])
    return shlex.join(kept), ""


def _continue_options_should_use_cached_defaults(options):
    try:
        parts = shlex.split(options or "")
    except ValueError:
        return False
    if not parts:
        return False
    if parts[0].lstrip("#").isdigit():
        return False
    explicit_target_options = {
        "--auth",
        "--model-backend",
        "--model",
        "--base-url",
        "--model-timeout",
        "--allow-read",
        "--allow-write",
        "--verify-command",
        "--verify-timeout",
    }
    explicit_target_flags = {
        "--allow-shell",
        "--allow-verify",
    }
    explicit_target_prefixes = tuple(f"{option}=" for option in explicit_target_options)
    return not any(
        token in explicit_target_options
        or token.startswith(explicit_target_prefixes)
        or token in explicit_target_flags
        for token in parts
    )


def _strip_cached_work_control_options(cached, override_options):
    try:
        override_parts = shlex.split(override_options or "")
        cached_parts = shlex.split(cached or "")
    except ValueError:
        return (cached or "").strip()
    singleton_value_options = {"--max-steps", "--act-mode"}
    override_names = {
        token.split("=", 1)[0]
        for token in override_parts
        if token in singleton_value_options or token.split("=", 1)[0] in singleton_value_options
    }
    if not override_names:
        return shlex.join(cached_parts)
    kept = []
    index = 0
    while index < len(cached_parts):
        token = cached_parts[index]
        option_name = token.split("=", 1)[0]
        if option_name in override_names:
            index += 2 if token == option_name else 1
            continue
        kept.append(token)
        index += 1
    return shlex.join(kept)


def _chat_continue_rest(rest, chat_state):
    rest = (rest or "").strip()
    cached = (chat_state or {}).get("work_continue_options", "").strip()
    if not cached:
        cached = work_chat_continue_options(active_work_session(load_state()))
    if not rest:
        return cached
    if _looks_like_work_continue_options(rest):
        options, guidance_text = _split_continue_options_and_guidance(rest)
        if cached and _continue_options_should_use_cached_defaults(options):
            cached = _strip_cached_work_control_options(cached, options)
            options = " ".join(part for part in (cached, options) if part)
        if guidance_text:
            guidance = "--work-guidance " + shlex.quote(guidance_text)
            return " ".join(part for part in (options, guidance) if part)
        return options
    guidance = "--work-guidance " + shlex.quote(rest)
    return " ".join(part for part in (cached, guidance) if part)


def _chat_follow_rest(rest, chat_state):
    options = _chat_continue_rest(rest, chat_state)
    try:
        parts = shlex.split(options or "")
    except ValueError:
        return " ".join(part for part in (options, "--follow") if part)
    if "--follow" not in parts:
        parts.append("--follow")
    return shlex.join(parts)


def _remember_work_continue_options(parts, chat_state):
    if chat_state is None:
        return
    options = _strip_work_guidance_options(shlex.join(parts[1:]))
    if options:
        chat_state["work_continue_options"] = options


def chat_set_work_mode(rest, chat_state):
    if chat_state is None:
        chat_state = {}
    value = (rest or "").strip().casefold()
    if not value:
        enabled = not bool(chat_state.get("work_mode"))
    elif value in ("on", "true", "1", "yes"):
        enabled = True
    elif value in ("off", "false", "0", "no"):
        enabled = False
    else:
        print("usage: /work-mode [on|off]")
        return
    chat_state["work_mode"] = enabled
    chat_state["blank_continue_ready"] = False
    if enabled:
        print("work-mode: on; text becomes /continue guidance; blank line repeats after one work step")
    else:
        print("work-mode: off; text is sent as user messages")


def _parse_chat_work_resume_args(parts):
    task_id = None
    allow_read = []
    allow_write = []
    auto_recover_safe = False
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
        if token == "--allow-write" and index + 1 < len(parts):
            allow_write.append(parts[index + 1])
            index += 2
            continue
        if token.startswith("--allow-write="):
            allow_write.append(token.partition("=")[2])
            index += 1
            continue
        if token == "--auto-recover-safe":
            auto_recover_safe = True
            index += 1
            continue
        if token.lstrip("#").isdigit() and task_id is None:
            task_id = token.lstrip("#")
            index += 1
            continue
        return None, None, None, False, f"mew: unsupported resume option: {token}"
    return task_id, allow_read, allow_write, auto_recover_safe, ""


def _work_read_flags_from_options(option_text, session=None):
    roots = []
    try:
        parts = shlex.split(option_text or "")
    except ValueError:
        parts = []
    index = 0
    while index < len(parts):
        token = parts[index]
        if token == "--allow-read" and index + 1 < len(parts):
            roots.append(parts[index + 1])
            index += 2
            continue
        if token.startswith("--allow-read="):
            roots.append(token.partition("=")[2])
        index += 1
    if not roots:
        roots = list(((session or {}).get("default_options") or {}).get("allow_read") or [])
    if not roots:
        roots = ["."]
    flags = []
    for root in roots:
        flags.extend(["--allow-read", root])
    return shlex.join(flags)


def _replace_work_allow_read_options(option_text, roots):
    try:
        parts = shlex.split(option_text or "")
    except ValueError:
        parts = []
    kept = []
    index = 0
    while index < len(parts):
        token = parts[index]
        if token == "--allow-read":
            index += 2
            continue
        if token.startswith("--allow-read="):
            index += 1
            continue
        kept.append(token)
        index += 1
    for root in roots or []:
        kept.extend(["--allow-read", root])
    return shlex.join(kept)


def _append_work_cockpit_approval_lines(lines, resume):
    resume = resume or {}
    if resume.get("approve_all_blocked_reason"):
        lines.append(f"- approve all blocked: {resume.get('approve_all_blocked_reason')}")
        if resume.get("override_approve_all_hint"):
            lines.append(f"- {resume.get('override_approve_all_hint')}")
    elif resume.get("approve_all_hint"):
        lines.append(f"- {resume.get('approve_all_hint')}")
    for approval in resume.get("pending_approvals") or []:
        if approval.get("approval_blocked_reason"):
            lines.append(f"- approve blocked for #{approval.get('tool_call_id')}: {approval.get('approval_blocked_reason')}")
            if approval.get("override_approve_hint"):
                lines.append(f"- {approval.get('override_approve_hint')}")
        elif approval.get("approve_hint"):
            lines.append(f"- {approval.get('approve_hint')}")
        if approval.get("reject_hint"):
            lines.append(f"- {approval.get('reject_hint')}")


def format_work_cockpit_controls(state=None, session=None, continue_options="", compact=False, terse=False):
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
    resume = build_work_session_resume(session, task=work_session_task(state, session), state=state)
    if session.get("stop_requested_at"):
        cached = (continue_options or "").strip() or work_chat_continue_options(session)
        if session.get("stop_action") == "interrupt_submit" and not work_session_has_running_activity(session):
            lines.append("Primary")
            if terse:
                lines.append("- /c")
                lines.append("- /follow")
                lines.append("- /continue <guidance>")
            elif cached:
                lines.append(f"- /c {cached}")
                lines.append(f"- /follow {_work_options_with_max_steps(cached, 10)}")
                lines.append("- /continue <guidance>")
            else:
                lines.append("- /c --allow-read .")
                lines.append("- /follow --allow-read . --max-steps 10")
                lines.append("- /continue --allow-read .")
                lines.append('- /continue --allow-read . --work-guidance "focus ..."')
        _append_work_cockpit_approval_lines(lines, resume)
        lines.append(f"- /work-session resume{task_suffix}")
        lines.append("- /work-session details")
        lines.append("- /work-session diffs")
        lines.append("- /work-session close")
        return "\n".join(lines)

    recovery_command = work_cockpit_recovery_command(resume, task_id=task_id)
    if recovery_command:
        lines.append("Recovery")
        lines.append(f"- {recovery_command}")
    _append_work_cockpit_approval_lines(lines, resume)

    cached = (continue_options or "").strip() or work_chat_continue_options(session)
    read_flags = _work_read_flags_from_options(cached, session=session)
    lines.append("Primary")
    if terse:
        lines.append("- /c")
        lines.append("- /follow")
        lines.append("- /continue <guidance>")
    elif cached:
        lines.append(f"- /c {cached}")
        lines.append(f"- /follow {_work_options_with_max_steps(cached, 10)}")
        lines.append("- /continue <guidance>")
    else:
        lines.append("- /c --allow-read .")
        lines.append("- /follow --allow-read . --max-steps 10")
        lines.append("- /continue --allow-read .")
        lines.append('- /continue --allow-read . --work-guidance "focus ..."')
    if compact:
        lines.append("Inspect")
        lines.append(f"- /work-session resume {read_flags}")
        lines.append("- /work-session details")
        lines.append("- /help work for diffs, tests, commands, cells, manage, and advanced controls")
        return "\n".join(lines)
    lines.append("Inspect")
    lines.append(f"- /work-session resume {read_flags}")
    lines.append("- /work-session details")
    lines.append("- /work-session diffs")
    lines.append("- /work-session tests")
    lines.append("- /work-session commands")
    lines.append("- /work-session cells")
    lines.append("- /work-session timeline")
    lines.append("Manage")
    lines.append("- /work-session note <remember this>")
    lines.append("- /work-session steer <next-step guidance>")
    lines.append("- /work-session queue <follow-up for a later step>")
    lines.append("- /work-session interrupt <submit immediately at next boundary>")
    lines.append("- /work-session stop <reason>")
    lines.append("- /work-session close")
    lines.append("Advanced")
    if cached:
        lines.append(f"- /continue {cached}")
        lines.append(f"- /work-session live {_work_options_with_max_steps(cached, 3)}")
    else:
        lines.append("- /work-session live --allow-read . --max-steps 3")
    lines.append(f"- /work-session recover {read_flags}")
    return "\n".join(lines)


def chat_work_session(rest, chat_state=None):
    try:
        parts = shlex.split(rest)
    except ValueError as exc:
        print(f"mew: {exc}")
        return
    details = "details" in {part.casefold() for part in parts}
    parts = [part for part in parts if part.casefold() != "details"]
    task_first_actions = {
        "show",
        "start",
        "close",
        "stop",
        "note",
        "steer",
        "queue",
        "interrupt",
        "recover",
        "ai",
        "step",
        "live",
        "resume",
        "timeline",
        "diffs",
        "tests",
        "commands",
        "cells",
    }
    task_first = False
    if len(parts) >= 2 and parts[0].lstrip("#").isdigit() and parts[1].casefold() in task_first_actions:
        task_first = True
        parts = [parts[1], parts[0], *parts[2:]]
    action = parts[0].casefold() if parts else "show"
    task_id = parts[1] if len(parts) > 1 else None
    if action not in (
        "show",
        "start",
        "close",
        "stop",
        "note",
        "steer",
        "queue",
        "interrupt",
        "recover",
        "ai",
        "step",
        "live",
        "resume",
        "timeline",
        "diffs",
        "tests",
        "commands",
        "cells",
        "approve",
        "reject",
    ):
        task_id = parts[0] if parts else None
        action = "show"
    scope_kind = (chat_state or {}).get("kind")

    if action == "start":
        with state_lock():
            state = load_state()
            task = select_workbench_task(state, task_id, kind=scope_kind)
            if not task:
                if task_id:
                    print(f"mew: task not found: {task_id}")
                elif scope_kind:
                    print(f"No {scope_kind} tasks.")
                else:
                    print("No tasks.")
                return
            if task.get("status") == "done":
                print(done_task_work_session_error(task))
                return
            session, created = create_work_session(state, task)
            save_state(state)
        print(("created " if created else "reused ") + f"work session #{session['id']} for task #{task['id']}")
        print(format_work_session(session, task=task))
        return

    if action == "close":
        snapshot_file = None
        with state_lock():
            state = load_state()
            session = active_work_session_for_kind(state, scope_kind)
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
            snapshot_file = save_snapshot(take_snapshot(session["id"], state=state))
        print(f"closed work session #{session['id']}")
        print(f"snapshot saved: {snapshot_file}")
        return

    if action == "stop":
        scoped_task_id = None
        if scope_kind:
            state = load_state()
            session = active_work_session_for_kind(state, scope_kind)
            if not session:
                print(format_no_active_work_session(state, kind=scope_kind))
                return
            scoped_task_id = session.get("task_id")
        args = SimpleNamespace(task_id=scoped_task_id, stop_reason=" ".join(parts[1:]), json=False)
        cmd_work_stop_session(args)
        state = load_state()
        session = active_work_session_for_kind(state, scope_kind)
        print(
            format_work_cockpit_controls(
                state=state,
                session=session,
                continue_options=(chat_state or {}).get("work_continue_options", ""),
            )
        )
        return

    if action == "note":
        scoped_task_id = None
        note_parts = parts[1:]
        if task_first:
            scoped_task_id = task_id
            note_parts = parts[2:]
        if scope_kind:
            state = load_state()
            session = active_work_session_for_kind(state, scope_kind)
            if not session:
                print(format_no_active_work_session(state, kind=scope_kind))
                return
            scoped_task_id = session.get("task_id")
        args = SimpleNamespace(task_id=scoped_task_id, session_note=" ".join(note_parts), json=False)
        cmd_work_session_note(args)
        state = load_state()
        session = active_work_session_for_kind(state, scope_kind)
        print(
            format_work_cockpit_controls(
                state=state,
                session=session,
                continue_options=(chat_state or {}).get("work_continue_options", ""),
            )
        )
        return

    if action == "steer":
        scoped_task_id = None
        steer_parts = parts[1:]
        if task_first:
            scoped_task_id = task_id
            steer_parts = parts[2:]
        if scope_kind:
            state = load_state()
            session = active_work_session_for_kind(state, scope_kind)
            if not session:
                print(format_no_active_work_session(state, kind=scope_kind))
                return
            scoped_task_id = session.get("task_id")
        args = SimpleNamespace(task_id=scoped_task_id, steer=" ".join(steer_parts), json=False)
        cmd_work_steer(args)
        state = load_state()
        session = active_work_session_for_kind(state, scope_kind)
        print(
            format_work_cockpit_controls(
                state=state,
                session=session,
                continue_options=(chat_state or {}).get("work_continue_options", ""),
            )
        )
        return

    if action == "queue":
        scoped_task_id = None
        followup_parts = parts[1:]
        if task_first:
            scoped_task_id = task_id
            followup_parts = parts[2:]
        if scope_kind:
            state = load_state()
            session = active_work_session_for_kind(state, scope_kind)
            if not session:
                print(format_no_active_work_session(state, kind=scope_kind))
                return
            scoped_task_id = session.get("task_id")
        args = SimpleNamespace(
            task_id=scoped_task_id,
            queue_followup=" ".join(followup_parts),
            json=False,
        )
        cmd_work_queue_followup(args)
        state = load_state()
        session = active_work_session_for_kind(state, scope_kind)
        print(
            format_work_cockpit_controls(
                state=state,
                session=session,
                continue_options=(chat_state or {}).get("work_continue_options", ""),
            )
        )
        return

    if action == "interrupt":
        scoped_task_id = None
        interrupt_parts = parts[1:]
        if task_first:
            scoped_task_id = task_id
            interrupt_parts = parts[2:]
        if scope_kind:
            state = load_state()
            session = active_work_session_for_kind(state, scope_kind)
            if not session:
                print(format_no_active_work_session(state, kind=scope_kind))
                return
            scoped_task_id = session.get("task_id")
        args = SimpleNamespace(
            task_id=scoped_task_id,
            interrupt_submit=" ".join(interrupt_parts),
            json=False,
        )
        cmd_work_interrupt_submit(args)
        state = load_state()
        session = active_work_session_for_kind(state, scope_kind)
        print(
            format_work_cockpit_controls(
                state=state,
                session=session,
                continue_options=(chat_state or {}).get("work_continue_options", ""),
            )
        )
        return

    if action == "recover":
        recover_parts = ["recover", *parts[1:]]
        args, error = _parse_chat_work_ai_args(recover_parts)
        if error:
            print(error)
            return
        if scope_kind and not args.task_id:
            state = load_state()
            session = active_work_session_for_kind(state, scope_kind)
            if not session:
                print(format_no_active_work_session(state, kind=scope_kind))
                return
            args.task_id = session.get("task_id")
        args.recover_session = True
        args.json = False
        cmd_work_recover_session(args)
        state = load_state()
        session = active_work_session_for_kind(state, scope_kind)
        print(
            format_work_cockpit_controls(
                state=state,
                session=session,
                continue_options=(chat_state or {}).get("work_continue_options", ""),
            )
        )
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
            state = load_state()
            if scope_kind and not args.task_id:
                session = active_work_session_for_kind(state, scope_kind)
                if not session:
                    print(format_no_active_work_session(state, kind=scope_kind))
                    return
                args.task_id = session.get("task_id")
            session = _select_active_work_session_for_args(state, args)
            live_session_id = session.get("id") if session else None
        work_exit_code = cmd_work_ai(args)
        if action == "live":
            if work_exit_code in (0, 130):
                _remember_work_continue_options(parts, chat_state)
            state = load_state()
            session = find_work_session(state, live_session_id) if live_session_id else None
            if session is None and args.task_id:
                session = _latest_work_session_for_task(state, args.task_id)
            print(
                format_work_cockpit_controls(
                    state=state,
                    session=session,
                    continue_options=(chat_state or {}).get("work_continue_options", ""),
                    compact=True,
                    terse=bool((chat_state or {}).get("compact_controls")),
                )
            )
        return

    if action == "resume":
        task_id, allow_read, allow_write, auto_recover_safe, error = _parse_chat_work_resume_args(parts)
        if error:
            print(error)
            return
        state = load_state()
        session = active_work_session_for_kind(state, scope_kind)
        if task_id:
            session = _latest_work_session_for_task(state, task_id)
        auto_recovery = None
        if auto_recover_safe:
            recover_args = SimpleNamespace(
                task_id=task_id,
                allow_read=allow_read,
                allow_write=allow_write,
                progress=False,
                json=False,
            )
            _, auto_recovery = _work_recover_safe_session(recover_args)
            state = load_state()
            session = active_work_session_for_kind(state, scope_kind)
            if task_id:
                session = _latest_work_session_for_task(state, task_id)
        resume = build_work_session_resume(session, task=work_session_task(state, session), state=state)
        if resume and allow_read:
            attach_work_resume_world_state(resume, build_work_world_state(resume, allow_read))
        snapshot_summary = work_session_snapshot_summary(session, state) if resume else {}
        if not resume and not task_id:
            if auto_recovery is not None:
                print("Auto recovery")
                print_work_recovery_report(auto_recovery)
                print("")
            print(format_no_active_work_session(state, kind=scope_kind))
            return
        if auto_recovery is not None:
            print("Auto recovery")
            print_work_recovery_report(auto_recovery)
            print("")
        if resume and not task_id and scope_kind:
            active_matches = active_work_sessions_for_kind(state, scope_kind)
            if len(active_matches) > 1:
                selected_task_id = session.get("task_id") if session else ""
                print(
                    f"selected active work session for task #{selected_task_id}; "
                    "choose another with /work-session resume <task-id>"
                )
        print(format_work_session_resume(resume))
        snapshot_text = format_work_session_snapshot_summary(snapshot_summary)
        if snapshot_text:
            print(snapshot_text)
        if resume:
            continue_options = (chat_state or {}).get("work_continue_options", "") or work_chat_continue_options(session)
            if allow_read:
                continue_options = _replace_work_allow_read_options(continue_options, allow_read)
                if chat_state is not None:
                    chat_state["work_continue_options"] = continue_options
            compact_controls = bool((chat_state or {}).get("compact_controls"))
            print(
                format_work_cockpit_controls(
                    state=state,
                    session=session,
                    continue_options=continue_options,
                    compact=compact_controls,
                    terse=compact_controls,
                )
            )
        return

    if action == "timeline":
        state = load_state()
        session = active_work_session_for_kind(state, scope_kind)
        if task_id:
            session = _latest_work_session_for_task(state, task_id)
        task = work_session_task(state, session)
        if not session and not task_id:
            print(format_no_active_work_session(state, kind=scope_kind))
            return
        print(format_work_session_timeline(session, task=task))
        if session:
            print(format_work_cockpit_controls(state=state, session=session, continue_options=(chat_state or {}).get("work_continue_options", "")))
        return

    if action == "approve":
        if len(parts) < 2:
            print(
                'usage: /work-session approve <tool-call-id|all> [--task <task-id>] '
                '--allow-write <path> [--defer-verify|--verify-command "<command>"]'
            )
            return
        approve_all = parts[1] == "all"
        if approve_all:
            tool_call_id = None
        else:
            try:
                tool_call_id = int(parts[1])
            except ValueError:
                print(f"mew: invalid tool call id: {parts[1]}")
                return
        approve_task_id = None
        allow_write = []
        allow_unpaired_source_edit = False
        defer_verify = False
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
            if token == "--allow-unpaired-source-edit":
                allow_unpaired_source_edit = True
                index += 1
                continue
            if token == "--defer-verify":
                defer_verify = True
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
        if scope_kind and not approve_task_id:
            state = load_state()
            session = active_work_session_for_kind(state, scope_kind)
            if not session:
                print(format_no_active_work_session(state, kind=scope_kind))
                return
            approve_task_id = session.get("task_id")
        args = SimpleNamespace(
            task_id=approve_task_id,
            approve_tool=tool_call_id,
            allow_write=allow_write,
            allow_verify=bool(verify_command),
            verify_command=verify_command,
            verify_cwd=verify_cwd,
            verify_timeout=verify_timeout,
            allow_unpaired_source_edit=allow_unpaired_source_edit,
            defer_verify=defer_verify,
            allow_read=[],
            json=False,
        )
        if approve_all:
            args.approve_all = True
            cmd_work_approve_all(args)
        else:
            cmd_work_approve_tool(args)
        state = load_state()
        session = active_work_session_for_kind(state, scope_kind)
        print(
            format_work_cockpit_controls(
                state=state,
                session=session,
                continue_options=(chat_state or {}).get("work_continue_options", ""),
            )
        )
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
        if scope_kind and not reject_task_id:
            state = load_state()
            session = active_work_session_for_kind(state, scope_kind)
            if not session:
                print(format_no_active_work_session(state, kind=scope_kind))
                return
            reject_task_id = session.get("task_id")
        args = SimpleNamespace(
            task_id=reject_task_id,
            reject_tool=tool_call_id,
            reject_reason=" ".join(reason_parts),
            json=False,
        )
        cmd_work_reject_tool(args)
        state = load_state()
        session = active_work_session_for_kind(state, scope_kind)
        print(
            format_work_cockpit_controls(
                state=state,
                session=session,
                continue_options=(chat_state or {}).get("work_continue_options", ""),
            )
        )
        return

    state = load_state()
    session = active_work_session_for_kind(state, scope_kind)
    if task_id:
        session = _latest_work_session_for_task(state, task_id)
    elif not session:
        print(format_no_active_work_session(state, kind=scope_kind))
        return
    if action == "diffs":
        print(format_work_session_diffs(session, task=work_session_task(state, session)))
    elif action == "tests":
        print(format_work_session_tests(session, task=work_session_task(state, session)))
    elif action == "commands":
        print(format_work_session_commands(session, task=work_session_task(state, session)))
    elif action == "cells":
        print(format_work_session_cells(session, task=work_session_task(state, session)))
    else:
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


def print_chat_questions(show_all=False, kind=None):
    state = load_state()
    questions = state["questions"] if show_all else open_questions(state)
    tasks = filter_tasks_by_kind(state.get("tasks", []), kind=kind)
    questions = filter_questions_for_tasks(questions, tasks, kind=kind)
    if not questions:
        print("No questions.")
        return
    for question in questions:
        status = question.get("status")
        task = question.get("related_task_id")
        task_text = f" task=#{task}" if task else ""
        context = format_question_context(question)
        print(f"#{question['id']} [{status}]{task_text}{context} {question['text']}")


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


def print_chat_attention(show_all=False, kind=None):
    state = load_state()
    items = state["attention"]["items"] if show_all else open_attention_items(state)
    tasks = filter_tasks_by_kind(state.get("tasks", []), kind=kind)
    items = filter_attention_for_tasks(items, tasks, kind=kind)
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


def print_chat_outbox(show_all=False, kind=None):
    state = load_state()
    messages = state["outbox"] if show_all else [message for message in state["outbox"] if not message.get("read_at")]
    messages = messages_for_kind_scope(state, messages, kind=kind)
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


def cmd_digest(args):
    print_chat_digest()
    return 0


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
        "native",
        "--native",
        "start",
        "--start",
        "start-session",
        "--start-session",
    }
    flags = {part.casefold() for part in parts if part.casefold() in option_tokens}
    dry_run = "dry-run" in flags or "--dry-run" in flags
    dispatch = "dispatch" in flags or "--dispatch" in flags or dry_run
    force = "force" in flags or "--force" in flags
    force_plan = "force-plan" in flags or "--force-plan" in flags
    show_prompt = "prompt" in flags or "--prompt" in flags
    start_session = bool({"start", "--start", "start-session", "--start-session"} & flags)
    ready = dispatch or start_session or "ready" in flags or "--ready" in flags
    auto_execute = "auto-execute" in flags or "--auto-execute" in flags
    native = "native" in flags or "--native" in flags or start_session
    validation_error = self_improve_native_validation_error(
        native=native,
        dispatch=dispatch,
        show_prompt=show_prompt,
        force_plan=force_plan,
    )
    if validation_error:
        print(f"mew: {validation_error}")
        return
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
        plan = None
        plan_created = False
        if not native:
            plan, plan_created = ensure_self_improve_plan(state, task, force=force_plan)
        run = None
        if dispatch:
            run = create_implementation_run_from_plan(state, task, plan, dry_run=dry_run)
            if dry_run:
                ensure_agent_run_prompt_file(run)
                run["command"] = build_ai_cli_run_command(run)
            else:
                start_agent_run(state, run)
        session = None
        session_created = False
        if start_session:
            session, session_created = create_work_session(state, task)
            seed_native_self_improve_session_defaults(session, task)
            seed_native_self_improve_reentry_note(session, task)
        save_state(state)

    print(("created " if created else "reused ") + format_task(task))
    if plan:
        print(("created " if plan_created else "reused ") + format_task_plan(plan))
    if native:
        if session:
            print(("started " if session_created else "reused ") + f"work session #{session['id']}")
        print_native_self_improve_controls(task, include_start_hint=not start_session, session=session)
    if show_prompt:
        if not plan:
            print("No programmer plan was created for native self-improvement.")
            return
        print("implementation_prompt:")
        print(plan.get("implementation_prompt") or "")
        print("review_prompt:")
        print(plan.get("review_prompt") or "")
    if run:
        print_self_improve_run_status(run, dry_run=dry_run, plan=plan)


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
    if command == "scope":
        if not rest:
            scope = chat_state.get("kind") or "off"
            print(f"scope: {scope}")
            return "continue"
        if rest.casefold() in ("off", "none", "global", "all"):
            chat_state["kind"] = None
            print("scope: off")
            return "continue"
        kind, error = chat_kind_filter(
            rest,
            usage="usage: /scope [coding|research|personal|admin|unknown|off]",
        )
        if error:
            print(error)
        else:
            chat_state["kind"] = kind
            print(f"scope: {kind}")
        return "continue"
    if command in ("focus", "daily"):
        kind, error = chat_kind_filter(rest, default_kind=chat_state.get("kind"))
        if error:
            print(error)
        else:
            print(format_focus(build_focus_data(load_state(), limit=3, kind=kind, include_context_checkpoint=True)))
        return "continue"
    if command == "brief":
        kind, error = chat_kind_filter(
            rest,
            default_kind=chat_state.get("kind"),
            usage="usage: /brief [kind] or /brief --kind <kind>",
        )
        if error:
            print(error)
        else:
            print(build_brief(load_state(), kind=kind, include_context_checkpoint=True))
        return "continue"
    if command == "next":
        kind, error = chat_kind_filter(rest, default_kind=chat_state.get("kind"))
        if error:
            print(error)
        else:
            print(next_move(load_state(), kind=kind))
        return "continue"
    if command == "doctor":
        if rest:
            print("usage: /doctor")
        else:
            args = SimpleNamespace(auth=None, require_auth=False)
            print(format_doctor_data(build_doctor_data(args)))
        return "continue"
    if command == "repair":
        repair_parts = rest.split() if rest else []
        invalid = [part for part in repair_parts if part.casefold() not in ("--force", "force", "--dry-run", "dry-run")]
        if invalid:
            print("usage: /repair [--force] [--dry-run]")
        else:
            lowered = {part.casefold() for part in repair_parts}
            args = SimpleNamespace(
                force=bool(lowered & {"--force", "force"}),
                dry_run=bool(lowered & {"--dry-run", "dry-run"}),
                json=False,
            )
            cmd_repair(args)
        return "continue"
    if command == "status":
        kind, error = chat_kind_filter(
            rest,
            default_kind=chat_state.get("kind"),
            usage="usage: /status [kind] or /status --kind <kind>",
        )
        if error:
            print(error)
        else:
            print_chat_status(kind=kind)
        return "continue"
    if command in ("perception", "perceive"):
        print_chat_perception()
        return "continue"
    if command == "add":
        chat_add_task(rest)
        return "continue"
    if command in ("tasks", "task"):
        print_chat_tasks(show_all=rest.casefold() == "all", kind=chat_state.get("kind"))
        return "continue"
    if command == "show":
        if not rest:
            print("usage: /show <task-id>")
        else:
            print_chat_task(rest)
        return "continue"
    if command == "work":
        print_chat_workbench(rest or None, kind=chat_state.get("kind"))
        return "continue"
    if command in ("work-session", "work_session"):
        chat_work_session(rest, chat_state)
        return "continue"
    if command in ("continue", "cont", "c"):
        chat_work_session(("live " + _chat_continue_rest(rest, chat_state)).strip(), chat_state)
        chat_state["blank_continue_ready"] = True
        return "continue"
    if command == "follow":
        chat_work_session(("live " + _chat_follow_rest(rest, chat_state)).strip(), chat_state)
        chat_state["blank_continue_ready"] = True
        return "continue"
    if command in ("work-mode", "workmode"):
        chat_set_work_mode(rest, chat_state)
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
        print_chat_questions(show_all=rest.casefold() == "all", kind=chat_state.get("kind"))
        return "continue"
    if command == "defer":
        chat_defer_question(rest)
        return "continue"
    if command == "reopen":
        chat_reopen_question(rest)
        return "continue"
    if command == "attention":
        print_chat_attention(show_all=rest.casefold() == "all", kind=chat_state.get("kind"))
        return "continue"
    if command == "resolve":
        chat_resolve_attention(rest)
        return "continue"
    if command == "outbox":
        print_chat_outbox(show_all=rest.casefold() == "all", kind=chat_state.get("kind"))
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
    if command in ("transcript", "chat-log"):
        limit = 20
        if rest:
            try:
                limit = int(rest)
            except ValueError:
                print("usage: /transcript [limit]")
                return "continue"
        print(format_chat_transcript(read_chat_transcript(limit=limit)))
        return "continue"
    if command == "activity":
        value = rest.casefold()
        if not rest:
            print(format_activity(load_state(), kind=chat_state.get("kind")))
        elif value in ("on", "true", "1"):
            chat_state["activity"] = True
            chat_state["activity_offset"] = current_log_offset()
            print("activity: on")
        elif value in ("off", "false", "0"):
            chat_state["activity"] = False
            print("activity: off")
        else:
            kind, error = chat_kind_filter(
                rest,
                default_kind=chat_state.get("kind"),
                usage="usage: /activity [coding|research|personal|admin|unknown|--kind <kind>|on|off]",
            )
            if error:
                print(error)
            else:
                print(format_activity(load_state(), kind=kind))
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


def chat_prompt_text(chat_state):
    if (chat_state or {}).get("work_mode"):
        return "mew[work]> "
    return "mew> "


def read_chat_line(poll_interval, prompt_state, prompt="mew> "):
    if not sys.stdin.isatty():
        line = sys.stdin.readline()
        if line == "":
            return CHAT_EOF
        return line.rstrip("\n")

    if prompt_state.get("needed", True):
        print(prompt, end="", flush=True)
        prompt_state["needed"] = False

    readable, _, _ = select.select([sys.stdin], [], [], poll_interval)
    if not readable:
        return None
    line = sys.stdin.readline()
    prompt_state["needed"] = True
    if line == "":
        return CHAT_EOF
    return line.rstrip("\n")


def format_compact_chat_brief(state, kind=None):
    focus = build_focus_data(state, limit=1, kind=kind)
    runtime = state.get("runtime_status", {})
    runtime_phase = runtime.get("phase") or ("running" if runtime.get("pid") else "stopped")
    title = "Mew code"
    if kind:
        title += f" ({kind})"
    active = (focus.get("active_work_sessions") or [])[:1]
    if kind == "coding" and active:
        current_line = (
            f"Current: coding cockpit is open for task #{active[0].get('task_id')}; "
            "use /c, /follow, or /continue <guidance>"
        )
    else:
        current_line = f"Next: {focus.get('next_move')}"
    lines = [
        f"{title}: runtime={runtime_phase} tasks={focus.get('open_task_count') or 0} "
        f"unread={focus.get('unread_outbox_count') or 0}",
        current_line,
    ]
    if active:
        session = active[0]
        lines.append(
            f"Active: #{session.get('id')} task=#{session.get('task_id')} "
            f"phase={session.get('phase')} {session.get('title') or ''}".rstrip()
        )
    return "\n".join(lines)


def cmd_chat(args):
    if getattr(args, "quiet", False):
        args.no_brief = True
        args.no_unread = True
        args.activity = False
    if not getattr(args, "quiet", False):
        print("mew chat. Type /help for commands, /exit to leave.", flush=True)
    kind = getattr(args, "kind", None) or None
    pending_line = None
    can_preload_stdin = args.timeout is None or args.timeout > 0
    if can_preload_stdin and not sys.stdin.isatty():
        try:
            pending_line = sys.stdin.readline()
            if pending_line == "":
                pending_line = CHAT_EOF
        except OSError:
            pending_line = None
    pending_text = pending_line.strip() if isinstance(pending_line, str) else ""
    suppress_startup_controls = bool(getattr(args, "quiet", False)) or pending_text.startswith(
        ("/work-session", "/continue", "/c", "/follow")
    )
    append_chat_transcript(
        "start",
        "chat started",
        kind=kind,
        metadata={"work_mode": bool(getattr(args, "work_mode", False))},
    )
    if kind and not getattr(args, "quiet", False):
        print(f"scope: {kind}", flush=True)
    if getattr(args, "work_mode", False) and not getattr(args, "quiet", False):
        print("work-mode: on; text becomes /continue guidance; blank line repeats after one work step", flush=True)
    state = load_state()
    if not args.no_brief:
        if getattr(args, "compact_brief", False):
            print(format_compact_chat_brief(state, kind=kind), flush=True)
        else:
            print(build_brief(state, limit=args.limit, kind=kind, include_context_checkpoint=True), flush=True)
    session = active_work_session_for_kind(state, kind=kind)
    if session and not suppress_startup_controls:
        print(
            format_work_cockpit_controls(
                state=state,
                session=session,
                compact=bool(getattr(args, "compact_controls", False)),
                terse=bool(getattr(args, "compact_controls", False)),
            ),
            flush=True,
        )

    seen_ids = emit_initial_outbox(
        history=False,
        unread=not args.no_unread,
        mark_read=args.mark_read,
        kind=kind,
    )
    chat_state = {
        "activity": bool(args.activity),
        "activity_offset": current_log_offset() if args.activity else None,
        "kind": kind,
        "work_mode": bool(getattr(args, "work_mode", False)),
        "blank_continue_ready": False,
        "compact_controls": bool(getattr(args, "compact_controls", False)),
    }
    prompt_state = {"needed": True}
    deadline = time.monotonic() + max(0.0, args.timeout) if args.timeout is not None else None

    try:
        while True:
            emit_new_outbox(seen_ids, args.mark_read, kind=kind)
            if chat_state["activity"]:
                chat_state["activity_offset"] = emit_new_activity(chat_state["activity_offset"])
            if deadline is not None and time.monotonic() >= deadline:
                append_chat_transcript("timeout", "chat timeout", kind=chat_state.get("kind"))
                return 0

            poll_interval = args.poll_interval
            if deadline is not None:
                poll_interval = min(poll_interval, max(0.0, deadline - time.monotonic()))

            if pending_line is not None:
                line = pending_line if pending_line is CHAT_EOF else pending_line.rstrip("\n")
                pending_line = None
            else:
                line = read_chat_line(poll_interval, prompt_state, prompt=chat_prompt_text(chat_state))
            if line is None:
                continue
            if line is CHAT_EOF:
                append_chat_transcript("eof", "chat eof", kind=chat_state.get("kind"))
                return 0
            text = line.strip()
            if not text:
                if chat_state.get("work_mode"):
                    if not chat_state.get("blank_continue_ready"):
                        append_chat_transcript("blank_ignored", "", kind=chat_state.get("kind"))
                        print("work-mode: blank ignored until one /c, /follow, or text-guided work step runs", flush=True)
                        continue
                    append_chat_transcript("blank_continue", "/continue", kind=chat_state.get("kind"))
                    result = run_chat_slash_command("/continue", chat_state)
                    if result == "exit":
                        return 0
                continue
            if text.startswith("/"):
                append_chat_transcript("slash", text, kind=chat_state.get("kind"))
                result = run_chat_slash_command(text, chat_state)
                if result == "exit":
                    return 0
                continue
            if chat_state.get("work_mode"):
                append_chat_transcript("work_guidance", text, kind=chat_state.get("kind"))
                result = run_chat_slash_command("/continue " + text, chat_state)
                chat_state["blank_continue_ready"] = True
                if result == "exit":
                    return 0
                continue

            warn_if_runtime_inactive()
            event = queue_user_message(text)
            append_chat_transcript(
                "message",
                text,
                kind=chat_state.get("kind"),
                metadata={"event_id": event.get("id")},
            )
            print(f"queued message event #{event['id']}", flush=True)
    except KeyboardInterrupt:
        append_chat_transcript("interrupt", "keyboard interrupt", kind=chat_state.get("kind"))
        print("\nleft chat")
        return 0

def cmd_log(args):
    if not LOG_FILE.exists():
        print("No runtime log.")
        return 0
    print(LOG_FILE.read_text(encoding="utf-8").rstrip())
    return 0


def append_chat_transcript(entry_type, text="", kind=None, metadata=None):
    ensure_state_dir()
    record = {
        "created_at": now_iso(),
        "type": entry_type,
        "kind": kind or "",
        "text": clip_output(" ".join(str(text or "").splitlines()), 1000),
    }
    if metadata:
        record["metadata"] = metadata
    with CHAT_TRANSCRIPT_FILE.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    return record


def read_chat_transcript(limit=20):
    if not CHAT_TRANSCRIPT_FILE.exists():
        return []
    try:
        lines = CHAT_TRANSCRIPT_FILE.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    records = []
    for line in lines:
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            records.append({"created_at": "", "type": "corrupt", "kind": "", "text": line})
    if limit is None:
        return records
    count = max(0, int(limit))
    if count == 0:
        return []
    return records[-count:]


def format_chat_transcript(records):
    if not records:
        return "No chat transcript."
    lines = ["Chat transcript"]
    for record in records:
        kind = f" kind={record.get('kind')}" if record.get("kind") else ""
        text = record.get("text") or ""
        lines.append(f"- {record.get('created_at') or ''} {record.get('type')}{kind}: {text}".rstrip())
    return "\n".join(lines)


def cmd_chat_log(args):
    records = read_chat_transcript(limit=args.limit)
    if args.json:
        print(json.dumps(records, ensure_ascii=False, indent=2))
    else:
        print(format_chat_transcript(records))
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
    limit = getattr(args, "limit_arg", None)
    records = read_effect_records(limit=limit if limit is not None else args.limit)
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
    recovery_decision = effect.get("recovery_decision") or {}
    if recovery_decision:
        text += (
            f" recovery={recovery_decision.get('action')} "
            f"effect={recovery_decision.get('effect_classification')} "
            f"safety={recovery_decision.get('safety')}"
        )
        world_states = recovery_decision.get("runtime_write_world_states") or []
        if world_states:
            summary = ", ".join(
                f"{item.get('state') or 'unknown'}:{item.get('path') or '-'}"
                for item in world_states
            )
            text += f" write_world={clip_output(summary, 160)}"
    recovery_followup = effect.get("recovery_followup") or {}
    if recovery_followup:
        text += (
            f" followup={recovery_followup.get('action')} "
            f"status={recovery_followup.get('status')} "
            f"command={recovery_followup.get('command') or ''}"
        )
        if recovery_followup.get("question_id"):
            text += f" question=#{recovery_followup.get('question_id')}"
    return text

def cmd_runtime_effects(args):
    state = load_state()
    limit = getattr(args, "limit_arg", None)
    limit = max(0, int(limit if limit is not None else args.limit))
    effects = list(reversed(state.get("runtime_effects", [])[-limit:])) if limit else []
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
