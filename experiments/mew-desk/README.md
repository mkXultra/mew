# mew-desk

Small CLI-first experiment that maps mew state into a desktop-pet view model.

Outputs:

- `.mew/desk/YYYY-MM-DD.json`
- `.mew/desk/YYYY-MM-DD.md`
- a tiny terminal pet renderer for the same JSON view model

This first slice does not create a window, tray app, or Tauri project. It only
answers the question a future desktop shell needs first: what should the pet
look like right now?

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

## Test

```bash
uv run pytest -q experiments/mew-desk
```
