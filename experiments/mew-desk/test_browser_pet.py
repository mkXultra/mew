from __future__ import annotations

import importlib.util
import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("browser_pet.py")
SPEC = importlib.util.spec_from_file_location("browser_pet", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
browser_pet = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = browser_pet
SPEC.loader.exec_module(browser_pet)


def test_render_browser_pet_for_alerting_state() -> None:
    html = browser_pet.render_browser_pet(
        {
            "date": "2026-04-19",
            "pet_state": "alerting",
            "focus": "Waiting for reply",
            "counts": {
                "open_tasks": 2,
                "open_questions": 1,
                "active_work_sessions": 0,
                "open_attention": 3,
            },
        }
    )

    assert '<main data-state="alerting">' in html
    assert "( O.O )" in html
    assert "Needs input" in html
    assert "<strong>2</strong>" in html
    assert "<strong>3</strong>" in html


def test_unknown_state_falls_back_to_sleeping() -> None:
    html = browser_pet.render_browser_pet({"pet_state": "confused", "counts": {}})

    assert '<main data-state="sleeping">' in html
    assert "Quiet" in html


def test_focus_and_date_are_escaped() -> None:
    html = browser_pet.render_browser_pet(
        {
            "date": '<script>alert("date")</script>',
            "pet_state": "typing",
            "focus": '<script>alert("focus")</script>',
            "counts": {},
        }
    )

    assert '<script>alert("focus")</script>' not in html
    assert '<script>alert("date")</script>' not in html
    assert "&lt;script&gt;alert(&quot;focus&quot;)&lt;/script&gt;" in html
    assert "&lt;script&gt;alert(&quot;date&quot;)&lt;/script&gt;" in html


def test_long_focus_is_compacted_for_browser_output() -> None:
    html = browser_pet.render_browser_pet({"pet_state": "thinking", "focus": "A" * 240, "counts": {}})

    focus_line = next(line.strip() for line in html.splitlines() if line.strip().startswith('<p class="focus">'))
    rendered_focus = focus_line.removeprefix('<p class="focus">').removesuffix("</p>")
    assert rendered_focus.endswith("...")
    assert len(rendered_focus) == browser_pet.MAX_FOCUS_LENGTH


def test_main_reads_stdin_and_writes_file(tmp_path: Path) -> None:
    output = tmp_path / "desk.html"
    view_model = {"pet_state": "typing", "focus": "Working on browser shell", "counts": {"open_tasks": 1}}

    exit_code = browser_pet.main(
        ["-", "--output", str(output)],
        stdin=io.StringIO(json.dumps(view_model)),
    )

    assert exit_code == 0
    assert output.exists()
    assert "Working on browser shell" in output.read_text(encoding="utf-8")
    assert "http-equiv" not in output.read_text(encoding="utf-8")


def test_main_can_add_refresh_meta(tmp_path: Path) -> None:
    output = tmp_path / "desk.html"
    view_model = {"pet_state": "typing", "focus": "Working on browser shell", "counts": {"open_tasks": 1}}

    exit_code = browser_pet.main(
        ["-", "--output", str(output), "--refresh-seconds", "11"],
        stdin=io.StringIO(json.dumps(view_model)),
    )

    assert exit_code == 0
    assert '<meta http-equiv="refresh" content="11">' in output.read_text(encoding="utf-8")


def test_main_prints_html_to_stdout(tmp_path: Path) -> None:
    path = tmp_path / "desk.json"
    path.write_text(json.dumps({"pet_state": "sleeping", "counts": {}}), encoding="utf-8")

    stdout = io.StringIO()
    with redirect_stdout(stdout):
        exit_code = browser_pet.main([str(path)])

    assert exit_code == 0
    assert "<!doctype html>" in stdout.getvalue()
