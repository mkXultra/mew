"""M6.13 deliberation-lane policy primitives.

The deliberation lane is intentionally split into pure decision helpers before
it is wired into the work loop. This keeps model binding, blocker eligibility,
budget accounting, and fallback reasons testable without starting model calls.
"""

from __future__ import annotations

from collections.abc import Mapping

from .reasoning_policy import normalize_reasoning_effort
from .work_lanes import DELIBERATION_LANE, TINY_LANE

DELIBERATION_RESULT_SCHEMA_CONTRACT = "deliberation_result_v1"
DELIBERATION_BUDGET_POLICY_VERSION = "m6_13.v0"

DELIBERATION_COST_EVENT_BUDGET_CHECKED = "budget_checked"
DELIBERATION_COST_EVENT_BUDGET_RESERVED = "budget_reserved"
DELIBERATION_COST_EVENT_BUDGET_BLOCKED = "budget_blocked"
DELIBERATION_COST_EVENT_FALLBACK_TO_TINY = "fallback_to_tiny"

STATE_LIMIT_BLOCKER_CODES = frozenset(
    {
        "missing_exact_cached_window_texts",
        "cached_window_incomplete",
        "cached_window_text_truncated",
        "stale_cached_window_text",
        "old_text_not_found",
    }
)
CONTRACT_LIMIT_BLOCKER_CODES = frozenset(
    {
        "ambiguous_old_text_match",
        "overlapping_hunks",
    }
)
POLICY_LIMIT_BLOCKER_CODES = frozenset(
    {
        "unpaired_source_edit_blocked",
        "write_policy_violation",
    }
)
REVIEWER_COMMAND_ELIGIBLE_BLOCKER_CODES = frozenset(
    {
        "review_rejected",
        "no_material_change",
        "model_returned_refusal",
        "model_returned_non_schema",
    }
)
AUTOMATIC_ELIGIBLE_BLOCKER_CODES = frozenset({"review_rejected"})
ABSTRACT_TASK_SHAPES = frozenset({"abstract", "repeated", "design", "conceptual", "cross_file"})
DELIBERATION_RESULT_DECISIONS = frozenset(
    {
        "propose_patch_strategy",
        "decline_escalation",
        "needs_state_refresh",
    }
)
DELIBERATION_RECOMMENDED_NEXT = frozenset(
    {
        "retry_tiny",
        "refresh_state",
        "ask_reviewer",
        "finish_blocked",
    }
)
DELIBERATION_CONFIDENCE_VALUES = frozenset({"low", "medium", "high"})


def _text(value: object) -> str:
    return str(value or "").strip()


def _positive_int(value: object) -> int:
    try:
        parsed = int(value or 0)
    except (TypeError, ValueError):
        return 0
    return parsed if parsed > 0 else 0


def _non_negative_int(value: object) -> int:
    try:
        parsed = int(value or 0)
    except (TypeError, ValueError):
        return 0
    return parsed if parsed > 0 else 0


def normalize_deliberation_binding(binding: Mapping[str, object] | None) -> dict[str, object]:
    """Return requested/effective model binding fields for one attempt."""

    binding = binding if isinstance(binding, Mapping) else {}
    requested_backend = _text(binding.get("backend") or binding.get("requested_backend"))
    requested_model = _text(binding.get("model") or binding.get("requested_model"))
    requested_effort = _text(
        binding.get("requested_effort")
        or binding.get("effort")
        or binding.get("reasoning_effort")
    ).casefold()
    effective_backend = _text(binding.get("effective_backend") or requested_backend)
    effective_model = _text(binding.get("effective_model") or requested_model)
    effective_effort = normalize_reasoning_effort(
        binding.get("effective_effort") or requested_effort
    )
    timeout_seconds = _positive_int(
        binding.get("timeout_seconds") or binding.get("timeout") or 0
    )
    schema_contract = _text(binding.get("schema_contract")) or DELIBERATION_RESULT_SCHEMA_CONTRACT

    if not requested_effort:
        effort_resolution_reason = "missing_effort"
    elif not effective_effort:
        effort_resolution_reason = "unsupported_effort"
    elif requested_effort != effective_effort:
        effort_resolution_reason = "remapped"
    else:
        effort_resolution_reason = "accepted"

    missing_fields = []
    for field, value in (
        ("backend", effective_backend),
        ("model", effective_model),
        ("effort", effective_effort),
        ("timeout_seconds", timeout_seconds),
        ("schema_contract", schema_contract),
    ):
        if not value:
            missing_fields.append(field)

    return {
        "configured": not missing_fields,
        "missing_fields": missing_fields,
        "requested_backend": requested_backend,
        "requested_model": requested_model,
        "requested_effort": requested_effort,
        "effective_backend": effective_backend,
        "effective_model": effective_model,
        "effective_effort": effective_effort,
        "effort_resolution_reason": effort_resolution_reason,
        "timeout_seconds": timeout_seconds,
        "schema_contract": schema_contract,
    }


