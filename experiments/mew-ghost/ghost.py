#!/usr/bin/env python3
'''Standalone SP18 mew-ghost foreground watch-mode shell.

The module is deliberately local and deterministic for machine-readable output.
It can perform an explicit opt-in macOS active app/window probe through
osascript, render deterministic local HTML, expose dry-run command intents, and
use repo-local live desk JSON for the foreground human terminal surface by
default. Watch mode is a foreground loop with bounded `--watch-count` support
or operator-controlled interrupt; it uses no screen capture, hidden monitoring,
network access, background live .mew reads, or core mew imports.
'''

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence, TextIO

SCHEMA_VERSION = 'mew-ghost.sp18.v1'
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FIXTURE = Path(__file__).resolve().parent / 'fixtures' / 'sample_ghost_state.json'
DEFAULT_DESK_FIXTURE = Path(__file__).resolve().parent / 'fixtures' / 'sample_desk_view.json'
LIVE_DESK_COMMAND_DISPLAY = ['./mew', 'desk', '--json']
DESK_PET_STATE_TO_PRESENCE = {
    'sleeping': 'idle',
    'thinking': 'attentive',
    'typing': 'coding',
    'alerting': 'waiting',
}
EXECUTABLE_LAUNCHER_IDS = {'mew-chat', 'mew-code'}
ProbeProvider = Callable[[], Mapping[str, Any]]
DeskProvider = Callable[[], Mapping[str, Any]]
OsascriptRunner = Callable[..., subprocess.CompletedProcess[str]]
DeskRunner = Callable[..., subprocess.CompletedProcess[str]]
LauncherRunner = Callable[..., subprocess.CompletedProcess[str]]
WhichProvider = Callable[[str], str | None]
Sleeper = Callable[[float], None]
Clock = Callable[[], str]
OSASCRIPT_TIMEOUT_SECONDS = 2.0
DESK_TIMEOUT_SECONDS = 1.5
DEFAULT_REFRESH_COUNT = 3
MAX_REFRESH_COUNT = 12
DEFAULT_WATCH_INTERVAL_SECONDS = 2.0
PRESENCE_STATES = ('idle', 'attentive', 'coding', 'waiting', 'blocked')
TERMINAL_FORMS = ('default', 'cat')
CAT_TERMINAL_SPRITE_MASK = (
    '.####.......####......',
    '.#####.....#####......',
    '.##.###....##.##......',
    '.##..#######..##......',
    '.##...######..##......',
    '.##...........##......',
    '###.##....###.####....',
    '##..##....###..###....',
    '##..##....###..###....',
    '###.##.##..##.###.....',
    '.#####.##....###......',
    '...###......####......',
    '...###.......#####....',
    '....##........#####...',
    '....##.........####...',
    '....##.##.##....###...',
    '....##.##.##.....####.',
    '....##.##.##.....####.',
    '....##.##.##.....##.##',
    '...#########....###.##',
    '...##.#####....###..##',
    '...#############...##.',
    '...##################.',
    '..............#####...',
)
CAT_TERMINAL_STATE_MARKERS = {
    'idle': 'zZ',
    'attentive': '?',
    'coding': '*',
    'waiting': '...',
    'blocked': '!',
}
CAT_TERMINAL_STATE_CUES = {
    'idle': 'dreaming softly',
    'attentive': 'ears forward',
    'coding': 'paws on keys',
    'waiting': 'tail swishes',
    'blocked': 'signal flare',
}
CAT_TERMINAL_PIXEL_WIDTH = len(CAT_TERMINAL_SPRITE_MASK[0]) * 2
CAT_TERMINAL_WIDTH_ENV = 'MEW_GHOST_TERMINAL_WIDTH'
DEFAULT_TERMINAL_WIDTH = 80


def _terminal_width() -> int:
    raw_width = os.environ.get(CAT_TERMINAL_WIDTH_ENV)
    if raw_width is not None:
        try:
            return max(0, int(raw_width))
        except ValueError:
            return DEFAULT_TERMINAL_WIDTH
    if sys.stdout.isatty():
        return max(0, shutil.get_terminal_size(fallback=(DEFAULT_TERMINAL_WIDTH, 24)).columns)
    return DEFAULT_TERMINAL_WIDTH


