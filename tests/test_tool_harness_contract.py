from __future__ import annotations

import json
from pathlib import Path

from mew.implement_lane.provider import FakeProviderAdapter
from mew.implement_lane.affordance_visibility import scan_forbidden_provider_visible
from mew.implement_lane.tool_harness_contract import (
    build_evidence_ref_index_artifact,
    build_evidence_sidecar_artifact,
    build_model_turn_index_artifact,
    build_tool_policy_index_artifact,
    build_tool_registry_artifact,
    build_tool_route_artifact,
    build_tool_result_index_artifact,
    tool_ref_for_name,
)
from mew.implement_lane.tool_routes import route_records_from_native_transcript_items
from mew.implement_lane.tool_policy import list_v2_tool_specs_for_mode
from mew.implement_lane.types import ImplementLaneInput, ImplementLaneProofManifest, ToolResultEnvelope
from mew.implement_lane.v2_runtime import _tool_result_transcript_events, _write_live_json_artifacts
from mew.tool_kernel import ToolKernel, ToolKernelConfig, make_tool_call_envelope
from mew.work_lanes import IMPLEMENT_V2_LANE


def test_tool_result_provider_content_includes_natural_text_and_output_refs() -> None:
    result = ToolResultEnvelope(
        lane_attempt_id="attempt-1",
        provider_call_id="call-1",
        mew_tool_call_id="attempt-1:tool:1:1",
        tool_name="run_command",
        status="failed",
        is_error=True,
        content=(
            {
                "exit_code": 2,
                "stderr_tail": "line 1\nfatal error",
                "output_ref": "exec://attempt-1/cmd/output",
                "failure_class": "compile_error",
            },
        ),
        content_refs=("exec://attempt-1/cmd/output",),
        evidence_refs=("ev:compile-error",),
    )

    visible = result.provider_visible_content()

    assert visible["output_refs"] == ["exec://attempt-1/cmd/output"]
    assert "run_command result: failed" in visible["natural_result_text"]
    assert "exit_code=2" in visible["natural_result_text"]
    assert "fatal error" in visible["natural_result_text"]
    assert "ev:compile-error" in visible["natural_result_text"]
    assert scan_forbidden_provider_visible(visible["tool_output_card"], surface="tool_output_card") == []


def test_read_file_natural_text_exposes_bounded_path_line_excerpt() -> None:
    long_line = "x" * 400
    text = "\n".join([long_line, "needle = value", "tail"]) + "\n"
    result = ToolResultEnvelope(
        lane_attempt_id="attempt-1",
        provider_call_id="call-read",
        mew_tool_call_id="attempt-1:tool:1:1",
        tool_name="read_file",
        status="completed",
        content=(
            {
                "path": "src/app.py",
                "line_start": 10,
                "line_end": 12,
                "text": text,
                "truncated": False,
            },
        ),
        content_refs=("read://attempt-1/call-read/content",),
    )

    visible = result.provider_visible_content()
    card = visible["tool_output_card"]
    rendered = visible["natural_result_text"]

    assert "src/app.py:10-12" in card["paths"]
    assert "src/app.py:10:" in card["excerpt"]
    assert "src/app.py:11: needle = value" in card["excerpt"]
    assert long_line[:220] in card["excerpt"]
    assert long_line[:260] not in card["excerpt"]
    assert len(json.dumps(card, ensure_ascii=False)) <= 6144
    assert "src/app.py:11: needle = value" in rendered


def test_command_failure_visible_card_puts_latest_failure_before_output_tail() -> None:
    result = ToolResultEnvelope(
        lane_attempt_id="attempt-1",
        provider_call_id="call-run",
        mew_tool_call_id="attempt-1:tool:1:1",
        tool_name="run_command",
        status="failed",
        is_error=True,
        content=(
            {
                "exit_code": 1,
                "failure_class": "test_failure",
                "stderr_tail": "tests/test_app.py:42: AssertionError: bad value\nolder context",
                "stdout_tail": "generic log tail",
                "output_ref": "exec://attempt-1/call-run/output",
            },
        ),
        content_refs=("exec://attempt-1/call-run/output",),
    )

    rendered = result.natural_result_text()
    latest_index = rendered.index("latest_failure:")
    output_index = rendered.index("output_tail:")

    assert latest_index < output_index
    assert "tests/test_app.py:42" in rendered
    card = result.provider_visible_content()["tool_output_card"]
    assert len(card["latest_failure"]) <= 1200
    assert "mutation" not in card


