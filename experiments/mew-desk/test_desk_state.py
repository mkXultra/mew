from __future__ import annotations

import importlib.util
import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("desk_state.py")
SPEC = importlib.util.spec_from_file_location("desk_state", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
desk_state = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = desk_state
SPEC.loader.exec_module(desk_state)


def test_generate_alerting_view_model_for_open_question(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    state_path.write_text(
        '{"date":"2026-04-17",'
        '"tasks":[{"id":1,"title":"Build desk","status":"ready"}],'
        '"outbox":[{"id":2,"question_id":3,"requires_reply":true,"text":"Need input?"}]}'
    )

    paths = desk_state.generate(state_path, tmp_path)
    data = json.loads(paths.json_path.read_text())
    markdown = paths.markdown_path.read_text()

    assert paths.json_path == tmp_path / ".mew" / "desk" / "2026-04-17.json"
    assert data["pet_state"] == "alerting"
    assert data["counts"]["open_questions"] == 1
    assert data["focus"] == "Waiting for reply: Need input?"
    assert "- pet_state: alerting" in markdown


def test_runtime_planning_maps_to_thinking(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    state_path.write_text(
        '{"date":"2026-04-17","runtime_status":{"state":"running","current_phase":"planning"}}'
    )

    paths = desk_state.generate(state_path, tmp_path)
    data = json.loads(paths.json_path.read_text())

    assert data["pet_state"] == "thinking"


def test_active_work_session_maps_to_typing(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    state_path.write_text(
        '{"date":"2026-04-17",'
        '"work_sessions":[{"id":1,"status":"active","goal":"Continue implementation"}]}'
    )

    paths = desk_state.generate(state_path, tmp_path)
    data = json.loads(paths.json_path.read_text())

    assert data["pet_state"] == "typing"
    assert data["focus"] == "Working on: Continue implementation"


def test_empty_state_maps_to_sleeping(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    state_path.write_text('{"date":"2026-04-17"}')

    paths = desk_state.generate(state_path, tmp_path)
    data = json.loads(paths.json_path.read_text())

    assert data["pet_state"] == "sleeping"
    assert data["focus"] == "No active work recorded"


def test_main_prints_created_paths(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    state_path.write_text('{"date":"2026-04-17"}')

    stdout = io.StringIO()
    with redirect_stdout(stdout):
        exit_code = desk_state.main([str(state_path), "--output-dir", str(tmp_path)])

    assert exit_code == 0
    assert stdout.getvalue().strip().splitlines() == [
        str(tmp_path / ".mew" / "desk" / "2026-04-17.json"),
        str(tmp_path / ".mew" / "desk" / "2026-04-17.md"),
    ]
