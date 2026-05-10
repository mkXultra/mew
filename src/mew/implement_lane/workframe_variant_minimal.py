"""Minimal WorkFrame reducer variant for implement_v2 experiments."""

from __future__ import annotations

from dataclasses import replace

from .workframe import (
    WorkFrame,
    WorkFrameInputs,
    WorkFrameInvariantReport,
    WorkFrameRequiredNext,
    reduce_workframe,
    validate_workframe,
    workframe_output_hash,
)

VARIANT_NAME = "minimal"


def reduce_minimal_workframe(inputs: WorkFrameInputs) -> tuple[WorkFrame, WorkFrameInvariantReport]:
    """Return a thinner WorkFrame while preserving finish and verifier gates."""

    workframe, _ = reduce_workframe(inputs)
    required_next = _minimal_required_next(workframe)
    current_phase = "orient" if required_next is None and workframe.current_phase == "cheap_probe" else workframe.current_phase
    minimal = replace(workframe, current_phase=current_phase, required_next=required_next)
    minimal = replace(minimal, trace=replace(minimal.trace, output_hash=workframe_output_hash(minimal)))
    return minimal, validate_workframe(minimal, inputs=inputs)


def _minimal_required_next(workframe: WorkFrame) -> WorkFrameRequiredNext | None:
    required_next = workframe.required_next
    if required_next is None:
        return None
    if required_next.kind == "finish":
        if workframe.finish_readiness.state == "ready" and required_next.evidence_refs:
            return required_next
        return None
    if required_next.kind == "run_verifier":
        if _must_preserve_run_verifier_next(workframe):
            return required_next
        return None
    if required_next.kind == "blocked":
        return required_next
    return None


def _must_preserve_run_verifier_next(workframe: WorkFrame) -> bool:
    if workframe.finish_readiness.state == "blocked":
        return True
    if workframe.changed_sources.since_last_strict_verifier:
        return True
    if workframe.verifier_state.budget_closeout_required:
        return True
    return bool(
        workframe.latest_actionable
        and workframe.latest_actionable.generic_family == "verifier_stale_after_mutation"
    )


__all__ = ["VARIANT_NAME", "reduce_minimal_workframe"]
