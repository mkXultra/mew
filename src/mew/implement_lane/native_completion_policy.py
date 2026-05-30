"""Completion closeout policy for the native implement lane."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .completion_resolver import CompletionResolverInput, FinishClaim
from .native_transcript import NativeTranscript, NativeTranscriptItem, native_transcript_hash
from .types import ImplementLaneInput, ToolResultEnvelope


@dataclass(frozen=True)
class NativeCompletionCloseoutContext:
    closeout_refs: tuple[str, ...] = ()
    fresh_verifier_refs: tuple[str, ...] = ()
    planner_verified_finish_refs: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()
    missing_obligations: tuple[str, ...] = ()
    unsafe_blockers: tuple[str, ...] = ()
    budget_blockers: tuple[str, ...] = ()


def build_completion_resolver_input_from_finish(
    call: NativeTranscriptItem,
    result: ToolResultEnvelope,
    *,
    lane_input: ImplementLaneInput,
    transcript_items: tuple[NativeTranscriptItem, ...],
    arguments: Mapping[str, object],
    outcome: str,
    gate: Mapping[str, object],
    compact_sidecar_digest_hash: str,
    closeout_context: object,
    finish_closeout_context: object,
) -> CompletionResolverInput:
    """Build sidecar-only resolver input from pre-extracted finish facts."""

    blockers: list[str] = []
    missing: list[str] = []
    unsafe_blockers: list[str] = []
    budget_blockers: list[str] = []
    if outcome in {"blocked", "continue"} or arguments.get("task_done") is False:
        blockers.append("finish_claim_not_completed")
    if outcome == "blocked_return" or arguments.get("return_to_supervisor") is True:
        budget_blockers.append("finish_requested_supervisor_return")
    if arguments.get("unsafe_to_continue") is True:
        unsafe_blockers.append("finish_marked_unsafe_to_continue")

    effective_closeout_context = closeout_context_resolved_by_finish_evidence(
        closeout_context,
        finish_closeout_context,
    )
    blockers.extend(finish_arg_strings(arguments.get("blockers")))
    missing.extend(finish_arg_strings(arguments.get("missing_obligations")))
    unsafe_blockers.extend(finish_arg_strings(arguments.get("unsafe_blockers")))
    budget_blockers.extend(finish_arg_strings(arguments.get("budget_blockers")))
    blockers.extend(effective_closeout_context.blockers)
    missing.extend(effective_closeout_context.missing_obligations)
    unsafe_blockers.extend(effective_closeout_context.unsafe_blockers)
    budget_blockers.extend(effective_closeout_context.budget_blockers)

    gate_codes = finish_gate_blocker_codes(gate) if gate else ()
    gate_missing = finish_gate_missing_obligations(gate) if gate else ()
    if (
        gate
        and gate.get("decision") != "allow_complete"
        and not finish_gate_block_resolved_by_closeout(
            gate_codes,
            gate_missing,
            gate=gate,
            closeout_context=effective_closeout_context,
        )
    ):
        blockers.append("finish_gate_blocked")
        blockers.extend(gate_codes)
        missing.extend(gate_missing)

    if (
        outcome == "completed"
        and _task_contract_acceptance_constraints(lane_input)
        and not _completion_evidence_refs_present(
            result=result,
            closeout_context=effective_closeout_context,
        )
    ):
        blockers.append("typed_acceptance_evidence_missing")
        missing.append("strict_verifier_evidence")

    return CompletionResolverInput(
        finish_claim=FinishClaim(
            lane_attempt_id=call.lane_attempt_id,
            turn_id=call.turn_id,
            finish_call_id=call.call_id,
            finish_output_call_id=call.call_id,
            outcome=outcome,
            summary=str(arguments.get("summary") or ""),
            arguments=dict(arguments),
        ),
        transcript_hash_before_decision=native_transcript_hash(
            NativeTranscript(
                lane_attempt_id=call.lane_attempt_id,
                provider=call.provider,
                model=call.model,
                items=transcript_items,
            )
        ),
        compact_sidecar_digest_hash=compact_sidecar_digest_hash,
        typed_evidence_refs=tuple(dict.fromkeys(result.evidence_refs)),
        fresh_verifier_refs=tuple(effective_closeout_context.fresh_verifier_refs),
        missing_obligations=tuple(dict.fromkeys(missing)),
        closeout_refs=tuple(effective_closeout_context.closeout_refs),
        blockers=tuple(dict.fromkeys(blockers)),
        unsafe_blockers=tuple(dict.fromkeys(unsafe_blockers)),
        budget_blockers=tuple(dict.fromkeys(budget_blockers)),
        verifier_required=bool(gate and gate.get("decision") != "allow_complete"),
    )


def closeout_context_resolved_by_finish_evidence(
    closeout_context: object,
    finish_context: object,
) -> NativeCompletionCloseoutContext:
    base = closeout_context_from_object(closeout_context)
    finish = closeout_context_from_object(finish_context)
    if not finish.fresh_verifier_refs:
        return base
    merged = NativeCompletionCloseoutContext(
        closeout_refs=tuple(dict.fromkeys((*base.closeout_refs, *finish.closeout_refs))),
        fresh_verifier_refs=tuple(dict.fromkeys((*base.fresh_verifier_refs, *finish.fresh_verifier_refs))),
        planner_verified_finish_refs=tuple(
            dict.fromkeys((*base.planner_verified_finish_refs, *finish.planner_verified_finish_refs))
        ),
        blockers=tuple(dict.fromkeys((*base.blockers, *finish.blockers))),
        missing_obligations=tuple(dict.fromkeys((*base.missing_obligations, *finish.missing_obligations))),
        unsafe_blockers=tuple(dict.fromkeys((*base.unsafe_blockers, *finish.unsafe_blockers))),
        budget_blockers=tuple(dict.fromkeys((*base.budget_blockers, *finish.budget_blockers))),
    )
    blockers = tuple(
        blocker
        for blocker in merged.blockers
        if blocker
        not in {
            "closeout_verifier_command_missing",
            "closeout_verifier_not_run",
        }
    )
    removed_missing_closeout_blocker = len(blockers) != len(merged.blockers)
    if removed_missing_closeout_blocker:
        missing = tuple(item for item in merged.missing_obligations if item != "strict_verifier_evidence")
    else:
        missing = merged.missing_obligations
    return NativeCompletionCloseoutContext(
        closeout_refs=merged.closeout_refs,
        fresh_verifier_refs=merged.fresh_verifier_refs,
        planner_verified_finish_refs=merged.planner_verified_finish_refs,
        blockers=blockers,
        missing_obligations=missing,
        unsafe_blockers=merged.unsafe_blockers,
        budget_blockers=merged.budget_blockers,
    )


def closeout_context_from_object(value: object) -> NativeCompletionCloseoutContext:
    return NativeCompletionCloseoutContext(
        closeout_refs=text_tuple(getattr(value, "closeout_refs", ())),
        fresh_verifier_refs=text_tuple(getattr(value, "fresh_verifier_refs", ())),
        planner_verified_finish_refs=text_tuple(getattr(value, "planner_verified_finish_refs", ())),
        blockers=text_tuple(getattr(value, "blockers", ())),
        missing_obligations=text_tuple(getattr(value, "missing_obligations", ())),
        unsafe_blockers=text_tuple(getattr(value, "unsafe_blockers", ())),
        budget_blockers=text_tuple(getattr(value, "budget_blockers", ())),
    )


def finish_arg_strings(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,) if value else ()
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(text for item in value if (text := str(item or "").strip()))


def _task_contract_acceptance_constraints(lane_input: ImplementLaneInput) -> tuple[str, ...]:
    task_contract = lane_input.task_contract if isinstance(lane_input.task_contract, Mapping) else {}
    constraints = task_contract.get("acceptance_constraints")
    if not isinstance(constraints, (list, tuple)):
        return ()
    return tuple(text for item in constraints if (text := str(item or "").strip()))


def _completion_evidence_refs_present(
    *,
    result: ToolResultEnvelope,
    closeout_context: NativeCompletionCloseoutContext,
) -> bool:
    return bool(
        result.evidence_refs
        or closeout_context.fresh_verifier_refs
        or closeout_context.closeout_refs
    )


def text_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(text for item in value if (text := str(item or "").strip()))


def finish_gate_blocker_codes(gate: Mapping[str, object]) -> tuple[str, ...]:
    codes: list[str] = []
    blockers = gate.get("blockers")
    if isinstance(blockers, list):
        for blocker in blockers:
            if isinstance(blocker, Mapping):
                code = str(blocker.get("code") or blocker.get("family") or blocker.get("message") or "").strip()
                if code:
                    codes.append(code)
            else:
                text = str(blocker or "").strip()
                if text:
                    codes.append(text)
    return tuple(dict.fromkeys(codes))


def finish_gate_missing_obligations(gate: Mapping[str, object]) -> tuple[str, ...]:
    missing: list[str] = []
    top_level_missing = gate.get("missing_obligations")
    if isinstance(top_level_missing, list):
        for item in top_level_missing:
            text = finish_gate_missing_obligation_text(item)
            if text:
                missing.append(text)
    blockers = gate.get("blockers")
    if isinstance(blockers, list):
        for blocker in blockers:
            if not isinstance(blocker, Mapping):
                continue
            for key in ("required_evidence_ref", "missing_obligation", "obligation"):
                value = str(blocker.get(key) or "").strip()
                if value:
                    missing.append(value)
    return tuple(dict.fromkeys(missing))


def finish_gate_block_resolved_by_closeout(
    gate_codes: tuple[str, ...],
    gate_missing: tuple[str, ...],
    *,
    gate: Mapping[str, object],
    closeout_context: object,
) -> bool:
    context = closeout_context_from_object(closeout_context)
    if not context.fresh_verifier_refs:
        return False
    top_level_missing = gate.get("missing_obligations")
    runtime_artifact_codes = {"runtime_final_verifier_artifact_evidence"}
    if gate_codes and all(code in runtime_artifact_codes for code in gate_codes):
        return not gate_missing and (not isinstance(top_level_missing, list) or not top_level_missing)
    closeout_resolvable_codes = {
        "failed_typed_evidence_ref",
        "invalid_typed_evidence_ref",
        "missing_typed_evidence",
        "missing_typed_obligation",
    }
    planner_verified = bool(context.planner_verified_finish_refs)
    if planner_verified:
        planner_only_codes = {"acceptance_constraints_unchecked"}
        if gate_codes and all(code in planner_only_codes for code in gate_codes):
            if not gate_missing and (not isinstance(top_level_missing, list) or not top_level_missing):
                return True
    if any(code not in closeout_resolvable_codes for code in gate_codes):
        return False
    if isinstance(top_level_missing, list):
        return bool(top_level_missing) and all(
            finish_gate_missing_obligation_is_verifier(item) for item in top_level_missing
        )
    if not gate_missing:
        return False
    return all(
        not missing
        or missing == "strict_verifier_evidence"
        or missing == "verifier_pass"
        or missing.endswith(":verifier_pass")
        for missing in gate_missing
    )


def finish_gate_missing_obligation_is_verifier(value: object) -> bool:
    if isinstance(value, Mapping):
        kind = str(value.get("kind") or "").strip()
        if kind:
            return kind == "verifier_pass"
        text = str(value.get("id") or value.get("missing_obligation") or value.get("obligation") or "").strip()
    else:
        text = str(value or "").strip()
    return text in {"strict_verifier_evidence", "verifier_pass"} or text.endswith(":verifier_pass")


def finish_gate_missing_obligation_text(value: object) -> str:
    if isinstance(value, Mapping):
        for key in ("id", "kind", "missing_obligation", "obligation", "required_evidence_ref"):
            text = str(value.get(key) or "").strip()
            if text:
                return text
        return ""
    return str(value or "").strip()


__all__ = [
    "NativeCompletionCloseoutContext",
    "build_completion_resolver_input_from_finish",
    "closeout_context_resolved_by_finish_evidence",
    "finish_arg_strings",
    "finish_gate_block_resolved_by_closeout",
    "finish_gate_blocker_codes",
    "finish_gate_missing_obligations",
]
