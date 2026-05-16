import json
import hashlib
from pathlib import Path

import pytest

from mew.implement_lane.completion_resolver import CompletionResolverDecision, write_completion_resolver_artifacts
from mew.implement_lane.hot_path_fastcheck import _workframe_resolvable_refs, run_hot_path_fastcheck
from mew.implement_lane.native_finish_gate import (
    NativeFinishCloseoutResult,
    NativeFinishGateDecision,
    write_native_finish_gate_artifacts,
)
from mew.implement_lane.native_sidecar_projection import build_compact_native_sidecar_digest
from mew.implement_lane.native_tool_harness import _native_loop_control_state
from mew.implement_lane.native_workframe_projection import build_native_prompt_input_inventory
from mew.implement_lane.native_transcript import (
    NativeTranscript,
    NativeTranscriptItem,
    native_transcript_hash,
    write_native_evidence_observation,
    write_native_transcript_artifacts,
)
from mew.implement_lane.workframe import WorkFrameInputs, canonicalize_workframe_inputs, reduce_workframe
from mew.implement_lane.workframe_variants import (
    canonicalize_common_workframe_inputs,
    common_workframe_inputs_from_workframe_inputs,
    project_workframe_with_variant,
)


def _write_artifact(tmp_path: Path) -> Path:
    artifact = tmp_path / "artifact"
    implement_v2 = artifact / "implement_v2"
    implement_v2.mkdir(parents=True)
    manifest = {
        "lane": "implement_v2",
        "metrics": {
            "hot_path_projection": {
                "phase": "m6_24_workframe_redesign_phase_1",
                "normal_full_prompt_bytes": 1024,
                "normal_full_prompt_bytes_total": 2048,
                "provider_visible_tool_result_bytes": 128,
                "normal_section_inventory": [
                    {
                        "id": "implement_v2_workframe",
                        "visibility": "ordinary",
                        "stability": "dynamic",
                        "cache_policy": "dynamic",
                        "bytes": 256,
                    }
                ],
            },
            "resident_sidecar_state": {
                "surface": "resident_sidecar_state",
                "total_bytes": 4096,
                "per_turn_growth_bytes": 256,
                "families": {"tool_results": 1},
            },
            "workframe": {
                "schema_version": 1,
                "phase": "m6_24_workframe_redesign_phase_6",
            },
        },
    }
    history = [
        {
            "turn": 1,
            "summary": "Probe source and prepare first patch.",
            "tool_calls": [],
            "tool_results": [],
        }
    ]
    workframe = _write_workframe_bundle(implement_v2 / "workframes" / "turn-1")
    manifest["metrics"]["workframe"]["input_hash"] = workframe.trace.input_hash
    manifest["metrics"]["workframe"]["output_hash"] = workframe.trace.output_hash
    (implement_v2 / "proof-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (implement_v2 / "history.json").write_text(json.dumps(history), encoding="utf-8")
    return artifact


def _write_native_artifact(tmp_path: Path, *, with_failed_verifier_repair: bool = False) -> Path:
    artifact = tmp_path / "native-artifact"
    lane_attempt_id = "native-fastcheck:task-1"
    items = [
        NativeTranscriptItem(
            sequence=1,
            turn_id="turn-1",
            lane_attempt_id=lane_attempt_id,
            provider="codex",
            model="gpt-5.5",
            kind="function_call",
            call_id="call-read-1",
            tool_name="read_file",
            arguments_json_text='{"path":"vm.js"}',
        ),
        NativeTranscriptItem(
            sequence=2,
            turn_id="turn-1",
            lane_attempt_id=lane_attempt_id,
            provider="codex",
            model="gpt-5.5",
            kind="function_call_output",
            call_id="call-read-1",
            tool_name="read_file",
            status="completed",
            output_text_or_ref="read_file result: completed",
        ),
        NativeTranscriptItem(
            sequence=3,
            turn_id="turn-2",
            lane_attempt_id=lane_attempt_id,
            provider="codex",
            model="gpt-5.5",
            kind="function_call",
            call_id="call-write-1",
            tool_name="write_file",
            arguments_json_text='{"path":"vm.js","content":"console.log(1)"}',
        ),
        NativeTranscriptItem(
            sequence=4,
            turn_id="turn-2",
            lane_attempt_id=lane_attempt_id,
            provider="codex",
            model="gpt-5.5",
            kind="function_call_output",
            call_id="call-write-1",
            tool_name="write_file",
            status="completed",
            output_text_or_ref="write_file result: completed",
        ),
        NativeTranscriptItem(
            sequence=5,
            turn_id="turn-3",
            lane_attempt_id=lane_attempt_id,
            provider="codex",
            model="gpt-5.5",
            kind="function_call",
            call_id="call-test-0",
            tool_name="run_tests",
            arguments_json_text='{"command":"node vm.js"}',
        ),
        NativeTranscriptItem(
            sequence=6,
            turn_id="turn-3",
            lane_attempt_id=lane_attempt_id,
            provider="codex",
            model="gpt-5.5",
            kind="function_call_output",
            call_id="call-test-0",
            tool_name="run_tests",
            status="completed",
            output_text_or_ref="run_tests result: completed",
        ),
    ]
    if with_failed_verifier_repair:
        items.extend(
            [
                NativeTranscriptItem(
                    sequence=7,
                    turn_id="turn-4",
                    lane_attempt_id=lane_attempt_id,
                    provider="codex",
                    model="gpt-5.5",
                    kind="function_call",
                    call_id="call-test-1",
                    tool_name="run_tests",
                    arguments_json_text='{"command":"node vm.js"}',
                ),
                NativeTranscriptItem(
                    sequence=8,
                    turn_id="turn-4",
                    lane_attempt_id=lane_attempt_id,
                    provider="codex",
                    model="gpt-5.5",
                    kind="function_call_output",
                    call_id="call-test-1",
                    tool_name="run_tests",
                    status="failed",
                    is_error=True,
                    output_text_or_ref="run_tests result: failed; stderr=ReferenceError: x is not defined",
                ),
                NativeTranscriptItem(
                    sequence=9,
                    turn_id="turn-5",
                    lane_attempt_id=lane_attempt_id,
                    provider="codex",
                    model="gpt-5.5",
                    kind="function_call",
                    call_id="call-read-2",
                    tool_name="read_file",
                    arguments_json_text='{"path":"vm.js"}',
                ),
                NativeTranscriptItem(
                    sequence=10,
                    turn_id="turn-5",
                    lane_attempt_id=lane_attempt_id,
                    provider="codex",
                    model="gpt-5.5",
                    kind="function_call_output",
                    call_id="call-read-2",
                    tool_name="read_file",
                    status="completed",
                    output_text_or_ref="read_file result: completed",
                ),
                NativeTranscriptItem(
                    sequence=11,
                    turn_id="turn-6",
                    lane_attempt_id=lane_attempt_id,
                    provider="codex",
                    model="gpt-5.5",
                    kind="function_call",
                    call_id="call-probe-1",
                    tool_name="run_command",
                    arguments_json_text='{"command":"node -e \\"require(\\\\\\"./vm.js\\\\\\")\\""}',
                ),
                NativeTranscriptItem(
                    sequence=12,
                    turn_id="turn-6",
                    lane_attempt_id=lane_attempt_id,
                    provider="codex",
                    model="gpt-5.5",
                    kind="function_call_output",
                    call_id="call-probe-1",
                    tool_name="run_command",
                    status="completed",
                    output_text_or_ref="run_command result: completed",
                ),
            ]
        )
    transcript = NativeTranscript(
        lane_attempt_id=lane_attempt_id,
        provider="codex",
        model="gpt-5.5",
        items=tuple(items),
    )
    write_native_transcript_artifacts(artifact, transcript)
    return artifact


def _write_native_provider_request(
    artifact: Path,
    transcript: NativeTranscript,
    *,
    prefix_item_count: int = 0,
    task_contract: dict[str, object] | None = None,
    workframe_variant: str = "",
    live_shape: bool = False,
) -> None:
    task_contract = task_contract or {"goal": "exercise native request fastcheck"}
    prefix = NativeTranscript(
        lane_attempt_id=transcript.lane_attempt_id,
        provider=transcript.provider,
        model=transcript.model,
        items=tuple(transcript.items[:prefix_item_count]),
    )
    digest = build_compact_native_sidecar_digest(
        prefix,
        loop_signals=_native_loop_control_state(
            list(prefix.items),
            current_turn_index=1,
            task_contract=task_contract,
        ),
    )
    task_payload = {
        "task_contract": task_contract,
        "compact_sidecar_digest": digest,
        "workspace": str(artifact),
        "lane": "implement_v2",
    }
    if workframe_variant:
        task_payload["workframe_variant"] = workframe_variant
    input_items = [
        {
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": json.dumps(task_payload, ensure_ascii=False, sort_keys=True),
                }
            ],
        }
    ]
    request = {
        "runtime_id": "implement_v2_native_transcript_loop",
        "transport_kind": "provider_native",
        "native_transport_kind": "provider_native",
        "lane_attempt_id": transcript.lane_attempt_id,
        "turn_index": 1,
        "input_item_count": prefix_item_count,
        "provider_request_inventory": build_native_prompt_input_inventory(compact_sidecar_digest=digest),
    }
    if live_shape:
        request["provider"] = transcript.provider
        request["model"] = transcript.model
        request["request_body"] = {
            "model": transcript.model,
            "instructions": "native loop instructions",
            "input": input_items,
            "tools": [],
            "tool_choice": "auto",
            "parallel_tool_calls": True,
            "stream": True,
            "store": False,
        }
    else:
        request["transcript_window"] = [item.as_dict() for item in prefix.items]
        request["input_items"] = input_items
    payload = {
        "schema_version": 1,
        "runtime_id": "implement_v2_native_transcript_loop",
        "transport_kind": "provider_native",
        "native_transport_kind": "provider_native",
        "status": "completed",
        "request_count": 1,
        "requests": [request],
    }
    (artifact / "native-provider-requests.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _read_native_transcript(artifact: Path) -> NativeTranscript:
    payload = json.loads((artifact / "response_transcript.json").read_text(encoding="utf-8"))
    return NativeTranscript(
        lane_attempt_id=str(payload["lane_attempt_id"]),
        provider=str(payload["provider"]),
        model=str(payload["model"]),
        items=tuple(NativeTranscriptItem(**{k: v for k, v in item.items() if k != "schema_version"}) for item in payload["items"]),
    )


def _native_request_payload(artifact: Path) -> dict[str, object]:
    request_file = artifact / "native-provider-requests.json"
    payload = json.loads(request_file.read_text(encoding="utf-8"))
    request = payload["requests"][0]
    input_items = request.get("input_items") or request["request_body"]["input"]
    text = input_items[0]["content"][0]["text"]
    return json.loads(text)


def _replace_native_request_payload(artifact: Path, task_payload: dict[str, object]) -> None:
    request_file = artifact / "native-provider-requests.json"
    payload = json.loads(request_file.read_text(encoding="utf-8"))
    request = payload["requests"][0]
    input_items = request.get("input_items") or request["request_body"]["input"]
    input_items[0]["content"][0]["text"] = json.dumps(
        task_payload,
        ensure_ascii=False,
        sort_keys=True,
    )
    request_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_native_finish_artifact(tmp_path: Path) -> Path:
    artifact = tmp_path / "native-finish-artifact"
    lane_attempt_id = "native-fastcheck:finish"
    transcript = NativeTranscript(
        lane_attempt_id=lane_attempt_id,
        provider="codex",
        model="gpt-5.5",
        items=(
            NativeTranscriptItem(
                sequence=1,
                turn_id="turn-1",
                lane_attempt_id=lane_attempt_id,
                provider="codex",
                model="gpt-5.5",
                kind="function_call",
                call_id="call-write-1",
                tool_name="write_file",
                arguments_json_text='{"path":"vm.js","content":"console.log(1)"}',
            ),
            NativeTranscriptItem(
                sequence=2,
                turn_id="turn-1",
                lane_attempt_id=lane_attempt_id,
                provider="codex",
                model="gpt-5.5",
                kind="function_call_output",
                call_id="call-write-1",
                tool_name="write_file",
                status="completed",
                output_text_or_ref="write_file result: completed",
            ),
            NativeTranscriptItem(
                sequence=3,
                turn_id="turn-2",
                lane_attempt_id=lane_attempt_id,
                provider="codex",
                model="gpt-5.5",
                kind="function_call",
                call_id="call-test-1",
                tool_name="run_tests",
                arguments_json_text='{"command":"node vm.js"}',
            ),
            NativeTranscriptItem(
                sequence=4,
                turn_id="turn-2",
                lane_attempt_id=lane_attempt_id,
                provider="codex",
                model="gpt-5.5",
                kind="function_call_output",
                call_id="call-test-1",
                tool_name="run_tests",
                status="completed",
                output_text_or_ref="run_tests result: completed",
                evidence_refs=("ev:verify-pass",),
            ),
            NativeTranscriptItem(
                sequence=5,
                turn_id="turn-3",
                lane_attempt_id=lane_attempt_id,
                provider="codex",
                model="gpt-5.5",
                kind="finish_call",
                call_id="finish-1",
                tool_name="finish",
                arguments_json_text='{"outcome":"completed","summary":"done","evidence_refs":["ev:verify-pass"]}',
            ),
            NativeTranscriptItem(
                sequence=6,
                turn_id="turn-3",
                lane_attempt_id=lane_attempt_id,
                provider="codex",
                model="gpt-5.5",
                kind="finish_output",
                call_id="finish-1",
                tool_name="finish",
                status="completed",
                output_text_or_ref="finish result: completed; summary=done",
                evidence_refs=("ev:verify-pass",),
            ),
        ),
    )
    paths = write_native_transcript_artifacts(artifact, transcript)
    decision = CompletionResolverDecision(
        decision_id="resolver:turn-3:finish-1",
        lane_attempt_id=lane_attempt_id,
        turn_id="turn-3",
        finish_call_id="finish-1",
        finish_output_call_id="finish-1",
        lane_status="completed",
        result="allow",
        evidence_refs=("ev:verify-pass",),
        reason="done",
        transcript_hash_before_decision="sha256:before",
        compact_sidecar_digest_hash="sha256:digest",
    )
    write_completion_resolver_artifacts(
        artifact,
        [decision],
        proof_manifest_path=paths["proof_manifest"],
    )
    write_native_evidence_observation(artifact, transcript, resolver_decisions=[decision], proof_manifest_path=paths["proof_manifest"])
    return artifact


def _write_native_finish_gate_artifact(
    tmp_path: Path,
    *,
    projection_warning: bool = False,
    finish_verifier_plan: dict[str, object] | None = None,
) -> Path:
    artifact = tmp_path / ("native-finish-gate-warning-artifact" if projection_warning else "native-finish-gate-artifact")
    lane_attempt_id = "native-fastcheck:finish-gate"
    closeout_arguments = {"command": "node vm.js", "command_intent": "finish_verifier"}
    if finish_verifier_plan is not None:
        closeout_arguments["finish_verifier_plan"] = finish_verifier_plan
    items = (
        NativeTranscriptItem(
            sequence=1,
            turn_id="turn-1",
            lane_attempt_id=lane_attempt_id,
            provider="codex",
            model="gpt-5.5",
            kind="function_call",
            call_id="call-write-1",
            tool_name="write_file",
            arguments_json_text='{"path":"vm.js","content":"console.log(1)"}',
        ),
        NativeTranscriptItem(
            sequence=2,
            turn_id="turn-1",
            lane_attempt_id=lane_attempt_id,
            provider="codex",
            model="gpt-5.5",
            kind="function_call_output",
            call_id="call-write-1",
            tool_name="write_file",
            status="completed",
            output_text_or_ref="write_file result: completed",
        ),
        NativeTranscriptItem(
            sequence=3,
            turn_id="turn-2",
            lane_attempt_id=lane_attempt_id,
            provider="codex",
            model="gpt-5.5",
            kind="finish_call",
            call_id="finish-1",
            tool_name="finish",
            arguments_json_text='{"outcome":"completed","summary":"done"}',
        ),
        NativeTranscriptItem(
            sequence=4,
            turn_id="turn-2",
            lane_attempt_id=lane_attempt_id,
            provider="codex",
            model="gpt-5.5",
            kind="function_call",
            call_id="call-final-verifier-closeout-001",
            tool_name="exec_command",
            arguments_json_text=json.dumps(closeout_arguments, ensure_ascii=False, sort_keys=True),
        ),
        NativeTranscriptItem(
            sequence=5,
            turn_id="turn-2",
            lane_attempt_id=lane_attempt_id,
            provider="codex",
            model="gpt-5.5",
            kind="function_call_output",
            call_id="call-final-verifier-closeout-001",
            tool_name="exec_command",
            status="completed",
            output_text_or_ref="command exited 0",
            evidence_refs=("ev:closeout:terminal",),
            sidecar_refs=("implement-v2-exec://attempt/final-verifier/terminal",),
        ),
        NativeTranscriptItem(
            sequence=6,
            turn_id="turn-2",
            lane_attempt_id=lane_attempt_id,
            provider="codex",
            model="gpt-5.5",
            kind="finish_output",
            call_id="finish-1",
            tool_name="finish",
            status="completed",
            output_text_or_ref="finish result: completed; native_finish_gate_decision_id=native-finish-gate:turn-2:finish-1",
        ),
    )
    transcript = NativeTranscript(
        lane_attempt_id=lane_attempt_id,
        provider="codex",
        model="gpt-5.5",
        items=items,
    )
    paths = write_native_transcript_artifacts(artifact, transcript)
    prefix = NativeTranscript(
        lane_attempt_id=lane_attempt_id,
        provider="codex",
        model="gpt-5.5",
        items=items[:5],
    )
    decision = NativeFinishGateDecision(
        decision_id="native-finish-gate:turn-2:finish-1",
        lane_attempt_id=lane_attempt_id,
        turn_id="turn-2",
        finish_call_id="finish-1",
        lane_status="completed",
        result="allow",
        closeout=NativeFinishCloseoutResult(
            command=None,
            call_item=items[3].as_dict(),
            output_item=items[4].as_dict(),
            tool_result=None,
            status="completed_zero",
            exit_code=0,
            typed_evidence_projection_status="warning" if projection_warning else "passed",
            evidence_refs=("ev:closeout:terminal",),
            closeout_refs=("implement-v2-exec://attempt/final-verifier/terminal",),
            warnings=("typed_evidence_projection_failed",) if projection_warning else (),
        ),
        evidence_refs=("ev:closeout:terminal",),
        closeout_refs=("implement-v2-exec://attempt/final-verifier/terminal",),
        transcript_hash_before_decision=native_transcript_hash(prefix),
        compact_sidecar_digest_hash="sha256:compact-digest",
        reason="trusted final verifier closeout exited 0",
    )
    write_native_finish_gate_artifacts(artifact, [decision], proof_manifest_path=paths["proof_manifest"])
    write_native_evidence_observation(artifact, transcript, proof_manifest_path=paths["proof_manifest"])
    return artifact


def _write_finish_verifier_planner_decisions(artifact: Path, rows: list[dict[str, object]]) -> None:
    decision_path = artifact / "finish_verifier_planner_decisions.jsonl"
    decision_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    manifest_path = artifact / "proof-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    digest = "sha256:" + hashlib.sha256(decision_path.read_bytes()).hexdigest()
    metrics = manifest.get("metrics") if isinstance(manifest.get("metrics"), dict) else {}
    metrics["finish_verifier_planner_decisions"] = {
        "artifact_ref": decision_path.name,
        "artifact_sha256": digest,
        "decision_count": len(rows),
        "accepted_count": sum(1 for row in rows if row.get("status") == "accepted"),
        "rejected_count": sum(1 for row in rows if row.get("status") == "rejected"),
        "error_count": sum(1 for row in rows if row.get("status") == "error"),
        "no_plan_count": sum(1 for row in rows if row.get("status") == "no_plan"),
        "fallback_count": sum(1 for row in rows if row.get("fallback_source")),
    }
    manifest["finish_verifier_planner_decisions_ref"] = decision_path.name
    manifest["finish_verifier_planner_decisions_sha256"] = digest
    manifest["metrics"] = metrics
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_read_only_native_artifact(tmp_path: Path) -> Path:
    artifact = tmp_path / "read-only-native-artifact"
    lane_attempt_id = "native-fastcheck:read-only"
    transcript = NativeTranscript(
        lane_attempt_id=lane_attempt_id,
        provider="codex",
        model="gpt-5.5",
        items=(
            NativeTranscriptItem(
                sequence=1,
                turn_id="turn-1",
                lane_attempt_id=lane_attempt_id,
                provider="codex",
                model="gpt-5.5",
                kind="function_call",
                call_id="call-read-1",
                tool_name="read_file",
                arguments_json_text='{"path":"vm.js"}',
            ),
            NativeTranscriptItem(
                sequence=2,
                turn_id="turn-1",
                lane_attempt_id=lane_attempt_id,
                provider="codex",
                model="gpt-5.5",
                kind="function_call_output",
                call_id="call-read-1",
                tool_name="read_file",
                status="completed",
                output_text_or_ref="read_file result: completed",
            ),
        ),
    )
    write_native_transcript_artifacts(artifact, transcript)
    return artifact


def _write_native_artifact_with_search_output(tmp_path: Path, *, output_text: str) -> Path:
    artifact = tmp_path / "native-search-artifact"
    lane_attempt_id = "native-fastcheck:search"
    transcript = NativeTranscript(
        lane_attempt_id=lane_attempt_id,
        provider="codex",
        model="gpt-5.5",
        items=(
            NativeTranscriptItem(
                sequence=1,
                turn_id="turn-1",
                lane_attempt_id=lane_attempt_id,
                provider="codex",
                model="gpt-5.5",
                kind="function_call",
                call_id="call-search-1",
                tool_name="search_text",
                arguments_json_text='{"path":".","query":"syscall"}',
            ),
            NativeTranscriptItem(
                sequence=2,
                turn_id="turn-1",
                lane_attempt_id=lane_attempt_id,
                provider="codex",
                model="gpt-5.5",
                kind="function_call_output",
                call_id="call-search-1",
                tool_name="search_text",
                status="completed",
                output_text_or_ref=output_text,
            ),
            NativeTranscriptItem(
                sequence=3,
                turn_id="turn-2",
                lane_attempt_id=lane_attempt_id,
                provider="codex",
                model="gpt-5.5",
                kind="function_call",
                call_id="call-write-1",
                tool_name="write_file",
                arguments_json_text='{"path":"vm.js","content":"console.log(1)"}',
            ),
            NativeTranscriptItem(
                sequence=4,
                turn_id="turn-2",
                lane_attempt_id=lane_attempt_id,
                provider="codex",
                model="gpt-5.5",
                kind="function_call_output",
                call_id="call-write-1",
                tool_name="write_file",
                status="completed",
                output_text_or_ref="write_file result: completed",
            ),
            NativeTranscriptItem(
                sequence=5,
                turn_id="turn-3",
                lane_attempt_id=lane_attempt_id,
                provider="codex",
                model="gpt-5.5",
                kind="function_call",
                call_id="call-test-1",
                tool_name="run_tests",
                arguments_json_text='{"command":"node vm.js","command_intent":"verify"}',
            ),
            NativeTranscriptItem(
                sequence=6,
                turn_id="turn-3",
                lane_attempt_id=lane_attempt_id,
                provider="codex",
                model="gpt-5.5",
                kind="function_call_output",
                call_id="call-test-1",
                tool_name="run_tests",
                status="completed",
                output_text_or_ref="run_tests result: completed",
            ),
        ),
    )
    write_native_transcript_artifacts(artifact, transcript)
    return artifact


def test_hot_path_fastcheck_accepts_native_transcript_artifact_without_history(tmp_path):
    artifact = _write_native_artifact(tmp_path)

    result = run_hot_path_fastcheck(artifact)

    assert result["status"] == "pass"
    assert result["history_path"] == ""
    assert result["transcript_path"].endswith("response_transcript.json")
    checks = {check["name"]: check for check in result["checks"]}
    assert checks["native_manifest_contract"]["status"] == "pass"
    assert checks["native_response_items_match"]["status"] == "pass"
    assert result["micro_next_action_refresh"]["reason"] == "native_transcript_mode"


def test_hot_path_fastcheck_surfaces_large_native_write_generation(tmp_path):
    artifact = tmp_path / "large-native-write"
    lane_attempt_id = "native-fastcheck:large-write"
    transcript = NativeTranscript(
        lane_attempt_id=lane_attempt_id,
        provider="codex",
        model="gpt-5.5",
        items=(
            NativeTranscriptItem(
                sequence=1,
                turn_id="turn-1",
                lane_attempt_id=lane_attempt_id,
                provider="codex",
                model="gpt-5.5",
                kind="function_call",
                call_id="call-write-1",
                tool_name="write_file",
                arguments_json_text=json.dumps(
                    {
                        "path": "vm.js",
                        "content": None,
                        "content_lines": ["console.log(1);"] * 1200,
                    }
                ),
            ),
            NativeTranscriptItem(
                sequence=2,
                turn_id="turn-1",
                lane_attempt_id=lane_attempt_id,
                provider="codex",
                model="gpt-5.5",
                kind="function_call_output",
                call_id="call-write-1",
                tool_name="write_file",
                status="completed",
            ),
            NativeTranscriptItem(
                sequence=3,
                turn_id="turn-2",
                lane_attempt_id=lane_attempt_id,
                provider="codex",
                model="gpt-5.5",
                kind="function_call",
                call_id="call-test-1",
                tool_name="run_tests",
                arguments_json_text='{"command":"node vm.js"}',
            ),
            NativeTranscriptItem(
                sequence=4,
                turn_id="turn-2",
                lane_attempt_id=lane_attempt_id,
                provider="codex",
                model="gpt-5.5",
                kind="function_call_output",
                call_id="call-test-1",
                tool_name="run_tests",
                status="completed",
                output_text_or_ref="run_tests result: completed",
            ),
        ),
    )
    write_native_transcript_artifacts(artifact, transcript)

    result = run_hot_path_fastcheck(artifact)

    assert result["status"] == "pass"
    checks = {check["name"]: check for check in result["checks"]}
    details = checks["native_generation_observation"]["details"]
    assert checks["native_generation_observation"]["status"] == "pass"
    assert details["large_write_generation_suspected"] is True
    assert details["first_write_content_lines_count"] == 1200
    assert result["metrics"]["native_generation"]["large_write_argument_count"] == 1


def test_hot_path_fastcheck_replays_native_provider_request_compact_digest(tmp_path):
    artifact = _write_native_artifact(tmp_path)
    _write_native_provider_request(artifact, _read_native_transcript(artifact))

    result = run_hot_path_fastcheck(artifact)

    assert result["status"] == "pass"
    checks = {check["name"]: check for check in result["checks"]}
    assert checks["native_affordance_visibility_caps"]["status"] == "pass"
    assert checks["native_compact_digest_replay"]["status"] == "pass"
    assert checks["native_provider_visible_state"]["status"] == "pass"


def test_hot_path_fastcheck_replays_live_provider_request_body_shape(tmp_path):
    artifact = _write_native_artifact(tmp_path)
    transcript = _read_native_transcript(artifact)
    _write_native_provider_request(artifact, transcript, prefix_item_count=2, live_shape=True)

    result = run_hot_path_fastcheck(artifact)

    assert result["status"] == "pass"
    checks = {check["name"]: check for check in result["checks"]}
    assert checks["native_compact_digest_replay"]["details"]["checked_requests"] == 1
    assert checks["native_provider_visible_state"]["status"] == "pass"


def test_hot_path_fastcheck_allows_task_source_todo_in_function_output(tmp_path):
    artifact = _write_native_artifact(tmp_path)
    transcript = _read_native_transcript(artifact)
    _write_native_provider_request(artifact, transcript, prefix_item_count=2, live_shape=True)
    request_file = artifact / "native-provider-requests.json"
    payload = json.loads(request_file.read_text(encoding="utf-8"))
    payload["requests"][0]["request_body"]["input"].append(
        {
            "type": "function_call_output",
            "call_id": "call-read",
            "output": "stdout:\n1117:    // TODO: Implement stat syscall\n",
        }
    )
    request_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    result = run_hot_path_fastcheck(artifact)

    checks = {check["name"]: check for check in result["checks"]}
    assert checks["native_provider_visible_state"]["status"] == "pass"


def test_hot_path_fastcheck_allows_task_source_todo_in_transcript_output(tmp_path):
    artifact = _write_native_artifact(tmp_path)
    transcript = _read_native_transcript(artifact)
    _write_native_provider_request(artifact, transcript, prefix_item_count=2)
    request_file = artifact / "native-provider-requests.json"
    payload = json.loads(request_file.read_text(encoding="utf-8"))
    payload["requests"][0]["transcript_window"].append(
        {
            "kind": "function_call_output",
            "call_id": "call-read",
            "output_text_or_ref": "stdout:\n1117:    // TODO: Implement stat syscall\n",
        }
    )
    request_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    result = run_hot_path_fastcheck(artifact)

    checks = {check["name"]: check for check in result["checks"]}
    assert checks["native_provider_visible_state"]["status"] == "pass"


def test_hot_path_fastcheck_rejects_specific_steering_in_function_output(tmp_path):
    artifact = _write_native_artifact(tmp_path)
    transcript = _read_native_transcript(artifact)
    _write_native_provider_request(artifact, transcript, prefix_item_count=2, live_shape=True)
    request_file = artifact / "native-provider-requests.json"
    payload = json.loads(request_file.read_text(encoding="utf-8"))
    payload["requests"][0]["request_body"]["input"].append(
        {
            "type": "function_call_output",
            "call_id": "call-read",
            "output": "next_action_policy: patch now",
        }
    )
    request_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    result = run_hot_path_fastcheck(artifact)

    checks = {check["name"]: check for check in result["checks"]}
    assert checks["native_provider_visible_state"]["status"] == "fail"
    assert any(
        violation["reason"] == "legacy_state_leak"
        for violation in checks["native_provider_visible_state"]["details"]["violations"]
    )


def test_hot_path_fastcheck_rejects_specific_steering_in_transcript_output(tmp_path):
    artifact = _write_native_artifact(tmp_path)
    transcript = _read_native_transcript(artifact)
    _write_native_provider_request(artifact, transcript, prefix_item_count=2)
    request_file = artifact / "native-provider-requests.json"
    payload = json.loads(request_file.read_text(encoding="utf-8"))
    payload["requests"][0]["transcript_window"].append(
        {
            "kind": "custom_tool_call_output",
            "call_id": "call-read",
            "output_text_or_ref": "next_action_policy: patch now",
        }
    )
    request_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    result = run_hot_path_fastcheck(artifact)

    checks = {check["name"]: check for check in result["checks"]}
    assert checks["native_provider_visible_state"]["status"] == "fail"
    assert any(
        violation["reason"] == "legacy_state_leak"
        for violation in checks["native_provider_visible_state"]["details"]["violations"]
    )


def test_hot_path_fastcheck_requires_previous_response_id_for_multi_turn_live_provider_requests(tmp_path):
    artifact = _write_native_artifact(tmp_path)
    transcript = _read_native_transcript(artifact)
    _write_native_provider_request(artifact, transcript, prefix_item_count=2, live_shape=True)
    request_file = artifact / "native-provider-requests.json"
    payload = json.loads(request_file.read_text(encoding="utf-8"))
    first_request = dict(payload["requests"][0])
    second_request = json.loads(json.dumps(first_request))
    second_request["turn_index"] = 2
    payload["request_count"] = 2
    payload["requests"] = [first_request, second_request]
    request_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    result = run_hot_path_fastcheck(artifact)

    checks = {check["name"]: check for check in result["checks"]}
    assert checks["native_previous_response_id"]["status"] == "fail"
    assert checks["native_previous_response_id"]["details"]["missing"][0]["request"] == 2


def test_hot_path_fastcheck_accepts_previous_response_id_for_multi_turn_live_provider_requests(tmp_path):
    artifact = _write_native_artifact(tmp_path)
    transcript = _read_native_transcript(artifact)
    _write_native_provider_request(artifact, transcript, prefix_item_count=2, live_shape=True)
    request_file = artifact / "native-provider-requests.json"
    payload = json.loads(request_file.read_text(encoding="utf-8"))
    first_request = dict(payload["requests"][0])
    second_request = json.loads(json.dumps(first_request))
    second_request["turn_index"] = 2
    second_request["previous_response_id"] = "resp-prev"
    second_request["previous_response_id_in_request_body"] = True
    second_request["previous_response_delta_mode"] = "delta_with_context_refresh"
    second_request["previous_response_suppressed_context_refresh_item_count"] = 0
    second_request["previous_response_leading_refresh_item_count"] = 1
    second_request["request_body"]["previous_response_id"] = "resp-prev"
    output_item = {
        "type": "function_call_output",
        "call_id": "call-read",
        "output": "read_file result: completed",
    }
    second_request["logical_input_items"] = list(first_request["request_body"]["input"]) + [output_item]
    second_request["suppressed_context_refresh_items"] = []
    second_request["request_body"]["input"] = list(first_request["request_body"]["input"]) + [output_item]
    inventory = dict(second_request["provider_request_inventory"])
    inventory["model_visible_sections"] = ["native_transcript_window", "compact_sidecar_digest"]
    inventory["compact_sidecar_digest_wire_visible"] = True
    inventory["previous_response_delta_mode"] = "delta_with_context_refresh"
    inventory["previous_response_suppressed_context_refresh_item_count"] = 0
    inventory["previous_response_leading_refresh_item_count"] = 1
    second_request["provider_request_inventory"] = inventory
    payload["request_count"] = 2
    payload["requests"] = [first_request, second_request]
    request_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    result = run_hot_path_fastcheck(artifact)

    checks = {check["name"]: check for check in result["checks"]}
    assert checks["native_previous_response_id"]["status"] == "pass"
    assert checks["native_previous_response_id"]["details"]["observed"] == 1


def test_hot_path_fastcheck_rejects_suppressed_context_without_task_refresh(tmp_path):
    artifact = _write_native_artifact(tmp_path)
    transcript = _read_native_transcript(artifact)
    _write_native_provider_request(artifact, transcript, prefix_item_count=2, live_shape=True)
    request_file = artifact / "native-provider-requests.json"
    payload = json.loads(request_file.read_text(encoding="utf-8"))
    request = payload["requests"][0]
    request["previous_response_id"] = "resp-prev"
    request["previous_response_id_in_request_body"] = True
    request["previous_response_delta_mode"] = "delta_minimal_context_refresh"
    request["previous_response_suppressed_context_refresh_item_count"] = 1
    request["previous_response_leading_refresh_item_count"] = 0
    request["request_body"]["previous_response_id"] = "resp-prev"
    request["request_body"]["input"] = [
        {
            "type": "function_call_output",
            "call_id": "call-read",
            "output": "read_file result: completed",
        }
    ]
    inventory = dict(request["provider_request_inventory"])
    inventory["model_visible_sections"] = ["native_transcript_window"]
    inventory["compact_sidecar_digest_wire_visible"] = False
    inventory["previous_response_delta_mode"] = "delta_minimal_context_refresh"
    inventory["previous_response_suppressed_context_refresh_item_count"] = 1
    inventory["previous_response_leading_refresh_item_count"] = 0
    request["provider_request_inventory"] = inventory
    request_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    result = run_hot_path_fastcheck(artifact)

    checks = {check["name"]: check for check in result["checks"]}
    assert checks["native_provider_visible_state"]["status"] == "fail"
    assert any(
        violation["reason"] == "suppressed_context_refresh_without_task_context_refresh"
        for violation in checks["native_provider_visible_state"]["details"]["violations"]
    )


def test_hot_path_fastcheck_rejects_hidden_digest_wire_leak(tmp_path):
    artifact = _write_native_artifact(tmp_path)
    transcript = _read_native_transcript(artifact)
    _write_native_provider_request(artifact, transcript, live_shape=True)
    request_file = artifact / "native-provider-requests.json"
    payload = json.loads(request_file.read_text(encoding="utf-8"))
    request = payload["requests"][0]
    inventory = dict(request["provider_request_inventory"])
    inventory["compact_sidecar_digest_wire_visible"] = False
    inventory["model_visible_sections"] = ["native_transcript_window", "task_context_refresh"]
    request["provider_request_inventory"] = inventory
    request_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    result = run_hot_path_fastcheck(artifact)

    checks = {check["name"]: check for check in result["checks"]}
    assert checks["native_provider_visible_state"]["status"] == "fail"
    assert any(
        violation["reason"] == "compact_sidecar_digest_wire_leak"
        for violation in checks["native_provider_visible_state"]["details"]["violations"]
    )


def test_hot_path_fastcheck_replays_live_openai_request_against_codex_digest_identity(tmp_path):
    artifact = _write_native_artifact(tmp_path)
    transcript = _read_native_transcript(artifact)
    _write_native_provider_request(artifact, transcript, prefix_item_count=2, live_shape=True)
    request_file = artifact / "native-provider-requests.json"
    payload = json.loads(request_file.read_text(encoding="utf-8"))
    payload["requests"][0]["provider"] = "openai"
    request_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    result = run_hot_path_fastcheck(artifact)

    checks = {check["name"]: check for check in result["checks"]}
    assert checks["native_compact_digest_replay"]["status"] == "pass"


def test_hot_path_fastcheck_replays_hard_runtime_native_request_thresholds(tmp_path):
    artifact = tmp_path / "native-hard-runtime-artifact"
    lane_attempt_id = "native-fastcheck:hard-runtime"
    items: list[NativeTranscriptItem] = []
    for index in range(10):
        call_id = f"call-read-{index}"
        items.extend(
            [
                NativeTranscriptItem(
                    sequence=len(items) + 1,
                    turn_id=f"turn-{index + 1}",
                    lane_attempt_id=lane_attempt_id,
                    provider="codex",
                    model="gpt-5.5",
                    kind="function_call",
                    call_id=call_id,
                    tool_name="read_file",
                    arguments_json_text=json.dumps({"path": f"missing-{index}.txt"}, sort_keys=True),
                ),
                NativeTranscriptItem(
                    sequence=len(items) + 2,
                    turn_id=f"turn-{index + 1}",
                    lane_attempt_id=lane_attempt_id,
                    provider="codex",
                    model="gpt-5.5",
                    kind="function_call_output",
                    call_id=call_id,
                    tool_name="read_file",
                    status="completed",
                    output_text_or_ref="read_file result: completed",
                ),
            ]
        )
    transcript = NativeTranscript(
        lane_attempt_id=lane_attempt_id,
        provider="codex",
        model="gpt-5.5",
        items=tuple(items),
    )
    write_native_transcript_artifacts(artifact, transcript)
    hard_runtime_contract = {
        "goal": (
            "Implement a MIPS ELF interpreter from provided source code "
            "and write the rendered frame to /tmp/frame.bmp."
        )
    }
    _write_native_provider_request(
        artifact,
        transcript,
        prefix_item_count=len(transcript.items),
        task_contract=hard_runtime_contract,
    )

    result = run_hot_path_fastcheck(artifact)

    checks = {check["name"]: check for check in result["checks"]}
    assert checks["native_compact_digest_replay"]["status"] == "pass"
    assert checks["native_compact_digest_replay"]["details"]["checked_requests"] == 1


def test_hot_path_fastcheck_rejects_native_compact_digest_drift(tmp_path):
    artifact = _write_native_artifact(tmp_path)
    _write_native_provider_request(artifact, _read_native_transcript(artifact))
    task_payload = _native_request_payload(artifact)
    task_payload["compact_sidecar_digest"]["transcript_hash"] = "sha256:stale"  # type: ignore[index]
    _replace_native_request_payload(artifact, task_payload)

    result = run_hot_path_fastcheck(artifact)

    assert result["status"] == "fail"
    check = [item for item in result["checks"] if item["name"] == "native_compact_digest_replay"][0]
    assert check["status"] == "fail"
    assert check["details"]["mismatches"][0]["reason"] == "digest_mismatch"


def test_hot_path_fastcheck_rejects_default_native_required_next_leak(tmp_path):
    artifact = _write_native_artifact(tmp_path)
    _write_native_provider_request(artifact, _read_native_transcript(artifact))
    task_payload = _native_request_payload(artifact)
    task_payload["compact_sidecar_digest"]["required_next_kind"] = "patch"  # type: ignore[index]
    _replace_native_request_payload(artifact, task_payload)

    result = run_hot_path_fastcheck(artifact)

    assert result["status"] == "fail"
    check = [item for item in result["checks"] if item["name"] == "native_provider_visible_state"][0]
    assert check["status"] == "fail"
    assert check["details"]["violations"][0]["reason"] == "default_required_next_leak"


def test_hot_path_fastcheck_rejects_live_request_body_instruction_state_leak(tmp_path):
    artifact = _write_native_artifact(tmp_path)
    _write_native_provider_request(artifact, _read_native_transcript(artifact), live_shape=True)
    request_file = artifact / "native-provider-requests.json"
    payload = json.loads(request_file.read_text(encoding="utf-8"))
    payload["requests"][0]["request_body"]["instructions"] = "Use persisted_lane_state and next_action_policy."
    request_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    result = run_hot_path_fastcheck(artifact)

    assert result["status"] == "fail"
    check = [item for item in result["checks"] if item["name"] == "native_provider_visible_state"][0]
    assert check["status"] == "fail"
    assert check["details"]["violations"][0]["reason"] == "legacy_state_leak"


def test_hot_path_fastcheck_rejects_resolver_decision_hash_drift(tmp_path):
    artifact = _write_native_finish_artifact(tmp_path)
    decision_path = artifact / "resolver_decisions.jsonl"
    rows = [json.loads(line) for line in decision_path.read_text(encoding="utf-8").splitlines()]
    rows[0]["reason"] = "tampered"
    decision_path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")

    result = run_hot_path_fastcheck(artifact)

    assert result["status"] == "fail"
    check = [item for item in result["checks"] if item["name"] == "native_resolver_decisions"][0]
    assert check["status"] == "fail"
    assert check["details"]["sha_matches"] is False


def test_hot_path_fastcheck_rejects_native_evidence_observation_transcript_hash_drift(tmp_path):
    artifact = _write_native_finish_artifact(tmp_path)
    manifest_path = artifact / "proof-manifest.json"
    observation_path = artifact / "native-evidence-observation.json"
    observation = json.loads(observation_path.read_text(encoding="utf-8"))
    observation["transcript_hash"] = "stale-transcript-hash"
    observation_path.write_text(json.dumps(observation, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    updated_sha = "sha256:" + hashlib.sha256(observation_path.read_bytes()).hexdigest()
    manifest["native_evidence_observation_sha256"] = updated_sha
    manifest["metrics"]["native_evidence_observation"]["artifact_sha256"] = updated_sha
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    result = run_hot_path_fastcheck(artifact)

    assert result["status"] == "fail"
    check = [item for item in result["checks"] if item["name"] == "native_evidence_observation"][0]
    assert check["status"] == "fail"
    assert check["details"]["manifest_sha_matches"] is True
    assert check["details"]["transcript_hash_matches"] is False


def test_hot_path_fastcheck_accepts_native_finish_gate_decision_sidecar(tmp_path):
    artifact = _write_native_finish_gate_artifact(tmp_path)

    result = run_hot_path_fastcheck(artifact)

    checks = {item["name"]: item for item in result["checks"]}
    assert result["status"] == "pass"
    assert checks["native_finish_gate_decisions"]["status"] == "pass"
    assert checks["native_finish_gate_decisions"]["details"]["matching_closeout_ref_allow_count"] == 1
    assert checks["native_resolver_decisions"]["status"] == "pass"
    assert checks["native_resolver_decisions"]["details"]["native_finish_gate_decisions_present"] is True


def test_hot_path_fastcheck_surfaces_projection_warning_without_blocking_native_finish(tmp_path):
    artifact = _write_native_finish_gate_artifact(tmp_path, projection_warning=True)

    result = run_hot_path_fastcheck(artifact)

    checks = {item["name"]: item for item in result["checks"]}
    assert result["status"] == "pass"
    assert checks["native_finish_gate_decisions"]["status"] == "pass"
    assert checks["native_finish_gate_decisions"]["details"]["projection_warning_count"] == 1


def test_hot_path_fastcheck_rejects_native_finish_gate_decision_hash_drift(tmp_path):
    artifact = _write_native_finish_gate_artifact(tmp_path)
    decision_path = artifact / "native_finish_gate_decisions.jsonl"
    rows = [json.loads(line) for line in decision_path.read_text(encoding="utf-8").splitlines()]
    rows[0]["reason"] = "tampered"
    decision_path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")

    result = run_hot_path_fastcheck(artifact)

    checks = {item["name"]: item for item in result["checks"]}
    assert result["status"] == "fail"
    assert checks["native_finish_gate_decisions"]["status"] == "fail"
    assert checks["native_finish_gate_decisions"]["details"]["sha_matches"] is False


def test_hot_path_fastcheck_accepts_finish_verifier_planner_decision_sidecar(tmp_path):
    artifact = _write_native_finish_gate_artifact(tmp_path)
    _write_finish_verifier_planner_decisions(
        artifact,
        [
            {
                "status": "no_plan",
                "request_hash": "sha256:request",
                "raw_plan": None,
                "raw_plan_hash": "sha256:raw-plan",
                "reject_reason": "planner returned no plan",
                "reject_blockers": ["planner_plan_not_mapping"],
                "fallback": {},
                "fallback_source": "",
            }
        ],
    )

    result = run_hot_path_fastcheck(artifact)

    checks = {item["name"]: item for item in result["checks"]}
    assert result["status"] == "pass"
    assert checks["finish_verifier_planner_decisions"]["status"] == "pass"
    assert checks["finish_verifier_planner_decisions"]["details"]["row_count"] == 1


def test_hot_path_fastcheck_accepts_visible_planner_rejection_fallback_provenance(tmp_path):
    artifact = _write_native_finish_gate_artifact(
        tmp_path,
        finish_verifier_plan={
            "source": "auto_detected_verifier",
            "provenance": {
                "fallback_after_finish_verifier_planner": {
                    "status": "rejected",
                    "fallback_source": "auto_detected_verifier",
                    "reject_reason": "finish verifier command is a no-op success",
                    "reject_blockers": ["finish_verifier_noop_success"],
                }
            },
        },
    )
    _write_finish_verifier_planner_decisions(
        artifact,
        [
            {
                "status": "rejected",
                "request_hash": "sha256:request",
                "raw_plan": {"command": "true"},
                "raw_plan_hash": "sha256:raw-plan",
                "reject_reason": "finish verifier command is a no-op success",
                "reject_blockers": ["finish_verifier_noop_success"],
                "fallback": {"command": "node vm.js", "source": "auto_detected_verifier"},
                "fallback_source": "auto_detected_verifier",
            }
        ],
    )

    result = run_hot_path_fastcheck(artifact)

    checks = {item["name"]: item for item in result["checks"]}
    assert result["status"] == "pass"
    assert checks["finish_verifier_planner_decisions"]["status"] == "pass"


def test_hot_path_fastcheck_rejects_hidden_auto_fallback_after_planner_rejection(tmp_path):
    artifact = _write_native_finish_gate_artifact(tmp_path)
    _write_finish_verifier_planner_decisions(
        artifact,
        [
            {
                "status": "rejected",
                "request_hash": "sha256:request",
                "raw_plan": {"command": "true"},
                "raw_plan_hash": "sha256:raw-plan",
                "reject_reason": "finish verifier command is a no-op success",
                "reject_blockers": ["finish_verifier_noop_success"],
                "fallback": {"command": "node vm.js", "source": "auto_detected_verifier"},
                "fallback_source": "auto_detected_verifier",
            }
        ],
    )

    result = run_hot_path_fastcheck(artifact)

    checks = {item["name"]: item for item in result["checks"]}
    assert result["status"] == "fail"
    assert checks["finish_verifier_planner_decisions"]["status"] == "fail"
    assert checks["finish_verifier_planner_decisions"]["details"]["fallback_rows_hidden"] == [
        {"status": "rejected", "fallback_source": "auto_detected_verifier"}
    ]


def test_hot_path_fastcheck_rejects_status_only_planner_fallback_provenance(tmp_path):
    artifact = _write_native_finish_gate_artifact(
        tmp_path,
        finish_verifier_plan={
            "source": "auto_detected_verifier",
            "provenance": {
                "fallback_after_finish_verifier_planner": {
                    "status": "rejected",
                    "fallback_source": "auto_detected_verifier",
                }
            },
        },
    )
    _write_finish_verifier_planner_decisions(
        artifact,
        [
            {
                "status": "rejected",
                "request_hash": "sha256:request",
                "raw_plan": {"command": "true"},
                "raw_plan_hash": "sha256:raw-plan",
                "reject_reason": "finish verifier command is a no-op success",
                "reject_blockers": ["finish_verifier_noop_success"],
                "fallback": {"command": "node vm.js", "source": "auto_detected_verifier"},
                "fallback_source": "auto_detected_verifier",
            }
        ],
    )

    result = run_hot_path_fastcheck(artifact)

    checks = {item["name"]: item for item in result["checks"]}
    assert result["status"] == "fail"
    assert checks["finish_verifier_planner_decisions"]["status"] == "fail"
    assert checks["finish_verifier_planner_decisions"]["details"]["fallback_rows_hidden"] == [
        {"status": "rejected", "fallback_source": "auto_detected_verifier"}
    ]


def test_hot_path_fastcheck_rejects_finish_verifier_planner_metric_drift(tmp_path):
    artifact = _write_native_finish_gate_artifact(
        tmp_path,
        finish_verifier_plan={"source": "finish_verifier_planner"},
    )
    _write_finish_verifier_planner_decisions(
        artifact,
        [
            {
                "status": "accepted",
                "request_hash": "sha256:request",
                "raw_plan": {"command": "node vm.js"},
                "raw_plan_hash": "sha256:raw-plan",
                "accepted_plan": {"command": "node vm.js"},
            }
        ],
    )
    manifest_path = artifact / "proof-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["metrics"]["finish_verifier_planner_decisions"]["artifact_sha256"] = "sha256:stale"
    manifest["metrics"]["finish_verifier_planner_decisions"]["accepted_count"] = 0
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    result = run_hot_path_fastcheck(artifact)

    checks = {item["name"]: item for item in result["checks"]}
    assert result["status"] == "fail"
    assert checks["finish_verifier_planner_decisions"]["status"] == "fail"
    assert checks["finish_verifier_planner_decisions"]["details"]["metric_artifact_sha256_matches"] is False
    assert checks["finish_verifier_planner_decisions"]["details"]["metric_status_count_mismatches"] == {
        "accepted_count": {"expected": 1, "observed": 0}
    }


def test_hot_path_fastcheck_rejects_resolver_fallback_when_trusted_closeout_pass_needs_native_sidecar(tmp_path):
    artifact = _write_native_finish_gate_artifact(tmp_path)
    manifest_path = artifact / "proof-manifest.json"
    decision = CompletionResolverDecision(
        decision_id="resolver:turn-2:finish-1",
        lane_attempt_id="native-fastcheck:finish-gate",
        turn_id="turn-2",
        finish_call_id="finish-1",
        finish_output_call_id="finish-1",
        lane_status="completed",
        result="allow",
        evidence_refs=("ev:closeout:terminal",),
        closeout_refs=("implement-v2-exec://attempt/final-verifier/terminal",),
        reason="legacy resolver fallback",
    )
    write_completion_resolver_artifacts(artifact, [decision], proof_manifest_path=manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.pop("native_finish_gate_decisions_ref", None)
    manifest.pop("native_finish_gate_decisions_sha256", None)
    manifest.get("metrics", {}).pop("native_finish_gate_decisions", None)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (artifact / "native_finish_gate_decisions.jsonl").unlink()

    result = run_hot_path_fastcheck(artifact)

    checks = {item["name"]: item for item in result["checks"]}
    assert result["status"] == "fail"
    assert checks["native_finish_gate_decisions"]["status"] == "fail"
    assert checks["native_finish_gate_decisions"]["details"]["resolver_fallback_present"] is True
    assert checks["native_finish_gate_decisions"]["details"]["trusted_final_verifier_closeout_pass_present"] is True


def test_hot_path_fastcheck_rejects_native_finish_gate_bogus_closeout_ref(tmp_path):
    artifact = _write_native_finish_gate_artifact(tmp_path)
    manifest_path = artifact / "proof-manifest.json"
    decision_path = artifact / "native_finish_gate_decisions.jsonl"
    rows = [json.loads(line) for line in decision_path.read_text(encoding="utf-8").splitlines()]
    rows[0]["closeout_refs"] = ["bogus:closeout"]
    decision_path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["native_finish_gate_decisions_sha256"] = "sha256:" + hashlib.sha256(decision_path.read_bytes()).hexdigest()
    manifest["metrics"]["native_finish_gate_decisions"]["artifact_sha256"] = manifest[
        "native_finish_gate_decisions_sha256"
    ]
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    result = run_hot_path_fastcheck(artifact)

    checks = {item["name"]: item for item in result["checks"]}
    assert result["status"] == "fail"
    assert checks["native_finish_gate_decisions"]["status"] == "fail"
    assert checks["native_finish_gate_decisions"]["details"]["allow_rows_have_matching_closeout_refs"] is False


def test_hot_path_fastcheck_rejects_native_finish_gate_row_without_finish_call_id(tmp_path):
    artifact = _write_native_finish_gate_artifact(tmp_path)
    manifest_path = artifact / "proof-manifest.json"
    decision_path = artifact / "native_finish_gate_decisions.jsonl"
    rows = [json.loads(line) for line in decision_path.read_text(encoding="utf-8").splitlines()]
    rows[0]["finish_call_id"] = ""
    decision_path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["native_finish_gate_decisions_sha256"] = "sha256:" + hashlib.sha256(decision_path.read_bytes()).hexdigest()
    manifest["metrics"]["native_finish_gate_decisions"]["artifact_sha256"] = manifest[
        "native_finish_gate_decisions_sha256"
    ]
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    result = run_hot_path_fastcheck(artifact)

    checks = {item["name"]: item for item in result["checks"]}
    assert result["status"] == "fail"
    assert checks["native_finish_gate_decisions"]["status"] == "fail"
    assert checks["native_finish_gate_decisions"]["details"]["row_finish_ids_present"] is False


def test_hot_path_fastcheck_allows_native_finish_gate_expected_source_mutation_block(tmp_path):
    artifact = _write_native_finish_gate_artifact(tmp_path)
    manifest_path = artifact / "proof-manifest.json"
    decision_path = artifact / "native_finish_gate_decisions.jsonl"
    rows = [json.loads(line) for line in decision_path.read_text(encoding="utf-8").splitlines()]
    rows[0]["result"] = "block"
    rows[0]["lane_status"] = "blocked_continue"
    rows[0]["blockers"] = ["closeout_unexpected_source_mutation"]
    rows[0]["reason"] = "trusted final verifier passed but closeout mutated source unexpectedly"
    rows[0]["closeout"]["observed_unexpected_source_mutation"] = True
    rows[0]["closeout"]["blockers"] = ["closeout_unexpected_source_mutation"]
    decision_path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["native_finish_gate_decisions_sha256"] = "sha256:" + hashlib.sha256(decision_path.read_bytes()).hexdigest()
    manifest["metrics"]["native_finish_gate_decisions"]["artifact_sha256"] = manifest[
        "native_finish_gate_decisions_sha256"
    ]
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    result = run_hot_path_fastcheck(artifact)

    checks = {item["name"]: item for item in result["checks"]}
    assert result["status"] == "pass"
    assert checks["native_finish_gate_decisions"]["status"] == "pass"
    assert checks["native_finish_gate_decisions"]["details"]["trusted_closeout_pass_rows_allow_completed"] is True
    assert checks["native_finish_gate_decisions"]["details"]["expected_unexpected_source_mutation_block_finish_ids"] == [
        "finish-1"
    ]


def test_hot_path_fastcheck_rejects_source_mutation_block_without_closeout_ref(tmp_path):
    artifact = _write_native_finish_gate_artifact(tmp_path)
    manifest_path = artifact / "proof-manifest.json"
    decision_path = artifact / "native_finish_gate_decisions.jsonl"
    rows = [json.loads(line) for line in decision_path.read_text(encoding="utf-8").splitlines()]
    rows[0]["result"] = "block"
    rows[0]["lane_status"] = "blocked_continue"
    rows[0]["blockers"] = ["closeout_unexpected_source_mutation"]
    rows[0]["reason"] = "trusted final verifier passed but closeout mutated source unexpectedly"
    rows[0]["closeout"]["observed_unexpected_source_mutation"] = True
    rows[0]["closeout"]["blockers"] = ["closeout_unexpected_source_mutation"]
    rows[0]["closeout_refs"] = []
    decision_path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["native_finish_gate_decisions_sha256"] = "sha256:" + hashlib.sha256(decision_path.read_bytes()).hexdigest()
    manifest["metrics"]["native_finish_gate_decisions"]["artifact_sha256"] = manifest[
        "native_finish_gate_decisions_sha256"
    ]
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    result = run_hot_path_fastcheck(artifact)

    checks = {item["name"]: item for item in result["checks"]}
    assert result["status"] == "fail"
    assert checks["native_finish_gate_decisions"]["status"] == "fail"
    assert checks["native_finish_gate_decisions"]["details"]["trusted_closeout_pass_rows_allow_completed"] is False
    assert checks["native_finish_gate_decisions"]["details"]["expected_unexpected_source_mutation_block_finish_ids"] == []


def test_hot_path_fastcheck_ignores_synthetic_cancelled_finish_after_trusted_closeout(tmp_path):
    artifact = tmp_path / "native-finish-gate-cancelled-finish-artifact"
    lane_attempt_id = "native-fastcheck:finish-gate-cancelled"
    items = (
        NativeTranscriptItem(
            sequence=1,
            turn_id="turn-1",
            lane_attempt_id=lane_attempt_id,
            provider="codex",
            model="gpt-5.5",
            kind="function_call",
            call_id="call-write-1",
            tool_name="write_file",
            arguments_json_text='{"path":"vm.js","content":"console.log(1)"}',
        ),
        NativeTranscriptItem(
            sequence=2,
            turn_id="turn-1",
            lane_attempt_id=lane_attempt_id,
            provider="codex",
            model="gpt-5.5",
            kind="function_call_output",
            call_id="call-write-1",
            tool_name="write_file",
            status="completed",
            output_text_or_ref="write_file result: completed",
        ),
        NativeTranscriptItem(
            sequence=3,
            turn_id="turn-2",
            lane_attempt_id=lane_attempt_id,
            provider="codex",
            model="gpt-5.5",
            kind="finish_call",
            call_id="finish-1",
            tool_name="finish",
            arguments_json_text='{"outcome":"completed","summary":"done"}',
        ),
        NativeTranscriptItem(
            sequence=4,
            turn_id="turn-2",
            lane_attempt_id=lane_attempt_id,
            provider="codex",
            model="gpt-5.5",
            kind="finish_call",
            call_id="finish-2",
            tool_name="finish",
            arguments_json_text='{"outcome":"completed","summary":"duplicate"}',
        ),
        NativeTranscriptItem(
            sequence=5,
            turn_id="turn-2",
            lane_attempt_id=lane_attempt_id,
            provider="codex",
            model="gpt-5.5",
            kind="function_call",
            call_id="call-final-verifier-closeout-001",
            tool_name="exec_command",
            arguments_json_text='{"command":"node vm.js","command_intent":"finish_verifier"}',
        ),
        NativeTranscriptItem(
            sequence=6,
            turn_id="turn-2",
            lane_attempt_id=lane_attempt_id,
            provider="codex",
            model="gpt-5.5",
            kind="function_call_output",
            call_id="call-final-verifier-closeout-001",
            tool_name="exec_command",
            status="completed",
            output_text_or_ref="command exited 0",
            evidence_refs=("ev:closeout:terminal",),
            sidecar_refs=("implement-v2-exec://attempt/final-verifier/terminal",),
        ),
        NativeTranscriptItem(
            sequence=7,
            turn_id="turn-2",
            lane_attempt_id=lane_attempt_id,
            provider="codex",
            model="gpt-5.5",
            kind="finish_output",
            call_id="finish-1",
            tool_name="finish",
            status="completed",
            output_text_or_ref="finish result: completed",
        ),
        NativeTranscriptItem(
            sequence=8,
            turn_id="turn-2",
            lane_attempt_id=lane_attempt_id,
            provider="codex",
            model="gpt-5.5",
            kind="finish_output",
            call_id="finish-2",
            tool_name="finish",
            status="synthetic_error",
            is_error=True,
            output_text_or_ref="cancelled because finish call finish-1 completed",
        ),
    )
    transcript = NativeTranscript(
        lane_attempt_id=lane_attempt_id,
        provider="codex",
        model="gpt-5.5",
        items=items,
    )
    paths = write_native_transcript_artifacts(artifact, transcript)
    prefix = NativeTranscript(
        lane_attempt_id=lane_attempt_id,
        provider="codex",
        model="gpt-5.5",
        items=items[:6],
    )
    decision = NativeFinishGateDecision(
        decision_id="native-finish-gate:turn-2:finish-1",
        lane_attempt_id=lane_attempt_id,
        turn_id="turn-2",
        finish_call_id="finish-1",
        lane_status="completed",
        result="allow",
        closeout=NativeFinishCloseoutResult(
            command=None,
            call_item=items[4].as_dict(),
            output_item=items[5].as_dict(),
            tool_result=None,
            status="completed_zero",
            exit_code=0,
            typed_evidence_projection_status="passed",
            evidence_refs=("ev:closeout:terminal",),
            closeout_refs=("implement-v2-exec://attempt/final-verifier/terminal",),
        ),
        evidence_refs=("ev:closeout:terminal",),
        closeout_refs=("implement-v2-exec://attempt/final-verifier/terminal",),
        transcript_hash_before_decision=native_transcript_hash(prefix),
        compact_sidecar_digest_hash="sha256:compact-digest",
        reason="trusted final verifier closeout exited 0",
    )
    write_native_finish_gate_artifacts(artifact, [decision], proof_manifest_path=paths["proof_manifest"])
    write_native_evidence_observation(artifact, transcript, proof_manifest_path=paths["proof_manifest"])

    result = run_hot_path_fastcheck(artifact)

    checks = {item["name"]: item for item in result["checks"]}
    assert result["status"] == "pass"
    assert checks["native_finish_gate_decisions"]["status"] == "pass"
    assert checks["native_finish_gate_decisions"]["details"]["trusted_closeout_pass_finish_ids"] == ["finish-1"]


def test_hot_path_fastcheck_rejects_native_finish_gate_block_for_trusted_closeout_pass(tmp_path):
    artifact = _write_native_finish_gate_artifact(tmp_path)
    manifest_path = artifact / "proof-manifest.json"
    decision_path = artifact / "native_finish_gate_decisions.jsonl"
    rows = [json.loads(line) for line in decision_path.read_text(encoding="utf-8").splitlines()]
    rows[0]["result"] = "block"
    rows[0]["lane_status"] = "blocked_continue"
    rows[0]["blockers"] = ["tampered-block"]
    decision_path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["native_finish_gate_decisions_sha256"] = "sha256:" + hashlib.sha256(decision_path.read_bytes()).hexdigest()
    manifest["metrics"]["native_finish_gate_decisions"]["artifact_sha256"] = manifest[
        "native_finish_gate_decisions_sha256"
    ]
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    result = run_hot_path_fastcheck(artifact)

    checks = {item["name"]: item for item in result["checks"]}
    assert result["status"] == "fail"
    assert checks["native_finish_gate_decisions"]["status"] == "fail"
    assert checks["native_finish_gate_decisions"]["details"]["trusted_closeout_pass_rows_allow_completed"] is False
    assert (
        checks["native_finish_gate_decisions"]["details"]["trusted_closeout_pass_rows_have_matching_closeout_refs"]
        is False
    )


def test_hot_path_fastcheck_rejects_extra_resolver_decision_row_even_with_matching_hash(tmp_path):
    artifact = _write_native_finish_artifact(tmp_path)
    manifest_path = artifact / "proof-manifest.json"
    decision_path = artifact / "resolver_decisions.jsonl"
    rows = [json.loads(line) for line in decision_path.read_text(encoding="utf-8").splitlines()]
    extra = dict(rows[0])
    extra["decision_id"] = "resolver:turn-extra:finish-extra"
    extra["turn_id"] = "turn-extra"
    extra["finish_call_id"] = "finish-extra"
    extra["finish_output_call_id"] = "finish-extra"
    decision_path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in (*rows, extra)), encoding="utf-8")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["resolver_decisions_sha256"] = "sha256:" + hashlib.sha256(decision_path.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    result = run_hot_path_fastcheck(artifact)

    assert result["status"] == "fail"
    check = [item for item in result["checks"] if item["name"] == "native_resolver_decisions"][0]
    assert check["status"] == "fail"
    assert check["details"]["sha_matches"] is True
    assert check["details"]["finish_calls_exact"] is False
    assert check["details"]["decision_count_matches_finish_count"] is False


def test_hot_path_fastcheck_allows_invalid_finish_retry_with_one_valid_resolver_decision(tmp_path):
    artifact = tmp_path / "native-finish-retry-artifact"
    lane_attempt_id = "native-fastcheck:finish-retry"
    transcript = NativeTranscript(
        lane_attempt_id=lane_attempt_id,
        provider="codex",
        model="gpt-5.5",
        items=(
            NativeTranscriptItem(
                sequence=1,
                turn_id="turn-1",
                lane_attempt_id=lane_attempt_id,
                provider="codex",
                model="gpt-5.5",
                kind="function_call",
                call_id="write-1",
                tool_name="write_file",
                arguments_json_text='{"path":"vm.js","content":"console.log(1)"}',
            ),
            NativeTranscriptItem(
                sequence=2,
                turn_id="turn-1",
                lane_attempt_id=lane_attempt_id,
                provider="codex",
                model="gpt-5.5",
                kind="function_call_output",
                call_id="write-1",
                tool_name="write_file",
                status="completed",
                output_text_or_ref="write_file result: completed",
            ),
            NativeTranscriptItem(
                sequence=3,
                turn_id="turn-2",
                lane_attempt_id=lane_attempt_id,
                provider="codex",
                model="gpt-5.5",
                kind="function_call",
                call_id="test-1",
                tool_name="run_tests",
                arguments_json_text='{"command":"node vm.js"}',
            ),
            NativeTranscriptItem(
                sequence=4,
                turn_id="turn-2",
                lane_attempt_id=lane_attempt_id,
                provider="codex",
                model="gpt-5.5",
                kind="function_call_output",
                call_id="test-1",
                tool_name="run_tests",
                status="completed",
                output_text_or_ref="run_tests result: completed",
                evidence_refs=("ev:verify-pass",),
            ),
            NativeTranscriptItem(
                sequence=5,
                turn_id="turn-3",
                lane_attempt_id=lane_attempt_id,
                provider="codex",
                model="gpt-5.5",
                kind="finish_call",
                call_id="finish-json",
                tool_name="finish",
                arguments_json_text="{not-json",
            ),
            NativeTranscriptItem(
                sequence=6,
                turn_id="turn-3",
                lane_attempt_id=lane_attempt_id,
                provider="codex",
                model="gpt-5.5",
                kind="finish_output",
                call_id="finish-json",
                tool_name="finish",
                status="invalid",
                is_error=True,
                output_text_or_ref="finish result: invalid; summary=invalid JSON arguments",
            ),
            NativeTranscriptItem(
                sequence=7,
                turn_id="turn-4",
                lane_attempt_id=lane_attempt_id,
                provider="codex",
                model="gpt-5.5",
                kind="finish_call",
                call_id="finish-ok",
                tool_name="finish",
                arguments_json_text='{"outcome":"completed","summary":"retried","evidence_refs":["ev:verify-pass"]}',
            ),
            NativeTranscriptItem(
                sequence=8,
                turn_id="turn-4",
                lane_attempt_id=lane_attempt_id,
                provider="codex",
                model="gpt-5.5",
                kind="finish_output",
                call_id="finish-ok",
                tool_name="finish",
                status="completed",
                output_text_or_ref="finish result: completed; summary=retried",
                evidence_refs=("ev:verify-pass",),
            ),
        ),
    )
    paths = write_native_transcript_artifacts(artifact, transcript)
    decision = CompletionResolverDecision(
        decision_id="resolver:turn-4:finish-ok",
        lane_attempt_id=lane_attempt_id,
        turn_id="turn-4",
        finish_call_id="finish-ok",
        finish_output_call_id="finish-ok",
        lane_status="completed",
        result="allow",
        evidence_refs=("ev:verify-pass",),
        reason="retried",
    )
    write_completion_resolver_artifacts(artifact, [decision], proof_manifest_path=paths["proof_manifest"])
    write_native_evidence_observation(artifact, transcript, resolver_decisions=[decision], proof_manifest_path=paths["proof_manifest"])

    result = run_hot_path_fastcheck(artifact)

    checks = {check["name"]: check for check in result["checks"]}
    assert checks["native_resolver_decisions"]["status"] == "pass"


def test_hot_path_fastcheck_allows_resolver_blocked_invalid_finish_output(tmp_path):
    artifact = tmp_path / "native-finish-blocked-artifact"
    lane_attempt_id = "native-fastcheck:finish-blocked"
    transcript = NativeTranscript(
        lane_attempt_id=lane_attempt_id,
        provider="codex",
        model="gpt-5.5",
        items=(
            NativeTranscriptItem(
                sequence=1,
                turn_id="turn-1",
                lane_attempt_id=lane_attempt_id,
                provider="codex",
                model="gpt-5.5",
                kind="function_call",
                call_id="write-1",
                tool_name="write_file",
                arguments_json_text='{"path":"vm.js","content":"console.log(1)"}',
            ),
            NativeTranscriptItem(
                sequence=2,
                turn_id="turn-1",
                lane_attempt_id=lane_attempt_id,
                provider="codex",
                model="gpt-5.5",
                kind="function_call_output",
                call_id="write-1",
                tool_name="write_file",
                status="completed",
                output_text_or_ref="write_file result: completed",
            ),
            NativeTranscriptItem(
                sequence=3,
                turn_id="turn-2",
                lane_attempt_id=lane_attempt_id,
                provider="codex",
                model="gpt-5.5",
                kind="function_call",
                call_id="test-1",
                tool_name="run_tests",
                arguments_json_text='{"command":"node vm.js"}',
            ),
            NativeTranscriptItem(
                sequence=4,
                turn_id="turn-2",
                lane_attempt_id=lane_attempt_id,
                provider="codex",
                model="gpt-5.5",
                kind="function_call_output",
                call_id="test-1",
                tool_name="run_tests",
                status="completed",
                output_text_or_ref="run_tests result: completed",
            ),
            NativeTranscriptItem(
                sequence=5,
                turn_id="turn-3",
                lane_attempt_id=lane_attempt_id,
                provider="codex",
                model="gpt-5.5",
                kind="finish_call",
                call_id="finish-blocked",
                tool_name="finish",
                arguments_json_text='{"outcome":"completed","summary":"needs verifier"}',
            ),
            NativeTranscriptItem(
                sequence=6,
                turn_id="turn-3",
                lane_attempt_id=lane_attempt_id,
                provider="codex",
                model="gpt-5.5",
                kind="finish_output",
                call_id="finish-blocked",
                tool_name="finish",
                status="invalid",
                is_error=True,
                output_text_or_ref="finish result: invalid; summary=finish blocked; more evidence or repair is required",
            ),
        ),
    )
    paths = write_native_transcript_artifacts(artifact, transcript)
    decision = CompletionResolverDecision(
        decision_id="resolver:turn-3:finish-blocked",
        lane_attempt_id=lane_attempt_id,
        turn_id="turn-3",
        finish_call_id="finish-blocked",
        finish_output_call_id="finish-blocked",
        lane_status="blocked_continue",
        result="block",
        blockers=("verifier_evidence_missing",),
        missing_obligations=("strict_verifier_evidence",),
        reason="finish blocked; more evidence or repair is required",
    )
    write_completion_resolver_artifacts(artifact, [decision], proof_manifest_path=paths["proof_manifest"])
    write_native_evidence_observation(artifact, transcript, resolver_decisions=[decision], proof_manifest_path=paths["proof_manifest"])

    result = run_hot_path_fastcheck(artifact)

    checks = {check["name"]: check for check in result["checks"]}
    assert checks["native_resolver_decisions"]["status"] == "pass"


def test_hot_path_fastcheck_accepts_fake_native_transport_kind(tmp_path):
    artifact = _write_native_artifact(tmp_path)
    manifest_path = artifact / "proof-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["transport_kind"] = "fake_native"
    manifest["native_transport_kind"] = "provider_native"
    manifest["metrics"]["transport_kind"] = "fake_native"
    manifest["metrics"]["native_transport_kind"] = "provider_native"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True), encoding="utf-8")

    result = run_hot_path_fastcheck(artifact)

    assert result["status"] == "pass"
    check = [item for item in result["checks"] if item["name"] == "native_manifest_contract"][0]
    assert check["details"]["native_transport"] is True


def test_hot_path_fastcheck_rejects_native_controller_steering_outputs(tmp_path):
    artifact = _write_native_artifact(tmp_path)
    transcript = _read_native_transcript(artifact)
    items = list(transcript.items)
    items.extend(
        [
            NativeTranscriptItem(
                sequence=7,
                turn_id="turn-4",
                lane_attempt_id=transcript.lane_attempt_id,
                provider=transcript.provider,
                model=transcript.model,
                kind="function_call",
                call_id="probe-after-first-write-due",
                tool_name="search_text",
                arguments_json_text='{"path":".","query":"main"}',
            ),
            NativeTranscriptItem(
                sequence=8,
                turn_id="turn-4",
                lane_attempt_id=transcript.lane_attempt_id,
                provider=transcript.provider,
                model=transcript.model,
                kind="function_call_output",
                call_id="probe-after-first-write-due",
                tool_name="search_text",
                status="invalid",
                is_error=True,
                output_text_or_ref=(
                    "search_text result: invalid; error=true; reason=first-write due overrun: "
                    "enough read/probe evidence has been gathered"
                ),
            ),
        ]
    )
    write_native_transcript_artifacts(
        artifact,
        NativeTranscript(
            lane_attempt_id=transcript.lane_attempt_id,
            provider=transcript.provider,
            model=transcript.model,
            items=tuple(items),
        ),
    )

    result = run_hot_path_fastcheck(artifact)

    checks = {check["name"]: check for check in result["checks"]}
    assert result["status"] == "fail"
    assert checks["native_trace_summary"]["details"]["parse_error_count"] == 0
    assert checks["native_controller_steering_outputs"]["status"] == "fail"
    assert checks["native_controller_steering_outputs"]["details"]["violations"][0]["call_id"] == (
        "probe-after-first-write-due"
    )


def test_hot_path_fastcheck_rejects_non_finish_invalid_json_output_in_trace_summary(tmp_path):
    artifact = _write_native_artifact(tmp_path)
    transcript = _read_native_transcript(artifact)
    items = list(transcript.items)
    items.extend(
        [
            NativeTranscriptItem(
                sequence=7,
                turn_id="turn-4",
                lane_attempt_id=transcript.lane_attempt_id,
                provider=transcript.provider,
                model=transcript.model,
                kind="function_call",
                call_id="bad-read-json",
                tool_name="read_file",
                arguments_json_text="{not-json",
            ),
            NativeTranscriptItem(
                sequence=8,
                turn_id="turn-4",
                lane_attempt_id=transcript.lane_attempt_id,
                provider=transcript.provider,
                model=transcript.model,
                kind="function_call_output",
                call_id="bad-read-json",
                tool_name="read_file",
                status="invalid",
                is_error=True,
                output_text_or_ref="read_file result: invalid; summary=invalid JSON arguments",
            ),
        ]
    )
    write_native_transcript_artifacts(
        artifact,
        NativeTranscript(
            lane_attempt_id=transcript.lane_attempt_id,
            provider=transcript.provider,
            model=transcript.model,
            items=tuple(items),
        ),
    )

    result = run_hot_path_fastcheck(artifact)

    checks = {check["name"]: check for check in result["checks"]}
    assert result["status"] == "fail"
    assert checks["native_trace_summary"]["details"]["parse_error_count"] == 1


def test_hot_path_fastcheck_rejects_read_only_native_artifact_without_trace(tmp_path):
    artifact = _write_read_only_native_artifact(tmp_path)

    result = run_hot_path_fastcheck(artifact)

    assert result["status"] == "fail"
    check = [item for item in result["checks"] if item["name"] == "native_trace_summary"][0]
    assert check["status"] == "fail"


def test_hot_path_fastcheck_rejects_read_only_native_artifact_with_empty_trace(tmp_path):
    artifact = _write_read_only_native_artifact(tmp_path)
    trace_dir = artifact / "normalized-trace"
    trace_dir.mkdir()
    (trace_dir / "summary.json").write_text("{}", encoding="utf-8")

    result = run_hot_path_fastcheck(artifact)

    assert result["status"] == "fail"
    check = [item for item in result["checks"] if item["name"] == "native_trace_summary"][0]
    assert check["status"] == "fail"


def test_hot_path_fastcheck_counts_native_process_source_observation_sidecar(tmp_path):
    artifact = _write_native_artifact(tmp_path)
    response_path = artifact / "response_transcript.json"
    data = json.loads(response_path.read_text(encoding="utf-8"))
    for item in data["items"]:
        if item.get("call_id") == "call-write-1":
            item["tool_name"] = "run_command"
            if item["kind"] == "function_call":
                item["arguments_json_text"] = '{"command":"python3 - <<\'PY\'\\nopen(\'vm.js\',\'w\').write(\'x\')\\nPY"}'
            else:
                item["output_text_or_ref"] = "run_command result: completed; exit_code=0"
    response_path.write_text(json.dumps(data), encoding="utf-8")
    items_path = artifact / "response_items.jsonl"
    items_path.write_text(
        "\n".join(json.dumps(item, ensure_ascii=False, sort_keys=True) for item in data["items"]) + "\n",
        encoding="utf-8",
    )
    (artifact / "tool_result_index.json").write_text(
        json.dumps(
            {
                "by_provider_call_id": {
                    "call-write-1": {
                        "changed_paths": ["vm.js"],
                        "mutation_refs": ["implement-v2-evidence://attempt/process_source_observation/call-write-1"],
                        "source_mutation_effect_kinds": ["process_source_observation"],
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    result = run_hot_path_fastcheck(artifact)

    checks = {check["name"]: check for check in result["checks"]}
    assert checks["native_trace_summary"]["status"] == "pass"
    assert checks["native_trace_summary"]["details"]["edit_count"] == 0
    assert checks["native_trace_summary"]["details"]["source_mutation_count"] == 1
    assert checks["native_trace_summary"]["details"]["process_source_mutation_count"] == 1


def test_hot_path_fastcheck_ignores_stale_native_process_source_observation_sidecar(tmp_path):
    artifact = _write_native_artifact(tmp_path)
    (artifact / "tool_result_index.json").write_text(
        json.dumps(
            {
                "by_provider_call_id": {
                    "stale-call": {
                        "changed_paths": ["vm.js"],
                        "mutation_refs": ["implement-v2-evidence://attempt/process_source_observation/stale-call"],
                        "source_mutation_effect_kinds": ["process_source_observation"],
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    result = run_hot_path_fastcheck(artifact)

    checks = {check["name"]: check for check in result["checks"]}
    assert checks["native_trace_summary"]["status"] == "pass"
    assert checks["native_trace_summary"]["details"]["edit_count"] == 1
    assert checks["native_trace_summary"]["details"]["source_mutation_count"] == 1
    assert checks["native_trace_summary"]["details"]["process_source_mutation_count"] == 0


def test_hot_path_fastcheck_rejects_process_source_observation_on_read_only_call(tmp_path):
    artifact = _write_read_only_native_artifact(tmp_path)
    (artifact / "tool_result_index.json").write_text(
        json.dumps(
            {
                "by_provider_call_id": {
                    "call-read-1": {
                        "tool_name": "run_command",
                        "changed_paths": ["vm.js"],
                        "mutation_refs": ["implement-v2-evidence://attempt/process_source_observation/call-read-1"],
                        "source_mutation_effect_kinds": ["process_source_observation"],
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    result = run_hot_path_fastcheck(artifact)

    checks = {check["name"]: check for check in result["checks"]}
    assert checks["native_trace_summary"]["status"] == "fail"
    assert checks["native_trace_summary"]["details"]["edit_count"] == 0
    assert checks["native_trace_summary"]["details"]["source_mutation_count"] == 0
    assert checks["native_trace_summary"]["details"]["process_source_mutation_count"] == 0


def test_hot_path_fastcheck_revalidates_stale_normalized_trace_source_mutation(tmp_path):
    artifact = _write_read_only_native_artifact(tmp_path)
    trace_dir = artifact / "normalized-trace"
    trace_dir.mkdir()
    (trace_dir / "summary.json").write_text(
        json.dumps(
            {
                "parse_error_count": 0,
                "edit_count": 0,
                "source_mutation_count": 1,
                "process_source_mutation_count": 1,
                "verifier_count": 1,
            }
        ),
        encoding="utf-8",
    )
    (artifact / "tool_result_index.json").write_text(
        json.dumps(
            {
                "by_provider_call_id": {
                    "call-read-1": {
                        "tool_name": "run_command",
                        "changed_paths": ["vm.js"],
                        "mutation_refs": ["implement-v2-evidence://attempt/process_source_observation/call-read-1"],
                        "source_mutation_effect_kinds": ["process_source_observation"],
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    result = run_hot_path_fastcheck(artifact)

    checks = {check["name"]: check for check in result["checks"]}
    assert checks["native_trace_summary"]["status"] == "fail"
    assert checks["native_trace_summary"]["details"]["source_mutation_count"] == 0
    assert checks["native_trace_summary"]["details"]["process_source_mutation_count"] == 0


def test_hot_path_fastcheck_rejects_native_response_items_drift(tmp_path):
    artifact = _write_native_artifact(tmp_path)
    items_path = artifact / "response_items.jsonl"
    lines = items_path.read_text(encoding="utf-8").splitlines()
    first = json.loads(lines[0])
    first["tool_name"] = "stale_tool"
    lines[0] = json.dumps(first, ensure_ascii=False, sort_keys=True)
    items_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    result = run_hot_path_fastcheck(artifact)

    assert result["status"] == "fail"
    check = [item for item in result["checks"] if item["name"] == "native_response_items_match"][0]
    assert check["status"] == "fail"


def test_hot_path_fastcheck_replays_native_failed_verifier_repair_control(tmp_path):
    artifact = _write_native_artifact(tmp_path, with_failed_verifier_repair=True)

    result = run_hot_path_fastcheck(artifact)

    assert result["status"] == "pass"
    check = [item for item in result["checks"] if item["name"] == "native_loop_control_replay"][0]
    assert check["status"] == "pass"
    assert check["details"]["verifier_repair_due"] is True
    assert "next_action_policy" not in check["details"]


def test_hot_path_fastcheck_rejects_positive_native_search_without_line_anchor(tmp_path):
    artifact = _write_native_artifact_with_search_output(
        tmp_path,
        output_text=(
            "search_text result: completed; "
            "summary=Searched /app/doomgeneric for 'syscall' matches=50 (truncated); "
            "output_refs=implement-v2-read://run/call-search-1/content"
        ),
    )

    result = run_hot_path_fastcheck(artifact)

    assert result["status"] == "fail"
    check = [item for item in result["checks"] if item["name"] == "native_search_text_anchor_projection"][0]
    assert check["status"] == "fail"
    assert check["details"]["missing"][0]["call_id"] == "call-search-1"


def _workframe_inputs(
    *,
    summary: str = "TypeError: missing opcode handler",
    success_contract_ref: str = "",
    sidecar_events: tuple[dict[str, object], ...] | None = None,
) -> WorkFrameInputs:
    return WorkFrameInputs(
        attempt_id="attempt-1",
        turn_id="turn-1",
        task_id="task-1",
        objective="Repair the workspace.",
        success_contract_ref=success_contract_ref,
        constraints=("model_visible_workframe_only",),
        sidecar_events=sidecar_events
        or (
            {
                "kind": "verifier",
                "event_sequence": 1,
                "event_id": "verify-1",
                "status": "failed",
                "family": "runtime_verifier_failure",
                "summary": summary,
                "evidence_refs": ["ev:verify-1"],
            },
        ),
        prompt_inventory=(
            {
                "id": "implement_v2_workframe",
                "visibility": "ordinary",
                "stability": "dynamic",
                "cache_policy": "dynamic",
                "bytes": 256,
            },
        ),
    )


def _write_workframe_bundle(root: Path, inputs: WorkFrameInputs | None = None):
    root.mkdir(parents=True, exist_ok=True)
    inputs = inputs or _workframe_inputs()
    workframe, report = reduce_workframe(inputs)
    files = {
        "reducer_inputs.json": {
            "schema_version": 1,
            "workframe_inputs": inputs.as_dict(),
            "canonical": canonicalize_workframe_inputs(inputs),
        },
        "reducer_output.workframe.json": workframe.as_dict(),
        "invariant_report.json": report.as_dict(),
        "prompt_visible_workframe.json": {
            "workframe": workframe.as_dict(),
            "rule": "This is the only ordinary dynamic state object.",
        },
        "prompt_render_inventory.json": {
            "schema_version": 1,
            "sections": list(inputs.prompt_inventory),
        },
        "workframe_cursor.json": {
            "schema_version": 1,
            "attempt_id": inputs.attempt_id,
            "turn_id": inputs.turn_id,
            "workframe_id": workframe.trace.workframe_id,
            "input_hash": workframe.trace.input_hash,
            "output_hash": workframe.trace.output_hash,
        },
    }
    for filename, payload in files.items():
        (root / filename).write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    return workframe


def _write_common_workframe_bundle(
    root: Path,
    inputs: WorkFrameInputs | None = None,
    *,
    variant: str = "transcript_tool_nav",
):
    root.mkdir(parents=True, exist_ok=True)
    inputs = inputs or _workframe_inputs()
    common = common_workframe_inputs_from_workframe_inputs(inputs)
    projection = project_workframe_with_variant(common, variant=variant)
    workframe = projection.workframe
    report = projection.invariant_report
    files = {
        "reducer_inputs.json": {
            "schema_version": 2,
            "workframe_variant": variant,
            "common_workframe_inputs_schema_version": common.schema_version,
            "workframe_inputs": inputs.as_dict(),
            "common_workframe_inputs": common.as_dict(),
            "canonical": canonicalize_common_workframe_inputs(common),
            "shared_substrate_hash": projection.shared_substrate_hash,
        },
        "reducer_output.workframe.json": workframe.as_dict(),
        "invariant_report.json": report.as_dict(),
        "prompt_visible_workframe.json": {
            "workframe": workframe.as_dict(),
            "rule": "This is the only ordinary dynamic state object.",
        },
        "prompt_render_inventory.json": {
            "schema_version": 2,
            "static_shape": [
                "static_instructions",
                "task_contract_digest",
                "natural_transcript_tail",
                "one_workframe_projection",
            ],
            "workframe_variant": variant,
            "shared_substrate_hash": projection.shared_substrate_hash,
            "projection_hash": projection.projection_hash,
            "sections": list(inputs.prompt_inventory),
        },
        "workframe_cursor.json": {
            "schema_version": 2,
            "attempt_id": inputs.attempt_id,
            "turn_id": inputs.turn_id,
            "workframe_id": workframe.trace.workframe_id,
            "workframe_variant": variant,
            "shared_substrate_hash": projection.shared_substrate_hash,
            "projection_hash": projection.projection_hash,
            "input_hash": workframe.trace.input_hash,
            "output_hash": workframe.trace.output_hash,
        },
    }
    for filename, payload in files.items():
        (root / filename).write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    return workframe


def _set_manifest_workframe_hashes(artifact: Path, workframe, *, bundle_root: str = "") -> None:
    manifest_path = artifact / "implement_v2" / "proof-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["metrics"]["workframe"]["input_hash"] = workframe.trace.input_hash
    manifest["metrics"]["workframe"]["output_hash"] = workframe.trace.output_hash
    if bundle_root:
        manifest["metrics"]["workframe"]["bundle_root"] = bundle_root
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")


def test_hot_path_fastcheck_refreshes_and_reuses_micro_fixture(tmp_path):
    artifact = _write_artifact(tmp_path)
    fixture_path = tmp_path / "micro.json"
    calls = []

    def fake_model(prompt):
        calls.append(prompt)
        return {
            "category": "patch/edit",
            "reason": "history has enough source evidence for first write",
        }

    result = run_hot_path_fastcheck(
        artifact,
        micro_next_action=fixture_path,
        expected_categories=("patch/edit",),
        micro_model_callable=fake_model,
    )

    assert result["status"] == "pass"
    assert result["micro_next_action_refresh"]["mode"] == "refreshed"
    assert fixture_path.is_file()
    assert len(calls) == 1

    def fail_if_called(prompt):
        raise AssertionError(f"unexpected live call: {prompt[:80]}")

    reused = run_hot_path_fastcheck(
        artifact,
        micro_next_action=fixture_path,
        expected_categories=("patch/edit",),
        micro_model_callable=fail_if_called,
    )

    assert reused["status"] == "pass"
    assert reused["micro_next_action_refresh"]["mode"] == "reused"


def test_hot_path_fastcheck_rejects_wrong_micro_category(tmp_path):
    artifact = _write_artifact(tmp_path)

    result = run_hot_path_fastcheck(
        artifact,
        micro_next_action=tmp_path / "micro.json",
        expected_categories=("patch/edit",),
        micro_model_callable=lambda _prompt: {"category": "cheap_probe", "reason": "more reading"},
    )

    assert result["status"] == "fail"
    micro = [check for check in result["checks"] if check["name"] == "micro_next_action"][0]
    assert micro["status"] == "fail"


def test_hot_path_fastcheck_binds_micro_fixture_to_workframe_hash(tmp_path):
    artifact = _write_artifact(tmp_path)
    fixture_path = tmp_path / "micro.json"
    calls = []

    def first_model(prompt):
        calls.append(prompt)
        return {"category": "patch/edit", "reason": "first frame"}

    first = run_hot_path_fastcheck(
        artifact,
        micro_next_action=fixture_path,
        expected_categories=("patch/edit",),
        micro_model_callable=first_model,
    )

    assert first["status"] == "pass"
    assert first["micro_next_action_refresh"]["mode"] == "refreshed"

    workframe = _write_workframe_bundle(
        artifact / "implement_v2" / "workframes" / "turn-1",
        _workframe_inputs(summary="ReferenceError: missing helper after patch"),
    )
    _set_manifest_workframe_hashes(artifact, workframe)

    def second_model(prompt):
        calls.append(prompt)
        assert "ReferenceError: missing helper after patch" in prompt
        return {"category": "patch/edit", "reason": "refreshed frame"}

    second = run_hot_path_fastcheck(
        artifact,
        micro_next_action=fixture_path,
        expected_categories=("patch/edit",),
        micro_model_callable=second_model,
    )

    assert second["status"] == "pass"
    assert second["micro_next_action_refresh"]["mode"] == "refreshed"
    assert len(calls) == 2


def test_hot_path_fastcheck_uses_manifest_workframe_bundle_root(tmp_path):
    artifact = _write_artifact(tmp_path)
    manifest_path = artifact / "implement_v2" / "proof-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["metrics"]["workframe"]["bundle_root"] = "workframes/turn-selected"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    selected = _write_workframe_bundle(artifact / "implement_v2" / "workframes" / "turn-selected")
    _set_manifest_workframe_hashes(artifact, selected, bundle_root="workframes/turn-selected")
    bad_root = artifact / "implement_v2" / "workframes" / "turn-z-stale"
    _write_workframe_bundle(bad_root)
    output_path = bad_root / "reducer_output.workframe.json"
    output = json.loads(output_path.read_text(encoding="utf-8"))
    output["trace"]["output_hash"] = "sha256:stale"
    output_path.write_text(json.dumps(output), encoding="utf-8")

    result = run_hot_path_fastcheck(
        artifact,
        micro_next_action=tmp_path / "micro.json",
        expected_categories=("patch/edit",),
        micro_model_callable=lambda _prompt: {"category": "patch/edit", "reason": "selected bundle"},
    )

    assert result["status"] == "pass"
    replay = [check for check in result["checks"] if check["name"] == "workframe_replay"][0]
    assert replay["details"]["bundle_dir"].endswith("turn-selected")


def test_hot_path_fastcheck_rejects_manifest_workframe_hash_mismatch(tmp_path):
    artifact = _write_artifact(tmp_path)
    manifest_path = artifact / "implement_v2" / "proof-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["metrics"]["workframe"]["output_hash"] = "sha256:wrong"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    result = run_hot_path_fastcheck(
        artifact,
        micro_next_action=tmp_path / "micro.json",
        micro_model_callable=lambda _prompt: {"category": "patch/edit", "reason": "unused"},
    )

    assert result["status"] == "fail"
    replay = [check for check in result["checks"] if check["name"] == "workframe_replay"][0]
    assert replay["details"]["manifest_output_hash_matches"] is False


def test_hot_path_fastcheck_replays_common_workframe_projection_hashes(tmp_path):
    artifact = _write_artifact(tmp_path)
    workframe = _write_common_workframe_bundle(artifact / "implement_v2" / "workframes" / "turn-1")
    _set_manifest_workframe_hashes(artifact, workframe)

    result = run_hot_path_fastcheck(
        artifact,
        micro_next_action=tmp_path / "micro.json",
        expected_categories=("patch/edit",),
        micro_model_callable=lambda _prompt: {"category": "patch/edit", "reason": "common replay"},
    )

    assert result["status"] == "pass"
    replay = [check for check in result["checks"] if check["name"] == "workframe_replay"][0]
    assert replay["details"]["shared_substrate_hash_matches"] is True
    assert replay["details"]["projection_hash_matches"] is True
    assert replay["details"]["recomputed_shared_substrate_hash"].startswith("sha256:")
    assert replay["details"]["recomputed_projection_hash"].startswith("sha256:")


def test_hot_path_fastcheck_detects_common_workframe_projection_hash_drift(tmp_path):
    artifact = _write_artifact(tmp_path)
    workframe = _write_common_workframe_bundle(artifact / "implement_v2" / "workframes" / "turn-1")
    _set_manifest_workframe_hashes(artifact, workframe)
    cursor_path = artifact / "implement_v2" / "workframes" / "turn-1" / "workframe_cursor.json"
    cursor = json.loads(cursor_path.read_text(encoding="utf-8"))
    cursor["projection_hash"] = "sha256:wrong"
    cursor_path.write_text(json.dumps(cursor), encoding="utf-8")

    result = run_hot_path_fastcheck(
        artifact,
        micro_next_action=tmp_path / "micro.json",
        expected_categories=("patch/edit",),
        micro_model_callable=lambda _prompt: {"category": "patch/edit", "reason": "common replay"},
    )

    assert result["status"] == "fail"
    replay = [check for check in result["checks"] if check["name"] == "workframe_replay"][0]
    assert replay["details"]["projection_hash_matches"] is False


@pytest.mark.parametrize(
    ("cursor_field", "detail_field"),
    (
        ("shared_substrate_hash", "shared_substrate_hash_matches"),
        ("projection_hash", "projection_hash_matches"),
    ),
)
def test_hot_path_fastcheck_rejects_missing_common_workframe_cursor_hash(
    tmp_path,
    cursor_field,
    detail_field,
):
    artifact = _write_artifact(tmp_path)
    workframe = _write_common_workframe_bundle(artifact / "implement_v2" / "workframes" / "turn-1")
    _set_manifest_workframe_hashes(artifact, workframe)
    cursor_path = artifact / "implement_v2" / "workframes" / "turn-1" / "workframe_cursor.json"
    cursor = json.loads(cursor_path.read_text(encoding="utf-8"))
    cursor.pop(cursor_field)
    cursor_path.write_text(json.dumps(cursor), encoding="utf-8")

    result = run_hot_path_fastcheck(
        artifact,
        micro_next_action=tmp_path / "micro.json",
        expected_categories=("patch/edit",),
        micro_model_callable=lambda _prompt: {"category": "patch/edit", "reason": "common replay"},
    )

    assert result["status"] == "fail"
    replay = [check for check in result["checks"] if check["name"] == "workframe_replay"][0]
    assert replay["details"][detail_field] is False


def test_hot_path_fastcheck_rejects_tool_navigation_reentry_drift(tmp_path):
    artifact = _write_artifact(tmp_path)
    workframe = _write_common_workframe_bundle(artifact / "implement_v2" / "workframes" / "turn-1")
    _set_manifest_workframe_hashes(artifact, workframe)
    reentry_path = artifact / "implement_v2" / "workframes" / "turn-1" / "reentry_fixture.json"
    before = workframe.as_dict()
    after = workframe.as_dict()
    before["tool_context"] = {
        "active_tool_refs": ["tool:read_file", "tool:apply_patch"],
        "recommended_tool_refs": [{"tool_ref": "tool:apply_patch"}],
        "disabled_tool_refs": [],
        "policy_refs": ["tool-policy:mutation-boundary:v1"],
        "fetchable_refs": ["tool-result-index:latest"],
        "tool_result_search": {"index_ref": "tool-result-index:latest"},
        "model_turn_search": {"index_ref": "model-turn-index:debug"},
    }
    after["tool_context"] = {
        **before["tool_context"],
        "recommended_tool_refs": [{"tool_ref": "tool:read_file"}],
    }
    reentry_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "semantic_event_changed": False,
                "before": before,
                "after": after,
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    result = run_hot_path_fastcheck(
        artifact,
        micro_next_action=tmp_path / "micro.json",
        expected_categories=("patch/edit",),
        micro_model_callable=lambda _prompt: {"category": "patch/edit", "reason": "common replay"},
    )

    assert result["status"] == "fail"
    reentry = [check for check in result["checks"] if check["name"] == "workframe_reentry_stability"][0]
    assert reentry["status"] == "fail"
    assert reentry["details"]["projection_matches"] is False
    assert reentry["details"]["before"]["tool_context"]["recommended_tool_refs"] != reentry["details"]["after"][
        "tool_context"
    ]["recommended_tool_refs"]


def test_hot_path_fastcheck_resolves_configured_verifier_ref(tmp_path):
    artifact = _write_artifact(tmp_path)
    workframe = _write_workframe_bundle(
        artifact / "implement_v2" / "workframes" / "turn-1",
        _workframe_inputs(
            success_contract_ref="task-contract:pytest",
            sidecar_events=(
                {
                    "kind": "source_mutation",
                    "event_sequence": 1,
                    "event_id": "write-1",
                    "path": "src/app.py",
                    "evidence_refs": ["sidecar:write-1"],
                },
            ),
        ),
    )
    _set_manifest_workframe_hashes(artifact, workframe)

    result = run_hot_path_fastcheck(
        artifact,
        micro_next_action=tmp_path / "micro.json",
        expected_categories=("run_verifier",),
        micro_model_callable=lambda _prompt: {"category": "run_verifier", "reason": "verify changed source"},
    )

    assert result["status"] == "pass"
    evidence = [check for check in result["checks"] if check["name"] == "workframe_evidence_ref_policy"][0]
    assert evidence["status"] == "pass"


def test_hot_path_fastcheck_resolves_paired_finish_gate_support_refs(tmp_path):
    artifact = _write_artifact(tmp_path)
    workframe = _write_workframe_bundle(
        artifact / "implement_v2" / "workframes" / "turn-1",
        _workframe_inputs(
            sidecar_events=(
                {
                    "kind": "strict_verifier",
                    "event_sequence": 1,
                    "event_id": "verify-1",
                    "status": "passed",
                    "evidence_refs": ["ev:verifier:1"],
                    "execution_contract_normalized": {
                        "id": "contract:verify",
                        "role": "verify",
                        "proof_role": "verifier",
                        "acceptance_kind": "external_verifier",
                    },
                },
                {
                    "kind": "structured_finish_gate",
                    "event_sequence": 2,
                    "event_id": "finish-gate-1",
                    "status": "passed",
                    "finish_gate": {"id": "finish:gate-1"},
                },
            ),
        ),
    )
    _set_manifest_workframe_hashes(artifact, workframe)

    result = run_hot_path_fastcheck(
        artifact,
        micro_next_action=tmp_path / "micro.json",
        expected_categories=("finish_with_evidence",),
        micro_model_callable=lambda _prompt: {"category": "finish_with_evidence", "reason": "fresh verifier"},
    )

    assert result["status"] == "pass"
    evidence = [check for check in result["checks"] if check["name"] == "workframe_evidence_ref_policy"][0]
    assert evidence["status"] == "pass"


def test_hot_path_fastcheck_resolves_nested_missing_obligation_refs(tmp_path):
    artifact = _write_artifact(tmp_path)
    workframe = _write_workframe_bundle(
        artifact / "implement_v2" / "workframes" / "turn-1",
        _workframe_inputs(
            sidecar_events=(
                {
                    "kind": "structured_finish_gate",
                    "event_sequence": 1,
                    "event_id": "finish-gate-1",
                    "status": "failed",
                    "reason": "finish is blocked until artifact freshness oracle obligation resolves",
                    "finish_gate": {"missing_obligations": [{"id": "oracle:artifact-fresh"}]},
                },
            ),
        ),
    )
    _set_manifest_workframe_hashes(artifact, workframe)

    result = run_hot_path_fastcheck(
        artifact,
        micro_next_action=tmp_path / "micro.json",
        expected_categories=("run_verifier",),
        micro_model_callable=lambda _prompt: {"category": "run_verifier", "reason": "missing obligation"},
    )

    assert result["status"] == "pass"
    evidence = [check for check in result["checks"] if check["name"] == "workframe_evidence_ref_policy"][0]
    assert evidence["status"] == "pass"


def test_hot_path_fastcheck_resolver_includes_nested_evidence_id() -> None:
    refs = _workframe_resolvable_refs(
        _workframe_inputs(
            sidecar_events=(
                {
                    "kind": "verifier",
                    "event_sequence": 1,
                    "event_id": "verify-1",
                    "status": "failed",
                    "side_effects": (
                        {
                            "kind": "artifact_evidence",
                            "record": {
                                "evidence_id": "artifact-evidence:/app/frame.bmp:tool-run-record:verify-1",
                            },
                        },
                    ),
                },
            )
        )
    )

    assert "artifact-evidence:/app/frame.bmp:tool-run-record:verify-1" in refs


def test_hot_path_fastcheck_rejects_model_supplied_unknown_category(tmp_path):
    artifact = _write_artifact(tmp_path)

    result = run_hot_path_fastcheck(
        artifact,
        micro_next_action=tmp_path / "micro.json",
        micro_model_callable=lambda _prompt: {
            "category": "invented_category",
            "expected_categories": ["invented_category"],
        },
    )

    assert result["status"] == "fail"
    assert result["metrics"]["micro_next_action"]["category"] == "invalid"


def test_hot_path_fastcheck_rejects_generic_runtime_exit_code_projection(tmp_path):
    artifact = _write_artifact(tmp_path)
    history_path = artifact / "implement_v2" / "history.json"
    history = [
        {
            "turn": 1,
            "summary": "runtime verifier failed",
            "tool_calls": [],
            "tool_results": [
                {
                    "provider_call_id": "call-runtime",
                    "tool_name": "run_command",
                    "status": "failed",
                    "content": {
                        "content": [
                            {
                                "provider_history_projection": "terminal_result_v0",
                                "command_run_id": "cmd-runtime",
                                "output_ref": "out-runtime",
                                "latest_failure": {
                                    "phase": "runtime",
                                    "kind": "nonzero_exit",
                                    "class": "runtime_failure",
                                    "summary": "exit code 1",
                                },
                            }
                        ]
                    },
                }
            ],
        }
    ]
    history_path.write_text(json.dumps(history), encoding="utf-8")

    def fail_if_called(prompt):
        raise AssertionError(f"unexpected live call: {prompt[:80]}")

    result = run_hot_path_fastcheck(
        artifact,
        micro_next_action=tmp_path / "micro.json",
        micro_model_callable=fail_if_called,
    )

    assert result["status"] == "fail"
    latest_failure = [check for check in result["checks"] if check["name"] == "latest_actionable_failure_shape"][0]
    assert latest_failure["details"]["generic_runtime_failures"][0]["summary"] == "exit code 1"
    assert result["micro_next_action_refresh"]["mode"] == "skipped"


def test_hot_path_fastcheck_rejects_generic_runtime_killed_projection(tmp_path):
    artifact = _write_artifact(tmp_path)
    history_path = artifact / "implement_v2" / "history.json"
    history = [
        {
            "turn": 1,
            "summary": "runtime verifier killed",
            "tool_calls": [],
            "tool_results": [
                {
                    "provider_call_id": "call-runtime-killed",
                    "tool_name": "run_tests",
                    "status": "interrupted",
                    "content": {
                        "content": [
                            {
                                "provider_history_projection": "terminal_result_v0",
                                "command_run_id": "cmd-runtime",
                                "output_ref": "out-runtime",
                                "latest_failure": {
                                    "phase": "runtime",
                                    "kind": "killed",
                                    "class": "runtime_failure",
                                    "summary": "tool run tool-run-record:call-runtime:2:interrupted ended with killed",
                                },
                            }
                        ]
                    },
                }
            ],
        }
    ]
    history_path.write_text(json.dumps(history), encoding="utf-8")

    def fail_if_called(prompt):
        raise AssertionError(f"unexpected live call: {prompt[:80]}")

    result = run_hot_path_fastcheck(
        artifact,
        micro_next_action=tmp_path / "micro.json",
        micro_model_callable=fail_if_called,
    )

    assert result["status"] == "fail"
    latest_failure = [check for check in result["checks"] if check["name"] == "latest_actionable_failure_shape"][0]
    assert latest_failure["details"]["generic_runtime_failures"][0]["summary"].endswith("ended with killed")
    assert result["micro_next_action_refresh"]["mode"] == "skipped"


def test_hot_path_fastcheck_allows_same_summary_failures_with_distinct_paths(tmp_path):
    artifact = _write_artifact(tmp_path)
    history_path = artifact / "implement_v2" / "history.json"
    history = [
        {
            "turn": 1,
            "summary": "runtime verifier failed before artifact contract",
            "tool_calls": [],
            "tool_results": [
                {
                    "provider_call_id": "call-runtime-before",
                    "tool_name": "run_command",
                    "status": "failed",
                    "content": {
                        "content": [
                            {
                                "provider_history_projection": "terminal_result_v0",
                                "command_run_id": "cmd-runtime-before",
                                "output_ref": "out-runtime-before",
                                "latest_failure": {
                                    "phase": "runtime",
                                    "kind": "nonzero_exit",
                                    "class": "runtime_failure",
                                    "summary": "Error: memory access 0x00000000+4 outside mapped range",
                                },
                            }
                        ]
                    },
                }
            ],
        },
        {
            "turn": 2,
            "summary": "runtime verifier failed with artifact contract",
            "tool_calls": [],
            "tool_results": [
                {
                    "provider_call_id": "call-runtime-after",
                    "tool_name": "run_command",
                    "status": "failed",
                    "content": {
                        "content": [
                            {
                                "provider_history_projection": "terminal_result_v0",
                                "command_run_id": "cmd-runtime-after",
                                "output_ref": "out-runtime-after",
                                "latest_failure": {
                                    "phase": "runtime",
                                    "kind": "nonzero_exit",
                                    "class": "runtime_failure",
                                    "summary": "Error: memory access 0x00000000+4 outside mapped range",
                                    "path": "/tmp/frame.bmp",
                                },
                            }
                        ]
                    },
                }
            ],
        },
    ]
    history_path.write_text(json.dumps(history), encoding="utf-8")

    result = run_hot_path_fastcheck(
        artifact,
        micro_next_action=tmp_path / "micro.json",
        expected_categories=("patch/edit",),
        micro_model_callable=lambda _prompt: {"category": "patch/edit", "reason": "repair latest runtime failure"},
    )

    assert result["status"] == "pass"
    latest_failure = [check for check in result["checks"] if check["name"] == "latest_actionable_failure_shape"][0]
    assert latest_failure["status"] == "pass"
    assert latest_failure["details"]["duplicate_families"] == []


def test_hot_path_fastcheck_allows_same_summary_failures_with_distinct_artifact_identities(tmp_path):
    artifact = _write_artifact(tmp_path)
    history_path = artifact / "implement_v2" / "history.json"

    def runtime_failure(provider_call_id: str, artifact_id: str, path: str) -> dict[str, object]:
        return {
            "provider_call_id": provider_call_id,
            "tool_name": "run_command",
            "status": "failed",
            "content": {
                "content": [
                    {
                        "provider_history_projection": "terminal_result_v0",
                        "command_run_id": f"cmd-{provider_call_id}",
                        "output_ref": f"out-{provider_call_id}",
                        "latest_failure": {
                            "phase": "runtime",
                            "kind": "nonzero_exit",
                            "class": "runtime_failure",
                            "summary": "Error: memory access 0x00000000+4 outside mapped range",
                        },
                        "execution_evidence_digest": {
                            "artifact_miss": [{"artifact_id": artifact_id, "path": path}]
                        },
                    }
                ]
            },
        }

    history = [
        {
            "turn": 1,
            "summary": "first artifact verifier failed",
            "tool_calls": [],
            "tool_results": [runtime_failure("call-runtime-frame", "frame", "/tmp/frame.bmp")],
        },
        {
            "turn": 2,
            "summary": "second artifact verifier failed",
            "tool_calls": [],
            "tool_results": [runtime_failure("call-runtime-log", "log", "/tmp/run.log")],
        },
        {
            "turn": 3,
            "summary": "third artifact verifier failed",
            "tool_calls": [],
            "tool_results": [runtime_failure("call-runtime-json", "json", "/tmp/result.json")],
        },
    ]
    history_path.write_text(json.dumps(history), encoding="utf-8")

    result = run_hot_path_fastcheck(
        artifact,
        micro_next_action=tmp_path / "micro.json",
        expected_categories=("patch/edit",),
        micro_model_callable=lambda _prompt: {"category": "patch/edit", "reason": "repair latest artifact failure"},
    )

    assert result["status"] == "pass"
    latest_failure = [check for check in result["checks"] if check["name"] == "latest_actionable_failure_shape"][0]
    assert latest_failure["status"] == "pass"
    assert latest_failure["details"]["duplicate_families"] == []


def test_hot_path_fastcheck_skips_live_micro_when_static_checks_fail(tmp_path):
    artifact = _write_artifact(tmp_path)
    manifest_path = artifact / "implement_v2" / "proof-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["metrics"]["resident_sidecar_state"]["total_bytes"] = 999999
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    def fail_if_called(prompt):
        raise AssertionError(f"unexpected live call: {prompt[:80]}")

    result = run_hot_path_fastcheck(
        artifact,
        micro_next_action=tmp_path / "micro.json",
        micro_model_callable=fail_if_called,
        max_sidecar_total_bytes=1024,
    )

    assert result["status"] == "fail"
    assert result["micro_next_action_refresh"]["mode"] == "skipped"


def test_hot_path_fastcheck_uses_phase0_baseline_for_sidecar_caps(tmp_path):
    artifact = _write_artifact(tmp_path)
    manifest_path = artifact / "implement_v2" / "proof-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["metrics"]["resident_sidecar_state"]["total_bytes"] = 900000
    manifest["metrics"]["resident_sidecar_state"]["per_turn_growth_bytes"] = 50000
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "metrics": {
                    "resident_sidecar_state": {
                        "total_bytes": 800000,
                        "per_turn_growth_bytes": 40000,
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    result = run_hot_path_fastcheck(
        artifact,
        baseline=baseline_path,
        micro_next_action=tmp_path / "micro.json",
        micro_model_callable=lambda _prompt: {"category": "patch/edit", "reason": "ready"},
    )

    assert result["status"] == "pass"
    sidecar = [check for check in result["checks"] if check["name"] == "resident_sidecar_metrics"][0]
    assert sidecar["details"]["cap_source"] == "phase0_baseline"
    assert sidecar["details"]["total_band"] == "yellow"


def test_hot_path_fastcheck_rejects_artifact_sidecar_cap_tampering(tmp_path):
    artifact = _write_artifact(tmp_path)
    manifest_path = artifact / "implement_v2" / "proof-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["metrics"]["resident_sidecar_state"]["total_bytes"] = 1_100_000
    manifest["metrics"]["resident_sidecar_state"]["per_turn_growth_bytes"] = 50_000
    manifest["metrics"]["resident_sidecar_state"]["cap_bands"] = {
        "yellow_total_ratio": 99.0,
        "red_per_turn_growth_ratio": 99.0,
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "metrics": {
                    "resident_sidecar_state": {
                        "total_bytes": 800000,
                        "per_turn_growth_bytes": 40000,
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    result = run_hot_path_fastcheck(
        artifact,
        baseline=baseline_path,
        micro_next_action=tmp_path / "micro.json",
        micro_model_callable=lambda _prompt: {"category": "patch/edit", "reason": "ready"},
    )

    assert result["status"] == "fail"
    sidecar = [check for check in result["checks"] if check["name"] == "resident_sidecar_metrics"][0]
    assert sidecar["details"]["max_total_bytes"] == 1_000_000
    assert sidecar["details"]["total_band"] == "red"
    assert result["micro_next_action_refresh"]["mode"] == "skipped"


def test_hot_path_fastcheck_missing_configured_baseline_is_not_silent(tmp_path):
    artifact = _write_artifact(tmp_path)

    with pytest.raises(FileNotFoundError):
        run_hot_path_fastcheck(artifact, baseline=tmp_path / "missing-baseline.json")
