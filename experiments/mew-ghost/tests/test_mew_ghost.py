from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README_PATH = ROOT / 'README.md'
GHOST_PATH = ROOT / 'ghost.py'
FIXTURE_PATH = ROOT / 'fixtures' / 'sample_ghost_state.json'

spec = importlib.util.spec_from_file_location('mew_ghost_sp16', GHOST_PATH)
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
    assert state_one['schema_version'] == 'mew-ghost.sp16.v1'
    assert state_one['active_window']['status'] == 'available'
    assert state_one['active_window']['active_app'] == 'Visual Studio Code'
    assert state_one['presence']['classification']['state'] == 'coding'
    assert [snapshot['presence_state'] for snapshot in state_one['presence']['snapshots']] == ['coding', 'coding', 'coding']
    assert 'Ghost is watching VS Code without screen capture.' in html_one
    assert 'Writing the SP12 scaffold' in html_one
    assert 'mew-ghost.sp16.v1' in html_one
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
        'schema_version': 'mew-ghost.sp16.v1',
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


def test_cli_writes_local_html_and_state_from_fixture(tmp_path: Path) -> None:
    html_output = tmp_path / 'ghost.html'
    state_output = tmp_path / 'ghost-state.json'

    assert ghost.main(['--fixture', str(FIXTURE_PATH), '--output', str(html_output), '--refresh-count', '2']) == 0
    assert ghost.main(['--fixture', str(FIXTURE_PATH), '--format', 'state', '--output', str(state_output), '--refresh-count', '2']) == 0

    html = html_output.read_text(encoding='utf-8')
    state = json.loads(state_output.read_text(encoding='utf-8'))

    assert html.startswith('<!doctype html>')
    assert '<title>mew-ghost SP16 watch mode</title>' in html
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


def test_readme_usage_prefers_uv_run_python_commands() -> None:
    readme = README_PATH.read_text(encoding='utf-8')
    usage_lines = [line.strip() for line in readme.splitlines() if 'experiments/mew-ghost/ghost.py' in line]

    assert usage_lines == [
        'UV_CACHE_DIR=.uv-cache uv run python experiments/mew-ghost/ghost.py --output /tmp/mew-ghost.html',
        'UV_CACHE_DIR=.uv-cache uv run python experiments/mew-ghost/ghost.py --format state --watch-count 3 --interval 0.5',
        'UV_CACHE_DIR=.uv-cache uv run python experiments/mew-ghost/ghost.py --format html --output /tmp/mew-ghost.html --watch-count 3 --interval 0.5',
        'UV_CACHE_DIR=.uv-cache uv run python experiments/mew-ghost/ghost.py --format state --watch --interval 2',
        'UV_CACHE_DIR=.uv-cache uv run python experiments/mew-ghost/ghost.py --format state --live-active-window --watch-count 2',
        'UV_CACHE_DIR=.uv-cache uv run python experiments/mew-ghost/ghost.py --format state --execute-launchers',
    ]
    assert all(not line.startswith('python experiments/mew-ghost/ghost.py') for line in usage_lines)
    assert '--watch-count N' in readme
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
    assert '--watch-count' in source
    assert '--interval' in source
    assert 'background_monitoring' in source
    assert 'network' in source
    assert 'live_mew_reads' in source
