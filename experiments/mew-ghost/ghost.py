#!/usr/bin/env python3
"""Standalone SP13 mew-ghost shell scaffold.

The module is deliberately local and fixture-driven by default. It can perform
an explicit opt-in macOS active app/window probe through osascript, renders a
deterministic local HTML shell, exposes dry-run command intents, and uses no
screen capture or hidden monitoring.
"""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
import sys
from html import escape
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

SCHEMA_VERSION = "mew-ghost.sp13.v1"
DEFAULT_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "sample_ghost_state.json"
ProbeProvider = Callable[[], Mapping[str, Any]]
OsascriptRunner = Callable[..., subprocess.CompletedProcess[str]]
WhichProvider = Callable[[str], str | None]
OSASCRIPT_TIMEOUT_SECONDS = 2.0
ACTIVE_WINDOW_OSASCRIPT = "\n".join(
    [
        'tell application "System Events"',
        "  set frontApp to first application process whose frontmost is true",
        "  set appName to name of frontApp",
        "  set windowTitle to \"\"",
        "  try",
        "    set windowTitle to name of front window of frontApp",
        "  end try",
        "  return appName & (ASCII character 9) & windowTitle",
        "end tell",
    ]
)


def load_fixture(path: str | Path = DEFAULT_FIXTURE) -> dict[str, Any]:
    """Load an explicit local fixture file."""
    fixture_path = Path(path)
    with fixture_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("ghost fixture must be a JSON object")
    return data


def _probe_result(
    *,
    status: str,
    reason: str | None,
    platform_name: str,
    active_app: str | None = None,
    window_title: str | None = None,
    requires_permission: bool = False,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "reason": reason,
        "platform": platform_name or "unknown",
        "active_app": active_app,
        "window_title": window_title,
        "requires_permission": requires_permission,
    }


