import json

from mew.implement_lane import (
    IMPLEMENT_V2_NATIVE_RUNTIME_ID,
    NativeTranscript,
    NativeTranscriptItem,
    build_native_evidence_observation,
    build_synthetic_error_output,
    native_artifact_contract,
    native_function_call_argument_metrics,
    native_proof_manifest_from_transcript,
    native_transcript_hash,
    native_transcript_sidecar_events,
    normalize_claude_tool_events,
    normalize_codex_response_items,
    reduce_workframe,
    validate_native_transcript_pairing,
    WorkFrameInputs,
    write_native_evidence_observation,
    write_native_transcript_artifacts,
)
from mew.implement_lane.native_transcript import LEGACY_IMPLEMENT_V2_MODEL_JSON_RUNTIME_ID


def _read_call_output_transcript() -> NativeTranscript:
    return NativeTranscript(
        lane_attempt_id="attempt-1",
        provider="codex",
        model="gpt-5.5",
        items=(
            NativeTranscriptItem(
                sequence=1,
                turn_id="turn-1",
                lane_attempt_id="attempt-1",
                provider="codex",
                model="gpt-5.5",
                kind="assistant_message",
                output_text_or_ref="I will inspect the file.",
            ),
            NativeTranscriptItem(
                sequence=2,
                turn_id="turn-1",
                lane_attempt_id="attempt-1",
                provider="codex",
                model="gpt-5.5",
                kind="function_call",
                call_id="call-read-1",
                tool_name="read_file",
                arguments_json_text='{"path":"src/mew/example.py"}',
            ),
            NativeTranscriptItem(
                sequence=3,
                turn_id="turn-1",
                lane_attempt_id="attempt-1",
                provider="codex",
                model="gpt-5.5",
                kind="function_call_output",
                call_id="call-read-1",
                tool_name="read_file",
                output_text_or_ref="read_file result: completed",
                status="completed",
            ),
        ),
    )


def test_native_artifact_contract_freezes_runtime_identity_and_authority() -> None:
    contract = native_artifact_contract()

    assert contract["runtime_id"] == IMPLEMENT_V2_NATIVE_RUNTIME_ID
    assert contract["forbidden_main_path_runtime_id"] == LEGACY_IMPLEMENT_V2_MODEL_JSON_RUNTIME_ID
    assert contract["source_of_truth"] == "response_transcript.json"
    assert "response_items.jsonl" in contract["authoritative_files"]
    assert contract["model_json_main_path_allowed"] is False


def test_native_transcript_pairing_accepts_non_tool_siblings_and_paired_call() -> None:
    transcript = _read_call_output_transcript()
    validation = validate_native_transcript_pairing(transcript)

    assert validation.valid is True
    assert validation.call_count == 1
    assert validation.output_count == 1
    assert validation.non_tool_count == 1


def test_native_transcript_pairing_rejects_missing_duplicate_and_orphan_outputs() -> None:
    transcript = NativeTranscript(
        lane_attempt_id="attempt-1",
        provider="codex",
        model="gpt-5.5",
        items=(
            NativeTranscriptItem(
                sequence=1,
                turn_id="turn-1",
                kind="function_call",
                lane_attempt_id="attempt-1",
                call_id="call-1",
                tool_name="read_file",
            ),
            NativeTranscriptItem(
                sequence=2,
                turn_id="turn-1",
                kind="function_call",
                lane_attempt_id="attempt-1",
                call_id="call-1",
                tool_name="read_file",
            ),
            NativeTranscriptItem(
                sequence=3,
                turn_id="turn-1",
                kind="function_call_output",
                lane_attempt_id="attempt-1",
                call_id="orphan",
                tool_name="read_file",
                status="completed",
            ),
        ),
    )

    validation = validate_native_transcript_pairing(transcript)

    assert validation.valid is False
    assert "duplicate_call_id:call-1" in validation.errors
    assert "missing_output_for_call_id:call-1" in validation.errors
    assert "orphan_output_for_call_id:orphan" in validation.errors


def test_native_transcript_pairing_rejects_non_monotonic_stored_order() -> None:
    transcript = NativeTranscript(
        lane_attempt_id="attempt-1",
        provider="codex",
        model="gpt-5.5",
        items=(
            NativeTranscriptItem(
                sequence=2,
                turn_id="turn-1",
                kind="function_call_output",
                lane_attempt_id="attempt-1",
                call_id="call-1",
                tool_name="read_file",
                status="completed",
            ),
            NativeTranscriptItem(
                sequence=1,
                turn_id="turn-1",
                kind="function_call",
                lane_attempt_id="attempt-1",
                call_id="call-1",
                tool_name="read_file",
            ),
        ),
    )

    validation = validate_native_transcript_pairing(transcript)

    assert validation.valid is False
    assert "non_monotonic_sequence:2->1" in validation.errors


