from __future__ import annotations

import json
from pathlib import Path

from mew.implement_lane.hot_path_step_diff import (
    analyze_hot_path_step_diff,
    format_hot_path_step_diff_markdown,
    write_hot_path_step_diff_report,
)


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def _codex_tool_events(
    *,
    tool: str,
    tool_id: str,
    summary: str,
    arguments: dict[str, object],
    step_id: int,
    elapsed_ms: int,
    status: str = "completed",
    exit_code: int | None = None,
) -> list[dict[str, object]]:
    started = {
        "schema_version": 1,
        "agent": "codex",
        "kind": "tool_call",
        "phase": "started",
        "tool": tool,
        "id": tool_id,
        "summary": summary,
        "arguments": arguments,
        "step_id": step_id,
        "elapsed_ms": elapsed_ms,
        "source": "agent_trace.jsonl",
        "line_number": step_id,
    }
    completed = {
        **started,
        "phase": "completed",
        "status": status,
        "elapsed_ms": elapsed_ms + 100,
        "duration_ms": 100,
    }
    if exit_code is not None:
        completed["exit_code"] = exit_code
    return [started, completed]


def _write_codex_reference(root: Path) -> Path:
    trace_dir = root / "normalized-trace"
    rows: list[dict[str, object]] = []
    rows.extend(
        _codex_tool_events(
            tool="read_file",
            tool_id="read-1",
            summary="src/main.c",
            arguments={"path": "src/main.c"},
            step_id=1,
            elapsed_ms=1000,
        )
    )
    rows.extend(
        _codex_tool_events(
            tool="apply_patch",
            tool_id="patch-1",
            summary="*** Begin Patch",
            arguments={"patch": "*** Begin Patch\n*** Update File: src/main.c\n@@\n-old\n+new\n*** End Patch"},
            step_id=2,
            elapsed_ms=2000,
        )
    )
    rows.extend(
        _codex_tool_events(
            tool="exec_command",
            tool_id="verify-1",
            summary="pytest -q",
            arguments={"cmd": "pytest -q"},
            step_id=3,
            elapsed_ms=3000,
            exit_code=0,
        )
    )
    _write_jsonl(trace_dir / "agent_trace.jsonl", rows)
    (trace_dir / "summary.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "agent": "codex",
                "tool_call_count": 6,
                "tool_call_started_count": 3,
                "first_edit_seconds": 2.0,
                "first_verifier_seconds": 3.0,
                "total_seconds": 3.1,
            }
        ),
        encoding="utf-8",
    )
    return root


def _write_codex_reference_with_command_steps(root: Path, commands: list[str]) -> Path:
    trace_dir = root / "normalized-trace"
    rows: list[dict[str, object]] = []
    for index, command in enumerate(commands, 1):
        rows.extend(
            _codex_tool_events(
                tool="exec_command",
                tool_id=f"cmd-{index}",
                summary=command,
                arguments={"cmd": command},
                step_id=index,
                elapsed_ms=index * 1000,
                exit_code=0,
            )
        )
    rows.extend(
        _codex_tool_events(
            tool="apply_patch",
            tool_id="patch-1",
            summary="*** Begin Patch",
            arguments={"patch": "*** Begin Patch\n*** Update File: src/main.c\n@@\n-old\n+new\n*** End Patch"},
            step_id=len(commands) + 1,
            elapsed_ms=(len(commands) + 1) * 1000,
        )
    )
    _write_jsonl(trace_dir / "agent_trace.jsonl", rows)
    (trace_dir / "summary.json").write_text(
        json.dumps({"schema_version": 1, "agent": "codex", "tool_call_count": len(rows)}),
        encoding="utf-8",
    )
    return root


def _write_codex_reference_with_commands(root: Path, commands: list[str]) -> Path:
    trace_dir = root / "normalized-trace"
    rows: list[dict[str, object]] = []
    for index, command in enumerate(commands, 1):
        rows.extend(
            _codex_tool_events(
                tool="exec_command",
                tool_id=f"cmd-{index}",
                summary=command,
                arguments={"cmd": command},
                step_id=index,
                elapsed_ms=index * 1000,
                exit_code=0,
            )
        )
    _write_jsonl(trace_dir / "agent_trace.jsonl", rows)
    (trace_dir / "summary.json").write_text(
        json.dumps({"schema_version": 1, "agent": "codex", "tool_call_count": len(rows)}),
        encoding="utf-8",
    )
    return root


def _native_call(sequence: int, turn: int, call_id: str, tool_name: str, arguments: dict[str, object]) -> dict[str, object]:
    return {
        "sequence": sequence,
        "kind": "function_call",
        "turn_id": f"turn-{turn}",
        "call_id": call_id,
        "tool_name": tool_name,
        "arguments_json_text": json.dumps(arguments),
        "output_index": sequence,
    }