def normalize_probe_fixture(raw_probe: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize a fixture-provided probe snapshot into the public contract."""
    status = str(raw_probe.get("status") or "unavailable")
    reason = raw_probe.get("reason")
    active_app = raw_probe.get("active_app")
    window_title = raw_probe.get("window_title")
    return _probe_result(
        status=status,
        reason=str(reason) if reason is not None else None,
        platform_name=str(raw_probe.get("platform") or "fixture"),
        active_app=str(active_app) if active_app else None,
        window_title=str(window_title) if window_title else None,
        requires_permission=bool(raw_probe.get("requires_permission", False)),
    )


def _looks_like_permission_denied(message: str) -> bool:
    text = message.lower()
    return any(
        marker in text
        for marker in (
            "accessibility",
            "assistive access",
            "not authorized",
            "not allowed",
            "operation not permitted",
        )
    )


def _parse_osascript_probe_output(output: str) -> dict[str, Any]:
    """Parse the tab-delimited output emitted by ACTIVE_WINDOW_OSASCRIPT."""
    if not output.strip():
        return {}

    payload = output.strip("\r\n")
    parts = payload.split("\t")
    if len(parts) != 2:
        raise ValueError("osascript probe returned malformed output")

    active_app = parts[0].strip()
    window_title = parts[1].strip()
    if not active_app and not window_title:
        return {}
    return {
        "active_app": active_app,
        "window_title": window_title,
        "requires_permission": True,
    }


def _run_osascript_active_window(
    *,
    runner: OsascriptRunner = subprocess.run,
    osascript_path: str | None = None,
    which: WhichProvider | None = None,
    timeout_seconds: float = OSASCRIPT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    resolver = which if which is not None else shutil.which
    resolved_path = osascript_path or resolver("osascript")
    if not resolved_path:
        raise FileNotFoundError("osascript")

    completed = runner(
        [resolved_path, "-e", ACTIVE_WINDOW_OSASCRIPT],
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout_seconds,
    )
    stdout = str(getattr(completed, "stdout", "") or "")
    stderr = str(getattr(completed, "stderr", "") or "")
    returncode = int(getattr(completed, "returncode", 0) or 0)
    if returncode != 0:
        if _looks_like_permission_denied(stderr):
            raise PermissionError(stderr or "Accessibility permission denied")
        raise OSError(stderr or f"osascript exited with {returncode}")
    return _parse_osascript_probe_output(stdout)


def make_macos_osascript_probe_provider(
    *,
    runner: OsascriptRunner = subprocess.run,
    osascript_path: str | None = None,
    which: WhichProvider | None = None,
    timeout_seconds: float = OSASCRIPT_TIMEOUT_SECONDS,
) -> ProbeProvider:
    """Build an injectable provider for the explicit live macOS probe path."""

    def provider() -> Mapping[str, Any]:
        return _run_osascript_active_window(
            runner=runner,
            osascript_path=osascript_path,
            which=which,
            timeout_seconds=timeout_seconds,
        )

    return provider


def probe_active_window(
    provider: ProbeProvider | None = None,
    *,
    platform_name: str | None = None,
) -> dict[str, Any]:
    """Return a permission-safe active app/window probe result.

    Default behavior never performs a live probe. The osascript provider is used
    only when a caller explicitly opts in, and tests can inject providers or
    runners without requiring Accessibility permission or live macOS state.
    """
    system_name = platform_name if platform_name is not None else platform.system()
    if system_name != "Darwin":
        return _probe_result(
            status="unavailable",
            reason="requires_macos",
            platform_name=system_name,
            requires_permission=False,
        )

    if provider is None:
        return _probe_result(
            status="unavailable",
            reason="live_probe_not_requested",
            platform_name=system_name,
            requires_permission=True,
        )

    try:
        raw = provider()
    except FileNotFoundError:
        return _probe_result(
            status="unavailable",
            reason="missing_osascript",
            platform_name=system_name,
            requires_permission=True,
        )
    except PermissionError:
        return _probe_result(
            status="permission_denied",
            reason="accessibility_permission_denied",
            platform_name=system_name,
            requires_permission=True,
        )
    except subprocess.TimeoutExpired:
        return _probe_result(
            status="unavailable",
            reason="osascript_timeout",
            platform_name=system_name,
            requires_permission=True,
        )
    except ValueError:
        return _probe_result(
            status="unavailable",
            reason="malformed_probe_result",
            platform_name=system_name,
            requires_permission=True,
        )
    except OSError:
        return _probe_result(
            status="unavailable",
            reason="probe_unavailable",
            platform_name=system_name,
            requires_permission=True,
        )

    active_app = str(raw.get("active_app") or "").strip() or None
    window_title = str(raw.get("window_title") or "").strip() or None
    if not active_app and not window_title:
        return _probe_result(
            status="unavailable",
            reason="empty_probe_result",
            platform_name=system_name,
            requires_permission=bool(raw.get("requires_permission", True)),
        )

    return _probe_result(
        status="available",
        reason=None,
        platform_name=system_name,
        active_app=active_app,
        window_title=window_title,
        requires_permission=bool(raw.get("requires_permission", True)),
    )


def build_launcher_intents(*, dry_run: bool = True) -> list[dict[str, Any]]:
    """Return dry-run launcher intents for the two SP13 command surfaces."""
    return [
        {
            "id": "mew-chat",
            "label": "Open mew chat",
            "command": ["mew", "chat"],
            "dry_run": dry_run,
            "side_effects": "none",
            "description": "Would open the chat surface for the operator.",
        },
        {
            "id": "mew-code",
            "label": "Open mew code",
            "command": ["mew", "code"],
            "dry_run": dry_run,
            "side_effects": "none",
            "description": "Would open the coding surface for the operator.",
        },
    ]


def build_ghost_state(
    fixture: Mapping[str, Any],
    *,
    probe_provider: ProbeProvider | None = None,
    platform_name: str | None = None,
) -> dict[str, Any]:
    """Build deterministic ghost state from a fixture plus optional probe."""
    ghost = fixture.get("ghost")
    if not isinstance(ghost, Mapping):
        raise ValueError("ghost fixture requires a 'ghost' object")

    if probe_provider is None and isinstance(fixture.get("probe"), Mapping):
        probe = normalize_probe_fixture(fixture["probe"])
    else:
        probe = probe_active_window(probe_provider, platform_name=platform_name)

    return {
        "schema_version": SCHEMA_VERSION,
        "fixture_name": str(fixture.get("fixture_name") or "unknown"),
        "generated_at": str(fixture.get("generated_at") or "fixture-time"),
        "ghost": {
            "name": str(ghost.get("name") or "mew-ghost"),
            "mood": str(ghost.get("mood") or "neutral"),
            "message": str(ghost.get("message") or "ready"),
            "focus": str(ghost.get("focus") or "local shell"),
        },
        "active_window": probe,
        "launch_intents": build_launcher_intents(dry_run=True),
    }


def render_local_html(state: Mapping[str, Any]) -> str:
    """Render deterministic local HTML for the ghost shell."""
    ghost = state["ghost"]
    probe = state["active_window"]
    intents = state["launch_intents"]

    intent_items = "\n".join(
        "        <li><code>"
        + escape(" ".join(intent["command"]))
        + "</code> — "
        + escape(intent["description"])
        + " <strong>(dry-run)</strong></li>"
        for intent in intents
    )
    state_json = escape(json.dumps(state, indent=2, sort_keys=True))

    return "\n".join(
        [
            "<!doctype html>",
            "<html lang=\"en\">",
            "  <head>",
            "    <meta charset=\"utf-8\">",
            "    <title>mew-ghost SP13 shell</title>",
            "    <style>",
            "      body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 2rem; background: #111827; color: #f9fafb; }",
            "      main { max-width: 780px; }",
            "      section { border: 1px solid #374151; border-radius: 12px; padding: 1rem; margin: 1rem 0; background: #1f2937; }",
            "      code, pre { background: #030712; color: #d1fae5; padding: 0.15rem 0.3rem; border-radius: 6px; }",
            "      pre { padding: 1rem; overflow-x: auto; }",
            "      .status { color: #93c5fd; }",
            "    </style>",
            "  </head>",
            "  <body>",
            "    <main>",
            "      <h1>" + escape(ghost["name"]) + "</h1>",
            "      <section>",
            "        <h2>Ghost state</h2>",
            "        <p><strong>Mood:</strong> " + escape(ghost["mood"]) + "</p>",
            "        <p><strong>Focus:</strong> " + escape(ghost["focus"]) + "</p>",
            "        <p>" + escape(ghost["message"]) + "</p>",
            "      </section>",
            "      <section>",
            "        <h2>Active app/window probe</h2>",
            "        <p class=\"status\"><strong>Status:</strong> " + escape(probe["status"]) + "</p>",
            "        <p><strong>App:</strong> " + escape(probe.get("active_app") or "unavailable") + "</p>",
            "        <p><strong>Window:</strong> " + escape(probe.get("window_title") or "unavailable") + "</p>",
            "        <p><strong>Reason:</strong> " + escape(probe.get("reason") or "none") + "</p>",
            "      </section>",
            "      <section>",
            "        <h2>Launcher intents</h2>",
            "        <ul>",
            intent_items,
            "        </ul>",
            "      </section>",
            "      <section>",
            "        <h2>Deterministic state JSON</h2>",
            "        <pre>" + state_json + "</pre>",
            "      </section>",
            "    </main>",
            "  </body>",
            "</html>",
            "",
        ]
    )


def render_fixture(
    path: str | Path = DEFAULT_FIXTURE,
    *,
    probe_provider: ProbeProvider | None = None,
    platform_name: str | None = None,
) -> tuple[dict[str, Any], str]:
    fixture = load_fixture(path)
    state = build_ghost_state(fixture, probe_provider=probe_provider, platform_name=platform_name)
    return state, render_local_html(state)


def main(
    argv: Sequence[str] | None = None,
    *,
    live_probe_provider: ProbeProvider | None = None,
) -> int:
    parser = argparse.ArgumentParser(description="Render the SP13 mew-ghost shell")
    parser.add_argument("--fixture", default=str(DEFAULT_FIXTURE), help="local JSON fixture to render")
    parser.add_argument("--output", help="write rendered output to this path")
    parser.add_argument("--format", choices=("html", "state"), default="html")
    parser.add_argument(
        "--live-active-window",
        action="store_true",
        help="explicitly opt into the macOS osascript active app/window probe",
    )
    args = parser.parse_args(argv)

    provider = None
    if args.live_active_window:
        provider = live_probe_provider or make_macos_osascript_probe_provider()

    state, html = render_fixture(args.fixture, probe_provider=provider)
    rendered = json.dumps(state, indent=2, sort_keys=True) + "\n" if args.format == "state" else html

    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