def test_command_semantic_failure_visible_card_has_latest_failure_when_tool_completed() -> None:
    result = ToolResultEnvelope(
        lane_attempt_id="attempt-1",
        provider_call_id="call-run",
        mew_tool_call_id="attempt-1:tool:1:1",
        tool_name="run_command",
        status="completed",
        is_error=False,
        content=(
            {
                "status": "failed",
                "exit_code": 127,
                "stderr_tail": "/bin/bash: line 1: readelf: command not found",
                "stdout_tail": "generic stdout",
                "command_run_id": "cmd-1",
            },
        ),
    )

    visible = result.provider_visible_content()
    rendered = visible["natural_result_text"]

    assert "latest_failure:" in rendered
    assert "exit_code=127" in visible["tool_output_card"]["latest_failure"]
    assert "readelf: command not found" in visible["tool_output_card"]["latest_failure"]


def test_visible_tool_output_card_redacts_forbidden_latest_failure_fields() -> None:
    result = ToolResultEnvelope(
        lane_attempt_id="attempt-1",
        provider_call_id="call-run",
        mew_tool_call_id="attempt-1:tool:1:1",
        tool_name="run_command",
        status="failed",
        is_error=True,
        content=(
            {
                "exit_code": 2,
                "latest_failure": {
                    "summary": "artifact missing",
                    "required_next_probe": "read_file src/main.c",
                    "required_next_action": "patch src/main.c",
                },
                "stderr_tail": "required_next_probe should not leak as steering text",
            },
        ),
    )

    visible = result.provider_visible_content()
    card = visible["tool_output_card"]

    assert "artifact missing" in card["latest_failure"]
    assert "required_next" not in json.dumps(card, ensure_ascii=False)
    assert "required_next" not in visible["natural_result_text"]
    assert scan_forbidden_provider_visible(card, surface="tool_output_card") == []
    assert scan_forbidden_provider_visible(visible, surface="provider_visible_tool_result") == []


def test_provider_visible_tool_result_redacts_raw_content_side_effects_and_route_pressure() -> None:
    result = ToolResultEnvelope(
        lane_attempt_id="attempt-1",
        provider_call_id="call-run",
        mew_tool_call_id="attempt-1:tool:1:1",
        tool_name="run_command",
        status="failed",
        is_error=True,
        content=(
            {
                "latest_failure": {
                    "summary": "artifact missing",
                    "required_next_probe": "read_file src/main.c",
                },
                "acceptance_kind": "candidate_final_proof",
                "note": "proof artifact is an ordinary phrase here",
                "stderr_tail": "required_next_action should not leak",
            },
        ),
        side_effects=(
            {
                "kind": "failure_classification",
                "record": {
                    "summary": "artifact missing",
                    "required_next_probe": "inspect more",
                },
            },
        ),
        route_decision={
            "route": "execute",
            "suggested_next_action": "use apply_patch next",
        },
    )

    visible = result.provider_visible_content()
    serialized = json.dumps(visible, ensure_ascii=False, sort_keys=True)

    assert "artifact missing" in serialized
    assert "candidate_final_proof" in serialized
    assert "proof artifact is an ordinary phrase here" in serialized
    assert "required_next" not in serialized
    assert "suggested_next_action" not in serialized
    assert scan_forbidden_provider_visible(visible, surface="provider_visible_tool_result") == []


def test_visible_tool_output_card_enforces_hard_caps_for_paths_and_mutation() -> None:
    huge_path = "src/" + ("deep/" * 120) + "file.py"
    huge_stats = {f"file_{index}_{'x' * 80}.py": {"added": "y" * 500} for index in range(80)}
    result = ToolResultEnvelope(
        lane_attempt_id="attempt-1",
        provider_call_id="call-edit",
        mew_tool_call_id="attempt-1:tool:1:1",
        tool_name="apply_patch",
        status="completed",
        content=(
            {
                "mutation_output_card": {
                    "operation": "apply_patch",
                    "status": "applied",
                    "changed_paths": [huge_path for _ in range(50)],
                    "diff_ref": "mutation://" + ("d" * 2000),
                    "mutation_ref": "mutation://" + ("m" * 2000),
                    "diff_stats": huge_stats,
                },
                "text": "patched\n" * 2000,
            },
        ),
    )

    visible = result.provider_visible_content()
    card = visible["tool_output_card"]
    mutation = card["mutation"]

    assert len(json.dumps(card, ensure_ascii=False, default=str).encode("utf-8")) <= 6144
    assert len(json.dumps(mutation, ensure_ascii=False, default=str).encode("utf-8")) <= 4096
    assert all(len(path) <= 260 for path in mutation["changed_paths"])
    assert scan_forbidden_provider_visible(card, surface="tool_output_card") == []


def test_run_command_natural_text_includes_bounded_stdout_head_and_tail() -> None:
    result = ToolResultEnvelope(
        lane_attempt_id="attempt-1",
        provider_call_id="call-1",
        mew_tool_call_id="attempt-1:tool:1:1",
        tool_name="run_command",
        status="completed",
        content=(
            {
                "exit_code": 0,
                "stdout": "ELF Header: entry 0x400110\n" + ("middle\n" * 80),
                "stdout_tail": "tail disassembly line\nfinal symbol table line\n",
                "output_ref": "exec://attempt-1/cmd/output",
            },
        ),
        content_refs=("exec://attempt-1/cmd/output",),
    )

    text = result.natural_result_text()

    assert "stdout_preview:" in text
    assert "ELF Header: entry 0x400110" in text
    assert "tail disassembly line" in text
    assert "stdout_tail:" not in text


