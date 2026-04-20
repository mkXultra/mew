from pathlib import Path

from .cli_command import mew_command
from .self_improve import DEFAULT_SELF_IMPROVE_TITLE
from .tasks import find_task
from .timeutil import now_iso


M5_AUDIT_SCHEMA_VERSION = 1
M5_CANDIDATE_CREDIT_STATUS = "candidate_no_rescue_reviewed_pending_m3"

RESCUE_INTERVENTION_MARKERS = (
    "supervisor rescue",
    "manual patch",
    "manual file patch",
    "rescue edit",
    "rescue_edit",
)

NO_RESCUE_REVIEW_MARKERS = (
    "no supervisor file patch was used",
    "no supervisor file patch",
    "approvals only",
)

M5_WRITE_TOOLS = {"write_file", "edit_file"}

M5_GOVERNANCE_PATH_RULES = (
    ("roadmap", ("ROADMAP.md", "ROADMAP_STATUS.md")),
    ("skill", (".codex/skills/",)),
    (
        "permission_or_policy",
        (
            "src/mew/agent.py",
            "src/mew/commands.py",
            "src/mew/runtime.py",
            "src/mew/write_tools.py",
        ),
    ),
    (
        "recovery_or_audit",
        (
            "src/mew/context.py",
            "src/mew/self_improve.py",
            "src/mew/self_improve_audit.py",
            "src/mew/work_session.py",
        ),
    ),
)

M5_EXTERNAL_VISIBLE_COMMAND_MARKERS = (
    "git push",
    "gh pr create",
    "gh issue",
    "gh api repos/",
    "npm publish",
    "twine upload",
    "docker push",
)


def is_self_improve_task_record(task):
    if not isinstance(task, dict):
        return False
    if (task.get("title") or "").strip() == DEFAULT_SELF_IMPROVE_TITLE:
        return True
    return "Created by mew self-improve" in (task.get("notes") or "")


def self_improve_permission_context(defaults):
    defaults = defaults or {}
    return {
        "allow_read": list(defaults.get("allow_read") or []),
        "allow_write": list(defaults.get("allow_write") or []),
        "allow_verify": bool(defaults.get("allow_verify")),
        "verify_command": defaults.get("verify_command") or "",
        "approval_mode": defaults.get("approval_mode") or "default",
        "compact_live": bool(defaults.get("compact_live")),
        "external_visible_side_effects_allowed": False,
    }


def self_improve_effect_budget(defaults):
    defaults = defaults or {}
    return {
        "continue_max_steps": 1,
        "follow_max_steps": 10,
        "write_roots": list(defaults.get("allow_write") or []),
        "verify_command": defaults.get("verify_command") or "",
        "budget_exhaustion_action": "stop_and_report",
        "ambiguous_recovery_action": "stop_and_ask",
    }


def seed_m5_self_improve_audit(session, task):
    if not isinstance(session, dict) or not isinstance(task, dict):
        return {}
    defaults = session.get("default_options") or {}
    current_permission = self_improve_permission_context(defaults)
    current_budget = self_improve_effect_budget(defaults)
    audit = session.get("m5_self_improve_audit")
    if not isinstance(audit, dict):
        audit = {
            "schema_version": M5_AUDIT_SCHEMA_VERSION,
            "created_at": now_iso(),
            "task_id": task.get("id"),
            "product_goal": "make mew an inhabitable passive AI for task and coding work",
            "loop_credit_status": "not_counted_until_closed_with_no_rescue_review",
            "frozen_permission_context": current_permission,
            "effect_budget": current_budget,
            "human_intervention_policy": {
                "allowed": ["approval", "rejection", "redirection", "product_judgment"],
                "disallowed_for_m5_credit": ["manual_file_patch_to_rescue_loop"],
            },
        }
    audit["updated_at"] = now_iso()
    audit["current_permission_context"] = current_permission
    audit["permission_context_drift"] = audit.get("frozen_permission_context") != current_permission
    session["m5_self_improve_audit"] = audit
    return audit


def _latest_self_improve_task(state):
    for task in reversed(state.get("tasks") or []):
        if is_self_improve_task_record(task):
            return task
    return None


