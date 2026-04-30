from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README_PATH = ROOT / 'README.md'
GHOST_PATH = ROOT / 'ghost.py'
WISP_PATH = ROOT / 'mew_wisp.py'
FIXTURE_PATH = ROOT / 'fixtures' / 'sample_ghost_state.json'
DESK_FIXTURE_PATH = ROOT / 'fixtures' / 'sample_desk_view.json'

spec = importlib.util.spec_from_file_location('mew_ghost_sp18', GHOST_PATH)
ghost = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(ghost)


def test_product_named_mew_wisp_entrypoint_delegates_to_ghost_main_without_cli_duplication() -> None:
    source = WISP_PATH.read_text(encoding='utf-8')

    assert 'from ghost import main' in source
    assert 'argparse' not in source
    assert 'subprocess' not in source
    assert 'import mew' not in source
    assert 'shell' not in source

    previous_path = list(sys.path)
    previous_ghost = sys.modules.pop('ghost', None)
    try:
        sys.path.insert(0, str(ROOT))
        wisp_spec = importlib.util.spec_from_file_location('mew_wisp_entrypoint', WISP_PATH)
        mew_wisp = importlib.util.module_from_spec(wisp_spec)
        assert wisp_spec.loader is not None
        wisp_spec.loader.exec_module(mew_wisp)
    finally:
        sys.path[:] = previous_path
        if previous_ghost is None:
            sys.modules.pop('ghost', None)
        else:
            sys.modules['ghost'] = previous_ghost

    assert mew_wisp.main.__name__ == 'main'
    assert Path(mew_wisp.main.__code__.co_filename).resolve() == GHOST_PATH


def test_cli_help_presents_mew_wisp_resident_entrypoint_and_compatibility(capsys) -> None:
    original_argv = sys.argv[:]
    sys.argv = [str(WISP_PATH), '--help']
    try:
        try:
            ghost.main(None)
        except SystemExit as exc:
            assert exc.code == 0
        else:
            raise AssertionError('--help should exit through argparse')
    finally:
        sys.argv = original_argv

    help_text = capsys.readouterr().out
    normalized_help = ' '.join(help_text.split())

    assert 'Run the mew-wisp resident terminal' in normalized_help
    assert 'ghost.py remains the compatibility implementation' in normalized_help
    assert 'explicit --output keeps compatibility HTML/state flows' in normalized_help
    assert 'normal mew-wisp resident human cat foreground watch preset' in normalized_help
    assert 'Render the SP18 mew-ghost watch-mode shell' not in normalized_help


def test_product_named_entrypoint_omitted_mode_form_and_watch_defaults_to_resident(capsys, tmp_path: Path) -> None:
    repo_root = tmp_path / 'repo'
    repo_root.mkdir()
    mew_path = repo_root / 'mew'
    mew_path.write_text('#!/bin/sh\n', encoding='utf-8')
    original_repo_root = ghost.REPO_ROOT
    original_argv = sys.argv[:]
    calls: list[list[str]] = []
    sleeps: list[float] = []

    def forbidden_launcher(*_args: object, **_kwargs: object) -> None:
        raise AssertionError('launcher runner must not be called for product default proof')

    def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        assert kwargs['shell'] is False
        payload = {
            'fixture_name': 'product-entrypoint-default',
            'desk': {
                'status': 'typing',
                'pets': [
                    {
                        'name': 'mew-wisp',
                        'pet_state': 'coding',
                        'detail': 'product entrypoint default',
                    }
                ],
                'primary_action': {
                    'id': 'resume',
                    'label': 'Resume resident task',
                    'command': ['mew', 'code'],
                },
            },
        }
        return _completed_process(stdout=json.dumps(payload), returncode=0)

    def sleeper(interval: float) -> None:
        sleeps.append(interval)
        raise KeyboardInterrupt

    ghost.REPO_ROOT = repo_root
    sys.argv = [str(WISP_PATH), '--fixture', str(FIXTURE_PATH), '--interval', '0']
    try:
        assert ghost.main(
            None,
            live_desk_runner=runner,
            launcher_runner=forbidden_launcher,
            sleeper=sleeper,
        ) == 0
    finally:
        ghost.REPO_ROOT = original_repo_root
        sys.argv = original_argv

    output = capsys.readouterr().out

    assert calls == [[str(mew_path), 'desk', '--json']]
    assert sleeps == [0.0]
    assert 'mew-wisp resident cat' in output
    assert 'resident state: coding' in output
    assert '<!doctype html>' not in output
    assert '"record_type"' not in output


