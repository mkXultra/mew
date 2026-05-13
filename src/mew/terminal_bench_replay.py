import json
import re
from pathlib import Path

from .implement_lane.execution_evidence import (
    classify_execution_failure,
    derive_verifier_evidence,
    normalize_execution_contract,
)
from .implement_lane.native_transcript import (
    CALL_ITEM_KINDS,
    IMPLEMENT_V2_NATIVE_RUNTIME_ID,
    OUTPUT_ITEM_KINDS,
    NativeTranscript,
    NativeTranscriptItem,
    native_transcript_hash,
    validate_native_transcript_pairing,
)
from .implement_lane.types import ToolResultEnvelope
from .implement_lane.v2_runtime import _frontier_evidence_registry, _source_output_contract_from_tool_results
from .timeutil import now_iso
from .work_session import build_work_session_resume


_IMPLEMENT_V2_TERMINAL_TOOLS = {"run_command", "run_tests", "poll_command"}
_IMPLEMENT_V2_WRITE_TOOLS = {"write_file", "edit_file", "apply_patch"}
_FAILURE_CLASSIFICATION_COMPARE_KEYS = (
    "schema_version",
    "classification_id",
    "phase",
    "kind",
    "class",
    "secondary_classes",
    "secondary_kinds",
    "confidence",
    "retryable",
    "summary",
    "evidence_refs",
    "required_next_probe",
)
_FAILURE_CLASSIFICATION_DEFAULTS = {
    "schema_version": 1,
    "classification_id": "",
    "phase": "unknown",
    "kind": "unknown_failure",
    "class": "unknown_failure",
    "secondary_classes": [],
    "secondary_kinds": [],
    "confidence": "low",
    "retryable": True,
    "summary": "",
    "evidence_refs": [],
    "required_next_probe": "",
}
_TMP_PATH_RE = re.compile(r"(/tmp/[A-Za-z0-9_./@+-]+)")
_EXTERNAL_EXPECTED_PATH_MARKERS = (
    "filenotfounderror",
    "no such file",
    "does not exist",
    "not found",
    "expected",
    "assertionerror",
    "failed",
)


def _read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {} if default is None else default


def _read_text(path):
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _find_parent_with_result(path):
    current = Path(path).resolve(strict=False)
    if current.is_file():
        current = current.parent
    for candidate in [current, *current.parents]:
        result_path = candidate / "result.json"
        if result_path.is_file():
            return candidate
    return current


def _trial_name_from_result(result, trial_dir):
    return (
        str(result.get("trial_name") or "")
        or str((result.get("task_id") or {}).get("name") or "")
        or Path(trial_dir).name
    )


def _safe_float(value):
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _reward_from_trial(trial_dir, trial_result):
    verifier_result = trial_result.get("verifier_result") if isinstance(trial_result, dict) else {}
    reward = None
    if isinstance(verifier_result, dict):
        reward = verifier_result.get("reward")
        if reward is None:
            reward = verifier_result.get("score")
    if reward is None and isinstance(trial_result, dict):
        reward = trial_result.get("reward")
    if reward is None:
        reward_text = _read_text(Path(trial_dir) / "verifier" / "reward.txt").strip()
        if reward_text:
            reward = reward_text
    return _safe_float(reward)


def _root_stats(job_dir):
    root_result = _read_json(Path(job_dir) / "result.json")
    stats = root_result.get("stats") if isinstance(root_result, dict) else {}
    return stats if isinstance(stats, dict) else {}


def _resume_candidates(report):
    candidates = []
    if not isinstance(report, dict):
        return candidates
    for key in ("resume", "work_session_resume"):
        value = report.get(key)
        if isinstance(value, dict):
            candidates.append(value)
    for key in ("work_report", "work_session"):
        value = report.get(key)
        if isinstance(value, dict) and isinstance(value.get("resume"), dict):
            candidates.append(value["resume"])
    return candidates


def _primary_resume(report):
    candidates = _resume_candidates(report)
    return candidates[0] if candidates else {}


def _tool_calls_from_work_report(report):
    steps = ((report.get("work_report") or {}).get("steps") or []) if isinstance(report, dict) else []
    calls = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        call = step.get("tool_call")
        if isinstance(call, dict):
            calls.append(dict(call))
    return calls


def _model_turns_from_work_report(report):
    steps = ((report.get("work_report") or {}).get("steps") or []) if isinstance(report, dict) else []
    turns = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        turn = step.get("model_turn")
        if isinstance(turn, dict):
            turns.append(dict(turn))
    return turns


def _raw_action_from_model_turn(turn):
    if not isinstance(turn, dict):
        return {}
    for key in ("action_plan", "decision_plan"):
        plan = turn.get(key)
        if isinstance(plan, dict) and isinstance(plan.get("action"), dict):
            return dict(plan["action"])
    action = turn.get("action")
    if isinstance(action, dict) and isinstance(action.get("blocked_action"), dict):
        return dict(action["blocked_action"])
    return dict(action) if isinstance(action, dict) else {}


def _llm_action_fixture_from_step(step):
    if not isinstance(step, dict):
        return {}
    turn = step.get("model_turn")
    if not isinstance(turn, dict):
        return {}
    raw_action = _raw_action_from_model_turn(turn)
    if not raw_action:
        return {}
    post_policy_action = turn.get("action") if isinstance(turn.get("action"), dict) else {}
    return {
        "step_index": step.get("index"),
        "step_status": step.get("status") or "",
        "model_turn_id": turn.get("id"),
        "model_turn_status": turn.get("status") or "",
        "raw_action": raw_action,
        "post_policy_action": dict(post_policy_action),
        "source": "model_turn.action_plan.action",
    }


def _llm_action_fixtures_from_work_report(report):
    steps = ((report.get("work_report") or {}).get("steps") or []) if isinstance(report, dict) else []
    fixtures = []
    for step in steps:
        fixture = _llm_action_fixture_from_step(step)
        if fixture:
            fixtures.append(fixture)
    return fixtures


def _implement_v2_artifact_dir(report_path):
    parent = Path(report_path).parent
    parent_manifest = _read_json(parent / "proof-manifest.json")
    if (parent / "proof-manifest.json").is_file() and _implement_v2_is_native_artifact(parent, parent_manifest):
        return parent
    direct = Path(report_path).parent / "implement_v2"
    if direct.is_dir():
        return direct
    if (parent / "proof-manifest.json").is_file():
        return parent
    return None


def _implement_v2_replay_summary(report_path, report):
    work_report = report.get("work_report") if isinstance(report.get("work_report"), dict) else {}
    result = work_report.get("implement_lane_result") if isinstance(work_report.get("implement_lane_result"), dict) else {}
    metrics = result.get("metrics") if isinstance(result.get("metrics"), dict) else {}
    runtime_id = str(metrics.get("runtime_id") or result.get("runtime_id") or work_report.get("runtime_id") or "")
    selected_lane = str(work_report.get("selected_lane") or result.get("lane") or "")
    if runtime_id != "implement_v2_model_json_tool_loop" and selected_lane != "implement_v2":
        return {}
    artifact_dir = _implement_v2_artifact_dir(report_path)
    manifest = _read_json(artifact_dir / "proof-manifest.json") if artifact_dir else {}
    if _implement_v2_is_native_artifact(artifact_dir, manifest):
        return _implement_v2_native_replay_summary(report_path, report, artifact_dir=artifact_dir, manifest=manifest)
    history = _read_json(artifact_dir / "history.json", default=[]) if artifact_dir else []
    if not isinstance(history, list):
        history = []
    tool_results = manifest.get("tool_results") if isinstance(manifest.get("tool_results"), list) else []
    replayed_source_output_contract = _implement_v2_replay_source_output_contract(
        tool_results,
        artifact_namespace=str(artifact_dir or Path(report_path).parent),
    )
    updated_lane_state = result.get("updated_lane_state") if isinstance(result.get("updated_lane_state"), dict) else {}
    hard_runtime_frontier = (
        updated_lane_state.get("lane_hard_runtime_frontier")
        if isinstance(updated_lane_state.get("lane_hard_runtime_frontier"), dict)
        else {}
    )
    stored_source_output_contract = (
        hard_runtime_frontier.get("source_output_contract")
        if isinstance(hard_runtime_frontier.get("source_output_contract"), dict)
        else {}
    )
    model_error = _implement_v2_model_error_from_report(report, history=history, metrics=metrics, manifest=manifest)
    if not history and not tool_results and not model_error:
        return {}
    failed_results = [
        result for result in tool_results
        if isinstance(result, dict) and str(result.get("status") or "") in {"failed", "interrupted", "invalid", "denied"}
    ]
    terminal_results = [
        result for result in tool_results
        if isinstance(result, dict) and str(result.get("tool_name") or "") in {"run_command", "run_tests", "poll_command"}
    ]
    structured_replay = _implement_v2_structured_execution_replay(tool_results)
    write_evidence_count = _implement_v2_write_evidence_count(tool_results)
    external_expected_artifacts = _external_verifier_expected_artifacts(_find_parent_with_result(report_path))
    external_verifier_missing_artifacts = _external_verifier_missing_artifacts(_find_parent_with_result(report_path))
    passed_structured_artifacts = _implement_v2_passed_structured_artifacts(tool_results)
    external_expected_artifact_missing = [
        path
        for path in external_expected_artifacts
        if not _external_artifact_satisfied_by_structured_evidence(path, passed_structured_artifacts)
    ]
    legacy_marker_fallback = _implement_v2_legacy_runtime_marker_fallback(
        failed_results,
        structured_replay=structured_replay,
    )
    first_write_frontier_stall = _implement_v2_first_write_frontier_stall(
        history,
        tool_results,
        model_error=model_error,
        write_evidence_count=write_evidence_count,
    )
    lane_status = str(result.get("status") or _implement_v2_step_status(work_report) or "")
    if _implement_v2_should_project_completed(tool_results, external_reward=_reward_from_trial(_find_parent_with_result(report_path), _read_json(_find_parent_with_result(report_path) / "result.json"))):
        lane_status = "completed"
    return {
        "runtime_id": runtime_id or "implement_v2_model_json_tool_loop",
        "lane": selected_lane or "implement_v2",
        "lane_status": lane_status,
        "replay_valid": bool(metrics.get("replay_valid", True)),
        "history_turn_count": len(history),
        "tool_call_count": sum(len(turn.get("tool_calls") or []) for turn in history if isinstance(turn, dict)),
        "tool_result_count": len(tool_results),
        "failed_tool_result_count": len(failed_results),
        "terminal_result_count": len(terminal_results),
        "terminal_evidence_count": int(metrics.get("terminal_evidence_count") or 0),
        "write_evidence_count": write_evidence_count,
        "latest_failure": _implement_v2_latest_failure(failed_results, structured_replay=structured_replay),
        "structured_execution_replay": structured_replay,
        "model_error": model_error,
        "first_write_frontier_stall": first_write_frontier_stall,
        "active_command_closeout_failed": _implement_v2_active_command_closeout_failed(failed_results),
        "tool_contract_shell_surface_misuse": _implement_v2_tool_contract_shell_surface_misuse(failed_results),
        "tool_contract_shell_surface_misuse_seen": _implement_v2_any_tool_contract_shell_surface_misuse(failed_results),
        "tool_contract_recovery_observed": _implement_v2_tool_contract_recovery_observed(tool_results),
        "runtime_artifact_contract_mismatch": bool(external_expected_artifact_missing),
        "external_expected_artifacts": external_expected_artifacts,
        "external_verifier_missing_artifacts": external_verifier_missing_artifacts,
        "passed_structured_artifacts": passed_structured_artifacts,
        "external_expected_artifact_missing": external_expected_artifact_missing,
        "source_output_contract_path": str(replayed_source_output_contract.get("path") or ""),
        "stored_source_output_contract_path": str(stored_source_output_contract.get("path") or ""),
        "post_run_cleanup_present": bool((report.get("post_run_cleanup") or _primary_resume(report).get("post_run_cleanup") or {})),
        "legacy_runtime_marker_fallback": legacy_marker_fallback,
        "hard_runtime_frontier_present": isinstance(updated_lane_state.get("lane_hard_runtime_frontier"), dict)
        and bool(updated_lane_state.get("lane_hard_runtime_frontier")),
        "compiled_source_frontier_observed": _implement_v2_history_mentions_compiled_source_frontier(history),
        "artifact_dir": str(artifact_dir) if artifact_dir else "",
    }