def select_self_improve_audit_task(state, task_ref=None):
    if task_ref in (None, "", "latest"):
        return _latest_self_improve_task(state)
    try:
        return find_task(state, int(task_ref))
    except (TypeError, ValueError):
        return None


def latest_session_for_task(state, task_id):
    wanted = str(task_id)
    for session in reversed(state.get("work_sessions") or []):
        if str(session.get("task_id")) == wanted:
            return session
    return None


def work_sessions_for_task(state, task_id):
    wanted = str(task_id)
    return [
        session for session in (state.get("work_sessions") or [])
        if str(session.get("task_id")) == wanted
    ]


def combined_audit_session(sessions):
    combined = {"notes": [], "tool_calls": []}
    for session in sessions or []:
        combined["notes"].extend(session.get("notes") or [])
        combined["tool_calls"].extend(session.get("tool_calls") or [])
    return combined


def self_improve_audit_controls(task):
    task_id = task.get("id")
    return {
        "audit": mew_command("self-improve", "--audit", task_id),
        "audit_json": mew_command("self-improve", "--audit", task_id, "--json"),
    }


def self_improve_audit_sequence_controls(task_refs):
    return {
        "audit_sequence": mew_command("self-improve", "--audit-sequence", *task_refs),
        "audit_sequence_json": mew_command("self-improve", "--audit-sequence", *task_refs, "--json"),
    }


def _tool_approval_records(session):
    records = []
    for call in session.get("tool_calls") or []:
        if not isinstance(call, dict):
            continue
        approval = call.get("approval_status")
        result = call.get("result") or {}
        if approval or result.get("dry_run"):
            record = {
                "id": call.get("id"),
                "tool": call.get("tool"),
                "status": call.get("status"),
                "approval_status": approval or "",
                "dry_run": bool(result.get("dry_run")),
            }
            if "rolled_back" in result:
                record["rolled_back"] = result.get("rolled_back")
            if result.get("rollback_error"):
                record["rollback_error"] = result.get("rollback_error")
            records.append(record)
    return records


def _recovery_records(session):
    records = []
    for call in session.get("tool_calls") or []:
        if not isinstance(call, dict):
            continue
        result = call.get("result") or {}
        rollback_recorded = "rolled_back" in result or bool(result.get("rollback_error"))
        if call.get("status") == "interrupted" or call.get("recovery_status") or call.get("recovered_by_tool_call_id"):
            records.append(
                {
                    "id": call.get("id"),
                    "tool": call.get("tool"),
                    "status": call.get("status"),
                    "recovery_status": call.get("recovery_status") or "",
                    "recovered_by_tool_call_id": call.get("recovered_by_tool_call_id"),
                }
            )
        elif call.get("status") == "failed" and rollback_recorded:
            records.append(
                {
                    "id": call.get("id"),
                    "tool": call.get("tool"),
                    "status": call.get("status"),
                    "recovery_status": "rolled_back" if result.get("rolled_back") else "rollback_failed",
                    "recovered_by_tool_call_id": None,
                    "rolled_back": result.get("rolled_back"),
                    "rollback_error": result.get("rollback_error") or "",
                }
            )
    return records


def _verification_status(exit_code):
    if exit_code == 0:
        return "passed"
    if exit_code is None:
        return "unknown"
    return "failed"


def _verification_record_from_command(source, record):
    return {
        "source": source,
        "id": record.get("id"),
        "command": record.get("command") or "",
        "exit_code": record.get("exit_code"),
        "status": _verification_status(record.get("exit_code")),
        "started_at": record.get("started_at") or "",
        "finished_at": record.get("finished_at") or "",
        "reason": record.get("reason") or "",
    }


