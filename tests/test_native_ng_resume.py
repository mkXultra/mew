from __future__ import annotations

import json
from pathlib import Path

from mew.implement_lane.native_finish_gate import (
    FinishCloseoutCommand,
    NativeFinishCloseoutResult,
    NativeFinishGateDecision,
)
from mew.implement_lane.native_ng_resume import (
    NG_RESUME_SIGNALS_FILE,
    PROHIBITED_NG_RESUME_LEAK_KEYS,
    build_native_ng_resume_signal,
    native_ng_resume_input_item,
    render_native_ng_resume_signal,
    write_native_ng_resume_signal_artifacts,
)


def _blocked_decision() -> NativeFinishGateDecision:
    return NativeFinishGateDecision(
        decision_id="native-finish-gate:turn-3:abc",
        lane_attempt_id="attempt-1",
        turn_id="turn-3",
        finish_call_id="",
        done_candidate_id="done-candidate:turn-3:abc",
        lane_status="blocked_continue",
        result="block",
        closeout=NativeFinishCloseoutResult(
            command=FinishCloseoutCommand(command="pytest -q", source="finish_verifier_planner"),
            call_item=None,
            output_item=None,
            tool_result=None,
            status="completed_nonzero",
            exit_code=1,
            reason="verifier failed",
            closeout_refs=("native-tool-result://verify-1",),
        ),
        blockers=("verifier_failed", "task_contract hidden detail must not leak"),
        closeout_refs=("native-tool-result://verify-1",),
        reason="finish_gate blocked because task_contract verifier failed",
    )


def test_native_ng_resume_signal_renders_provider_safe_input() -> None:
    signal = build_native_ng_resume_signal(_blocked_decision())

    rendered = render_native_ng_resume_signal(signal)
    item = native_ng_resume_input_item(signal, sequence=4, provider="openai", model="gpt-5.5")

    assert signal.done_candidate_id == "done-candidate:turn-3:abc"
    assert signal.lane_status == "blocked_continue"
    assert "Previous completion attempt was not accepted" in rendered
    assert "native-tool-result://verify-1" not in rendered
    assert "A verification command did not pass." in rendered
    assert item.kind == "input_message"
    assert item.sidecar_refs == (NG_RESUME_SIGNALS_FILE,)
    assert item.output_text_or_ref == rendered
    for key in PROHIBITED_NG_RESUME_LEAK_KEYS:
        assert key not in rendered
    for phrase in ("finish gate", "task contract", "internal gate", "final verifier closeout", "resolver"):
        assert phrase not in rendered.casefold()


def test_native_ng_resume_signal_artifact_updates_manifest(tmp_path: Path) -> None:
    manifest_path = tmp_path / "proof-manifest.json"
    manifest_path.write_text(json.dumps({"metrics": {}}), encoding="utf-8")
    signal = build_native_ng_resume_signal(_blocked_decision())

    paths = write_native_ng_resume_signal_artifacts(tmp_path, [signal], proof_manifest_path=manifest_path)

    rows = [json.loads(line) for line in paths["ng_resume_signals"].read_text(encoding="utf-8").splitlines()]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert rows[0]["done_candidate_id"] == signal.done_candidate_id
    assert rows[0]["decision_id"] == signal.decision_id
    assert manifest["ng_resume_signals_ref"] == NG_RESUME_SIGNALS_FILE
    assert str(manifest["ng_resume_signals_sha256"]).startswith("sha256:")
    assert manifest["metrics"]["ng_resume_signal_count"] == 1
