# mew-ghost SP13 shell scaffold

`mew-ghost` is an isolated side project for a permission-safe macOS presence shell. SP13 is fixture-driven by default and adds an explicit opt-in live macOS active-window probe: it does not import core mew code, read live `.mew` state, capture the screen, monitor hidden activity, use the network, or package a native app.

## What this slice provides

- `ghost.py`: a standalone Python entrypoint/module.
- `fixtures/sample_ghost_state.json`: deterministic input for ghost state and local HTML rendering.
- `tests/test_mew_ghost.py`: focused tests for fixture rendering, explicit live-probe fallbacks, CLI output, isolation, and dry-run launch intents.

## Permission-safe probe contract

`probe_active_window()` returns a structured object with:

- `status`: `available`, `unavailable`, or `permission_denied`
- `reason`: stable machine-readable fallback detail
- `platform`: detected or injected platform name
- `active_app`: app name or `null`
- `window_title`: window title or `null`
- `requires_permission`: whether Accessibility-style permission would be needed for a real macOS probe

Default rendering uses the fixture and does not perform live probing. `--live-active-window` explicitly opts into the macOS `osascript` provider. On non-macOS platforms the probe returns `unavailable` without calling the provider. On macOS, callers may inject a provider or runner; missing `osascript`, permission denial, empty output, malformed output, timeout, and other runner failures are converted into structured `status`/`reason` values instead of prompting, retrying, or reading hidden state.

## Dry-run launch intents

`build_launcher_intents()` returns command intents for:

- `mew chat`
- `mew code`

The intents are dry-run only. They describe what would be launched and never execute the commands.

## Usage

Render deterministic local HTML from the fixture:

```bash
UV_CACHE_DIR=.uv-cache uv run python experiments/mew-ghost/ghost.py --output /tmp/mew-ghost.html
```

Print deterministic JSON state:

```bash
UV_CACHE_DIR=.uv-cache uv run python experiments/mew-ghost/ghost.py --format state
```

Explicitly opt into the live macOS active-window probe and print the structured fallback/result:

```bash
UV_CACHE_DIR=.uv-cache uv run python experiments/mew-ghost/ghost.py --format state --live-active-window
```

Run the focused verifier:

```bash
UV_CACHE_DIR=.uv-cache uv run pytest --no-testmon -q experiments/mew-ghost/tests/test_mew_ghost.py
```
