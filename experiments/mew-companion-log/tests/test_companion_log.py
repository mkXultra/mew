from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "companion_log.py"
FIXTURE = ROOT / "fixtures" / "sample_session.json"
STATE_FIXTURE = ROOT / "fixtures" / "sample_mew_state.json"
BUNDLE_FIXTURE = ROOT / "fixtures" / "sample_bundle.json"
ARCHIVE_FIXTURE = ROOT / "fixtures" / "sample_archive.json"
DOGFOOD_DIGEST_FIXTURE = ROOT / "fixtures" / "sample_dogfood_digest.json"


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


def test_render_evening_journal_snapshot() -> None:
    sys.path.insert(0, str(ROOT))
    try:
        from companion_log import load_session, render_evening_journal
    finally:
        sys.path.pop(0)

    journal = render_evening_journal(load_session(FIXTURE))

    assert journal == (
        "# Evening Journal: SP2 companion output\n"
        "\n"
        "_Date: 2026-04-26_\n"
        "\n"
        "## Reflection\n"
        "The companion log experiment now has room for both planning the day and closing it gently.\n"
        "\n"
        "## Wins\n"
        "- Kept the journal surface fixture-driven and easy to snapshot.\n"
        "- Preserved the existing report and morning journal behavior.\n"
        "\n"
        "## Learned\n"
        "- A small CLI mode can make a second surface discoverable without changing the default report.\n"
        "\n"
        "## Release\n"
        "- No need to solve every future companion prompt in this scaffold.\n"
        "\n"
        "## Tomorrow\n"
        "- Run the focused pytest command after reviewing the markdown shape.\n"
        "\n"
        "## Companion Prompt\n"
        "What should be acknowledged before setting the work down for the night?\n"
    )


def test_render_dream_learning_snapshot() -> None:
    sys.path.insert(0, str(ROOT))
    try:
        from companion_log import load_session, render_dream_learning
    finally:
        sys.path.pop(0)

    dream = render_dream_learning(load_session(FIXTURE))

    assert dream == (
        "# Dream Learning: SP2 companion output\n"
        "\n"
        "_Date: 2026-04-26_\n"
        "\n"
        "## Dream\n"
        "Let the companion notice quiet patterns across the day without turning them into pressure.\n"
        "\n"
        "## Signals\n"
        "- Morning intentions and evening reflections both point toward gentle, fixture-driven surfaces.\n"
        "- Small CLI modes keep each companion output discoverable without changing the default report.\n"
        "\n"
        "## Learning\n"
        "- Snapshot tests make the markdown contract easy to review.\n"
        "- A final dream/learning mode can connect planning and reflection into one lightweight surface.\n"
        "\n"
        "## Practice\n"
        "- Choose one learning signal to carry into tomorrow's experiment.\n"
        "- Keep the next companion iteration isolated under experiments/mew-companion-log.\n"
        "\n"
        "## Companion Prompt\n"
        "What quiet signal wants to become tomorrow's small experiment?\n"
    )


def test_render_research_digest_snapshot() -> None:
    sys.path.insert(0, str(ROOT))
    try:
        from companion_log import load_session, render_research_digest
    finally:
        sys.path.pop(0)

    digest = render_research_digest(load_session(FIXTURE))

    assert digest == (
        "# Research Digest: SP4 static companion output\n"
        "\n"
        "_Date: 2026-04-26_\n"
        "\n"
        "## Summary\n"
        "Fixture-backed digest of local research signals; no live feeds are fetched.\n"
        "\n"
        "## Ranked Entries\n"
        "1. **Mew companion patterns** _(Local Notes, score 98)_\n"
        "   - Why: Connects morning, evening, and dream surfaces into one companion loop.\n"
        "   - URL: fixture://research/mew-companion-patterns\n"
        "   - Tags: companion, fixtures\n"
        "2. **Deterministic digest rendering** _(Test Journal, score 91)_\n"
        "   - Why: Keeps ranking stable for snapshot-style tests and CLI review.\n"
        "   - URL: fixture://research/deterministic-digest-rendering\n"
        "   - Tags: testing, markdown\n"
        "3. **Static feed safety** _(Experiment Brief, score 87)_\n"
        "   - Why: Demonstrates a research/feed slice without live network dependency.\n"
        "   - URL: fixture://research/static-feed-safety\n"
        "   - Tags: offline, safety\n"
    )