def _build_lane_attempt_id(todo_id: str, attempt_number: int) -> str:
    return f"lane-{DELIBERATION_LANE}-{todo_id}-attempt-{attempt_number}"


def _budget_snapshot(
    *,
    max_attempts_per_todo: int,
    attempts_used: int,
    reserved_units: int = 0,
) -> dict[str, object]:
    remaining = max(0, max_attempts_per_todo - attempts_used - reserved_units)
    return {
        "session_cap": {},
        "iteration_cap": {},
        "task_cap": {"attempts": max_attempts_per_todo},
        "reserved": {"attempts": reserved_units},
        "spent": {"attempts": attempts_used},
        "remaining": {"attempts": remaining},
        "budget_policy_version": DELIBERATION_BUDGET_POLICY_VERSION,
    }


def _cost_event(
    event: str,
    *,
    todo_id: str,
    lane_attempt_id: str,
    reason: str = "",
    max_attempts_per_todo: int = 0,
    attempts_used: int = 0,
    reserved_units: int = 0,
    created_at: str = "",
) -> dict[str, object]:
    remaining_units = max(0, max_attempts_per_todo - attempts_used - reserved_units)
    payload = {
        "event": event,
        "todo_id": todo_id,
        "lane_attempt_id": lane_attempt_id,
        "cap_scope": "task",
        "reserved_units": reserved_units,
        "remaining_units": remaining_units,
        "created_at": created_at,
    }
    if reason:
        payload["reason"] = reason
    return payload


def _block_decision(
    *,
    todo_id: str,
    blocker_code: str,
    lane_attempt_id: str,
    reason: str,
    binding: dict[str, object],
    budget_snapshot: dict[str, object] | None = None,
    cost_events: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "allowed": False,
        "decision": "fallback",
        "reason": reason,
        "lane": DELIBERATION_LANE,
        "fallback_lane": TINY_LANE,
        "todo_id": todo_id,
        "blocker_code": blocker_code,
        "lane_attempt_id": lane_attempt_id,
        "binding": binding,
        "budget_snapshot": budget_snapshot or {},
        "cost_events": list(cost_events or []),
    }


def _blocker_is_eligible(
    blocker_code: str,
    *,
    reviewer_commanded: bool,
    auto_deliberation_enabled: bool,
    task_shape: str,
    repeated: bool,
    refusal_classified: bool,
) -> tuple[bool, str]:
    task_shape = _text(task_shape).casefold()
    if blocker_code in STATE_LIMIT_BLOCKER_CODES:
        return False, "state_refresh_required"
    if blocker_code in CONTRACT_LIMIT_BLOCKER_CODES:
        return False, "contract_repair_required"
    if blocker_code in POLICY_LIMIT_BLOCKER_CODES:
        return False, "policy_limit"

    if reviewer_commanded:
        if blocker_code not in REVIEWER_COMMAND_ELIGIBLE_BLOCKER_CODES:
            return False, "ineligible_reviewer_command"
        if blocker_code == "model_returned_non_schema" and not repeated:
            return False, "schema_retry_required"
        return True, "reviewer_commanded"

    if not auto_deliberation_enabled:
        return False, "auto_deliberation_disabled"

    if blocker_code in AUTOMATIC_ELIGIBLE_BLOCKER_CODES:
        return True, "automatic_eligible"
    if blocker_code == "no_material_change" and (repeated or task_shape in ABSTRACT_TASK_SHAPES):
        return True, "automatic_eligible"
    if blocker_code == "model_returned_refusal" and refusal_classified:
        return True, "automatic_eligible"
    if blocker_code == "model_returned_non_schema" and repeated and task_shape in ABSTRACT_TASK_SHAPES:
        return True, "automatic_eligible"
    return False, "ineligible_blocker"


