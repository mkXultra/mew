"""NG-resume sidecar records for the native implement_v2 loop."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import re
from typing import Iterable

from .native_finish_gate import NativeFinishGateDecision
from .native_transcript import NativeTranscriptItem

NG_RESUME_SIGNAL_SCHEMA_VERSION = 1
NG_RESUME_SIGNALS_FILE = "ng_resume_signals.jsonl"
NG_RESUME_SIGNAL_VERSION = "native-ng-resume-v1"

PROHIBITED_NG_RESUME_LEAK_KEYS: tuple[str, ...] = (
    "task_contract",
    "finish_gate",
    "native_finish_gate_decision",
    "resolver_decision",
    "evidence_refs",
    "missing_obligations",
    "oracle_obligation_refs",
    "finish_status",
    "finish_readiness_state",
    "finish_required_evidence_refs",
)


@dataclass(frozen=True)
class NativeNgResumeSignal:
    """Transport-neutral signal for resuming after an internal finish-gate NG."""

    done_candidate_id: str
    decision_id: str
    lane_attempt_id: str
    turn_id: str
    concise_reason: str
    repair_focus: str
    observable_refs: tuple[str, ...] = ()
    lane_status: str = "blocked_continue"
    prohibited_leak_keys: tuple[str, ...] = PROHIBITED_NG_RESUME_LEAK_KEYS
    sidecar_ref: str = NG_RESUME_SIGNALS_FILE
    signal_version: str = NG_RESUME_SIGNAL_VERSION
    schema_version: int = field(default=NG_RESUME_SIGNAL_SCHEMA_VERSION, init=False)

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "signal_version": self.signal_version,
            "done_candidate_id": self.done_candidate_id,
            "decision_id": self.decision_id,
            "lane_attempt_id": self.lane_attempt_id,
            "turn_id": self.turn_id,
            "lane_status": self.lane_status,
            "concise_reason": self.concise_reason,
            "repair_focus": self.repair_focus,
            "observable_refs": list(self.observable_refs),
            "prohibited_leak_keys": list(self.prohibited_leak_keys),
            "sidecar_ref": self.sidecar_ref,
        }


def build_native_ng_resume_signal(decision: NativeFinishGateDecision) -> NativeNgResumeSignal:
    """Build a bounded, provider-safe resume signal from an internal gate block."""

    reason = _concise_visible_reason(decision)
    repair_focus = _repair_focus(decision)
    return NativeNgResumeSignal(
        done_candidate_id=decision.done_candidate_id,
        decision_id=decision.decision_id,
        lane_attempt_id=decision.lane_attempt_id,
        turn_id=decision.turn_id,
        concise_reason=reason or "The previous completion was not accepted.",
        repair_focus=repair_focus,
        observable_refs=(),
    )


def native_ng_resume_input_item(
    signal: NativeNgResumeSignal,
    *,
    sequence: int,
    provider: str,
    model: str,
) -> NativeTranscriptItem:
    """Render the abstract resume signal into the current input-message transport."""

    return NativeTranscriptItem(
        sequence=sequence,
        turn_id=f"{signal.turn_id}-ng-resume",
        kind="input_message",
        lane_attempt_id=signal.lane_attempt_id,
        provider=provider,
        model=model,
        output_text_or_ref=render_native_ng_resume_signal(signal),
        sidecar_refs=(signal.sidecar_ref,),
    )


def render_native_ng_resume_signal(signal: NativeNgResumeSignal) -> str:
    refs = ", ".join(signal.observable_refs)
    lines = [
        "Previous completion attempt was not accepted.",
        "Assistant text is not a completion signal.",
        "Last assistant response was not accepted as completion.",
        f"Reason: {signal.concise_reason}",
        f"Next: {signal.repair_focus}",
        "Call a concrete verification command or tool, then repair before responding again.",
    ]
    if refs:
        lines.append(f"Observable refs: {refs}")
    return "\n".join(_sanitize_visible_text(line) for line in lines)


def write_native_ng_resume_signal_artifacts(
    root: Path | str,
    signals: Iterable[NativeNgResumeSignal],
    *,
    proof_manifest_path: str | Path | None = None,
) -> dict[str, Path]:
    records = [signal.as_dict() for signal in signals]
    if not records:
        return {}
    artifact_root = Path(root)
    artifact_root.mkdir(parents=True, exist_ok=True)
    path = artifact_root / NG_RESUME_SIGNALS_FILE
    payload = "".join(
        json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in records
    )
    path.write_text(payload, encoding="utf-8")
    digest = _file_sha256(path)
    if proof_manifest_path is not None:
        _patch_proof_manifest(Path(proof_manifest_path), signal_path=path, digest=digest, count=len(records))
    return {"ng_resume_signals": path}


def _repair_focus(decision: NativeFinishGateDecision) -> str:
    text = " ".join(
        (
            decision.reason,
            *decision.blockers,
            *decision.closeout.blockers,
            *decision.closeout.warnings,
        )
    ).casefold()
    if "verifier" in text or "verify" in text or "test" in text:
        return "Run the relevant verifier, inspect the concrete failure, then repair the workspace."
    if "artifact" in text or "missing" in text:
        return "Inspect the requested artifact, create or repair it, then verify it with a concrete command."
    if "command" in text or "closeout" in text:
        return "Inspect the latest command result and run a concrete follow-up verifier or repair."
    return "Call a tool to verify the latest result or repair the remaining task gap."


def _closeout_reason(decision: NativeFinishGateDecision) -> str:
    return decision.closeout.reason or "internal verifier did not accept completion"


def _concise_visible_reason(decision: NativeFinishGateDecision) -> str:
    closeout_status = str(decision.closeout.status or "")
    if closeout_status == "completed_nonzero":
        return "A verification command did not pass."
    if closeout_status in {"missing_command", "not_run"}:
        return "No sufficient completion verifier was available."
    if closeout_status == "timed_out":
        return "A verification command timed out."
    if closeout_status == "unsafe":
        return "The completion check was not safe to run."
    if decision.closeout.observed_unexpected_source_mutation:
        return "The workspace changed unexpectedly during completion checking."
    if decision.blockers or decision.closeout.blockers:
        return "The previous completion was not accepted."
    return _sanitize_visible_text(_closeout_reason(decision)) or "The previous completion was not accepted."


def _sanitize_visible_text(value: object) -> str:
    text = " ".join(str(value or "").split())
    for pattern in (
        *PROHIBITED_NG_RESUME_LEAK_KEYS,
        "task contract",
        "finish gate",
        "finish-gate",
        "native finish gate",
        "internal gate",
        "done candidate",
        "final verifier closeout",
        "resolver",
    ):
        text = re.sub(re.escape(pattern), "internal detail", text, flags=re.IGNORECASE)
    return text[:360]


def _patch_proof_manifest(
    manifest_path: Path,
    *,
    signal_path: Path,
    digest: str,
    count: int,
) -> None:
    manifest: dict[str, object] = {}
    if manifest_path.exists():
        loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            manifest = loaded
    metrics = manifest.get("metrics") if isinstance(manifest.get("metrics"), dict) else {}
    metrics = dict(metrics or {})
    metrics["ng_resume_signal_count"] = count
    metrics["ng_resume_signals"] = count
    manifest["ng_resume_signals_ref"] = signal_path.name
    manifest["ng_resume_signals_sha256"] = digest
    manifest["metrics"] = metrics
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _file_sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


__all__ = [
    "NG_RESUME_SIGNALS_FILE",
    "NativeNgResumeSignal",
    "build_native_ng_resume_signal",
    "native_ng_resume_input_item",
    "render_native_ng_resume_signal",
    "write_native_ng_resume_signal_artifacts",
]
