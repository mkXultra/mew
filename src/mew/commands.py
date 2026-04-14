import json
import os
import select
import shlex
import signal
import shutil
import subprocess
import sys
import time

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
from .brief import build_brief, build_brief_data, next_move, verification_outcome
from .codex_api import load_codex_oauth
from .config import LOG_FILE, STATE_DIR
from .errors import MewError
from .memory import compact_memory
from .programmer import (
    create_follow_up_task_from_review,
    create_implementation_run_from_plan,
    create_retry_run_for_implementation,
    create_review_run_for_implementation,
    create_task_plan,
    find_task_plan,
    format_task_plan,
    latest_task_plan,
)
from .self_improve import create_self_improve_task, ensure_self_improve_plan
from .state import (
    add_outbox_message,
    add_event,
    ensure_desires,
    ensure_guidance,
    ensure_policy,
    ensure_self,
    ensure_state_dir,
    find_question,
    load_state,
    mark_message_read,
    mark_question_answered,
    next_id,
    open_attention_items,
    open_questions,
    pid_alive,
    read_desires,
    read_guidance,
    read_policy,
    read_self,
    read_lock,
    save_state,
    state_lock,
)
from .sweep import format_sweep_report, sweep_agent_runs
from .read_tools import inspect_dir, read_file, search_text, summarize_read_result
from .tasks import find_task, format_task, open_tasks, task_sort_key
from .timeutil import now_iso
from .toolbox import format_command_record, run_command_record, run_git_tool
from .write_tools import edit_file, summarize_write_result, write_file


