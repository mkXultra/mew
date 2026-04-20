from .cli_command import mew_command
from .self_improve import DEFAULT_SELF_IMPROVE_TITLE
from .tasks import find_task
from .timeutil import now_iso


M5_AUDIT_SCHEMA_VERSION = 1


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


def self_improve_audit_controls(task):
    task_id = task.get("id")
    return {
        "audit": mew_command("self-improve", "--audit", task_id),
        "audit_json": mew_command("self-improve", "--audit", task_id, "--json"),
    }


def _tool_approval_records(session):
    records = []
    for call in session.get("tool_calls") or []:
        if not isinstance(call, dict):
            continue
        approval = call.get("approval_status")
        if approval or (call.get("result") or {}).get("dry_run"):
            records.append(
                {
                    "id": call.get("id"),
                    "tool": call.get("tool"),
                    "status": call.get("status"),
                    "approval_status": approval or "",
                    "dry_run": bool((call.get("result") or {}).get("dry_run")),
                }
            )
    return records


def _recovery_records(session):
    records = []
    for call in session.get("tool_calls") or []:
        if not isinstance(call, dict):
            continue
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
    return records


def classify_human_intervention(session):
    notes = session.get("notes") or []
    human_notes = [
        note for note in notes
        if isinstance(note, dict) and (note.get("source") or "").strip().casefold() in {"human", "user"}
    ]
    approvals = _tool_approval_records(session)
    if human_notes:
        classification = "human_guidance_recorded"
    elif approvals:
        classification = "approval_or_rejection_recorded"
    else:
        classification = "none_recorded"
    return {
        "classification": classification,
        "human_note_count": len(human_notes),
        "approval_record_count": len(approvals),
        "rescue_edit_status": "not_assessed",
        "m5_credit": "not_counted_until_human_review_confirms_no_rescue_edits",
    }


def build_m5_self_improve_audit_bundle(state, task_ref=None):
    task = select_self_improve_audit_task(state, task_ref)
    if not task:
        return {
            "schema_version": M5_AUDIT_SCHEMA_VERSION,
            "status": "missing_task",
            "task_ref": task_ref or "latest",
        }
    session = latest_session_for_task(state, task.get("id"))
    if session:
        seed_m5_self_improve_audit(session, task)
    audit = (session or {}).get("m5_self_improve_audit") or {}
    defaults = (session or {}).get("default_options") or {}
    permission_context = self_improve_permission_context(defaults)
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
        "product_rationale": task.get("description") or task.get("title") or "",
        "permission_context": {
            "frozen": audit.get("frozen_permission_context") or permission_context,
            "current": permission_context,
            "drift": bool(audit.get("permission_context_drift")),
        },
        "effect_budget": audit.get("effect_budget") or self_improve_effect_budget(defaults),
        "human_intervention": classify_human_intervention(session or {}),
        "approvals": _tool_approval_records(session or {}),
        "recovery_events": _recovery_records(session or {}),
        "verification": {
            "verify_command": defaults.get("verify_command") or "",
            "allow_verify": bool(defaults.get("allow_verify")),
        },
        "loop_credit_status": audit.get("loop_credit_status") or "not_counted",
        "controls": self_improve_audit_controls(task),
    }
    return bundle


def format_m5_self_improve_audit_bundle(bundle):
    task = bundle.get("task") or {}
    session = bundle.get("work_session") or {}
    permission = bundle.get("permission_context") or {}
    current = permission.get("current") or {}
    budget = bundle.get("effect_budget") or {}
    intervention = bundle.get("human_intervention") or {}
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
                "human_intervention: "
                f"{intervention.get('classification')} "
                f"rescue={intervention.get('rescue_edit_status')} "
                f"credit={intervention.get('m5_credit')}"
            ),
            f"loop_credit_status: {bundle.get('loop_credit_status')}",
        ]
    )
    controls = bundle.get("controls") or {}
    if controls.get("audit_json"):
        lines.append(f"audit_json: {controls['audit_json']}")
    return "\n".join(lines)
