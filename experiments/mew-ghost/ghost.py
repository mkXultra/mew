#!/usr/bin/env python3
"""Standalone SP15 mew-ghost launcher contract shell.

The module is deliberately local and fixture-driven by default. It can perform
an explicit opt-in macOS active app/window probe through osascript, renders a
deterministic local HTML shell, exposes dry-run command intents, and only runs
mew launch commands behind an explicit CLI opt-in. It uses no screen capture,
hidden monitoring, network access, live .mew reads, or core mew imports.
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

SCHEMA_VERSION = "mew-ghost.sp15.v1"
DEFAULT_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "sample_ghost_state.json"
ProbeProvider = Callable[[], Mapping[str, Any]]
OsascriptRunner = Callable[..., subprocess.CompletedProcess[str]]
LauncherRunner = Callable[..., subprocess.CompletedProcess[str]]
WhichProvider = Callable[[str], str | None]
OSASCRIPT_TIMEOUT_SECONDS = 2.0
DEFAULT_REFRESH_COUNT = 3
MAX_REFRESH_COUNT = 12
PRESENCE_STATES = ("idle", "attentive", "coding", "waiting", "blocked")
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
    """Return launcher intents for the two explicit mew command surfaces."""
    side_effects = "none" if dry_run else "executes_local_mew_command"
    return [
        {
            "id": "mew-chat",
            "label": "Open mew chat",
            "command": ["mew", "chat"],
            "dry_run": dry_run,
            "side_effects": side_effects,
            "description": "Would open the chat surface for the operator."
            if dry_run
            else "Opens the chat surface for the operator.",
        },
        {
            "id": "mew-code",
            "label": "Open mew code",
            "command": ["mew", "code"],
            "dry_run": dry_run,
            "side_effects": side_effects,
            "description": "Would open the coding surface for the operator."
            if dry_run
            else "Opens the coding surface for the operator.",
        },
    ]


def execute_launcher_intents(
    intents: Sequence[Mapping[str, Any]],
    *,
    allow_execute: bool = False,
    runner: LauncherRunner = subprocess.run,
) -> list[dict[str, Any]]:
    """Return launcher intents after dry-run simulation or explicit execution."""
    observed: list[dict[str, Any]] = []
    for intent in intents:
        command = [str(part) for part in intent.get("command", [])]
        result = dict(intent)
        if not allow_execute or bool(intent.get("dry_run", True)):
            result["dry_run"] = True
            result["side_effects"] = "none"
            result["execution"] = {
                "status": "dry_run",
                "executed": False,
                "returncode": None,
            }
            observed.append(result)
            continue

        completed = runner(command, capture_output=True, text=True, check=False)
        returncode = int(getattr(completed, "returncode", 0) or 0)
        result["dry_run"] = False
        result["side_effects"] = "executes_local_mew_command"
        result["execution"] = {
            "status": "executed" if returncode == 0 else "failed",
            "executed": True,
            "returncode": returncode,
        }
        observed.append(result)
    return observed


def _lower_text(*parts: object) -> str:
    return " ".join(str(part or "") for part in parts).lower()


def _task_mapping(fixture: Mapping[str, Any]) -> Mapping[str, Any]:
    raw = fixture.get("task")
    return raw if isinstance(raw, Mapping) else {}


def classify_presence(
    *,
    active_window: Mapping[str, Any],
    task: Mapping[str, Any] | None = None,
    ghost: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Map app/window/task state into one deterministic presence state."""
    del ghost
    task = task or {}
    probe_status = str(active_window.get("status") or "unavailable")
    reason = active_window.get("reason")
    task_status = str(task.get("status") or "").lower()
    task_kind = str(task.get("kind") or "").lower()
    surface_text = _lower_text(active_window.get("active_app"), active_window.get("window_title"))
    task_text = _lower_text(task.get("title"), task.get("description"))
    combined_text = _lower_text(surface_text, task_text)

    if probe_status == "permission_denied" or task_status in {"blocked", "error"}:
        state = "blocked"
        detail = "permission_or_task_blocked"
    elif task_status in {"waiting", "paused", "review", "pending"} or any(
        marker in combined_text for marker in ("waiting", "review", "pending", "blocked on")
    ):
        state = "waiting"
        detail = "task_waiting"
    elif task_kind == "coding" or any(
        marker in combined_text
        for marker in (
            "code",
            "coding",
            "visual studio code",
            "vscode",
            "xcode",
            "terminal",
            ".py",
        )
    ):
        state = "coding"
        detail = "coding_surface"
    elif probe_status == "available" or any(marker in surface_text for marker in ("notes", "browser", "safari")):
        state = "attentive"
        detail = "active_surface"
    else:
        state = "idle"
        detail = str(reason or "no_active_surface")

    return {
        "state": state,
        "detail": detail,
        "allowed_states": list(PRESENCE_STATES),
        "inputs": {
            "probe_status": probe_status,
            "probe_reason": reason,
            "active_app": active_window.get("active_app"),
            "window_title": active_window.get("window_title"),
            "task_status": task.get("status"),
            "task_kind": task.get("kind"),
        },
    }