def _verification_records(state, task, session):
    records = []
    for call in (session or {}).get("tool_calls") or []:
        if not isinstance(call, dict):
            continue
        result = call.get("result") or {}
        if call.get("tool") == "run_tests" and isinstance(result, dict) and "exit_code" in result:
            item = _verification_record_from_command("work_tool", result)
            item["tool_call_id"] = call.get("id")
            item["tool"] = call.get("tool") or ""
            records.append(item)
        verification = result.get("verification")
        if isinstance(verification, dict):
            item = _verification_record_from_command("work_tool", verification)
            item["tool_call_id"] = call.get("id")
            item["tool"] = call.get("tool") or ""
            records.append(item)
    task_id = str((task or {}).get("id"))
    for run in state.get("verification_runs") or []:
        if not isinstance(run, dict) or str(run.get("task_id")) != task_id:
            continue
        records.append(_verification_record_from_command("task_verification", run))
    return records


def _normalize_audit_path(path):
    text = str(path or "").strip()
    if not text:
        return ""
    if text.startswith("./"):
        text = text[2:]
    try:
        candidate = Path(text).expanduser()
        if candidate.is_absolute():
            resolved = candidate.resolve(strict=False)
            try:
                return resolved.relative_to(Path.cwd().resolve(strict=False)).as_posix()
            except ValueError:
                return str(resolved)
    except (OSError, ValueError):
        pass
    return text.replace("\\", "/")


def _unique_non_empty(values):
    seen = set()
    items = []
    for value in values:
        value = value or ""
        if not value or value in seen:
            continue
        seen.add(value)
        items.append(value)
    return items


def _work_call_paths(call):
    values = []
    for container in (call.get("parameters") or {}, call.get("result") or {}, call.get("write_intent") or {}):
        if not isinstance(container, dict):
            continue
        for key in ("path", "target_path", "file", "filename"):
            values.append(_normalize_audit_path(container.get(key)))
        paths = container.get("paths")
        if isinstance(paths, list):
            values.extend(_normalize_audit_path(path) for path in paths)
    return _unique_non_empty(values)


def _m5_governance_path_category(path):
    normalized = _normalize_audit_path(path)
    for category, patterns in M5_GOVERNANCE_PATH_RULES:
        for pattern in patterns:
            if pattern.endswith("/") and normalized.startswith(pattern):
                return category
            if normalized == pattern:
                return category
    return ""


def _command_texts_for_call(call):
    texts = []
    for container in (call.get("parameters") or {}, call.get("result") or {}):
        if not isinstance(container, dict):
            continue
        for key in ("command", "verify_command"):
            command = container.get(key)
            if isinstance(command, str):
                texts.append(command)
            elif isinstance(command, list):
                texts.append(" ".join(str(part) for part in command))
    return _unique_non_empty(texts)


def _external_visible_side_effect_records(session):
    records = []
    for call in (session or {}).get("tool_calls") or []:
        if not isinstance(call, dict):
            continue
        for command in _command_texts_for_call(call):
            compact = " ".join(command.casefold().split())
            marker = next((item for item in M5_EXTERNAL_VISIBLE_COMMAND_MARKERS if item in compact), "")
            if not marker:
                continue
            records.append(
                {
                    "tool_call_id": call.get("id"),
                    "tool": call.get("tool") or "",
                    "marker": marker,
                    "command": command,
                    "status": call.get("status") or "",
                }
            )
    return records


def _governance_or_policy_edit_records(session):
    records = []
    for call in (session or {}).get("tool_calls") or []:
        if not isinstance(call, dict) or call.get("tool") not in M5_WRITE_TOOLS:
            continue
        result = call.get("result") or {}
        for path in _work_call_paths(call):
            category = _m5_governance_path_category(path)
            if not category:
                continue
            records.append(
                {
                    "tool_call_id": call.get("id"),
                    "tool": call.get("tool") or "",
                    "path": path,
                    "category": category,
                    "status": call.get("status") or "",
                    "approval_status": call.get("approval_status") or "",
                    "dry_run": bool(result.get("dry_run")),
                    "written": bool(result.get("written")),
                }
            )
    return records


def _safety_blocked_records(session):
    records = []
    for note in (session or {}).get("notes") or []:
        if not isinstance(note, dict):
            continue
        text = note.get("text") or ""
        if "M5 safety blocked tool execution" not in text:
            continue
        records.append(
            {
                "created_at": note.get("created_at") or "",
                "source": note.get("source") or "",
                "text": text,
            }
        )
    return records


