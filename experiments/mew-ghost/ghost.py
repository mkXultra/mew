#!/usr/bin/env python3
'''Standalone SP16 mew-ghost foreground watch-mode shell.

The module is deliberately local and fixture-driven by default. It can perform
an explicit opt-in macOS active app/window probe through osascript, renders a
deterministic local HTML shell, exposes dry-run command intents, and only runs
mew launch commands behind an explicit CLI opt-in. Watch mode is a foreground
loop with bounded `--watch-count` support or operator-controlled interrupt; it
uses no screen capture, hidden monitoring, network access, live .mew reads, or
core mew imports.
'''

from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence, TextIO

SCHEMA_VERSION = 'mew-ghost.sp16.v1'
DEFAULT_FIXTURE = Path(__file__).resolve().parent / 'fixtures' / 'sample_ghost_state.json'
ProbeProvider = Callable[[], Mapping[str, Any]]
OsascriptRunner = Callable[..., subprocess.CompletedProcess[str]]
LauncherRunner = Callable[..., subprocess.CompletedProcess[str]]
WhichProvider = Callable[[str], str | None]
Sleeper = Callable[[float], None]
Clock = Callable[[], str]
OSASCRIPT_TIMEOUT_SECONDS = 2.0
DEFAULT_REFRESH_COUNT = 3
MAX_REFRESH_COUNT = 12
DEFAULT_WATCH_INTERVAL_SECONDS = 2.0
PRESENCE_STATES = ('idle', 'attentive', 'coding', 'waiting', 'blocked')
ACTIVE_WINDOW_OSASCRIPT = chr(10).join(
    [
        'tell application ' + chr(34) + 'System Events' + chr(34),
        '  set frontApp to first application process whose frontmost is true',
        '  set appName to name of frontApp',
        '  set windowTitle to ' + chr(34) + chr(34),
        '  try',
        '    set windowTitle to name of front window of frontApp',
        '  end try',
        '  return appName & (ASCII character 9) & windowTitle',
        'end tell',
    ]
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def load_fixture(path: str | Path = DEFAULT_FIXTURE) -> dict[str, Any]:
    fixture_path = Path(path)
    with fixture_path.open('r', encoding='utf-8') as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError('ghost fixture must be a JSON object')
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
        'schema_version': SCHEMA_VERSION,
        'status': status,
        'reason': reason,
        'platform': platform_name or 'unknown',
        'active_app': active_app,
        'window_title': window_title,
        'requires_permission': requires_permission,
    }


def normalize_probe_fixture(raw_probe: Mapping[str, Any]) -> dict[str, Any]:
    status = str(raw_probe.get('status') or 'unavailable')
    reason = raw_probe.get('reason')
    active_app = raw_probe.get('active_app')
    window_title = raw_probe.get('window_title')
    return _probe_result(
        status=status,
        reason=str(reason) if reason is not None else None,
        platform_name=str(raw_probe.get('platform') or 'fixture'),
        active_app=str(active_app) if active_app else None,
        window_title=str(window_title) if window_title else None,
        requires_permission=bool(raw_probe.get('requires_permission', False)),
    )


def _looks_like_permission_denied(message: str) -> bool:
    text = message.lower()
    return any(
        marker in text
        for marker in (
            'accessibility',
            'assistive access',
            'not authorized',
            'not allowed',
            'operation not permitted',
        )
    )


def _parse_osascript_probe_output(output: str) -> dict[str, Any]:
    if not output.strip():
        return {}
    parts = output.strip().split(chr(9))
    if len(parts) != 2:
        raise ValueError('osascript probe returned malformed output')
    active_app = parts[0].strip()
    window_title = parts[1].strip()
    if not active_app and not window_title:
        return {}
    return {
        'active_app': active_app,
        'window_title': window_title,
        'requires_permission': True,
    }


