from __future__ import annotations

import importlib.util
import io
import sys
from contextlib import redirect_stdout
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("journal_report.py")
SPEC = importlib.util.spec_from_file_location("journal_report", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
journal_report = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = journal_report
SPEC.loader.exec_module(journal_report)


def test_generate_writes_morning_and_evening_journal(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    state_path.write_text(
        '{"date":"2026-04-17",'
        '"tasks":['
        '{"id":1,"title":"Ship journal","status":"ready","priority":"high","kind":"coding"},'
        '{"id":2,"title":"Done work","status":"done","notes":"Created\\n2026-04-17T12:00:00Z done: Verified journal output."}'
        '],'
        '"outbox":[{"id":9,"question_id":3,"related_task_id":1,"requires_reply":true,"text":"Should I continue?"}],'
        '"work_sessions":[{"id":4,"task_id":1,"status":"active","goal":"Build journal","phase":"idle","next_action":"write tests"}],'
        '"runtime_effects":[{"id":7,"reason":"passive_tick","status":"applied","action_types":["update_memory"],"summary":"Noted quiet passive progress."}]}'
    )

    paths = journal_report.generate(state_path, tmp_path)
    text = paths.journal.read_text()

    assert paths.journal == tmp_path / ".mew" / "journal" / "2026-04-17.md"
    assert "# Mew Journal 2026-04-17" in text
    assert "## Morning" in text
    assert "## Evening" in text
    assert "- #2 Done work [done]: Verified journal output." in text
    assert "- #1 Ship journal [ready/coding]" in text
    assert "Question #3 for task #1: Should I continue?" in text
    assert "Work session #4 task #1: Ship journal is idle: Build journal; next: write tests" in text
    assert "effect #7 [applied/passive_tick] actions=update_memory: Noted quiet passive progress." in text


def test_active_tasks_are_ranked_by_status_then_priority(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    state_path.write_text(
        '{"date":"2026-04-17",'
        '"tasks":['
        '{"id":1,"title":"Low todo","status":"todo","priority":"low"},'
        '{"id":2,"title":"Running normal","status":"running","priority":"normal"},'
        '{"id":3,"title":"Ready high","status":"ready","priority":"high"}'
        ']}'
    )

    paths = journal_report.generate(state_path, tmp_path)
    text = paths.journal.read_text()
    today = text.split("### Today", 1)[1].split("### Mew note", 1)[0]

    assert today.index("#2 Running normal") < today.index("#3 Ready high")
    assert today.index("#3 Ready high") < today.index("#1 Low todo")


def test_empty_state_renders_fallbacks(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    state_path.write_text('{"date":"2026-04-17"}')

    paths = journal_report.generate(state_path, tmp_path)
    text = paths.journal.read_text()

    assert "- No completed work or runtime effects recorded" in text
    assert "- No active tasks recorded" in text
    assert "- No stuck points recorded" in text
    assert "- Pick one small task and make it ready" in text


def test_explicit_date_override_wins_over_state_date(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    state_path.write_text('{"date":"2026-04-17","tasks":[]}')

    paths = journal_report.generate(state_path, tmp_path, explicit_date="2026-04-18")

    assert paths.journal.name == "2026-04-18.md"
    assert "# Mew Journal 2026-04-18" in paths.journal.read_text()


def test_main_prints_created_path(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    state_path.write_text('{"date":"2026-04-17","tasks":[]}')

    stdout = io.StringIO()
    with redirect_stdout(stdout):
        exit_code = journal_report.main([str(state_path), "--output-dir", str(tmp_path)])

    assert exit_code == 0
    assert stdout.getvalue().strip() == str(tmp_path / ".mew" / "journal" / "2026-04-17.md")