def _native_output(sequence: int, turn: int, call_id: str, tool_name: str, output: str, *, exit_code: int = 0) -> dict[str, object]:
    return {
        "sequence": sequence,
        "kind": "function_call_output",
        "turn_id": f"turn-{turn}",
        "call_id": call_id,
        "tool_name": tool_name,
        "status": "completed",
        "output_text_or_ref": f"{output}; exit_code={exit_code}",
        "output_index": sequence,
    }


def _write_mew_artifact(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    calls = [
        _native_call(1, 1, "scan-1", "exec_command", {"cmd": "rg TODO src"}),
        _native_call(3, 2, "scan-2", "exec_command", {"cmd": "rg FIXME src"}),
        _native_call(5, 3, "read-1", "read_file", {"path": "src/main.c"}),
        _native_call(7, 4, "patch-1", "apply_patch", {"patch": "*** Begin Patch\n*** End Patch", "apply": True}),
        _native_call(9, 5, "verify-1", "run_tests", {"command": "pytest -q"}),
    ]
    outputs = [
        _native_output(2, 1, "scan-1", "exec_command", "one TODO"),
        _native_output(4, 2, "scan-2", "exec_command", "one FIXME"),
        _native_output(6, 3, "read-1", "read_file", "old"),
        _native_output(8, 4, "patch-1", "apply_patch", "patched"),
        _native_output(10, 5, "verify-1", "run_tests", "passed"),
    ]
    items = [item for pair in zip(calls, outputs) for item in pair]
    (root / "response_transcript.json").write_text(json.dumps({"items": items}), encoding="utf-8")
    (root / "proof-manifest.json").write_text(
        json.dumps(
            {
                "metrics": {
                    "tool_latency": [
                        {"call_id": "scan-1", "started_ms": 1000, "finished_ms": 100},
                        {"call_id": "scan-2", "started_ms": 2000, "finished_ms": 100},
                        {"call_id": "read-1", "started_ms": 3000, "finished_ms": 100},
                        {"call_id": "patch-1", "started_ms": 4000, "finished_ms": 100},
                        {"call_id": "verify-1", "started_ms": 5000, "finished_ms": 100},
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    (root / "transcript_metrics.json").write_text(
        json.dumps({"call_count": 5, "output_count": 5, "pairing_valid": True, "provider_native_tool_loop": True}),
        encoding="utf-8",
    )
    (root / "native-provider-requests.json").write_text(
        json.dumps({"status": "completed", "request_count": 5, "native_transport_kind": "provider_native"}),
        encoding="utf-8",
    )
    return root


def test_hot_path_step_diff_compares_reference_and_mew_native_artifact(tmp_path: Path) -> None:
    codex_root = _write_codex_reference(tmp_path / "codex")
    mew_root = _write_mew_artifact(tmp_path / "mew")

    report = analyze_hot_path_step_diff(codex_reference_root=codex_root, mew_artifact_root=mew_root)

    codex_summary = report["summary"]["codex"]
    mew_summary = report["summary"]["mew"]
    assert codex_summary["probe_count_before_first_mutation"] == 1
    assert mew_summary["probe_count_before_first_mutation"] == 3
    assert codex_summary["first_mutation_turn"] == 2
    assert mew_summary["first_mutation_turn"] == 4
    assert [step["intent"] for step in report["normalized_codex_steps"]] == [
        "source_read",
        "mutation",
        "runtime_verifier",
    ]
    assert [step["intent"] for step in report["normalized_mew_steps"]] == [
        "source_scan",
        "source_scan",
        "source_read",
        "mutation",
        "runtime_verifier",
    ]
    mew_repeats = report["repeated_probe_family_diagnostics"]["mew"]["before_first_mutation"]
    assert mew_repeats[0]["family"] == "source_scan:rg"
    assert report["possible_first_patch_opportunity_diagnostics"][0]["kind"] == (
        "reference_first_mutation_probe_budget_exceeded"
    )
    assert report["summary"]["mew"]["artifact_summary"]["native_provider_requests"]["request_count"] == 5


def test_hot_path_step_diff_writes_json_and_markdown(tmp_path: Path) -> None:
    codex_root = _write_codex_reference(tmp_path / "codex")
    mew_root = _write_mew_artifact(tmp_path / "mew")
    out_json = tmp_path / "out" / "step-diff.json"
    out_md = tmp_path / "out" / "step-diff.md"

    report = write_hot_path_step_diff_report(
        codex_reference_root=codex_root,
        mew_artifact_root=mew_root,
        out_json=out_json,
        out_md=out_md,
    )
    markdown = format_hot_path_step_diff_markdown(report)

    assert out_json.exists()
    assert out_md.exists()
    assert json.loads(out_json.read_text(encoding="utf-8"))["report_kind"] == "m6_24_hot_path_step_diff"
    assert "Normalized Codex Steps" in out_md.read_text(encoding="utf-8")
    assert "Normalized mew Steps" in markdown


def test_hot_path_step_diff_accepts_normalized_json_trace(tmp_path: Path) -> None:
    codex_root = _write_codex_reference(tmp_path / "codex")
    trace_dir = codex_root / "normalized-trace"
    rows = [json.loads(line) for line in (trace_dir / "agent_trace.jsonl").read_text(encoding="utf-8").splitlines()]
    (trace_dir / "agent_trace.jsonl").unlink()
    (trace_dir / "agent_trace.json").write_text(json.dumps({"events": rows}), encoding="utf-8")
    mew_root = _write_mew_artifact(tmp_path / "mew")

    report = analyze_hot_path_step_diff(codex_reference_root=codex_root, mew_artifact_root=mew_root)

    assert report["sources"]["codex"]["events"].endswith("agent_trace.json")
    assert report["summary"]["codex"]["first_mutation_turn"] == 2


def test_hot_path_step_diff_does_not_treat_readonly_greater_than_text_as_mutation(tmp_path: Path) -> None:
    codex_root = _write_codex_reference_with_commands(
        tmp_path / "codex",
        [
            "llvm-objdump -d ./program | rg 'branch > target'",
            "node <<'NODE'\nconst shifted = value >>> 1;\n// comment mentions comparison > src/main.c\nNODE",
            "rg 'state > next' src >/dev/null",
            "python -c \"print('literal > src/main.c')\"",
            "rg apply_patch src",
            "apply_patch <<'PATCH'\n*** Begin Patch\n*** Update File: src/main.c\n@@\n-old\n+new\n*** End Patch\nPATCH",
        ],
    )
    mew_root = _write_mew_artifact(tmp_path / "mew")

    report = analyze_hot_path_step_diff(codex_reference_root=codex_root, mew_artifact_root=mew_root)

    codex_steps = report["normalized_codex_steps"]
    assert [step["intent"] for step in codex_steps[:5]] == [
        "disassembly_probe",
        "runtime_verifier",
        "source_scan",
        "runtime_verifier",
        "source_scan",
    ]
    assert codex_steps[5]["intent"] == "mutation"
    assert report["summary"]["codex"]["first_mutation_step_index"] == 6


def test_hot_path_step_diff_keeps_source_file_redirection_as_command_mutation(tmp_path: Path) -> None:
    codex_root = _write_codex_reference_with_commands(
        tmp_path / "codex",
        [
            "printf 'print(42)\\n' > src/generated.py",
        ],
    )
    mew_root = _write_mew_artifact(tmp_path / "mew")

    report = analyze_hot_path_step_diff(codex_reference_root=codex_root, mew_artifact_root=mew_root)

    first_step = report["normalized_codex_steps"][0]
    assert first_step["intent"] == "mutation"
    assert "command_write_pattern" in first_step["classification_basis"]


def test_hot_path_step_diff_keeps_read_only_shell_operators_out_of_mutations(tmp_path: Path) -> None:
    codex_root = _write_codex_reference_with_command_steps(
        tmp_path / "codex",
        [
            "llvm-objdump -d /app/program | rg 'slt|bgtz|a > b|>' >/dev/null",
            "node -e \"const fs = require('fs'); const b = fs.readFileSync('/app/program'); console.log(b[0] >>> 2)\"",
            "python -c \"print(3 > 2)\" > /dev/null",
        ],
    )
    mew_root = _write_mew_artifact(tmp_path / "mew")

    report = analyze_hot_path_step_diff(codex_reference_root=codex_root, mew_artifact_root=mew_root)
    codex_steps = report["normalized_codex_steps"]

    assert [step["intent"] for step in codex_steps[:3]] == [
        "disassembly_probe",
        "binary_probe",
        "runtime_verifier",
    ]
    assert all(step["intent"] != "mutation" for step in codex_steps[:3])
    assert report["summary"]["codex"]["first_mutation_step_index"] == 4


def test_hot_path_step_diff_still_detects_source_redirection_mutation(tmp_path: Path) -> None:
    codex_root = _write_codex_reference_with_command_steps(
        tmp_path / "codex",
        ["cat <<'EOF' > src/generated.c\nint main(void) { return 0; }\nEOF"],
    )
    mew_root = _write_mew_artifact(tmp_path / "mew")

    report = analyze_hot_path_step_diff(codex_reference_root=codex_root, mew_artifact_root=mew_root)

    assert report["normalized_codex_steps"][0]["intent"] == "mutation"
    assert report["summary"]["codex"]["first_mutation_step_index"] == 1