def _run_osascript_active_window(
    *,
    runner: OsascriptRunner = subprocess.run,
    osascript_path: str | None = None,
    which: WhichProvider | None = None,
    timeout_seconds: float = OSASCRIPT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    resolver = which if which is not None else shutil.which
    resolved_path = osascript_path or resolver('osascript')
    if not resolved_path:
        raise FileNotFoundError('osascript')

    completed = runner(
        [resolved_path, '-e', ACTIVE_WINDOW_OSASCRIPT],
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout_seconds,
    )
    stdout = str(getattr(completed, 'stdout', '') or '')
    stderr = str(getattr(completed, 'stderr', '') or '')
    returncode = int(getattr(completed, 'returncode', 0) or 0)
    if returncode != 0:
        if _looks_like_permission_denied(stderr):
            raise PermissionError(stderr or 'Accessibility permission denied')
        raise OSError(stderr or 'osascript exited with %s' % returncode)
    return _parse_osascript_probe_output(stdout)


def make_macos_osascript_probe_provider(
    *,
    runner: OsascriptRunner = subprocess.run,
    osascript_path: str | None = None,
    which: WhichProvider | None = None,
    timeout_seconds: float = OSASCRIPT_TIMEOUT_SECONDS,
) -> ProbeProvider:
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
    system_name = platform_name if platform_name is not None else platform.system()
    if system_name != 'Darwin':
        return _probe_result(
            status='unavailable',
            reason='requires_macos',
            platform_name=system_name,
            requires_permission=False,
        )

    if provider is None:
        return _probe_result(
            status='unavailable',
            reason='live_probe_not_requested',
            platform_name=system_name,
            requires_permission=True,
        )

    try:
        raw = provider()
    except FileNotFoundError:
        return _probe_result(status='unavailable', reason='missing_osascript', platform_name=system_name, requires_permission=True)
    except PermissionError:
        return _probe_result(status='permission_denied', reason='accessibility_permission_denied', platform_name=system_name, requires_permission=True)
    except subprocess.TimeoutExpired:
        return _probe_result(status='unavailable', reason='osascript_timeout', platform_name=system_name, requires_permission=True)
    except ValueError:
        return _probe_result(status='unavailable', reason='malformed_probe_result', platform_name=system_name, requires_permission=True)
    except OSError:
        return _probe_result(status='unavailable', reason='probe_unavailable', platform_name=system_name, requires_permission=True)

    active_app = str(raw.get('active_app') or '').strip() or None
    window_title = str(raw.get('window_title') or '').strip() or None
    if not active_app and not window_title:
        return _probe_result(
            status='unavailable',
            reason='empty_probe_result',
            platform_name=system_name,
            requires_permission=bool(raw.get('requires_permission', True)),
        )
    return _probe_result(
        status='available',
        reason=None,
        platform_name=system_name,
        active_app=active_app,
        window_title=window_title,
        requires_permission=bool(raw.get('requires_permission', True)),
    )


def build_launcher_intents(*, dry_run: bool = True) -> list[dict[str, Any]]:
    side_effects = 'none' if dry_run else 'executes_local_mew_command'
    return [
        {
            'id': 'mew-chat',
            'label': 'Open mew chat',
            'command': ['mew', 'chat'],
            'dry_run': dry_run,
            'side_effects': side_effects,
            'description': 'Would open the chat surface for the operator.' if dry_run else 'Opens the chat surface for the operator.',
        },
        {
            'id': 'mew-code',
            'label': 'Open mew code',
            'command': ['mew', 'code'],
            'dry_run': dry_run,
            'side_effects': side_effects,
            'description': 'Would open the coding surface for the operator.' if dry_run else 'Opens the coding surface for the operator.',
        },
    ]


def execute_launcher_intents(
    intents: Sequence[Mapping[str, Any]],
    *,
    allow_execute: bool = False,
    runner: LauncherRunner = subprocess.run,
) -> list[dict[str, Any]]:
    observed: list[dict[str, Any]] = []
    for intent in intents:
        command = [str(part) for part in intent.get('command', [])]
        result = dict(intent)
        if not allow_execute or bool(intent.get('dry_run', True)):
            result['dry_run'] = True
            result['side_effects'] = 'none'
            result['execution'] = {'status': 'dry_run', 'executed': False, 'returncode': None}
            observed.append(result)
            continue
        completed = runner(command, capture_output=True, text=True, check=False)
        returncode = int(getattr(completed, 'returncode', 0) or 0)
        result['dry_run'] = False
        result['side_effects'] = 'executes_local_mew_command'
        result['execution'] = {'status': 'executed' if returncode == 0 else 'failed', 'executed': True, 'returncode': returncode}
        observed.append(result)
    return observed


def _lower_text(*parts: object) -> str:
    return ' '.join(str(part or '') for part in parts).lower()


def _task_mapping(fixture: Mapping[str, Any]) -> Mapping[str, Any]:
    raw = fixture.get('task')
    return raw if isinstance(raw, Mapping) else {}


def classify_presence(
    *,
    active_window: Mapping[str, Any],
    task: Mapping[str, Any] | None = None,
    ghost: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    del ghost
    task = task or {}
    probe_status = str(active_window.get('status') or 'unavailable')
    reason = active_window.get('reason')
    task_status = str(task.get('status') or '').lower()
    task_kind = str(task.get('kind') or '').lower()
    surface_text = _lower_text(active_window.get('active_app'), active_window.get('window_title'))
    task_text = _lower_text(task.get('title'), task.get('description'))
    combined_text = _lower_text(surface_text, task_text)

    if probe_status == 'permission_denied' or task_status in {'blocked', 'error'}:
        state = 'blocked'
        detail = 'permission_or_task_blocked'
    elif task_status in {'waiting', 'paused', 'review', 'pending'} or any(marker in combined_text for marker in ('waiting', 'review', 'pending', 'blocked on')):
        state = 'waiting'
        detail = 'task_waiting'
    elif task_kind == 'coding' or any(marker in combined_text for marker in ('code', 'coding', 'visual studio code', 'vscode', 'xcode', 'terminal', '.py')):
        state = 'coding'
        detail = 'coding_surface'
    elif probe_status == 'available' or any(marker in surface_text for marker in ('notes', 'browser', 'safari')):
        state = 'attentive'
        detail = 'active_surface'
    else:
        state = 'idle'
        detail = str(reason or 'no_active_surface')

    return {
        'state': state,
        'detail': detail,
        'allowed_states': list(PRESENCE_STATES),
        'inputs': {
            'probe_status': probe_status,
            'probe_reason': reason,
            'active_app': active_window.get('active_app'),
            'window_title': active_window.get('window_title'),
            'task_status': task.get('status'),
            'task_kind': task.get('kind'),
        },
    }


def normalize_refresh_count(value: int | str | None = DEFAULT_REFRESH_COUNT) -> int:
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
    count = normalize_refresh_count(refresh_count)
    task = _task_mapping(fixture)
    classified = classify_presence(active_window=active_window, task=task, ghost=ghost)
    base_time = str(fixture.get('generated_at') or 'fixture-time')
    snapshots = [
        {
            'refresh_index': index,
            'rendered_at': base_time,
            'presence_state': classified['state'],
            'visual_state': classified['state'],
            'detail': classified['detail'],
            'active_app': active_window.get('active_app'),
            'window_title': active_window.get('window_title'),
            'task_title': task.get('title'),
        }
        for index in range(count)
    ]
    return {
        'contract': 'bounded_deterministic_refresh',
        'refresh_count': count,
        'max_refresh_count': MAX_REFRESH_COUNT,
        'background_monitoring': False,
        'hidden_capture': False,
        'network': False,
        'live_mew_reads': False,
        'classification': classified,
        'snapshots': snapshots,
    }


def build_ghost_state(
    fixture: Mapping[str, Any],
    *,
    probe_provider: ProbeProvider | None = None,
    platform_name: str | None = None,
    refresh_count: int | str | None = DEFAULT_REFRESH_COUNT,
    freshness: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    ghost_raw = fixture.get('ghost')
    if not isinstance(ghost_raw, Mapping):
        raise ValueError('ghost fixture requires a ghost object')

    if probe_provider is None and isinstance(fixture.get('probe'), Mapping):
        probe = normalize_probe_fixture(fixture['probe'])
    else:
        probe = probe_active_window(probe_provider, platform_name=platform_name)

    ghost = {
        'name': str(ghost_raw.get('name') or 'mew-ghost'),
        'mood': str(ghost_raw.get('mood') or 'neutral'),
        'message': str(ghost_raw.get('message') or 'ready'),
        'focus': str(ghost_raw.get('focus') or 'local shell'),
    }
    presence = build_presence_loop(fixture=fixture, active_window=probe, ghost=ghost, refresh_count=refresh_count)
    return {
        'schema_version': SCHEMA_VERSION,
        'fixture_name': str(fixture.get('fixture_name') or 'unknown'),
        'generated_at': str(fixture.get('generated_at') or 'fixture-time'),
        'ghost': ghost,
        'active_window': probe,
        'presence': presence,
        'freshness': dict(freshness or {'mode': 'single-render', 'rendered_at': str(fixture.get('generated_at') or 'fixture-time')}),
        'launch_intents': execute_launcher_intents(build_launcher_intents(dry_run=True)),
    }


def render_local_html(state: Mapping[str, Any]) -> str:
    ghost = state['ghost']
    probe = state['active_window']
    presence = state['presence']
    classification = presence['classification']
    intents = state['launch_intents']
    freshness = state.get('freshness', {})
    watch_iteration = freshness.get('watch_iteration')
    watch_total = freshness.get('watch_total')
    iteration_label = 'single render' if watch_iteration is None else 'watch iteration %s%s' % (
        watch_iteration,
        '' if watch_total is None else ' of %s' % watch_total,
    )

    intent_items = chr(10).join(
        '        <li><code>'
        + escape(' '.join(intent['command']))
        + '</code> — '
        + escape(intent['description'])
        + ' <strong>('
        + escape('dry-run' if intent.get('dry_run', True) else 'executed')
        + ')</strong></li>'
        for intent in intents
    )
    snapshot_items = chr(10).join(
        '        <li>refresh '
        + escape(str(snapshot['refresh_index']))
        + ': <strong>'
        + escape(snapshot['presence_state'])
        + '</strong> — '
        + escape(snapshot['detail'])
        + '</li>'
        for snapshot in presence['snapshots']
    )
    state_json = escape(json.dumps(state, indent=2, sort_keys=True))

    return chr(10).join(
        [
            '<!doctype html>',
            '<html lang=' + chr(39) + 'en' + chr(39) + '>',
            '  <head>',
            '    <meta charset=' + chr(39) + 'utf-8' + chr(39) + '>',
            '    <title>mew-ghost SP16 watch mode</title>',
            '    <style>',
            '      body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 2rem; background: #111827; color: #f9fafb; }',
            '      main { max-width: 780px; }',
            '      section { border: 1px solid #374151; border-radius: 12px; padding: 1rem; margin: 1rem 0; background: #1f2937; }',
            '      code, pre { background: #030712; color: #d1fae5; padding: 0.15rem 0.3rem; border-radius: 6px; }',
            '      pre { padding: 1rem; overflow-x: auto; }',
            '      .status { color: #93c5fd; }',
            '      .presence { color: #fcd34d; }',
            '    </style>',
            '  </head>',
            '  <body>',
            '    <main>',
            '      <h1>' + escape(ghost['name']) + '</h1>',
            '      <section>',
            '        <h2>Ghost state</h2>',
            '        <p><strong>Mood:</strong> ' + escape(ghost['mood']) + '</p>',
            '        <p><strong>Focus:</strong> ' + escape(ghost['focus']) + '</p>',
            '        <p>' + escape(ghost['message']) + '</p>',
            '      </section>',
            '      <section>',
            '        <h2>Freshness</h2>',
            '        <p><strong>Mode:</strong> ' + escape(str(freshness.get('mode', 'single-render'))) + '</p>',
            '        <p><strong>Iteration:</strong> ' + escape(iteration_label) + '</p>',
            '        <p><strong>Refreshed:</strong> ' + escape(str(freshness.get('rendered_at', state.get('generated_at')))) + '</p>',
            '        <p><strong>Interval seconds:</strong> ' + escape(str(freshness.get('interval_seconds', 'n/a'))) + '</p>',
            '      </section>',
            '      <section>',
            '        <h2>Presence loop</h2>',
            '        <p class=' + chr(39) + 'presence' + chr(39) + '><strong>Presence:</strong> ' + escape(classification['state']) + '</p>',
            '        <p><strong>Refresh contract:</strong> ' + escape(presence['contract']) + ' (' + escape(str(presence['refresh_count'])) + ' snapshots)</p>',
            '        <ul>',
            snapshot_items,
            '        </ul>',
            '      </section>',
            '      <section>',
            '        <h2>Active app/window probe</h2>',
            '        <p class=' + chr(39) + 'status' + chr(39) + '><strong>Status:</strong> ' + escape(probe['status']) + '</p>',
            '        <p><strong>App:</strong> ' + escape(probe.get('active_app') or 'unavailable') + '</p>',
            '        <p><strong>Window:</strong> ' + escape(probe.get('window_title') or 'unavailable') + '</p>',
            '        <p><strong>Reason:</strong> ' + escape(probe.get('reason') or 'none') + '</p>',
            '      </section>',
            '      <section>',
            '        <h2>Launcher intents</h2>',
            '        <ul>',
            intent_items,
            '        </ul>',
            '      </section>',
            '      <section>',
            '        <h2>Deterministic state JSON</h2>',
            '        <pre>' + state_json + '</pre>',
            '      </section>',
            '    </main>',
            '  </body>',
            '</html>',
        ]
    ) + chr(10)


def render_fixture(
    path: str | Path = DEFAULT_FIXTURE,
    *,
    probe_provider: ProbeProvider | None = None,
    platform_name: str | None = None,
    refresh_count: int | str | None = DEFAULT_REFRESH_COUNT,
    freshness: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], str]:
    fixture = load_fixture(path)
    state = build_ghost_state(
        fixture,
        probe_provider=probe_provider,
        platform_name=platform_name,
        refresh_count=refresh_count,
        freshness=freshness,
    )
    return state, render_local_html(state)


def _render_payload(state: Mapping[str, Any], html: str, format_name: str) -> str:
    if format_name == 'state':
        return json.dumps(state, indent=2, sort_keys=True) + chr(10)
    return html


def _watch_record(
    state: Mapping[str, Any],
    *,
    format_name: str,
    rendered: str,
    output_path: Path | None,
    launchers_executed: bool,
) -> dict[str, Any]:
    freshness = state['freshness']
    record: dict[str, Any] = {
        'schema_version': SCHEMA_VERSION,
        'record_type': 'mew_ghost_watch_iteration',
        'watch_iteration': freshness.get('watch_iteration'),
        'watch_total': freshness.get('watch_total'),
        'interval_seconds': freshness.get('interval_seconds'),
        'refreshed_at': freshness.get('rendered_at'),
        'format': format_name,
        'output': str(output_path) if output_path is not None else None,
        'presence_state': state['presence']['classification']['state'],
        'active_window_status': state['active_window']['status'],
        'active_app': state['active_window'].get('active_app'),
        'launcher_execution_requested': launchers_executed,
    }
    if format_name == 'state':
        record['state'] = state
    elif output_path is None:
        record['html'] = rendered
    return record


def run_watch(
    fixture_path: str | Path = DEFAULT_FIXTURE,
    *,
    format_name: str = 'html',
    output: str | Path | None = None,
    probe_provider: ProbeProvider | None = None,
    platform_name: str | None = None,
    watch_count: int | None = None,
    interval_seconds: float = DEFAULT_WATCH_INTERVAL_SECONDS,
    execute_launchers: bool = False,
    launcher_runner: LauncherRunner | None = None,
    sleeper: Sleeper = time.sleep,
    clock: Clock = utc_now_iso,
    stdout: TextIO | None = None,
) -> int:
    stream = stdout or sys.stdout
    output_path = Path(output) if output else None
    iteration = 0
    try:
        while watch_count is None or iteration < watch_count:
            freshness = {
                'mode': 'foreground-watch',
                'rendered_at': clock(),
                'watch_iteration': iteration,
                'watch_total': watch_count,
                'interval_seconds': interval_seconds,
                'background_monitoring': False,
                'hidden_capture': False,
                'network': False,
                'live_mew_reads': False,
            }
            state, html = render_fixture(
                fixture_path,
                probe_provider=probe_provider,
                platform_name=platform_name,
                refresh_count=1,
                freshness=freshness,
            )
            if execute_launchers:
                state['launch_intents'] = execute_launcher_intents(
                    build_launcher_intents(dry_run=False),
                    allow_execute=True,
                    runner=launcher_runner or subprocess.run,
                )
                html = render_local_html(state)
            rendered = _render_payload(state, html, format_name)
            if output_path is not None:
                output_path.write_text(rendered, encoding='utf-8')
            print(
                json.dumps(
                    _watch_record(
                        state,
                        format_name=format_name,
                        rendered=rendered,
                        output_path=output_path,
                        launchers_executed=execute_launchers,
                    ),
                    sort_keys=True,
                ),
                file=stream,
            )
            iteration += 1
            if watch_count is not None and iteration >= watch_count:
                break
            sleeper(interval_seconds)
    except KeyboardInterrupt:
        return 0
    return 0


def main(
    argv: Sequence[str] | None = None,
    *,
    live_probe_provider: ProbeProvider | None = None,
    launcher_runner: LauncherRunner | None = None,
    sleeper: Sleeper = time.sleep,
    clock: Clock = utc_now_iso,
    platform_name: str | None = None,
) -> int:
    parser = argparse.ArgumentParser(description='Render the SP16 mew-ghost watch-mode shell')
    parser.add_argument('--fixture', default=str(DEFAULT_FIXTURE), help='local JSON fixture to render')
    parser.add_argument('--output', help='write rendered output to this path')
    parser.add_argument('--format', choices=('html', 'state'), default='html')
    parser.add_argument('--refresh-count', type=int, default=DEFAULT_REFRESH_COUNT, help='single-render snapshot count, clamped locally')
    parser.add_argument('--watch', action='store_true', help='run foreground watch until KeyboardInterrupt')
    parser.add_argument('--watch-count', type=int, help='run exactly this many foreground watch iterations')
    parser.add_argument('--interval', type=float, default=DEFAULT_WATCH_INTERVAL_SECONDS, help='seconds to sleep between watch iterations')
    parser.add_argument('--live-active-window', action='store_true', help='explicitly opt into the macOS osascript active app/window probe')
    parser.add_argument('--execute-launchers', action='store_true', help='explicitly opt into running mew chat and mew code; dry-run remains the default')
    args = parser.parse_args(argv)

    if args.watch_count is not None and args.watch_count < 1:
        parser.error('--watch-count must be a positive integer')
    if args.interval < 0:
        parser.error('--interval must be non-negative')

    provider = None
    if args.live_active_window:
        provider = live_probe_provider or make_macos_osascript_probe_provider()

    if args.watch or args.watch_count is not None:
        return run_watch(
            args.fixture,
            format_name=args.format,
            output=args.output,
            probe_provider=provider,
            platform_name=platform_name,
            watch_count=args.watch_count,
            interval_seconds=args.interval,
            execute_launchers=args.execute_launchers,
            launcher_runner=launcher_runner,
            sleeper=sleeper,
            clock=clock,
        )

    state, html = render_fixture(
        args.fixture,
        probe_provider=provider,
        platform_name=platform_name,
        refresh_count=args.refresh_count,
    )
    if args.execute_launchers:
        state['launch_intents'] = execute_launcher_intents(
            build_launcher_intents(dry_run=False),
            allow_execute=True,
            runner=launcher_runner or subprocess.run,
        )
        html = render_local_html(state)
    rendered = _render_payload(state, html, args.format)
    if args.output:
        Path(args.output).write_text(rendered, encoding='utf-8')
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
