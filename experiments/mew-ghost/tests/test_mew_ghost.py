from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README_PATH = ROOT / "README.md"
GHOST_PATH = ROOT / "ghost.py"
FIXTURE_PATH = ROOT / "fixtures" / "sample_ghost_state.json"

spec = importlib.util.spec_from_file_location("mew_ghost_sp12", GHOST_PATH)
ghost = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(ghost)


def test_fixture_builds_deterministic_state_and_html() -> None:
    fixture = ghost.load_fixture(FIXTURE_PATH)

    state_one = ghost.build_ghost_state(fixture)
    state_two = ghost.build_ghost_state(fixture)
    html_one = ghost.render_local_html(state_one)
    html_two = ghost.render_local_html(state_two)

    assert state_one == state_two
    assert html_one == html_two
    assert state_one["schema_version"] == "mew-ghost.sp12.v1"
    assert state_one["active_window"]["status"] == "available"
    assert state_one["active_window"]["active_app"] == "Visual Studio Code"
    assert "Ghost is watching VS Code without screen capture." in html_one
    assert "Writing the SP12 scaffold" in html_one
    assert "mew-ghost.sp12.v1" in html_one


def test_probe_contract_is_safe_without_accessibility_or_live_api() -> None:
    calls: list[str] = []

    def provider() -> dict[str, str]:
        calls.append("called")
        return {"active_app": "Should Not Be Called"}

    unavailable = ghost.probe_active_window(provider, platform_name="Linux")

    assert calls == []
    assert unavailable == {
        "schema_version": "mew-ghost.sp12.v1",
        "status": "unavailable",
        "reason": "requires_macos",
        "platform": "Linux",
        "active_app": None,
        "window_title": None,
        "requires_permission": False,
    }

    deferred = ghost.probe_active_window(platform_name="Darwin")
    assert deferred["status"] == "unavailable"
    assert deferred["reason"] == "sp12_live_probe_deferred"
    assert deferred["requires_permission"] is True


def test_probe_contract_reports_permission_denied_structurally() -> None:
    def denied_provider() -> dict[str, str]:
        raise PermissionError("Accessibility denied")

    denied = ghost.probe_active_window(denied_provider, platform_name="Darwin")

    assert denied["status"] == "permission_denied"
    assert denied["reason"] == "accessibility_permission_denied"
    assert denied["active_app"] is None
    assert denied["window_title"] is None
    assert denied["requires_permission"] is True


def test_probe_contract_accepts_injected_success_provider() -> None:
    observed = ghost.probe_active_window(
        lambda: {
            "active_app": "Terminal",
            "window_title": "mew work 12",
            "requires_permission": True,
        },
        platform_name="Darwin",
    )

    assert observed["status"] == "available"
    assert observed["reason"] is None
    assert observed["active_app"] == "Terminal"
    assert observed["window_title"] == "mew work 12"


def test_launcher_intents_are_dry_run_chat_and_code_only() -> None:
    intents = ghost.build_launcher_intents()

    assert [intent["id"] for intent in intents] == ["mew-chat", "mew-code"]
    assert [intent["command"] for intent in intents] == [["mew", "chat"], ["mew", "code"]]
    assert all(intent["dry_run"] is True for intent in intents)
    assert all(intent["side_effects"] == "none" for intent in intents)


def test_cli_writes_local_html_and_state_from_fixture(tmp_path: Path) -> None:
    html_output = tmp_path / "ghost.html"
    state_output = tmp_path / "ghost-state.json"

    assert ghost.main(["--fixture", str(FIXTURE_PATH), "--output", str(html_output)]) == 0
    assert ghost.main([
        "--fixture",
        str(FIXTURE_PATH),
        "--format",
        "state",
        "--output",
        str(state_output),
    ]) == 0

    html = html_output.read_text(encoding="utf-8")
    state = json.loads(state_output.read_text(encoding="utf-8"))

    assert html.startswith("<!doctype html>")
    assert "<title>mew-ghost SP12 shell</title>" in html
    assert state["fixture_name"] == "sample_ghost_state"
    assert state["launch_intents"][0]["command"] == ["mew", "chat"]


def test_readme_usage_prefers_uv_run_python_commands() -> None:
    readme = README_PATH.read_text(encoding="utf-8")
    usage_lines = [
        line.strip()
        for line in readme.splitlines()
        if "experiments/mew-ghost/ghost.py" in line
    ]

    assert usage_lines == [
        "UV_CACHE_DIR=.uv-cache uv run python experiments/mew-ghost/ghost.py --output /tmp/mew-ghost.html",
        "UV_CACHE_DIR=.uv-cache uv run python experiments/mew-ghost/ghost.py --format state",
    ]
    assert all(not line.startswith("python experiments/mew-ghost/ghost.py") for line in usage_lines)


def test_source_stays_isolated_from_core_mew_and_live_state() -> None:
    source = GHOST_PATH.read_text(encoding="utf-8")

    assert "import mew" not in source
    assert "src/mew" not in source
    assert "src.mew" not in source
    assert "Path(\".mew\")" not in source
    assert "screen capture" in source
