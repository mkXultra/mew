from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("watch_browser_pet.py")
if str(MODULE_PATH.parent) not in sys.path:
    sys.path.insert(0, str(MODULE_PATH.parent))
SPEC = importlib.util.spec_from_file_location("watch_browser_pet", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
watch_browser_pet = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = watch_browser_pet
SPEC.loader.exec_module(watch_browser_pet)


def test_render_once_writes_html_with_refresh(tmp_path: Path) -> None:
    source_path = tmp_path / "desk.json"
    output = tmp_path / "desk.html"
    source_path.write_text(json.dumps({"pet_state": "typing", "focus": "Working", "counts": {}}), encoding="utf-8")

    result = watch_browser_pet.render_once(watch_browser_pet.FileViewModelSource(source_path), output, 7)

    assert result.wrote is True
    text = output.read_text(encoding="utf-8")
    assert '<meta http-equiv="refresh" content="7">' in text
    assert "Working" in text


def test_write_if_changed_skips_identical_content(tmp_path: Path) -> None:
    output = tmp_path / "desk.html"

    first = watch_browser_pet.write_if_changed(output, "same")
    second = watch_browser_pet.write_if_changed(output, "same")
    third = watch_browser_pet.write_if_changed(output, "different")

    assert first is True
    assert second is False
    assert third is True
    assert output.read_text(encoding="utf-8") == "different"


def test_render_once_reports_bad_json_without_raising(tmp_path: Path) -> None:
    source_path = tmp_path / "desk.json"
    output = tmp_path / "desk.html"
    source_path.write_text("{bad json", encoding="utf-8")

    result = watch_browser_pet.render_once(watch_browser_pet.FileViewModelSource(source_path), output, 5)

    assert result.wrote is False
    assert "JSONDecodeError" in result.error
    assert not output.exists()


def test_watch_runs_bounded_iterations(tmp_path: Path) -> None:
    source_path = tmp_path / "desk.json"
    output = tmp_path / "desk.html"
    source_path.write_text(json.dumps({"pet_state": "sleeping", "counts": {}}), encoding="utf-8")
    sleeps: list[float] = []

    watch_browser_pet.watch(
        watch_browser_pet.FileViewModelSource(source_path),
        output,
        interval_seconds=3,
        refresh_seconds=3,
        sleep=sleeps.append,
        iterations=2,
    )

    assert output.exists()
    assert sleeps == [3]