def _implement_v2_is_native_artifact(artifact_dir, manifest):
    if not artifact_dir:
        return False
    if str(manifest.get("runtime_id") or "") == IMPLEMENT_V2_NATIVE_RUNTIME_ID:
        return True
    metrics = manifest.get("metrics") if isinstance(manifest.get("metrics"), dict) else {}
    if metrics.get("provider_native_tool_loop") is True:
        return True
    if str(manifest.get("transport_kind") or metrics.get("transport_kind") or "") == "provider_native":
        return True
    return False


def _implement_v2_native_replay_summary(report_path, report, *, artifact_dir, manifest):
    artifact_dir = Path(artifact_dir) if artifact_dir else None
    work_report = report.get("work_report") if isinstance(report.get("work_report"), dict) else {}
    result = work_report.get("implement_lane_result") if isinstance(work_report.get("implement_lane_result"), dict) else {}
    metrics = result.get("metrics") if isinstance(result.get("metrics"), dict) else {}
    transcript_error = ""
    transcript = None
    try:
        transcript = _read_native_transcript(artifact_dir)
    except Exception as exc:
        transcript_error = str(exc)
    if transcript is None:
        return {
            "runtime_id": IMPLEMENT_V2_NATIVE_RUNTIME_ID,
            "lane": "implement_v2",
            "lane_status": str(result.get("status") or _implement_v2_step_status(work_report) or ""),
            "replay_valid": False,
            "native_transcript": {"valid": False, "error": transcript_error},
            "artifact_dir": str(artifact_dir) if artifact_dir else "",
        }

    pairing = validate_native_transcript_pairing(transcript)
    response_items_match = _native_response_items_match(artifact_dir, transcript)
    transcript_hash = native_transcript_hash(transcript)
    manifest_hash_matches = str(manifest.get("transcript_hash") or "") == transcript_hash
    manifest_pairing_matches = _native_manifest_pairing_matches(manifest, pairing)
    trace_summary = _native_trace_summary(artifact_dir)
    calls = [item for item in transcript.items if item.kind in CALL_ITEM_KINDS]
    outputs = [item for item in transcript.items if item.kind in OUTPUT_ITEM_KINDS]
    failed_outputs = [
        item for item in outputs
        if item.is_error or str(item.status or "").casefold() in {"failed", "interrupted", "invalid", "denied", "synthetic_error", "blocked"}
    ]
    terminal_outputs = [
        item for item in outputs
        if str(item.tool_name or "") in {*_IMPLEMENT_V2_TERMINAL_TOOLS, "cancel_command", "read_command_output"}
    ]
    lane_status = str(result.get("status") or _implement_v2_step_status(work_report) or "")
    external_reward = _reward_from_trial(_find_parent_with_result(report_path), _read_json(_find_parent_with_result(report_path) / "result.json"))
    if external_reward == 1.0:
        lane_status = "completed"
    replay_valid = bool(
        transcript.items
        and pairing.call_count > 0
        and pairing.output_count > 0
        and pairing.valid
        and response_items_match
        and manifest_hash_matches
        and manifest_pairing_matches
    )
    latest_failure = _implement_v2_native_latest_failure(outputs)
    return {
        "runtime_id": IMPLEMENT_V2_NATIVE_RUNTIME_ID,
        "lane": "implement_v2",
        "lane_status": lane_status,
        "replay_valid": replay_valid,
        "history_turn_count": _safe_int(trace_summary.get("turn_count")) or len({item.turn_id for item in transcript.items if item.turn_id}),
        "tool_call_count": len(calls),
        "tool_result_count": len(outputs),
        "failed_tool_result_count": len(failed_outputs),
        "terminal_result_count": len(terminal_outputs),
        "terminal_evidence_count": _safe_int(trace_summary.get("command_count")) or len(terminal_outputs),
        "write_evidence_count": _safe_int(trace_summary.get("edit_count")) or sum(
            1 for item in calls if str(item.tool_name or "") in _IMPLEMENT_V2_WRITE_TOOLS
        ),
        "latest_failure": latest_failure,
        "structured_execution_replay": {
            "classification_count": 0,
            "stored_classification_count": 0,
            "missing_stored_classification_count": 0,
            "mismatch_count": 0,
            "mismatches": [],
            "latest_failure_classification": {},
            "records": [],
            "source": "native_transcript",
        },
        "model_error": _implement_v2_model_error_from_report(report, history=[], metrics=metrics, manifest=manifest),
        "first_write_frontier_stall": {},
        "active_command_closeout_failed": _implement_v2_native_active_command_closeout_failed(outputs),
        "tool_contract_shell_surface_misuse": False,
        "tool_contract_shell_surface_misuse_seen": False,
        "tool_contract_recovery_observed": False,
        "runtime_artifact_contract_mismatch": False,
        "external_expected_artifacts": _external_verifier_expected_artifacts(_find_parent_with_result(report_path)),
        "external_verifier_missing_artifacts": _external_verifier_missing_artifacts(_find_parent_with_result(report_path)),
        "passed_structured_artifacts": [],
        "external_expected_artifact_missing": _external_verifier_missing_artifacts(_find_parent_with_result(report_path)),
        "source_output_contract_path": "",
        "stored_source_output_contract_path": "",
        "post_run_cleanup_present": bool((report.get("post_run_cleanup") or _primary_resume(report).get("post_run_cleanup") or {})),
        "legacy_runtime_marker_fallback": {},
        "hard_runtime_frontier_present": bool(latest_failure),
        # Native transcript replay has already crossed the provider-native
        # source/probe/edit loop.  Do not route it through the legacy
        # compiled-source-frontier fallback that only existed for history.json.
        "compiled_source_frontier_observed": True,
        "artifact_dir": str(artifact_dir) if artifact_dir else "",
        "native_transcript": {
            "valid": replay_valid,
            "pairing": pairing.as_dict(),
            "response_items_match": response_items_match,
            "manifest_hash_matches": manifest_hash_matches,
            "manifest_pairing_matches": manifest_pairing_matches,
            "transcript_hash": transcript_hash,
            "item_count": len(transcript.items),
            "trace_summary": trace_summary,
            "error": "",
        },
    }


def _read_native_transcript(artifact_dir):
    root = Path(artifact_dir) if artifact_dir else None
    if root is None:
        raise FileNotFoundError("missing native artifact dir")
    payload = _read_json(root / "response_transcript.json")
    if not isinstance(payload, dict) or not payload:
        raise FileNotFoundError(f"missing native response_transcript.json under {root}")
    return NativeTranscript(
        lane_attempt_id=str(payload.get("lane_attempt_id") or ""),
        provider=str(payload.get("provider") or ""),
        model=str(payload.get("model") or ""),
        items=tuple(
            _native_transcript_item_from_mapping(item)
            for item in payload.get("items") or []
            if isinstance(item, dict)
        ),
    )


def _native_transcript_item_from_mapping(item):
    return NativeTranscriptItem(
        sequence=_safe_int(item.get("sequence")),
        turn_id=str(item.get("turn_id") or ""),
        kind=str(item.get("kind") or ""),  # type: ignore[arg-type]
        lane_attempt_id=str(item.get("lane_attempt_id") or ""),
        provider=str(item.get("provider") or ""),
        model=str(item.get("model") or ""),
        response_id=str(item.get("response_id") or ""),
        provider_item_id=str(item.get("provider_item_id") or ""),
        output_index=_safe_int(item.get("output_index")),
        call_id=str(item.get("call_id") or ""),
        tool_name=str(item.get("tool_name") or ""),
        arguments_json_text=str(item.get("arguments_json_text") or ""),
        custom_input_text=str(item.get("custom_input_text") or ""),
        output_text_or_ref=str(item.get("output_text_or_ref") or ""),
        status=str(item.get("status") or ""),
        is_error=bool(item.get("is_error")),
        raw_ref=str(item.get("raw_ref") or ""),
        encrypted_reasoning_ref=str(item.get("encrypted_reasoning_ref") or ""),
        metrics_ref=str(item.get("metrics_ref") or ""),
        content_refs=tuple(str(ref) for ref in item.get("content_refs") or ()),
        evidence_refs=tuple(str(ref) for ref in item.get("evidence_refs") or ()),
        sidecar_refs=tuple(str(ref) for ref in item.get("sidecar_refs") or ()),
    )