def test_render_state_brief_snapshot() -> None:
    sys.path.insert(0, str(ROOT))
    try:
        from companion_log import load_session, render_state_brief
    finally:
        sys.path.pop(0)

    brief = render_state_brief(load_session(STATE_FIXTURE))

    assert brief == (
        "# Mew State Companion Brief: SP6 side-project loop\n"
        "\n"
        "_Date: 2026-04-26_\n"
        "\n"
        "## Current State\n"
        "- Status: focused side-project implementation\n"
        "- Summary: Static fixture snapshot for companion review; it is not read from live .mew state.\n"
        "- Active task: SP6 add state brief companion output\n"
        "\n"
        "## Recent Work\n"
        "- Tasks: SP4 research digest completed; SP6 state brief is now active.\n"
        "- Sessions: Work session 9 inspected the companion-log CLI, tests, README, and fixtures.\n"
        "- Memory notes: Long-session charter preserves the no-core-source and static-fixture boundary.\n"
        "- Dogfood: CLI stdout and output-file checks make companion markdown reviewable.\n"
        "- Side-pj issues: SP6 remains the next side-project issue to land after SP4.\n"
        "\n"
        "## Unresolved Risks\n"
        "- Accidentally reading live mew state: Use only this static fixture under experiments/mew-companion-log.\n"
        "- State brief becoming too verbose: Render only current state, recent work, unresolved risks, and one next action.\n"
        "\n"
        "## Next Suggested Side-Project Action\n"
        "- Land SP6 state-brief mode with fixture, README usage, and focused tests.\n"
        "  - Why: It gives the companion a concise state export without coupling to core mew internals.\n"
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


def test_cli_prints_evening_journal_mode_to_stdout() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(FIXTURE), "--mode", "evening-journal"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.startswith("# Evening Journal: SP2 companion output")
    assert "## Tomorrow" in result.stdout
    assert "setting the work down for the night" in result.stdout
    assert result.stderr == ""


def test_cli_prints_dream_learning_mode_to_stdout() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(FIXTURE), "--mode", "dream-learning"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.startswith("# Dream Learning: SP2 companion output")
    assert "## Learning" in result.stdout
    assert "tomorrow's small experiment" in result.stdout
    assert result.stderr == ""


def test_cli_prints_research_digest_mode_to_stdout() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(FIXTURE), "--mode", "research-digest"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.startswith("# Research Digest: SP4 static companion output")
    assert "## Ranked Entries" in result.stdout
    assert "1. **Mew companion patterns**" in result.stdout
    assert "fixture://research/static-feed-safety" in result.stdout
    assert result.stderr == ""


def test_cli_prints_state_brief_mode_to_stdout() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(STATE_FIXTURE), "--mode", "state-brief"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.startswith("# Mew State Companion Brief: SP6 side-project loop")
    assert "## Current State" in result.stdout
    assert "## Recent Work" in result.stdout
    assert "## Unresolved Risks" in result.stdout
    assert "## Next Suggested Side-Project Action" in result.stdout
    assert "Land SP6 state-brief mode" in result.stdout
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


def test_cli_writes_research_digest_output_file(tmp_path: Path) -> None:
    output = tmp_path / "research-digest.md"

    subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            str(FIXTURE),
            "--mode",
            "research-digest",
            "--output",
            str(output),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    written = output.read_text(encoding="utf-8")
    assert written.startswith("# Research Digest: SP4 static companion output")
    assert "1. **Mew companion patterns**" in written


def test_cli_writes_state_brief_output_file(tmp_path: Path) -> None:
    output = tmp_path / "state-brief.md"

    subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            str(STATE_FIXTURE),
            "--mode",
            "state-brief",
            "--output",
            str(output),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    written = output.read_text(encoding="utf-8")
    assert written.startswith("# Mew State Companion Brief: SP6 side-project loop")
    assert "Accidentally reading live mew state" in written
    assert "Next Suggested Side-Project Action" in written


def test_fixture_is_valid_json_object() -> None:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))

    assert data["id"] == "sp1-sample"
    assert isinstance(data["highlights"], list)
    assert isinstance(data["morning_journal"], dict)
    assert isinstance(data["morning_journal"]["focus"], list)
    assert isinstance(data["evening_journal"], dict)
    assert isinstance(data["evening_journal"]["wins"], list)
    assert isinstance(data["research_digest"], dict)
    assert isinstance(data["research_digest"]["entries"], list)
    assert data["research_digest"]["entries"][0]["url"].startswith("fixture://research/")


