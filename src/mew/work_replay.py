import json
from copy import deepcopy
from pathlib import Path
import subprocess

from .errors import CodexRefusalError, ModelBackendError, ModelRefusalError
from .patch_draft import PATCH_BLOCKER_RECOVERY_ACTIONS
from .timeutil import now_date_iso, now_iso, parse_time
from .work_session import WORK_TODO_PHASE_STATUSES, build_work_session_resume


REPLAYS_ROOT = Path(".mew/replays/work-loop")
NATIVE_PATCH_DRAFT_BLOCKER_CODES = frozenset(PATCH_BLOCKER_RECOVERY_ACTIONS.keys())
PATCH_DRAFT_COMPILER_PASSTHROUGH_NON_NATIVE_EXCLUSION_REASON = (
    "model-authored patch_blocker code outside native patch_draft vocabulary"
)


def _is_calibration_measured_patch_draft_task(task):
    task = task or {}
    text = " ".join(
        str(task.get(field) or "").strip().lower()
        for field in ("title", "description", "notes")
        if task.get(field) is not None
    ).strip()
    if not text:
        return False
    has_sample_marker = "sample" in text
    has_current_head_marker = any(
        marker in text
        for marker in (
            "current-head",
            "current head",
            "current_head",
        )
    )
    has_patch_draft_marker = any(
        marker in text
        for marker in ("patchdraft", "patch draft", "patch_draft")
    )
    has_measurement_contract_marker = any(
        marker in text
        for marker in (
            "replay bundle",
            "get one live replay result",
            "count the sample only if",
            "calibration ledger row",
            "counted replay bundle",
            "exact non-counted conclusion",
            "do not finish from a passing verifier alone",
        )
    )
    return (
        has_sample_marker
        and has_current_head_marker
        and has_patch_draft_marker
        and has_measurement_contract_marker
    )


def _is_draft_related_failure(session, model_turn, task=None):
    if not session or not isinstance(model_turn, dict):
        return False
    model_metrics = model_turn.get("model_metrics") or {}
    if bool(model_metrics.get("write_ready_fast_path")):
        return True
    active_work_todo = session.get("active_work_todo") or {}
    todo_status = str(active_work_todo.get("status") or "").strip()
    if todo_status in WORK_TODO_PHASE_STATUSES:
        return True
    if todo_status != "queued":
        return False
    source = active_work_todo.get("source") or {}
    target_paths = source.get("target_paths") or []
    has_target_paths = isinstance(target_paths, (list, tuple)) and any(
        isinstance(path, str) and path.strip() for path in target_paths
    )
    failure_reason = str(model_metrics.get("write_ready_fast_path_reason") or "").strip()
    if failure_reason == "first_plan_item_not_edit_ready":
        return has_target_paths
    if failure_reason == "missing_plan_item_observations":
        return has_target_paths and _is_calibration_measured_patch_draft_task(task)
    if failure_reason in {
        "insufficient_cached_window_context",
        "missing_exact_cached_window_texts",
    }:
        return has_target_paths and _is_calibration_measured_patch_draft_task(task)
    return False


def _task_id_for_report(session, task):
    if session is not None and session.get("task_id") is not None:
        return session.get("task_id")
    if task and task.get("id") is not None:
        return task.get("id")
    return None


def _date_bucket_from_model_turn(model_turn):
    finished_at = model_turn.get("finished_at")
    started_at = model_turn.get("started_at")
    for value in (finished_at, started_at):
        parsed = parse_time(value)
        if parsed:
            return parsed.date().isoformat()
    return now_date_iso()


def _safe_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _current_git_head():
    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
        if head.returncode == 0:
            return (head.stdout or "").strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return ""


def _build_bucket_tag(*parts):
    labels = [
        f"{key}={str(value).strip()}"
        for key, value in parts
        if str(value).strip()
    ]
    return "/".join(labels)