def _budget_exhaustion_records(session):
    records = []
    for note in (session or {}).get("notes") or []:
        if not isinstance(note, dict):
            continue
        text = note.get("text") or ""
        if not text.startswith(("Follow reached max_steps=", "Live run reached max_steps=")):
            continue
        records.append(
            {
                "created_at": note.get("created_at") or "",
                "source": note.get("source") or "",
                "text": text,
            }
        )
    return records


def _ambiguous_recovery_records(session):
    records = []
    for call in (session or {}).get("tool_calls") or []:
        if not isinstance(call, dict):
            continue
        result = call.get("result") or {}
        recovery_status = call.get("recovery_status") or ""
        approval_status = call.get("approval_status") or ""
        ambiguous = False
        reason = ""
        if call.get("status") == "interrupted" and not recovery_status:
            ambiguous = True
            reason = "interrupted_without_recovery"
        elif recovery_status in {"retry_failed", "rollback_failed"}:
            ambiguous = True
            reason = recovery_status
        elif result.get("rollback_error"):
            ambiguous = True
            reason = "rollback_error"
        elif approval_status == "indeterminate":
            ambiguous = True
            reason = "approval_indeterminate"
        if not ambiguous:
            continue
        records.append(
            {
                "tool_call_id": call.get("id"),
                "tool": call.get("tool") or "",
                "status": call.get("status") or "",
                "recovery_status": recovery_status,
                "approval_status": approval_status,
                "reason": reason,
            }
        )
    return records


def build_m5_safety_boundary_report(session, permission_context, effect_budget):
    permission_context = permission_context or {}
    effect_budget = effect_budget or {}
    governance_edits = _governance_or_policy_edit_records(session or {})
    external_side_effects = _external_visible_side_effect_records(session or {})
    blocked_events = _safety_blocked_records(session or {})
    budget_events = _budget_exhaustion_records(session or {})
    ambiguous_recovery_events = _ambiguous_recovery_records(session or {})
    permission_drift = bool(permission_context.get("drift"))
    findings = []
    status = "ok"
    if permission_drift:
        status = "needs_review"
        findings.append("permission_context_drift")
    if governance_edits:
        status = "needs_review"
        findings.append("governance_or_policy_edit")
    if external_side_effects:
        status = "blocked"
        findings.append("external_visible_side_effect")
    if blocked_events:
        status = "blocked"
        findings.append("safety_blocked_event")
    if budget_events:
        status = "needs_review" if status == "ok" else status
        findings.append("budget_exhaustion_event")
    if ambiguous_recovery_events:
        status = "blocked"
        findings.append("ambiguous_recovery_event")
    if (effect_budget.get("budget_exhaustion_action") or "") != "stop_and_report":
        status = "needs_review" if status == "ok" else status
        findings.append("budget_exhaustion_not_stop_and_report")
    if (effect_budget.get("ambiguous_recovery_action") or "") != "stop_and_ask":
        status = "needs_review" if status == "ok" else status
        findings.append("ambiguous_recovery_not_stop_and_ask")
    return {
        "status": status,
        "permission_context_drift": permission_drift,
        "governance_or_policy_edits": governance_edits,
        "external_visible_side_effects": external_side_effects,
        "blocked_events": blocked_events,
        "budget_events": budget_events,
        "ambiguous_recovery_events": ambiguous_recovery_events,
        "budget_exhaustion_action": effect_budget.get("budget_exhaustion_action") or "",
        "ambiguous_recovery_action": effect_budget.get("ambiguous_recovery_action") or "",
        "findings": findings,
    }


def m5_self_improve_auto_approval_blocker(task, source_call):
    if not is_self_improve_task_record(task):
        return ""
    single_call_session = {"tool_calls": [source_call] if source_call else []}
    external_side_effects = _external_visible_side_effect_records(single_call_session)
    if external_side_effects:
        marker = external_side_effects[0].get("marker") or "external-visible side effect"
        return (
            "M5 safety boundary blocks automatic approval of external-visible "
            f"side-effect command ({marker}); require explicit human approval"
        )
    governance_edits = _governance_or_policy_edit_records(single_call_session)
    if governance_edits:
        first = governance_edits[0]
        return (
            "M5 safety boundary blocks automatic approval of governance/policy "
            f"edit ({first.get('category')} {first.get('path')}); require explicit human approval"
        )
    return ""


