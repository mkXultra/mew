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
    cmd_attention,
    cmd_brief,
    cmd_desires_init,
    cmd_desires_show,
    cmd_doctor,
    cmd_guidance_init,
    cmd_guidance_show,
    cmd_listen,
    cmd_log,
    cmd_memory,
    cmd_message,
    cmd_next,
    cmd_outbox,
    cmd_policy_init,
    cmd_policy_show,
    cmd_questions,
    cmd_reply,
    cmd_self_init,
    cmd_self_improve,
    cmd_self_show,
    cmd_status,
    cmd_task_add,
    cmd_task_dispatch,
    cmd_task_done,
    cmd_task_list,
    cmd_task_plan,
    cmd_task_run,
    cmd_task_show,
    cmd_task_update,
)
from .config import (
    DEFAULT_ATTACH_POLL_INTERVAL_SECONDS,
    DEFAULT_CODEX_MODEL,
    DEFAULT_CODEX_WEB_BASE_URL,
    DEFAULT_INTERVAL_SECONDS,
    DEFAULT_TASK_TIMEOUT_SECONDS,
)
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
        "--ai",
        action="store_true",
        help="use Codex Web API via OAuth auth.json for startup and user messages",
    )
    run_parser.add_argument(
        "--ai-ticks",
        action="store_true",
        help="also call Codex Web API for legacy tick events",
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
        "--task-timeout",
        type=float,
        default=DEFAULT_TASK_TIMEOUT_SECONDS,
        help=f"autonomous task command timeout in seconds; default {DEFAULT_TASK_TIMEOUT_SECONDS:g}",
    )
    run_parser.add_argument(
        "--auth",
        help="path to Codex OAuth auth.json; defaults to ./auth.json then ~/.codex/auth.json",
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
        "--model",
        default=os.environ.get("MEW_CODEX_MODEL", DEFAULT_CODEX_MODEL),
        help=f"Codex model name; default {DEFAULT_CODEX_MODEL}",
    )
    run_parser.add_argument(
        "--base-url",
        default=os.environ.get("MEW_CODEX_BASE_URL", DEFAULT_CODEX_WEB_BASE_URL),
        help=f"Codex Web API base URL; default {DEFAULT_CODEX_WEB_BASE_URL}",
    )
    run_parser.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="Codex Web API request timeout in seconds",
    )
    run_parser.set_defaults(func=run_runtime)

    status_parser = subparsers.add_parser("status", help="show runtime status")
    status_parser.set_defaults(func=cmd_status)

    doctor_parser = subparsers.add_parser("doctor", help="check local mew dependencies and state")
    doctor_parser.add_argument("--auth", help="path to Codex OAuth auth.json")
    doctor_parser.add_argument("--require-auth", action="store_true", help="fail if Codex OAuth auth is missing")
    doctor_parser.set_defaults(func=cmd_doctor)

    brief_parser = subparsers.add_parser("brief", help="show a compact operational brief")
    brief_parser.add_argument("--limit", type=int, default=5, help="maximum items per section")
    brief_parser.set_defaults(func=cmd_brief)

    next_parser = subparsers.add_parser("next", help="print the next useful command or move")
    next_parser.set_defaults(func=cmd_next)

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
    self_improve_parser.set_defaults(func=cmd_self_improve)

    outbox_parser = subparsers.add_parser("outbox", help="show runtime messages")
    outbox_parser.add_argument("--all", action="store_true", help="show read and unread messages")
    outbox_parser.set_defaults(func=cmd_outbox)

    questions_parser = subparsers.add_parser("questions", help="show open questions")
    questions_parser.add_argument("--all", action="store_true", help="include answered questions")
    questions_parser.set_defaults(func=cmd_questions)

    attention_parser = subparsers.add_parser("attention", help="show attention items")
    attention_parser.add_argument("--all", action="store_true", help="include resolved attention items")
    attention_parser.add_argument("--resolve", action="append", default=[], help="resolve an open attention item")
    attention_parser.add_argument("--resolve-all", action="store_true", help="resolve all open attention items")
    attention_parser.set_defaults(func=cmd_attention)

    memory_parser = subparsers.add_parser("memory", help="show what mew remembers")
    memory_parser.add_argument("--recent", type=int, default=5, help="number of recent shallow memory events")
    memory_parser.add_argument("--deep", action="store_true", help="include deep memory sections")
    memory_parser.add_argument("--compact", action="store_true", help="compact recent shallow memory into project memory")
    memory_parser.add_argument("--keep-recent", type=int, default=5, help="recent events to keep when compacting")
    memory_parser.add_argument("--dry-run", action="store_true", help="print compact note without changing state")
    memory_parser.set_defaults(func=cmd_memory)

    reply_parser = subparsers.add_parser("reply", help="answer a question")
    reply_parser.add_argument("question_id")
    reply_parser.add_argument("text")
    reply_parser.set_defaults(func=cmd_reply)

    ack_parser = subparsers.add_parser("ack", help="mark outbox messages as read")
    ack_parser.add_argument("message_ids", nargs="*")
    ack_parser.add_argument("--all", action="store_true", help="mark all unread outbox messages as read")
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

    log_parser = subparsers.add_parser("log", help="show runtime log")
    log_parser.set_defaults(func=cmd_log)

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
    add_parser.add_argument("--priority", choices=("low", "normal", "high"), default="normal")
    add_parser.set_defaults(func=cmd_task_add)

    list_parser = task_subparsers.add_parser("list", help="list tasks")
    list_parser.add_argument("--all", action="store_true", help="include done tasks")
    list_parser.set_defaults(func=cmd_task_list)

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