def _derive_model_failure_bucket_tag(model_metrics):
    contract = str(model_metrics.get("draft_prompt_contract_version") or "").strip()
    tiny_contract = str(
        model_metrics.get("tiny_write_ready_draft_prompt_contract_version") or ""
    ).strip()
    exit_stage = str(model_metrics.get("tiny_write_ready_draft_exit_stage") or "").strip()
    return _build_bucket_tag(
        ("contract", contract),
        ("tiny", tiny_contract),
        ("exit", exit_stage),
    )


def _derive_model_failure_blocker_code(model_metrics):
    fallback_reason = str(
        model_metrics.get("tiny_write_ready_draft_fallback_reason") or ""
    ).strip()
    artifact_kind = str(
        model_metrics.get("patch_draft_compiler_artifact_kind") or ""
    ).strip()
    if fallback_reason:
        return fallback_reason
    return artifact_kind


def _derive_compiler_bucket_tag(validator_result, todo):
    validator_code = str((validator_result or {}).get("code") or "").strip()
    contract = str((todo or {}).get("draft_prompt_contract_version") or "").strip()
    tiny_contract = str(
        (todo or {}).get("tiny_write_ready_draft_prompt_contract_version") or ""
    ).strip()
    return _build_bucket_tag(
        ("code", validator_code),
        ("contract", contract),
        ("tiny", tiny_contract),
    )


def _derive_compiler_blocker_code(validator_code):
    code = str(validator_code or "").strip()
    if code in {"", "patch_valid", "patch_adapted"}:
        return ""
    return code


def _is_model_authored_non_native_patch_blocker_pass_through(proposal, validator_result):
    proposal_kind = str((proposal or {}).get("kind") or "").strip()
    validator_kind = str((validator_result or {}).get("kind") or "").strip()
    proposal_code = str((proposal or {}).get("code") or "").strip()
    validator_code = str((validator_result or {}).get("code") or "").strip()
    if proposal_kind != "patch_blocker":
        return False
    if validator_kind != "patch_blocker":
        return False
    if proposal_code != validator_code:
        return False
    return validator_code not in NATIVE_PATCH_DRAFT_BLOCKER_CODES


def _sanitize_replay_path_component(value):
    sanitized = str(value if value is not None else "").strip()
    sanitized = sanitized.replace("/", "-").replace("\\", "-")
    return sanitized


def _next_attempt(base_dir: Path):
    if not base_dir.exists():
        return 1
    max_attempt = 0
    for attempt_dir in base_dir.glob("attempt-*"):
        if not attempt_dir.is_dir():
            continue
        _, sep, suffix = attempt_dir.name.partition("attempt-")
        if sep != "attempt-":
            continue
        attempt = _safe_int(suffix)
        if attempt is None:
            continue
        if attempt > max_attempt:
            max_attempt = attempt
    return max_attempt + 1


def _failure_profile(exc, model_turn):
    message = str(exc or "").strip()
    if isinstance(exc, (ModelRefusalError, CodexRefusalError)):
        return {
            "kind": "refusal",
            "code": "model_refused",
            "summary": message or "model refused",
        }
    if isinstance(exc, ModelBackendError) and "timed out" in message.lower():
        return {
            "kind": "timeout",
            "code": "request_timed_out",
            "summary": message or "request timed out",
        }
    if "timed out" in message.lower():
        return {
            "kind": "timeout",
            "code": "request_timed_out",
            "summary": message or "request timed out",
        }

    return {
        "kind": "generic",
        "code": "model_failure",
        "summary": message or str(model_turn.get("summary") or model_turn.get("error") or "failed"),
    }


def _todo_dir_name(session):
    session_id = session.get("id")
    session_id = "" if session_id is None else str(session_id)
    active_work_todo = session.get("active_work_todo") or {}
    todo_id = str(active_work_todo.get("id") or "").strip()
    if todo_id:
        return todo_id
    return f"no-todo-{session_id}"


