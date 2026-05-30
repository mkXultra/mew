from __future__ import annotations

import json
from pathlib import Path

import pytest

from mew.implement_lane.provider_continuity_audit import (
    analyze_provider_continuity,
    format_provider_continuity_markdown,
    write_provider_continuity_audit_report,
)


def _write_artifact(root: Path, *, mismatch: bool = False) -> Path:
    root.mkdir(parents=True)
    requests = {
        "schema_version": 1,
        "status": "ok",
        "requests": [
            {
                "turn_index": 1,
                "previous_response_id": None,
                "previous_response_id_in_request_body": False,
                "previous_response_delta_mode": "none",
                "request_body": {
                    "input": [
                        {"role": "user", "content": [{"type": "input_text", "text": "Task: create output.txt"}]},
                    ],
                },
            },
            {
                "turn_index": 2,
                "previous_response_id": "wrong" if mismatch else "resp_1",
                "previous_response_id_in_request_body": True,
                "previous_response_delta_mode": "delta",
                "logical_input_item_count": 4,
                "previous_response_prefix_item_count": 99 if mismatch else 3,
                "wire_input_item_count": 1,
                "request_body": {
                    "previous_response_id": "wrong" if mismatch else "resp_1",
                    "input": [
                        {
                            "type": "function_call_output",
                            "call_id": "call_1",
                            "output": "ok",
                        }
                    ],
                },
            },
        ],
    }
    transcript = {
        "schema_version": 1,
        "items": [
            {
                "sequence": 1,
                "turn_id": "turn-1",
                "kind": "reasoning",
                "response_id": "resp_1",
            },
            {
                "sequence": 2,
                "turn_id": "turn-1",
                "kind": "function_call",
                "response_id": "resp_1",
                "call_id": "call_1",
                "tool_name": "exec_command",
            },
            {
                "sequence": 3,
                "turn_id": "turn-1",
                "kind": "function_call_output",
                "response_id": "resp_1",
                "call_id": "call_1",
                "tool_name": "exec_command",
                "status": "completed",
            },
            {
                "sequence": 4,
                "turn_id": "turn-2",
                "kind": "reasoning",
                "response_id": "resp_2",
            },
        ],
    }
    (root / "native-provider-requests.json").write_text(json.dumps(requests), encoding="utf-8")
    (root / "provider-request-inventory.json").write_text(
        json.dumps({"schema_version": 1, "status": "ok", "provider_request_inventory": []}),
        encoding="utf-8",
    )
    (root / "response_transcript.json").write_text(json.dumps(transcript), encoding="utf-8")
    (root / "response_items.jsonl").write_text(
        "\n".join(json.dumps(item) for item in transcript["items"]) + "\n",
        encoding="utf-8",
    )
    return root


def test_provider_continuity_audit_accepts_delta_previous_response(tmp_path: Path) -> None:
    root = _write_artifact(tmp_path / "artifact")

    report = analyze_provider_continuity(mew_artifact_root=root)

    aggregate = report["aggregate"]
    assert isinstance(aggregate, dict)
    assert aggregate["previous_response_missing_after_first"] == 0
    assert aggregate["expected_previous_response_mismatch_count"] == 0
    assert aggregate["delta_coverage_mismatch_count"] == 0
    assert aggregate["pairing_error_count"] == 0
    assert "Every request after the first used previous_response_id" in "\n".join(report["interpretation"])  # type: ignore[arg-type]


def test_provider_continuity_audit_flags_mismatched_previous_response(tmp_path: Path) -> None:
    root = _write_artifact(tmp_path / "artifact", mismatch=True)

    report = analyze_provider_continuity(mew_artifact_root=root)

    aggregate = report["aggregate"]
    assert isinstance(aggregate, dict)
    assert aggregate["expected_previous_response_mismatch_count"] == 1
    assert aggregate["delta_coverage_mismatch_count"] == 1
    assert "expected_previous_response_mismatch:1" in aggregate["warnings"]
    assert "delta_coverage_mismatch:1" in aggregate["warnings"]


