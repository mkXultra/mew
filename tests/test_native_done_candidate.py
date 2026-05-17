import json
from pathlib import Path

from mew.implement_lane.internal_finish_gate_contract import validate_done_candidate_record
from mew.implement_lane.native_done_candidate import (
    DONE_CANDIDATES_FILE,
    build_native_done_candidate,
    write_native_done_candidate_artifacts,
)
from mew.implement_lane.native_transcript import NativeTranscript, NativeTranscriptItem


def _assistant_item(text: str = "Done.") -> NativeTranscriptItem:
    return NativeTranscriptItem(
        sequence=1,
        turn_id="turn-7",
        lane_attempt_id="attempt-1",
        provider="openai",
        model="gpt-5.5",
        provider_item_id="msg-1",
        output_index=0,
        kind="assistant_message",
        output_text_or_ref=text,
    )


def test_build_native_done_candidate_matches_contract_schema() -> None:
    assistant = _assistant_item()
    transcript = NativeTranscript(
        lane_attempt_id="attempt-1",
        provider="openai",
        model="gpt-5.5",
        items=(assistant,),
    )

    candidate = build_native_done_candidate(
        transcript,
        (assistant,),
        compact_sidecar_digest_hash="sha256:sidecar",
    )

    assert candidate is not None
    record = candidate.as_dict()
    assert record["done_candidate_id"].startswith("done-candidate:turn-7:")
    assert record["final_response_text_ref"] == (
        "native-transcript://attempt-1/turn-7/assistant-final-response"
    )
    assert record["compact_sidecar_digest_hash"] == "sha256:sidecar"
    assert validate_done_candidate_record(record).ok


def test_write_native_done_candidate_artifacts_patches_manifest(tmp_path: Path) -> None:
    assistant = _assistant_item("Completed after verifier passed.")
    transcript = NativeTranscript(
        lane_attempt_id="attempt-1",
        provider="openai",
        model="gpt-5.5",
        items=(assistant,),
    )
    candidate = build_native_done_candidate(
        transcript,
        (assistant,),
        compact_sidecar_digest_hash="sha256:sidecar",
        reason="no_tool_repeat",
    )
    assert candidate is not None
    manifest_path = tmp_path / "proof-manifest.json"
    manifest_path.write_text('{"metrics":{"existing":1}}\n', encoding="utf-8")

    paths = write_native_done_candidate_artifacts(
        tmp_path,
        (candidate,),
        proof_manifest_path=manifest_path,
    )

    assert paths["done_candidates"] == tmp_path / DONE_CANDIDATES_FILE
    rows = [
        json.loads(line)
        for line in (tmp_path / DONE_CANDIDATES_FILE).read_text(encoding="utf-8").splitlines()
    ]
    assert rows[0]["reason"] == "no_tool_repeat"
    assert validate_done_candidate_record(rows[0]).ok
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["done_candidates_ref"] == DONE_CANDIDATES_FILE
    assert str(manifest["done_candidates_sha256"]).startswith("sha256:")
    assert manifest["metrics"]["existing"] == 1
    assert manifest["metrics"]["done_candidate_count"] == 1
    assert manifest["metrics"]["done_candidates"] == 1