def cmd_task_add(args):
    with state_lock():
        state = load_state()
        current_time = now_iso()
        task = {
            "id": next_id(state, "task"),
            "title": args.title,
            "description": args.description or "",
            "status": "todo",
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
    tasks = state["tasks"] if args.all else open_tasks(state)
    tasks = sorted(tasks, key=task_sort_key)
    if not tasks:
        print("No tasks.")
        return 0
    for task in tasks:
        print(format_task(task))
    return 0

def cmd_task_show(args):
    state = load_state()
    task = find_task(state, args.task_id)
    if not task:
        print(f"mew: task not found: {args.task_id}", file=sys.stderr)
        return 1

    print(format_task(task))
    print(f"description: {task.get('description') or ''}")
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

def cmd_task_done(args):
    with state_lock():
        state = load_state()
        task = find_task(state, args.task_id)
        if not task:
            print(f"mew: task not found: {args.task_id}", file=sys.stderr)
            return 1
        task["status"] = "done"
        task["updated_at"] = now_iso()
        save_state(state)
    print(format_task(task))
    return 0

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

def queue_user_message(text, reply_to_question_id=None):
    current_time = now_iso()
    with state_lock():
        state = load_state()
        payload = {"text": text}
        if reply_to_question_id is not None:
            payload["reply_to_question_id"] = reply_to_question_id
        event = add_event(state, "user_message", "user", payload)
        if reply_to_question_id is not None:
            question = find_question(state, reply_to_question_id)
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

def cmd_message(args):
    event = queue_user_message(args.message)
    print(f"queued message event #{event['id']}")
    if not getattr(args, "wait", False):
        return 0
    warn_if_runtime_inactive()
    return wait_for_event_response(
        event["id"],
        timeout=getattr(args, "timeout", 60.0),
        poll_interval=getattr(args, "poll_interval", 1.0),
        mark_read=getattr(args, "mark_read", False),
    )

def cmd_reply(args):
    with state_lock():
        state = load_state()
        question = find_question(state, args.question_id)
        if not question:
            print(f"mew: question not found: {args.question_id}", file=sys.stderr)
            return 1
    event = queue_user_message(args.text, reply_to_question_id=question["id"])
    print(f"answered question #{question['id']} with event #{event['id']}")
    return 0

def cmd_ack(args):
    with state_lock():
        state = load_state()
        if args.all:
            messages = [message for message in state["outbox"] if not message.get("read_at")]
            for message in messages:
                mark_message_read(state, message["id"])
            save_state(state)
            print(f"acknowledged {len(messages)} message(s)")
            return 0

        if not args.message_ids:
            print("mew: ack requires a message id or --all", file=sys.stderr)
            return 1

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
    with output_path.open("ab") as output:
        process = subprocess.Popen(
            command,
            stdout=output,
            stderr=subprocess.STDOUT,
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

def cmd_doctor(args):
    failed = False

    try:
        state = load_state()
        print("state: ok")
        print(f"state_version: {state.get('version')}")
        print(f"tasks: {len(state.get('tasks', []))}")
        print(f"agent_runs: {len(state.get('agent_runs', []))}")
    except Exception as exc:
        print(f"state: error {exc}")
        failed = True

    lock = read_lock()
    if lock:
        lock_state = "active" if pid_alive(lock.get("pid")) else "stale"
        print(f"runtime_lock: {lock_state} pid={lock.get('pid')}")
    else:
        print("runtime_lock: none")

    for executable in ("ai-cli", "rg"):
        path = shutil.which(executable)
        if path:
            print(f"{executable}: ok {path}")
        else:
            print(f"{executable}: missing")
            failed = True

    try:
        auth = load_codex_oauth(args.auth)
        account = "present" if auth.get("account_id") else "none"
        expires = auth.get("expires") or "(unknown)"
        print(f"codex_auth: ok path={auth.get('path')} account_id={account} expires={expires}")
    except MewError as exc:
        level = "error" if args.require_auth else "missing"
        print(f"codex_auth: {level} {exc}")
        if args.require_auth:
            failed = True

    return 1 if failed else 0

def cmd_brief(args):
    state = load_state()
    if args.json:
        print(json.dumps(build_brief_data(state, limit=args.limit), ensure_ascii=False, indent=2))
        return 0
    print(build_brief(state, limit=args.limit))
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

def command_from_next_move(move):
    parts = (move or "").split("`")
    for index in range(1, len(parts), 2):
        candidate = parts[index].strip()
        if candidate.startswith("mew ") or candidate.startswith("uv run mew "):
            return candidate
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
    return (
        f"#{run.get('id')} [{run.get('operation') or run.get('action_type')}] "
        f"changed={run.get('changed')} dry_run={run.get('dry_run')} "
        f"written={run.get('written')}{rollback} path={run.get('path')}"
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
        result = read_file(args.path, _tool_allowed_roots(args), max_chars=args.max_chars)
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
    if not messages:
        print("No messages.")
        return 0
    for message in messages:
        read = "read" if message.get("read_at") else "unread"
        print(f"#{message['id']} [{message['type']}/{read}] {message['text']}")
    return 0

def cmd_questions(args):
    state = load_state()
    questions = state["questions"] if args.all else open_questions(state)
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
        print(f"resolved {len(items)} attention item(s)")
        return 0

    state = load_state()
    items = state["attention"]["items"] if args.all else open_attention_items(state)
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
    if args.compact:
        with state_lock():
            state = load_state()
            note = compact_memory(state, keep_recent=args.keep_recent, dry_run=args.dry_run)
            if not args.dry_run:
                save_state(state)
        print(note)
        return 0

    state = load_state()
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
        print("decisions:")
        for item in deep.get("decisions", []):
            print(f"- {item}")
    return 0

def cmd_task_run(args):
    with state_lock():
        state = load_state()
        task = find_task(state, args.task_id)
        if not task:
            print(f"mew: task not found: {args.task_id}", file=sys.stderr)
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
    if not args.all:
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
        "session_id",
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
        followup, status = create_follow_up_task_from_review(state, task, review_run)
        save_state(state)
    print(f"review run #{review_run['id']} status={status}")
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

def wait_for_event_response(event_id, timeout=60.0, poll_interval=1.0, mark_read=False):
    deadline = time.monotonic() + max(0.0, timeout)
    seen_ids = set()

    while True:
        state = load_state()
        messages = outbox_for_event(state, event_id)
        new_messages = [
            message
            for message in messages
            if str(message.get("id")) not in seen_ids
        ]
        if new_messages:
            print_outbox_messages(new_messages)
            seen_ids.update(str(message.get("id")) for message in new_messages)
            if mark_read:
                mark_outbox_read(message.get("id") for message in new_messages)
            return 0

        event = find_event_by_id(state, event_id)
        if event and event.get("processed_at"):
            print(f"message event #{event_id} was processed without an outbox response.")
            return 0

        if time.monotonic() >= deadline:
            print(f"mew: timed out waiting for message event #{event_id}", file=sys.stderr)
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
/help                 show this help
/brief                show the current operational brief
/next                 show the next useful move
/status               show compact runtime status
/add <title> [| desc] create a task from chat
/tasks [all]          list open tasks, or all tasks
/show <task-id>       show task details
/note <task-id> <txt> append a task note
/questions [all]      list open questions, or all questions
/attention [all]      list open attention items, or all attention items
/outbox [all]         list unread outbox messages, or all messages
/agents [all]         list running agent runs, or all agent runs
/result <run-id>      collect an agent run result
/wait <run-id> [sec]  wait for an agent run result
/review <run-id>      start a review run; add dry-run to preview
/followup <run-id>    process a completed review run
/retry <run-id>       retry an implementation run; add dry-run to preview
/sweep [dry-run]      collect stale programmer-loop work
/verification         show recent verification runs
/writes               show recent runtime write/edit runs
/why                  explain the latest processed think/act decision
/digest               summarize activity since the last user message
/approve <task-id>    mark a task ready and auto_execute=true
/ready <task-id>      mark a task ready without changing auto_execute
/done <task-id>       mark a task done
/block <task-id>      mark a task blocked
/plan <task-id>       create or show a programmer plan; add prompt to print prompts
/dispatch <task-id>   start an implementation run; add dry-run to preview
/pause [reason]       pause autonomous non-user work
/resume               resume autonomous non-user work
/mode <level>         override autonomy level: observe|propose|act|default
/ack all|<ids...>     mark outbox messages as read
/reply <id> <text>    answer an open question
/activity on|off      toggle runtime activity lines
/history              print all outbox messages
/exit                 leave chat
Any non-slash line is sent to mew as a user message."""

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
    print(f"notes: {task.get('notes') or ''}")
    print(f"command: {task.get('command') or ''}")
    print(f"cwd: {task.get('cwd') or ''}")
    print(f"auto_execute: {task.get('auto_execute')}")
    print(f"agent_model: {task.get('agent_model') or ''}")
    print(f"agent_run_id: {task.get('agent_run_id') or ''}")
    print(f"latest_plan_id: {task.get('latest_plan_id') or ''}")


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


def print_chat_attention(show_all=False):
    state = load_state()
    items = state["attention"]["items"] if show_all else open_attention_items(state)
    if not items:
        print("No attention items.")
        return
    for item in items:
        print(f"#{item['id']} [{item.get('status')}/{item.get('priority')}] {item.get('title')}: {item.get('reason')}")


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


def print_chat_writes():
    state = load_state()
    runs = list(reversed(state.get("write_runs", [])[-10:]))
    if not runs:
        print("No write runs.")
        return
    for run in runs:
        print(format_write_run(run))


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


def run_chat_slash_command(line, chat_state):
    body = line[1:].strip()
    command, _, rest = body.partition(" ")
    command = command.casefold()
    rest = rest.strip()

    if command in ("exit", "quit", "q"):
        return "exit"
    if command in ("help", "?"):
        print(CHAT_HELP)
        return "continue"
    if command == "brief":
        print(build_brief(load_state()))
        return "continue"
    if command == "next":
        print(next_move(load_state()))
        return "continue"
    if command == "status":
        print_chat_status()
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
    if command == "note":
        chat_append_task_note(rest)
        return "continue"
    if command in ("questions", "question"):
        print_chat_questions(show_all=rest.casefold() == "all")
        return "continue"
    if command == "attention":
        print_chat_attention(show_all=rest.casefold() == "all")
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
    if command in ("verification", "verify"):
        print_chat_verification()
        return "continue"
    if command in ("writes", "write"):
        print_chat_writes()
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
            print("usage: /ack all|<ids...>")
            return "continue"
        if rest.casefold() == "all":
            with state_lock():
                state = load_state()
                ids = [message.get("id") for message in state["outbox"] if not message.get("read_at")]
            mark_outbox_read(ids)
            print(f"acknowledged {len(ids)} message(s)")
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
    warn_if_runtime_inactive()
    print("mew chat. Type /help for commands, /exit to leave.", flush=True)
    if not args.no_brief:
        print(build_brief(load_state(), limit=args.limit), flush=True)

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