def _build_resume_context(session, task):
    resume = build_work_session_resume(session, task=task)
    return {
        "phase": resume.get("phase"),
        "draft_phase": resume.get("draft_phase"),
        "draft_attempts": resume.get("draft_attempts", 0),
        "cached_window_ref_count": resume.get("cached_window_ref_count", 0),
        "cached_window_hashes": resume.get("cached_window_hashes") or [],
        "draft_runtime_mode": resume.get("draft_runtime_mode") or "",
        "draft_prompt_contract_version": resume.get("draft_prompt_contract_version") or "",
        "draft_prompt_static_chars": resume.get("draft_prompt_static_chars"),
        "draft_prompt_dynamic_chars": resume.get("draft_prompt_dynamic_chars"),
        "draft_retry_same_prefix": bool(resume.get("draft_retry_same_prefix")),
        "active_work_todo": resume.get("active_work_todo") or {},
        "plan_item_observations": resume.get("plan_item_observations") or [],
        "skipped_exact_read_plan_items": resume.get("skipped_exact_read_plan_items") or [],
    }


def write_work_model_failure_replay(*, session, model_turn, exc, task=None):
    if not isinstance(session, dict) or not isinstance(model_turn, dict):
        return None

    if not _is_draft_related_failure(session, model_turn, task=task):
        return None

    session_id = session.get("id")
    if session_id is None:
        return None

    turn_id = _safe_int(model_turn.get("id"))
    if turn_id is None:
        return None

    date_bucket = _date_bucket_from_model_turn(model_turn)
    todo_dir = _todo_dir_name(session)
    base = REPLAYS_ROOT / date_bucket / f"session-{session_id}" / f"todo-{todo_dir}" / f"turn-{turn_id}"
    attempt = _next_attempt(base)
    report_path = base / f"attempt-{attempt}" / "report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)

    session_copy = deepcopy(session)
    resume_context = _build_resume_context(session_copy, task=task)
    model_metrics = model_turn.get("model_metrics") or {}
    failure = _failure_profile(exc, model_turn=model_turn)

    report = {
        "schema_version": 1,
        "bundle": "work-loop-model-failure",
        "calibration_counted": True,
        "calibration_exclusion_reason": "",
        "session_id": session_id,
        "task_id": _task_id_for_report(session, task),
        "model_turn_id": turn_id,
        "date_bucket": date_bucket,
        "captured_at": now_iso(),
        "attempt": attempt,
        "failure": {
            "kind": failure["kind"],
            "code": failure["code"],
            "summary": failure["summary"],
        },
        "git_head": _current_git_head(),
        "bucket_tag": _derive_model_failure_bucket_tag(model_metrics),
        "error": {
            "text": str(exc),
            "summary": model_turn.get("summary") or model_turn.get("error") or failure["summary"],
        },
        "blocker_code": _derive_model_failure_blocker_code(model_metrics),
        "active_work_todo": resume_context.get("active_work_todo") or session.get("active_work_todo") or {},
        "model_metrics": dict(model_metrics),
        "draft_metrics": {
            "draft_phase": resume_context.get("draft_phase"),
            "draft_attempts": resume_context.get("draft_attempts", 0),
            "cached_window_ref_count": resume_context.get("cached_window_ref_count", 0),
            "cached_window_hashes": resume_context.get("cached_window_hashes") or [],
            "draft_runtime_mode": resume_context.get("draft_runtime_mode"),
            "draft_prompt_contract_version": resume_context.get("draft_prompt_contract_version"),
            "draft_prompt_static_chars": resume_context.get("draft_prompt_static_chars"),
            "draft_prompt_dynamic_chars": resume_context.get("draft_prompt_dynamic_chars"),
            "draft_retry_same_prefix": resume_context.get("draft_retry_same_prefix"),
        },
        "resume_context": {
            "phase": resume_context.get("phase"),
            "plan_item_observations": resume_context.get("plan_item_observations"),
            "skipped_exact_read_plan_items": resume_context.get("skipped_exact_read_plan_items"),
        },
    }

    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return str(report_path)