def test_state_fixture_is_valid_json_object() -> None:
    data = json.loads(STATE_FIXTURE.read_text(encoding="utf-8"))

    assert data["id"] == "sp6-sample-state"
    assert isinstance(data["current_state"], dict)
    assert isinstance(data["recent_tasks"], list)
    assert isinstance(data["sessions"], list)
    assert isinstance(data["memory_notes"], list)
    assert isinstance(data["dogfood_rows"], list)
    assert isinstance(data["side_pj_issues"], list)
    assert isinstance(data["recent_work"], list)
    assert isinstance(data["unresolved_risks"], list)
    assert isinstance(data["next_side_project_action"], dict)


def test_render_bundle_snapshot() -> None:
    sys.path.insert(0, str(ROOT))
    try:
        from companion_log import load_session, render_bundle
    finally:
        sys.path.pop(0)

    bundle = render_bundle(load_session(BUNDLE_FIXTURE), base_path=BUNDLE_FIXTURE.parent)

    assert bundle.startswith("# Companion Bundle: SP7 multi-fixture companion bundle")
    assert "## Session fixture surfaces" in bundle
    assert "### Morning journal" in bundle
    assert "# Morning Journal: SP2 companion output" in bundle
    assert "### Research digest" in bundle
    assert "# Research Digest: SP4 static companion output" in bundle
    assert "## State fixture surfaces" in bundle
    assert "### State brief" in bundle
    assert "# Mew State Companion Brief: SP6 side-project loop" in bundle


def test_cli_prints_bundle_mode_to_stdout() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(BUNDLE_FIXTURE), "--mode", "bundle"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.startswith("# Companion Bundle: SP7 multi-fixture companion bundle")
    assert "## Session fixture surfaces" in result.stdout
    assert "## State fixture surfaces" in result.stdout
    assert result.stdout.index("### Morning journal") < result.stdout.index("### Research digest")
    assert result.stdout.index("### Research digest") < result.stdout.index("### State brief")
    assert result.stderr == ""


def test_cli_writes_bundle_output_file(tmp_path: Path) -> None:
    output = tmp_path / "bundle.md"

    subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            str(BUNDLE_FIXTURE),
            "--mode",
            "bundle",
            "--output",
            str(output),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    written = output.read_text(encoding="utf-8")
    assert written.startswith("# Companion Bundle: SP7 multi-fixture companion bundle")
    assert "# Morning Journal: SP2 companion output" in written
    assert "# Mew State Companion Brief: SP6 side-project loop" in written


