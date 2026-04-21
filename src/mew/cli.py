#!/usr/bin/env python3
import argparse
import os

from .dogfood import DOGFOOD_SCENARIOS, M2_COMPARATIVE_TASK_SHAPES
from .typed_memory import CODING_MEMORY_KINDS
from .commands import (
    APPROVAL_MODES,
    CHAT_HELP,
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
    cmd_chat_log,
    cmd_code,
    cmd_context,
    cmd_daemon,
    cmd_digest,
    cmd_do,
    cmd_desires_init,
    cmd_desires_show,
    cmd_desk,
    cmd_dogfood,
    cmd_doctor,
    cmd_dream,
    cmd_effects,
    cmd_event,
    cmd_focus,
    cmd_guidance_init,
    cmd_guidance_show,
    cmd_journal,
    cmd_listen,
    cmd_log,
    cmd_memory,
    cmd_message,
    cmd_metrics,
    cmd_mood,
    cmd_morning_paper,
    cmd_next,
    cmd_outbox,
    cmd_passive_bundle,
    cmd_perceive,
    cmd_policy_init,
    cmd_policy_show,
    cmd_proof_summary,
    cmd_questions,
    cmd_repair,
    cmd_reply,
    cmd_runtime_effects,
    cmd_self_init,
    cmd_self_improve,
    cmd_self_memory,
    cmd_self_show,
    cmd_session,
    cmd_signals,
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
    cmd_trace,
    cmd_tool_git,
    cmd_tool_edit,
    cmd_tool_glob,
    cmd_tool_list,
    cmd_tool_read,
    cmd_tool_search,
    cmd_tool_status,
    cmd_tool_test,
    cmd_tool_write,
    cmd_verification,
    cmd_webhook,
    cmd_work,
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
from .read_tools import DEFAULT_READ_MAX_CHARS
from .runtime import run_runtime
from .tasks import TASK_KINDS


def cmd_help(args):
    parser = build_parser()
    topic = getattr(args, "topic", None) or []
    if topic:
        try:
            parser.parse_args([*topic, "--help"])
        except SystemExit as exc:
            return int(exc.code or 0)
        return 0
    parser.print_help()
    return 0


def build_parser():
    parser = argparse.ArgumentParser(prog="mew")
    parser.add_argument("-m", "--message", help="queue a message for the runtime")
    parser.add_argument("--wait", dest="message_wait", action="store_true", help="with -m, wait for an outbox response")
    parser.add_argument("--timeout", dest="message_timeout", type=float, default=60.0, help="with -m, maximum wait time in seconds")
    parser.add_argument(
        "--poll-interval",
        dest="message_poll_interval",
        type=float,
        default=DEFAULT_ATTACH_POLL_INTERVAL_SECONDS,
        help=f"with -m, outbox poll interval in seconds; default {DEFAULT_ATTACH_POLL_INTERVAL_SECONDS:g}",
    )
    parser.add_argument("--mark-read", dest="message_mark_read", action="store_true", help="with -m, mark printed responses as read")

    subparsers = parser.add_subparsers(dest="command")

    help_parser = subparsers.add_parser("help", help="show top-level or command help")
    help_parser.add_argument("topic", nargs="*", help="optional command path to show help for")
    help_parser.set_defaults(func=cmd_help)

    run_parser = subparsers.add_parser("run", help="start the runtime")
    run_parser.add_argument("--once", action="store_true", help="process one loop and exit")
    run_parser.add_argument(
        "--passive-now",
        action="store_true",
        help="when no user or external event is pending, process passive_tick before startup on the first loop",
    )
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
        "--watch-path",
        action="append",
        default=[],
        help="watch a file or directory path and queue file_change external events when it changes",
    )
    run_parser.add_argument(
        "--echo-outbox",
        action="store_true",
        help="print newly created outbox messages in the runtime terminal",
    )
    run_parser.add_argument(
        "--echo-effects",
        action="store_true",
        help="print the runtime effect summary for each processed cycle",
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
        "--allow-native-work",
        action="store_true",
        help="allow autonomous programmer loop to start native mew work sessions",
    )
    run_parser.add_argument(
        "--allow-native-advance",
        action="store_true",
        help="allow autonomous runtime to advance runtime-owned native work sessions one bounded step",
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
        help="archive old processed/read runtime records and effect log entries after runtime cycles",
    )
    run_parser.add_argument(
        "--archive-keep-recent",
        type=int,
        default=100,
        help="records to keep active per section when --auto-archive is enabled",
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
    run_parser.add_argument("--focus", default="", help="immediate focus to inject into runtime guidance")
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
    run_parser.add_argument(
        "--trace-model",
        action="store_true",
        help="record full THINK/ACT prompts and normalized plans to .mew/model-trace.jsonl; may contain private state",
    )
    run_parser.add_argument(
        "--max-reflex-rounds",
        type=int,
        default=0,
        help="extra bounded THINK rounds after read-only observation decisions; default 0, max 3",
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
    status_parser.add_argument("--kind", choices=["coding", "research", "personal", "admin", "unknown"], help="scope task/question/attention counts and next move by kind")
    status_parser.add_argument("--json", action="store_true", help="print structured JSON")
    status_parser.set_defaults(func=cmd_status)

    stop_parser = subparsers.add_parser("stop", help="stop the active runtime")
    stop_parser.add_argument("--no-wait", dest="wait", action="store_false", help="return after sending SIGTERM")
    stop_parser.add_argument("--timeout", type=float, default=10.0, help="seconds to wait for shutdown")
    stop_parser.add_argument("--poll-interval", type=float, default=0.1, help="shutdown poll interval in seconds")
    stop_parser.set_defaults(wait=True)
    stop_parser.set_defaults(func=cmd_stop)

    daemon_parser = subparsers.add_parser("daemon", help="manage the resident runtime daemon")
    daemon_subparsers = daemon_parser.add_subparsers(dest="daemon_command")
    daemon_parser.set_defaults(func=cmd_daemon)

    daemon_start_parser = daemon_subparsers.add_parser("start", help="start the runtime daemon")
    daemon_start_parser.add_argument("--no-wait", dest="wait", action="store_false", help="return after spawning")
    daemon_start_parser.add_argument("--timeout", type=float, default=10.0, help="seconds to wait for startup")
    daemon_start_parser.add_argument("--poll-interval", type=float, default=0.1, help="startup poll interval in seconds")
    daemon_start_parser.add_argument(
        "run_args",
        nargs=argparse.REMAINDER,
        help="arguments passed to `mew run`; use `mew daemon start -- --autonomous`",
    )
    daemon_start_parser.set_defaults(wait=True)
    daemon_start_parser.set_defaults(func=cmd_daemon)

    daemon_status_parser = daemon_subparsers.add_parser("status", help="show daemon status")
    daemon_status_parser.add_argument("--json", action="store_true", help="print structured JSON")
    daemon_status_parser.set_defaults(func=cmd_daemon)

    daemon_inspect_parser = daemon_subparsers.add_parser("inspect", help="inspect daemon state")
    daemon_inspect_parser.add_argument("--json", action="store_true", help="print structured JSON")
    daemon_inspect_parser.set_defaults(func=cmd_daemon)

    daemon_stop_parser = daemon_subparsers.add_parser("stop", help="stop the runtime daemon")
    daemon_stop_parser.add_argument("--no-wait", dest="wait", action="store_false", help="return after sending SIGTERM")
    daemon_stop_parser.add_argument("--timeout", type=float, default=10.0, help="seconds to wait for shutdown")
    daemon_stop_parser.add_argument("--poll-interval", type=float, default=0.1, help="shutdown poll interval in seconds")
    daemon_stop_parser.set_defaults(wait=True)
    daemon_stop_parser.set_defaults(func=cmd_daemon)

    daemon_pause_parser = daemon_subparsers.add_parser("pause", help="pause autonomous daemon work")
    daemon_pause_parser.add_argument("reason", nargs="*", help="optional pause reason")
    daemon_pause_parser.add_argument("--json", action="store_true", help="print structured JSON")
    daemon_pause_parser.set_defaults(func=cmd_daemon)

    daemon_resume_parser = daemon_subparsers.add_parser("resume", help="resume autonomous daemon work")
    daemon_resume_parser.add_argument("--json", action="store_true", help="print structured JSON")
    daemon_resume_parser.set_defaults(func=cmd_daemon)

    daemon_repair_parser = daemon_subparsers.add_parser("repair", help="repair daemon/runtime state")
    daemon_repair_parser.add_argument("--force", action="store_true", help="repair even when a runtime lock is active")
    daemon_repair_parser.add_argument("--dry-run", action="store_true", help="preview repairs without saving state")
    daemon_repair_parser.add_argument("--json", action="store_true", help="print structured JSON")
    daemon_repair_parser.set_defaults(func=cmd_daemon)

    daemon_logs_parser = daemon_subparsers.add_parser("logs", help="show daemon output log")
    daemon_logs_parser.add_argument("--lines", type=int, default=40, help="number of log lines to print")
    daemon_logs_parser.add_argument("--json", action="store_true", help="print structured JSON")
    daemon_logs_parser.set_defaults(func=cmd_daemon)

    doctor_parser = subparsers.add_parser("doctor", help="check local mew dependencies and state")
    doctor_parser.add_argument("--auth", help="path to Codex OAuth auth.json")
    doctor_parser.add_argument("--require-auth", action="store_true", help="fail if Codex OAuth auth is missing")
    doctor_parser.add_argument("--json", action="store_true", help="print structured JSON")
    doctor_parser.set_defaults(func=cmd_doctor)

    repair_parser = subparsers.add_parser("repair", help="reconcile and validate local mew state")
    repair_parser.add_argument("--force", action="store_true", help="repair even when a runtime lock is active")
    repair_parser.add_argument("--dry-run", action="store_true", help="preview repairs without saving state")
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

    signals_parser = subparsers.add_parser("signals", help="manage audited inbound signal sources")
    signals_subparsers = signals_parser.add_subparsers(dest="signals_command")
    signals_parser.set_defaults(func=cmd_signals)

    signals_sources_parser = signals_subparsers.add_parser("sources", help="list configured signal sources")
    signals_sources_parser.add_argument("--json", action="store_true", help="print structured JSON")
    signals_sources_parser.set_defaults(func=cmd_signals)

    signals_enable_parser = signals_subparsers.add_parser("enable", help="enable a gated signal source")
    signals_enable_parser.add_argument("name", help="source name, for example hn")
    signals_enable_parser.add_argument("--kind", required=True, help="source kind, for example rss or calendar")
    signals_enable_parser.add_argument("--reason", default="", help="why mew may use this source")
    signals_enable_parser.add_argument("--budget", type=int, default=None, help="daily observation budget")
    signals_enable_parser.add_argument("--config", default="", help="JSON source config")
    signals_enable_parser.add_argument("--json", action="store_true", help="print structured JSON")
    signals_enable_parser.set_defaults(func=cmd_signals)

    signals_disable_parser = signals_subparsers.add_parser("disable", help="disable a signal source")
    signals_disable_parser.add_argument("name", help="source name")
    signals_disable_parser.add_argument("--json", action="store_true", help="print structured JSON")
    signals_disable_parser.set_defaults(func=cmd_signals)

    signals_record_parser = signals_subparsers.add_parser("record", help="record an observation from an enabled source")
    signals_record_parser.add_argument("source", help="enabled source name")
    signals_record_parser.add_argument("--kind", default="observation", help="observation kind")
    signals_record_parser.add_argument("--summary", default="", help="short human-readable observation")
    signals_record_parser.add_argument("--reason", default="", help="why this observation is useful")
    signals_record_parser.add_argument("--payload", default="", help="JSON observation payload")
    signals_record_parser.add_argument("--cost", type=int, default=1, help="budget units consumed")
    signals_record_parser.add_argument("--no-queue", action="store_true", help="record without queueing a runtime event")
    signals_record_parser.add_argument("--json", action="store_true", help="print structured JSON")
    signals_record_parser.set_defaults(func=cmd_signals)

    signals_journal_parser = signals_subparsers.add_parser("journal", help="show recent signal observations")
    signals_journal_parser.add_argument("--limit", type=int, default=20, help="number of observations to show")
    signals_journal_parser.add_argument("--json", action="store_true", help="print structured JSON")
    signals_journal_parser.set_defaults(func=cmd_signals)

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
    brief_parser.add_argument("--kind", choices=["coding", "research", "personal", "admin", "unknown"], help="scope tasks, related questions, attention, and next move by kind")
    brief_parser.add_argument("--json", action="store_true", help="print structured JSON")
    brief_parser.set_defaults(func=cmd_brief)

    focus_parser = subparsers.add_parser("focus", help="show the quiet daily next-action view")
    focus_parser.add_argument("--limit", type=int, default=3, help="maximum tasks/questions to show")
    focus_parser.add_argument("--kind", choices=["coding", "research", "personal", "admin", "unknown"], help="filter tasks and related questions by kind")
    focus_parser.add_argument("--json", action="store_true", help="print structured JSON")
    focus_parser.set_defaults(func=cmd_focus)

    daily_parser = subparsers.add_parser("daily", help="alias for the quiet focus view")
    daily_parser.add_argument("--limit", type=int, default=3, help="maximum tasks/questions to show")
    daily_parser.add_argument("--kind", choices=["coding", "research", "personal", "admin", "unknown"], help="filter tasks and related questions by kind")
    daily_parser.add_argument("--json", action="store_true", help="print structured JSON")
    daily_parser.set_defaults(func=cmd_focus)

    journal_parser = subparsers.add_parser("journal", help="generate a daily mew journal")
    journal_parser.add_argument("--date", help="journal date YYYY-MM-DD; defaults to today")
    journal_parser.add_argument("--write", action="store_true", help="write .mew/journal/YYYY-MM-DD.md")
    journal_parser.add_argument("--output-dir", default=".", help="where to write .mew/journal files with --write")
    journal_parser.add_argument("--show", action="store_true", help="print the markdown report")
    journal_parser.add_argument("--json", action="store_true", help="print structured output")
    journal_parser.set_defaults(func=cmd_journal)

    bundle_parser = subparsers.add_parser("bundle", help="compose generated daily reports into a passive bundle")
    bundle_parser.add_argument("--reports-root", default=".", help="root containing generated .mew report files")
    bundle_parser.add_argument("--output-dir", default=".", help="where to write .mew/passive-bundle/YYYY-MM-DD.md")
    bundle_parser.add_argument("--date", help="bundle date YYYY-MM-DD; defaults to today")
    bundle_parser.add_argument("--show", action="store_true", help="print the generated bundle instead of only its path")
    bundle_parser.add_argument("--json", action="store_true", help="print structured output")
    bundle_parser.add_argument(
        "--generate-core",
        action="store_true",
        help="generate core journal and mood reports before composing the bundle",
    )
    bundle_parser.add_argument("--morning-feed", help="with --generate-core, feed JSON for morning-paper generation")
    bundle_parser.add_argument("--interest", action="append", default=[], help="with --morning-feed, interest tag to rank for")
    bundle_parser.add_argument("--limit", type=int, default=8, help="with --morning-feed, maximum feed items to include")
    bundle_parser.set_defaults(func=cmd_passive_bundle)

    desk_parser = subparsers.add_parser("desk", help="show the desktop-pet view model")
    desk_parser.add_argument("--date", help="view-model date YYYY-MM-DD; defaults to today")
    desk_parser.add_argument("--kind", choices=TASK_KINDS, help="scope the desk view to one task kind")
    desk_parser.add_argument("--write", action="store_true", help="write .mew/desk/YYYY-MM-DD.json and .md")
    desk_parser.add_argument("--output-dir", default=".", help="where to write .mew/desk files with --write")
    desk_parser.add_argument("--json", action="store_true", help="print structured output")
    desk_parser.set_defaults(func=cmd_desk)

    mood_parser = subparsers.add_parser("mood", help="show the current mew mood score")
    mood_parser.add_argument("--date", help="mood report date YYYY-MM-DD; defaults to today")
    mood_parser.add_argument("--write", action="store_true", help="write .mew/mood/YYYY-MM-DD.md")
    mood_parser.add_argument("--output-dir", default=".", help="where to write .mew/mood files with --write")
    mood_parser.add_argument("--show", action="store_true", help="print the markdown report")
    mood_parser.add_argument("--json", action="store_true", help="print structured output")
    mood_parser.set_defaults(func=cmd_mood)

    morning_paper_parser = subparsers.add_parser(
        "morning-paper",
        help="rank a static feed JSON into a morning paper report",
    )
    morning_paper_parser.add_argument("feed", help="feed JSON file or object with an items array")
    morning_paper_parser.add_argument("--date", help="report date YYYY-MM-DD; defaults to today")
    morning_paper_parser.add_argument("--interest", action="append", default=[], help="interest tag to rank for")
    morning_paper_parser.add_argument("--limit", type=int, default=8, help="maximum feed items to include")
    morning_paper_parser.add_argument("--write", action="store_true", help="write .mew/morning-paper/YYYY-MM-DD.md")
    morning_paper_parser.add_argument(
        "--output-dir",
        default=".",
        help="where to write .mew/morning-paper files with --write",
    )
    morning_paper_parser.add_argument("--show", action="store_true", help="print the markdown report")
    morning_paper_parser.add_argument("--json", action="store_true", help="print structured output")
    morning_paper_parser.set_defaults(func=cmd_morning_paper)

    self_memory_parser = subparsers.add_parser("self-memory", help="generate a self-memory report")
    self_memory_parser.add_argument("--date", help="report date YYYY-MM-DD; defaults to today")
    self_memory_parser.add_argument("--write", action="store_true", help="write .mew/self/learned-YYYY-MM-DD.md")
    self_memory_parser.add_argument("--output-dir", default=".", help="where to write .mew/self files with --write")
    self_memory_parser.add_argument("--show", action="store_true", help="print the markdown report")
    self_memory_parser.add_argument("--json", action="store_true", help="print structured output")
    self_memory_parser.set_defaults(func=cmd_self_memory)

    dream_parser = subparsers.add_parser("dream", help="generate a dream report")
    dream_parser.add_argument("--date", help="report date YYYY-MM-DD; defaults to today")
    dream_parser.add_argument("--write", action="store_true", help="write .mew/dreams/YYYY-MM-DD.md")
    dream_parser.add_argument("--output-dir", default=".", help="where to write .mew/dreams files with --write")
    dream_parser.add_argument("--show", action="store_true", help="print the markdown report")
    dream_parser.add_argument("--json", action="store_true", help="print structured output")
    dream_parser.set_defaults(func=cmd_dream)

    digest_parser = subparsers.add_parser("digest", help="summarize activity since the last user message")
    digest_parser.set_defaults(func=cmd_digest)

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
    activity_parser.add_argument("--kind", choices=TASK_KINDS, help="scope activity to tasks of this kind")
    activity_parser.add_argument("--json", action="store_true", help="print structured JSON")
    activity_parser.set_defaults(func=cmd_activity)

    metrics_parser = subparsers.add_parser("metrics", help="show observation-first reliability and latency metrics")
    metrics_parser.add_argument("--kind", choices=TASK_KINDS, help="scope metrics to tasks of this kind")
    metrics_parser.add_argument("--limit", type=int, help="maximum recent work sessions to include")
    metrics_parser.add_argument(
        "--sample-limit",
        type=int,
        default=3,
        help="maximum recent diagnostic samples to show for each bottleneck",
    )
    metrics_parser.add_argument("--json", action="store_true", help="print structured JSON")
    metrics_parser.set_defaults(func=cmd_metrics)

    context_parser = subparsers.add_parser("context", help="show resident prompt context diagnostics")
    context_parser.add_argument(
        "--event-type",
        default="passive_tick",
        choices=("startup", "passive_tick", "tick", "user_message"),
        help="synthetic event type used to build diagnostics",
    )
    context_parser.add_argument("--send-message", dest="context_message", help="synthetic user message payload")
    context_parser.add_argument(
        "--save",
        metavar="NOTE",
        help="save the context diagnostics plus a reentry note to typed project memory",
    )
    context_parser.add_argument(
        "--load",
        action="store_true",
        help="load recent context checkpoints from typed project memory",
    )
    context_parser.add_argument(
        "--query",
        default="Context save next safe action context compression long session",
        help="checkpoint search query for --load",
    )
    context_parser.add_argument("--limit", type=int, default=3, help="maximum context checkpoints for --load")
    context_parser.add_argument("--name", help="typed memory name for --save")
    context_parser.add_argument("--description", help="typed memory description for --save")
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
        help="freedom level for the step loop; agent runs remain disabled",
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
        "--allow-write",
        action="append",
        default=[],
        help="allow gated step write actions under this path; can be passed more than once",
    )
    step_parser.add_argument(
        "--model-backend",
        default=os.environ.get("MEW_MODEL_BACKEND", DEFAULT_MODEL_BACKEND),
        help=f"resident model backend ({', '.join(SUPPORTED_MODEL_BACKENDS)})",
    )
    step_parser.add_argument(
        "--model",
        default=os.environ.get("MEW_MODEL", os.environ.get("MEW_CODEX_MODEL", "")),
        help="resident model override; defaults to the backend default model",
    )
    step_parser.add_argument(
        "--base-url",
        default=os.environ.get("MEW_MODEL_BASE_URL", os.environ.get("MEW_CODEX_BASE_URL", "")),
        help="resident model API base URL override",
    )
    step_parser.add_argument("--timeout", type=float, default=60.0, help="resident model request timeout")
    step_parser.add_argument(
        "--trace-model",
        action="store_true",
        help="record full THINK/ACT prompts and normalized plans to .mew/model-trace.jsonl; may contain private state",
    )
    step_parser.add_argument(
        "--max-reflex-rounds",
        type=int,
        default=0,
        help="extra bounded THINK rounds after read-only observation decisions; default 0, max 3",
    )
    step_parser.add_argument("--json", action="store_true", help="print structured JSON")
    step_parser.set_defaults(func=cmd_step)

    dogfood_parser = subparsers.add_parser("dogfood", help="run a short isolated mew runtime dogfood")
    dogfood_parser.add_argument(
        "--scenario",
        choices=("all", *DOGFOOD_SCENARIOS),
        help="run a deterministic CLI dogfood scenario instead of a timed runtime dogfood",
    )
    dogfood_parser.add_argument(
        "--all",
        dest="all_scenarios",
        action="store_true",
        help="shortcut for --scenario all",
    )
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
    dogfood_parser.add_argument(
        "--mew-session-id",
        help="for m2-comparative, prefill mew-side evidence from the current workspace work session id (or latest)",
    )
    dogfood_parser.add_argument(
        "--m2-comparison-report",
        help="for m2-comparative, merge a JSON report from the paired fresh CLI run",
    )
    dogfood_parser.add_argument(
        "--m3-comparison-report",
        help="for m3-reentry-gate, merge a JSON report from the paired fresh CLI run",
    )
    dogfood_parser.add_argument(
        "--m2-task-shape",
        choices=M2_COMPARATIVE_TASK_SHAPES,
        help="for m2-comparative, set task_shape.selected for this paired run",
    )
    dogfood_parser.add_argument("--duration", type=float, default=argparse.SUPPRESS, help="seconds to run the runtime")
    dogfood_parser.add_argument("--interval", type=float, default=argparse.SUPPRESS, help="passive wake interval in seconds")
    dogfood_parser.add_argument("--poll-interval", type=float, default=argparse.SUPPRESS, help="runtime poll interval in seconds")
    dogfood_parser.add_argument(
        "--time-dilation",
        type=float,
        default=argparse.SUPPRESS,
        help="resident-loop only: multiply logical mew timestamps while real scheduling stays unchanged",
    )
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
        "--trace-model",
        action="store_true",
        help="pass --trace-model to the dogfood runtime; trace files may contain private state",
    )
    dogfood_parser.add_argument(
        "--max-reflex-rounds",
        type=int,
        default=0,
        help="pass bounded THINK observation rounds to the dogfood runtime",
    )
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
    dogfood_parser.add_argument("--allow-native-work", action="store_true", help="allow runtime native work session start during dogfood")
    dogfood_parser.add_argument(
        "--allow-native-advance",
        action="store_true",
        help="allow runtime native work session advance during dogfood",
    )
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
    dogfood_parser.add_argument(
        "--cleanup",
        action="store_true",
        help="remove a mew-created temporary dogfood workspace after reporting; explicit --workspace paths are kept",
    )
    dogfood_parser.add_argument("--report", help="write the structured dogfood report to this JSON file")
    dogfood_parser.add_argument(
        "--json",
        action="store_true",
        help="print structured JSON report; scenario mode prints a compact summary, use --report for full details",
    )
    dogfood_parser.set_defaults(func=cmd_dogfood)

    proof_summary_parser = subparsers.add_parser("proof-summary", help="summarize collected proof artifacts")
    proof_summary_parser.add_argument("artifact_dir", help="artifact directory created by scripts/collect_proof_docker.sh")
    proof_summary_parser.add_argument("--json", action="store_true", help="print structured JSON")
    proof_summary_parser.add_argument(
        "--strict",
        action="store_true",
        help="return non-zero when the collected proof did not pass cleanly",
    )
    proof_summary_parser.set_defaults(func=cmd_proof_summary)

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

    observe_parser = subparsers.add_parser("observe", help="alias for perceive")
    observe_parser.add_argument("--cwd", default=".", help="workspace directory to observe")
    observe_parser.add_argument(
        "--allow-read",
        action="append",
        default=[],
        help="read root that enables passive workspace observations; can be passed more than once",
    )
    observe_parser.add_argument("--json", action="store_true", help="print structured JSON")
    observe_parser.set_defaults(func=cmd_perceive)

    next_parser = subparsers.add_parser("next", help="print the next useful command or move")
    next_parser.add_argument("--kind", choices=["coding", "research", "personal", "admin", "unknown"], help="filter tasks and related questions by kind")
    next_parser.add_argument("--json", action="store_true", help="print structured JSON")
    next_parser.set_defaults(func=cmd_next)

    do_parser = subparsers.add_parser("do", help="run the common supervised resident coding loop")
    do_parser.add_argument("task_id", nargs="?")
    do_parser.add_argument("--auth", help="model auth file; defaults to ./auth.json then ~/.codex/auth.json")
    do_parser.add_argument("--model-backend", default=DEFAULT_MODEL_BACKEND, choices=SUPPORTED_MODEL_BACKENDS)
    do_parser.add_argument("--model", help="model name")
    do_parser.add_argument("--base-url", help="model API base URL")
    do_parser.add_argument("--model-timeout", type=float, default=60.0)
    do_parser.add_argument("--max-steps", type=int, default=3)
    do_parser.add_argument("--act-mode", choices=("model", "deterministic"), default="deterministic")
    do_parser.add_argument("--work-guidance", help="extra guidance for the resident work loop")
    do_parser.add_argument("--stream-model", action="store_true", help="stream model text deltas when supported")
    do_parser.add_argument(
        "--compact-live",
        action="store_true",
        help="skip full per-step resumes and keep the live stream to thinking/action/result panes",
    )
    do_parser.add_argument(
        "--prompt-approval",
        action="store_true",
        help="force inline approval prompts before applying dry-run writes, even when stdin is not a TTY",
    )
    do_parser.add_argument(
        "--no-prompt-approval",
        action="store_true",
        help="disable the default inline approval prompt in interactive live mode",
    )
    do_parser.add_argument(
        "--approval-mode",
        choices=APPROVAL_MODES,
        help="approval policy for work-loop dry-run writes; accept-edits applies write/edit previews automatically",
    )
    do_parser.add_argument("--allow-read", action="append", default=[], help="read root; defaults to .")
    do_parser.add_argument("--allow-write", action="append", default=[], help="write root; defaults to .")
    do_parser.add_argument("--read-only", action="store_true", help="do not grant write roots")
    do_parser.add_argument("--verify-command", help="verification command; auto-detected for common projects")
    do_parser.add_argument("--no-verify", action="store_true", help="do not grant run_tests verification")
    do_parser.add_argument("--verify-timeout", type=int, default=300)
    do_parser.set_defaults(func=cmd_do)

    code_parser = subparsers.add_parser(
        "code",
        help="enter the persistent coding cockpit",
        description=(
            "Enter the persistent coding cockpit.\n\n"
            "With a task id, mew creates or reuses that task's native work session,\n"
            "caches the continue gates, then opens coding-scoped work-mode chat."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Common flows:\n"
            "  mew code <task-id>\n"
            "  mew code <task-id> --read-only --no-verify\n"
            "  mew code <task-id> --quiet --timeout 0\n"
            "  mew work <task-id> --session --resume --allow-read .\n"
            "  mew memory --add \"Prefer compact diffs\" --category preferences\n"
            "  mew chat --kind coding --work-mode"
        ),
    )
    code_parser.add_argument("task_id", nargs="?")
    code_parser.add_argument("--auth", help="model auth file; defaults to ./auth.json then ~/.codex/auth.json")
    code_parser.add_argument("--model-backend", choices=SUPPORTED_MODEL_BACKENDS)
    code_parser.add_argument("--model", help="model name")
    code_parser.add_argument("--base-url", help="model API base URL")
    code_parser.add_argument("--allow-read", action="append", default=[], help="read root cached for /continue; defaults to . when task_id is supplied")
    code_parser.add_argument("--allow-write", action="append", default=[], help="write root cached for /continue; defaults to . unless --read-only")
    code_parser.add_argument("--read-only", action="store_true", help="do not cache write roots for /continue")
    code_parser.add_argument("--verify-command", help="verification command cached for /continue; auto-detected for common projects")
    code_parser.add_argument("--no-verify", action="store_true", help="do not cache run_tests verification")
    code_parser.add_argument("--verify-timeout", type=int, default=300)
    code_parser.add_argument("--compact-live", action="store_true", help="cache compact live output for /continue")
    code_parser.add_argument("--prompt-approval", action="store_true", help="cache forced inline approval prompts")
    code_parser.add_argument("--no-prompt-approval", action="store_true", help="cache disabled inline approval prompts")
    code_parser.add_argument(
        "--approval-mode",
        choices=APPROVAL_MODES,
        help="cache approval policy for work-loop writes; accept-edits applies write/edit previews automatically",
    )
    code_parser.add_argument(
        "--poll-interval",
        type=float,
        default=DEFAULT_ATTACH_POLL_INTERVAL_SECONDS,
        help=f"chat poll interval in seconds; default {DEFAULT_ATTACH_POLL_INTERVAL_SECONDS:g}",
    )
    code_parser.add_argument("--limit", type=int, default=5, help="maximum items in the startup brief")
    code_parser.add_argument("--mark-read", action="store_true", help="mark printed messages as read")
    code_parser.add_argument("--activity", dest="activity", action="store_true", help="show runtime activity lines")
    code_parser.add_argument("--no-activity", dest="activity", action="store_false", help="hide runtime activity lines")
    code_parser.add_argument("--no-brief", action="store_true", help="do not print the startup brief")
    code_parser.add_argument("--quiet", action="store_true", help="start without brief, unread messages, activity, or startup controls")
    code_parser.add_argument("--show-unread", dest="no_unread", action="store_false", help="print unread messages on startup")
    code_parser.add_argument("--no-unread", dest="no_unread", action="store_true", help=argparse.SUPPRESS)
    code_parser.add_argument("--timeout", type=float, help="leave chat after this many seconds")
    code_parser.set_defaults(activity=False)
    code_parser.set_defaults(no_unread=True)
    code_parser.set_defaults(func=cmd_code)

    work_parser = subparsers.add_parser("work", help="show a task coding workbench")
    work_parser.add_argument("task_id", nargs="?")
    work_parser.add_argument("--ai", action="store_true", help="let the resident model choose and run work-session tools")
    work_parser.add_argument("--live", action="store_true", help="run --ai with progress and print a resume after each step")
    work_parser.add_argument(
        "--follow",
        action="store_true",
        help="run a compact continuous live loop with model streaming; defaults to 10 steps unless --max-steps is set",
    )
    work_parser.add_argument("--auth", help="model auth file for --ai; defaults to ./auth.json then ~/.codex/auth.json")
    work_parser.add_argument("--model-backend", default="codex", help="model backend for --ai")
    work_parser.add_argument("--model", help="model name for --ai")
    work_parser.add_argument("--base-url", help="model API base URL for --ai")
    work_parser.add_argument("--model-timeout", type=float, default=60.0, help="model timeout for --ai")
    work_parser.add_argument("--max-steps", type=int, help="maximum model tool turns for --ai")
    work_parser.add_argument(
        "--act-mode",
        choices=("model", "deterministic"),
        default=None,
        help="ACT phase mode for --ai; default is deterministic in --live and model otherwise",
    )
    work_parser.add_argument("--work-guidance", help="extra guidance for --ai work mode")
    work_parser.add_argument("--progress", action="store_true", help="stream work progress and command output lines to stderr")
    work_parser.add_argument("--quiet", action="store_true", help="suppress default work progress lines unless --progress is set")
    work_parser.add_argument("--stream-model", action="store_true", help="stream model text deltas to progress output when supported")
    work_parser.add_argument(
        "--compact-live",
        action="store_true",
        help="in --live mode, skip the full per-step resume and keep the stream to thinking/action/result panes",
    )
    work_parser.add_argument(
        "--prompt-approval",
        action="store_true",
        help="force inline approval prompts before applying dry-run writes in --live mode, even when stdin is not a TTY",
    )
    work_parser.add_argument(
        "--no-prompt-approval",
        action="store_true",
        help="disable the default inline approval prompt in interactive --live mode",
    )
    work_parser.add_argument(
        "--approval-mode",
        choices=APPROVAL_MODES,
        help="approval policy for work-loop dry-run writes; accept-edits applies write/edit previews automatically",
    )
    work_parser.add_argument("--start-session", action="store_true", help="start or reuse a native work session")
    work_parser.add_argument("--session", action="store_true", help="show the active native work session")
    work_parser.add_argument("--close-session", action="store_true", help="close the active native work session")
    work_parser.add_argument("--stop-session", action="store_true", help="request the active native work loop to stop at the next boundary")
    work_parser.add_argument("--stop-reason", help="reason recorded with --stop-session")
    work_parser.add_argument(
        "--session-note",
        help="record a durable note on the active native work session, or latest task session when task_id is provided",
    )
    work_parser.add_argument("--steer", help="queue guidance for the next live/follow work step")
    work_parser.add_argument("--queue-followup", help="queue a follow-up message for a later live/follow work step")
    work_parser.add_argument(
        "--interrupt-submit",
        help="stop the current step at the next boundary and submit this guidance immediately after",
    )
    work_parser.add_argument(
        "--reply-file",
        help="apply a structured follow reply JSON file with observer actions",
    )
    work_parser.add_argument(
        "--reply-schema",
        action="store_true",
        help="print the structured follow reply schema/template",
    )
    work_parser.add_argument(
        "--follow-status",
        action="store_true",
        help="inspect the latest follow snapshot freshness and producer process",
    )
    work_parser.add_argument("--recover-session", action="store_true", help="recover a safely retryable interrupted work-session tool")
    work_parser.add_argument(
        "--auto-recover-safe",
        action="store_true",
        help="with --session --resume, retry one interrupted safe tool after explicit gates",
    )
    work_parser.add_argument("--approve-tool", type=int, help="approve and apply a dry-run write/edit tool call")
    work_parser.add_argument("--approve-all", action="store_true", help="approve and apply all pending dry-run write/edit tool calls")
    work_parser.add_argument(
        "--defer-verify",
        action="store_true",
        help="apply an approved write/edit now and leave verification for a later paired approval or manual verify",
    )
    work_parser.add_argument(
        "--allow-unpaired-source-edit",
        action="store_true",
        help="allow approval of a src/mew/** write/edit without a paired tests/** write/edit in the same work session",
    )
    work_parser.add_argument("--reject-tool", type=int, help="reject a dry-run write/edit tool call")
    work_parser.add_argument("--reject-reason", help="reason recorded with --reject-tool")
    work_parser.add_argument(
        "--tool",
        choices=(
            "inspect_dir",
            "read_file",
            "search_text",
            "glob",
            "git_status",
            "git_diff",
            "git_log",
            "run_command",
            "run_tests",
            "write_file",
            "edit_file",
            "edit_file_hunks",
        ),
        help="run a native work-session tool",
    )
    work_parser.add_argument("--allow-read", action="append", default=[], help="read root for native work tools; persisted on the work session")
    work_parser.add_argument("--allow-write", action="append", default=[], help="write root for native work tools; persisted on the work session")
    work_parser.add_argument("--allow-shell", action="store_true", help="allow run_command work-session tool; persisted on the work session")
    work_parser.add_argument("--allow-verify", action="store_true", help="allow run_tests work-session tool; persisted on the work session")
    work_parser.add_argument("--path", default=".", help="path for a native work tool")
    work_parser.add_argument("--query", help="query for search_text")
    work_parser.add_argument("--pattern", help="pattern for glob")
    work_parser.add_argument("--command", help="command for run_command or run_tests")
    work_parser.add_argument("--base", help="base ref for git_diff base...HEAD")
    work_parser.add_argument("--staged", action="store_true", help="show staged changes for git_diff")
    work_parser.add_argument("--stat", action="store_true", help="show diffstat for git_diff")
    work_parser.add_argument("--content", help="content for write_file")
    work_parser.add_argument("--old", help="old text for edit_file")
    work_parser.add_argument("--new", help="new text for edit_file")
    work_parser.add_argument("--edits-json", help="JSON list of {old,new} hunks for edit_file_hunks")
    work_parser.add_argument("--create", action="store_true", help="allow write_file to create a file")
    work_parser.add_argument("--replace-all", action="store_true", help="replace all edit_file matches")
    work_parser.add_argument("--apply", action="store_true", help="apply write_file/edit_file/edit_file_hunks instead of dry-run")
    work_parser.add_argument("--verify-command", help="verification command required for applied writes; persisted on the work session")
    work_parser.add_argument("--verify-cwd", default=".", help="verification command cwd")
    work_parser.add_argument("--verify-timeout", type=float, default=300.0, help="verification timeout")
    work_parser.add_argument("--cwd", default=".", help="cwd for run_command or run_tests")
    work_parser.add_argument("--timeout", type=float, default=300.0, help="timeout for run_command or run_tests")
    work_parser.add_argument("--limit", type=int, default=50, help="maximum inspect_dir entries")
    work_parser.add_argument("--max-chars", type=int, default=DEFAULT_READ_MAX_CHARS, help="maximum read_file characters")
    work_parser.add_argument("--offset", type=int, default=0, help="character offset for read_file")
    work_parser.add_argument("--line-start", type=int, help="1-based starting line for read_file")
    work_parser.add_argument("--line-count", type=int, help="number of lines to read with --line-start")
    work_parser.add_argument("--max-matches", type=int, default=50, help="maximum search/glob matches")
    work_parser.add_argument("--context-lines", type=int, default=3, help="context lines around search_text matches")
    work_parser.add_argument("--details", action="store_true", help="show model turns, touched files, and tool details")
    work_parser.add_argument("--resume", action="store_true", help="show a compact work-session resume bundle")
    work_parser.add_argument("--timeline", action="store_true", help="show a compact chronological work-session timeline")
    work_parser.add_argument("--diffs", action="store_true", help="show recent work-session write/edit diffs")
    work_parser.add_argument("--tests", action="store_true", help="show recent work-session test and verification output")
    work_parser.add_argument("--commands", action="store_true", help="show recent work-session command output")
    work_parser.add_argument("--cells", action="store_true", help="show stable work-session cockpit cells")
    work_parser.add_argument(
        "--cell-tail-lines",
        type=int,
        help="maximum stdout/stderr tail lines per command/test cell in --cells output",
    )
    work_parser.add_argument("--json", action="store_true", help="print structured JSON")
    work_parser.set_defaults(func=cmd_work)

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
    tool_read_parser.add_argument("--max-chars", type=int, default=DEFAULT_READ_MAX_CHARS)
    tool_read_parser.add_argument("--offset", type=int, default=0)
    tool_read_parser.add_argument("--line-start", type=int, help="1-based starting line")
    tool_read_parser.add_argument("--line-count", type=int, help="number of lines to read")
    tool_read_parser.add_argument("--json", action="store_true", help="print structured JSON")
    tool_read_parser.set_defaults(func=cmd_tool_read)

    tool_search_parser = tool_subparsers.add_parser("search", help="fixed-string search under an allowed root")
    tool_search_parser.add_argument("query")
    tool_search_parser.add_argument("path", nargs="?", default=".")
    tool_search_parser.add_argument("--root", action="append", default=[], help="allowed root; default current directory")
    tool_search_parser.add_argument("--max-matches", type=int, default=50)
    tool_search_parser.add_argument("--context-lines", type=int, default=3, help="context lines around matches")
    tool_search_parser.add_argument("--pattern", help="optional rg glob filter, e.g. '*.md'")
    tool_search_parser.add_argument("--json", action="store_true", help="print structured JSON")
    tool_search_parser.set_defaults(func=cmd_tool_search)

    tool_glob_parser = tool_subparsers.add_parser("glob", help="glob paths under an allowed root")
    tool_glob_parser.add_argument("pattern")
    tool_glob_parser.add_argument("path", nargs="?", default=".")
    tool_glob_parser.add_argument("--root", action="append", default=[], help="allowed root; default current directory")
    tool_glob_parser.add_argument("--max-matches", type=int, default=100)
    tool_glob_parser.add_argument("--json", action="store_true", help="print structured JSON")
    tool_glob_parser.set_defaults(func=cmd_tool_glob)

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

    self_improve_parser = subparsers.add_parser(
        "self-improve",
        help="create, plan, or open a mew self-improvement task",
        description=(
            "Create or continue a mew self-improvement task.\n\n"
            "Default mode creates a programmer-plan task. Use --native to prepare a\n"
            "native mew work task without a programmer plan, or --start-session to\n"
            "open or reuse that work session immediately."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Native work-session flow:\n"
            "  mew self-improve --start-session --focus \"Make the coding cockpit calmer\"\n"
            "    prints concrete continue/follow/status/resume/cells/active-memory/chat controls for the task\n"
            "  mew self-improve --start-session --json --focus \"Make the coding cockpit calmer\"\n"
            "    returns controls.continue, controls.follow, controls.status, controls.resume, controls.cells, controls.active_memory, controls.chat\n"
            "  # Or copy one of the printed controls and continue manually:\n"
            "  mew work <task-id> --live --allow-read . --compact-live --max-steps 1\n"
            "  mew work <task-id> --follow --allow-read . --compact-live --quiet --max-steps 10\n\n"
            "  mew work <task-id> --session --resume --allow-read .\n"
            "  mew work <task-id> --cells\n"
            "  mew memory --active --task-id <task-id>\n"
            "  mew work <task-id> --follow-status --json\n\n"
            "  mew chat\n\n"
            "Planned dispatcher flow:\n"
            "  mew self-improve --focus \"Improve stale agent-run handling\"\n"
            "  mew self-improve --focus \"Improve docs\" --ready --auto-execute --dispatch --dry-run"
        ),
    )
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
    self_improve_parser.add_argument(
        "--native",
        action="store_true",
        help="prepare native mew work instead of a programmer-plan/ai-cli dispatch",
    )
    self_improve_parser.add_argument(
        "--start-session",
        action="store_true",
        help="open or reuse the native mew work session now; implies --native",
    )
    self_improve_parser.add_argument("--force", action="store_true", help="create a new task even if one is open")
    self_improve_parser.add_argument("--force-plan", action="store_true", help="create a new plan even if one exists")
    self_improve_parser.add_argument("--prompt", action="store_true", help="print generated implementation and review prompts")
    self_improve_parser.add_argument(
        "--audit",
        nargs="?",
        const="latest",
        help="show the M5 audit bundle for a self-improvement task id, or latest when omitted",
    )
    self_improve_parser.add_argument(
        "--audit-sequence",
        nargs="+",
        help="show an M5 audit summary for a sequence of self-improvement task ids",
    )
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
    self_improve_parser.add_argument("--json", action="store_true", help="print structured JSON")
    self_improve_parser.set_defaults(func=cmd_self_improve)

    outbox_parser = subparsers.add_parser("outbox", help="show runtime messages")
    outbox_parser.add_argument("--all", action="store_true", help="show read and unread messages")
    outbox_parser.add_argument("--limit", type=int, help="show only the most recent N matching messages")
    outbox_parser.add_argument("--json", action="store_true", help="print structured JSON")
    outbox_parser.set_defaults(func=cmd_outbox)

    questions_parser = subparsers.add_parser("questions", help="show open questions")
    questions_parser.add_argument("--all", action="store_true", help="include answered and deferred questions")
    questions_parser.add_argument("--defer", action="append", default=[], help="defer an open question id")
    questions_parser.add_argument("--reopen", action="append", default=[], help="reopen a deferred question id")
    questions_parser.add_argument("--reason", help="short reason stored when deferring")
    questions_parser.add_argument("--json", action="store_true", help="print structured JSON")
    questions_parser.set_defaults(func=cmd_questions)

    attention_parser = subparsers.add_parser("attention", help="show attention items")
    attention_parser.add_argument("--all", action="store_true", help="include resolved attention items")
    attention_parser.add_argument("--resolve", action="append", default=[], help="resolve an open attention item")
    attention_parser.add_argument("--resolve-all", action="store_true", help="resolve all open attention items")
    attention_parser.add_argument("--json", action="store_true", help="print structured JSON")
    attention_parser.set_defaults(func=cmd_attention)

    archive_parser = subparsers.add_parser("archive", help="archive old runtime records and effect log entries")
    archive_parser.add_argument("--apply", action="store_true", help="write archive and compact active state")
    archive_parser.add_argument(
        "--keep-recent",
        type=int,
        default=100,
        help="records to keep active per section",
    )
    archive_parser.set_defaults(func=cmd_archive)

    memory_parser = subparsers.add_parser("memory", help="show what mew remembers")
    memory_parser.add_argument("--recent", type=int, default=5, help="number of recent shallow memory events")
    memory_parser.add_argument("--deep", action="store_true", help="include deep memory sections")
    memory_parser.add_argument("--search", help="search shallow and deep memory text")
    memory_parser.add_argument("--active", action="store_true", help="show typed memory that would be injected now")
    memory_parser.add_argument("--task-id", help="task id used to select active typed memory")
    memory_parser.add_argument("--limit", type=int, default=20, help="maximum search matches")
    memory_parser.add_argument("--json", action="store_true", help="print structured search results")
    memory_parser.add_argument("--add", help="add a deep memory entry")
    memory_parser.add_argument(
        "--scope",
        choices=("private", "team"),
        help="typed memory scope for --add or --search",
    )
    memory_parser.add_argument(
        "--type",
        dest="memory_type",
        choices=("user", "feedback", "project", "reference", "unknown"),
        help="typed memory type for --add or --search; enables file-backed typed memory for --add",
    )
    memory_parser.add_argument("--name", help="typed memory name for --add --type")
    memory_parser.add_argument("--description", help="typed memory description for --add --type")
    memory_parser.add_argument(
        "--kind",
        dest="memory_kind",
        choices=CODING_MEMORY_KINDS,
        help="coding memory kind for --add or --search; valid only with --type project",
    )
    memory_parser.add_argument(
        "--category",
        choices=("preferences", "project", "decisions"),
        default="project",
        help="deep memory category for --add",
    )
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
    listen_parser.add_argument(
        "--kind",
        choices=["coding", "research", "personal", "admin", "unknown"],
        help="scope streamed outbox messages by task kind",
    )
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
    attach_parser.add_argument(
        "--kind",
        choices=["coding", "research", "personal", "admin", "unknown"],
        help="scope streamed outbox messages by task kind",
    )
    attach_parser.add_argument("--mark-read", action="store_true", help="mark printed messages as read")
    attach_parser.add_argument("--no-activity", dest="activity", action="store_false", help="hide runtime activity lines")
    attach_parser.add_argument("--no-input", action="store_true", help="do not read interactive terminal input")
    attach_parser.add_argument("--timeout", type=float, help="detach after this many seconds")
    attach_parser.set_defaults(activity=True)
    attach_parser.set_defaults(func=cmd_attach)

    chat_parser = subparsers.add_parser(
        "chat",
        help="human-friendly chat REPL for mew",
        description="human-friendly chat REPL for mew.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Slash commands available inside chat:\n\n" + CHAT_HELP,
    )
    chat_parser.add_argument(
        "--poll-interval",
        type=float,
        default=DEFAULT_ATTACH_POLL_INTERVAL_SECONDS,
        help=f"poll interval in seconds; default {DEFAULT_ATTACH_POLL_INTERVAL_SECONDS:g}",
    )
    chat_parser.add_argument("--limit", type=int, default=5, help="maximum items in the startup brief")
    chat_parser.add_argument(
        "--kind",
        choices=["coding", "research", "personal", "admin", "unknown"],
        help="scope the startup brief and unread messages by task kind",
    )
    chat_parser.add_argument("--mark-read", action="store_true", help="mark printed messages as read")
    chat_parser.add_argument("--no-activity", dest="activity", action="store_false", help="hide runtime activity lines")
    chat_parser.add_argument("--no-brief", action="store_true", help="do not print the startup brief")
    chat_parser.add_argument("--no-unread", action="store_true", help="do not print unread messages on startup")
    chat_parser.add_argument("--quiet", action="store_true", help="start without brief, unread messages, activity, or startup controls")
    chat_parser.add_argument(
        "--work-mode",
        action="store_true",
        help="treat chat text as work-session continue guidance and blank lines as continue",
    )
    chat_parser.add_argument("--timeout", type=float, help="leave chat after this many seconds")
    chat_parser.set_defaults(activity=True)
    chat_parser.set_defaults(func=cmd_chat)

    log_parser = subparsers.add_parser("log", help="show runtime log")
    log_parser.set_defaults(func=cmd_log)

    chat_log_parser = subparsers.add_parser("chat-log", help="show recent chat input transcript")
    chat_log_parser.add_argument("--limit", type=int, default=20, help="maximum transcript entries")
    chat_log_parser.add_argument("--json", action="store_true", help="print structured JSON")
    chat_log_parser.set_defaults(func=cmd_chat_log)

    trace_parser = subparsers.add_parser("trace", help="show opt-in model THINK/ACT traces")
    trace_parser.add_argument("--limit", type=int, default=20, help="maximum trace records")
    trace_parser.add_argument("--phase", help="show only records for this phase, for example think_reflex")
    trace_parser.add_argument("--prompt", action="store_true", help="include full stored prompts")
    trace_parser.add_argument("--json", action="store_true", help="print structured JSON")
    trace_parser.set_defaults(func=cmd_trace)

    effects_parser = subparsers.add_parser("effects", help="show recent state effect checkpoints")
    effects_parser.add_argument("limit_arg", nargs="?", type=int, help="maximum effect records")
    effects_parser.add_argument("--limit", type=int, default=20, help="maximum effect records")
    effects_parser.add_argument("--json", action="store_true", help="print structured JSON")
    effects_parser.set_defaults(func=cmd_effects)

    runtime_effects_parser = subparsers.add_parser("runtime-effects", help="show recent runtime effect journal entries")
    runtime_effects_parser.add_argument("limit_arg", nargs="?", type=int, help="maximum runtime effects")
    runtime_effects_parser.add_argument("--limit", type=int, default=20, help="maximum runtime effects")
    runtime_effects_parser.add_argument("--json", action="store_true", help="print structured JSON")
    runtime_effects_parser.set_defaults(func=cmd_runtime_effects)

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
    task_parser.add_argument("--json", action="store_true", help="print the default task list as JSON")
    task_parser.set_defaults(func=cmd_task_list)
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
    add_parser.add_argument("--json", action="store_true", help="print the created task as JSON")
    add_parser.set_defaults(func=cmd_task_add)

    list_parser = task_subparsers.add_parser("list", help="list tasks")
    list_parser.add_argument("--all", action="store_true", help="include done tasks")
    list_parser.add_argument("--kind", choices=("coding", "research", "personal", "admin", "unknown"), help="filter by task kind")
    list_parser.add_argument(
        "--status",
        choices=("todo", "ready", "running", "blocked", "done", "pending", "open"),
        help="filter by task status across all tasks; pending/open means not done",
    )
    list_parser.add_argument("--limit", type=int, help="show at most N tasks")
    list_parser.add_argument("--json", action="store_true", help="print tasks as JSON")
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
    show_parser.add_argument("--json", action="store_true", help="print the task as JSON")
    show_parser.set_defaults(func=cmd_task_show)

    done_parser = task_subparsers.add_parser("done", help="mark a task done")
    done_parser.add_argument("task_id")
    done_parser.add_argument("--summary", help="completion summary; passing test reports create a user-reported verification")
    done_parser.add_argument("--json", action="store_true", help="print the completed task as JSON")
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
    update_parser.add_argument("--json", action="store_true", help="print the updated task as JSON")
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
    agent_sweep_parser.add_argument("--json", action="store_true", help="print structured JSON")
    agent_sweep_parser.set_defaults(func=cmd_agent_sweep)

    return parser


def require_positive_float(parser, args, attribute, flag):
    value = getattr(args, attribute, None)
    if value is not None and value <= 0:
        parser.error(f"{flag} must be positive")


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    if hasattr(args, "interval_minutes") and args.interval_minutes is not None:
        require_positive_float(parser, args, "interval_minutes", "--interval-minutes")
        args.interval = args.interval_minutes * 60.0
    require_positive_float(parser, args, "interval", "--interval")
    require_positive_float(parser, args, "poll_interval", "--poll-interval")
    require_positive_float(parser, args, "message_poll_interval", "--poll-interval")
    require_positive_float(parser, args, "time_dilation", "--time-dilation")

    if args.message and args.command is None:
        args.wait = args.message_wait
        args.timeout = args.message_timeout
        args.poll_interval = args.message_poll_interval
        args.mark_read = args.message_mark_read
        return cmd_message(args)
    if hasattr(args, "func"):
        return args.func(args)

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
