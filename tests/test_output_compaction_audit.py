from __future__ import annotations

import json
from pathlib import Path

from mew.implement_lane.output_compaction_audit import (
    analyze_output_compaction,
    format_output_compaction_markdown,
    write_output_compaction_audit_report,
)


def _tool_result(call_id: str, *, stdout: str, visible: str) -> tuple[dict[str, object], dict[str, object]]:
    result = {
        "provider_call_id": call_id,
        "tool_name": "exec_command",
        "status": "completed",
        "content": [
            {
                "provider_call_id": call_id,
                "tool_name": "exec_command",
                "command": "cat /app/src/main.c && ./verify",
                "status": "completed",
                "exit_code": 0,
                "stdout": stdout,
                "stderr": "",
                "output_truncated": False,
            }
        ],
    }
    provider_item = {
        "type": "function_call_output",
        "call_id": call_id,
        "output": visible,
    }
    return result, provider_item


def _write_artifact(root: Path, *, compacted: bool = True) -> Path:
    root.mkdir(parents=True)
    raw_stdout = "\n".join(
        [
            "/app/src/main.c",
            "int important_symbol(int x) { return x + 1; }",
            "ERROR: missing syscall writev",
            "Entry point 0x400110",
            "tail line",
        ]
    )
    visible = "tail line" if compacted else raw_stdout
    result, provider_item = _tool_result("call_1", stdout=raw_stdout, visible=visible)
    (root / "tool_results.jsonl").write_text(json.dumps(result) + "\n", encoding="utf-8")
    (root / "native-provider-requests.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "status": "ok",
                "requests": [
                    {
                        "turn_index": 2,
                        "request_body": {
                            "previous_response_id": "resp_1",
                            "input": [provider_item],
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (root / "tool_render_outputs.jsonl").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "call_id": "call_1",
                "tool_name": "exec_command",
                "output_chars": len(visible),
                "output_bytes": len(visible.encode()),
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return root


def test_output_compaction_audit_flags_missing_critical_facts(tmp_path: Path) -> None:
    root = _write_artifact(tmp_path / "artifact", compacted=True)

    report = analyze_output_compaction(mew_artifact_root=root)

    aggregate = report["aggregate"]
    assert isinstance(aggregate, dict)
    assert aggregate["critical_fact_loss_result_count"] == 1
    assert aggregate["lost_critical_fact_count"] > 0
    assert "H5 found a concrete output-visibility gap" in "\n".join(report["interpretation"])  # type: ignore[arg-type]
    top = report["top_losses"]
    assert isinstance(top, list)
    assert top
    assert any("paths:/app/src/main.c" in sample for sample in top[0]["missing_fact_samples"])


def test_output_compaction_audit_accepts_fully_visible_output(tmp_path: Path) -> None:
    root = _write_artifact(tmp_path / "artifact", compacted=False)

    report = analyze_output_compaction(mew_artifact_root=root)

    aggregate = report["aggregate"]
    assert isinstance(aggregate, dict)
    assert aggregate["critical_fact_loss_result_count"] == 0
    assert aggregate["lost_critical_fact_count"] == 0
    assert "H5 found no critical raw-vs-visible fact loss" in "\n".join(report["interpretation"])  # type: ignore[arg-type]


def test_output_compaction_audit_uses_wire_output_not_logical_metadata(tmp_path: Path) -> None:
    root = _write_artifact(tmp_path / "artifact", compacted=True)
    native = json.loads((root / "native-provider-requests.json").read_text(encoding="utf-8"))
    native["requests"][0]["logical_input_items"] = [
        {
            "type": "function_call_output",
            "call_id": "call_1",
            "output": "\n".join(
                [
                    "/app/src/main.c",
                    "int important_symbol(int x) { return x + 1; }",
                    "ERROR: missing syscall writev",
                    "Entry point 0x400110",
                    "tail line",
                ]
            ),
        }
    ]
    (root / "native-provider-requests.json").write_text(json.dumps(native), encoding="utf-8")

    report = analyze_output_compaction(mew_artifact_root=root)

    aggregate = report["aggregate"]
    assert isinstance(aggregate, dict)
    assert aggregate["critical_fact_loss_result_count"] == 1


def test_output_compaction_audit_does_not_count_unmatched_results_as_compacted(tmp_path: Path) -> None:
    root = _write_artifact(tmp_path / "artifact", compacted=True)
    native = json.loads((root / "native-provider-requests.json").read_text(encoding="utf-8"))
    native["requests"][0]["request_body"]["input"] = []
    (root / "native-provider-requests.json").write_text(json.dumps(native), encoding="utf-8")

    report = analyze_output_compaction(mew_artifact_root=root)

    aggregate = report["aggregate"]
    assert isinstance(aggregate, dict)
    assert aggregate["provider_output_missing_count"] == 1
    assert aggregate["critical_fact_loss_result_count"] == 0
    assert aggregate["omitted_output_chars_total"] == 0


def test_output_compaction_audit_writes_reports(tmp_path: Path) -> None:
    root = _write_artifact(tmp_path / "artifact", compacted=True)
    out_json = tmp_path / "compaction.json"
    out_md = tmp_path / "compaction.md"

    report = write_output_compaction_audit_report(
        mew_artifact_root=root,
        out_json=out_json,
        out_md=out_md,
    )
    markdown = format_output_compaction_markdown(report)

    assert out_json.is_file()
    assert out_md.is_file()
    assert "# M6.24 Output Compaction Audit" in markdown
    assert "Output Compaction" in out_md.read_text(encoding="utf-8")