def test_render_archive_index_snapshot() -> None:
    sys.path.insert(0, str(ROOT))
    try:
        from companion_log import load_session, render_archive_index
    finally:
        sys.path.pop(0)

    archive = render_archive_index(load_session(ARCHIVE_FIXTURE))

    assert archive == (
        "# Companion Archive Index: SP8 multi-day companion archive\n"
        "\n"
        "_Date: 2026-04-26_\n"
        "\n"
        "## Summary\n"
        "Static multi-day archive manifest for reviewing companion outputs without reading live mew state.\n"
        "\n"
        "## 2026-04-24\n"
        "- Summary: Earlier companion outputs show research and state context.\n"
        "\n"
        "### research-digest\n"
        "#### Next action: Carry the strongest signal forward\n"
        "- **Research digest review** (`research-digest`) — Ranked static research feed for companion planning.\n"
        "  - Fixture: sample_session.json\n"
        "  - Why: The digest can seed a later companion loop.\n"
        "\n"
        "### state-brief\n"
        "#### Next action: Stay inside fixture boundaries\n"
        "- **State brief checkpoint** (`state-brief`) — A static state snapshot marks the project boundary.\n"
        "  - Fixture: sample_mew_state.json\n"
        "  - Why: Avoid live .mew reads while reviewing archive history.\n"
        "\n"
        "## 2026-04-25\n"
        "- Summary: A deliberately empty archive day documents quiet days.\n"
        "- No companion outputs archived for this day.\n"
        "\n"
        "## 2026-04-26\n"
        "- Summary: SP6 and SP7 companion surfaces are ready for review.\n"
        "\n"
        "### morning-journal\n"
        "#### Next action: Keep journal behavior unchanged\n"
        "- **Morning journal companion note** (`morning-journal`) — Morning planning remains available as a single-session surface.\n"
        "  - Fixture: sample_session.json\n"
        "  - Why: The archive index should not alter single-session markdown.\n"
        "\n"
        "### state-brief\n"
        "#### Next action: Review SP8 archive index\n"
        "- **State brief after SP6** (`state-brief`) — Static state brief summarizes current side-project context.\n"
        "  - Fixture: sample_mew_state.json\n"
        "  - Why: Use the archive index to choose the next companion surface.\n"
    )


def test_cli_prints_archive_index_mode_to_stdout() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(ARCHIVE_FIXTURE), "--mode", "archive-index"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.startswith("# Companion Archive Index: SP8 multi-day companion archive")
    assert "# Companion Bundle:" not in result.stdout
    assert "# Companion Log:" not in result.stdout
    assert result.stdout.index("## 2026-04-24") < result.stdout.index("## 2026-04-25")
    assert result.stdout.index("## 2026-04-25") < result.stdout.index("## 2026-04-26")
    day_2026_04_26 = result.stdout.split("## 2026-04-26", 1)[1]
    assert day_2026_04_26.index("### morning-journal") < day_2026_04_26.index("### state-brief")
    assert "- No companion outputs archived for this day." in result.stdout
    assert result.stderr == ""


def test_cli_writes_archive_index_output_file(tmp_path: Path) -> None:
    output = tmp_path / "archive-index.md"

    subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            str(ARCHIVE_FIXTURE),
            "--mode",
            "archive-index",
            "--output",
            str(output),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    written = output.read_text(encoding="utf-8")
    assert written.startswith("# Companion Archive Index: SP8 multi-day companion archive")
    assert "#### Next action: Review SP8 archive index" in written
    assert "sample_mew_state.json" in written


def test_archive_fixture_is_valid_json_object() -> None:
    data = json.loads(ARCHIVE_FIXTURE.read_text(encoding="utf-8"))

    assert data["id"] == "sp8-sample-archive"
    assert isinstance(data["days"], list)
    assert {day["day"] for day in data["days"]} == {
        "2026-04-24",
        "2026-04-25",
        "2026-04-26",
    }
    assert any(day["entries"] == [] for day in data["days"])
    required = {"day", "surface", "fixture", "mode", "title", "summary", "next_action"}
    for day in data["days"]:
        assert isinstance(day["entries"], list)
        for entry in day["entries"]:
            assert required <= set(entry)
            assert entry["day"] == day["day"]
            assert not Path(entry["fixture"]).is_absolute()
            assert isinstance(entry["next_action"], dict)
            assert "label" in entry["next_action"]