def test_synthetic_errors_are_paired_outputs_not_distinct_kinds() -> None:
    call = NativeTranscriptItem(
        sequence=1,
        turn_id="turn-1",
        lane_attempt_id="attempt-1",
        provider="codex",
        kind="function_call",
        call_id="call-bad",
        tool_name="read_file",
    )
    output = build_synthetic_error_output(call, sequence=2, reason="schema invalid")
    transcript = NativeTranscript(
        lane_attempt_id="attempt-1",
        provider="codex",
        model="gpt-5.5",
        items=(call, output),
    )

    assert output.kind == "function_call_output"
    assert output.status == "synthetic_error"
    assert output.is_error is True
    assert validate_native_transcript_pairing(transcript).valid is True


def test_native_transcript_hash_is_stable_and_uses_reasoning_ref_not_raw_ref() -> None:
    base = NativeTranscriptItem(
        sequence=1,
        turn_id="turn-1",
        lane_attempt_id="attempt-1",
        provider="codex",
        kind="reasoning",
        encrypted_reasoning_ref="reasoning_sidecar.json#sha256:abc",
        raw_ref="raw/a.json",
    )
    changed_raw_ref = NativeTranscriptItem(
        sequence=1,
        turn_id="turn-1",
        lane_attempt_id="attempt-1",
        provider="codex",
        kind="reasoning",
        encrypted_reasoning_ref="reasoning_sidecar.json#sha256:abc",
        raw_ref="raw/b.json",
    )
    changed_reasoning_ref = NativeTranscriptItem(
        sequence=1,
        turn_id="turn-1",
        lane_attempt_id="attempt-1",
        provider="codex",
        kind="reasoning",
        encrypted_reasoning_ref="reasoning_sidecar.json#sha256:def",
        raw_ref="raw/a.json",
    )

    base_hash = native_transcript_hash(NativeTranscript("attempt-1", "codex", "gpt-5.5", (base,)))

    assert base_hash == native_transcript_hash(NativeTranscript("attempt-1", "codex", "gpt-5.5", (changed_raw_ref,)))
    assert base_hash != native_transcript_hash(
        NativeTranscript("attempt-1", "codex", "gpt-5.5", (changed_reasoning_ref,))
    )


def test_codex_and_claude_normalizers_produce_same_pairing_schema() -> None:
    codex = normalize_codex_response_items(
        [
            {"type": "message", "role": "assistant", "content": "checking"},
            {"type": "function_call", "id": "fc-1", "call_id": "call-1", "name": "read_file", "arguments": {"path": "a.py"}},
            {"type": "function_call_output", "call_id": "call-1", "name": "read_file", "output": "ok"},
        ],
        lane_attempt_id="attempt-1",
        model="gpt-5.5",
    )
    claude = normalize_claude_tool_events(
        [
            {"type": "text", "text": "checking"},
            {"type": "tool_use", "id": "call-1", "name": "read_file", "input": {"path": "a.py"}},
            {"type": "tool_result", "tool_use_id": "call-1", "name": "read_file", "content": "ok"},
        ],
        lane_attempt_id="attempt-1",
        model="claude",
    )

    assert [item.kind for item in codex.items] == ["assistant_message", "function_call", "function_call_output"]
    assert [item.kind for item in claude.items] == ["assistant_message", "function_call", "function_call_output"]
    assert validate_native_transcript_pairing(codex).valid is True
    assert validate_native_transcript_pairing(claude).valid is True


def test_provider_normalizers_keep_provider_item_ids_out_of_missing_call_ids() -> None:
    codex = normalize_codex_response_items(
        [{"type": "function_call", "id": "fc-item-1", "name": "read_file", "arguments": {"path": "a.py"}}],
        lane_attempt_id="attempt-1",
        model="gpt-5.5",
    )
    claude = normalize_claude_tool_events(
        [{"type": "tool_result", "id": "result-block-1", "content": "ok"}],
        lane_attempt_id="attempt-1",
        model="claude",
    )

    assert codex.items[0].provider_item_id == "fc-item-1"
    assert codex.items[0].call_id == ""
    assert "call_missing_call_id:1:function_call" in validate_native_transcript_pairing(codex).errors
    assert claude.items[0].provider_item_id == "result-block-1"
    assert claude.items[0].call_id == ""
    assert "output_missing_call_id:1:function_call_output" in validate_native_transcript_pairing(claude).errors


