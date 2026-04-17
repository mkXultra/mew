from __future__ import annotations

import importlib.util
import io
import sys
from contextlib import redirect_stdout
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("self_memory.py")
SPEC = importlib.util.spec_from_file_location("self_memory", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
self_memory = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = self_memory
SPEC.loader.exec_module(self_memory)


def test_generate_writes_self_memory_report(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    state_path.write_text(
        '{"date":"2026-04-17",'
        '"traits":["I prefer small verified steps."],'
        '"learnings":["Cross-task memory matters."],'
        '"changes":[{"summary":"Added a self-memory report."}],'
        '"decisions":[{"title":"Keep the prototype isolated."}],'
        '"tasks":[]}'
    )

    paths = self_memory.generate(state_path, tmp_path)
    text = paths.self_memory.read_text()

    assert paths.self_memory == tmp_path / ".mew" / "self" / "learned-2026-04-17.md"
    assert "# Mew Self Memory 2026-04-17" in text
    assert "- I prefer small verified steps." in text
    assert "- Cross-task memory matters." in text
    assert "- Added a self-memory report." in text
    assert "- Keep the prototype isolated." in text


def test_done_task_notes_feed_recent_self_learnings(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    state_path.write_text(
        '{"date":"2026-04-17",'
        '"tasks":['
        '{"title":"Ignore todo","status":"todo","notes":"not durable"},'
        '{"title":"Done","status":"done","notes":"Created\\n2026-04-17T12:00:00Z done: I should preserve verification evidence."}'
        ']}'
    )

    paths = self_memory.generate(state_path, tmp_path)
    text = paths.self_memory.read_text()

    assert "- I should preserve verification evidence." in text
    assert "not durable" not in text


def test_active_work_sessions_feed_continuity_cues(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    state_path.write_text(
        '{"date":"2026-04-17",'
        '"tasks":[{"id":3,"title":"Continue shell work","status":"ready"}],'
        '"work_sessions":[{'
        '"id":9,'
        '"task_id":3,'
        '"status":"active",'
        '"goal":"Recover resident context",'
        '"phase":"idle",'
        '"next_action":"resume with mew code 3"'
        '}]}'
    )

    paths = self_memory.generate(state_path, tmp_path)
    text = paths.self_memory.read_text()

    assert "## Continuity cues" in text
    assert "- Work session #9 task #3: Continue shell work is idle: Recover resident context; next: resume with mew code 3" in text


def test_repeated_learnings_are_deduplicated(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    state_path.write_text(
        '{"date":"2026-04-17",'
        '"learnings":["Repeat this."],'
        '"changes":["repeat this."],'
        '"tasks":[{"status":"done","notes":"2026-04-17T12:00:00Z done: Repeat this."}]}'
    )

    paths = self_memory.generate(state_path, tmp_path)
    text = paths.self_memory.read_text()

    assert text.count("Repeat this.") == 1


def test_empty_state_renders_fallbacks(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    state_path.write_text('{"date":"2026-04-17"}')

    paths = self_memory.generate(state_path, tmp_path)
    text = paths.self_memory.read_text()

    assert "- No durable traits recorded" in text
    assert "- No self learnings recorded" in text
    assert "- No active continuity cues" in text


def test_main_prints_created_path(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    state_path.write_text('{"date":"2026-04-17"}')

    stdout = io.StringIO()
    with redirect_stdout(stdout):
        exit_code = self_memory.main([str(state_path), "--output-dir", str(tmp_path)])

    assert exit_code == 0
    assert stdout.getvalue().strip() == str(tmp_path / ".mew" / "self" / "learned-2026-04-17.md")
