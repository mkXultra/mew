#!/usr/bin/env python3
import argparse
import os

from .commands import (
    cmd_attach,
    cmd_ack,
    cmd_agent_list,
    cmd_agent_followup,
    cmd_agent_result,
    cmd_agent_retry,
    cmd_agent_review,
    cmd_agent_show,
    cmd_agent_sweep,
    cmd_agent_wait,
    cmd_archive,
    cmd_activity,
    cmd_attention,
    cmd_brief,
    cmd_buddy,
    cmd_chat,
    cmd_context,
    cmd_desires_init,
    cmd_desires_show,
    cmd_dogfood,
    cmd_doctor,
    cmd_effects,
    cmd_event,
    cmd_focus,
    cmd_guidance_init,
    cmd_guidance_show,
    cmd_listen,
    cmd_log,
    cmd_memory,
    cmd_message,
    cmd_next,
    cmd_outbox,
    cmd_perceive,
    cmd_policy_init,
    cmd_policy_show,
    cmd_questions,
    cmd_repair,
    cmd_reply,
    cmd_self_init,
    cmd_self_improve,
    cmd_self_show,
    cmd_session,
    cmd_snapshot,
    cmd_start,
    cmd_status,
    cmd_step,
    cmd_stop,
    cmd_task_add,
    cmd_task_classify,
    cmd_task_dispatch,
    cmd_task_done,
    cmd_task_list,
    cmd_task_plan,
    cmd_task_run,
    cmd_task_show,
    cmd_task_update,
    cmd_thoughts,
    cmd_tool_git,
    cmd_tool_edit,
    cmd_tool_list,
    cmd_tool_read,
    cmd_tool_search,
    cmd_tool_status,
    cmd_tool_test,
    cmd_tool_write,
    cmd_verification,
    cmd_webhook,
    cmd_writes,
)
from .config import (
    DEFAULT_ATTACH_POLL_INTERVAL_SECONDS,
    DEFAULT_CODEX_MODEL,
    DEFAULT_CODEX_WEB_BASE_URL,
    DEFAULT_INTERVAL_SECONDS,
    DEFAULT_MODEL_BACKEND,
    DEFAULT_TASK_TIMEOUT_SECONDS,
)
from .model_backends import SUPPORTED_MODEL_BACKENDS
from .runtime import run_runtime


