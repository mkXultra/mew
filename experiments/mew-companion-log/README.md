# mew-companion-log

An isolated experiment for rendering small markdown companion surfaces from a mew session fixture. This scaffold intentionally lives under `experiments/mew-companion-log` and does not edit core `src/mew` files.

## Files

- `companion_log.py` — standalone Python CLI/script that reads fixture JSON and renders markdown.
- `fixtures/sample_session.json` — sample session data used by the report, morning journal, evening journal, dream/learning, and static research digest commands/tests.
- `fixtures/sample_mew_state.json` — static mew-state-like sample used by the SP6 state brief; it is not loaded from live `.mew` state.
- `fixtures/sample_bundle.json` — static SP7 manifest that combines explicit local fixtures and companion surfaces into one bundle.
- `fixtures/sample_archive.json` — static SP8 multi-day archive manifest for indexing companion outputs without reading live state.
- `tests/test_companion_log.py` — focused pytest coverage for rendering, stdout, output-file writing, ordering/grouping, empty archive days, missing fixtures, and fixture shape.

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

Render the SP7 multi-fixture companion bundle from its static manifest:

```bash
UV_CACHE_DIR=.uv-cache uv run python experiments/mew-companion-log/companion_log.py experiments/mew-companion-log/fixtures/sample_bundle.json --mode bundle
```

Render the SP8 multi-day archive index from its static manifest:

```bash
UV_CACHE_DIR=.uv-cache uv run python experiments/mew-companion-log/companion_log.py experiments/mew-companion-log/fixtures/sample_archive.json --mode archive-index
```

Render the SP9 dogfood digest from static side-project dogfood rows and `[side-pj]` issue summaries:

```bash
UV_CACHE_DIR=.uv-cache uv run python experiments/mew-companion-log/companion_log.py experiments/mew-companion-log/fixtures/sample_dogfood_digest.json --mode dogfood-digest
```

Write markdown to a file:

```bash
UV_CACHE_DIR=.uv-cache uv run python experiments/mew-companion-log/companion_log.py experiments/mew-companion-log/fixtures/sample_session.json --output report.md
```

The output-file contract also works for alternate modes, including the static research digest, SP6 state brief, SP7 bundle, SP8 archive index, and SP9 dogfood digest:

```bash
UV_CACHE_DIR=.uv-cache uv run python experiments/mew-companion-log/companion_log.py experiments/mew-companion-log/fixtures/sample_session.json --mode research-digest --output research-digest.md
UV_CACHE_DIR=.uv-cache uv run python experiments/mew-companion-log/companion_log.py experiments/mew-companion-log/fixtures/sample_mew_state.json --mode state-brief --output state-brief.md
UV_CACHE_DIR=.uv-cache uv run python experiments/mew-companion-log/companion_log.py experiments/mew-companion-log/fixtures/sample_bundle.json --mode bundle --output companion-bundle.md
UV_CACHE_DIR=.uv-cache uv run python experiments/mew-companion-log/companion_log.py experiments/mew-companion-log/fixtures/sample_archive.json --mode archive-index --output companion-archive-index.md
UV_CACHE_DIR=.uv-cache uv run python experiments/mew-companion-log/companion_log.py experiments/mew-companion-log/fixtures/sample_dogfood_digest.json --mode dogfood-digest --output dogfood-digest.md
```

## Verify

Run the focused side-project tests:

```bash
UV_CACHE_DIR=.uv-cache uv run pytest --no-testmon -q experiments/mew-companion-log/tests/test_companion_log.py
```

The script uses only the Python standard library. The research digest uses only static fixture data, the state brief uses only `fixtures/sample_mew_state.json` rather than live `.mew` state, the bundle mode reads only explicit local fixture paths declared by `fixtures/sample_bundle.json`, the archive index reads only `fixtures/sample_archive.json` while listing explicit archived fixture paths, and the dogfood digest reads only `fixtures/sample_dogfood_digest.json` while summarizing static dogfood rows and `[side-pj]` issue summaries.