def test_provider_continuity_audit_uses_wire_body_not_descriptor_flag(tmp_path: Path) -> None:
    root = _write_artifact(tmp_path / "artifact")
    native = json.loads((root / "native-provider-requests.json").read_text(encoding="utf-8"))
    native["requests"][1]["previous_response_id"] = "resp_1"
    native["requests"][1]["previous_response_id_in_request_body"] = True
    native["requests"][1]["request_body"].pop("previous_response_id")
    native["requests"][1]["wire_input_item_count"] = 99
    (root / "native-provider-requests.json").write_text(json.dumps(native), encoding="utf-8")

    report = analyze_provider_continuity(mew_artifact_root=root)

    aggregate = report["aggregate"]
    assert isinstance(aggregate, dict)
    assert aggregate["previous_response_missing_after_first"] == 1
    assert aggregate["wire_count_metadata_mismatch_count"] == 1
    assert aggregate["previous_response_body_descriptor_mismatch_count"] == 1


def test_provider_continuity_audit_requires_response_transcript(tmp_path: Path) -> None:
    root = _write_artifact(tmp_path / "artifact")
    (root / "response_transcript.json").unlink()

    with pytest.raises(FileNotFoundError) as exc_info:
        analyze_provider_continuity(mew_artifact_root=root)
    assert "response_transcript.json" in str(exc_info.value)


def test_provider_continuity_audit_flags_duplicate_pairing(tmp_path: Path) -> None:
    root = _write_artifact(tmp_path / "artifact")
    transcript = json.loads((root / "response_transcript.json").read_text(encoding="utf-8"))
    duplicate = dict(transcript["items"][1])
    duplicate["sequence"] = 5
    transcript["items"].append(duplicate)
    (root / "response_transcript.json").write_text(json.dumps(transcript), encoding="utf-8")
    (root / "response_items.jsonl").write_text(
        "\n".join(json.dumps(item) for item in transcript["items"]) + "\n",
        encoding="utf-8",
    )

    report = analyze_provider_continuity(mew_artifact_root=root)

    aggregate = report["aggregate"]
    assert isinstance(aggregate, dict)
    assert aggregate["sequence_error_count"] >= 1
    assert any(str(warning).startswith("sequence_errors:") for warning in aggregate["warnings"])


def test_provider_continuity_audit_flags_missing_call_id(tmp_path: Path) -> None:
    root = _write_artifact(tmp_path / "artifact")
    transcript = json.loads((root / "response_transcript.json").read_text(encoding="utf-8"))
    transcript["items"][1].pop("call_id")
    (root / "response_transcript.json").write_text(json.dumps(transcript), encoding="utf-8")
    (root / "response_items.jsonl").write_text(
        "\n".join(json.dumps(item) for item in transcript["items"]) + "\n",
        encoding="utf-8",
    )

    report = analyze_provider_continuity(mew_artifact_root=root)

    aggregate = report["aggregate"]
    assert isinstance(aggregate, dict)
    assert aggregate["pairing_error_count"] >= 1
    assert any(str(warning).startswith("pairing_errors:") for warning in aggregate["warnings"])


def test_provider_continuity_audit_writes_reports(tmp_path: Path) -> None:
    root = _write_artifact(tmp_path / "artifact")
    out_json = tmp_path / "continuity.json"
    out_md = tmp_path / "continuity.md"

    report = write_provider_continuity_audit_report(
        mew_artifact_root=root,
        out_json=out_json,
        out_md=out_md,
    )
    markdown = format_provider_continuity_markdown(report)

    assert out_json.is_file()
    assert out_md.is_file()
    assert "# M6.24 Provider Continuity Audit" in markdown
    assert "previous_response_id" in "\n".join(report["interpretation"])  # type: ignore[arg-type]
