# SP25 human watch rerender proof

Date: 2026-04-29
Scope: experiments/mew-ghost only

## Slice

Change mew-wisp human watch stdout so `--format human` with `--watch` / `--watch-count` and no `--output` repaints the same terminal surface instead of visually appending another full cat/HUD screen each iteration.

## Patch summary

- Adds ANSI cursor-home / clear-to-end controls before each no-output human watch render.
- Keeps `--output` behavior on the existing file-write plus JSONL watch-record path.
- Keeps non-human `state` and `html` watch stdout on the existing JSONL watch-record path.
- Adds a focused `watch_count=2` human cat regression that proves rerender controls are emitted and the current cat/HUD surface still renders.
- Adds preservation coverage for state JSONL, html JSONL, and human `--output` behavior.

## Safety boundary

The change is limited to `experiments/mew-ghost`. It does not add background monitoring, hidden capture, shell execution, launcher execution, networking, or changes to the state/html render payloads.

## Verifier

`UV_CACHE_DIR=.uv-cache uv run pytest --no-testmon -q experiments/mew-ghost/tests/test_mew_ghost.py`

Result: `46 passed in 0.04s`

Smoke: `MEW_GHOST_TERMINAL_WIDTH=80 UV_CACHE_DIR=.uv-cache uv run python experiments/mew-ghost/ghost.py --format human --form cat --watch-count 2 --interval 0` emitted the ANSI rerender prefix before both human cat frames.