def test_claude_tool_result_prefers_tool_use_id_over_content_block_id() -> None:
    transcript = normalize_claude_tool_events(
        [
            {"type": "tool_use", "id": "tool-use-1", "name": "read_file", "input": {"path": "a.py"}},
            {"type": "tool_result", "id": "result-block-1", "tool_use_id": "tool-use-1", "name": "read_file", "content": "ok"},
        ],
        lane_attempt_id="attempt-1",
        model="claude",
    )

    assert transcript.items[1].provider_item_id == "result-block-1"
    assert transcript.items[1].call_id == "tool-use-1"
    assert validate_native_transcript_pairing(transcript).valid is True


def test_codex_normalizer_preserves_custom_tool_pairing() -> None:
    transcript = normalize_codex_response_items(
        [
            {"type": "custom_tool_call", "id": "ctc-1", "call_id": "custom-1", "name": "shell", "input": "make"},
            {"type": "custom_tool_call_output", "call_id": "custom-1", "name": "shell", "output": "ok"},
        ],
        lane_attempt_id="attempt-1",
        model="gpt-5.5",
    )

    assert [item.kind for item in transcript.items] == ["custom_tool_call", "custom_tool_call_output"]
    assert validate_native_transcript_pairing(transcript).valid is True


def test_native_transcript_sidecar_events_regenerate_workframe_inputs() -> None:
    transcript = NativeTranscript(
        lane_attempt_id="attempt-1",
        provider="codex",
        model="gpt-5.5",
        items=(
            NativeTranscriptItem(
                sequence=1,
                turn_id="turn-1",
                lane_attempt_id="attempt-1",
                provider="codex",
                model="gpt-5.5",
                kind="function_call",
                call_id="call-patch",
                tool_name="apply_patch",
                arguments_json_text='{"path":"src/mew/example.py"}',
            ),
            NativeTranscriptItem(
                sequence=2,
                turn_id="turn-1",
                lane_attempt_id="attempt-1",
                provider="codex",
                model="gpt-5.5",
                kind="function_call_output",
                call_id="call-patch",
                tool_name="apply_patch",
                output_text_or_ref="patched src/mew/example.py",
                status="completed",
                evidence_refs=("ev:patch-1",),
                content_refs=("sidecar:patch-1",),
            ),
        ),
    )

    sidecar_events = native_transcript_sidecar_events(transcript)
    workframe, report = reduce_workframe(
        WorkFrameInputs(
            attempt_id=transcript.lane_attempt_id,
            turn_id="turn-1",
            task_id="task-1",
            objective="Patch the implementation.",
            sidecar_events=sidecar_events,
        )
    )

    assert sidecar_events[0]["kind"] == "apply_patch"
    assert sidecar_events[0]["native_transcript_kind"] == "function_call_output"
    assert "ev:patch-1" in workframe.evidence_refs.typed
    assert "sidecar:patch-1" in workframe.evidence_refs.sidecar
    assert report.status == "pass"


def test_native_transcript_artifacts_and_derived_manifest_are_regenerable(tmp_path) -> None:
    transcript = _read_call_output_transcript()

    paths = write_native_transcript_artifacts(tmp_path, transcript)
    initial_manifest = json.loads(paths["proof_manifest"].read_text(encoding="utf-8"))
    initial_pairing = json.loads(paths["call_result_pairing"].read_text(encoding="utf-8"))

    paths["proof_manifest"].unlink()
    paths["call_result_pairing"].unlink()
    regenerated_paths = write_native_transcript_artifacts(tmp_path, transcript)
    regenerated_manifest = json.loads(regenerated_paths["proof_manifest"].read_text(encoding="utf-8"))
    regenerated_pairing = json.loads(regenerated_paths["call_result_pairing"].read_text(encoding="utf-8"))

    assert initial_manifest == regenerated_manifest
    assert initial_pairing == regenerated_pairing
    assert initial_manifest == native_proof_manifest_from_transcript(transcript)
    assert initial_manifest["pairing"]["valid"] is True
    assert paths["response_transcript"].exists()
    assert paths["response_items"].read_text(encoding="utf-8").count("\n") == len(transcript.items)


