# mew-companion-log

An isolated experiment for rendering a small markdown companion report from a mew session fixture. This scaffold intentionally lives under `experiments/mew-companion-log` and does not edit core `src/mew` files.

## Files

- `companion_log.py` — standalone Python CLI/script that reads fixture JSON and renders markdown.
- `fixtures/sample_session.json` — sample session data used by the first command and tests.
- `tests/test_companion_log.py` — focused pytest coverage for rendering, stdout, output-file writing, and fixture shape.

## Usage

Print a report to stdout:

```bash
UV_CACHE_DIR=.uv-cache uv run python experiments/mew-companion-log/companion_log.py experiments/mew-companion-log/fixtures/sample_session.json
```

Write a report to a file:

```bash
UV_CACHE_DIR=.uv-cache uv run python experiments/mew-companion-log/companion_log.py experiments/mew-companion-log/fixtures/sample_session.json --output report.md
```

## Verify

Run the focused side-project tests:

```bash
UV_CACHE_DIR=.uv-cache uv run pytest --no-testmon -q experiments/mew-companion-log/tests/test_companion_log.py
```

The script uses only the Python standard library.