def test_run_command_natural_text_preserves_terminal_line_structure() -> None:
    result = ToolResultEnvelope(
        lane_attempt_id="attempt-1",
        provider_call_id="call-1",
        mew_tool_call_id="attempt-1:tool:1:1",
        tool_name="run_command",
        status="completed",
        content=(
            {
                "exit_code": 0,
                "stdout": "ELF Header:\n  Entry point: 0x400110\n  Machine: MIPS\n",
                "output_ref": "exec://attempt-1/cmd/output",
            },
        ),
        content_refs=("exec://attempt-1/cmd/output",),
    )

    text = result.natural_result_text()

    assert "stdout_preview:\nELF Header:\n  Entry point: 0x400110\n  Machine: MIPS" in text
    assert "stdout_preview: ELF Header: Entry point: 0x400110 Machine: MIPS" not in text
    assert "  Machine: MIPS\nrefs: exec://attempt-1/cmd/output" in text


def test_run_command_natural_text_large_output_keeps_line_oriented_tail() -> None:
    result = ToolResultEnvelope(
        lane_attempt_id="attempt-1",
        provider_call_id="call-1",
        mew_tool_call_id="attempt-1:tool:1:1",
        tool_name="run_command",
        status="completed",
        content=(
            {
                "exit_code": 0,
                "stdout": "first probe line\n" + ("middle disassembly line\n" * 400),
                "stdout_tail": "penultimate verifier clue\nfinal verifier clue\n",
                "output_ref": "exec://attempt-1/cmd/output",
            },
        ),
        content_refs=("exec://attempt-1/cmd/output",),
    )

    text = result.natural_result_text()

    assert "stdout_preview:\nfirst probe line\n...\ntail:\npenultimate verifier clue\nfinal verifier clue" in text


def test_run_command_natural_text_preserves_tail_when_tail_is_inside_full_stdout() -> None:
    result = ToolResultEnvelope(
        lane_attempt_id="attempt-1",
        provider_call_id="call-1",
        mew_tool_call_id="attempt-1:tool:1:1",
        tool_name="run_command",
        status="completed",
        content=(
            {
                "exit_code": 0,
                "stdout": "first symbol\n" + ("middle\n" * 200) + "important final verifier line\n",
                "stdout_tail": "important final verifier line\n",
                "output_ref": "exec://attempt-1/cmd/output",
            },
        ),
        content_refs=("exec://attempt-1/cmd/output",),
    )

    text = result.natural_result_text()

    assert "stdout_preview:" in text
    assert "first symbol" in text
    assert "important final verifier line" in text


def test_run_command_natural_text_includes_stderr_and_stdout_previews() -> None:
    result = ToolResultEnvelope(
        lane_attempt_id="attempt-1",
        provider_call_id="call-1",
        mew_tool_call_id="attempt-1:tool:1:1",
        tool_name="run_command",
        status="completed",
        content=(
            {
                "exit_code": 0,
                "stderr": "warning: fallback path used\n",
                "stdout": "runtime result marker\n",
                "output_ref": "exec://attempt-1/cmd/output",
            },
        ),
        content_refs=("exec://attempt-1/cmd/output",),
    )

    text = result.natural_result_text()

    assert "stderr_preview:" in text
    assert "warning: fallback path used" in text
    assert "stdout_preview:" in text
    assert "runtime result marker" in text


def test_command_family_natural_text_honors_medium_requested_output_budget() -> None:
    marker_after_tiny_cap = "VISIBLE_AFTER_2400_CHARS"
    noisy_stdout = (
        "first useful line\n"
        + ("a" * 2600)
        + f"\n{marker_after_tiny_cap}\n"
        + ("large bounded probe output\n" * 120)
        + "final useful line\n"
    )
    for tool_name in ("run_command", "run_tests", "poll_command", "cancel_command"):
        result = ToolResultEnvelope(
            lane_attempt_id="attempt-1",
            provider_call_id=f"call-{tool_name}",
            mew_tool_call_id=f"attempt-1:tool:{tool_name}:1",
            tool_name=tool_name,
            status="completed",
            content=(
                {
                    "exit_code": 0,
                    "stdout": noisy_stdout,
                    "stdout_tail": "final useful line\n",
                    "provider_visible_output_chars": 50_000,
                    "output_ref": f"exec://attempt-1/{tool_name}/output",
                },
            ),
            content_refs=(f"exec://attempt-1/{tool_name}/output",),
        )

        text = result.natural_result_text()

        assert len(text) <= 12_000
        assert "first useful line" in text
        assert marker_after_tiny_cap in text
        assert "final useful line" in text
        assert f"exec://attempt-1/{tool_name}/output" in text


