from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "companion_log.py"
FIXTURE = ROOT / "fixtures" / "sample_session.json"


def test_render_report_from_fixture_module_import() -> None:
    sys.path.insert(0, str(ROOT))
    try:
        from companion_log import load_session, render_report
    finally:
        sys.path.pop(0)

    report = render_report(load_session(FIXTURE))

    assert report.startswith("# Companion Log: SP1 scaffold mew-companion-log")
    assert "- Status: in-progress" in report
    assert "## Highlights" in report
    assert "Confirmed the side project stays outside core mew source files." in report
    assert "## Next Steps" in report


def test_render_morning_journal_snapshot() -> None:
    sys.path.insert(0, str(ROOT))
    try:
        from companion_log import load_session, render_morning_journal
    finally:
        sys.path.pop(0)

    journal = render_morning_journal(load_session(FIXTURE))

    assert journal == (
        "# Morning Journal: SP2 companion output\n"
        "\n"
        "_Date: 2026-04-26_\n"
        "\n"
        "## Intention\n"
        "Make the first journal surface feel calm, fixture-driven, and easy to verify.\n"
        "\n"
        "## Gratitude\n"
        "- A small isolated experiment keeps product iteration safe.\n"
        "- Snapshot tests can document the markdown shape.\n"
        "\n"
        "## Focus\n"
        "- Preserve the existing companion report CLI behavior.\n"
        "- Add a morning journal mode backed by fixture JSON.\n"
        "\n"
        "## Watch For\n"
        "- Avoid touching core mew source files.\n"
        "\n"
        "## Companion Prompt\n"
        "What is the one gentle next action that would make today successful?\n"
    )


def test_cli_prints_markdown_to_stdout() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(FIXTURE)],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "# Companion Log: SP1 scaffold mew-companion-log" in result.stdout
    assert "- Goal: Create an isolated companion log scaffold" in result.stdout
    assert result.stderr == ""


def test_cli_prints_morning_journal_mode_to_stdout() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(FIXTURE), "--mode", "morning-journal"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.startswith("# Morning Journal: SP2 companion output")
    assert "## Companion Prompt" in result.stdout
    assert "one gentle next action" in result.stdout
    assert result.stderr == ""


def test_cli_writes_markdown_output_file(tmp_path: Path) -> None:
    output = tmp_path / "report.md"

    subprocess.run(
        [sys.executable, str(SCRIPT), str(FIXTURE), "--output", str(output)],
        check=True,
        capture_output=True,
        text=True,
    )

    written = output.read_text(encoding="utf-8")
    assert written.startswith("# Companion Log: SP1 scaffold mew-companion-log")
    assert "Run the focused pytest command for the side project." in written


def test_fixture_is_valid_json_object() -> None:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))

    assert data["id"] == "sp1-sample"
    assert isinstance(data["highlights"], list)
    assert isinstance(data["morning_journal"], dict)
    assert isinstance(data["morning_journal"]["focus"], list)