def evaluate_deliberation_request(
    *,
    todo: Mapping[str, object] | None,
    blocker_code: object,
    binding: Mapping[str, object] | None,
    budget: Mapping[str, object] | None,
    reviewer_commanded: bool = False,
    auto_deliberation_enabled: bool = True,
    task_shape: str = "",
    repeated: bool = False,
    refusal_classified: bool = False,
    stale_state: bool = False,
    created_at: str = "",
) -> dict[str, object]:
    """Evaluate whether a deliberation attempt may run.

    This function deliberately does not call a model. It returns the stable
    request/budget/fallback facts that later work-loop wiring can append to
    session trace state.
    """

    todo = todo if isinstance(todo, Mapping) else {}
    todo_id = _text(todo.get("id"))
    code = _text(blocker_code)
    configured_binding = normalize_deliberation_binding(binding)
    budget = budget if isinstance(budget, Mapping) else {}
    max_attempts = _positive_int(budget.get("max_attempts_per_todo"))
    attempts_used = _non_negative_int(budget.get("attempts_used"))
    attempt_number = attempts_used + 1
    lane_attempt_id = _build_lane_attempt_id(todo_id or "missing-todo", attempt_number)

    empty_budget = _budget_snapshot(
        max_attempts_per_todo=max_attempts,
        attempts_used=attempts_used,
    )
    if not todo_id:
        return _block_decision(
            todo_id=todo_id,
            blocker_code=code,
            lane_attempt_id=lane_attempt_id,
            reason="missing_todo_id",
            binding=configured_binding,
            budget_snapshot=empty_budget,
        )
    if not code:
        return _block_decision(
            todo_id=todo_id,
            blocker_code=code,
            lane_attempt_id=lane_attempt_id,
            reason="missing_blocker_code",
            binding=configured_binding,
            budget_snapshot=empty_budget,
        )
    if stale_state:
        return _block_decision(
            todo_id=todo_id,
            blocker_code=code,
            lane_attempt_id=lane_attempt_id,
            reason="state_refresh_required",
            binding=configured_binding,
            budget_snapshot=empty_budget,
        )

    eligible, eligibility_reason = _blocker_is_eligible(
        code,
        reviewer_commanded=bool(reviewer_commanded),
        auto_deliberation_enabled=bool(auto_deliberation_enabled),
        task_shape=task_shape,
        repeated=bool(repeated),
        refusal_classified=bool(refusal_classified),
    )
    if not eligible:
        return _block_decision(
            todo_id=todo_id,
            blocker_code=code,
            lane_attempt_id=lane_attempt_id,
            reason=eligibility_reason,
            binding=configured_binding,
            budget_snapshot=empty_budget,
        )
    if not configured_binding["configured"]:
        return _block_decision(
            todo_id=todo_id,
            blocker_code=code,
            lane_attempt_id=lane_attempt_id,
            reason="missing_model_binding",
            binding=configured_binding,
            budget_snapshot=empty_budget,
        )

    cost_events = [
        _cost_event(
            DELIBERATION_COST_EVENT_BUDGET_CHECKED,
            todo_id=todo_id,
            lane_attempt_id=lane_attempt_id,
            max_attempts_per_todo=max_attempts,
            attempts_used=attempts_used,
            created_at=created_at,
        )
    ]
    if max_attempts <= 0 or attempts_used >= max_attempts:
        cost_events.append(
            _cost_event(
                DELIBERATION_COST_EVENT_BUDGET_BLOCKED,
                todo_id=todo_id,
                lane_attempt_id=lane_attempt_id,
                reason="budget_exceeded",
                max_attempts_per_todo=max_attempts,
                attempts_used=attempts_used,
                created_at=created_at,
            )
        )
        cost_events.append(
            _cost_event(
                DELIBERATION_COST_EVENT_FALLBACK_TO_TINY,
                todo_id=todo_id,
                lane_attempt_id=lane_attempt_id,
                reason="budget_exceeded",
                max_attempts_per_todo=max_attempts,
                attempts_used=attempts_used,
                created_at=created_at,
            )
        )
        return _block_decision(
            todo_id=todo_id,
            blocker_code=code,
            lane_attempt_id=lane_attempt_id,
            reason="budget_exceeded",
            binding=configured_binding,
            budget_snapshot=empty_budget,
            cost_events=cost_events,
        )

    reserved_budget = _budget_snapshot(
        max_attempts_per_todo=max_attempts,
        attempts_used=attempts_used,
        reserved_units=1,
    )
    cost_events.append(
        _cost_event(
            DELIBERATION_COST_EVENT_BUDGET_RESERVED,
            todo_id=todo_id,
            lane_attempt_id=lane_attempt_id,
            max_attempts_per_todo=max_attempts,
            attempts_used=attempts_used,
            reserved_units=1,
            created_at=created_at,
        )
    )
    return {
        "allowed": True,
        "decision": "attempt",
        "reason": eligibility_reason,
        "lane": DELIBERATION_LANE,
        "fallback_lane": TINY_LANE,
        "todo_id": todo_id,
        "blocker_code": code,
        "lane_attempt_id": lane_attempt_id,
        "binding": configured_binding,
        "budget_snapshot": reserved_budget,
        "cost_events": cost_events,
    }


