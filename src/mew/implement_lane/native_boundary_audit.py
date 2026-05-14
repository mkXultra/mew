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


DESIGN_DOC = Path("docs/DESIGN_2026-05-13_M6_24_CODEX_LIKE_NATIVE_HOT_PATH.md")

@dataclass(frozen=True)
class SourceControlSpec:
    name: str
    relative_path: str
    anchor: str
    markers: tuple[str, ...]
    forbidden_markers: tuple[str, ...] = ()
    window_before: int = 0
    window_after: int = 30


SOURCE_CONTROL_SPECS: tuple[SourceControlSpec, ...] = (
    SourceControlSpec(
        name="finish_call_resolver_completion",
        relative_path="src/mew/implement_lane/native_tool_harness.py",
        anchor='if call.kind == "finish_call" and _native_finish_resolver_lane_status(result) == "completed"',
        markers=("accepted_finish = call", 'status = "completed"'),
        forbidden_markers=('result.status == "completed" and not result.is_error',),
        window_after=8,
    ),
    SourceControlSpec(
        name="native_final_verifier_closeout_call",
        relative_path="src/mew/implement_lane/native_tool_harness.py",
        anchor="closeout = _native_final_verifier_closeout(",
        markers=("provider=provider", "tool_calls=tuple(scoped_calls)"),
        window_after=18,
    ),
    SourceControlSpec(
        name="native_loop_control_policy_state",
        relative_path="src/mew/implement_lane/native_tool_harness.py",
        anchor="def _native_loop_control_state",
        markers=("first_write_due", "verifier_repair_due", '"surface": "native_loop_signals"'),
        forbidden_markers=("next_action_policy",),
        window_after=58,
    ),
    SourceControlSpec(
        name="native_loop_control_instruction_removed",
        relative_path="src/mew/implement_lane/native_tool_harness.py",
        anchor="def _responses_input_items",
        markers=('"task_contract": dict(lane_input.task_contract)', '"task_facts": task_facts'),
        forbidden_markers=(
            "_native_loop_control_input_item",
            "patch/edit/write",
            "Do not continue broad exploration",
            '"compact_sidecar_digest": dict(compact_sidecar_digest)',
        ),
        window_after=48,
    ),
    SourceControlSpec(
        name="persisted_lane_state_provider_payload",
        relative_path="src/mew/implement_lane/native_tool_harness.py",
        anchor="task_payload = {",
        markers=('"task_contract": dict(lane_input.task_contract)', '"workspace": lane_input.workspace'),
        forbidden_markers=("persisted_lane_state", '"compact_sidecar_digest": dict(compact_sidecar_digest)'),
        window_after=12,
    ),
    SourceControlSpec(
        name="exec_runtime_applies_finish_gate",
        relative_path="src/mew/implement_lane/exec_runtime.py",
        anchor="finish_gate = apply_finish_gate(",
        markers=('payload["structured_finish_gate"]', "_contract_failure_blocks_tool_status"),
        window_after=40,
    ),
    SourceControlSpec(
        name="execution_evidence_finish_gate_producer",
        relative_path="src/mew/implement_lane/execution_evidence.py",
        anchor="def apply_finish_gate(",
        markers=("FinishGateResult", "reasons", "evidence_refs"),
        window_after=36,
    ),
    SourceControlSpec(
        name="compact_digest_factual_only",
        relative_path="src/mew/implement_lane/native_sidecar_projection.py",
        anchor="def build_compact_native_sidecar_digest",
        markers=(
            '"provider_input_authority": "transcript_window_plus_compact_sidecar_digest"',
            '"latest_tool_results"',
            '"latest_evidence_refs"',
            '"sidecar_hashes"',
        ),
        forbidden_markers=('"workframe_projection"', '"attention_hints"', '"loop_signals"', '"required_next_kind"'),
        window_after=64,
    ),
    SourceControlSpec(
        name="sidecar_todo_required_next_projection",
        relative_path="src/mew/implement_lane/native_sidecar_projection.py",
        anchor="def _derived_active_work_todo",
        markers=("required_next_kind", '"first_write_readiness"', '"required_next"'),
        window_after=42,
    ),
    SourceControlSpec(
        name="workframe_prompt_visible_sidecar_debug_ref",
        relative_path="src/mew/implement_lane/native_workframe_projection.py",
        anchor="def _prompt_visible_workframe",
        markers=('"provider_visible": False', '"native_workframe_sidecar_debug_ref"', '"missing_evidence_refs"'),
        forbidden_markers=('"required_next"', '"target_paths"', '"attention_hints"'),
        window_after=28,
    ),
    SourceControlSpec(
        name="provider_inventory_keeps_diagnostics_sidecar_only",
        relative_path="src/mew/implement_lane/native_workframe_projection.py",
        anchor="def build_native_prompt_input_inventory",
        markers=(
            '"diagnostic_only_fields_report"',
            '"provider_visible": False',
            '"provider_visible_forbidden_fields"',
            '"native_loop_signals"',
        ),
        window_after=48,
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
    "codex_like_live_hot_path": (
        "Codex-like live hot path",
        "native transcript window",
        "compact factual tool-result digest",
        "mew-specific durable sidecar proof",
    ),
    "provider_visible_forbidden_fields": (
        "Provider-Visible Forbidden",
        "next_action",
        "first_write_due",
        "prewrite_probe_plateau",
        "WorkFrame",
    ),
    "internal_sidecar_contract": (
        "Internal Sidecar Contract",
        "response_transcript.json",
        "provider request inventory",
        "typed evidence sidecars",
    ),
    "tool_surface_contract": (
        "Tool Surface Contract",
        "apply_patch",
        "edit_file",
        "write_file",
    ),
    "parallel_phase_ownership": (
        "Phase 1A: Transcript/Input Collapse",
        "Phase 1B: Tool Surface And Mutation Path",
        "Main Codex responsibilities",
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
    forbidden = [marker for marker in spec.forbidden_markers if marker in window]
    passed = not missing and not forbidden
    details: list[str] = []
    if missing:
        details.append(f"missing markers: {', '.join(missing)}")
    if forbidden:
        details.append(f"forbidden markers present: {', '.join(forbidden)}")
    return BoundaryAuditCheck(
        name=f"source_inventory_{spec.name}",
        passed=passed,
        detail=(
            f"{spec.relative_path} around {spec.anchor!r}"
            if passed
            else f"{spec.relative_path} around {spec.anchor!r} {'; '.join(details)}"
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
