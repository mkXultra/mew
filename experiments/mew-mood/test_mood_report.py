from __future__ import annotations

import importlib.util
import io
import sys
from contextlib import redirect_stdout
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("mood_report.py")
SPEC = importlib.util.spec_from_file_location("mood_report", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
mood_report = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = mood_report
SPEC.loader.exec_module(mood_report)


def test_generate_writes_mood_report_with_scores_and_signals(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    state_path.write_text(
        '{"date":"2026-04-17",'
        '"tasks":['
        '{"id":1,"title":"Open work","status":"ready"},'
        '{"id":2,"title":"Done A","status":"done"},'
        '{"id":3,"title":"Done B","status":"done"}'
        '],'
        '"outbox":[{"id":4,"question_id":2,"requires_reply":true,"text":"What next?"}],'
        '"work_sessions":[{"id":5,"status":"active","goal":"Continue work","phase":"idle"}],'
        '"verification_runs":[{"id":1,"exit_code":0}],'
        '"runtime_effects":[{"id":6,"reason":"passive_tick","status":"applied"}]}'
    )

    paths = mood_report.generate(state_path, tmp_path)
    text = paths.mood.read_text()

    assert paths.mood == tmp_path / ".mew" / "mood" / "2026-04-17.md"
    assert "# Mew Mood 2026-04-17" in text
    assert "Current mood: **steady**" in text
    assert "### Energy" in text
    assert "- score: 54" in text
    assert "- 2 recent done task(s) add momentum" in text
    assert "- 1 unanswered question(s) reduce free energy" in text
    assert "- open task: #1 Open work [ready]" in text
    assert "- open question #2: What next?" in text
    assert "- runtime effect #6: applied/passive_tick" in text


def test_productive_but_watchful_when_joy_and_worry_are_both_high(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    done_tasks = ",".join(f'{{"id":{i},"title":"Done {i}","status":"done"}}' for i in range(1, 9))
    questions = ",".join(
        f'{{"id":{i},"question_id":{i},"requires_reply":true,"text":"Question {i}"}}' for i in range(1, 5)
    )
    attention = ",".join(f'{{"id":{i},"status":"open","title":"Attention {i}"}}' for i in range(1, 4))
    verifications = ",".join(f'{{"id":{i},"exit_code":0}}' for i in range(1, 9))
    state_path.write_text(
        '{"date":"2026-04-17",'
        f'"tasks":[{done_tasks}],'
        f'"outbox":[{questions}],'
        f'"attention":{{"items":[{attention}]}},'
        f'"verification_runs":[{verifications}]'
        '}'
    )

    paths = mood_report.generate(state_path, tmp_path)
    text = paths.mood.read_text()

    assert "Current mood: **productive but watchful**" in text
    assert "### Worry\n- score: 74" in text
    assert "### Joy\n- score: 65" in text


def test_failed_verifications_raise_worry_to_concerned(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    state_path.write_text(
        '{"date":"2026-04-17",'
        '"verification_runs":[{"id":1,"exit_code":1},{"id":2,"exit_code":2},{"id":3,"exit_code":1}]}'
    )

    paths = mood_report.generate(state_path, tmp_path)
    text = paths.mood.read_text()

    assert "Current mood: **concerned**" in text
    assert "### Worry\n- score: 60" in text
    assert "- 3 recent failed verification(s) detected" in text


def test_empty_state_renders_fallbacks(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    state_path.write_text('{"date":"2026-04-17"}')

    paths = mood_report.generate(state_path, tmp_path)
    text = paths.mood.read_text()

    assert "Current mood: **steady**" in text
    assert "- No strong energy signals found" in text
    assert "- No strong worry signals found" in text
    assert "- No strong joy signals found" in text
    assert "- No active signals recorded" in text


def test_explicit_date_override_wins_over_state_date(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    state_path.write_text('{"date":"2026-04-17"}')

    paths = mood_report.generate(state_path, tmp_path, explicit_date="2026-04-18")

    assert paths.mood.name == "2026-04-18.md"
    assert "# Mew Mood 2026-04-18" in paths.mood.read_text()


def test_main_prints_created_path(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    state_path.write_text('{"date":"2026-04-17"}')

    stdout = io.StringIO()
    with redirect_stdout(stdout):
        exit_code = mood_report.main([str(state_path), "--output-dir", str(tmp_path)])

    assert exit_code == 0
    assert stdout.getvalue().strip() == str(tmp_path / ".mew" / "mood" / "2026-04-17.md")