def test_tool_registry_and_result_index_artifacts_are_stable() -> None:
    registry = build_tool_registry_artifact(
        provider="model_json",
        tool_specs=tuple(spec for spec in list_v2_tool_specs_for_mode("read_only") if spec.name in {"read_file", "finish"}),
    )
    policy = build_tool_policy_index_artifact(registry)
    result = ToolResultEnvelope(
        lane_attempt_id="attempt-1",
        provider_call_id="call-1",
        mew_tool_call_id="attempt-1:tool:1:1",
        tool_name="read_file",
        status="completed",
        content=({"path": "README.md", "text": "hello"},),
        content_refs=("file://README.md",),
    )
    index = build_tool_result_index_artifact(
        (result,),
        tool_registry_ref=str(registry["tool_registry_ref"]),
        provider_tool_spec_hash=str(registry["provider_tool_spec_hash"]),
    )
    routes = build_tool_route_artifact((result,))

    assert registry["tool_registry_hash"] == registry["provider_tool_spec_hash"]
    assert {"read_file", "finish", "model_response_error"}.issubset(set(registry["by_tool_name"]))
    assert policy["by_tool"]["read_file"]["tool_ref"] == tool_ref_for_name("read_file")
    assert policy["by_tool_ref"][tool_ref_for_name("read_file")]["tool_name"] == "read_file"
    assert policy["by_tool_ref"][tool_ref_for_name("model_response_error")]["access"] == "internal"
    assert index["by_provider_call_id"]["call-1"]["ref"] == "tool-result:call-1"
    assert index["by_provider_call_id"]["call-1"]["tool_ref"] == tool_ref_for_name("read_file")
    assert index["by_provider_call_id"]["call-1"]["output_refs"] == ["file://README.md"]
    assert routes["counts"]["read"] == 1
    assert routes["records"][0]["tool_route"] == "read"
    assert routes["records"][0]["ref"] == "tool-route:call-1"
    assert index["index_hash"].startswith("sha256:")


def test_tool_route_records_classify_process_lifecycle_without_shell_semantics() -> None:
    records = route_records_from_native_transcript_items(
        (
            {"kind": "function_call", "call_id": "poll-1", "tool_name": "poll_command"},
            {"kind": "function_call_output", "call_id": "poll-1", "status": "completed"},
        )
    )

    assert records[0]["tool_route"] == "process_lifecycle"
    assert records[0]["command_classification"]["result"] == "unavailable"
    assert records[0]["command_classification"]["not_source_mutation_classifier"] is True


def test_evidence_sidecar_and_ref_index_cover_hot_path_lookup() -> None:
    result = ToolResultEnvelope(
        lane_attempt_id="attempt-1",
        provider_call_id="call-run",
        mew_tool_call_id="attempt-1:tool:1:1",
        tool_name="run_command",
        status="completed",
        content=(
            {
                "command_run_id": "cmd-1",
                "tool_run_record": {
                    "record_id": "record-1",
                    "command_run_id": "cmd-1",
                    "provider_call_id": "call-run",
                    "tool_name": "run_command",
                    "contract_id": "contract-1",
                    "status": "completed",
                    "exit_code": 0,
                    "semantic_exit": {"category": "ok"},
                },
                "execution_contract_normalized": {
                    "id": "contract-1",
                    "acceptance_kind": "candidate_final_proof",
                    "expected_artifacts": [
                        {
                            "id": "frame",
                            "path": "/tmp/frame.bmp",
                            "kind": "image",
                            "freshness": "modified_after_run_start",
                        }
                    ],
                },
                "artifact_evidence": [
                    {
                        "evidence_id": "artifact-1",
                        "artifact_id": "frame",
                        "command_run_id": "cmd-1",
                        "tool_run_record_id": "record-1",
                        "contract_id": "contract-1",
                        "path": "/tmp/frame.bmp",
                        "kind": "image",
                        "freshness": "modified_after_run_start",
                        "post_run_stat": {"exists": True},
                        "status": "passed",
                    }
                ],
                "verifier_evidence": {
                    "verifier_id": "verifier-1",
                    "contract_id": "contract-1",
                    "verdict": "pass",
                },
            },
        ),
        evidence_refs=("ev:verifier:verifier-1",),
    )

    sidecar = build_evidence_sidecar_artifact((result,), task_contract={"description": "make a frame"})
    index = build_evidence_ref_index_artifact(sidecar)

    assert sidecar["event_count"] >= 3
    assert "tool-result:call-run" in sidecar["by_tool_result_ref"]
    assert "ev:verifier:verifier-1" in index["by_evidence_ref"]
    assert "cmd-1" in index["by_command_run_id"]
    assert "/tmp/frame.bmp" in index["by_path"]
    assert index["by_tool_ref"][tool_ref_for_name("run_command")]
    assert index["hot_path_model_turn_search_allowed"] is False
    assert index["unresolved_evidence_refs"] == []
    assert sidecar["artifact_obligations"]["obligations"]