def build_deliberation_attempt_record(decision: Mapping[str, object] | None) -> dict[str, object]:
    """Build the append-only session-trace record for a request decision."""

    decision = decision if isinstance(decision, Mapping) else {}
    binding = decision.get("binding") if isinstance(decision.get("binding"), Mapping) else {}
    budget_snapshot = (
        decision.get("budget_snapshot")
        if isinstance(decision.get("budget_snapshot"), Mapping)
        else {}
    )
    return {
        "lane": _text(decision.get("lane")) or DELIBERATION_LANE,
        "fallback_lane": _text(decision.get("fallback_lane")) or TINY_LANE,
        "lane_attempt_id": _text(decision.get("lane_attempt_id")),
        "todo_id": _text(decision.get("todo_id")),
        "blocker_code": _text(decision.get("blocker_code")),
        "allowed": bool(decision.get("allowed")),
        "decision": _text(decision.get("decision")),
        "reason": _text(decision.get("reason")),
        "requested_backend": _text(binding.get("requested_backend")),
        "requested_model": _text(binding.get("requested_model")),
        "requested_effort": _text(binding.get("requested_effort")),
        "effective_backend": _text(binding.get("effective_backend")),
        "effective_model": _text(binding.get("effective_model")),
        "effective_effort": _text(binding.get("effective_effort")),
        "effort_resolution_reason": _text(binding.get("effort_resolution_reason")),
        "timeout_seconds": _positive_int(binding.get("timeout_seconds")),
        "schema_contract": _text(binding.get("schema_contract")),
        "budget_snapshot": dict(budget_snapshot),
    }


def append_deliberation_decision_to_session(
    session: dict[str, object] | None,
    decision: Mapping[str, object] | None,
) -> dict[str, object]:
    """Append a deliberation decision and cost events to a work-session dict."""

    if not isinstance(session, dict):
        return {}
    attempt = build_deliberation_attempt_record(decision)
    attempts = session.setdefault("deliberation_attempts", [])
    if isinstance(attempts, list):
        attempts.append(attempt)
    else:
        session["deliberation_attempts"] = [attempt]

    decision = decision if isinstance(decision, Mapping) else {}
    cost_events = decision.get("cost_events") if isinstance(decision.get("cost_events"), list) else []
    existing_cost_events = session.setdefault("deliberation_cost_events", [])
    if not isinstance(existing_cost_events, list):
        existing_cost_events = []
        session["deliberation_cost_events"] = existing_cost_events
    for event in cost_events:
        if isinstance(event, Mapping):
            existing_cost_events.append(dict(event))

    session["latest_deliberation_result"] = {
        "lane_attempt_id": attempt.get("lane_attempt_id") or "",
        "status": "reserved" if attempt.get("allowed") else "fallback",
        "reason": attempt.get("reason") or "",
        "fallback_lane": attempt.get("fallback_lane") or TINY_LANE,
    }
    return attempt


