# mew-ghost SP18 live desk opt-in

`mew-ghost` is an isolated side project for a permission-safe macOS presence shell. SP18 keeps the fixture-driven and dry-run defaults, preserves `--live-active-window` as the only live active-window opt-in, keeps `--desk-json` fixture-only, and adds explicit `--live-desk` for repo-local live desk JSON. Direct launcher execution remains available only behind the explicit `--execute-launchers` CLI opt-in, and desk `primary_action` is always surfaced as a dry-run intent.

The shell does not import core mew code, read live `.mew` state unless `--live-desk` is provided, run a desk command unless explicitly requested, capture the screen, monitor hidden activity, use the network, or package a native app.

## What this slice provides

- `ghost.py`: a standalone Python entrypoint/module.
- `fixtures/sample_ghost_state.json`: deterministic input for ghost state, active-window classification, presence classification, and local HTML rendering.
- `fixtures/sample_desk_view.json`: deterministic desk view-model input for `--desk-json` status/counts/details/primary_action rendering.
- `tests/test_mew_ghost.py`: focused tests for fixture rendering, foreground watch output, repeated HTML rewrites, explicit live-probe fallbacks, launcher dry-run/execution gating, desk fixture mapping, isolation, and README usage.

## Fixture-only desk bridge

`--desk-json PATH` loads a static desk view-model fixture. It never invokes a live desk command and never reads live `.mew` state. Watch mode reloads the desk fixture on every iteration so local dogfood can rewrite the JSON file and observe refreshed desk status without a background daemon.

`--live-desk` is the separate live opt-in. It runs repo-local `./mew desk --json` as an argument list with no shell, uses a short timeout, normalizes successful output through the same status/count/detail/primary_action surface, and converts missing command, nonzero exit, timeout, malformed JSON, or non-object JSON into structured fallback desk states. Default renders and `--desk-json` renders remain deterministic and non-live.

Desk pet states are mapped into ghost presence metadata without replacing the active-window classification path:

- `sleeping` → `idle`
- `thinking` → `attentive`
- `typing` → `coding`
- `alerting` → `waiting`

The rendered state includes `desk.status`, `desk.counts`, `desk.details`, `desk.primary_action`, and `presence.desk`. The HTML output adds a Desk bridge section with the same status/count/action details.

## Foreground watch contract

Single renders still build one local state/HTML document and then stop. Watch mode is explicit foreground work:

- `--watch-count N` performs exactly `N` bounded iterations and exits.
- `--watch` without `--watch-count` runs in the foreground until `KeyboardInterrupt`.
- `--interval SECONDS` controls the sleep between iterations.
- Tests can inject the sleeper, clock, probe provider, and launcher runner.
- Every iteration reloads the ghost fixture and optional desk fixture or opted-in live desk status, rebuilds state, and reruns the selected probe path.
- With `--format state`, stdout remains newline-delimited JSONL watch records.
- With `--format human` and no `--output`, stdout prints the terminal-first human surface for each iteration instead of JSONL watch records.
- With `--format html --output PATH`, each iteration rewrites the same local HTML file with freshness metadata for that iteration.

Watch mode does not create a daemon, background monitor, hidden capture loop, or network connection. Live desk reads occur only during foreground `--live-desk` renders.

## Presence states

`classify_presence()` maps fixture task/app/window inputs into visual/presence states:

- `idle`: no active surface is available.
- `attentive`: an active non-coding surface is available.
- `coding`: coding tools, coding task metadata, terminal, or source-file windows are active.
- `waiting`: the task/window text indicates waiting, pending review, or pause.
- `blocked`: the live probe is permission-denied or task state is blocked/error.

Desk-derived presence is exposed separately under `presence.desk` so the active-window classification remains visible and unchanged.

## Permission-safe probe contract

Default rendering uses fixtures and does not perform live probing. `--live-active-window` explicitly opts into the macOS `osascript` provider. On non-macOS platforms the probe returns `unavailable` without calling the provider. On macOS, callers may inject a provider or runner; missing `osascript`, permission denial, empty output, malformed output, timeout, and other runner failures are converted into structured `status`/`reason` values instead of prompting, retrying, or reading hidden state.

## Launcher contract