def test_evidence_sidecar_indexes_plain_read_and_write_mutation_refs() -> None:
    read_result = ToolResultEnvelope(
        lane_attempt_id="attempt-1",
        provider_call_id="call-read",
        mew_tool_call_id="attempt-1:tool:1:1",
        tool_name="read_file",
        status="completed",
        content=({"path": "README.md", "text": "hello"},),
        content_refs=("file://README.md",),
    )
    write_result = ToolResultEnvelope(
        lane_attempt_id="attempt-1",
        provider_call_id="call-write",
        mew_tool_call_id="attempt-1:tool:2:1",
        tool_name="write_file",
        status="completed",
        content=({"path": "README.md", "written": True, "dry_run": False},),
        evidence_refs=("implement-v2-write://attempt-1/call-write/mutation",),
        side_effects=(
            {
                "kind": "file_write",
                "operation": "write_file",
                "path": "README.md",
                "written": True,
                "dry_run": False,
            },
        ),
    )

    sidecar = build_evidence_sidecar_artifact((read_result, write_result))
    index = build_evidence_ref_index_artifact(sidecar)

    assert "tool-result:call-read" in sidecar["by_tool_result_ref"]
    assert "tool-result:call-write" in sidecar["by_tool_result_ref"]
    assert "file://README.md" in index["by_output_ref"]
    assert "implement-v2-write://attempt-1/call-write/mutation" in index["by_mutation_ref"]
    assert "README.md" in index["by_path"]
    assert index["by_kind"]["source_mutation"]
    assert index["unresolved_evidence_refs"] == []


def test_tool_result_index_carries_concise_mutation_card_refs() -> None:
    mutation_ref = "implement-v2-write://attempt-1/call-patch/mutation"
    diff_ref = "implement-v2-write://attempt-1/call-patch/source-diff"
    pre_ref = "implement-v2-write://attempt-1/call-patch/source-snapshot/pre"
    post_ref = "implement-v2-write://attempt-1/call-patch/source-snapshot/post"
    result = ToolResultEnvelope(
        lane_attempt_id="attempt-1",
        provider_call_id="call-patch",
        mew_tool_call_id="attempt-1:tool:1:1",
        tool_name="apply_patch",
        status="completed",
        content=(
            {
                "path": "/workspace/src/app.py",
                "changed": True,
                "written": True,
                "dry_run": False,
                "source_diff_ref": diff_ref,
                "source_snapshot_refs": {"pre": pre_ref, "post": post_ref},
                "typed_source_mutation": {
                    "mutation_ref": mutation_ref,
                    "diff_ref": diff_ref,
                    "path": "/workspace/src/app.py",
                    "changed_paths": ["src/app.py"],
                },
                "mutation_output_card": {
                    "kind": "mutation_output_card",
                    "operation": "apply_patch",
                    "status": "applied",
                    "path": "/workspace/src/app.py",
                    "changed_paths": ["src/app.py"],
                    "changed": True,
                    "written": True,
                    "dry_run": False,
                    "diff_ref": diff_ref,
                    "mutation_ref": mutation_ref,
                    "snapshot_refs": {"pre": pre_ref, "post": post_ref},
                    "artifact_refs": [diff_ref, pre_ref, post_ref, mutation_ref],
                },
            },
        ),
        content_refs=(diff_ref, pre_ref, post_ref),
        evidence_refs=(mutation_ref,),
        side_effects=(
            {
                "kind": "file_write",
                "operation": "apply_patch",
                "path": "/workspace/src/app.py",
                "mutation_ref": mutation_ref,
                "diff_ref": diff_ref,
                "written": True,
                "dry_run": False,
            },
        ),
    )

    index = build_tool_result_index_artifact((result,))
    card = index["by_provider_call_id"]["call-patch"]["compact_result_card"]

    assert index["by_provider_call_id"]["call-patch"]["changed_paths"] == ["src/app.py"]
    assert index["by_provider_call_id"]["call-patch"]["mutation_refs"] == [mutation_ref]
    assert mutation_ref in index["by_provider_call_id"]["call-patch"]["artifact_refs"]
    assert card["mutation_output_card"]["changed_paths"] == ["src/app.py"]
    assert card["mutation_output_card"]["mutation_ref"] == mutation_ref
    assert "source-diff" in card["artifact_refs"][0]


