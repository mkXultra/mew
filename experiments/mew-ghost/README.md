# mew-wisp SP26 default live human terminal

`mew_wisp.py` is the product-named Python entrypoint for the isolated `mew-wisp` side project; `ghost.py` remains the historical implementation module for compatibility. SP26 makes the normal user-facing human terminal/cat path prefer foreground repo-local live desk state by default, while `--fixture-terminal` keeps deterministic fixture display available for tests, docs, and smoke proof. Machine-readable `state`/`html` surfaces keep their explicit `--live-desk` opt-in, `--desk-json` remains fixture-only, direct launcher execution stays behind `--execute-launchers`, and desk `primary_action` is always surfaced as a dry-run intent.

The shell does not import core mew code, read live `.mew` state for machine-readable `state`/`html` renders unless `--live-desk` is provided, run a hidden desk command, capture the screen, monitor hidden activity, use the network, or package a native app. Default human/cat live reads are foreground repo-local `./mew desk --json` reads and can be replaced with deterministic fixture display by passing `--fixture-terminal`.

## What this slice provides

- `mew_wisp.py`: the product-named Python entrypoint for operators; it delegates to `ghost.py` without duplicating CLI logic.
- `ghost.py`: the historical standalone implementation module retained for compatibility.
- `fixtures/sample_ghost_state.json`: deterministic input for ghost state, active-window classification, presence classification, and local HTML rendering.
- `fixtures/sample_desk_view.json`: deterministic desk view-model input for `--desk-json` status/counts/details/primary_action rendering.
- `tests/test_mew_ghost.py`: focused tests for fixture rendering, foreground watch output, repeated HTML rewrites, explicit live-probe fallbacks, launcher dry-run/execution gating, desk fixture mapping, isolation, and README usage.

## Fixture-only desk bridge

`--desk-json PATH` loads a static desk view-model fixture. It never invokes a live desk command and never reads live `.mew` state. Watch mode reloads the desk fixture on every iteration so local dogfood can rewrite the JSON file and observe refreshed desk status without a background daemon.

`--live-desk` is the separate live opt-in for machine-readable `state` and `html` output. It runs repo-local `./mew desk --json` as an argument list with no shell, uses a short timeout, normalizes successful output through the same status/count/detail/primary_action surface, and converts missing command, nonzero exit, timeout, malformed JSON, or non-object JSON into structured fallback desk states. Human terminal and cat renders use that same foreground repo-local live read by default; pass `--fixture-terminal` to keep deterministic fixture display. Default `state`/`html` renders and `--desk-json` renders remain deterministic and non-live.

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
- Every iteration reloads the ghost fixture and optional desk fixture, explicit
  state/html live desk status, or default human terminal live desk status,
  rebuilds state, and reruns the selected probe path.
- With `--format state`, stdout remains newline-delimited JSONL watch records.
- With `--format human` and no `--output`, stdout prints the terminal-first human surface for each iteration instead of JSONL watch records.
- With `--format html --output PATH`, each iteration rewrites the same local HTML file with freshness metadata for that iteration.

Watch mode does not create a daemon, background monitor, hidden capture loop, or
network connection. Live desk reads occur only during foreground human terminal
renders or explicit foreground `--live-desk` state/html renders.

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

Start the product-named resident cat HUD with omitted mode/form/watch intent. This is an explicit foreground watch, performs only foreground repo-local live desk reads, and exits cleanly on `KeyboardInterrupt`:

```bash
UV_CACHE_DIR=.uv-cache uv run python experiments/mew-ghost/mew_wisp.py
```

Render deterministic local HTML from the fixture with explicit `--output`. This keeps the historical HTML default and never launches `mew`:

```bash
UV_CACHE_DIR=.uv-cache uv run python experiments/mew-ghost/mew_wisp.py --output /tmp/mew-ghost.html
```

Print three bounded foreground watch records as newline-delimited JSON:

```bash
UV_CACHE_DIR=.uv-cache uv run python experiments/mew-ghost/mew_wisp.py --format state --watch-count 3 --interval 0.5
```

Start the named mew-wisp resident preset. `--wisp` expands omitted options to the live human cat foreground watch surface (`--format human --form cat --watch`) while explicit `--format`, `--form`, and `--watch-count` choices still win; the example below stays bounded for tests and demos:

```bash
UV_CACHE_DIR=.uv-cache uv run python experiments/mew-ghost/mew_wisp.py --wisp --watch-count 2 --interval 0.5
```

Print two bounded foreground watch iterations as the compact mew-wisp terminal HUD. Normal human terminal output reads repo-local live desk state by default, stays in the foreground, and does not emit JSONL records or diagnostic details:

```bash
UV_CACHE_DIR=.uv-cache uv run python experiments/mew-ghost/mew_wisp.py --format human --watch-count 2 --interval 0.5
```

Keep the same human terminal surface on deterministic fixture display for tests, docs, and smoke proof:

```bash
UV_CACHE_DIR=.uv-cache uv run python experiments/mew-ghost/mew_wisp.py --format human --fixture-terminal --watch-count 2 --interval 0.5
```

Render the bounded compact human watch as the cat terminal form, with a literal 22x24 block-cell coarse pixel cat converted from `cat.png` (derived by thresholding the repo-root reference mask; each black cell renders as `██`, each white cell as two spaces). The sprite keeps the square white face with thick stepped black outline, blocky pointed ears, vertical rectangular eyes, tiny square nose, slim standing body, two narrow legs/feet, and a large stepped curled right tail; presence state markers render on a separate line outside the 22x24 silhouette. Freshness, desk counts/details, active-window reason, and launcher intents stay hidden unless `--details` is requested:

```bash
UV_CACHE_DIR=.uv-cache uv run python experiments/mew-ghost/mew_wisp.py --format human --form cat --watch-count 2 --interval 0.5
```

Show the expanded human diagnostic details when debugging the compact HUD:

```bash
UV_CACHE_DIR=.uv-cache uv run python experiments/mew-ghost/mew_wisp.py --format human --form cat --details
```

Rewrite local HTML on every bounded watch iteration and emit one CLI record per rewrite:

```bash
UV_CACHE_DIR=.uv-cache uv run python experiments/mew-ghost/mew_wisp.py --format html --output /tmp/mew-ghost.html --watch-count 3 --interval 0.5
```

Run foreground watch until interrupted by the operator:

```bash
UV_CACHE_DIR=.uv-cache uv run python experiments/mew-ghost/mew_wisp.py --format state --watch --interval 2
```

Load the static desk fixture and render desk status/counts/details/primary_action into CLI state:

```bash
UV_CACHE_DIR=.uv-cache uv run python experiments/mew-ghost/mew_wisp.py --desk-json experiments/mew-ghost/fixtures/sample_desk_view.json --format state
```

Render the static desk fixture as terminal-first human text for an operator console:

```bash
UV_CACHE_DIR=.uv-cache uv run python experiments/mew-ghost/mew_wisp.py --format human --desk-json experiments/mew-ghost/fixtures/sample_desk_view.json
```

Explicitly opt into live repo-local desk JSON for one machine-readable state render:

```bash
UV_CACHE_DIR=.uv-cache uv run python experiments/mew-ghost/mew_wisp.py --format state --live-desk
```

Explicitly opt into live desk state while rewriting local HTML in bounded foreground watch:

```bash
UV_CACHE_DIR=.uv-cache uv run python experiments/mew-ghost/mew_wisp.py --format html --output /tmp/mew-ghost-live-desk.html --live-desk --watch-count 2 --interval 1
```

Explicitly opt into the live macOS active-window probe while keeping the watch bounded:

```bash
UV_CACHE_DIR=.uv-cache uv run python experiments/mew-ghost/mew_wisp.py --format state --live-active-window --watch-count 2
```

Explicitly opt into direct launcher execution for local macOS dogfood. This runs only `mew chat` and `mew code`; omit the flag to stay in dry-run mode, and desk primary_action remains non-executable either way:

```bash
UV_CACHE_DIR=.uv-cache uv run python experiments/mew-ghost/mew_wisp.py --format state --execute-launchers
```

Run the focused verifier:

```bash
UV_CACHE_DIR=.uv-cache uv run pytest --no-testmon -q experiments/mew-ghost/tests/test_mew_ghost.py
```