`build_launcher_intents()` returns command intents for `mew chat` and `mew code`. Dry-run is the default: launcher commands include `dry_run: true`, `side_effects: none`, and execution status `dry_run`; no subprocess is spawned.

When `--desk-json` contains a `primary_action`, it is exposed beside those intents as `desk-primary-action`. That desk action is fixture evidence only: it remains `dry_run: true`, `side_effects: none`, `executable: false`, and is not executed even when `--execute-launchers` is set.

Direct execution requires `--execute-launchers`. That flag switches only the two explicit local launcher command arrays, `mew chat` and `mew code`, to executable mode. Tests use an injected runner so the test suite never spawns real `mew` subprocesses.

## Usage

Render deterministic local HTML from the fixture. This is the safe dry-run path and never launches `mew`:

```bash
UV_CACHE_DIR=.uv-cache uv run python experiments/mew-ghost/ghost.py --output /tmp/mew-ghost.html
```

Print three bounded foreground watch records as newline-delimited JSON:

```bash
UV_CACHE_DIR=.uv-cache uv run python experiments/mew-ghost/ghost.py --format state --watch-count 3 --interval 0.5
```

Print two bounded foreground watch iterations as the terminal-first human surface, without JSONL records:

```bash
UV_CACHE_DIR=.uv-cache uv run python experiments/mew-ghost/ghost.py --format human --watch-count 2 --interval 0.5
```

Render the same bounded human watch as the cat terminal form, with a literal 22x24 block-cell coarse pixel cat converted from `cat.png` (derived by thresholding the repo-root reference mask; each black cell renders as `██`, each white cell as two spaces). The sprite keeps the square white face with thick stepped black outline, blocky pointed ears, vertical rectangular eyes, tiny square nose, slim standing body, two narrow legs/feet, and a large stepped curled right tail; presence state markers render on a separate line outside the 22x24 silhouette:

```bash
UV_CACHE_DIR=.uv-cache uv run python experiments/mew-ghost/ghost.py --format human --form cat --watch-count 2 --interval 0.5
```

Rewrite local HTML on every bounded watch iteration and emit one CLI record per rewrite:

```bash
UV_CACHE_DIR=.uv-cache uv run python experiments/mew-ghost/ghost.py --format html --output /tmp/mew-ghost.html --watch-count 3 --interval 0.5
```

Run foreground watch until interrupted by the operator:

```bash
UV_CACHE_DIR=.uv-cache uv run python experiments/mew-ghost/ghost.py --format state --watch --interval 2
```

Load the static desk fixture and render desk status/counts/details/primary_action into CLI state:

```bash
UV_CACHE_DIR=.uv-cache uv run python experiments/mew-ghost/ghost.py --desk-json experiments/mew-ghost/fixtures/sample_desk_view.json --format state
```

Render the static desk fixture as terminal-first human text for an operator console:

```bash
UV_CACHE_DIR=.uv-cache uv run python experiments/mew-ghost/ghost.py --format human --desk-json experiments/mew-ghost/fixtures/sample_desk_view.json
```

Explicitly opt into live repo-local desk JSON for one terminal state render:

```bash
UV_CACHE_DIR=.uv-cache uv run python experiments/mew-ghost/ghost.py --format state --live-desk
```

Explicitly opt into live desk state while rewriting local HTML in bounded foreground watch:

```bash
UV_CACHE_DIR=.uv-cache uv run python experiments/mew-ghost/ghost.py --format html --output /tmp/mew-ghost-live-desk.html --live-desk --watch-count 2 --interval 1
```

Explicitly opt into the live macOS active-window probe while keeping the watch bounded:

```bash
UV_CACHE_DIR=.uv-cache uv run python experiments/mew-ghost/ghost.py --format state --live-active-window --watch-count 2
```

Explicitly opt into direct launcher execution for local macOS dogfood. This runs only `mew chat` and `mew code`; omit the flag to stay in dry-run mode, and desk primary_action remains non-executable either way:

```bash
UV_CACHE_DIR=.uv-cache uv run python experiments/mew-ghost/ghost.py --format state --execute-launchers
```

Run the focused verifier:

```bash
UV_CACHE_DIR=.uv-cache uv run pytest --no-testmon -q experiments/mew-ghost/tests/test_mew_ghost.py
```
