# mew-ghost SP16 watch mode

`mew-ghost` is an isolated side project for a permission-safe macOS presence shell. SP16 keeps the fixture-driven and dry-run defaults, preserves `--live-active-window` as the only live active-window opt-in, and adds a foreground watch mode that can refresh CLI records and local HTML output continuously. Direct launcher execution remains available only behind the explicit `--execute-launchers` CLI opt-in.

The shell does not import core mew code, read live `.mew` state, capture the screen, monitor hidden activity, use the network, or package a native app.

## What this slice provides

- `ghost.py`: a standalone Python entrypoint/module.
- `fixtures/sample_ghost_state.json`: deterministic input for ghost state, presence classification, and local HTML rendering.
- `tests/test_mew_ghost.py`: focused tests for fixture rendering, foreground watch output, repeated HTML rewrites, explicit live-probe fallbacks, launcher dry-run/execution gating, isolation, and README usage.

## Foreground watch contract

Single renders still build one local state/HTML document and then stop. Watch mode is explicit foreground work:

- `--watch-count N` performs exactly `N` bounded iterations and exits.
- `--watch` without `--watch-count` runs in the foreground until `KeyboardInterrupt`.
- `--interval SECONDS` controls the sleep between iterations.
- Tests can inject the sleeper, clock, probe provider, and launcher runner.
- Every iteration reloads the fixture, rebuilds state, reruns the selected probe path, and emits one newline-delimited CLI JSON record.
- With `--format html --output PATH`, each iteration rewrites the same local HTML file with freshness metadata for that iteration.

Watch mode does not create a daemon, background monitor, hidden capture loop, network connection, or live `.mew` reader.

## Presence states

`classify_presence()` maps fixture task/app/window inputs into visual/presence states:

- `idle`: no active surface is available.
- `attentive`: an active non-coding surface is available.
- `coding`: coding tools, coding task metadata, terminal, or source-file windows are active.
- `waiting`: the task/window text indicates waiting, pending review, or pause.
- `blocked`: the live probe is permission-denied or task state is blocked/error.

## Permission-safe probe contract

Default rendering uses the fixture and does not perform live probing. `--live-active-window` explicitly opts into the macOS `osascript` provider. On non-macOS platforms the probe returns `unavailable` without calling the provider. On macOS, callers may inject a provider or runner; missing `osascript`, permission denial, empty output, malformed output, timeout, and other runner failures are converted into structured `status`/`reason` values instead of prompting, retrying, or reading hidden state.

## Launcher contract

`build_launcher_intents()` returns command intents for `mew chat` and `mew code`. Dry-run is the default: launcher commands include `dry_run: true`, `side_effects: none`, and execution status `dry_run`; no subprocess is spawned.

Direct execution requires `--execute-launchers`. That flag switches the intents to `dry_run: false` and runs only the two explicit command arrays. Tests use an injected runner so the test suite never spawns real `mew` subprocesses.

## Usage

Render deterministic local HTML from the fixture. This is the safe dry-run path and never launches `mew`:

```bash
UV_CACHE_DIR=.uv-cache uv run python experiments/mew-ghost/ghost.py --output /tmp/mew-ghost.html
```

Print three bounded foreground watch records as newline-delimited JSON:

```bash
UV_CACHE_DIR=.uv-cache uv run python experiments/mew-ghost/ghost.py --format state --watch-count 3 --interval 0.5
```

Rewrite local HTML on every bounded watch iteration and emit one CLI record per rewrite:

```bash
UV_CACHE_DIR=.uv-cache uv run python experiments/mew-ghost/ghost.py --format html --output /tmp/mew-ghost.html --watch-count 3 --interval 0.5
```

Run foreground watch until interrupted by the operator:

```bash
UV_CACHE_DIR=.uv-cache uv run python experiments/mew-ghost/ghost.py --format state --watch --interval 2
```

Explicitly opt into the live macOS active-window probe while keeping the watch bounded:

```bash
UV_CACHE_DIR=.uv-cache uv run python experiments/mew-ghost/ghost.py --format state --live-active-window --watch-count 2
```

Explicitly opt into direct launcher execution for local macOS dogfood. This runs `mew chat` and `mew code`; omit the flag to stay in dry-run mode:

```bash
UV_CACHE_DIR=.uv-cache uv run python experiments/mew-ghost/ghost.py --format state --execute-launchers
```

Run the focused verifier:

```bash
UV_CACHE_DIR=.uv-cache uv run pytest --no-testmon -q experiments/mew-ghost/tests/test_mew_ghost.py
```