def _center_terminal_line(line: str, terminal_width: int) -> str:
    padding = max(0, (terminal_width - CAT_TERMINAL_PIXEL_WIDTH) // 2)
    return ' ' * padding + line


def _cat_terminal_caption(line: str) -> str:
    return line.center(CAT_TERMINAL_PIXEL_WIDTH).rstrip()


def _cat_terminal_sprite(presence_state: str) -> tuple[str, ...]:
    sprite_lines = tuple(
        ''.join('██' if cell == '#' else '  ' for cell in row)
        for row in CAT_TERMINAL_SPRITE_MASK
    )
    return (
        _cat_terminal_caption('mew-wisp resident cat'),
        _cat_terminal_caption('resident state: %s' % presence_state),
        *sprite_lines,
        _cat_terminal_caption(
            'resident marker: %s | %s'
            % (CAT_TERMINAL_STATE_MARKERS[presence_state], CAT_TERMINAL_STATE_CUES[presence_state])
        ),
    )


CAT_TERMINAL_FORM_BY_PRESENCE = {
    state: _cat_terminal_sprite(state) for state in PRESENCE_STATES
}
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


def load_desk_fixture(path: str | Path = DEFAULT_DESK_FIXTURE) -> dict[str, Any]:
    fixture_path = Path(path)
    with fixture_path.open('r', encoding='utf-8') as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError('desk fixture must be a JSON object')
    return data


def _coerce_command(raw_command: object) -> list[str]:
    if isinstance(raw_command, str):
        return [part for part in raw_command.split() if part]
    if isinstance(raw_command, Sequence):
        return [str(part) for part in raw_command]
    return []


def _normalize_primary_action(raw_action: object) -> dict[str, Any] | None:
    if not isinstance(raw_action, Mapping):
        return None
    command = _coerce_command(raw_action.get('command'))
    label = str(raw_action.get('label') or raw_action.get('title') or raw_action.get('id') or 'Desk primary action')
    return {
        'id': str(raw_action.get('id') or 'desk-primary-action'),
        'label': label,
        'command': command,
        'dry_run': True,
        'side_effects': 'none',
        'description': str(raw_action.get('description') or 'Fixture-only desk primary_action; mew-ghost never executes it.'),
        'source': 'desk-json-fixture',
        'executable': False,
    }


def build_desk_status(desk_fixture: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if desk_fixture is None:
        return {
            'enabled': False,
            'source': None,
            'fixture_name': None,
            'generated_at': None,
            'status': 'disabled',
            'counts': {},
            'details': [],
            'primary_action': None,
            'pet_state_presence_map': dict(DESK_PET_STATE_TO_PRESENCE),
            'live_mew_reads': False,
        }

    desk_root = desk_fixture.get('desk') if isinstance(desk_fixture.get('desk'), Mapping) else desk_fixture
    raw_pets = desk_root.get('pets') if isinstance(desk_root.get('pets'), list) else []
    raw_focus = desk_root.get('focus')
    raw_grouped_details = desk_root.get('details') if isinstance(desk_root.get('details'), Mapping) else {}
    raw_current_git = desk_root.get('current_git') if isinstance(desk_root.get('current_git'), Mapping) else {}
    details: list[dict[str, Any]] = []
    pet_state_counts: dict[str, int] = {}
    for index, raw_pet in enumerate(raw_pets):
        if not isinstance(raw_pet, Mapping):
            continue
        pet_state = str(raw_pet.get('pet_state') or raw_pet.get('state') or 'unknown')
        presence_state = DESK_PET_STATE_TO_PRESENCE.get(pet_state, 'attentive')
        pet_state_counts[pet_state] = pet_state_counts.get(pet_state, 0) + 1
        details.append(
            {
                'index': index,
                'name': str(raw_pet.get('name') or raw_pet.get('id') or 'desk-pet-%s' % index),
                'pet_state': pet_state,
                'presence_state': presence_state,
                'detail': str(raw_pet.get('detail') or raw_pet.get('message') or raw_pet.get('status') or ''),
            }
        )

    if not details:
        raw_top_level_pet_state = desk_root.get('pet_state') or desk_root.get('state')
        if raw_top_level_pet_state is not None:
            pet_state = str(raw_top_level_pet_state or 'unknown')
            presence_state = DESK_PET_STATE_TO_PRESENCE.get(pet_state, 'attentive')
            pet_state_counts[pet_state] = pet_state_counts.get(pet_state, 0) + 1
            if isinstance(raw_focus, Mapping):
                focus_detail = str(raw_focus.get('detail') or raw_focus.get('summary') or '')
            else:
                focus_detail = str(raw_focus or '')
            top_level_detail: dict[str, Any] = {
                'index': 0,
                'name': str(desk_root.get('name') or desk_root.get('id') or 'desk-pet-0'),
                'pet_state': pet_state,
                'presence_state': presence_state,
                'detail': focus_detail,
            }
            if isinstance(raw_focus, Mapping):
                top_level_detail['focus'] = dict(raw_focus)
            if raw_grouped_details:
                top_level_detail['raw_grouped_details'] = dict(raw_grouped_details)
            if raw_current_git:
                top_level_detail['current_git'] = dict(raw_current_git)
            details.append(top_level_detail)

    raw_counts = desk_root.get('counts') if isinstance(desk_root.get('counts'), Mapping) else {}
    counts: dict[str, Any] = {}
    for key, value in raw_counts.items():
        try:
            counts[str(key)] = int(value)
        except (TypeError, ValueError):
            counts[str(key)] = value
    counts['pets_total'] = len(details)
    counts['pet_states'] = pet_state_counts
    if raw_grouped_details:
        counts['raw_grouped_details'] = dict(raw_grouped_details)

    raw_primary_action = desk_root.get('primary_action') or desk_fixture.get('primary_action')
    raw_actions = desk_root.get('actions') or desk_fixture.get('actions')
    if raw_primary_action is None:
        if isinstance(raw_actions, Mapping):
            raw_action_items = raw_actions.get('items')
            raw_primary_action = raw_actions.get('primary_action') or raw_actions.get('primary')
            if raw_primary_action is None and isinstance(raw_action_items, list) and raw_action_items:
                raw_primary_action = raw_action_items[0]
        elif isinstance(raw_actions, Sequence) and not isinstance(raw_actions, (str, bytes)) and raw_actions:
            raw_primary_action = raw_actions[0]
    primary_action = _normalize_primary_action(raw_primary_action)
    primary_pet_state = details[0]['pet_state'] if details else 'unknown'
    return {
        'enabled': True,
        'source': 'desk-json-fixture',
        'fixture_name': str(desk_fixture.get('fixture_name') or 'desk-json-fixture'),
        'generated_at': str(desk_fixture.get('generated_at') or 'fixture-time'),
        'status': str(desk_root.get('status') or primary_pet_state),
        'counts': counts,
        'details': details,
        'primary_action': primary_action,
        'pet_state_presence_map': dict(DESK_PET_STATE_TO_PRESENCE),
        'live_mew_reads': False,
    }


def _live_desk_command(mew_path: str | Path | None = None) -> list[str]:
    command_path = Path(mew_path) if mew_path is not None else REPO_ROOT / 'mew'
    return [str(command_path), 'desk', '--json']


def _apply_live_desk_metadata(status: dict[str, Any]) -> dict[str, Any]:
    status['source'] = 'live-desk'
    status['live_mew_reads'] = True
    status['command'] = list(LIVE_DESK_COMMAND_DISPLAY)
    status['fallback'] = None
    primary_action = status.get('primary_action')
    if isinstance(primary_action, dict):
        primary_action['source'] = 'live-desk'
        if primary_action.get('description') == 'Fixture-only desk primary_action; mew-ghost never executes it.':
            primary_action['description'] = (
                'Live desk primary_action is a dry-run hint from opted-in live desk JSON; '
                'mew-ghost never executes it.'
            )
        primary_action['dry_run'] = True
        primary_action['side_effects'] = 'none'
        primary_action['executable'] = False
    return status


def build_live_desk_fallback_status(
    reason: str,
    *,
    message: str = '',
    returncode: int | None = None,
) -> dict[str, Any]:
    fallback = {
        'reason': reason,
        'message': message,
        'returncode': returncode,
        'command': list(LIVE_DESK_COMMAND_DISPLAY),
    }
    status = build_desk_status(None)
    status.update(
        {
            'enabled': True,
            'source': 'live-desk',
            'fixture_name': 'live-desk-fallback',
            'generated_at': utc_now_iso(),
            'status': 'fallback',
            'counts': {'pets_total': 0, 'pet_states': {}},
            'details': [
                {
                    'name': 'live-desk-fallback',
                    'pet_state': 'fallback',
                    'presence_state': reason,
                    'detail': 'message=%s; returncode=%s; command=%s'
                    % (message or 'none', returncode if returncode is not None else 'none', ' '.join(LIVE_DESK_COMMAND_DISPLAY)),
                }
            ],
            'primary_action': None,
            'live_mew_reads': True,
            'command': list(LIVE_DESK_COMMAND_DISPLAY),
            'fallback': fallback,
        }
    )
    return status


def fetch_live_desk_status(
    *,
    runner: DeskRunner = subprocess.run,
    mew_path: str | Path | None = None,
    timeout_seconds: float = DESK_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    command_path = Path(mew_path) if mew_path is not None else REPO_ROOT / 'mew'
    if not command_path.exists():
        return build_live_desk_fallback_status('missing_command', message=str(command_path))

    command = _live_desk_command(command_path)
    try:
        completed = runner(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds,
            shell=False,
        )
    except FileNotFoundError as exc:
        return build_live_desk_fallback_status('missing_command', message=str(exc))
    except subprocess.TimeoutExpired:
        return build_live_desk_fallback_status('timeout', message='desk command timed out')

    stdout = str(getattr(completed, 'stdout', '') or '')
    stderr = str(getattr(completed, 'stderr', '') or '')
    returncode = int(getattr(completed, 'returncode', 0) or 0)
    if returncode != 0:
        return build_live_desk_fallback_status('nonzero_exit', message=stderr.strip(), returncode=returncode)
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        return build_live_desk_fallback_status('malformed_json', message=stdout[:200])
    if not isinstance(payload, dict):
        return build_live_desk_fallback_status('non_object_json', message=type(payload).__name__)
    return _apply_live_desk_metadata(build_desk_status(payload))


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


def build_launcher_intents(
    *,
    dry_run: bool = True,
    desk_status: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    side_effects = 'none' if dry_run else 'executes_local_mew_command'
    intents = [
        {
            'id': 'mew-chat',
            'label': 'Open mew chat',
            'command': ['mew', 'chat'],
            'dry_run': dry_run,
            'side_effects': side_effects,
            'description': 'Would open the chat surface for the operator.' if dry_run else 'Opens the chat surface for the operator.',
            'source': 'local-launcher',
            'executable': True,
        },
        {
            'id': 'mew-code',
            'label': 'Open mew code',
            'command': ['mew', 'code'],
            'dry_run': dry_run,
            'side_effects': side_effects,
            'description': 'Would open the coding surface for the operator.' if dry_run else 'Opens the coding surface for the operator.',
            'source': 'local-launcher',
            'executable': True,
        },
    ]
    if desk_status and isinstance(desk_status.get('primary_action'), Mapping):
        primary_action = dict(desk_status['primary_action'])
        primary_action['id'] = 'desk-primary-action'
        primary_action['dry_run'] = True
        primary_action['side_effects'] = 'none'
        primary_action['executable'] = False
        primary_action['execution_policy'] = 'fixture_intent_never_executed_by_mew_ghost'
        intents.append(primary_action)
    return intents


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
        executable_intent = str(intent.get('id')) in EXECUTABLE_LAUNCHER_IDS and bool(intent.get('executable', True))
        if not allow_execute or bool(intent.get('dry_run', True)) or not executable_intent:
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
    desk_status: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    count = normalize_refresh_count(refresh_count)
    task = _task_mapping(fixture)
    classified = classify_presence(active_window=active_window, task=task, ghost=ghost)
    desk_presence: dict[str, Any] | None = None
    if desk_status and desk_status.get('enabled'):
        details = desk_status.get('details') if isinstance(desk_status.get('details'), list) else []
        primary_detail = details[0] if details else {}
        desk_presence = {
            'state': str(primary_detail.get('presence_state') or 'attentive'),
            'pet_state': str(primary_detail.get('pet_state') or desk_status.get('status') or 'unknown'),
            'status': desk_status.get('status'),
            'detail': primary_detail.get('detail'),
            'preserves_active_window_classification': True,
        }
    base_time = str(fixture.get('generated_at') or 'fixture-time')
    snapshots = [
        {
            'refresh_index': index,
            'rendered_at': base_time,
            'presence_state': classified['state'],
            'visual_state': classified['state'],
            'detail': classified['detail'],
            'desk_presence_state': None if desk_presence is None else desk_presence['state'],
            'desk_pet_state': None if desk_presence is None else desk_presence['pet_state'],
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
        'live_mew_reads': bool(desk_status and desk_status.get('live_mew_reads')),
        'classification': classified,
        'desk': desk_presence,
        'snapshots': snapshots,
    }


def build_ghost_state(
    fixture: Mapping[str, Any],
    *,
    probe_provider: ProbeProvider | None = None,
    platform_name: str | None = None,
    refresh_count: int | str | None = DEFAULT_REFRESH_COUNT,
    freshness: Mapping[str, Any] | None = None,
    desk_fixture: Mapping[str, Any] | None = None,
    desk_status: Mapping[str, Any] | None = None,
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
    resolved_desk_status = dict(desk_status) if desk_status is not None else build_desk_status(desk_fixture)
    presence = build_presence_loop(
        fixture=fixture,
        active_window=probe,
        ghost=ghost,
        refresh_count=refresh_count,
        desk_status=resolved_desk_status,
    )
    return {
        'schema_version': SCHEMA_VERSION,
        'fixture_name': str(fixture.get('fixture_name') or 'unknown'),
        'generated_at': str(fixture.get('generated_at') or 'fixture-time'),
        'ghost': ghost,
        'active_window': probe,
        'presence': presence,
        'desk': resolved_desk_status,
        'freshness': dict(freshness or {'mode': 'single-render', 'rendered_at': str(fixture.get('generated_at') or 'fixture-time')}),
        'launch_intents': execute_launcher_intents(build_launcher_intents(dry_run=True, desk_status=resolved_desk_status)),
    }


def render_local_html(state: Mapping[str, Any]) -> str:
    ghost = state['ghost']
    probe = state['active_window']
    presence = state['presence']
    classification = presence['classification']
    intents = state['launch_intents']
    freshness = state.get('freshness', {})
    desk = state.get('desk', {})
    desk_counts = desk.get('counts') if isinstance(desk, Mapping) and isinstance(desk.get('counts'), Mapping) else {}
    desk_details = desk.get('details') if isinstance(desk, Mapping) and isinstance(desk.get('details'), list) else []
    desk_primary = desk.get('primary_action') if isinstance(desk, Mapping) and isinstance(desk.get('primary_action'), Mapping) else None
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
    desk_detail_items = chr(10).join(
        '        <li>'
        + escape(str(detail.get('name')))
        + ': <strong>'
        + escape(str(detail.get('pet_state')))
        + '</strong> → '
        + escape(str(detail.get('presence_state')))
        + ' — '
        + escape(str(detail.get('detail') or ''))
        + '</li>'
        for detail in desk_details
    ) or '        <li>No desk pet details loaded.</li>'
    desk_primary_command = '' if desk_primary is None else ' '.join(str(part) for part in desk_primary.get('command', []))
    state_json = escape(json.dumps(state, indent=2, sort_keys=True))

    return chr(10).join(
        [
            '<!doctype html>',
            '<html lang=' + chr(39) + 'en' + chr(39) + '>',
            '  <head>',
            '    <meta charset=' + chr(39) + 'utf-8' + chr(39) + '>',
            '    <title>mew-ghost SP18 watch mode</title>',
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
            '        <h2>Desk bridge</h2>',
            '        <p><strong>Status:</strong> ' + escape(str(desk.get('status', 'disabled') if isinstance(desk, Mapping) else 'disabled')) + '</p>',
            '        <p><strong>Counts:</strong> ' + escape(json.dumps(desk_counts, sort_keys=True)) + '</p>',
            '        <p><strong>Primary action:</strong> ' + escape('none' if desk_primary is None else str(desk_primary.get('label'))) + '</p>',
            '        <p><strong>Primary command:</strong> <code>' + escape(desk_primary_command or 'none') + '</code></p>',
            '        <ul>',
            desk_detail_items,
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


def _terminal_cat_lines(presence_state: str, terminal_width: int | None = None) -> list[str]:
    form_lines = CAT_TERMINAL_FORM_BY_PRESENCE.get(
        presence_state,
        CAT_TERMINAL_FORM_BY_PRESENCE['attentive'],
    )
    resolved_width = _terminal_width() if terminal_width is None else max(0, terminal_width)
    return [_center_terminal_line(line, resolved_width) for line in form_lines]


def render_terminal_human(
    state: Mapping[str, Any],
    terminal_form: str = 'default',
    *,
    terminal_details: bool = False,
) -> str:
    ghost = state['ghost']
    probe = state['active_window']
    presence = state['presence']
    classification = presence['classification']
    freshness = state.get('freshness', {})
    desk = state.get('desk', {})
    if not isinstance(desk, Mapping):
        desk = {}
    desk_counts = desk.get('counts') if isinstance(desk.get('counts'), Mapping) else {}
    desk_details = desk.get('details') if isinstance(desk.get('details'), list) else []
    desk_primary = desk.get('primary_action') if isinstance(desk.get('primary_action'), Mapping) else None
    intents = state.get('launch_intents', [])
    watch_iteration = freshness.get('watch_iteration')
    watch_total = freshness.get('watch_total')
    iteration_label = 'single render' if watch_iteration is None else 'watch iteration %s%s' % (
        watch_iteration,
        '' if watch_total is None else ' of %s' % watch_total,
    )
    primary_label = 'none' if desk_primary is None else str(desk_primary.get('label', 'none'))
    primary_command = 'none' if desk_primary is None else ' '.join(str(part) for part in desk_primary.get('command', [])) or 'none'
    presence_state = str(classification.get('state', 'attentive'))
    state_marker = {
        'idle': 'zZ',
        'attentive': '?',
        'coding': '*',
        'waiting': '...',
        'blocked': '!',
    }.get(presence_state, '?')

    if terminal_form == 'cat':
        lines = _terminal_cat_lines(presence_state)
    elif terminal_form == 'default':
        lines = []
    else:
        raise ValueError('unsupported terminal form: %s' % terminal_form)

    def _compact_live_context(value: object, *, max_words: int = 5, max_chars: int = 72) -> str:
        raw = str(value).replace(chr(10), ' ')
        text = ''.join(
            character if 32 <= ord(character) < 127 else '?'
            for character in raw
        ).strip()
        if not text:
            return ''
        words = text.split()
        compact = ' '.join(words[:max_words])
        if len(words) > max_words:
            compact += '...'
        if len(compact) > max_chars:
            compact = compact[: max_chars - 3].rstrip() + '...'
        return compact

    def _speech_bubble_lines() -> list[str]:
        terminal_width = _terminal_width()
        left_padding = max(0, (terminal_width - CAT_TERMINAL_PIXEL_WIDTH) // 2)
        content_width = min(60, max(12, terminal_width - left_padding - 6))
        if desk.get('live_mew_reads'):
            pets_total = desk_counts.get('pets_total')
            if isinstance(pets_total, int):
                pets_label = '%s desk pet%s' % (pets_total, '' if pets_total == 1 else 's')
            else:
                pets_label = 'desk pets present'
            desk_status = str(desk.get('status') or presence_state)
            detail_bits = []
            live_context_bits = []
            for detail in desk_details[:2]:
                if not isinstance(detail, Mapping):
                    continue
                detail_name = str(detail.get('name') or 'desk-pet')
                detail_state = str(detail.get('pet_state') or detail.get('presence_state') or 'unknown')
                detail_bits.append('%s %s' % (detail_name, detail_state))
                detail_text = _compact_live_context(detail.get('detail') or detail.get('message') or detail.get('status') or '')
                if detail_text:
                    live_context_bits.append('%s: %s' % (detail_name, detail_text))
            live_context = '; '.join(live_context_bits)
            if not live_context:
                live_context = '%s - %s' % (ghost['focus'], ghost['message'])
            detail_label = '; ' + ', '.join(detail_bits) if detail_bits else ''
            speech = 'mew-wisp live desk %s: %s, status %s%s; %s' % (
                presence_state,
                pets_label,
                desk_status,
                detail_label,
                live_context,
            )
        elif desk.get('enabled'):
            desk_source = str(desk.get('source') or 'desk fixture')
            speech = 'mew-wisp %s %s: %s - %s' % (
                desk_source,
                presence_state,
                ghost['focus'],
                ghost['message'],
            )
        else:
            speech = 'mew-wisp local terminal %s: %s - %s' % (
                presence_state,
                ghost['focus'],
                ghost['message'],
            )
        text = ''.join(
            character if 32 <= ord(character) < 127 else '?'
            for character in speech.replace(chr(10), ' ')
        ).strip()
        if not text:
            text = 'mew-wisp %s' % presence_state
        wrapped: list[str] = []
        current = ''
        for word in text.split():
            while len(word) > content_width:
                if current:
                    wrapped.append(current)
                    current = ''
                wrapped.append(word[:content_width])
                word = word[content_width:]
            if not word:
                continue
            candidate = word if not current else current + ' ' + word
            if len(candidate) <= content_width:
                current = candidate
            else:
                wrapped.append(current)
                current = word
        if current:
            wrapped.append(current)
        if not wrapped:
            wrapped.append('')
        bubble_width = max(len(segment) for segment in wrapped)
        border = '+' + '-' * (bubble_width + 2) + '+'
        spacer = '| ' + ' ' * bubble_width + ' |'
        bubble_lines = [border, spacer]
        bubble_lines.extend('| ' + segment.ljust(bubble_width) + ' |' for segment in wrapped)
        bubble_lines.extend([spacer, border])
        return [_center_terminal_line(line, terminal_width) for line in bubble_lines]

    if lines:
        lines.append('')
    lines.extend(_speech_bubble_lines())
    lines.append('')

    panel_content_width = 68
    panel_border_width = panel_content_width + 2
    panel_label_width = 9
    panel_title = ' mew-wisp resident HUD '

    def _panel_safe_text(value: object) -> str:
        raw = str(value).replace(chr(10), ' ')
        return ''.join(
            character if 32 <= ord(character) < 127 else '?'
            for character in raw
        ).strip()

    def _panel_wrapped_values(value: object, value_width: int) -> list[str]:
        text = _panel_safe_text(value)
        if not text:
            return ['']
        wrapped: list[str] = []
        current = ''
        for word in text.split():
            while len(word) > value_width:
                if current:
                    wrapped.append(current)
                    current = ''
                wrapped.append(word[:value_width])
                word = word[value_width:]
            if not word:
                continue
            candidate = word if not current else current + ' ' + word
            if len(candidate) <= value_width:
                current = candidate
            else:
                wrapped.append(current)
                current = word
        if current:
            wrapped.append(current)
        return wrapped or ['']

    def _panel_title_border() -> str:
        remaining_width = panel_border_width - len(panel_title)
        left_width = remaining_width // 2
        right_width = remaining_width - left_width
        return '+' + '-' * left_width + panel_title + '-' * right_width + '+'

    def _panel_plain_border() -> str:
        return '+' + '-' * panel_border_width + '+'

    def _panel_row(label: str, value: object) -> list[str]:
        label_prefix = '%-*s ' % (panel_label_width, label + ':')
        continuation_prefix = ' ' * len(label_prefix)
        value_width = panel_content_width - len(label_prefix)
        rows: list[str] = []
        for index, segment in enumerate(_panel_wrapped_values(value, value_width)):
            prefix = label_prefix if index == 0 else continuation_prefix
            rows.append('| ' + (prefix + segment).ljust(panel_content_width) + ' |')
        return rows

    def _resident_panel_lines(panel_rows: list[tuple[str, object]]) -> list[str]:
        panel_lines = [_panel_title_border()]
        for label, value in panel_rows:
            panel_lines.extend(_panel_row(label, value))
        panel_lines.append(_panel_plain_border())
        terminal_width = _terminal_width()
        panel_width = len(panel_lines[0]) if panel_lines else 0
        padding = max(0, (terminal_width - panel_width) // 2)
        return [' ' * padding + line for line in panel_lines]

    panel_focus_value = '%s - %s' % (ghost['focus'], ghost['message'])
    if desk.get('live_mew_reads'):
        live_focus_value = ''
        for detail in desk_details[:1]:
            if not isinstance(detail, Mapping):
                continue
            detail_name = str(detail.get('name') or 'desk-pet')
            detail_text = _compact_live_context(detail.get('detail') or detail.get('message') or detail.get('status') or '')
            live_focus_value = detail_name if not detail_text else '%s - %s' % (detail_name, detail_text)
            break
        if not live_focus_value and desk.get('status'):
            live_focus_value = 'live desk status: %s' % desk.get('status')
        if not live_focus_value and desk_primary is not None:
            live_focus_value = 'action: %s' % primary_label
        if live_focus_value:
            panel_focus_value = live_focus_value

    panel_rows: list[tuple[str, object]] = [
        ('resident', 'mew-wisp | mood: %s | state: %s' % (ghost['mood'], presence_state)),
        ('focus', panel_focus_value),
        (
            'signal',
            '%s | snapshots: %s | desk: %s'
            % (presence['contract'], presence['refresh_count'], desk.get('status', 'disabled')),
        ),
        ('action', primary_label),
    ]
    if terminal_form == 'default':
        panel_rows.insert(1, ('marker', state_marker))
    lines.extend(_resident_panel_lines(panel_rows))

    if terminal_details:
        lines.extend(
            [
                'details:',
                'freshness: %s | %s | refreshed: %s | interval: %s'
                % (
                    freshness.get('mode', 'single-render'),
                    iteration_label,
                    freshness.get('rendered_at', state.get('generated_at')),
                    freshness.get('interval_seconds', 'n/a'),
                ),
                'desk: %s | counts: %s'
                % (
                    desk.get('status', 'disabled'),
                    json.dumps(
                        {key: desk_counts[key] for key in ('pets_total', 'pet_states') if key in desk_counts},
                        sort_keys=True,
                    ),
                ),
                'desk primary: %s -> %s' % (primary_label, primary_command),
            ]
        )
        if desk_details:
            lines.append('desk details:')
            for detail in desk_details:
                if not isinstance(detail, Mapping):
                    continue
                detail_text = str(detail.get('detail') or '')
                suffix = '' if not detail_text else ' - ' + detail_text
                lines.append(
                    '  - %s: %s -> %s%s'
                    % (
                        detail.get('name', 'desk pet'),
                        detail.get('pet_state', 'unknown'),
                        detail.get('presence_state', 'unknown'),
                        suffix,
                    )
                )
        else:
            lines.append('desk details: none')
        lines.extend(
            [
                'active window: %s | app: %s | window: %s | reason: %s'
                % (
                    probe['status'],
                    probe.get('active_app') or 'unavailable',
                    probe.get('window_title') or 'unavailable',
                    probe.get('reason') or 'none',
                ),
                'launcher intents:',
            ]
        )
        for intent in intents:
            if not isinstance(intent, Mapping):
                continue
            command = ' '.join(str(part) for part in intent.get('command', [])) or 'none'
            execution = 'dry-run' if intent.get('dry_run', True) else 'execute'
            lines.append('  - %s: %s (%s)' % (intent.get('id', 'launcher'), command, execution))
        if lines[-1] == 'launcher intents:':
            lines.append('  - none')
    return chr(10).join(lines) + chr(10)


def render_fixture(
    path: str | Path = DEFAULT_FIXTURE,
    *,
    probe_provider: ProbeProvider | None = None,
    platform_name: str | None = None,
    refresh_count: int | str | None = DEFAULT_REFRESH_COUNT,
    freshness: Mapping[str, Any] | None = None,
    desk_path: str | Path | None = None,
    desk_status: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], str]:
    fixture = load_fixture(path)
    desk_fixture = load_desk_fixture(desk_path) if desk_path is not None else None
    state = build_ghost_state(
        fixture,
        probe_provider=probe_provider,
        platform_name=platform_name,
        refresh_count=refresh_count,
        freshness=freshness,
        desk_fixture=desk_fixture,
        desk_status=desk_status,
    )
    return state, render_local_html(state)


def _render_payload(
    state: Mapping[str, Any],
    html: str,
    format_name: str,
    terminal_form: str = 'default',
    terminal_details: bool = False,
) -> str:
    if format_name == 'state':
        return json.dumps(state, indent=2, sort_keys=True) + chr(10)
    if format_name == 'human':
        return render_terminal_human(state, terminal_form=terminal_form, terminal_details=terminal_details)
    if format_name == 'html':
        return html
    raise ValueError('unsupported format: %s' % format_name)


def _watch_record(
    state: Mapping[str, Any],
    *,
    format_name: str,
    rendered: str,
    output_path: Path | None,
    launchers_executed: bool,
) -> dict[str, Any]:
    freshness = state['freshness']
    desk = state.get('desk', {})
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
        'desk_status': desk.get('status') if isinstance(desk, Mapping) else None,
        'desk_primary_action': desk.get('primary_action') if isinstance(desk, Mapping) else None,
        'active_window_status': state['active_window']['status'],
        'active_app': state['active_window'].get('active_app'),
        'launcher_execution_requested': launchers_executed,
    }
    if format_name == 'state':
        record['state'] = state
    elif output_path is None:
        if format_name == 'human':
            record['human'] = rendered
        else:
            record['html'] = rendered
    return record


def run_watch(
    fixture_path: str | Path = DEFAULT_FIXTURE,
    *,
    desk_path: str | Path | None = None,
    desk_provider: DeskProvider | None = None,
    format_name: str = 'html',
    terminal_form: str = 'default',
    terminal_details: bool = False,
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
                'live_mew_reads': bool(desk_provider),
            }
            desk_status = desk_provider() if desk_provider is not None else None
            state, html = render_fixture(
                fixture_path,
                probe_provider=probe_provider,
                platform_name=platform_name,
                refresh_count=1,
                freshness=freshness,
                desk_path=desk_path,
                desk_status=desk_status,
            )
            if execute_launchers:
                state['launch_intents'] = execute_launcher_intents(
                    build_launcher_intents(dry_run=False, desk_status=state.get('desk')),
                    allow_execute=True,
                    runner=launcher_runner or subprocess.run,
                )
                html = render_local_html(state)
            rendered = _render_payload(
                state,
                html,
                format_name,
                terminal_form=terminal_form,
                terminal_details=terminal_details,
            )
            if output_path is not None:
                output_path.write_text(rendered, encoding='utf-8')
            if format_name == 'human' and output_path is None:
                stream.write('\x1b[H\x1b[J')
                stream.write(rendered)
                stream.flush()
            else:
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
    live_desk_provider: DeskProvider | None = None,
    live_desk_runner: DeskRunner | None = None,
    launcher_runner: LauncherRunner | None = None,
    sleeper: Sleeper = time.sleep,
    clock: Clock = utc_now_iso,
    platform_name: str | None = None,
) -> int:
    parser = argparse.ArgumentParser(description='Render the SP18 mew-ghost watch-mode shell')
    parser.add_argument('--fixture', default=str(DEFAULT_FIXTURE), help='local JSON fixture to render')
    parser.add_argument('--desk-json', help='static mew desk JSON-style fixture to bridge into ghost state')
    parser.add_argument('--live-desk', action='store_true', help='explicitly opt into repo-local live desk JSON state')
    parser.add_argument('--fixture-terminal', action='store_true', help='render the deterministic fixture terminal instead of the default repo-local live desk terminal')
    parser.add_argument('--output', help='write rendered output to this path')
    parser.add_argument('--format', choices=('html', 'state', 'human'), default=None, help='render format; defaults to html unless --wisp sets human')
    parser.add_argument('--form', choices=TERMINAL_FORMS, default=None, help='terminal form for --format human; defaults to default unless --wisp sets cat')
    parser.add_argument('--wisp', action='store_true', help='start the live human cat foreground watch preset; explicit --format/--form choices and --watch-count still win')
    parser.add_argument('--details', action='store_true', help='include diagnostic details in --format human output')
    parser.add_argument('--refresh-count', type=int, default=DEFAULT_REFRESH_COUNT, help='single-render snapshot count, clamped locally')
    parser.add_argument('--watch', action='store_true', help='run foreground watch until KeyboardInterrupt')
    parser.add_argument('--watch-count', type=int, help='run exactly this many foreground watch iterations')
    parser.add_argument('--interval', type=float, default=DEFAULT_WATCH_INTERVAL_SECONDS, help='seconds to sleep between watch iterations')
    parser.add_argument('--live-active-window', action='store_true', help='explicitly opt into the macOS osascript active app/window probe')
    parser.add_argument('--execute-launchers', action='store_true', help='explicitly opt into running mew chat and mew code; dry-run remains the default')
    args = parser.parse_args(argv)

    if args.format is None:
        args.format = 'human' if args.wisp else 'html'
    if args.form is None:
        args.form = 'cat' if args.wisp else 'default'
    if args.wisp and not args.watch and args.watch_count is None:
        args.watch = True

    if args.watch_count is not None and args.watch_count < 1:
        parser.error('--watch-count must be a positive integer')
    if args.interval < 0:
        parser.error('--interval must be non-negative')
    if args.live_desk and args.desk_json:
        parser.error('--live-desk cannot be combined with --desk-json')
    if args.fixture_terminal and args.format != 'human':
        parser.error('--fixture-terminal only applies to --format human')
    if args.fixture_terminal and args.live_desk:
        parser.error('--fixture-terminal cannot be combined with --live-desk')

    provider = None
    if args.live_active_window:
        provider = live_probe_provider or make_macos_osascript_probe_provider()

    use_live_desk = args.live_desk or (
        args.format == 'human' and not args.fixture_terminal and not args.desk_json
    )
    desk_provider = None
    if use_live_desk:
        desk_provider = live_desk_provider or (lambda: fetch_live_desk_status(runner=live_desk_runner or subprocess.run))

    if args.watch or args.watch_count is not None:
        return run_watch(
            args.fixture,
            desk_path=args.desk_json,
            desk_provider=desk_provider,
            format_name=args.format,
            terminal_form=args.form,
            terminal_details=args.details,
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

    desk_status = desk_provider() if desk_provider is not None else None
    state, html = render_fixture(
        args.fixture,
        probe_provider=provider,
        platform_name=platform_name,
        refresh_count=args.refresh_count,
        desk_path=args.desk_json,
        desk_status=desk_status,
    )
    if args.execute_launchers:
        state['launch_intents'] = execute_launcher_intents(
            build_launcher_intents(dry_run=False, desk_status=state.get('desk')),
            allow_execute=True,
            runner=launcher_runner or subprocess.run,
        )
        html = render_local_html(state)
    rendered = _render_payload(
        state,
        html,
        args.format,
        terminal_form=args.form,
        terminal_details=args.details,
    )
    if args.output:
        Path(args.output).write_text(rendered, encoding='utf-8')
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