def test_tool_result_index_carries_process_source_observation_refs() -> None:
    result = ToolResultEnvelope(
        lane_attempt_id="attempt-1",
        provider_call_id="call-run",
        mew_tool_call_id="attempt-1:tool:1:1",
        tool_name="run_command",
        status="completed",
        side_effects=(
            {
                "kind": "process_source_observation",
                "record": {
                    "command_run_id": "cmd-1",
                    "provider_call_id": "call-run",
                    "changed_count": 1,
                    "changes": [{"path": "vm.js", "change": "created"}],
                },
            },
        ),
    )

    index = build_tool_result_index_artifact((result,))
    card = index["by_provider_call_id"]["call-run"]["compact_result_card"]

    assert index["by_provider_call_id"]["call-run"]["changed_paths"] == ["vm.js"]
    assert index["by_provider_call_id"]["call-run"]["source_mutation_effect_kinds"] == [
        "process_source_observation"
    ]
    assert card["source_mutation_effect_kinds"] == ["process_source_observation"]
    assert "process_source_observation" in index["by_provider_call_id"]["call-run"]["mutation_refs"][0]


def test_evidence_sidecar_does_not_treat_non_file_side_effects_as_mutations() -> None:
    result = ToolResultEnvelope(
        lane_attempt_id="attempt-1",
        provider_call_id="call-run",
        mew_tool_call_id="attempt-1:tool:1:1",
        tool_name="run_command",
        status="completed",
        content=({"command_run_id": "cmd-1"},),
        side_effects=({"kind": "command_run", "command_run_id": "cmd-1"},),
    )

    sidecar = build_evidence_sidecar_artifact((result,))
    index = build_evidence_ref_index_artifact(sidecar)

    assert "source_mutation" not in index["by_kind"]
    assert index["by_mutation_ref"] == {}


def _assert_process_source_observation(result, *, changed_name: str, change: str) -> None:
    assert result.status == "completed"
    assert result.route_decision["tool_route"] == "process_runner"
    payload = result.content[0]
    assert payload["tool_route"] == "process_runner"
    assert payload["observed_source_side_effect"] is True
    observations = payload["process_source_observations"]
    assert observations
    assert any(
        Path(item["path"]).name == changed_name and item["change"] == change
        for observation in observations
        for item in observation["changes"]
    )
    assert any(effect["kind"] == "process_source_observation" for effect in result.side_effects)


def test_tool_kernel_observes_run_command_source_creation_as_process_side_effect(tmp_path: Path) -> None:
    kernel = ToolKernel(
        ToolKernelConfig(
            workspace=str(tmp_path),
            mode="full",
            allowed_read_roots=(str(tmp_path),),
            allowed_write_roots=(str(tmp_path),),
            allow_shell=True,
            run_command_available=True,
        )
    )
    call = make_tool_call_envelope(
        "run_command",
        {
            "command": "printf 'ok\\n' > generated.py",
            "cwd": ".",
            "use_shell": True,
            "timeout": 3,
            "foreground_budget_seconds": 1,
        },
        provider_call_id="call-shell-writer",
    )

    result = kernel.execute(call)

    _assert_process_source_observation(result, changed_name="generated.py", change="created")
    assert (tmp_path / "generated.py").read_text(encoding="utf-8") == "ok\n"


def test_tool_kernel_observes_run_command_source_move_to_runtime_artifact_as_process_side_effect(
    tmp_path: Path,
) -> None:
    source = tmp_path / "vm.js"
    source.write_text("console.log('ok')\n", encoding="utf-8")
    kernel = ToolKernel(
        ToolKernelConfig(
            workspace=str(tmp_path),
            mode="full",
            allowed_read_roots=(str(tmp_path),),
            allowed_write_roots=(str(tmp_path),),
            allow_shell=True,
            run_command_available=True,
        )
    )
    call = make_tool_call_envelope(
        "run_command",
        {
            "command": "mv vm.js /tmp/vm.js",
            "cwd": ".",
            "use_shell": True,
            "timeout": 3,
            "foreground_budget_seconds": 1,
        },
        provider_call_id="call-mv-source",
    )

    result = kernel.execute(call)

    _assert_process_source_observation(result, changed_name="vm.js", change="deleted")
    assert not source.exists()


def test_tool_kernel_observes_run_command_source_creation_through_shell_argv_as_process_side_effect(
    tmp_path: Path,
) -> None:
    kernel = ToolKernel(
        ToolKernelConfig(
            workspace=str(tmp_path),
            mode="full",
            allowed_read_roots=(str(tmp_path),),
            allowed_write_roots=(str(tmp_path),),
            allow_shell=True,
            run_command_available=True,
        )
    )
    call = make_tool_call_envelope(
        "run_command",
        {
            "argv": ["bash", "-lc", "printf 'ok\\n' > generated.py"],
            "cwd": ".",
            "timeout": 3,
            "foreground_budget_seconds": 1,
        },
        provider_call_id="call-shell-argv-writer",
    )

    result = kernel.execute(call)

    _assert_process_source_observation(result, changed_name="generated.py", change="created")
    assert (tmp_path / "generated.py").read_text(encoding="utf-8") == "ok\n"


