# mew-desk

Small CLI-first experiment that maps mew state into a desktop-pet view model.

Outputs:

- `.mew/desk/YYYY-MM-DD.json`
- `.mew/desk/YYYY-MM-DD.md`
- a tiny terminal pet renderer for the same JSON view model
- a standalone browser pet renderer for the same JSON view model
- a local browser server that refreshes from a JSON file or command

This experiment still does not create a tray app or Tauri project. It answers
the next UI question first: can a dumb visual shell consume `mew desk --json`
without reading raw `.mew/state.json` or touching the resident runtime?
The view model can include a `primary_action` hint such as a reply or resume
command; the browser shell renders it as a copyable next move.

Pet states:

- `sleeping`: no active work or alert.
- `thinking`: runtime is planning.
- `typing`: runtime is applying/acting or a work session is active.
- `alerting`: unanswered questions or open attention exist.

## Usage

```bash
uv run python experiments/mew-desk/desk_state.py experiments/mew-desk/sample_state.json --output-dir /tmp/mew-desk
```

Generate from this repository's live mew state:

```bash
uv run python experiments/mew-desk/desk_state.py .mew/state.json --output-dir /tmp/mew-desk-real
```

Read the generated view model:

```bash
cat /tmp/mew-desk/.mew/desk/2026-04-17.json
```

Render the same view model as a terminal pet:

```bash
uv run python experiments/mew-desk/terminal_pet.py /tmp/mew-desk/.mew/desk/2026-04-17.json
```

Or pipe the core command directly:

```bash
uv run mew desk --json | uv run python experiments/mew-desk/terminal_pet.py -
```

Render a standalone browser view:

```bash
uv run mew desk --json | uv run python experiments/mew-desk/browser_pet.py - --output /tmp/mew-desk.html
```

Then open `/tmp/mew-desk.html` in a browser.

Continuously rewrite that HTML file atomically and skip unchanged output:

```bash
uv run python experiments/mew-desk/watch_browser_pet.py --output /tmp/mew-desk.html --source-command ./mew desk --json
```

Serve a refreshing local browser shell from a generated JSON file:

```bash
uv run python experiments/mew-desk/browser_server.py /tmp/mew-desk-browser/.mew/desk/2026-04-19.json
```

Or let the server call the core view-model command on each refresh:

```bash
uv run python experiments/mew-desk/browser_server.py --source-command ./mew desk --json
```

The server prints the local URL, usually `http://127.0.0.1:8765/`.
It rejects non-loopback Host headers and non-loopback binds by default because
the view model can contain private task context. Use `--allow-non-loopback`
only for an explicitly trusted network.

## Test

```bash
uv run pytest -q experiments/mew-desk
```