def m5_self_improve_tool_execution_blocker(task, action_type, parameters):
    if not is_self_improve_task_record(task):
        return ""
    if action_type not in {"run_command", "run_tests"}:
        return ""
    single_call_session = {
        "tool_calls": [
            {
                "tool": action_type,
                "parameters": parameters or {},
                "result": {},
            }
        ]
    }
    external_side_effects = _external_visible_side_effect_records(single_call_session)
    if not external_side_effects:
        return ""
    marker = external_side_effects[0].get("marker") or "external-visible side effect"
    return (
        "M5 safety boundary blocks self-improvement command before execution "
        f"because it appears externally visible ({marker})"
    )


def classify_human_intervention(session):
    notes = session.get("notes") or []
    human_notes = [
        note for note in notes
        if isinstance(note, dict) and (note.get("source") or "").strip().casefold() in {"human", "user"}
    ]
    human_texts = [(note.get("text") or "").casefold() for note in human_notes]
    approvals = _tool_approval_records(session)
    rescue_recorded = any(
        marker in text
        for text in human_texts
        for marker in RESCUE_INTERVENTION_MARKERS
    )
    no_rescue_review_recorded = any(
        marker in text
        for text in human_texts
        for marker in NO_RESCUE_REVIEW_MARKERS
    )
    if human_notes:
        classification = "human_guidance_recorded"
    elif approvals:
        classification = "approval_or_rejection_recorded"
    else:
        classification = "none_recorded"
    if rescue_recorded:
        no_rescue_review_status = "rescue_recorded"
        m5_credit = "not_counted_due_to_rescue"
    elif no_rescue_review_recorded:
        no_rescue_review_status = "no_rescue_review_recorded"
        m5_credit = M5_CANDIDATE_CREDIT_STATUS
    else:
        no_rescue_review_status = "pending_human_review"
        m5_credit = "not_counted_until_human_review_confirms_no_rescue_edits"
    return {
        "classification": classification,
        "human_note_count": len(human_notes),
        "approval_record_count": len(approvals),
        "rescue_edit_status": "rescue_recorded" if rescue_recorded else "not_assessed",
        "no_rescue_review_status": no_rescue_review_status,
        "m5_credit": m5_credit,
    }


def build_m5_self_improve_audit_bundle(state, task_ref=None):
    task = select_self_improve_audit_task(state, task_ref)
    if not task:
        return {
            "schema_version": M5_AUDIT_SCHEMA_VERSION,
            "status": "missing_task",
            "task_ref": task_ref or "latest",
        }
    sessions = work_sessions_for_task(state, task.get("id"))
    session = sessions[-1] if sessions else None
    if session:
        seed_m5_self_improve_audit(session, task)
    combined_session = combined_audit_session(sessions)
    audit = (session or {}).get("m5_self_improve_audit") or {}
    defaults = (session or {}).get("default_options") or {}
    permission_context = self_improve_permission_context(defaults)
    permission_report = {
        "frozen": audit.get("frozen_permission_context") or permission_context,
        "current": permission_context,
        "drift": bool(audit.get("permission_context_drift")),
    }
    effect_budget = audit.get("effect_budget") or self_improve_effect_budget(defaults)
    verification_records = _verification_records(state, task, combined_session)
    latest_verification = verification_records[-1] if verification_records else None
    human_intervention = classify_human_intervention(combined_session)
    safety_boundaries = build_m5_safety_boundary_report(
        combined_session,
        permission_report,
        effect_budget,
    )
    bundle = {
        "schema_version": M5_AUDIT_SCHEMA_VERSION,
        "status": "ready" if session else "missing_session",
        "task": {
            "id": task.get("id"),
            "title": task.get("title"),
            "status": task.get("status"),
            "priority": task.get("priority"),
            "cwd": task.get("cwd") or ".",
        },
        "work_session": {
            "id": (session or {}).get("id"),
            "status": (session or {}).get("status"),
            "created_at": (session or {}).get("created_at"),
            "updated_at": (session or {}).get("updated_at"),
        },
        "work_sessions": [
            {
                "id": item.get("id"),
                "status": item.get("status"),
                "created_at": item.get("created_at"),
                "updated_at": item.get("updated_at"),
            }
            for item in sessions
        ],
        "product_rationale": task.get("description") or task.get("title") or "",
        "permission_context": permission_report,
        "effect_budget": effect_budget,
        "safety_boundaries": safety_boundaries,
        "human_intervention": human_intervention,
        "approvals": _tool_approval_records(combined_session),
        "recovery_events": _recovery_records(combined_session),
        "verification": {
            "verify_command": defaults.get("verify_command") or "",
            "allow_verify": bool(defaults.get("allow_verify")),
            "status": (latest_verification or {}).get("status") or "not_recorded",
            "latest": latest_verification,
            "records": verification_records,
        },
        "loop_credit_status": human_intervention.get("m5_credit") or audit.get("loop_credit_status") or "not_counted",
        "controls": self_improve_audit_controls(task),
    }
    return bundle