def test_render_dogfood_digest_groups_failure_classes_and_links_issues() -> None:
    sys.path.insert(0, str(ROOT))
    try:
        from companion_log import load_session, render_dogfood_digest
    finally:
        sys.path.pop(0)

    digest = render_dogfood_digest(load_session(DOGFOOD_DIGEST_FIXTURE))

    assert digest.startswith("# Dogfood Digest: SP9 side-project dogfood digest")
    assert "- completed: 2" in digest
    assert "- completed-with-resume-repair: 1" in digest
    assert "- completed-with-test-followup: 1" in digest
    assert "rescued" not in digest
    assert digest.index("### context-drift") < digest.index("### verifier-gap")
    assert "- Rows: 2" in digest
    assert "  - rescue_edits: 1" not in digest
    assert "- rescue_edits_total: 0" in digest
    assert "  - SP9 retry after stopped session: 1" not in digest
    assert "  - Dogfood digest output-file coverage: 1" not in digest
    assert "Rescue edit:" not in digest
    assert "- [#4](https://github.com/mkXultra/mew/issues/4) [side-pj] M6.16 rejected-batch retry can accumulate context until timeout" in digest
    assert "- [#5](https://github.com/mkXultra/mew/issues/5) [side-pj] M6.16 scoped verifier repairs should not require fresh sessions" in digest
    assert "Importing src/mew or reading live .mew state from the experiment remains blocked." in digest
    assert "Tighten resume guidance when a session stops before product edits." in digest


def test_cli_prints_dogfood_digest_mode_to_stdout() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(DOGFOOD_DIGEST_FIXTURE), "--mode", "dogfood-digest"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.startswith("# Dogfood Digest: SP9 side-project dogfood digest")
    assert "## Failure Classes" in result.stdout
    assert "## [side-pj] Issues" in result.stdout
    assert "# Companion Archive Index:" not in result.stdout
    assert result.stderr == ""


def test_cli_writes_dogfood_digest_output_file(tmp_path: Path) -> None:
    output = tmp_path / "dogfood-digest.md"

    subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            str(DOGFOOD_DIGEST_FIXTURE),
            "--mode",
            "dogfood-digest",
            "--output",
            str(output),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    written = output.read_text(encoding="utf-8")
    assert written.startswith("# Dogfood Digest: SP9 side-project dogfood digest")
    assert "## Rescue Edits" in written
    assert "- rescue_edits_total: 0" in written
    assert "https://github.com/mkXultra/mew/issues/4" in written


def test_dogfood_digest_fixture_shape_is_static_and_explicit() -> None:
    data = json.loads(DOGFOOD_DIGEST_FIXTURE.read_text(encoding="utf-8"))

    assert data["id"] == "sp9-sample-dogfood-digest"
    assert isinstance(data["dogfood_rows"], list)
    assert isinstance(data["side_pj_issues"], list)
    assert isinstance(data["product_progress"], list)
    assert isinstance(data["blockers"], list)
    assert isinstance(data["m6_16_polish_candidates"], list)
    required_row = {"id", "label", "outcome", "failure_class", "evidence", "rescue_edits"}
    for row in data["dogfood_rows"]:
        assert required_row <= set(row)
        assert isinstance(row["rescue_edits"], int)
        assert row["rescue_edits"] == 0
        assert "rescue_edit" not in row
        assert row["outcome"] != "rescued"
        assert "live" not in row.get("fixture_source", "static")
    required_issue = {"number", "title", "url", "status", "summary"}
    assert {issue["number"] for issue in data["side_pj_issues"]} == {4, 5}
    for issue in data["side_pj_issues"]:
        assert required_issue <= set(issue)
        assert "[side-pj]" in issue["title"]
        assert issue["url"].startswith("https://github.com/mkXultra/mew/issues/")


def test_cli_bundle_missing_fixture_error_is_deterministic(tmp_path: Path) -> None:
    missing_manifest = tmp_path / "missing_bundle.json"
    missing_manifest.write_text(
        json.dumps(
            {
                "id": "missing-bundle",
                "entries": [
                    {
                        "label": "Missing report",
                        "fixture": "does-not-exist.json",
                        "mode": "report",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(missing_manifest), "--mode", "bundle"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert result.stdout == ""
    assert "error: fixture not found:" in result.stderr
    assert "does-not-exist.json" in result.stderr


def test_bundle_fixture_is_valid_json_object() -> None:
    data = json.loads(BUNDLE_FIXTURE.read_text(encoding="utf-8"))

    assert data["id"] == "sp7-sample-bundle"
    assert isinstance(data["entries"], list)
    assert [entry["label"] for entry in data["entries"]] == [
        "Morning journal",
        "Research digest",
        "State brief",
    ]
    assert {entry["fixture"] for entry in data["entries"]} == {
        "sample_session.json",
        "sample_mew_state.json",
    }
