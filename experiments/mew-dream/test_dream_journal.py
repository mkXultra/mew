from __future__ import annotations

import importlib.util
import io
import sys
from contextlib import redirect_stdout
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("dream_journal.py")
SPEC = importlib.util.spec_from_file_location("dream_journal", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
dream_journal = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = dream_journal
SPEC.loader.exec_module(dream_journal)


def test_generate_writes_dream_and_journal(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    state_path.write_text(
        '{"date":"2026-04-17","tasks":[{"title":"Prototype","status":"in_progress"}],"notes":["Keep it local-first."]}'
    )

    paths = dream_journal.generate(state_path, tmp_path)

    assert paths.dream == tmp_path / ".mew" / "dreams" / "2026-04-17.md"
    assert paths.journal == tmp_path / ".mew" / "journal" / "2026-04-17.md"
    assert "# Dream 2026-04-17" in paths.dream.read_text()
    assert "- Prototype [in_progress]" in paths.dream.read_text()
    assert "## Learnings" in paths.dream.read_text()
    assert "- No learnings recorded" in paths.dream.read_text()
    assert "# Journal 2026-04-17" in paths.journal.read_text()
    assert "- Keep it local-first." in paths.journal.read_text()


def test_main_prints_created_paths(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    state_path.write_text('{"date":"2026-04-17","tasks":[],"notes":[]}')

    stdout = io.StringIO()
    with redirect_stdout(stdout):
        exit_code = dream_journal.main([str(state_path), "--output-dir", str(tmp_path)])

    lines = stdout.getvalue().strip().splitlines()
    assert exit_code == 0
    assert lines == [
        str(tmp_path / ".mew" / "dreams" / "2026-04-17.md"),
        str(tmp_path / ".mew" / "journal" / "2026-04-17.md"),
    ]


def test_explicit_date_override_wins_over_state_date(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    state_path.write_text('{"date":"2026-04-17","tasks":[],"notes":[]}')

    paths = dream_journal.generate(state_path, tmp_path, explicit_date="2026-04-18")

    assert paths.dream.name == "2026-04-18.md"
    assert paths.journal.name == "2026-04-18.md"
    assert "2026-04-18" in paths.dream.read_text()
    assert "2026-04-18" in paths.journal.read_text()


def test_dream_renders_learnings_changes_and_decisions(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    state_json = (
        '{"date":"2026-04-17",'
        '"tasks":[{"title":"Prototype","status":"done"}],'
        '"learnings":["Mew needs cross-task memory."],'
        '"changes":[{"summary":"Added dream markdown output."}],'
        '"decisions":[{"title":"Keep the prototype isolated."}],'
        '"notes":[]}'
    )
    state_path.write_text(state_json)

    paths = dream_journal.generate(state_path, tmp_path)
    dream = paths.dream.read_text()

    assert "## Learnings" in dream
    assert "- Mew needs cross-task memory." in dream
    assert "- Added dream markdown output." in dream
    assert "- Keep the prototype isolated." in dream


def test_dream_derives_recent_learnings_from_done_task_notes(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    state_path.write_text(
        '{"date":"2026-04-17",'
        '"tasks":['
        '{"title":"Open work","status":"ready"},'
        '{"title":"Old work","status":"done","notes":"Created\\n2026-04-17T12:00:00Z done: Verified dream output."}'
        '],'
        '"notes":[]}'
    )

    paths = dream_journal.generate(state_path, tmp_path)
    dream = paths.dream.read_text()

    assert "- Open work [ready]" in dream
    assert "- Old work [done]" not in dream
    assert "- Verified dream output." in dream
