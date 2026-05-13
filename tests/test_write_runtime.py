import json
from pathlib import Path

from mew.implement_lane.types import ToolCallEnvelope
from mew.implement_lane.write_runtime import ImplementV2WriteRuntime


def _tool_call(tool_name: str, arguments: dict[str, object]) -> ToolCallEnvelope:
    return ToolCallEnvelope(
        lane_attempt_id="attempt-1",
        provider="test",
        provider_call_id="call-1",
        mew_tool_call_id="mew-call-1",
        tool_name=tool_name,
        arguments=arguments,
        status="validated",
    )


def test_apply_patch_output_card_is_typed_concise_and_ref_backed(tmp_path: Path) -> None:
    target = tmp_path / "worker.py"
    target.write_text("value = 'old'\n", encoding="utf-8")
    runtime = ImplementV2WriteRuntime(
        workspace=tmp_path,
        allowed_write_roots=(str(tmp_path),),
        approved_write_calls=(
            {"provider_call_id": "call-1", "status": "approved", "approval_id": "approval-1"},
        ),
        artifact_dir=tmp_path / "artifacts",
    )
    patch_lines = [
        "*** Begin Patch",
        "*** Update File: worker.py",
        "@@",
        "-value = 'old'",
        "+value = 'new'",
        "*** End Patch",
    ]

    result = runtime.execute(_tool_call("apply_patch", {"patch_lines": patch_lines, "apply": True}))

    assert result.status == "completed"
    assert target.read_text(encoding="utf-8") == "value = 'new'\n"
    payload = result.content[0]
    assert isinstance(payload, dict)
    card = payload["mutation_output_card"]
    assert card["kind"] == "mutation_output_card"
    assert card["operation"] == "apply_patch"
    assert card["status"] == "applied"
    assert card["path"].endswith("worker.py")
    assert "diff" not in card
    assert card["diff_ref"] in result.content_refs
    assert card["snapshot_refs"]["pre"] in result.content_refs
    assert card["snapshot_refs"]["post"] in result.content_refs
    assert result.evidence_refs == (card["mutation_ref"],)
    assert card["mutation_ref"] in card["artifact_refs"]
    assert "value = 'new'" not in json.dumps(card, sort_keys=True)
    assert len(json.dumps(card, sort_keys=True)) < 5000
    assert payload["summary"].startswith("apply_patch applied")