def test_product_named_entrypoint_output_requires_explicit_format(capsys, tmp_path: Path) -> None:
    output_path = tmp_path / 'mew-wisp.html'
    original_argv = sys.argv[:]
    calls: list[list[str]] = []

    def forbidden_runner(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        raise AssertionError('live desk runner must not be called for rejected output default')

    sys.argv = [str(WISP_PATH), '--fixture', str(FIXTURE_PATH), '--output', str(output_path)]
    try:
        try:
            ghost.main(None, live_desk_runner=forbidden_runner)
        except SystemExit as exc:
            exit_code = exc.code
        else:
            raise AssertionError('mew_wisp.py --output without --format should fail')
    finally:
        sys.argv = original_argv

    captured = capsys.readouterr()

    assert exit_code == 2
    assert calls == []
    assert captured.out == ''
    assert 'mew_wisp.py --output requires explicit --format html or --format state' in captured.err
    assert not output_path.exists()


def test_product_named_entrypoint_output_accepts_explicit_html_format(capsys, tmp_path: Path) -> None:
    output_path = tmp_path / 'mew-wisp.html'
    original_argv = sys.argv[:]
    calls: list[list[str]] = []

    def forbidden_runner(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        raise AssertionError('live desk runner must not be called for explicit html output')

    sys.argv = [str(WISP_PATH), '--fixture', str(FIXTURE_PATH), '--format', 'html', '--output', str(output_path)]
    try:
        assert ghost.main(None, live_desk_runner=forbidden_runner) == 0
    finally:
        sys.argv = original_argv

    rendered = output_path.read_text(encoding='utf-8')

    assert calls == []
    assert capsys.readouterr().out == ''
    assert '<!doctype html>' in rendered
    assert '<title>mew-wisp resident state (ghost.py compatibility render)</title>' in rendered
    assert '<h2>Resident state (ghost.py compatibility)</h2>' in rendered
    assert 'mew-wisp resident cat' not in rendered


def test_product_named_entrypoint_output_accepts_explicit_state_format(capsys, tmp_path: Path) -> None:
    output_path = tmp_path / 'mew-wisp.json'
    original_argv = sys.argv[:]
    calls: list[list[str]] = []

    def forbidden_runner(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        raise AssertionError('live desk runner must not be called for explicit state output')

    sys.argv = [str(WISP_PATH), '--fixture', str(FIXTURE_PATH), '--format', 'state', '--output', str(output_path)]
    try:
        assert ghost.main(None, live_desk_runner=forbidden_runner) == 0
    finally:
        sys.argv = original_argv

    rendered = output_path.read_text(encoding='utf-8')

    assert calls == []
    assert capsys.readouterr().out == ''
    assert '"schema_version": "mew-ghost.sp18.v1"' in rendered
    assert '<!doctype html>' not in rendered
    assert 'mew-wisp resident cat' not in rendered


def test_compatibility_entrypoint_output_keeps_historical_html_default(capsys, tmp_path: Path) -> None:
    output_path = tmp_path / 'ghost.html'
    calls: list[list[str]] = []

    def forbidden_runner(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        raise AssertionError('live desk runner must not be called for compatibility output default')

    assert ghost.main(['--fixture', str(FIXTURE_PATH), '--output', str(output_path)], live_desk_runner=forbidden_runner) == 0

    rendered = output_path.read_text(encoding='utf-8')

    assert calls == []
    assert capsys.readouterr().out == ''
    assert '<!doctype html>' in rendered
    assert '<title>mew-wisp resident state (ghost.py compatibility render)</title>' in rendered
    assert '<h2>Resident state (ghost.py compatibility)</h2>' in rendered
    assert 'mew-wisp resident cat' not in rendered


def test_fixture_builds_deterministic_state_and_html() -> None:
    fixture = ghost.load_fixture(FIXTURE_PATH)

    state_one = ghost.build_ghost_state(fixture)
    state_two = ghost.build_ghost_state(fixture)
    html_one = ghost.render_local_html(state_one)
    html_two = ghost.render_local_html(state_two)

    assert state_one == state_two
    assert html_one == html_two
    assert state_one['schema_version'] == 'mew-ghost.sp18.v1'
    assert state_one['active_window']['status'] == 'available'
    assert state_one['active_window']['active_app'] == 'Visual Studio Code'
    assert state_one['presence']['classification']['state'] == 'coding'
    assert [snapshot['presence_state'] for snapshot in state_one['presence']['snapshots']] == ['coding', 'coding', 'coding']
    assert 'mew-wisp is keeping VS Code in view without screen capture.' in html_one
    assert 'Ghost is watching' not in html_one
    assert 'Writing the SP12 scaffold' in html_one
    assert 'mew-ghost.sp18.v1' in html_one
    assert 'Freshness' in html_one


def test_presence_classifies_idle_attentive_coding_waiting_and_blocked() -> None:
    base_probe = {'status': 'available', 'reason': None, 'active_app': 'Notes', 'window_title': 'planning'}

    idle = ghost.classify_presence(active_window={'status': 'unavailable', 'reason': 'requires_macos'}, task={'status': 'ready'}, ghost={'focus': 'local shell'})
    attentive = ghost.classify_presence(active_window=base_probe, task={'status': 'ready'})
    coding = ghost.classify_presence(active_window={**base_probe, 'active_app': 'Visual Studio Code', 'window_title': 'ghost.py'}, task={'status': 'ready', 'kind': 'coding'})
    waiting = ghost.classify_presence(active_window=base_probe, task={'status': 'waiting'})
    blocked = ghost.classify_presence(active_window={'status': 'permission_denied'}, task={'status': 'ready'})

    assert [idle['state'], attentive['state'], coding['state'], waiting['state'], blocked['state']] == ['idle', 'attentive', 'coding', 'waiting', 'blocked']
    assert blocked['allowed_states'] == ['idle', 'attentive', 'coding', 'waiting', 'blocked']


def test_presence_loop_is_bounded_deterministic_and_fixture_safe() -> None:
    fixture = ghost.load_fixture(FIXTURE_PATH)

    state_one = ghost.build_ghost_state(fixture, refresh_count=99)
    state_two = ghost.build_ghost_state(fixture, refresh_count=99)

    assert state_one['presence'] == state_two['presence']
    assert state_one['presence']['refresh_count'] == ghost.MAX_REFRESH_COUNT
    assert len(state_one['presence']['snapshots']) == ghost.MAX_REFRESH_COUNT
    assert state_one['presence']['background_monitoring'] is False
    assert state_one['presence']['hidden_capture'] is False
    assert state_one['presence']['network'] is False
    assert state_one['presence']['live_mew_reads'] is False
    assert [snapshot['refresh_index'] for snapshot in state_one['presence']['snapshots']] == list(range(ghost.MAX_REFRESH_COUNT))


def test_probe_contract_is_safe_without_accessibility_or_live_api() -> None:
    calls: list[str] = []

    def provider() -> dict[str, str]:
        calls.append('called')
        return {'active_app': 'Should Not Be Called'}

    unavailable = ghost.probe_active_window(provider, platform_name='Linux')

    assert calls == []
    assert unavailable == {
        'schema_version': 'mew-ghost.sp18.v1',
        'status': 'unavailable',
        'reason': 'requires_macos',
        'platform': 'Linux',
        'active_app': None,
        'window_title': None,
        'requires_permission': False,
    }

    deferred = ghost.probe_active_window(platform_name='Darwin')
    assert deferred['status'] == 'unavailable'
    assert deferred['reason'] == 'live_probe_not_requested'
    assert deferred['requires_permission'] is True


def test_probe_contract_reports_permission_denied_structurally() -> None:
    def denied_provider() -> dict[str, str]:
        raise PermissionError('Accessibility denied')

    denied = ghost.probe_active_window(denied_provider, platform_name='Darwin')

    assert denied['status'] == 'permission_denied'
    assert denied['reason'] == 'accessibility_permission_denied'
    assert denied['active_app'] is None
    assert denied['window_title'] is None
    assert denied['requires_permission'] is True


def test_probe_contract_accepts_injected_success_provider() -> None:
    observed = ghost.probe_active_window(
        lambda: {'active_app': 'Terminal', 'window_title': 'mew work 12', 'requires_permission': True},
        platform_name='Darwin',
    )

    assert observed['status'] == 'available'
    assert observed['reason'] is None
    assert observed['active_app'] == 'Terminal'
    assert observed['window_title'] == 'mew work 12'


def _completed_process(*, stdout: str = '', stderr: str = '', returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=['osascript'], returncode=returncode, stdout=stdout, stderr=stderr)


def test_live_desk_status_uses_injected_runner_without_shell_and_normalizes_surface(tmp_path: Path) -> None:
    mew_path = tmp_path / 'mew'
    mew_path.write_text('#!/bin/sh\n', encoding='utf-8')
    calls: list[tuple[list[str], dict[str, object]]] = []

    def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append((command, kwargs))
        payload = {
            'fixture_name': 'live-sample',
            'desk': {
                'status': 'typing',
                'pets': [{'name': 'mew', 'pet_state': 'typing', 'detail': 'live task'}],
                'primary_action': {'id': 'resume', 'label': 'Resume live task', 'command': ['mew', 'code']},
            },
        }
        return _completed_process(stdout=json.dumps(payload), returncode=0)

    status = ghost.fetch_live_desk_status(runner=runner, mew_path=mew_path, timeout_seconds=0.25)

    assert calls[0][0] == [str(mew_path), 'desk', '--json']
    assert calls[0][1]['capture_output'] is True
    assert calls[0][1]['text'] is True
    assert calls[0][1]['check'] is False
    assert calls[0][1]['timeout'] == 0.25
    assert calls[0][1]['shell'] is False
    assert status['source'] == 'live-desk'
    assert status['live_mew_reads'] is True
    assert status['command'] == ['./mew', 'desk', '--json']
    assert status['fallback'] is None
    assert status['status'] == 'typing'
    assert status['counts']['pets_total'] == 1
    assert status['details'][0]['presence_state'] == 'coding'
    assert status['primary_action']['source'] == 'live-desk'
    assert status['primary_action']['description'] == (
        'Live desk primary_action is a dry-run hint from opted-in live desk JSON; '
        'mew-ghost never executes it.'
    )
    assert status['primary_action']['dry_run'] is True
    assert status['primary_action']['executable'] is False


def test_live_desk_status_normalizes_current_top_level_live_shape_with_injected_runner(tmp_path: Path) -> None:
    mew_path = tmp_path / 'mew'
    mew_path.write_text('#!/bin/sh\n', encoding='utf-8')
    calls: list[tuple[list[str], dict[str, object]]] = []

    def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append((command, kwargs))
        payload = {
            'pet_state': 'sleeping',
            'focus': {'summary': 'review queue', 'detail': 'resting on current branch'},
            'counts': {'queue': {'ready': 2}, 'actions': 1},
            'details': {'current_task': {'title': 'SP18'}, 'watch': 'foreground'},
            'actions': [
                {
                    'id': 'resume',
                    'label': 'Resume live desk',
                    'command': ['mew', 'work', '18'],
                    'description': 'Resume provided by live desk.',
                }
            ],
            'current_git': {'branch': 'sp18-live-desk', 'dirty': True},
        }
        return _completed_process(stdout=json.dumps(payload), returncode=0)

    status = ghost.fetch_live_desk_status(runner=runner, mew_path=mew_path, timeout_seconds=0.25)

    assert calls[0][0] == [str(mew_path), 'desk', '--json']
    assert calls[0][1]['shell'] is False
    assert status['source'] == 'live-desk'
    assert status['live_mew_reads'] is True
    assert status['fallback'] is None
    assert status['status'] == 'sleeping'
    assert status['counts']['queue'] == {'ready': 2}
    assert status['counts']['actions'] == 1
    assert status['counts']['pets_total'] == 1
    assert status['counts']['pet_states'] == {'sleeping': 1}
    assert status['counts']['raw_grouped_details']['current_task']['title'] == 'SP18'
    assert status['details'][0]['pet_state'] == 'sleeping'
    assert status['details'][0]['presence_state'] == 'idle'
    assert status['details'][0]['detail'] == 'resting on current branch'
    assert status['details'][0]['focus']['summary'] == 'review queue'
    assert status['details'][0]['raw_grouped_details']['watch'] == 'foreground'
    assert status['details'][0]['current_git']['branch'] == 'sp18-live-desk'
    assert status['primary_action']['source'] == 'live-desk'
    assert status['primary_action']['command'] == ['mew', 'work', '18']
    assert status['primary_action']['description'] == 'Resume provided by live desk.'
    assert status['primary_action']['dry_run'] is True
    assert status['primary_action']['executable'] is False

    state = ghost.build_ghost_state(ghost.load_fixture(FIXTURE_PATH), desk_status=status)
    terminal = ghost.render_terminal_human(state)
    focus_lines = [line for line in terminal.splitlines() if 'focus:' in line]

    assert len(focus_lines) == 1
    assert 'desk-pet-0 - resting on current branch' in focus_lines[0]
    assert 'Writing the SP12 scaffold' not in focus_lines[0]
    assert 'action:   Resume live desk' in terminal


def test_live_desk_status_reports_structured_fallbacks_without_real_subprocesses(tmp_path: Path) -> None:
    mew_path = tmp_path / 'mew'
    mew_path.write_text('#!/bin/sh\n', encoding='utf-8')

    missing = ghost.fetch_live_desk_status(runner=lambda command, **kwargs: _completed_process(), mew_path=tmp_path / 'missing')
    nonzero = ghost.fetch_live_desk_status(runner=lambda command, **kwargs: _completed_process(stderr='boom', returncode=7), mew_path=mew_path)

    def timeout_runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(cmd=command, timeout=kwargs.get('timeout'))

    timed_out = ghost.fetch_live_desk_status(runner=timeout_runner, mew_path=mew_path)
    malformed = ghost.fetch_live_desk_status(runner=lambda command, **kwargs: _completed_process(stdout='{not json'), mew_path=mew_path)
    non_object = ghost.fetch_live_desk_status(runner=lambda command, **kwargs: _completed_process(stdout='[]'), mew_path=mew_path)

    observed = [missing, nonzero, timed_out, malformed, non_object]
    assert [status['fallback']['reason'] for status in observed] == [
        'missing_command',
        'nonzero_exit',
        'timeout',
        'malformed_json',
        'non_object_json',
    ]
    assert all(status['source'] == 'live-desk' for status in observed)
    assert all(status['live_mew_reads'] is True for status in observed)
    assert all(status['status'] == 'fallback' for status in observed)
    assert nonzero['fallback']['returncode'] == 7


def test_live_osascript_provider_parses_injected_runner_success() -> None:
    calls: list[tuple[list[str], dict[str, object]]] = []

    def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append((command, kwargs))
        return _completed_process(stdout='Terminal\tmew work 13\n')

    provider = ghost.make_macos_osascript_probe_provider(runner=runner, osascript_path='/usr/bin/osascript', timeout_seconds=0.5)
    observed = ghost.probe_active_window(provider, platform_name='Darwin')

    assert observed['status'] == 'available'
    assert observed['reason'] is None
    assert observed['active_app'] == 'Terminal'
    assert observed['window_title'] == 'mew work 13'
    assert calls[0][0] == ['/usr/bin/osascript', '-e', ghost.ACTIVE_WINDOW_OSASCRIPT]
    assert calls[0][1]['timeout'] == 0.5


def test_live_probe_reports_missing_osascript_without_calling_runner() -> None:
    calls: list[str] = []

    def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append('called')
        return _completed_process(stdout='Terminal\tmew work 13\n')

    provider = ghost.make_macos_osascript_probe_provider(runner=runner, which=lambda name: None)
    observed = ghost.probe_active_window(provider, platform_name='Darwin')

    assert calls == []
    assert observed['status'] == 'unavailable'
    assert observed['reason'] == 'missing_osascript'
    assert observed['requires_permission'] is True


def test_live_probe_reports_permission_denied_from_osascript_stderr() -> None:
    def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        return _completed_process(returncode=1, stderr='Not authorized to send Apple events to System Events')

    provider = ghost.make_macos_osascript_probe_provider(runner=runner, osascript_path='/usr/bin/osascript')
    observed = ghost.probe_active_window(provider, platform_name='Darwin')

    assert observed['status'] == 'permission_denied'
    assert observed['reason'] == 'accessibility_permission_denied'
    assert observed['active_app'] is None
    assert observed['window_title'] is None


def test_live_probe_reports_empty_malformed_and_timeout_results() -> None:
    empty_provider = ghost.make_macos_osascript_probe_provider(runner=lambda command, **kwargs: _completed_process(stdout='\n'), osascript_path='/usr/bin/osascript')
    malformed_provider = ghost.make_macos_osascript_probe_provider(runner=lambda command, **kwargs: _completed_process(stdout='Terminal only\n'), osascript_path='/usr/bin/osascript')

    def timeout_runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(cmd=command, timeout=kwargs.get('timeout'))

    timeout_provider = ghost.make_macos_osascript_probe_provider(runner=timeout_runner, osascript_path='/usr/bin/osascript')

    empty = ghost.probe_active_window(empty_provider, platform_name='Darwin')
    malformed = ghost.probe_active_window(malformed_provider, platform_name='Darwin')
    timed_out = ghost.probe_active_window(timeout_provider, platform_name='Darwin')

    assert empty['status'] == 'unavailable'
    assert empty['reason'] == 'empty_probe_result'
    assert malformed['status'] == 'unavailable'
    assert malformed['reason'] == 'malformed_probe_result'
    assert timed_out['status'] == 'unavailable'
    assert timed_out['reason'] == 'osascript_timeout'


def test_launcher_intents_are_dry_run_by_default_and_execute_only_when_allowed() -> None:
    intents = ghost.build_launcher_intents()

    assert [intent['id'] for intent in intents] == ['mew-chat', 'mew-code']
    assert [intent['command'] for intent in intents] == [['mew', 'chat'], ['mew', 'code']]
    assert all(intent['dry_run'] is True for intent in intents)
    assert all(intent['side_effects'] == 'none' for intent in intents)

    dry_run_results = ghost.execute_launcher_intents(intents)
    assert [result['execution']['status'] for result in dry_run_results] == ['dry_run', 'dry_run']
    assert all(result['execution']['executed'] is False for result in dry_run_results)

    calls: list[list[str]] = []

    def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        assert kwargs['capture_output'] is True
        assert kwargs['text'] is True
        assert kwargs['check'] is False
        return _completed_process()

    executable = ghost.build_launcher_intents(dry_run=False)
    executed = ghost.execute_launcher_intents(executable, allow_execute=True, runner=runner)

    assert calls == [['mew', 'chat'], ['mew', 'code']]
    assert all(result['dry_run'] is False for result in executed)
    assert [result['execution']['status'] for result in executed] == ['executed', 'executed']


def test_desk_fixture_loads_status_counts_mapping_and_primary_action() -> None:
    fixture = ghost.load_fixture(FIXTURE_PATH)
    desk_fixture = ghost.load_desk_fixture(DESK_FIXTURE_PATH)

    state = ghost.build_ghost_state(fixture, desk_fixture=desk_fixture)

    assert state['presence']['classification']['state'] == 'coding'
    assert state['desk']['enabled'] is True
    assert state['desk']['status'] == 'typing'
    assert state['desk']['counts']['pets_total'] == 4
    assert state['desk']['counts']['pet_states'] == {'sleeping': 1, 'thinking': 1, 'typing': 1, 'alerting': 1}
    assert [detail['presence_state'] for detail in state['desk']['details']] == ['idle', 'attentive', 'coding', 'waiting']
    assert state['presence']['desk']['state'] == 'idle'
    assert state['presence']['desk']['preserves_active_window_classification'] is True
    assert state['presence']['snapshots'][0]['desk_presence_state'] == 'idle'
    assert state['desk']['primary_action']['command'] == ['mew', 'code', '--task', '17']
    assert state['desk']['primary_action']['dry_run'] is True

    desk_intent = state['launch_intents'][-1]
    assert desk_intent['id'] == 'desk-primary-action'
    assert desk_intent['execution']['status'] == 'dry_run'
    assert desk_intent['execution']['executed'] is False


def test_cli_renders_desk_json_state_and_html(tmp_path: Path) -> None:
    html_output = tmp_path / 'desk.html'
    state_output = tmp_path / 'desk-state.json'

    assert ghost.main(['--fixture', str(FIXTURE_PATH), '--desk-json', str(DESK_FIXTURE_PATH), '--format', 'state', '--output', str(state_output)]) == 0
    assert ghost.main(['--fixture', str(FIXTURE_PATH), '--desk-json', str(DESK_FIXTURE_PATH), '--format', 'html', '--output', str(html_output)]) == 0

    state = json.loads(state_output.read_text(encoding='utf-8'))
    html = html_output.read_text(encoding='utf-8')

    assert state['desk']['source'] == 'desk-json-fixture'
    assert state['desk']['primary_action']['label'] == 'Resume SP17 desk bridge'
    assert state['presence']['classification']['state'] == 'coding'
    assert 'Desk bridge' in html
    assert 'Resume SP17 desk bridge' in html
    assert 'mew code --task 17' in html
    assert 'typing' in html


def test_cli_fixture_terminal_renders_deterministic_human_for_desk_fixture(capsys, tmp_path: Path) -> None:
    human_output = tmp_path / 'desk-human.txt'

    assert ghost.main(['--fixture', str(FIXTURE_PATH), '--desk-json', str(DESK_FIXTURE_PATH), '--format', 'human', '--output', str(human_output)]) == 0

    human = human_output.read_text(encoding='utf-8')

    human_panel = _resident_panel_lines(human)
    human_lines = human.splitlines()
    human_bubble = _speech_bubble_lines(human)
    assert human_bubble
    assert human_lines.index(human_bubble[0]) < _panel_start_index(human)
    assert 'mew-wisp resident HUD' not in '\n'.join(human_bubble)
    assert 'mew-wisp resident HUD' in human_panel[0]
    assert _resident_panel_values(human, 'resident') == ['mew-wisp | mood: curious | state: coding']
    assert _resident_panel_values(human, 'marker') == ['*']
    assert 'focus:' in human
    assert 'signal:' in human
    assert 'desk:' in human
    assert _resident_panel_values(human, 'action') == ['Resume SP17 desk bridge']
    assert 'hud: mew-ghost' not in human
    assert 'next:' not in human
    assert 'freshness:' not in human
    assert 'desk primary:' not in human
    assert 'desk details:' not in human
    assert 'active window:' not in human
    assert 'launcher intents:' not in human
    assert '<!doctype html>' not in human
    assert '"schema_version"' not in human

    details_output = tmp_path / 'desk-human-details.txt'
    assert ghost.main(['--fixture', str(FIXTURE_PATH), '--desk-json', str(DESK_FIXTURE_PATH), '--format', 'human', '--details', '--output', str(details_output)]) == 0

    details = details_output.read_text(encoding='utf-8')

    details_panel = _resident_panel_lines(details)
    details_lines = details.splitlines()
    details_bubble = _speech_bubble_lines(details)
    assert details_bubble
    assert details_lines.index(details_bubble[0]) < _panel_start_index(details)
    assert 'mew-wisp resident HUD' not in '\n'.join(details_bubble)
    assert 'mew-wisp resident HUD' in details_panel[0]
    assert 'details:\n' in details
    assert 'freshness:' in details
    assert 'desk:' in details
    assert 'desk primary:' in details
    assert 'desk details:' in details
    assert 'active window:' in details
    assert 'launcher intents:' in details
    assert '<!doctype html>' not in details
    assert '"schema_version"' not in details

    assert ghost.main(['--fixture', str(FIXTURE_PATH), '--format', 'human', '--fixture-terminal']) == 0
    stdout = capsys.readouterr().out

    stdout_panel = _resident_panel_lines(stdout)
    stdout_lines = stdout.splitlines()
    stdout_bubble = _speech_bubble_lines(stdout)
    assert stdout_bubble
    assert stdout_lines.index(stdout_bubble[0]) < _panel_start_index(stdout)
    assert 'mew-wisp resident HUD' not in '\n'.join(stdout_bubble)
    assert 'mew-wisp resident HUD' in stdout_panel[0]
    assert 'resident: mew-wisp' in stdout
    assert 'hud: mew-ghost' not in stdout
    assert 'next:' not in stdout
    assert 'launcher intents:' not in stdout


def test_cli_live_desk_opt_in_uses_injected_runner_without_spawning(capsys, tmp_path: Path) -> None:
    repo_root = tmp_path / 'repo'
    repo_root.mkdir()
    mew_path = repo_root / 'mew'
    mew_path.write_text('#!/bin/sh\n', encoding='utf-8')
    original_repo_root = ghost.REPO_ROOT
    calls: list[list[str]] = []

    def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        assert kwargs['shell'] is False
        payload = {
            'fixture_name': 'cli-live-desk',
            'desk': {
                'status': 'typing',
                'pets': [{'name': 'mew', 'pet_state': 'typing', 'detail': 'live CLI task'}],
                'primary_action': {'id': 'resume', 'label': 'Resume live CLI task', 'command': ['mew', 'code']},
            },
        }
        return _completed_process(stdout=json.dumps(payload), returncode=0)

    ghost.REPO_ROOT = repo_root
    try:
        assert ghost.main(
            ['--fixture', str(FIXTURE_PATH), '--format', 'state', '--live-desk'],
            live_desk_runner=runner,
        ) == 0
    finally:
        ghost.REPO_ROOT = original_repo_root

    state = json.loads(capsys.readouterr().out)

    assert calls == [[str(mew_path), 'desk', '--json']]
    assert state['desk']['source'] == 'live-desk'
    assert state['desk']['live_mew_reads'] is True
    assert state['desk']['command'] == ['./mew', 'desk', '--json']
    assert state['presence']['live_mew_reads'] is True
    assert state['desk']['primary_action']['dry_run'] is True
    assert state['desk']['primary_action']['executable'] is False
    assert state['launch_intents'][-1]['id'] == 'desk-primary-action'
    assert state['launch_intents'][-1]['execution']['executed'] is False


def test_cli_default_human_cat_uses_live_desk_with_injected_runner(capsys, tmp_path: Path) -> None:
    repo_root = tmp_path / 'repo'
    repo_root.mkdir()
    mew_path = repo_root / 'mew'
    mew_path.write_text('#!/bin/sh\n', encoding='utf-8')
    original_repo_root = ghost.REPO_ROOT
    calls: list[list[str]] = []
    long_live_detail = (
        'SP24b CLI live desk status with a full task instruction paragraph that should stay out '
        'of the default resident terminal surface while preserving the current work signal'
    )

    def forbidden_launcher(*_args: object, **_kwargs: object) -> None:
        raise AssertionError('launcher runner must not be called for live desk proof')

    def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        assert kwargs['shell'] is False
        payload = {
            'fixture_name': 'sp24b-cli-live-desk',
            'desk': {
                'status': 'sp24b-cli-live-ready',
                'pets': [{'name': 'mew-wisp', 'pet_state': 'coding', 'detail': long_live_detail}],
                'primary_action': {
                    'id': 'sp24b-cli-live-action',
                    'label': 'SP24b CLI live desk action',
                    'command': ['mew', 'code', '--task', '40'],
                },
            },
        }
        return _completed_process(stdout=json.dumps(payload), returncode=0)

    ghost.REPO_ROOT = repo_root
    try:
        assert ghost.main(
            ['--fixture', str(FIXTURE_PATH), '--format', 'human', '--form', 'cat'],
            live_desk_runner=runner,
            launcher_runner=forbidden_launcher,
        ) == 0
        minimal = capsys.readouterr().out

        assert ghost.main(
            ['--fixture', str(FIXTURE_PATH), '--format', 'human', '--form', 'cat', '--details'],
            live_desk_runner=runner,
            launcher_runner=forbidden_launcher,
        ) == 0
        detailed = capsys.readouterr().out
    finally:
        ghost.REPO_ROOT = original_repo_root

    assert calls == [[str(mew_path), 'desk', '--json'], [str(mew_path), 'desk', '--json']]
    assert 'mew-wisp resident cat' in minimal
    assert 'resident state: coding' in minimal
    assert 'resident marker: * | paws on keys' in minimal
    minimal_bubble = ' '.join(' '.join(_cat_speech_bubble_lines(minimal)).split())
    minimal_focus = ' '.join(' '.join(_resident_panel_values(minimal, 'focus')).split())
    assert minimal_bubble
    for compact_word in ('SP24b', 'CLI', 'live', 'desk', 'status...'):
        assert compact_word in minimal_bubble
        assert compact_word in minimal_focus
    assert 'with a full task instruction paragraph' not in minimal
    assert 'default resident terminal surface' not in minimal
    assert 'SP24b CLI live desk action' in ' '.join(_resident_panel_values(minimal, 'action'))
    assert 'desk details:' not in minimal
    assert 'active window:' not in minimal
    assert 'launcher intents:' not in minimal
    assert 'details:' in detailed
    assert 'freshness:' in detailed
    assert 'desk details:' in detailed
    assert 'active window:' in detailed
    assert 'launcher intents:' in detailed
    assert 'sp24b-cli-live-ready' in detailed
    assert 'desk-primary-action: mew code --task 40 (dry-run)' in detailed
    assert DESK_FIXTURE_PATH.name not in minimal
    assert DESK_FIXTURE_PATH.name not in detailed
    assert '--desk-json' not in minimal
    assert '--desk-json' not in detailed


def test_cli_wisp_preset_uses_live_cat_watch_with_bounded_count(capsys, tmp_path: Path) -> None:
    repo_root = tmp_path / 'repo'
    repo_root.mkdir()
    mew_path = repo_root / 'mew'
    mew_path.write_text('#!/bin/sh\n', encoding='utf-8')
    original_repo_root = ghost.REPO_ROOT
    calls: list[list[str]] = []
    statuses = iter(['typing', 'alerting'])
    sleeps: list[float] = []

    def forbidden_launcher(*_args: object, **_kwargs: object) -> None:
        raise AssertionError('launcher runner must not be called for --wisp live desk proof')

    def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        assert kwargs['shell'] is False
        status = next(statuses)
        payload = {
            'fixture_name': 'wisp-live-desk',
            'desk': {
                'status': status,
                'pets': [{'name': 'mew-wisp', 'pet_state': status, 'detail': f'wisp foreground {status}'}],
                'primary_action': {'id': 'resume', 'label': 'Resume wisp task', 'command': ['mew', 'code']},
            },
        }
        return _completed_process(stdout=json.dumps(payload), returncode=0)

    ghost.REPO_ROOT = repo_root
    try:
        assert ghost.main(
            ['--fixture', str(FIXTURE_PATH), '--wisp', '--watch-count', '2', '--interval', '0'],
            live_desk_runner=runner,
            launcher_runner=forbidden_launcher,
            clock=lambda: 'wisp-clock',
            sleeper=lambda interval: sleeps.append(interval),
        ) == 0
    finally:
        ghost.REPO_ROOT = original_repo_root

    output = capsys.readouterr().out

    assert calls == [[str(mew_path), 'desk', '--json'], [str(mew_path), 'desk', '--json']]
    assert sleeps == [0]
    assert output.count('mew-wisp resident cat') == 2
    assert 'wisp foreground typing' in output
    assert 'wisp foreground alerting' in output
    assert 'schema_version' not in output
    assert 'launcher intents:' not in output


def test_cli_wisp_preserves_explicit_format_form_and_fixture_terminal(capsys) -> None:
    def forbidden_live_desk(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise AssertionError('live desk runner must not be called for fixture or explicit state proof')

    assert ghost.main(
        ['--fixture', str(FIXTURE_PATH), '--wisp', '--fixture-terminal', '--watch-count', '1', '--interval', '0'],
        live_desk_runner=forbidden_live_desk,
        clock=lambda: 'fixture-wisp',
        sleeper=lambda interval: None,
    ) == 0
    fixture_output = capsys.readouterr().out

    assert 'mew-wisp resident cat' in fixture_output
    assert 'schema_version' not in fixture_output

    assert ghost.main(
        ['--fixture', str(FIXTURE_PATH), '--wisp', '--form', 'default', '--fixture-terminal', '--watch-count', '1', '--interval', '0'],
        live_desk_runner=forbidden_live_desk,
        clock=lambda: 'default-form-wisp',
        sleeper=lambda interval: None,
    ) == 0
    default_form_output = capsys.readouterr().out

    assert 'mew-wisp resident HUD' in default_form_output
    assert 'mew-wisp resident cat' not in default_form_output

    assert ghost.main(
        ['--fixture', str(FIXTURE_PATH), '--wisp', '--format', 'state', '--watch-count', '1', '--interval', '0'],
        live_desk_runner=forbidden_live_desk,
        clock=lambda: 'state-wisp',
        sleeper=lambda interval: None,
    ) == 0
    state_records = [json.loads(line) for line in capsys.readouterr().out.splitlines()]

    assert len(state_records) == 1
    assert state_records[0]['desk_status'] == 'disabled'
    assert state_records[0]['state']['desk']['live_mew_reads'] is False


def test_cli_live_desk_human_cat_details_sanitizes_raw_grouped_counts(capsys, tmp_path: Path) -> None:
    repo_root = tmp_path / 'repo'
    repo_root.mkdir()
    mew_path = repo_root / 'mew'
    mew_path.write_text('#!/bin/sh\n', encoding='utf-8')
    original_repo_root = ghost.REPO_ROOT
    calls: list[list[str]] = []

    def forbidden_launcher(*_args: object, **_kwargs: object) -> None:
        raise AssertionError('launcher runner must not be called for live desk proof')

    def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        assert kwargs['shell'] is False
        payload = {
            'fixture_name': 'sp24b-cli-live-desk',
            'desk': {
                'status': 'sp24b-cli-live-ready',
                'details': {
                    'current_task': {'title': 'SP24b hidden raw grouped detail'},
                },
                'pets': [{'name': 'mew-wisp', 'pet_state': 'coding', 'detail': 'SP24b CLI live desk status'}],
                'primary_action': {
                    'id': 'sp24b-cli-live-action',
                    'label': 'SP24b CLI live desk action',
                    'command': ['mew', 'code', '--task', '40'],
                },
            },
        }
        return _completed_process(stdout=json.dumps(payload), returncode=0)

    ghost.REPO_ROOT = repo_root
    try:
        normalized = ghost.fetch_live_desk_status(runner=runner, mew_path=mew_path)
        assert ghost.main(
            ['--fixture', str(FIXTURE_PATH), '--format', 'human', '--form', 'cat', '--live-desk', '--details'],
            live_desk_runner=runner,
            launcher_runner=forbidden_launcher,
        ) == 0
    finally:
        ghost.REPO_ROOT = original_repo_root

    detailed = capsys.readouterr().out

    assert calls == [[str(mew_path), 'desk', '--json'], [str(mew_path), 'desk', '--json']]
    assert normalized['counts']['raw_grouped_details']['current_task']['title'] == 'SP24b hidden raw grouped detail'
    assert 'desk: sp24b-cli-live-ready | counts:' in detailed
    assert '"pet_states": {"coding": 1}' in detailed
    assert '"pets_total": 1' in detailed
    assert 'raw_grouped_details' not in detailed
    assert 'SP24b hidden raw grouped detail' not in detailed


def test_cli_live_desk_human_cat_failure_renders_structured_fallback(capsys, tmp_path: Path) -> None:
    repo_root = tmp_path / 'repo'
    repo_root.mkdir()
    mew_path = repo_root / 'mew'
    mew_path.write_text('#!/bin/sh\n', encoding='utf-8')
    original_repo_root = ghost.REPO_ROOT
    calls: list[list[str]] = []

    def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        assert kwargs['shell'] is False
        return _completed_process(stderr='SP24b live desk read failed', returncode=23)

    ghost.REPO_ROOT = repo_root
    try:
        assert ghost.main(
            ['--fixture', str(FIXTURE_PATH), '--format', 'human', '--form', 'cat', '--live-desk', '--details'],
            live_desk_runner=runner,
        ) == 0
    finally:
        ghost.REPO_ROOT = original_repo_root

    fallback = capsys.readouterr().out

    assert calls == [[str(mew_path), 'desk', '--json']]
    assert 'mew-wisp resident cat' in fallback
    assert 'desk details:' in fallback
    assert 'fallback' in fallback
    assert 'live-desk-fallback' in fallback
    assert 'nonzero_exit' in fallback
    assert 'SP24b live desk read failed' in fallback
    assert 'returncode' in fallback
    assert '23' in fallback
    assert DESK_FIXTURE_PATH.name not in fallback
    assert '--desk-json' not in fallback


def test_watch_live_desk_reruns_only_when_opted_in(capsys, tmp_path: Path) -> None:
    repo_root = tmp_path / 'repo'
    repo_root.mkdir()
    (repo_root / 'mew').write_text('#!/bin/sh\n', encoding='utf-8')
    original_repo_root = ghost.REPO_ROOT
    calls: list[list[str]] = []
    statuses = iter(['thinking', 'alerting'])

    def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        status = next(statuses)
        payload = {
            'fixture_name': 'watch-live-desk',
            'desk': {
                'status': status,
                'pets': [{'name': 'mew', 'pet_state': status, 'detail': 'foreground watch'}],
            },
        }
        return _completed_process(stdout=json.dumps(payload), returncode=0)

    ghost.REPO_ROOT = repo_root
    try:
        assert ghost.main(
            ['--fixture', str(FIXTURE_PATH), '--format', 'state', '--watch-count', '2', '--interval', '0'],
            live_desk_runner=runner,
            clock=lambda: 'fixture-watch',
            sleeper=lambda interval: None,
        ) == 0
        fixture_records = [json.loads(line) for line in capsys.readouterr().out.splitlines()]

        clocks = iter(['live-0', 'live-1'])
        assert ghost.main(
            ['--fixture', str(FIXTURE_PATH), '--format', 'state', '--live-desk', '--watch-count', '2', '--interval', '0'],
            live_desk_runner=runner,
            clock=lambda: next(clocks),
            sleeper=lambda interval: None,
        ) == 0
    finally:
        ghost.REPO_ROOT = original_repo_root

    live_records = [json.loads(line) for line in capsys.readouterr().out.splitlines()]

    assert calls == [[str(repo_root / 'mew'), 'desk', '--json'], [str(repo_root / 'mew'), 'desk', '--json']]
    assert [record['desk_status'] for record in fixture_records] == ['disabled', 'disabled']
    assert all(record['state']['desk']['live_mew_reads'] is False for record in fixture_records)
    assert [record['desk_status'] for record in live_records] == ['thinking', 'alerting']
    assert all(record['state']['desk']['source'] == 'live-desk' for record in live_records)
    assert all(record['state']['presence']['live_mew_reads'] is True for record in live_records)


def test_watch_reloads_desk_fixture_each_iteration(tmp_path: Path, capsys) -> None:
    desk_path = tmp_path / 'desk.json'
    desk_path.write_text(json.dumps({'fixture_name': 'first', 'desk': {'status': 'thinking', 'pets': [{'name': 'mew', 'pet_state': 'thinking'}]}}), encoding='utf-8')
    clocks = iter(['desk-0', 'desk-1'])
    sleeps: list[float] = []

    def sleeper(interval: float) -> None:
        sleeps.append(interval)
        desk_path.write_text(json.dumps({'fixture_name': 'second', 'desk': {'status': 'alerting', 'pets': [{'name': 'mew', 'pet_state': 'alerting'}]}}), encoding='utf-8')

    assert ghost.main(
        ['--fixture', str(FIXTURE_PATH), '--desk-json', str(desk_path), '--format', 'state', '--watch-count', '2', '--interval', '0'],
        clock=lambda: next(clocks),
        sleeper=sleeper,
    ) == 0

    records = [json.loads(line) for line in capsys.readouterr().out.splitlines()]

    assert sleeps == [0]
    assert [record['desk_status'] for record in records] == ['thinking', 'alerting']
    assert records[0]['state']['presence']['desk']['state'] == 'attentive'
    assert records[1]['state']['presence']['desk']['state'] == 'waiting'
    assert records[1]['state']['desk']['fixture_name'] == 'second'


def test_execute_launchers_never_executes_desk_primary_action(capsys) -> None:
    calls: list[list[str]] = []

    def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return _completed_process()

    assert ghost.main(
        ['--fixture', str(FIXTURE_PATH), '--desk-json', str(DESK_FIXTURE_PATH), '--format', 'state', '--execute-launchers'],
        launcher_runner=runner,
    ) == 0

    state = json.loads(capsys.readouterr().out)

    assert calls == [['mew', 'chat'], ['mew', 'code']]
    desk_intent = state['launch_intents'][-1]
    assert desk_intent['id'] == 'desk-primary-action'
    assert desk_intent['dry_run'] is True
    assert desk_intent['execution']['executed'] is False


def test_cli_writes_local_html_and_state_from_fixture(tmp_path: Path) -> None:
    html_output = tmp_path / 'ghost.html'
    state_output = tmp_path / 'ghost-state.json'

    assert ghost.main(['--fixture', str(FIXTURE_PATH), '--output', str(html_output), '--refresh-count', '2']) == 0
    assert ghost.main(['--fixture', str(FIXTURE_PATH), '--format', 'state', '--output', str(state_output), '--refresh-count', '2']) == 0

    html = html_output.read_text(encoding='utf-8')
    state = json.loads(state_output.read_text(encoding='utf-8'))

    assert html.startswith('<!doctype html>')
    assert '<title>mew-wisp resident state (ghost.py compatibility render)</title>' in html
    assert '<h2>Resident state (ghost.py compatibility)</h2>' in html
    assert 'single render' in html
    assert 'refresh 0' in html
    assert 'refresh 1' in html
    assert state['fixture_name'] == 'sample_ghost_state'
    assert state['presence']['refresh_count'] == 2
    assert state['presence']['snapshots'][0]['presence_state'] == 'coding'
    assert state['launch_intents'][0]['command'] == ['mew', 'chat']
    assert state['launch_intents'][0]['execution']['status'] == 'dry_run'


def test_cli_live_opt_in_uses_injected_provider_for_stdout(capsys) -> None:
    assert ghost.main(
        ['--fixture', str(FIXTURE_PATH), '--format', 'state', '--live-active-window', '--refresh-count', '1'],
        live_probe_provider=lambda: {'active_app': 'Safari', 'window_title': 'mew-ghost notes', 'requires_permission': True},
        platform_name='Darwin',
    ) == 0

    state = json.loads(capsys.readouterr().out)

    assert state['active_window']['status'] == 'available'
    assert state['active_window']['active_app'] == 'Safari'
    assert state['presence']['refresh_count'] == 1
    assert state['presence']['classification']['state'] == 'attentive'
    assert state['launch_intents'][0]['dry_run'] is True


def test_cli_execute_launchers_requires_explicit_flag_and_injected_runner(capsys) -> None:
    calls: list[list[str]] = []

    def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        assert kwargs['capture_output'] is True
        assert kwargs['text'] is True
        assert kwargs['check'] is False
        return _completed_process()

    assert ghost.main(['--fixture', str(FIXTURE_PATH), '--format', 'state'], launcher_runner=runner) == 0
    dry_run_state = json.loads(capsys.readouterr().out)

    assert calls == []
    assert dry_run_state['launch_intents'][0]['execution']['status'] == 'dry_run'

    assert ghost.main(['--fixture', str(FIXTURE_PATH), '--format', 'state', '--execute-launchers'], launcher_runner=runner) == 0
    executed_state = json.loads(capsys.readouterr().out)

    assert calls == [['mew', 'chat'], ['mew', 'code']]
    assert all(intent['dry_run'] is False for intent in executed_state['launch_intents'])
    assert all(intent['execution']['executed'] is True for intent in executed_state['launch_intents'])


def test_watch_count_emits_exact_records_and_rebuilds_each_iteration(capsys) -> None:
    probes = iter([
        {'active_app': 'Notes', 'window_title': 'planning', 'requires_permission': True},
        {'active_app': 'Terminal', 'window_title': 'ghost.py', 'requires_permission': True},
    ])
    clocks = iter(['fresh-0', 'fresh-1'])
    sleeps: list[float] = []

    assert ghost.main(
        ['--fixture', str(FIXTURE_PATH), '--format', 'state', '--live-active-window', '--watch-count', '2', '--interval', '0.25'],
        live_probe_provider=lambda: next(probes),
        platform_name='Darwin',
        clock=lambda: next(clocks),
        sleeper=lambda interval: sleeps.append(interval),
    ) == 0

    records = [json.loads(line) for line in capsys.readouterr().out.splitlines()]

    assert len(records) == 2
    assert sleeps == [0.25]
    assert [record['watch_iteration'] for record in records] == [0, 1]
    assert records[0]['record_type'] == 'mew_ghost_watch_iteration'
    assert records[0]['state']['active_window']['active_app'] == 'Notes'
    assert records[1]['state']['active_window']['active_app'] == 'Terminal'
    assert records[1]['state']['freshness']['rendered_at'] == 'fresh-1'
    assert records[1]['state']['presence']['refresh_count'] == 1


def test_human_watch_count_prints_terminal_surface_instead_of_jsonl(capsys) -> None:
    clocks = iter(['human-0', 'human-1'])
    sleeps: list[float] = []

    assert ghost.main(
        ['--fixture', str(FIXTURE_PATH), '--format', 'human', '--watch-count', '2', '--interval', '0'],
        clock=lambda: next(clocks),
        sleeper=lambda interval: sleeps.append(interval),
    ) == 0

    output = capsys.readouterr().out

    assert sleeps == [0.0]
    assert output.count('mew-wisp resident HUD') == 2
    assert output.count('resident: mew-wisp') == 2
    assert output.count('focus:') == 2
    assert output.count('signal:') == 2
    assert output.count('action:') == 2
    assert 'hud: mew-ghost' not in output
    assert 'next:' not in output
    assert 'freshness:' not in output
    assert 'desk details:' not in output
    assert 'active window:' not in output
    assert 'launcher intents:' not in output
    assert 'record_type' not in output
    assert 'schema_version' not in output
    assert not output.lstrip().startswith('{')


def test_watch_without_count_runs_until_keyboard_interrupt(capsys) -> None:
    clocks = iter(['loop-0', 'loop-1', 'loop-2'])
    sleeps: list[float] = []

    def sleeper(interval: float) -> None:
        sleeps.append(interval)
        if len(sleeps) >= 2:
            raise KeyboardInterrupt

    assert ghost.main(
        ['--fixture', str(FIXTURE_PATH), '--format', 'state', '--watch', '--interval', '0.5'],
        clock=lambda: next(clocks),
        sleeper=sleeper,
    ) == 0

    records = [json.loads(line) for line in capsys.readouterr().out.splitlines()]

    assert len(records) == 2
    assert [record['watch_iteration'] for record in records] == [0, 1]
    assert [record['watch_total'] for record in records] == [None, None]
    assert sleeps == [0.5, 0.5]


def test_human_watch_without_count_prints_surface_until_keyboard_interrupt(capsys) -> None:
    clocks = iter(['human-loop-0', 'human-loop-1', 'human-loop-2'])
    sleeps: list[float] = []

    def sleeper(interval: float) -> None:
        sleeps.append(interval)
        if len(sleeps) >= 2:
            raise KeyboardInterrupt

    assert ghost.main(
        ['--fixture', str(FIXTURE_PATH), '--format', 'human', '--watch', '--interval', '0.5'],
        clock=lambda: next(clocks),
        sleeper=sleeper,
    ) == 0

    output = capsys.readouterr().out

    assert sleeps == [0.5, 0.5]
    assert output.count('mew-wisp resident HUD') == 2
    assert output.count('resident: mew-wisp') == 2
    assert output.count('focus:') == 2
    assert output.count('signal:') == 2
    assert output.count('action:') == 2
    assert 'hud: mew-ghost' not in output
    assert 'next:' not in output
    assert 'freshness:' not in output
    assert 'watch iteration' not in output
    assert 'record_type' not in output
    assert 'schema_version' not in output


def test_watch_html_output_rewrites_each_iteration_with_freshness_metadata(tmp_path: Path, capsys) -> None:
    output = tmp_path / 'ghost.html'
    probes = iter([
        {'active_app': 'Notes', 'window_title': 'planning', 'requires_permission': True},
        {'active_app': 'Terminal', 'window_title': 'ghost.py', 'requires_permission': True},
    ])
    clocks = iter(['html-0', 'html-1'])

    assert ghost.main(
        ['--fixture', str(FIXTURE_PATH), '--format', 'html', '--output', str(output), '--live-active-window', '--watch-count', '2', '--interval', '0'],
        live_probe_provider=lambda: next(probes),
        platform_name='Darwin',
        clock=lambda: next(clocks),
        sleeper=lambda interval: None,
    ) == 0

    records = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    html = output.read_text(encoding='utf-8')

    assert len(records) == 2
    assert records[0]['output'] == str(output)
    assert records[1]['output'] == str(output)
    assert records[1]['active_app'] == 'Terminal'
    assert 'watch iteration 1 of 2' in html
    assert 'html-1' in html
    assert 'Terminal' in html
    assert 'Notes' not in html


CAT_REFERENCE_MASK = (
    '.####.......####......',
    '.#####.....#####......',
    '.##.###....##.##......',
    '.##..#######..##......',
    '.##...######..##......',
    '.##...........##......',
    '###..#....###.####....',
    '##...#....###..###....',
    '##...#....###..###....',
    '###..#.##..##.###.....',
    '.#####.##....###......',
    '...###......####......',
    '...###.......#####....',
    '....##........#####...',
    '....##.........####...',
    '....##.#..#.....###...',
    '....##.#..#......####.',
    '....##.#..#......####.',
    '....##.#..#......##.##',
    '...#########....###.##',
    '...##.#####....###..##',
    '...#############...##.',
    '...##################.',
    '..............#####...',
)


def _cat_state_line_index(rendered: str) -> int:
    lines = rendered.splitlines()
    return next(index for index, line in enumerate(lines) if line.lstrip().startswith('resident state: '))


def _expected_cat_caption(text: str) -> str:
    return text.center(ghost.CAT_TERMINAL_PIXEL_WIDTH).rstrip()


def _cat_sprite_lines(rendered: str) -> list[str]:
    lines = rendered.splitlines()
    cat_state_index = _cat_state_line_index(rendered)
    start = cat_state_index + 1
    end = start + len(CAT_REFERENCE_MASK)
    return lines[start:end]


def _cat_sprite_mask(rendered: str) -> tuple[str, ...]:
    mask_lines: list[str] = []
    for expected_row, rendered_row in zip(CAT_REFERENCE_MASK, _cat_sprite_lines(rendered), strict=True):
        sprite_width = len(expected_row) * 2
        sprite_row = rendered_row[-sprite_width:]
        assert len(sprite_row) == sprite_width
        mask_lines.append(
            ''.join(
                '#' if sprite_row[index:index + 2] == '██' else '.'
                for index in range(0, len(sprite_row), 2)
            )
        )
    return tuple(mask_lines)


def _cat_sprite_similarity(rendered: str) -> float:
    actual = ''.join(_cat_sprite_mask(rendered))
    expected = ''.join(CAT_REFERENCE_MASK)
    matches = sum(1 for actual_cell, expected_cell in zip(actual, expected, strict=True) if actual_cell == expected_cell)
    return matches / len(expected)


def _expected_cat_padding(terminal_width: int) -> int:
    return max(0, (terminal_width - len(CAT_REFERENCE_MASK[0]) * 2) // 2)


def _rendered_reference_row(mask_row: str) -> str:
    return ''.join('██' if cell == '#' else '  ' for cell in mask_row)


def _leading_spaces(line: str) -> int:
    return len(line) - len(line.lstrip(' '))


def _resident_panel_content(line: str) -> str:
    return line.lstrip(' ')


def _resident_panel_lines(rendered: str) -> list[str]:
    lines = rendered.splitlines()
    start = next(
        index for index, line in enumerate(lines)
        if _resident_panel_content(line).startswith('+') and 'mew-wisp resident HUD' in line
    )
    end = next(
        index for index in range(start + 1, len(lines))
        if _resident_panel_content(lines[index]).startswith('+')
        and set(_resident_panel_content(lines[index])[1:-1]) == {'-'}
    )
    return lines[start:end + 1]


def _resident_panel_padding(rendered: str) -> int:
    return _leading_spaces(_resident_panel_lines(rendered)[0])


def _expected_resident_panel_padding(terminal_width: int, rendered: str) -> int:
    panel_width = len(_resident_panel_content(_resident_panel_lines(rendered)[0]))
    return max(0, (terminal_width - panel_width) // 2)


def _assert_resident_panel_padding(rendered: str, terminal_width: int) -> None:
    panel_lines = _resident_panel_lines(rendered)
    expected_padding = _expected_resident_panel_padding(terminal_width, rendered)
    assert _resident_panel_padding(rendered) == expected_padding
    assert all(_leading_spaces(line) == expected_padding for line in panel_lines)
    assert all(
        len(_resident_panel_content(line)) == len(_resident_panel_content(panel_lines[0]))
        for line in panel_lines
    )


def _resident_panel_values(rendered: str, label: str) -> list[str]:
    label_prefix = '| ' + (label + ':').ljust(9) + ' '
    continuation_prefix = '| ' + ' ' * 10
    values: list[str] = []
    collecting = False
    for line in _resident_panel_lines(rendered)[1:-1]:
        content = _resident_panel_content(line)
        if content.startswith(label_prefix):
            values.append(content[len(label_prefix):-2].rstrip())
            collecting = True
            continue
        if collecting and content.startswith(continuation_prefix):
            values.append(content[len(continuation_prefix):-2].rstrip())
            continue
        if collecting:
            break
    return values


def _resident_panel_value_column(rendered: str, label: str) -> int:
    label_prefix = '| ' + (label + ':').ljust(9) + ' '
    row = next(
        _resident_panel_content(line)
        for line in _resident_panel_lines(rendered)
        if _resident_panel_content(line).startswith(label_prefix)
    )
    value = _resident_panel_values(rendered, label)[0]
    return row.index(value)


def _panel_start_index(rendered: str) -> int:
    lines = rendered.splitlines()
    panel = _resident_panel_lines(rendered)
    return lines.index(panel[0])


def _trim_blank_separator_lines(lines: list[str]) -> list[str]:
    start = 0
    end = len(lines)
    while start < end and not lines[start].strip():
        start += 1
    while end > start and not lines[end - 1].strip():
        end -= 1
    return lines[start:end]


def _speech_bubble_lines(rendered: str) -> list[str]:
    lines = rendered.splitlines()
    return _trim_blank_separator_lines(lines[:_panel_start_index(rendered)])


def _cat_speech_bubble_lines(rendered: str) -> list[str]:
    lines = rendered.splitlines()
    bubble_start = 3 + len(CAT_REFERENCE_MASK)
    return _trim_blank_separator_lines(lines[bubble_start:_panel_start_index(rendered)])


def test_terminal_human_default_form_is_compact_and_details_are_opt_in(monkeypatch) -> None:
    monkeypatch.delenv(ghost.CAT_TERMINAL_WIDTH_ENV, raising=False)
    state, html = ghost.render_fixture(FIXTURE_PATH)

    implicit = ghost._render_payload(state, html, 'human')
    explicit = ghost._render_payload(state, html, 'human', terminal_form='default')
    cat = ghost._render_payload(state, html, 'human', terminal_form='cat')
    details = ghost._render_payload(state, html, 'human', terminal_form='cat', terminal_details=True)

    assert implicit == explicit
    implicit_panel = _resident_panel_lines(implicit)
    cat_panel = _resident_panel_lines(cat)
    details_panel = _resident_panel_lines(details)
    _assert_resident_panel_padding(implicit, ghost.DEFAULT_TERMINAL_WIDTH)
    _assert_resident_panel_padding(cat, ghost.DEFAULT_TERMINAL_WIDTH)
    _assert_resident_panel_padding(details, ghost.DEFAULT_TERMINAL_WIDTH)
    implicit_bubble = _speech_bubble_lines(implicit)
    cat_bubble = _cat_speech_bubble_lines(cat)
    details_bubble = _cat_speech_bubble_lines(details)
    bubble_text = '\n'.join(implicit_bubble)
    normalized_bubble_text = ' '.join(bubble_text.split())
    message_words = state['ghost']['message'].split()
    assert implicit_bubble
    assert cat_bubble == implicit_bubble
    assert details_bubble == implicit_bubble
    bubble_rows = [line.strip() for line in implicit_bubble]
    readable_spacer = '|' + ' ' * (len(bubble_rows[0]) - 2) + '|'
    assert bubble_rows[1] == readable_spacer
    assert bubble_rows[-2] == readable_spacer
    assert bubble_rows[0] == bubble_rows[-1]
    assert _panel_start_index(implicit) >= len(implicit_bubble)
    assert _panel_start_index(cat) >= 3 + len(CAT_REFERENCE_MASK) + len(cat_bubble)
    assert 'mew-wisp resident HUD' not in bubble_text
    assert 'coding' in bubble_text
    assert 'mew-wisp live desk' not in normalized_bubble_text
    assert 'mew-wisp local terminal' in normalized_bubble_text
    assert all(word in normalized_bubble_text for word in state['ghost']['focus'].split())
    live_status = ghost._apply_live_desk_metadata(
        ghost.build_desk_status(
            {
                'desk': {
                    'status': 'coding',
                    'pets': [
                        {
                            'name': 'wisp',
                            'pet_state': 'coding',
                            'detail': 'watching task 47',
                        }
                    ],
                }
            }
        )
    )
    live_state, live_html = ghost.render_fixture(FIXTURE_PATH, desk_status=live_status)
    live_rendered = ghost._render_payload(live_state, live_html, 'human')
    live_bubble_text = ' '.join('\n'.join(_speech_bubble_lines(live_rendered)).split())
    assert 'mew-wisp live desk coding' in live_bubble_text
    assert '1 desk pet' in live_bubble_text
    assert 'status coding' in live_bubble_text
    assert 'wisp' in live_bubble_text
    assert 'watching task 47' in live_bubble_text
    assert not all(word in live_bubble_text for word in live_state['ghost']['focus'].split())
    assert all(word in normalized_bubble_text for word in message_words)
    assert all(ord(character) < 128 for line in implicit_bubble for character in line)
    assert all(len(line.rstrip()) <= ghost.DEFAULT_TERMINAL_WIDTH for line in implicit_bubble if line.strip())
    assert 'mew-wisp resident HUD' in implicit_panel[0]
    assert 'mew-wisp resident HUD' in cat_panel[0]
    assert 'mew-wisp resident HUD' in details_panel[0]
    assert len({len(line) for line in implicit_panel}) == 1
    assert {_resident_panel_value_column(implicit, label) for label in ('resident', 'marker', 'focus', 'signal', 'action')} == {12}
    assert 'resident: mew-wisp' in implicit
    assert _resident_panel_values(implicit, 'marker') == ['*']
    assert 'hud: mew-ghost' not in implicit
    assert 'next:' not in implicit
    assert 'terminal form: cat' not in implicit
    assert 'freshness:' not in implicit
    assert 'desk details:' not in implicit
    assert 'active window:' not in implicit
    assert 'launcher intents:' not in implicit
    cat_padding = ' ' * _expected_cat_padding(ghost.DEFAULT_TERMINAL_WIDTH)
    cat_lines = cat.splitlines()
    assert cat_lines[0] == cat_padding + _expected_cat_caption('mew-wisp resident cat')
    assert cat_lines[1] == cat_padding + _expected_cat_caption('resident state: coding')
    assert 'terminal form: cat' not in cat
    assert 'cat state:' not in cat
    cat_bubble_start = next(
        index for index in range(3 + len(CAT_REFERENCE_MASK), _panel_start_index(cat))
        if cat_lines[index].strip()
    )
    assert cat_lines[cat_bubble_start] == cat_bubble[0]
    assert cat_lines[_panel_start_index(cat)] == cat_panel[0]
    assert 'resident: mew-wisp' in cat
    assert 'focus:' in cat
    assert 'signal:' in cat
    assert 'action:' in cat
    assert 'next:' not in cat
    assert 'freshness:' not in cat
    assert 'desk details:' not in cat
    assert 'active window:' not in cat
    assert 'launcher intents:' not in cat
    assert 'details:' in details
    assert 'freshness:' in details
    assert 'desk details:' in details
    assert 'active window:' in details
    assert 'launcher intents:' in details
    assert _cat_sprite_similarity(cat) >= 0.90
    cat_mask = _cat_sprite_mask(cat)
    assert cat_mask[6][0:6] == '###..#'
    assert all(row[3:6] == '..#' for row in cat_mask[7:10])
    assert all(row[4:6] != '##' for row in cat_mask[6:10])
    foreleg_rows = cat_mask[15:19]
    foreleg_segments = [row[6:11] for row in foreleg_rows]
    assert all('.##.##.##' not in row for row in foreleg_rows)
    assert all(segment != '.####' for segment in foreleg_segments)
    assert foreleg_segments == ['.#..#'] * 4
    assert _resident_panel_values(implicit, 'marker') == ['*']
    assert cat.count('resident marker: *') == 1
    assert 'resident marker: *' in cat
    assert 'state marker:' not in cat
    assert 'resident marker: *' not in '\n'.join(_cat_sprite_lines(cat))
    cat_focus_line = ' '.join(_resident_panel_values(cat, 'focus'))
    implicit_focus_line = ' '.join(_resident_panel_values(implicit, 'focus'))
    assert cat_focus_line == '%s - %s' % (state['ghost']['focus'], state['ghost']['message'])
    assert implicit_focus_line == cat_focus_line
    assert all(ord(character) < 128 for character in cat_focus_line)
    assert chr(8212) not in cat_focus_line

    long_state = json.loads(json.dumps(state))
    long_state['ghost']['focus'] = 'SP22c'
    long_state['ghost']['message'] = 'x' * 140
    long_focus = ghost._render_payload(long_state, html, 'human')
    long_bubble = _speech_bubble_lines(long_focus)
    long_bubble_text = '\n'.join(long_bubble)
    long_panel = _resident_panel_lines(long_focus)
    assert 'x' * 140 not in long_bubble_text
    assert long_bubble_text.count('x') == 140
    assert sum(1 for line in long_bubble if 'x' in line) > 1
    assert all(ord(character) < 128 for line in long_bubble for character in line)
    assert all(len(line.rstrip()) <= ghost.DEFAULT_TERMINAL_WIDTH for line in long_bubble if line.strip())
    assert len({len(line) for line in long_panel}) == 1
    assert len(_resident_panel_values(long_focus, 'focus')) > 1
    assert all(len(line) == len(long_panel[0]) for line in long_panel)
    assert '  code  ' not in cat
    assert '   /\\_____/\\        ' not in cat
    assert ' |  \\_____/  |__/   ' not in cat


def test_terminal_human_cat_renders_injected_live_desk_provider(capsys) -> None:
    calls: list[str] = []

    def provider() -> dict[str, object]:
        calls.append('desk')
        return {
            'enabled': True,
            'source': 'live-desk',
            'fixture_name': 'sp24-injected-live-desk',
            'generated_at': '2026-04-29T08:00:00Z',
            'status': 'sp24-live-ready',
            'counts': {'pets_total': 1, 'pet_states': {'coding': 1}},
            'details': [
                {
                    'id': 'mew-wisp',
                    'name': 'mew-wisp',
                    'pet': 'mew-wisp',
                    'state': 'coding',
                    'status': 'sp24-live-ready',
                    'summary': 'SP24 live desk status visible in human cat details.',
                }
            ],
            'primary_action': {
                'id': 'sp24-live-desk-reconnect',
                'label': 'SP24 live desk reconnect',
                'command': ['mew', 'code', '--task', '39'],
                'title': 'SP24 live desk reconnect',
                'name': 'SP24 live desk reconnect',
                'description': 'SP24 live desk reconnect action from injected provider.',
                'source': 'live-desk',
                'dry_run': True,
                'side_effects': 'none',
                'executable': False,
            },
            'live_mew_reads': True,
            'command': ['mew', 'desk', '--json'],
            'fallback': None,
        }

    minimal_exit = ghost.run_watch(
        FIXTURE_PATH,
        desk_provider=provider,
        format_name='human',
        terminal_form='cat',
        watch_count=1,
        interval_seconds=0,
        clock=lambda: '2026-04-29T08:00:00Z',
    )
    minimal = capsys.readouterr().out

    detailed_exit = ghost.run_watch(
        FIXTURE_PATH,
        desk_provider=provider,
        format_name='human',
        terminal_form='cat',
        terminal_details=True,
        watch_count=1,
        interval_seconds=0,
        clock=lambda: '2026-04-29T08:00:01Z',
    )
    detailed = capsys.readouterr().out

    assert minimal_exit == 0
    assert detailed_exit == 0
    assert calls == ['desk', 'desk']
    assert 'mew-wisp resident cat' in minimal
    assert 'resident state: coding' in minimal
    assert 'mew-wisp resident HUD' in minimal
    assert _cat_speech_bubble_lines(minimal)
    assert _cat_speech_bubble_lines(detailed) == _cat_speech_bubble_lines(minimal)
    assert 'mew-wisp resident HUD' not in '\n'.join(_cat_speech_bubble_lines(minimal))
    assert 'SP24 live desk reconnect' in ' '.join(_resident_panel_values(minimal, 'action'))
    assert 'desk details:' not in minimal
    assert 'active window:' not in minimal
    assert 'launcher intents:' not in minimal
    assert 'details:' in detailed
    assert 'freshness:' in detailed
    assert 'desk details:' in detailed
    assert 'active window:' in detailed
    assert 'launcher intents:' in detailed
    assert 'sp24-live-ready' in detailed
    assert 'SP24 live desk reconnect' in detailed
    assert 'desk-primary-action: mew code --task 39 (dry-run)' in detailed
    assert DESK_FIXTURE_PATH.name not in minimal
    assert DESK_FIXTURE_PATH.name not in detailed
    assert '--desk-json' not in detailed


def test_human_watch_stdout_rerenders_terminal_surface(capsys) -> None:
    ticks = iter(['2026-04-29T09:00:00Z', '2026-04-29T09:00:01Z'])

    exit_code = ghost.run_watch(
        FIXTURE_PATH,
        format_name='human',
        terminal_form='cat',
        watch_count=2,
        interval_seconds=0,
        sleeper=lambda _seconds: None,
        clock=lambda: next(ticks),
    )
    captured = capsys.readouterr().out

    assert exit_code == 0
    assert captured.startswith('\x1b[H\x1b[J')
    assert captured.count('\x1b[H\x1b[J') == 2
    assert captured.count('mew-wisp resident cat') == 2
    assert captured.count('mew-wisp resident HUD') == 2
    assert 'resident state: coding' in captured


def test_watch_jsonl_state_html_and_output_file_skip_rerender_controls(tmp_path: Path, capsys) -> None:
    state_exit = ghost.run_watch(
        FIXTURE_PATH,
        format_name='state',
        watch_count=2,
        interval_seconds=0,
        sleeper=lambda _seconds: None,
        clock=lambda: '2026-04-29T09:01:00Z',
    )
    state_stdout = capsys.readouterr().out
    state_records = [json.loads(line) for line in state_stdout.splitlines()]

    html_exit = ghost.run_watch(
        FIXTURE_PATH,
        format_name='html',
        watch_count=2,
        interval_seconds=0,
        sleeper=lambda _seconds: None,
        clock=lambda: '2026-04-29T09:02:00Z',
    )
    html_stdout = capsys.readouterr().out
    html_records = [json.loads(line) for line in html_stdout.splitlines()]

    output_path = tmp_path / 'watch-human.txt'
    output_exit = ghost.run_watch(
        FIXTURE_PATH,
        format_name='human',
        terminal_form='cat',
        output=output_path,
        watch_count=2,
        interval_seconds=0,
        sleeper=lambda _seconds: None,
        clock=lambda: '2026-04-29T09:03:00Z',
    )
    output_stdout = capsys.readouterr().out
    output_records = [json.loads(line) for line in output_stdout.splitlines()]
    output_text = output_path.read_text(encoding='utf-8')

    assert state_exit == 0
    assert html_exit == 0
    assert output_exit == 0
    assert len(state_records) == 2
    assert len(html_records) == 2
    assert len(output_records) == 2
    assert '\x1b[' not in state_stdout
    assert '\x1b[' not in html_stdout
    assert '\x1b[' not in output_stdout
    assert '\x1b[' not in output_text
    assert 'mew-wisp resident cat' in output_text
    assert 'mew-wisp resident HUD' in output_text


def test_terminal_human_resident_panel_centers_with_forced_width(monkeypatch) -> None:
    monkeypatch.setenv(ghost.CAT_TERMINAL_WIDTH_ENV, '100')
    state, html = ghost.render_fixture(FIXTURE_PATH)

    default = ghost._render_payload(state, html, 'human')
    cat = ghost._render_payload(state, html, 'human', terminal_form='cat')

    _assert_resident_panel_padding(default, 100)
    _assert_resident_panel_padding(cat, 100)
    assert _resident_panel_padding(default) > 0
    assert _resident_panel_padding(cat) > 0
    default_bubble = _speech_bubble_lines(default)
    default_bubble_content = [line for line in default_bubble if line.strip()]
    assert default_bubble_content
    assert all(line.startswith(' ') for line in default_bubble_content)
    assert _cat_speech_bubble_lines(cat) == default_bubble
    assert _panel_start_index(default) >= len(default_bubble)
    assert _panel_start_index(cat) >= 3 + len(CAT_REFERENCE_MASK) + len(_cat_speech_bubble_lines(cat))


def test_terminal_human_resident_panel_narrow_width_adds_no_padding(monkeypatch) -> None:
    monkeypatch.setenv(ghost.CAT_TERMINAL_WIDTH_ENV, '20')
    state, html = ghost.render_fixture(FIXTURE_PATH)

    default = ghost._render_payload(state, html, 'human')
    cat = ghost._render_payload(state, html, 'human', terminal_form='cat')

    assert _speech_bubble_lines(default)
    assert _cat_speech_bubble_lines(cat) == _speech_bubble_lines(default)

    for rendered in (default, cat):
        _assert_resident_panel_padding(rendered, 20)
        assert _resident_panel_padding(rendered) == 0
        assert all(line == _resident_panel_content(line) for line in _resident_panel_lines(rendered))


def test_cat_terminal_form_centers_sprite_and_marker_with_forced_width(monkeypatch) -> None:
    monkeypatch.setenv(ghost.CAT_TERMINAL_WIDTH_ENV, '100')
    state, html = ghost.render_fixture(FIXTURE_PATH)

    cat = ghost._render_payload(state, html, 'human', terminal_form='cat')

    padding = ' ' * _expected_cat_padding(100)
    lines = cat.splitlines()
    cat_state_index = _cat_state_line_index(cat)
    assert lines[cat_state_index - 1] == padding + _expected_cat_caption('mew-wisp resident cat')
    assert lines[cat_state_index] == padding + _expected_cat_caption('resident state: coding')
    assert all(line.startswith(padding) for line in _cat_sprite_lines(cat))
    assert all(len(line) == len(padding) + len(CAT_REFERENCE_MASK[0]) * 2 for line in _cat_sprite_lines(cat))
    assert lines[cat_state_index + 1 + len(CAT_REFERENCE_MASK)] == padding + _expected_cat_caption('resident marker: * | paws on keys')
    assert _cat_sprite_similarity(cat) == 1.0


def test_cat_terminal_form_narrow_width_adds_no_padding_and_preserves_sprite(monkeypatch) -> None:
    monkeypatch.setenv(ghost.CAT_TERMINAL_WIDTH_ENV, '20')
    state, html = ghost.render_fixture(FIXTURE_PATH)

    cat = ghost._render_payload(state, html, 'human', terminal_form='cat')

    lines = cat.splitlines()
    cat_state_index = _cat_state_line_index(cat)
    assert lines[cat_state_index - 1] == _expected_cat_caption('mew-wisp resident cat')
    assert lines[cat_state_index] == _expected_cat_caption('resident state: coding')
    assert all(len(line) == len(CAT_REFERENCE_MASK[0]) * 2 for line in _cat_sprite_lines(cat))
    assert lines[cat_state_index + 1 + len(CAT_REFERENCE_MASK)] == _expected_cat_caption('resident marker: * | paws on keys')
    assert _cat_sprite_similarity(cat) == 1.0


def test_human_watch_cat_output_centers_terminal_surface(monkeypatch, capsys) -> None:
    monkeypatch.setenv(ghost.CAT_TERMINAL_WIDTH_ENV, '96')
    clocks = iter(['cat-watch-0', 'cat-watch-1'])
    sleeps: list[float] = []

    assert ghost.main(
        [
            '--fixture',
            str(FIXTURE_PATH),
            '--format',
            'human',
            '--form',
            'cat',
            '--watch-count',
            '2',
            '--interval',
            '0',
        ],
        clock=lambda: next(clocks),
        sleeper=lambda interval: sleeps.append(interval),
    ) == 0

    output = capsys.readouterr().out
    padding = ' ' * _expected_cat_padding(96)
    assert sleeps == [0.0]
    assert output.count(padding + _expected_cat_caption('mew-wisp resident cat')) == 2
    assert 'terminal form: cat' not in output
    panel_header = _resident_panel_lines(output)[0]
    _assert_resident_panel_padding(output, 96)
    assert output.count(padding + _expected_cat_caption('resident state: coding')) == 2
    assert output.count(padding + _expected_cat_caption('resident marker: * | paws on keys')) == 2
    assert 'cat state:' not in output
    assert 'state marker:' not in output
    assert output.count(padding + _rendered_reference_row(CAT_REFERENCE_MASK[0])) == 2
    assert output.count('mew-wisp resident HUD') == 2
    assert output.count(panel_header) == 2


def test_cat_terminal_form_uses_reference_like_pixel_silhouette_by_presence_state() -> None:
    state, html = ghost.render_fixture(FIXTURE_PATH)
    expected_markers = {
        'idle': 'resident marker: zZ | dreaming softly',
        'attentive': 'resident marker: ? | ears forward',
        'coding': 'resident marker: * | paws on keys',
        'waiting': 'resident marker: ... | tail swishes',
        'blocked': 'resident marker: ! | signal flare',
    }
    masks_by_state: dict[str, tuple[str, ...]] = {}

    for presence_state, marker in expected_markers.items():
        mutated = json.loads(json.dumps(state))
        mutated['presence']['classification']['state'] = presence_state
        rendered = ghost._render_payload(mutated, html, 'human', terminal_form='cat')

        assert 'mew-wisp resident cat' in rendered
        assert 'resident state: %s' % presence_state in rendered
        assert 'terminal form: cat' not in rendered
        assert 'cat state:' not in rendered
        assert 'state marker:' not in rendered
        assert marker in rendered
        assert rendered.count(marker) == 1
        assert marker not in '\n'.join(_cat_sprite_lines(rendered))
        assert _cat_sprite_similarity(rendered) >= 0.90
        assert '  code  ' not in rendered
        assert '  /  ▌   ▌  \\___   ' not in rendered
        masks_by_state[presence_state] = _cat_sprite_mask(rendered)

    assert len({mask for mask in masks_by_state.values()}) == 1


def test_human_details_flag_prints_diagnostic_sections(capsys) -> None:
    assert ghost.main(
        ['--fixture', str(FIXTURE_PATH), '--format', 'human', '--form', 'cat', '--details'],
    ) == 0

    output = capsys.readouterr().out

    assert output.splitlines()[0].strip() == 'mew-wisp resident cat'
    assert output.splitlines()[1].strip() == 'resident state: coding'
    assert 'terminal form: cat' not in output
    assert 'cat state:' not in output
    assert 'mew-wisp resident HUD' in output
    assert 'details:' in output
    assert 'freshness:' in output
    assert 'desk details:' in output
    assert 'active window:' in output
    assert 'launcher intents:' in output
    assert 'record_type' not in output


def test_human_cat_watch_count_prints_cat_form_surface(capsys) -> None:
    clocks = iter(['cat-0', 'cat-1'])
    sleeps: list[float] = []

    assert ghost.main(
        ['--fixture', str(FIXTURE_PATH), '--format', 'human', '--form', 'cat', '--watch-count', '2', '--interval', '0'],
        clock=lambda: next(clocks),
        sleeper=lambda interval: sleeps.append(interval),
    ) == 0

    output = capsys.readouterr().out

    assert sleeps == [0.0]
    assert output.count('mew-wisp resident cat') == 2
    assert output.count('resident state: coding') == 2
    assert 'terminal form: cat' not in output
    assert 'cat state:' not in output
    assert output.count('mew-wisp resident HUD') == 2
    assert output.count('resident: mew-wisp') == 2
    assert output.count('focus:') == 2
    assert output.count('signal:') == 2
    assert output.count('action:') == 2
    assert 'hud: mew-ghost' not in output
    assert 'next:' not in output
    assert 'freshness:' not in output
    assert 'desk details:' not in output
    assert 'active window:' not in output
    assert 'launcher intents:' not in output
    assert 'record_type' not in output
    assert 'schema_version' not in output


def test_readme_usage_prefers_product_named_uv_run_python_commands() -> None:
    readme = README_PATH.read_text(encoding='utf-8')
    normalized_readme = ' '.join(readme.split())

    assert '# mew-wisp resident terminal' in readme
    assert '`mew_wisp.py` is the normal product-named resident terminal entrypoint' in normalized_readme
    assert '`ghost.py` remains the historical compatibility implementation module' in normalized_readme
    assert 'Product-named `mew_wisp.py` output files require explicit `--format html` or `--format state`' in normalized_readme
    assert '`ghost.py`: the historical standalone compatibility implementation module retained for direct `ghost.py` users.' in readme

    usage_lines = [line.strip() for line in readme.splitlines() if 'experiments/mew-ghost/mew_wisp.py' in line]

    assert usage_lines == [
        'UV_CACHE_DIR=.uv-cache uv run python experiments/mew-ghost/mew_wisp.py',
        'UV_CACHE_DIR=.uv-cache uv run python experiments/mew-ghost/mew_wisp.py --format html --output /tmp/mew-ghost.html',
        'UV_CACHE_DIR=.uv-cache uv run python experiments/mew-ghost/mew_wisp.py --format state --watch-count 3 --interval 0.5',
        'UV_CACHE_DIR=.uv-cache uv run python experiments/mew-ghost/mew_wisp.py --wisp --watch-count 2 --interval 0.5',
        'UV_CACHE_DIR=.uv-cache uv run python experiments/mew-ghost/mew_wisp.py --format human --watch-count 2 --interval 0.5',
        'UV_CACHE_DIR=.uv-cache uv run python experiments/mew-ghost/mew_wisp.py --format human --fixture-terminal --watch-count 2 --interval 0.5',
        'UV_CACHE_DIR=.uv-cache uv run python experiments/mew-ghost/mew_wisp.py --format human --form cat --watch-count 2 --interval 0.5',
        'UV_CACHE_DIR=.uv-cache uv run python experiments/mew-ghost/mew_wisp.py --format human --form cat --details',
        'UV_CACHE_DIR=.uv-cache uv run python experiments/mew-ghost/mew_wisp.py --format html --output /tmp/mew-ghost.html --watch-count 3 --interval 0.5',
        'UV_CACHE_DIR=.uv-cache uv run python experiments/mew-ghost/mew_wisp.py --format state --watch --interval 2',
        'UV_CACHE_DIR=.uv-cache uv run python experiments/mew-ghost/mew_wisp.py --desk-json experiments/mew-ghost/fixtures/sample_desk_view.json --format state',
        'UV_CACHE_DIR=.uv-cache uv run python experiments/mew-ghost/mew_wisp.py --format human --desk-json experiments/mew-ghost/fixtures/sample_desk_view.json',
        'UV_CACHE_DIR=.uv-cache uv run python experiments/mew-ghost/mew_wisp.py --format state --live-desk',
        'UV_CACHE_DIR=.uv-cache uv run python experiments/mew-ghost/mew_wisp.py --format html --output /tmp/mew-ghost-live-desk.html --live-desk --watch-count 2 --interval 1',
        'UV_CACHE_DIR=.uv-cache uv run python experiments/mew-ghost/mew_wisp.py --format state --live-active-window --watch-count 2',
        'UV_CACHE_DIR=.uv-cache uv run python experiments/mew-ghost/mew_wisp.py --format state --execute-launchers',
    ]
    assert all(not line.startswith('python experiments/mew-ghost/mew_wisp.py') for line in usage_lines)
    assert 'uv run python experiments/mew-ghost/ghost.py' not in readme
    assert '--watch-count N' in readme
    assert '--wisp' in readme
    assert '--format human' in readme
    assert '--form cat' in readme
    assert '--details' in readme
    assert 'compact mew-wisp terminal HUD' in readme
    assert 'diagnostic details' in readme
    assert 'coarse pixel cat converted from `cat.png`' in readme
    assert 'square white face with thick stepped black outline' in readme
    assert 'blocky pointed ears, vertical rectangular eyes, tiny square nose, slim standing body, two narrow legs/feet, and a large stepped curled right tail' in readme
    assert 'KeyboardInterrupt' in readme
    assert 'rewrites the same local HTML file' in readme


def test_source_stays_isolated_from_core_mew_and_live_state() -> None:
    source = GHOST_PATH.read_text(encoding='utf-8')

    assert 'import mew' not in source
    assert 'src/mew' not in source
    assert 'src.mew' not in source
    assert 'screen capture' in source
    assert 'hidden monitoring' in source
    assert '--live-active-window' in source
    assert '--execute-launchers' in source
    assert '--details' in source
    assert '--watch-count' in source
    assert '--wisp' in source
    assert '--interval' in source
    assert '--desk-json' in source
    assert '--live-desk' in source
    assert '--fixture-terminal' in source
    assert "choices=('html', 'state', 'human')" in source
    assert 'render_terminal_human' in source
    assert "SCHEMA_VERSION = 'mew-ghost.sp18.v1'" in source
    assert 'Standalone SP18 mew-ghost foreground watch-mode shell' in source
    assert "description='Run the mew-wisp resident terminal; ghost.py remains the compatibility implementation'" in source
    assert '<title>mew-wisp resident state (ghost.py compatibility render)</title>' in source
    assert '<h2>Resident state (ghost.py compatibility)</h2>' in source
    assert 'mew-ghost.sp17.v1' not in source
    assert 'sample_desk_view.json' in source
    assert "'desk', '--json'" in source
    assert 'mew desk --json' not in source
    assert 'background_monitoring' in source
    assert 'network' in source
    assert 'live_mew_reads' in source