def _audit_sequence_entry(bundle):
    task = bundle.get("task") or {}
    session = bundle.get("work_session") or {}
    intervention = bundle.get("human_intervention") or {}
    verification = bundle.get("verification") or {}
    recovery_events = bundle.get("recovery_events") or []
    return {
        "task_id": task.get("id"),
        "task_status": task.get("status"),
        "work_session_id": session.get("id"),
        "work_session_status": session.get("status"),
        "verification_status": verification.get("status"),
        "recovery_event_count": len(recovery_events),
        "has_recovery_events": bool(recovery_events),
        "rescue_edit_status": intervention.get("rescue_edit_status"),
        "no_rescue_review_status": intervention.get("no_rescue_review_status"),
        "m5_credit": intervention.get("m5_credit"),
        "loop_credit_status": bundle.get("loop_credit_status"),
    }


def _consecutive_ints(values):
    if not values:
        return False
    if any(not isinstance(value, int) for value in values):
        return False
    return values == list(range(values[0], values[0] + len(values)))


def build_m5_self_improve_audit_sequence(state, task_refs):
    task_refs = [str(ref) for ref in (task_refs or [])]
    bundles = [build_m5_self_improve_audit_bundle(state, ref) for ref in task_refs]
    entries = [_audit_sequence_entry(bundle) for bundle in bundles]
    task_ids = [entry.get("task_id") for entry in entries]
    checks = {
        "all_found": bool(entries) and all(bundle.get("status") == "ready" for bundle in bundles),
        "consecutive_task_ids": _consecutive_ints(task_ids),
        "all_tasks_done": bool(entries) and all(entry.get("task_status") == "done" for entry in entries),
        "all_sessions_closed": bool(entries) and all(entry.get("work_session_status") == "closed" for entry in entries),
        "all_verification_passed": bool(entries) and all(entry.get("verification_status") == "passed" for entry in entries),
        "any_recovery_events": any(entry.get("has_recovery_events") for entry in entries),
        "all_no_rescue_reviewed": bool(entries)
        and all(entry.get("no_rescue_review_status") == "no_rescue_review_recorded" for entry in entries),
        "all_candidate_credit": bool(entries)
        and all(
            entry.get("m5_credit") == M5_CANDIDATE_CREDIT_STATUS
            and entry.get("loop_credit_status") == M5_CANDIDATE_CREDIT_STATUS
            for entry in entries
        ),
    }
    ready = all(checks.values())
    return {
        "schema_version": M5_AUDIT_SCHEMA_VERSION,
        "status": "candidate_sequence_ready" if ready else "needs_review",
        "task_refs": task_refs,
        "count": len(entries),
        "checks": checks,
        "entries": entries,
        "controls": self_improve_audit_sequence_controls(task_refs),
    }