def _native_response_items_match(artifact_dir, transcript):
    items_path = Path(artifact_dir) / "response_items.jsonl"
    try:
        response_items = [json.loads(line) for line in items_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except Exception:
        return False
    return response_items == [item.as_dict() for item in transcript.items]


def _native_manifest_pairing_matches(manifest, pairing):
    manifest_pairing = manifest.get("pairing") if isinstance(manifest.get("pairing"), dict) else {}
    metrics = manifest.get("metrics") if isinstance(manifest.get("metrics"), dict) else {}
    if not manifest_pairing:
        return False
    if manifest_pairing.get("valid") is not True:
        return False
    if list(manifest_pairing.get("errors") or []) != list(pairing.errors):
        return False
    for key, value in (
        ("call_count", pairing.call_count),
        ("output_count", pairing.output_count),
        ("non_tool_count", pairing.non_tool_count),
    ):
        if _safe_int(manifest_pairing.get(key)) != value:
            return False
    if metrics:
        if metrics.get("pairing_valid") is not True:
            return False
        for key, value in (
            ("call_count", pairing.call_count),
            ("output_count", pairing.output_count),
            ("non_tool_count", pairing.non_tool_count),
        ):
            if key in metrics and _safe_int(metrics.get(key)) != value:
                return False
    return True


def _native_trace_summary(artifact_dir):
    data = _read_json(Path(artifact_dir) / "normalized-trace" / "summary.json")
    return data if isinstance(data, dict) else {}


def _implement_v2_native_latest_failure(outputs):
    failed_indexes = [
        index
        for index, item in enumerate(outputs if isinstance(outputs, list) else [])
        if _implement_v2_native_output_is_failed(item)
    ]
    if not failed_indexes:
        return {}
    latest_index = failed_indexes[-1]
    item = outputs[latest_index]
    if _implement_v2_native_output_is_low_signal_active_command_closeout(item):
        prior = _implement_v2_native_prior_actionable_terminal_output(
            outputs[:latest_index],
            command_run_id=_implement_v2_native_output_command_run_id(item),
        )
        if prior is not None:
            return _implement_v2_native_failure_from_output(
                prior,
                source="native_transcript_prior_terminal_output",
                suppressed_closeout_provider_call_id=str(item.call_id or ""),
            )
    return _implement_v2_native_failure_from_output(item, source="native_transcript_output")


def _implement_v2_native_active_command_closeout_failed(outputs):
    failed_indexes = [
        index
        for index, item in enumerate(outputs if isinstance(outputs, list) else [])
        if _implement_v2_native_output_is_failed(item)
    ]
    for index in reversed(failed_indexes):
        item = outputs[index]
        if not _implement_v2_native_output_is_terminal(item):
            continue
        if not _implement_v2_native_output_is_active_command_closeout(item):
            return False
        if _implement_v2_native_output_is_low_signal_active_command_closeout(item) and _implement_v2_native_prior_actionable_terminal_output(
            outputs[:index],
            command_run_id=_implement_v2_native_output_command_run_id(item),
        ) is not None:
            return False
        return True
    return False


def _implement_v2_native_failure_from_output(
    item,
    *,
    source,
    suppressed_closeout_provider_call_id="",
):
    text = str(item.output_text_or_ref or "")
    latest = {
        "provider_call_id": str(item.call_id or ""),
        "tool_name": str(item.tool_name or ""),
        "status": str(item.status or ""),
        "reason": _clip_text(text),
        "exit_code": _extract_exit_code(text),
        "timed_out": "timed_out=true" in text.casefold() or "timed out" in text.casefold(),
        "stderr_tail": _extract_labeled_tail(text, "stderr_tail"),
        "stdout_tail": _extract_labeled_tail(text, "stdout_tail"),
        "source": source,
    }
    if suppressed_closeout_provider_call_id:
        latest["suppressed_closeout_provider_call_id"] = suppressed_closeout_provider_call_id
    return latest


def _implement_v2_native_output_is_failed(item):
    return (
        isinstance(item, NativeTranscriptItem)
        and item.kind in OUTPUT_ITEM_KINDS
        and (
            item.is_error
            or str(item.status or "").casefold()
            in {"failed", "interrupted", "invalid", "denied", "synthetic_error", "blocked"}
        )
    )


def _implement_v2_native_output_is_active_command_closeout(item):
    if not isinstance(item, NativeTranscriptItem):
        return False
    call_id = str(item.call_id or "")
    if call_id.startswith("call-active-command-closeout-"):
        return True
    text = str(item.output_text_or_ref or "").casefold()
    return "active command closeout" in text


def _implement_v2_native_output_is_terminal(item):
    return isinstance(item, NativeTranscriptItem) and str(item.tool_name or "") in _IMPLEMENT_V2_TERMINAL_TOOLS


def _implement_v2_native_output_is_low_signal_active_command_closeout(item):
    if not _implement_v2_native_output_is_active_command_closeout(item):
        return False
    text = str(item.output_text_or_ref or "")
    lowered = text.casefold()
    if not any(marker in lowered for marker in ("timed_out", "timed out", "budget exhausted", "orphaned")):
        return False
    stdout_tail = _extract_labeled_tail(text, "stdout_tail").strip()
    stderr_tail = _extract_labeled_tail(text, "stderr_tail").strip()
    if stdout_tail:
        return False
    if not stderr_tail:
        return True
    normalized = re.sub(r"\s+", " ", stderr_tail.casefold()).strip()
    timeout_only = normalized.startswith("command timed out after ") or normalized in {
        "timed out",
        "timeout",
    }
    return timeout_only


def _implement_v2_native_prior_actionable_terminal_output(outputs, *, command_run_id):
    candidates = [
        item
        for item in reversed(outputs if isinstance(outputs, list) else [])
        if _implement_v2_native_output_is_actionable_terminal_evidence(item)
    ]
    if command_run_id:
        for item in candidates:
            if _implement_v2_native_output_command_run_id(item) == command_run_id:
                return item
        return None
    return candidates[0] if candidates else None


def _implement_v2_native_output_is_actionable_terminal_evidence(item):
    if not isinstance(item, NativeTranscriptItem):
        return False
    if item.kind not in OUTPUT_ITEM_KINDS:
        return False
    if str(item.tool_name or "") not in _IMPLEMENT_V2_TERMINAL_TOOLS:
        return False
    if _implement_v2_native_output_is_active_command_closeout(item):
        return False
    text = str(item.output_text_or_ref or "")
    stdout_tail = _extract_labeled_tail(text, "stdout_tail").strip()
    stderr_tail = _extract_labeled_tail(text, "stderr_tail").strip()
    if stdout_tail or stderr_tail:
        return True
    lowered = text.casefold()
    return any(
        marker in lowered
        for marker in (
            "exit_code=",
            "failure_classification",
            "verifier_evidence",
            "artifact_evidence",
        )
    )


def _implement_v2_native_output_command_run_id(item):
    if not isinstance(item, NativeTranscriptItem):
        return ""
    match = re.search(r"command_run_id=([^;\s]+)", str(item.output_text_or_ref or ""))
    return str(match.group(1) if match else "").strip()


def _extract_exit_code(text):
    match = re.search(r"exit_code=([+-]?\d+)", str(text or ""))
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _extract_labeled_tail(text, label):
    match = re.search(rf"{re.escape(label)}:\s*(.*?)(?:;\s*(?:output_refs|evidence_refs|content|status|exit_code)=|$)", str(text or ""), re.DOTALL)
    if not match:
        return ""
    return _clip_text(match.group(1).strip())


def _safe_int(value):
    if isinstance(value, bool):
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _external_verifier_expected_artifacts(trial_dir):
    trial_dir = Path(trial_dir)
    texts = [
        _read_text(trial_dir / "verifier" / "test-stdout.txt"),
        _read_text(trial_dir / "verifier" / "test-stderr.txt"),
        _read_text(trial_dir / "verifier" / "ctrf.json"),
    ]
    artifacts = []
    for text in texts:
        for path in _tmp_paths_with_expected_context(text):
            if path not in artifacts:
                artifacts.append(path)
    return artifacts[:12]


def _implement_v2_replay_source_output_contract(tool_results, *, artifact_namespace):
    envelopes = []
    for index, result in enumerate(tool_results or []):
        if not isinstance(result, dict):
            continue
        tool_name = str(result.get("tool_name") or "")
        if tool_name not in {"read_file", "search_text", "run_command", "run_tests"}:
            continue
        status = str(result.get("status") or "completed")
        if status not in {"completed", "failed", "denied", "invalid", "interrupted", "running", "yielded"}:
            status = "failed"
        content = result.get("content")
        if isinstance(content, list):
            content_items = tuple(content)
        elif isinstance(content, tuple):
            content_items = content
        elif content is None:
            content_items = ()
        else:
            content_items = (content,)
        provider_call_id = str(result.get("provider_call_id") or result.get("id") or f"tool-result-{index}")
        content_refs = result.get("content_refs")
        evidence_refs = result.get("evidence_refs")
        envelopes.append(
            ToolResultEnvelope(
                lane_attempt_id=str(result.get("lane_attempt_id") or "terminal-bench-replay"),
                provider_call_id=provider_call_id,
                mew_tool_call_id=str(result.get("mew_tool_call_id") or provider_call_id),
                tool_name=tool_name,
                status=status,
                is_error=bool(result.get("is_error")),
                content=content_items,
                content_refs=tuple(str(item) for item in content_refs) if isinstance(content_refs, list) else (),
                evidence_refs=tuple(str(item) for item in evidence_refs) if isinstance(evidence_refs, list) else (),
            )
        )
    if not envelopes:
        return {}
    registry = _frontier_evidence_registry(tuple(envelopes), artifact_namespace=str(artifact_namespace))
    return _source_output_contract_from_tool_results(tuple(envelopes), registry)


def _external_verifier_missing_artifacts(trial_dir):
    # The verifier output is the external ground truth. Keep this separate from
    # "expected but internally missing" because an internal structured pass can
    # still fail under the external verifier's cwd/lifecycle/latency contract.
    return _external_verifier_expected_artifacts(trial_dir)


def _tmp_paths_with_expected_context(text):
    value = str(text or "")
    if not value:
        return []
    lowered = value.casefold()
    paths = []
    for match in _TMP_PATH_RE.finditer(value):
        path = str(match.group(1) or "").rstrip("`'\".,;:)]}")
        if not path or path.endswith("/"):
            continue
        context = lowered[max(0, match.start() - 160) : min(len(lowered), match.end() + 160)]
        if not any(marker in context for marker in _EXTERNAL_EXPECTED_PATH_MARKERS):
            continue
        if path not in paths:
            paths.append(path)
    return paths


def _implement_v2_passed_structured_artifacts(tool_results):
    artifacts = []
    for result in tool_results:
        if not isinstance(result, dict):
            continue
        if str(result.get("status") or "").casefold() != "completed":
            continue
        content = result.get("content")
        first_content = content[0] if isinstance(content, list) and content and isinstance(content[0], dict) else {}
        verifier = first_content.get("verifier_evidence") if isinstance(first_content, dict) else {}
        if not isinstance(verifier, dict) or str(verifier.get("verdict") or "").casefold() != "pass":
            continue
        contract = first_content.get("execution_contract_normalized")
        if not isinstance(contract, dict):
            contract = first_content.get("execution_contract")
        if not _implement_v2_contract_is_final_verifier(contract):
            continue
        artifact_evidence = first_content.get("artifact_evidence") if isinstance(first_content, dict) else []
        if not isinstance(artifact_evidence, list):
            continue
        for artifact in artifact_evidence:
            if not isinstance(artifact, dict):
                continue
            if str(artifact.get("status") or "").casefold() != "passed":
                continue
            for key in ("artifact_id", "path", "artifact_path"):
                value = str(artifact.get(key) or "").strip()
                if _verifier_scratch_tmp_artifact(value):
                    continue
                if value and value not in artifacts:
                    artifacts.append(value)
    return artifacts[:24]


def _implement_v2_should_project_completed(tool_results, *, external_reward):
    try:
        reward = float(external_reward)
    except (TypeError, ValueError):
        return False
    if reward != 1.0:
        return False
    return _implement_v2_latest_terminal_result_is_passed_final_verifier(tool_results)


def _implement_v2_latest_terminal_result_is_passed_final_verifier(tool_results):
    for result in reversed(tool_results if isinstance(tool_results, list) else []):
        if not isinstance(result, dict):
            continue
        if str(result.get("tool_name") or "") not in _IMPLEMENT_V2_TERMINAL_TOOLS:
            continue
        if str(result.get("status") or "").casefold() != "completed":
            return False
        content = result.get("content")
        first_content = content[0] if isinstance(content, list) and content and isinstance(content[0], dict) else {}
        verifier = first_content.get("verifier_evidence") if isinstance(first_content, dict) else {}
        if not isinstance(verifier, dict) or str(verifier.get("verdict") or "").casefold() != "pass":
            return False
        contract = first_content.get("execution_contract_normalized")
        if not isinstance(contract, dict):
            contract = first_content.get("execution_contract")
        if not _implement_v2_contract_is_final_verifier(contract):
            return False
        artifacts = first_content.get("artifact_evidence") if isinstance(first_content, dict) else []
        if not isinstance(artifacts, list):
            return False
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                continue
            if str(artifact.get("status") or "").casefold() != "passed":
                continue
            candidates = [
                str(artifact.get(key) or "").strip()
                for key in ("artifact_id", "path", "artifact_path")
            ]
            if any(value and not _verifier_scratch_tmp_artifact(value) for value in candidates):
                return True
        return False
    return False


def _implement_v2_contract_is_final_verifier(contract):
    if not isinstance(contract, dict):
        return False
    proof_role = str(contract.get("proof_role") or "").casefold()
    acceptance_kind = str(contract.get("acceptance_kind") or "").casefold()
    stage = str(contract.get("stage") or "").casefold()
    purpose = str(contract.get("purpose") or "").casefold()
    role = str(contract.get("role") or "").casefold()
    if acceptance_kind not in {"external_verifier", "candidate_final_proof"}:
        return False
    if proof_role not in {"verifier", "final_artifact", "custom_runtime_smoke", "default_smoke"}:
        return False
    return (
        stage in {"verification", "artifact_proof", "custom_runtime_smoke", "default_smoke"}
        or purpose in {"verification", "artifact_proof", "smoke"}
        or role in {"verify", "runtime", "test"}
    )


def _verifier_scratch_tmp_artifact(value):
    lowered = str(value or "").casefold()
    if not lowered.startswith("/tmp/") or not lowered.endswith((".log", ".txt", ".out", ".stdout", ".stderr")):
        return False
    name = lowered.rsplit("/", 1)[-1]
    return any(token in name for token in ("log", "out", "stdout", "stderr", "trace", "transcript"))


def _external_artifact_satisfied_by_structured_evidence(path, artifacts):
    expected = str(path or "").casefold()
    if not expected:
        return False
    return any(str(artifact or "").casefold() == expected for artifact in artifacts)


def _implement_v2_step_status(work_report):
    steps = work_report.get("steps") if isinstance(work_report, dict) else []
    if not isinstance(steps, list) or not steps:
        return ""
    for step in reversed(steps):
        if isinstance(step, dict) and step.get("status"):
            return str(step.get("status") or "")
    return ""


def _implement_v2_model_error_from_report(report, *, history, metrics, manifest):
    manifest_metrics = manifest.get("metrics") if isinstance(manifest.get("metrics"), dict) else {}
    for source in (metrics, manifest_metrics):
        model_error = source.get("model_error") if isinstance(source, dict) else {}
        if isinstance(model_error, dict) and model_error:
            return _normalize_implement_v2_model_error(model_error)
    for turn in reversed(history):
        if isinstance(turn, dict) and isinstance(turn.get("model_error"), dict):
            return _normalize_implement_v2_model_error(turn["model_error"])
    work_report = report.get("work_report") if isinstance(report.get("work_report"), dict) else {}
    steps = work_report.get("steps") if isinstance(work_report.get("steps"), list) else []
    for step in reversed(steps):
        if not isinstance(step, dict):
            continue
        model_turn = step.get("model_turn") if isinstance(step.get("model_turn"), dict) else {}
        if str(step.get("status") or "") != "failed" and str(model_turn.get("status") or "") != "failed":
            continue
        model_metrics = model_turn.get("model_metrics") if isinstance(model_turn.get("model_metrics"), dict) else {}
        candidates = [
            model_metrics.get("error") if isinstance(model_metrics, dict) else "",
            model_turn.get("error") if isinstance(model_turn, dict) else "",
            step.get("error"),
        ]
        for candidate in candidates:
            text = str(candidate or "")
            if text and _looks_like_implement_v2_model_error_text(text):
                return _normalize_implement_v2_model_error({"message": text, "error_type": "ModelBackendError"})
    return {}


def _looks_like_implement_v2_model_error_text(message):
    lowered = str(message or "").casefold()
    return any(
        marker in lowered
        for marker in (
            "codex web api",
            "incompleteread",
            "modelbackenderror",
            "model backend",
            "failed to parse json plan",
            "response did not contain json",
            "response did not contain assistant",
            "max_turns before finish",
            "max turns before finish",
            "request timed out",
            "model timed out",
            "model timeout",
            "model_timeout",
            "readtimeout",
        )
    )


def _normalize_implement_v2_model_error(model_error):
    message = str(model_error.get("message") or model_error.get("error") or "")
    failure_class = str(model_error.get("failure_class") or "")
    lowered = message.casefold()
    if not failure_class:
        if "failed to parse json plan" in lowered or "response did not contain json" in lowered:
            failure_class = "model_json_parse_error"
        elif "max_turns before finish" in lowered or "max turns before finish" in lowered:
            failure_class = "max_turns_before_finish"
        elif (
            "request timed out" in lowered
            or "model timed out" in lowered
            or "model timeout" in lowered
            or "model_timeout" in lowered
            or "readtimeout" in lowered
        ):
            failure_class = "model_timeout"
        else:
            failure_class = "model_backend_error"
    error_type = str(model_error.get("error_type") or "ModelBackendError")
    if failure_class == "max_turns_before_finish" and error_type == "ModelBackendError":
        error_type = "ImplementV2LoopLimit"
    return {
        "failure_class": failure_class,
        "error_type": error_type,
        "message": _clip_text(message),
        "raw_excerpt": _clip_text(model_error.get("raw_excerpt") or _raw_excerpt_from_error_text(message)),
    }


def _raw_excerpt_from_error_text(message):
    marker = "raw="
    index = str(message).find(marker)
    if index == -1:
        return ""
    return str(message)[index + len(marker) :]


def _implement_v2_structured_execution_replay(tool_results):
    records = []
    mismatches = []
    stored_count = 0
    missing_stored_count = 0
    for index, result in enumerate(tool_results):
        if not isinstance(result, dict) or str(result.get("tool_name") or "") not in _IMPLEMENT_V2_TERMINAL_TOOLS:
            continue
        payload = _first_tool_result_payload(result)
        if not payload:
            continue
        tool_run = payload.get("tool_run_record")
        if not isinstance(tool_run, dict):
            continue
        normalized_contract = payload.get("execution_contract_normalized")
        raw_contract = payload.get("execution_contract")
        contract_raw = {}
        if isinstance(normalized_contract, dict):
            contract_raw.update(normalized_contract)
        if isinstance(raw_contract, dict):
            contract_raw.update(raw_contract)
        if not contract_raw:
            contract_raw = {"id": tool_run.get("contract_id") or f"contract:{tool_run.get('command_run_id') or index}"}
        artifacts_raw = payload.get("artifact_evidence")
        artifacts = [item for item in artifacts_raw if isinstance(item, dict)] if isinstance(artifacts_raw, list) else []
        contract = normalize_execution_contract(contract_raw)
        verifier = derive_verifier_evidence(contract, (tool_run,), artifacts)
        classification = classify_execution_failure(tool_run, artifacts, verifier, contract).as_dict()
        stored = payload.get("failure_classification")
        stored_classification = dict(stored) if isinstance(stored, dict) else {}
        if stored_classification:
            stored_count += 1
        else:
            missing_stored_count += 1
        matches = None
        if stored_classification:
            matches = _failure_classification_core(stored_classification) == _failure_classification_core(classification)
            if not matches:
                mismatches.append(
                    {
                        "tool_result_index": index,
                        "provider_call_id": str(result.get("provider_call_id") or ""),
                        "tool_name": str(result.get("tool_name") or ""),
                        "stored": _failure_classification_core(stored_classification),
                        "recomputed": _failure_classification_core(classification),
                    }
                )
        records.append(
            {
                "tool_result_index": index,
                "provider_call_id": str(result.get("provider_call_id") or ""),
                "tool_name": str(result.get("tool_name") or ""),
                "status": str(result.get("status") or ""),
                "tool_run_record_id": str(tool_run.get("record_id") or ""),
                "command_run_id": str(tool_run.get("command_run_id") or ""),
                "artifact_evidence_count": len(artifacts),
                "verifier_verdict": verifier.verdict,
                "classification": classification,
                "stored_classification_matches": matches,
            }
        )
    latest = {}
    for record in reversed(records):
        classification = record.get("classification") if isinstance(record.get("classification"), dict) else {}
        if classification.get("class") and classification.get("class") != "unknown_failure":
            latest = dict(classification)
            break
    return {
        "classification_count": len(records),
        "stored_classification_count": stored_count,
        "missing_stored_classification_count": missing_stored_count,
        "mismatch_count": len(mismatches),
        "mismatches": mismatches[:8],
        "latest_failure_classification": latest,
        "records": records[-8:],
    }


def _failure_classification_core(classification):
    return {
        key: _json_comparable_failure_value(classification.get(key, _FAILURE_CLASSIFICATION_DEFAULTS[key]))
        for key in _FAILURE_CLASSIFICATION_COMPARE_KEYS
    }


def _json_comparable_failure_value(value):
    if isinstance(value, dict):
        return {str(key): _json_comparable_failure_value(value[key]) for key in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [_json_comparable_failure_value(item) for item in value]
    return value


def _first_tool_result_payload(result):
    content = result.get("content") if isinstance(result, dict) else None
    return content[0] if isinstance(content, list) and content and isinstance(content[0], dict) else {}


def _latest_structured_failure_record(structured_replay, *, skip_provider_call_ids=None):
    skip_ids = {str(item) for item in (skip_provider_call_ids or set()) if str(item)}
    records = structured_replay.get("records") if isinstance(structured_replay, dict) else []
    for record in reversed(records if isinstance(records, list) else []):
        if not isinstance(record, dict):
            continue
        if str(record.get("provider_call_id") or "") in skip_ids:
            continue
        classification = record.get("classification") if isinstance(record.get("classification"), dict) else {}
        if classification.get("class") and classification.get("class") != "unknown_failure":
            return record
    return {}


def _implement_v2_latest_failure(failed_results, *, structured_replay=None):
    low_signal_closeout_ids = _implement_v2_low_signal_active_command_closeout_ids(failed_results)
    structured_record = _latest_structured_failure_record(
        structured_replay or {},
        skip_provider_call_ids=low_signal_closeout_ids,
    )
    if not failed_results:
        if structured_record:
            classification = structured_record.get("classification") or {}
            return {
                "provider_call_id": str(structured_record.get("provider_call_id") or ""),
                "tool_name": str(structured_record.get("tool_name") or ""),
                "status": str(structured_record.get("status") or ""),
                "failure_class": str(classification.get("class") or ""),
                "failure_kind": str(classification.get("kind") or ""),
                "failure_phase": str(classification.get("phase") or ""),
                "required_next_probe": str(classification.get("required_next_probe") or ""),
                "source": "recomputed_structured_execution_evidence",
            }
        return {}
    by_provider_call_id = {
        str(result.get("provider_call_id") or ""): result
        for result in failed_results
        if isinstance(result, dict) and str(result.get("provider_call_id") or "")
    }
    result = by_provider_call_id.get(str(structured_record.get("provider_call_id") or "")) if structured_record else None
    if result is None:
        result = failed_results[-1]
        for candidate in reversed(failed_results):
            if not isinstance(candidate, dict):
                continue
            if str(candidate.get("provider_call_id") or "") in low_signal_closeout_ids:
                continue
            if str(candidate.get("tool_name") or "") in _IMPLEMENT_V2_TERMINAL_TOOLS:
                result = candidate
                break
    first_content = _first_tool_result_payload(result)
    latest = {
        "provider_call_id": str(result.get("provider_call_id") or ""),
        "tool_name": str(result.get("tool_name") or ""),
        "status": str(result.get("status") or ""),
        "reason": str(first_content.get("reason") or ""),
        "kill_status": str(first_content.get("kill_status") or ""),
        "exit_code": first_content.get("exit_code"),
        "timed_out": bool(first_content.get("timed_out")),
        "stderr_tail": _clip_text(first_content.get("stderr_tail") or first_content.get("stderr") or ""),
        "stdout_tail": _clip_text(first_content.get("stdout_tail") or first_content.get("stdout") or ""),
    }
    if structured_record:
        classification = structured_record.get("classification") if isinstance(structured_record.get("classification"), dict) else {}
        latest.update(
            {
                "failure_class": str(classification.get("class") or ""),
                "failure_kind": str(classification.get("kind") or ""),
                "failure_phase": str(classification.get("phase") or ""),
                "required_next_probe": str(classification.get("required_next_probe") or ""),
                "source": "recomputed_structured_execution_evidence",
            }
        )
    return latest


def _implement_v2_first_write_frontier_stall(history, tool_results, *, model_error, write_evidence_count):
    if not isinstance(model_error, dict) or model_error.get("failure_class") != "model_timeout":
        return {}
    try:
        writes = int(write_evidence_count or 0)
    except (TypeError, ValueError):
        writes = 0
    if writes > 0:
        return {}
    by_provider_call_id = _implement_v2_history_calls_by_provider_id(history)
    missing = _implement_v2_latest_missing_read_target(tool_results, by_provider_call_id=by_provider_call_id)
    if not missing:
        return {}
    prior_observations = _implement_v2_prior_observation_count(tool_results, before_provider_call_id=missing["provider_call_id"])
    if prior_observations <= 0:
        return {}
    target = str(missing.get("target_path") or "").strip()
    required = (
        f"create or update {target} with write_file/edit_file/apply_patch before another live speed run"
        if target
        else "make the first source mutation with write_file/edit_file/apply_patch before another live speed run"
    )
    return {
        "detected": True,
        "failure_class": "first_write_frontier_stall",
        "failure_kind": "missing_target_create_frontier",
        "failure_phase": "planning_to_edit",
        "provider_call_id": missing["provider_call_id"],
        "tool_name": "read_file",
        "target_path": target,
        "target_path_display": missing.get("target_path_display") or target,
        "prior_observation_count": prior_observations,
        "source": "model_timeout_after_missing_read_target_without_write",
        "required_next_action": required,
    }


def _implement_v2_history_calls_by_provider_id(history):
    calls: dict[str, dict[str, object]] = {}
    for turn in history if isinstance(history, list) else []:
        if not isinstance(turn, dict):
            continue
        for call in turn.get("tool_calls") or []:
            if not isinstance(call, dict):
                continue
            provider_call_id = str(call.get("provider_call_id") or call.get("id") or "")
            if provider_call_id:
                calls[provider_call_id] = call
    return calls


def _implement_v2_latest_missing_read_target(tool_results, *, by_provider_call_id):
    for result in reversed(tool_results if isinstance(tool_results, list) else []):
        if not isinstance(result, dict):
            continue
        if str(result.get("tool_name") or "") != "read_file":
            continue
        if str(result.get("status") or "").casefold() not in {"failed", "invalid", "denied"}:
            continue
        payload = _first_tool_result_payload(result)
        reason = str(payload.get("reason") or "")
        if "path does not exist" not in reason.casefold():
            continue
        provider_call_id = str(result.get("provider_call_id") or "")
        call = by_provider_call_id.get(provider_call_id) if provider_call_id else {}
        arguments = call.get("arguments") if isinstance(call, dict) and isinstance(call.get("arguments"), dict) else {}
        target = str(arguments.get("path") or _missing_path_from_read_reason(reason) or "").strip()
        target = _createable_first_write_target_path(target)
        if not target:
            continue
        return {
            "provider_call_id": provider_call_id,
            "target_path": target,
            "target_path_display": target,
            "reason": reason,
        }
    return {}


def _missing_path_from_read_reason(reason):
    text = str(reason or "")
    marker = "path does not exist:"
    index = text.casefold().find(marker)
    if index < 0:
        return ""
    return text[index + len(marker) :].split(";", 1)[0].strip()


def _workspace_relative_path_display(path):
    value = str(path or "").strip()
    for prefix in ("/app/", "/workspace/"):
        if value.startswith(prefix):
            return value[len(prefix) :]
    return value


def _createable_first_write_target_path(path):
    value = str(path or "").strip()
    if not value:
        return ""
    lowered = value.casefold()
    if lowered.startswith(("/tmp/", "/var/tmp/")):
        return ""
    relative = _workspace_relative_path_display(value)
    if not relative or relative in {".", ".."}:
        return ""
    if relative.startswith("../") or relative.startswith("/"):
        return ""
    return relative


def _implement_v2_write_evidence_count(tool_results):
    count = 0
    for result in tool_results if isinstance(tool_results, list) else []:
        if not isinstance(result, dict):
            continue
        if str(result.get("tool_name") or "") not in _IMPLEMENT_V2_WRITE_TOOLS:
            continue
        if result.get("side_effects"):
            count += 1
    return count


def _implement_v2_prior_observation_count(tool_results, *, before_provider_call_id):
    count = 0
    for result in tool_results if isinstance(tool_results, list) else []:
        if not isinstance(result, dict):
            continue
        if str(result.get("provider_call_id") or "") == str(before_provider_call_id or ""):
            break
        if str(result.get("status") or "").casefold() != "completed":
            continue
        if str(result.get("tool_name") or "") in {
            "glob",
            "inspect_dir",
            "read_command_output",
            "read_file",
            "run_command",
            "search_text",
        }:
            count += 1
    return count


def _implement_v2_low_signal_active_command_closeout_ids(failed_results):
    ids = set()
    for result in failed_results:
        if not _implement_v2_tool_result_is_low_signal_active_command_closeout(result):
            continue
        provider_call_id = str(result.get("provider_call_id") or "")
        if provider_call_id:
            ids.add(provider_call_id)
    return ids


def _implement_v2_tool_result_is_low_signal_active_command_closeout(result):
    if not isinstance(result, dict):
        return False
    payload = _first_tool_result_payload(result)
    reason = str(payload.get("reason") or "").lower()
    if "active command closeout budget exhausted" not in reason:
        return False
    status = str(payload.get("status") or "").lower()
    if status not in {"killed", "timed_out", "orphaned"}:
        return False
    if payload.get("exit_code") is not None:
        return False
    stdout = str(payload.get("stdout") or payload.get("stdout_tail") or "").strip()
    stderr = str(payload.get("stderr") or payload.get("stderr_tail") or "").strip()
    if stdout or stderr:
        return False
    try:
        output_bytes = int(payload.get("output_bytes") or 0)
    except (TypeError, ValueError):
        output_bytes = 0
    return output_bytes <= 0


def _implement_v2_latest_failed_terminal_result(failed_results):
    for result in reversed(failed_results):
        if isinstance(result, dict) and str(result.get("tool_name") or "") in _IMPLEMENT_V2_TERMINAL_TOOLS:
            return result
    return {}


def _implement_v2_active_command_closeout_failed(failed_results):
    for index in range(len(failed_results) - 1, -1, -1):
        result = failed_results[index]
        if not isinstance(result, dict):
            continue
        if str(result.get("tool_name") or "") in _IMPLEMENT_V2_TERMINAL_TOOLS:
            if not _implement_v2_tool_result_is_active_command_closeout(result):
                return False
            if _implement_v2_tool_result_is_low_signal_active_command_closeout(
                result
            ) and _implement_v2_has_prior_actionable_terminal_failure(failed_results[:index]):
                return False
            return True
    return False


def _implement_v2_tool_result_is_active_command_closeout(result):
    if not isinstance(result, dict):
        return False
    content = result.get("content")
    first_content = content[0] if isinstance(content, list) and content and isinstance(content[0], dict) else {}
    reason = str(first_content.get("reason") or "").lower()
    status = str(result.get("status") or "").lower()
    if status != "interrupted":
        return False
    return (
        "closed before command finalized" in reason
        or "active command closeout budget exhausted" in reason
    )


def _implement_v2_has_prior_actionable_terminal_failure(failed_results):
    for result in reversed(failed_results):
        if not isinstance(result, dict):
            continue
        if str(result.get("tool_name") or "") not in _IMPLEMENT_V2_TERMINAL_TOOLS:
            continue
        if not _implement_v2_tool_result_is_active_command_closeout(result):
            return True
    return False


def _implement_v2_tool_contract_shell_surface_misuse(failed_results):
    result = _implement_v2_latest_failed_terminal_result(failed_results)
    return _implement_v2_tool_result_is_run_tests_shell_surface_misuse(result)


def _implement_v2_any_tool_contract_shell_surface_misuse(failed_results):
    return any(
        _implement_v2_tool_result_is_run_tests_shell_surface_misuse(result)
        for result in failed_results
        if isinstance(result, dict)
    )


def _implement_v2_tool_result_is_run_tests_shell_surface_misuse(result):
    if str(result.get("tool_name") or "") != "run_tests":
        return False
    content = result.get("content")
    first_content = content[0] if isinstance(content, list) and content and isinstance(content[0], dict) else {}
    structured = (
        first_content.get("failure_class") == "tool_contract_misuse"
        and first_content.get("failure_subclass") == "run_tests_shell_surface"
        and first_content.get("recoverable_tool_contract_misuse") is True
        and first_content.get("suggested_tool") == "run_command"
    )
    if structured:
        return True
    reason = str(first_content.get("reason") or "").casefold()
    return (
        "run_tests executes one argv command without a shell" in reason
        and "use run_command for shell orchestration" in reason
    )


def _implement_v2_tool_contract_recovery_observed(tool_results):
    for result in tool_results:
        if not isinstance(result, dict):
            continue
        content = result.get("content")
        first_content = content[0] if isinstance(content, list) and content and isinstance(content[0], dict) else {}
        recovery = first_content.get("tool_contract_recovery") if isinstance(first_content, dict) else {}
        if isinstance(recovery, dict) and recovery.get("kind") == "run_tests_shell_surface_routed_to_run_command":
            return True
    return False


def _implement_v2_runtime_artifact_contract_mismatch(failed_results):
    result = _implement_v2_latest_failed_terminal_result(failed_results)
    if not result:
        return False
    content = result.get("content")
    first_content = content[0] if isinstance(content, list) and content and isinstance(content[0], dict) else {}
    text = "\n".join(
        str(first_content.get(key) or "")
        for key in (
            "reason",
            "failure_class",
            "failure_subclass",
            "stdout_tail",
            "stderr_tail",
            "stdout",
            "stderr",
        )
    ).casefold()
    runtime_marker = any(
        marker in text
        for marker in (
            "unknown opcode",
            "illegal instruction",
            "exec format error",
            "bad cpu type",
            "invalid instruction",
            "unhandled instruction",
        )
    )
    artifact_contract_marker = any(
        marker in text
        for marker in (
            "elf",
            "readelf",
            "objdump",
            "machine:",
            "entry point",
            "readuint32le",
            "readuint32be",
            "big endian",
            "little endian",
            "emulator",
            " vm.",
            " vm)",
        )
    )
    return runtime_marker and artifact_contract_marker


def _implement_v2_legacy_runtime_marker_fallback(failed_results, *, structured_replay=None):
    structured_count = (
        structured_replay.get("classification_count")
        if isinstance(structured_replay, dict)
        else 0
    )
    detected = _implement_v2_runtime_artifact_contract_mismatch(failed_results)
    if not detected:
        return {}
    return {
        "detected": True,
        "kind": "runtime_artifact_contract_mismatch",
        "confidence": "low",
        "active": False,
        "inactive_reason": (
            "structured_execution_evidence_present"
            if int(structured_count or 0) > 0
            else "marker_only_not_authoritative"
        ),
    }


def _clip_text(text, limit=500):
    text = str(text or "")
    return text[-limit:] if len(text) > limit else text


def _implement_v2_history_mentions_compiled_source_frontier(history):
    needles = ("*.pyx", "*.pxd", ".pyx", ".pxd", "rglob('*.pyx')", 'rglob("*.pyx")')
    for turn in history:
        if not isinstance(turn, dict):
            continue
        for call in turn.get("tool_calls") or []:
            if not isinstance(call, dict):
                continue
            args = call.get("arguments") if isinstance(call.get("arguments"), dict) else {}
            text = json.dumps(args, ensure_ascii=True, sort_keys=True)
            if any(needle in text for needle in needles):
                return True
    return False


def _implement_v2_next_action(summary, *, external_reward=None):
    if not summary:
        return ""
    if str(summary.get("lane_status") or "") == "completed" and bool(summary.get("replay_valid", True)):
        if external_reward == 0.0:
            return (
                "debug implement_v2 divergence: external verifier reward 0 after v2 completed; "
                "inspect verifier stdout and repair finish acceptance gate before another live speed run"
            )
        return "record implement_v2 pass and continue M6.24 scoped parity"
    model_error = summary.get("model_error") if isinstance(summary.get("model_error"), dict) else {}
    if model_error.get("failure_class") == "model_json_parse_error":
        return "debug implement_v2 divergence: repair model_json parse failure before another live speed run"
    latest = summary.get("latest_failure") if isinstance(summary.get("latest_failure"), dict) else {}
    if summary.get("active_command_closeout_failed"):
        return "debug implement_v2 divergence: repair active command closeout before another live speed run"
    if summary.get("tool_contract_shell_surface_misuse") and not summary.get("tool_contract_recovery_observed"):
        return (
            "debug implement_v2 divergence: recover run_tests shell-surface verifier through "
            "run_command before another live speed run"
        )
    if summary.get("tool_contract_shell_surface_misuse_seen") and latest:
        tool = latest.get("tool_name") or "tool"
        return f"debug implement_v2 divergence: inspect latest failed {tool} result before another live speed run"
    first_write_stall = (
        summary.get("first_write_frontier_stall")
        if isinstance(summary.get("first_write_frontier_stall"), dict)
        else {}
    )
    if first_write_stall.get("detected"):
        target = str(first_write_stall.get("target_path") or "the missing target file")
        return (
            "debug implement_v2 divergence: first_write_frontier_stall after cheap source/probe evidence; "
            f"create or update {target} with write_file/edit_file/apply_patch before another live speed run"
        )
    missing_external = summary.get("external_expected_artifact_missing")
    if missing_external and _implement_v2_runtime_producer_blocked(summary, latest):
        preview = ", ".join(str(item) for item in list(missing_external)[:3])
        return (
            "debug implement_v2 divergence: runtime producer/resource/syscall frontier blocked before "
            f"external verifier artifact {preview}; inspect producer stdout/stderr, runtime resources, "
            "syscall/ABI behavior, and the producing substep before another live speed run"
        )
    if missing_external:
        preview = ", ".join(str(item) for item in list(missing_external)[:3])
        return (
            "debug implement_v2 divergence: external verifier expected runtime artifact "
            f"{preview} but internal structured final proof did not create it; "
            "align the final runtime artifact contract before another live speed run"
        )
    if external_reward == 0.0 and _implement_v2_external_runtime_artifact_lifecycle_gap(summary):
        missing = summary.get("external_verifier_missing_artifacts") or []
        preview = ", ".join(str(item) for item in list(missing)[:3])
        cleanup_note = (
            "cleanup was recorded; "
            if summary.get("post_run_cleanup_present")
            else "no deferred cleanup was recorded; "
        )
        return (
            "debug implement_v2 divergence: runtime_artifact_latency_contract gap for "
            f"{preview}; {cleanup_note}require an external-verifier-shaped lifecycle/cwd/latency "
            "proof and clean verifier-visible runtime artifacts before another live speed run"
        )
    if latest.get("failure_class") == "runtime_artifact_missing":
        required_next_probe = str(latest.get("required_next_probe") or "inspect the producing substep and artifact path")
        return (
            "debug implement_v2 divergence: expected runtime artifact is missing after structured verifier evidence; "
            f"{required_next_probe} before another live speed run"
        )
    if summary.get("runtime_artifact_contract_mismatch"):
        return (
            "debug implement_v2 divergence: compare runtime artifact ABI/ISA/endianness/entrypoint "
            "with the VM/emulator loader contract before another live speed run"
        )
    if model_error.get("failure_class") == "max_turns_before_finish":
        if latest:
            tool = latest.get("tool_name") or "tool"
            return (
                "debug implement_v2 divergence: max-turn limit reached after latest failed "
                f"{tool} result; resume from that terminal failure before another live speed run"
            )
        return "debug implement_v2 divergence: max-turn limit reached before finish; inspect lane loop budget before another live speed run"
    if model_error:
        return "debug implement_v2 divergence: inspect model backend failure before another live speed run"
    if summary.get("hard_runtime_frontier_present") and latest:
        tool = latest.get("tool_name") or "tool"
        return f"debug implement_v2 divergence: inspect latest failed {tool} result before another live speed run"
    if not summary.get("compiled_source_frontier_observed"):
        return "debug implement_v2 divergence: broaden compiled/native source frontier before another live speed run"
    if latest:
        tool = latest.get("tool_name") or "tool"
        return f"debug implement_v2 divergence: inspect latest failed {tool} result before another live speed run"
    return "debug implement_v2 divergence before another live speed run"


def _implement_v2_external_runtime_artifact_lifecycle_gap(summary):
    if not isinstance(summary, dict):
        return False
    missing = [str(item or "") for item in summary.get("external_verifier_missing_artifacts") or []]
    passed = {str(item or "").casefold() for item in summary.get("passed_structured_artifacts") or []}
    if not missing or not passed:
        return False
    for artifact in missing:
        lowered = artifact.casefold()
        if lowered.startswith("/tmp/") and lowered in passed:
            return True
    return False


def _implement_v2_runtime_producer_blocked(summary, latest):
    if not isinstance(summary, dict) or not isinstance(latest, dict):
        return False
    if latest.get("failure_class") != "runtime_artifact_missing":
        return False
    passed = summary.get("passed_structured_artifacts")
    if isinstance(passed, list) and passed:
        return False
    phase = str(latest.get("failure_phase") or "").lower()
    exit_code = latest.get("exit_code")
    nonzero_exit = exit_code not in (None, 0, "0")
    stdout_tail = str(latest.get("stdout_tail") or "").strip()
    if phase == "runtime" and nonzero_exit and stdout_tail:
        return True
    text = " ".join(
        str(latest.get(key) or "")
        for key in (
            "stdout_tail",
            "stderr_tail",
            "reason",
            "summary",
            "required_next_probe",
        )
    ).lower()
    progress_markers = (
        "frames will be saved",
        "trying iwad",
        "-iwad",
        "vm_status=",
        "unhandled syscall",
        "program terminated",
        "no_frame",
        "bmp_missing",
        "frame missing",
    )
    return any(marker in text for marker in progress_markers)


def _task_from_report(report, resume):
    task_id = report.get("task_id") or resume.get("task_id") or 1
    return {
        "id": task_id,
        "title": resume.get("title") or "terminal-bench replay task",
        "description": resume.get("goal") or "",
        "status": "ready",
        "kind": "coding",
    }


def _session_from_report(report):
    resume = _primary_resume(report)
    work_report = report.get("work_report") if isinstance(report.get("work_report"), dict) else {}
    session_id = work_report.get("session_id") or report.get("session_id") or resume.get("session_id") or 1
    task_id = work_report.get("task_id") or report.get("task_id") or resume.get("task_id") or 1
    long_build_state = resume.get("long_build_state") if isinstance(resume.get("long_build_state"), dict) else {}
    session = {
        "id": session_id,
        "task_id": task_id,
        "status": "active",
        "title": resume.get("title") or "terminal-bench replay task",
        "goal": resume.get("goal") or "",
        "updated_at": resume.get("updated_at") or now_iso(),
        "tool_calls": _tool_calls_from_work_report(report),
        "model_turns": _model_turns_from_work_report(report),
        "long_command_runs": list(long_build_state.get("long_command_runs") or []),
        "default_options": {"verify_disabled": True},
        "_allow_synthesized_command_evidence": True,
    }
    frontier = resume.get("active_compatibility_frontier")
    if isinstance(frontier, dict) and frontier:
        session["active_compatibility_frontier"] = dict(frontier)
    return session


def _summarize_active_compatibility_frontier(frontier):
    frontier = frontier if isinstance(frontier, dict) else {}
    if not frontier:
        return {}
    signature = frontier.get("failure_signature") if isinstance(frontier.get("failure_signature"), dict) else {}
    closure = frontier.get("closure_state") if isinstance(frontier.get("closure_state"), dict) else {}
    compact = frontier.get("compact_summary") if isinstance(frontier.get("compact_summary"), dict) else {}
    candidates = frontier.get("open_candidates") or frontier.get("sibling_candidates") or compact.get("open_candidates") or []
    open_candidate_ids = []
    for candidate in candidates:
        if isinstance(candidate, dict):
            status = str(candidate.get("status") or "unexplored")
            if status in {"verified", "rejected", "deferred"}:
                continue
            if candidate.get("id"):
                open_candidate_ids.append(candidate.get("id"))
        elif candidate:
            open_candidate_ids.append(str(candidate))
    next_action = closure.get("next_action") or compact.get("next_action") or ""
    return {
        "id": frontier.get("id") or "",
        "status": frontier.get("status") or "",
        "signature": signature.get("fingerprint") or compact.get("failure_signature") or "",
        "kind": signature.get("kind") or "",
        "family_key": signature.get("family_key") or "",
        "runtime_component_kind": signature.get("runtime_component_kind") or "",
        "next_action": next_action,
        "guard_mode": closure.get("guard_mode") or compact.get("guard_mode") or "",
        "blocked_action_kinds": list(closure.get("blocked_action_kinds") or compact.get("blocked_action_kinds") or []),
        "open_candidate_count": len(open_candidate_ids),
        "open_candidate_ids": open_candidate_ids[:8],
        "evidence_ref_count": len(frontier.get("evidence_refs") or compact.get("evidence_refs") or []),
    }


def _summarize_long_build_state(state):
    if not isinstance(state, dict) or not state:
        return {}
    current_failure = state.get("current_failure") if isinstance(state.get("current_failure"), dict) else {}
    recovery_decision = state.get("recovery_decision") if isinstance(state.get("recovery_decision"), dict) else {}
    allowed_next_action = (
        recovery_decision.get("allowed_next_action")
        if isinstance(recovery_decision.get("allowed_next_action"), dict)
        else {}
    )
    return {
        "status": state.get("status") or "",
        "incomplete_reason": state.get("incomplete_reason") or "",
        "latest_build_status": state.get("latest_build_status") or "",
        "latest_long_command_run_id": state.get("latest_long_command_run_id") or "",
        "latest_long_command_status": state.get("latest_long_command_status") or "",
        "current_failure_class": current_failure.get("failure_class") or "",
        "current_failure_status": current_failure.get("status") or "",
        "recovery_decision": recovery_decision.get("decision") or "",
        "recovery_action_kind": allowed_next_action.get("kind") or "",
        "strategy_blockers": [
            item.get("code") for item in state.get("strategy_blockers") or [] if isinstance(item, dict)
        ],
        "missing_artifacts": [
            item.get("path") for item in state.get("missing_artifacts") or [] if isinstance(item, dict)
        ],
    }


def _trial_report_paths(root):
    root = Path(root).expanduser()
    if root.is_file() and root.name == "mew-report.json":
        return [root.resolve(strict=False)]
    if not root.exists():
        return []
    reports = sorted(root.rglob("mew-report.json"))
    return [path.resolve(strict=False) for path in reports]


def _trial_entry_from_report(report_path):
    report_path = Path(report_path)
    report = _read_json(report_path)
    trial_dir = _find_parent_with_result(report_path)
    trial_result = _read_json(trial_dir / "result.json")
    transcript = _read_json(report_path.parent / "command-transcript.json")
    stored_resume = _primary_resume(report)
    session = _session_from_report(report)
    task = _task_from_report(report, stored_resume)
    implement_v2_replay = _implement_v2_replay_summary(report_path, report)
    reward = _reward_from_trial(trial_dir, trial_result)
    recomputed_resume = {}
    replay_error = ""
    if session.get("tool_calls"):
        try:
            recomputed_resume = build_work_session_resume(session, task=task) or {}
            stored_frontier = stored_resume.get("active_compatibility_frontier")
            if isinstance(stored_frontier, dict) and stored_frontier:
                recomputed_resume["active_compatibility_frontier"] = dict(stored_frontier)
        except Exception as exc:  # pragma: no cover - defensive replay should report, not crash.
            replay_error = str(exc)
    elif implement_v2_replay:
        replay_valid = bool(implement_v2_replay.get("replay_valid"))
        if replay_valid:
            recomputed_resume = {
                "phase": "implement_v2_replay",
                "next_action": _implement_v2_next_action(implement_v2_replay, external_reward=reward),
                "implement_v2": dict(implement_v2_replay),
            }
        else:
            replay_error = "implement_v2 proof manifest reported replay_valid=false"
    else:
        replay_error = "work_report steps did not contain replayable tool calls"
    verifier_stdout = _read_text(trial_dir / "verifier" / "test-stdout.txt")
    stored_long = _summarize_long_build_state(stored_resume.get("long_build_state") or {})
    current_long = _summarize_long_build_state(recomputed_resume.get("long_build_state") or {})
    stored_frontier = _summarize_active_compatibility_frontier(stored_resume.get("active_compatibility_frontier"))
    current_frontier = _summarize_active_compatibility_frontier(
        recomputed_resume.get("active_compatibility_frontier")
    )
    llm_action_fixtures = _llm_action_fixtures_from_work_report(report)
    return {
        "trial_name": _trial_name_from_result(trial_result, trial_dir),
        "trial_dir": str(trial_dir),
        "report_path": str(report_path),
        "command_transcript_path": str(report_path.parent / "command-transcript.json"),
        "result_path": str(trial_dir / "result.json"),
        "verifier_stdout_path": str(trial_dir / "verifier" / "test-stdout.txt"),
        "external_reward": reward,
        "mew_exit_code": report.get("work_exit_code"),
        "stop_reason": (report.get("work_report") or {}).get("stop_reason") or "",
        "wall_timeout": bool((report.get("work_report") or {}).get("wall_timeout")),
        "command_exit_code": transcript.get("exit_code") if isinstance(transcript, dict) else None,
        "command_timed_out": bool(transcript.get("timed_out")) if isinstance(transcript, dict) else False,
        "llm_action_fixture_count": len(llm_action_fixtures),
        "latest_llm_action_fixture": llm_action_fixtures[-1] if llm_action_fixtures else {},
        "stored": {
            "phase": stored_resume.get("phase") or "",
            "next_action": stored_resume.get("next_action") or "",
            "long_build_state": stored_long,
            "active_compatibility_frontier": stored_frontier,
        },
        "current": {
            "recomputed": bool(recomputed_resume),
            "replay_error": replay_error,
            "phase": recomputed_resume.get("phase") or "",
            "next_action": recomputed_resume.get("next_action") or "",
            "long_build_state": current_long,
            "active_compatibility_frontier": current_frontier,
            "implement_v2": recomputed_resume.get("implement_v2") or {},
        },
        "verifier_stdout_excerpt": "\n".join((verifier_stdout or "").splitlines()[-12:]),
    }


def terminal_bench_llm_action_fixture_contexts(job_dir, *, task=None, trial=None):
    """Return replay contexts for model-chosen actions saved in Harbor artifacts.

    The provider's exact raw text is not persisted in all historical artifacts.
    This exposes the raw action JSON that mew parsed from each model turn, plus
    the reconstructed session/task needed to re-run policy checks around that
    action without rerunning Harbor.
    """
    contexts = []
    for report_path in _trial_report_paths(job_dir):
        report_path = Path(report_path)
        report = _read_json(report_path)
        trial_dir = _find_parent_with_result(report_path)
        trial_result = _read_json(trial_dir / "result.json")
        trial_name = _trial_name_from_result(trial_result, trial_dir)
        if task and task not in trial_name and task not in str(trial_dir):
            continue
        if trial and trial != trial_name and trial not in str(trial_dir):
            continue
        stored_resume = _primary_resume(report)
        session = _session_from_report(report)
        task_data = _task_from_report(report, stored_resume)
        for fixture in _llm_action_fixtures_from_work_report(report):
            contexts.append(
                {
                    "trial_name": trial_name,
                    "trial_dir": str(trial_dir),
                    "report_path": str(report_path),
                    "fixture": fixture,
                    "session": session,
                    "task": task_data,
                }
            )
    return contexts


def _check_assertions(entry, assertions):
    checks = []
    current_long = ((entry.get("current") or {}).get("long_build_state") or {})

    def add(name, passed, observed, expected):
        checks.append({"name": name, "passed": bool(passed), "observed": observed, "expected": expected})

    expected = assertions.get("long_build_status")
    if expected:
        observed = current_long.get("status") or ""
        add("long_build_status", observed == expected, observed, expected)
    expected = assertions.get("current_failure")
    if expected:
        observed = current_long.get("current_failure_class") or ""
        add("current_failure", observed == expected, observed, expected)
    expected = assertions.get("recovery_action")
    if expected:
        observed = current_long.get("recovery_action_kind") or ""
        add("recovery_action", observed == expected, observed, expected)
    for blocker in assertions.get("blockers") or []:
        observed = current_long.get("strategy_blockers") or []
        add(f"blocker:{blocker}", blocker in observed, observed, blocker)
    expected = assertions.get("mew_exit_code")
    if expected is not None:
        observed = entry.get("mew_exit_code")
        add("mew_exit_code", observed == expected, observed, expected)
    expected = assertions.get("external_reward")
    if expected is not None:
        observed = entry.get("external_reward")
        add("external_reward", observed == expected, observed, expected)
    expected = assertions.get("next_action_contains")
    if expected:
        observed = (entry.get("current") or {}).get("next_action") or ""
        add("next_action_contains", expected in observed, observed, expected)
    current_v2 = ((entry.get("current") or {}).get("implement_v2") or {})
    structured_replay = current_v2.get("structured_execution_replay") if isinstance(current_v2, dict) else {}
    if assertions.get("structured_execution_replay_required"):
        observed = (structured_replay or {}).get("classification_count") if isinstance(structured_replay, dict) else 0
        add("structured_execution_replay_required", int(observed or 0) > 0, observed, ">=1 structured classification")
    expected = assertions.get("structured_failure_class")
    if expected:
        latest_structured = (
            (structured_replay or {}).get("latest_failure_classification")
            if isinstance(structured_replay, dict)
            else {}
        )
        observed = latest_structured.get("class") if isinstance(latest_structured, dict) else ""
        add("structured_failure_class", observed == expected, observed, expected)
    expected = assertions.get("structured_replay_mismatch_count")
    if expected is not None:
        observed = (structured_replay or {}).get("mismatch_count") if isinstance(structured_replay, dict) else None
        add("structured_replay_mismatch_count", observed == expected, observed, expected)
    expected = assertions.get("source_output_contract_path")
    if expected:
        observed = current_v2.get("source_output_contract_path") if isinstance(current_v2, dict) else ""
        add("source_output_contract_path", observed == expected, observed, expected)
    current_frontier = ((entry.get("current") or {}).get("active_compatibility_frontier") or {})
    expected = assertions.get("frontier_signature")
    if expected:
        observed = current_frontier.get("signature") or ""
        add("frontier_signature", observed == expected, observed, expected)
    if assertions.get("frontier_signature_required"):
        observed = current_frontier.get("signature") or ""
        add("frontier_signature_required", bool(observed), observed, "non-empty frontier signature")
    stored_frontier = ((entry.get("stored") or {}).get("active_compatibility_frontier") or {})
    if assertions.get("frontier_signature_matches_stored"):
        observed = current_frontier.get("signature") or ""
        expected_stored = stored_frontier.get("signature") or ""
        add("frontier_signature_matches_stored", bool(expected_stored) and observed == expected_stored, observed, expected_stored)
    expected = assertions.get("frontier_family_key")
    if expected:
        observed = current_frontier.get("family_key") or ""
        add("frontier_family_key", observed == expected, observed, expected)
    if assertions.get("frontier_family_key_matches_stored"):
        observed = current_frontier.get("family_key") or ""
        expected_stored = stored_frontier.get("family_key") or ""
        add("frontier_family_key_matches_stored", bool(expected_stored) and observed == expected_stored, observed, expected_stored)
    expected = assertions.get("frontier_next_action_contains")
    if expected:
        observed = current_frontier.get("next_action") or ""
        add("frontier_next_action_contains", expected in observed, observed, expected)
    if assertions.get("frontier_next_action_required"):
        observed = current_frontier.get("next_action") or ""
        add("frontier_next_action_required", bool(observed), observed, "non-empty frontier next_action")
    if assertions.get("frontier_next_action_matches_stored"):
        observed = current_frontier.get("next_action") or ""
        expected_stored = stored_frontier.get("next_action") or ""
        add("frontier_next_action_matches_stored", bool(expected_stored) and observed == expected_stored, observed, expected_stored)
    expected = assertions.get("frontier_open_candidate_count_min")
    if expected is not None:
        observed = current_frontier.get("open_candidate_count") or 0
        add("frontier_open_candidate_count_min", observed >= int(expected), observed, f">={expected}")
    if assertions.get("frontier_open_candidate_ids_match_stored"):
        observed = current_frontier.get("open_candidate_ids") or []
        expected_stored = stored_frontier.get("open_candidate_ids") or []
        add(
            "frontier_open_candidate_ids_match_stored",
            bool(expected_stored) and observed == expected_stored,
            observed,
            expected_stored,
        )
    expected = assertions.get("frontier_evidence_ref_count_min")
    if expected is not None:
        observed = current_frontier.get("evidence_ref_count") or 0
        add("frontier_evidence_ref_count_min", observed >= int(expected), observed, f">={expected}")
    if assertions.get("frontier_evidence_ref_count_matches_stored"):
        observed = current_frontier.get("evidence_ref_count") or 0
        expected_stored = stored_frontier.get("evidence_ref_count") or 0
        add(
            "frontier_evidence_ref_count_matches_stored",
            expected_stored > 0 and observed == expected_stored,
            observed,
            expected_stored,
        )
    return checks


def replay_terminal_bench_job(
    job_dir,
    *,
    task=None,
    trial=None,
    assertions=None,
):
    job_dir = Path(job_dir).expanduser().resolve(strict=False)
    assertions = dict(assertions or {})
    report_paths = _trial_report_paths(job_dir)
    entries = []
    for report_path in report_paths:
        entry = _trial_entry_from_report(report_path)
        if task and task not in entry.get("trial_name", "") and task not in entry.get("trial_dir", ""):
            continue
        if trial and trial != entry.get("trial_name") and trial not in entry.get("trial_dir", ""):
            continue
        entry["checks"] = _check_assertions(entry, assertions)
        entries.append(entry)
    stats = _root_stats(job_dir if job_dir.is_dir() else job_dir.parent)
    checks = []
    if not entries:
        checks.append(
            {
                "name": "replay_artifacts_found",
                "passed": False,
                "observed": str(job_dir),
                "expected": "at least one mew-report.json under job_dir",
            }
        )
    for entry in entries:
        checks.extend(entry.get("checks") or [])
        checks.append(
            {
                "name": f"{entry.get('trial_name')}:recomputed_resume",
                "passed": bool((entry.get("current") or {}).get("recomputed")),
                "observed": (entry.get("current") or {}).get("replay_error") or "ok",
                "expected": "current resume rebuilt from work_report steps",
            }
        )
        current_v2 = ((entry.get("current") or {}).get("implement_v2") or {})
        structured_replay = current_v2.get("structured_execution_replay") if isinstance(current_v2, dict) else {}
        expected_mismatch_count = None
        if isinstance(assertions, dict):
            expected_mismatch_count = assertions.get("structured_replay_mismatch_count")
        if (
            isinstance(structured_replay, dict)
            and structured_replay.get("mismatch_count")
            and structured_replay.get("mismatch_count") != expected_mismatch_count
        ):
            checks.append(
                {
                    "name": f"{entry.get('trial_name')}:structured_execution_classification_matches",
                    "passed": False,
                    "observed": structured_replay.get("mismatches") or [],
                    "expected": "stored failure_classification matches replay-recomputed classification",
                }
            )
    return {
        "kind": "terminal_bench_replay",
        "schema_version": 1,
        "generated_at": now_iso(),
        "job_dir": str(job_dir),
        "task_filter": task or "",
        "trial_filter": trial or "",
        "root_stats": stats,
        "trial_count": len(entries),
        "status": "pass" if all(check.get("passed") for check in checks) else "fail",
        "checks": checks,
        "trials": entries,
    }


def format_terminal_bench_replay(report):
    lines = [
        f"terminal-bench replay: {report.get('status')} trials={report.get('trial_count')}",
        f"job_dir: {report.get('job_dir')}",
    ]
    for entry in report.get("trials") or []:
        current_long = ((entry.get("current") or {}).get("long_build_state") or {})
        current_v2 = ((entry.get("current") or {}).get("implement_v2") or {})
        lines.append("")
        lines.append(
            f"- {entry.get('trial_name')} reward={entry.get('external_reward')} "
            f"mew_exit={entry.get('mew_exit_code')} stop={entry.get('stop_reason') or '-'}"
        )
        lines.append(
            "  current_long_build: "
            f"status={current_long.get('status') or '-'} "
            f"failure={current_long.get('current_failure_class') or '-'} "
            f"recovery={current_long.get('recovery_action_kind') or '-'}"
        )
        blockers = current_long.get("strategy_blockers") or []
        if blockers:
            lines.append(f"  blockers: {', '.join(str(item) for item in blockers)}")
        if current_v2:
            structured_replay = current_v2.get("structured_execution_replay")
            latest_structured = (
                structured_replay.get("latest_failure_classification")
                if isinstance(structured_replay, dict)
                else {}
            )
            lines.append(
                "  implement_v2: "
                f"status={current_v2.get('lane_status') or '-'} "
                f"turns={current_v2.get('history_turn_count') or 0} "
                f"tool_results={current_v2.get('tool_result_count') or 0} "
                f"compiled_frontier={current_v2.get('compiled_source_frontier_observed')} "
                f"tool_contract_misuse={current_v2.get('tool_contract_shell_surface_misuse')}"
            )
            if isinstance(structured_replay, dict) and structured_replay.get("classification_count"):
                lines.append(
                    "  structured_execution: "
                    f"classifications={structured_replay.get('classification_count')} "
                    f"mismatches={structured_replay.get('mismatch_count')} "
                    f"latest={latest_structured.get('class') or '-'}"
                )
    failed = [check for check in report.get("checks") or [] if not check.get("passed")]
    if failed:
        lines.append("")
        lines.append("failed checks:")
        for check in failed:
            lines.append(f"- {check.get('name')}: observed={check.get('observed')} expected={check.get('expected')}")
    return "\n".join(lines)
