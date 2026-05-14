from __future__ import annotations

import json
from pathlib import Path

from mew.implement_lane.provider_visible_salience import (
    analyze_provider_visible_salience,
    format_provider_visible_salience_markdown,
    write_provider_visible_salience_report,
)


def _input_item(payload: dict[str, object]) -> dict[str, object]:
    return {
        "role": "user",
        "content": [{"type": "input_text", "text": json.dumps(payload)}],
    }


def _write_artifact(root: Path) -> Path:
    payload = {
        "workspace": {"cwd": "/workspace"},
        "lane": "implement_v2",
        "task_contract": {
            "description": "Create vm.js and make it run.",
            "verify_command": "node vm.js",
        },
        "task_facts": {
            "missing_workspace_paths": ["vm.js"],
            "mentioned_workspace_paths": ["vm.js", "doomgeneric"],
            "existing_workspace_paths": ["doomgeneric"],
            "verify_command_paths": ["vm.js"],
        },
        "compact_sidecar_digest": {
            "digest_hash": "sha256:digest",
            "digest_kind": "native_transcript_compact_sidecar_digest",
            "digest_text": "native_sidecar_digest=sha256:digest; transcript_hash=sha256:tx",
            "lane_attempt_id": "1:1:implement_v2:native",
            "latest_evidence_refs": ["ev:tool_result:1"],
            "latest_tool_results": [
                {
                    "tool_name": "exec_command",
                    "summary": "Output: x",
                    "evidence_refs": ["implement-v2-evidence://ref"],
                    "output_refs": ["implement-v2-exec://ref"],
                }
            ],
            "provider_input_authority": "transcript_window_plus_compact_sidecar_digest",
            "provider_request_note": "Use with native transcript.",
            "runtime_id": "implement_v2_native_transcript_loop",
            "sidecar_hashes": {"tool_result_index": "sha256:tool"},
            "source_of_truth": "response_transcript.json",
            "transcript_hash": "sha256:tx",
        },
    }
    root.mkdir(parents=True)
    (root / "native-provider-requests.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "status": "ok",
                "requests": [
                    {
                        "turn_index": 1,
                        "previous_response_id_in_request_body": False,
                        "request_body": {
                            "instructions": "Implement V2 Lane Base",
                            "input": [_input_item(payload)],
                        },
                    },
                    {
                        "turn_index": 2,
                        "previous_response_id_in_request_body": True,
                        "request_body": {
                            "instructions": "Implement V2 Lane Base",
                            "input": [_input_item(payload)],
                        },
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    (root / "provider-request-inventory.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "status": "ok",
                "provider_request_inventory": [
                    {"compact_sidecar_digest_wire_visible": True},
                    {"compact_sidecar_digest_wire_visible": True},
                ],
            }
        ),
        encoding="utf-8",
    )
    return root


def test_provider_visible_salience_detects_json_envelope_and_sidecar(tmp_path: Path) -> None:
    root = _write_artifact(tmp_path / "artifact")

    report = analyze_provider_visible_salience(mew_artifact_root=root)

    assert report["request_count"] == 2
    first = report["first_request"]
    assert isinstance(first, dict)
    assert first["leading_shape"] == "json_envelope"
    assert first["top_level_section_order"] == [
        "workspace",
        "lane",
        "task_contract",
        "task_facts",
        "compact_sidecar_digest",
    ]
    aggregate = report["aggregate"]
    assert isinstance(aggregate, dict)
    assert aggregate["compact_sidecar_visible_request_count"] == 2
    assert aggregate["json_envelope_request_count"] == 2
    assert aggregate["scaffolding_occurrences_total"] > 0
    assert "H1 is measurable" in "\n".join(report["interpretation"])  # type: ignore[arg-type]
    assert "H7 is measurable" in "\n".join(report["interpretation"])  # type: ignore[arg-type]


def test_provider_visible_salience_writes_json_and_markdown(tmp_path: Path) -> None:
    root = _write_artifact(tmp_path / "artifact")
    out_json = tmp_path / "report.json"
    out_md = tmp_path / "report.md"

    report = write_provider_visible_salience_report(
        mew_artifact_root=root,
        out_json=out_json,
        out_md=out_md,
    )
    markdown = format_provider_visible_salience_markdown(report)

    assert out_json.is_file()
    assert out_md.is_file()
    assert "# M6.24 Provider-Visible Salience" in markdown
    assert "json_envelope" in out_md.read_text(encoding="utf-8")


def test_provider_visible_salience_direct_file_input_uses_sibling_inventory(tmp_path: Path) -> None:
    root = _write_artifact(tmp_path / "artifact")

    report = analyze_provider_visible_salience(mew_artifact_root=root / "native-provider-requests.json")

    aggregate = report["aggregate"]
    assert isinstance(aggregate, dict)
    assert aggregate["compact_sidecar_visible_request_count"] == 2
    inputs = report["inputs"]
    assert isinstance(inputs, dict)
    assert str(inputs["provider_request_inventory"]).endswith("provider-request-inventory.json")