def test_tool_kernel_observes_run_command_source_creation_through_shell_argv_options_as_process_side_effect(
    tmp_path: Path,
) -> None:
    kernel = ToolKernel(
        ToolKernelConfig(
            workspace=str(tmp_path),
            mode="full",
            allowed_read_roots=(str(tmp_path),),
            allowed_write_roots=(str(tmp_path),),
            allow_shell=True,
            run_command_available=True,
        )
    )
    call = make_tool_call_envelope(
        "run_command",
        {
            "argv": ["bash", "-e", "-c", "printf 'ok\\n' > generated.py"],
            "cwd": ".",
            "timeout": 3,
            "foreground_budget_seconds": 1,
        },
        provider_call_id="call-shell-argv-option-writer",
    )

    result = kernel.execute(call)

    _assert_process_source_observation(result, changed_name="generated.py", change="created")
    assert (tmp_path / "generated.py").read_text(encoding="utf-8") == "ok\n"


def test_tool_kernel_observes_run_command_source_creation_through_shell_argv_pipefail_as_process_side_effect(
    tmp_path: Path,
) -> None:
    kernel = ToolKernel(
        ToolKernelConfig(
            workspace=str(tmp_path),
            mode="full",
            allowed_read_roots=(str(tmp_path),),
            allowed_write_roots=(str(tmp_path),),
            allow_shell=True,
            run_command_available=True,
        )
    )
    call = make_tool_call_envelope(
        "run_command",
        {
            "argv": ["bash", "-euo", "pipefail", "-c", "printf 'ok\\n' > generated.py"],
            "cwd": ".",
            "timeout": 3,
            "foreground_budget_seconds": 1,
        },
        provider_call_id="call-shell-argv-pipefail-writer",
    )

    result = kernel.execute(call)

    _assert_process_source_observation(result, changed_name="generated.py", change="created")
    assert (tmp_path / "generated.py").read_text(encoding="utf-8") == "ok\n"


def test_evidence_sidecar_indexes_exec_source_tree_mutations() -> None:
    result = ToolResultEnvelope(
        lane_attempt_id="attempt-1",
        provider_call_id="call-run",
        mew_tool_call_id="attempt-1:tool:1:1",
        tool_name="run_command",
        status="completed",
        content=({"command_run_id": "cmd-1"},),
        side_effects=(
            {
                "kind": "source_tree_mutation",
                "record": {
                    "command_run_id": "cmd-1",
                    "provider_call_id": "call-run",
                    "changed_count": 2,
                    "changes": [
                        {"path": "src/main.c", "change": "modified"},
                        {"path": "src/vm.c", "change": "created"},
                    ],
                },
            },
        ),
    )

    sidecar = build_evidence_sidecar_artifact((result,))
    index = build_evidence_ref_index_artifact(sidecar)

    assert index["by_kind"]["source_mutation"]
    assert "src/main.c" in index["by_path"]
    assert "src/vm.c" in index["by_path"]
    assert "implement-v2-evidence://attempt-1/source_tree_mutation/cmd-1" in index["by_mutation_ref"]


def test_evidence_ref_index_reports_missing_internal_evidence_refs() -> None:
    sidecar = {
        "sidecar_ref": "evidence-sidecar:test",
        "sidecar_hash": "sha256:test",
        "by_tool_result_ref": {"tool-result:known": []},
        "known_result_evidence_refs": ["ev:known-generic"],
        "events": [
            {
                "id": "ev:root",
                "kind": "tool_result",
                "status": "failed",
                "observed": {},
                "refs": [
                    {"kind": "evidence_event", "id": "ev:missing"},
                    {"kind": "tool_result_ref", "id": "tool-result:missing"},
                    {"kind": "evidence_ref", "id": "ev:missing-generic"},
                ],
            }
        ],
    }

    index = build_evidence_ref_index_artifact(sidecar)

    assert index["unresolved_evidence_refs"] == [
        {"event_id": "ev:root", "missing_ref": "ev:missing"},
        {"event_id": "ev:root", "missing_ref": "tool-result:missing"},
        {"event_id": "ev:root", "missing_ref": "ev:missing-generic"},
    ]


def test_model_turn_index_is_debug_recovery_only() -> None:
    adapter = FakeProviderAdapter()
    call = adapter.normalize_tool_calls(
        lane_attempt_id="attempt-1",
        turn_index=1,
        calls=({"provider_call_id": "call-1", "tool_name": "read_file", "arguments": {"path": "README.md"}},),
    )[0]
    transcript = adapter.transcript_events_for_turn(
        lane=IMPLEMENT_V2_LANE,
        lane_attempt_id="attempt-1",
        turn_id="turn-1",
        text="reading",
        tool_calls=(call,),
    )
    index = build_model_turn_index_artifact(
        history=(
            {
                "turn": 1,
                "summary": "reading",
                "tool_calls": [call.as_dict()],
                "tool_results": [
                    {
                        "provider_call_id": "call-1",
                        "tool_name": "read_file",
                        "status": "completed",
                    }
                ],
            },
        ),
        transcript=transcript,
    )

    assert index["index_kind"] == "debug_recovery_only"
    assert index["hot_path_model_turn_search_allowed"] is False
    assert index["by_provider_call_id"]["call-1"] == 1


