"""Phase 0 inventory audit for the implement_v2 native-loop boundary.

This does not prove the boundary has been implemented. It proves the design is
tracking the current semantic-ish controls that must be moved or justified in
later phases.
"""

from __future__ import annotations

from dataclasses import dataclass
import argparse
import json
from pathlib import Path


DESIGN_DOC = Path("docs/DESIGN_2026-05-12_M6_24_NATIVE_TOOL_LOOP_RESPONSIBILITY_BOUNDARY.md")

@dataclass(frozen=True)
class SourceControlSpec:
    name: str
    relative_path: str
    anchor: str
    markers: tuple[str, ...]
    window_before: int = 0
    window_after: int = 30


SOURCE_CONTROL_SPECS: tuple[SourceControlSpec, ...] = (
    SourceControlSpec(
        name="finish_call_status_completion",
        relative_path="src/mew/implement_lane/native_tool_harness.py",
        anchor='if call.kind == "finish_call" and result.status == "completed"',
        markers=("accepted_finish = call", 'status = "completed"'),
        window_after=8,
    ),
    SourceControlSpec(
        name="native_final_verifier_closeout_call",
        relative_path="src/mew/implement_lane/native_tool_harness.py",
        anchor="closeout = _native_final_verifier_closeout(",
        markers=("provider=provider", "tool_calls=tuple(tool_calls)"),
        window_after=18,
    ),
    SourceControlSpec(
        name="native_loop_control_policy_state",
        relative_path="src/mew/implement_lane/native_tool_harness.py",
        anchor="def _native_loop_control_state",
        markers=("first_write_due", "verifier_repair_due", "next_action_policy =", '"next_action_policy": next_action_policy'),
        window_after=58,
    ),
    SourceControlSpec(
        name="native_loop_control_instruction_text",
        relative_path="src/mew/implement_lane/native_tool_harness.py",
        anchor="def _native_loop_control_input_item",
        markers=("patch/edit/write", "Do not continue broad exploration"),
        window_after=28,
    ),
    SourceControlSpec(
        name="persisted_lane_state_provider_payload",
        relative_path="src/mew/implement_lane/native_tool_harness.py",
        anchor="task_payload = {",
        markers=('"persisted_lane_state": dict(lane_input.persisted_lane_state)',),
        window_after=12,
    ),
    SourceControlSpec(
        name="exec_runtime_applies_finish_gate",
        relative_path="src/mew/implement_lane/exec_runtime.py",
        anchor="finish_gate = apply_finish_gate(",
        markers=('payload["structured_finish_gate"]', "_contract_failure_blocks_tool_status"),
        window_after=24,
    ),
    SourceControlSpec(
        name="execution_evidence_finish_gate_producer",
        relative_path="src/mew/implement_lane/execution_evidence.py",
        anchor="def apply_finish_gate(",
        markers=("FinishGateResult", "reasons", "evidence_refs"),
        window_after=36,
    ),
    SourceControlSpec(
        name="sidecar_required_next_digest",
        relative_path="src/mew/implement_lane/native_sidecar_projection.py",
        anchor="def _workframe_digest",
        markers=("required_next", '"required_next_kind"', '"required_next_evidence_refs"'),
        window_after=28,
    ),
    SourceControlSpec(
        name="sidecar_todo_required_next_projection",
        relative_path="src/mew/implement_lane/native_sidecar_projection.py",
        anchor="def _derived_active_work_todo",
        markers=("required_next_kind", '"first_write_readiness"', '"required_next"'),
        window_after=42,
    ),
    SourceControlSpec(
        name="workframe_prompt_visible_required_next",
        relative_path="src/mew/implement_lane/native_workframe_projection.py",
        anchor="def _prompt_visible_workframe",
        markers=('"required_next"', '"target_paths"', '"evidence_refs"'),
        window_after=28,
    ),
    SourceControlSpec(
        name="workframe_debug_bundle_prompt_visible_projection",
        relative_path="src/mew/implement_lane/native_workframe_projection.py",
        anchor='"prompt_visible_workframe": _prompt_visible_workframe',
        markers=('"reducer_output": workframe.as_dict()', '"prompt_render_inventory"'),
        window_before=8,
        window_after=8,
    ),
)

