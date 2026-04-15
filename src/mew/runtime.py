from copy import deepcopy
import os
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
from .config import (
    DEFAULT_CODEX_MODEL,
    DEFAULT_CODEX_WEB_BASE_URL,
    DEFAULT_INTERVAL_SECONDS,
    DEFAULT_TASK_TIMEOUT_SECONDS,
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
    append_log,
    ensure_desires,
    ensure_guidance,
    ensure_policy,
    ensure_self,
    has_pending_user_message,
    load_state,
    read_desires,
    read_guidance,
    read_policy,
    read_self,
    release_lock,
    save_state,
    state_lock,
)
from .sweep import sweep_agent_runs
from .timeutil import now_iso
from .toolbox import run_command_record


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
    runtime["current_phase"] = None
    runtime["cycle_started_at"] = None
    runtime["last_action"] = "runtime stopped"

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
    autonomy["allow_verify"] = bool(args.allow_verify)
    autonomy["verify_command_configured"] = bool(args.verify_command)
    autonomy["allow_write"] = bool(args.allow_write)
    autonomy["updated_at"] = current_time

    autonomous_for_cycle = effective_enabled and not pending_user
    return {
        "autonomous": autonomous_for_cycle,
        "autonomy_level": effective_level if autonomous_for_cycle else "off",
        "allow_agent_run": bool(args.allow_agent_run) and autonomous_for_cycle,
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
        allow_verify=args.allow_verify,
        verify_command=args.verify_command or "",
        verify_interval_seconds=max(0.0, args.verify_interval_minutes * 60.0),
        allow_write=bool(args.allow_write),
        allowed_read_roots=args.allow_read,
        allowed_write_roots=args.allow_write,
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
        allow_verify=args.allow_verify,
        verify_command=args.verify_command or "",
        verify_timeout=args.verify_timeout,
        allow_write=bool(args.allow_write),
        allowed_write_roots=args.allow_write,
        agent_result_timeout=getattr(args, "agent_result_timeout", 10.0),
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
    initial_guidance = read_guidance(args.guidance)
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
        with state_lock():
            state = load_state()
            set_runtime_running(state, lock["started_at"])
            save_state(state)
        append_log(f"## {lock['started_at']}: runtime started pid={os.getpid()}")
        print(f"mew runtime started pid={os.getpid()} state={STATE_FILE}")
        if model_auth:
            print(
                f"{model_backend_label(model_backend)} enabled "
                f"auth={model_auth['path']} model={model} base_url={base_url}"
            )
        if initial_guidance:
            guidance_path = args.guidance or str(GUIDANCE_FILE)
            print(f"guidance loaded path={guidance_path}")
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
            event_snapshot = None
            state_snapshot = None
            decision_plan = None
            action_plan = None
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
            }
            outbox_ids_before = set()
            with state_lock():
                state = load_state()
                if state["runtime_status"].get("state") != "running":
                    set_runtime_running(state, lock["started_at"])
                pending_user = has_pending_user_message(state)
                current_monotonic = time.time()
                if pending_user:
                    reason = "user_input"
                    create_internal_event = False
                elif first:
                    reason = "startup"
                    create_internal_event = True
                elif current_monotonic >= next_passive_at:
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
                    run_runtime_post_run_pipeline(state, args, autonomy_controls)
                    if create_internal_event:
                        add_event(state, reason, "runtime", {"pid": os.getpid()})
                    event = next_unprocessed_event(
                        state,
                        "user_message" if reason == "user_input" else None,
                    )
                    if event:
                        event_id = event["id"]
                        event_snapshot = deepcopy(event)
                        state_snapshot = deepcopy(state)
                        runtime_status["current_event_id"] = event_id
                        runtime_status["current_phase"] = "planning"
                    save_state(state)

            if sleep_for is not None:
                time.sleep(sleep_for)
                continue

            guidance = read_guidance(args.guidance)
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
                        else:
                            state["runtime_status"]["current_phase"] = "precomputing"
                            save_state(state)
                    if action_plan is not None:
                        action_plan = precompute_runtime_action_effects(
                            event_snapshot,
                            action_plan,
                            args,
                            autonomy_controls,
                        )

            with state_lock():
                state = load_state()
                if event_id is not None and decision_plan is not None and action_plan is not None:
                    commit_time = now_iso()
                    state["runtime_status"]["current_phase"] = "committing"
                    save_state(state)
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
                runtime_status = state["runtime_status"]
                runtime_status["current_reason"] = None
                runtime_status["current_event_id"] = None
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
                if args.echo_outbox:
                    new_outbox_messages = [
                        message
                        for message in state.get("outbox", [])
                        if str(message.get("id")) not in outbox_ids_before
                    ]
                save_state(state)
                first = False
                if reason in ("startup", "passive_tick"):
                    next_passive_at = time.time() + args.interval

            print(f"processed {processed_count} event(s) reason={reason}")
            for message in new_outbox_messages:
                text = str(message.get("text") or "").replace("\n", "\n  ")
                print(f"outbox #{message.get('id')} [{message.get('type')}]: {text}")
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