def test_native_function_call_argument_metrics_surface_large_write_payload() -> None:
    transcript = NativeTranscript(
        lane_attempt_id="attempt-1",
        provider="codex",
        model="gpt-5.5",
        items=(
            NativeTranscriptItem(
                sequence=1,
                turn_id="turn-1",
                kind="function_call",
                call_id="write-1",
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
                kind="function_call_output",
                call_id="write-1",
                tool_name="write_file",
                status="completed",
            ),
        ),
    )

    metrics = native_function_call_argument_metrics(transcript)

    assert metrics["large_write_generation_suspected"] is True
    assert metrics["large_write_argument_count"] == 1
    assert metrics["first_write_call"]["path"] == "vm.js"  # type: ignore[index]
    assert metrics["first_write_call"]["content_lines_count"] == 1200  # type: ignore[index]
    assert metrics["max_argument_call"]["tool_name"] == "write_file"  # type: ignore[index]


def test_native_evidence_observation_resolves_finish_refs_without_finish_echo(tmp_path) -> None:
    transcript = NativeTranscript(
        lane_attempt_id="attempt-1",
        provider="codex",
        model="gpt-5.5",
        items=(
            NativeTranscriptItem(
                sequence=1,
                turn_id="turn-1",
                kind="function_call",
                call_id="write-1",
                tool_name="write_file",
            ),
            NativeTranscriptItem(
                sequence=2,
                turn_id="turn-1",
                kind="function_call_output",
                call_id="write-1",
                tool_name="write_file",
                status="completed",
                evidence_refs=("implement-v2-write://attempt-1/write-1/mutation",),
            ),
            NativeTranscriptItem(
                sequence=3,
                turn_id="turn-2",
                kind="finish_call",
                call_id="finish-1",
                tool_name="finish",
                arguments_json_text=json.dumps(
                    {
                        "summary": "done",
                        "evidence_refs": (
                            "implement-v2-write://attempt-1/write-1/mutation",
                            "implement-v2-evidence://attempt-1/missing/verifier",
                        ),
                    }
                ),
            ),
            NativeTranscriptItem(
                sequence=4,
                turn_id="turn-2",
                kind="finish_output",
                call_id="finish-1",
                tool_name="finish",
                status="blocked",
                is_error=True,
                evidence_refs=(
                    "implement-v2-write://attempt-1/write-1/mutation",
                    "implement-v2-evidence://attempt-1/missing/verifier",
                ),
            ),
            NativeTranscriptItem(
                sequence=5,
                turn_id="turn-3",
                kind="function_call",
                call_id="verify-late",
                tool_name="run_tests",
            ),
            NativeTranscriptItem(
                sequence=6,
                turn_id="turn-3",
                kind="function_call_output",
                call_id="verify-late",
                tool_name="run_tests",
                status="completed",
                evidence_refs=("implement-v2-evidence://attempt-1/missing/verifier",),
            ),
        ),
    )

    observation = build_native_evidence_observation(
        transcript,
        resolver_decisions=(
            {
                "finish_call_id": "finish-1",
                "result": "block",
                "blockers": ["verifier_evidence_missing"],
                "missing_obligations": ["strict_verifier_evidence"],
            },
        ),
    )

    assert observation["summary"]["finish_claim_count"] == 1
    assert observation["summary"]["known_tool_evidence_ref_count"] == 2
    assert observation["summary"]["cited_evidence_ref_count"] == 2
    assert observation["summary"]["unresolved_cited_evidence_ref_count"] == 1
    claim = observation["finish_claims"][0]
    assert claim["known_tool_evidence_ref_count_before_finish"] == 1
    assert claim["resolved_cited_evidence_refs"] == ["implement-v2-write://attempt-1/write-1/mutation"]
    assert claim["unresolved_cited_evidence_refs"] == ["implement-v2-evidence://attempt-1/missing/verifier"]
    assert claim["finish_output_evidence_refs"] == [
        "implement-v2-write://attempt-1/write-1/mutation",
        "implement-v2-evidence://attempt-1/missing/verifier",
    ]

    manifest_path = tmp_path / "proof-manifest.json"
    manifest_path.write_text(json.dumps(native_proof_manifest_from_transcript(transcript)), encoding="utf-8")
    paths = write_native_evidence_observation(
        tmp_path,
        transcript,
        resolver_decisions=({"finish_call_id": "finish-1", "result": "block"},),
        proof_manifest_path=manifest_path,
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert paths["native_evidence_observation"].name == "native-evidence-observation.json"
    assert manifest["native_evidence_observation_ref"] == "native-evidence-observation.json"
    assert manifest["metrics"]["native_evidence_observation"]["unresolved_cited_evidence_ref_count"] == 1