def format_m5_self_improve_audit_bundle(bundle):
    task = bundle.get("task") or {}
    session = bundle.get("work_session") or {}
    permission = bundle.get("permission_context") or {}
    current = permission.get("current") or {}
    budget = bundle.get("effect_budget") or {}
    safety = bundle.get("safety_boundaries") or {}
    intervention = bundle.get("human_intervention") or {}
    verification = bundle.get("verification") or {}
    latest_verification = verification.get("latest") or {}
    lines = [
        "M5 self-improve audit",
        f"status: {bundle.get('status')}",
    ]
    if bundle.get("status") == "missing_task":
        lines.append(f"task_ref: {bundle.get('task_ref')}")
        return "\n".join(lines)
    lines.extend(
        [
            f"task: #{task.get('id')} {task.get('title')} [{task.get('status')}]",
            f"work_session: #{session.get('id')} [{session.get('status')}]",
            (
                "permission: "
                f"read={current.get('allow_read')} "
                f"write={current.get('allow_write')} "
                f"verify={current.get('allow_verify')} "
                f"approval={current.get('approval_mode')} "
                f"drift={permission.get('drift')}"
            ),
            (
                "budget: "
                f"continue_steps={budget.get('continue_max_steps')} "
                f"follow_steps={budget.get('follow_max_steps')} "
                f"exhaustion={budget.get('budget_exhaustion_action')}"
            ),
            (
                "safety_boundaries: "
                f"{safety.get('status')} "
                f"findings={len(safety.get('findings') or [])} "
                f"governance_edits={len(safety.get('governance_or_policy_edits') or [])} "
                f"external_side_effects={len(safety.get('external_visible_side_effects') or [])} "
                f"blocked_events={len(safety.get('blocked_events') or [])} "
                f"budget_events={len(safety.get('budget_events') or [])} "
                f"ambiguous_recovery={len(safety.get('ambiguous_recovery_events') or [])}"
            ),
            (
                "human_intervention: "
                f"{intervention.get('classification')} "
                f"rescue={intervention.get('rescue_edit_status')} "
                f"no_rescue_review={intervention.get('no_rescue_review_status')} "
                f"credit={intervention.get('m5_credit')}"
            ),
            (
                "verification: "
                f"{verification.get('status')} "
                f"exit_code={latest_verification.get('exit_code')}"
            ),
            f"loop_credit_status: {bundle.get('loop_credit_status')}",
        ]
    )
    controls = bundle.get("controls") or {}
    if controls.get("audit_json"):
        lines.append(f"audit_json: {controls['audit_json']}")
    return "\n".join(lines)


def format_m5_self_improve_audit_sequence(sequence):
    checks = sequence.get("checks") or {}
    lines = [
        "M5 self-improve audit sequence",
        f"status: {sequence.get('status')}",
        f"count: {sequence.get('count')}",
        (
            "checks: "
            f"found={checks.get('all_found')} "
            f"consecutive={checks.get('consecutive_task_ids')} "
            f"done={checks.get('all_tasks_done')} "
            f"closed={checks.get('all_sessions_closed')} "
            f"verification={checks.get('all_verification_passed')} "
            f"recovery={checks.get('any_recovery_events')} "
            f"no_rescue_review={checks.get('all_no_rescue_reviewed')} "
            f"candidate_credit={checks.get('all_candidate_credit')}"
        ),
    ]
    for entry in sequence.get("entries") or []:
        lines.append(
            (
                f"- #{entry.get('task_id')} task={entry.get('task_status')} "
                f"session=#{entry.get('work_session_id')}[{entry.get('work_session_status')}] "
                f"verification={entry.get('verification_status')} "
                f"recovery_events={entry.get('recovery_event_count')} "
                f"no_rescue_review={entry.get('no_rescue_review_status')} "
                f"credit={entry.get('loop_credit_status')}"
            )
        )
    controls = sequence.get("controls") or {}
    if controls.get("audit_sequence_json"):
        lines.append(f"audit_sequence_json: {controls['audit_sequence_json']}")
    return "\n".join(lines)
