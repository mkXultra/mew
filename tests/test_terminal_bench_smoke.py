from __future__ import annotations

import json

from mew.terminal_bench_smoke import main


def test_main_records_instruction_report_and_artifact_json(tmp_path):
    report_path = tmp_path / "nested" / "mew-report.json"
    artifact_dir = tmp_path / "artifacts"

    exit_code = main(
        [
            "--instruction",
            "solve this Terminal-Bench task",
            "--report",
            str(report_path),
            "--artifacts",
            str(artifact_dir),
        ]
    )

    assert exit_code == 0
    instruction = json.loads((artifact_dir / "instruction.json").read_text(encoding="utf-8"))
    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert instruction["instruction"] == "solve this Terminal-Bench task"
    assert isinstance(instruction["recorded_at"], str)
    assert report == {
        "artifacts": str(artifact_dir),
        "instruction": "solve this Terminal-Bench task",
        "instruction_path": str(artifact_dir / "instruction.json"),
        "status": "smoke-complete",
    }


def test_main_creates_missing_report_parent_and_artifacts_dir(tmp_path):
    report_path = tmp_path / "missing" / "parents" / "report.json"
    artifact_dir = tmp_path / "also" / "missing"

    assert main(["--instruction", "hi", "--report", str(report_path), "--artifacts", str(artifact_dir)]) == 0

    assert report_path.is_file()
    assert (artifact_dir / "instruction.json").is_file()
