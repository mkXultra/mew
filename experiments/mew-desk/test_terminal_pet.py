from __future__ import annotations

import importlib.util
import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("terminal_pet.py")
SPEC = importlib.util.spec_from_file_location("terminal_pet", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
terminal_pet = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = terminal_pet
SPEC.loader.exec_module(terminal_pet)


def test_render_terminal_pet_for_alerting_state() -> None:
    text = terminal_pet.render_terminal_pet(
        {
            "pet_state": "alerting",
            "focus": "Waiting for reply: Need input?",
            "counts": {
                "open_tasks": 2,
                "open_questions": 1,
                "active_work_sessions": 0,
                "open_attention": 3,
            },
        }
    )

    assert "mew desk :: alerting" in text
    assert "( O.O )" in text
    assert "focus: Waiting for reply: Need input?" in text
    assert "tasks=2 questions=1 sessions=0 attention=3" in text


def test_unknown_state_falls_back_to_sleeping() -> None:
    text = terminal_pet.render_terminal_pet({"pet_state": "confused", "counts": {}})

    assert "mew desk :: sleeping" in text
    assert "( -.- )" in text


def test_load_view_model_from_stdin() -> None:
    model = terminal_pet.load_view_model(
        None,
        stdin=io.StringIO('{"pet_state":"thinking","focus":"Read roadmap","counts":{}}'),
    )

    assert model["pet_state"] == "thinking"


def test_main_reads_file_and_prints_terminal_pet(tmp_path: Path) -> None:
    path = tmp_path / "desk.json"
    path.write_text(
        json.dumps(
            {
                "pet_state": "typing",
                "focus": "Working on: terminal pet",
                "counts": {"open_tasks": 1, "open_questions": 0, "active_work_sessions": 1},
            }
        )
    )

    stdout = io.StringIO()
    with redirect_stdout(stdout):
        exit_code = terminal_pet.main([str(path)])

    assert exit_code == 0
    assert "mew desk :: typing" in stdout.getvalue()
    assert "Working on: terminal pet" in stdout.getvalue()