def test_live_artifact_writer_emits_phase1_tool_harness_files(tmp_path: Path) -> None:
    adapter = FakeProviderAdapter()
    call = adapter.normalize_tool_calls(
        lane_attempt_id="attempt-1",
        turn_index=1,
        calls=({"provider_call_id": "call-1", "tool_name": "read_file", "arguments": {"path": "README.md"}},),
    )[0]
    result = ToolResultEnvelope(
        lane_attempt_id="attempt-1",
        provider_call_id="call-1",
        mew_tool_call_id=call.mew_tool_call_id,
        tool_name="read_file",
        status="completed",
        content=({"path": "README.md", "text": "hello"},),
        content_refs=("file://README.md",),
    )
    transcript = adapter.transcript_events_for_turn(
        lane=IMPLEMENT_V2_LANE,
        lane_attempt_id="attempt-1",
        turn_id="turn-1",
        text="reading",
        tool_calls=(call,),
    )
    manifest = ImplementLaneProofManifest(
        lane=IMPLEMENT_V2_LANE,
        lane_attempt_id="attempt-1",
        artifact_namespace="implement-lane/implement_v2/ws/task",
        tool_calls=(call,),
        tool_results=(result,),
        metrics={"transport": "model_json", "provider_tool_names": ["read_file", "finish"]},
    )
    lane_input = ImplementLaneInput(
        work_session_id="ws",
        task_id="task",
        workspace=str(tmp_path),
        lane=IMPLEMENT_V2_LANE,
        lane_config={"artifact_dir": str(tmp_path / "artifacts")},
    )

    paths = _write_live_json_artifacts(
        lane_input,
        manifest=manifest,
        transcript=(
            *transcript,
            *_tool_result_transcript_events(
                lane_attempt_id="attempt-1",
                turn_id="turn-1",
                tool_results=(result,),
            ),
        ),
        history=(),
    )
    artifact_root = tmp_path / "artifacts" / "implement_v2"

    assert str(artifact_root / "tool_registry.json") in paths
    assert str(artifact_root / "tool_policy_index.json") in paths
    assert str(artifact_root / "natural_transcript.jsonl") in paths
    assert str(artifact_root / "tool_results.jsonl") in paths
    assert str(artifact_root / "tool_result_index.json") in paths
    assert str(artifact_root / "tool_routes.json") in paths
    assert str(artifact_root / "tool_routes.jsonl") in paths
    assert str(artifact_root / "evidence_sidecar.json") in paths
    assert str(artifact_root / "evidence_ref_index.json") in paths
    assert str(artifact_root / "model_turn_index.json") in paths

    registry = json.loads((artifact_root / "tool_registry.json").read_text(encoding="utf-8"))
    result_index = json.loads((artifact_root / "tool_result_index.json").read_text(encoding="utf-8"))
    route_artifact = json.loads((artifact_root / "tool_routes.json").read_text(encoding="utf-8"))
    evidence_index = json.loads((artifact_root / "evidence_ref_index.json").read_text(encoding="utf-8"))
    model_turn_index = json.loads((artifact_root / "model_turn_index.json").read_text(encoding="utf-8"))
    transcript_lines = (artifact_root / "natural_transcript.jsonl").read_text(encoding="utf-8").splitlines()
    result_lines = (artifact_root / "tool_results.jsonl").read_text(encoding="utf-8").splitlines()
    route_lines = (artifact_root / "tool_routes.jsonl").read_text(encoding="utf-8").splitlines()

    assert registry["provider"] == "model_json"
    assert {"read_file", "finish", "model_response_error"}.issubset(set(registry["by_tool_name"]))
    assert result_index["by_provider_call_id"]["call-1"]["tool_name"] == "read_file"
    assert result_index["by_provider_call_id"]["call-1"]["tool_ref"] == tool_ref_for_name("read_file")
    assert route_artifact["counts"]["read"] == 1
    assert json.loads(route_lines[0])["tool_route"] == "read"
    result_event_payloads = [
        json.loads(line)["payload"] for line in transcript_lines if json.loads(line)["kind"] == "tool_result"
    ]
    assert result_event_payloads[0]["natural_result_text"].startswith("read_file result: completed")
    assert len(result_lines) == 1
    assert json.loads(result_lines[0])["natural_result_text"].startswith("read_file result: completed")
    assert evidence_index["hot_path_model_turn_search_allowed"] is False
    assert model_turn_index["index_kind"] == "debug_recovery_only"