def build_parser():
    parser = argparse.ArgumentParser(prog="mew")
    parser.add_argument("-m", "--message", help="queue a message for the runtime")

    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run", help="start the runtime")
    run_parser.add_argument("--once", action="store_true", help="process one loop and exit")
    run_parser.add_argument(
        "--interval",
        type=float,
        default=DEFAULT_INTERVAL_SECONDS,
        help=f"passive wake interval in seconds; default {DEFAULT_INTERVAL_SECONDS:g}",
    )
    run_parser.add_argument(
        "--interval-minutes",
        type=float,
        help="passive wake interval in minutes; overrides --interval",
    )
    run_parser.add_argument(
        "--poll-interval",
        type=float,
        default=1.0,
        help="inbox poll interval in seconds; default 1",
    )
    run_parser.add_argument(
        "--echo-outbox",
        action="store_true",
        help="print newly created outbox messages in the runtime terminal",
    )
    run_parser.add_argument(
        "--notify-command",
        default="",
        help="command to run once for each new outbox message; message fields are passed as MEW_OUTBOX_* env vars",
    )
    run_parser.add_argument(
        "--notify-timeout",
        type=float,
        default=5.0,
        help="seconds to wait for each notify command",
    )
    run_parser.add_argument(
        "--notify-bell",
        action="store_true",
        help="emit a terminal bell when new outbox messages are created",
    )
    run_parser.add_argument(
        "--ai",
        action="store_true",
        help="use the resident model backend for startup and user messages",
    )
    run_parser.add_argument(
        "--ai-ticks",
        action="store_true",
        help="also call the resident model backend for legacy tick events",
    )
    run_parser.add_argument(
        "--execute-tasks",
        action="store_true",
        help="execute one ready auto-execute task on each passive wake",
    )
    run_parser.add_argument(
        "--autonomous",
        action="store_true",
        help="allow self-directed work when there is no pending user input",
    )
    run_parser.add_argument(
        "--autonomy-level",
        choices=("observe", "propose", "act"),
        default="propose",
        help="self-directed freedom level; task execution still requires --execute-tasks",
    )
    run_parser.add_argument(
        "--allow-agent-run",
        action="store_true",
        help="allow autonomous programmer loop to start ai-cli agent runs",
    )
    run_parser.add_argument(
        "--agent-stale-minutes",
        type=float,
        default=60.0,
        help="minutes before active agent runs are marked stale by the runtime reflex sweep",
    )
    run_parser.add_argument(
        "--agent-result-timeout",
        type=float,
        default=10.0,
        help="seconds to wait when polling agent run results in the runtime reflex sweep",
    )
    run_parser.add_argument(
        "--agent-start-timeout",
        type=float,
        default=30.0,
        help="seconds to wait when starting review runs in the runtime reflex sweep",
    )
    run_parser.add_argument(
        "--review-model",
        help="ai-cli model used for autonomous programmer review runs",
    )
    run_parser.add_argument(
        "--allow-verify",
        action="store_true",
        help="allow runtime actions to run the configured verification command",
    )
    run_parser.add_argument(
        "--verify-command",
        help="verification command available to runtime run_verification actions",
    )
    run_parser.add_argument(
        "--verify-timeout",
        type=float,
        default=300.0,
        help="runtime verification command timeout in seconds",
    )
    run_parser.add_argument(
        "--verify-interval-minutes",
        type=float,
        default=60.0,
        help="minimum minutes between autonomous runtime verification runs",
    )
    run_parser.add_argument(
        "--auto-archive",
        action="store_true",
        help="archive old processed inbox and read outbox records after runtime cycles",
    )
    run_parser.add_argument(
        "--archive-keep-recent",
        type=int,
        default=100,
        help="processed/read records to keep active per section when --auto-archive is enabled",
    )
    run_parser.add_argument(
        "--task-timeout",
        type=float,
        default=DEFAULT_TASK_TIMEOUT_SECONDS,
        help=f"autonomous task command timeout in seconds; default {DEFAULT_TASK_TIMEOUT_SECONDS:g}",
    )
    run_parser.add_argument(
        "--auth",
        help=(
            "path to model auth file; codex defaults to ./auth.json then ~/.codex/auth.json; "
            "claude can use ANTHROPIC_API_KEY"
        ),
    )
    run_parser.add_argument(
        "--guidance",
        help="human-written think-phase guidance file; default .mew/guidance.md",
    )
    run_parser.add_argument(
        "--policy",
        help="human-written safety/boundary policy file; default .mew/policy.md",
    )
    run_parser.add_argument(
        "--self",
        dest="self_file",
        help="human-written self/personality file; default .mew/self.md",
    )
    run_parser.add_argument(
        "--desires",
        help="human-written desires file; default .mew/desires.md",
    )
    run_parser.add_argument(
        "--allow-read",
        action="append",
        default=[],
        help="allow read-only autonomous inspection under this path; can be passed more than once",
    )
    run_parser.add_argument(
        "--allow-write",
        action="append",
        default=[],
        help="allow gated autonomous writes under this path; can be passed more than once",
    )
    run_parser.add_argument(
        "--model-backend",
        default=os.environ.get("MEW_MODEL_BACKEND", DEFAULT_MODEL_BACKEND),
        help=(
            "resident model backend "
            f"({', '.join(SUPPORTED_MODEL_BACKENDS)}); default {DEFAULT_MODEL_BACKEND}"
        ),
    )
    run_parser.add_argument(
        "--model",
        default=os.environ.get(
            "MEW_MODEL",
            os.environ.get("MEW_CODEX_MODEL", ""),
        ),
        help=f"resident model name; backend defaults include codex={DEFAULT_CODEX_MODEL}",
    )
    run_parser.add_argument(
        "--base-url",
        default=os.environ.get(
            "MEW_MODEL_BASE_URL",
            os.environ.get("MEW_CODEX_BASE_URL", ""),
        ),
        help=f"resident model API base URL; backend defaults include codex={DEFAULT_CODEX_WEB_BASE_URL}",
    )
    run_parser.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="resident model request timeout in seconds",
    )
    run_parser.set_defaults(func=run_runtime)

    start_parser = subparsers.add_parser("start", help="start the runtime in the background")
    start_parser.add_argument("--no-wait", dest="wait", action="store_false", help="return after spawning")
    start_parser.add_argument("--timeout", type=float, default=10.0, help="seconds to wait for startup")
    start_parser.add_argument("--poll-interval", type=float, default=0.1, help="startup poll interval in seconds")
    start_parser.add_argument(
        "run_args",
        nargs=argparse.REMAINDER,
        help="arguments passed to `mew run`; use `mew start -- --autonomous`",
    )
    start_parser.set_defaults(wait=True)
    start_parser.set_defaults(func=cmd_start)

    status_parser = subparsers.add_parser("status", help="show runtime status")
    status_parser.add_argument("--json", action="store_true", help="print structured JSON")
    status_parser.set_defaults(func=cmd_status)

    stop_parser = subparsers.add_parser("stop", help="stop the active runtime")
    stop_parser.add_argument("--no-wait", dest="wait", action="store_false", help="return after sending SIGTERM")
    stop_parser.add_argument("--timeout", type=float, default=10.0, help="seconds to wait for shutdown")
    stop_parser.add_argument("--poll-interval", type=float, default=0.1, help="shutdown poll interval in seconds")
    stop_parser.set_defaults(wait=True)
    stop_parser.set_defaults(func=cmd_stop)

    doctor_parser = subparsers.add_parser("doctor", help="check local mew dependencies and state")
    doctor_parser.add_argument("--auth", help="path to Codex OAuth auth.json")
    doctor_parser.add_argument("--require-auth", action="store_true", help="fail if Codex OAuth auth is missing")
    doctor_parser.add_argument("--json", action="store_true", help="print structured JSON")
    doctor_parser.set_defaults(func=cmd_doctor)

    repair_parser = subparsers.add_parser("repair", help="reconcile and validate local mew state")
    repair_parser.add_argument("--force", action="store_true", help="repair even when a runtime lock is active")
    repair_parser.add_argument("--json", action="store_true", help="print structured JSON")
    repair_parser.set_defaults(func=cmd_repair)

    message_parser = subparsers.add_parser("message", help="queue a user message")
    message_parser.add_argument("message")
    message_parser.add_argument("--wait", action="store_true", help="wait for outbox messages from this event")
    message_parser.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="maximum wait time in seconds",
    )
    message_parser.add_argument(
        "--poll-interval",
        type=float,
        default=DEFAULT_ATTACH_POLL_INTERVAL_SECONDS,
        help=f"outbox poll interval in seconds; default {DEFAULT_ATTACH_POLL_INTERVAL_SECONDS:g}",
    )
    message_parser.add_argument("--mark-read", action="store_true", help="mark printed responses as read")
    message_parser.set_defaults(func=cmd_message)

    event_parser = subparsers.add_parser("event", help="queue an external event")
    event_parser.add_argument("event_type", help="event type, for example github_webhook or file_change")
    event_parser.add_argument("--source", default="cli", help="event source label")
    event_parser.add_argument("--payload", default="", help="JSON object payload")
    event_parser.add_argument("--text", help="convenience payload text field")
    event_parser.add_argument("--wait", action="store_true", help="wait for outbox messages from this event")
    event_parser.add_argument("--timeout", type=float, default=60.0, help="maximum wait time in seconds")
    event_parser.add_argument(
        "--poll-interval",
        type=float,
        default=DEFAULT_ATTACH_POLL_INTERVAL_SECONDS,
        help=f"outbox poll interval in seconds; default {DEFAULT_ATTACH_POLL_INTERVAL_SECONDS:g}",
    )
    event_parser.add_argument("--mark-read", action="store_true", help="mark printed responses as read")
    event_parser.set_defaults(func=cmd_event)

    webhook_parser = subparsers.add_parser("webhook", help="serve HTTP external event ingress")
    webhook_parser.add_argument("--host", default="127.0.0.1", help="bind host")
    webhook_parser.add_argument("--port", type=int, default=8765, help="bind port")
    webhook_parser.add_argument("--token", default=os.environ.get("MEW_WEBHOOK_TOKEN", ""), help="optional bearer/X-Mew-Token secret")
    webhook_parser.add_argument(
        "--allow-unauthenticated",
        action="store_true",
        help="allow tokenless webhook ingress on non-loopback hosts",
    )
    webhook_parser.add_argument("--max-body-bytes", type=int, default=1024 * 1024, help="maximum JSON payload size")
    webhook_parser.add_argument("--read-timeout", type=float, default=5.0, help="request body read timeout in seconds")
    webhook_parser.add_argument("--once", action="store_true", help="serve a single request and exit")
    webhook_parser.set_defaults(func=cmd_webhook)

    session_parser = subparsers.add_parser("session", help="JSONL control session for automation")
    session_parser.set_defaults(func=cmd_session)

    brief_parser = subparsers.add_parser("brief", help="show a compact operational brief")
    brief_parser.add_argument("--limit", type=int, default=5, help="maximum items per section")
    brief_parser.add_argument("--json", action="store_true", help="print structured JSON")
    brief_parser.set_defaults(func=cmd_brief)

    focus_parser = subparsers.add_parser("focus", help="show the quiet daily next-action view")
    focus_parser.add_argument("--limit", type=int, default=3, help="maximum tasks/questions to show")
    focus_parser.add_argument("--json", action="store_true", help="print structured JSON")
    focus_parser.set_defaults(func=cmd_focus)

    daily_parser = subparsers.add_parser("daily", help="alias for the quiet focus view")
    daily_parser.add_argument("--limit", type=int, default=3, help="maximum tasks/questions to show")
    daily_parser.add_argument("--json", action="store_true", help="print structured JSON")
    daily_parser.set_defaults(func=cmd_focus)

    buddy_parser = subparsers.add_parser("buddy", help="advance one coding task through the programmer loop")
    buddy_parser.add_argument("--task", dest="task_id", help="task id; defaults to the next open coding task")
    buddy_parser.add_argument("--cwd", help="working directory for generated plan/run")
    buddy_parser.add_argument("--agent-model", help="implementation model")
    buddy_parser.add_argument("--review-model", help="review model")
    buddy_parser.add_argument("--objective", help="override plan objective")
    buddy_parser.add_argument("--approach", help="override plan approach")
    buddy_parser.add_argument("--force-plan", action="store_true", help="create a new plan even if one exists")
    buddy_parser.add_argument("--dispatch", action="store_true", help="create or start an implementation run")
    buddy_parser.add_argument("--force-dispatch", action="store_true", help="create a new implementation run even if one is active")
    buddy_parser.add_argument("--dry-run", action="store_true", help="create run records and commands without starting ai-cli")
    buddy_parser.add_argument("--review", action="store_true", help="create or start a review run after implementation")
    buddy_parser.add_argument("--force-review", action="store_true", help="review even if implementation run is not completed or failed")
    buddy_parser.add_argument("--json", action="store_true", help="print structured JSON")
    buddy_parser.set_defaults(func=cmd_buddy)

    activity_parser = subparsers.add_parser("activity", help="show recent mew activity")
    activity_parser.add_argument("--limit", type=int, default=10, help="maximum activity items")
    activity_parser.add_argument("--json", action="store_true", help="print structured JSON")
    activity_parser.set_defaults(func=cmd_activity)

    context_parser = subparsers.add_parser("context", help="show resident prompt context diagnostics")
    context_parser.add_argument(
        "--event-type",
        default="passive_tick",
        choices=("startup", "passive_tick", "tick", "user_message"),
        help="synthetic event type used to build diagnostics",
    )
    context_parser.add_argument("--send-message", dest="context_message", help="synthetic user message payload")
    context_parser.add_argument(
        "--allowed-read-root",
        action="append",
        default=[],
        help="allowed read root for passive perception; may be repeated",
    )
    context_parser.add_argument("--json", action="store_true", help="print structured JSON")
    context_parser.set_defaults(func=cmd_context)

    step_parser = subparsers.add_parser("step", help="run a bounded manual feedback step loop")
    step_parser.add_argument("--max-steps", type=int, default=1, help="maximum feedback steps to run")
    step_parser.add_argument("--dry-run", action="store_true", help="plan one step without changing state")
    step_parser.add_argument("--ai", action="store_true", help="use the resident model backend for each step")
    step_parser.add_argument(
        "--auth",
        help=(
            "path to model auth file; codex defaults to ./auth.json then ~/.codex/auth.json; "
            "claude can use ANTHROPIC_API_KEY"
        ),
    )
    step_parser.add_argument("--guidance", help="human-written think-phase guidance file")
    step_parser.add_argument("--focus", default="", help="immediate focus to inject into this step loop")
    step_parser.add_argument("--policy", help="human-written safety/boundary policy file")
    step_parser.add_argument("--self", dest="self_file", help="human-written self/personality file")
    step_parser.add_argument("--desires", help="human-written desires file")
    step_parser.add_argument(
        "--autonomy-level",
        choices=("observe", "propose", "act"),
        default="act",
        help="freedom level for the step loop; writes and agent runs remain disabled",
    )
    step_parser.add_argument(
        "--allow-read",
        action="append",
        default=[],
        help="allow read-only inspection under this path; can be passed more than once",
    )
    step_parser.add_argument("--allow-verify", action="store_true", help="allow run_verification actions")
    step_parser.add_argument("--verify-command", help="verification command available to run_verification")
    step_parser.add_argument("--verify-timeout", type=float, default=300.0, help="verification timeout in seconds")
    step_parser.add_argument(
        "--model-backend",
        default=os.environ.get("MEW_MODEL_BACKEND", DEFAULT_MODEL_BACKEND),
        help=f"resident model backend ({', '.join(SUPPORTED_MODEL_BACKENDS)})",
    )
    step_parser.add_argument("--model", default=os.environ.get("MEW_MODEL", os.environ.get("MEW_CODEX_MODEL", "")))
    step_parser.add_argument(
        "--base-url",
        default=os.environ.get("MEW_MODEL_BASE_URL", os.environ.get("MEW_CODEX_BASE_URL", "")),
    )
    step_parser.add_argument("--timeout", type=float, default=60.0, help="resident model request timeout")
    step_parser.add_argument("--json", action="store_true", help="print structured JSON")
    step_parser.set_defaults(func=cmd_step)

    dogfood_parser = subparsers.add_parser("dogfood", help="run a short isolated mew runtime dogfood")
    dogfood_parser.add_argument("--workspace", help="workspace to use; default creates a temporary directory")
    dogfood_parser.add_argument(
        "--source-workspace",
        help="copy a repository snapshot into the dogfood workspace before running",
    )
    dogfood_parser.add_argument(
        "--pre-snapshot",
        action="store_true",
        help="refresh project snapshot memory before starting the dogfood runtime",
    )
    dogfood_parser.add_argument("--duration", type=float, default=45.0, help="seconds to run the runtime")
    dogfood_parser.add_argument("--interval", type=float, default=10.0, help="passive wake interval in seconds")
    dogfood_parser.add_argument("--poll-interval", type=float, default=0.5, help="runtime poll interval in seconds")
    dogfood_parser.add_argument("--cycles", type=int, default=1, help="number of dogfood runtime cycles")
    dogfood_parser.add_argument("--cycle-gap", type=float, default=0.0, help="seconds to wait between cycles")
    dogfood_parser.add_argument("--startup-timeout", type=float, default=15.0, help="seconds to wait for startup")
    dogfood_parser.add_argument("--stop-timeout", type=float, default=10.0, help="seconds to wait for shutdown")
    dogfood_parser.add_argument(
        "--wait-agent-runs",
        type=float,
        default=0.0,
        help="seconds to wait for active programmer agent runs after stopping the dogfood runtime",
    )
    dogfood_parser.add_argument("--message-timeout", type=float, default=30.0, help="seconds to wait while queueing messages")
    dogfood_parser.add_argument(
        "--send-message",
        action="append",
        default=[],
        help="message to queue inside the dogfood runtime after startup",
    )
    dogfood_parser.add_argument("--ai", action="store_true", help="use resident model backend during dogfood")
    dogfood_parser.add_argument("--auth", help="model auth file passed to runtime")
    dogfood_parser.add_argument(
        "--model-backend",
        default=os.environ.get("MEW_MODEL_BACKEND", DEFAULT_MODEL_BACKEND),
        help=f"resident model backend ({', '.join(SUPPORTED_MODEL_BACKENDS)})",
    )
    dogfood_parser.add_argument("--model", default=os.environ.get("MEW_MODEL", os.environ.get("MEW_CODEX_MODEL", "")))
    dogfood_parser.add_argument(
        "--base-url",
        default=os.environ.get("MEW_MODEL_BASE_URL", os.environ.get("MEW_CODEX_BASE_URL", "")),
    )
    dogfood_parser.add_argument("--model-timeout", type=float, default=60.0, help="resident model request timeout")
    dogfood_parser.add_argument(
        "--autonomy-level",
        choices=("observe", "propose", "act"),
        default="act",
        help="autonomy level to dogfood",
    )
    dogfood_parser.add_argument("--allow-write", action="store_true", help="allow runtime writes inside dogfood workspace")
    dogfood_parser.add_argument("--allow-verify", action="store_true", help="allow runtime verification")
    dogfood_parser.add_argument("--execute-tasks", action="store_true", help="allow runtime task execution gates during dogfood")
    dogfood_parser.add_argument("--allow-agent-run", action="store_true", help="allow runtime programmer agent dispatch during dogfood")
    dogfood_parser.add_argument(
        "--agent-stale-minutes",
        type=float,
        default=None,
        help="pass --agent-stale-minutes through to the dogfood runtime",
    )
    dogfood_parser.add_argument(
        "--agent-result-timeout",
        type=float,
        default=None,
        help="pass --agent-result-timeout through to the dogfood runtime",
    )
    dogfood_parser.add_argument(
        "--agent-start-timeout",
        type=float,
        default=None,
        help="pass --agent-start-timeout through to the dogfood runtime",
    )
    dogfood_parser.add_argument(
        "--review-model",
        help="pass --review-model through to the dogfood runtime",
    )
    dogfood_parser.add_argument(
        "--seed-ready-coding-task",
        action="store_true",
        help="seed a ready auto-executable coding task before starting the dogfood runtime",
    )
    dogfood_parser.add_argument("--verify-command", help="verification command for dogfood runtime")
    dogfood_parser.add_argument(
        "--verify-interval-minutes",
        type=float,
        default=0.05,
        help="minimum minutes between dogfood verification runs",
    )
    dogfood_parser.add_argument("--cleanup", action="store_true", help="remove a temporary dogfood workspace after reporting")
    dogfood_parser.add_argument("--report", help="write the structured dogfood report to this JSON file")
    dogfood_parser.add_argument("--json", action="store_true", help="print structured JSON report")
    dogfood_parser.set_defaults(func=cmd_dogfood)

    perceive_parser = subparsers.add_parser("perceive", help="show passive workspace observations")
    perceive_parser.add_argument("--cwd", default=".", help="workspace directory to observe")
    perceive_parser.add_argument(
        "--allow-read",
        action="append",
        default=[],
        help="read root that enables passive workspace observations; can be passed more than once",
    )
    perceive_parser.add_argument("--json", action="store_true", help="print structured JSON")
    perceive_parser.set_defaults(func=cmd_perceive)

    next_parser = subparsers.add_parser("next", help="print the next useful command or move")
    next_parser.add_argument("--json", action="store_true", help="print structured JSON")
    next_parser.set_defaults(func=cmd_next)

    verification_parser = subparsers.add_parser("verification", help="show runtime verification runs")
    verification_parser.add_argument("--all", action="store_true", help="show all verification runs")
    verification_parser.add_argument("--limit", type=int, default=10, help="number of recent runs to show")
    verification_parser.add_argument("--details", action="store_true", help="include stdout and stderr")
    verification_parser.add_argument("--json", action="store_true", help="print structured JSON")
    verification_parser.set_defaults(func=cmd_verification)

    writes_parser = subparsers.add_parser("writes", help="show runtime write/edit runs")
    writes_parser.add_argument("--all", action="store_true", help="show all write runs")
    writes_parser.add_argument("--limit", type=int, default=10, help="number of recent runs to show")
    writes_parser.add_argument("--details", action="store_true", help="include diffs")
    writes_parser.add_argument("--json", action="store_true", help="print structured JSON")
    writes_parser.set_defaults(func=cmd_writes)

    thoughts_parser = subparsers.add_parser("thoughts", help="show recent thought journal entries")
    thoughts_parser.add_argument("--all", action="store_true", help="show all thought journal entries")
    thoughts_parser.add_argument("--limit", type=int, default=10, help="number of recent entries to show")
    thoughts_parser.add_argument("--details", action="store_true", help="include threads and action digest")
    thoughts_parser.add_argument("--json", action="store_true", help="print structured JSON")
    thoughts_parser.set_defaults(func=cmd_thoughts)

    tool_parser = subparsers.add_parser("tool", help="safe local tools for AI-facing inspection")
    tool_subparsers = tool_parser.add_subparsers(dest="tool_command")

    tool_status_parser = tool_subparsers.add_parser("status", help="show read-only workspace status")
    tool_status_parser.add_argument("--cwd", default=".")
    tool_status_parser.add_argument("--json", action="store_true", help="print structured JSON")
    tool_status_parser.set_defaults(func=cmd_tool_status)

    tool_list_parser = tool_subparsers.add_parser("list", help="list a directory under an allowed root")
    tool_list_parser.add_argument("path", nargs="?", default=".")
    tool_list_parser.add_argument("--root", action="append", default=[], help="allowed root; default current directory")
    tool_list_parser.add_argument("--limit", type=int, default=50)
    tool_list_parser.add_argument("--json", action="store_true", help="print structured JSON")
    tool_list_parser.set_defaults(func=cmd_tool_list)

    tool_read_parser = tool_subparsers.add_parser("read", help="read a non-sensitive file")
    tool_read_parser.add_argument("path")
    tool_read_parser.add_argument("--root", action="append", default=[], help="allowed root; default current directory")
    tool_read_parser.add_argument("--max-chars", type=int, default=6000)
    tool_read_parser.add_argument("--json", action="store_true", help="print structured JSON")
    tool_read_parser.set_defaults(func=cmd_tool_read)

    tool_search_parser = tool_subparsers.add_parser("search", help="fixed-string search under an allowed root")
    tool_search_parser.add_argument("query")
    tool_search_parser.add_argument("path", nargs="?", default=".")
    tool_search_parser.add_argument("--root", action="append", default=[], help="allowed root; default current directory")
    tool_search_parser.add_argument("--max-matches", type=int, default=50)
    tool_search_parser.add_argument("--json", action="store_true", help="print structured JSON")
    tool_search_parser.set_defaults(func=cmd_tool_search)

    tool_write_parser = tool_subparsers.add_parser("write", help="write a file under an allowed root")
    tool_write_parser.add_argument("path")
    tool_write_parser.add_argument("--content", required=True)
    tool_write_parser.add_argument("--root", action="append", default=[], help="allowed root; default current directory")
    tool_write_parser.add_argument("--create", action="store_true", help="allow creating a new file")
    tool_write_parser.add_argument("--dry-run", action="store_true", help="show diff without writing")
    tool_write_parser.add_argument("--json", action="store_true", help="print structured JSON")
    tool_write_parser.set_defaults(func=cmd_tool_write)

    tool_edit_parser = tool_subparsers.add_parser("edit", help="replace text in a file under an allowed root")
    tool_edit_parser.add_argument("path")
    tool_edit_parser.add_argument("--old", required=True)
    tool_edit_parser.add_argument("--new", required=True)
    tool_edit_parser.add_argument("--root", action="append", default=[], help="allowed root; default current directory")
    tool_edit_parser.add_argument("--replace-all", action="store_true", help="replace every occurrence")
    tool_edit_parser.add_argument("--dry-run", action="store_true", help="show diff without writing")
    tool_edit_parser.add_argument("--json", action="store_true", help="print structured JSON")
    tool_edit_parser.set_defaults(func=cmd_tool_edit)

    tool_test_parser = tool_subparsers.add_parser("test", help="run a bounded verification command")
    tool_test_parser.add_argument("--command", required=True)
    tool_test_parser.add_argument("--cwd", default=".")
    tool_test_parser.add_argument("--timeout", type=float, default=300.0)
    tool_test_parser.add_argument("--json", action="store_true", help="print structured JSON")
    tool_test_parser.set_defaults(func=cmd_tool_test)

    tool_git_parser = tool_subparsers.add_parser("git", help="read-only git helpers")
    tool_git_subparsers = tool_git_parser.add_subparsers(dest="git_action")
    for git_action in ("status", "diff", "log"):
        git_action_parser = tool_git_subparsers.add_parser(git_action, help=f"git {git_action}")
        git_action_parser.add_argument("--cwd", default=".")
        if git_action == "diff":
            git_action_parser.add_argument("--staged", action="store_true", help="show staged changes")
            git_action_parser.add_argument("--stat", action="store_true", help="show diffstat instead of patch")
            git_action_parser.add_argument("--base", help="show diff from base...HEAD")
        if git_action == "log":
            git_action_parser.add_argument("--limit", type=int, default=20, help="log entries for git log")
        git_action_parser.add_argument("--json", action="store_true", help="print structured JSON")
        git_action_parser.set_defaults(func=cmd_tool_git, git_action=git_action)

    self_improve_parser = subparsers.add_parser("self-improve", help="create and optionally dispatch a mew self-improvement task")
    self_improve_parser.add_argument("--title", help="task title")
    self_improve_parser.add_argument("--description", help="task description")
    self_improve_parser.add_argument("--focus", help="self-improvement focus")
    self_improve_parser.add_argument("--cwd", default=".", help="working directory for the improvement task")
    self_improve_parser.add_argument("--priority", choices=("low", "normal", "high"), default="normal")
    self_improve_parser.add_argument("--ready", action="store_true", help="mark the task ready")
    self_improve_parser.add_argument("--auto-execute", action="store_true", help="allow autonomous dispatch later")
    self_improve_parser.add_argument("--agent-model", help="implementation model")
    self_improve_parser.add_argument("--review-model", help="review model")
    self_improve_parser.add_argument("--no-plan", action="store_true", help="create/reuse the task without creating a plan")
    self_improve_parser.add_argument("--force", action="store_true", help="create a new task even if one is open")
    self_improve_parser.add_argument("--force-plan", action="store_true", help="create a new plan even if one exists")
    self_improve_parser.add_argument("--dispatch", action="store_true", help="start an implementation run immediately")
    self_improve_parser.add_argument("--dry-run", action="store_true", help="create the run record without starting ai-cli")
    self_improve_parser.add_argument(
        "--cycle",
        action="store_true",
        help="run a supervised implementation, review, and follow-up cycle",
    )
    self_improve_parser.add_argument(
        "--cycles",
        type=int,
        default=1,
        help="number of supervised cycles to run with --cycle",
    )
    self_improve_parser.add_argument("--timeout", type=float, default=900.0, help="agent wait timeout per run")
    self_improve_parser.add_argument(
        "--verify-command",
        help="command to run after implementation and before review in --cycle mode",
    )
    self_improve_parser.add_argument(
        "--verify-timeout",
        type=float,
        default=300.0,
        help="verification command timeout in seconds",
    )
    self_improve_parser.add_argument(
        "--allow-unknown-review",
        action="store_true",
        help="continue supervised cycles when a review returns unknown",
    )
    self_improve_parser.set_defaults(func=cmd_self_improve)

    outbox_parser = subparsers.add_parser("outbox", help="show runtime messages")
    outbox_parser.add_argument("--all", action="store_true", help="show read and unread messages")
    outbox_parser.add_argument("--limit", type=int, help="show only the most recent N matching messages")
    outbox_parser.set_defaults(func=cmd_outbox)

    questions_parser = subparsers.add_parser("questions", help="show open questions")
    questions_parser.add_argument("--all", action="store_true", help="include answered and deferred questions")
    questions_parser.add_argument("--defer", action="append", default=[], help="defer an open question id")
    questions_parser.add_argument("--reopen", action="append", default=[], help="reopen a deferred question id")
    questions_parser.add_argument("--reason", help="short reason stored when deferring")
    questions_parser.set_defaults(func=cmd_questions)

    attention_parser = subparsers.add_parser("attention", help="show attention items")
    attention_parser.add_argument("--all", action="store_true", help="include resolved attention items")
    attention_parser.add_argument("--resolve", action="append", default=[], help="resolve an open attention item")
    attention_parser.add_argument("--resolve-all", action="store_true", help="resolve all open attention items")
    attention_parser.set_defaults(func=cmd_attention)

    archive_parser = subparsers.add_parser("archive", help="archive old processed inbox and read outbox records")
    archive_parser.add_argument("--apply", action="store_true", help="write archive and compact active state")
    archive_parser.add_argument(
        "--keep-recent",
        type=int,
        default=100,
        help="processed/read records to keep active per section",
    )
    archive_parser.set_defaults(func=cmd_archive)

    memory_parser = subparsers.add_parser("memory", help="show what mew remembers")
    memory_parser.add_argument("--recent", type=int, default=5, help="number of recent shallow memory events")
    memory_parser.add_argument("--deep", action="store_true", help="include deep memory sections")
    memory_parser.add_argument("--compact", action="store_true", help="compact recent shallow memory into project memory")
    memory_parser.add_argument("--keep-recent", type=int, default=5, help="recent events to keep when compacting")
    memory_parser.add_argument("--dry-run", action="store_true", help="print compact note without changing state")
    memory_parser.set_defaults(func=cmd_memory)

    snapshot_parser = subparsers.add_parser("snapshot", help="refresh structured project snapshot memory")
    snapshot_parser.add_argument("--path", default=".", help="directory to inspect")
    snapshot_parser.add_argument(
        "--allow-read",
        action="append",
        default=[],
        help="read root that permits snapshot inspection; can be passed more than once",
    )
    snapshot_parser.add_argument("--no-read-files", action="store_true", help="skip key file reads")
    snapshot_parser.add_argument("--no-inspect-key-dirs", action="store_true", help="skip src/tests directory inspection")
    snapshot_parser.add_argument("--json", action="store_true", help="print structured JSON")
    snapshot_parser.set_defaults(func=cmd_snapshot)

    reply_parser = subparsers.add_parser("reply", help="answer a question")
    reply_parser.add_argument("question_id")
    reply_parser.add_argument("text")
    reply_parser.set_defaults(func=cmd_reply)

    ack_parser = subparsers.add_parser("ack", help="mark outbox messages as read")
    ack_parser.add_argument("message_ids", nargs="*")
    ack_parser.add_argument("--all", action="store_true", help="mark all unread outbox messages as read")
    ack_parser.add_argument("--routine", action="store_true", help="mark unread routine info messages as read")
    ack_parser.add_argument("--dry-run", action="store_true", help="show what would be acknowledged without changing state")
    ack_parser.add_argument("--verbose", action="store_true", help="print acknowledged message ids and types")
    ack_parser.set_defaults(func=cmd_ack)

    listen_parser = subparsers.add_parser("listen", help="stream outbox messages")
    listen_parser.add_argument(
        "--poll-interval",
        type=float,
        default=DEFAULT_ATTACH_POLL_INTERVAL_SECONDS,
        help=f"outbox poll interval in seconds; default {DEFAULT_ATTACH_POLL_INTERVAL_SECONDS:g}",
    )
    listen_parser.add_argument("--unread", action="store_true", help="print unread existing messages first")
    listen_parser.add_argument("--history", action="store_true", help="print all existing messages first")
    listen_parser.add_argument("--mark-read", action="store_true", help="mark printed messages as read")
    listen_parser.add_argument("--activity", action="store_true", help="also stream runtime activity lines")
    listen_parser.add_argument("--timeout", type=float, help="stop listening after this many seconds")
    listen_parser.set_defaults(func=cmd_listen)

    attach_parser = subparsers.add_parser("attach", help="send messages and stream outbox messages")
    attach_parser.add_argument(
        "-m",
        "--message",
        dest="attach_messages",
        action="append",
        help="queue an initial message; can be passed more than once",
    )
    attach_parser.add_argument(
        "--poll-interval",
        type=float,
        default=DEFAULT_ATTACH_POLL_INTERVAL_SECONDS,
        help=f"outbox poll interval in seconds; default {DEFAULT_ATTACH_POLL_INTERVAL_SECONDS:g}",
    )
    attach_parser.add_argument("--unread", action="store_true", help="print unread existing messages first")
    attach_parser.add_argument("--history", action="store_true", help="print all existing messages first")
    attach_parser.add_argument("--mark-read", action="store_true", help="mark printed messages as read")
    attach_parser.add_argument("--no-activity", dest="activity", action="store_false", help="hide runtime activity lines")
    attach_parser.add_argument("--no-input", action="store_true", help="do not read interactive terminal input")
    attach_parser.add_argument("--timeout", type=float, help="detach after this many seconds")
    attach_parser.set_defaults(activity=True)
    attach_parser.set_defaults(func=cmd_attach)

    chat_parser = subparsers.add_parser("chat", help="human-friendly chat REPL for mew")
    chat_parser.add_argument(
        "--poll-interval",
        type=float,
        default=DEFAULT_ATTACH_POLL_INTERVAL_SECONDS,
        help=f"poll interval in seconds; default {DEFAULT_ATTACH_POLL_INTERVAL_SECONDS:g}",
    )
    chat_parser.add_argument("--limit", type=int, default=5, help="maximum items in the startup brief")
    chat_parser.add_argument("--mark-read", action="store_true", help="mark printed messages as read")
    chat_parser.add_argument("--no-activity", dest="activity", action="store_false", help="hide runtime activity lines")
    chat_parser.add_argument("--no-brief", action="store_true", help="do not print the startup brief")
    chat_parser.add_argument("--no-unread", action="store_true", help="do not print unread messages on startup")
    chat_parser.add_argument("--timeout", type=float, help="leave chat after this many seconds")
    chat_parser.set_defaults(activity=True)
    chat_parser.set_defaults(func=cmd_chat)

    log_parser = subparsers.add_parser("log", help="show runtime log")
    log_parser.set_defaults(func=cmd_log)

    effects_parser = subparsers.add_parser("effects", help="show recent state effect checkpoints")
    effects_parser.add_argument("--limit", type=int, default=20, help="maximum effect records")
    effects_parser.add_argument("--json", action="store_true", help="print structured JSON")
    effects_parser.set_defaults(func=cmd_effects)

    guidance_parser = subparsers.add_parser("guidance", help="manage think-phase guidance")
    guidance_subparsers = guidance_parser.add_subparsers(dest="guidance_command")

    guidance_init_parser = guidance_subparsers.add_parser("init", help="create a guidance file")
    guidance_init_parser.add_argument("--path", help="guidance file path; default .mew/guidance.md")
    guidance_init_parser.set_defaults(func=cmd_guidance_init)

    guidance_show_parser = guidance_subparsers.add_parser("show", help="show guidance")
    guidance_show_parser.add_argument("--path", help="guidance file path; default .mew/guidance.md")
    guidance_show_parser.set_defaults(func=cmd_guidance_show)

    policy_parser = subparsers.add_parser("policy", help="manage safety/boundary policy")
    policy_subparsers = policy_parser.add_subparsers(dest="policy_command")

    policy_init_parser = policy_subparsers.add_parser("init", help="create a policy file")
    policy_init_parser.add_argument("--path", help="policy file path; default .mew/policy.md")
    policy_init_parser.set_defaults(func=cmd_policy_init)

    policy_show_parser = policy_subparsers.add_parser("show", help="show policy")
    policy_show_parser.add_argument("--path", help="policy file path; default .mew/policy.md")
    policy_show_parser.set_defaults(func=cmd_policy_show)

    self_parser = subparsers.add_parser("self", help="manage mew self/personality")
    self_subparsers = self_parser.add_subparsers(dest="self_command")

    self_init_parser = self_subparsers.add_parser("init", help="create a self file")
    self_init_parser.add_argument("--path", help="self file path; default .mew/self.md")
    self_init_parser.set_defaults(func=cmd_self_init)

    self_show_parser = self_subparsers.add_parser("show", help="show self")
    self_show_parser.add_argument("--path", help="self file path; default .mew/self.md")
    self_show_parser.set_defaults(func=cmd_self_show)

    desires_parser = subparsers.add_parser("desires", help="manage self-directed desires")
    desires_subparsers = desires_parser.add_subparsers(dest="desires_command")

    desires_init_parser = desires_subparsers.add_parser("init", help="create a desires file")
    desires_init_parser.add_argument("--path", help="desires file path; default .mew/desires.md")
    desires_init_parser.set_defaults(func=cmd_desires_init)

    desires_show_parser = desires_subparsers.add_parser("show", help="show desires")
    desires_show_parser.add_argument("--path", help="desires file path; default .mew/desires.md")
    desires_show_parser.set_defaults(func=cmd_desires_show)

    task_parser = subparsers.add_parser("task", help="manage tasks")
    task_subparsers = task_parser.add_subparsers(dest="task_command")

    add_parser = task_subparsers.add_parser("add", help="add a task")
    add_parser.add_argument("title")
    add_parser.add_argument("--kind", choices=("coding", "research", "personal", "admin", "unknown"), help="task kind; inferred when omitted")
    add_parser.add_argument("--description")
    add_parser.add_argument("--notes")
    add_parser.add_argument("--command", help="command to run when the task is auto-executed")
    add_parser.add_argument("--cwd", help="working directory for the task command")
    add_parser.add_argument("--agent-backend", choices=("ai-cli",), help="agent backend for task run")
    add_parser.add_argument("--agent-model", help="agent model for task run, e.g. codex-ultra")
    add_parser.add_argument("--agent-prompt", help="prompt override for task run")
    add_parser.add_argument(
        "--auto-execute",
        action="store_true",
        help="allow passive runtime to execute this task command",
    )
    add_parser.add_argument("--ready", action="store_true", help="create the task in ready status")
    add_parser.add_argument("--priority", choices=("low", "normal", "high"), default="normal")
    add_parser.set_defaults(func=cmd_task_add)

    list_parser = task_subparsers.add_parser("list", help="list tasks")
    list_parser.add_argument("--all", action="store_true", help="include done tasks")
    list_parser.add_argument("--kind", choices=("coding", "research", "personal", "admin", "unknown"), help="filter by task kind")
    list_parser.set_defaults(func=cmd_task_list)

    classify_parser = task_subparsers.add_parser("classify", help="inspect or update task kind inference")
    classify_parser.add_argument("task_id", nargs="?", help="task id to classify; defaults to open tasks")
    classify_parser.add_argument("--all", action="store_true", help="include done tasks")
    classify_parser.add_argument("--mismatches", action="store_true", help="show only explicit kind mismatches")
    classify_parser.add_argument("--apply", action="store_true", help="store inferred kind on selected tasks")
    classify_parser.add_argument("--clear", action="store_true", help="clear stored kind override on selected tasks")
    classify_parser.add_argument("--include-unknown", action="store_true", help="allow --apply to store unknown")
    classify_parser.add_argument("--json", action="store_true", help="print JSON")
    classify_parser.set_defaults(func=cmd_task_classify)

    show_parser = task_subparsers.add_parser("show", help="show a task")
    show_parser.add_argument("task_id")
    show_parser.set_defaults(func=cmd_task_show)

    done_parser = task_subparsers.add_parser("done", help="mark a task done")
    done_parser.add_argument("task_id")
    done_parser.set_defaults(func=cmd_task_done)

    run_task_parser = task_subparsers.add_parser("run", help="start an agent run for a task")
    run_task_parser.add_argument("task_id")
    run_task_parser.add_argument("--agent-backend", choices=("ai-cli",), help="override agent backend")
    run_task_parser.add_argument("--agent-model", help="override agent model")
    run_task_parser.add_argument("--agent-prompt", help="override agent prompt")
    run_task_parser.add_argument("--cwd", help="override run working directory")
    run_task_parser.add_argument("--dry-run", action="store_true", help="create the run record without starting ai-cli")
    run_task_parser.set_defaults(func=cmd_task_run)

    plan_task_parser = task_subparsers.add_parser("plan", help="create or show a programmer plan for a task")
    plan_task_parser.add_argument("task_id")
    plan_task_parser.add_argument("--cwd", help="working directory for the planned implementation")
    plan_task_parser.add_argument("--agent-model", help="implementation model for the plan")
    plan_task_parser.add_argument("--review-model", help="review model for the plan")
    plan_task_parser.add_argument("--objective", help="override plan objective")
    plan_task_parser.add_argument("--approach", help="override suggested approach")
    plan_task_parser.add_argument("--force", action="store_true", help="create a new plan even if one exists")
    plan_task_parser.add_argument("--prompt", action="store_true", help="print generated implementation and review prompts")
    plan_task_parser.set_defaults(func=cmd_task_plan)

    dispatch_task_parser = task_subparsers.add_parser("dispatch", help="start an implementation run from a task plan")
    dispatch_task_parser.add_argument("task_id")
    dispatch_task_parser.add_argument("--plan-id", help="specific plan id to dispatch")
    dispatch_task_parser.add_argument("--cwd", help="override plan working directory")
    dispatch_task_parser.add_argument("--agent-model", help="override implementation model")
    dispatch_task_parser.add_argument("--dry-run", action="store_true", help="create the run record without starting ai-cli")
    dispatch_task_parser.set_defaults(func=cmd_task_dispatch)

    update_parser = task_subparsers.add_parser("update", help="update a task")
    update_parser.add_argument("task_id")
    update_parser.add_argument("--title")
    update_parser.add_argument("--kind", choices=("coding", "research", "personal", "admin", "unknown"))
    update_parser.add_argument("--description")
    update_parser.add_argument("--notes")
    update_parser.add_argument("--command")
    update_parser.add_argument("--cwd")
    update_parser.add_argument("--agent-backend")
    update_parser.add_argument("--agent-model")
    update_parser.add_argument("--agent-prompt")
    update_parser.add_argument("--auto-execute", dest="auto_execute", action="store_true")
    update_parser.add_argument("--no-auto-execute", dest="auto_execute", action="store_false")
    update_parser.set_defaults(auto_execute=None)
    update_parser.add_argument("--status", choices=("todo", "ready", "running", "blocked", "done"))
    update_parser.add_argument("--priority", choices=("low", "normal", "high"))
    update_parser.set_defaults(func=cmd_task_update)

    agent_parser = subparsers.add_parser("agent", help="manage agent runs")
    agent_parser.set_defaults(func=cmd_agent_list)
    agent_subparsers = agent_parser.add_subparsers(dest="agent_command")

    agent_list_parser = agent_subparsers.add_parser("list", help="list agent runs")
    agent_list_parser.add_argument("--all", action="store_true", help="include completed and failed runs")
    agent_list_parser.set_defaults(func=cmd_agent_list)

    agent_show_parser = agent_subparsers.add_parser("show", help="show an agent run")
    agent_show_parser.add_argument("run_id")
    agent_show_parser.add_argument("--prompt", action="store_true", help="print the full prompt")
    agent_show_parser.set_defaults(func=cmd_agent_show)

    agent_wait_parser = agent_subparsers.add_parser("wait", help="wait for an agent run")
    agent_wait_parser.add_argument("run_id")
    agent_wait_parser.add_argument("--timeout", type=float, help="maximum wait time in seconds")
    agent_wait_parser.set_defaults(func=cmd_agent_wait)

    agent_result_parser = agent_subparsers.add_parser("result", help="fetch an agent run result")
    agent_result_parser.add_argument("run_id")
    agent_result_parser.add_argument("--verbose", action="store_true", help="ask ai-cli for verbose result output")
    agent_result_parser.set_defaults(func=cmd_agent_result)

    agent_review_parser = agent_subparsers.add_parser("review", help="start a review run for an implementation run")
    agent_review_parser.add_argument("run_id")
    agent_review_parser.add_argument("--agent-model", help="review model")
    agent_review_parser.add_argument("--dry-run", action="store_true", help="create the review run record without starting ai-cli")
    agent_review_parser.add_argument("--force", action="store_true", help="review a run that is not completed or failed")
    agent_review_parser.set_defaults(func=cmd_agent_review)

    agent_followup_parser = agent_subparsers.add_parser("followup", help="create a follow-up task from a review run")
    agent_followup_parser.add_argument("run_id")
    agent_followup_parser.add_argument("--ack", action="store_true", help="mark review follow-up processed without creating a task")
    agent_followup_parser.add_argument("--note", help="note for --ack")
    agent_followup_parser.set_defaults(func=cmd_agent_followup)

    agent_retry_parser = agent_subparsers.add_parser("retry", help="start a retry implementation run")
    agent_retry_parser.add_argument("run_id")
    agent_retry_parser.add_argument("--agent-model", help="implementation model")
    agent_retry_parser.add_argument("--dry-run", action="store_true", help="create the retry run record without starting ai-cli")
    agent_retry_parser.add_argument("--force", action="store_true", help="retry a run that is not failed or completed")
    agent_retry_parser.set_defaults(func=cmd_agent_retry)

    agent_sweep_parser = agent_subparsers.add_parser("sweep", help="advance and diagnose agent-run lifecycle")
    agent_sweep_parser.add_argument("--dry-run", action="store_true", help="report actions without changing state")
    agent_sweep_parser.add_argument("--no-collect", action="store_true", help="do not fetch running agent results")
    agent_sweep_parser.add_argument("--start-reviews", action="store_true", help="start review runs for completed implementations")
    agent_sweep_parser.add_argument("--no-followup", action="store_true", help="do not create follow-up tasks from completed reviews")
    agent_sweep_parser.add_argument("--agent-model", help="review model when starting reviews")
    agent_sweep_parser.add_argument("--stale-minutes", type=float, default=60.0, help="age before running runs are considered stale")
    agent_sweep_parser.add_argument(
        "--agent-result-timeout",
        type=float,
        help="seconds to wait when polling running agent results",
    )
    agent_sweep_parser.add_argument(
        "--agent-start-timeout",
        type=float,
        help="seconds to wait when starting review runs",
    )
    agent_sweep_parser.set_defaults(func=cmd_agent_sweep)

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    if hasattr(args, "interval_minutes") and args.interval_minutes is not None:
        args.interval = args.interval_minutes * 60.0

    if args.message:
        return cmd_message(args)
    if hasattr(args, "func"):
        return args.func(args)

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