DESIGN_TRACKING_MARKERS: dict[str, tuple[str, ...]] = {
    "compact_sidecar_digest_bounds": (
        "compact_sidecar_digest",
        "<= 6144",
        "workframe_projection",
        "top-level keys",
    ),
    "finish_state_machine": (
        "Finish State Machine",
        "blocked_continue",
        "blocked_return",
        "resolver_decision",
    ),
    "completion_resolver_boundary": (
        "CompletionResolver",
        "tool を実行すること",
        "pre-extracted typed evidence refs",
    ),
    "required_next_migration": (
        "Required Next Migration",
        "ordinary repair",
        "attention_hints",
        "transition_contract",
    ),
    "native_loop_control_signal_migration": (
        "first_write_due",
        "verifier_repair_due",
        "next_action_policy",
        "bounded booleans",
    ),
    "non_finish_closeout_migration": (
        "Non-finish / max-turn closeout migration",
        "no lane may become `completed` without a valid `finish_call`",
    ),
    "current_phase_observational_only": (
        "current_phase",
        "Allowed values",
        "observational label",
        "action prescription ではない",
    ),
    "persisted_lane_state_treatment": (
        "persisted_lane_state",
        "provider-visible",
        "compact_sidecar_digest",
    ),
    "migration_table_phase_tracking": (
        "Owner phase",
        "残す場合の compatibility 理由",
        "Phase 1-2",
        "Phase 3",
    ),
}


@dataclass(frozen=True)
class BoundaryAuditCheck:
    name: str
    passed: bool
    detail: str

    def as_dict(self) -> dict[str, object]:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


@dataclass(frozen=True)
class BoundaryAuditReport:
    source_root: str
    checks: tuple[BoundaryAuditCheck, ...]

    @property
    def ok(self) -> bool:
        return all(check.passed for check in self.checks)

    def as_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "source_root": self.source_root,
            "checks": [check.as_dict() for check in self.checks],
        }


def run_native_boundary_audit(source_root: str | Path = ".") -> BoundaryAuditReport:
    root = Path(source_root)
    checks: list[BoundaryAuditCheck] = []
    design_text = _read_text(root / DESIGN_DOC)

    checks.append(
        BoundaryAuditCheck(
            name="design_doc_exists",
            passed=bool(design_text),
            detail=str(DESIGN_DOC),
        )
    )
    for name, markers in DESIGN_TRACKING_MARKERS.items():
        missing = [marker for marker in markers if marker not in design_text]
        checks.append(
            BoundaryAuditCheck(
                name=f"design_tracks_{name}",
                passed=not missing,
                detail="ok" if not missing else f"missing markers: {', '.join(missing)}",
            )
        )
    for spec in SOURCE_CONTROL_SPECS:
        checks.append(_source_window_check(root, spec))

    return BoundaryAuditReport(source_root=str(root), checks=tuple(checks))


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _source_window_check(root: Path, spec: SourceControlSpec) -> BoundaryAuditCheck:
    source_text = _read_text(root / spec.relative_path)
    if not source_text:
        return BoundaryAuditCheck(
            name=f"source_inventory_{spec.name}",
            passed=False,
            detail=f"{spec.relative_path} missing or unreadable",
        )
    window = _line_window(source_text, anchor=spec.anchor, before=spec.window_before, after=spec.window_after)
    if window is None:
        return BoundaryAuditCheck(
            name=f"source_inventory_{spec.name}",
            passed=False,
            detail=f"{spec.relative_path} missing anchor: {spec.anchor}",
        )
    missing = [marker for marker in spec.markers if marker not in window]
    return BoundaryAuditCheck(
        name=f"source_inventory_{spec.name}",
        passed=not missing,
        detail=(
            f"{spec.relative_path} around {spec.anchor!r}"
            if not missing
            else f"{spec.relative_path} around {spec.anchor!r} missing markers: {', '.join(missing)}"
        ),
    )


def _line_window(text: str, *, anchor: str, before: int, after: int) -> str | None:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if anchor in line:
            start = max(0, index - before)
            stop = min(len(lines), index + after + 1)
            return "\n".join(lines[start:stop])
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", default=".", help="repository root to audit")
    parser.add_argument("--json", action="store_true", help="print structured JSON")
    args = parser.parse_args(argv)

    report = run_native_boundary_audit(args.source_root)
    if args.json:
        print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"native tool-loop Phase 0 inventory audit: {'PASS' if report.ok else 'FAIL'}")
        for check in report.checks:
            print(f"- {'ok' if check.passed else 'fail'}: {check.name}: {check.detail}")
    return 0 if report.ok else 1


__all__ = [
    "BoundaryAuditCheck",
    "BoundaryAuditReport",
    "SourceControlSpec",
    "run_native_boundary_audit",
    "main",
]