def normalize_refresh_count(value: int | str | None = DEFAULT_REFRESH_COUNT) -> int:
    """Clamp refresh count to a bounded deterministic range."""
    try:
        parsed = int(value if value is not None else DEFAULT_REFRESH_COUNT)
    except (TypeError, ValueError):
        parsed = DEFAULT_REFRESH_COUNT
    return max(1, min(parsed, MAX_REFRESH_COUNT))


def build_presence_loop(
    *,
    fixture: Mapping[str, Any],
    active_window: Mapping[str, Any],
    ghost: Mapping[str, Any],
    refresh_count: int | str | None = DEFAULT_REFRESH_COUNT,
) -> dict[str, Any]:
    """Render a bounded deterministic refresh contract without monitoring."""
    count = normalize_refresh_count(refresh_count)
    task = _task_mapping(fixture)
    classified = classify_presence(active_window=active_window, task=task, ghost=ghost)
    base_time = str(fixture.get("generated_at") or "fixture-time")
    snapshots = [
        {
            "refresh_index": index,
            "rendered_at": base_time,
            "presence_state": classified["state"],
            "visual_state": classified["state"],
            "detail": classified["detail"],
            "active_app": active_window.get("active_app"),
            "window_title": active_window.get("window_title"),
            "task_title": task.get("title"),
        }
        for index in range(count)
    ]
    return {
        "contract": "bounded_deterministic_refresh",
        "refresh_count": count,
        "max_refresh_count": MAX_REFRESH_COUNT,
        "background_monitoring": False,
        "hidden_capture": False,
        "network": False,
        "live_mew_reads": False,
        "classification": classified,
        "snapshots": snapshots,
    }


def build_ghost_state(
    fixture: Mapping[str, Any],
    *,
    probe_provider: ProbeProvider | None = None,
    platform_name: str | None = None,
    refresh_count: int | str | None = DEFAULT_REFRESH_COUNT,
) -> dict[str, Any]:
    """Build deterministic ghost state from a fixture plus optional probe."""
    ghost_raw = fixture.get("ghost")
    if not isinstance(ghost_raw, Mapping):
        raise ValueError("ghost fixture requires a 'ghost' object")

    if probe_provider is None and isinstance(fixture.get("probe"), Mapping):
        probe = normalize_probe_fixture(fixture["probe"])
    else:
        probe = probe_active_window(probe_provider, platform_name=platform_name)

    ghost = {
        "name": str(ghost_raw.get("name") or "mew-ghost"),
        "mood": str(ghost_raw.get("mood") or "neutral"),
        "message": str(ghost_raw.get("message") or "ready"),
        "focus": str(ghost_raw.get("focus") or "local shell"),
    }
    presence = build_presence_loop(
        fixture=fixture,
        active_window=probe,
        ghost=ghost,
        refresh_count=refresh_count,
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "fixture_name": str(fixture.get("fixture_name") or "unknown"),
        "generated_at": str(fixture.get("generated_at") or "fixture-time"),
        "ghost": ghost,
        "active_window": probe,
        "presence": presence,
        "launch_intents": execute_launcher_intents(build_launcher_intents(dry_run=True)),
    }