def write_patch_draft_compiler_replay(
    *,
    session_id,
    todo_id,
    todo,
    proposal,
    cached_windows,
    live_files,
    allowed_write_roots,
    validator_result,
):
    if not isinstance(todo, dict):
        return None
    if not isinstance(proposal, dict):
        return None
    if not isinstance(cached_windows, dict):
        return None
    if not isinstance(live_files, dict):
        return None
    if not isinstance(validator_result, dict):
        return None
    if not isinstance(allowed_write_roots, (list, tuple)):
        return None

    normalized_session_id = _sanitize_replay_path_component(session_id)
    normalized_todo_id = _sanitize_replay_path_component(todo_id)
    if not normalized_session_id or not normalized_todo_id:
        return None

    date_bucket = now_date_iso()
    base = REPLAYS_ROOT / date_bucket / f"session-{normalized_session_id}" / f"todo-{normalized_todo_id}"
    attempt = _next_attempt(base)
    attempt_dir = base / f"attempt-{attempt}"
    attempt_dir.mkdir(parents=True, exist_ok=True)
    captured_at = now_iso()

    payloads = {
        "todo": todo,
        "proposal": proposal,
        "cached_windows": cached_windows,
        "live_files": live_files,
        "allowed_write_roots": list(allowed_write_roots),
        "validator_result": validator_result,
    }

    for filename, payload in (
        ("todo.json", payloads["todo"]),
        ("proposal.json", payloads["proposal"]),
        ("cached_windows.json", payloads["cached_windows"]),
        ("live_files.json", payloads["live_files"]),
        ("allowed_write_roots.json", payloads["allowed_write_roots"]),
        ("validator_result.json", payloads["validator_result"]),
    ):
        (attempt_dir / filename).write_text(
            json.dumps(payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    is_non_native_patch_blocker_pass_through = (
        _is_model_authored_non_native_patch_blocker_pass_through(
            proposal=payloads["proposal"],
            validator_result=payloads["validator_result"],
        )
    )
    calibration_counted = not is_non_native_patch_blocker_pass_through
    calibration_exclusion_reason = (
        PATCH_DRAFT_COMPILER_PASSTHROUGH_NON_NATIVE_EXCLUSION_REASON
        if not calibration_counted
        else ""
    )

    metadata = {
        "schema_version": 1,
        "bundle": "patch_draft_compiler",
        "calibration_counted": calibration_counted,
        "calibration_exclusion_reason": calibration_exclusion_reason,
        "git_head": _current_git_head(),
        "bucket_tag": _derive_compiler_bucket_tag(validator_result, todo),
        "session_id": normalized_session_id,
        "todo_id": normalized_todo_id,
        "blocker_code": _derive_compiler_blocker_code(
            validator_result.get("code"),
        ),
        "attempt": attempt,
        "captured_at": captured_at,
        "files": {
            "todo": "todo.json",
            "proposal": "proposal.json",
            "cached_windows": "cached_windows.json",
            "live_files": "live_files.json",
            "allowed_write_roots": "allowed_write_roots.json",
            "validator_result": "validator_result.json",
        },
    }
    metadata_path = attempt_dir / "replay_metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")
    return str(metadata_path)


def mark_patch_draft_compiler_replay_non_counted(metadata_path, reason=""):
    if not metadata_path:
        return False
    path = Path(metadata_path)
    if not path.is_file():
        return False
    try:
        metadata_text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    try:
        metadata = json.loads(metadata_text) if metadata_text.strip() else None
    except json.JSONDecodeError:
        return False
    if not isinstance(metadata, dict):
        return False
    metadata["calibration_counted"] = False
    metadata["calibration_exclusion_reason"] = str(reason or "")
    try:
        path.write_text(
            json.dumps(metadata, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    except OSError:
        return False
    return True
