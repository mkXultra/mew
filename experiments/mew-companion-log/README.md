# mew-companion-log

An isolated experiment for rendering small markdown companion surfaces from a mew session fixture. This scaffold intentionally lives under `experiments/mew-companion-log` and does not edit core `src/mew` files.

## Files

- `companion_log.py` — standalone Python CLI/script that reads fixture JSON and renders markdown.
- `fixtures/sample_session.json` — sample session data used by the report, morning journal, evening journal, dream/learning, and static research digest commands/tests.
- `fixtures/sample_mew_state.json` — static mew-state-like sample used by the SP6 state brief; it is not loaded from live `.mew` state.
- `tests/test_companion_log.py` — focused pytest coverage for rendering, stdout, output-file writing, and fixture shape.

## Usage

Print the default companion report to stdout:

```bash
UV_CACHE_DIR=.uv-cache uv run python experiments/mew-companion-log/companion_log.py experiments/mew-companion-log/fixtures/sample_session.json
```

Render the SP2 morning journal surface from the same fixture:

```bash
UV_CACHE_DIR=.uv-cache uv run python experiments/mew-companion-log/companion_log.py experiments/mew-companion-log/fixtures/sample_session.json --mode morning-journal
```

Render the SP2 evening journal surface from the same fixture:

```bash
UV_CACHE_DIR=.uv-cache uv run python experiments/mew-companion-log/companion_log.py experiments/mew-companion-log/fixtures/sample_session.json --mode evening-journal
```

Render the SP2 dream/learning surface from the same fixture:

```bash
UV_CACHE_DIR=.uv-cache uv run python experiments/mew-companion-log/companion_log.py experiments/mew-companion-log/fixtures/sample_session.json --mode dream-learning
```

Render the SP4 static research digest from fixture feed entries:

```bash
UV_CACHE_DIR=.uv-cache uv run python experiments/mew-companion-log/companion_log.py experiments/mew-companion-log/fixtures/sample_session.json --mode research-digest
```

Render the SP6 state brief from a static mew-state-like fixture:

```bash
UV_CACHE_DIR=.uv-cache uv run python experiments/mew-companion-log/companion_log.py experiments/mew-companion-log/fixtures/sample_mew_state.json --mode state-brief
```

Write markdown to a file:

```bash
UV_CACHE_DIR=.uv-cache uv run python experiments/mew-companion-log/companion_log.py experiments/mew-companion-log/fixtures/sample_session.json --output report.md
```

The output-file contract also works for alternate modes, including the static research digest and SP6 state brief:

```bash
UV_CACHE_DIR=.uv-cache uv run python experiments/mew-companion-log/companion_log.py experiments/mew-companion-log/fixtures/sample_session.json --mode research-digest --output research-digest.md
UV_CACHE_DIR=.uv-cache uv run python experiments/mew-companion-log/companion_log.py experiments/mew-companion-log/fixtures/sample_mew_state.json --mode state-brief --output state-brief.md
```

## Verify

Run the focused side-project tests:

```bash
UV_CACHE_DIR=.uv-cache uv run pytest --no-testmon -q experiments/mew-companion-log/tests/test_companion_log.py
```

The script uses only the Python standard library. The research digest uses only static fixture data, and the state brief uses only `fixtures/sample_mew_state.json` rather than live `.mew` state.