def render_local_html(state: Mapping[str, Any]) -> str:
    """Render deterministic local HTML for the ghost shell."""
    ghost = state["ghost"]
    probe = state["active_window"]
    presence = state["presence"]
    classification = presence["classification"]
    intents = state["launch_intents"]

    intent_items = "\n".join(
        "        <li><code>"
        + escape(" ".join(intent["command"]))
        + "</code> — "
        + escape(intent["description"])
        + " <strong>("
        + escape("dry-run" if intent.get("dry_run", True) else "executed")
        + ")</strong></li>"
        for intent in intents
    )
    snapshot_items = "\n".join(
        "        <li>refresh "
        + escape(str(snapshot["refresh_index"]))
        + ": <strong>"
        + escape(snapshot["presence_state"])
        + "</strong> — "
        + escape(snapshot["detail"])
        + "</li>"
        for snapshot in presence["snapshots"]
    )
    state_json = escape(json.dumps(state, indent=2, sort_keys=True))

    return "\n".join(
        [
            "<!doctype html>",
            "<html lang=\"en\">",
            "  <head>",
            "    <meta charset=\"utf-8\">",
            "    <title>mew-ghost SP15 launcher contract</title>",
            "    <style>",
            "      body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 2rem; background: #111827; color: #f9fafb; }",
            "      main { max-width: 780px; }",
            "      section { border: 1px solid #374151; border-radius: 12px; padding: 1rem; margin: 1rem 0; background: #1f2937; }",
            "      code, pre { background: #030712; color: #d1fae5; padding: 0.15rem 0.3rem; border-radius: 6px; }",
            "      pre { padding: 1rem; overflow-x: auto; }",
            "      .status { color: #93c5fd; }",
            "      .presence { color: #fcd34d; }",
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
            "        <h2>Presence loop</h2>",
            "        <p class=\"presence\"><strong>Presence:</strong> " + escape(classification["state"]) + "</p>",
            "        <p><strong>Refresh contract:</strong> " + escape(presence["contract"]) + " (" + escape(str(presence["refresh_count"])) + " snapshots)</p>",
            "        <ul>",
            snapshot_items,
            "        </ul>",
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
    refresh_count: int | str | None = DEFAULT_REFRESH_COUNT,
) -> tuple[dict[str, Any], str]:
    fixture = load_fixture(path)
    state = build_ghost_state(
        fixture,
        probe_provider=probe_provider,
        platform_name=platform_name,
        refresh_count=refresh_count,
    )
    return state, render_local_html(state)


def main(
    argv: Sequence[str] | None = None,
    *,
    live_probe_provider: ProbeProvider | None = None,
    launcher_runner: LauncherRunner | None = None,
) -> int:
    parser = argparse.ArgumentParser(description="Render the SP15 mew-ghost launcher contract")
    parser.add_argument("--fixture", default=str(DEFAULT_FIXTURE), help="local JSON fixture to render")
    parser.add_argument("--output", help="write rendered output to this path")
    parser.add_argument("--format", choices=("html", "state"), default="html")
    parser.add_argument(
        "--refresh-count",
        type=int,
        default=DEFAULT_REFRESH_COUNT,
        help=f"bounded deterministic snapshot count, clamped to 1..{MAX_REFRESH_COUNT}",
    )
    parser.add_argument(
        "--live-active-window",
        action="store_true",
        help="explicitly opt into the macOS osascript active app/window probe",
    )
    parser.add_argument(
        "--execute-launchers",
        action="store_true",
        help="explicitly opt into running mew chat and mew code; dry-run remains the default",
    )
    args = parser.parse_args(argv)

    provider = None
    if args.live_active_window:
        provider = live_probe_provider or make_macos_osascript_probe_provider()

    state, html = render_fixture(args.fixture, probe_provider=provider, refresh_count=args.refresh_count)
    if args.execute_launchers:
        state["launch_intents"] = execute_launcher_intents(
            build_launcher_intents(dry_run=False),
            allow_execute=True,
            runner=launcher_runner or subprocess.run,
        )
        html = render_local_html(state)
    rendered = json.dumps(state, indent=2, sort_keys=True) + "\n" if args.format == "state" else html

    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