def build_deliberation_fallback_event(
    *,
    reason: str,
    todo_id: object,
    blocker_code: object,
    lane_attempt_id: object = "",
    created_at: str = "",
) -> dict[str, object]:
    """Build the stable v0 fallback event shape for a failed attempt."""

    return {
        "event": "deliberation_fallback",
        "reason": _text(reason),
        "fallback_lane": TINY_LANE,
        "todo_id": _text(todo_id),
        "blocker_code": _text(blocker_code),
        "lane_attempt_id": _text(lane_attempt_id),
        "created_at": _text(created_at),
    }


def validate_deliberation_result(
    payload: Mapping[str, object] | None,
    *,
    todo_id: object,
    blocker_code: object,
) -> dict[str, object]:
    """Validate the v1 read-only deliberation result contract."""

    if not isinstance(payload, Mapping):
        return {"ok": False, "reason": "non_schema", "result": {}}

    result = {
        "kind": _text(payload.get("kind")),
        "schema_version": payload.get("schema_version"),
        "todo_id": _text(payload.get("todo_id")),
        "lane": _text(payload.get("lane")),
        "blocker_code": _text(payload.get("blocker_code")),
        "decision": _text(payload.get("decision")),
        "situation": _text(payload.get("situation")),
        "reasoning_summary": _text(payload.get("reasoning_summary")),
        "recommended_next": _text(payload.get("recommended_next")),
        "expected_trace_candidate": bool(payload.get("expected_trace_candidate")),
        "confidence": _text(payload.get("confidence")),
    }

    expected_todo_id = _text(todo_id)
    expected_blocker_code = _text(blocker_code)
    required_failures = []
    if result["kind"] != "deliberation_result":
        required_failures.append("kind")
    if result["schema_version"] != 1:
        required_failures.append("schema_version")
    if result["todo_id"] != expected_todo_id:
        required_failures.append("todo_id")
    if result["lane"] != DELIBERATION_LANE:
        required_failures.append("lane")
    if result["blocker_code"] != expected_blocker_code:
        required_failures.append("blocker_code")
    if result["decision"] not in DELIBERATION_RESULT_DECISIONS:
        required_failures.append("decision")
    if result["recommended_next"] not in DELIBERATION_RECOMMENDED_NEXT:
        required_failures.append("recommended_next")
    if result["confidence"] not in DELIBERATION_CONFIDENCE_VALUES:
        required_failures.append("confidence")
    if not result["situation"]:
        required_failures.append("situation")
    if not result["reasoning_summary"]:
        required_failures.append("reasoning_summary")

    if required_failures:
        return {
            "ok": False,
            "reason": "validation_failed",
            "invalid_fields": required_failures,
            "result": result,
        }
    return {"ok": True, "reason": "", "invalid_fields": [], "result": result}


__all__ = [
    "ABSTRACT_TASK_SHAPES",
    "AUTOMATIC_ELIGIBLE_BLOCKER_CODES",
    "CONTRACT_LIMIT_BLOCKER_CODES",
    "DELIBERATION_BUDGET_POLICY_VERSION",
    "DELIBERATION_COST_EVENT_BUDGET_BLOCKED",
    "DELIBERATION_COST_EVENT_BUDGET_CHECKED",
    "DELIBERATION_COST_EVENT_BUDGET_RESERVED",
    "DELIBERATION_COST_EVENT_FALLBACK_TO_TINY",
    "DELIBERATION_CONFIDENCE_VALUES",
    "DELIBERATION_RECOMMENDED_NEXT",
    "DELIBERATION_RESULT_SCHEMA_CONTRACT",
    "DELIBERATION_RESULT_DECISIONS",
    "POLICY_LIMIT_BLOCKER_CODES",
    "REVIEWER_COMMAND_ELIGIBLE_BLOCKER_CODES",
    "STATE_LIMIT_BLOCKER_CODES",
    "append_deliberation_decision_to_session",
    "build_deliberation_attempt_record",
    "build_deliberation_fallback_event",
    "evaluate_deliberation_request",
    "normalize_deliberation_binding",
    "validate_deliberation_result",
]
