# mew-ghost SP15 launcher contract

`mew-ghost` is an isolated side project for a permission-safe macOS presence shell. SP15 remains fixture-driven and dry-run by default, keeps the bounded deterministic presence loop, and represents `mew chat` and `mew code` as explicit launcher commands. Direct launcher execution is available only behind the explicit `--execute-launchers` CLI opt-in. The shell does not import core mew code, read live `.mew` state, capture the screen, monitor hidden activity, use the network, or package a native app.

## What this slice provides

- `ghost.py`: a standalone Python entrypoint/module.
- `fixtures/sample_ghost_state.json`: deterministic input for ghost state, presence classification, and local HTML rendering.
- `tests/test_mew_ghost.py`: focused tests for fixture rendering, presence transitions, stable refresh snapshots, explicit live-probe fallbacks, launcher dry-run/execution gating, CLI output, isolation, and README usage.

## Presence refresh contract

Default rendering is local and fixture-safe. A render builds a bounded list of deterministic snapshots in-process and then stops. There is no background loop, hidden capture, screen capture, network access, live `.mew` read, or watcher.

`build_presence_loop()` maps the fixture task/app/window inputs into visual/presence states:

- `idle`: no active surface is available.
- `attentive`: an active non-coding surface is available.
- `coding`: coding tools, coding task metadata, terminal, or source-file windows are active.
- `waiting`: the task/window text indicates waiting, pending review, or pause.
- `blocked`: the live probe is permission-denied or task state is blocked/error.

The CLI option `--refresh-count` controls how many snapshots are rendered and is clamped to a fixed local bound. Every snapshot is derived from the same fixture/probe input and stable fixture timestamp, so repeated renders produce identical state and HTML.

## Permission-safe probe contract

`probe_active_window()` returns a structured object with:

- `status`: `available`, `unavailable`, or `permission_denied`
- `reason`: stable machine-readable fallback detail
- `platform`: detected or injected platform name
- `active_app`: app name or `null`
- `window_title`: window title or `null`
- `requires_permission`: whether Accessibility-style permission would be needed for a real macOS probe

Default rendering uses the fixture and does not perform live probing. `--live-active-window` explicitly opts into the macOS `osascript` provider. On non-macOS platforms the probe returns `unavailable` without calling the provider. On macOS, callers may inject a provider or runner; missing `osascript`, permission denial, empty output, malformed output, timeout, and other runner failures are converted into structured `status`/`reason` values instead of prompting, retrying, or reading hidden state.

## Launcher contract

`build_launcher_intents()` returns command intents for:

- `mew chat`
- `mew code`

Dry-run is the default. Default state includes both launcher commands with `dry_run: true`, `side_effects: "none"`, and an execution status of `dry_run`; no subprocess is spawned.

Direct execution requires `--execute-launchers`. That flag switches the intents to `dry_run: false` and runs only the two explicit command arrays. Tests use an injected runner so the test suite never spawns real `mew` subprocesses.

## Usage

Render deterministic local HTML from the fixture. This is the safe dry-run path and never launches `mew`:

```bash
UV_CACHE_DIR=.uv-cache uv run python experiments/mew-ghost/ghost.py --output /tmp/mew-ghost.html
```

Print deterministic JSON state with five bounded refresh snapshots:

```bash
UV_CACHE_DIR=.uv-cache uv run python experiments/mew-ghost/ghost.py --format state --refresh-count 5
```

Explicitly opt into the live macOS active-window probe and print the structured fallback/result:

```bash
UV_CACHE_DIR=.uv-cache uv run python experiments/mew-ghost/ghost.py --format state --live-active-window
```

Explicitly opt into direct launcher execution for local macOS dogfood. This runs `mew chat` and `mew code`; omit the flag to stay in dry-run mode:

```bash
UV_CACHE_DIR=.uv-cache uv run python experiments/mew-ghost/ghost.py --format state --execute-launchers
```

Run the focused verifier:

```bash
UV_CACHE_DIR=.uv-cache uv run pytest --no-testmon -q experiments/mew-ghost/tests/test_mew_ghost.py
```
